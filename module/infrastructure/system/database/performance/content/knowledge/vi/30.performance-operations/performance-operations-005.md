# Tạo chỉ mục hoặc đổi lược đồ dưới tải: khóa và chi phí tài nguyên

## Mục tiêu học tập

Sau bài học này, bạn có thể:

- Giải thích vì sao thao tác tạo index hoặc thay đổi schema có thể ảnh hưởng truy vấn và giao dịch đang chạy.
- Phân biệt khóa dữ liệu, khóa metadata/schema và các giai đoạn khóa ngắn của DDL online.
- Ước lượng chi phí CPU, RAM, I/O, transaction log/WAL/redo, temp space và replication khi xây dựng chỉ mục.
- So sánh cơ chế tạo index và thay đổi schema của PostgreSQL, MySQL/InnoDB và SQL Server.
- Thiết kế migration theo hướng expand-contract, backfill theo batch và triển khai tương thích ngược.
- Lập kế hoạch, giám sát, dừng hoặc phục hồi migration dựa trên SLO, lock wait và ngân sách tài nguyên.

## 1. Vì sao DDL dưới tải cần được kiểm soát?

Tạo chỉ mục hoặc thay đổi cấu trúc bảng thường được gọi là DDL (Data Definition Language). Các thao tác như `CREATE INDEX`, `ALTER TABLE`, thêm cột, đổi kiểu dữ liệu, thêm constraint hoặc rebuild index có thể cần đọc và ghi lượng dữ liệu lớn, cập nhật catalog, giữ khóa hoặc tạo cấu trúc mới.

Trong module DATABASE_PERFORMANCE, vận hành hiệu năng không dừng ở tối ưu câu SQL. Một index mới có thể cải thiện truy vấn đọc nhưng làm INSERT/UPDATE/DELETE chậm hơn vì mỗi lần ghi phải duy trì thêm cấu trúc. Một thay đổi schema có thể hoàn tất nhanh ở môi trường ít tải nhưng gây blocking khi production có transaction dài. Một thao tác được gọi là online vẫn có thể cần khóa metadata trong một số giai đoạn.

Vì vậy, cần đánh giá đồng thời ba khía cạnh:

1. **Khả năng phục vụ:** truy vấn và giao dịch trực tuyến có tiếp tục chạy trong khi migration diễn ra không?
2. **Chi phí tài nguyên:** CPU, memory, I/O, log, temp space, network và replication có nằm trong ngân sách không?
3. **Khả năng triển khai an toàn:** ứng dụng cũ và mới có cùng hoạt động trong giai đoạn chuyển tiếp không, và có thể dừng hoặc phục hồi thế nào?

DDL dưới tải là một hoạt động vận hành có rủi ro và cần được thiết kế như một migration có quan sát, giới hạn và điều kiện dừng.

## 2. Phân loại thay đổi cấu trúc

Không phải mọi thay đổi schema đều có cùng chi phí.

| Loại thay đổi | Ví dụ | Chi phí hoặc rủi ro chính |
| --- | --- | --- |
| Tạo index | B-tree trên cột lọc hoặc khóa ngoại | Đọc bảng, sort, ghi index, log, I/O và ảnh hưởng giao dịch ghi |
| Xóa index | Bỏ index không còn dùng | Có thể cần khóa metadata; plan của query thay đổi ngay sau khi bỏ |
| Thêm cột | Thêm `source_code` | Có thể metadata-only hoặc cần rewrite tùy engine, version, default và kiểu dữ liệu |
| Đổi kiểu cột | `VARCHAR` sang kiểu khác | Có thể rewrite bảng, kiểm tra dữ liệu, khóa hoặc tăng log |
| Thêm constraint | CHECK, UNIQUE, FOREIGN KEY, NOT NULL | Scan/validate dữ liệu, tạo index phụ hoặc khóa trong một số giai đoạn |
| Đổi tên/bỏ cột | Rename/drop column | Ứng dụng phiên bản cũ có thể không tương thích; phụ thuộc metadata lock |
| Rebuild index | Tạo lại cấu trúc index | Đọc/ghi lớn, temp space, log và có thể cạnh tranh CPU/I/O |
| Repartition hoặc đổi storage layout | Chuyển partition, clustered layout | Di chuyển dữ liệu, cập nhật metadata, replication và cutover |

Trước khi chạy, hãy xác định thao tác thuộc loại nào, có rewrite dữ liệu hay không, có thể chạy đồng thời với DML không và cần bao nhiêu dung lượng tạm.

## 3. Các loại khóa cần hiểu

### Khóa dữ liệu

Khóa dữ liệu bảo vệ hàng, key, page hoặc phạm vi dữ liệu khi transaction đọc/ghi. DML như UPDATE hoặc DELETE thường cần khóa phù hợp để duy trì tính nhất quán. Một DDL có thể cần khóa rộng hơn tùy engine và loại thao tác.

### Khóa metadata hoặc schema

Metadata lock (MDL) hoặc schema lock bảo vệ định nghĩa bảng/index và đảm bảo các session không sử dụng cấu trúc đang bị thay đổi theo cách không an toàn. Một DDL có thể phải chờ transaction đang dùng bảng kết thúc trước khi lấy metadata lock cần thiết.

Điều này có nghĩa một câu SELECT dài hoặc transaction đã mở nhưng chưa commit có thể trì hoãn DDL. Ngược lại, DDL đang chờ metadata lock có thể tạo hàng đợi khiến các session đến sau cũng phải chờ, tùy cơ chế lock queue của engine.

### Khóa ngắn không đồng nghĩa không có blocking

Online/concurrent DDL thường giảm thời gian giữ khóa mạnh, nhưng có thể cần khóa ở đầu và cuối thao tác để chốt metadata hoặc xác nhận trạng thái. Nếu một transaction dài giữ lock tương thích không phù hợp, bước cutover có thể chờ.

