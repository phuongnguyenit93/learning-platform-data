# Hot standby, truy vấn chỉ đọc và xung đột phục hồi trong PostgreSQL

Hot standby cho phép một PostgreSQL standby server phục vụ các truy vấn chỉ đọc trong khi liên tục replay WAL từ primary. Nhờ đó, hệ thống có thể dùng standby cho báo cáo, tra cứu, phân tích và giảm tải truy vấn đọc trên primary, đồng thời duy trì một bản sao sẵn sàng cho failover.

Tuy nhiên, standby vừa phải phục vụ query vừa phải áp dụng các thay đổi đã ghi trong WAL. Một truy vấn đọc có thể đang giữ snapshot, lock hoặc buffer pin mà thao tác replay cần để tiếp tục. Khi hai hoạt động xung đột, PostgreSQL phải cân bằng giữa thời gian phản hồi của query và độ trễ replay. Đây là **recovery conflict**.

~~~text
                 Primary PostgreSQL
                 ------------------
                 INSERT / UPDATE / DELETE
                           |
                           v
                     WAL records
                           |
                  Streaming replication
                           |
                           v
                 Standby PostgreSQL
                 ------------------
                    WAL receiver
                           |
                           v
                    Startup process
                     replay WAL
                           |
              +------------+------------+
              |                         |
              v                         v
       Read-only queries          Recovery actions
       SELECT/reporting           VACUUM cleanup
       analytics                  DROP/TRUNCATE
              |                   AccessExclusive lock
              |                         |
              +------------+------------+
                           |
                     Conflict manager
                           |
              +------------+------------+
              |                         |
              v                         v
        Wait for query             Cancel query
        within delay               to replay WAL
              |
              v
       Replay continues
~~~

Một standby có thể trả lời query thành công trong phần lớn thời gian nhưng vẫn hủy một truy vấn dài khi WAL replay cần tiến lên. Vì vậy, ứng dụng đọc trên standby phải chấp nhận khả năng query bị hủy, biết retry an toàn và theo dõi cả replication lag lẫn recovery conflicts.

Bài này thuộc chương **Sao chép vật lý** của module *Database Engine Relational PostgreSQL*, tập trung vào chế độ hot standby, giới hạn truy vấn chỉ đọc, các loại xung đột phục hồi, cách PostgreSQL xử lý conflict và cách vận hành standby cho workload đọc.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích hot standby và phân biệt với warm standby hoặc streaming replication không phục vụ query.
2. Mô tả cách standby nhận WAL và replay WAL trong khi xử lý truy vấn.
3. Hiểu vì sao standby chỉ cho phép các thao tác đọc.
4. Kiểm tra server đang ở recovery bằng `pg_is_in_recovery()`.
5. Phân biệt read-only transaction với quyền SELECT của database role.
6. Giải thích snapshot, lock, buffer pin và tablespace conflicts.
7. Nhận biết các recovery conflict counters trong `pg_stat_database_conflicts`.
8. Cấu hình `max_standby_archive_delay` và `max_standby_streaming_delay`.
9. Hiểu vì sao delay limit không phải thời lượng tối đa riêng của từng query.
10. Cân bằng query latency với WAL replay lag.
11. Giải thích `hot_standby_feedback` và nguy cơ table bloat trên primary.
12. Theo dõi receive LSN, replay LSN và replication lag.
13. Đọc thông tin từ `pg_stat_replication`, `pg_stat_wal_receiver` và `pg_stat_activity`.
14. Thiết kế query/reporting workload để giảm recovery conflicts.
15. Xử lý lỗi `canceling statement due to conflict with recovery`.
16. Xây dựng retry policy an toàn cho ứng dụng đọc trên standby.
17. Kiểm tra tính nhất quán dữ liệu và độ trễ khi đọc từ replica.
18. Chuẩn bị standby cho failover và kiểm tra sau promotion.
19. Thiết kế monitoring, alert và replication drills.
20. Chọn cấu hình phù hợp với RPO, RTO và nhu cầu truy vấn đọc.

## 2. Hot standby là gì?

Hot standby là trạng thái của một PostgreSQL standby server trong đó server tiếp tục replay WAL nhận từ primary nhưng đồng thời cho phép các client kết nối và chạy các truy vấn chỉ đọc.

### 2.1. Streaming replication

Primary gửi WAL tới standby. Standby ghi WAL nhận được, sau đó startup process replay WAL để cập nhật data files và catalog state của bản sao.

### 2.2. Hot standby

Khi standby đã replay đủ WAL để đạt trạng thái nhất quán, nó có thể cho phép các client kết nối. Các transaction đọc nhìn thấy trạng thái đã được replay trên standby.

### 2.3. Không phải primary thứ hai

Standby đang ở recovery không nhận các thao tác ghi thông thường. Nó không tự tạo một nhánh dữ liệu độc lập trong lúc vẫn là standby.

### 2.4. Lợi ích chính

- Chuyển một phần SELECT/reporting sang standby.
- Giảm tải CPU, I/O và buffer cache pressure trên primary.
- Cho phép chạy một số truy vấn phân tích dài mà không chiếm tài nguyên query trên primary.
- Có một server đang replay WAL và có thể được promote khi primary gặp sự cố.
- Tách workload đọc và workload ghi theo vai trò.

### 2.5. Chi phí vận hành

Standby cần CPU, memory, storage, network và monitoring riêng. Truy vấn đọc trên standby có thể cản trở WAL replay; feedback để giảm conflict có thể khiến primary giữ dead tuples lâu hơn.

## 3. Các chế độ standby

Cần phân biệt khả năng nhận WAL với khả năng phục vụ query.

| Trạng thái | Nhận/replay WAL | Cho phép query đọc |
| --- | --- | --- |
| Primary | Tạo WAL | Có, đọc và ghi theo quyền |
| Warm standby | Replay WAL trong recovery | Không phục vụ client query thông thường |
| Hot standby | Replay WAL trong recovery | Có, chỉ đọc |
| Promoted standby | Trở thành primary mới | Có, đọc và ghi |

### 3.1. Warm standby

Một standby chỉ replay WAL và chờ failover, không bật khả năng phục vụ truy vấn đọc.

### 3.2. Hot standby

Standby mở kết nối đọc khi đã đạt consistency point và `hot_standby` được bật.

### 3.3. Promotion

Khi được promote, standby kết thúc recovery và trở thành primary mới. Sau promotion, các giới hạn read-only do recovery không còn áp dụng như trước.

### 3.4. Hot standby vẫn là recovery

`pg_is_in_recovery()` trả true trong khi server vẫn replay WAL ở standby mode, kể cả khi client đang chạy SELECT thành công.

## 4. Kiến trúc xử lý trên hot standby

Một standby có các thành phần chính:

- WAL receiver nhận WAL từ primary qua replication protocol.
- WAL files được ghi vào `pg_wal`.
- Startup process replay WAL và áp dụng các thay đổi.
- Backend processes phục vụ client query.
- Recovery conflict manager phối hợp query với các thao tác replay gây xung đột.

~~~text
Primary
  |
  | WAL stream
  v
WAL receiver
  |
  v
pg_wal on standby
  |
  v
Startup / recovery process
  |
  +----------------------------+
  |                            |
  v                            v
Replay record             Read-only backend
  |                            |
  v                            v
Need cleanup/lock          Holds snapshot/lock/pin
  |                            |
  +-------------+--------------+
                |
                v
          Recovery conflict
                |
       +--------+--------+
       |                 |
       v                 v
    Wait WAL          Cancel query
    replay delay
       |
       v
Replay proceeds
~~~

### 4.1. WAL receiver

WAL receiver kết nối tới primary, nhận WAL stream và ghi vào WAL files trên standby. Trạng thái receiver có thể xem qua `pg_stat_wal_receiver`.

### 4.2. Startup process

Startup process đọc WAL và replay các records. Nó phải giữ tiến độ để standby không tụt quá xa so với primary.

### 4.3. Read-only backend

Backend chạy query với snapshot phù hợp trên dữ liệu đã replay. Query có thể giữ AccessShareLock, snapshot hoặc buffer pin trong thời gian thực thi.

### 4.4. Recovery conflict manager

Khi một WAL record cần thực hiện thao tác xung đột với query đang chạy, PostgreSQL có thể chờ một khoảng thời gian. Nếu vượt delay limit, query bị cancel để replay tiếp tục.

### 4.5. Replay không đồng bộ với query

