# binlog cache, giao dịch lớn và chi phí ghi log

Binary log (binlog) ghi lại các thay đổi dữ liệu và một số sự kiện cần thiết để replica áp dụng thay đổi hoặc để khôi phục dữ liệu theo thời điểm (point-in-time recovery, PITR). Với bảng InnoDB, MySQL cần giữ các sự kiện của giao dịch cho đến khi biết giao dịch commit hay rollback. Cơ chế **binlog cache** làm nhiệm vụ lưu tạm các sự kiện đó trước khi chúng được ghi vào binary log.

Kích thước giao dịch, cách MySQL ghi cache, định dạng binlog và tần suất đồng bộ xuống storage đều ảnh hưởng đến dung lượng, độ trễ commit, tải I/O và thời gian replica áp dụng dữ liệu. Bài học này giải thích vòng đời của cache, cách nhận biết cache tràn ra tệp tạm, các tác động của giao dịch lớn và cách điều chỉnh chi phí ghi log mà vẫn giữ yêu cầu nhất quán và phục hồi của hệ thống.

Các ví dụ hướng đến MySQL 8.0. Một số biến và hành vi có thể khác giữa các phiên bản hoặc cấu hình; hãy kiểm tra giá trị thực tế trên instance trước khi áp dụng.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Mô tả vai trò của transaction cache và statement cache trong quá trình ghi binary log.
- Phân biệt cache dùng bộ nhớ với cache phải sử dụng tệp tạm, và hiểu giới hạn do `max_binlog_cache_size` kiểm soát.
- Đo mức độ cache spill bằng các status counter của MySQL.
- Giải thích vì sao giao dịch lớn làm tăng chi phí ghi log, độ trễ commit và replica lag.
- Chọn cách chia lô, định dạng row image, cấu hình cache và chính sách đồng bộ phù hợp với workload.

## 1. Vòng đời của binlog cache

Khi một session thực hiện câu lệnh làm thay đổi dữ liệu, MySQL tạo các sự kiện binlog tương ứng. Với giao dịch, các sự kiện được giữ tạm cho đến khi kết quả giao dịch được xác định. Nếu giao dịch rollback, các sự kiện thuộc phần thay đổi có thể rollback sẽ không được ghi như một giao dịch đã commit. Nếu giao dịch commit, MySQL đưa nhóm sự kiện vào binary log theo ranh giới giao dịch.

Có thể hình dung luồng xử lý như sau:

```text
Session thực hiện câu lệnh
          |
          v
   Tạo sự kiện binlog
          |
          v
   Chọn cache phù hợp
     /             \
    v               v
Transaction       Statement
cache             cache
    \               /
     \             /
      v           v
    Bộ nhớ cache đầy?
       /       \
     Chưa       Rồi
      |          |
      |          v
      |      Ghi tiếp vào
      |      tệp tạm
      |          |
      +-----+----+
            |
            v
      COMMIT / kết thúc
            |
            v
      Ghi nhóm sự kiện
      vào binary log
            |
            v
      Đồng bộ theo cấu hình
      và hoàn tất commit
```

Sơ đồ mô tả ý tưởng tổng quát. Chi tiết xử lý phụ thuộc storage engine, loại câu lệnh và định dạng binlog đang dùng.

### 1.1. Transaction cache

`binlog_cache_size` quy định kích thước bộ nhớ cache dùng để giữ sự kiện của giao dịch. Cache này phục vụ các thay đổi có thể được quản lý theo ranh giới giao dịch, chẳng hạn thay đổi trên bảng InnoDB. Khi dữ liệu binlog của một giao dịch vượt quá vùng nhớ cache, MySQL có thể tiếp tục lưu phần dữ liệu đó vào tệp tạm thay vì buộc giao dịch dừng ngay.

Giới hạn tối đa của transaction cache được kiểm soát bởi `max_binlog_cache_size`. Nếu một giao dịch cần nhiều dung lượng hơn giới hạn này, MySQL trả lỗi và giao dịch không thể tiếp tục theo cách thông thường. Vì vậy, `binlog_cache_size` và `max_binlog_cache_size` có vai trò khác nhau:

- `binlog_cache_size`: dung lượng bộ nhớ cache ban đầu cho transaction cache.
- `max_binlog_cache_size`: giới hạn trên cho lượng dữ liệu transaction cache của một giao dịch.

