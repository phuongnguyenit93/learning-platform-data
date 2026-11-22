# Phục hồi thao tác xóa nhầm và phân biệt với sự cố hạ tầng trong PostgreSQL

Khi dữ liệu PostgreSQL bị xóa nhầm, phản xạ đầu tiên thường là restart database hoặc chuyển traffic sang standby. Hai hành động đó có thể không khôi phục được dữ liệu đã mất. Với physical replication, một lệnh DELETE hoặc DROP hợp lệ trên primary thường cũng được replay sang standby. Failover sang replica vì vậy có thể mang nguyên trạng thái đã bị xóa sang node mới.

Phục hồi đúng bắt đầu bằng việc xác định **điều gì đã xảy ra, thời điểm nào, dữ liệu nào bị ảnh hưởng và hệ thống còn những bản sao/WAL nào**. Nếu thao tác xóa đã commit, cách khôi phục phổ biến là dùng base backup và WAL archive để Point-in-Time Recovery (PITR) tới một thời điểm ngay trước thao tác, trên một cluster độc lập. Sau đó trích xuất dữ liệu cần thiết và đưa trở lại hệ thống đang hoạt động theo kế hoạch có kiểm soát.

Sự cố hạ tầng có bản chất khác. Nếu máy chủ, volume, availability zone hoặc cả region bị mất, mục tiêu có thể là failover sang standby, khôi phục từ backup hoặc dựng lại hệ thống tại địa điểm khác. Phải phân biệt hai tình huống vì **HA duy trì dịch vụ khi node/hạ tầng gặp lỗi; backup và PITR giúp quay lại trạng thái dữ liệu trước một sự kiện**.

Bài học này trình bày quy trình ứng phó khi xóa nhầm, lựa chọn recovery target, dựng cluster khôi phục, lấy lại rows/tables, xử lý DELETE/TRUNCATE/DROP, phân biệt lỗi dữ liệu với lỗi hạ tầng, cùng các runbook và bài tập thực hành.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân loại DELETE chưa commit, DELETE đã commit, TRUNCATE, DROP TABLE và DROP DATABASE.
2. Xác định thời điểm sự cố và phạm vi dữ liệu bị ảnh hưởng.
3. Giữ lại bằng chứng và ngăn các thao tác tiếp theo làm mất recovery options.
4. Giải thích vì sao physical standby thường replay cả thao tác xóa nhầm.
5. Phân biệt failover, PITR, restore từ base backup và logical restore.
6. Dùng base backup và WAL archive để phục hồi tới một recovery target.
7. Hiểu recovery_target_time, recovery_target_lsn, recovery_target_xid, inclusive và recovery_target_action.
8. Khôi phục trên cluster cô lập và trích xuất dữ liệu cần thiết.
9. Đưa dữ liệu trở lại production bằng INSERT, COPY, pg_dump/pg_restore hoặc quy trình ứng dụng.
10. Tránh ghi đè dữ liệu mới được tạo sau thời điểm PITR.
11. Xử lý sự cố host, disk, filesystem, network, availability zone và region.
12. Chọn failover hay restore dựa trên loại lỗi và RPO/RTO.
13. Xây dựng quy trình bảo vệ WAL archive, base backup, credentials và restore environment.
14. Lập kế hoạch kiểm tra sau khôi phục và phòng ngừa tái diễn.

## 2. Phân loại sự cố trước khi hành động

Không phải mọi lỗi database đều cần PITR. Hãy phân loại trước:

| Tình huống | Ví dụ | Hướng xử lý ban đầu |
| --- | --- | --- |
| Thao tác chưa commit | DELETE trong transaction còn mở | ROLLBACK nếu đúng transaction và chưa commit |
| Thao tác đã commit | DELETE nhầm một nhóm khách hàng | PITR sang cluster riêng, trích xuất dữ liệu |
| Xóa cấu trúc | DROP TABLE hoặc DROP DATABASE | PITR/backup restore; sau đó lấy object/data |
| Xóa một phần | DELETE có WHERE sai | PITR hoặc nguồn dữ liệu khác; merge rows có kiểm soát |
| Lỗi logic ứng dụng | Job cập nhật sai hàng triệu rows | Dừng job, xác định thời điểm và phạm vi, PITR/repair |
| Hỏng host/VM | OS hoặc instance không hoạt động | Failover hoặc dựng lại từ backup |
| Hỏng storage | Volume lỗi, filesystem corruption | Dừng ghi, bảo toàn storage, restore/DR |
| Mất availability zone/region | Không truy cập được primary và storage | DR failover hoặc restore tại region khác |
| Network partition | Primary và standby mất kết nối | Đánh giá quorum/fencing, tránh split brain |
| Database process crash | PostgreSQL dừng bất thường | Crash recovery; kiểm tra WAL/data integrity |

### 2.1. Xóa nhầm là logical data loss

Một câu lệnh SQL hợp lệ có thể xóa dữ liệu mà không tạo ra lỗi PostgreSQL. Server thực hiện đúng yêu cầu; lỗi nằm ở thao tác hoặc logic nghiệp vụ. Khi transaction commit, thay đổi đó trở thành một phần lịch sử database và được physical replication truyền tới standby.

### 2.2. Sự cố hạ tầng là availability hoặc physical integrity failure

Máy chủ mất điện, volume không mount được hoặc network không truy cập được có thể làm database unavailable dù dữ liệu logic chưa bị xóa. Cần xác định có thể restart/crash-recover tại node cũ, promote standby hay restore sang hạ tầng mới.

### 2.3. Một sự cố có thể gồm cả hai loại

Ví dụ một volume bị lỗi trong lúc một job xóa nhầm đang chạy. Cần xử lý đồng thời tính toàn vẹn dữ liệu và khả năng phục hồi hạ tầng. Không chọn phương án chỉ dựa vào triệu chứng đầu tiên.

## 3. Câu hỏi đầu tiên: transaction đã commit chưa?

Nếu thao tác xóa nằm trong transaction chưa commit, PostgreSQL vẫn có thể rollback toàn bộ thay đổi.

~~~sql
BEGIN;

DELETE FROM app.orders
WHERE created_at < DATE '2020-01-01';

-- Phát hiện điều kiện WHERE sai trước COMMIT
ROLLBACK;
~~~

ROLLBACK hủy thay đổi của transaction đó.

### 3.1. Transaction đã commit

~~~sql
BEGIN;

DELETE FROM app.orders
WHERE order_id = 12345;

COMMIT;
~~~

Sau COMMIT, ROLLBACK trong một transaction mới không thể đảo ngược transaction cũ. PostgreSQL không có lệnh undo commit tổng quát để tự phục hồi rows đã xóa.

### 3.2. Transaction còn mở ở session khác

Nếu bạn có đúng session/backend đang thực hiện thao tác và transaction chưa commit, có thể rollback từ session đó. Không terminate backend một cách mù quáng; xác minh PID, owner và transaction trước.

### 3.3. Savepoint

Savepoint chỉ giúp quay lại một điểm bên trong transaction hiện tại:

~~~sql
BEGIN;
SAVEPOINT before_delete;

DELETE FROM app.customers WHERE ...;

ROLLBACK TO SAVEPOINT before_delete;
COMMIT;
~~~

Savepoint không thể khôi phục một transaction đã commit trong quá khứ.

### 3.4. DELETE trong autocommit

Nhiều client chạy mỗi statement trong transaction riêng và tự commit khi statement thành công. Nếu người dùng thực thi DELETE trực tiếp ở chế độ autocommit, thay đổi có thể đã commit ngay khi statement hoàn tất.

## 4. Những việc cần làm ngay khi phát hiện xóa nhầm

Mục tiêu đầu tiên là giữ nguyên các lựa chọn khôi phục và giảm phạm vi tác động.

1. Dừng job, script, deployment hoặc thao tác đang tiếp tục xóa/sửa dữ liệu.
2. Xác định database, schema, table, tenant và điều kiện WHERE liên quan.
3. Ghi lại thời gian phát hiện và ước lượng thời gian thao tác xảy ra.
4. Lưu query text, application name, PID, user, transaction ID và logs nếu có.
5. Xác định transaction đã commit hay chưa.
6. Kiểm tra primary, standbys, base backups, WAL archive và retention.
7. Tránh chạy cleanup hoặc xóa backup/WAL trong lúc điều tra.
8. Chọn restore target và cluster đích độc lập.
9. Thông báo cho owner dữ liệu và người chịu trách nhiệm quyết định recovery.
10. Ghi lại mọi thay đổi vận hành kể từ khi sự cố xảy ra.

### 4.1. Dừng nguồn gây lỗi

Nếu một application worker đang chạy DELETE sai, hãy pause worker hoặc chặn đúng đường thực thi. Không cần tắt toàn bộ database nếu có thể dừng chính xác nguồn lỗi.

### 4.2. Bảo toàn log và metadata

Thu thập PostgreSQL logs, application logs, job logs, audit records, deployment timestamps, query IDs và backup catalog. Các thông tin này giúp tìm recovery target.

### 4.3. Không chạy PITR trên primary hiện tại

