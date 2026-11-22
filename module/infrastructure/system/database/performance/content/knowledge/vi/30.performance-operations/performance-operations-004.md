# Quản lý thay đổi SQL, chỉ mục và cấu hình có kế hoạch hoàn tác

Một thay đổi SQL, index hoặc tham số cấu hình có thể cải thiện một truy vấn nhưng đồng thời làm tăng chi phí ghi, giữ khóa lâu hơn, tiêu thụ thêm dung lượng hoặc khiến workload khác chọn execution plan kém hơn. Trên môi trường production, thay đổi hiệu năng còn có thể ảnh hưởng nhiều ứng dụng cùng lúc, tạo tải I/O trong lúc xây dựng index, tăng transaction log hoặc làm gián đoạn kết nối khi cần restart database.

Vì vậy, thay đổi hiệu năng cần được quản lý như một hoạt động vận hành có kiểm soát. Trước khi triển khai phải xác định mục tiêu, bằng chứng, phạm vi, rủi ro, điều kiện tiên quyết, cách triển khai, metric theo dõi và ngưỡng dừng. Kế hoạch hoàn tác phải được chuẩn bị trước khi thay đổi bắt đầu, bao gồm cả trường hợp rollback không thể thực hiện bằng một câu lệnh đơn giản.

Trong phạm vi DATABASE_PERFORMANCE, bài học này tập trung vào quy trình thay đổi SQL, chỉ mục và cấu hình database; cách đánh giá tính đảo ngược; triển khai theo giai đoạn; xử lý migration tương thích; kiểm soát lock, log và replication; thiết lập rollback trigger; và xác minh sau triển khai. Mục tiêu là cải thiện hiệu năng mà vẫn bảo vệ tính đúng đắn của dữ liệu, tính sẵn sàng và SLO của workload.

## 1. Vì sao thay đổi hiệu năng cần kế hoạch hoàn tác?

Một tối ưu có thể có lợi ở một góc nhìn nhưng gây tác động khác ở toàn hệ thống:

- Thêm index giúp SELECT nhanh hơn nhưng làm INSERT/UPDATE/DELETE phải duy trì thêm cấu trúc.
- Viết lại SQL giảm số hàng đọc nhưng thay đổi semantics với NULL, collation hoặc thứ tự kết quả.
- Tăng memory grant giúp sort/hash ít spill nhưng có thể làm nhiều query đồng thời tranh bộ nhớ.
- Tăng connection limit giúp giảm pool wait ở ứng dụng nhưng làm DB nhận quá nhiều session và tăng contention.
- Tăng batch size làm throughput import cao hơn nhưng tạo transaction log burst và replica lag.
- Bật parallelism giúp một query hoàn tất nhanh hơn nhưng chiếm CPU của workload tương tác.
- Tạo index online giảm thời gian chặn DML nhưng vẫn tiêu thụ I/O, CPU, log và có thể chờ metadata lock.

Không có thay đổi nào chỉ cần đánh giá “trước chạy bao lâu, sau chạy bao lâu”. Cần đánh giá cả correctness, latency phân vị cao, throughput, error rate, tài nguyên, replication và khả năng phục hồi.

### Hoàn tác là một phần của thiết kế thay đổi

Rollback không phải việc nghĩ đến sau khi triển khai thất bại. Trước khi bắt đầu, người vận hành phải biết:

- Thay đổi nào có thể đảo ngược bằng lệnh hoặc migration ngược.
- Thay đổi nào cần khôi phục snapshot/backup hoặc chạy quy trình bù.
- Dữ liệu mới được ghi trong thời gian triển khai có tương thích với phiên bản cũ không.
- Có thể quay lại application version cũ mà vẫn đọc/ghi schema mới không.
- Cần bao lâu để rollback và ai có quyền quyết định.
- Điều kiện nào buộc phải dừng rollout ngay.

Một kế hoạch hoàn tác chỉ ghi “revert code” hoặc “drop index nếu chậm” là chưa đủ nếu chưa xác định tác động của dữ liệu, lock, thời gian thực thi và phụ thuộc.

## 2. Phân loại thay đổi theo phạm vi và rủi ro

Trước khi lập kế hoạch, hãy phân loại thay đổi:

| Loại thay đổi | Ví dụ | Rủi ro chính |
|---|---|---|
| SQL/application query | Thêm predicate, đổi join, batch query | Sai semantics, plan regression |
| Index | Tạo/drop/đổi index, filtered/partial index | Lock, I/O, storage, write amplification |
| Schema | Thêm cột, đổi kiểu, constraint, partition | Lock, rewrite dữ liệu, tương thích ứng dụng |
| Database configuration | Memory, parallelism, timeout, connection limit | Ảnh hưởng nhiều workload, cần restart |
| Runtime/pool | Pool size, timeout, routing | Connection storm, queue, failover |
| Statistics/plan management | Analyze, histogram, plan baseline/forcing | Optimizer chọn plan khác |
| Data migration | Backfill, deduplicate, re-key | Log, replication, correctness |

### Phân loại theo khả năng đảo ngược

- **Dễ đảo ngược:** thay đổi query trong một release có thể revert; tham số động có giá trị cũ đã lưu; thêm index có thể drop khi không còn phụ thuộc.
- **Đảo ngược có điều kiện:** thay đổi schema additive; index lớn cần thời gian để drop; cấu hình chỉ áp dụng sau restart; thay đổi routing cần chuyển traffic về.
- **Khó đảo ngược:** đổi kiểu dữ liệu có mất thông tin; xóa cột hoặc dữ liệu; hợp nhất/đổi khóa; backfill ghi đè giá trị; thay đổi format không tương thích.

Đừng đồng nhất “có lệnh ngược” với “rollback an toàn”. DROP INDEX có thể chặn hoặc tiêu thụ tài nguyên; khôi phục cột đã xóa cần backup; revert ứng dụng có thể không đọc được dữ liệu mới. Đánh giá cả thời gian, lock và trạng thái dữ liệu sau khi hoàn tác.

### Phân loại mức ảnh hưởng

Có thể đánh giá mức rủi ro theo:

- Số bảng, index, tenant và dịch vụ bị ảnh hưởng.
- Tần suất truy cập đối tượng thay đổi.
- Dung lượng dữ liệu cần scan/rewrite.
- Thời gian giữ lock và khả năng chặn ghi.
- Lượng log/redo/WAL dự kiến.
- Số replica và tốc độ apply.
- Khả năng rollback và thời gian khôi phục.
- Khả năng phát hiện sớm qua metric.

Thay đổi có phạm vi rộng hoặc khó đảo ngược cần review và diễn tập kỹ hơn. Không dùng một điểm số tổng hợp để che khuất rủi ro nghiêm trọng như mất dữ liệu hoặc không tương thích schema.

## 3. Bắt đầu từ bằng chứng và mục tiêu đo được

Một đề xuất thay đổi cần nêu vấn đề hiện tại bằng số liệu:

- Query fingerprint hoặc transaction nào chậm?
- p50/p95/p99 và throughput hiện tại là bao nhiêu?
- Query tiêu thụ tổng DB time, CPU, logical reads hoặc I/O ra sao?
- Execution plan có scan lớn, estimate sai, sort/hash spill hay join không phù hợp?
- Có lock wait, deadlock, pool wait hoặc replication lag không?
- Vấn đề xuất hiện ở mọi tenant hay chỉ nhóm dữ liệu có skew?

### Ví dụ giả thuyết thay đổi index

Truy vấn:

```sql
SELECT order_id, status, created_at
FROM orders
WHERE tenant_id = :tenant_id
  AND created_at >= :from_time
  AND created_at < :to_time
ORDER BY created_at DESC
LIMIT 100;
```

Ví dụ dùng cú pháp LIMIT phổ biến trong PostgreSQL/MySQL; SQL Server và Oracle có cú pháp giới hạn hàng riêng. Khi so sánh plan, hãy dùng đúng dialect và phiên bản DBMS đang vận hành.

Giả thuyết: index ghép trên (tenant_id, created_at) có thể giảm số hàng phải đọc vì tenant_id được lọc bằng equality và created_at bằng range. Trước khi triển khai cần kiểm tra selectivity, sort direction, index hiện có, kích thước index, chi phí ghi và plan với tenant lớn/nhỏ.

### Ví dụ giả thuyết thay đổi SQL

Nếu ứng dụng đang thực hiện N+1 query, có thể gom truy vấn thành một lần đọc theo danh sách ID. Mục tiêu không chỉ là giảm số query mà phải giữ nguyên:

- Quyền truy cập theo tenant/user.
- Thứ tự và tính đầy đủ của kết quả.
- Hành vi khi danh sách rỗng hoặc chứa ID trùng.
- Isolation và snapshot semantics.
- Cách xử lý NULL và bản ghi không tồn tại.

### Đặt tiêu chí thành công trước

Ví dụ:

| Metric | Baseline | Mục tiêu sau thay đổi |
|---|---:|---:|
| p95 query latency | 240 ms | dưới 140 ms |
| p99 API latency | 900 ms | không tăng quá 5% |
| Throughput thành công | 180 request/s | ít nhất 220 request/s |
| Error rate | 0,05% | không vượt 0,1% |
| DB CPU | 72% | dưới 80% ở tải mục tiêu |
| Replica lag | 1,5 s | dưới 5 s |

Các số liệu là ví dụ. Ngưỡng thực tế phải đến từ SLO, capacity budget và yêu cầu nghiệp vụ. Đừng chỉ đặt mục tiêu cho query được tối ưu; hãy đặt guardrail cho workload còn lại.

## 4. Hồ sơ thay đổi (change record)

Mỗi thay đổi production nên có một hồ sơ thống nhất để review và truy vết:

| Trường | Nội dung |
|---|---|
| Change ID | Mã duy nhất của thay đổi |
| Mục tiêu | Vấn đề và kết quả cần đạt |
| Phạm vi | DB, schema, bảng, query, service, tenant |
| Bằng chứng | Baseline, plan, metric, trace và benchmark |
| Nội dung thay đổi | SQL, DDL, config hoặc application version |
| Phụ thuộc | Driver, app release, replica, job, consumer |
| Rủi ro | Lock, log, I/O, compatibility, data correctness |
| Tiền điều kiện | Backup, disk headroom, replication health |
| Kế hoạch triển khai | Thứ tự, batch, canary, người thực hiện |
| Kế hoạch hoàn tác | Trigger, thao tác, thời gian, kiểm tra |
| Giám sát | Dashboard, alert, query fingerprint |
| Kết quả | PASS/FAIL, metric sau triển khai, ghi chú |

### Lưu trạng thái trước thay đổi

Trước khi thay đổi, lưu:

- DDL/schema và index definition hiện tại.
- Giá trị cấu hình hiện tại, scope và trạng thái dynamic/static.
- Query text/fingerprint và execution plan quan trọng.
- Số liệu latency, throughput, error, CPU, memory, I/O và lock.
- Replication topology/lag và trạng thái backup.
- Application version và migration version.

Giá trị cấu hình cũ cần được lưu chính xác, không dựa vào trí nhớ. Nếu thay đổi nhiều tham số cùng lúc, phải biết giá trị cũ của từng tham số và thứ tự phục hồi.

## 5. Chuẩn bị trước khi triển khai

Trước khi chạy DDL hoặc thay đổi cấu hình, kiểm tra:

1. **Backup và khôi phục:** backup gần nhất hợp lệ, đã kiểm tra khả năng restore theo yêu cầu.
2. **Dung lượng:** đủ disk cho index mới, temporary file, transaction log/WAL/redo và tăng trưởng trong lúc build.
3. **Replication:** replica khỏe, lag thấp, apply capacity còn dư và log retention đủ.
4. **Lock:** xác định loại lock DDL cần, thời gian chờ và đối tượng có transaction dài.
5. **Workload:** tránh trùng thời điểm với backup, batch, vacuum, ETL hoặc giờ cao điểm nếu rủi ro cao.
6. **Quyền:** tài khoản triển khai có đúng quyền cần thiết và có audit.
7. **Timeout:** lock timeout, statement timeout và job timeout được xác định.
8. **Monitoring:** dashboard/alert đã sẵn sàng trước khi bắt đầu.
9. **Rollback:** câu lệnh hoặc quy trình hoàn tác đã được review và ước lượng thời gian.
10. **Liên lạc vận hành:** người quyết định dừng/tiếp tục và người xử lý sự cố đã rõ.

### Kiểm tra transaction dài

DDL có thể phải chờ metadata lock hoặc lock mạnh. Một transaction idle lâu có thể khiến lệnh DDL chờ, hoặc chính DDL chặn các query mới sau khi lấy lock. Trước khi thay đổi, kiểm tra transaction age, blocker và session idle in transaction.

Không giải quyết bằng cách tùy tiện kill session. Xác định owner, tác động rollback, thời gian undo và chính sách ứng dụng trước khi kết thúc transaction.

## 6. Triển khai thay đổi SQL an toàn

Thay đổi SQL nên được kiểm chứng theo hai hướng: correctness và performance.

### Correctness trước hiệu năng

So sánh kết quả cũ/mới trên tập dữ liệu đại diện:

- Số hàng trả về.
- Giá trị từng cột hoặc checksum theo khóa.
- Xử lý NULL, duplicate và collation.
- Boundary của timestamp, timezone và range.
- Tenant/security predicate.
- Transaction isolation và consistency.
- Hành vi khi dữ liệu rỗng, lớn hoặc có giá trị ngoại lệ.

Nếu query mới dùng JOIN thay cho subquery, cần xác minh không nhân bản hàng khi quan hệ một-nhiều. Nếu dùng aggregate, kiểm tra GROUP BY và NULL. Nếu thay đổi pagination, xác định thứ tự ổn định và tie-breaker.

### Kiểm tra plan với nhiều parameter class

Một query có thể chạy tốt với tenant nhỏ nhưng chậm với tenant lớn. Kiểm thử:

- Giá trị phổ biến và hiếm.
- Tenant lớn/nhỏ.
- Range ngắn/dài.
- Danh sách ID nhỏ/lớn.
- Dữ liệu mới/cũ.
- NULL và giá trị biên.

Parameter sniffing/plan caching có thể làm một plan được tái sử dụng cho giá trị không phù hợp. Báo cáo cần nêu parameter class đã thử và cách DBMS quản lý plan.

### Triển khai theo application release

Nếu SQL mới nằm trong application code:

1. Đưa query mới vào release có thể bật/tắt bằng feature flag nếu phù hợp.
2. Chạy shadow/read-only comparison khi có thể, nhưng tránh tạo tải gấp đôi không kiểm soát.
3. Bật cho một tỷ lệ nhỏ request hoặc một nhóm tenant.
4. Theo dõi latency, error, rows và DB resource.
5. Tăng dần traffic nếu đạt ngưỡng.
6. Giữ đường quay lại query cũ trong thời gian canary.

Shadow query cần tránh side effect và cần giới hạn concurrency. Không chạy đồng thời hai phiên bản DML chỉ để so sánh kết quả.

### SQL hint và plan forcing

Hint hoặc plan forcing có thể hữu ích khi optimizer chọn plan không phù hợp, nhưng tạo thêm phụ thuộc vào dữ liệu, version và cấu hình. Trước khi áp dụng:

- Xác định nguyên nhân plan regression.
- Kiểm tra statistics và cardinality.
- Xác nhận plan tốt trên parameter class quan trọng.
- Ghi điều kiện gỡ hint/forcing.
- Theo dõi khi phân bố dữ liệu thay đổi.

Không dùng hint để che một index sai hoặc statistics lỗi mà không ghi rõ trade-off. Plan forcing cũng có thể giữ plan cũ khi dữ liệu đã thay đổi đáng kể.

## 7. Triển khai index: đánh giá trước khi tạo

Index mới có thể giảm reads nhưng phải trả chi phí:

- Storage và backup tăng.
- INSERT phải thêm entry.
- UPDATE cột được index có thể sửa index.
- DELETE phải loại bỏ entry.
- Cache cần giữ thêm page index.
- Build index đọc dữ liệu và ghi cấu trúc mới.
- Replication hoặc log có thể tăng tùy DBMS/cách triển khai.

Trước khi tạo index, kiểm tra:

- Index hiện có có prefix hoặc cấu trúc tương đương không.
- Query predicate, join, sort và selectivity.
- Thứ tự cột trong index ghép.
- Có cần covering/include column không.
- Có thể dùng partial/filtered index không.
- Cột thay đổi thường xuyên có làm write amplification lớn không.
- Index có thể thay thế index khác hay tạo trùng lặp.

### Không tạo index chỉ dựa trên một query plan

Một index giúp một query có thể làm các query khác chọn plan khác hoặc tăng chi phí ghi. Đánh giá workload tổng thể, index usage, query frequency và write mix.

### Ước lượng dung lượng

Kích thước index phụ thuộc kiểu dữ liệu, độ dài khóa, độ lặp, page fill, compression, include columns và DBMS. Dùng thử nghiệm trên bản sao dữ liệu hoặc thống kê phù hợp để ước lượng; dành headroom cho build và temporary space.

## 8. Tạo index online/concurrently theo DBMS

Các DBMS có cơ chế giảm blocking khi tạo index, nhưng “online” không có nghĩa không khóa hoặc không ảnh hưởng hiệu năng. Cú pháp, giới hạn và hỗ trợ phụ thuộc version, edition, storage engine và loại index.

### PostgreSQL

PostgreSQL hỗ trợ CREATE INDEX CONCURRENTLY:

```sql
CREATE INDEX CONCURRENTLY ix_orders_tenant_created
ON orders (tenant_id, created_at DESC);
```

Điểm cần lưu ý:

- CREATE INDEX CONCURRENTLY không chạy bên trong transaction block thông thường.
- Quá trình cần nhiều pha và có thể chờ transaction/snapshot cũ.
- Nó giảm mức chặn INSERT/UPDATE/DELETE so với CREATE INDEX thông thường nhưng vẫn tiêu thụ CPU/I/O và có thể ảnh hưởng workload.
- Nếu thất bại, có thể để lại index INVALID; cần kiểm tra trạng thái trước khi retry hoặc drop.
- Concurrent index build có thể tạo thêm I/O và WAL.

Với unique index, việc kiểm tra uniqueness trong quá trình build có semantics riêng; lỗi duplicate có thể làm build thất bại. Cần làm sạch dữ liệu trùng và xác nhận constraint trước.

Có thể kiểm tra trạng thái qua catalog/index validity hoặc progress view phù hợp phiên bản. Không chỉ nhìn câu lệnh kết thúc; phải xác minh index hợp lệ và plan sử dụng khi thích hợp.

### MySQL/InnoDB

MySQL hỗ trợ nhiều mức online DDL qua ALGORITHM và LOCK, ví dụ:

```sql
ALTER TABLE orders
    ADD INDEX ix_orders_tenant_created (tenant_id, created_at),
    ALGORITHM=INPLACE,
    LOCK=NONE;
```

Đây là cú pháp minh họa cho các phiên bản/engine hỗ trợ thao tác đó. Không phải mọi thay đổi index hoặc ALTER TABLE đều hỗ trợ ALGORITHM=INPLACE và LOCK=NONE. Một số thao tác có thể cần rebuild table hoặc lấy metadata lock ở đầu/cuối. Nếu yêu cầu thuật toán/lock không hỗ trợ, câu lệnh có thể báo lỗi thay vì tự chuyển sang cách khác tùy chỉ định.

Trước khi triển khai, kiểm tra tài liệu đúng phiên bản, EXPLAIN ALTER nếu phiên bản hỗ trợ, disk headroom, online DDL log và metadata lock. Một DDL online vẫn có thể chờ transaction cũ khi cần cập nhật metadata.

### SQL Server

SQL Server hỗ trợ tùy chọn ONLINE cho một số thao tác tạo/rebuild index, tùy phiên bản, edition, loại index và tính năng:

```sql
CREATE INDEX IX_Orders_Tenant_Created
ON dbo.Orders (TenantId, CreatedAt)
WITH (ONLINE = ON);
```

Không phải mọi index hoặc edition đều hỗ trợ ONLINE. Online operation vẫn cần lock ngắn ở các pha bắt đầu/kết thúc, dùng tài nguyên bổ sung và có thể bị chặn bởi transaction dài. Một số phiên bản hỗ trợ resumable index operation cho các trường hợp phù hợp; hãy kiểm tra cú pháp và giới hạn cụ thể trước khi dùng.

Theo dõi blocking, tempdb, transaction log, CPU/I/O và tiến độ index operation. Nếu dùng low-priority wait option, đặt chính sách MAX_DURATION và hành động khi hết thời gian rõ ràng.

### Oracle

Oracle hỗ trợ CREATE INDEX ... ONLINE trong các trường hợp phù hợp:

```sql
CREATE INDEX ix_orders_tenant_created
ON orders (tenant_id, created_at)
ONLINE;
```

ONLINE giảm một số dạng blocking DML nhưng vẫn có yêu cầu khóa ở các giai đoạn và giới hạn với loại đối tượng/operation. Theo dõi DDL lock, redo/undo, I/O và không gian. Với global/local index hoặc partitioned table, kiểm tra phạm vi index và maintenance.

### Quy tắc chung

- Xác nhận cú pháp với đúng DBMS version.
- Xác nhận operation thực sự online/concurrent.
- Xác định lock ở từng pha.
- Đo tài nguyên trong lúc build.
- Có giới hạn thời gian chờ lock và kế hoạch hủy.
- Xác minh index hợp lệ sau khi hoàn tất.
- Kiểm tra plan và write overhead sau triển khai.

## 9. Thêm, thay thế và xóa index theo giai đoạn

Nếu cần thay index cũ bằng index mới, không nhất thiết drop index cũ trước. Một quy trình an toàn hơn có thể:

1. Tạo index mới theo cách giảm blocking phù hợp.
2. Xác minh index hợp lệ.
3. Kiểm tra plan của workload mục tiêu và workload liên quan.
4. Theo dõi write latency, storage và cache.
5. Xác định index cũ không còn cần thiết bằng usage evidence trong một khoảng thời gian đủ đại diện.
6. Drop index cũ trong cửa sổ đã chọn.
7. Theo dõi sau khi drop và khôi phục nếu cần.

Giữ hai index cùng lúc làm tăng storage và write cost trong thời gian chuyển tiếp. Hãy tính phần chi phí này vào kế hoạch.

### Index trùng hoặc ít dùng

Không xóa index chỉ vì thống kê usage thấp trong một khoảng ngắn. Có thể index chỉ được dùng theo tháng, trong báo cáo cuối kỳ hoặc cho một tác vụ khẩn cấp. Kiểm tra:

- Query log/fingerprint theo chu kỳ nghiệp vụ.
- Constraint phụ thuộc index.
- Index có hỗ trợ unique/primary key không.
- Index có được dùng bởi FK hoặc maintenance job không.
- Thời gian thống kê usage và reset counter.

Index backing constraint không thể drop như index phụ thông thường nếu constraint còn cần. Phải xử lý constraint theo đúng quy tắc DBMS và nghiệp vụ.

## 10. Thay đổi cấu hình database

Thay đổi cấu hình cần xác định phạm vi áp dụng:

- Session: chỉ ảnh hưởng kết nối hiện tại.
- Transaction: chỉ có hiệu lực trong transaction.
- Database: áp dụng cho một database.
- Instance/server: ảnh hưởng nhiều database và session.
- Cluster: cần đồng nhất giữa các node hoặc có khác biệt có chủ đích.

Ngoài phạm vi, cần biết tham số có dynamic hay cần restart, giá trị hiện tại, giá trị mặc định, min/max và tương tác với tham số khác.

### Tham số động và tham số cần restart

Tham số động có thể đổi khi DB đang chạy, nhưng có thể ảnh hưởng ngay tới mọi query mới hoặc session. Tham số cần restart tạo rủi ro gián đoạn và phải có kế hoạch failover/maintenance window.

Không giả định tham số đổi bằng câu lệnh quản trị sẽ tự tồn tại sau restart. Một số DBMS phân biệt runtime value và persistent configuration file/parameter store.

### Thay đổi một nhóm nhỏ

Không thay 10 tham số cùng lúc rồi kết luận tham số nào cải thiện. Thay từng biến hoặc nhóm có quan hệ trực tiếp, đo lại và ghi rõ. Với tham số phụ thuộc nhau, thiết kế ma trận thử nghiệm và giữ cấu hình nhất quán.

### Ví dụ: giới hạn statement timeout trong PostgreSQL

Có thể đặt timeout theo transaction:

```sql
BEGIN;
SET LOCAL statement_timeout = '2s';

SELECT *
FROM orders
WHERE tenant_id = :tenant_id;
COMMIT;
```

SET LOCAL chỉ áp dụng trong transaction hiện tại và tự hết hiệu lực khi transaction kết thúc. Đây là cách giảm rủi ro thay đổi session state lâu dài cho một thao tác cụ thể. Tuy nhiên, timeout phải phù hợp SLA và query thực tế; đặt quá thấp có thể làm tăng lỗi và retry.

### Ví dụ: thay đổi tham số instance

Với PostgreSQL, một số tham số có thể thay đổi qua ALTER SYSTEM hoặc cấu hình server, nhưng hiệu lực phụ thuộc tham số và reload/restart. Với MySQL, SET GLOBAL và persistence option khác nhau theo version. SQL Server dùng sp_configure/RECONFIGURE cho nhiều tham số, một số cần restart. Oracle dùng ALTER SYSTEM và SPFILE/PFILE theo phạm vi tham số.

Các lệnh quản trị này không thể dùng thay thế lẫn nhau. Change record phải lưu lệnh đúng DBMS, giá trị runtime, giá trị persistent, phạm vi và cách phục hồi.

## 11. Đánh giá tác động của cấu hình lên workload

### Memory

Tăng memory cho sort/hash hoặc buffer cache có thể giảm I/O, nhưng tổng memory cần tính theo concurrency và số operation có thể cấp phát đồng thời. Một tham số per-query như work_mem trong PostgreSQL không phải ngân sách tổng cố định cho cả instance; nhiều sort/hash node và nhiều session có thể dùng đồng thời.

Đánh giá:

- Memory resident và peak.
- Swap/page fault.
- Sort/hash spill.
- Buffer hit và eviction.
- Memory grant wait hoặc pressure.
- Số query đồng thời.

### Parallelism

Tăng parallelism có thể rút ngắn một truy vấn nặng nhưng chiếm nhiều worker và CPU. Đánh giá cả throughput workload hỗn hợp, queue worker, CPU saturation và p99 của request nhỏ.

### Connection limit

Tăng max connection không đồng nghĩa tăng năng lực DB. Nhiều session hơn có thể làm tăng memory, context switching, lock contention và số query đồng thời. Xem connection pool, queue và DB active session trước khi đổi.

### Timeout

Timeout quá dài giữ connection và worker lâu khi DB đã nghẽn. Timeout quá ngắn gây lỗi và retry. Đặt timeout theo tầng: acquire, statement, transaction và request; đảm bảo deadline truyền xuống DB và retry không vượt tổng deadline.

### Durability và commit

Thay đổi synchronous commit, flush policy hoặc log durability có thể ảnh hưởng latency nhưng cũng thay đổi mức bảo vệ dữ liệu khi crash. Không thay đổi durability chỉ để cải thiện benchmark nếu chưa có phê duyệt rõ về RPO và yêu cầu mất dữ liệu chấp nhận được.

## 12. Migration schema tương thích với nhiều phiên bản ứng dụng

Một thay đổi schema có thể triển khai khi nhiều phiên bản ứng dụng cùng chạy trong rolling deployment. Chiến lược expand-contract giảm nguy cơ ứng dụng cũ không hiểu schema mới.

