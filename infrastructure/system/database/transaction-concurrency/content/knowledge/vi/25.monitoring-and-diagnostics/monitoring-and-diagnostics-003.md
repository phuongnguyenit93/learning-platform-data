# Đọc đồ thị bế tắc và lịch sử giao dịch bị hủy

Deadlock report cho biết hệ quản trị đã phát hiện một nhóm giao dịch chờ tài nguyên theo vòng tròn và đã chọn ít nhất một giao dịch để phá chu trình. Báo cáo thường chứa session/process, câu lệnh tại thời điểm phát hiện, tài nguyên bị khóa, chế độ khóa đang giữ hoặc đang yêu cầu và transaction được chọn làm victim.

Đọc report đúng cách cần trả lời hai câu hỏi riêng:

1. **Chu trình được tạo ra như thế nào?** Giao dịch nào đang chờ giao dịch nào, trên tài nguyên nào và theo lock mode nào?
2. **Điều gì đã xảy ra với giao dịch sau khi deadlock được phát hiện?** Transaction nào bị rollback, các thay đổi nào đã được hoàn tác, transaction nào tiếp tục và ứng dụng có retry hay không?

Một deadlock graph thường là ảnh chụp tại thời điểm detector phát hiện chu trình. Nó không phải nhật ký đầy đủ của mọi câu SQL trong các transaction. Muốn tái dựng lịch sử, cần kết hợp graph với log database, trace ứng dụng, transaction ID, request ID và audit nghiệp vụ.

## 1. Deadlock report trả lời điều gì?

### 1.1. Từ lỗi của một câu SQL đến chu trình giao dịch

Một lỗi deadlock thường xuất hiện ở ứng dụng dưới dạng exception hoặc mã lỗi. Dòng log có thể chỉ ghi câu lệnh thất bại, nhưng nguyên nhân nằm trong quan hệ khóa giữa nhiều transaction.

Ví dụ:

~~~text
T1 giữ khóa trên hàng A và chờ hàng B.
T2 giữ khóa trên hàng B và chờ hàng A.

T1 -> T2 -> T1
~~~

Câu lệnh của T1 bị lỗi có thể chỉ là câu UPDATE thứ hai. Câu UPDATE đầu tiên của T1 mới là thao tác đã lấy khóa A. Nếu chỉ xem câu lệnh cuối cùng, ta không thấy toàn bộ chu trình.

Deadlock report giúp tìm ra các transaction tham gia và tài nguyên khép kín chu trình. Lịch sử transaction giúp giải thích vì sao chúng lấy khóa theo thứ tự đó.

### 1.2. Các thành phần thường gặp

Tên trường khác nhau giữa DBMS, nhưng thường có các nhóm thông tin:

| Thành phần | Ý nghĩa |
|---|---|
| Victim | Transaction/session được chọn để rollback hoặc hủy |
| Process/session | Kết nối database đang thực hiện hoặc chờ |
| Transaction ID | Định danh transaction ở DBMS |
| SQL statement | Câu lệnh đang chạy tại thời điểm deadlock |
| Resource | Hàng, key, page, bảng, transaction ID, metadata hoặc tài nguyên khác |
| Owner | Transaction đang giữ khóa trên resource |
| Waiter | Transaction đang yêu cầu khóa và phải chờ |
| Lock mode | Chế độ khóa đang giữ hoặc yêu cầu |
| Wait duration | Thời gian chờ được ghi nhận, nếu report có |
| Execution context | Thread, task, worker hoặc execution context thuộc session |
| Isolation level | Mức cô lập được ghi nhận, nếu report có |
| Transaction cost | Một số DBMS ghi lượng công việc/undo cần rollback để chọn victim |

Không phải report nào cũng chứa đủ tất cả trường. Một số công cụ hiển thị graph đã rút gọn; một số hiển thị resource allocation graph với cả nút transaction và resource.

### 1.3. Report không phải lịch sử đầy đủ

Deadlock report thường cho biết:

- Các participant ở thời điểm detector chạy.
- Các resource và lock mode liên quan.
- Câu lệnh đang chạy hoặc câu lệnh được engine ghi nhận.
- Victim được chọn.
- Một phần thông tin transaction.

Report thường không cho biết đầy đủ:

- Mọi câu SQL đã chạy từ đầu transaction.
- Mọi giá trị bind parameter.
- Toàn bộ dữ liệu đã đọc.
- Mọi tác dụng phụ ngoài database.
- Request HTTP hoặc message ban đầu.
- Tất cả lần retry trước đó.
- Chính xác thời điểm từng khóa được lấy nếu engine không ghi riêng.

Vì vậy, hãy coi deadlock report là bằng chứng về chu trình, rồi dùng telemetry khác để tái dựng nguyên nhân nghiệp vụ.

## 2. Quy ước đọc mũi tên và vai trò

### 2.1. Wait-for graph

Trong wait-for graph, mỗi nút là một transaction. Cạnh có hướng đi từ waiter đến blocker:

\[
T_i \rightarrow T_j
\]

nghĩa là T_i đang chờ tài nguyên mà T_j giữ hoặc đang được xem là bên chặn theo quy tắc hàng đợi khóa.

Ví dụ:

~~~text
T1 ─────> T2
^         |
|         |
└─────────┘
~~~

T1 chờ T2; T2 chờ T1. Có chu trình nên hai transaction tạo deadlock.

Đừng đảo chiều mũi tên. Nếu công cụ hiển thị một cạnh từ T1 đến T2 theo quy ước waiter-to-blocker, T1 là waiter và T2 là blocker.

### 2.2. Resource allocation graph

Một số report biểu diễn tài nguyên tách biệt:

~~~text
T1 --request--> R2 --owned by--> T2
T2 --request--> R1 --owned by--> T1
~~~

T1 yêu cầu R2 do T2 sở hữu. T2 yêu cầu R1 do T1 sở hữu. Bỏ các nút resource và nối waiter đến owner sẽ thu được wait-for graph.

Khi đọc XML hoặc sơ đồ, hãy tìm các cặp owner/waiter trên cùng resource. Không chỉ nhìn tên session hoặc vị trí các nút trên hình.

### 2.3. Một waiter có thể có nhiều blocker

Một yêu cầu khóa độc quyền có thể xung đột với nhiều khóa đang được giữ. Vì vậy, một transaction có thể có nhiều cạnh đi ra:

~~~text
       T2
        ^
        |
T1 -----+
        |
        v
       T3
~~~

T1 đang chờ T2 và T3. Không nên ép mỗi transaction chỉ có một blocker khi dựng graph.

### 2.4. Giao dịch ngoài chu trình

Ví dụ:

~~~text
T1 -> T2 -> T3 -> T1

T4 -> T2
T5 -> T4
~~~

Chu trình là T1, T2 và T3. T4 và T5 đang bị ảnh hưởng bởi chuỗi chờ, nhưng không nằm trong chu trình.

Khi một participant trong chu trình bị rollback, khóa được giải phóng và các transaction ngoài chu trình có thể tiếp tục. Report có thể hiển thị nhiều process hơn số transaction trong chu trình cốt lõi.

### 2.5. Wait chain không phải deadlock

~~~text
T1 -> T2 -> T3
~~~

Nếu T3 không chờ ai và có thể commit, chuỗi chờ có thể tự tiến triển. Chỉ có cạnh nối vòng trở lại một nút đã nằm trên đường đi mới tạo chu trình.

Một session có thời gian chờ dài hoặc nhiều waiter không tự chứng minh deadlock. Cần tìm chu trình hoặc xem thông báo deadlock do engine ghi nhận.

## 3. Đọc tài nguyên và lock mode

