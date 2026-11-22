# Bản sao phục vụ đọc: phân luồng truy vấn và độ trễ sao chép

Trong chương **Mở rộng hệ thống** của module **DATABASE_PERFORMANCE**, bản sao phục vụ đọc (*read replica* hoặc *read-only replica*) cho phép phân phối một phần truy vấn đọc sang các node khác, giảm áp lực CPU, bộ nhớ và I/O trên primary. Mô hình này hữu ích khi workload có tỷ lệ đọc cao, truy vấn báo cáo tiêu thụ nhiều tài nguyên hoặc nhiều ứng dụng cần đọc cùng một tập dữ liệu. Tuy nhiên, replica thường nhận thay đổi từ primary qua cơ chế sao chép bất đồng bộ hoặc bán đồng bộ, vì vậy dữ liệu trên replica có thể chậm hơn primary.

Thiết kế read replica cần giải quyết đồng thời ba vấn đề: truy vấn nào được chuyển sang replica, mức dữ liệu cũ mà nghiệp vụ chấp nhận và cách ứng dụng xử lý khi replica lag hoặc không khả dụng. Nếu chỉ chuyển mọi câu `SELECT` sang replica, ứng dụng có thể đọc dữ liệu cũ ngay sau khi ghi, gặp lỗi với locking read hoặc đọc không nhất quán giữa nhiều câu lệnh. Mở rộng đọc chỉ hiệu quả khi routing bám theo ngữ nghĩa nghiệp vụ, replica có đủ năng lực apply log và hệ thống đo được độ trễ sao chép.

## 1. Kiến trúc primary và read replica

Trong kiến trúc phổ biến, primary nhận thao tác ghi và là nguồn phát sinh thay đổi chuẩn. Replica nhận log hoặc luồng thay đổi từ primary, áp dụng các thay đổi đó lên bản sao dữ liệu rồi phục vụ truy vấn đọc.

```text
                  +----------------------+
                  |   Java/API services  |
                  +----------+-----------+
                             |
                    Query routing layer
                      /             \
             write / strong read   read-only
                    /                 \
          +---------v------+   +------v-------+
          |    PRIMARY     |   | READ ROUTER  |
          | writes + reads |   +------+-------+
          +--------+-------+          |
                   |             +----+----+
             WAL/binlog/log       |         |
                   |          +--v----+ +--v----+
                   +--------->| REPLICA| |REPLICA|
                              |   A   | |   B   |
                              +-------+ +-------+
```

Primary và replica có thể nằm trên cùng vùng mạng, khác máy, khác availability zone hoặc khác region. Vị trí ảnh hưởng tới network latency, chi phí truyền log, khả năng chịu lỗi và độ trễ sao chép.

### 1.1. Replica giúp mở rộng điều gì?

- Phân tán truy vấn đọc độc lập giữa nhiều node.
- Cách ly một số workload báo cáo hoặc truy vấn dài khỏi primary.
- Cung cấp bản sao cho tác vụ export, tìm kiếm hoặc phân tích gần thời gian thực.
- Tăng khả năng phục vụ đọc khi một node đọc gặp sự cố, nếu có routing và failover phù hợp.
- Đặt bản sao gần người dùng ở vùng địa lý khác để giảm network round trip, nếu nghiệp vụ chấp nhận độ trễ sao chép.

Replica không tự động tăng năng lực ghi của primary. Primary vẫn phải tạo log và truyền thay đổi; replica phải nhận, ghi và apply các thay đổi đó. Khi workload ghi tăng, replication stream và apply worker cũng tăng tải. Nhiều replica còn làm tăng network, storage, chi phí vận hành và nhu cầu giám sát.

### 1.2. Primary vẫn có thể phục vụ đọc

Không nhất thiết chuyển toàn bộ truy vấn đọc khỏi primary. Những truy vấn cần dữ liệu mới nhất, cần khóa, cần đọc lại kết quả vừa ghi hoặc tham gia transaction ghi nên tiếp tục dùng primary. Replica phù hợp với truy vấn có thể chấp nhận mức nhất quán đã định nghĩa.

Một thiết kế thực tế thường có ba nhóm:

1. Ghi và đọc cần nhất quán mạnh: primary.
2. Đọc thông thường có thể chấp nhận dữ liệu trễ trong giới hạn: read replica.
3. Báo cáo nặng hoặc truy vấn phân tích dài: replica chuyên dụng hoặc kho phân tích riêng, tùy tải.

## 2. Cơ chế sao chép và độ trễ

Replica cần nhận biết thay đổi đã commit trên primary và áp dụng chúng theo đúng thứ tự cần thiết. Cơ chế cụ thể phụ thuộc hệ quản trị, nhưng thường có các giai đoạn gửi log, nhận log, ghi bền vững và replay/apply.

### 2.1. Các giai đoạn của replication

Một luồng sao chép có thể được hình dung qua các bước:

1. Transaction commit trên primary và tạo log record.
2. Log được gửi qua network tới replica.
3. Replica nhận và ghi log vào vùng lưu trữ phù hợp.
4. Replica replay/apply log để cập nhật data page hoặc trạng thái dữ liệu.
5. Truy vấn trên replica nhìn thấy thay đổi sau khi cơ chế apply và snapshot của truy vấn cho phép nhìn thấy phiên bản mới.

Một số hệ thống tách rõ vị trí log đã gửi, đã nhận, đã flush và đã replay. Vì vậy, “replica lag” không phải lúc nào cũng chỉ có một con số. Có thể network đang chậm, ghi log ở replica chậm, hoặc apply worker không theo kịp.