PITR thường tạo một cluster được phục hồi tới trạng thái quá khứ. Thực hiện trên một data directory/instance riêng để giữ primary hiện tại và các thay đổi hợp lệ sau sự cố.

### 4.4. Không promote standby theo phản xạ

Nếu standby đã replay DELETE, promote standby chỉ tạo primary mới với dữ liệu đã bị xóa. Trước failover, xác định standby replay position và xem nó có thực sự ở trạng thái dữ liệu mong muốn hay không.

## 5. Tìm thời điểm thao tác xóa

PITR cần một recovery target đủ chính xác để dừng trước transaction gây mất dữ liệu.

### 5.1. Nguồn thời gian

Có thể kết hợp PostgreSQL server logs, application logs và request IDs, job scheduler history, audit extension hoặc audit table, transaction timestamps trong dữ liệu còn lại, monitoring/alert timestamps và WAL decoding tooling phù hợp.

### 5.2. Thời gian client và server có thể khác

Client, application server, database host và log collector có thể dùng timezone hoặc clock khác nhau. Chuẩn hóa về UTC, kiểm tra NTP/clock drift và phân biệt thời điểm gửi query với thời điểm transaction commit.

### 5.3. Query start không phải commit time

Một DELETE có thể chạy lâu. Query start là lúc bắt đầu statement; commit xảy ra sau đó. Recovery target cần nằm trước commit gây mất dữ liệu, không nhất thiết trước query start.

### 5.4. Transaction có nhiều statements

Nếu transaction xóa dữ liệu rồi thực hiện các thay đổi hợp lệ khác trước COMMIT, PITR trước commit sẽ loại bỏ toàn bộ transaction đó. Sau restore cần đánh giá các thay đổi hợp lệ cùng transaction để tái áp dụng nếu cần.

### 5.5. Tìm qua application request

Nếu application logs có request ID, map request đó tới job, database session, application_name hoặc query log. Tránh suy ra thời gian từ một dashboard có sampling thưa.

## 6. Xác định phạm vi dữ liệu bị xóa

Trước khi phục hồi, lập danh sách cụ thể:

- Tên database/schema/table.
- Primary keys hoặc business keys bị ảnh hưởng.
- Khoảng thời gian rows được tạo/cập nhật.
- Số lượng rows ước tính.
- Các foreign keys và bảng phụ thuộc.
- Triggers, audit tables, outbox/event tables liên quan.
- Các thay đổi hợp lệ sau sự cố cần được giữ lại.

### 6.1. DELETE theo điều kiện

Ví dụ:

~~~sql
DELETE FROM app.orders
WHERE tenant_id = 42
  AND status <> 'archived';
~~~

Phạm vi có thể là tất cả orders của tenant 42 trừ archived. Hãy tìm query thực tế và parameter values; query template đơn thuần có thể chưa đủ để xác định rows.

### 6.2. TRUNCATE

TRUNCATE loại bỏ toàn bộ rows của table nhanh hơn DELETE thông thường và có semantics transaction riêng. Nó có thể CASCADE nếu dùng tùy chọn tương ứng. Phục hồi thường cần PITR/backup hoặc bản sao khác.

### 6.3. DROP TABLE

DROP TABLE xóa relation và metadata liên quan. Nếu đã commit, cần phục hồi schema/table từ một trạng thái trước DROP, rồi lấy dữ liệu cần thiết.

### 6.4. DROP DATABASE

DROP DATABASE xóa toàn bộ database. Phục hồi thường cần dựng cluster/database từ base backup hoặc PITR tới trước lệnh DROP. Một database khác trên cùng cluster có thể vẫn tồn tại, nhưng phải kiểm tra scope.

### 6.5. CASCADE

DROP ... CASCADE có thể xóa các objects phụ thuộc. Khi phục hồi, cần xác định toàn bộ dependency graph: views, foreign keys, functions, types và các objects liên quan.

## 7. Vì sao physical standby không cứu được thao tác xóa nhầm?

Physical replication sao chép WAL để tái tạo thay đổi vật lý trên standby. Nếu DELETE đã commit trên primary, standby thường replay thay đổi đó.

~~~text
Primary
  DELETE FROM app.customers WHERE id = 42;
       |
       v
      WAL
       |
       v
Physical standby replays WAL
       |
       v
Row id=42 cũng biến mất trên standby
~~~

### 7.1. Standby phù hợp cho node failure

Nếu primary host chết nhưng standby khỏe và đã nhận đủ WAL cần thiết, promote standby có thể giảm downtime.

### 7.2. Standby không phải historical snapshot

Standby thường cố theo kịp primary. Nó không giữ tự động một bản dữ liệu ở trạng thái ngày hôm qua để quay lại.

### 7.3. Replication delay không phải recovery policy

Một standby bất đồng bộ có thể chậm vài giây hoặc vài phút. Dựa vào độ trễ ngẫu nhiên để cứu một DELETE là không đáng tin cậy. Khi standby replay transaction xóa, cơ hội này mất.

### 7.4. Delayed standby

PostgreSQL có thể cấu hình recovery_min_apply_delay để trì hoãn replay WAL trên standby. Đây là một lớp phòng vệ có giới hạn: delay phải lớn hơn thời gian phát hiện và hành động; WAL vẫn cần được giữ; người vận hành phải dừng recovery trước khi transaction xóa được replay. Delay làm tăng lag và có thể gây vấn đề failover/RPO. Nó không thay thế backup/PITR.

## 8. Phân biệt HA, backup, PITR và DR

| Cơ chế | Mục tiêu | Phục hồi thao tác xóa nhầm? | Phục hồi mất node/region? |
| --- | --- | --- | --- |
| Physical standby | Availability, failover | Thường không; xóa được replay | Có thể |
| Synchronous replication | Giảm mất commit khi failover | Không; commit xóa cũng được xác nhận/replay | Có thể |
| Base backup | Có điểm khởi đầu để restore | Có, nhưng cần trạng thái trước sự cố/WAL phù hợp | Có |
| WAL archive + PITR | Quay về một thời điểm | Có | Có, nếu backup/archive còn truy cập được |
| Logical dump | Phục hồi object/data đã dump | Có nếu dump trước sự cố | Có cho phần được dump |
| Delayed standby | Cửa sổ phát hiện lỗi logic | Có thể, nếu dừng replay đúng lúc | Có giới hạn |
| Storage snapshot | Bản sao storage tại thời điểm snapshot | Có nếu snapshot trước sự cố và nhất quán | Tùy kiến trúc |

### 8.1. High Availability

HA giảm downtime khi một thành phần thất bại. Nó thường ưu tiên nhanh chóng đưa dịch vụ về trạng thái hoạt động.

### 8.2. Backup

Backup cung cấp bản dữ liệu có thể khôi phục độc lập. Nó phải được lưu ở failure domain phù hợp và được kiểm tra.

### 8.3. Point-in-Time Recovery

PITR dùng base backup cộng WAL để tái tạo trạng thái database tại một điểm trong lịch sử.

### 8.4. Disaster Recovery

DR bao gồm cả con người, hạ tầng, credentials, backup copies, network, DNS, ứng dụng và quy trình khôi phục tại failure domain khác. Một file backup duy nhất chưa phải DR plan.

## 9. PITR hoạt động như thế nào?

Một base backup là bản sao vật lý nhất quán của cluster tại một khoảng thời gian. PostgreSQL cần WAL để replay các thay đổi cần thiết và hoàn tất recovery.

~~~text
Base backup
    |
    v
Khởi động recovery
    |
    v
Replay WAL liên tục
    |
    v
Đạt recovery target
    |
    +--> Pause
    +--> Promote
    +--> Shutdown
~~~

### 9.1. Base backup và WAL chain

Để phục hồi tới một thời điểm, phải có:

1. Base backup hợp lệ.
2. WAL liên tục từ điểm cần thiết của backup tới recovery target.
3. Timeline history files nếu recovery đi qua timeline changes.
4. Cấu hình restore_command có thể lấy WAL.
5. Storage, permissions và PostgreSQL version tương thích.

### 9.2. WAL không phải log SQL dễ đọc

WAL chứa records ở mức storage và transaction. Không nên kỳ vọng tìm một câu DELETE bằng cách grep file WAL. Dùng logs/audit để tìm query; dùng WAL để phục hồi theo cơ chế PostgreSQL.

### 9.3. PITR là cấp cluster

Physical PITR phục hồi trạng thái của cluster/database system tại một điểm, không phải một nút undo độc lập cho một row. Muốn chỉ lấy lại một table, thường restore cả cluster sang nơi riêng rồi export table/rows cần thiết.

### 9.4. Một lần restore tạo timeline mới khi promote

Nếu recovery dừng ở target và promote, instance bắt đầu ghi WAL theo timeline mới. Giữ riêng cluster PITR để điều tra hoặc trích xuất; đừng nhầm timeline mới với lịch sử production hiện tại.

## 10. Chọn recovery target

PostgreSQL hỗ trợ các loại recovery target như recovery_target_time, recovery_target_lsn, recovery_target_xid, recovery_target_name và recovery_target = immediate. Tên, hành vi và cách cấu hình phụ thuộc major version. Đọc tài liệu đúng phiên bản trước khi chạy.