Query đọc có thể nhìn thấy trạng thái cũ hơn primary vì standby chỉ hiển thị dữ liệu đã replay. Đây là replication lag, không phải dữ liệu bị hỏng.

## 5. Điều kiện bật hot standby

Cấu hình hot standby phụ thuộc vào replication setup và phiên bản PostgreSQL.

### 5.1. Primary wal_level

Primary cần `wal_level = replica` hoặc `logical` để hỗ trợ physical streaming replication.

~~~conf
wal_level = replica
max_wal_senders = 10
~~~

### 5.2. Standby hot_standby

Trên standby:

~~~conf
hot_standby = on
~~~

Tham số này là tham số khởi động server; thay đổi cần restart để có hiệu lực.

### 5.3. Standby signal

Với PostgreSQL 12 trở lên, `standby.signal` trong PGDATA yêu cầu server chạy standby mode.

### 5.4. primary_conninfo

Standby cần thông tin kết nối tới primary hoặc upstream standby:

~~~conf
primary_conninfo = 'host=primary.example.internal port=5432 user=replicator application_name=standby_reports sslmode=verify-full'
~~~

Quản lý mật khẩu bằng cơ chế an toàn như password file hoặc secret store. Không đưa secret vào source control hoặc log.

### 5.5. Replication role

Primary cần role có quyền replication và pg_hba rule phù hợp:

~~~sql
CREATE ROLE replicator WITH LOGIN REPLICATION PASSWORD 'replace-with-secret';
~~~

Ví dụ pg_hba.conf:

~~~conf
hostssl replication replicator 10.20.0.0/24 scram-sha-256
~~~

### 5.6. Kiểm tra standby state

~~~sql
SELECT
    pg_is_in_recovery() AS in_recovery,
    current_setting('transaction_read_only') AS transaction_read_only,
    current_setting('hot_standby') AS hot_standby;
~~~

`pg_is_in_recovery()` xác định server còn ở recovery. `transaction_read_only` phản ánh transaction hiện tại; `hot_standby` cho biết cấu hình hỗ trợ query trong recovery.

## 6. Vì sao hot standby chỉ cho phép đọc?

Standby replay WAL do primary tạo. Nếu client tự thay đổi dữ liệu trên standby, các thay đổi đó sẽ không có trong WAL stream của primary và có thể xung đột với quá trình replay.

### 6.1. SELECT thông thường

Các truy vấn SELECT thông thường được phép khi hot standby đã sẵn sàng.

~~~sql
SELECT count(*) FROM app.orders;
~~~

### 6.2. DML bị từ chối

Các thao tác ghi như INSERT, UPDATE, DELETE và MERGE không được phép trong recovery.

~~~sql
UPDATE app.orders
SET status = 'closed'
WHERE order_id = 100;
~~~

Lệnh trên sẽ thất bại khi chạy trên hot standby.

### 6.3. DDL bị từ chối

Các thao tác thay đổi cấu trúc database như CREATE, ALTER, DROP không được thực hiện trong hot standby.

### 6.4. SELECT FOR UPDATE/SHARE

Các truy vấn cần row-level locking để bảo vệ bản ghi khỏi cập nhật không được phép như trên primary.

~~~sql
SELECT *
FROM app.orders
WHERE order_id = 100
FOR UPDATE;
~~~

### 6.5. Sequence changes

Các hàm làm thay đổi sequence state như `nextval()` hoặc `setval()` không phù hợp với read-only standby và bị từ chối trong recovery.

### 6.6. Temporary objects

Không thiết kế ứng dụng dựa trên khả năng tạo hoặc thay đổi temporary tables trong hot standby. Hot standby có các giới hạn DDL/DML riêng; nếu cần thao tác tạm, hãy kiểm tra đúng khả năng của major version và chạy workload đó trên primary hoặc một môi trường writable riêng.

### 6.7. Read-only transaction

Có thể chủ động đặt transaction read-only:

~~~sql
BEGIN READ ONLY;
SELECT count(*) FROM app.orders;
COMMIT;
~~~

Đây là cách thể hiện ý định của ứng dụng. Trên hot standby, transaction đã bị giới hạn bởi recovery state ngay cả khi không viết BEGIN READ ONLY.

## 7. Kiểm tra transaction và server read-only

### 7.1. Server có đang recovery?

~~~sql
SELECT pg_is_in_recovery();
~~~

- `true`: server đang ở recovery/standby.
- `false`: server không còn ở recovery, thường là primary hoặc standby đã promote.

### 7.2. Transaction hiện tại

~~~sql
SHOW transaction_read_only;
~~~

### 7.3. Default transaction mode

~~~sql
SHOW default_transaction_read_only;
~~~

Tham số này có thể được dùng để mặc định transaction read-only ở một session/role/database, tùy cấu hình.

### 7.4. Kiểm tra role

~~~sql
SELECT
    rolname,
    rolsuper,
    rolreplication,
    rolcreatedb,
    rolcreaterole
FROM pg_roles
WHERE rolname = current_user;
~~~

Quyền SELECT của role vẫn cần được cấp trên database/schema/table. Hot standby không tự cấp quyền đọc mọi dữ liệu.

### 7.5. Kiểm tra từ ứng dụng

Ứng dụng nên xác định replica qua service discovery/connection metadata hoặc kiểm tra `pg_is_in_recovery()` khi thiết lập connection. Không suy đoán vai trò chỉ từ hostname nếu failover có thể thay đổi vai trò server.

## 8. Đọc dữ liệu trên standby và replication lag

Hot standby chỉ phục vụ trạng thái đã replay. Một transaction vừa commit trên primary có thể chưa nhìn thấy ngay trên standby.

### 8.1. Read-after-write

Nếu ứng dụng ghi một đơn hàng trên primary rồi ngay lập tức đọc đơn hàng đó từ standby, query có thể chưa tìm thấy row do replay lag.

### 8.2. Eventual consistency

Trong asynchronous replication, standby thường hội tụ về trạng thái primary khi WAL được truyền và replay, nhưng tại một thời điểm cụ thể có thể đang chậm.

### 8.3. Read routing

Một cách triển khai phổ biến:
- INSERT/UPDATE/DELETE và transaction cần read-your-writes đi primary.
- Báo cáo, dashboard và query chấp nhận stale reads đi standby.
- Query cần trạng thái mới nhất có thể route primary hoặc đợi standby replay tới LSN đã ghi nhận.

### 8.4. LSN barrier

Ứng dụng có thể lấy LSN sau khi commit trên primary rồi đợi standby replay tới LSN đó trước khi đọc, trong giới hạn timeout.

Trên primary:

~~~sql
SELECT pg_current_wal_flush_lsn();
~~~

Trên standby:

~~~sql
SELECT pg_last_wal_replay_lsn();
~~~

So sánh hai LSN trong cùng timeline/cluster context. Khi replay LSN đã đạt hoặc vượt barrier, transaction tương ứng đã được replay tới vị trí đó.

### 8.5. Không chỉ so timestamp

`pg_last_xact_replay_timestamp()` có thể cũ khi primary không có transaction mới. LSN là thước đo tiến độ WAL phù hợp hơn cho một barrier cụ thể.

## 9. Các loại recovery conflict

PostgreSQL ghi nhận năm nhóm conflict chính trong `pg_stat_database_conflicts`:

| Counter | Nhóm conflict | Ví dụ |
| --- | --- | --- |
| confl_tablespace | Tablespace | WAL replay xóa tablespace mà query đang dùng |
| confl_lock | Lock | Replay cần lock mạnh hơn query đang giữ |
| confl_snapshot | Snapshot | VACUUM cleanup row version mà snapshot standby còn cần |
| confl_bufferpin | Buffer pin | Replay cần sửa/reclaim page đang được query pin |
| confl_deadlock | Deadlock | Recovery conflict tạo tình huống deadlock cần xử lý |

### 9.1. Tablespace conflict

Primary có thể drop một tablespace. Nếu standby query đang truy cập object trong tablespace đó, replay thao tác xóa có thể xung đột và query phải kết thúc để recovery tiến lên.

### 9.2. Lock conflict

Primary thực hiện DDL hoặc thao tác cần AccessExclusiveLock, trong khi standby query giữ AccessShareLock trên relation. Recovery không thể đợi vô hạn nếu delay limit bị giới hạn.

### 9.3. Snapshot conflict

Đây là nhóm thường gặp với query đọc dài. Query giữ snapshot cần nhìn thấy một row version cũ. Primary VACUUM có thể dọn row version đó và WAL chứa cleanup record. Standby phải hủy query hoặc trì hoãn replay.