### 2.2. Sao chép đồng bộ và bất đồng bộ

| Kiểu | Cách xác nhận commit khái quát | Ưu điểm | Đánh đổi |
|---|---|---|---|
| Bất đồng bộ | Primary có thể xác nhận commit trước khi replica nhận hoặc apply log | Latency ghi thấp hơn, primary ít phụ thuộc network replica | Replica có thể lag; thay đổi mới nhất có nguy cơ chưa có ở replica khi primary hỏng |
| Đồng bộ | Commit chờ một hoặc nhiều replica đạt điều kiện xác nhận đã cấu hình | Có thể giảm nguy cơ mất dữ liệu đã xác nhận khi failover theo semantics cấu hình | Commit phụ thuộc latency và khả năng sẵn sàng của replica |
| Bán đồng bộ | Chờ replica nhận/ghi log ở một mức nhất định nhưng không nhất thiết chờ apply | Thỏa hiệp giữa latency và bảo vệ log | Không đồng nghĩa replica đã đọc được dữ liệu mới; semantics tùy engine |

Phải đọc chính xác điều kiện xác nhận của sản phẩm. “Replica đã nhận log”, “đã flush log” và “đã apply log” là ba trạng thái khác nhau. Một cơ chế bán đồng bộ có thể bảo đảm log đã tới replica nhưng truy vấn trên replica vẫn chưa thấy transaction đó vì apply chưa hoàn tất.

### 2.3. Replication lag

Replication lag là độ chậm giữa trạng thái đã commit trên primary và trạng thái đã được replica nhận hoặc áp dụng. Có thể đo theo:

- Thời gian ước lượng giữa thời điểm commit và thời điểm replay.
- Khoảng cách log position/LSN/GTID/SCN.
- Số byte log đang chờ gửi hoặc apply.
- Số transaction hoặc event còn trong hàng đợi.
- Tốc độ tạo log so với tốc độ truyền và apply.

Không dùng một metric thời gian duy nhất cho mọi hệ thống. Nếu primary không phát sinh transaction mới, timestamp của lần replay gần nhất có thể cũ dù replica đã theo kịp. Ngược lại, metric log position cho biết khoảng cách dữ liệu nhưng không trực tiếp biểu diễn số giây người dùng phải chờ.

### 2.4. Network lag và apply lag

- **Send/transport lag:** primary tạo log nhanh hơn tốc độ gửi hoặc network không đủ băng thông.
- **Receive/flush lag:** replica nhận log nhưng chưa ghi bền vững theo yêu cầu.
- **Apply/replay lag:** log đã tới replica nhưng worker áp dụng không theo kịp.
- **Query visibility lag:** log đã apply nhưng transaction đọc hiện tại vẫn giữ snapshot cũ.

Phân loại đúng giai đoạn giúp chọn biện pháp phù hợp. Tăng network bandwidth không giải quyết được apply lag do CPU hoặc I/O; tăng apply worker không giúp nếu thứ tự transaction hoặc giới hạn engine không cho phép song song hóa thêm.

## 3. Độ nhất quán khi đọc replica

Replica bất đồng bộ có thể trả dữ liệu cũ hơn primary. Đây là đặc tính kiến trúc cần được biểu đạt trong hợp đồng dữ liệu của ứng dụng, không phải lỗi có thể loại bỏ chỉ bằng cách thêm retry.

### 3.1. Eventual consistency

Eventual consistency có nghĩa là nếu không có thay đổi mới và replication tiếp tục tiến triển, replica sẽ hội tụ về trạng thái primary. Trong khoảng thời gian trước khi hội tụ, hai node có thể trả kết quả khác nhau.

Ví dụ:

1. Người dùng tạo đơn hàng trên primary.
2. API trả về thành công.
3. Trang danh sách ngay sau đó đọc replica.
4. Replica chưa apply transaction tạo đơn nên trang chưa thấy đơn vừa tạo.

Nếu giao diện coi đây là lỗi nghiệp vụ, người dùng có thể bấm tạo lại và sinh đơn trùng. Ứng dụng cần có chiến lược read-your-writes hoặc thông báo trạng thái đang đồng bộ.

### 3.2. Read-your-writes consistency

Read-your-writes yêu cầu người dùng nhìn thấy ít nhất những thay đổi mà chính họ vừa ghi. Cách đơn giản là sau một thao tác ghi, giữ các lần đọc liên quan trên primary trong một khoảng thời gian hoặc cho tới khi xác nhận replica đã apply tới vị trí commit đó.

Một cách chính xác hơn là lấy token vị trí commit từ primary, rồi chờ replica đạt hoặc vượt token trước khi định tuyến truy vấn đọc sang replica. Token có thể là LSN, GTID, commit sequence hoặc cơ chế tương ứng của engine.

Ví dụ luồng xử lý:

```text
Client -> API: cập nhật hồ sơ
API -> Primary: COMMIT
Primary -> API: commit token T
API -> Replica: chờ replica apply >= T
Replica -> API: đã theo kịp T
API -> Replica: đọc hồ sơ
API -> Client: trả dữ liệu mới
```

Nếu replica không đạt token trong timeout, ứng dụng có thể fallback sang primary hoặc trả trạng thái phù hợp. Không nên chờ vô hạn vì một replica lag nặng có thể giữ request và làm cạn connection pool.

### 3.3. Monotonic reads

Monotonic reads yêu cầu một client không nhìn thấy trạng thái cũ hơn trạng thái mà client đã từng quan sát. Nếu request đầu được route tới replica A đã apply tới version 100, request tiếp theo không nên được route tới replica B mới chỉ ở version 95.