Tăng `binlog_cache_size` có thể giảm số giao dịch phải dùng tệp tạm, nhưng làm tăng tiềm năng sử dụng RAM khi có nhiều session đồng thời. Tăng `max_binlog_cache_size` cho phép một giao dịch lớn hơn, nhưng không làm giao dịch đó rẻ hơn: nó vẫn cần ghi, lưu trữ, truyền và áp dụng lượng dữ liệu tương ứng.

### 1.2. Statement cache

`binlog_stmt_cache_size` quy định vùng nhớ cache cho các câu lệnh không thể rollback theo cách của giao dịch, ví dụ câu lệnh làm thay đổi bảng dùng storage engine không hỗ trợ transaction. MySQL dùng statement cache để xử lý nhóm sự kiện này.

Giới hạn tối đa tương ứng là `max_binlog_stmt_cache_size`. Nếu statement cache vượt quá vùng nhớ, MySQL có thể dùng tệp tạm; nếu vượt giới hạn tối đa, câu lệnh có thể thất bại. Hai biến này phục vụ statement cache, không phải cách thay thế cho `binlog_cache_size` và `max_binlog_cache_size`.

Trong một workload có cả InnoDB và bảng nontransactional, cần quan sát cả hai nhóm counter. Chỉ xem transaction cache có thể bỏ sót áp lực phát sinh từ statement cache.

### 1.3. Cache spill không đồng nghĩa binary log đã được ghi

Khi cache vượt vùng nhớ, MySQL ghi dữ liệu cache vào tệp tạm. Đây là bước lưu trữ trung gian trước khi nhóm sự kiện được đưa vào binary log. Do đó, counter `Binlog_cache_disk_use` tăng không có nghĩa MySQL vừa ghi thêm một binary log file hoặc binary log đã được đồng bộ an toàn xuống storage.

Tệp tạm của cache tạo thêm I/O trên filesystem dùng cho temporary files. Nếu `tmpdir` nằm trên thiết bị chậm hoặc gần hết dung lượng, giao dịch lớn có thể làm tăng độ trễ hoặc thất bại dù phân vùng chứa binary log vẫn còn dung lượng.

## 2. Các biến cấu hình và giới hạn

Những biến quan trọng cần kiểm tra gồm:

| Biến | Vai trò | Cần cân nhắc |
|---|---|---|
| `binlog_cache_size` | Kích thước vùng nhớ transaction cache | Tăng khi có cache spill đáng kể và còn ngân sách RAM |
| `max_binlog_cache_size` | Giới hạn tối đa transaction cache của một giao dịch | Đặt đủ cho giao dịch hợp lệ lớn nhất mà hệ thống cho phép |
| `binlog_stmt_cache_size` | Kích thước vùng nhớ statement cache | Chỉ điều chỉnh khi statement cache có áp lực thực tế |
| `max_binlog_stmt_cache_size` | Giới hạn tối đa statement cache | Tránh lỗi với câu lệnh nontransactional hợp lệ, đồng thời kiểm soát mức sử dụng tài nguyên |
| `sync_binlog` | Tần suất đồng bộ binary log xuống storage | Cân bằng độ bền dữ liệu và chi phí fsync |
| `binlog_format` | Định dạng sự kiện: `ROW`, `STATEMENT` hoặc `MIXED` | Ảnh hưởng tính xác định, kích thước và khả năng áp dụng log |
| `binlog_row_image` | Mức độ ảnh trước/sau của row event | Ảnh hưởng dung lượng log và dữ liệu mà consumer có thể đọc |

Kiểm tra cấu hình hiện tại:

```sql
SHOW GLOBAL VARIABLES
WHERE Variable_name IN (
  'binlog_cache_size',
  'max_binlog_cache_size',
  'binlog_stmt_cache_size',
  'max_binlog_stmt_cache_size',
  'sync_binlog',
  'binlog_format',
  'binlog_row_image'
);
```

Không nên đặt `max_binlog_cache_size` thật lớn chỉ để loại bỏ lỗi của một giao dịch bất thường. Trước hết cần xác định giao dịch đó có hợp lý về nghiệp vụ hay đang cập nhật quá nhiều bản ghi trong một lần. Một giới hạn đủ lớn giúp workload hợp lệ hoạt động, nhưng giới hạn quá cao có thể cho phép một session chiếm nhiều tài nguyên và gây áp lực lên temporary storage.