Không chỉ hỏi 'DDL có online không?'. Hãy hỏi:

- Lock mode nào được dùng ở từng giai đoạn?
- DDL phải chờ transaction nào trước khi bắt đầu?
- DML có bị chặn trong lúc scan/build không?
- Có một giai đoạn ngắn cần khóa mạnh ở cuối không?
- Nếu lock không lấy được trong thời gian cho phép, thao tác chờ, timeout hay hủy?

## 4. Chi phí tài nguyên khi tạo index

Để xây index, database thường phải đọc dữ liệu của bảng, trích xuất khóa, sắp xếp hoặc tổ chức các entry, rồi ghi cấu trúc index mới. Chi tiết khác nhau theo engine, loại index, thuật toán và chế độ online.

Các nguồn chi phí:

- **CPU:** so sánh/sắp xếp key, nén, tính expression, kiểm tra uniqueness và cập nhật metadata.
- **Memory:** sort buffer, build workspace, parallel worker và cache.
- **Data I/O:** đọc heap/table hoặc index hiện có.
- **Index I/O:** ghi các page của index mới.
- **Temp I/O:** spill các run sort hoặc dữ liệu trung gian khi memory không đủ.
- **Log/WAL/redo:** ghi nhận thay đổi để phục hồi và replication.
- **DML overhead:** duy trì index mới hoặc ghi nhận thay đổi phát sinh trong lúc build.
- **Network/replication:** truyền log hoặc thay đổi sang replica.

Index lớn có thể cần thêm dung lượng gần với kích thước index cuối cùng, cộng thêm temp space, log và headroom. Không bắt đầu build khi storage gần đầy hoặc log backup/replica không thể theo kịp.

### Index build và workload ghi

Trong lúc tạo index, hệ quản trị có thể phải theo dõi thay đổi do INSERT/UPDATE/DELETE xảy ra đồng thời. Cơ chế này giúp index phản ánh dữ liệu mới nhất nhưng tạo thêm công việc.

Khi DML rate cao, build có thể chậm hơn, log tăng nhanh hoặc cần nhiều lần đồng bộ. Index mới cũng làm các giao dịch ghi sau này tốn thêm công sức.

### Chi phí lâu dài sau khi tạo index

Index không chỉ có chi phí một lần lúc build. Mỗi INSERT có thể thêm entry; UPDATE cột được index có thể sửa entry; DELETE cần đánh dấu hoặc loại bỏ entry theo cơ chế engine.

Do đó, sau khi tạo index hãy đo cả read benefit và write cost:

- Query latency, logical reads và rows examined của truy vấn được tối ưu.
- INSERT/UPDATE/DELETE throughput và commit latency.
- Index size, page split, fragmentation/bloat và cache residency.
- Log bytes per transaction và storage I/O.

## 5. Chi phí khi thay đổi schema

Thêm cột nullable không default có thể chỉ cần cập nhật metadata ở một số hệ quản trị/version, trong khi đổi kiểu dữ liệu hoặc thêm default có thể cần rewrite hoặc kiểm tra dữ liệu. Không được suy ra chi phí chỉ từ câu lệnh SQL ngắn.

Các câu hỏi cần xác minh:

- Thao tác có rewrite toàn bộ bảng hoặc từng partition không?
- Có scan dữ liệu để validate constraint không?
- Có tạo index ngầm hoặc rebuild clustered structure không?
- Có cần thêm dung lượng cho bản sao bảng/index mới không?
- DML có thể tiếp tục trong lúc thao tác không?
- Lock mode mạnh nhất xuất hiện ở thời điểm nào?
- Có giới hạn theo kiểu dữ liệu, engine, version hoặc edition không?

Ví dụ `ALTER TABLE ... ADD COLUMN ... DEFAULT ...` có thể có hành vi khác nhau giữa phiên bản PostgreSQL, MySQL và SQL Server. PostgreSQL hiện đại có thể tối ưu một số constant default thành thay đổi metadata, nhưng default có biểu thức volatile hoặc các dạng thay đổi khác có thể cần công việc lớn hơn. Hãy kiểm tra đúng phiên bản và thử trên bản sao dữ liệu đại diện.

## 6. Online DDL: hiểu đúng giới hạn

Online DDL là tên gọi chung cho các cơ chế cho phép một phần hoặc phần lớn hoạt động đọc/ghi tiếp tục trong lúc thay đổi cấu trúc. Nó không phải cam kết rằng không có lock, không có I/O spike hoặc không ảnh hưởng latency.

Đánh giá online DDL theo ma trận:

| Khía cạnh | Câu hỏi |
| --- | --- |
| Read availability | SELECT có tiếp tục không? |
| Write availability | INSERT/UPDATE/DELETE có tiếp tục không? |
| Lock phases | Đầu/cuối có cần lock mạnh hoặc metadata lock không? |
| Resource cost | CPU, memory, I/O, log và temp tăng bao nhiêu? |
| Concurrency | Thay đổi DML trong lúc build được ghi nhận ra sao? |
| Failure | Nếu build lỗi, index/table ở trạng thái nào? |
| Replication | Replica có theo kịp log và schema change không? |
| Compatibility | Ứng dụng phiên bản cũ có hoạt động với schema mới không? |

Trước khi triển khai production, xác nhận hành vi của đúng engine/version, không dựa vào tên option `ONLINE`, `CONCURRENTLY` hoặc `INPLACE`.

## 7. PostgreSQL: CREATE INDEX CONCURRENTLY

PostgreSQL hỗ trợ `CREATE INDEX CONCURRENTLY` để tạo index mà không khóa các thao tác INSERT/UPDATE/DELETE trong phần lớn quá trình build như cách tạo index thông thường. Cơ chế này thực hiện nhiều giai đoạn và scan, đồng thời chờ các transaction có thể ảnh hưởng đến tính hợp lệ của index.

