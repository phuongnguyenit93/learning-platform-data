# Deadlock, thứ tự truy cập và chi phí thực hiện lại giao dịch

## Mục tiêu học tập

Sau bài học này, bạn có thể:

- Phân biệt deadlock với blocking, lock timeout và lỗi serialization.
- Mô tả chu trình chờ khóa bằng wait-for graph và xác định vì sao các giao dịch tạo thành chu trình.
- Thiết kế thứ tự truy cập bảng và hàng nhất quán để giảm nguy cơ deadlock.
- Rút ngắn thời gian giữ khóa bằng cách cải thiện truy vấn, chỉ mục, transaction scope và kích thước batch.
- Phát hiện deadlock qua công cụ của PostgreSQL, SQL Server và MySQL.
- Thiết kế retry có giới hạn, backoff, idempotency và quan sát chi phí thực hiện lại.

## 1. Deadlock là gì?

Deadlock (bế tắc giao dịch) xảy ra khi hai hoặc nhiều giao dịch giữ những tài nguyên mà giao dịch khác cần, đồng thời mỗi giao dịch lại chờ một tài nguyên đang do giao dịch khác giữ. Các giao dịch tạo thành một chu trình chờ nên không giao dịch nào có thể tiếp tục nếu không có một giao dịch bị hủy hoặc một điều kiện chờ được phá vỡ.

Ví dụ đơn giản:

- Giao dịch T1 khóa hàng A, sau đó cần khóa hàng B.
- Giao dịch T2 khóa hàng B, sau đó cần khóa hàng A.
- T1 chờ T2 nhả B; T2 chờ T1 nhả A.
- Cả hai không thể tự tiến triển.

Deadlock khác với blocking thông thường. Blocking chỉ có nghĩa một giao dịch đang chờ tài nguyên do giao dịch khác giữ; khi giao dịch giữ khóa commit hoặc rollback, giao dịch đang chờ có thể tiếp tục. Deadlock có chu trình chờ và cần hệ quản trị phá chu trình bằng cách chọn một giao dịch làm nạn nhân (victim), hoặc một cơ chế timeout/điều phối khác can thiệp.

Trong module DATABASE_PERFORMANCE, deadlock cần được xử lý như một vấn đề về thứ tự truy cập, thời gian giữ khóa, kế hoạch thực thi và mức đồng thời. Retry có thể giúp giao dịch hoàn tất, nhưng retry liên tục không sửa được nguyên nhân tạo chu trình.

## 2. Wait-for graph và chu trình khóa

Wait-for graph là đồ thị mô tả giao dịch nào đang chờ giao dịch nào. Mỗi đỉnh đại diện cho một transaction; một cạnh `T1 -> T2` nghĩa là T1 đang chờ tài nguyên mà T2 đang giữ.

Với ví dụ hai hàng:

```text
T1 giữ khóa A, chờ khóa B
T2 giữ khóa B, chờ khóa A

       chờ B
   T1 -------> T2
    ^          |
    |          |
    +----------+
       chờ A
```

Chu trình T1 → T2 → T1 là dấu hiệu deadlock. Với nhiều giao dịch, chu trình có thể dài hơn hai cạnh và liên quan đến nhiều bảng, index key, page hoặc loại tài nguyên khác nhau.

Deadlock không nhất thiết chỉ xảy ra khi hai câu UPDATE khóa hai hàng theo thứ tự ngược nhau. Các tài nguyên có thể gồm:

- Row/key lock hoặc record lock trên các hàng khác nhau.
- Page/table lock hoặc lock được nâng cấp từ mức thấp lên mức cao.
- Range/gap/next-key lock để bảo vệ một khoảng khóa.
- Metadata/schema lock trong một số thao tác DDL.
- Nhiều index được cập nhật bởi cùng một INSERT, UPDATE hoặc DELETE.
- Các tài nguyên đồng bộ nội bộ của hệ quản trị.

Loại khóa, phạm vi khóa và cách phát hiện deadlock phụ thuộc hệ quản trị, isolation level, execution plan và cấu trúc chỉ mục.

## 3. Ví dụ hai giao dịch cập nhật cùng hai tài khoản

Giả sử bảng tài khoản:

```sql
CREATE TABLE accounts (
    account_id BIGINT PRIMARY KEY,
    balance NUMERIC(19, 2) NOT NULL
);
```

Hai giao dịch chuyển tiền giữa tài khoản 101 và 202. T1 chuyển từ 101 sang 202; T2 chuyển theo chiều ngược lại.

```sql
-- Giao dịch T1
BEGIN;
UPDATE accounts
SET balance = balance - 100
WHERE account_id = 101;

UPDATE accounts
SET balance = balance + 100
WHERE account_id = 202;
COMMIT;
```

```sql
-- Giao dịch T2
BEGIN;
UPDATE accounts
SET balance = balance - 50
WHERE account_id = 202;

UPDATE accounts
SET balance = balance + 50
WHERE account_id = 101;
COMMIT;
```