### 10.1. recovery_target_time

Dừng recovery theo timestamp:

~~~conf
recovery_target_time = '2026-11-14 02:17:30+00'
~~~

Đây là lựa chọn thường dùng khi có timestamp đáng tin từ logs. Đặt target trước commit xóa và kiểm tra inclusive semantics.

### 10.2. recovery_target_lsn

Dừng theo LSN:

~~~conf
recovery_target_lsn = '0/7A120F0'
~~~

LSN phù hợp khi có vị trí WAL chính xác từ replication/diagnostic tooling. Không đoán LSN từ thời gian.

### 10.3. recovery_target_xid

Dừng theo transaction ID khi đã xác định đúng transaction gây sự cố và hiểu semantics target. Transaction IDs có thể wraparound; không dùng một con số từ log cũ mà không xác minh context.

### 10.4. recovery_target_name

Có thể đặt named restore point trước một deployment hoặc thao tác nguy hiểm:

~~~sql
SELECT pg_create_restore_point('before_customer_cleanup');
~~~

Sau đó dùng recovery_target_name với tên tương ứng trong recovery config. Restore point cần được tạo trước sự kiện; không thể tạo hồi tố sau khi đã xóa nhầm.

### 10.5. recovery_target = immediate

Dùng để dừng tại điểm sớm nhất có thể sau khi backup đã đạt trạng thái consistent theo cơ chế recovery. Nó hữu ích cho một số workflow clone/test, nhưng không có nghĩa “trước lệnh DELETE”.

## 11. Inclusive và exclusive target

PostgreSQL có setting recovery_target_inclusive để quyết định có bao gồm transaction/record tại target hay dừng trước target theo loại target được chọn.

~~~conf
recovery_target_time = '2026-11-14 02:17:30+00'
recovery_target_inclusive = false
~~~

### 11.1. Ý nghĩa cần xác minh

Inclusive semantics phụ thuộc loại target và cách PostgreSQL xác định điểm dừng. Đối với time target, transaction commit boundary quan trọng. Không suy luận rằng đặt một timestamp bằng thời gian log là chắc chắn đã loại bỏ transaction xóa.

### 11.2. Chọn target an toàn

Nếu commit xảy ra khoảng 02:17:30, hãy chọn một target rõ ràng trước thời điểm đó, sau đó kiểm tra dữ liệu trên restored cluster. Nếu không chắc, restore một vài candidate targets trên môi trường dùng một lần.

### 11.3. recovery_target_action

Các lựa chọn thường gặp:

- pause: dừng replay tại target và giữ instance ở trạng thái recovery để kiểm tra.
- promote: hoàn tất recovery và promote thành primary mới.
- shutdown: tắt server khi đạt target.

Với tình huống xóa nhầm, pause thường hữu ích để kiểm tra trước khi quyết định promote. Nếu mục tiêu chỉ là đọc/export, không cần promote nếu có thể truy cập dữ liệu ở trạng thái recovery phù hợp.

## 12. Cấu hình PITR trên cluster riêng

Ví dụ workflow với PostgreSQL hiện đại:

1. Chuẩn bị base backup vào directory riêng.
2. Chuẩn bị WAL archive đầy đủ.
3. Copy base backup vào PGDATA của restore instance.
4. Tạo recovery.signal.
5. Cấu hình restore_command và target.
6. Start instance trên port và network riêng.
7. Quan sát logs tới khi recovery dừng.

Ví dụ cấu hình:

~~~conf
restore_command = 'cp /backup/archive/%f %p'
recovery_target_time = '2026-11-14 02:17:00+00'
recovery_target_inclusive = false
recovery_target_action = 'pause'
~~~

Đây là cấu hình minh họa cho archive lưu trên filesystem. Nếu dùng object storage, cần fetch command/script phù hợp. Không dùng đường dẫn production nếu có nguy cơ ghi đè hoặc đọc nhầm cluster.

### 12.1. recovery.signal

Trên các phiên bản hiện đại, tạo file recovery.signal trong data directory để yêu cầu archive recovery/PITR. Các phiên bản cũ có cách cấu hình khác; kiểm tra tài liệu đúng major version.

### 12.2. standby.signal

standby.signal dùng cho standby mode, thường kết hợp primary_conninfo/streaming. Không nhầm standby bootstrap với PITR độc lập.

### 12.3. Không cấu hình recovery trên primary production

Đừng đặt recovery.signal hoặc recovery target vào PGDATA đang phục vụ production. Dùng bản sao data directory riêng.

### 12.4. Restore command phải xử lý lỗi

Command cần trả exit status đúng khi WAL file không tồn tại và có thể được gọi lại. Với object storage, cần timeout/retry có giới hạn và logs không chứa secrets.

## 13. Runbook: phục hồi DELETE đã commit

Giả sử một DELETE nhầm đã commit tại thời điểm T.

### Bước 1: Dừng tác nhân gây lỗi

Pause worker/job hoặc deploy hotfix để không tiếp tục xóa. Nếu có thể, giữ ứng dụng ở chế độ read-only hoặc hạn chế đúng chức năng gây lỗi.

### Bước 2: Xác định thời điểm commit

Thu thập logs và xác định một target ngay trước transaction commit. Chuẩn hóa timestamp/UTC và ghi lại độ tin cậy.

### Bước 3: Kiểm tra recovery assets

Xác nhận base backup phù hợp, WAL archive liên tục, timeline history và quyền truy cập encryption keys.

### Bước 4: Dựng PITR cluster riêng

Restore backup vào host/volume khác, dùng port khác, network riêng và recovery target trước transaction xóa.

### Bước 5: Xác minh kết quả

Kiểm tra rows/keys bị xóa có mặt. Kiểm tra các dữ liệu hợp lệ trước target. Xác định chính xác số rows cần trích xuất.

### Bước 6: Export dữ liệu

Dùng pg_dump cho table hoặc COPY/query có điều kiện. Lưu schema, constraints, indexes và dependency metadata cần thiết.

### Bước 7: Đưa dữ liệu về production

Import vào staging table, kiểm tra conflicts/duplicates/foreign keys rồi merge bằng transaction hoặc migration script đã review.

### Bước 8: Kiểm tra ứng dụng

Chạy queries nghiệp vụ, row counts, aggregate checks và smoke tests.

### Bước 9: Ghi nhận

Lưu recovery target, backup ID, WAL range, số rows khôi phục, script, approver và thời gian hoàn tất.

## 14. Vì sao nên restore sang cluster riêng?

Giả sử thao tác xóa xảy ra lúc 02:17 và production tiếp tục nhận đơn hàng tới 03:00.

Nếu rollback toàn bộ production về 02:16:
- Các đơn hàng hợp lệ tạo sau 02:17 sẽ biến mất.
- Các thay đổi hợp lệ khác cũng bị mất.
- Ứng dụng có thể không biết các request đã thành công sau target.

Thay vào đó:

~~~text
Production hiện tại (03:00)
  Dữ liệu mới + trạng thái đã xóa nhầm
          |
          | Không rollback cluster này
          |
PITR cluster (02:16)
  Trạng thái trước DELETE
          |
          v
Export rows cần khôi phục
          |
          v
Production staging table
          |
          v
Merge có kiểm tra
~~~

### 14.1. Bảo toàn writes hợp lệ

Restore riêng giúp giữ các writes production sau sự cố. Chỉ dữ liệu mục tiêu được trích xuất và merge.

### 14.2. Có thể so sánh hai trạng thái

Bạn có thể đối chiếu current production với PITR cluster để tìm rows thiếu, rows đã được cập nhật lại hoặc rows có xung đột.

### 14.3. Tránh split brain

PITR cluster chỉ dùng để đọc/export. Không cho ứng dụng production ghi vào cluster này hoặc cho cả hai cluster nhận traffic ghi độc lập.

### 14.4. Giữ cluster PITR tới khi kết thúc điều tra

Đừng xóa restore instance ngay sau export nếu cần bằng chứng hoặc có thể phải lấy thêm dữ liệu. Đặt retention và quyền truy cập phù hợp.

## 15. Trích xuất table bằng pg_dump

Nếu cần toàn bộ một table tại recovery target:

~~~bash
pg_dump \
  --host=pitr-db.example.internal \
  --port=55432 \
  --username=restore_reader \
  --dbname=appdb \
  --table=app.customers \
  --format=custom \
  --file=/recovery/export/customers.dump
~~~

Restore vào database/staging:

~~~bash
pg_restore \
  --host=production-staging.example.internal \
  --port=5432 \
  --username=restore_operator \
  --dbname=recovery_staging \
  --no-owner \
  --no-privileges \
  /recovery/export/customers.dump
~~~

### 15.1. Table dump không luôn bao gồm mọi dependency

Một table dump có thể không bao gồm mọi object phụ thuộc như roles, grants, functions, types hoặc các bảng tham chiếu. Kiểm tra schema và dependencies.

### 15.2. Dùng schema-only nếu cần so sánh