### 3.1. Resource định danh đối tượng nào?

Tùy DBMS, resource có thể được biểu diễn là:

- Database, schema hoặc object/table.
- Row, tuple hoặc record.
- Index key hoặc key range.
- Page hoặc partition.
- Transaction ID mà một transaction khác đang chờ.
- Metadata hoặc schema lock.
- Application/advisory lock.
- Tài nguyên nội bộ của storage engine.

Tên resource có thể là ID nội bộ thay vì tên bảng dễ đọc. Cần dùng metadata catalog hoặc công cụ của DBMS để ánh xạ ID sang object, index và key khi có thể.

### 3.2. Phân biệt object, index và row

Một thao tác UPDATE có thể chạm nhiều tài nguyên:

1. Hàng trong clustered/heap storage.
2. Khóa key trên clustered index.
3. Nonclustered index cần cập nhật.
4. Khóa kiểm tra UNIQUE.
5. Khóa kiểm tra FOREIGN KEY.
6. Page hoặc metadata liên quan.

Vì vậy, deadlock report có thể cho thấy hai giao dịch chờ trên index key dù source code chỉ cập nhật một cột trong bảng. Cần xem index name, resource type và execution plan.

### 3.3. Lock mode giải thích xung đột

Một số mode thường gặp:

- S (Shared): đọc theo locking semantics.
- X (Exclusive): ghi hoặc thay đổi tài nguyên.
- U (Update): hỗ trợ mẫu đọc rồi cập nhật.
- IS/IX/SIX: intent locks ở cấp cao hơn.
- Key-range locks: bảo vệ phạm vi khóa trong SERIALIZABLE.
- Schema locks như Sch-S và Sch-M trong SQL Server.

Tên và ma trận tương thích thay đổi theo DBMS. Không suy luận chỉ từ chữ S hoặc X nếu report thuộc một engine có mode riêng.

### 3.4. Owner mode và waiter mode

Với mỗi resource, ghi lại hai thông tin:

| Vai trò | Cần ghi |
|---|---|
| Owner | Transaction nào đang giữ, lock mode nào |
| Waiter | Transaction nào yêu cầu, lock mode nào |

Ví dụ:

~~~text
Resource: index key K
Owner: T1, mode X
Waiter: T2, mode S
~~~

Nếu mode không tương thích, T2 phải chờ T1. Nếu có nhiều owner, ghi từng owner và mode. Nếu có wait queue, kiểm tra liệu một yêu cầu đứng trước có đang chặn yêu cầu sau hay không.

### 3.5. Chuyển đổi khóa

Một transaction có thể đã giữ S và yêu cầu nâng lên X. Nếu hai transaction cùng giữ S rồi cùng yêu cầu X, chúng có thể chờ khóa của nhau.

Report có thể biểu diễn conversion lock hoặc cho thấy cùng transaction vừa là owner vừa là waiter trên resource. Đây là dấu hiệu cần xem mẫu read-then-update và các hint/locking read.

### 3.6. Khóa do index range hoặc predicate

Một deadlock trên range/key có thể bắt nguồn từ truy vấn range scan, INSERT, UPDATE hoặc DELETE. Với InnoDB, record/gap/next-key locks có thể tham gia. Với SQL Server SERIALIZABLE, key-range locks có thể bảo vệ predicate.

Không chỉ ghi tên bảng. Hãy ghi index, key/range, điều kiện WHERE và access path để hiểu phạm vi khóa thực tế.

## 4. Nhận diện victim và transaction còn lại

### 4.1. Victim là transaction được chọn để phá chu trình

Khi detector phát hiện deadlock, DBMS thường chọn một transaction làm victim. Rollback transaction đó giải phóng khóa và phá chu trình.

Không giả định victim luôn là:

- Transaction mới nhất.
- Transaction ít câu SQL nhất.
- Transaction đang chờ lâu nhất.
- Transaction có ít thay đổi nhất.
- Session có ID lớn hơn.

Chính sách chọn victim khác nhau theo sản phẩm và có thể xét chi phí rollback, ưu tiên, deadlock priority hoặc dữ liệu nội bộ khác.

### 4.2. Victim và câu lệnh gây deadlock không nhất thiết giống nhau

Câu lệnh cuối cùng tạo cạnh khép chu trình có thể nằm trong một transaction khác với victim. Victim được chọn theo chính sách của engine.

Khi đọc report, tách hai câu hỏi:

- Câu lệnh nào yêu cầu khóa khiến chu trình được khép lại?
- Transaction nào được chọn làm victim?

Không dùng câu lệnh báo lỗi ở ứng dụng làm bằng chứng rằng nó là nguyên nhân duy nhất.

### 4.3. Transaction survivor

Transaction còn lại trong chu trình có thể tiếp tục sau khi victim rollback và khóa được giải phóng. Nó có thể hoàn tất thành công hoặc gặp lỗi khác.

Khi tái dựng lịch sử, cần ghi rõ:

- Victim bị rollback ở thời điểm nào.
- Survivor được đánh thức lúc nào.
- Survivor có nhận khóa hay không.
- Survivor có commit hay rollback sau đó.
- Các waiter ngoài chu trình có tiếp tục không.

Không phải tất cả transaction trong report đều nhất thiết commit thành công sau khi deadlock được xử lý.

### 4.4. Deadlock victim không phải dữ liệu đã commit bị xóa

Rollback victim hoàn tác thay đổi chưa commit trong transaction theo semantics của DBMS. Nó không xóa các transaction đã commit trước đó.

Nếu ứng dụng đã thực hiện tác dụng phụ ngoài database trước deadlock, chẳng hạn gửi email hoặc gọi payment provider, rollback không tự thu hồi tác dụng phụ đó. Đây là lý do cần outbox, idempotency hoặc compensation.

## 5. Đọc lịch sử transaction theo timeline

### 5.1. Dựng một dòng thời gian chung

Tạo timeline theo thời gian, không chỉ liệt kê log theo từng session.

Ví dụ:

~~~text
10:00:00.100  T1 BEGIN
10:00:00.120  T1 UPDATE hàng A, giữ khóa A
10:00:00.150  T2 BEGIN
10:00:00.170  T2 UPDATE hàng B, giữ khóa B
10:00:00.200  T1 UPDATE hàng B, chờ T2
10:00:00.230  T2 UPDATE hàng A, chờ T1
10:00:00.240  DB phát hiện deadlock
10:00:00.245  DB chọn T2 làm victim
10:00:00.260  T2 rollback, khóa B được giải phóng
10:00:00.270  T1 tiếp tục
10:00:00.310  T1 COMMIT
~~~

Các mốc trên là ví dụ. Trong hệ thống thực, log có thể dùng đồng hồ khác nhau hoặc không ghi đủ từng sự kiện. Cần chuẩn hóa timestamp và ghi nhận sai số clock.

### 5.2. Phân biệt thời điểm bắt đầu request và transaction

Một HTTP request có thể bắt đầu trước khi lấy connection. Transaction có thể bắt đầu muộn hơn. Một worker có thể nhận message rồi đợi pool trước khi mở transaction.

Do đó, không dùng request start time thay cho transaction start time. Ghi riêng:

- Request received.
- Connection acquired.
- Transaction begin.
- Statement start/end.
- Lock wait start/end nếu quan sát được.
- Commit/rollback start/end.
- Response sent.
- Message ACK hoặc job completion.

### 5.3. Gắn các định danh xuyên suốt

Các định danh hữu ích:

| Định danh | Dùng để nối |
|---|---|
| Request/correlation ID | HTTP request qua các service |
| Trace ID/span ID | Các lời gọi phân tán |
| Application operation ID | Một ý định nghiệp vụ ổn định |
| Idempotency key | Các lần gửi lại cùng request |
| DB session/process ID | Kết nối cụ thể tới database |
| Transaction ID/XID | Transaction database |
| Message/event ID | Message hoặc webhook |
| Business entity ID | Đơn hàng, payment, reservation |
| Worker/job ID | Tác vụ nền |

Không có một ID duy nhất luôn tồn tại ở mọi tầng. Cần lưu mapping giữa request ID, operation ID, session ID và transaction ID tại thời điểm mở transaction.

### 5.4. Transaction ID có thể tái sử dụng hoặc khác định dạng theo engine

PID, SPID, connection ID và transaction ID là các khái niệm khác nhau. Session ID có thể được tái sử dụng sau khi connection đóng; transaction ID có thể có vòng đời và format riêng.

Khi đối chiếu log, dùng kết hợp session ID, transaction ID, timestamp, database name, application name và request ID. Không nối hai log chỉ vì PID giống nhau ở hai thời điểm khác nhau.

### 5.5. Sắp xếp log khi nhiều máy có clock lệch

Trong microservices, application logs có thể đến từ nhiều host. Nếu đồng hồ lệch, sự kiện sau có thể mang timestamp nhỏ hơn sự kiện trước.

Nên:

- Đồng bộ clock bằng NTP hoặc cơ chế chuẩn của môi trường.
- Ghi timestamp UTC.
- Giữ monotonic duration trong process nếu có.
- Dùng trace/span parent-child để bổ sung quan hệ nhân quả.
- Ghi sự kiện bắt đầu/kết thúc với duration.
- Không suy ra thứ tự chỉ từ timestamp khi hai sự kiện gần nhau và clock không đáng tin.

## 6. Lịch sử câu lệnh trước deadlock

### 6.1. Deadlock graph thường chỉ chứa statement hiện tại

Một report có thể cho biết T1 đang chạy UPDATE bảng B và T2 đang chạy UPDATE bảng A. Nó không nhất thiết cho biết T1 đã khóa A bằng câu lệnh nào trước đó.

Muốn tái dựng thứ tự lấy khóa, cần lịch sử statement của từng transaction:

~~~text
Transaction T1:
  1. SELECT ... FOR UPDATE trên A
  2. UPDATE A
  3. UPDATE B  <-- đang chờ

Transaction T2:
  1. UPDATE B
  2. SELECT ... FOR UPDATE trên B
  3. UPDATE A  <-- đang chờ
~~~

Cần phân biệt statement đã hoàn tất trước deadlock với statement đang chạy và statement chưa từng được thực thi.

### 6.2. Log câu lệnh có thể thiếu bind values

Prepared statement log có thể chỉ chứa SQL template:

~~~sql
UPDATE inventory
SET quantity = quantity - ?
WHERE sku = ?
~~~

Nếu không ghi bind values hoặc không có trace an toàn tương đương, khó biết hai session tranh cùng SKU hay các SKU khác nhau.

Không nên bật log toàn bộ payload nhạy cảm chỉ để lấy parameter. Có thể ghi business key đã che, hash ổn định, resource ID hoặc structured fields cần thiết.

### 6.3. Một câu SQL có thể khóa nhiều tài nguyên

Câu UPDATE set-based có thể truy cập nhiều hàng/index theo execution plan. Trigger hoặc cascade có thể chạy thêm SQL bên trong transaction.

Lịch sử cần gồm:

- Statement bên ngoài.
- Trigger được kích hoạt.
- Stored procedure được gọi.
- Constraint check.
- Cascade operation.
- Index maintenance có liên quan.
- Locking hint và isolation level.
- Execution plan nếu cần hiểu thứ tự access.

Nếu chỉ xem repository method hoặc câu SQL ngoài cùng, có thể bỏ sót phần thực sự tạo cạnh chờ.

### 6.4. Execution plan giúp giải thích resource

Plan có thể cho thấy:

- Index seek hay scan.
- Join order.
- Access path của từng bảng.
- Predicate được áp dụng ở đâu.
- Số hàng ước lượng và thực tế.
- Sort/spool hoặc thao tác phụ.
- Có index khác nhau giữa hai câu lệnh hay không.

Plan không phải deadlock history và không tự chứng minh thứ tự khóa chính xác trong mọi tình huống. Hãy dùng nó cùng resource list và statement trace.

## 7. Đọc deadlock report trong SQL Server

### 7.1. Các phần của deadlock XML

SQL Server deadlock graph thường có các phần chính:

- victim-list: process được chọn làm victim.
- process-list: các process tham gia, thông tin transaction và câu lệnh.
- resource-list: resource cùng owner-list và waiter-list.

Một process có thể chứa:

- SPID/session ID.
- ECID hoặc execution context.
- Transaction ID.
- Wait resource và lock mode.
- Input buffer hoặc execution stack.
- Transaction isolation level.
- Deadlock priority và log/undo information tùy report.

### 7.2. Xem deadlock graph từ system_health

SQL Server thường có Extended Events session system_health thu thập deadlock graph. Có thể truy vấn event file theo cấu hình mặc định:

~~~sql
SELECT
    XEvent.value('(event/@timestamp)[1]', 'datetime2') AS event_time_utc,
    XEvent.query('(event/data/value/deadlock)[1]') AS deadlock_graph
FROM (
    SELECT CAST(event_data AS XML) AS XEvent
    FROM sys.fn_xe_file_target_read_file(
        'system_health*.xel',
        NULL,
        NULL,
        NULL
    )
) AS Data
WHERE XEvent.value('(event/@name)[1]', 'nvarchar(128)')
      = 'xml_deadlock_report'
ORDER BY event_time_utc DESC;
~~~

Đường dẫn file thực tế có thể cần chỉ rõ theo server instance và quyền truy cập. DMV/function và cấu hình target phụ thuộc phiên bản, quyền và vị trí file.

### 7.3. Đọc victim-list trước

Tìm process ID được liệt kê trong victim-list, rồi đối chiếu process-list để lấy session/transaction tương ứng.

Không nhầm victim process ID trong XML với SPID trực tiếp. Trong report, process ID có thể là định danh nội bộ; cần ánh xạ qua process-list.

### 7.4. Đọc resource-list

Với mỗi resource, tìm:

- Database/object/index.
- Resource type: KEY, PAGE, OBJECT, METADATA hoặc loại khác.
- Owner-list và lock mode.
- Waiter-list và lock mode.
- Process ID tương ứng.

Từ các cặp owner/waiter, dựng cạnh waiter → owner. Nếu có nhiều owner hoặc conversion, ghi đủ quan hệ.

### 7.5. Tìm SQL text và execution stack

Process-list có thể chứa inputbuf hoặc executionStack. Input buffer thường là câu lệnh được gửi gần thời điểm report. Execution stack có thể giúp thấy thủ tục hoặc module đang thực thi.

Câu lệnh trong report chưa chắc chứa đầy đủ các câu trước đó của transaction. Hãy nối session ID/transaction ID với Extended Events, Query Store, application logs hoặc tracing đã thu thập trước đó.

### 7.6. Deadlock priority và victim selection

SQL Server có thể dùng DEADLOCK_PRIORITY và chi phí rollback để lựa chọn victim. Transaction có priority thấp hơn có thể được ưu tiên làm victim; nếu priority tương đương, engine còn xét các yếu tố chi phí.

Không kết luận rằng transaction ít thay đổi nhất luôn bị chọn. Đọc victim-list và process metadata của report cụ thể.

### 7.7. Mã lỗi và transaction state

SQL Server thường trả lỗi 1205 cho deadlock victim. Transaction được chọn làm victim bị rollback. Ứng dụng nên bắt đúng lỗi, tạo transaction mới và retry toàn bộ đơn vị nghiệp vụ nếu thao tác an toàn.

