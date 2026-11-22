# Sao chép bất đồng bộ và đồng bộ trong PostgreSQL

PostgreSQL có thể duy trì một hoặc nhiều standby servers bằng cách truyền Write-Ahead Log (WAL) từ primary. Standby nhận WAL, ghi WAL vào storage và replay các records để tái tạo trạng thái dữ liệu. Cơ chế này được gọi là physical streaming replication khi standby nhận luồng WAL vật lý của cluster.

Điểm khác biệt quan trọng giữa **sao chép bất đồng bộ (asynchronous replication)** và **sao chép đồng bộ (synchronous replication)** nằm ở thời điểm primary xác nhận một transaction đã COMMIT cho client. Với async replication, primary không đợi standby xác nhận WAL trước khi trả kết quả commit. Với synchronous replication, primary có thể phải đợi một hoặc nhiều standby đạt đến mức xác nhận WAL được cấu hình.

Sự khác biệt đó ảnh hưởng trực tiếp đến độ trễ ghi, khả năng tiếp tục phục vụ khi standby mất kết nối và lượng dữ liệu có thể mất khi failover. Async thường tối ưu latency và khả năng ghi liên tục; synchronous có thể cung cấp bảo đảm mạnh hơn cho các transaction đã được standby xác nhận, đổi lại commit có thể bị chậm hoặc chờ khi không còn đủ synchronous standbys.

Bài học thuộc chương **Sao chép vật lý** của module *Database Engine Relational PostgreSQL*. Chúng ta sẽ tìm hiểu đường đi của WAL, các mức xác nhận `synchronous_commit`, cách chọn standby bằng `synchronous_standby_names`, cấu hình primary/standby, monitoring, failover và cách thiết kế RPO/RTO phù hợp.

> **Nguyên tắc:** “Synchronous” mô tả việc primary chờ acknowledgement từ standby trước khi xác nhận commit. Nó không tự tạo failover, không thay thế backup và không bảo đảm an toàn trước mọi dạng mất đồng thời của primary, standby, storage hoặc network.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Mô tả kiến trúc primary/standby của physical streaming replication.
2. Giải thích WAL được gửi, ghi và replay như thế nào.
3. Phân biệt asynchronous và synchronous replication.
4. Hiểu primary commit response trong từng chế độ.
5. Phân biệt `synchronous_commit = off`, `local`, `remote_write`, `on` và `remote_apply`.
6. Giải thích vai trò của `synchronous_standby_names`.
7. Phân biệt priority-based `FIRST` và quorum-based `ANY`.
8. Cấu hình `application_name` để nhận diện synchronous standby.
9. Tạo physical replication role, pg_hba rule và base backup.
10. Cấu hình replication slot và hiểu WAL retention.
11. Theo dõi primary bằng `pg_stat_replication`.
12. Theo dõi standby bằng `pg_stat_wal_receiver` và replay functions.
13. Nhận biết transaction đang chờ `SyncRep`.
14. Hiểu latency, throughput, availability và RPO trade-offs.
15. Phân biệt received, written, flushed và replayed LSN.
16. Xử lý synchronous standby bị mất kết nối.
17. Hiểu giới hạn của cascading replication và quorum.
18. Thiết kế failover an toàn, tránh split brain và promote sai node.
19. Kiểm tra read-after-write khi dùng `remote_apply`.
20. Xây dựng runbook, lab và checklist vận hành replication.

## 2. Kiến trúc physical streaming replication

PostgreSQL dùng WAL để ghi lại các thay đổi cần thiết nhằm phục hồi database sau crash. Trong physical replication, primary truyền WAL records đến standby. Standby ghi các records vào WAL files rồi replay chúng lên data files của cluster.

```text
                 Applications
                       |
                       v
                +-------------+
                |   Primary   |
                | transactions|
                +-------------+
                       |
                 WAL generation
                       |
                WAL sender process
                       |
              Streaming replication
                       |
             +---------+----------+
             |                    |
             v                    v
      +-------------+      +-------------+
      | Standby A   |      | Standby B   |
      | WAL receiver|      | WAL receiver|
      +-------------+      +-------------+
             |                    |
        WAL write/flush      WAL write/flush
             |                    |
          Replay                 Replay
             |                    |
       Read-only queries    Read-only queries
```

### 2.1. Primary

Primary nhận các thao tác ghi, tạo WAL records và quản lý replication connections. WAL sender processes gửi WAL tới các standbys trực tiếp kết nối.

### 2.2. Standby

Standby ở chế độ recovery, nhận WAL qua WAL receiver, ghi WAL vào storage và replay records. Với `hot_standby = on`, client có thể kết nối để chạy read-only queries trong khi standby tiếp tục replay.

### 2.3. WAL sender và WAL receiver

- WAL sender chạy ở primary, gửi WAL.
- WAL receiver chạy ở standby, nhận WAL.
- Startup/receiver/replay processes phối hợp để duy trì recovery state.

### 2.4. Physical replication sao chép cấp cluster

Physical standby tái tạo trạng thái vật lý của cluster, bao gồm các databases trong cluster. Nó không phải một subscription riêng cho từng table như logical replication.

### 2.5. Cùng major version

Physical streaming replication thường yêu cầu primary và standby tương thích ở cùng PostgreSQL major version và cùng định dạng vật lý. Đây không phải phương pháp thông thường để replicate trực tiếp giữa hai major versions khác nhau; dùng logical replication hoặc quy trình major upgrade phù hợp.

## 3. WAL đi qua những giai đoạn nào?

Để hiểu synchronous replication, cần phân biệt các mốc WAL:

1. **Generated:** primary tạo WAL records cho transaction.
2. **Sent:** WAL sender gửi records qua connection.
3. **Received:** standby nhận records.
4. **Written:** standby ghi WAL vào operating system.
5. **Flushed:** standby flush WAL xuống storage theo durability semantics của hệ thống.
6. **Replayed:** standby apply WAL records vào data files và tiến recovery position.

Các LSN như `sent_lsn`, `write_lsn`, `flush_lsn` và `replay_lsn` phản ánh những vị trí khác nhau.

### 3.1. LSN

Log Sequence Number (LSN) là vị trí trong WAL stream. Có thể so sánh LSN để xem standby đang theo kịp đến đâu.

Ví dụ trên primary:

```sql
SELECT pg_current_wal_lsn() AS primary_current_lsn;
```

Trên standby:

```sql
SELECT
    pg_last_wal_receive_lsn() AS received_lsn,
    pg_last_wal_replay_lsn() AS replayed_lsn;
```

### 3.2. Received không có nghĩa durable

Standby có thể đã nhận bytes qua network nhưng chưa ghi chúng xuống storage. Nếu standby crash ở thời điểm đó, những bytes chỉ nằm trong memory/network buffers có thể mất.

### 3.3. Written không nhất thiết flushed

WAL đã được ghi qua OS write nhưng có thể vẫn nằm trong page cache hoặc storage cache chưa được flush theo durability request.

### 3.4. Flushed không có nghĩa replay xong

WAL có thể đã durable trên standby nhưng recovery process chưa apply records. Read-only query trên standby có thể chưa nhìn thấy transaction đó.

### 3.5. Replay không đồng nghĩa mọi client snapshot thấy dữ liệu ngay

Ngay cả khi WAL đã replay, một transaction đọc đang dùng snapshot cũ có thể chưa thấy thay đổi. `remote_apply` bảo đảm standby đã replay tới commit record trước khi primary trả commit, nhưng ứng dụng vẫn cần tạo snapshot đọc phù hợp.

## 4. Asynchronous replication

Trong chế độ bất đồng bộ, primary không đợi standby xác nhận WAL trước khi hoàn tất commit cho client.

Luồng khái quát:

```text
Client             Primary               Standby
  |                   |                     |
  |--- COMMIT ------->|                     |
  |                   |-- write/flush WAL   |
  |<-- COMMIT OK -----|                     |
  |                   |---- send WAL ------>|
  |                   |                     |-- write/flush
  |                   |                     |-- replay
  |                   |                     |
```

### 4.1. Ưu điểm

- Commit latency không phải chờ network round trip tới standby.
- Primary có thể tiếp tục ghi khi standby chậm hoặc tạm mất kết nối.
- Phù hợp hệ thống ưu tiên write availability và chấp nhận một cửa sổ data loss khi failover.
- Nhiều standby có thể nhận WAL độc lập mà không làm commit chờ tất cả.

### 4.2. Nhược điểm

- Standby có thể lag sau primary.
- Primary có thể báo commit thành công trong khi standby chưa nhận hoặc chưa flush WAL đó.
- Nếu primary mất đột ngột và promote một standby chưa bắt kịp, các transaction đã được client xác nhận có thể không có trên node mới.
- Read-after-write qua standby có thể trả dữ liệu cũ.

### 4.3. Async không có nghĩa WAL không được flush trên primary

Với `synchronous_commit = on` và không cấu hình synchronous standby, primary vẫn chờ local WAL flush trước khi trả commit. Điều không xảy ra là chờ acknowledgement từ standby.

### 4.4. Async vẫn có thể có replication slot

Replication slot có thể giữ WAL để standby chưa theo kịp vẫn có thể nhận phần WAL cần thiết. Slot bảo vệ WAL retention; nó không biến async replication thành synchronous và không bảo đảm commit đã đến standby.

### 4.5. RPO của async

RPO phụ thuộc lượng WAL standby chưa nhận/flush tại thời điểm failover và standby nào được promote. Lag nhỏ không phải bảo đảm zero data loss. Nếu business cần RPO gần 0, cần đánh giá synchronous replication hoặc một cơ chế durability khác.

## 5. Synchronous replication

Trong synchronous replication, primary chờ acknowledgement từ số lượng standby được cấu hình trước khi trả commit thành công cho client, nếu transaction sử dụng synchronous commit level yêu cầu remote acknowledgement.

Luồng khái quát:

```text
Client             Primary               Sync Standby
  |                   |                       |
  |--- COMMIT ------->|                       |
  |                   |-- write/flush WAL     |
  |                   |---- send WAL -------->|
  |                   |                       |-- receive
  |                   |                       |-- write/flush
  |                   |<--- acknowledgement --|
  |<-- COMMIT OK -----|                       |
```

### 5.1. Điều kiện để synchronous replication hoạt động

Cần phối hợp:
- Primary có `synchronous_standby_names` xác định standby đủ điều kiện.
- Standby kết nối streaming và có `application_name` khớp tên được cấu hình.
- Transaction dùng `synchronous_commit` ở mức yêu cầu remote acknowledgement.
- Standby đạt tới acknowledgement level tương ứng.