pg_dump có thể xuất schema riêng. So sánh DDL giữa PITR và production trước khi restore dữ liệu nếu schema đã thay đổi sau sự cố.

### 15.3. Đừng restore thẳng lên table production đang có

Restore vào staging table/database trước. Tên table trùng hoặc schema khác có thể gây xung đột, ghi đè hoặc lỗi constraint.

## 16. Trích xuất rows bằng COPY

Nếu chỉ cần một tập rows:

~~~sql
COPY (
    SELECT customer_id, email, created_at, status
    FROM app.customers
    WHERE tenant_id = 42
) TO '/recovery/export/customers.csv'
WITH (FORMAT csv, HEADER true);
~~~

Đường dẫn file trong COPY là đường dẫn phía server database và process PostgreSQL cần quyền truy cập. Nếu chạy từ client, dùng psql \copy để ghi file trên máy client.

Ví dụ:

~~~sql
\copy (SELECT customer_id, email, created_at, status FROM app.customers WHERE tenant_id = 42) TO '/recovery/export/customers.csv' WITH (FORMAT csv, HEADER true)
~~~

### 16.1. Chọn columns tường minh

Không dùng SELECT * trong quy trình khôi phục dài hạn nếu schema có thể khác giữa PITR và production. Chọn columns rõ ràng và map types.

### 16.2. Dữ liệu nhị phân và encoding

CSV có thể cần xử lý quoting, NULL, delimiter, encoding và bytea. Với dữ liệu phức tạp, custom-format pg_dump hoặc COPY binary có thể phù hợp hơn.

### 16.3. Bảo vệ file export

File export có thể chứa PII hoặc payment-related data. Lưu ở encrypted staging, giới hạn quyền, đặt retention ngắn và xóa an toàn theo policy sau khi hoàn tất.

## 17. Merge rows trở lại production

Trước khi import, xác định rows hiện tại có thể đã được tạo lại hoặc cập nhật sau sự cố.

### 17.1. Dùng staging table

~~~sql
CREATE SCHEMA IF NOT EXISTS recovery_stage;

CREATE TABLE recovery_stage.customers_restore
(LIKE app.customers INCLUDING DEFAULTS);
~~~

Nạp rows vào staging table qua COPY hoặc pg_restore theo workflow phù hợp.

### 17.2. Kiểm tra duplicate keys

~~~sql
SELECT r.customer_id
FROM recovery_stage.customers_restore AS r
JOIN app.customers AS c
  ON c.customer_id = r.customer_id;
~~~

Các keys trùng có thể là rows đã được tạo lại hoặc rows hiện tại cần reconcile. Không tự động overwrite.

### 17.3. INSERT có điều kiện

Nếu business rule cho phép chỉ thêm các keys chưa có:

~~~sql
INSERT INTO app.customers (
    customer_id, email, created_at, status
)
SELECT
    r.customer_id, r.email, r.created_at, r.status
FROM recovery_stage.customers_restore AS r
WHERE NOT EXISTS (
    SELECT 1
    FROM app.customers AS c
    WHERE c.customer_id = r.customer_id
);
~~~

Đây chỉ là mẫu. Cần kiểm tra foreign keys, unique constraints, defaults, generated columns, triggers và dữ liệu phụ thuộc trước khi áp dụng.

### 17.4. Upsert không phải luôn đúng

ON CONFLICT DO UPDATE có thể ghi đè thay đổi hợp lệ phát sinh sau recovery target. Chỉ dùng khi có quy tắc rõ về precedence và versioning.

### 17.5. Transaction boundaries

Merge trong transaction nếu khối lượng và lock duration cho phép. Với dữ liệu lớn, chia batch có checkpoint và idempotency, nhưng ghi lại chính xác tiến độ để có thể resume.

### 17.6. Foreign keys

Khôi phục parent rows trước child rows. Nếu parent đã được tạo lại với key khác hoặc child references đã đổi, cần reconcile thay vì ép constraint.

## 18. Khôi phục DELETE nhầm nhưng giữ các updates hợp lệ

Một row có thể đã bị xóa rồi được tạo lại hoặc được thay đổi ở một hệ thống khác sau sự cố.

Ví dụ:
- Customer bị xóa lúc 02:17.
- Support tạo lại customer record lúc 02:30.
- Production hiện tại có row mới với cùng business email nhưng ID khác.

Nếu import row cũ nguyên trạng, có thể tạo duplicate hoặc làm sai foreign keys.

### 18.1. So sánh theo business key

So sánh customer number, external ID hoặc key nghiệp vụ ổn định, không chỉ dựa vào surrogate ID.

### 18.2. So sánh row versions

Nếu có updated_at/version column, dùng để xác định bản nào mới hơn. Timestamp không phải lúc nào cũng đáng tin nếu clock skew hoặc application không cập nhật nhất quán.

### 18.3. Audit trail

Nếu có audit table hoặc event log, dùng để tái tạo các thay đổi hợp lệ sau target. Không dựa vào một snapshot cũ để ghi đè lịch sử mới.

### 18.4. Domain-specific reconciliation

Đơn hàng, thanh toán, tồn kho và tài khoản có semantics khác nhau. Một đơn hàng đã được thanh toán sau sự cố không thể chỉ khôi phục bằng cách INSERT row cũ mà bỏ qua ledger/payment provider.

## 19. Khôi phục DROP TABLE

Khi table bị DROP:

1. Xác định thời điểm DROP commit.
2. Restore cluster tới trước DROP trên môi trường riêng.
3. Xác định table definition, indexes, constraints, triggers, ownership và grants.
4. Export table schema/data.
5. So sánh với schema production hiện tại.
6. Tạo table staging hoặc table đích theo migration có kiểm soát.
7. Nạp dữ liệu và kiểm tra dependencies.

### 19.1. Table có thể đã được tạo lại

Nếu production đã tạo table cùng tên sau DROP, không restore đè ngay. So sánh OIDs/DDL, business meaning và dữ liệu hiện tại.

### 19.2. Sequence và identity

Nếu table dùng sequence, cần xác định next value phù hợp sau khi import. Không đặt sequence thấp hơn giá trị đã sử dụng.

Ví dụ kiểm tra/điều chỉnh:

~~~sql
SELECT setval(
    'app.orders_order_id_seq',
    (SELECT COALESCE(MAX(order_id), 1) FROM app.orders),
    true
);
~~~

Chỉ dùng sau khi xác minh sequence name, ownership, cache và concurrency. Thực hiện trong maintenance window nếu cần tránh race với writers.

### 19.3. Dependencies

Table có thể được tham chiếu bởi views, functions, triggers, foreign keys, publications hoặc application code. Khôi phục dữ liệu mà bỏ qua dependencies có thể làm ứng dụng lỗi.

## 20. Khôi phục TRUNCATE

TRUNCATE xóa nhanh toàn bộ rows trong table và có thể cascade tới bảng phụ thuộc.

### 20.1. Transactional behavior

Trong PostgreSQL, TRUNCATE có thể nằm trong transaction và rollback nếu transaction chưa commit. Sau commit, cần PITR/backup hoặc nguồn dữ liệu khác.

### 20.2. Identity behavior

TRUNCATE có tùy chọn RESTART IDENTITY hoặc CONTINUE IDENTITY. Khi phục hồi, cần xác minh sequence state so với rows hiện tại.

### 20.3. CASCADE

TRUNCATE ... CASCADE có thể xóa dữ liệu ở các bảng phụ thuộc. Phải lập danh sách tất cả tables bị ảnh hưởng từ query/log và schema dependencies.

### 20.4. Restore toàn bộ table

Nếu table hiện tại không có dữ liệu mới sau sự cố, có thể thay thế từ PITR table dump sau khi kiểm tra schema. Nếu có dữ liệu mới, cần merge và reconcile.

## 21. Khôi phục DROP DATABASE

DROP DATABASE đã commit không thể đảo ngược bằng ROLLBACK mới.

### 21.1. PITR toàn cluster

Dựng cluster PITR tới trước DROP DATABASE. Database sẽ xuất hiện trong trạng thái tại recovery target.

### 21.2. Export database

Có thể dùng pg_dump từ database trong PITR cluster:

~~~bash
pg_dump \
  --host=pitr-db.example.internal \
  --port=55432 \
  --username=restore_reader \
  --dbname=appdb \
  --format=custom \
  --file=/recovery/export/appdb.dump
~~~

Restore vào database mới:

~~~bash
createdb -h production-staging.example.internal -p 5432 -U restore_operator appdb_recovered

pg_restore \
  -h production-staging.example.internal \
  -p 5432 \
  -U restore_operator \
  -d appdb_recovered \
  /recovery/export/appdb.dump
~~~

### 21.3. Roles và globals

pg_dump không dump cluster-wide roles/tablespaces như pg_dumpall --globals-only. Nếu database cần roles, grants hoặc tablespace definitions, chuẩn bị chúng riêng và review trước khi áp dụng.

### 21.4. Database name conflict

Không tạo database cùng tên trên production nếu đã có database khác hoặc application đang kết nối. Dùng tên staging/recovered, rồi lên kế hoạch cutover rõ ràng.