### 9.4. Buffer pin conflict

Query đang giữ buffer pin trên page mà recovery cần sửa hoặc reclaim. Recovery có thể chờ pin được giải phóng; nếu vượt giới hạn, query bị cancel.

### 9.5. Deadlock conflict

Recovery có thể gặp tình huống deadlock liên quan tới lock/query trên standby. PostgreSQL có cơ chế phát hiện và xử lý; thống kê conflict giúp theo dõi nhóm này.

### 9.6. Conflict không có nghĩa dữ liệu hỏng

PostgreSQL hủy query để bảo đảm replay và tính nhất quán. Query bị cancel là một hành vi điều phối có chủ đích, không tự động có nghĩa standby corruption.

## 10. Snapshot conflict và VACUUM

Snapshot conflict cần hiểu rõ vì nó thường xuất hiện khi chạy báo cáo dài trên standby.

### 10.1. MVCC trên primary

PostgreSQL giữ nhiều row versions để transaction có thể nhìn thấy dữ liệu phù hợp với snapshot của nó. UPDATE/DELETE tạo hoặc làm cũ row versions; VACUUM dọn các version không còn cần thiết.

### 10.2. Snapshot trên standby

Một SELECT dài có thể giữ snapshot trong thời gian dài. Query cần đọc các version phù hợp với snapshot đó.

### 10.3. Cleanup record trong WAL

Khi primary VACUUM dọn row versions, WAL chứa thông tin để standby thực hiện cleanup tương ứng. Nếu standby query còn cần các version đó, hai hoạt động xung đột.

### 10.4. Hủy query hoặc trì hoãn replay

PostgreSQL có thể đợi query hoàn thành trong giới hạn delay. Khi vượt giới hạn, query bị hủy để WAL replay tiếp tục.

### 10.5. Query chạy lâu tăng xác suất conflict

Một báo cáo quét hàng tỷ dòng hoặc transaction read-only giữ snapshot quá lâu làm tăng cửa sổ mà cleanup có thể va chạm.

### 10.6. VACUUM không bị vô hiệu hóa trên primary

Không tắt autovacuum trên primary chỉ để giảm conflict cho standby. Điều đó có thể gây table bloat, transaction ID wraparound risk và vấn đề vận hành lớn hơn.

## 11. Lock conflict và DDL

### 11.1. AccessShareLock của SELECT

SELECT thông thường lấy AccessShareLock trên relation. Lock này tương thích với nhiều lock khác nhưng xung đột với AccessExclusiveLock.

### 11.2. DDL trên primary

Các lệnh như DROP TABLE, TRUNCATE, một số ALTER TABLE và thao tác thay đổi relation cần lock mạnh. Khi WAL replay áp dụng thay đổi đó, standby query đang giữ lock có thể bị ảnh hưởng.

### 11.3. DDL window

Nếu có thể, thực hiện DDL nặng vào thời điểm standby workload thấp. Tránh chạy báo cáo dài đúng lúc migration cần lock mạnh.

### 11.4. Lock timeout trên primary không giải quyết standby conflict

`lock_timeout` ở primary điều khiển thời gian chờ lock của session primary. Nó không phải cơ chế điều khiển recovery conflict trên standby.

### 11.5. Theo dõi query đang giữ lock

~~~sql
SELECT
    pid,
    usename,
    application_name,
    state,
    xact_start,
    query_start,
    wait_event_type,
    wait_event,
    query
FROM pg_stat_activity
WHERE state <> 'idle'
ORDER BY xact_start NULLS LAST;
~~~

Query này giúp nhận diện transaction/query dài trên standby. Đọc query cẩn thận vì có thể chứa dữ liệu nhạy cảm.

## 12. Buffer pin conflict

Buffer pin là cơ chế backend giữ một page trong shared buffers để thao tác an toàn.

### 12.1. Vì sao pin tồn tại?

Một query có thể cần page ổn định trong lúc đọc hoặc xử lý dữ liệu. Buffer pin ngăn một số thao tác reclaim/modify page cho tới khi backend nhả pin.

### 12.2. Replay cần page

Startup process có thể cần áp dụng WAL record lên page hoặc thực hiện cleanup. Nếu query đang giữ pin, replay phải chờ.

### 12.3. Query scan lớn

Một số query đọc nhiều pages, chạy function hoặc giữ cursor lâu có thể làm buffer pin conflict kéo dài.

### 12.4. Không phải mọi buffer pin đều là lỗi

Buffer pin là cơ chế bình thường. Chỉ khi replay cần page bị giữ quá lâu và delay limit bị vượt, conflict mới có thể dẫn tới cancel.

### 12.5. Giảm thời gian giữ tài nguyên

Chia nhỏ query, tránh giữ cursor lâu, materialize kết quả ở ứng dụng khi phù hợp và không giữ transaction mở trong lúc client xử lý dữ liệu.

## 13. max_standby_archive_delay

Tham số này quy định thời gian tối đa standby được trì hoãn replay WAL lấy từ archive khi có recovery conflict.

~~~conf
max_standby_archive_delay = 30s
~~~

### 13.1. Ý nghĩa

Khi replay WAL từ archive gặp conflict với query, standby có thể đợi trong giới hạn cấu hình trước khi cancel query.

### 13.2. Giá trị mặc định

Giá trị mặc định phổ biến là 30 giây. Kiểm tra giá trị thực bằng:

~~~sql
SHOW max_standby_archive_delay;
~~~

### 13.3. Giá trị -1

`-1` cho phép standby chờ vô hạn trong trường hợp conflict. Điều này có thể làm WAL replay dừng lâu và tăng replication lag.

### 13.4. Không phải query timeout

Đây không phải thời lượng tối đa mà một query được phép chạy. Thời gian chờ còn phụ thuộc WAL đã đến standby bao lâu và các conflict trước đó.

### 13.5. Archive replay

Tham số chỉ áp dụng cho WAL được lấy từ archive. WAL streaming dùng tham số riêng.

## 14. max_standby_streaming_delay

Tham số này điều khiển thời gian tối đa standby được trì hoãn replay WAL nhận qua streaming replication khi có conflict.

~~~conf
max_standby_streaming_delay = 30s
~~~

### 14.1. Ý nghĩa

Khi replay streaming WAL gặp recovery conflict, standby có thể chờ query hoàn tất trong giới hạn này. Nếu không giải phóng conflict kịp, query bị cancel.

### 14.2. Giá trị -1

`-1` cho phép chờ vô hạn. Cần cân nhắc replication lag, WAL retention trên primary và nhu cầu failover.

### 14.3. Khác với archive delay

- `max_standby_archive_delay`: WAL lấy từ archive.
- `max_standby_streaming_delay`: WAL nhận qua streaming.

### 14.4. Kiểm tra

~~~sql
SHOW max_standby_streaming_delay;
~~~

### 14.5. Tác động lên standby lag

Delay lớn cho query thêm thời gian, nhưng replay có thể chậm lại. Nếu standby dùng replication slot, primary có thể phải giữ WAL lâu hơn và dung lượng pg_wal tăng.

## 15. Delay limit không phải thời gian tối đa riêng của query

Đây là điểm rất dễ hiểu nhầm.

### 15.1. Thời gian tính theo WAL

Delay limit giới hạn thời gian trì hoãn replay trong quá trình xử lý WAL conflict, tính từ khi WAL được nhận/đưa vào xử lý theo cơ chế tương ứng.

### 15.2. Query mới có thể chỉ còn ít thời gian

Nếu standby đã dùng phần lớn delay budget cho một conflict trước đó trong cùng khoảng WAL, query mới gặp conflict có thể bị cancel gần như ngay lập tức.

### 15.3. Query có thể chạy lâu hơn delay

Một query không gặp conflict có thể chạy lâu hơn giá trị delay. Tham số không tự cancel mọi query khi chúng vượt 30 giây.

### 15.4. Một query ngắn vẫn có thể bị cancel

Nếu WAL replay đã chờ conflict trước đó và delay budget gần hết, query vừa bắt đầu có thể không được thêm nhiều thời gian.

### 15.5. Thiết kế SLA query riêng

Dùng `statement_timeout` và timeout ở ứng dụng để kiểm soát query duration. Dùng standby delay settings để cân bằng recovery progress. Hai nhóm cấu hình giải quyết hai vấn đề khác nhau.

## 16. Cấu hình conflict delay

Các tham số có thể cấu hình trong postgresql.conf trên standby:

~~~conf
hot_standby = on
max_standby_archive_delay = 30s
max_standby_streaming_delay = 30s
log_recovery_conflict_waits = on
~~~