### Expand

Thêm cấu trúc mới theo cách tương thích:

- Thêm cột nullable hoặc có default phù hợp.
- Tạo bảng/index mới.
- Thêm constraint theo chế độ có thể kiểm tra trước nếu DBMS hỗ trợ.
- Giữ cột và đường đọc cũ.

### Migrate

- Deploy ứng dụng có thể ghi/đọc cấu trúc mới.
- Backfill dữ liệu theo batch có checkpoint.
- Có thể dual-write tạm thời nếu thiết kế bảo đảm consistency và idempotency.
- Đối chiếu dữ liệu cũ/mới.
- Theo dõi lag và lỗi.

### Switch

- Chuyển read path sang cấu trúc mới theo feature flag hoặc canary.
- So sánh kết quả và metric.
- Tăng dần traffic.
- Giữ khả năng quay lại read path cũ trong thời gian xác nhận.

### Contract

Chỉ sau khi mọi application version và job đã ngừng dùng cấu trúc cũ mới:

- Ngừng ghi cột/bảng cũ.
- Xác nhận không còn query phụ thuộc.
- Drop cột/index/bảng cũ trong change riêng.
- Giữ backup/retention theo chính sách.

Không gộp expand, backfill, switch và drop vào một deployment khó rollback. Tách các bước giúp mỗi bước có thể quan sát và dừng.

### Ví dụ đổi tên cột

Thay vì rename cột ngay khi ứng dụng cũ còn chạy:

1. Thêm cột mới.
2. Deploy code ghi cả hai cột hoặc dùng compatibility layer.
3. Backfill cột mới từ cột cũ theo batch.
4. Đối chiếu dữ liệu.
5. Chuyển read path sang cột mới.
6. Ngừng ghi cột cũ.
7. Xác nhận không còn client cũ.
8. Drop cột cũ ở change riêng.

Dual-write có thể tạo lệch nếu một lần ghi thành công một cột nhưng thất bại cột còn lại. Hãy dùng transaction chung trong DB hoặc outbox/reconciliation nếu ghi qua hệ thống khác.

## 13. Backfill và migration dữ liệu có kiểm soát

Backfill có thể đọc/ghi hàng triệu bản ghi. Không chạy một UPDATE lớn nếu chưa đánh giá log, lock và replica:

```sql
UPDATE orders
SET normalized_code = LOWER(TRIM(external_code))
WHERE normalized_code IS NULL;
```

Với bảng lớn, chia batch theo khóa ổn định:

```sql
UPDATE orders
SET normalized_code = LOWER(TRIM(external_code))
WHERE order_id > :last_id
  AND order_id <= :next_id
  AND normalized_code IS NULL;
```

Ví dụ cần điều chỉnh theo DBMS, khóa và dữ liệu thực tế. Nếu có bản ghi được cập nhật đồng thời, predicate normalized_code IS NULL giúp tránh ghi đè một giá trị đã được ứng dụng mới tạo. Cần kiểm tra idempotency và checkpoint.

### Điều tiết backfill

- Batch size nhỏ ban đầu.
- Giới hạn worker/concurrency.
- Commit từng batch.
- Theo dõi WAL/redo/transaction log và replica lag.
- Giảm tốc khi workload trực tuyến suy giảm.
- Tránh trùng backup, index build hoặc maintenance nặng.
- Ghi checkpoint cùng batch hoặc dùng trạng thái có thể phục hồi.

### Xác minh backfill

Kiểm tra:

- Số hàng còn thiếu.
- Count theo partition/tenant.
- Giá trị NULL và duplicate.
- Checksum hoặc đối chiếu theo khóa.
- Các invariant nghiệp vụ.
- Query mới trả kết quả tương đương.

Không đánh dấu migration hoàn tất chỉ vì job kết thúc exit code 0. Phải kiểm tra dữ liệu và metric.

## 14. Kế hoạch hoàn tác theo loại thay đổi

Rollback plan phải cụ thể và có thể thực hiện được.

| Thay đổi | Hướng hoàn tác | Điều cần kiểm tra |
|---|---|---|
| SQL trong ứng dụng | Revert release/feature flag về query cũ | Schema và dữ liệu vẫn tương thích |
| Index mới | Drop index nếu an toàn | Lock, thời gian drop, constraint và query phụ thuộc |
| Index cũ bị drop | Recreate hoặc restore theo DDL | Thời gian build và tải I/O |
| Tham số động | Đặt lại giá trị đã lưu | Giá trị runtime/persistent và tác động session |
| Tham số cần restart | Khôi phục config và restart/failover | Downtime, cluster consistency |
| Cột/bảng additive | Ứng dụng quay về đường cũ; giữ schema mới tạm thời | Code cũ có tương thích schema mở rộng |
| Backfill additive | Dừng job, giữ dữ liệu đã backfill | Có thể tiếp tục idempotent hoặc xóa phần đã ghi |
| Data rewrite/mất thông tin | Restore/point-in-time recovery hoặc migration bù | RPO/RTO, log retention và dữ liệu phát sinh sau mốc |
| Routing/pool | Chuyển traffic về pool/route cũ | Session affinity và connection draining |

### Rollback và roll-forward

Rollback đưa hệ thống về trạng thái trước. Roll-forward sửa lỗi bằng một thay đổi mới trong khi giữ dữ liệu hiện tại. Với migration dữ liệu lớn hoặc schema additive, roll-forward thường ít rủi ro hơn khi rollback sẽ làm mất dữ liệu đã được ứng dụng mới ghi.

Ví dụ, nếu cột mới đã nhận dữ liệu hợp lệ, không nên drop cột ngay chỉ để quay về ứng dụng cũ. Có thể chuyển application read path về cột cũ, giữ hai cột đồng bộ, điều tra và sửa forward.

### Phân biệt rollback code và rollback data

Revert application code không tự đảo ngược DDL hoặc dữ liệu đã ghi. Một release có thể bị rollback nhưng schema vẫn ở phiên bản mới. Đây là lý do migration phải tương thích ngược trong giai đoạn rolling deployment.

### Không chạy migration ngược mù quáng

Migration down có thể:

- Drop dữ liệu mới.
- Cắt cụt độ chính xác khi chuyển kiểu.
- Gây lock/rewrite lớn.
- Không khôi phục giá trị cũ đã bị ghi đè.
- Vi phạm foreign key hoặc uniqueness.

Review migration down như một thay đổi độc lập. Nếu không thể đảo ngược an toàn, ghi rõ điều đó và chuẩn bị roll-forward/restore plan.

## 15. Định nghĩa rollback trigger trước khi rollout

Rollback trigger là điều kiện quan sát được khiến rollout phải dừng hoặc đảo ngược. Ví dụ:

- p95/p99 vượt SLO trong một khoảng thời gian đã định.
- Error rate vượt ngưỡng.
- Deadlock/lock timeout tăng vượt baseline.
- CPU, I/O latency hoặc memory pressure vượt budget.
- Connection pool wait tăng liên tục.
- Replica lag vượt ngưỡng hoặc không bắt kịp.
- Transaction log/WAL/redo gần hết dung lượng hoặc tăng bất thường.
- Query plan regression làm DB time tăng đáng kể.
- Kết quả query sai, thiếu hàng hoặc vi phạm invariant.
- Ứng dụng cũ không tương thích schema.

### Trigger phải có thời gian và phạm vi

Một spike 5 giây có thể là nhiễu; p99 tăng liên tục 10 phút có thể là vấn đề. Ghi rõ:

- Metric và nguồn đo.
- Ngưỡng.
- Cửa sổ đánh giá.
- Số lần liên tiếp vượt ngưỡng.
- Phạm vi ảnh hưởng (toàn hệ thống, tenant, query class).
- Người có quyền quyết định.
- Hành động tự động hay thủ công.

Không dùng một ngưỡng CPU duy nhất để rollback mọi thay đổi. CPU có thể tăng nhẹ nhưng latency và error vẫn đạt; ngược lại, lock wait có thể gây sự cố khi CPU thấp.

### Trigger correctness luôn ưu tiên

Nếu phát hiện sai dữ liệu, vi phạm tenant isolation, duplicate không mong muốn hoặc mất transaction, dừng rollout ngay theo quy trình sự cố. Không chờ đủ cửa sổ latency.

## 16. Canary và triển khai theo giai đoạn

Canary giới hạn phạm vi ảnh hưởng ban đầu để quan sát trước khi mở rộng.

Một rollout có thể chia:

1. Development/test: kiểm tra syntax, correctness và plan.
2. Staging: chạy workload gần production, kiểm tra lock và log.
3. Một replica hoặc một shard/tenant phù hợp: thử trong phạm vi cô lập.
4. Một tỷ lệ nhỏ traffic: ví dụ 1–5%, nếu kiến trúc hỗ trợ.
5. Tăng dần: 10%, 25%, 50%, 100% theo các cửa sổ quan sát.
6. Theo dõi sau rollout: xác nhận hiệu năng ổn định qua chu kỳ workload.

Tỷ lệ và thời gian là ví dụ. Thay đổi DDL toàn database có thể không hỗ trợ canary theo request; khi đó canary có thể là một shard, tenant, replica hoặc môi trường đại diện.

### Không tăng traffic khi chưa đủ dữ liệu

Mỗi giai đoạn cần đủ request để đánh giá latency percentile và lỗi. Với workload theo giờ/ngày, cửa sổ canary phải bao phủ chu kỳ liên quan. Không tăng 100% chỉ vì 100 request đầu tiên đều thành công.

### Feature flag cho SQL path

Feature flag có thể chọn query cũ/mới theo tenant hoặc tỷ lệ traffic. Cần bảo đảm:

- Flag có default an toàn.
- Có thể chuyển lại nhanh.
- Cả hai query path cùng đúng semantics.
- Không tạo hai lần ghi.
- Metric phân tách theo flag/version.
- Flag không bị giữ vĩnh viễn sau khi rollout hoàn tất.

## 17. Giám sát trong và sau thay đổi

Dashboard phải được chuẩn bị trước deployment. Theo dõi cả metric của query mục tiêu và guardrail toàn hệ thống.

### Metric truy vấn

- Calls và total DB time.
- Mean/p50/p95/p99 latency.
- Rows returned/affected.
- Logical/physical reads.
- Plan ID/fingerprint và plan change.
- Sort/hash spill.
- Error, timeout và retry.

### Metric database và host

- CPU, memory, swap và I/O latency.
- Buffer cache hit/eviction.
- Lock wait, deadlock và transaction age.
- Active/idle session và pool wait.
- WAL/redo/undo/log generation và flush latency.
- Checkpoint, vacuum/purge và statistics.
- Replica send/receive/apply lag.
- Disk free và temporary space.

### Metric ứng dụng

- Request rate và success rate.
- p50/p95/p99 end-to-end.
- Queue depth và worker saturation.
- Connection acquisition/hold time.
- Timeout và retry count.
- Canary cohort so với control cohort.

### So sánh với baseline

Dùng cùng time window và phân loại workload. Nếu traffic sau triển khai tăng gấp đôi, không so sánh raw query count mà không chuẩn hóa theo request hoặc transaction. Ghi cả tỷ lệ và tổng giá trị để tránh kết luận sai.

## 18. Xác minh sau triển khai

Sau khi thay đổi, xác minh theo ba lớp:

### 1. Trạng thái kỹ thuật

- Migration hoàn tất.
- Index hợp lệ/visible/usable theo DBMS.
- Config runtime và persistent đúng giá trị.
- Replica đã áp dụng thay đổi hoặc bắt kịp.
- Không còn DDL/job bị treo.

### 2. Tính đúng đắn

- Query mới trả cùng kết quả theo quy tắc nghiệp vụ.
- Count/checksum hoặc invariant không đổi ngoài dự kiến.
- Unique/FK/check constraint được bảo toàn.
- Tenant/security filter vẫn áp dụng.
- Transaction commit/rollback đúng.

### 3. Hiệu năng

- Metric mục tiêu cải thiện theo giả thuyết.
- Guardrail không vượt ngưỡng.
- Workload khác không bị regression.
- Index write overhead và storage được chấp nhận.
- Không có replication backlog kéo dài.
- Kết quả ổn định qua thời gian quan sát.

### Xác minh index được sử dụng

Index tồn tại không có nghĩa optimizer sẽ dùng. Kiểm tra plan của query với parameter đại diện. Nếu optimizer vẫn chọn scan, có thể đó là lựa chọn hợp lý do selectivity hoặc kích thước bảng; không ép dùng index chỉ để chứng minh DDL có tác dụng.

### Xác minh config thực sự có hiệu lực

Đọc lại runtime value và persistent value theo DBMS. Một số tham số chỉ áp dụng cho session mới; một số cần reload/restart; một số có thể bị ghi đè bởi config management. Xác minh trên tất cả node liên quan.

## 19. Xử lý khi thay đổi gây regression

Khi metric vượt ngưỡng:

1. Dừng tăng rollout và đóng feature flag nếu có.
2. Xác định phạm vi cohort/tenant/query bị ảnh hưởng.
3. So sánh metric với baseline cùng tải.
4. Kiểm tra plan, statistics, lock, I/O, memory, log và pool.
5. Quyết định rollback hay roll-forward dựa trên tính tương thích dữ liệu.
6. Thực hiện hành động đã chuẩn bị, không tự tạo migration ngược chưa review.
7. Xác minh hệ thống ổn định và dữ liệu đúng.
8. Ghi timeline, metric và nguyên nhân đã xác nhận.

### Ví dụ: index build làm tăng latency

Nếu tạo index online khiến I/O tăng và p99 API vượt ngưỡng:

- Dừng các index build tiếp theo.
- Kiểm tra tiến độ build, disk, I/O queue và query latency.
- Nếu build có thể hủy an toàn theo DBMS, đánh giá tác động và trạng thái index sau hủy.
- Nếu build đã hoàn tất, quyết định giữ hay drop dựa trên write/read benefit và chi phí; drop cũng có thể cần tài nguyên/lock.
- Chờ I/O và replication ổn định trước khi tiếp tục.

Không mặc định hủy ngay là không có tác động. Một build bị hủy có thể để lại trạng thái index invalid hoặc cần cleanup.

### Ví dụ: tham số memory gây pressure

Nếu tăng memory grant làm nhiều query đồng thời dùng quá nhiều RAM:

- Dừng rollout cấu hình hoặc giảm concurrency.
- Đặt lại giá trị đã lưu nếu tham số có thể đổi động.
- Nếu cần restart, theo kế hoạch node/failover.
- Theo dõi swap, memory grant, spill và p99 sau phục hồi.
- Xác minh config không bị persistence layer ghi lại giá trị mới.

### Ví dụ: SQL mới trả sai kết quả

Nếu query mới thiếu predicate tenant hoặc join làm nhân đôi hàng:

- Tắt query path mới ngay.
- Quay lại query cũ nếu schema tương thích.
- Xác định dữ liệu nào đã được ghi bằng logic sai.
- Đối soát và chạy corrective migration có kiểm soát.
- Thêm kiểm thử correctness trước khi bật lại.

Hiệu năng tốt không thể bù cho sai dữ liệu hoặc vi phạm quyền truy cập.

## 20. Đặc thù rollback của DDL và cấu hình theo DBMS

### PostgreSQL

Nhiều DDL PostgreSQL có thể chạy trong transaction, nhưng không phải mọi lệnh. CREATE INDEX CONCURRENTLY và DROP INDEX CONCURRENTLY không chạy trong transaction block thông thường. Vì vậy, không thể luôn gói DDL và thay đổi trạng thái ứng dụng trong một transaction duy nhất.

Rollback một index mới thường là drop index, nhưng cần chọn dạng drop phù hợp và kiểm tra lock. Nếu concurrent build thất bại, xác minh index validity trước khi retry. Với schema migration có dữ liệu, transaction rollback chỉ đảo được thay đổi nằm trong transaction; side effect bên ngoài và thao tác không transactional cần xử lý riêng.

### MySQL

Nhiều DDL gây implicit commit; không giả định ROLLBACK sẽ hoàn tác ALTER TABLE hoặc CREATE INDEX. Online DDL có giới hạn theo operation/engine/version và có thể cần metadata lock. Rollback thường là một DDL ngược, có thể mất thời gian và tài nguyên.

Nếu dùng gh-ost hoặc pt-online-schema-change, kế hoạch rollback phải xét bảng shadow, trigger, replication, cutover và cleanup theo công cụ/version. Không chạy đồng thời nhiều schema migration trên cùng bảng nếu chưa đánh giá metadata lock và replica.

### SQL Server

Một số DDL có thể nằm trong transaction, nhưng khả năng rollback và chi phí log phụ thuộc operation. Online/resumable index operation có trạng thái và cú pháp riêng. Khi hủy hoặc pause, kiểm tra trạng thái operation và cleanup; không giả định lệnh đã dừng đồng nghĩa mọi tài nguyên đã được giải phóng.

Thay đổi cấu hình qua sp_configure có thể có runtime/persistent behavior riêng. Ghi lại giá trị cấu hình, dùng RECONFIGURE theo đúng quy trình và kiểm tra tham số cần restart.

### Oracle

Oracle DDL thường có implicit commit trước/sau thao tác theo semantics của Oracle. Không dựa vào ROLLBACK để đảo CREATE/ALTER/DROP. Rollback DDL thường là DDL bù, restore hoặc flashback/point-in-time recovery tùy loại thay đổi và cấu hình.

Với index online, kiểm tra trạng thái index và DDL lock. Thay đổi tham số có thể ở memory, SPFILE hoặc PFILE; cần biết scope và cách phục hồi qua restart.

## 21. Ví dụ change plan hoàn chỉnh: thêm index cho truy vấn nóng

### Bối cảnh

API tìm đơn hàng theo tenant có p95 280 ms ở giờ cao điểm. Plan hiện tại đọc nhiều hàng rồi lọc và sort. Giả thuyết là index ghép (tenant_id, created_at DESC) giảm logical reads và sort work.

### Trước thay đổi

- Ghi query fingerprint, p50/p95/p99 và throughput.
- Lưu execution plan, actual rows, logical reads và sort spill.
- Kiểm tra index hiện có và constraint.
- Đo insert/update latency trên orders.
- Ước lượng index size và disk headroom.
- Kiểm tra replica lag, backup window và DDL lock.
- Chuẩn bị DDL concurrent/online phù hợp DBMS.
- Chuẩn bị câu lệnh drop index và cách xử lý nếu build lỗi.

### Triển khai

1. Chọn cửa sổ tải thấp hoặc thời điểm có headroom.
2. Chạy DDL theo cơ chế online đã xác minh.
3. Theo dõi build progress, CPU, I/O, log, disk và lock.
4. Xác minh index hợp lệ.
5. Chạy query với nhiều tenant/parameter class.
6. Bật query path hoặc workload mục tiêu ở canary.
7. Theo dõi read latency, write latency, error và replica.
8. Tăng dần phạm vi khi đạt ngưỡng.

### Rollback trigger

- p99 API tăng trên 15% so với baseline trong 10 phút ở tải tương đương.
- Error rate vượt 0,1%.
- Replica lag vượt 5 giây và không giảm.
- Disk headroom thấp hơn ngưỡng vận hành.
- Write latency tăng vượt SLO.
- Kết quả query sai hoặc plan regression ảnh hưởng workload khác.

Các ngưỡng là ví dụ cần thay bằng SLO thực tế.

### Hoàn tác

- Nếu query path mới là nguyên nhân, tắt feature flag và quay lại SQL cũ.
- Nếu index build chưa hoàn tất, hủy theo cơ chế DBMS và xác minh trạng thái.
- Nếu index đã hoàn tất nhưng gây write/storage regression không chấp nhận được, drop theo quy trình đã review.
- Nếu drop có rủi ro lock/tải, đánh giá cửa sổ và không thực hiện đồng thời với sự cố khác.

### Sau triển khai

- So sánh plan và metric ở cùng workload.
- Xác nhận p95 mục tiêu cải thiện.
- Xác nhận p99, write latency, error, CPU/I/O và replication không vượt guardrail.
- Theo dõi đủ chu kỳ nghiệp vụ.
- Cập nhật change record với kết quả, quyết định giữ index và lý do.

## 22. Ví dụ change plan: thay đổi cấu hình memory

### Bối cảnh

Một workload report có sort/hash spill ra disk. Nhóm muốn tăng memory cấp cho mỗi operation để giảm spill.

### Phân tích trước

- Xác định query fingerprint gây spill và số operation đồng thời.
- Đo memory grant/work_mem hiện tại, peak memory và swap.
- Kiểm tra số sort/hash node mỗi query.
- Ước lượng tổng memory trong kịch bản concurrency cao.
- Xác định tham số có scope session/database/instance và dynamic hay restart.
- Chọn một nhóm report hoặc session thử nghiệm nếu có thể.