### 5.2. Synchronous không phải chờ mọi standby

Có thể yêu cầu primary chờ một standby hoặc một quorum gồm nhiều standbys. Số lượng và cách chọn được cấu hình bằng `FIRST` hoặc `ANY`.

### 5.3. Synchronous commit ảnh hưởng thời điểm trả kết quả

Transaction có thể đã thực hiện thay đổi trên primary nhưng client chưa nhận được COMMIT response vì primary đang đợi standby. Nếu standby không đáp ứng, backend có thể chờ.

### 5.4. Synchronous replication không tự failover

PostgreSQL streaming replication không tự chọn/promote standby chỉ vì primary mất. Cần quy trình vận hành hoặc HA manager để phát hiện failure, fence primary cũ và promote đúng standby.

### 5.5. Synchronous không bảo vệ mọi transaction nếu session override

Một transaction có thể đặt `synchronous_commit = local` hoặc `off`, bỏ qua remote wait. Kiểm soát role/database/session settings và ứng dụng để không vô tình làm suy yếu durability policy.

## 6. So sánh asynchronous và synchronous

| Tiêu chí | Asynchronous | Synchronous |
|---|---|---|
| Primary chờ standby trước COMMIT response | Không | Có, theo commit level và quorum |
| Commit latency | Thấp hơn | Có thể tăng theo network/storage/replay |
| Primary tiếp tục ghi khi standby mất kết nối | Thường có | Có thể block nếu thiếu quorum |
| Data loss khi promote standby | Có thể mất WAL chưa đến standby | Có thể tránh mất transaction đã được standby xác nhận nếu promote đúng node và dùng durability level phù hợp |
| Read-after-write trên standby | Có thể lag | `remote_apply` có thể bảo đảm replay trước response |
| Cấu hình sync standby names | Không bắt buộc | Cần |
| Khả năng chịu lỗi | Tập trung availability | Đổi availability lấy durability/consistency cao hơn |
| Phù hợp | Read replicas, DR với RPO khác 0 | Workloads yêu cầu durability mạnh hơn |

### 6.1. Không có chế độ tốt nhất cho mọi workload

Chọn theo yêu cầu:
- RPO.
- RTO.
- Write latency budget.
- Network RTT.
- Storage flush latency.
- Số lượng standby và failure domains.
- Khả năng vận hành failover.
- Khả năng chấp nhận write outage.

### 6.2. Có thể kết hợp sync và async standbys

Một primary có thể có synchronous standby candidates và các async replicas khác. Synchronous quorum chỉ áp dụng cho các standbys được chọn theo `synchronous_standby_names`.

### 6.3. Đừng chỉ nhìn số lượng replicas

Ba standbys cùng nằm trên một host/storage failure domain có thể không tăng durability như ba replicas ở các failure domains độc lập. Placement quan trọng không kém số lượng.

## 7. `synchronous_commit` điều khiển điều gì?

`synchronous_commit` là setting quyết định primary chờ đến mức nào trước khi xác nhận transaction commit. Nó có thể đặt ở system, database, role, session hoặc transaction scope theo cơ chế PostgreSQL.

Các giá trị thường dùng:

| Giá trị | Primary chờ local WAL flush? | Chờ synchronous standby? | Mốc remote |
|---|---|---|---|
| `off` | Không bắt buộc trước response | Không | Không chờ |
| `local` | Có | Không | Chỉ local flush |
| `remote_write` | Có | Có | Standby đã write WAL tới OS |
| `on` | Có | Có | Standby đã flush WAL |
| `remote_apply` | Có | Có | Standby đã replay WAL |

### 7.1. off

Transaction có thể được báo commit trước khi WAL record được flush local. Nếu primary OS crash, một số transaction vừa được báo thành công có thể mất. PostgreSQL vẫn giữ database consistency nhờ WAL recovery; rủi ro là mất các commit gần nhất theo durability window, không phải server cố ý bỏ qua mọi consistency rules.

### 7.2. local

Primary chờ local WAL flush nhưng không đợi standby. Đây là lựa chọn khi muốn local durability nhưng bỏ remote synchronous wait.

### 7.3. remote_write

Primary chờ synchronous standby ghi WAL tới operating system. Nó có thể có latency thấp hơn `on`, nhưng WAL trên standby chưa chắc đã được flush tới durable storage. Standby OS crash hoặc power loss có thể làm mất phần WAL mới ghi chưa flush.

### 7.4. on

Giá trị mặc định. Primary chờ local WAL flush và synchronous standby flush WAL tới durable storage theo semantics của standby/storage stack.

### 7.5. remote_apply

Primary chờ synchronous standby replay WAL records. Nó bao gồm yêu cầu WAL đã được nhận và xử lý tới commit record. Giá trị này hữu ích khi ứng dụng cần đọc trên standby sau khi primary trả commit, nhưng có thể tăng latency do replay queue và standby query conflicts.

### 7.6. Không có synchronous standby

Nếu không có synchronous standby được cấu hình/chọn, các mức remote không thể chờ một standby thực tế; local WAL durability vẫn phụ thuộc setting. Vì vậy `synchronous_commit = on` một mình không bật synchronous replication. Phải có `synchronous_standby_names` và standby phù hợp.

### 7.7. Set cho một transaction

```sql
BEGIN;
SET LOCAL synchronous_commit = 'remote_apply';

UPDATE app.orders
SET status = 'PAID'
WHERE order_id = 1001;

COMMIT;
```

`SET LOCAL` chỉ có hiệu lực trong transaction hiện tại. Chọn đúng policy trước khi chạy transaction.

### 7.8. Set theo role hoặc database

```sql
ALTER ROLE app_runtime
SET synchronous_commit = 'on';

ALTER DATABASE app_db
SET synchronous_commit = 'on';
```

Kiểm tra effective setting trong application connection:

```sql
SHOW synchronous_commit;
```

### 7.9. Một số workload có thể chọn mức khác nhau

Ví dụ, transaction tài chính có thể cần remote flush, trong khi job có thể tái tạo được có thể chấp nhận local-only durability. Thiết kế policy theo business semantics và audit các overrides; không để ứng dụng tự hạ durability một cách không kiểm soát.

## 8. `synchronous_standby_names`

Setting này nằm trên primary và xác định các standbys đủ điều kiện tham gia synchronous replication.

Ví dụ:

```conf
synchronous_standby_names = 'FIRST 1 (standby_a, standby_b)'
```

Primary ưu tiên standby_a. Nếu standby_a không khả dụng, standby_b có thể được chọn làm synchronous standby theo cơ chế priority.

### 8.1. application_name phải khớp

Trên standby, `primary_conninfo` có thể khai báo:

```conf
primary_conninfo = 'host=primary.example.internal port=5432 user=replicator application_name=standby_a sslmode=verify-full'
```

Tên `standby_a` cần khớp với tên trong `synchronous_standby_names`.

### 8.2. Standby phải kết nối trực tiếp và ở trạng thái phù hợp

Primary lựa chọn trong các replication connections trực tiếp đáp ứng điều kiện. Một replica downstream trong cascading chain không xuất hiện như một connection trực tiếp tới primary gốc.

### 8.3. Không nhầm application_name với hostname

`application_name` là nhãn client gửi trong connection startup options. Nó có thể khác hostname, server name hoặc slot name.

### 8.4. Có thể đổi danh sách khi runtime

Thay đổi cấu hình cần reload theo tham số context. Kiểm tra `pg_settings`/`pg_file_settings` và trạng thái `pg_stat_replication` sau reload. Đừng coi file config đã sửa là setting đã có hiệu lực.

## 9. Priority-based selection với FIRST

Cú pháp:

```conf
synchronous_standby_names = 'FIRST 1 (standby_a, standby_b, standby_c)'
```

### 9.1. FIRST 1

Primary chọn standby đủ điều kiện có priority cao nhất trong danh sách. Khi standby ưu tiên cao hơn không khả dụng, standby kế tiếp có thể được chọn.

### 9.2. FIRST 2

```conf
synchronous_standby_names = 'FIRST 2 (standby_a, standby_b, standby_c)'
```

Primary yêu cầu hai standbys có priority cao nhất trong số các standbys đủ điều kiện. Đây là priority-based synchronous replication với nhiều acknowledgements.

### 9.3. Potential synchronous standby

Một standby có thể là candidate/potential nhưng chưa được chọn làm synchronous standby hiện tại. Xem `sync_state` và `sync_priority` trong `pg_stat_replication`.

### 9.4. Ưu điểm

- Dễ xác định standby ưu tiên.
- Có thể ưu tiên replica trong cùng region hoặc storage class.
- Có thể dùng standby thứ hai làm fallback.

### 9.5. Trade-off

Nếu standby ưu tiên cao nhất chậm, nó có thể nằm trên đường commit và làm tăng latency. Cần lựa chọn priority theo topology, latency và failure domain.

## 10. Quorum-based selection với ANY

Cú pháp:

```conf
synchronous_standby_names = 'ANY 2 (standby_a, standby_b, standby_c)'
```

Primary đợi bất kỳ hai standbys trong danh sách xác nhận theo commit level.

### 10.1. ANY 1

```conf
synchronous_standby_names = 'ANY 1 (standby_a, standby_b, standby_c)'
```

Một standby bất kỳ trong danh sách có thể đáp ứng acknowledgement. Cấu hình này cho phép chọn node nhanh/available theo runtime state.

### 10.2. ANY 2

Với ba candidates, primary cần acknowledgement từ hai node. Nếu một node mất kết nối, hai node còn lại vẫn có thể đáp ứng quorum. Nếu chỉ còn một node, các commits yêu cầu synchronous acknowledgement sẽ chờ.

### 10.3. Quorum không có nghĩa mọi node đều đồng bộ

Nếu ANY 2 trong ba nodes, node thứ ba có thể lag và không nằm trong acknowledgement set của transaction đó. Khi failover, cần biết node nào thực sự đã nhận/flush WAL của các commits quan trọng.

### 10.4. Chọn quorum theo failure domains

Nếu cần chịu được một node failure mà vẫn tiếp tục commit, số candidates và quorum phải phù hợp. Tuy nhiên, hai replicas cùng một failure domain có thể mất đồng thời; đặt nodes ở failure domains độc lập.

### 10.5. FIRST và ANY không thể hoán đổi tùy tiện