Nếu T1 khóa hàng 101 trước và T2 khóa hàng 202 trước, sau đó mỗi giao dịch cần hàng còn lại, hai giao dịch có thể tạo deadlock. Đây là ví dụ minh họa lịch thực thi; deadlock thực tế phụ thuộc thời điểm, isolation level, engine và cách câu lệnh được triển khai.

### Thứ tự truy cập nhất quán

Một cách phòng ngừa là quy định mọi luồng nghiệp vụ khóa các tài khoản theo cùng thứ tự, chẳng hạn `account_id` tăng dần. Khi chuyển tiền giữa 101 và 202, cả T1 và T2 đều khóa 101 rồi mới khóa 202, bất kể chiều chuyển tiền.

Ví dụ với PostgreSQL:

```sql
BEGIN;

-- Khóa các hàng theo một thứ tự thống nhất
SELECT account_id
FROM accounts
WHERE account_id IN (101, 202)
ORDER BY account_id
FOR UPDATE;

-- Sau khi đã khóa đủ hàng, áp dụng các thay đổi
UPDATE accounts
SET balance = balance - 100
WHERE account_id = 101;

UPDATE accounts
SET balance = balance + 100
WHERE account_id = 202;

COMMIT;
```

Ví dụ này minh họa cách khóa theo thứ tự trong PostgreSQL. Với hệ quản trị khác, cú pháp và bảo đảm thứ tự khóa có thể khác. `ORDER BY` trong câu SELECT không phải là cam kết phổ quát rằng mọi engine sẽ lấy mọi loại khóa theo đúng thứ tự đó trong mọi execution plan. Hãy kiểm tra tài liệu engine, plan thực tế và thử nghiệm đồng thời.

Trong ứng dụng, một lựa chọn khác là chuẩn hóa danh sách ID, sắp xếp tăng dần rồi khóa từng hàng theo thứ tự trong cùng transaction. Cách này dễ hiểu nhưng có thể tạo nhiều round trip; có thể dùng một câu lệnh khóa theo tập hợp nếu hệ quản trị bảo đảm hành vi cần thiết.

Điều quan trọng là mọi đường code có thể khóa cùng tập tài nguyên phải tuân theo cùng một quy tắc, kể cả tác vụ nền, API quản trị và luồng xử lý batch.

## 4. Thứ tự truy cập nhiều bảng

Deadlock cũng xuất hiện khi hai giao dịch truy cập nhiều bảng theo thứ tự khác nhau.

Ví dụ:

- Luồng đặt hàng khóa `customers`, sau đó khóa `inventory`.
- Luồng hoàn kho khóa `inventory`, sau đó cập nhật `customers`.

Nếu hai luồng cùng làm việc trên một khách hàng và một mặt hàng, chúng có thể chờ lẫn nhau.

Hãy thiết lập thứ tự tài nguyên ở cấp ứng dụng, ví dụ:

1. Khóa hàng khách hàng.
2. Khóa hàng đơn hàng.
3. Khóa hàng tồn kho theo `product_id` tăng dần.
4. Ghi ledger hoặc bảng lịch sử.

Thứ tự cụ thể phụ thuộc mô hình dữ liệu. Mọi luồng ghi cần tuân theo cùng thứ tự; chỉ một luồng tuân thủ là chưa đủ.

Với bảng có nhiều hàng con, hãy sắp xếp khóa theo cùng một tiêu chí ổn định. Nếu một transaction cập nhật nhiều sản phẩm, khóa product ID tăng dần; transaction khác cũng phải làm như vậy.

### Chú ý đến index và execution plan

Thứ tự hàng được engine truy cập có thể bị ảnh hưởng bởi execution plan. Khi thêm chỉ mục, cập nhật thống kê hoặc nâng cấp phiên bản, optimizer có thể đổi scan, join order hoặc cách lấy hàng. Một truy vấn trông giống nhau có thể khóa tài nguyên theo lịch khác.

Vì vậy, nếu tính an toàn phụ thuộc thứ tự khóa, hãy dùng cơ chế khóa rõ ràng theo engine và xác minh bằng concurrency test. Không dựa vào thứ tự vật lý hiện tại của bảng hoặc giả định một index scan sẽ luôn duyệt hàng theo cùng cách.

## 5. Giảm deadlock bằng cách rút ngắn thời gian giữ khóa

Thời gian một transaction giữ khóa càng dài thì cửa sổ xảy ra xung đột càng lớn. Các biện pháp sau thường giúp:

- Chỉ mở transaction khi đã chuẩn bị xong dữ liệu cần thiết.
- Không gọi HTTP, gửi email, chờ người dùng hoặc thực hiện tác vụ chậm trong khi đang giữ khóa.
- Đọc và xử lý dữ liệu ngoài transaction nếu có thể, rồi mở transaction ngắn để kiểm tra và ghi.
- Giữ số câu lệnh và số hàng bị khóa ở mức cần thiết.
- Commit hoặc rollback ngay khi công việc trong transaction hoàn tất.
- Tránh transaction kéo dài qua nhiều bước tương tác hoặc qua hàng đợi.