## 3. Đo mức sử dụng cache

MySQL cung cấp các status counter để theo dõi transaction cache và statement cache:

| Counter | Ý nghĩa |
|---|---|
| `Binlog_cache_use` | Số lần giao dịch sử dụng transaction cache |
| `Binlog_cache_disk_use` | Số giao dịch phải dùng tệp tạm cho transaction cache |
| `Binlog_stmt_cache_use` | Số giao dịch sử dụng statement cache |
| `Binlog_stmt_cache_disk_use` | Số lần statement cache phải dùng tệp tạm |

Đọc counter:

```sql
SHOW GLOBAL STATUS
WHERE Variable_name IN (
  'Binlog_cache_use',
  'Binlog_cache_disk_use',
  'Binlog_stmt_cache_use',
  'Binlog_stmt_cache_disk_use'
);
```

Để đánh giá đúng, hãy chụp số liệu ở hai thời điểm rồi tính chênh lệch trong cùng một khoảng tải. Không nên chỉ nhìn tổng số tích lũy từ lúc MySQL khởi động, vì counter cũ có thể phản ánh workload đã thay đổi.

Tỷ lệ giao dịch dùng tệp tạm có thể ước lượng bằng:

\[
\text{Tỷ lệ spill (\%)} =
\frac{\Delta \text{Binlog\_cache\_disk\_use}}
     {\Delta \text{Binlog\_cache\_use}} \times 100
\]

Tính tương tự với statement cache. Nếu mẫu số bằng 0 thì chưa có giao dịch tương ứng trong khoảng đo và không thể diễn giải tỷ lệ. Tỷ lệ spill cao cho thấy nhiều giao dịch vượt vùng nhớ cache, nhưng chưa đủ để kết luận cần tăng cache: cần xem kích thước giao dịch, số session đồng thời, tốc độ I/O của `tmpdir` và ngân sách RAM.

Để quan sát biến và counter cùng nhau, có thể chạy:

```sql
SHOW GLOBAL STATUS LIKE 'Binlog%cache%';
SHOW GLOBAL VARIABLES LIKE '%binlog%cache%';
```

Nên kết hợp số liệu này với latency commit, throughput, dung lượng temporary filesystem, kích thước binary log và replica lag. Một tỷ lệ spill nhỏ có thể hoàn toàn chấp nhận được nếu I/O tệp tạm không phải nút thắt.

## 4. Vì sao giao dịch lớn làm tăng chi phí ghi log?

Giao dịch lớn có thể tạo nhiều row event, giữ cache lâu hơn và yêu cầu ghi một nhóm sự kiện lớn khi commit. Tác động xuất hiện ở nhiều tầng:

1. **Bộ nhớ và temporary storage:** transaction cache có thể vượt vùng nhớ và ghi tệp tạm. Nhiều giao dịch lớn đồng thời làm tăng áp lực RAM và I/O trên `tmpdir`.
2. **Binary log:** commit phải đưa nhóm sự kiện lớn vào binlog. Dung lượng binlog tăng, việc xoay vòng và lưu giữ log cần nhiều storage hơn.
3. **Độ trễ commit:** ghi nhiều dữ liệu và đồng bộ xuống storage có thể làm commit chậm. Nếu `sync_binlog` yêu cầu đồng bộ thường xuyên, chi phí fsync cũng ảnh hưởng đến latency.
4. **Khóa và undo:** giao dịch kéo dài thường giữ lock lâu hơn và tạo nhiều undo record. Điều này có thể làm các transaction khác phải chờ, đồng thời làm chậm quá trình purge của InnoDB.
5. **Replication:** replica phải nhận và áp dụng toàn bộ thay đổi của giao dịch. Một transaction lớn có thể mất nhiều thời gian apply và tạo replica lag; việc chia worker không làm mất ranh giới commit của giao dịch.
6. **PITR:** nhiều log hơn làm tăng dung lượng lưu trữ và lượng sự kiện phải phát lại khi khôi phục đến một thời điểm. Thời gian recovery còn phụ thuộc tốc độ đọc log, thực thi thay đổi và tài nguyên của máy đích.

