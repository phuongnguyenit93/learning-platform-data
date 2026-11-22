# Đặt ngân sách tài nguyên và thời điểm chạy công việc bảo trì

## Mục tiêu học tập

Sau bài học này, bạn có thể:

- Phân loại các công việc bảo trì dữ liệu theo mục tiêu, mức ưu tiên và tài nguyên chúng tiêu thụ.
- Lập ngân sách CPU, bộ nhớ, I/O, log, temp space, connection và thời gian giữ khóa cho tác vụ bảo trì.
- Chọn cửa sổ chạy dựa trên workload thực tế, SLA và xung đột với backup, ETL, batch nghiệp vụ hoặc checkpoint.
- Điều tiết công việc bằng concurrency limit, batch size, rate limit, pause/resume và ngưỡng dừng.
- Thiết kế lịch bảo trì riêng cho PostgreSQL, MySQL/InnoDB và SQL Server theo đặc tính từng hệ quản trị.
- Đo tác động trước, trong và sau bảo trì để xác nhận hệ thống vẫn đáp ứng mục tiêu hiệu năng.

## 1. Bảo trì dữ liệu là một phần của vận hành hiệu năng

Trong chương **Bảo trì dữ liệu**, bài học này tập trung vào cách đặt ngân sách tài nguyên và chọn thời điểm chạy công việc bảo trì. Với phạm vi DATABASE_PERFORMANCE, bảo trì hỗ trợ duy trì hiệu năng lâu dài thông qua cập nhật thống kê, dọn dữ liệu đã xóa, xử lý phân mảnh, xây dựng lại chỉ mục, quản lý partition, kiểm tra tính toàn vẹn và sao lưu.

Các công việc này cần CPU, RAM, I/O, transaction log/WAL, temp space và đôi khi cần khóa hoặc metadata lock. Nếu chạy không đúng thời điểm hoặc không giới hạn mức tiêu thụ, chúng có thể cạnh tranh với truy vấn nghiệp vụ, làm tăng p95/p99, gây lock wait, làm chậm commit hoặc khiến storage chạm trần.

Mục tiêu không phải hoàn thành mọi tác vụ nhanh nhất có thể. Mục tiêu là duy trì trạng thái dữ liệu và chỉ mục khỏe mạnh trong giới hạn tài nguyên mà hệ thống vẫn phải phục vụ workload chính.

## 2. Những công việc bảo trì thường gặp

| Công việc | Mục đích | Tài nguyên thường tiêu thụ |
| --- | --- | --- |
| Cập nhật statistics | Giúp optimizer ước lượng cardinality và chọn execution plan phù hợp | CPU, đọc dữ liệu mẫu, I/O, metadata |
| Vacuum/purge/cleanup | Thu hồi hoặc tái sử dụng không gian từ phiên bản/hàng đã xóa | CPU, đọc/ghi data page, WAL/redo, I/O nền |
| Rebuild/reorganize index | Khôi phục cấu trúc chỉ mục, xử lý page split hoặc phân mảnh | CPU, RAM, đọc/ghi, log, temp space và lock |
| Xóa dữ liệu hết hạn | Giữ dung lượng và retention theo chính sách | Log/WAL, I/O, lock, replication bandwidth |
| Partition attach/detach/drop | Quản lý vòng đời dữ liệu theo khoảng hoặc nhóm | Metadata lock, catalog, index và storage metadata |
| Backup/restore validation | Bảo vệ khả năng phục hồi | Đọc dữ liệu, ghi backup, network và CPU nén/mã hóa |
| Kiểm tra toàn vẹn | Phát hiện lỗi cấu trúc hoặc dữ liệu | Đọc nhiều page, CPU và I/O |
| Nạp lại hoặc đồng bộ dữ liệu | Đưa dữ liệu mới vào bảng/staging | CPU, log, index maintenance, I/O và network |

Không phải tác vụ nào cũng cần chạy theo lịch cố định. Một số việc được hệ quản trị tự động thực hiện như autovacuum, purge hoặc checkpoint; DBA cần theo dõi backlog và điều chỉnh ngưỡng, thay vì tạo thêm một job thủ công trùng lặp.

## 3. Vì sao phải có ngân sách tài nguyên?

Một máy chủ có thể còn CPU nhưng storage đã bão hòa. Một tác vụ có thể dùng ít I/O nhưng chiếm nhiều RAM và làm truy vấn sort/hash bị spill. Rebuild index có thể hoàn tất nhanh nhưng tạo log lớn khiến replica tụt lại. Vì vậy, ngân sách bảo trì phải xét nhiều tài nguyên cùng lúc.

Các giới hạn cần xem:

- **CPU:** mức dùng trung bình và đỉnh, CPU quota/throttling, parallel worker và CPU còn lại cho truy vấn nghiệp vụ.
- **Memory:** buffer pool, query workspace, maintenance memory, session, kernel và headroom để tránh OOM hoặc memory pressure.
- **I/O:** IOPS, throughput, latency và queue depth riêng cho data, log, temp và backup.
- **Transaction log/WAL/redo:** tốc độ sinh log, dung lượng còn trống, log backup và khả năng apply của replica.
- **Temp space:** file sort, worktable, index build và dữ liệu trung gian.
- **Lock/concurrency:** số hàng hoặc phạm vi bị khóa, thời gian giữ khóa và khả năng chặn giao dịch trực tuyến.
- **Network:** băng thông cho backup, replication, cross-zone hoặc đồng bộ dữ liệu.
- **Connection/worker:** session, background worker, job slot và thread pool còn khả dụng.

Ngân sách nên đặt theo từng tài nguyên. Không dùng một giới hạn CPU duy nhất để kết luận một tác vụ bảo trì an toàn.

## 4. Xác định ngân sách từ workload nghiệp vụ

Trước khi cấp tài nguyên cho bảo trì, cần đo nhu cầu của workload chính trong khung giờ và tình huống tải quan trọng.

Một cách lập ngân sách thực tế:

1. Đo CPU, memory, IOPS, throughput, log generation và network ở giờ cao điểm bình thường.
2. Ghi lại p95/p99 latency, throughput và wait events của các truy vấn quan trọng.
3. Xác định headroom cần giữ cho burst, failover, tác vụ nền và dao động dữ liệu.
4. Tính phần tài nguyên còn lại có thể dành cho maintenance.
5. Đặt giới hạn riêng cho từng job và giới hạn tổng số job chạy đồng thời.
6. Chạy thử dưới tải đại diện, sau đó điều chỉnh ngân sách dựa trên số liệu.

Có thể biểu diễn ngân sách còn lại theo từng tài nguyên:

```text
Maintenance budget
  = capacity thực tế
  - nhu cầu foreground tại mức tải mục tiêu
  - headroom vận hành và dự phòng
```

Ví dụ minh họa: nếu volume có thể duy trì 8.000 IOPS, workload nghiệp vụ cần 5.000 IOPS ở giờ cao điểm và cần giữ 1.000 IOPS dự phòng, ngân sách lý thuyết còn lại cho maintenance là khoảng 2.000 IOPS. Đây chỉ là cách lập ngân sách ban đầu; cần xét latency, loại I/O, queue depth và giới hạn riêng của log/data.

Không lấy utilization trung bình thấp để cấp hết phần tài nguyên còn lại. Một workload có thể có đỉnh ngắn, burst hoặc phụ thuộc latency. Headroom phải được xác định từ SLO và dữ liệu thực tế.

## 5. Ngân sách CPU và parallelism

Index rebuild, integrity check, compression, sort và một số thao tác thống kê có thể sử dụng nhiều CPU. Parallelism giúp hoàn thành nhanh hơn nhưng làm tăng cạnh tranh với truy vấn nghiệp vụ.

Khi đặt ngân sách CPU, xem:

- Số core/vCPU thực tế được cấp cho database.
- CPU quota hoặc throttling nếu database chạy trong container.
- Mức CPU nền của query workload, replication, backup và agent.
- Số worker bảo trì có thể chạy cùng lúc.
- Giới hạn parallelism của từng job.

Không nên đồng thời chạy nhiều index rebuild có parallelism cao trên cùng database nếu chưa kiểm tra tổng worker. Ví dụ, bốn job mỗi job dùng tối đa bốn worker có thể tạo nhu cầu lên đến 16 worker, chưa tính truy vấn và tác vụ nền.

Giới hạn parallelism giúp giảm đỉnh CPU nhưng có thể kéo dài thời gian chạy. Chọn mức sao cho tổng throughput hệ thống và p95/p99 nghiệp vụ vẫn nằm trong mục tiêu.

## 6. Ngân sách bộ nhớ

Các tác vụ bảo trì có thể cấp phát bộ nhớ cho sort, hash, index build, integrity check hoặc buffer nội bộ. Nếu nhiều job cùng chạy, tổng memory demand có thể lớn hơn nhiều so với một job đơn lẻ.

Ngân sách cần tính:

- Bộ nhớ dùng chung của database như buffer pool/shared buffers.
- Bộ nhớ riêng cho từng session hoặc worker.
- Maintenance memory cho mỗi operation.
- Query memory grant của workload nghiệp vụ.
- Filesystem cache, kernel, agent và sidecar.
- Headroom cho peak và sự kiện failover.

Không tăng maintenance memory chỉ vì một index build chậm. Nếu tăng memory cho mỗi job, phải tính số job đồng thời và khả năng cấp phát trong toàn bộ process/container.

Khi memory pressure tăng, hãy cân nhắc giảm số job đồng thời, giảm parallelism hoặc chia công việc thành lô trước khi nâng memory limit. Nếu tác vụ có thể spill sang temp, kiểm tra cả temp I/O và dung lượng còn trống.

## 7. Ngân sách I/O, log và temp space