Ví dụ không tốt là bắt đầu transaction, khóa đơn hàng, gọi dịch vụ thanh toán mất vài giây rồi mới cập nhật trạng thái. Trong thời gian chờ dịch vụ ngoài, các giao dịch khác có thể bị chặn.

Một thiết kế thường an toàn hơn là gọi dịch vụ ngoài trước theo cơ chế phù hợp, sau đó mở transaction ngắn để xác nhận trạng thái hiện tại và ghi kết quả. Nếu cần bảo đảm sự kiện ngoài và cập nhật database không bị lệch, hãy cân nhắc transactional outbox hoặc quy trình saga thay vì giữ khóa trong lúc gọi mạng.

## 6. Chỉ mục và độ rộng truy vấn ảnh hưởng đến tranh chấp

Chỉ mục phù hợp giúp engine tìm đúng hàng với ít lần đọc hơn. Khi truy vấn không có index phù hợp, engine có thể scan nhiều hàng hoặc nhiều trang trước khi tìm được hàng cần cập nhật. Tùy isolation level và engine, việc scan hoặc kiểm tra predicate có thể giữ khóa lâu hơn hoặc khóa phạm vi rộng hơn.

Ví dụ, nếu tác vụ cập nhật đơn theo `customer_id` nhưng thiếu chỉ mục trên cột này, hệ quản trị có thể phải đọc nhiều hàng để tìm các đơn liên quan. Chỉ mục phù hợp có thể giảm công việc tìm kiếm và thời gian transaction.

Tuy nhiên, thêm index cũng làm INSERT/UPDATE/DELETE phải duy trì thêm cấu trúc. Index quá nhiều có thể tăng write amplification, page contention và thời gian ghi. Cần đo cả lợi ích đọc lẫn chi phí ghi.

Những điểm nên xem:

- Predicate có dùng cột được lập chỉ mục không?
- Kiểu dữ liệu của tham số có khớp kiểu cột không?
- Có implicit conversion hoặc hàm trên cột làm giảm index access không?
- Execution plan có scan quá nhiều hàng trước khi cập nhật không?
- Có nhiều index trên cùng bảng khiến mỗi lần ghi phải cập nhật nhiều trang không?
- Chỉ mục có phân tán điểm ghi hay tạo hotspot ở một trang cuối không?

## 7. Isolation level, range lock và deadlock

Isolation level ảnh hưởng loại và thời gian khóa, cách đọc phiên bản dữ liệu và khả năng phát sinh xung đột.

- **Read Committed:** thường chỉ giữ một số khóa đọc trong thời gian ngắn hoặc dùng MVCC tùy engine; ghi vẫn cần khóa phù hợp.
- **Repeatable Read:** bảo đảm các hàng đã đọc giữ tính nhất quán theo cách engine triển khai; có thể giữ khóa lâu hơn hoặc dùng snapshot.
- **Serializable:** cung cấp mức cô lập cao hơn, có thể dùng range/predicate lock hoặc phát hiện xung đột serialization; có thể làm tăng blocking hoặc lỗi cần retry.
- **Snapshot/MVCC modes:** giảm một số xung đột đọc-ghi bằng phiên bản hàng, nhưng không loại bỏ xung đột giữa các giao dịch ghi cùng dữ liệu.

Không nên tăng isolation level để chữa deadlock nếu chưa xác định nguyên nhân. Isolation cao hơn có thể thêm khóa hoặc serialization failure. Ngược lại, hạ isolation tùy tiện có thể làm sai nghiệp vụ do dirty read, non-repeatable read hoặc phantom tùy engine.

### Range lock và phantom protection

Một giao dịch kiểm tra `WHERE quantity > 0` rồi cập nhật có thể cần bảo vệ không chỉ những hàng hiện có mà cả phạm vi có thể xuất hiện hàng mới, tùy isolation và engine. Range lock, gap lock hoặc predicate lock có thể khiến hai giao dịch xung đột dù chúng không cập nhật cùng một hàng hiện hữu.

Ví dụ, MySQL InnoDB ở một số mức isolation có thể dùng next-key lock để khóa bản ghi và khoảng khóa trong index. SQL Server ở SERIALIZABLE có thể dùng key-range lock. PostgreSQL SERIALIZABLE dùng Serializable Snapshot Isolation và có thể hủy giao dịch khi phát hiện xung đột serialization thay vì khóa mọi khoảng theo cùng cách.

Vì vậy, khi điều tra deadlock, hãy ghi nhận isolation level, index được dùng, predicate và loại lock thực tế, không chỉ nhìn câu SQL.

## 8. Tránh lock conversion và cập nhật cạnh tranh

Một tình huống dễ gây deadlock là nhiều giao dịch cùng đọc một hàng bằng khóa chia sẻ, sau đó cùng cố nâng cấp lên khóa độc quyền để cập nhật. Mỗi giao dịch giữ khóa đọc mà giao dịch kia cần chuyển đổi, tạo chu trình chờ.