`max_binlog_size` cũng không phải giới hạn cứng cho kích thước của một giao dịch. MySQL không chia một transaction đã commit thành nhiều transaction độc lập chỉ để giữ mỗi binlog file dưới giá trị này; một giao dịch lớn có thể khiến file vượt ngưỡng trước khi xoay vòng.

### 4.1. Kích thước row event

Với `binlog_format=ROW`, binary log ghi thay đổi ở mức hàng. Cách này tránh nhiều vấn đề không xác định của statement-based replication, nhưng một câu lệnh cập nhật hàng triệu bản ghi có thể tạo ra lượng row event rất lớn.

`binlog_row_image` quyết định mức độ ảnh được ghi cho row event:

- `FULL`: ghi ảnh đầy đủ theo quy tắc của row event; thuận tiện cho một số công cụ audit, CDC hoặc consumer cần dữ liệu trước/sau đầy đủ, nhưng thường tốn dung lượng hơn.
- `MINIMAL`: chỉ ghi các cột cần thiết để nhận diện hàng và các cột thay đổi theo quy tắc của MySQL; có thể giảm đáng kể dung lượng với bảng rộng.
- `NOBLOB`: giảm dữ liệu BLOB/TEXT không cần thiết trong các trường hợp được hỗ trợ.

Giảm row image có thể làm thay đổi lượng thông tin mà công cụ downstream nhận được. Trước khi dùng `MINIMAL` hoặc `NOBLOB`, cần kiểm tra yêu cầu của CDC, audit, giải mã binlog và quy trình khôi phục. Không đánh đổi khả năng phục hồi hoặc dữ liệu consumer cần chỉ để giảm dung lượng log.

## 5. Điều chỉnh chi phí ghi log

Điều chỉnh hiệu quả bắt đầu từ số liệu. Không nên tăng tất cả biến cache hoặc giảm độ bền chỉ vì thấy commit chậm.

### 5.1. Tăng cache khi số liệu chứng minh cần thiết

Nếu `Binlog_cache_disk_use` tăng nhanh trong workload bình thường, hãy xác định kích thước transaction thường gặp và phần RAM còn trống. Khi có đủ ngân sách bộ nhớ, tăng `binlog_cache_size` ở mức vừa phải có thể giúp nhiều giao dịch giữ được sự kiện trong RAM.

Ví dụ thay đổi runtime trên phiên bản hỗ trợ biến động tương ứng:

```sql
-- Ví dụ minh họa: 128 KiB, không phải giá trị tối ưu cho mọi hệ thống
SET GLOBAL binlog_cache_size = 131072;
```

Thay đổi `GLOBAL` không nhất thiết tự tồn tại sau khi restart; để giữ cấu hình, hãy cập nhật cấu hình khởi động theo quy trình quản lý cấu hình của hệ thống. Kiểm tra quyền quản trị cần thiết và khả năng thay đổi biến trên đúng phiên bản trước khi chạy.

Đánh giá lại counter, RAM và I/O sau thay đổi. Nếu cache spill giảm nhưng bộ nhớ tăng quá mức khi concurrency cao, cần cân bằng lại. `binlog_stmt_cache_size` chỉ nên tăng khi counter statement cache cho thấy vấn đề tương ứng.

### 5.2. Chọn giới hạn tối đa phù hợp

Nếu giao dịch hợp lệ thất bại vì vượt `max_binlog_cache_size`, hãy đo lượng dữ liệu binlog cần cho giao dịch đó và xác định giới hạn mới theo mức tối đa đã được kiểm thử. Làm tương tự với `max_binlog_stmt_cache_size` cho statement cache.

Không dùng việc nâng giới hạn như biện pháp duy nhất. Giao dịch quá lớn có thể gây lock lâu, tăng undo, chiếm temporary storage và tạo replica lag. Nếu nghiệp vụ cho phép, chia công việc thành các batch có kích thước được đo bằng dữ liệu thực tế.

### 5.3. Cân nhắc định dạng và row image

`ROW` thường được chọn cho replication hiện đại vì replica áp dụng thay đổi theo row event và ít phụ thuộc việc thực thi lại câu SQL. Tuy nhiên, lượng log có thể lớn khi cập nhật nhiều hàng hoặc bảng có nhiều cột rộng. Đánh giá `binlog_row_image=MINIMAL` nếu các consumer không cần ảnh đầy đủ.