### Rollout

1. Thử trên staging với workload hỗn hợp.
2. Đặt giá trị theo scope hẹp nhất đáp ứng mục tiêu.
3. Canary một nhóm report hoặc connection.
4. Theo dõi spill, memory pressure, swap, CPU và p99 API.
5. Tăng dần phạm vi nếu memory headroom vẫn an toàn.

### Rollback

- Đặt lại giá trị cũ ở đúng scope.
- Nếu tham số cần restart, dùng quy trình restart/failover đã phê duyệt.
- Xác minh runtime và persistent configuration.
- Kiểm tra session cũ có giữ giá trị riêng hay không.

Không tăng memory cho mọi query nếu chỉ một report cần thêm tài nguyên. Cấu hình rộng có thể làm giảm capacity tổng khi concurrency tăng.

## 23. Quản lý thay đổi theo lịch và phối hợp vận hành

Thay đổi database có thể xung đột với các hoạt động khác:

- Backup/restore.
- Index rebuild hoặc statistics update.
- Vacuum/purge và checkpoint.
- ETL, import/export, retention job.
- Replication maintenance hoặc failover.
- Deploy ứng dụng và migration schema.

Một change calendar giúp tránh nhiều tác vụ nặng cùng lúc. Tuy nhiên, cửa sổ ít traffic không tự động có nghĩa là an toàn; backup hoặc batch nền có thể đang chiếm I/O.

### Change freeze và emergency change

Trong giai đoạn rủi ro cao, có thể giới hạn thay đổi không thiết yếu. Emergency change cần quy trình rút gọn nhưng vẫn phải có:

- Mục tiêu và bằng chứng.
- Phạm vi ảnh hưởng.
- Người chịu trách nhiệm.
- Điều kiện dừng.
- Cách khôi phục.
- Ghi nhận hậu kiểm.

Không bỏ qua rollback chỉ vì thay đổi được gọi là khẩn cấp.

### Phân vai

- Người đề xuất: nêu vấn đề, giả thuyết và metric.
- Người review DB: đánh giá SQL, plan, DDL, lock và log.
- Người vận hành: thực hiện lệnh và theo dõi.
- Người sở hữu ứng dụng: xác nhận correctness và compatibility.
- Người quyết định: tiếp tục, dừng, rollback hoặc roll-forward.

Với thay đổi nhỏ, một người có thể đảm nhiệm nhiều vai trò; trách nhiệm vẫn cần rõ.

## 24. Những sai lầm thường gặp

- **Chỉ có kế hoạch triển khai, không có kế hoạch hoàn tác:** khi có regression phải quyết định trong lúc sự cố.
- **Coi online DDL là không khóa:** metadata lock và các pha bắt đầu/kết thúc vẫn có thể chặn.
- **Drop index cũ trước khi index mới được xác minh:** mất đường truy cập ổn định nếu build mới thất bại.
- **Tạo index mà không tính write overhead:** read nhanh hơn nhưng toàn workload có thể chậm.
- **Thay nhiều tham số cùng lúc:** không xác định được yếu tố gây cải thiện hoặc regression.
- **Tăng connection limit để chữa pool wait:** có thể làm DB bão hòa nặng hơn.
- **Revert code nhưng bỏ qua schema/data:** application cũ có thể không tương thích dữ liệu mới.
- **Dùng migration down không được diễn tập:** có thể mất dữ liệu hoặc gây lock lớn.
- **Không lưu giá trị cấu hình cũ:** rollback đặt sai giá trị hoặc sai scope.
- **Chỉ theo dõi CPU:** bỏ qua lock, I/O, memory, log và replication.
- **Không kiểm tra parameter skew:** query mới tốt với tenant nhỏ nhưng chậm với tenant lớn.
- **Không có rollback trigger định lượng:** quyết định dừng bị chậm hoặc thiếu nhất quán.
- **Tiếp tục rollout khi metric thiếu:** không đủ bằng chứng để đánh giá an toàn.
- **Không xác minh sau thay đổi:** index có thể invalid, config chưa có hiệu lực hoặc replica chưa bắt kịp.
- **Cho rằng rollback luôn an toàn:** thao tác drop/rebuild hoặc restore có thể gây tải và downtime mới.

## 25. Checklist change management

| Hạng mục | Câu hỏi cần xác nhận |
|---|---|
| Mục tiêu | Vấn đề, giả thuyết và ngưỡng thành công có số liệu? |
| Phạm vi | Query, bảng, index, node, tenant và ứng dụng bị ảnh hưởng đã rõ? |
| Correctness | Có so sánh kết quả và kiểm tra invariant? |
| Baseline | Có plan, latency, throughput, error và resource metrics trước thay đổi? |
| Compatibility | Các application version và job có tương thích schema? |
| DDL | Đã xác nhận online/concurrent support theo đúng version? |
| Lock | Biết lock mode, metadata lock, timeout và blocker? |
| Capacity | Có disk, memory, I/O, log và replica headroom? |
| Config | Biết scope, dynamic/static, runtime/persistent và giá trị cũ? |
| Rollout | Có canary, feature flag, shard hoặc tenant cohort phù hợp? |
| Rollback | Có thao tác, thời gian, phụ thuộc và người thực hiện? |
| Trigger | Có ngưỡng p95/p99, error, lock, I/O, log và lag? |
| Monitoring | Dashboard/alert và query fingerprint sẵn sàng? |
| Verification | Có kiểm tra trạng thái DDL, plan, dữ liệu và hiệu năng? |
| Record | Có Change ID, timeline, kết quả và quyết định cuối? |

## 26. Nguyên tắc ra quyết định

Thay đổi SQL, index và cấu hình database phải bắt đầu từ một vấn đề đo được và một giả thuyết có thể kiểm chứng. Trước khi triển khai, đánh giá correctness, execution plan, workload hỗn hợp, lock, log, memory, I/O, replication và khả năng tương thích giữa các phiên bản ứng dụng.

Hãy lưu trạng thái trước thay đổi, chuẩn bị điều kiện vận hành, triển khai theo giai đoạn và định nghĩa rollback trigger bằng metric cụ thể. Với thay đổi schema hoặc dữ liệu khó đảo ngược, dùng expand-migrate-switch-contract và cân nhắc roll-forward thay vì ép rollback làm mất dữ liệu mới. Với DDL online, xác minh đúng hỗ trợ của DBMS/version và vẫn theo dõi lock, I/O, log và disk.

Sau triển khai, kiểm tra cả trạng thái kỹ thuật, tính đúng đắn và hiệu năng của toàn workload. Chỉ kết thúc change khi metric mục tiêu đạt, guardrail ổn định, dữ liệu đúng và kế hoạch hoàn tác không còn cần kích hoạt. Hồ sơ thay đổi phải lưu bằng chứng và kết quả để lần tối ưu tiếp theo có thể học từ dữ liệu thực tế.