Có thể đạt hành vi này bằng sticky routing theo session/tenant, chọn replica có replay position đủ mới hoặc mang theo consistency token từ lần đọc trước. Sticky routing giảm nguy cơ đổi sang replica chậm hơn nhưng không bảo đảm replica được chọn luôn theo kịp nếu nó bị lag hoặc failover.

### 3.4. Bounded staleness

Bounded staleness cho phép dữ liệu cũ tối đa một ngưỡng đã định, ví dụ 2 giây hoặc một khoảng log position. Router chỉ chọn replica đáp ứng ngưỡng; nếu không có replica phù hợp, có thể chuyển primary, chờ có giới hạn hoặc từ chối một số chức năng không thiết yếu.

Ngưỡng phải được chọn theo nghiệp vụ. Dashboard tổng hợp có thể chấp nhận 30 giây; màn hình trạng thái thanh toán có thể cần dữ liệu mới hơn nhiều. Không dùng một ngưỡng chung cho mọi endpoint.

### 3.5. Strong consistency và truy vấn cần primary

Các truy vấn cần đọc chính xác trạng thái mới nhất hoặc tham gia quyết định ghi nên đọc primary, trừ khi hệ thống có cơ chế đồng bộ và consistency guarantee khác đã được xác minh. Ví dụ:

- Đọc số dư ngay sau khi ghi giao dịch.
- Kiểm tra tồn kho trước khi trừ tồn.
- Kiểm tra trạng thái thanh toán trước khi cho phép giao hàng.
- Đọc dữ liệu vừa tạo để trả response ngay sau commit.
- `SELECT ... FOR UPDATE` hoặc locking read.
- Transaction thực hiện read-modify-write trên nhiều câu lệnh.

Đọc primary cũng không tự động giải quyết mọi vấn đề nhất quán: transaction isolation, snapshot và logic cập nhật vẫn phải đúng. Nhưng nó tránh thêm độ trễ sao chép giữa hai node.

## 4. Phân luồng truy vấn đọc và ghi

Routing nên dựa trên ý nghĩa của thao tác nghiệp vụ và đặc điểm transaction, không chỉ dựa vào việc câu SQL bắt đầu bằng `SELECT` hay `UPDATE`.

### 4.1. Quy tắc định tuyến cơ bản

| Loại thao tác | Đích thường phù hợp | Lý do |
|---|---|---|
| INSERT/UPDATE/DELETE/MERGE | Primary | Ghi vào nguồn chuẩn |
| SELECT cần đọc ngay kết quả vừa ghi | Primary hoặc replica đã xác nhận token | Bảo đảm read-your-writes |
| SELECT báo cáo chấp nhận dữ liệu trễ | Read replica phù hợp | Giảm tải primary |
| SELECT ... FOR UPDATE | Primary | Cần khóa và phối hợp với writer |
| Transaction có cả đọc và ghi | Primary trong toàn transaction | Giữ một transaction context và semantics nhất quán |
| Truy vấn quản trị/DDL | Theo quy định engine, thường primary | Thay đổi schema và metadata cần điều phối riêng |
| Truy vấn phân tích dài | Replica chuyên dụng hoặc kho phân tích | Cách ly tài nguyên và tải scan |

Một câu `SELECT` có thể gọi function có side effect, đọc temporary table, dùng advisory lock hoặc khóa dòng. Một câu lệnh có thể phụ thuộc session state, transaction isolation hoặc dữ liệu chưa commit trong transaction hiện tại. Vì vậy, router không nên chỉ parse từ khóa SQL để quyết định node.

### 4.2. Định tuyến ở tầng ứng dụng

Ứng dụng hiểu rõ use case hơn proxy SQL tổng quát. Có thể định nghĩa rõ datasource cho read/write hoặc đánh dấu service/repository method theo semantics.

Ví dụ cấu trúc:

```text
OrderCommandService  -> primaryDataSource
OrderQueryService    -> readDataSource
BalanceService       -> primaryDataSource
AnalyticsService     -> reportingReplica
```

Tách command và query ở tầng service giúp tránh một repository method vô tình dùng replica trong transaction cần dữ liệu mới. Cần bảo đảm transaction manager và connection được chọn trước khi transaction bắt đầu; không đổi datasource giữa một transaction đang mở.

### 4.3. Read-only transaction trong Java/Spring

`@Transactional(readOnly = true)` biểu đạt ý định chỉ đọc và có thể giúp framework/provider tối ưu một số hành vi. Tuy nhiên, annotation này không tự động bảo đảm truy vấn được route sang read replica. Việc định tuyến cần cấu hình datasource/router/transaction manager riêng và phải được kiểm tra bằng connection metadata hoặc log.

Ví dụ minh họa:

```java
@Service
public class OrderQueryService {
    @Transactional(readOnly = true, transactionManager = "readTransactionManager")
    public OrderView findOrder(long orderId) {
        return orderQueryRepository.findViewById(orderId);
    }
}

@Service
public class OrderCommandService {
    @Transactional(transactionManager = "primaryTransactionManager")
    public void confirmOrder(long orderId) {
        orderCommandRepository.confirm(orderId);
    }
}
```

Đây là cấu trúc minh họa với hai transaction manager/datasource được cấu hình riêng. Không thể chỉ thêm tên `readTransactionManager` mà ứng dụng tự có replica; cần wiring bean, pool, health check, routing policy và kiểm thử transaction propagation.

### 4.4. Transaction stickiness