Ví dụ:

```sql
CREATE INDEX CONCURRENTLY idx_orders_customer_created
ON orders (customer_id, created_at DESC);
```

Đặc điểm cần lưu ý:

- Không thể chạy `CREATE INDEX CONCURRENTLY` bên trong transaction block.
- Quá trình có thể lâu hơn tạo index thông thường do cần các giai đoạn kiểm tra và đồng bộ.
- DML tiếp tục nhưng phải chịu thêm công việc ghi cho index đang build và log.
- Một số loại index hoặc điều kiện đặc biệt có giới hạn riêng.
- Nếu thao tác thất bại, có thể để lại index ở trạng thái invalid; cần kiểm tra catalog và xử lý trước khi thử lại.

Kiểm tra trạng thái index:

```sql
SELECT
    indexrelid::regclass AS index_name,
    indisvalid,
    indisready
FROM pg_index
WHERE indexrelid = 'idx_orders_customer_created'::regclass;
```

`indisvalid` và `indisready` giúp nhận biết index có hợp lệ và sẵn sàng nhận cập nhật hay không. Nếu build lỗi, không giả định index có thể dùng như bình thường.

### Theo dõi tiến độ PostgreSQL

Ở các phiên bản hỗ trợ, `pg_stat_progress_create_index` cung cấp phase, blocks/tuples đã xử lý và tiến độ index build.

```sql
SELECT
    pid,
    command,
    phase,
    lockers_total,
    lockers_done,
    blocks_total,
    blocks_done,
    tuples_total,
    tuples_done
FROM pg_stat_progress_create_index;
```

Đối chiếu với `pg_stat_activity`, `pg_locks`, `pg_stat_io` hoặc metric I/O của hệ điều hành để tìm session chờ, CPU và storage pressure. Tên cột và metric có thể thay đổi theo phiên bản PostgreSQL.

### Lock timeout và thời gian chờ

PostgreSQL có `lock_timeout` để giới hạn thời gian một statement chờ khóa. Có thể đặt theo session/job trước khi thực hiện migration:

```sql
SET lock_timeout = '5s';
SET statement_timeout = '2h';

CREATE INDEX CONCURRENTLY idx_orders_status_created
ON orders (status, created_at);
```

Đây là ví dụ cấu hình cho session thực thi. Chọn timeout theo cửa sổ và chính sách vận hành. `statement_timeout` giới hạn thời gian statement; nó không thay thế ngân sách tài nguyên hoặc quy trình theo dõi.

Nếu DDL không lấy được lock cần thiết trong thời gian ngắn, thường tốt hơn là hủy và thử lại trong cửa sổ khác thay vì để một hàng đợi lock kéo dài.

### Xóa index

`DROP INDEX CONCURRENTLY` có thể giảm blocking khi xóa index, nhưng cũng có giới hạn transaction và cần xác minh dependency. Không xóa index chỉ vì thấy ít lượt dùng trong một cửa sổ ngắn; cần xem workload chu kỳ dài, constraint và kế hoạch phục hồi.

## 8. MySQL/InnoDB: ALGORITHM và LOCK

MySQL/InnoDB hỗ trợ nhiều thuật toán DDL, tùy thao tác và phiên bản:

- `INSTANT`: thay đổi metadata trong các trường hợp được hỗ trợ, không rebuild toàn bảng.
- `INPLACE`: thao tác được thực hiện trong engine mà không nhất thiết copy toàn bộ bảng; vẫn có thể đọc/ghi nhiều dữ liệu và tạo I/O.
- `COPY`: tạo bản sao/cấu trúc mới và copy dữ liệu; thường có chi phí storage và thời gian lớn hơn.

Ví dụ thêm index:

```sql
ALTER TABLE orders
    ADD INDEX idx_orders_customer_created (customer_id, created_at),
    ALGORITHM=INPLACE,
    LOCK=NONE;
```

Ví dụ này chỉ hợp lệ nếu thao tác, engine và phiên bản hỗ trợ combination đã yêu cầu. Nếu không hỗ trợ, MySQL có thể từ chối thay vì tự động bảo đảm một phương thức online khác. Hãy thử trước trên đúng phiên bản và kiểm tra execution behavior.

`LOCK=NONE` yêu cầu cho phép concurrent reads/writes trong quá trình được hỗ trợ; nó không có nghĩa không cần metadata lock. DDL vẫn cần metadata lock ở các giai đoạn, đặc biệt khi bắt đầu hoặc kết thúc.

### Metadata lock và transaction dài

MySQL giữ metadata lock khi session truy cập bảng trong transaction. Một transaction mở lâu có thể khiến DDL chờ. Khi DDL đang chờ MDL, các truy vấn mới có thể bị xếp hàng phía sau tùy lock scheduling, làm ảnh hưởng rộng hơn một session ban đầu.

Trước migration, kiểm tra transaction lâu, session idle in transaction, lock wait và metadata lock. Nếu DDL chờ, tìm blocker thay vì chỉ tăng timeout.

### Online DDL log và dung lượng

Trong một số online DDL, InnoDB ghi nhận thay đổi DML phát sinh trong lúc xây dựng cấu trúc. Online alter log có giới hạn; nếu lượng thay đổi vượt giới hạn, thao tác có thể thất bại. Việc build cũng cần temporary space, redo/undo và I/O.

Kiểm tra tham số như `innodb_online_alter_log_max_size` cùng dung lượng storage và tốc độ DML. Không tăng giới hạn chỉ để ép thao tác chạy nếu chưa tính log, temp và replica.

### Theo dõi MySQL