## 22. Khôi phục khi không có WAL archive đầy đủ

Nếu không có WAL cần thiết:
- Có thể chỉ khôi phục tới trạng thái của base backup hoặc điểm WAL còn sẵn.
- Có thể dùng một logical dump/replica/snapshot khác nếu có.
- Có thể khôi phục dữ liệu từ application event log, CDC sink hoặc external source.
- Có thể phải chấp nhận mất một phần thay đổi sau backup.

### 22.1. Kiểm tra các nguồn khác

Inventory base backups gần nhất, WAL archive ở primary/standby/DR storage, physical standbys và delayed standbys, logical replicas, CDC sinks/data lake, storage snapshots, logical dumps và application audit/event logs.

### 22.2. Không tự tạo WAL giả

Không thể bịa segment hoặc sửa tên file để lấp khoảng trống WAL. Nếu chain thiếu, recovery có thể dừng hoặc không nhất quán.

### 22.3. Đánh giá dữ liệu có thể tái tạo

Một số dữ liệu cache/materialized hoặc dữ liệu có nguồn ngoài có thể được rebuild. Phân biệt dữ liệu gốc với derived data để giảm phạm vi restore.

### 22.4. Ghi rõ recovery point thực tế

Nếu chỉ có base backup lúc 01:00 và không có WAL sau đó, đừng báo khôi phục tới 02:00. Ghi chính xác thời điểm/LSN cuối cùng có thể khôi phục và dữ liệu bị ảnh hưởng.

## 23. Phân biệt lỗi database process với lỗi storage

### 23.1. PostgreSQL process crash

Nếu server process crash nhưng data files/WAL còn nguyên, PostgreSQL thường chạy crash recovery khi khởi động lại. Đọc logs, xác định checkpoint và recovery completion.

### 23.2. OS crash/power loss

Có thể tương tự process crash, nhưng cần kiểm tra filesystem và storage đã flush writes đúng hay chưa. Không khởi động liên tục nếu volume có dấu hiệu corruption.

### 23.3. Disk full

Disk full có thể làm write, WAL, archive hoặc temporary operations thất bại. Xác định filesystem nào đầy: PGDATA, pg_wal, tablespace, temp, archive hay OS root.

### 23.4. Disk/media corruption

I/O errors, checksum failures hoặc filesystem errors có thể cho thấy storage bị lỗi. Ưu tiên bảo toàn snapshot/volume và log; không chạy các thao tác sửa chữa ghi đè trước khi có bản sao.

### 23.5. Network failure

Network partition có thể khiến primary và standby không liên lạc. Không promote standby một cách tùy tiện khi primary vẫn có thể nhận writes ở phía khác.

## 24. Failover khi primary host hỏng

Nếu primary host mất nhưng standby khỏe và có dữ liệu đủ mới:

1. Xác nhận primary thật sự không thể tiếp tục phục vụ hoặc đã được fencing.
2. Kiểm tra standby nhận/replay LSN.
3. Đánh giá asynchronous replication gap và RPO.
4. Xác nhận không có primary khác đang nhận writes.
5. Promote standby theo failover procedure.
6. Chuyển connection routing/DNS/proxy.
7. Kiểm tra application writes và data consistency.
8. Tạo lại redundancy bằng cách dựng standby mới.

### 24.1. Fencing

Fencing bảo đảm node primary cũ không thể tiếp tục ghi khi node mới được promote. Nếu hai primary cùng nhận writes, hệ thống có thể split brain.

### 24.2. Không chỉ dựa vào ping

Host không ping được có thể do network path lỗi chứ không phải host chết. Cần kiểm tra qua nhiều tín hiệu và cơ chế cluster manager.

### 24.3. Asynchronous replication gap

Nếu standby chưa nhận hết WAL, failover có thể mất các commits gần nhất. Ghi lại LSN và ước lượng data loss; synchronous replication có thể giảm rủi ro nhưng không thay thế backup.

## 25. Sự cố storage hoặc filesystem

Nếu PGDATA hoặc pg_wal nằm trên storage lỗi:

1. Dừng PostgreSQL nếu còn chạy và có dấu hiệu I/O corruption nghiêm trọng.
2. Thu thập kernel/storage logs và PostgreSQL logs.
3. Chụp snapshot/clone volume nếu có thể làm an toàn.
4. Kiểm tra tình trạng filesystem và mount.
5. Không chạy fsck hoặc repair ghi đè trên volume duy nhất khi chưa có bản sao.
6. Xác định có thể dùng standby, snapshot hoặc backup.
7. Restore sang volume mới.
8. Chạy integrity checks và restore validation.

### 25.1. pg_checksums

Nếu data checksums được bật, checksum errors có thể phát hiện page corruption. Không phải mọi page/file error đều được checksum phát hiện.

### 25.2. Page corruption

Một số trường hợp có thể dùng standby hoặc backup để thay thế page/file hỏng; không tự copy một file relation từ node khác nếu không hiểu physical consistency và WAL state.

### 25.3. WAL corruption

WAL corruption có thể ngăn crash recovery hoặc PITR. Tìm segment hợp lệ từ archive/standby/backup chain. Không chỉnh bytes thủ công.

## 26. Sự cố availability zone hoặc region

DR ở region khác cần chuẩn bị trước:
- Base backup hoặc backup repository có bản sao region khác.
- WAL archive replication tới region DR.
- Network, DNS, certificates, firewall và secrets.
- Compute/storage capacity.
- PostgreSQL binaries/extensions.
- Application artifacts và configuration.
- Quy trình promote/restore và cutover.

### 26.1. Standby ở region khác

Có thể promote nếu standby đã nhận đủ WAL và failure domain còn hoạt động. Đánh giá replication lag trước khi tuyên bố RPO.

### 26.2. Backup ở region khác

Nếu primary và standby cùng mất, restore từ backup/archive có thể là lựa chọn duy nhất. Download và WAL replay có thể kéo dài RTO.

### 26.3. Archive cross-region

WAL archive phải được replicate liên tục và kiểm tra tính đầy đủ. Chỉ thấy object storage replication status xanh không chứng minh PITR chain có thể phục hồi.

### 26.4. DNS/cutover

Sau restore hoặc promote, kiểm tra connection pools, DNS TTL, read replicas, background jobs, scheduler và các writers. Tránh để ứng dụng ghi vào cả cluster cũ và cluster mới.

## 27. Network partition và split brain

Khi primary không liên lạc được với standby, cần xác định node nào được phép nhận writes.

### 27.1. Quorum và leader election

Cluster manager/consensus layer có thể dùng quorum để quyết định node leader. PostgreSQL core không tự cung cấp toàn bộ cơ chế distributed leader election cho mọi topology.

### 27.2. Fencing trước promote

Đảm bảo primary cũ đã bị cô lập hoặc không thể ghi. Nếu không, cả hai node có thể phát sinh histories độc lập.

### 27.3. Rejoin node cũ

Sau failover, node primary cũ không được đơn giản mở lại và nhận writes. Nó cần được rewind/rebuild theo timeline và WAL divergence.

### 27.4. pg_rewind

pg_rewind có thể đồng bộ một data directory đã diverge sau timeline switch nếu prerequisites đáp ứng, thường cần data checksums hoặc wal_log_hints phù hợp và WAL còn đủ. Nó không phải công cụ phục hồi DELETE nhầm; nó giúp đưa node cũ trở lại cùng timeline với primary mới.

## 28. Khi nào dùng pg_rewind, khi nào dùng PITR?

| Tình huống | Công cụ/chiến lược phù hợp |
| --- | --- |
| Node cũ diverge sau failover, muốn rejoin primary mới | pg_rewind nếu prerequisites đáp ứng, nếu không base backup mới |
| DELETE nhầm đã commit, cần rows trước thao tác | PITR cluster riêng rồi export/merge |
| Primary host chết, standby đủ mới | Fencing và promote standby |
| Storage primary hỏng, standby độc lập khỏe | Promote standby; sau đó dựng redundancy |
| Cần database ở một thời điểm lịch sử | Base backup + WAL archive + PITR |
| Chỉ cần một số bảng từ backup | Restore riêng rồi pg_dump/COPY |

pg_rewind không tạo một snapshot trước thao tác xóa. Nếu node cũ đã replay DELETE, rewind nó theo primary hiện tại sẽ giữ lịch sử DELETE.

## 29. Phục hồi khi thao tác xóa xảy ra trên nhiều database

Physical PITR phục hồi cluster ở cấp instance, bao gồm trạng thái của các databases trong cluster tại recovery target. Khi export một database, phải kiểm tra database có tồn tại ở target hay không, roles/grants, tablespaces, extensions, publications/subscriptions, sequences/ownership và objects ngoài database như scheduled jobs.

Không nhầm database-level logical dump với physical cluster restore.

## 30. Sequence, identity và generated data sau merge

Khi khôi phục rows vào production hiện tại, sequence state có thể không trùng với trạng thái ở PITR cluster.

### 30.1. Sequence collision

Nếu production đã tạo rows mới sau sự cố, sequence hiện tại có thể đã tiến xa hơn PITR. Không setval sequence về giá trị thấp từ bản backup cũ.