`STATEMENT` có thể tạo log nhỏ hơn cho một số câu lệnh, nhưng cần bảo đảm câu lệnh có tính xác định và phù hợp với replication. Không chuyển từ `ROW` sang `STATEMENT` chỉ để giảm dung lượng nếu điều đó làm tăng nguy cơ replica nhận kết quả khác primary. `MIXED` để máy chủ chọn định dạng theo quy tắc của MySQL; vẫn cần hiểu hành vi của workload.

Trên các phiên bản MySQL hỗ trợ transaction compression (từ MySQL 8.0.20), có thể đánh giá `binlog_transaction_compression` để giảm dung lượng payload giao dịch trong binary log; tính năng này áp dụng cho payload row-based. Compression tiêu tốn CPU và cần tương thích với phiên bản, replica và công cụ đọc binlog. Hãy benchmark bằng dữ liệu đại diện trước khi bật trong production.

### 5.4. Cân bằng độ bền và chi phí fsync

`sync_binlog` điều khiển tần suất đồng bộ binary log xuống storage. Với `sync_binlog=1`, MySQL yêu cầu đồng bộ sau mỗi commit group; group commit có thể cho phép nhiều giao dịch chia sẻ một lần đồng bộ. Giá trị lớn hơn 1 hoặc 0 có thể giảm chi phí đồng bộ, nhưng tăng khả năng mất các binlog write gần nhất khi hệ điều hành hoặc máy chủ gặp sự cố, tùy trạng thái cache của OS và thiết bị lưu trữ.

Với InnoDB, `innodb_flush_log_at_trx_commit` điều khiển việc ghi và đồng bộ redo log. Binary log và redo log phục vụ hai mục đích khác nhau. Trong hệ thống cần độ bền cao, cấu hình thường dùng là:

```ini
[mysqld]
sync_binlog = 1
innodb_flush_log_at_trx_commit = 1
```

Hai thiết lập này có thể tăng chi phí I/O, nhưng giúp giảm cửa sổ mất dữ liệu khi crash. Chỉ thay đổi chúng sau khi đã thống nhất RPO, RTO và mức rủi ro dữ liệu mà tổ chức chấp nhận. Không dùng cấu hình ít bền hơn để che giấu vấn đề do giao dịch quá lớn hoặc storage chậm.

Group commit cho phép MySQL gom nhiều giao dịch commit gần nhau để giảm số lần đồng bộ. Các biến như `binlog_group_commit_sync_delay` và `binlog_group_commit_sync_no_delay_count` có thể điều chỉnh hành vi chờ gom nhóm trên các phiên bản hỗ trợ. Tăng thời gian chờ có thể cải thiện throughput trong một số workload nhưng cũng tăng latency; hãy đo trước và sau, không áp dụng một giá trị chung cho mọi hệ thống.

## 6. Kiểm soát giao dịch lớn ở tầng ứng dụng

### 6.1. Chia batch khi nghiệp vụ cho phép

Một tác vụ cập nhật hàng triệu đơn hàng có thể được xử lý theo batch. Ứng dụng chọn một tập khóa chính có giới hạn, cập nhật tập đó trong transaction ngắn, commit, lưu checkpoint rồi tiếp tục batch kế tiếp.

Ví dụ minh họa quy trình dùng danh sách khóa chính do ứng dụng lấy theo từng lô:

```sql
-- Ứng dụng truy vấn tối đa 1.000 id tiếp theo theo thứ tự khóa chính.
SELECT id
FROM orders
WHERE archived = 0
  AND created_at < '2024-01-01'
  AND id > 0
ORDER BY id
LIMIT 1000;

-- Ứng dụng truyền danh sách id vừa lấy vào transaction cập nhật.
START TRANSACTION;

UPDATE orders
SET archived = 1
WHERE id IN (101, 102, 103 /* ... các id trong batch ... */)
  AND archived = 0;

COMMIT;
```