FIRST chọn theo priority order; ANY chọn theo quorum. Hãy chọn theo yêu cầu về latency, node preference và khả năng chịu lỗi.

## 11. Primary xác nhận synchronous commit ở mốc nào?

Các mức remote có thể được hiểu qua WAL positions:

```text
Primary WAL
    |
    | send
    v
Standby receive buffer
    |
    | write
    v
Operating-system write cache
    |
    | flush
    v
Standby durable WAL
    |
    | replay
    v
Standby data files / recovery state
```

- `remote_write`: đợi tới bước write.
- `on`: đợi tới bước flush.
- `remote_apply`: đợi tới bước replay.

### 11.1. Storage semantics vẫn quan trọng

Flush request chỉ đáng tin trong phạm vi operating system, controller, device firmware và storage service thực sự tuân thủ durability semantics. Hardware có write cache không được bảo vệ hoặc cloud storage misconfiguration có thể làm yếu giả định durability.

### 11.2. Remote flush và local flush

Với `on`, primary cũng phải bảo đảm local WAL flush. Standby acknowledgement không thay local WAL durability.

### 11.3. Remote apply cho read-after-write

Nếu transaction commit trả về sau khi standby replay xong, một transaction đọc mới trên standby đó có thể nhìn thấy commit, subject to snapshot semantics và routing đúng standby đã xác nhận.

### 11.4. Commit acknowledgement không phải application-level validation

Synchronous replication xác nhận WAL progress. Nó không kiểm tra business constraints ngoài những gì transaction đã thực hiện, không xác nhận external side effects và không thay thế application-level idempotency.

## 12. Latency và throughput

Synchronous replication thêm acknowledgement dependency vào commit path. Latency chịu ảnh hưởng bởi:
- Network round-trip giữa primary và standby.
- Standby write/flush latency.
- Standby replay speed nếu dùng remote_apply.
- Quorum size và node placement.
- Queueing, WAL volume và concurrent commits.
- Storage jitter, network congestion và failover events.

### 12.1. Một ví dụ latency

Giả sử local commit cần 2 ms, network round trip tới standby là 12 ms, standby flush cần 4 ms. Synchronous commit có thể cần ít nhất thời gian chờ remote acknowledgement cộng processing overhead; không thể chỉ lấy 2 ms local làm latency kỳ vọng.

Đây là ví dụ minh họa, không phải benchmark hay công thức cộng latency tuyệt đối vì pipeline, batching và concurrency ảnh hưởng kết quả.

### 12.2. remote_write có thể giảm wait time

Remote write acknowledgement có thể nhanh hơn remote flush trên một số storage stacks. Nhưng đổi lại durability trên standby yếu hơn trước OS/power failure.

### 12.3. remote_apply thường có thêm replay delay

Nếu standby replay chậm do CPU, I/O hoặc conflict với read queries, primary commit có thể chờ lâu hơn. Chỉ dùng khi read visibility requirement có giá trị rõ ràng.

### 12.4. Group commit

PostgreSQL có thể gom WAL flush cho nhiều concurrent transactions. Synchronous replication vẫn cần acknowledgements theo policy nhưng không nhất thiết mỗi transaction tạo một network flush độc lập. Đo bằng workload thực tế thay vì suy ra từ một transaction đơn lẻ.

### 12.5. Connection pool và long transactions

Synchronous replication ảnh hưởng commit response của write transactions. Connection pools có thể giữ connections lâu hơn khi standby chậm; kiểm soát pool size, timeouts và backpressure.

## 13. Availability và commit blocking

Synchronous replication đổi một phần write availability lấy remote acknowledgement.

### 13.1. Không còn đủ synchronous standbys

Nếu `FIRST 1` không có candidate khả dụng hoặc `ANY 2` chỉ còn một node, các transactions cần synchronous acknowledgement có thể chờ vô thời hạn cho tới khi tình trạng thay đổi hoặc operator can thiệp.

### 13.2. Đây là behavior có chủ ý

Primary không thể vừa bảo đảm transaction được xác nhận trên quorum vừa tự bỏ qua quorum khi nó không có phản hồi. Nếu tự tiếp tục commit, durability contract sẽ thay đổi.

### 13.3. Cần quy trình degradation

Runbook phải xác định:
- Chờ standby quay lại.
- Khôi phục network/storage.
- Chọn standby khác.
- Giảm quorum theo quyết định được phê duyệt.
- Chuyển transaction cụ thể sang local-only khi business cho phép.

### 13.4. Không tự động đổi sang async mà không thông báo

Bỏ synchronous requirement có thể làm các commits sau đó không còn được standby xác nhận trước khi client nhận response. Đây là thay đổi RPO và cần được ghi nhận.

### 13.5. Read-only workload vẫn có thể hoạt động

Synchronous commit wait chủ yếu ảnh hưởng transactions có commit WAL cần acknowledgement. Read queries trên primary/standby có thể tiếp tục nếu các servers và routing còn hoạt động; nhưng DDL/writes phụ thuộc transaction behavior.

## 14. RPO, RTO và data loss

**RPO (Recovery Point Objective)** là lượng dữ liệu tối đa business chấp nhận mất. **RTO (Recovery Time Objective)** là thời gian tối đa để khôi phục dịch vụ.

### 14.1. Async RPO

Async replication có thể có RPO khác 0. Khi primary mất trước khi WAL tới standby được promote, các commits đã được primary trả thành công nhưng chưa có trên standby có thể bị mất khỏi timeline mới.

### 14.2. Sync remote flush

Nếu transaction được xác nhận sau khi ít nhất số lượng synchronous standbys yêu cầu đã flush WAL, và failover promote một standby đã xác nhận transaction đó, các commits được xác nhận có thể được bảo toàn trong mô hình failure giả định phù hợp.

### 14.3. Remote write có durability yếu hơn

`remote_write` chỉ chờ WAL được ghi tới OS trên standby. Nếu standby OS/power mất trước flush, WAL đó có thể mất. Vì vậy không coi remote_write là cùng durability guarantee với `on`.

### 14.4. Remote apply

`remote_apply` chờ replay và phù hợp khi cần visibility ngay trên standby. Về durability, WAL đã được flush trước khi replay, nhưng mức này thêm điều kiện apply vào commit response.

### 14.5. Không hứa zero data loss trong mọi tình huống

Ngay cả synchronous replication cũng không bảo vệ trước:
- Mất đồng thời primary và mọi standbys chứa acknowledged WAL.
- Storage stack báo flush thành công nhưng không bền vững.
- Promote sai standby chưa nhận đủ WAL.
- Split brain hoặc fencing thất bại.
- Lỗi logic/application được replicate.
- Operator bỏ sync policy hoặc session override.
- Backup/WAL archive không có hoặc không phục hồi được.

## 15. Xây dựng physical standby: prerequisites

Ví dụ topology:
- Primary: `db-primary`.
- Standby A: `db-standby-a`.
- Standby B: `db-standby-b`.
- Replication role: `replicator`.

### 15.1. Primary settings

Các tham số thường cần:

```conf
wal_level = replica
max_wal_senders = 10
max_replication_slots = 10
wal_keep_size = '2GB'
```

`wal_keep_size` là một lượng WAL tối thiểu được giữ lại theo cấu hình, không phải thay thế monitoring/slots. Chọn giá trị theo WAL generation và thời gian gián đoạn dự kiến.

### 15.2. Replication role

```sql
CREATE ROLE replicator
    WITH LOGIN REPLICATION PASSWORD 'use-a-secret-manager';
```

Dùng credential thật qua secret manager/password file; không đưa password thật vào script được commit.

### 15.3. pg_hba.conf

Ví dụ:

```conf
hostssl replication replicator 10.20.0.0/24 scram-sha-256
```

Chỉ cho phép các standby addresses cần thiết. Dùng TLS và network restrictions theo security policy.

### 15.4. Restart hay reload?

Một số WAL sender/slot settings cần restart nếu thay đổi; một số settings có thể reload. Kiểm tra `pg_settings.context` và documentation cho đúng major version thay vì giả định mọi tham số đều reload được.

### 15.5. Standby phải được tạo từ base backup hợp lệ

Physical standby cần bản sao vật lý nhất quán của primary và WAL cần thiết để bắt đầu recovery. Dùng `pg_basebackup` hoặc backup solution tương thích.

## 16. Tạo standby bằng pg_basebackup

Một ví dụ tạo standby với replication slot:

```bash
pg_basebackup \
  --host=db-primary \
  --port=5432 \
  --username=replicator \
  --pgdata=/var/lib/postgresql/18/standby-a \
  --format=plain \
  --wal-method=stream \
  --progress \
  --write-recovery-conf \
  --create-slot \
  --slot=standby_a_slot
```

Các option names có short forms tương ứng trong một số phiên bản. Đọc `pg_basebackup --help` của client tools được cài.

### 16.1. write-recovery-conf / -R

Option này tạo `standby.signal` và ghi connection/slot settings phù hợp vào `postgresql.auto.conf` trên target. Với PostgreSQL hiện đại, standby.signal đánh dấu cluster khởi động ở standby mode.

### 16.2. Replication slot

`--create-slot --slot=standby_a_slot` yêu cầu primary tạo physical slot cho standby. Primary cần đủ `max_replication_slots`.

### 16.3. Không tạo slot trùng

Nếu slot đã tồn tại, `--create-slot` sẽ không thể tạo slot cùng tên. Có thể tạo slot thủ công trước và dùng `--slot` mà không yêu cầu tạo lại; xác nhận slot không thuộc standby khác.

### 16.4. Bảo vệ credential

Dùng passfile hoặc secret injection theo OS. Tránh ghi password vào shell history hoặc process listings.

### 16.5. Khởi động standby

Sau base backup, cấu hình `hot_standby`/`primary_conninfo`/slot theo policy, đảm bảo port/data directory đúng, rồi start service. Kiểm tra logs và `pg_is_in_recovery()`.

## 17. Cấu hình standby connection

Ví dụ trong `postgresql.auto.conf` hoặc config được include:

```conf
primary_conninfo = 'host=db-primary port=5432 user=replicator application_name=standby_a sslmode=verify-full'
primary_slot_name = 'standby_a_slot'
hot_standby = on
```

### 17.1. application_name

Đặt một tên duy nhất, ổn định cho từng standby. Primary dùng tên này để khớp `synchronous_standby_names`.

### 17.2. Slot name

Slot name là identifier giữ WAL retention. Nó không cần giống application_name, dù đặt tương ứng giúp vận hành dễ hiểu.

### 17.3. Connection string