### 16.1. Thay đổi delay

Các tham số delay có thể reload theo context của phiên bản:

~~~sql
SELECT pg_reload_conf();
~~~

Sau đó kiểm tra:

~~~sql
SHOW max_standby_archive_delay;
SHOW max_standby_streaming_delay;
SHOW log_recovery_conflict_waits;
~~~

### 16.2. hot_standby

`hot_standby` cần restart khi thay đổi. Không giả định reload đã bật được hot standby nếu server đang chạy với thiết lập khác.

### 16.3. log_recovery_conflict_waits

Khi bật, PostgreSQL log các lần recovery conflict phải chờ lâu hơn ngưỡng liên quan đến `deadlock_timeout`. Điều này hữu ích để tìm conflict kéo dài.

### 16.4. Thay đổi có kiểm soát

Thử điều chỉnh delay trên một standby trước, theo dõi replay lag và query cancellation. Không tăng lên vô hạn chỉ để loại bỏ lỗi ứng dụng.

## 17. hot_standby_feedback

`hot_standby_feedback` cho phép standby gửi feedback về xmin cần giữ tới upstream primary, giúp primary tránh VACUUM dọn các row versions mà query trên standby vẫn cần.

~~~conf
hot_standby_feedback = on
~~~

### 17.1. Cách hoạt động

Standby thông báo transaction horizon cần thiết để giữ snapshot. Primary dùng feedback này khi xác định tuple nào chưa thể cleanup an toàn.

### 17.2. Giảm snapshot conflicts

Feedback có thể giảm các snapshot conflicts phát sinh do VACUUM cleanup trên primary.

### 17.3. Không loại bỏ mọi conflict

Feedback không giải quyết mọi lock conflict, tablespace conflict hoặc buffer pin conflict. DDL và các thao tác khác vẫn có thể khiến query bị hủy.

### 17.4. Trade-off: bloat trên primary

Primary có thể phải giữ dead tuples lâu hơn. Nếu standby giữ xmin cũ trong thời gian dài, VACUUM không thể reclaim một số row versions, làm tăng table/index bloat.

### 17.5. Feedback và replication lag

Feedback phản ánh horizon mà standby cần. Nếu standby lag hoặc query giữ snapshot lâu, horizon có thể cũ. Theo dõi cả conflict giảm được lẫn dead tuple growth trên primary.

### 17.6. Không phải một bảo đảm tuyệt đối

Feedback không bảo đảm mọi query sẽ không bị cancel. Nó chỉ giúp tránh một nhóm conflict do cleanup tuple.

## 18. Bật hot_standby_feedback có nên không?

Không có một lựa chọn đúng cho mọi hệ thống.

| Workload | Cân nhắc |
| --- | --- |
| Query ngắn, cần replay nhanh | Có thể để off nếu conflict thấp |
| Reporting dài, cần ít query cancellation | Cân nhắc on và theo dõi bloat |
| Primary nhạy cảm với table bloat | Thận trọng với on |
| Standby có thể lag lâu | Đánh giá feedback horizon và retained dead tuples |
| Nhiều standby | Đánh giá tác động tổng hợp của từng standby |

### 18.1. Khi bật

Ưu tiên khi query dài trên standby quan trọng và snapshot conflicts thường xuyên làm gián đoạn công việc.

### 18.2. Khi tắt

Ưu tiên khi primary cần VACUUM reclaim tuple sớm, bloat đã là vấn đề hoặc query trên standby có thể được rút ngắn/đổi lịch.

### 18.3. Theo dõi primary

Kiểm tra n_dead_tup, vacuum progress, table size và các transaction horizon. Đừng chỉ nhìn số query cancellation trên standby.

### 18.4. Bật theo thời gian

Một số môi trường có thể dùng feedback theo workload/standby role. Thay đổi phải được kiểm soát, vì việc bật/tắt không thay thế một policy retention và vacuum rõ ràng.

## 19. Recovery conflicts được thống kê ở đâu?

View `pg_stat_database_conflicts` cung cấp số conflict theo database trên standby.

~~~sql
SELECT
    datname,
    confl_tablespace,
    confl_lock,
    confl_snapshot,
    confl_bufferpin,
    confl_deadlock
FROM pg_stat_database_conflicts
ORDER BY datname;
~~~

### 19.1. confl_tablespace

Số query bị cancel do tablespace conflict.

### 19.2. confl_lock

Số query bị cancel do lock conflict.

### 19.3. confl_snapshot

Số query bị cancel do snapshot conflict.

### 19.4. confl_bufferpin

Số query bị cancel do buffer pin conflict.

### 19.5. confl_deadlock

Số query bị cancel do recovery deadlock conflict.

### 19.6. Counters là cumulative

Counters tích lũy kể từ lần reset statistics gần nhất. So sánh delta giữa các lần scrape thay vì chỉ nhìn giá trị tuyệt đối.

### 19.7. Reset stats

Stats có thể reset bởi thao tác quản trị hoặc sự kiện server. Lưu ý reset time khi tính rate và alert.

## 20. Kết hợp pg_stat_database_conflicts với pg_stat_database

~~~sql
SELECT
    d.datname,
    d.numbackends,
    d.xact_commit,
    d.xact_rollback,
    d.deadlocks,
    c.confl_tablespace,
    c.confl_lock,
    c.confl_snapshot,
    c.confl_bufferpin,
    c.confl_deadlock
FROM pg_stat_database AS d
LEFT JOIN pg_stat_database_conflicts AS c
       ON c.datid = d.datid
ORDER BY d.datname;
~~~

### 20.1. Đọc theo database

Conflict counters được nhóm theo database. Nếu một database có snapshot conflict tăng nhanh, tập trung điều tra query/reporting trong database đó.

### 20.2. Đọc theo delta

Lưu mẫu counters định kỳ. Tính số tăng trong khoảng scrape và gắn với thời gian query cancellation.

### 20.3. Không chỉ nhìn tổng

Một counter lớn từ trước có thể không phản ánh vấn đề hiện tại. Alert dựa trên tốc độ tăng và ảnh hưởng tới ứng dụng.

### 20.4. Kết hợp logs

Counter cho biết nhóm conflict, log giúp xác định thời điểm, query/backend và thời gian chờ. Cần cả hai để điều tra.

## 21. Theo dõi replication lag từ primary

Trên primary:

~~~sql
SELECT
    application_name,
    client_addr,
    state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn,
    write_lag,
    flush_lag,
    replay_lag
FROM pg_stat_replication
ORDER BY application_name;
~~~

### 21.1. sent_lsn

Vị trí WAL đã gửi tới standby.

### 21.2. write_lsn

Vị trí WAL standby đã ghi xuống filesystem.

### 21.3. flush_lsn

Vị trí WAL standby đã flush bền vững.

### 21.4. replay_lsn

Vị trí WAL standby đã replay vào data state.

### 21.5. Lag fields

Các trường lag là thống kê độ trễ theo các giai đoạn gần đây, không phải lúc nào cũng là một phép đo chính xác về khoảng cách hiện tại. Khi standby idle, giá trị có thể null hoặc không phản ánh độ trễ theo cách trực quan.

### 21.6. LSN difference

Có thể tính chênh lệch bytes giữa current flush LSN của primary và replay LSN của standby khi hai vị trí thuộc cùng replication history:

~~~sql
SELECT
    application_name,
    pg_wal_lsn_diff(pg_current_wal_lsn(), replay_lsn) AS bytes_behind
FROM pg_stat_replication;
~~~

Kết quả là khoảng cách WAL theo bytes, không phải số giây. Chuyển sang thời gian cần WAL generation rate và workload context.

## 22. Theo dõi trên standby

### 22.1. Recovery state

~~~sql
SELECT pg_is_in_recovery();
~~~

### 22.2. Receive và replay LSN

~~~sql
SELECT
    pg_last_wal_receive_lsn() AS receive_lsn,
    pg_last_wal_replay_lsn() AS replay_lsn;
~~~

### 22.3. Replay lag theo bytes

~~~sql
SELECT pg_wal_lsn_diff(
    pg_last_wal_receive_lsn(),
    pg_last_wal_replay_lsn()
) AS received_not_replayed_bytes;
~~~

Nếu một trong hai LSN null, standby chưa nhận/replay WAL theo trạng thái hiện tại hoặc hàm không có dữ liệu để trả.

### 22.4. Replay timestamp

~~~sql
SELECT pg_last_xact_replay_timestamp();
~~~