Với nghiệp vụ chắc chắn sẽ cập nhật, có thể dùng cơ chế khóa cập nhật hoặc khóa ghi ngay từ đầu theo cú pháp của hệ quản trị, thay vì đọc lâu rồi mới nâng cấp. SQL Server có hint `UPDLOCK` trong một số trường hợp; PostgreSQL có `SELECT ... FOR UPDATE`; MySQL InnoDB có locking read `FOR UPDATE`.

Không dùng hint hoặc khóa mạnh hơn một cách đại trà. Khóa sớm có thể giảm một kiểu deadlock nhưng tăng blocking và giảm concurrency. Chỉ áp dụng cho đường nghiệp vụ đã xác định và đo lại.

### Dùng phép cập nhật nguyên tử khi phù hợp

Thay vì đọc số dư về ứng dụng, tính toán rồi ghi lại, có thể dùng một câu UPDATE có điều kiện:

```sql
UPDATE inventory
SET quantity = quantity - 1
WHERE product_id = ?
  AND quantity >= 1;
```

Ứng dụng kiểm tra số hàng bị ảnh hưởng: 1 nghĩa là đã trừ thành công; 0 nghĩa là không có hàng hoặc không đủ tồn kho theo điều kiện. Cần phân biệt hai trường hợp nếu nghiệp vụ yêu cầu.

Câu lệnh nguyên tử rút ngắn chuỗi đọc-sửa-ghi và tránh lost update kiểu ứng dụng tự tính rồi ghi đè. Nó không loại bỏ mọi deadlock nếu có nhiều tài nguyên hoặc giao dịch khác khóa theo thứ tự khác nhau.

## 9. Deadlock, lock timeout và serialization failure

Ba loại lỗi này thường cần cách xử lý khác nhau:

| Hiện tượng | Ý nghĩa | Hướng xử lý |
| --- | --- | --- |
| Deadlock | Có chu trình chờ khóa; engine chọn transaction victim hoặc phá chu trình | Retry toàn transaction nếu lỗi được xác định là tạm thời; đồng thời sửa thứ tự khóa hoặc thời gian giữ khóa |
| Lock timeout | Một thao tác chờ khóa quá thời hạn cấu hình | Điều tra blocker và thời gian chờ; retry có kiểm soát nếu phù hợp, nhưng không mặc định là deadlock |
| Serialization failure | Giao dịch không thể hoàn tất mà vẫn bảo đảm mức cô lập yêu cầu | Chạy lại toàn bộ transaction với dữ liệu/điều kiện được đọc lại |

Timeout có thể xảy ra mà không có chu trình. Ví dụ một báo cáo giữ khóa lâu và một cập nhật chờ quá hạn; khi báo cáo kết thúc, cập nhật có thể tiếp tục nếu chưa timeout.

Serialization failure cũng có thể xuất hiện trong hệ thống MVCC mà không có wait-for cycle. Không nên gom mọi lỗi database vào một nhánh retry giống nhau.

## 10. Hệ quản trị phát hiện và xử lý deadlock

### PostgreSQL

PostgreSQL theo dõi chờ khóa và chạy deadlock detection sau khoảng thời gian được điều khiển bởi `deadlock_timeout`. Khi phát hiện chu trình, một transaction bị hủy với SQLSTATE `40P01` (`deadlock_detected`). Ứng dụng cần rollback/khôi phục transaction theo trạng thái driver rồi mới chạy lại.

Các công cụ điều tra:

- `pg_stat_activity` để xem session, trạng thái và câu lệnh đang chạy.
- `pg_blocking_pids(pid)` để tìm session đang chặn một backend.
- `pg_locks` để xem các lock đang được giữ hoặc chờ.
- Log server để đọc thông báo deadlock và các chi tiết process/statement.
- `log_lock_waits` cùng `deadlock_timeout` để ghi nhận một số lock wait kéo dài; cấu hình log cần cân nhắc lượng log.

Ví dụ xem session đang chờ và blocker:

```sql
SELECT
    pid,
    wait_event_type,
    wait_event,
    state,
    query,
    pg_blocking_pids(pid) AS blocking_pids
FROM pg_stat_activity
WHERE wait_event_type = 'Lock';
```

Truy vấn cần quyền xem thông tin session tương ứng. Một lần chụp trạng thái chỉ phản ánh thời điểm truy vấn; deadlock đã kết thúc có thể cần đọc log để điều tra.

### SQL Server

SQL Server có deadlock monitor để phát hiện deadlock và chọn victim dựa trên tiêu chí nội bộ cùng `DEADLOCK_PRIORITY`. Transaction victim thường nhận lỗi 1205 và bị rollback.

Công cụ quan sát:

- Extended Events với sự kiện `xml_deadlock_report`.
- Session `system_health` mặc định thường thu thập deadlock graph, tùy cấu hình và thời gian lưu.
- Actual execution plan, Query Store và DMV về lock/wait để liên hệ câu lệnh với workload.
- Deadlock graph để xem process, resource, lock mode và quan hệ owner/waiter.

Không nên chỉ tăng `DEADLOCK_PRIORITY` cho một ứng dụng mà không hiểu tác động. Thay đổi priority chỉ ảnh hưởng lựa chọn victim; nó không loại bỏ chu trình khóa.