Cần host, port, user, TLS options, passfile/certificate và các connection parameters theo môi trường. Không hardcode password trong config nếu có thể dùng passfile/secret mechanism.

### 17.4. Kiểm tra standby state

Trên standby:

```sql
SELECT
    pg_is_in_recovery() AS is_standby,
    pg_last_wal_receive_lsn() AS received_lsn,
    pg_last_wal_replay_lsn() AS replayed_lsn;
```

`pg_is_in_recovery()` phải là true khi server đang ở standby/recovery mode.

## 18. Bật synchronous replication sau khi standby streaming

Không nên cấu hình primary chờ một standby name trước khi standby thực sự được chuẩn bị nếu hệ thống đang phục vụ writes.

Một rollout an toàn theo từng bước:
1. Tạo replication role và pg_hba rule.
2. Base backup và khởi động standby.
3. Xác nhận standby streaming.
4. Kiểm tra application_name.
5. Cấu hình `synchronous_standby_names`.
6. Reload primary config.
7. Xác nhận `sync_state` chuyển thành sync/quorum.
8. Test transaction commit latency và behavior khi standby disconnect.

### 18.1. Ví dụ FIRST 1

Trên primary:

```conf
synchronous_standby_names = 'FIRST 1 (standby_a, standby_b)'
synchronous_commit = on
```

### 18.2. Reload và kiểm tra

```sql
SELECT pg_reload_conf();

SHOW synchronous_standby_names;
SHOW synchronous_commit;
```

`pg_reload_conf()` trả kết quả yêu cầu reload được gửi; vẫn cần kiểm tra setting effective và logs.

### 18.3. Xác nhận standby đã được chọn

```sql
SELECT
    application_name,
    state,
    sync_state,
    sync_priority,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn
FROM pg_stat_replication
ORDER BY application_name;
```

Đối với FIRST configuration, standby được chọn sẽ có sync_state phù hợp như `sync`; các candidate khác có thể là `potential` hoặc `async` tùy trạng thái/cấu hình.

### 18.4. Khi không có matching standby

Nếu synchronous standby được cấu hình nhưng không có standby phù hợp, transactions yêu cầu remote acknowledgement có thể chờ. Kiểm tra tên application_name, connection state, pg_hba, replication role và WAL sender capacity.

## 19. FIRST và ANY trong cấu hình thực tế

### 19.1. Một synchronous standby ưu tiên

```conf
synchronous_standby_names = 'FIRST 1 (standby_a, standby_b)'
```

Phù hợp khi standby_a có latency/failure domain ưu tiên, standby_b là fallback.

### 19.2. Hai synchronous standbys theo priority

```conf
synchronous_standby_names = 'FIRST 2 (standby_a, standby_b, standby_c)'
```

Commit cần acknowledgement từ hai standbys được chọn theo priority.

### 19.3. Một standby bất kỳ

```conf
synchronous_standby_names = 'ANY 1 (standby_a, standby_b, standby_c)'
```

Primary có thể chờ một trong các nodes đủ điều kiện.

### 19.4. Hai standbys bất kỳ

```conf
synchronous_standby_names = 'ANY 2 (standby_a, standby_b, standby_c)'
```

Yêu cầu quorum hai acknowledgements trong danh sách.

### 19.5. Tên phải unique

Đặt application_name khác nhau cho mỗi standby. Nếu nhiều connections dùng cùng name, việc chọn synchronous standby có thể không rõ ràng và vận hành khó kiểm soát.

## 20. Monitoring trên primary

`pg_stat_replication` hiển thị thông tin về các standbys kết nối trực tiếp.

```sql
SELECT
    pid,
    application_name,
    client_addr,
    state,
    sync_state,
    sync_priority,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn,
    write_lag,
    flush_lag,
    replay_lag
FROM pg_stat_replication
ORDER BY application_name;
```

### 20.1. state

`state` có thể phản ánh startup, catchup, streaming hoặc trạng thái liên quan. Với replication ổn định, thường mong đợi `streaming`.

### 20.2. sync_state

Các trạng thái có thể gồm:
- `async`: asynchronous standby.
- `potential`: candidate có thể trở thành synchronous.
- `sync`: synchronous standby được chọn theo priority mode.
- `quorum`: standby tham gia quorum mode.

Giá trị và semantics cần đối chiếu version đang chạy.

### 20.3. sync_priority

Thể hiện priority liên quan synchronous selection. Trong quorum mode, không diễn giải nó như thứ tự ưu tiên giống FIRST.

### 20.4. LSN gaps

So sánh `sent_lsn`, `write_lsn`, `flush_lsn` và `replay_lsn` để tìm khoảng cách giữa send, write, flush và replay. Dùng `pg_wal_lsn_diff()` để tính bytes.

Ví dụ:

```sql
SELECT
    application_name,
    pg_wal_lsn_diff(sent_lsn, write_lsn) AS send_to_write_bytes,
    pg_wal_lsn_diff(write_lsn, flush_lsn) AS write_to_flush_bytes,
    pg_wal_lsn_diff(flush_lsn, replay_lsn) AS flush_to_replay_bytes
FROM pg_stat_replication
WHERE state = 'streaming';
```

Các giá trị có thể NULL trong một số thời điểm/trạng thái; xử lý NULL trong monitoring.

### 20.5. Lag time fields

`write_lag`, `flush_lag`, `replay_lag` là các chỉ báo thời gian dựa trên WAL activity gần đây. Khi workload idle hoặc lag đã hết, chúng có thể NULL; không dùng chúng một mình làm dự báo thời gian catch-up.

## 21. Monitoring trên standby

`pg_stat_wal_receiver` hiển thị receiver connection hiện tại:

```sql
SELECT
    status,
    receive_start_lsn,
    written_lsn,
    flushed_lsn,
    received_tli,
    last_msg_send_time,
    last_msg_receipt_time,
    latest_end_lsn,
    latest_end_time,
    slot_name,
    sender_host,
    sender_port
FROM pg_stat_wal_receiver;
```

### 21.1. Receiver status

Khi streaming bình thường, status thường thể hiện receiver đang streaming. Nếu view không có row, standby có thể không có active WAL receiver connection tại thời điểm query.

### 21.2. Receive và replay

```sql
SELECT
    pg_last_wal_receive_lsn() AS receive_lsn,
    pg_last_wal_replay_lsn() AS replay_lsn,
    pg_last_xact_replay_timestamp() AS last_replayed_commit_time;
```

`receive_lsn` và `replay_lsn` khác nhau khi standby đã nhận WAL nhưng chưa replay hết.

### 21.3. Replay timestamp không phải lag metric hoàn hảo

Nếu primary idle, timestamp của transaction cuối cùng có thể cũ dù standby đã theo kịp hoàn toàn. So sánh LSN và thông điệp receiver cùng thời gian primary/standby.

### 21.4. Standby conflicts

```sql
SELECT *
FROM pg_stat_database_conflicts;
```

View này cung cấp thông tin về query conflicts trên hot standby. Các query dài có thể bị cancel hoặc trì hoãn replay theo cấu hình standby conflict handling.

## 22. Nhận diện transaction đang chờ SyncRep

Trên primary:

```sql
SELECT
    pid,
    usename,
    application_name,
    state,
    wait_event_type,
    wait_event,
    xact_start,
    query
FROM pg_stat_activity
WHERE wait_event = 'SyncRep';
```

### 22.1. SyncRep wait

Backend chờ synchronous replication acknowledgement có thể hiển thị wait event `SyncRep` với wait event type liên quan IPC.

### 22.2. Điều tra nguyên nhân

Kiểm tra:
- `synchronous_standby_names`.
- `synchronous_commit` của transaction/session.
- `pg_stat_replication` và sync_state.
- Network latency/loss.
- Standby write/flush/replay progress.
- Standby disk saturation.
- Standby recovery conflicts nếu dùng remote_apply.
- Replication slots và WAL sender errors.

### 22.3. Không kill transaction đầu tiên thấy chờ

Backend có thể đang thực hiện một transaction quan trọng và chờ theo durability policy. Xác định application, transaction age, commit stage và business impact trước khi cancel/terminate.

## 23. Replication slots và WAL retention

Physical replication slot giữ WAL cần thiết cho standby chưa nhận. Slot ngăn primary recycle WAL segments mà standby vẫn cần.

### 23.1. Tạo physical slot

```sql
SELECT *
FROM pg_create_physical_replication_slot('standby_a_slot');
```

Có thể tạo slot tự động bằng pg_basebackup option phù hợp.

### 23.2. Xem slots

```sql
SELECT
    slot_name,
    slot_type,
    active,
    restart_lsn,
    wal_status
FROM pg_replication_slots
ORDER BY slot_name;
```

Một số cột phụ thuộc major version; điều chỉnh query theo catalog đích.

### 23.3. Slot không bảo đảm standby đang hoạt động

Slot inactive vẫn có thể giữ WAL. Nếu standby mất kết nối lâu, `pg_wal` có thể tăng đến khi đầy filesystem.

### 23.4. max_slot_wal_keep_size

Tham số này giới hạn lượng WAL mà replication slots có thể giữ lại theo policy của PostgreSQL version. Khi vượt giới hạn, slot có thể trở nên unusable/lost WAL status, standby cần được xử lý hoặc tạo lại.

### 23.5. wal_keep_size

Giữ một lượng WAL tối thiểu theo cấu hình cho standby có thể catch up trong một khoảng outage ngắn. Nó không đảm bảo WAL luôn tồn tại cho một standby offline lâu.

### 23.6. Slot và synchronous acknowledgement là hai chức năng khác nhau

- Slot giúp giữ WAL cần thiết.
- Synchronous commit quyết định primary chờ acknowledgement trước khi trả commit.
- Slot không chứng minh WAL đã được flush trên standby.
- Synchronous replication có thể dùng slot nhưng slot không tự làm replication synchronous.

## 24. Hot standby và read queries

Khi `hot_standby = on`, standby có thể phục vụ read-only queries trong lúc replay WAL.

### 24.1. Read scaling

Ứng dụng có thể route reporting/read-heavy queries sang standby để giảm tải primary. Cần chấp nhận read lag trong async mode.

### 24.2. Read-after-write

Nếu một transaction vừa commit trên primary và application lập tức đọc standby, async mode có thể trả dữ liệu cũ. Có thể:
- Đọc lại từ primary.
- Chờ standby replay tới LSN của transaction.
- Dùng `remote_apply` và route tới standby đã acknowledge.
- Dùng session consistency/routing policy.