Ứng dụng cần lưu khóa chính cuối cùng đã xử lý hoặc một checkpoint tương đương, và chỉ tiến checkpoint sau khi commit thành công. Điều kiện `archived = 0` giúp thao tác có thể chạy lại an toàn hơn trong trường hợp tiến trình bị gián đoạn. Kích thước 1.000 chỉ là ví dụ; số hàng phù hợp phụ thuộc độ rộng row, index, tốc độ storage, lock contention và giới hạn replica.

Chia batch làm giảm kích thước mỗi transaction, thời gian giữ lock và lượng binlog phải commit cùng lúc. Đổi lại, các batch commit riêng lẻ nên toàn bộ tác vụ không còn tính nguyên tử như một transaction duy nhất. Cần có checkpoint, retry idempotent, giám sát tiến độ và khả năng tiếp tục sau lỗi.

### 6.2. Giữ một transaction lớn khi tính nguyên tử là yêu cầu bắt buộc

Không chia một thao tác thành nhiều commit nếu nghiệp vụ yêu cầu tất cả thay đổi phải thành công hoặc thất bại cùng nhau. Trong trường hợp đó, cần:

- Ước lượng kích thước binlog và undo của transaction trước khi chạy.
- Đảm bảo `max_binlog_cache_size`, `tmpdir` và filesystem chứa binlog có đủ dung lượng.
- Chạy vào khung giờ phù hợp, kiểm soát concurrency và theo dõi lock wait.
- Kiểm tra replica có đủ năng lực apply và retention binlog có đủ cho PITR.
- Có kế hoạch rollback hoặc phục hồi đã được diễn tập.

Nếu một transaction không thể chia nhỏ mà vẫn đáp ứng nghiệp vụ, giới hạn tài nguyên phải được thiết kế cho trường hợp đó. Không nên giả định rằng tăng cache đơn thuần sẽ loại bỏ toàn bộ chi phí của transaction.

## 7. Quy trình chẩn đoán khi binlog gây chậm

Khi commit chậm hoặc replica lag tăng, hãy lần lượt xác định lớp đang tạo chi phí:

1. **Kiểm tra workload:** xác định transaction nào tạo nhiều thay đổi, thời gian mở transaction và số hàng bị tác động. Dùng log truy vấn, tracing ở ứng dụng hoặc công cụ quan sát hiện có.
2. **Kiểm tra cache counter:** so sánh delta của `Binlog_cache_use`, `Binlog_cache_disk_use` và các counter statement cache trong cùng khoảng tải.
3. **Kiểm tra temporary storage:** quan sát dung lượng trống, latency và throughput của filesystem `tmpdir`; tìm dấu hiệu I/O tăng khi transaction lớn chạy.
4. **Kiểm tra binary log:** theo dõi tốc độ tăng dung lượng, số lần xoay file và thời gian ghi/đồng bộ. Nhớ rằng `max_binlog_size` không chia nhỏ một transaction.
5. **Kiểm tra durability và storage:** xác nhận `sync_binlog`, `innodb_flush_log_at_trx_commit` và hiệu năng thiết bị lưu trữ; không hạ độ bền trước khi đánh giá RPO.
6. **Kiểm tra replica:** dùng `SHOW REPLICA STATUS` trên các phiên bản hỗ trợ cú pháp này, theo dõi trạng thái receiver/applier, lỗi và thời gian trễ. Phân biệt thời gian truyền log với thời gian apply transaction.
7. **Thử một thay đổi có kiểm soát:** chỉ thay một yếu tố mỗi lần, chạy lại workload đại diện và so sánh throughput, p95/p99 commit latency, cache spill, disk I/O và replica lag.

Một số câu lệnh kiểm tra tổng hợp:

```sql
SHOW GLOBAL STATUS
WHERE Variable_name IN (
  'Binlog_cache_use',
  'Binlog_cache_disk_use',
  'Binlog_stmt_cache_use',
  'Binlog_stmt_cache_disk_use'
);

SHOW GLOBAL VARIABLES
WHERE Variable_name IN (
  'binlog_cache_size',
  'max_binlog_cache_size',
  'binlog_stmt_cache_size',
  'max_binlog_stmt_cache_size',
  'sync_binlog',
  'innodb_flush_log_at_trx_commit'
);
```

`SHOW REPLICA STATUS` có thể được thay bằng cú pháp cũ trên các bản phát hành trước khi tên lệnh được đổi. Hãy dùng cú pháp phù hợp với phiên bản máy chủ và kiểm tra các trường lag cùng trạng thái SQL/applier thread, thay vì chỉ dựa vào một con số độ trễ.