### 30.2. Identity columns

Kiểm tra identity generation và dependency sequence. pg_dump/pg_restore có thể xử lý sequence state trong một số workflow, nhưng khi chỉ import subset rows cần xác minh thủ công.

### 30.3. UUID

UUID không có sequence collision theo cách integer ID, nhưng business key/unique constraint vẫn có thể trùng. Kiểm tra unique indexes.

### 30.4. Generated columns

Generated columns được tính từ các cột khác; cân nhắc không import trực tiếp nếu target schema có expression khác.

## 31. Trigger, constraints và side effects

Khi import rows trở lại production:
- Trigger có thể gửi event hoặc tạo audit entries.
- Foreign keys có thể từ chối dữ liệu nếu parent không tồn tại.
- Unique constraints có thể phát hiện duplicate.
- Exclusion constraints có thể chặn range overlap.
- Application event/outbox logic có thể phát sinh side effects.

### 31.1. Kiểm tra trigger

Đọc trigger definitions và xác định import có kích hoạt nghiệp vụ không mong muốn hay không. Không disable triggers trên production nếu chưa hiểu các invariants bị bỏ qua.

### 31.2. Deferrable constraints

Một số constraints có thể được defer tới cuối transaction. Điều này hữu ích khi import dependency graph nhưng phải xác minh consistency trước COMMIT.

### 31.3. Audit trail

Ghi lại nguồn gốc rows được phục hồi và recovery operation ID. Đừng làm cho audit history trông như các rows được tạo mới bởi người dùng cuối.

## 32. Khôi phục bằng logical dump có sẵn

Nếu có pg_dump trước sự cố, có thể restore vào database tạm và trích xuất data mà không cần PITR, miễn dump chứa đúng rows cần.

### 32.1. Ưu điểm

- Không cần replay toàn bộ WAL chain.
- Có thể chỉ chứa một database hoặc objects cụ thể.
- Có thể dùng cho selective restore.

### 32.2. Giới hạn

- Dump chỉ phản ánh thời điểm tạo.
- Không có rows mới hơn dump.
- Có thể thiếu roles, tablespaces hoặc external dependencies.
- Restore có thể cần extension/schema tương thích.

### 32.3. Logical backup không phải PITR

pg_dump không cung cấp mọi điểm thời gian giữa hai lần dump. Nếu cần khôi phục tới 02:17:00, base backup + WAL thường phù hợp hơn.

## 33. Kiểm tra sau khôi phục

Sau khi export/import hoặc promote/restore, kiểm tra nhiều lớp.

### 33.1. Database state

~~~sql
SELECT
    current_database(),
    pg_is_in_recovery(),
    current_timestamp;
~~~

### 33.2. Row counts và keys

So sánh số rows dự kiến, danh sách primary keys, min/max timestamps và các nhóm tenant/status.

### 33.3. Constraints

Kiểm tra foreign keys, unique constraints và các invariants được application quản lý. Nếu có constraints bị bỏ qua trong import, phải xác minh và bật lại theo quy trình.

### 33.4. Application smoke tests

Kiểm tra luồng đọc, tạo mới và cập nhật trong staging trước khi mở traffic. Kiểm tra kết nối pool, permissions, extensions và background workers.

### 33.5. Replication

Sau promote hoặc restore production replacement, dựng lại standbys và xác minh streaming/slots/archive. Một primary mới không hoàn tất HA cho tới khi redundancy được khôi phục.

### 33.6. Backup sau recovery

Sau một PITR promotion/cutover, tạo base backup mới và xác nhận WAL archive theo timeline mới. Không tiếp tục retention như thể cluster chưa đổi timeline.

## 34. Kế hoạch cutover sau PITR

Nếu quyết định thay thế production bằng một cluster PITR, cần:

1. Dừng hoặc giới hạn writes trên hệ thống cũ.
2. Chốt recovery target và xác minh dữ liệu.
3. Kiểm tra WAL replay hoàn tất.
4. Promote instance nếu đang pause.
5. Đặt quyền/credentials/network.
6. Kiểm tra ứng dụng và dependencies.
7. Chuyển connection routing/DNS/proxy.
8. Theo dõi error rate, latency và data consistency.
9. Giữ cluster cũ ở trạng thái cô lập để đối chiếu.
10. Tạo lại replicas và backup mới.

### 34.1. Rủi ro writes sau target

Mọi commits sau recovery target không có trong cluster PITR. Phải xác định có thể tái áp dụng từ audit/event logs hoặc cần chấp nhận data loss.

### 34.2. Idempotent replay

Nếu tái áp dụng events sau target, pipeline phải có event IDs/idempotency keys để tránh tạo duplicate side effects.

### 34.3. Cutover gate

Chỉ chuyển traffic khi owner dữ liệu chấp thuận recovery point, ứng dụng vượt qua tests và các dịch vụ phụ thuộc sẵn sàng.

## 35. RTO và RPO

### 35.1. RPO

Recovery Point Objective là lượng dữ liệu theo thời gian mà tổ chức chấp nhận mất.

Ví dụ:
- RPO 0 trong một phạm vi commit được synchronous standby xác nhận có thể đạt được theo semantics/configuration phù hợp, nhưng không có nghĩa không thể mất dữ liệu trong mọi failure mode.
- RPO 5 phút với PITR phụ thuộc archive cadence, archive success và recovery chain thực tế.

### 35.2. RTO

Recovery Time Objective là thời gian mục tiêu để dịch vụ hoạt động lại.

RTO gồm phát hiện và phân loại sự cố, chọn recovery path, provision host/storage, download/restore base backup, replay WAL, validate data, cutover và smoke test.

### 35.3. PITR có thể lâu hơn failover

Failover standby khỏe thường nhanh hơn restore terabytes từ object storage và replay nhiều WAL. Nhưng failover không phù hợp nếu standby đã replay thao tác xóa nhầm.

### 35.4. Đo thực tế

Ghi lại thời gian từng bước trong drill. Đừng lấy tốc độ copy lý thuyết hoặc thời gian tạo backup làm RTO.

## 36. Thiết kế phòng ngừa xóa nhầm

### 36.1. Least privilege

Ứng dụng không cần quyền DROP DATABASE, DROP SCHEMA hoặc TRUNCATE nếu chức năng không yêu cầu. Tách role migration/admin khỏi runtime application role.

### 36.2. Guardrails trong SQL workflow

Với thao tác nguy hiểm:
- Dùng transaction rõ ràng.
- Chạy SELECT cùng WHERE trước DELETE.
- Xác nhận row count.
- Dùng RETURNING để lưu rows bị tác động nếu workflow phù hợp.
- Có approval cho bulk destructive operation.

Ví dụ:

~~~sql
BEGIN;

DELETE FROM app.customers
WHERE tenant_id = 42
  AND status = 'test'
RETURNING customer_id, email;

-- Kiểm tra số rows và nội dung trước khi quyết định
-- COMMIT hoặc ROLLBACK
~~~

### 36.3. Soft delete

Với dữ liệu nghiệp vụ cần khả năng khôi phục nhanh, có thể dùng deleted_at/deleted_by thay vì DELETE vật lý. Cần quy tắc uniqueness, query filters, retention và quyền restore.

### 36.4. Audit

Ghi actor, timestamp, request ID, table, keys và operation vào audit system có quyền truy cập riêng. Không ghi dữ liệu nhạy cảm vượt mức cần thiết.

### 36.5. Restore points trước change

Với một số deployment/maintenance nguy hiểm, có thể tạo named restore point trước thao tác. Restore point không thay backup/WAL retention nhưng giúp chọn target dễ hơn.

## 37. Delayed standby như một lớp phòng vệ

Một standby có recovery_min_apply_delay có thể trì hoãn apply WAL.

~~~conf
recovery_min_apply_delay = '15min'
~~~

### 37.1. Cửa sổ phản ứng

Nếu xóa nhầm được phát hiện trong 15 phút và người vận hành pause standby trước khi replay transaction xóa, có thể giữ được một bản trạng thái cũ.

### 37.2. Không bảo vệ nếu phát hiện muộn

Nếu thao tác được phát hiện sau khi standby đã apply, delayed standby không còn giữ trạng thái trước sự kiện.

### 37.3. Tác động đến standby

Delay làm tăng replay lag, ảnh hưởng read queries và failover freshness. Không dùng delayed standby làm synchronous failover target nếu SLA không chấp nhận độ trễ.

### 37.4. Dừng replay đúng cách

Phải có monitoring và runbook để pause recovery trước khi transaction nguy hiểm được apply. Chỉ ngắt network có thể không đủ nếu WAL đã nhận vào local storage và recovery tiếp tục.

### 37.5. Không thay backup

Delayed standby có thể hữu ích nhưng vẫn là một node có thể hỏng cùng failure domain hoặc mất WAL. Cần base backup và archive độc lập.

## 38. Lưu ý về managed PostgreSQL services