### 24.3. remote_apply không tự định tuyến ứng dụng

Primary chờ standby replay nhưng application vẫn cần kết nối đúng standby và mở snapshot mới. Nếu load balancer route sang một standby khác chưa replay, stale read vẫn có thể xảy ra.

### 24.4. Long-running standby queries

Queries dài có thể conflict với WAL replay khi replay cần remove row versions hoặc thay đổi catalog state. Cấu hình `max_standby_streaming_delay` và `hot_standby_feedback` ảnh hưởng trade-off giữa query availability, replay lag và bloat trên primary.

## 25. Synchronous replication và standby conflicts

Với `remote_apply`, commit response chờ standby replay. Nếu standby replay bị chặn bởi read queries hoặc recovery conflict, primary commit có thể chậm.

### 25.1. max_standby_streaming_delay

Tham số này điều khiển mức thời gian standby có thể trì hoãn apply WAL để cho query hoàn tất trước khi cancel query do conflict. Cần xem đúng semantics của version và workload.

### 25.2. hot_standby_feedback

Feedback có thể giúp primary tránh vacuum cleanup làm conflict với standby queries, nhưng có thể giữ xmin và gây bloat trên primary.

### 25.3. Không tăng delay vô hạn

Nếu query không bao giờ bị cancel, replay lag có thể tăng và remote_apply commit có thể chờ lâu. Chọn delay dựa trên read SLA và write commit SLA.

### 25.4. Remote flush có thể phù hợp hơn remote_apply

Nếu mục tiêu là bảo đảm WAL đã được flush trên standby nhưng không cần read visibility ngay, `synchronous_commit = on` thường tránh phải chờ replay hoàn tất.

## 26. Network và storage ảnh hưởng synchronous replication

Synchronous commit path phụ thuộc network và standby storage.

### 26.1. Network RTT

Primary cần gửi WAL và nhận acknowledgement. Standby ở xa region có thể tăng commit latency đáng kể.

### 26.2. Network loss/jitter

Mất packet, congestion hoặc reconnect làm standby không theo kịp. Synchronous transactions có thể chờ cho tới khi connection ổn định và quorum được đáp ứng.

### 26.3. Standby storage

Flush latency cao có thể khiến `on` chậm. Dùng storage phù hợp với write latency và WAL workload; đo fsync/flush behavior.

### 26.4. Shared failure domain

Primary và standby cùng power domain, rack, storage array hoặc region có thể mất đồng thời. Synchronous acknowledgement không thay thế topology design.

### 26.5. TLS

TLS bảo vệ confidentiality/integrity của connection trên network; nó không tự bảo đảm standby storage durability hay failover correctness.

## 27. Synchronous replication với nhiều standbys

Ví dụ topology:

```text
Primary
  |
  +-- standby_a (region A)
  |
  +-- standby_b (region B)
  |
  +-- standby_c (region C)
```

### 27.1. FIRST 1

Chọn một standby ưu tiên. Đơn giản và latency thường có thể tối ưu bằng cách đặt standby ưu tiên gần primary, nhưng fallback behavior phải được kiểm tra.

### 27.2. ANY 2

Chờ hai trong ba standbys. Có thể chịu một node outage mà vẫn commit nếu hai nodes còn lại hoạt động và đủ điều kiện.

### 27.3. Latency của quorum

Commit latency phụ thuộc acknowledgement đủ quorum, không nhất thiết node chậm nhất trong mọi candidates. Tuy nhiên, network/storage và scheduler có thể làm node chậm trở thành một phần quorum.

### 27.4. Promote node nào?

Khi primary mất, chọn một standby đã nhận/flush đủ WAL của các commits được acknowledge. Với quorum, không phải mọi standby đều có toàn bộ WAL cuối cùng; failover manager phải chọn node đúng dựa trên WAL state và topology.

### 27.5. Quorum size và availability

Quorum lớn hơn tăng số bản WAL đã xác nhận nhưng giảm khả năng commit khi nodes mất. Thiết kế theo failure model, không chỉ theo công thức majority chung chung.

## 28. Cascading replication

Trong cascading replication, standby có thể gửi WAL tới các standbys downstream.

```text
Primary
   |
   +---- Standby A
              |
              +---- Standby A1
              |
              +---- Standby A2
```

### 28.1. Giảm connections trên primary

Cascading có thể giảm số trực tiếp WAL sender connections và phân phối replication load.

### 28.2. Downstream lag tích lũy

WAL cần đi qua nhiều hops; downstream replicas có thể lag hơn primary-connected standby.

### 28.3. Synchronous acknowledgement là cho direct standby

Primary chỉ nhìn thấy replication connections trực tiếp. Nó không nhận acknowledgement riêng từ A1/A2 qua Standby A để tính chúng vào synchronous quorum của primary gốc.

### 28.4. Synchronous giữa các tầng

Mỗi tầng cần hiểu rõ sender/receiver relationship và khả năng cấu hình. Đừng giả định một primary sync ack đồng nghĩa toàn bộ cascading tree đã flush hoặc replay.

## 29. Failover trong async replication

Khi primary mất, operator/HA manager đánh giá standbys và chọn một node promote.

### 29.1. Data loss window

Nếu standby được promote chưa nhận WAL cuối cùng của primary, những commits chưa được truyền có thể mất khỏi timeline mới.

### 29.2. Lag không phải chỉ số duy nhất

Kiểm tra LSN positions, WAL availability, receiver status, replay progress và timeline. Timestamp lag có thể misleading khi workload idle.

### 29.3. Promote

Một standby có thể được promote bằng `pg_ctl promote` hoặc SQL function `pg_promote()` tùy quy trình. Chỉ thực hiện sau khi xác nhận primary cũ đã được fence và node được chọn là candidate đúng.

### 29.4. Rejoin primary cũ

Primary cũ không thể tự quay lại cùng timeline như primary mới nếu đã phân kỳ. Cần `pg_rewind` khi điều kiện phù hợp hoặc rebuild từ base backup. Đừng start hai writable primaries cùng lúc.

## 30. Failover trong synchronous replication

Synchronous replication giúp bảo toàn các commits đã được acknowledged bởi standby đáp ứng synchronous policy, nhưng failover vẫn cần quyết định đúng.

### 30.1. Promote đúng standby

- Với FIRST 1, ưu tiên node đã được chọn sync và có WAL flush tới commit đã acknowledged.
- Với ANY quorum, xác định node nào trong quorum đã nhận/flush các commits cần giữ.
- Kiểm tra LSN và timeline trước promotion.
- Tránh promote standby không nằm trong acknowledgement set nếu có node tốt hơn.

### 30.2. Fencing primary cũ

Nếu primary cũ vẫn có thể nhận writes, split brain có thể xảy ra. Dùng fencing/quorum/STONITH/network isolation hoặc cơ chế tương đương của HA platform.

### 30.3. Synchronous không là consensus cluster manager

`synchronous_standby_names` không bầu primary, không fence node, không quản lý VIP/DNS và không tự bảo đảm chỉ có một writer.

### 30.4. Rejoin và timeline

Sau promotion, node cũ cần follow timeline mới bằng rewind/rebuild. Kiểm tra WAL availability và `wal_log_hints`/data checksums prerequisites nếu dùng pg_rewind.

## 31. Khi synchronous standby mất kết nối

Giả sử cấu hình:

```conf
synchronous_standby_names = 'FIRST 1 (standby_a)'
```

Nếu standby_a mất kết nối:
- Transactions với synchronous_commit yêu cầu remote acknowledgement có thể chờ.
- Transactions dùng `local` hoặc `off` có thể không đợi remote, nhưng durability policy yếu hơn.
- Read queries trên primary vẫn có thể hoạt động.
- Standby reconnect có thể khôi phục commit progress sau khi catch up.

### 31.1. Kiểm tra trước

```sql
SELECT
    application_name,
    state,
    sync_state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn
FROM pg_stat_replication;
```

### 31.2. Kiểm tra WAL receiver

Trên standby, xem `pg_stat_wal_receiver`, PostgreSQL logs, network, DNS, credentials, pg_hba và slot state.

### 31.3. Không drop slot chỉ để giải phóng disk ngay

Slot có thể giữ WAL cần thiết để standby catch up. Nếu drop slot, standby có thể cần reinitialize/reseed. Kiểm tra WAL retention và data recovery path trước.

### 31.4. Emergency degrade

Nếu business quyết định tiếp tục writes mà không có synchronous standby, operator có thể thay đổi sync policy theo change/incident process. Ghi lại thời điểm, phạm vi transactions không còn remote acknowledgement và RPO mới.

## 32. Thay đổi synchronous policy an toàn

Một runbook thay đổi có thể gồm:

1. Xác nhận lý do và người phê duyệt.
2. Kiểm tra các standbys đang connected/streaming.
3. Xác định FIRST/ANY quorum hiện tại.
4. Xác định transaction classes có thể dùng local commit.
5. Thay config hoặc per-transaction setting có kiểm soát.
6. Reload nếu tham số cho phép.
7. Kiểm tra effective settings và `sync_state`.
8. Test commit/monitor wait events.
9. Ghi lại thời điểm policy đổi và khi khôi phục.
10. Xác nhận lại RPO sau sự cố.

### 32.1. Giảm quorum

Giảm `ANY 2` xuống `ANY 1` có thể giúp tiếp tục commits nhưng giảm số standby acknowledgements. Đây là thay đổi durability, không phải tuning vô hại.

### 32.2. Chuyển async

Xóa synchronous standby requirement hoặc dùng local commit có thể khôi phục write availability. Cần ghi nhận các commits sau thời điểm đó không có cùng guarantee.

### 32.3. Khôi phục sync

Khi standby đã streaming, catch up và đủ khỏe, khôi phục quorum theo config. Xác nhận sync_state trước khi tuyên bố durability policy đã trở lại.

## 33. Synchronous replication và backup

Replication không thay backup.

### 33.1. Lỗi logic được replicate

Nếu application vô tình DELETE nhầm rows hoặc migration drop table, WAL hợp lệ sẽ truyền thao tác đó tới standby. Synchronous replication không giữ lịch sử trước thay đổi.

### 33.2. Corruption có thể được replicate

Một số lỗi dữ liệu hoặc thao tác gây hỏng có thể xuất hiện trên replicas. Backup/PITR cho phép khôi phục về thời điểm trước lỗi nếu WAL archive/retention đủ.

### 33.3. Backup độc lập