### MySQL InnoDB

InnoDB phát hiện deadlock và thường rollback một transaction được chọn làm victim. Lỗi deadlock phổ biến có mã 1213 (`ER_LOCK_DEADLOCK`). Lock wait timeout phổ biến có mã 1205 (`ER_LOCK_WAIT_TIMEOUT`) và có hành vi rollback khác tùy cấu hình, phiên bản và phạm vi statement/transaction.

Công cụ điều tra:

- `SHOW ENGINE INNODB STATUS` để xem phần LATEST DETECTED DEADLOCK.
- Performance Schema `data_locks` và `data_lock_waits` ở phiên bản hỗ trợ.
- InnoDB monitor hoặc deadlock logging nếu cần thu thập thường xuyên.
- Execution plan và index để hiểu thứ tự truy cập record/range.

Ví dụ xem trạng thái deadlock gần nhất:

```sql
SHOW ENGINE INNODB STATUS\G
```

Phần deadlock report thường chứa transaction, câu lệnh, index, record lock và transaction được rollback. Đây là snapshot gần nhất, nên cần thu thập kịp thời hoặc bật log phù hợp để không mất sự kiện.

## 11. Đọc deadlock graph để tìm nguyên nhân gốc

Khi có deadlock report, đừng chỉ ghi nhận tên câu SQL. Hãy dựng lại chuỗi sự kiện:

1. Transaction nào đang giữ resource nào?
2. Transaction nào đang chờ resource nào?
3. Resource thuộc bảng, index, khóa hoặc phạm vi nào?
4. Câu lệnh nào đã lấy khóa trước?
5. Các giao dịch có truy cập cùng tập bảng/hàng theo thứ tự khác nhau không?
6. Có scan lớn, range lock, trigger hoặc cascade mở rộng phạm vi khóa không?
7. Transaction có thực hiện gọi mạng, xử lý ứng dụng hoặc chờ lâu trong khi giữ khóa không?

Ví dụ deadlock graph có thể cho thấy T1 giữ khóa key K1 trên index của `orders` và chờ K2; T2 giữ K2 và chờ K1. Điều này gợi ý hai giao dịch đang cập nhật cùng hai đơn theo thứ tự ngược nhau.

Nếu resource là range hoặc page, hãy xem isolation level và index access. Nếu một transaction đi qua trigger hoặc cập nhật bảng phụ, phải đưa các thao tác gián tiếp đó vào sơ đồ thứ tự truy cập.

## 12. Retry giao dịch: chạy lại đúng đơn vị công việc

Khi engine hủy một transaction vì deadlock, ứng dụng thường cần chạy lại toàn bộ đơn vị giao dịch từ đầu. Chỉ chạy lại câu lệnh cuối có thể sai vì các câu trước đã bị rollback hoặc transaction đã ở trạng thái không thể tiếp tục.

Quy trình retry cơ bản:

1. Nhận diện đúng mã lỗi tạm thời của hệ quản trị.
2. Rollback transaction hoặc đóng/khôi phục connection theo yêu cầu của driver.
3. Chờ một khoảng ngắn có backoff và jitter.
4. Bắt đầu transaction mới.
5. Đọc lại dữ liệu và điều kiện hiện tại.
6. Thực hiện toàn bộ thao tác nghiệp vụ từ đầu.
7. Commit; nếu lại gặp lỗi transient, tăng thời gian chờ và thử trong giới hạn.

Không retry lỗi constraint, lỗi cú pháp, dữ liệu không hợp lệ hoặc lỗi nghiệp vụ vì chúng không tự biến mất khi chạy lại.

### Backoff và jitter

Exponential backoff tăng thời gian chờ sau mỗi lần thất bại, ví dụ 50 ms, 100 ms, 200 ms. Jitter thêm một thành phần ngẫu nhiên để các client không cùng retry tại một thời điểm và tạo một đợt tải mới.

Ví dụ minh họa:

```text
attempt 1: delay = random(0, 50 ms)
attempt 2: delay = random(0, 100 ms)
attempt 3: delay = random(0, 200 ms)
attempt 4: dừng và trả lỗi
```

Giá trị thực tế cần dựa trên latency mục tiêu, timeout request và mức tải. Luôn có số lần retry tối đa, tổng thời gian retry tối đa và một deadline của request.

### Không retry vô hạn

Retry làm tăng lượng công việc khi hệ thống đang quá tải. Nếu mọi request đồng loạt retry, throughput hữu ích giảm và deadlock có thể lặp lại nhiều hơn. Dùng retry budget, backoff, jitter và circuit breaker hoặc giới hạn concurrency khi phù hợp.

Retry chỉ là cơ chế phục hồi cho xung đột tạm thời. Nếu cùng cặp giao dịch luôn khóa theo thứ tự ngược nhau, deadlock có thể tiếp tục xảy ra ở mỗi lần retry. Cần sửa thứ tự truy cập hoặc thiết kế transaction.

## 13. Idempotency và tác dụng phụ ngoài database