I/O thường là giới hạn quan trọng của bảo trì. Rebuild index đọc cấu trúc cũ, sắp xếp khóa và ghi cấu trúc mới. Backup đọc nhiều data page và ghi ra storage/network. Cleanup đọc và cập nhật page. Các tác vụ này có thể cạnh tranh cùng thiết bị với truy vấn nghiệp vụ.

Hãy tách theo loại I/O:

- **Data I/O:** đọc và ghi bảng, index, partition.
- **Log I/O:** ghi WAL/redo/transaction log và log backup.
- **Temp I/O:** sort, hash, worktable và file trung gian.
- **Backup I/O:** đọc data và ghi backup target.
- **Replication I/O:** truyền log hoặc thay đổi sang replica.

Đặt giới hạn theo cả IOPS và MiB/s. Workload nhiều I/O nhỏ có thể chạm IOPS trước khi chạm băng thông; backup tuần tự có thể chạm throughput trước.

Đừng để job sử dụng hết dung lượng log hoặc temp. Một tác vụ bảo trì có thể làm transaction log tăng nhanh; nếu log backup hoặc replica không theo kịp, dung lượng log có thể tăng đến mức gây gián đoạn ghi.

## 8. Ngân sách lock và ảnh hưởng đến truy vấn trực tuyến

Thời gian chạy không phải chỉ số duy nhất. Một tác vụ chạy 10 phút nhưng giữ metadata lock khiến DDL hoặc truy vấn khác bị chặn có thể nguy hiểm hơn tác vụ chạy một giờ nhưng ít ảnh hưởng.

Đánh giá:

- Lock mode và phạm vi lock.
- Có cho phép concurrent reads/writes trong lúc chạy không?
- Có cần schema/metadata lock lúc bắt đầu hoặc kết thúc không?
- Transaction có giữ lock xuyên suốt job không?
- Có thể chia nhỏ để commit theo batch không?
- Có nguy cơ lock escalation hoặc blocking chain không?

Online index operation thường giảm mức chặn đọc/ghi nhưng không có nghĩa hoàn toàn không khóa. Một số bước đầu/cuối vẫn cần metadata lock; phiên bản, edition và loại index quyết định khả năng online.

Trước khi chạy, xác định điều kiện dừng nếu lock wait hoặc blocking vượt ngưỡng. Không chờ đến khi người dùng báo lỗi mới dừng job.

## 9. Chọn thời điểm chạy theo workload

Giờ thấp điểm là một yếu tố, nhưng không đủ để chọn maintenance window. Hãy xét chu kỳ nghiệp vụ và tác vụ khác:

- Batch thanh toán, đối soát, payroll hoặc chốt sổ.
- ETL, data warehouse load và đồng bộ dữ liệu.
- Backup đầy đủ, backup log và snapshot.
- Replication catch-up hoặc failover exercise.
- Checkpoint, vacuum, purge và cleanup tự động.
- Báo cáo định kỳ hoặc truy vấn cuối ngày.
- Thời điểm traffic tăng theo múi giờ của khách hàng.

Một maintenance window tốt là thời điểm workload thấp, các tác vụ nặng khác đã được sắp xếp, có đủ người trực và còn thời gian phục hồi nếu job kéo dài.

### Dùng lịch theo múi giờ rõ ràng

Đặt lịch bằng múi giờ có chủ đích. Nếu hệ thống phục vụ nhiều khu vực, hãy xác định giờ thấp điểm theo traffic thực tế thay vì mặc định giờ đêm của đội vận hành.

Với hệ thống chạy qua vùng có daylight saving time, lịch địa phương có thể dịch chuyển theo mùa. Có thể lưu lịch vận hành theo UTC hoặc ghi rõ timezone và quy tắc chuyển đổi. Cần tránh chạy trùng hoặc bỏ sót job khi chuyển giờ.

### Không dồn mọi tác vụ vào cùng một cửa sổ

Nếu backup, index rebuild, integrity check và purge cùng bắt đầu lúc 02:00, chúng có thể tạo đỉnh I/O, CPU và log. Hãy stagger lịch:

1. Chạy backup hoặc snapshot theo thiết kế đã chọn.
2. Theo dõi log/replica và xác nhận backup không còn gây đỉnh I/O.
3. Chạy tác vụ bảo trì cần I/O lớn.
4. Chạy tác vụ kiểm tra hoặc báo cáo ít cạnh tranh hơn.

Thứ tự cụ thể phụ thuộc quy trình backup, recovery và sản phẩm. Một số hệ thống cần backup sau khi index rebuild; một số backup snapshot có thể chạy song song. Hãy kiểm tra yêu cầu phục hồi và retention.

## 10. Phân loại mức ưu tiên và độ khẩn cấp

Không phải mọi maintenance job đều có cùng mức ưu tiên. Có thể chia thành:

| Mức | Ví dụ | Cách xử lý |
| --- | --- | --- |
| Khẩn cấp | Dung lượng log sắp đầy, autovacuum không theo kịp gây nguy cơ transaction ID wraparound, storage gần hết | Hành động theo runbook ngay, có giám sát và giới hạn rủi ro |
| Cao | Statistics cũ làm plan regression, index/partition tăng trưởng ảnh hưởng SLO | Đưa vào cửa sổ sớm, ưu tiên theo tác động query |
| Định kỳ | Analyze, vacuum/purge bình thường, backup, kiểm tra toàn vẹn | Lập lịch và giới hạn tài nguyên |
| Tối ưu tùy chọn | Rebuild index khi có bằng chứng fragmentation hoặc page bloat ảnh hưởng | Chỉ chạy khi đo được lợi ích và có ngân sách |

Không dùng fragmentation percentage đơn lẻ làm lý do rebuild. Với một số workload, mức phân mảnh không ảnh hưởng đáng kể; rebuild có thể tạo log, I/O và lock lớn hơn lợi ích.

## 11. Điều tiết maintenance bằng rate limit và concurrency

Rate limit kiểm soát tốc độ tác vụ tiêu thụ tài nguyên. Concurrency limit kiểm soát số job hoặc worker chạy đồng thời.

Các cách điều tiết:

- Giới hạn số job bảo trì cùng lúc.
- Giới hạn parallel worker cho mỗi job.
- Chia dữ liệu thành batch theo khóa hoặc partition.
- Thêm khoảng nghỉ giữa các batch nếu latency foreground tăng.
- Điều chỉnh I/O priority hoặc cost-based throttling nếu hệ quản trị hỗ trợ.
- Dùng queue để tuần tự hóa các job cùng tranh chấp một tài nguyên.

### Điều tiết thích ứng

Thay vì dùng một tốc độ cố định, scheduler có thể điều chỉnh dựa trên metric:

```text
Nếu p95 latency < mục tiêu và I/O queue còn thấp:
    tăng nhẹ tốc độ maintenance

Nếu p95 latency vượt ngưỡng hoặc log/IO queue tăng:
    giảm tốc độ hoặc pause job

Nếu có OOM, log gần đầy hoặc replica lag vượt giới hạn:
    dừng job theo runbook và cảnh báo
```

Ngưỡng cần dựa trên baseline và SLO. Dùng hysteresis hoặc thời gian xác nhận để tránh job liên tục pause/resume do dao động ngắn.

## 12. Chia nhỏ công việc và khả năng tiếp tục

Công việc lớn thường nên chia theo partition, khoảng khóa hoặc nhóm hàng nếu ngữ nghĩa cho phép. Chia lô giúp giới hạn transaction size, lock duration, log burst và khả năng rollback.

Ví dụ purge dữ liệu cũ theo batch:

```sql
DELETE FROM audit_events
WHERE event_id IN (
    SELECT event_id
    FROM audit_events
    WHERE created_at < :retention_cutoff
    ORDER BY event_id
    LIMIT 5000
);
```

Đây là mẫu minh họa theo cú pháp gần với PostgreSQL/MySQL; cách dùng `LIMIT` trong subquery và cách khóa hàng khác nhau theo hệ quản trị. Cần có index hỗ trợ predicate và thứ tự chọn batch. Nếu dùng PostgreSQL, có thể dùng CTE và `DELETE ... USING`; nếu dùng SQL Server, có thể dùng `DELETE TOP (...)` với thứ tự được xác định qua CTE.

Ứng dụng hoặc scheduler lặp lại batch, commit theo từng nhóm và ghi checkpoint tiến độ. Nếu nghiệp vụ yêu cầu atomicity toàn bộ, không được tự ý commit từng batch; cần giữ transaction hoặc thiết kế quy trình chuyển trạng thái có thể phục hồi.

### Idempotency và resume

Job có thể bị dừng do deploy, timeout, failover hoặc vượt ngân sách. Thiết kế để chạy lại an toàn:

- Xác định phạm vi batch bằng khóa ổn định.
- Ghi checkpoint sau khi batch commit thành công.
- Chỉ đánh dấu batch hoàn tất sau khi thao tác database đã commit.
- Dùng điều kiện lọc idempotent để chạy lại không làm thay đổi sai dữ liệu.
- Có cơ chế phát hiện batch đang chạy để tránh hai worker xử lý cùng vùng.
- Ghi lại job ID, cutoff time, partition và số hàng đã xử lý.

Không dùng OFFSET lớn để tiếp tục purge hàng triệu bản ghi nếu có thể dùng keyset theo khóa ổn định; OFFSET lớn thường phải bỏ qua nhiều hàng và tốn thêm công việc.

## 13. PostgreSQL: vacuum, analyze và index maintenance

PostgreSQL dùng MVCC; UPDATE/DELETE tạo phiên bản hàng mới hoặc đánh dấu phiên bản cũ không còn cần thiết. VACUUM giúp thu hồi/tái sử dụng không gian và ngăn transaction ID wraparound. ANALYZE cập nhật thống kê cho optimizer.

Ví dụ bảo trì một bảng:

```sql
VACUUM (ANALYZE) orders;
```

`VACUUM` thông thường có thể chạy đồng thời với nhiều hoạt động đọc/ghi, nhưng vẫn tiêu thụ I/O và CPU. Một số thao tác như `VACUUM FULL` cần lock mạnh và ghi lại bảng; không coi chúng tương đương VACUUM thường.

### Theo dõi autovacuum

Các yếu tố cần theo dõi:

- Dead tuples và tốc độ tăng.
- Thời điểm vacuum/analyze gần nhất.
- Autovacuum worker đang chạy và backlog.
- Transaction ID age và cảnh báo wraparound.
- I/O, vacuum cost delay và thời gian hoàn thành.

Autovacuum là cơ chế bảo trì nền quan trọng. Tắt autovacuum để tránh I/O có thể dẫn đến bloat hoặc nguy cơ wraparound. Nếu autovacuum không theo kịp, hãy xem bảng nào có update/delete nhiều, ngưỡng trigger, worker capacity và I/O budget.

Các tham số như `autovacuum_vacuum_threshold`, `autovacuum_vacuum_scale_factor`, `autovacuum_analyze_threshold`, `autovacuum_analyze_scale_factor`, `autovacuum_max_workers`, `autovacuum_vacuum_cost_limit` và `autovacuum_vacuum_cost_delay` có thể được điều chỉnh theo workload. Không tăng worker hoặc cost limit mà không kiểm tra tổng I/O.

### Điều chỉnh VACUUM có giới hạn

`vacuum_cost_delay` và `vacuum_cost_limit` giúp điều tiết lượng công việc vacuum dựa trên cost model. Cấu hình phù hợp có thể giảm cạnh tranh I/O, nhưng nếu quá thấp vacuum có thể không theo kịp tốc độ tạo dead tuple.

Đối với index build/rebuild, PostgreSQL có `maintenance_work_mem` và `max_parallel_maintenance_workers` để điều khiển tài nguyên của một số thao tác bảo trì. Tăng chúng có thể làm index build nhanh hơn nhưng cần tính memory và CPU đồng thời.

`CREATE INDEX CONCURRENTLY` giảm mức chặn ghi so với tạo index thông thường trong nhiều trường hợp, nhưng thường tốn nhiều công việc và thời gian hơn, có các giới hạn riêng và không chạy bên trong transaction block. Cần kiểm tra tiến độ và xử lý index invalid nếu thao tác thất bại.

Ví dụ:

```sql
CREATE INDEX CONCURRENTLY ix_orders_created_at
    ON orders (created_at);
```

Không chạy `REINDEX` hoặc `VACUUM FULL` hàng loạt chỉ theo lịch nếu chưa có bằng chứng bloat hoặc yêu cầu vận hành. Các thao tác này có thể cần lock mạnh, thêm dung lượng tạm và I/O lớn.

## 14. MySQL/InnoDB: purge, analyze và optimize

InnoDB dùng MVCC và undo log để hỗ trợ transaction. Purge thread dọn các phiên bản undo không còn cần thiết khi không transaction nào cần chúng. Transaction dài có thể giữ read view cũ, khiến purge không thể thu hồi dữ liệu và history list length tăng.

Những việc cần theo dõi:

- History list length và tốc độ purge.
- Transaction chạy lâu và transaction mở nhưng ít hoạt động.
- Buffer pool dirty pages và flushing.
- Redo log checkpoint age hoặc áp lực redo.
- I/O capacity và file I/O latency.

`ANALYZE TABLE` cập nhật thống kê optimizer; nên lên lịch sau khi dữ liệu thay đổi đáng kể hoặc khi plan có dấu hiệu sai ước lượng. `OPTIMIZE TABLE` với InnoDB thường thực hiện table rebuild để tổ chức lại dữ liệu và cập nhật thống kê, nhưng cách thực hiện, mức online và lock phụ thuộc phiên bản, engine và cấu trúc bảng.

Ví dụ:

```sql
ANALYZE TABLE orders;

OPTIMIZE TABLE orders;
```

Không chạy OPTIMIZE TABLE định kỳ cho mọi bảng nếu chưa xác định cần reclaim/rebuild. Tác vụ có thể đọc/ghi lượng dữ liệu lớn, cần dung lượng bổ sung và tạo metadata lock ở một số giai đoạn.

### Điều tiết I/O InnoDB

`innodb_io_capacity` và `innodb_io_capacity_max` ảnh hưởng mức công việc I/O nền mà InnoDB dùng cho một số tác vụ như flushing và change buffer merge. Giá trị cần tương ứng với khả năng storage thực tế; đặt quá cao có thể làm storage queue tăng, đặt quá thấp có thể để dirty page hoặc backlog tích tụ.

Đừng dùng tham số I/O capacity như một bộ giới hạn cứng cho mọi truy vấn. Nó là một phần của cơ chế điều phối I/O nền InnoDB; vẫn cần giám sát volume IOPS, latency và workload foreground.