Duy trì base backups, WAL archiving, retention, verification và restore drills. Synchronous replication chỉ cải thiện durability của commit theo acknowledgement policy.

### 33.4. DR region

Standby sync ở xa có thể tăng latency và chịu shared network/provider risks. Có thể dùng một synchronous standby gần primary và asynchronous DR standby ở region khác; xác định RPO khác nhau cho từng mục tiêu.

## 34. Monitoring WAL generation và replication capacity

Các chỉ số nên theo dõi:
- WAL generation rate trên primary.
- Send/write/flush/replay LSN gaps.
- Standby connection state.
- Sync state/quorum availability.
- WAL sender count/capacity.
- Replication slot WAL retention.
- `pg_wal` filesystem free space.
- Network RTT/loss/throughput.
- Standby write/flush I/O latency.
- Replay lag và standby query conflicts.
- Primary backends chờ SyncRep.
- Failover readiness và last restore drill.

### 34.1. max_wal_senders

Đảm bảo đủ WAL sender processes cho standbys, base backups và các replication clients liên quan. Quá ít có thể khiến connections mới không vào được.

### 34.2. max_replication_slots

Đảm bảo đủ slots cho consumers dự kiến. Slot không dùng vẫn có thể giữ WAL; monitor inactive slots.

### 34.3. WAL disk capacity

Một standby disconnect lâu có thể làm WAL tích tụ. Alert trước khi filesystem đầy; có giới hạn slot retention phù hợp và runbook reseed.

### 34.4. Checkpoint và WAL load

Replication không xóa nhu cầu checkpoint tuning. WAL generation, checkpoint frequency và storage performance ảnh hưởng primary/standby I/O.

## 35. Monitoring replication lag bằng bytes

Ví dụ trên primary:

```sql
SELECT
    application_name,
    pg_wal_lsn_diff(
        pg_current_wal_lsn(),
        replay_lsn
    ) AS replay_lag_bytes,
    pg_wal_lsn_diff(
        sent_lsn,
        write_lsn
    ) AS send_write_gap_bytes,
    pg_wal_lsn_diff(
        write_lsn,
        flush_lsn
    ) AS write_flush_gap_bytes,
    pg_wal_lsn_diff(
        flush_lsn,
        replay_lsn
    ) AS flush_replay_gap_bytes
FROM pg_stat_replication
WHERE state = 'streaming';
```

### 35.1. Byte lag phải đi cùng WAL rate

100 MB lag có thể tương đương vài giây hoặc nhiều phút tùy WAL generation rate. Đo cả bytes và tốc độ phát sinh WAL.

### 35.2. LSN positions có thể NULL

Trong startup/catchup/disconnected states, một số positions có thể NULL. Monitoring cần xử lý đúng, không coi NULL là zero lag.

### 35.3. Lag time và idle workload

Nếu không có writes, timestamp-based lag có thể giữ giá trị cũ hoặc NULL. Không phát cảnh báo chỉ từ một field mà không xem WAL activity.

## 36. Monitoring wait events và transaction latency

Query backend đang chờ sync:

```sql
SELECT
    pid,
    application_name,
    state,
    wait_event_type,
    wait_event,
    now() - xact_start AS transaction_age,
    left(query, 160) AS query_sample
FROM pg_stat_activity
WHERE wait_event = 'SyncRep'
ORDER BY xact_start;
```

### 36.1. Đo commit latency phía ứng dụng

DB views giúp thấy wait event, nhưng cần application metrics để đo latency end-to-end và phân biệt pool wait, query execution, commit wait và network response.

### 36.2. Correlate với standby flush

Khi commit chậm, đối chiếu primary waiters với standby flush_lsn, storage latency và network RTT. Nếu dùng remote_apply, xem replay_lsn và standby conflicts.

### 36.3. Không chỉ tăng timeout

Tăng application timeout có thể giảm lỗi timeout nhưng không cải thiện standby durability/latency. Tìm bottleneck thực sự.

## 37. Phân biệt replication lag và synchronous wait

Async standby có thể lag mà primary commits vẫn nhanh vì không chờ. Sync standby có thể lag một phần nhưng primary commit chỉ chờ đến acknowledgement threshold cần thiết.

### 37.1. FIRST 1

Một standby được chọn sync. Nếu standby khác lag nhưng không được chọn, lag đó có thể không ảnh hưởng commit acknowledgement hiện tại.

### 37.2. ANY 2

Primary cần hai acknowledgements. Node thứ ba có thể lag mà commits vẫn hoàn tất nếu hai nodes khác đủ điều kiện.

### 37.3. remote_apply

Replay lag của synchronous standby có thể trực tiếp ảnh hưởng commit latency khi dùng remote_apply.

### 37.4. remote_write/on

Với remote_write hoặc on, primary chờ write/flush, không cần đợi standby replay. Replay có thể lag mà commit vẫn được xác nhận.

## 38. Synchronous replication và transaction isolation

Synchronous commit không thay đổi isolation level của transaction. Nó điều khiển thời điểm trả COMMIT response theo WAL acknowledgement.

### 38.1. Read committed

Một transaction mới trên standby sau khi remote_apply acknowledgement có thể nhìn thấy commit, vì snapshot mới được lấy sau replay.

### 38.2. Repeatable read / serializable

Một transaction đã mở snapshot trước khi WAL replay có thể tiếp tục nhìn thấy snapshot cũ. Remote apply không làm mới snapshot hiện tại.

### 38.3. Application routing

Nếu ứng dụng dùng read pool, phải bảo đảm read sau commit đi tới standby đã xác nhận hoặc primary. Chỉ bật remote_apply mà không có routing/session consistency policy là chưa đủ.

## 39. Synchronous replication và DDL

DDL được ghi trong WAL và physical standby replay cùng thay đổi. Synchronous acknowledgement áp dụng cho transaction commit chứa DDL như các transaction khác, theo `synchronous_commit`.

### 39.1. Extension installation

CREATE EXTENSION thay đổi catalogs/objects và được WAL replicate. Tuy nhiên, extension shared library trên standby phải được cài/có sẵn ở filesystem; WAL không chuyển binary package.

### 39.2. Configuration changes

Thay đổi postgresql.conf, pg_hba.conf, certificates, preload libraries hoặc OS package không được WAL replicate như database DDL. Quản lý config đồng bộ qua automation/config management.

### 39.3. External files

Các files ngoài data directory hoặc tablespace không được WAL replication bao phủ trừ khi được xử lý bởi cơ chế riêng. Provision chúng trên standby.

## 40. Synchronous replication và replication slots

Physical replication slots thường dùng để đảm bảo WAL chưa được standby nhận không bị recycle.

### 40.1. Slot không tạo synchronous mode

Nếu `synchronous_standby_names` rỗng, một standby dùng slot vẫn có thể là async.

### 40.2. Synchronous không bắt buộc slot trong mọi setup

Standby có thể stream mà không dùng slot, nhưng cần đủ WAL retention bằng `wal_keep_size`/archive hoặc cơ chế khác để standby bắt kịp sau gián đoạn. Slot thường dễ kiểm soát retention hơn nhưng có rủi ro disk growth.

### 40.3. Slot và failover

Sau promotion, cần quản lý slots trên primary mới và đảm bảo downstream standbys có slot/connection config phù hợp. Không giả định slot state tự chuyển sang node mới.

## 41. Kiểm tra timeline và recovery state

Standby replay WAL theo timeline. Khi primary promote, timeline mới được tạo. Các nodes cần follow đúng history.

### 41.1. Timeline history

Timeline history files cho biết quan hệ phân nhánh giữa timelines. Đây là yếu tố quan trọng khi node rejoin sau failover.

### 41.2. Promote một lần

Không promote nhiều standbys độc lập cùng lúc khi chưa có fencing/leader election. Hai writable nodes có thể diverge và không tự merge.

### 41.3. pg_rewind

`pg_rewind` có thể đưa data directory của old primary về timeline mới khi đáp ứng prerequisites như data checksums hoặc `wal_log_hints` phù hợp, `full_page_writes` và WAL cần thiết. Kiểm tra tài liệu đúng version trước khi dùng.

### 41.4. Nếu rewind không phù hợp

Rebuild standby từ base backup là phương án rõ ràng hơn nếu không có common ancestor/WAL cần thiết hoặc prerequisites không đạt.

## 42. Tuning primary_conninfo và timeout

Các tham số thường xem:
- `wal_receiver_timeout`
- `wal_sender_timeout`
- `wal_receiver_status_interval`
- `wal_retrieve_retry_interval`
- `primary_conninfo`
- `primary_slot_name`

### 42.1. Timeout quá ngắn

Timeout quá ngắn có thể làm connection reset trong network jitter bình thường, tạo reconnect loops và synchronous commit waits.

### 42.2. Timeout quá dài

Timeout quá dài có thể trì hoãn phát hiện failure. HA manager/network monitoring có thể có health detection riêng; đồng bộ các timeout với failure detection strategy.

### 42.3. SSL verification

Dùng `sslmode=verify-full` và certificate validation khi phù hợp. `sslmode=require` mã hóa nhưng không nhất thiết xác minh hostname/identity theo cùng mức.

## 43. Lab: dựng physical async standby

Thực hiện trên hai PostgreSQL instances riêng trong môi trường lab.

### 43.1. Primary configuration

```conf
wal_level = replica
max_wal_senders = 5
max_replication_slots = 5
hot_standby = on
```

### 43.2. Tạo replication role

```sql
CREATE ROLE replicator
    WITH LOGIN REPLICATION PASSWORD 'lab-secret';
```

Dùng secret lab và không reuse password production.

### 43.3. pg_hba.conf

```conf
host replication replicator 127.0.0.1/32 scram-sha-256
```

Điều chỉnh địa chỉ/SSL theo cách hai instances lab kết nối.

### 43.4. Base backup

```bash
pg_basebackup \
  -h 127.0.0.1 \
  -U replicator \
  -D /path/to/standby_data \
  -X stream \
  -P \
  -R
```

### 43.5. Start standby và xác minh

Trên standby:

```sql
SELECT pg_is_in_recovery();
SELECT * FROM pg_stat_wal_receiver;
```

Trên primary:

```sql
SELECT application_name, state, sync_state
FROM pg_stat_replication;
```

Nếu `synchronous_standby_names` rỗng, standby thường được hiển thị async.

## 44. Lab: quan sát async lag

Trên primary, tạo workload ghi lab:

```sql
CREATE TABLE IF NOT EXISTS public.replication_lab (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    payload TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO public.replication_lab (payload)
SELECT repeat('x', 1000)
FROM generate_series(1, 10000);
```

