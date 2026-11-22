# innodb_flush_log_at_trx_commit, sync_binlog và đánh đổi độ bền

MySQL dùng nhiều loại log để bảo vệ dữ liệu và hỗ trợ phục hồi. InnoDB ghi **redo log** để khôi phục thay đổi của các trang dữ liệu sau sự cố; binary log ghi lại các sự kiện thay đổi dữ liệu để phục vụ replication và point-in-time recovery (PITR). Hai loại log có vai trò khác nhau và có cơ chế đồng bộ xuống thiết bị lưu trữ riêng.

Hai biến cấu hình ảnh hưởng trực tiếp đến thời điểm đồng bộ log là `innodb_flush_log_at_trx_commit` và `sync_binlog`. Chọn giá trị thấp hơn có thể giảm số lần flush hoặc sync và tăng thông lượng ghi, nhưng làm tăng lượng giao dịch gần nhất có nguy cơ mất khi hệ thống gặp sự cố. Với workload yêu cầu độ bền cao, cấu hình thường được khuyến nghị là cả hai biến bằng `1`.

## 1. Vì sao MySQL cần cả redo log và binary log?

### Redo log của InnoDB

Redo log ghi lại thông tin cần thiết để phát lại thay đổi trên trang dữ liệu khi InnoDB phục hồi sau crash. Khi transaction thay đổi một hàng, trang dữ liệu có thể vẫn nằm trong buffer pool và được ghi xuống data file sau đó. Commit không đòi hỏi mọi trang dữ liệu phải được ghi ngay; thay vào đó, InnoDB cần bảo đảm redo tương ứng được ghi và flush theo chính sách durability.

Redo log hỗ trợ crash recovery của InnoDB. Nó không phải bản ghi lịch sử đầy đủ để replica áp dụng giao dịch và cũng không thay thế backup.

### Binary log

Binary log (binlog) ghi lại các sự kiện thay đổi dữ liệu ở cấp server. Nó được dùng chủ yếu cho:

- Replication: replica đọc các sự kiện từ source và áp dụng chúng.
- Point-in-time recovery: khôi phục từ backup rồi phát lại các sự kiện binlog đến thời điểm cần thiết.
- Theo dõi và tích hợp dữ liệu: các công cụ có thể đọc binlog để phát hiện thay đổi.

Binlog không thay thế redo log. InnoDB cần redo để phục hồi trạng thái storage engine; replication và PITR cần binlog để biết các transaction đã được ghi nhận.

### Hai log có ranh giới đồng bộ riêng

Một transaction có thể đã được ghi vào redo log nhưng binlog chưa được đồng bộ bền vững, hoặc ngược lại tùy cấu hình và thời điểm crash. MySQL phối hợp InnoDB và binlog trong quy trình commit hai pha nội bộ để giữ trạng thái nhất quán khi phục hồi. Tuy vậy, để đạt mục tiêu durability mong muốn cho cả dữ liệu InnoDB và lịch sử binlog, cần cấu hình chính sách flush/sync phù hợp cho cả hai.

## 2. `innodb_flush_log_at_trx_commit` điều khiển điều gì?

Biến này điều khiển cách InnoDB ghi và flush redo log tại thời điểm commit. Ba giá trị chính:

| Giá trị | Hành vi chính | Rủi ro khi crash |
|---:|---|---|
| `0` | InnoDB ghi log buffer xuống redo log file và flush khoảng mỗi giây; không yêu cầu ghi/flush tại mỗi commit | Các transaction gần nhất có thể mất nếu mysqld, OS hoặc máy chủ gặp sự cố trước lần flush kế tiếp |
| `1` | Ghi redo log và yêu cầu flush xuống thiết bị lưu trữ bền vững tại mỗi commit | Mức bảo vệ cao nhất theo cơ chế flush của InnoDB; vẫn phụ thuộc OS, filesystem và thiết bị lưu trữ thực sự tôn trọng flush |
| `2` | Ghi redo log file tại mỗi commit nhưng flush xuống thiết bị lưu trữ khoảng mỗi giây | Nếu chỉ tiến trình mysqld chết mà OS còn chạy, dữ liệu trong OS cache thường vẫn còn; nếu OS hoặc máy chủ mất điện, các ghi chưa flush có thể mất |

Ví dụ xem giá trị hiện tại:

```sql
SHOW GLOBAL VARIABLES LIKE 'innodb_flush_log_at_trx_commit';
```

Đặt runtime:

```sql
SET GLOBAL innodb_flush_log_at_trx_commit = 1;
```

Muốn lưu thiết lập qua lần khởi động lại, có thể dùng `SET PERSIST` nếu biến và phiên bản hỗ trợ:

```sql
SET PERSIST innodb_flush_log_at_trx_commit = 1;
```

Hoặc khai báo trong option file ở nhóm server:

```ini
[mysqld]
innodb_flush_log_at_trx_commit = 1
```

Giá trị `1` thường là mặc định và là lựa chọn phù hợp khi không thể chấp nhận mất các transaction đã được xác nhận commit. Hãy kiểm tra giá trị hiệu lực trên instance, không giả định môi trường nào cũng giữ mặc định.

### Chu kỳ flush khi dùng giá trị 0 hoặc 2

Khoảng một giây là chu kỳ nền mặc định, không phải cam kết rằng mọi transaction chỉ có thể mất tối đa đúng một giây dữ liệu trong mọi tình huống. Thời điểm flush còn phụ thuộc lịch chạy, tải hệ thống, cấu hình `innodb_flush_log_at_timeout`, OS và thiết bị lưu trữ. Khi có sự cố đúng trước lần flush, lượng dữ liệu mất có thể lớn hơn kỳ vọng đơn giản dựa trên đồng hồ.

Kiểm tra biến liên quan:

```sql
SHOW GLOBAL VARIABLES LIKE 'innodb_flush_log_at_timeout';
```

Điều chỉnh timeout không biến giá trị `0` hoặc `2` thành chế độ bảo đảm mỗi commit được flush bền vững. Nếu yêu cầu là xác nhận commit chỉ sau khi redo đã được flush, dùng giá trị `1`.

## 3. `sync_binlog` điều khiển điều gì?

`sync_binlog` quy định tần suất MySQL đồng bộ binary log xuống thiết bị lưu trữ:

| Giá trị | Hành vi chính | Rủi ro khi crash |
|---:|---|---|
| `0` | MySQL không chủ động yêu cầu sync binlog theo từng nhóm commit; OS quyết định thời điểm flush | Các sự kiện binlog gần nhất có thể chưa bền vững khi OS hoặc máy chủ gặp sự cố |
| `1` | Yêu cầu sync binlog sau mỗi nhóm commit | Bảo vệ binlog tốt nhất theo cơ chế sync của MySQL; vẫn phụ thuộc thiết bị thực sự tôn trọng flush |
| `N` lớn hơn `1` | Yêu cầu sync sau mỗi `N` nhóm commit binlog | Khi crash có thể mất các nhóm commit gần nhất chưa được sync |

Kiểm tra giá trị:

```sql
SHOW GLOBAL VARIABLES LIKE 'sync_binlog';
```

Đặt runtime:

```sql
SET GLOBAL sync_binlog = 1;
```

Lưu qua lần khởi động lại:

```sql
SET PERSIST sync_binlog = 1;
```

Hoặc trong option file:

```ini
[mysqld]
sync_binlog = 1
```

Với `sync_binlog = 1`, MySQL yêu cầu đồng bộ sau mỗi nhóm commit, không nhất thiết gọi một lần sync riêng cho từng transaction. Group commit cho phép nhiều transaction chia sẻ một lần flush/sync ở một số giai đoạn, giúp giảm chi phí I/O mà vẫn duy trì ranh giới commit bền vững theo nhóm.

## 4. Group commit và ảnh hưởng đến hiệu năng

Flush log là thao tác I/O có chi phí. Nếu mọi transaction phải chờ một lần flush riêng biệt, độ trễ thiết bị lưu trữ có thể giới hạn số transaction commit mỗi giây.

MySQL hỗ trợ group commit: nhiều transaction cùng tham gia các nhóm commit để chia sẻ công việc ghi và đồng bộ log. Cơ chế này giúp tăng thông lượng mà không buộc phải bỏ yêu cầu durability. Vì vậy, `innodb_flush_log_at_trx_commit = 1` và `sync_binlog = 1` không đồng nghĩa với việc hệ thống luôn thực hiện đúng hai lần sync độc lập cho từng transaction.

Khi tải ghi tăng, hãy đo cả:

- Transaction commits per second.
- Commit latency, đặc biệt p95 và p99.
- Thời gian chờ log file sync và các wait event liên quan trong Performance Schema.
- IOPS, throughput và latency của thiết bị chứa redo log và binlog.
- Kích thước transaction và mức độ có thể gom nhóm commit.

Không nên thay đổi hai biến chỉ vì thấy commit latency cao. Trước tiên hãy xác định độ trễ đến từ thiết bị lưu trữ, contention, transaction quá lớn, cấu hình filesystem hay các wait khác.

## 5. Kết hợp hai biến theo mục tiêu durability

Hai biến điều khiển hai log khác nhau. Có thể dùng bảng sau làm khung đánh giá:

| `innodb_flush_log_at_trx_commit` | `sync_binlog` | Ý nghĩa vận hành |
|---:|---:|---|
| `1` | `1` | Lựa chọn ưu tiên khi cần độ bền cao cho cả redo và binlog |
| `1` | `0` | Redo được flush tại commit, nhưng binlog có thể chưa được sync bền vững khi OS/máy chủ gặp sự cố |
| `0` hoặc `2` | `1` | Binlog được sync theo nhóm commit, nhưng redo có thể chưa được flush bền vững tại từng commit |
| `0` hoặc `2` | `0` hoặc `N > 1` | Giảm tần suất flush/sync, có thể tăng thông lượng nhưng tăng cửa sổ rủi ro mất transaction gần nhất và sự kiện binlog |

Nếu hệ thống dùng binary log cho replication hoặc PITR, không chỉ quan tâm hàng dữ liệu còn tồn tại trong InnoDB. Binlog cũng cần phản ánh nhất quán các transaction được xác nhận commit. Cấu hình hai biến không đồng bộ có thể tạo ra rủi ro khác nhau cho crash recovery, replication và khả năng phát lại binlog.

Với workload nghiệp vụ quan trọng, điểm bắt đầu hợp lý là:

```ini
[mysqld]
innodb_flush_log_at_trx_commit = 1
sync_binlog = 1
```

Chỉ cân nhắc nới lỏng khi chủ hệ thống đã xác định rõ mức mất dữ liệu tối đa có thể chấp nhận, loại sự cố cần chịu được và cách phục hồi sau sự cố. Cần ghi quyết định này thành yêu cầu RPO (Recovery Point Objective), không chỉ là một chỉnh sửa hiệu năng.

## 6. Phân biệt các loại sự cố

Không phải mọi crash đều có cùng phạm vi mất dữ liệu:

| Sự cố | Tác động đến buffer/cache | Điều cần xem xét |
|---|---|---|
| Chỉ tiến trình `mysqld` bị dừng bất thường | OS và thiết bị vẫn chạy; dữ liệu đã chuyển khỏi bộ nhớ tiến trình có thể còn trong OS cache | Với `innodb_flush_log_at_trx_commit=2`, redo đã được ghi qua OS thường còn khả năng phục hồi; giá trị `0` có thể mất log buffer chưa được ghi |
| OS kernel crash hoặc máy chủ mất điện | OS page cache và cache dễ bay hơi có thể mất | Cần redo và binlog đã được flush thực sự xuống thiết bị bền vững |
| Thiết bị lưu trữ hoặc controller báo flush thành công nhưng không bảo đảm dữ liệu | Dữ liệu có thể mất hoặc hỏng dù MySQL đã yêu cầu sync | Kiểm tra write cache, power-loss protection, firmware và cam kết của nhà cung cấp |
| Hỏng thiết bị hoặc mất toàn bộ máy chủ | Không thể dựa vào bản log duy nhất trên thiết bị bị mất | Cần backup, bản sao ở nơi khác và quy trình restore/replication đã kiểm thử |

`innodb_flush_log_at_trx_commit=1` và `sync_binlog=1` bảo vệ commit trước các sự cố theo cơ chế flush của MySQL, nhưng không thay thế backup và không bảo vệ trước mọi dạng hỏng thiết bị, lỗi phần mềm, thao tác xóa nhầm hoặc mất toàn bộ hạ tầng.

## 7. Vì sao phần cứng lưu trữ rất quan trọng?

MySQL yêu cầu OS đồng bộ dữ liệu log xuống thiết bị bằng các cơ chế flush/sync phù hợp. Độ bền thực tế phụ thuộc nhiều lớp:

1. MySQL có phát lệnh flush/sync theo cấu hình hay không.
2. Filesystem và kernel có thực thi đúng yêu cầu đồng bộ hay không.
3. Controller và ổ đĩa có báo hoàn tất trước khi dữ liệu thật sự bền vững hay không.
4. Write cache có pin hoặc battery-backed protection hay có thể mất khi mất điện.
5. Hạ tầng lưu trữ có power-loss protection và firmware đáng tin cậy hay không.

Nếu thiết bị xác nhận flush nhưng chỉ giữ dữ liệu trong cache dễ bay hơi, cấu hình MySQL không thể tự tạo ra durability mà phần cứng không cung cấp. Với máy chủ vật lý, kiểm tra cache của RAID controller và pin bảo vệ. Với cloud volume, đọc cam kết durability/flush của dịch vụ lưu trữ và loại volume đang dùng.

## 8. Đo tác động đến hiệu năng

Trước khi thay đổi, hãy lưu baseline ở cùng workload:

```sql
SHOW GLOBAL STATUS LIKE 'Com_commit';
SHOW GLOBAL STATUS LIKE 'Innodb_os_log_fsyncs';
SHOW GLOBAL STATUS LIKE 'Innodb_log_waits';
SHOW GLOBAL VARIABLES LIKE 'innodb_flush_log_at_trx_commit';
SHOW GLOBAL VARIABLES LIKE 'sync_binlog';
```

Các status counter là số tích lũy từ lúc server khởi động hoặc được reset. Chụp hai lần ở hai thời điểm và tính chênh lệch thay vì chỉ đọc một giá trị. Tên và mức độ chi tiết của counter có thể thay đổi theo phiên bản.

Có thể xem các wait event trong Performance Schema:

```sql
SELECT EVENT_NAME,
       COUNT_STAR,
       ROUND(SUM_TIMER_WAIT / 1000000000000, 3) AS total_wait_seconds,
       ROUND(AVG_TIMER_WAIT / 1000000000, 3) AS avg_wait_ms
FROM performance_schema.events_waits_summary_global_by_event_name
WHERE EVENT_NAME LIKE '%log%'
   OR EVENT_NAME LIKE '%file%'
ORDER BY SUM_TIMER_WAIT DESC
LIMIT 30;
```

Tên event chính xác phụ thuộc phiên bản và instrumentation đang bật. Dùng truy vấn để khám phá các event hiện có; tập trung vào wait liên quan redo log, binlog và file I/O. Không kết luận chỉ từ tổng thời gian vì counter có thể tích lũy qua thời gian dài và bao gồm nhiều workload.

### Benchmark có kiểm soát

Một thử nghiệm hữu ích nên:

1. Dùng cùng dữ liệu, số client, transaction size và tỷ lệ đọc/ghi.
2. Giữ nguyên các cấu hình khác trong mỗi lượt thử.
3. Đo throughput, commit latency p95/p99, CPU, I/O latency và wait events.
4. Chạy đủ lâu để hệ thống đạt trạng thái ổn định; tránh so sánh một lượt cache nóng với một lượt cache lạnh.
5. Lặp lại thử nghiệm và lưu cấu hình cùng kết quả.
6. Đánh giá cả mức mất dữ liệu chấp nhận được, không chỉ TPS.

Không thử nghiệm nới lỏng durability trên dữ liệu production quan trọng nếu chưa có phê duyệt rủi ro, backup có thể restore và kế hoạch quay lại.

## 9. Liên hệ với replication và point-in-time recovery

Replica nhận các sự kiện từ binary log của source. Nếu binlog gần nhất chưa được sync bền vững khi source hoặc OS gặp sự cố, source có thể phục hồi dữ liệu khác với lịch sử sự kiện mà replica đã nhận hoặc đang cần đọc, tùy thời điểm sự cố và cơ chế replication. Cấu hình `sync_binlog=1` giảm cửa sổ sự kiện binlog chưa được đồng bộ.

PITR cần một full backup hoặc backup vật lý hợp lệ, cùng các file binlog liên tục từ thời điểm backup đến mốc phục hồi. Nếu binlog bị thiếu hoặc hỏng, không thể phát lại đến đúng thời điểm mong muốn. Vì vậy, `sync_binlog` là một phần của chiến lược durability, còn backup và kiểm tra chuỗi binlog là một phần của chiến lược phục hồi.