Có thể ghi nhận session/request bị hủy qua Extended Events, kết hợp sys.dm_exec_requests, sys.dm_tran_locks và SQL text để điều tra trạng thái khi sự cố đang diễn ra.

## 8. Đọc deadlock report trong MySQL InnoDB

### 8.1. Lấy deadlock gần nhất

Dùng:

~~~sql
SHOW ENGINE INNODB STATUS;
~~~

Phần LATEST DETECTED DEADLOCK thường mô tả transaction tham gia, câu SQL, khóa đang giữ, khóa đang chờ và transaction được rollback.

Đây là deadlock gần nhất mà InnoDB lưu trong status output, không phải kho lịch sử đầy đủ. Nếu nhiều deadlock xảy ra, report mới có thể thay thế report trước.

### 8.2. Các dấu hiệu trong report

Có thể gặp nội dung tương tự:

~~~text
TRANSACTION 1:
  ... ACTIVE ...
  query: UPDATE ...
  HOLDS THE LOCK(S):
    RECORD LOCKS ...
  WAITING FOR THIS LOCK TO BE GRANTED:
    RECORD LOCKS ...

TRANSACTION 2:
  ... ACTIVE ...
  query: UPDATE ...
  HOLDS THE LOCK(S):
    RECORD LOCKS ...
  WAITING FOR THIS LOCK TO BE GRANTED:
    RECORD LOCKS ...

WE ROLL BACK TRANSACTION ...
~~~

Đọc từng transaction:

1. Transaction ID và thời gian hoạt động.
2. SQL đang thực hiện.
3. Index/table mà record lock thuộc về.
4. Lock mode và trạng thái waiting/granted.
5. Resource transaction đang giữ.
6. Resource transaction đang yêu cầu.
7. Transaction được chọn rollback.

### 8.3. Record lock và gap/next-key lock

InnoDB có thể dùng record lock, gap lock và next-key lock. Nếu report nói về index record hoặc gap, cần xem index và điều kiện range scan.

Một câu INSERT có thể chờ gap/duplicate-key check. Một SELECT ... FOR UPDATE hoặc UPDATE range có thể khóa nhiều record/index entry. Thiếu index phù hợp có thể làm scan và phạm vi khóa rộng hơn dự kiến.

### 8.4. Dùng Performance Schema cho lock waits hiện tại

Các bảng có thể giúp quan sát quan hệ waiter/blocker:

~~~sql
SELECT *
FROM performance_schema.data_lock_waits;
~~~

Và khóa được cấp/đang chờ:

~~~sql
SELECT *
FROM performance_schema.data_locks;
~~~

Các cột cụ thể phụ thuộc phiên bản. Join theo engine lock ID và transaction/thread metadata để tìm SQL text và session.

Lock wait hiện tại có thể biến mất ngay sau khi deadlock detector rollback victim. Vì vậy, Performance Schema snapshot không thay thế deadlock report đã được ghi lại.

### 8.5. Victim và phạm vi rollback

InnoDB thường rollback toàn bộ transaction được chọn làm deadlock victim. Phân biệt điều này với lock wait timeout: mặc định phổ biến, lock wait timeout chỉ rollback statement; innodb_rollback_on_timeout có thể thay đổi phạm vi rollback.

Mã lỗi deadlock thường là 1213 với SQLSTATE 40001. Ứng dụng cần nhận diện đúng lỗi và retry transaction mới nếu an toàn.

## 9. Đọc deadlock log trong PostgreSQL

### 9.1. Deadlock detail trong server log

PostgreSQL ghi deadlock khi phát hiện. Log có thể chứa:

- PID của process.
- Resource đang chờ, thường là transaction ID hoặc lock khác.
- Process đang chặn.
- Câu lệnh của từng process.
- Thông tin về chu trình.
- Thời điểm phát hiện và SQLSTATE.

Thông báo có thể có dạng khái niệm:

~~~text
Process 123 waits for ShareLock on transaction 456;
blocked by process 789.
Process 789 waits for ShareLock on transaction 321;
blocked by process 123.
Process 123: UPDATE ...
Process 789: UPDATE ...
~~~

Đây là ví dụ minh họa. Cần đọc nguyên văn log thực tế vì resource và mode thay đổi theo tình huống.

### 9.2. Hiểu “waits for ShareLock on transaction”

Trong PostgreSQL, một transaction có thể chờ transaction ID của transaction khác để biết thay đổi đó commit hay rollback. Vì vậy, report có thể nói process chờ ShareLock trên transaction ID thay vì trực tiếp nói khóa hàng A.

Để ánh xạ về bảng/hàng, cần xem câu lệnh, transaction history, relation/index và các lock view nếu trạng thái còn tồn tại.

### 9.3. Cấu hình log hỗ trợ điều tra

Các thiết lập thường hữu ích:

~~~sql
SHOW deadlock_timeout;
SHOW log_lock_waits;
SHOW log_line_prefix;
~~~

deadlock_timeout quy định khoảng chờ trước khi kiểm tra deadlock trong cơ chế PostgreSQL. log_lock_waits cho phép ghi log các lần chờ khóa kéo dài theo ngưỡng đó. log_line_prefix có thể được cấu hình để thêm PID, user, database, application name và transaction ID.

Cấu hình cần được điều chỉnh theo tải và chính sách log. Không đặt deadlock_timeout quá thấp chỉ để log nhiều hơn nếu chi phí kiểm tra và log không phù hợp.

### 9.4. SQLSTATE và transaction state

PostgreSQL thường dùng SQLSTATE 40P01 cho deadlock_detected. Sau lỗi, transaction hiện tại ở trạng thái aborted; ứng dụng cần ROLLBACK transaction trước khi tái sử dụng connection cho transaction mới.

Đừng nhầm 40P01 với 40001 (serialization_failure). Cả hai có thể dẫn đến retry toàn transaction, nhưng report và nguyên nhân khác nhau.

### 9.5. Trạng thái hiện tại sau khi deadlock đã được xử lý

Sau khi victim bị hủy, pg_stat_activity có thể không còn hiển thị wait chain cũ. Dữ liệu hiện tại không tái tạo được graph đã biến mất.

Dùng server log có timestamp, PID, application_name và transaction ID để đối chiếu với application tracing. pg_blocking_pids() hữu ích khi sự cố còn đang diễn ra, nhưng không phải lịch sử deadlock đã qua.

## 10. Đọc deadlock trace trong Oracle

### 10.1. ORA-00060

Oracle thường báo lỗi ORA-00060: deadlock detected while waiting for resource. Thông tin chi tiết có thể được ghi trong trace file, bao gồm deadlock graph, resource và session tham gia.

Report có thể thể hiện:

- Session ID và serial number.
- Resource type và identifier.
- Lock mode đang giữ/yêu cầu.
- Row wait hoặc object liên quan.
- Câu SQL của session nếu trace thu thập được.
- Quan hệ giữa các session trong chu trình.

### 10.2. Phân biệt rollback statement và rollback transaction

Oracle thường rollback statement gây deadlock, không tự động rollback toàn bộ transaction như một số DBMS khác. Các câu lệnh trước đó trong transaction có thể vẫn tồn tại và transaction có thể tiếp tục nếu ứng dụng xử lý phù hợp.

Điều này khiến cleanup cần được thiết kế rõ. Với một đơn vị nghiệp vụ cần nguyên tử, ứng dụng thường nên ROLLBACK toàn transaction rồi retry toàn bộ công việc trong transaction mới, thay vì chỉ chạy lại statement gây lỗi.