Quan sát primary/standby LSN:

```sql
SELECT pg_current_wal_lsn();
```

Trên standby:

```sql
SELECT
    pg_last_wal_receive_lsn(),
    pg_last_wal_replay_lsn();
```

### 44.1. Tạo tải có kiểm soát

Không cố tình làm đầy disk hoặc kill process trên máy dùng chung. Nếu cần mô phỏng lag, dùng workload giới hạn và môi trường disposable.

### 44.2. Đọc LSN gaps

So sánh receive/replay để thấy WAL đã nhận nhưng chưa replay. Tăng workload có thể làm gap tăng nếu standby không theo kịp.

## 45. Lab: bật FIRST 1 synchronous standby

Đảm bảo standby có `application_name=standby_a` và đang streaming. Trên primary:

```conf
synchronous_standby_names = 'FIRST 1 (standby_a)'
synchronous_commit = on
```

Reload:

```sql
SELECT pg_reload_conf();
```

Kiểm tra:

```sql
SELECT
    application_name,
    state,
    sync_state,
    sync_priority
FROM pg_stat_replication;
```

### 45.1. Thử commit

Từ một session primary:

```sql
BEGIN;
INSERT INTO replication_lab(payload) VALUES ('sync-test');
COMMIT;
```

Quan sát commit response và standby replay state. Kết quả thời gian phụ thuộc network/storage của lab.

### 45.2. Đọc remote_apply

Thử transaction riêng với `SET LOCAL synchronous_commit='remote_apply'` và so sánh commit wait. Không kết luận từ một sample; đo nhiều lần.

## 46. Lab: mất kết nối standby và commit wait

Chỉ trong lab:
1. Xác nhận FIRST 1 standby đang sync.
2. Mở session trên primary.
3. Tạm dừng/kết thúc standby service theo cách lab kiểm soát.
4. Thực hiện một transaction insert/commit với synchronous_commit=on.
5. Quan sát session chờ SyncRep.
6. Khởi động lại standby và theo dõi catch-up.
7. Xác nhận commit tiếp tục sau khi standby đáp ứng.

### 46.1. Không làm trên production

Mô phỏng disconnect làm thay đổi availability và có thể ảnh hưởng transaction đang chạy. Chỉ dùng cluster lab có thể bỏ đi.

### 46.2. Emergency policy

Thử một session riêng với `SET synchronous_commit = local` để quan sát commit không chờ remote; sau đó reset setting. Đây là minh họa thay đổi durability, không phải khuyến nghị production.

## 47. Lab: ANY quorum

Dùng ba standbys có application_name riêng:
- standby_a
- standby_b
- standby_c

Primary config:

```conf
synchronous_standby_names = 'ANY 2 (standby_a, standby_b, standby_c)'
```

### 47.1. Quan sát sync_state

Kiểm tra `pg_stat_replication`. Các nodes tham gia quorum có state tương ứng quorum; node khác có thể async/potential theo selection.

### 47.2. Mất một standby

Trong lab, dừng một node và xác nhận hai nodes còn lại vẫn có thể đáp ứng quorum khi đủ điều kiện.

### 47.3. Mất hai standbys

Chỉ còn một node, commit yêu cầu ANY 2 có thể chờ. Xác nhận bằng `pg_stat_activity` wait event.

### 47.4. Không suy luận failover chỉ từ quorum

Sau khi primary mất, kiểm tra LSN của từng node và chọn candidate có đủ acknowledged WAL. Quorum config không tự promote.

## 48. Lab: kiểm tra read-after-write

Từ primary:
1. Insert một row có key duy nhất.
2. Commit với `synchronous_commit=on`.
3. Đọc ngay trên async standby và quan sát có thể chưa thấy row.
4. Với sync standby và `remote_apply`, commit chờ replay.
5. Mở transaction đọc mới trên đúng standby đã acknowledge và kiểm tra row.

### 48.1. Snapshot semantics

Nếu query đọc chạy trong transaction đã mở trước commit, nó có thể không thấy row dù standby đã replay. Bắt đầu transaction/snapshot mới để test.

### 48.2. Routing semantics

Nếu đọc qua load balancer, xác định node thực sự nhận query. Test một standby cụ thể để tách vấn đề replay khỏi routing.

## 49. Lab: đo commit latency

Dùng workload có commit nhiều lần trong lab và ghi:
- Median/p95/p99 commit latency.
- Network RTT.
- Primary WAL flush latency.
- Standby write/flush latency.
- Standby replay delay.
- Wait event duration.
- Standby count/quorum.

So sánh:
- Async với synchronous_standby_names rỗng.
- FIRST 1 + `on`.
- FIRST 1 + `remote_write`.
- FIRST 1 + `remote_apply`.
- ANY 2 nếu có ba standbys.

### 49.1. Kiểm soát điều kiện

Giữ cùng workload, connection count, data volume, cache warmness và storage. Ghi rõ cấu hình mỗi run.

### 49.2. Không tối ưu chỉ theo average

Commit tail latency thường quan trọng. Xem p95/p99 và số transaction bị chờ khi network/storage jitter.

## 50. Lab: failover và rejoin trên môi trường riêng

Một bài lab failover cần:
1. Tạo primary và ít nhất một standby.
2. Tạo writes và ghi nhận LSN.
3. Xác nhận standby catch-up.
4. Dừng primary có kiểm soát.
5. Fence primary cũ trong lab.
6. Promote standby.
7. Xác nhận `pg_is_in_recovery()` trả false trên node mới.
8. Kết nối application test.
9. Xử lý node cũ bằng rewind/rebuild.
10. Kiểm tra timeline và WAL.

### 50.1. Async và sync khác nhau ở data loss window

Thực hiện cùng bài lab với async và sync. Trong async, nếu cố tình promote node lag, có thể quan sát thiếu các commits cuối; trong sync remote_flush, promote node đã acknowledge cần giữ các commits đó trong failure model của lab.

### 50.2. Không dùng kill -9 để mô phỏng mọi failure

Hard kill, power loss, network partition và storage failure là các failure models khác nhau. Mô phỏng từng loại trong môi trường disposable và ghi rõ điều kiện.

## 51. Troubleshooting: commits bị treo

Dấu hiệu:
- Application commit timeout.
- Backend wait_event = SyncRep.
- Primary vẫn nhận read queries nhưng writes chờ.
- `pg_stat_replication` không có synchronous standby phù hợp.

Kiểm tra:
1. `SHOW synchronous_standby_names`.
2. `SHOW synchronous_commit`.
3. `pg_stat_replication`.
4. `pg_stat_activity` với SyncRep.
5. Standby logs/receiver status.
6. Network/TLS/pg_hba.
7. Disk flush/replay performance.
8. FIRST/ANY quorum availability.

Không chỉ tăng `statement_timeout`; commit wait có thể có semantics và timeout riêng theo application/connection.

## 52. Troubleshooting: standby không trở thành sync

Nguyên nhân:
- `application_name` không khớp.
- Standby chưa ở streaming state.
- Standby connection bị từ chối.
- Primary config chưa reload.
- FIRST standby có priority cao hơn đang active.
- ANY quorum selection khác kỳ vọng.
- Có nhiều connections trùng application_name.
- WAL sender/slot/connection limits.

Kiểm tra cấu hình hiệu lực và `sync_state`, không chỉ đọc file config.

## 53. Troubleshooting: standby lag tăng

Nguyên nhân có thể:
- Network bandwidth/RTT.
- Standby disk write/flush chậm.
- Replay CPU/I/O bottleneck.
- Long-running standby queries gây recovery conflicts.
- WAL burst lớn.
- Slot/WAL retention hoặc receiver reconnect loop.
- Standby storage gần đầy.

Đo receive gap và replay gap riêng. Nếu receive theo kịp nhưng replay lag, tập trung vào replay. Nếu sent-to-write gap tăng, tập trung network/receiver/write.

## 54. Troubleshooting: primary WAL disk tăng

Kiểm tra:
- Inactive physical replication slots.
- Standby disconnected.
- `restart_lsn` cũ.
- `max_slot_wal_keep_size`.
- WAL archiving backlog.
- `wal_keep_size`.
- WAL generation rate.
- `pg_wal` filesystem free space.

Không xóa thủ công WAL files trong pg_wal. Xử lý slot/standby bằng SQL và quy trình PostgreSQL phù hợp.

## 55. Troubleshooting: standby replay bị chậm

Kiểm tra:
- `pg_stat_wal_receiver`.
- `pg_last_wal_receive_lsn` và `pg_last_wal_replay_lsn`.
- CPU/storage I/O.
- Standby active queries và conflicts.
- `max_standby_streaming_delay`.
- `hot_standby_feedback`.
- WAL volume/checkpoint activity.

Nếu dùng `remote_apply`, replay lag có thể tăng commit latency. Nếu dùng `on`, flush có thể đã theo kịp dù replay còn chậm.

## 56. Troubleshooting: application đọc dữ liệu cũ

Kiểm tra:
- Read query đi tới primary hay standby nào.
- Standby có streaming không.
- Replay LSN so với commit LSN.
- Transaction snapshot được mở lúc nào.
- Load balancer có route sang node lag khác không.
- Commit dùng remote_apply hay chỉ on.
- Ứng dụng có read-your-writes policy không.

Đừng chỉ tăng sleep cố định sau commit; dùng LSN/session consistency nếu yêu cầu cần chính xác.

## 57. Troubleshooting: failover có thể mất acknowledged commits

Nếu dùng synchronous replication nhưng nghi mất commit sau failover:
- Xác định synchronous policy tại thời điểm transaction.
- Kiểm tra session/role/database overrides của synchronous_commit.
- Xác định standby thực sự được chọn/acknowledged.
- Xem sync_state và LSN positions.
- Kiểm tra node được promote có nằm trong acknowledgement set không.
- Xác minh standby storage durability và failure sequence.
- Kiểm tra split brain/old primary writes.

Synchronous mode không bảo vệ nếu operator promote sai node hoặc policy bị hạ trước commit.

## 58. Những hiểu lầm thường gặp

### 58.1. “Có hai standbys nghĩa là synchronous”

Không đúng. Nếu `synchronous_standby_names` rỗng, các standbys có thể đều async.

### 58.2. “synchronous_commit=on tự bật synchronous replication”

Không đúng. Nó cần synchronous standby được cấu hình và kết nối để chờ remote acknowledgement. Nếu không có synchronous standby, local flush vẫn là phần chính.