Với dịch vụ managed database, người dùng có thể không truy cập trực tiếp PGDATA, WAL directory hoặc recovery.signal. Nhà cung cấp có thể cung cấp point-in-time restore qua control plane, snapshot restore, cross-region replica/failover, backup retention configuration và log export/audit events.

### 38.1. PITR thường tạo instance mới

Nhiều dịch vụ managed tạo một database instance mới tại target time thay vì rollback instance hiện tại. Đây vẫn là chiến lược an toàn để export/compare dữ liệu.

### 38.2. Kiểm tra giới hạn của provider

Xác minh retention window, timezone semantics, restore granularity, extension support, parameter groups, networking và cách lấy dữ liệu từ restored instance.

### 38.3. Không giả định truy cập shell

pg_verifybackup, pg_basebackup hoặc restore_command có thể không được cung cấp trực tiếp cho user. Dùng công cụ/provider workflow tương ứng và yêu cầu báo cáo verification.

### 38.4. Managed không loại bỏ restore drills

Provider có thể quản lý backup infrastructure, nhưng application owner vẫn phải kiểm tra dữ liệu, permissions, integrations và RTO.

## 39. Runbook: phân loại sự cố trong 15 phút đầu

### Phút 0–3: bảo toàn trạng thái

- Dừng job/query gây lỗi.
- Không restart/promote vội.
- Ghi thời điểm và người phát hiện.
- Xác định primary/standby hiện tại.

### Phút 3–7: phân loại

- Data deletion hay infrastructure failure?
- Transaction commit chưa?
- Một table/database hay toàn cluster?
- Primary còn khỏe không?
- Standby đã replay tới đâu?

### Phút 7–12: kiểm tra recovery options

- Base backup gần nhất.
- WAL archive completeness.
- PITR retention window.
- Delayed standby/snapshot/logical dump.
- Available restore capacity.

### Phút 12–15: chọn hướng xử lý

- Uncommitted transaction: rollback đúng transaction.
- Committed logical deletion: PITR cluster riêng và selective restore.
- Primary host failure: fencing, đánh giá standby rồi failover.
- Storage/region loss: DR restore hoặc failover theo recovery plan.

Mốc thời gian chỉ là ví dụ cho incident checklist; không được để áp lực thời gian làm bỏ qua fencing, data loss assessment hoặc bảo toàn evidence.

## 40. Runbook: PITR để lấy lại rows đã xóa

1. Dừng nguồn gây lỗi.
2. Xác định commit timestamp/LSN/transaction.
3. Chọn base backup và WAL chain bao phủ target.
4. Tạo restore environment riêng.
5. Khôi phục backup vào data directory mới.
6. Cấu hình restore_command và recovery target trước thao tác xóa.
7. Start PostgreSQL và đọc recovery logs.
8. Pause/stop recovery theo kế hoạch.
9. Kiểm tra rows và schema.
10. Export table/rows cần thiết.
11. Import vào staging trên production.
12. Reconcile duplicates, updates, foreign keys và sequences.
13. Merge có transaction/approval.
14. Kiểm tra application/business invariants.
15. Lưu recovery report và giữ PITR instance theo policy.

## 41. Runbook: primary host hỏng

1. Xác nhận node primary không còn khả năng ghi.
2. Fencing node cũ hoặc storage để tránh split brain.
3. Kiểm tra trạng thái standby và replay LSN.
4. Đánh giá asynchronous replication gap.
5. Quyết định promote theo HA policy.
6. Chuyển traffic.
7. Kiểm tra application và writes.
8. Dựng lại standby từ primary mới/rewind nếu đủ điều kiện.
9. Xác minh archive và tạo backup mới.
10. Ghi nhận RPO/RTO thực tế.

## 42. Runbook: disk hoặc storage corruption

1. Dừng ghi nếu tiếp tục ghi có thể làm hỏng thêm dữ liệu.
2. Thu thập OS/kernel/storage/PostgreSQL logs.
3. Bảo toàn snapshot/clone của volume nếu có thể.
4. Kiểm tra standby độc lập và backup repository.
5. Không xóa file WAL/data thủ công.
6. Chọn restore target/backup hợp lệ.
7. Dựng cluster trên storage mới.
8. Kiểm tra checksums, WAL replay và startup.
9. Chạy business/application validation.
10. Tái lập HA/backup và điều tra nguyên nhân storage.

## 43. Runbook: DR region

1. Xác nhận region primary không thể phục hồi trong SLA.
2. Chốt quyền quyết định DR activation.
3. Chọn cross-region standby hoặc backup restore.
4. Kiểm tra replication lag hoặc WAL archive completeness.
5. Fencing/disable writers ở region cũ nếu cần.
6. Promote/restore tại region DR.
7. Khôi phục secrets, certificates, network, DNS và application services.
8. Chạy smoke tests và business validation.
9. Chuyển traffic theo từng bước.
10. Theo dõi latency, errors, lag và capacity.
11. Ghi RPO/RTO và lên kế hoạch failback.

## 44. Kế hoạch failback sau DR

Failback là đưa workload trở lại failure domain ban đầu sau khi nó được sửa. Không chỉ đổi DNS ngược.

1. Xác định cluster nào là source of truth hiện tại.
2. Chọn phương án đồng bộ dữ liệu từ DR về.
3. Kiểm tra timeline divergence và replication compatibility.
4. Dùng pg_rewind nếu phù hợp hoặc tạo base backup mới.
5. Thiết lập replication và xác minh lag.
6. Kiểm thử failover/failback trong staging.
7. Chọn maintenance window và dừng writes có kiểm soát.
8. Cutover traffic.
9. Giữ node DR theo vai trò standby/backup mới.
10. Cập nhật runbooks, DNS, monitoring và backup policies.

## 45. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Promote standby ngay khi phát hiện DELETE | Standby có thể đã replay DELETE | Kiểm tra replay LSN và mục tiêu recovery |
| Nghĩ ROLLBACK transaction mới undo commit cũ | Không khôi phục được dữ liệu | PITR hoặc selective restore |
| PITR đè lên production hiện tại | Mất writes hợp lệ sau target | Restore sang cluster riêng |
| Chọn target bằng query start time | Có thể vẫn bao gồm commit xóa | Xác định commit boundary |
| Không chuẩn hóa timezone | Chọn sai recovery target | Dùng UTC và kiểm tra clock drift |
| Chỉ có base backup, không có WAL | Không tới được target mong muốn | Duy trì WAL archive liên tục |
| Tin delayed standby luôn cứu được | Cửa sổ delay có thể đã hết | Monitoring, pause procedure và backup |
| Dùng pg_rewind để undo DELETE | Node vẫn theo lịch sử primary hiện tại | Dùng PITR |
| Import table dump thẳng vào production | Duplicate/overwrite và constraint errors | Staging + reconciliation |
| Upsert mọi row từ backup cũ | Ghi đè updates mới | Xác định precedence theo business rules |
| Quên sequence state | ID collision hoặc sequence lùi | Kiểm tra và đồng bộ sequence |
| Bỏ qua triggers | Side effects không mong muốn | Review triggers/audit/outbox |
| Không kiểm tra CASCADE | Bỏ sót bảng phụ thuộc | Xác định toàn bộ objects bị ảnh hưởng |
| Nghĩ standby là backup | Logical deletion được replicate | Backup/PITR độc lập |
| Promote khi primary chỉ mất network | Split brain | Fencing và quorum |
| Chỉ test database startup | App có thể không hoạt động | Smoke tests và business invariants |
| Không tạo backup sau PITR promotion | Thiếu recovery chain cho timeline mới | Tạo base backup và archive mới |
| Không diễn tập DR | RTO thực tế vượt SLA | Restore/failover drills |

## 46. Bài tập thực hành PostgreSQL

Thực hiện trên lab/staging có backup và WAL archive thử nghiệm. Không mô phỏng destructive commands trên production.