Hãy xác nhận hành vi qua trạng thái transaction và code xử lý của ứng dụng; không áp dụng quy tắc rollback của PostgreSQL, SQL Server hoặc InnoDB cho Oracle.

### 10.3. Đọc resource và row wait

Nếu trace có object ID, file/block/row hoặc resource identifier, dùng dictionary views để ánh xạ sang object/index. Một deadlock có thể liên quan đến row lock, index key hoặc tài nguyên khác.

Đừng kết luận từ tên bảng trong SQL text mà bỏ qua resource thực tế. Trigger, foreign key và index maintenance có thể tạo khóa ngoài câu lệnh nhìn thấy ở ứng dụng.

## 11. Tái dựng lịch sử giao dịch bị hủy

### 11.1. Lập bảng participant

Bắt đầu bằng bảng:

| Participant | Session | Transaction ID | SQL tại deadlock | Vai trò |
|---|---|---|---|---|
| P1 | Session A | TX-A | UPDATE bảng B | Waiter |
| P2 | Session B | TX-B | UPDATE bảng A | Waiter |
| P3 | Session C | TX-C | SELECT ... FOR UPDATE | Blocker/participant khác |

Điền dữ liệu từ report. Không đoán trường không có; đánh dấu “không được ghi nhận” và tìm nguồn bổ sung.

### 11.2. Lập bảng resource

| Resource | Owner | Owner mode | Waiter | Waiter mode |
|---|---|---|---|---|
| Index key A | TX-A | X | TX-B | X |
| Index key B | TX-B | X | TX-A | X |

Từ bảng này dựng cạnh waiter → owner. Nếu report có nhiều owner hoặc wait queue, thêm từng hàng.

### 11.3. Lập bảng sự kiện theo transaction

| Thời điểm | Transaction | Sự kiện | Resource | Kết quả |
|---|---|---|---|---|
| t1 | TX-A | UPDATE A | Key A | Được cấp |
| t2 | TX-B | UPDATE B | Key B | Được cấp |
| t3 | TX-A | UPDATE B | Key B | Chờ TX-B |
| t4 | TX-B | UPDATE A | Key A | Chờ TX-A |
| t5 | DB | Phát hiện deadlock | Chu trình A-B-A | Victim TX-B |
| t6 | TX-B | Rollback | Các khóa TX-B | Giải phóng |
| t7 | TX-A | Tiếp tục | Key B | Được cấp |
| t8 | TX-A | Commit | Transaction | Hoàn tất |

Bảng sự kiện cần đánh dấu đâu là timestamp trực tiếp từ log, đâu là suy luận từ graph. Không trình bày mốc suy luận như bằng chứng chính xác nếu không có event tương ứng.

### 11.4. Ghi rõ điều gì đã rollback

Với victim, xác định:

- Transaction đã thực hiện những statement nào.
- Statement nào đã hoàn tất trước deadlock.
- Statement nào đang chờ hoặc bị hủy.
- Phạm vi rollback theo DBMS.
- Có savepoint hay nested transaction semantics không.
- Có tác dụng phụ ngoài database đã xảy ra không.
- Ứng dụng có retry không và retry dùng cùng operation ID hay không.

Các thay đổi chưa commit có thể đã được hoàn tác, nhưng log ứng dụng vẫn có thể ghi “đã gửi yêu cầu” hoặc “đã gọi provider”. Đó là sự kiện khác với commit database.

### 11.5. Ghi rõ survivor đã làm gì

Sau khi victim rollback, survivor có thể tiếp tục. Tìm event:

- Statement đang chờ đã được cấp khóa.
- Statement hoàn tất.
- COMMIT thành công.
- ROLLBACK hoặc lỗi tiếp theo.
- Response hoặc message ACK.
- Các transaction khác được đánh thức.

Nếu không có log commit, không kết luận survivor đã commit chỉ vì deadlock report cho thấy victim bị hủy.

## 12. Phân biệt các loại kết thúc transaction

### 12.1. Deadlock victim

Detector tìm thấy chu trình và DBMS chọn victim. Mã lỗi và phạm vi rollback phụ thuộc engine.

### 12.2. Lock wait timeout

Một yêu cầu khóa chờ quá thời hạn. Không nhất thiết có chu trình. Phạm vi rollback khác nhau theo DBMS và cấu hình.

### 12.3. Statement timeout hoặc query cancellation

Một câu SQL bị hủy vì vượt thời gian hoặc nhận yêu cầu cancel. Transaction có thể còn mở, ở trạng thái aborted hoặc đã bị rollback tùy DBMS.

### 12.4. Application cancellation

Caller ngừng chờ hoặc task nhận interrupt. Điều này không chứng minh database đã nhận cancel.

### 12.5. Connection loss

Connection bị mất. Database có thể rollback transaction chưa commit khi phát hiện session kết thúc. Nếu COMMIT đã được gửi, client có thể không biết kết quả cuối.

### 12.6. Explicit rollback

Ứng dụng gửi ROLLBACK và nhận xác nhận. Đây là bằng chứng rõ hơn về transaction rollback, nhưng cần lưu ý connection có thể mất trước khi response được nhận.

### 12.7. Ambiguous commit

Ứng dụng gửi COMMIT nhưng không nhận phản hồi xác nhận. Server có thể đã commit hoặc chưa. Cần đối soát theo operation ID/idempotency key.

| Sự kiện | Có chu trình? | Transaction chắc chắn rollback? |
|---|---|---|
| Deadlock detected | Có | DBMS chọn victim và áp dụng rollback theo semantics |
| Lock wait timeout | Không nhất thiết | Phụ thuộc DBMS/cấu hình và phạm vi lỗi |
| Statement timeout | Không nhất thiết | Không thể suy ra chỉ từ timeout |
| Caller timeout | Không biết | Không |
| Connection loss trước COMMIT | Không nhất thiết | Thường rollback khi server phát hiện session mất |
| Connection loss trong COMMIT | Không biết | Outcome có thể không xác định với client |
| Rollback được xác nhận | Không cần chu trình | Có, với transaction hiện tại theo xác nhận |
| COMMIT được xác nhận | Không cần chu trình | Transaction đã commit |

## 13. Nối deadlock với application trace

### 13.1. Ghi transaction context ngay khi mở transaction

Khi application lấy connection và bắt đầu transaction, ghi một event có cấu trúc:

~~~json
{
  "event": "transaction_started",
  "request_id": "req-...",
  "operation_id": "op-...",
  "trace_id": "trace-...",
  "db_session_id": 123,
  "db_transaction_id": "tx-...",
  "application_name": "order-service",
  "isolation_level": "READ COMMITTED"
}
~~~

Đây là cấu trúc minh họa. Tên và khả năng lấy transaction ID phụ thuộc DBMS/driver. Nếu không có transaction ID ở thời điểm bắt đầu, vẫn ghi session ID và bổ sung mapping khi có thể.

### 13.2. Ghi statement theo transaction

Các event nên gồm:

- statement_started.
- statement_completed.
- statement_failed.
- lock_wait_started/ended nếu có instrumentation.
- transaction_commit_started.
- transaction_commit_confirmed.
- transaction_rollback_started.
- transaction_rollback_confirmed.
- connection_invalidated.

Mỗi event cần có request ID, operation ID, session/transaction ID, statement name hoặc query fingerprint và duration.

### 13.3. Dùng application name

DBMS thường cho phép đặt tên ứng dụng hoặc module trên connection. Ví dụ, PostgreSQL có application_name; SQL Server có application name trong connection string/session metadata; Oracle có module/action qua DBMS_APPLICATION_INFO; MySQL có thể dùng connection attributes hoặc session metadata tùy phiên bản.