Dùng Performance Schema và metadata lock instrumentation phù hợp phiên bản, `SHOW PROCESSLIST`, `performance_schema.metadata_locks`, `performance_schema.events_stages_current` và metric InnoDB để xác định DDL đang ở giai đoạn nào, ai đang chặn và storage đang chịu tải ra sao.

Không phải mọi version đều cung cấp cùng event hoặc cột. Xác minh schema Performance Schema trên phiên bản thực tế.

## 9. SQL Server: ONLINE, MAXDOP và WAIT_AT_LOW_PRIORITY

SQL Server hỗ trợ online index operation cho một số loại index, edition và phiên bản. Khi online, bảng có thể tiếp tục phục vụ một số DML trong phần lớn quá trình rebuild, nhưng vẫn có các giai đoạn cần schema lock ngắn ở đầu/cuối và có thể có giới hạn tính năng.

Ví dụ:

```sql
ALTER INDEX IX_Orders_CreatedAt
ON dbo.Orders
REBUILD WITH (
    ONLINE = ON,
    MAXDOP = 2
);
```

`MAXDOP` giới hạn parallelism của thao tác. Mức thấp hơn có thể giảm CPU spike nhưng kéo dài thời gian rebuild. Mức cao có thể rút ngắn thời gian nhưng cạnh tranh CPU, memory và I/O với truy vấn nghiệp vụ.

### WAIT_AT_LOW_PRIORITY

Với online index operation được hỗ trợ, `WAIT_AT_LOW_PRIORITY` cho phép kiểm soát cách thao tác chờ khóa ưu tiên thấp trong một khoảng thời gian.

```sql
ALTER INDEX IX_Orders_CreatedAt
ON dbo.Orders
REBUILD WITH (
    ONLINE = ON (
        WAIT_AT_LOW_PRIORITY (
            MAX_DURATION = 5 MINUTES,
            ABORT_AFTER_WAIT = SELF
        )
    ),
    MAXDOP = 2
);
```

Ví dụ trên chọn hủy thao tác index nếu không lấy được lock trong khoảng chờ đã cấu hình. Cú pháp và hỗ trợ phụ thuộc phiên bản, edition và loại index. Chọn `ABORT_AFTER_WAIT` theo runbook; không tự động chọn phương án có thể hủy blocker nghiệp vụ.

### Resumable index operation

Một số phiên bản/edition SQL Server hỗ trợ resumable online index operation. Khi được hỗ trợ, thao tác có thể pause và resume thay vì phải bắt đầu lại từ đầu.

```sql
ALTER INDEX IX_Orders_CreatedAt
ON dbo.Orders
REBUILD WITH (
    ONLINE = ON,
    RESUMABLE = ON,
    MAX_DURATION = 30 MINUTES,
    MAXDOP = 2
);
```

Resumable operation không có nghĩa mọi DDL đều resumable. Cần xác nhận loại index và cú pháp được hỗ trợ, theo dõi trạng thái operation và hiểu tài nguyên/space được giữ khi pause.

### Log và tempdb

Rebuild index có thể tạo lượng transaction log đáng kể. Trong môi trường recovery model và availability group, cần tính log backup, log reuse wait, data movement và replica redo queue. `SORT_IN_TEMPDB` có thể chuyển sort work sang tempdb trong các trường hợp hỗ trợ; điều đó giảm một số áp lực trên filegroup chính nhưng tăng nhu cầu I/O và dung lượng tempdb.

Không dùng `ONLINE = ON` như bằng chứng rằng thao tác không ảnh hưởng workload. Đo lock, log, tempdb, CPU, I/O và replica lag.

## 10. Thêm constraint an toàn theo từng giai đoạn

Thêm `NOT NULL`, `UNIQUE` hoặc `FOREIGN KEY` có thể cần scan/validate dữ liệu hoặc khóa trong một số giai đoạn. Với bảng lớn, có thể tách thành nhiều bước để giảm thời gian khóa mạnh.

Mẫu tổng quát:

1. Kiểm tra dữ liệu hiện tại có vi phạm constraint dự kiến không.
2. Thêm cấu trúc hoặc constraint ở chế độ ít chặn nhất mà engine hỗ trợ.
3. Backfill hoặc sửa dữ liệu cũ theo batch.
4. Validate constraint bằng thao tác phù hợp.
5. Chuyển ứng dụng sang giả định mới sau khi constraint đã được xác nhận.

Ví dụ PostgreSQL có thể thêm CHECK constraint dạng `NOT VALID`, sau đó validate riêng:

```sql
ALTER TABLE orders
ADD CONSTRAINT orders_amount_nonnegative
CHECK (total_amount >= 0) NOT VALID;

ALTER TABLE orders
VALIDATE CONSTRAINT orders_amount_nonnegative;
```

Việc validate vẫn đọc dữ liệu và tiêu thụ I/O/CPU, nhưng tách khỏi bước thêm constraint giúp kiểm soát lock behavior tốt hơn. Cần kiểm tra lock mode và tác động theo phiên bản.

Với MySQL và SQL Server, cách thêm và validate constraint khác nhau. Không sao chép cú pháp PostgreSQL sang engine khác; hãy chọn quy trình tương ứng.

## 11. Expand-contract cho thay đổi schema tương thích ứng dụng

Expand-contract là chiến lược triển khai schema theo nhiều bước để phiên bản ứng dụng cũ và mới cùng hoạt động trong giai đoạn chuyển tiếp.

Ví dụ cần đổi cột `customer_name` thành `display_name`.

### Giai đoạn expand

- Thêm cột `display_name` mới, giữ cột cũ.
- Tạo index hoặc constraint mới nếu cần, theo cách online/concurrent phù hợp.
- Triển khai ứng dụng có thể đọc cột mới và fallback cột cũ.
- Nếu cần, ghi đồng thời hai cột trong giai đoạn tương thích.