Timestamp này không phải một đồng hồ lag đáng tin cậy khi primary không phát sinh transaction.

### 22.5. WAL receiver state

~~~sql
SELECT
    status,
    receive_start_lsn,
    written_lsn,
    flushed_lsn,
    latest_end_lsn,
    latest_end_time,
    sender_host,
    sender_port
FROM pg_stat_wal_receiver;
~~~

View thường có một row khi WAL receiver đang kết nối. Cột có thể khác theo version.

## 23. Theo dõi query dài trên standby

Query dài là một yếu tố làm tăng xác suất recovery conflict.

~~~sql
SELECT
    pid,
    usename,
    application_name,
    client_addr,
    state,
    xact_start,
    query_start,
    now() - query_start AS query_age,
    now() - xact_start AS transaction_age,
    wait_event_type,
    wait_event,
    left(query, 500) AS query_sample
FROM pg_stat_activity
WHERE state <> 'idle'
ORDER BY xact_start NULLS LAST;
~~~

### 23.1. Query age

Thời gian từ lúc query bắt đầu giúp phát hiện truy vấn kéo dài.

### 23.2. Transaction age

Một transaction có thể mở lâu dù query hiện tại ngắn hoặc backend đang idle in transaction. Snapshot có thể vẫn được giữ.

### 23.3. Idle in transaction

Session idle in transaction có thể giữ snapshot/locks lâu hơn cần thiết. Đặt `idle_in_transaction_session_timeout` theo policy phù hợp.

### 23.4. Wait events

`wait_event_type` và `wait_event` giúp nhận biết backend đang chờ tài nguyên nào. Tên wait event phụ thuộc version; recovery conflict cũng có thể dẫn tới query bị cancel thay vì chờ mãi.

### 23.5. Tránh log query nhạy cảm

Query text có thể chứa literal data. Giới hạn quyền xem và cân nhắc logging policy.

## 24. log_recovery_conflict_waits

Tham số này giúp log các lần WAL replay phải chờ recovery conflict lâu.

~~~conf
log_recovery_conflict_waits = on
deadlock_timeout = 1s
~~~

### 24.1. Mục đích

Khi recovery process bị trì hoãn bởi conflict trong thời gian vượt ngưỡng liên quan đến deadlock_timeout, PostgreSQL ghi log để hỗ trợ điều tra.

### 24.2. Không thay thế conflict counters

`pg_stat_database_conflicts` thống kê query bị cancel theo nhóm; log recovery conflict waits giúp quan sát các lần chờ. Hai nguồn bổ sung cho nhau.

### 24.3. Log volume

Nếu conflict xảy ra thường xuyên, bật logging có thể tăng log volume. Dùng log rotation và retention phù hợp.

### 24.4. Điều tra từ log

Đối chiếu timestamp log với query_start/xact_start, DDL/VACUUM trên primary và conflict counters trên standby.

## 25. Ảnh hưởng của delay settings tới WAL retention

Khi standby trì hoãn replay để chờ query, WAL nhận được nhưng chưa replay sẽ tích lũy.

### 25.1. Replay lag tăng

Delay càng lớn thì standby có thể càng tụt xa so với primary trong thời gian query giữ conflict.

### 25.2. Replication slot

Nếu standby dùng physical replication slot, primary giữ WAL mà slot còn cần. Replay lag hoặc receiver lag kéo dài có thể làm slot giữ nhiều WAL.

### 25.3. Disk pressure trên primary

WAL retained bởi slot có thể làm `pg_wal` trên primary tăng. Nếu không giám sát, disk có thể đầy và ảnh hưởng toàn bộ cluster.

### 25.4. Không có slot

Nếu standby tụt quá xa và WAL cần thiết bị recycle, standby có thể không tiếp tục streaming được. Có thể cần WAL archive để catch up hoặc rebuild standby.

### 25.5. Delay vô hạn có chi phí

`max_standby_streaming_delay = -1` có thể bảo vệ query khỏi cancel do conflict nhưng làm replay dừng không giới hạn. Đánh giá storage, failover readiness và RPO.

## 26. Thiết kế workload đọc cho hot standby

### 26.1. Chia nhỏ báo cáo

Thay một truy vấn quét nhiều giờ bằng các truy vấn theo khoảng thời gian/key range khi nghiệp vụ cho phép.

### 26.2. Tránh transaction mở lâu

Không giữ transaction read-only trong khi người dùng xem kết quả hoặc chờ tương tác. Fetch dữ liệu theo trang, đóng transaction sớm.

### 26.3. Dùng pagination ổn định

Keyset pagination thường tránh offset scan lớn và giảm thời gian query so với phân trang offset sâu.

### 26.4. Tối ưu indexes

Tạo indexes phù hợp trên primary theo quy trình migration. Index tốt giảm pages phải đọc và thời gian giữ snapshot/lock trên standby.

### 26.5. Materialized reporting

Nếu báo cáo rất nặng, cân nhắc tạo dữ liệu tổng hợp ở primary hoặc pipeline ETL riêng, sau đó đọc từ kho phân tích. Hot standby không phải lúc nào cũng phù hợp cho workload OLAP kéo dài.

### 26.6. Query timeout

Đặt `statement_timeout` theo loại workload. Timeout này bảo vệ server trước query runaway; nó độc lập với recovery delay settings.

### 26.7. Pooling

Dùng connection pool để kiểm soát số backend, tránh session idle in transaction và định tuyến đúng read/write endpoints.

## 27. Định tuyến query giữa primary và standby

### 27.1. Primary endpoint

Dùng cho writes, DDL, transaction cần read-your-writes và truy vấn cần dữ liệu mới nhất.

### 27.2. Standby endpoint

Dùng cho SELECT có thể chấp nhận replication lag và khả năng query cancellation.

### 27.3. Transaction không được chia tùy tiện

Một transaction cần đọc rồi ghi phải ở primary. Không chuyển từng statement của cùng transaction qua hai server khác nhau.

### 27.4. Session consistency

Nếu một session vừa ghi primary vừa đọc standby, kết quả có thể stale. Gắn routing policy với yêu cầu consistency của request.

### 27.5. Retry policy

Khi query bị cancel do recovery conflict, ứng dụng có thể retry trên standby hoặc chuyển primary tùy nghiệp vụ. Retry phải có giới hạn và backoff để không tạo tải lớn hơn.

### 27.6. Phân loại query

Có thể phân loại:
- Strong read: cần dữ liệu mới nhất, route primary.
- Eventual read: chấp nhận lag, route standby.
- Long report: route reporting standby riêng, có timeout và lịch chạy.
- Write transaction: luôn route primary.

## 28. Xử lý lỗi canceling statement due to conflict with recovery

Thông báo điển hình:

~~~text
ERROR: canceling statement due to conflict with recovery
DETAIL: User query might have needed to see row versions that must be removed.
~~~

Nội dung DETAIL thay đổi theo loại conflict.

### 28.1. Đây là query cancellation

PostgreSQL đã hủy statement trên standby để recovery có thể tiếp tục replay WAL.

### 28.2. Kiểm tra counter

~~~sql
SELECT *
FROM pg_stat_database_conflicts
WHERE datname = current_database();
~~~

### 28.3. Xác định loại conflict

- confl_snapshot tăng: xem query dài và VACUUM cleanup trên primary.
- confl_lock tăng: xem DDL/lock mạnh trên primary.
- confl_bufferpin tăng: xem query giữ page/buffer lâu.
- confl_tablespace tăng: xem thao tác drop tablespace.
- confl_deadlock tăng: điều tra lock/recovery interactions qua logs.

### 28.4. Kiểm tra query và transaction age

Dùng pg_stat_activity để tìm session có xact_start/query_start cũ.

### 28.5. Kiểm tra delay

Đọc max_standby_streaming_delay và max_standby_archive_delay. Xác định WAL conflict đến từ streaming hay archive.

### 28.6. Chọn hướng khắc phục

Rút ngắn query, chuyển query sang primary, tăng delay có giới hạn, bật feedback nếu phù hợp, hoặc tách workload sang standby riêng.

### 28.7. Retry có kiểm soát

Không retry vô hạn. Dùng exponential backoff, giới hạn số lần và phân biệt lỗi do conflict với lỗi SQL khác.

## 29. Retry query an toàn

Query đọc thường có thể retry, nhưng vẫn cần xem side effects.

### 29.1. SELECT thuần

Một SELECT thuần không có side effects ứng dụng có thể retry trên cùng standby hoặc primary.

### 29.2. Function có side effects