Retry an toàn đòi hỏi thao tác có thể thực hiện lại mà không tạo tác dụng phụ trùng lặp.

Ví dụ, câu lệnh:

```sql
UPDATE orders
SET status = 'PAID'
WHERE order_id = ?;
```

có thể idempotent nếu quy tắc nghiệp vụ chỉ là đặt trạng thái thành PAID và các điều kiện khác được kiểm soát.

Ngược lại:

```sql
UPDATE accounts
SET balance = balance + 100
WHERE account_id = ?;
```

không idempotent: chạy hai lần sẽ cộng 200. Nếu client không biết lần commit trước đã thành công hay chưa do kết nối bị ngắt, retry có thể ghi trùng.

### Dùng idempotency key

Với thao tác tạo giao dịch, ứng dụng có thể gửi một idempotency key duy nhất và lưu key đó trong cùng transaction với kết quả nghiệp vụ. Một unique constraint bảo đảm cùng request không được áp dụng hai lần.

Ví dụ khái quát:

```sql
CREATE TABLE processed_requests (
    idempotency_key VARCHAR(100) PRIMARY KEY,
    result_reference BIGINT,
    created_at TIMESTAMP NOT NULL
);
```

Transaction kiểm tra hoặc chèn key, thực hiện cập nhật nghiệp vụ và lưu kết quả trong cùng transaction. Cách triển khai cần xử lý đồng thời hai request cùng key và xác định cách trả lại kết quả đã lưu.

### Không gửi email hoặc gọi dịch vụ ngoài trước khi commit

Nếu transaction cập nhật database rồi gửi email trước commit, transaction có thể bị rollback nhưng email đã gửi. Nếu gửi email sau commit mà process bị dừng trước khi gửi, email có thể bị mất.

Transactional outbox giải quyết vấn đề bằng cách ghi sự kiện cần gửi vào bảng outbox trong cùng transaction với cập nhật nghiệp vụ. Một worker riêng đọc outbox và gửi sự kiện; consumer cần idempotent vì việc gửi có thể lặp.

Không giữ khóa database trong khi chờ dịch vụ ngoài. Hãy tách tác dụng phụ thành bước sau commit hoặc quy trình bù có kiểm soát.

## 14. Chi phí thực hiện lại giao dịch

Retry có chi phí nhiều hơn một lần chạy lại câu SQL. Mỗi lần thử có thể tiêu tốn:

- CPU để parse, plan hoặc thực thi lại.
- I/O để đọc lại dữ liệu và cập nhật index.
- Log/WAL cho các thao tác được thực hiện trước khi transaction bị rollback, tùy engine.
- Thời gian chờ khóa và tài nguyên connection.
- Băng thông mạng và thời gian request.
- Công việc ứng dụng để dựng lại transaction context và kiểm tra điều kiện.

Rollback không có nghĩa mọi công việc trước đó miễn phí. Engine vẫn phải khôi phục trạng thái transaction và xử lý log/undo/version theo cơ chế của nó.

### Retry amplification

Nếu một request trung bình cần 1 lần chạy nhưng khi tải cao phải thử 3 lần, số lần thực thi database có thể tăng gấp ba trong giai đoạn đó. Tải tăng tạo thêm xung đột, xung đột tạo thêm retry, retry lại tăng tải. Đây là vòng khuếch đại.

Cần theo dõi:

- Tỷ lệ transaction retry trên tổng transaction.
- Số lần thử trung bình và phân vị số lần thử.
- Tổng thời gian từ lần thử đầu đến khi hoàn tất.
- CPU, I/O, lock wait và connection usage phát sinh bởi retry.
- Tỷ lệ request cuối cùng thất bại sau khi hết retry budget.

Đặt giới hạn retry theo deadline của nghiệp vụ. Nếu request có SLA 500 ms, không thể retry nhiều lần với backoff dài hơn thời gian còn lại.

## 15. Retry trong Java/JDBC

Ví dụ sau minh họa cấu trúc retry ở mức transaction. Hàm `isRetryableDeadlock` cần được cài đặt theo SQLState/vendor code của hệ quản trị và driver thực tế.

```java
int maxAttempts = 4;

for (int attempt = 1; attempt <= maxAttempts; attempt++) {
    try (Connection connection = dataSource.getConnection()) {
        connection.setAutoCommit(false);

        try {
            transferWithinTransaction(connection, fromId, toId, amount);
            connection.commit();
            return;
        } catch (SQLException e) {
            try {
                connection.rollback();
            } catch (SQLException rollbackError) {
                e.addSuppressed(rollbackError);
            }

            if (!isRetryableDeadlock(e) || attempt == maxAttempts) {
                throw e;
            }
        }
    }

    sleepWithExponentialBackoffAndJitter(attempt);
}
```

Đoạn mã chỉ là khung minh họa. Cần bổ sung deadline, interruption handling, phân loại lỗi theo driver, giới hạn tổng thời gian, metric và cách xử lý kết quả commit không rõ khi connection bị mất. Không retry trên connection còn ở trạng thái transaction lỗi.