Với replication, hãy kiểm tra thêm:

- Binlog có bật và retention đủ dài không.
- Replica có theo kịp source và có lag bất thường không.
- Có giám sát lỗi đọc/ghi binlog và relay log không.
- Backup có kèm thông tin vị trí binlog hoặc GTID cần thiết không.
- Quy trình PITR đã được diễn tập trên môi trường độc lập chưa.

Replication không thay thế backup: thao tác xóa nhầm hoặc dữ liệu sai có thể được sao chép sang replica.

## 10. Quy trình thay đổi hai biến trong production

Trước khi điều chỉnh:

1. Xác định yêu cầu RPO và loại crash hệ thống cần chịu được.
2. Ghi lại giá trị hiện tại của hai biến và nguồn cấu hình.
3. Xác nhận redo log và binlog nằm trên thiết bị có đặc tính flush phù hợp.
4. Đo baseline về commit latency, TPS, log waits và I/O.
5. Thử thay đổi trên staging hoặc workload thử nghiệm đại diện.
6. Thay đổi từng biến có kiểm soát và xác minh giá trị runtime.
7. Theo dõi latency, error log, replication lag và khả năng phục hồi.
8. Có phương án khôi phục cấu hình cũ nếu hiệu năng hoặc độ ổn định suy giảm.

Kiểm tra giá trị sau khi thay đổi:

```sql
SELECT @@GLOBAL.innodb_flush_log_at_trx_commit AS redo_flush_policy,
       @@GLOBAL.sync_binlog AS binlog_sync_policy;
```

Nếu cần cấu hình bền vững qua restart, lưu bằng option file hoặc `SET PERSIST` theo quy trình quản lý cấu hình của tổ chức. Sau restart, kiểm tra lại giá trị hiệu lực; không chỉ xác nhận file đã được sửa.

## 11. Bảng chọn cấu hình theo mục tiêu

| Mục tiêu | `innodb_flush_log_at_trx_commit` | `sync_binlog` | Ghi chú |
|---|---:|---:|---|
| Ưu tiên durability cho giao dịch quan trọng | `1` | `1` | Lựa chọn khuyến nghị thông thường |
| Chấp nhận rủi ro mất một số giao dịch gần nhất để giảm I/O | `2` hoặc `0` | Giá trị lớn hơn `1` hoặc `0` | Phải định lượng RPO và hiểu loại crash có thể gây mất dữ liệu |
| Cần binlog bền vững cho replication/PITR nhưng đang đánh giá redo policy | `1` | `1` | Không nên đánh đổi riêng binlog khi chưa hiểu phối hợp commit |
| Chạy benchmark không yêu cầu dữ liệu thử nghiệm được bảo toàn | Có thể thử giá trị khác trong môi trường cô lập | Có thể thử giá trị khác trong môi trường cô lập | Không mang cấu hình benchmark sang production mà không đánh giá lại |

Không có cấu hình hiệu năng nào miễn phí. Giảm flush/sync có thể tăng throughput ở workload bị giới hạn bởi log I/O, nhưng đổi lại là cửa sổ mất dữ liệu lớn hơn. Nếu thiết bị lưu trữ chậm, nâng cấp storage có power-loss protection hoặc cải thiện I/O thường là hướng cần cân nhắc trước khi giảm yêu cầu durability.

## 12. Tự kiểm tra

1. Redo log và binary log phục vụ hai mục đích khác nhau nào?
2. `innodb_flush_log_at_trx_commit = 0`, `1` và `2` khác nhau ra sao?
3. `sync_binlog = 0`, `1` và `N` có ý nghĩa gì?
4. Vì sao `sync_binlog = 1` đồng bộ theo nhóm commit mà không nhất thiết sync riêng cho từng transaction?
5. Vì sao nên phối hợp cả hai biến ở giá trị `1` khi ưu tiên durability?
6. Khác biệt giữa mysqld process crash và OS/power crash ảnh hưởng thế nào đến giá trị `0` và `2`?
7. Vì sao MySQL không thể bảo đảm durability nếu storage controller báo flush sai?
8. `sync_binlog` ảnh hưởng đến replication và PITR như thế nào?
9. Cần đo những chỉ số nào trước khi đánh đổi durability để lấy throughput?