## 15. SQL Server: statistics, index maintenance và MAXDOP

SQL Server có thể cập nhật statistics tự động, nhưng một số workload lớn hoặc thay đổi phân bố dữ liệu mạnh có thể cần cập nhật chủ động theo chính sách.

Ví dụ:

```sql
UPDATE STATISTICS dbo.Orders;
```

Index maintenance có thể dùng REORGANIZE hoặc REBUILD tùy tình trạng và yêu cầu:

```sql
ALTER INDEX IX_Orders_CreatedAt
ON dbo.Orders REORGANIZE;

ALTER INDEX IX_Orders_CreatedAt
ON dbo.Orders
REBUILD WITH (ONLINE = ON, MAXDOP = 2);
```

`REORGANIZE` thường là thao tác online, ít xâm lấn hơn nhưng có thể mất nhiều thời gian. `REBUILD` tạo lại cấu trúc index, tiêu thụ CPU, I/O, log và có thể cần thêm dung lượng; `ONLINE = ON` phụ thuộc phiên bản, edition, loại index và giới hạn cụ thể.

`MAXDOP` giới hạn mức parallelism cho thao tác. Cần chọn theo CPU budget và workload đồng thời, không dùng một giá trị cao cho mọi database.

Với online index operation được hỗ trợ, có thể cấu hình `WAIT_AT_LOW_PRIORITY` để giới hạn ảnh hưởng khi chờ lock. Cú pháp và khả năng phụ thuộc phiên bản SQL Server; ví dụ khái quát:

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

Chính sách `ABORT_AFTER_WAIT` cần được chọn theo mức ưu tiên của workload và job. Không dùng `BLOCKERS` hoặc chờ vô hạn nếu không có runbook và người chịu trách nhiệm rõ ràng.

## 16. Backup và kiểm tra toàn vẹn cũng cần ngân sách

Backup thường đọc một lượng lớn data page và ghi ra storage hoặc network target. Nếu chạy cùng index rebuild hoặc ETL, các tác vụ có thể cạnh tranh băng thông.

Để đặt lịch backup:

- Xác định RPO/RTO và loại backup cần thiết.
- Đo throughput đọc database và ghi backup target.
- Chọn compression/encryption phù hợp với CPU budget.
- Theo dõi backup duration, bytes, errors và tác động query latency.
- Đánh giá backup full, differential/incremental và log backup có chồng lấn không.
- Kiểm tra restore định kỳ; backup thành công không chứng minh có thể phục hồi.

Integrity check thường đọc nhiều page và có thể tiêu thụ I/O lớn. Hãy chọn lịch riêng, giới hạn concurrency và theo dõi latency. Nếu có lỗi cấu trúc, xử lý theo runbook của hệ quản trị; không tự động sửa chữa bằng tùy chọn có thể làm mất dữ liệu.

## 17. Quản lý lịch và phụ thuộc giữa các job

Một lịch bảo trì cần mô tả job, điều kiện bắt đầu, ngân sách, phụ thuộc, timeout và cách phục hồi.

| Job | Điều kiện bắt đầu | Xung đột cần tránh | Điều kiện hoàn tất |
| --- | --- | --- | --- |
| Analyze/statistics | Sau load lớn hoặc khi statistics stale | Không chạy trùng nhiều lần trên cùng bảng | Statistics được cập nhật, plan được kiểm tra |
| Vacuum/purge | Backlog hoặc threshold đạt ngưỡng | Transaction dài, backup I/O, batch delete | Dead tuple/history backlog giảm |
| Index rebuild | Có bằng chứng fragmentation/bloat hoặc thay đổi cấu trúc | Peak traffic, log backup, replica apply, temp space | Index hợp lệ, query plan và latency được xác nhận |
| Retention/purge | Đến cutoff theo chính sách lưu trữ | Báo cáo, archive, foreign key cascade | Số hàng/partition bị loại đúng và log ổn định |
| Backup | Theo RPO và lịch phục hồi | Rebuild, integrity scan, ETL nặng | Backup hoàn tất và có kiểm tra khả năng restore |
| Integrity check | Theo lịch hoặc sau sự kiện bất thường | Peak I/O, backup, storage maintenance | Kết quả được lưu và xử lý theo runbook |

Job scheduler nên hỗ trợ:

- Dependency để job sau chỉ chạy khi job trước hoàn tất.
- Mutex hoặc lock logic để tránh cùng một job chạy hai lần.
- Maximum runtime và cancellation policy.
- Retry có giới hạn cho lỗi tạm thời.
- Lưu trạng thái, checkpoint và kết quả.
- Cảnh báo khi job bỏ lỡ cửa sổ hoặc backlog vượt ngưỡng.

## 18. Dùng maintenance window động

Cửa sổ bảo trì cố định dễ quản lý nhưng có thể không còn phù hợp khi traffic thay đổi. Maintenance window động có thể chỉ cho phép job chạy khi các điều kiện tài nguyên thỏa mãn.