Một transaction phải dùng connection và consistency context nhất quán. Nếu câu SELECT đầu đọc replica nhưng câu UPDATE sau lại dùng primary trong cùng transaction, ứng dụng có thể vi phạm transaction semantics hoặc framework không cho đổi connection.

Quy tắc an toàn phổ biến là:

- Transaction có ghi: route toàn bộ transaction tới primary.
- Transaction read-only: chọn một replica phù hợp tại lúc bắt đầu và giữ node đó trong transaction.
- Sau khi commit write: áp dụng read-your-writes policy cho các request tiếp theo.

Không chuyển node giữa các statement của một transaction chỉ vì replica khác có latency thấp hơn.

## 5. Chọn replica và cân bằng tải

Khi có nhiều replica, router cần chọn node vừa đủ mới, khỏe và còn capacity. Round-robin đơn giản có thể phân phối request đều về số lượng nhưng không cân bằng theo thời gian query hoặc tài nguyên.

### 5.1. Các chiến lược phổ biến

- **Round-robin:** phân phối lần lượt; dễ triển khai nhưng không xét lag hoặc tải.
- **Least connections:** chọn node có ít connection đang hoạt động; không phản ánh độ dài và chi phí query.
- **Weighted routing:** gán trọng số theo CPU, memory, I/O và năng lực node.
- **Latency-aware:** ưu tiên node có latency thấp và queue ngắn.
- **Lag-aware:** chỉ chọn replica có replay/apply lag dưới ngưỡng.
- **Region-aware:** chọn replica gần client để giảm network round trip, có kiểm soát consistency.

Có thể kết hợp các tiêu chí: loại bỏ replica unhealthy hoặc lag vượt ngưỡng trước, sau đó chọn trong nhóm còn lại theo load/latency. Nếu không có node đủ điều kiện, policy fallback phải rõ ràng.

### 5.2. Tránh chỉ cân bằng số connection

Một truy vấn báo cáo chạy 30 giây và một point lookup chạy 5 ms đều chiếm một connection, nhưng chi phí tài nguyên rất khác nhau. Least-connections có thể chọn sai node nếu không xét active query, CPU, I/O và queue. Cần giới hạn truy vấn dài và tách nhóm workload khi cần.

### 5.3. Health check và circuit breaker

Replica nên được loại khỏi pool đọc khi:

- Không kết nối được hoặc health check thất bại.
- Không ở trạng thái phục vụ đọc.
- Lag vượt ngưỡng của workload.
- CPU, I/O hoặc connection pool đã quá tải.
- Đang recovery, resync hoặc failover.

Router cần circuit breaker để không liên tục gửi request tới node lỗi. Khi replica trở lại, chỉ đưa vào pool sau khi kiểm tra role, replication state, lag và khả năng phục vụ. Health check quá dày cũng tạo tải; nên dùng khoảng thời gian và timeout hợp lý.

## 6. Đo replication lag đúng cách

Một con số lag đơn lẻ có thể che giấu giai đoạn bị nghẽn. Hãy đo cả khoảng cách log và tốc độ apply, đồng thời quan sát xu hướng.

### 6.1. PostgreSQL streaming replication

Trên primary, `pg_stat_replication` cung cấp trạng thái gửi log và các vị trí write/flush/replay của từng standby. Ví dụ:

```sql
SELECT application_name,
       state,
       sync_state,
       sent_lsn,
       write_lsn,
       flush_lsn,
       replay_lsn,
       write_lag,
       flush_lag,
       replay_lag
FROM pg_stat_replication;
```

Các cột lag dạng thời gian phản ánh độ trễ quan sát được gần đây theo semantics của PostgreSQL; khi hệ thống idle, giá trị có thể `NULL` hoặc không biểu thị một khoảng cách thời gian liên tục. Đối chiếu LSN, tốc độ WAL và trạng thái standby.

Trên replica:

```sql
SELECT pg_is_in_recovery() AS is_replica,
       pg_last_wal_receive_lsn() AS received_lsn,
       pg_last_wal_replay_lsn() AS replayed_lsn,
       pg_last_xact_replay_timestamp() AS last_replayed_commit;
```

`pg_last_xact_replay_timestamp()` cho biết thời điểm commit gần nhất được replay; nếu primary không có transaction mới, giá trị này càng cũ dù replica có thể đã theo kịp hoàn toàn. Không dùng riêng phép `now() - pg_last_xact_replay_timestamp()` để kết luận replica đang lag. So sánh vị trí WAL và theo dõi primary có phát sinh WAL hay không.

### 6.2. MySQL replication

Trên MySQL 8.0.22 trở lên, `SHOW REPLICA STATUS` là cú pháp hiện hành thay cho cú pháp cũ `SHOW SLAVE STATUS`:

```sql
SHOW REPLICA STATUS\G
```

Các trường cần quan sát tùy cấu hình gồm:

- `Replica_IO_Running` và `Replica_SQL_Running` hoặc trạng thái receiver/applier tương ứng.
- `Seconds_Behind_Source` như một chỉ báo thời gian ước lượng, không phải bảo đảm chính xác cho mọi tình huống.
- `Retrieved_Gtid_Set` và `Executed_Gtid_Set` khi dùng GTID.
- Error code/message của receiver và applier.
- Relay log và trạng thái worker khi dùng parallel replication.

Nếu dùng GTID, có thể so sánh tập transaction đã nhận và đã thực thi. Với read-your-writes, ứng dụng có thể lấy GTID đã commit và dùng hàm chờ như `WAIT_FOR_EXECUTED_GTID_SET()` trên replica trong timeout có giới hạn, theo đúng semantics phiên bản. Nếu timeout, fallback primary hoặc trả trạng thái phù hợp.