Không giả định mọi câu SELECT đều không thay đổi trạng thái. Function có thể gọi external service hoặc tạo side effect ngoài database. Kiểm tra function semantics trước khi retry.

### 29.3. Cursor và transaction

Nếu transaction/cursor đã bị hủy, thường cần mở transaction mới và chạy lại query từ đầu. Không tiếp tục dùng cursor đã lỗi.

### 29.4. Retry budget

Đặt số lần retry và tổng thời gian tối đa. Khi hết budget, trả lỗi có ý nghĩa hoặc route primary nếu policy cho phép.

### 29.5. Backoff

Dùng exponential backoff với jitter để nhiều client không cùng retry đồng thời sau một đợt recovery conflict.

### 29.6. Ghi nhận metric

Theo dõi retry count, cancellation count, query latency và route fallback để phát hiện standby không còn phù hợp workload.

## 30. Tương tác với autovacuum trên primary

Autovacuum trên primary tạo ra các cleanup records được replay trên standby.

### 30.1. Không tắt autovacuum để chiều standby

Tắt autovacuum có thể làm table bloat, tăng chi phí query và gây transaction ID wraparound risk.

### 30.2. Điều chỉnh autovacuum đúng mục tiêu

Nếu VACUUM quá dồn dập gây conflict, xem table-level thresholds, workload churn, vacuum cost settings và lịch DDL. Thay đổi cần dựa trên metrics primary.

### 30.3. hot_standby_feedback trade-off

Feedback có thể làm giảm snapshot conflicts nhưng khiến primary giữ dead tuples. Đo bloat trước/sau khi bật.

### 30.4. Nhiều standby

Một standby giữ xmin cũ có thể ảnh hưởng cleanup trên primary. Nếu có nhiều replicas, đánh giá horizon từ tất cả các consumer và slot.

### 30.5. Kiểm tra dead tuples

~~~sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup,
    last_vacuum,
    last_autovacuum,
    last_analyze,
    last_autoanalyze
FROM pg_stat_user_tables
ORDER BY n_dead_tup DESC
LIMIT 20;
~~~

Số liệu là ước lượng statistics, không phải số row chính xác tuyệt đối.

## 31. Theo dõi replication slot và WAL retained

Trên primary:

~~~sql
SELECT
    slot_name,
    slot_type,
    active,
    restart_lsn,
    wal_status,
    safe_wal_size
FROM pg_replication_slots
ORDER BY slot_name;
~~~

### 31.1. restart_lsn

Vị trí WAL sớm nhất mà slot còn cần. Nếu vị trí cũ lâu, nhiều WAL có thể phải được giữ lại.

### 31.2. wal_status

Trạng thái khả năng slot tiếp tục nhận WAL phụ thuộc version và tình hình retained WAL.

### 31.3. safe_wal_size

Trên các version hỗ trợ, cho biết dung lượng WAL còn có thể phát sinh trước khi slot có nguy cơ vượt giới hạn giữ WAL.

### 31.4. max_slot_wal_keep_size

Giới hạn WAL mà slot có thể giữ. Giới hạn bảo vệ disk nhưng slot consumer chậm có thể mất khả năng tiếp tục và cần rebuild.

### 31.5. Không xóa WAL thủ công

Không xóa file trong pg_wal để giải phóng disk. Quản lý slot, archive và retention bằng cơ chế PostgreSQL.

## 32. Tác động tới failover readiness

Hot standby thường vừa phục vụ đọc vừa là ứng viên failover.

### 32.1. Replay lag

Standby lag lớn có thể mất nhiều transaction đã commit trên primary khi failover sang standby bất đồng bộ.

### 32.2. Conflict delay

Delay lớn cho query thời gian chạy nhưng làm standby replay chậm. Điều này có thể làm giảm mức cập nhật mới nhất khi promote.

### 32.3. Synchronous replication

Synchronous replication có thể giảm nguy cơ mất transaction đã được xác nhận theo mức sync được cấu hình. Các mức `synchronous_commit` như `remote_write`, `on` và `remote_apply` có semantics khác nhau.

### 32.4. remote_apply

Với synchronous standby phù hợp và `synchronous_commit = remote_apply`, commit trên primary có thể đợi tới khi transaction được replay trên standby. Điều này hỗ trợ read-after-write khi query đọc bắt đầu sau commit và dùng snapshot mới.

### 32.5. Không tự động loại bỏ mọi lag

Một standby có thể lag vì query conflicts, network, disk hoặc WAL receiver. Cần đo replay progress và xác định failover policy.

### 32.6. Promotion

Trước khi promote, đánh giá timeline, replay LSN, primary cũ đã được fence và quy trình reconfigure các replicas khác.

## 33. Cấu hình mẫu cho reporting standby

Ví dụ cấu hình standby phục vụ báo cáo với delay giới hạn:

~~~conf
hot_standby = on
max_standby_streaming_delay = 60s
max_standby_archive_delay = 60s
hot_standby_feedback = on
log_recovery_conflict_waits = on
~~~

### 33.1. Mục đích

- Cho query thêm thời gian trước khi bị cancel.
- Giảm snapshot conflicts bằng feedback.
- Ghi log những lần recovery phải chờ lâu.

### 33.2. Chi phí

- Replay lag có thể tăng.
- Primary có thể giữ dead tuples lâu hơn.
- Replication slot có thể giữ thêm WAL.
- Disk usage và failover freshness cần được theo dõi.

### 33.3. Không dùng nguyên mẫu cho mọi môi trường

Giá trị 60 giây chỉ là ví dụ. Chọn theo query SLA, WAL rate, disk headroom, số standby và RPO.

### 33.4. Standby dành cho failover

Nếu ưu tiên failover freshness, có thể dùng delay ngắn hơn, feedback off hoặc một standby riêng ít query. Reporting workload dài nên tách sang một replica khác nếu tài nguyên cho phép.

## 34. Kiểm tra hot standby end-to-end trong lab

### Bước 1. Tạo primary

Khởi tạo PostgreSQL primary riêng trong lab và cấu hình wal_level=replica, WAL senders và replication authentication.

### Bước 2. Tạo standby

Dùng pg_basebackup với -R hoặc quy trình standby phù hợp, sau đó start standby.

### Bước 3. Xác nhận recovery

Trên standby:

~~~sql
SELECT pg_is_in_recovery();
~~~

Kết quả phải là true khi standby đang hoạt động ở recovery.

### Bước 4. Chạy SELECT

~~~sql
SELECT now(), count(*) FROM app.orders;
~~~

Query đọc được phục vụ trên hot standby sau khi server đạt consistency point.

### Bước 5. Thử DML

~~~sql
INSERT INTO app.orders(order_id) VALUES (900001);
~~~

Lệnh phải bị từ chối trong recovery state.

### Bước 6. Tạo workload trên primary

Chạy UPDATE/DELETE/VACUUM trong lab để tạo WAL records có thể gây conflict với query standby.

### Bước 7. Chạy query dài trên standby

Dùng một SELECT có snapshot dài trong lab. Quan sát query có bị cancel hay không khi replay gặp cleanup conflict.

### Bước 8. Đọc conflict stats

~~~sql
SELECT *
FROM pg_stat_database_conflicts;
~~~

### Bước 9. Thử delay settings

Điều chỉnh max_standby_streaming_delay trong lab, reload cấu hình và quan sát query cancellation/replay lag.

### Bước 10. Thử feedback

Bật/tắt hot_standby_feedback trong lab, quan sát snapshot conflicts và dead tuple retention trên primary.

### Bước 11. So sánh LSN

Đo receive/replay LSN trên standby và sent/replay LSN trên primary.

### Bước 12. Ghi kết quả

Ghi query latency, conflict counters, replay lag, primary bloat indicators và tác động tới failover readiness.

## 35. Checklist xử lý conflict

Khi ứng dụng báo query bị cancel:

1. Ghi lại SQLSTATE, message, timestamp và application_name.
2. Xác định query chạy trên standby nào.
3. Đọc pg_stat_database_conflicts và tính counter delta.
4. Xác định nhóm conflict tăng.
5. Kiểm tra query_start và xact_start.
6. Kiểm tra DDL/VACUUM trên primary cùng thời điểm.
7. Xác định WAL đến qua streaming hay archive.
8. Kiểm tra max_standby_streaming_delay và max_standby_archive_delay.
9. Đo replay lag và WAL backlog.
10. Kiểm tra replication slots và retained WAL trên primary.
11. Đánh giá hot_standby_feedback và dead tuple growth.
12. Rút ngắn query hoặc chuyển workload nếu có thể.
13. Tăng delay có giới hạn nếu SLA đọc yêu cầu.
14. Đặt retry budget/backoff trong ứng dụng.
15. Theo dõi conflict rate và replay freshness sau thay đổi.