Ví dụ điều kiện:

- CPU utilization và CPU pressure dưới ngưỡng trong một khoảng liên tục.
- Storage latency p95 dưới ngưỡng và queue depth còn headroom.
- Foreground p95/p99 đang trong SLO.
- Không có backup hoặc ETL nặng đang chạy.
- Replica lag thấp hơn giới hạn.
- Transaction log và temp space còn đủ dung lượng.

Khi một điều kiện không còn thỏa mãn, scheduler giảm tốc hoặc tạm dừng job. Một số thao tác database không thể pause/resume an toàn ở mọi thời điểm; phải kiểm tra tính năng của engine trước khi bật điều khiển tự động.

Không để job liên tục khởi chạy rồi bị hủy giữa chừng. Dùng thời gian ổn định trước khi bắt đầu, hysteresis và giới hạn số lần pause để tránh tạo overhead lặp lại.

## 19. Theo dõi trước, trong và sau bảo trì

### Trước khi chạy

- Ghi baseline CPU, memory, I/O, log, temp, connection và replication.
- Lưu p50/p95/p99 và throughput của truy vấn quan trọng.
- Kiểm tra dung lượng data/log/temp và backup gần nhất.
- Kiểm tra blocker, transaction dài và job khác đang chạy.
- Xác nhận quyền, timeout, online mode và rollback/recovery plan.

### Trong khi chạy

- Theo dõi tiến độ, số hàng/page đã xử lý và thời gian còn lại.
- Theo dõi CPU, memory, IOPS, throughput, latency và queue.
- Theo dõi lock wait, blocking chain, deadlock và connection wait.
- Theo dõi log growth, WAL/redo backlog, temp usage và replica lag.
- So sánh foreground p95/p99 với baseline.
- Điều tiết, pause hoặc dừng nếu chạm ngưỡng đã định.

### Sau khi chạy

- Xác nhận job hoàn tất và không để lại trạng thái dở dang.
- Kiểm tra statistics, index validity và execution plan của truy vấn quan trọng.
- Xác nhận backlog vacuum/purge/checkpoint hoặc replica đã trở lại mức bình thường.
- Kiểm tra log/temp/data capacity và giải phóng file tạm theo cơ chế hệ quản trị.
- So sánh p95/p99, throughput, logical reads và I/O với baseline.
- Lưu kết quả, cấu hình, thời lượng và bài học cho lần chạy sau.

## 20. Ví dụ: lập kế hoạch bảo trì cho bảng đơn hàng lớn

Giả sử hệ thống có bảng `orders` tăng đều theo ngày, truy vấn trực tuyến chủ yếu tìm đơn gần đây, còn báo cáo cuối tháng quét dữ liệu lịch sử. Các công việc cần thực hiện gồm analyze, vacuum/purge, index maintenance, backup và retention.

Một kế hoạch mẫu:

| Thời điểm | Công việc | Ngân sách/điều kiện |
| --- | --- | --- |
| Sau đợt bulk load | Analyze bảng và index liên quan | CPU thấp-vừa, giới hạn I/O, kiểm tra plan sau cập nhật |
| Liên tục trong ngày | Autovacuum/purge nền | Theo dõi backlog, giới hạn cost/IO theo engine |
| Cửa sổ traffic thấp | Rebuild/reorganize index nếu có bằng chứng | Một job lớn mỗi storage group, giới hạn parallelism và log growth |
| Sau khi log/replica ổn định | Backup theo RPO | Giới hạn network và storage bandwidth, kiểm tra backup duration |
| Theo retention cutoff | Detach/drop partition cũ hoặc purge theo batch | Kiểm tra archive, FK, metadata lock và restore policy |
| Hàng tuần/tháng | Integrity check | Chạy lệch với backup và ETL nặng, theo dõi I/O |

Không nên hiểu lịch này là thứ tự bắt buộc cho mọi nền tảng. Nếu backup cần phản ánh index mới hoặc retention cần archive trước, thay đổi dependency theo chính sách phục hồi và tuân thủ.

### Xác định ngưỡng dừng minh họa

Giả sử SLO yêu cầu API p95 dưới 200 ms và storage write latency p95 dưới 10 ms. Có thể đặt quy tắc thử nghiệm:

- Giảm maintenance rate nếu API p95 vượt 180 ms trong 3 cửa sổ liên tiếp.
- Pause job nếu API p95 vượt 200 ms kéo dài hoặc lock wait vượt ngưỡng.
- Dừng và cảnh báo nếu log còn dưới ngưỡng dung lượng an toàn hoặc replica lag vượt giới hạn vận hành.
- Chỉ tăng tốc lại sau khi các metric ổn định dưới ngưỡng phục hồi trong một khoảng xác nhận.

Các ngưỡng trên chỉ là ví dụ. Ngưỡng production phải xuất phát từ SLO, baseline, capacity và quy trình xử lý sự cố của tổ chức.