### 58.3. “remote_write giống remote_flush”

Không đúng. remote_write chỉ đợi OS write; `on` đợi standby flush WAL.

### 58.4. “remote_apply chỉ là remote_flush nhanh hơn”

Không đúng. remote_apply còn đợi standby replay WAL, có thể bị ảnh hưởng bởi replay backlog và recovery conflicts.

### 58.5. “Synchronous replication không bao giờ mất dữ liệu”

Không đúng. Nó phụ thuộc node được promote, số acknowledgements, flush semantics, storage, fencing và failure model.

### 58.6. “Replication slot bảo đảm commit đã có trên standby”

Không đúng. Slot giữ WAL để standby có thể nhận; nó không chứng minh WAL đã được nhận/flush/replay.

### 58.7. “Standby streaming nghĩa đã replay hết”

Không đúng. State streaming chỉ nói receiver đang stream; receive/write/flush/replay LSN vẫn có thể khác nhau.

### 58.8. “Quorum ANY 2 nghĩa mọi ba replicas đều có transaction”

Không đúng. Chỉ cần hai acknowledgements để đáp ứng quorum; replica còn lại có thể lag.

### 58.9. “Sync ack đồng nghĩa automatic failover”

Không đúng. Cần HA manager, fencing, leader selection và routing.

### 58.10. “Read sau commit trên bất kỳ standby nào đều thấy dữ liệu”

Không đúng. Chỉ remote_apply tới standby được acknowledge mới hỗ trợ điều kiện replay; routing và snapshot vẫn quan trọng.

## 59. So sánh FIRST và ANY

| Tiêu chí | FIRST | ANY |
|---|---|---|
| Chọn standby | Theo priority order | Bất kỳ đủ số lượng |
| Cấu hình | `FIRST n (...)` | `ANY n (...)` |
| Latency | Có thể phụ thuộc node ưu tiên | Có thể dùng acknowledgements từ nodes nhanh hơn |
| Fallback | Node kế tiếp khi node ưu tiên không khả dụng | Bất kỳ candidate đủ điều kiện |
| Monitoring | sync/potential/priority | quorum state và count |
| Phù hợp | Preferred standby rõ ràng | Quorum/failure-domain design |

## 60. Mô hình lựa chọn theo yêu cầu

| Nhu cầu | Hướng cân nhắc |
|---|---|
| Latency ghi thấp, chấp nhận RPO khác 0 | Async |
| Local durability, không chờ standby | `synchronous_commit=local` |
| Chờ standby OS write | `remote_write` |
| Chờ standby WAL flush | `on` |
| Cần standby replay trước commit response | `remote_apply` |
| Một standby ưu tiên + fallback | `FIRST 1` |
| Bất kỳ 2 trong 3 replicas | `ANY 2` |
| DR ở region xa, latency thấp tại primary | Gần primary sync, remote DR async |
| Read-after-write trên standby | remote_apply + routing/snapshot policy |

Các lựa chọn cần được thử nghiệm trên topology thật và so với business RPO/RTO.

## 61. Checklist thiết kế

1. Primary/standby cùng major version và physical compatibility?
2. WAL level và WAL sender capacity đúng?
3. Replication role có quyền tối thiểu REPLICATION/LOGIN?
4. pg_hba chỉ cho phép standby hosts cần thiết?
5. TLS/authentication đã được kiểm tra?
6. Base backup nhất quán và standby start được?
7. application_name unique và khớp synchronous_standby_names?
8. Replication slots có được quản lý và monitor?
9. WAL retention đủ cho outage/reseed strategy?
10. FIRST hay ANY phù hợp failure model?
11. Quorum size có chịu được số node failure mong muốn?
12. Nodes có nằm ở failure domains độc lập?
13. synchronous_commit level phù hợp durability/read visibility?
14. Network RTT và standby flush latency nằm trong SLA?
15. Remote_apply có cần thiết hay remote flush đủ?
16. Commit wait behavior khi standby mất kết nối đã được thử?
17. Emergency async/local policy có phê duyệt và audit?
18. Failover manager có fencing/split-brain prevention?
19. Promote candidate selection dựa trên LSN/timeline?
20. Old primary có rewind/rebuild runbook?
21. Read routing có bảo đảm read-after-write?
22. Backup/WAL archive độc lập với replication?
23. Alerts cho SyncRep waits, lag, slots và pg_wal capacity?
24. Restore/failover drills đã được chạy định kỳ?

## 62. Checklist vận hành hàng ngày

- Kiểm tra `pg_stat_replication` trên primary.
- Kiểm tra state và sync_state của từng standby.
- Kiểm tra receive/write/flush/replay LSN gaps.
- Kiểm tra `pg_stat_wal_receiver` trên standbys.
- Kiểm tra backends chờ SyncRep.
- Kiểm tra inactive replication slots và retained WAL.
- Kiểm tra dung lượng filesystem của PGDATA/pg_wal.
- Kiểm tra network RTT/loss.
- Kiểm tra standby storage latency và replay throughput.
- Kiểm tra recovery conflicts và standby query cancellations.
- Xác nhận sync quorum đủ trước khi báo durability policy healthy.
- Kiểm tra backup/WAL archiving và restore status.
- Ghi nhận thay đổi config/commit policy.
- Kiểm tra failover readiness theo lịch.

## 63. Bảng tra cứu nhanh

| Nhu cầu | Lệnh/cấu hình |
|---|---|
| Bật physical WAL | `wal_level = replica` |
| Chọn synchronous standby | `synchronous_standby_names` |
| Chờ local flush + remote flush | `synchronous_commit = on` |
| Chờ remote OS write | `synchronous_commit = remote_write` |
| Chờ remote replay | `synchronous_commit = remote_apply` |
| Chỉ chờ local flush | `synchronous_commit = local` |
| Không chờ local flush | `synchronous_commit = off` |
| Priority selection | `FIRST 1 (standby_a, standby_b)` |
| Quorum selection | `ANY 2 (standby_a, standby_b, standby_c)` |
| Đặt standby identity | `application_name=standby_a` |
| Tạo physical slot | `pg_create_physical_replication_slot()` |
| Base backup | `pg_basebackup -R` |
| Xem standbys | `pg_stat_replication` |
| Xem receiver | `pg_stat_wal_receiver` |
| Xem primary LSN | `pg_current_wal_lsn()` |
| Xem standby receive | `pg_last_wal_receive_lsn()` |
| Xem standby replay | `pg_last_wal_replay_lsn()` |
| Tính LSN gap | `pg_wal_lsn_diff()` |
| Xem SyncRep waiters | `pg_stat_activity WHERE wait_event='SyncRep'` |
| Xem slots | `pg_replication_slots` |
| Promote standby | `pg_ctl promote` / `pg_promote()` theo runbook |
| Kiểm tra recovery state | `pg_is_in_recovery()` |

## 64. Tài liệu chính thức tham khảo

- [PostgreSQL 18 — Warm Standby](https://www.postgresql.org/docs/18/warm-standby.html): streaming replication và standby operation.
- [PostgreSQL 18 — Synchronous Replication](https://www.postgresql.org/docs/18/warm-standby.html#SYNCHRONOUS-REPLICATION): synchronous acknowledgement, FIRST/ANY và commit levels.
- [PostgreSQL 18 — Streaming Replication Protocol](https://www.postgresql.org/docs/18/protocol-replication.html): replication protocol.
- [PostgreSQL 18 — pg_basebackup](https://www.postgresql.org/docs/18/app-pgbasebackup.html): tạo base backup/standby.
- [PostgreSQL 18 — Replication Configuration](https://www.postgresql.org/docs/18/runtime-config-replication.html): WAL sender, slots, synchronous standby settings.
- [PostgreSQL 18 — Replication Statistics](https://www.postgresql.org/docs/18/monitoring-stats.html#MONITORING-PG-STAT-REPLICATION-VIEW): replication monitoring views.
- [PostgreSQL 18 — WAL Configuration](https://www.postgresql.org/docs/18/runtime-config-wal.html): WAL durability and checkpoint configuration.
- [PostgreSQL 18 — High Availability, Load Balancing, and Replication](https://www.postgresql.org/docs/18/high-availability.html): HA and replication overview.
- [PostgreSQL 18 — pg_rewind](https://www.postgresql.org/docs/18/app-pgrewind.html): rejoin a former primary after timeline divergence.

Một số parameters, catalog columns và tooling options có thể khác giữa major versions. Luôn đối chiếu manual đúng phiên bản của source và target trước khi thay đổi production configuration.

## 65. Tổng kết

Asynchronous và synchronous physical replication đều truyền WAL từ primary tới standby. Khác biệt nằm ở việc primary có đợi standby acknowledgement trước khi xác nhận commit hay không, và acknowledgement dừng ở mức write, flush hay replay.

1. **Async:** primary không đợi standby. Commit latency thấp và write availability cao hơn, nhưng promote standby lag có thể làm mất các transactions đã được client xác nhận.
2. **Sync:** primary đợi số lượng standbys được cấu hình. Nó có thể bảo vệ các commits đã được acknowledged nếu failover promote đúng node và storage/fencing đáp ứng giả định.
3. **Commit levels:** `remote_write` đợi OS write; `on` đợi remote WAL flush; `remote_apply` đợi replay. `local` chỉ chờ local flush; `off` có thể trả commit trước local flush.
4. **Selection:** `FIRST` chọn theo priority; `ANY` chọn quorum bất kỳ. Quorum size ảnh hưởng cả durability và khả năng tiếp tục commit khi node lỗi.
5. **Monitoring:** phân biệt sent/write/flush/replay LSN; xem `pg_stat_replication`, `pg_stat_wal_receiver`, replication slots và `SyncRep` wait events.
6. **Availability:** synchronous quorum không đủ có thể làm commits chờ. Hạ quorum/chuyển async thay đổi RPO và phải có incident policy.
7. **Failover:** PostgreSQL không tự bầu/promote/fence primary. Cần chọn đúng standby, ngăn split brain và quản lý timeline/rejoin.
8. **Backup:** replication không thay backup, WAL archiving, PITR, verification hoặc restore drills.

Thiết kế tốt bắt đầu từ câu hỏi business cần bảo đảm điều gì: commit phải tồn tại trên một node khác, phải durable trên storage khác, hay phải có thể đọc ngay trên standby? Chọn acknowledgement level và quorum theo câu trả lời đó, rồi kiểm chứng latency, failure behavior và failover bằng các bài thử có kiểm soát.