Tên ứng dụng giúp phân biệt service, worker, batch và admin tool khi đọc report.

### 13.4. Không log payload nhạy cảm

Deadlock diagnostics cần biết statement và resource, nhưng không phải lúc nào cũng cần toàn bộ dữ liệu nghiệp vụ. Hãy ưu tiên:

- Query fingerprint.
- Business key đã che hoặc hash.
- Table/index/resource ID.
- Tenant ID theo chính sách log.
- Operation ID.
- Mã trạng thái.
- Lock mode và duration.

Nếu log bind values, phải đánh giá dữ liệu cá nhân, thông tin tài chính và quyền truy cập log.

## 14. Những gì cần lưu từ DBMS

### 14.1. Event/report gốc

Giữ report gốc ở định dạng engine cung cấp:

- SQL Server: deadlock XML/XEL.
- MySQL InnoDB: output deadlock hoặc log tương ứng.
- PostgreSQL: server log với detail/hint/context.
- Oracle: trace file và alert log tham chiếu.

Không chỉ chụp màn hình sơ đồ. XML/text gốc có thể chứa resource ID và metadata cần cho việc ánh xạ sau này.

### 14.2. Metadata schema tại thời điểm xảy ra

Schema có thể thay đổi sau sự cố. Lưu:

- Table/index names.
- Index definitions.
- Foreign keys và constraints.
- Trigger definitions hoặc version.
- Stored procedure/function version.
- Database isolation options.
- DBMS version và compatibility level.
- Execution plan nếu có.

Nếu chỉ điều tra sau một lần deploy, schema hiện tại có thể khác schema lúc deadlock xảy ra.

### 14.3. Workload context

Ghi nhận:

- Số request đồng thời.
- Batch/worker đang chạy.
- Connection pool utilization.
- Transaction age.
- CPU, I/O và memory pressure.
- Lock waits và deadlock rate.
- Retry count.
- Query duration distribution.
- Thời điểm deploy hoặc thay đổi index/configuration.

Deadlock thường phụ thuộc interleaving. Một thay đổi plan, index hoặc tải có thể làm thứ tự lấy khóa và thời gian giữ khóa thay đổi.

### 14.4. Giữ retention hợp lý

Deadlock report có thể chứa SQL text và thông tin nhạy cảm. Đặt retention, quyền truy cập và cơ chế che dữ liệu phù hợp. Giữ đủ lâu để liên kết với incident và regression test.

## 15. Phân tích một ví dụ đầy đủ

Giả sử hệ thống có bảng Order và Inventory. Một luồng xác nhận đơn cập nhật Order trước rồi Inventory; một luồng điều chỉnh kho cập nhật Inventory trước rồi Order.

### 15.1. Hai transaction

~~~sql
-- Session A: xác nhận đơn
BEGIN TRANSACTION;

UPDATE dbo.Orders
SET Status = 'CONFIRMED'
WHERE OrderId = 100;

UPDATE dbo.Inventory
SET Reserved = Reserved + 1
WHERE Sku = 'SKU-A';

COMMIT TRANSACTION;
~~~

~~~sql
-- Session B: điều chỉnh kho và đồng bộ đơn
BEGIN TRANSACTION;

UPDATE dbo.Inventory
SET Available = Available - 1
WHERE Sku = 'SKU-A';

UPDATE dbo.Orders
SET LastInventoryCheck = SYSUTCDATETIME()
WHERE OrderId = 100;

COMMIT TRANSACTION;
~~~

Nếu T1 giữ khóa Order và chờ Inventory, trong khi T2 giữ Inventory và chờ Order, graph tạo chu trình.

### 15.2. Bảng resource

| Resource | Owner | Waiter | Ý nghĩa |
|---|---|---|---|
| Order 100 | T1 | T2 | T2 cần cập nhật Order đang bị T1 giữ |
| Inventory key SKU-A | T2 | T1 | T1 cần cập nhật Inventory đang bị T2 giữ |

Cạnh waiter → owner:

\[
T1 \rightarrow T2,\quad T2 \rightarrow T1
\]

### 15.3. Đọc victim

Giả sử report chọn T2 làm victim. DBMS rollback T2 theo semantics của sản phẩm. Khóa Inventory của T2 được giải phóng. T1 tiếp tục, cập nhật Inventory rồi commit.

Không được suy ra rằng thay đổi Inventory của T2 đã commit. Cũng không được suy ra T1 chắc chắn commit nếu chưa có log xác nhận.

### 15.4. Lịch sử cần tìm

Application trace nên cho biết:

- Request nào tạo Session A/B.
- Operation ID của xác nhận đơn và điều chỉnh kho.
- Thời điểm mỗi transaction bắt đầu.
- Statement nào cập nhật Order và Inventory.
- T2 có gọi dịch vụ ngoài trước khi deadlock không.
- T2 có retry không.
- T1 commit thành công hay tiếp tục lỗi.
- Order và Inventory sau sự cố có khớp nhau không.

### 15.5. Nguyên nhân và hướng sửa

Nguyên nhân trực tiếp là thứ tự lấy khóa ngược nhau. Hướng sửa có thể là:

- Quy định tất cả luồng khóa Order trước Inventory hoặc theo một thứ tự tài nguyên toàn cục.
- Tách thao tác nếu có thể giảm phạm vi transaction.
- Dùng transaction ngắn.
- Đảm bảo index phù hợp để tránh scan rộng.
- Thiết kế retry cho deadlock victim.
- Bảo vệ tác dụng phụ ngoài database bằng outbox/idempotency.

Sau khi sửa, tạo deterministic test ép hai transaction đến đúng cửa sổ cạnh tranh và xác nhận không còn chu trình hoặc lỗi được xử lý theo hợp đồng.

## 16. Phân tích lịch sử khi có trigger, cascade và stored procedure

### 16.1. Câu SQL ngoài cùng chưa phải toàn bộ transaction

Ví dụ:

~~~sql
UPDATE dbo.Orders
SET Status = 'PAID'
WHERE OrderId = 100;
~~~

Câu lệnh này có thể kích hoạt trigger cập nhật PaymentSummary, Inventory hoặc Audit. Trigger có thể gọi stored procedure hoặc cập nhật bảng khác.

Một session khác có thể đi theo thứ tự ngược. Deadlock report có thể chỉ hiển thị statement ngoài cùng hoặc một phần execution stack.

### 16.2. Lần theo dependency

Với mỗi participant:

1. Xác định stored procedure hoặc ORM operation.
2. Kiểm tra trigger trên các bảng được ghi.
3. Kiểm tra FK cascade và constraint.
4. Xem các index được cập nhật.
5. Đối chiếu resource trong deadlock graph.
6. Xác định thứ tự các thao tác nội bộ.
7. Ghi rõ phần nào được report chứng minh và phần nào là suy luận.

### 16.3. Không quy lỗi cho trigger chỉ vì nó xuất hiện

Trigger có thể là nơi tạo thêm lock nhưng nguyên nhân thiết kế có thể là thứ tự truy cập giữa hai luồng. Cần dựng chu trình cụ thể và chỉ ra cạnh nào được tạo bởi thao tác nào.

Nếu bỏ trigger mà deadlock biến mất trong một test, đó là bằng chứng hữu ích nhưng vẫn cần xác định tác động nghiệp vụ và phương án thay thế.

## 17. Xử lý deadlock victim ở ứng dụng

### 17.1. Phân loại lỗi theo DBMS

Một số mã thường gặp:

| DBMS | Deadlock indicator thường gặp |
|---|---|
| SQL Server | Error 1205 |
| MySQL InnoDB | Error 1213, SQLSTATE 40001 |
| PostgreSQL | SQLSTATE 40P01 |
| Oracle | ORA-00060 |