### Giai đoạn migrate dữ liệu

- Backfill `display_name` từ `customer_name` theo batch nhỏ.
- Ghi nhận tiến độ và các hàng lỗi.
- Đảm bảo write mới không làm dữ liệu hai cột lệch nhau.
- Đối chiếu số hàng, null count và checksum/logic nghiệp vụ.

### Giai đoạn switch

- Chuyển đọc chính sang `display_name`.
- Theo dõi lỗi, latency và tính nhất quán.
- Dừng dual-write khi mọi ứng dụng/worker đã dùng cột mới.

### Giai đoạn contract

- Chờ hết phiên bản ứng dụng cũ và job cũ.
- Xác nhận không còn truy vấn tham chiếu cột cũ.
- Bỏ index/cột cũ trong một migration riêng có kiểm soát.

Không gộp tất cả thành một `ALTER TABLE` phá vỡ tương thích. Việc giữ schema cũ qua nhiều phiên bản cho phép rollback ứng dụng dễ hơn, nhưng cần kế hoạch đồng bộ dữ liệu và giới hạn thời gian dual-write.

## 12. Backfill theo batch

Backfill toàn bộ bảng trong một transaction lớn có thể giữ lock lâu, tạo lượng log lớn, làm replica lag và khiến rollback tốn kém. Chia thành batch giúp giới hạn công việc mỗi lần.

Ví dụ cập nhật cột mới theo key range:

```sql
UPDATE customers
SET display_name = customer_name
WHERE customer_id > :last_id
  AND customer_id <= :next_id
  AND display_name IS NULL;
```

Ứng dụng migration chọn khoảng ID kế tiếp, chạy UPDATE, commit, ghi checkpoint và tiếp tục. Cần index phù hợp trên khóa điều kiện, kiểm soát batch size và bảo đảm dữ liệu mới phát sinh trong lúc backfill cũng được cập nhật.

### Chọn batch size

Batch size quá lớn làm transaction log, lock duration, rollback và replication lag tăng. Batch size quá nhỏ làm tăng round trip, commit overhead và thời gian hoàn thành tổng thể.

Thử một số mức batch dựa trên:

- Số hàng mỗi batch.
- Thời gian transaction và lock wait.
- Log bytes sinh ra.
- IOPS, throughput và storage latency.
- Replica lag và thời gian apply.
- Foreground p95/p99.

Không cố định batch size theo một con số chung. Có thể điều chỉnh rate dựa trên metric, nhưng cần giới hạn min/max và thời gian ổn định trước khi tăng tốc.

### Idempotency và checkpoint

Job backfill cần chạy lại an toàn:

- Dùng điều kiện như `WHERE new_column IS NULL` nếu phù hợp nghiệp vụ.
- Ghi checkpoint sau khi batch commit thành công.
- Không đánh dấu batch hoàn tất trước commit.
- Có thể chạy lại batch mà không nhân đôi tác dụng phụ.
- Xử lý bản ghi thay đổi đồng thời và đảm bảo write path mới nhất quán.
- Ghi job ID, key range, số hàng cập nhật và lỗi.

## 13. Xây index theo đúng query workload

Không nên tạo index chỉ vì một cột xuất hiện trong WHERE. Hãy xác định query pattern, selectivity, sort order, join key và write rate.

Ví dụ:

```sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE tenant_id = ?
  AND status = ?
ORDER BY created_at DESC
LIMIT 50;
```

Một index composite có thể cân nhắc:

```sql
CREATE INDEX ... ON orders (tenant_id, status, created_at DESC);
```

Thứ tự cột cần dựa trên equality/range predicates, sort, cardinality và engine. Một index rộng làm tăng build time, storage và chi phí DML. Nếu query chỉ cần một số cột, covering/include columns có thể giảm lookup nhưng tăng kích thước index.

Trước khi build, thu thập baseline:

- Query fingerprint, frequency và p95/p99.
- Estimated/actual rows, logical reads và plan hiện tại.
- Index size, table size và write rate.
- Storage free space, log capacity và replica lag.

Sau khi build, kiểm tra query có thật sự dùng index không. Optimizer có thể chọn plan khác nếu statistics, parameter distribution hoặc cost model khiến index không có lợi.

## 14. Tránh tạo index trùng lặp hoặc dư thừa

Index có cùng prefix hoặc phục vụ query pattern tương tự có thể trùng lặp về công dụng. Mỗi index thêm vào làm tăng:

- Storage và backup size.
- CPU và I/O khi INSERT/UPDATE/DELETE.
- WAL/redo/transaction log.
- Buffer pool pressure và cache miss.
- Thời gian vacuum/purge/rebuild.

Trước khi tạo index, kiểm tra các index hiện có và query workload. Một index `(tenant_id, status, created_at)` có thể hỗ trợ một số truy vấn dùng prefix, nhưng không mặc nhiên thay thế index khác có thứ tự/cột include khác hoặc yêu cầu uniqueness.

Không xóa index chỉ dựa trên một metric usage ngắn hạn. Index có thể phục vụ tác vụ hàng tháng, constraint, foreign key hoặc truy vấn hiếm nhưng quan trọng. Dùng thời gian quan sát đủ dài và xác minh dependency.

## 15. Trước khi chạy migration: preflight

Một preflight tốt phải xác nhận cả dữ liệu, tài nguyên và trạng thái transaction.

### Kiểm tra dữ liệu và schema

- Kích thước bảng, index và partition.
- Số hàng và phân bố dữ liệu.
- Null, duplicate hoặc giá trị không hợp lệ với constraint mới.
- Index trùng lặp, index invalid hoặc index đang được build.
- Trigger, foreign key, view, procedure và ứng dụng phụ thuộc.

### Kiểm tra workload và khóa