Với Spring hoặc framework transaction khác, retry cần đặt ở lớp bao ngoài transaction để mỗi lần thử tạo một transaction mới. Nếu retry chạy bên trong cùng một transaction đã rollback-only, lần thử tiếp theo có thể thất bại ngay hoặc dùng trạng thái không hợp lệ.

### Phân loại lỗi theo hệ quản trị

| Hệ quản trị | Deadlock thường gặp | Lỗi khác cần phân biệt |
| --- | --- | --- |
| PostgreSQL | SQLSTATE `40P01` | `40001` serialization failure; lock timeout có thể có SQLSTATE riêng theo cấu hình |
| SQL Server | Error 1205 | Lock timeout thường là 1222; lỗi snapshot/update conflict có thể có mã khác |
| MySQL InnoDB | Error 1213 | Lock wait timeout thường là 1205 |

Đây là các mã phổ biến, không phải danh sách đầy đủ. Hãy kiểm tra SQLState, vendor code và trạng thái transaction theo phiên bản driver/hệ quản trị.

## 16. Batch và deadlock

Batch cập nhật nhiều hàng có thể giảm round trip nhưng cũng làm transaction giữ nhiều khóa cùng lúc. Nếu nhiều worker chạy batch trên cùng dữ liệu với thứ tự khác nhau, xác suất deadlock có thể tăng.

Biện pháp:

- Sắp xếp khóa theo cùng một thứ tự trước khi cập nhật.
- Chia batch vừa đủ để giới hạn thời gian và số khóa giữ đồng thời.
- Tránh để một batch bao phủ nhiều vùng dữ liệu không liên quan.
- Dùng `SKIP LOCKED` hoặc cơ chế phân phối công việc khi phù hợp, tránh nhiều worker cùng lấy một hàng.
- Ghi checkpoint nếu commit theo từng batch và nghiệp vụ cho phép tiến độ từng phần.
- Giới hạn số worker đồng thời khi tài nguyên hoặc hotspot đã bão hòa.

Chia nhỏ batch không bảo đảm hết deadlock; nó chỉ có thể giảm số tài nguyên giữ cùng lúc và thời gian giữ khóa. Nếu thứ tự truy cập vẫn ngược nhau, deadlock vẫn có thể xảy ra.

## 17. Optimistic concurrency và cách tránh khóa kéo dài

Với dữ liệu ít xung đột, optimistic concurrency control có thể phù hợp hơn giữ khóa từ lúc đọc đến lúc ghi. Một cột version hoặc timestamp được dùng để xác nhận bản ghi chưa thay đổi kể từ lần đọc.

Ví dụ:

```sql
UPDATE documents
SET body = ?,
    version = version + 1
WHERE document_id = ?
  AND version = ?;
```

Nếu số hàng bị ảnh hưởng bằng 0, một giao dịch khác đã cập nhật bản ghi hoặc version không còn khớp. Ứng dụng cần đọc lại, hòa giải thay đổi hoặc trả xung đột cho người dùng.

Optimistic concurrency giảm thời gian giữ khóa trong một số luồng, nhưng có thể tạo nhiều lần thử lại khi contention cao. Nó không thay thế transaction và không phù hợp với mọi quy tắc nghiệp vụ.

## 18. Kiểm thử deadlock có kiểm soát

Để tái hiện lỗi, cần tạo hai session độc lập và điều phối thời điểm thực thi. Không chạy thử nghiệm gây khóa trên dữ liệu sản xuất.

Kịch bản minh họa:

1. Session A bắt đầu transaction và cập nhật hàng 101.
2. Session B bắt đầu transaction và cập nhật hàng 202.
3. Session A cập nhật hàng 202 và chờ.
4. Session B cập nhật hàng 101, tạo chu trình.
5. Quan sát engine chọn victim và transaction còn lại tiếp tục sau khi khóa được giải phóng.

Sau đó sửa cả hai luồng để khóa hàng theo cùng thứ tự, chạy lại nhiều lần với concurrency khác nhau và xác nhận deadlock giảm.

Benchmark nên ghi nhận:

- Số deadlock trên 1.000 hoặc 1 triệu transaction.
- Tỷ lệ transaction bị rollback và retry.
- Số lần retry trung bình, p95/p99 của retry count.
- Throughput giao dịch thành công.
- p50/p95/p99 latency tính cả thời gian retry.
- Lock wait time, CPU, I/O và log bytes.
- Tỷ lệ lỗi cuối cùng sau khi hết retry budget.

Chỉ đo số deadlock giảm là chưa đủ. Một giải pháp có thể giảm deadlock nhưng làm mọi giao dịch chậm hơn do khóa quá sớm hoặc tuần tự hóa quá mức.

## 19. Quy trình điều tra và khắc phục