### 6.3. SQL Server Availability Groups

Với Always On Availability Groups, có thể xem trạng thái database replica và các queue liên quan:

```sql
SELECT DB_NAME(database_id) AS database_name,
       is_local,
       synchronization_state_desc,
       synchronization_health_desc,
       log_send_queue_size,
       log_send_rate,
       redo_queue_size,
       redo_rate
FROM sys.dm_hadr_database_replica_states;
```

`log_send_queue_size` phản ánh log đang chờ gửi; `redo_queue_size` phản ánh log đã tới secondary nhưng còn chờ redo. Đọc cùng synchronization state, health, transport và redo rate để phân biệt network/send với apply lag. Quyền xem DMV và một số cột phụ thuộc phiên bản SQL Server.

### 6.4. Oracle Data Guard

Oracle Data Guard cung cấp các view và metric để quan sát transport/apply lag, ví dụ `V$DATAGUARD_STATS`, `V$ARCHIVE_DEST_STATUS` và các view managed standby process tùy kiến trúc. Có thể truy vấn:

```sql
SELECT name, value, unit, time_computed, datum_time
FROM v$dataguard_stats
WHERE name IN ('transport lag', 'apply lag');
```

Đọc `time_computed` và `datum_time` cùng giá trị lag để biết metric có mới hay không. Tên metric và khả năng hiển thị phụ thuộc cấu hình Data Guard, role và phiên bản.

### 6.5. Cảnh báo theo xu hướng và ngưỡng nghiệp vụ

Đặt cảnh báo theo nhiều chiều:

- Lag theo thời gian vượt ngưỡng.
- Khoảng cách log position tăng liên tục.
- Tốc độ apply thấp hơn tốc độ tạo log.
- Queue gửi hoặc queue redo tăng trong nhiều cửa sổ liên tiếp.
- Replica không nhận log hoặc apply worker bị lỗi.
- Replica lag khiến read-your-writes timeout tăng.

Một spike ngắn không nhất thiết cần loại replica ngay; lag tăng liên tục hoặc không thể bắt kịp mới là dấu hiệu nguy hiểm. Ngưỡng nên khác nhau cho dashboard, tìm kiếm và truy vấn cần gần nhất quán.

## 7. Read-your-writes bằng consistency token

Khi primary commit một transaction, ứng dụng có thể nhận một token đại diện cho vị trí log đã commit. Trước khi đọc từ replica, router kiểm tra replica đã áp dụng tới token đó chưa.

### 7.1. PostgreSQL: chờ replay tới LSN

Sau khi commit trên primary, ứng dụng có thể lấy một LSN phù hợp bằng cơ chế trả token từ primary. Trên replica, so sánh với `pg_last_wal_replay_lsn()`:

```sql
SELECT pg_last_wal_replay_lsn() >= :required_lsn AS caught_up;
```

Nếu kết quả là `true`, replica đã replay tới hoặc vượt vị trí cần thiết theo thứ tự WAL. Ứng dụng có thể poll với backoff và timeout ngắn; khi hết timeout, chuyển sang primary. Cần bảo đảm token lấy từ primary đại diện cho transaction đã commit và được truyền đúng định dạng LSN.

Không dùng `pg_current_wal_lsn()` một cách tùy tiện như token của transaction nếu giữa commit và lúc lấy LSN có thêm transaction khác; token có thể cao hơn mức cần thiết, gây chờ lâu hơn. Một số driver/application có thể lấy commit LSN thông qua cơ chế riêng hoặc ghi token từ transaction theo cách được kiểm chứng.

### 7.2. MySQL: GTID wait

Với GTID replication, ứng dụng có thể lưu GTID set liên quan tới commit trên source. Replica chờ cho tới khi `Executed_Gtid_Set` bao gồm set cần thiết. `WAIT_FOR_EXECUTED_GTID_SET(gtid_set, timeout)` trả về kết quả theo định nghĩa của phiên bản; cần xử lý timeout và lỗi rõ ràng.

### 7.3. Token trong API

Token có thể được giữ trong session người dùng hoặc trả về client dưới dạng metadata. Khi client gửi request tiếp theo, ứng dụng chuyển token tới router. Token cần được ký hoặc bảo vệ nếu đi qua client không tin cậy; không cho phép client tự chỉ định vị trí log tùy ý để gây chờ hoặc truy cập ngoài phạm vi.

Nếu client đổi vùng hoặc replica, router chỉ chọn node đã đạt token. Nếu không có node phù hợp, fallback primary. Không nên yêu cầu mọi request đều chờ token nếu nghiệp vụ không cần read-your-writes; điều đó có thể biến replica thành điểm chờ mới và làm mất lợi ích latency.

## 8. Các tình huống cần đọc primary

Một số trường hợp nên được định tuyến primary theo mặc định:

- Đọc sau ghi trong cùng use case cần kết quả tức thời.
- Kiểm tra tồn kho, hạn mức, quyền hoặc trạng thái dùng để quyết định một lần ghi tiếp theo.
- Transaction có thao tác khóa như `FOR UPDATE`, `NOWAIT`, `SKIP LOCKED` theo semantics engine.
- Transaction read-modify-write hoặc nhiều statement phụ thuộc cùng snapshot/connection.
- Truy vấn dùng temporary table, session variable, advisory lock hoặc session state chỉ tồn tại ở primary.
- Truy vấn có function/procedure tạo side effect hoặc đọc dữ liệu không được sao chép theo cơ chế replica.
- DDL, migration và tác vụ quản trị cần thay đổi schema.
- Truy vấn cần dữ liệu mới nhất theo hợp đồng nghiệp vụ.