- Active transaction và transaction chạy lâu.
- Session idle in transaction.
- Lock wait, blocker và deadlock gần đây.
- Query p95/p99 và throughput trong cửa sổ hiện tại.
- Job backup, ETL, vacuum/purge, checkpoint và batch khác.

### Kiểm tra tài nguyên

- Dung lượng data, log/WAL/redo và temp còn trống.
- CPU, memory, IOPS, throughput, latency và queue.
- Replica lag, log send/redo queue và khả năng apply.
- Connection/worker capacity.
- Dung lượng tăng thêm nếu cần copy/rebuild.

### Kiểm tra khả năng phục hồi

- Backup gần nhất và khả năng restore đã được kiểm tra.
- Migration có thể retry hoặc resume không?
- Nếu thất bại, có thể drop index mới hoặc tiếp tục build không?
- Schema có còn tương thích với ứng dụng hiện tại không?
- Có cách rollback/forward-fix rõ ràng không?

## 16. Lập ngân sách và giới hạn tác động

Trước khi bắt đầu, đặt ngân sách cho từng loại tài nguyên:

| Tài nguyên | Metric cần theo dõi | Cách giới hạn hoặc điều tiết |
| --- | --- | --- |
| CPU | Utilization, run queue, throttling | MAXDOP/parallel workers, job concurrency |
| Memory | Working set, memory grant, pressure, OOM | Maintenance memory, số worker, batch size |
| Data I/O | IOPS, MiB/s, latency, queue | I/O priority, rate limit, lịch chạy |
| Log | Log bytes/s, free space, backup/apply rate | Batch nhỏ, commit theo lô, theo dõi log backup |
| Temp | Temp space, sort spill, tempdb usage | Giới hạn concurrency và memory workspace |
| Locks | Lock wait, blocking duration, deadlocks | Online mode, lock timeout, batch, dừng khi vượt ngưỡng |
| Replication | Send/redo/apply lag | Giảm tốc, tránh chồng lấn, đợi replica hồi phục |
| Network | Throughput, RTT, retransmission | Giới hạn backup/replication bandwidth |

Đừng đặt ngưỡng chỉ dựa trên utilization trung bình. Ví dụ storage latency p99 có thể tăng mạnh dù average IOPS chưa chạm trần. Dùng SLO và baseline để đặt điều kiện cảnh báo/pause/stop.

## 17. Theo dõi tiến độ và tác động

Trong khi migration chạy, cần theo dõi cả tiến độ DDL và ảnh hưởng tới workload.

### Theo dõi migration

- Trạng thái và phase của index/schema operation.
- Số block/row đã xử lý và tổng số nếu engine cung cấp.
- Thời gian đã chạy, tốc độ tiến triển và ETA ước tính.
- Lock đang chờ và session blocker.
- Index validity hoặc operation state.
- Error, warning, retry và temporary object.

### Theo dõi foreground workload

- Goodput/throughput và request rate.
- p50/p95/p99 latency của truy vấn quan trọng.
- Connection acquisition và pool pending.
- Lock wait, deadlock và transaction duration.
- CPU, memory, I/O, log flush và temp usage.
- Replica lag và khả năng failover.

### Dấu hiệu cần giảm tốc hoặc dừng

- p95/p99 vượt SLO trong nhiều cửa sổ liên tiếp.
- DDL chờ metadata/schema lock và tạo blocking chain.
- Log hoặc temp space tiến gần ngưỡng nguy hiểm.
- Storage latency/queue tăng không hồi phục.
- Replica lag vượt ngưỡng vận hành.
- CPU throttling, memory pressure hoặc OOM xuất hiện.
- Index build lỗi hoặc index ở trạng thái invalid.

Điều kiện dừng phải được xác định trước khi chạy. Một thao tác DDL có thể không pause được giữa chừng; hủy có thể cần rollback hoặc cleanup đáng kể. Hãy biết hành vi hủy của đúng engine trước khi triển khai.

## 18. Lock timeout, statement timeout và retry

Timeout giúp tránh để migration chờ vô hạn, nhưng timeout không tự giải quyết nguyên nhân blocker.

Chính sách nên xác định:

- Thời gian tối đa chờ lock.
- Thời gian tối đa cho toàn thao tác.
- Có được retry không và sau bao lâu?
- Có thể retry toàn bộ migration hay phải kiểm tra trạng thái trước?
- Khi timeout, object đã được tạo một phần hay chưa?
- Ai quyết định tiếp tục, hủy hoặc chuyển cửa sổ?

Không retry mù quáng một DDL đã tạo một phần cấu trúc. Trước lần thử lại, kiểm tra catalog, index validity, operation state và log của lần trước.

Với thao tác không idempotent hoặc có side effect, cần script migration kiểm tra trạng thái hiện tại trước khi chạy. Tránh dùng `IF NOT EXISTS` như bảo đảm đầy đủ nếu cấu trúc index hiện hữu có thể khác định nghĩa mong muốn.

## 19. Rollback và forward recovery

Rollback của DDL phụ thuộc engine và loại thao tác. Một số DDL có transactional semantics; một số thao tác concurrent/online có giới hạn; một số migration đã thay đổi dữ liệu không thể đảo ngược đơn giản.

### Tạo index thất bại

- Kiểm tra index có tồn tại và trạng thái hợp lệ không.
- Xác định nguyên nhân: duplicate key, lock timeout, disk full, cancel hoặc replica/resource issue.
- Dọn index invalid hoặc object dở dang theo hướng dẫn engine.
- Chỉ chạy lại sau khi xác nhận không còn operation cũ và đủ ngân sách.

### Thay đổi schema đã được ứng dụng sử dụng

Nếu ứng dụng mới đã ghi dữ liệu vào cột mới, drop cột đó để rollback có thể làm mất dữ liệu. Trong tình huống này, forward-fix hoặc roll forward schema thường an toàn hơn rollback destructive.