## 8. Bài thực hành

Một hệ thống thương mại điện tử chạy InnoDB và `binlog_format=ROW`. Mỗi đêm, một job cập nhật trạng thái lưu trữ cho khoảng 5 triệu đơn hàng. Trong thời gian job chạy:

- `Binlog_cache_disk_use` tăng nhanh.
- Commit latency tăng rõ rệt.
- Replica lag kéo dài sau khi job kết thúc.
- Dung lượng binary log tăng nhanh hơn ngày thường.

Hãy xây dựng phương án xử lý và giải thích các quyết định:

1. Bạn cần lấy thêm số liệu nào để xác định transaction cache spill có phải nguyên nhân chính? Hãy nêu cách lấy delta của bốn counter cache.
2. Khi nào nên tăng `binlog_cache_size`? Vì sao cần xem RAM và số session đồng thời trước khi tăng?
3. Khi nào cần xem xét `max_binlog_cache_size`? Điều gì xảy ra nếu transaction vượt giới hạn tối đa?
4. Hãy thiết kế cách chia batch theo khóa chính, checkpoint và retry sao cho job có thể tiếp tục sau lỗi. Nêu rõ tính nguyên tử nào thay đổi khi mỗi batch commit riêng.
5. `binlog_row_image=MINIMAL` có thể giảm dung lượng trong trường hợp nào? Những công cụ downstream nào cần được kiểm tra trước khi thay đổi?
6. Giải thích mối quan hệ giữa `sync_binlog` và `innodb_flush_log_at_trx_commit`. Vì sao không nên giảm độ bền chỉ để làm job hoàn tất nhanh hơn?
7. Đề xuất cách kiểm tra replica apply và ước lượng tác động của job đến thời gian PITR.

Một phương án tốt phải chỉ ra số liệu trước/sau, tiêu chí rollback cấu hình và cách xác nhận tính đúng đắn dữ liệu sau khi job hoàn tất.

## 9. Những nhầm lẫn thường gặp

- **Cho rằng `Binlog_cache_disk_use` là số lần ghi binary log xuống đĩa:** counter này phản ánh việc cache giao dịch phải dùng tệp tạm khi vùng nhớ không đủ.
- **Tăng `binlog_cache_size` mà không xem concurrency:** một giá trị lớn có thể làm tăng nhu cầu RAM trong tải đồng thời.
- **Tăng `max_binlog_cache_size` để xử lý mọi giao dịch lớn:** giới hạn cao hơn cho phép transaction lớn hơn nhưng không giải quyết lock lâu, undo lớn, replica lag hoặc chi phí storage.
- **Chia batch mà không xem lại nghiệp vụ:** nhiều transaction nhỏ không có tính nguyên tử giống một transaction duy nhất; cần checkpoint và retry có kiểm soát.
- **Giảm `sync_binlog` mà không đánh giá RPO:** hiệu năng có thể tốt hơn nhưng rủi ro mất binary log gần nhất khi crash tăng lên.
- **Cho rằng `max_binlog_size` giới hạn tuyệt đối kích thước file:** một transaction có thể khiến file binlog vượt ngưỡng trước khi MySQL xoay vòng.
- **Chọn `MINIMAL` mà không kiểm tra consumer:** công cụ audit hoặc CDC có thể cần ảnh hàng đầy đủ để diễn giải thay đổi.

## Kết luận

Binlog cache giữ sự kiện tạm thời trước khi giao dịch được ghi vào binary log. Khi cache bộ nhớ không đủ, MySQL dùng tệp tạm; khi giao dịch vượt giới hạn tối đa, giao dịch có thể thất bại. Giao dịch lớn còn làm tăng lượng binlog, thời gian commit, áp lực lock/undo, replica lag và thời gian PITR. Việc tối ưu cần kết hợp quan sát counter, điều chỉnh cache theo ngân sách RAM, kiểm soát kích thước transaction, chọn row image phù hợp và giữ cấu hình durability theo RPO đã thống nhất. Hãy đo bằng workload đại diện và xác nhận replica cũng như quy trình phục hồi sau mỗi thay đổi quan trọng.