## 36. Các lỗi thường gặp

### Lỗi 1. Nghĩ standby luôn đọc được dữ liệu mới nhất

Standby chỉ thấy WAL đã replay. Dùng primary hoặc LSN barrier cho read-after-write.

### Lỗi 2. Query bị cancel nhưng không có SQL error trên primary

Recovery conflict xảy ra trên standby; điều tra pg_stat_database_conflicts và standby logs.

### Lỗi 3. Tăng delay vô hạn

Replay có thể dừng lâu, tăng lag và giữ WAL trên primary. Chọn delay theo SLA và capacity.

### Lỗi 4. Bật feedback mà không theo dõi bloat

Primary có thể giữ dead tuples lâu hơn. Theo dõi n_dead_tup, vacuum và table/index growth.

### Lỗi 5. Tắt autovacuum trên primary

Điều này có thể gây bloat và wraparound risk. Điều chỉnh workload/vacuum dựa trên số liệu.

### Lỗi 6. Nhầm delay với statement_timeout

Delay điều khiển recovery conflict; statement_timeout giới hạn thời gian query. Hai tham số độc lập.

### Lỗi 7. Nhầm delay là max runtime query

Query không conflict có thể chạy lâu hơn delay. Query conflict có thể bị cancel sớm hơn nếu budget WAL đã dùng.

### Lỗi 8. Chỉ xem replay timestamp

Primary idle khiến timestamp replay cũ dù không có lag thực. Dùng LSN và workload context.

### Lỗi 9. Không giám sát replication slots

Delay/lag làm slot giữ WAL lâu và có thể đầy disk primary.

### Lỗi 10. Retry vô hạn

Nhiều client retry cùng lúc có thể tạo retry storm. Dùng backoff, jitter và retry budget.

### Lỗi 11. Chạy transaction dài trên standby

Snapshot cũ làm tăng snapshot conflicts. Kết thúc transaction sớm và không để idle in transaction.

### Lỗi 12. Định tuyến writes tới standby

DML/DDL bị từ chối trong recovery. Route writes tới primary.

### Lỗi 13. Cho rằng hot_standby_feedback giải quyết mọi conflict

Feedback chủ yếu giảm snapshot conflicts do cleanup; lock, tablespace và buffer pin conflicts vẫn có thể xảy ra.

### Lỗi 14. Không phân biệt archive và streaming delay

WAL source khác nhau dùng hai tham số delay khác nhau.

### Lỗi 15. Đặt feedback trên primary

Tham số được cấu hình ở standby nơi feedback được gửi. Kiểm tra đúng server và version.

### Lỗi 16. Dùng standby reporting làm replica duy nhất cho failover

Query nặng có thể làm replay lag. Cân nhắc tách reporting standby và failover standby.

### Lỗi 17. Bỏ qua transaction age

Session idle in transaction vẫn có thể giữ snapshot dù không chạy query dài.

### Lỗi 18. Không kiểm tra role privileges

Hot standby chỉ read-only nhưng role vẫn cần SELECT privileges phù hợp.

### Lỗi 19. Không kiểm tra consistency sau failover

Sau promote, kiểm tra timeline, archive, replicas và ứng dụng trước khi coi failover hoàn tất.

### Lỗi 20. Đọc conflict counter tuyệt đối

Counter tích lũy; cần delta và reset timestamp để biết tình hình hiện tại.

## 37. Bài tập thực hành

Các bài tập dùng PostgreSQL primary/standby trong môi trường lab. Không cố tình gây recovery conflict trên production.

### Bài 1. Hot standby

Hot standby là gì?

### Bài 2. Warm và hot

Khác biệt chính giữa warm standby và hot standby?

### Bài 3. Recovery state

Viết SQL kiểm tra server có đang ở recovery không.

### Bài 4. Read-only

Vì sao standby không cho phép INSERT/UPDATE/DELETE?

### Bài 5. Dữ liệu stale

Vì sao một row vừa commit trên primary có thể chưa xuất hiện trên standby?

### Bài 6. Read-after-write

Nêu hai cách xử lý yêu cầu đọc thấy ngay dữ liệu vừa ghi.

### Bài 7. Recovery conflict

Recovery conflict là gì?

### Bài 8. Conflict types

Kể năm nhóm conflict trong pg_stat_database_conflicts.

### Bài 9. Snapshot conflict

Vì sao VACUUM trên primary có thể khiến query standby bị cancel?

### Bài 10. Lock conflict

Nêu một ví dụ DDL gây lock conflict.

### Bài 11. Buffer pin

Buffer pin conflict xảy ra trong tình huống nào?

### Bài 12. Tablespace

Một thao tác nào trên primary có thể gây tablespace conflict?

### Bài 13. Archive delay

Tham số nào điều khiển conflict delay khi replay WAL từ archive?

### Bài 14. Streaming delay

Tham số nào điều khiển conflict delay khi replay streaming WAL?

### Bài 15. Delay -1

Giá trị -1 có ý nghĩa gì và rủi ro nào?

### Bài 16. Delay budget

Vì sao max_standby_streaming_delay không phải timeout riêng của query?

### Bài 17. hot_standby_feedback

Tham số này giúp giảm nhóm conflict nào?

### Bài 18. Bloat

Trade-off lớn của hot_standby_feedback là gì?

### Bài 19. Conflict stats

Viết SQL đọc conflict counters cho database hiện tại.

### Bài 20. Replication lag

Viết SQL đọc sent/write/flush/replay LSN từ pg_stat_replication.

### Bài 21. Standby replay

Viết SQL đọc receive LSN và replay LSN trên standby.

### Bài 22. Replay timestamp

Vì sao pg_last_xact_replay_timestamp có thể gây hiểu nhầm khi primary idle?

### Bài 23. Long transaction

Vì sao idle in transaction trên standby có thể gây vấn đề?

### Bài 24. Logging

Tham số nào giúp log các lần recovery conflict phải chờ lâu?

### Bài 25. Query retry

Nêu ba nguyên tắc retry query bị cancel do recovery conflict.

### Bài 26. statement_timeout

Khác biệt giữa statement_timeout và max_standby_streaming_delay?

### Bài 27. Replication slot

Vì sao lag trên standby có thể làm WAL retained tăng trên primary?

### Bài 28. Autovacuum

Vì sao không nên tắt autovacuum để tránh snapshot conflicts?

### Bài 29. Reporting standby

Nêu hai lợi ích và hai chi phí của reporting standby.

### Bài 30. Failover

Vì sao standby lag có thể ảnh hưởng dữ liệu khi promote?

### Bài 31. remote_apply

synchronous_commit=remote_apply hỗ trợ read-after-write như thế nào?

### Bài 32. Read routing

Nêu loại query nên route primary và loại có thể route standby.

### Bài 33. Query optimization

Kể ba cách giảm thời gian giữ snapshot trên standby.

### Bài 34. Feedback monitoring

Nêu hai chỉ số cần theo dõi khi bật hot_standby_feedback.

### Bài 35. Conflict troubleshooting

Nêu các bước đầu tiên khi nhận lỗi canceling statement due to conflict with recovery.

### Bài 36. Archive vs stream

Vì sao phải phân biệt WAL source khi điều chỉnh delay?

### Bài 37. Promotion

Điều gì thay đổi khi standby được promote?

### Bài 38. Conflict lab

Đề xuất cách tạo và quan sát snapshot conflict trong lab.

### Bài 39. Monitoring

Nêu ít nhất năm metrics cần giám sát cho hot standby.

### Bài 40. Thiết kế

Đề xuất cấu hình/vận hành cho một standby vừa phục vụ báo cáo vừa cần sẵn sàng failover.

## 38. Lời giải tham khảo

### Bài 1–6. Hot standby và consistency

Hot standby là standby replay WAL đồng thời phục vụ read-only queries. Warm standby chỉ chờ/replay WAL mà không phục vụ query đọc. Kiểm tra recovery bằng:

~~~sql
SELECT pg_is_in_recovery();
~~~

Standby không ghi vì mọi thay đổi phải đến từ WAL primary để giữ cùng lịch sử. Row mới commit có thể chưa được replay. Có thể route read-after-write tới primary hoặc đợi replay LSN đạt barrier sau commit.

### Bài 7–12. Recovery conflicts