## 21. Đánh giá lợi ích và chi phí sau bảo trì

Một job hoàn tất không đồng nghĩa hiệu năng đã cải thiện. Hãy đo kết quả theo mục tiêu ban đầu:

| Mục tiêu | Bằng chứng cần có |
| --- | --- |
| Statistics tốt hơn | Estimated rows gần actual rows hơn, plan ổn định hơn, latency/reads giảm |
| Vacuum/purge theo kịp | Dead tuple hoặc history backlog giảm, dung lượng được tái sử dụng, transaction age an toàn |
| Index maintenance | Index hợp lệ, page/fragmentation metrics cải thiện, query reads/latency có lợi |
| Retention | Dữ liệu ngoài hạn được archive/xóa đúng, dung lượng và log trở lại bình thường |
| Backup | Backup hoàn tất, thời gian và băng thông trong ngân sách, restore test đạt |
| Integrity check | Kết quả sạch hoặc lỗi được xử lý theo runbook |

Không chỉ so sánh một truy vấn đơn lẻ. Cần kiểm tra workload tổng thể để chắc rằng job không cải thiện một báo cáo nhưng làm chậm đường ghi hoặc các truy vấn khác.

## 22. Những sai lầm thường gặp

- **Chạy tất cả job vào giờ thấp điểm giống nhau.** Backup, rebuild và integrity scan có thể cộng dồn I/O.
- **Cấp toàn bộ headroom cho maintenance.** Hệ thống cần dự phòng cho burst, failover và biến động.
- **Chỉ giới hạn CPU.** Job vẫn có thể bão hòa IOPS, log, temp hoặc network.
- **Chạy nhiều index rebuild song song.** Tổng CPU, memory, log và temp có thể vượt ngân sách.
- **Rebuild index theo lịch dù không có bằng chứng.** Chi phí ghi và lock có thể lớn hơn lợi ích.
- **Tắt autovacuum hoặc purge để giảm I/O.** Backlog có thể tăng, gây bloat hoặc nguy cơ vận hành nghiêm trọng.
- **Tăng maintenance memory mà không tính concurrency.** Nhiều job có thể làm cạn RAM.
- **Xóa dữ liệu hết hạn trong một transaction khổng lồ.** Log, lock và rollback cost có thể tăng mạnh.
- **Không có checkpoint tiến độ.** Job bị gián đoạn sẽ khó tiếp tục hoặc có thể xử lý trùng.
- **Không xem replica lag.** Primary hoàn tất job nhưng replica không theo kịp.
- **Không đo trước và sau.** Không biết maintenance đã giải quyết vấn đề hay chỉ tiêu thụ tài nguyên.
- **Giả định online nghĩa là không khóa.** Online operation vẫn có thể cần metadata lock hoặc có giới hạn theo phiên bản.

## 23. Danh sách kiểm tra trước khi lên lịch bảo trì

- [ ] Mục tiêu của từng job và bằng chứng cần đạt đã được xác định.
- [ ] Đã đo baseline workload nghiệp vụ ở giờ cao điểm và cửa sổ dự kiến.
- [ ] Có ngân sách riêng cho CPU, memory, IOPS, throughput, log, temp và network.
- [ ] Có headroom cho burst, failover và tác vụ nền.
- [ ] Đã xác định lock mode, blocking risk và khả năng online.
- [ ] Job không chồng lấn với backup, ETL, batch hoặc checkpoint nặng.
- [ ] Có dependency, concurrency limit, parallelism cap và maximum runtime.
- [ ] Có rate limit, pause/resume hoặc batch size phù hợp.
- [ ] Có checkpoint, idempotency và quy tắc retry/resume.
- [ ] Có ngưỡng cảnh báo, pause và stop dựa trên SLO.
- [ ] Đã xác nhận log, temp và storage còn đủ dung lượng.
- [ ] Đã xem xét replication lag và backup/restore policy.
- [ ] Có metric trước-trong-sau và người chịu trách nhiệm theo dõi.
- [ ] Có kế hoạch kiểm chứng kết quả và cập nhật lịch sau khi đo.

## Kết luận

Đặt ngân sách và thời điểm chạy bảo trì là một phần của tối ưu hiệu năng dài hạn. Mỗi job cần được đánh giá theo CPU, memory, data/log/temp I/O, network, lock, connection và tác động đến replica. Hãy lập ngân sách từ workload cùng SLO, giữ headroom, tránh dồn backup, rebuild, purge và integrity check vào một thời điểm, đồng thời điều tiết bằng concurrency limit, batch, rate limit và ngưỡng pause/stop. PostgreSQL, MySQL/InnoDB và SQL Server có cơ chế vacuum, purge, statistics và index maintenance khác nhau; cần dùng đúng công cụ và hiểu giới hạn online của phiên bản. Cuối cùng, đo trước-trong-sau để xác nhận backlog giảm, execution plan và latency cải thiện, trong khi workload nghiệp vụ vẫn nằm trong mục tiêu.