1. **Transaction:** tạo transaction, DELETE một row rồi ROLLBACK.
2. **Commit:** DELETE và COMMIT; giải thích vì sao transaction mới không undo được.
3. **Savepoint:** dùng ROLLBACK TO SAVEPOINT trước khi commit.
4. **Autocommit:** kiểm tra behavior của client khi chạy một DELETE đơn lẻ.
5. **Query evidence:** bật logging phù hợp trong lab và tìm query text.
6. **Application logs:** liên kết request ID với database operation.
7. **Time zones:** chuyển timestamp log về UTC.
8. **Commit time:** phân biệt query start và transaction commit.
9. **Scope:** tạo DELETE có điều kiện và xác định keys bị tác động.
10. **TRUNCATE:** mô phỏng TRUNCATE trong transaction và rollback.
11. **DROP TABLE:** mô phỏng drop table và ghi lại dependency list.
12. **DROP DATABASE:** tạo database lab, drop và xác định recovery assets.
13. **CASCADE:** quan sát objects bị ảnh hưởng bởi DROP ... CASCADE.
14. **Physical standby:** tạo standby và quan sát DELETE được replay.
15. **Delayed standby:** cấu hình recovery_min_apply_delay trong lab.
16. **Pause replay:** thực hành dừng replay trước một transaction thử nghiệm.
17. **Failover:** phân biệt promote standby với PITR.
18. **Base backup:** tạo base backup bằng pg_basebackup.
19. **WAL archive:** cấu hình archive trong lab.
20. **WAL continuity:** xác định segments cần cho một backup.
21. **Restore point:** tạo named restore point trước một thao tác.
22. **PITR time:** phục hồi tới recovery_target_time.
23. **PITR LSN:** tìm LSN trong lab và dùng recovery_target_lsn.
24. **PITR XID:** tìm hiểu recovery_target_xid theo version.
25. **Inclusive:** so sánh recovery_target_inclusive true/false.
26. **Target action:** thử pause, promote và shutdown trên các cluster dùng một lần.
27. **Recovery signal:** tạo recovery.signal và quan sát archive recovery.
28. **Standby signal:** phân biệt standby.signal với recovery.signal.
29. **Restore command:** viết command lấy WAL segment từ archive lab.
30. **Missing WAL:** tạo archive thiếu segment và đọc recovery error.
31. **Timeline:** quan sát timeline history sau promote.
32. **PITR isolation:** restore backup vào cluster có port/network riêng.
33. **No overwrite:** chứng minh PITR không sửa PGDATA production.
34. **Selective export:** dùng pg_dump --table để export một table.
35. **COPY:** export một tập rows với psql \copy.
36. **Staging import:** import rows vào recovery_stage schema.
37. **Duplicate keys:** tìm keys trùng giữa staging và production.
38. **Merge:** viết INSERT ... WHERE NOT EXISTS cho một tập rows lab.
39. **Upsert:** mô phỏng conflict và giải thích rủi ro overwrite.
40. **Foreign keys:** phục hồi parent trước child.
41. **Sequence:** kiểm tra setval sau selective restore.
42. **Identity:** kiểm tra identity sequence sau import subset.
43. **Triggers:** kiểm tra side effects khi insert rows được phục hồi.
44. **Audit:** ghi recovery operation ID cho các rows được import.
45. **DROP recovery:** phục hồi một table đã drop vào cluster riêng.
46. **TRUNCATE recovery:** phục hồi rows trước truncate và merge.
47. **Database recovery:** export database từ PITR cluster.
48. **Globals:** xác định roles/tablespaces cần phục hồi riêng.
49. **Logical dump:** restore pg_dump vào database lab và kiểm tra schema/data.
50. **No WAL:** mô phỏng chỉ có base backup và đánh giá recovery point.
51. **Alternative sources:** inventory snapshot, CDC sink, audit log và delayed standby.
52. **Process crash:** đọc log crash recovery sau khi dừng lab bất thường.
53. **Disk full:** mô phỏng filesystem quota trong lab và phân biệt filesystem bị đầy.
54. **Storage error:** đọc kernel/PostgreSQL logs khi storage giả lập báo lỗi.
55. **Fencing:** vẽ quy trình fencing trước khi promote.
56. **Split brain:** mô phỏng network partition bằng sơ đồ và đề xuất quorum decision.
57. **pg_rewind:** thực hành rewind một standby diverged trong lab.
58. **pg_rewind prerequisites:** kiểm tra data checksums/wal_log_hints và WAL availability.
59. **Region DR:** lập sơ đồ primary, standby và backup archive ở region khác.
60. **Cross-region restore:** restore backup từ bản sao region DR.
61. **DNS cutover:** mô tả các bước đổi endpoint và connection pools.
62. **Failback:** lập quy trình đồng bộ node cũ về DR primary mới.
63. **Managed service:** nghiên cứu PITR workflow của một PostgreSQL managed provider.
64. **Recovery target:** chọn target trước transaction xóa từ log có clock drift.
65. **Business reconciliation:** khôi phục customer rows nhưng giữ các updates hợp lệ sau sự cố.
66. **Order recovery:** phân tích side effects với orders/payments khi selective restore.
67. **Inventory:** phục hồi stock rows và đối chiếu ledger/event log.
68. **RTO:** đo thời gian provision, download, replay, validate và cutover.
69. **RPO:** xác định điểm WAL mới nhất có thể phục hồi.
70. **Incident timeline:** viết timeline từ phát hiện tới recovery complete.
71. **Runbook DELETE:** viết runbook PITR và selective merge.
72. **Runbook DROP:** viết runbook phục hồi table/database đã drop.
73. **Runbook host failure:** viết runbook fencing, promote và rebuild standby.
74. **Runbook storage:** viết runbook bảo toàn volume và restore trên storage mới.
75. **Runbook region:** viết DR activation và failback checklist.
76. **Privileges:** tạo role ứng dụng không có quyền DROP/TRUNCATE.
77. **Soft delete:** thiết kế deleted_at/deleted_by và quy trình restore.
78. **Restore drills:** lên lịch kiểm thử PITR nhiều target times.
79. **Backup protection:** thiết kế base backup, WAL archive, immutable copy và key recovery.
80. **Thiết kế tổng hợp:** xây chiến lược xử lý DELETE nhầm và infrastructure outage với classification, evidence, PITR isolation, selective merge, failover/fencing, RTO/RPO, monitoring và diễn tập định kỳ.

## 47. Checklist quyết định recovery path

### Phân loại

- [ ] Xác định logical deletion hay infrastructure failure.
- [ ] Xác định transaction đã commit chưa.
- [ ] Xác định database/table/rows và dependencies bị ảnh hưởng.
- [ ] Xác định primary/standby hiện tại và replay positions.
- [ ] Dừng nguồn gây lỗi và bảo toàn logs.

### Chọn recovery

- [ ] Uncommitted: rollback đúng transaction.
- [ ] Committed deletion: xác định PITR target.
- [ ] Có standby: kiểm tra nó đã replay thao tác chưa.
- [ ] Có base backup và WAL archive liên tục.
- [ ] Có delayed standby/snapshot/logical dump nếu cần.
- [ ] Infrastructure failure: xác nhận fencing và RPO trước promote.

### Thực hiện

- [ ] Restore/PITR vào cluster riêng.
- [ ] Dùng target trước commit gây mất dữ liệu.
- [ ] Kiểm tra rows/schema/tablespaces.
- [ ] Export vào staging.
- [ ] Reconcile duplicate keys và updates mới.
- [ ] Kiểm tra foreign keys, sequences, triggers và side effects.
- [ ] Có approval trước khi merge/cutover.

### Sau recovery

- [ ] Application smoke tests thành công.
- [ ] Business invariants được kiểm tra.
- [ ] Replicas và WAL archive được thiết lập lại.
- [ ] Base backup mới được tạo nếu timeline thay đổi.
- [ ] RTO/RPO và dữ liệu bị mất (nếu có) được ghi nhận.
- [ ] Root cause và guardrails được cập nhật.

## 48. Tổng kết

Phục hồi thao tác xóa nhầm và phục hồi sự cố hạ tầng giải quyết hai vấn đề khác nhau:

~~~text
XÓA NHẦM ĐÃ COMMIT
  -> Xác định commit time
  -> Base backup + WAL
  -> PITR sang cluster riêng
  -> Export rows/table/database
  -> Reconcile và merge

PRIMARY / HẠ TẦNG BỊ HỎNG
  -> Xác nhận failure domain
  -> Fencing nếu có nguy cơ split brain
  -> Promote standby hoặc restore backup
  -> Cutover ứng dụng
  -> Rebuild redundancy
~~~

Những nguyên tắc quan trọng:

- **Transaction chưa commit có thể rollback; transaction đã commit không thể undo bằng ROLLBACK mới.**
- **Physical standby thường replay cả thao tác xóa hợp lệ.** Kiểm tra replay state trước khi promote.
- **PITR là phục hồi trạng thái cluster tới một điểm lịch sử.** Để giữ writes hợp lệ sau sự cố, restore sang cluster riêng rồi trích xuất và merge dữ liệu.
- **Chọn recovery target theo commit boundary**, chuẩn hóa timezone và hiểu inclusive semantics.
- **Base backup cần WAL liên tục và timeline history phù hợp.** Thiếu WAL có thể khiến recovery không tới được target.
- **DELETE, TRUNCATE, DROP TABLE và DROP DATABASE có phạm vi khác nhau.** Xác định dependencies, constraints, sequences và side effects.
- **pg_rewind giúp node diverged rejoin timeline mới; nó không undo thao tác xóa.**
- **Failover cần fencing và đánh giá RPO.** Network partition không chứng minh primary đã chết.
- **Verified backup vẫn cần restore drill và business validation.** Đo RTO/RPO bằng quy trình thực tế.
- **Least privilege, soft delete, audit, named restore points và diễn tập** giúp giảm khả năng sự cố tái diễn.

Một kế hoạch recovery tốt không bắt đầu bằng nút restart hoặc promote. Nó bắt đầu bằng phân loại chính xác, bảo toàn recovery options và chọn đường phục hồi phù hợp với dữ liệu cần giữ. Khi tách biệt PITR khỏi failover, bạn có thể lấy lại dữ liệu đã xóa mà vẫn bảo toàn các thay đổi hợp lệ trên production, đồng thời xử lý sự cố hạ tầng theo mục tiêu availability và disaster recovery.