Recovery conflict xảy ra khi WAL replay cần thực hiện thao tác xung đột với snapshot/lock/page resource của query standby. Năm nhóm là tablespace, lock, snapshot, buffer pin và deadlock. VACUUM cleanup có thể xóa row version mà snapshot standby còn cần. DROP/ALTER/TRUNCATE có thể cần lock mạnh. Buffer pin conflict xảy ra khi recovery cần page đang được backend pin. DROP TABLESPACE có thể gây tablespace conflict với query đang dùng tablespace đó.

### Bài 13–18. Delay và feedback

`max_standby_archive_delay` áp dụng cho archive WAL; `max_standby_streaming_delay` áp dụng cho streaming WAL. `-1` cho phép chờ vô hạn, nhưng replay lag và retained WAL có thể tăng. Delay budget gắn với WAL replay, không phải timer riêng bắt đầu khi mỗi query chạy. `hot_standby_feedback` giúp giảm snapshot conflicts do cleanup. Trade-off là primary giữ dead tuples lâu hơn và có thể bloat.

### Bài 19–22. Monitoring

~~~sql
SELECT *
FROM pg_stat_database_conflicts
WHERE datname = current_database();
~~~

~~~sql
SELECT
    application_name,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn
FROM pg_stat_replication;
~~~

Trên standby:

~~~sql
SELECT
    pg_last_wal_receive_lsn(),
    pg_last_wal_replay_lsn();
~~~

Replay timestamp có thể cũ vì primary không phát sinh transaction, nên cần kết hợp LSN và workload activity.

### Bài 23–26. Query behavior

Idle in transaction có thể giữ snapshot/lock dù backend không chạy query. `log_recovery_conflict_waits` ghi nhận conflict wait kéo dài. Retry cần có giới hạn, backoff/jitter và xác minh query không có side effects. `statement_timeout` giới hạn query runtime; max_standby delay giới hạn thời gian recovery chờ conflict.

### Bài 27–30. Storage và failover

Replication slot giữ WAL từ restart_lsn; standby lag làm vị trí này cũ và giữ nhiều WAL trên primary. Không tắt autovacuum vì có nguy cơ bloat và transaction ID wraparound. Reporting standby giảm tải đọc nhưng tiêu thụ tài nguyên và có thể tăng replay lag. Standby lag khi promote có thể làm mất các transaction primary đã commit nhưng standby chưa replay.

### Bài 31–34. Routing và feedback

Với synchronous standby và `synchronous_commit=remote_apply`, commit có thể đợi transaction được replay trên standby; query mới với snapshot mới sau commit có thể thấy dữ liệu đó. Writes/strong reads route primary; eventual reads/reporting có thể route standby. Giảm query duration bằng indexes, pagination, chia batch và kết thúc transaction sớm. Khi bật feedback, theo dõi conflict counters cùng dead tuple/table growth và vacuum progress trên primary.

### Bài 35–39. Vận hành

Bắt đầu bằng SQLSTATE/message/time, xác định standby/database, đọc conflict counter delta, tìm query/transaction dài và đối chiếu DDL/VACUUM trên primary. Phân biệt archive/stream để điều chỉnh đúng delay. Promotion kết thúc recovery và tạo timeline mới. Trong lab, giữ một SELECT snapshot mở trên standby rồi VACUUM DELETE/UPDATE trên primary để quan sát snapshot conflict. Metrics gồm replay lag, receive/replay LSN, conflict deltas, ready backlog, slot retained WAL, query age, primary dead tuples và query cancellation/retry rate.

### Bài 40. Thiết kế

Tách một standby ưu tiên failover freshness với query ngắn và delay hạn chế; dùng một reporting standby riêng nếu báo cáo dài. Trên reporting standby có thể tăng delay có giới hạn và cân nhắc hot_standby_feedback, đồng thời giám sát bloat trên primary. Ứng dụng route writes/strong reads tới primary, eventual reads tới standby, retry cancellation có budget. Theo dõi LSN lag, conflict counters, slot retention, disk và restore/failover drills định kỳ.

## 39. Bảng tra cứu nhanh

| Nhu cầu | Công cụ/tham số |
| --- | --- |
| Kiểm tra đang recovery | pg_is_in_recovery() |
| Bật query trên standby | hot_standby = on |
| Conflict delay cho archive WAL | max_standby_archive_delay |
| Conflict delay cho streaming WAL | max_standby_streaming_delay |
| Feedback xmin về primary | hot_standby_feedback |
| Log conflict wait kéo dài | log_recovery_conflict_waits |
| Thống kê recovery conflicts | pg_stat_database_conflicts |
| Replication state trên primary | pg_stat_replication |
| WAL receiver state trên standby | pg_stat_wal_receiver |
| Query/transaction age | pg_stat_activity |
| Receive LSN | pg_last_wal_receive_lsn() |
| Replay LSN | pg_last_wal_replay_lsn() |
| Replay timestamp | pg_last_xact_replay_timestamp() |
| WAL distance | pg_wal_lsn_diff() |
| Slot retained WAL | pg_replication_slots |
| Dead tuple estimates | pg_stat_user_tables |
| Vacuum progress | pg_stat_progress_vacuum |
| Read-only transaction | SET TRANSACTION READ ONLY |
| Statement duration limit | statement_timeout |
| Idle transaction limit | idle_in_transaction_session_timeout |

## 40. Checklist vận hành hot standby

1. Primary dùng wal_level phù hợp cho physical replication.
2. Standby bật hot_standby và đã restart khi thay đổi cần restart.
3. Replication role, pg_hba và TLS được cấu hình an toàn.
4. Standby signal và primary_conninfo trỏ đúng upstream.
5. Standby đã đạt consistency point và nhận query được.
6. Ứng dụng chỉ gửi read-only workload tới standby.
7. Writes và strong read-after-write được route tới primary hoặc chờ replay barrier.
8. Query dài và idle-in-transaction được giám sát.
9. max_standby_archive_delay được cấu hình theo archive workload.
10. max_standby_streaming_delay được cấu hình theo streaming workload.
11. Không nhầm delay settings với statement_timeout.
12. hot_standby_feedback được bật/tắt theo trade-off có đo lường.
13. Primary dead tuples và vacuum progress được theo dõi khi feedback bật.
14. Conflict counters được scrape và tính delta.
15. Recovery conflict waits được log khi cần điều tra.
16. Replication receive/replay LSN và lag được theo dõi.
17. Replication slots và retained WAL được giám sát.
18. Primary pg_wal disk usage có cảnh báo.
19. Query cancellation được phân loại và retry có giới hạn.
20. Reporting query được tối ưu/index/paginate.
21. Query dài được tách sang reporting standby riêng khi cần.
22. Failover standby có replay lag phù hợp RPO.
23. Promotion có fencing primary cũ để tránh split-brain.
24. Sau promotion, kiểm tra timeline, archive và replicas.
25. Restore/failover drills được thực hiện định kỳ và lưu kết quả.

## 41. Tổng kết

Hot standby cho phép PostgreSQL vừa replay WAL vừa phục vụ các truy vấn chỉ đọc. Đây là cách hữu ích để giảm tải query trên primary và cung cấp read replica, nhưng dữ liệu trên standby luôn phản ánh trạng thái đã replay chứ không nhất thiết là trạng thái mới nhất của primary.

Recovery conflicts xảy ra khi WAL replay cần cleanup row versions, lấy lock mạnh, thay đổi tablespace hoặc sử dụng page đang bị query giữ. PostgreSQL có thể trì hoãn replay trong giới hạn `max_standby_archive_delay` hoặc `max_standby_streaming_delay`, rồi hủy query nếu conflict chưa được giải phóng. Các counters trong `pg_stat_database_conflicts` và log recovery conflict waits giúp xác định nguyên nhân.

`hot_standby_feedback` có thể giảm snapshot conflicts bằng cách yêu cầu primary giữ lại row versions mà standby còn cần. Đổi lại, primary có thể giữ dead tuples lâu hơn và tăng bloat. Vì vậy cần theo dõi cả query cancellation, replay lag, replication slots, disk usage và vacuum health.

Một hệ thống hot standby ổn định cần routing rõ giữa primary và replica, query đọc ngắn và tối ưu, transaction không mở lâu, retry có giới hạn, delay settings theo SLA và restore/failover drills thường xuyên. Nếu báo cáo dài xung đột với yêu cầu failover nhanh, tách reporting standby và failover standby sẽ giúp mỗi replica phục vụ một mục tiêu rõ ràng.