1. **Thu thập bằng chứng.** Lấy deadlock graph/log, timestamp, transaction ID, câu lệnh, resource và lock mode.
2. **Xác định chu trình.** Dựng wait-for graph để biết transaction nào giữ và chờ tài nguyên nào.
3. **Đối chiếu workload.** Tìm các luồng nghiệp vụ, batch, trigger, cascade hoặc tác vụ nền chạy cùng thời điểm.
4. **Đọc execution plan.** Kiểm tra scan, index lookup, join order, số hàng thực tế và phạm vi khóa.
5. **Xác định thứ tự truy cập.** So sánh thứ tự bảng, khóa và index giữa các transaction.
6. **Rút ngắn transaction.** Loại bỏ thời gian chờ ngoài database, giảm số câu lệnh và số hàng bị khóa.
7. **Sửa access path.** Bổ sung hoặc điều chỉnh index nếu có bằng chứng scan quá rộng; kiểm tra tác động ghi.
8. **Chuẩn hóa lock order.** Thiết lập thứ tự bảng và khóa thống nhất cho tất cả luồng.
9. **Thiết kế retry an toàn.** Retry toàn transaction cho lỗi transient, có backoff, jitter, deadline và idempotency.
10. **Benchmark lại.** So sánh deadlock rate, throughput, latency, lock wait và tài nguyên ở cùng mức concurrency.
11. **Theo dõi sau triển khai.** Xác nhận lỗi giảm ổn định và không chuyển thành timeout hoặc queueing kéo dài.

## 20. Những sai lầm thường gặp

- **Coi mọi lock wait là deadlock.** Blocking có thể tự kết thúc khi transaction giữ khóa commit hoặc rollback.
- **Chỉ tăng lock timeout.** Timeout dài hơn có thể làm request chờ lâu hơn mà không phá chu trình deadlock.
- **Retry riêng câu lệnh thất bại.** Transaction có thể đã bị rollback hoặc ở trạng thái không thể tiếp tục; cần chạy lại toàn bộ đơn vị giao dịch.
- **Retry vô hạn.** Làm tăng tải và khuếch đại contention khi hệ thống đang quá tải.
- **Retry cả lỗi dữ liệu.** Constraint violation và lỗi nghiệp vụ không tự hết khi chạy lại.
- **Không có idempotency.** Request bị thực thi lặp có thể cộng tiền, tạo đơn hoặc gửi sự kiện hai lần.
- **Chỉ chuẩn hóa thứ tự ở một API.** Tác vụ nền hoặc luồng khác vẫn có thể khóa theo thứ tự ngược.
- **Dựa vào thứ tự vật lý hoặc execution plan tình cờ.** Optimizer có thể đổi kế hoạch sau khi thống kê hoặc index thay đổi.
- **Tăng isolation level để chữa deadlock.** Có thể tăng blocking, range lock hoặc serialization failure.
- **Thêm index mà không đo.** Index có thể giảm scan nhưng làm tăng chi phí ghi và cạnh tranh trang.
- **Giữ transaction khi gọi dịch vụ ngoài.** Thời gian chờ mạng kéo dài cửa sổ giữ khóa.
- **Chỉ đo deadlock count.** Cần tính cả retry amplification, p95/p99 và throughput giao dịch thành công.

## 21. Danh sách kiểm tra trước khi triển khai

- [ ] Đã phân biệt deadlock, blocking, lock timeout và serialization failure.
- [ ] Có deadlock graph/log hoặc bằng chứng về resource và lock mode.
- [ ] Đã xác định chu trình wait-for và các transaction tham gia.
- [ ] Mọi luồng truy cập cùng tài nguyên có thứ tự khóa nhất quán.
- [ ] Không có gọi mạng hoặc chờ người dùng trong khi transaction giữ khóa.
- [ ] Execution plan và chỉ mục không gây scan rộng không cần thiết.
- [ ] Isolation level phù hợp với yêu cầu nhất quán.
- [ ] Batch size và concurrency đã được đo trên workload đại diện.
- [ ] Retry chỉ áp dụng cho lỗi transient đã phân loại.
- [ ] Retry có giới hạn, backoff, jitter và deadline.
- [ ] Toàn bộ transaction được chạy lại trong transaction mới.
- [ ] Các thao tác có idempotency key hoặc cơ chế chống tác dụng phụ lặp.
- [ ] Email, message và side effect ngoài database được xử lý sau commit hoặc qua outbox.
- [ ] Đã đo deadlock rate, retry count, throughput, p95/p99, lock wait và log/I/O.
- [ ] Có cảnh báo khi retry amplification hoặc lỗi cuối cùng vượt ngưỡng.

## Kết luận

Deadlock hình thành khi các giao dịch tạo chu trình chờ tài nguyên; nó khác với blocking đơn thuần và lock timeout. Phòng ngừa hiệu quả bắt đầu từ thứ tự truy cập bảng và hàng nhất quán, transaction ngắn, access path phù hợp và phạm vi khóa vừa đủ. Khi deadlock vẫn xảy ra, ứng dụng cần nhận diện đúng lỗi, rollback và chạy lại toàn bộ transaction trong một transaction mới với backoff, jitter và giới hạn rõ ràng. Retry phải an toàn nhờ idempotency và quản lý side effect; đồng thời cần đo chi phí thực hiện lại, lock wait, throughput và p95/p99 để tránh biến cơ chế phục hồi thành nguồn khuếch đại tải.