Expand-contract cho phép giữ cột cũ trong giai đoạn chuyển tiếp. Nếu cần rollback ứng dụng, cột cũ vẫn còn và dữ liệu có thể được đồng bộ theo chiến lược đã thiết kế.

### Migration history

Lưu lại:

- Migration ID và phiên bản schema trước/sau.
- Thời gian bắt đầu/kết thúc và người/automation thực hiện.
- SQL hoặc artifact migration đã chạy.
- Engine/version và cấu hình online/lock.
- Kết quả, lỗi, retry và trạng thái object.
- Metric trước/trong/sau và quyết định pause/resume.

## 20. Ví dụ triển khai tạo index dưới tải

Giả sử API thường xuyên tìm đơn theo tenant, trạng thái và thời gian. Query hiện tại có logical reads cao và p95 vượt mục tiêu.

### Bước 1: xác nhận bằng chứng

```sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE tenant_id = ?
  AND status = ?
ORDER BY created_at DESC
LIMIT 50;
```

Xem query fingerprint, execution plan, actual rows, logical reads, sort và index hiện tại. Xác nhận query này có tần suất đủ lớn và index mới có thể cải thiện access path.

### Bước 2: ước lượng chi phí

- Kích thước bảng và số hàng.
- Kích thước index dự kiến.
- Tốc độ ghi vào bảng trong giờ chạy.
- Dung lượng temp/log còn trống.
- IOPS/throughput và replica capacity.
- Tác động lâu dài lên write throughput.

### Bước 3: chọn cách triển khai theo engine

PostgreSQL có thể cân nhắc `CREATE INDEX CONCURRENTLY`; MySQL/InnoDB cần xác nhận `ALGORITHM`/`LOCK` được hỗ trợ; SQL Server có thể cân nhắc `ONLINE = ON`, `MAXDOP` và low-priority wait nếu phù hợp.

Không dùng một câu lệnh chung cho mọi engine. Xác nhận phiên bản, edition, loại index và giới hạn trước khi chạy.

### Bước 4: chạy và giám sát

- Chạy trong cửa sổ có headroom.
- Theo dõi progress, lock wait và blocker.
- Theo dõi CPU, memory, I/O, log, temp và replica lag.
- So sánh foreground p95/p99 với baseline.
- Dừng hoặc giảm tốc nếu chạm ngưỡng đã đặt.

### Bước 5: xác minh lợi ích

- Index hợp lệ và optimizer có thể chọn.
- Query plan có access path phù hợp.
- Logical reads và p95/p99 giảm trên workload đại diện.
- Write latency và transaction throughput không suy giảm quá mức.
- Storage, backup và replication vẫn trong ngân sách.

## 21. Ví dụ thay đổi schema bằng expand-contract

Giả sử cần thay `orders.customer_name` bằng `orders.customer_display_name`.

### Expand

```sql
ALTER TABLE orders
ADD COLUMN customer_display_name VARCHAR(200) NULL;
```

Thêm cột nullable có thể là thao tác nhẹ ở một số engine/version, nhưng vẫn phải xác nhận lock và metadata behavior. Không giả định câu lệnh này luôn metadata-only.

Triển khai ứng dụng phiên bản A:

- Đọc cột mới nếu có giá trị, fallback sang cột cũ.
- Ghi cả hai cột trong cùng transaction.
- Không bỏ cột cũ.

### Backfill

Chạy job theo key range và commit từng batch. Theo dõi rows updated, log, lock, I/O và replica lag. Đảm bảo request mới ghi cả hai cột để backfill không tạo race condition.

### Switch

Triển khai phiên bản B chỉ đọc cột mới. Theo dõi error, null count và tính nhất quán giữa hai cột. Chỉ dừng dual-write khi không còn ứng dụng/worker cũ.

### Contract

Sau thời gian quan sát và xác nhận dependency, bỏ cột cũ trong một migration riêng. Kiểm tra view, report, ETL, trigger và ứng dụng quản trị trước khi drop.

## 22. Migration nhiều node hoặc replica

Trong hệ thống có replication, DDL có thể được áp dụng hoặc tái tạo trên replica theo cơ chế của sản phẩm. DDL tạo index lớn có thể sinh log đáng kể hoặc làm replica apply chậm.

Kiểm tra:

- DDL được chạy trên primary hay từng node?
- Replica nhận schema change theo log hay cần thao tác riêng?
- Có replica nào có version/extension khác không?
- Apply lag tăng bao nhiêu trong lúc build?
- Read traffic trên replica có bị ảnh hưởng?
- Failover trong lúc migration có thể xảy ra không?
- Sau failover, trạng thái DDL và migration coordinator ra sao?

Không giả định một migration đã thành công trên primary nghĩa là mọi replica sẵn sàng. Xác nhận schema version và index validity trên từng node theo cơ chế của hệ thống.

Với sharded database, cần giới hạn số shard chạy DDL đồng thời. Chạy trên tất cả shard cùng lúc có thể tạo đỉnh CPU/I/O và replication lag toàn cụm. Có thể triển khai theo wave hoặc canary shard, xác nhận kết quả rồi mới tiếp tục.

## 23. DDL trên hệ thống sharded

Trong hệ thống sharded, một migration logic có thể cần chạy trên hàng chục hoặc hàng trăm database node. Những rủi ro bổ sung gồm:

- Schema version không đồng nhất giữa shard.
- Một shard chậm hoặc lỗi khiến migration toàn cụm ở trạng thái một phần.
- DDL fan-out tạo tải lớn đồng thời.
- Query router gặp schema cũ và mới trong giai đoạn chuyển tiếp.
- Shard có kích thước dữ liệu rất khác nhau nên thời gian build khác nhau.