Không phải mọi `SELECT` đều read-only theo nghĩa an toàn để route. Một câu `SELECT` có thể gọi stored procedure/function, khóa dòng hoặc dựa trên session context. Hãy phân loại ở tầng use case và kiểm soát quyền read-only tại replica.

## 9. Phân trang và nhiều truy vấn trên replica

Nếu một trang cần chạy nhiều query, các query có thể bị route tới những replica có mức replay khác nhau. Kết quả có thể không nhất quán: query đầu thấy một đơn hàng, query sau chưa thấy dòng chi tiết của đơn đó.

Các biện pháp:

- Giữ toàn bộ transaction đọc trên cùng một replica.
- Dùng transaction snapshot phù hợp nếu cần cùng một góc nhìn dữ liệu.
- Chọn replica đã đạt consistency token trước khi bắt đầu transaction.
- Dùng một truy vấn/projection nhất quán thay vì nhiều query độc lập khi phù hợp.
- Route sang primary nếu nghiệp vụ yêu cầu dữ liệu mới nhất hoặc transaction có ghi.

Không đổi replica giữa các statement của một transaction. Ngay cả cùng một replica, isolation level vẫn quyết định các statement có dùng cùng snapshot hay không.

### 9.1. Keyset pagination

Keyset pagination giảm chi phí offset lớn, nhưng không tự bảo đảm consistency giữa các trang nếu mỗi trang đọc replica khác nhau hoặc replica replay tiến triển trong lúc duyệt. Cần cursor ổn định và có thể gắn consistency token hoặc giữ cùng replica/session nếu người dùng yêu cầu monotonic view.

Nếu trang tiếp theo được route tới replica có trạng thái cũ hơn, một số dòng đã thấy có thể xuất hiện lại hoặc dòng mới bị bỏ qua tùy predicate và thứ tự. Hãy thiết kế cursor có tie-breaker duy nhất và chọn policy replica phù hợp.

## 10. Ảnh hưởng của truy vấn dài trên replica

Replica đọc không hoàn toàn tách biệt khỏi hoạt động apply. Một truy vấn dài có thể cần giữ snapshot trong khi replication muốn áp dụng thay đổi xung đột với dữ liệu đang đọc.

### 10.1. PostgreSQL hot standby conflict

Trên PostgreSQL hot standby, replay WAL có thể cần thực hiện cleanup hoặc thay đổi cấu trúc mà truy vấn đang chạy trên standby vẫn cần phiên bản cũ. Tùy cấu hình `max_standby_streaming_delay`, `max_standby_archive_delay` và `hot_standby_feedback`, hệ thống có thể chờ apply hoặc hủy truy vấn để tránh lag kéo dài.

`hot_standby_feedback` có thể giảm một số query cancellation do cleanup trên primary, nhưng có thể khiến primary giữ dead tuple lâu hơn và tăng bloat. Không bật chỉ vì thấy query trên replica bị hủy; cần cân nhắc cả tác động ngược về primary.

### 10.2. Query dài và apply lag

Một truy vấn phân tích quét nhiều dữ liệu có thể dùng CPU, memory và I/O trên replica, làm apply worker chậm lại. Khi apply lag tăng, mọi truy vấn yêu cầu dữ liệu mới hơn đều bị ảnh hưởng. Có thể tách reporting replica riêng, giới hạn query runtime, giảm parallelism hoặc chuyển phân tích nặng sang kho dữ liệu chuyên dụng.

### 10.3. Snapshot và transaction dài

Transaction đọc lâu giữ snapshot cũ trên replica. Điều này có thể gây conflict với replay hoặc giữ tài nguyên lâu hơn. Tránh mở transaction trước khi gọi dịch vụ bên ngoài; giới hạn thời gian query; chia báo cáo thành batch nếu semantics cho phép; theo dõi query cancellation và lag cùng thời điểm.

## 11. Capacity planning cho read replicas

Không thể giả định thêm một replica sẽ tăng throughput đọc đúng 100%. Mỗi replica có giới hạn CPU, memory, I/O, network và apply throughput. Router, connection pool và workload skew cũng ảnh hưởng.

### 11.1. Ước lượng tải đọc

Phân loại query theo tài nguyên:

- Point lookup và truy vấn ngắn: nhạy với latency và connection overhead.
- Range scan: dùng IOPS và throughput theo kích thước dữ liệu.
- Join/aggregate: dùng CPU, memory và temp I/O.
- Báo cáo dài: giữ snapshot và có thể cạnh tranh apply.
- Export: dùng network và sequential read lớn.

Đo số lần gọi, concurrency, p95/p99, CPU time, logical/physical reads và rows returned theo nhóm. Không chỉ lấy tổng QPS vì một báo cáo lớn có thể tiêu tốn tài nguyên tương đương hàng nghìn point lookup.

### 11.2. Ước lượng số replica

Một phép sizing sơ bộ có thể chia read workload theo năng lực bền vững của từng replica, nhưng cần thêm headroom cho apply và burst. Ví dụ nếu tải đọc cần 1.200 đơn vị công việc/giây và một replica giữ SLO ở mức 500 đơn vị/giây khi đồng thời apply log, tối thiểu ba replica là phép chia lý thuyết. Thực tế cần thử tải phân phối, vì request không đồng đều và router có thể tạo hot node.

Đừng chạy replica ở sát điểm bão hòa. Dành headroom để hấp thụ failover một replica, query dài và biến động replication. Nếu mất một replica khiến các node còn lại vượt SLO, số replica bình thường chưa đủ cho yêu cầu availability.