Driver/framework có thể bọc lỗi trong exception khác. Hãy xem vendor code, SQLSTATE và cause chain.

### 17.2. Retry toàn bộ đơn vị nghiệp vụ

Nếu transaction bị rollback, dữ liệu đã đọc trước đó có thể không còn phù hợp. Thông thường cần:

1. Kết thúc/rollback transaction bị lỗi theo DBMS.
2. Đóng hoặc phục hồi connection đúng cách.
3. Bắt đầu transaction mới.
4. Đọc lại dữ liệu.
5. Tính lại quyết định.
6. Thực hiện lại toàn bộ nghiệp vụ.
7. Giới hạn số lần retry.

Không chỉ gửi lại câu UPDATE cuối nếu nó phụ thuộc vào kết quả SELECT trước đó.

### 17.3. Dùng backoff và jitter

Nếu nhiều request cùng bị deadlock rồi retry ngay lập tức, chúng có thể tái tạo cùng lịch và làm contention tăng.

Dùng backoff tăng dần, jitter và số lần thử tối đa. Ghi lại operation ID, attempt number, error code và kết quả mỗi lần thử.

### 17.4. Retry phải an toàn với tác dụng phụ

Rollback database không thu hồi email, HTTP call, payment capture hoặc message đã phát. Nếu transaction có tác dụng phụ ngoài DB, cần:

- Idempotency key ở provider.
- Transactional outbox.
- Inbox/dedup ở consumer.
- Compensation workflow nếu thao tác không thể đảo ngược.
- Chỉ phát side effect sau khi transaction database commit theo thiết kế.

### 17.5. Không retry mọi lỗi giống nhau

- Deadlock: thường có thể retry toàn transaction.
- Serialization failure/update conflict: retry toàn transaction nếu logic có thể tính lại.
- Unique violation: thường là conflict nghiệp vụ, không retry mù quáng.
- Lock timeout: có thể không có chu trình; cần xem blocker và chính sách.
- Connection loss trong COMMIT: outcome có thể không xác định; cần đối soát trước khi chạy lại.
- Validation/constraint error: thường cần sửa input hoặc xử lý nghiệp vụ.

## 18. Đánh giá transaction bị rollback có để lại tác dụng phụ không

### 18.1. Phân biệt DB rollback với external rollback

Ví dụ transaction:

1. Cập nhật Order.
2. Gọi payment provider.
3. Cập nhật Inventory.
4. Deadlock.
5. Database rollback.

Nếu payment provider đã capture tiền ở bước 2, database rollback không hoàn tiền tự động. Hệ thống có thể có payment thành công nhưng Order chưa được xác nhận.

Đây không phải lỗi mà deadlock graph tự giải quyết. Cần kiểm tra lịch sử tác dụng phụ và workflow bù trừ.

### 18.2. Dùng outbox để tách phát event

Ghi thay đổi nghiệp vụ và outbox event trong cùng transaction. Sau commit, worker phát event. Nếu deadlock victim rollback, cả thay đổi và outbox event đều không commit.

Worker có thể phát lại event nếu crash sau publish nhưng trước khi đánh dấu đã gửi; consumer cần dedup.

### 18.3. Đối soát theo operation ID

Với payment/order/transfer, hãy có một operation ID ổn định để truy vấn:

- Operation đã tồn tại chưa?
- Có resource ID nào được tạo?
- Payment provider đã chấp nhận chưa?
- Ledger đã ghi chưa?
- Outbox event đã commit chưa?
- Operation đang PROCESSING, COMPLETED hay cần đối soát?

Không tạo operation ID mới cho lần retry của cùng ý định.

## 19. Checklist đọc deadlock graph

Khi nhận report, hãy đi theo trình tự:

1. Ghi timestamp, DBMS, database và nguồn report.
2. Xác định victim từ victim-list hoặc phần kết luận của engine.
3. Liệt kê tất cả participant và phân biệt session ID với transaction ID.
4. Với mỗi resource, ghi object/index/key/range.
5. Ghi owner, waiter và lock mode tương ứng.
6. Dựng cạnh waiter → blocker theo đúng quy ước.
7. Xác định chu trình cốt lõi và participant nằm ngoài chu trình.
8. Tìm statement đang chạy và execution stack.
9. Nối statement với lịch sử transaction trước đó.
10. Kiểm tra trigger, cascade, constraint và index maintenance.
11. Xác định transaction victim đã rollback ở phạm vi nào.
12. Xác nhận survivor có commit hay tiếp tục lỗi.
13. Kiểm tra tác dụng phụ ngoài database.
14. Đối chiếu request ID, operation ID, trace ID và transaction ID.
15. Xác định thứ tự khóa ngược nhau hoặc predicate/range gây xung đột.
16. Chọn thay đổi và tạo test tái hiện.

## 20. Mẫu ghi nhận một incident deadlock

Dùng mẫu ngắn để tránh bỏ sót bằng chứng:

~~~text
INCIDENT:
  incident_id:
  detected_at_utc:
  dbms_version:
  database:
  application/service:

VICTIM:
  session_id:
  transaction_id:
  error_code:
  rollback_scope:
  retry_attempt:

PARTICIPANTS:
  - session_id:
    transaction_id:
    request_id:
    operation_id:
    current_statement:
    isolation_level:

RESOURCES:
  - resource:
    object/index:
    owner:
    owner_mode:
    waiter:
    waiter_mode:

CYCLE:
  T1 -> T2 -> T3 -> T1

TRANSACTION HISTORY:
  - timestamp:
    transaction:
    statement/event:
    resource:
    outcome:

OUTCOME:
  victim_rollback_confirmed:
  survivor_commit_confirmed:
  external_side_effects:
  duplicate_or_missing_business_effect:

ROOT CAUSE:
  conflicting_lock_order_or_predicate:
  contributing_index_or_plan:
  trigger_or_constraint:

REMEDIATION:
  code/schema/configuration:
  retry_policy:
  regression_test_id:

EVIDENCE:
  deadlock_report_path:
  application_trace:
  db_log:
  execution_plan:
~~~

Nếu một trường chưa có bằng chứng, ghi “unknown” hoặc “not captured”. Không điền bằng phỏng đoán.

## 21. Biến deadlock report thành regression test

### 21.1. Lấy lịch từ report

Từ graph và transaction history, xác định:

- Hai hoặc nhiều transaction.
- Tài nguyên mỗi transaction lấy trước.
- Tài nguyên tiếp theo nó yêu cầu.
- Điểm chờ.
- Điều kiện khiến thứ tự khác nhau.
- Kết quả hợp lệ sau khi transaction kết thúc.

### 21.2. Tạo deterministic schedule

Dùng connection riêng cho từng actor và barrier/latch:

~~~text
T1: khóa A
T2: khóa B
Barrier
T1: yêu cầu B
T2: yêu cầu A
Observer: xác nhận lock waits
Controller: đợi deadlock hoặc timeout có giới hạn
~~~

Không dùng sleep để hy vọng các transaction đến đúng thời điểm. Nếu cần kiểm tra deadlock detector, observer phải xác nhận session thực sự đang chờ.

### 21.3. Assert kết quả nghiệp vụ

Không assert victim luôn là T1 hoặc T2. Chính sách chọn victim có thể thay đổi.

Hãy assert:

- Một transaction bị hủy theo đúng lỗi deadlock.
- Transaction còn lại có thể tiến triển.
- Không có thay đổi một phần đã commit từ victim.
- Bất biến dữ liệu giữ đúng.
- Retry không tạo tác dụng phụ trùng.
- Connection/transaction được cleanup.
- Sự cố được ghi nhận đủ context.