Thiết kế migration coordinator cần:

- Lưu trạng thái từng shard.
- Giới hạn concurrency theo wave.
- Retry riêng shard lỗi sau khi kiểm tra trạng thái.
- Chỉ đánh dấu hoàn tất toàn cụm khi mọi shard đạt version yêu cầu.
- Giữ ứng dụng tương thích với schema trong giai đoạn rollout.
- Có dashboard cho shard chậm, lock wait và resource usage.

Không dùng thời gian hoàn thành shard nhanh nhất làm ETA toàn cụm. Shard lớn nhất hoặc nóng nhất thường quyết định thời gian và rủi ro.

## 24. Kiểm chứng sau migration

Migration thành công về mặt DDL chưa chứng minh hiệu năng tốt hơn. Hãy xác minh:

### Tính đúng cấu trúc

- Index tồn tại, valid/usable và có định nghĩa đúng.
- Constraint được validate và enforcement theo yêu cầu.
- Column type, nullability, default và collation đúng.
- Schema version đồng nhất giữa application, worker, shard và replica.

### Hiệu năng truy vấn

- Optimizer có chọn index khi phù hợp không?
- Estimated rows và actual rows có hợp lý không?
- Logical reads, physical reads, CPU và elapsed time thay đổi thế nào?
- p50/p95/p99 của query quan trọng có cải thiện không?
- Query khác có bị plan regression không?

### Hiệu năng ghi và vận hành

- INSERT/UPDATE/DELETE throughput và commit latency.
- WAL/redo/log generation và backup duration.
- Storage latency, queue và free space.
- Replication lag và apply throughput.
- Index size, buffer cache residency và maintenance cost.

Chạy workload đọc/ghi hỗn hợp. Một index có thể cải thiện SELECT nhưng làm write path chậm hơn; quyết định cuối phải cân bằng tổng workload.

## 25. Những sai lầm thường gặp

- **Cho rằng online nghĩa là không khóa.** Online DDL vẫn có thể cần metadata/schema lock ở đầu hoặc cuối.
- **Chỉ xem thời gian DDL.** Tác động p95/p99, log, I/O và replica lag mới cho biết mức ảnh hưởng.
- **Chạy index build khi storage gần đầy.** Temp, log và index mới có thể làm hết dung lượng.
- **Không kiểm tra transaction dài.** Session giữ metadata lock có thể làm DDL chờ hoặc tạo blocking chain.
- **Tăng parallelism tối đa.** Build nhanh hơn nhưng có thể làm foreground CPU và I/O bão hòa.
- **Dùng `CONCURRENTLY`, `ONLINE` hoặc `INPLACE` mà không đọc giới hạn version.** Các option không có semantics giống nhau giữa engine.
- **Retry DDL mù quáng.** Lần chạy trước có thể đã tạo object invalid hoặc operation đang tiếp tục.
- **Backfill toàn bảng trong một transaction.** Log, lock, rollback và replication lag có thể tăng mạnh.
- **Đổi schema phá vỡ ứng dụng cũ ngay lập tức.** Deploy theo expand-contract để tương thích nhiều phiên bản.
- **Tạo index không dựa trên query plan.** Index mới có thể không được dùng hoặc làm write cost lớn hơn lợi ích.
- **Chỉ kiểm tra primary.** Replica hoặc shard khác có thể chưa hoàn tất migration.
- **Drop index theo usage ngắn hạn.** Có thể bỏ index phục vụ workload theo chu kỳ hoặc constraint.

## 26. Danh sách kiểm tra trước khi tạo index/đổi schema dưới tải

- [ ] Mục tiêu query hoặc thay đổi nghiệp vụ đã rõ.
- [ ] Có query fingerprint, execution plan và baseline latency/reads.
- [ ] Đã xác định engine, version, edition và tính năng DDL được hỗ trợ.
- [ ] Đã biết lock mode và các giai đoạn cần metadata/schema lock.
- [ ] Đã kiểm tra transaction dài, blocker và idle-in-transaction.
- [ ] Đã ước lượng index size, temp, log/WAL/redo và free space.
- [ ] Đã xác định CPU, memory, IOPS, throughput và replica budget.
- [ ] Đã chọn online/concurrent algorithm phù hợp và hiểu giới hạn.
- [ ] Có lock timeout, statement timeout và điều kiện dừng.
- [ ] Có kế hoạch xử lý index invalid hoặc DDL thất bại.
- [ ] Migration tương thích với phiên bản ứng dụng đang chạy.
- [ ] Backfill có batch size, checkpoint, idempotency và resume.
- [ ] DDL trên replica/shard có thứ tự và concurrency limit.
- [ ] Có metric theo dõi progress, lock, latency, log, I/O và replication.
- [ ] Có backup/recovery plan và người chịu trách nhiệm.
- [ ] Đã kiểm chứng query read benefit và write cost sau migration.

## Kết luận

Tạo index hoặc thay đổi schema dưới tải cần được xem là một migration có chi phí và trạng thái khóa cụ thể. Online/concurrent DDL có thể giữ phần lớn đọc/ghi tiếp tục nhưng vẫn cần metadata lock ở một số giai đoạn, đồng thời tiêu thụ CPU, RAM, I/O, log, temp space và replication capacity. PostgreSQL, MySQL/InnoDB và SQL Server có cơ chế và giới hạn khác nhau; phải xác minh đúng version, loại thao tác và hành vi khi thất bại. Hãy dựa trên execution plan và query workload để chọn index, triển khai schema theo expand-contract, backfill theo batch, giới hạn tài nguyên và theo dõi p95/p99, lock wait, log, storage và replica lag. Sau cùng, xác nhận cả lợi ích đọc lẫn chi phí ghi và tính tương thích của ứng dụng trước khi kết thúc migration.