### 11.3. Replica chuyên dụng theo workload

Có thể tách:

- Replica API cho truy vấn ngắn và latency thấp.
- Replica báo cáo cho scan, aggregate và query dài.
- Replica vùng địa lý cho người dùng ở xa primary.
- Replica phục vụ backup hoặc export nếu công cụ và topology hỗ trợ.

Tách workload giúp một báo cáo không làm p99 của API tăng trên cùng node. Đổi lại, mỗi replica cần capacity, monitoring, patching, backup policy và routing riêng.

### 11.4. Tác động lên primary

Thêm replica có thể làm primary tăng CPU/network do gửi log, quản lý replication connection và giữ WAL/binlog cần thiết. Với một số cơ chế, replica chậm hoặc replication slot có thể khiến primary giữ log lâu, làm storage tăng. Theo dõi send queue, retained WAL/binlog và free space trên primary.

## 12. Failover và quản lý vai trò replica

Replica phục vụ đọc có thể được promote thành primary khi sự cố, nhưng chỉ khi được cấu hình và vận hành như một ứng viên failover. Không phải read replica nào cũng đủ mới hoặc đủ năng lực để nhận toàn bộ workload ghi.

### 12.1. Promote và fencing

Failover phải ngăn primary cũ tiếp tục nhận ghi sau khi node mới được promote. Nếu hai node cùng nhận ghi, có thể xảy ra split-brain và dữ liệu phân nhánh. Cần cơ chế quorum/leader election, fencing hoặc quản lý endpoint để bảo đảm chỉ một primary có quyền ghi.

### 12.2. Đánh giá replica đủ điều kiện

Trước khi promote, cần xem:

- Replica đã nhận và apply log tới đâu.
- Có transaction đã xác nhận trên primary nhưng chưa có trên replica không.
- Replica có đang phục vụ query dài hoặc lag không.
- Storage, CPU, memory và connection có đủ cho workload ghi + đọc không.
- Có cần reconfigure downstream replica và CDC sau promote không.

Trong asynchronous replication, failover có thể mất các transaction chưa được replica nhận/apply. RPO phải phản ánh điều đó. Synchronous replication có thể giảm RPO nhưng tăng latency/availability trade-off.

### 12.3. Sau failover

Sau promote, router phải cập nhật role và connection pool, ngừng gửi ghi tới primary cũ, xác minh replication topology mới và theo dõi backlog. Khi node cũ trở lại, không tự động đưa nó vào read pool trước khi resync hoặc rejoin đúng cách.

## 13. Bảo mật và bảo vệ tính read-only

Replica phục vụ đọc vẫn chứa dữ liệu nhạy cảm tương đương primary. Cần áp dụng authentication, authorization, encryption in transit/at rest, audit và network segmentation tương ứng.

Các biện pháp:

- Dùng database account read-only cho ứng dụng đọc replica.
- Không cấp quyền DDL/DML không cần thiết.
- Giới hạn network access theo service và môi trường.
- Bảo vệ consistency token và metadata routing nếu gửi qua client.
- Kiểm tra dữ liệu nhạy cảm trong log/trace và query parameter.
- Áp dụng chính sách retention và backup cho replica theo vai trò.

Quyền read-only ở database là lớp bảo vệ quan trọng. Nếu router phân loại nhầm một truy vấn ghi hoặc function có side effect, database phải từ chối thay vì cho phép dữ liệu bị thay đổi ngoài primary.

## 14. Quy trình triển khai read routing

1. **Đo workload:** xác định tỷ lệ đọc/ghi, query mix, concurrency, p95/p99 và các query nặng.
2. **Xác định consistency requirement:** read-your-writes, monotonic reads, bounded staleness hoặc strong read.
3. **Chọn cơ chế replication:** physical/logical hoặc tính năng HA phù hợp, đồng bộ/bất đồng bộ theo RPO và latency.
4. **Provision replica:** cấu hình CPU, memory, storage, network và quyền read-only.
5. **Đo apply capacity:** kiểm tra tốc độ log generation so với transport/replay.
6. **Thiết kế routing policy:** phân loại use case, transaction và fallback.
7. **Cấu hình connection pool:** tách pool primary/replica, giới hạn connection và health check.
8. **Kiểm thử dữ liệu trễ:** cố ý tạo lag, xác nhận hành vi API và read-your-writes.
9. **Kiểm thử lỗi:** replica down, lag vượt ngưỡng, failover và reconnect.
10. **Canary routing:** chuyển một tỷ lệ nhỏ truy vấn phù hợp sang replica, quan sát trước khi mở rộng.
11. **Benchmark hỗn hợp:** đo primary, replica, apply lag, query latency và network cùng lúc.
12. **Vận hành liên tục:** cảnh báo lag, queue, replica health, retained log và capacity.

### 14.1. Bảng quyết định routing mẫu

| Use case | Routing | Consistency policy |
|---|---|---|
| Tạo đơn và trả kết quả | Primary | Đọc sau ghi trên primary |
| Xem ngay đơn vừa tạo | Primary hoặc chờ token trên replica | Read-your-writes |
| Danh sách đơn thông thường | Read replica | Bounded staleness nếu nghiệp vụ cho phép |
| Dashboard doanh thu | Reporting replica | Eventual consistency, hiển thị `data_as_of` |
| Kiểm tra tồn kho trước khi trừ | Primary | Strong read trong transaction ghi |
| Báo cáo lịch sử dài | Replica chuyên dụng | Snapshot và giới hạn runtime |
| `SELECT FOR UPDATE` | Primary | Locking semantics |
| Truy vấn sau failover | Node được xác nhận role và health | Tuân thủ consistency/fencing policy |