### 21.4. Giữ cả test trước và sau khi sửa

Một reproducer nên chứng minh lỗi có thể xảy ra trên thiết kế cũ. Regression test sau sửa phải chứng minh lịch tương tự không còn vi phạm bất biến hoặc deadlock được xử lý an toàn.

Không xóa test chỉ vì lỗi hiếm khi tái hiện. Hãy giữ lịch xác định và chạy stress test bổ sung khi phù hợp.

## 22. Những nhầm lẫn thường gặp

**“Deadlock report cho biết toàn bộ SQL đã chạy trong transaction.”**

Sai. Report thường là snapshot participant/resource và statement hiện tại. Cần application trace hoặc statement history để biết các thao tác trước đó.

**“Session bị lỗi là victim.”**

Không nhất thiết. Một câu SQL trong session có thể báo lỗi; cần đọc victim-list hoặc kết luận của engine để xác định transaction được chọn.

**“Câu SQL cuối cùng tạo ra toàn bộ deadlock.”**

Sai. Chu trình thường phụ thuộc các khóa đã lấy ở những statement trước đó.

**“Mọi process xuất hiện trong report đều nằm trong chu trình.”**

Sai. Có thể có waiter hoặc transaction ngoài chu trình đang phụ thuộc vào participant.

**“Nhiều session chờ lâu là deadlock.”**

Sai. Có thể chỉ là blocking chain. Cần chu trình hoặc deadlock event được engine xác nhận.

**“Rollback victim đồng nghĩa mọi tác dụng phụ đã được hoàn tác.”**

Sai. Rollback chỉ áp dụng cho transaction database theo semantics của DBMS. Email, HTTP call hoặc payment bên ngoài cần cơ chế riêng.

**“Mã lỗi deadlock giống nhau ở mọi DBMS.”**

Sai. SQL Server, MySQL, PostgreSQL và Oracle có mã lỗi, phạm vi rollback và cách ghi report khác nhau.

**“Sau deadlock, survivor chắc chắn commit.”**

Sai. Survivor chỉ có cơ hội tiếp tục sau khi chu trình được phá. Cần log commit/rollback riêng để xác nhận.

**“Chỉ cần thêm retry là hết deadlock.”**

Sai. Retry phục hồi request; nó không sửa thứ tự lấy khóa. Nếu lịch cũ lặp lại, deadlock có thể tái diễn.

**“Một ảnh chụp DMV sau sự cố đủ để tái dựng graph.”**

Sai. Khi victim đã rollback, wait edges có thể biến mất. Cần lưu deadlock report tại thời điểm phát hiện.

**“Có thể nối log chỉ bằng session ID.”**

Không an toàn. Session ID có thể được tái sử dụng. Kết hợp timestamp, transaction ID, database, application name và request/operation ID.

**“Nếu victim rollback thì có thể tạo request mới với key mới.”**

Sai. Nếu request ban đầu có thể đã thực hiện tác dụng phụ hoặc client không biết kết quả, key mới có thể tạo nghiệp vụ trùng. Giữ operation/idempotency key ổn định qua retry.

## 23. Quy trình điều tra từ lúc nhận cảnh báo đến khi sửa xong

### Bước 1: Bảo toàn bằng chứng

Lưu deadlock graph gốc, server log, thời điểm, database version, schema/index metadata và application trace. Đừng chỉ giữ screenshot hoặc một dòng exception.

### Bước 2: Xác định victim và participant

Đọc victim-list, process/session list và transaction ID. Tách session ID khỏi transaction ID và request ID.

### Bước 3: Dựng resource graph

Với mỗi resource, ghi owner, waiter, lock mode và object/index. Tạo cạnh waiter → blocker và tìm chu trình.

### Bước 4: Tái dựng transaction history

Nối session/transaction với statement logs, request trace, stored procedure, trigger và batch/worker. Xác định thao tác đã lấy khóa trước đó.

### Bước 5: Xác nhận rollback scope

Đọc semantics của DBMS và log ứng dụng. Xác nhận victim rollback toàn transaction hay statement, survivor commit hay không, connection còn dùng được hay đã bị loại bỏ.

### Bước 6: Đối soát nghiệp vụ

Kiểm tra dữ liệu đã commit, ledger, payment provider, outbox/inbox, webhook và tác dụng phụ ngoài database. Tìm operation bị thiếu hoặc bị lặp.

### Bước 7: Xác định nguyên nhân trực tiếp

Ví dụ:

- Thứ tự lấy khóa ngược nhau.
- Conversion deadlock.
- Range/gap/key-range lock.
- FK/UNIQUE/trigger/cascade.
- Scan rộng do thiếu index.
- Transaction quá dài.
- Hàng nóng hoặc guard row.
- Application lock kết hợp row lock.

### Bước 8: Chọn biện pháp sửa

Có thể:

- Chuẩn hóa thứ tự lấy khóa.
- Dùng atomic conditional UPDATE.
- Tạo index phù hợp.
- Thu hẹp transaction.
- Dùng UPDLOCK/HOLDLOCK hoặc isolation phù hợp.
- Thay đổi mô hình dữ liệu/constraint.
- Tách tác dụng phụ bằng outbox.
- Thêm idempotency và retry có giới hạn.

### Bước 9: Tạo regression test

Dùng lịch deterministic từ report. Kiểm tra cả dữ liệu cuối, lỗi được phân loại, rollback, retry và tác dụng phụ.

### Bước 10: Theo dõi sau triển khai

So sánh deadlock rate, lock wait duration, query latency, retry count, transaction age và các bất biến nghiệp vụ trước/sau thay đổi.

## 24. Checklist bằng chứng tối thiểu

Một incident chỉ nên được xem là đã hiểu khi có đủ bằng chứng để trả lời:

- Có deadlock event/report gốc không?
- Victim được xác định từ nguồn nào?
- Các participant và transaction ID là gì?
- Mỗi cạnh được tạo bởi resource và lock mode nào?
- Chu trình waiter → blocker cụ thể là gì?
- Câu lệnh nào đang chạy khi phát hiện?
- Câu lệnh trước đó nào đã lấy khóa?
- Trigger, cascade, FK hoặc index có tham gia không?
- Transaction victim bị rollback ở phạm vi nào?
- Survivor đã commit hay rollback?
- Có tác dụng phụ ngoài DB nào xảy ra trước rollback không?
- Request/operation nào cần retry hoặc đối soát?
- Bất biến nào có nguy cơ bị vi phạm?
- Có reproducer xác định được lịch tương tự không?
- Có regression test và metric xác nhận sau sửa không?

Nếu thiếu transaction history, hãy ghi rõ khoảng trống. Không được suy ra toàn bộ trình tự chỉ từ statement cuối cùng trong deadlock graph.

## 25. Kết luận

Deadlock graph cho thấy cấu trúc phụ thuộc đã khiến các giao dịch mắc kẹt: ai đang chờ ai, trên tài nguyên nào và với lock mode nào. Transaction history cho biết các khóa đó được lấy từ những thao tác nào, giao dịch nào bị chọn làm victim, thay đổi nào được rollback và giao dịch còn lại đã kết thúc ra sao.

Muốn điều tra chính xác, hãy đọc report gốc, dựng resource và wait-for graph, nối participant với session/transaction/request ID, rồi tái dựng timeline từ statement log và application trace. Sau đó xác nhận rollback scope, đối soát tác dụng phụ và chuyển lịch lỗi thành regression test. Khi report thiếu lịch sử, hãy nói rõ điều chưa biết và thu thập thêm bằng chứng; đừng coi một câu SQL cuối cùng là toàn bộ nguyên nhân của deadlock.