## 15. Ví dụ xử lý read-after-write trong Java

Một API cập nhật địa chỉ giao hàng rồi trả thông tin đơn hàng. Nếu query đọc được route sang replica, response có thể chứa địa chỉ cũ. Cách đơn giản là thực hiện cả write và read trong cùng transaction trên primary:

```java
@Transactional(transactionManager = "primaryTransactionManager")
public OrderView updateShippingAddress(long orderId, Address address) {
    orderCommandRepository.updateAddress(orderId, address);
    return orderQueryRepository.findViewById(orderId);
}
```

Nếu kiến trúc cần đọc từ replica sau commit, có thể trả consistency token và chờ replica đạt token trước khi đọc. Pseudocode:

```java
CommitToken token = primaryWriter.updateAndCommit(orderId, address);

Replica replica = replicaRouter.chooseReplicaAtLeast(token);
if (replica == null) {
    return primaryReader.findViewById(orderId);
}

return replicaReader.findViewById(replica, orderId);
```

`CommitToken` và `chooseReplicaAtLeast` là abstraction của ứng dụng, không phải API chuẩn chung của JDBC hoặc Spring. Cách lấy token, kiểm tra replay và quản lý timeout phải được triển khai theo database engine. Nếu không thể xác nhận replica đã theo kịp, fallback primary là cách giữ semantics rõ ràng.

Không chỉ dùng `ThreadLocal` để ghi nhớ “request vừa ghi” nếu ứng dụng có async execution, reactive pipeline hoặc nhiều thread. Context consistency phải được truyền theo request/transaction một cách an toàn và được xóa đúng vòng đời.

## 16. Những sai lầm thường gặp

- **Chuyển mọi SELECT sang replica:** bỏ qua locking read, function có side effect, session state và read-after-write.
- **Cho rằng replica luôn mới:** asynchronous replication có lag ngay cả khi bình thường.
- **Chỉ theo dõi `Seconds_Behind_Source` hoặc timestamp replay:** metric có thể không phản ánh đầy đủ khoảng cách log/apply.
- **Cân bằng round-robin mà không xét lag:** client có thể luân phiên đọc trạng thái mới và cũ.
- **Đổi replica giữa transaction:** làm mất consistency context hoặc vi phạm transaction semantics.
- **Dùng `@Transactional(readOnly=true)` và nghĩ routing tự động:** annotation không tự cấu hình datasource replica.
- **Dùng replica cho kiểm tra trước khi ghi:** có thể quyết định dựa trên dữ liệu cũ và tạo race condition.
- **Để báo cáo dài chạy chung replica API:** query nặng có thể làm apply lag và p99 tăng.
- **Tăng số replica mà không đo primary:** primary vẫn chịu chi phí gửi log và giữ WAL/binlog.
- **Không đặt timeout cho consistency wait:** request có thể giữ connection vô hạn khi replica lag.
- **Không có fallback rõ ràng:** khi replica down, request đọc có thể lỗi hàng loạt hoặc dồn hết về primary ngoài dự kiến.
- **Không kiểm thử failover/fencing:** có nguy cơ split-brain hoặc mất transaction chưa được sao chép.
- **Cấp quyền ghi cho read application:** routing nhầm có thể làm thay đổi dữ liệu trên node không đúng vai trò.

## 17. Checklist thiết kế và vận hành read replica

- [ ] Đã xác định query mix, tỷ lệ đọc/ghi và mục tiêu mở rộng.
- [ ] Đã xác định truy vấn nào cần primary, replica API và reporting replica.
- [ ] Đã ghi rõ read-your-writes, monotonic reads, bounded staleness và strong-read requirements.
- [ ] Đã hiểu điều kiện commit của synchronous/asynchronous/semi-synchronous replication.
- [ ] Đã đo send, receive/flush và apply/replay lag riêng biệt.
- [ ] Đã có metric lag theo log position/GTID/SCN cùng thời gian và xu hướng.
- [ ] Đã thiết kế router chọn replica theo health, lag, load và vùng địa lý.
- [ ] Đã giữ một transaction trên cùng node và không đổi datasource giữa transaction.
- [ ] Đã có timeout và fallback primary khi consistency token chưa đạt.
- [ ] Đã giới hạn query dài, theo dõi hot standby conflict và apply lag.
- [ ] Đã định cỡ CPU, memory, I/O, network và connection cho từng replica.
- [ ] Đã tính tác động replica tới primary, retained log và replication bandwidth.
- [ ] Đã dùng account read-only và kiểm soát quyền trên replica.
- [ ] Đã kiểm thử lag, replica down, failover, fencing và resync.
- [ ] Đã benchmark workload hỗn hợp và xác nhận SLO trước/sau routing.
- [ ] Đã có dashboard/cảnh báo cho lag, queue, apply rate, error và capacity.

Read replica giúp mở rộng năng lực đọc bằng cách phân phối truy vấn sang các node nhận bản sao dữ liệu từ primary. Lợi ích chỉ đạt được khi truy vấn được phân luồng theo ngữ nghĩa, replica có đủ năng lực apply log và ứng dụng xử lý rõ mức dữ liệu cũ có thể chấp nhận. Đo riêng transport/apply lag, dùng consistency token cho read-your-writes khi cần, giữ transaction trên một node và có fallback/failover được kiểm thử sẽ giúp tăng tải đọc mà vẫn bảo vệ tính đúng đắn của ứng dụng.
