# Khuếch đại ghi từ chỉ mục, cập nhật hàng và nhật ký

Một thao tác nghiệp vụ có thể chỉ thay đổi một vài byte, nhưng cơ sở dữ liệu phải thực hiện nhiều công việc hơn để bảo đảm dữ liệu đúng, có thể phục hồi sau sự cố và truy vấn được nhanh. Khi thêm một hàng, hệ quản trị có thể cập nhật trang dữ liệu, nhiều chỉ mục, cấu trúc kiểm tra ràng buộc và nhật ký giao dịch. Khi sửa một cột, nó có thể tạo phiên bản hàng mới, cập nhật các chỉ mục liên quan, ghi undo/redo hoặc WAL, rồi đồng bộ log trước khi xác nhận commit.

Hiện tượng lượng ghi nội bộ lớn hơn lượng thay đổi logic được gọi là **khuếch đại ghi** (*write amplification*). Khuếch đại ghi có thể đến từ số lượng chỉ mục, cách tổ chức hàng và page, cập nhật khóa, cơ chế MVCC, page split, checkpoint và yêu cầu durability. Nó làm tăng I/O, CPU, dung lượng log, thời gian commit và độ hao mòn thiết bị lưu trữ.

Trong module **DATABASE_PERFORMANCE**, cần hiểu đường đi của một thao tác ghi, nhận diện công việc phát sinh từ chỉ mục và cập nhật hàng, phân biệt transaction log với ghi data page, rồi đo lượng ghi trên mỗi thao tác nghiệp vụ. Mục tiêu là giảm công việc ghi không cần thiết trong khi vẫn giữ nguyên tính toàn vẹn, khả năng phục hồi và yêu cầu hiệu năng đọc.

## 1. Khuếch đại ghi là gì?

Ở mức khái quát, khuếch đại ghi mô tả lượng dữ liệu hệ thống phải ghi xuống tầng lưu trữ so với lượng dữ liệu logic mà ứng dụng yêu cầu thay đổi.

Một tỷ lệ minh họa có thể được định nghĩa như sau:

\[
\text{Write Amplification} =
\frac{\text{Bytes written at the measured layer}}
     {\text{Logical bytes changed by the workload}}
\]

Ví dụ, ứng dụng ghi mới 1 KB dữ liệu logic nhưng database tạo 6 KB transaction log, 4 KB page dữ liệu và 3 KB page chỉ mục trong khoảng đo, tổng lượng ghi quan sát được là 13 KB. Tỷ lệ ở phạm vi đo đó là 13 lần.

Đây chỉ là ví dụ để minh họa cách tính. Khi đo thực tế, phải xác định rõ phạm vi: bytes trong transaction log, bytes ghi từ database xuống thiết bị, bytes do storage controller ghi, hay bytes ghi xuống flash sau khi thiết bị tự quản lý block. Các lớp này không thể cộng hoặc so sánh tùy tiện.

### Phân biệt ba khái niệm

| Khái niệm | Nội dung | Ví dụ |
|---|---|---|
| Logical write | Thay đổi mà ứng dụng yêu cầu | Chèn một đơn hàng có 12 cột |
| Database write amplification | Công việc ghi phụ phát sinh trong database | Cập nhật bảng, 5 index, transaction log và page phiên bản |
| Storage/device write amplification | Thiết bị lưu trữ có thể ghi nhiều hơn lượng byte host gửi do garbage collection, erase block hoặc cơ chế nội bộ | SSD ghi lại các page trong flash block khi thu gom rác |

Một hệ thống có thể có write amplification cao ở database nhưng thấp ở thiết bị, hoặc ngược lại. Cần đo đúng tầng trước khi thay đổi schema, index hay cấu hình storage.

## 2. Đường đi của một thao tác ghi

Một lệnh `INSERT`, `UPDATE` hoặc `DELETE` thường trải qua nhiều bước. Trình tự chi tiết phụ thuộc hệ quản trị và cấu hình, nhưng có thể mô tả khái quát:

1. Phân tích câu lệnh, kiểm tra kiểu dữ liệu và quyền.
2. Tìm hàng hoặc vị trí cần thay đổi; lấy khóa và đồng bộ cấu trúc cần thiết.
3. Kiểm tra constraint, unique key, foreign key, trigger và quy tắc dữ liệu.
4. Thay đổi page dữ liệu hoặc tạo phiên bản hàng mới.
5. Cập nhật các index bị ảnh hưởng.
6. Tạo thông tin undo/redo hoặc bản ghi WAL/transaction log cần thiết.
7. Khi commit, bảo đảm log cần thiết đã được ghi bền vững theo cấu hình durability.
8. Data page đã thay đổi có thể được ghi xuống data file sau đó, chẳng hạn bởi background writer hoặc checkpoint.

Không phải mọi bước đều tạo một lần ghi vật lý riêng cho từng câu lệnh. Nhiều thay đổi có thể được gom trong buffer pool, log buffer hoặc batch I/O. Tuy nhiên, chúng vẫn tạo công việc CPU, bộ nhớ, log và ghi trang cần được xử lý.

### Log trước data page

Nhiều hệ quản trị dùng nguyên tắc write-ahead logging: thông tin log cần thiết phải được ghi bền vững trước khi page dữ liệu tương ứng được phép ghi xuống data file. Nhờ vậy, khi hệ thống gặp sự cố, database có thể dùng log để redo hoặc undo thay đổi và phục hồi trạng thái nhất quán.

Điều này có nghĩa commit thành công không nhất thiết đồng nghĩa mọi data page đã được ghi ngay xuống vị trí dữ liệu cuối cùng. Với chế độ durability thông thường, commit thường phải đợi log được flush đến mức bền vững mà cấu hình yêu cầu. Data page có thể được ghi sau. Vì vậy, khi đo I/O cần tách log write/flush khỏi data page write.

## 3. Chỉ mục làm tăng chi phí ghi như thế nào?

Mỗi chỉ mục là một cấu trúc dữ liệu cần được duy trì nhất quán với bảng. Một thao tác ghi vào bảng có thể phải thay đổi nhiều index, kể cả khi câu SQL chỉ nêu tên bảng một lần.

### INSERT

Khi chèn một hàng, hệ quản trị thường phải:

- Thêm hàng vào cấu trúc lưu trữ của bảng.
- Thêm khóa tương ứng vào từng index có liên quan.
- Kiểm tra unique constraint và các ràng buộc tham chiếu.
- Ghi log cho thay đổi dữ liệu và chỉ mục.
- Cập nhật thống kê hoặc cấu trúc nội bộ theo cơ chế của engine khi cần.

Nếu bảng có 12 chỉ mục, một lần insert có thể phải thực hiện công việc duy trì trên nhiều cấu trúc index. Không phải mọi index đều ghi cùng lượng dữ liệu, nhưng số lượng index lớn thường làm tăng CPU, log và I/O ghi.

### DELETE

Khi xóa hàng, database phải loại bỏ hoặc đánh dấu phiên bản hàng không còn hiệu lực và cập nhật các index liên quan. Trong hệ quản trị dùng MVCC, dữ liệu cũ có thể chưa được thu hồi ngay vì transaction khác vẫn có thể cần nhìn thấy phiên bản trước. Việc dọn dẹp có thể diễn ra sau thông qua vacuum, purge hoặc cơ chế tương đương.

Xóa hàng loạt vì vậy có thể tạo lượng log lớn, làm tăng số page bẩn và tạo thêm công việc dọn phiên bản cũ. Chia batch có thể giảm thời gian giữ khóa và kích thước transaction, nhưng batch quá nhỏ lại tăng overhead commit.

### UPDATE

Chi phí cập nhật phụ thuộc cột thay đổi và cách lưu trữ:

- Nếu cột không thuộc index thay đổi, một số engine có thể tránh sửa index tương ứng.
- Nếu cột khóa index thay đổi, entry cũ thường phải bị loại bỏ hoặc đánh dấu không còn hợp lệ và entry mới được thêm.
- Nếu khóa chính thay đổi, chi phí có thể lan sang các index phụ và các bảng tham chiếu.
- Nếu hàng lớn lên, nó có thể không còn vừa page cũ, gây di chuyển hàng hoặc page split tùy engine.
- Nếu hệ quản trị tạo phiên bản hàng mới theo MVCC, update có thể tạo thêm dữ liệu phiên bản và log.

### Ví dụ bảng có nhiều index

```sql
CREATE TABLE orders (
    order_id       BIGINT PRIMARY KEY,
    customer_id    BIGINT NOT NULL,
    status         VARCHAR(20) NOT NULL,
    created_at     TIMESTAMP NOT NULL,
    external_ref   VARCHAR(100),
    total_amount   DECIMAL(18, 2) NOT NULL
);

CREATE INDEX ix_orders_customer
    ON orders (customer_id);

CREATE INDEX ix_orders_status_created
    ON orders (status, created_at);

CREATE UNIQUE INDEX ux_orders_external_ref
    ON orders (external_ref);

CREATE INDEX ix_orders_created
    ON orders (created_at);
```

Một `INSERT` phải duy trì khóa chính và các index phụ. Khi chỉ cập nhật `total_amount`, index không chứa cột này có thể không cần thay entry, nhưng bảng vẫn cần ghi thay đổi và log. Khi cập nhật `status`, index `(status, created_at)` bị ảnh hưởng vì khóa index thay đổi.

## 4. Thiết kế chỉ mục và ngân sách ghi

Chỉ mục giảm chi phí đọc bằng cách cung cấp đường truy cập nhanh, nhưng mỗi index làm tăng chi phí duy trì khi dữ liệu thay đổi. Thiết kế tốt cần cân bằng workload đọc và ghi, không tối đa hóa số lượng index.

### Chỉ giữ index có giá trị

Trước khi thêm index, xác định:

- Truy vấn nào sử dụng index và tần suất chạy.
- Index có giảm đáng kể rows read, logical reads hoặc latency không.
- Index có trùng lặp hoàn toàn hoặc trùng tiền tố với index khác không.
- Index có kích thước lớn so với lợi ích đọc không.
- Index có làm tăng thời gian insert/update/delete hoặc lock contention không.

Index ít được dùng nhưng tốn dung lượng và phải cập nhật trên mọi thao tác ghi có thể là ứng viên cần loại bỏ. Tuy nhiên, index có thể phục vụ constraint, foreign key, báo cáo định kỳ hoặc truy vấn hiếm nhưng quan trọng. Không xóa chỉ dựa vào thống kê ngắn hạn; cần xem đầy đủ chu kỳ workload và yêu cầu toàn vẹn.

### Index ghép thay cho nhiều index đơn

Nếu workload thường xuyên lọc theo cùng một tổ hợp cột, một composite index có thể thay thế một số index đơn lẻ. Ví dụ, truy vấn thường tìm đơn hàng theo tenant và thời gian:

```sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE tenant_id = ?
  AND created_at >= ?
ORDER BY created_at DESC;
```

Index `(tenant_id, created_at)` có thể hỗ trợ cả điều kiện bằng trên tenant và range/order trên thời gian. Tuy nhiên, index ghép không tự thay thế mọi index đơn: truy vấn chỉ lọc `created_at` mà không có `tenant_id` có thể không dùng được tiền tố index hiệu quả. Phải kiểm tra toàn bộ workload trước khi hợp nhất.

### Index phủ và cột INCLUDE

Index phủ có thể giảm lookup khi truy vấn chỉ cần các cột nằm trong index. Nhưng thêm cột vào index làm tăng kích thước, cache footprint và chi phí ghi. Nếu cột được cập nhật thường xuyên, đưa nó vào khóa index có thể khiến mỗi update phải thay entry. Một số hệ quản trị cho phép cột INCLUDE ở phần leaf để phục vụ projection mà không tham gia thứ tự khóa; vẫn cần cập nhật phần dữ liệu index khi giá trị include thay đổi.

### Index duy nhất và foreign key

Unique index vừa hỗ trợ truy vấn vừa thực thi tính duy nhất, vì vậy không nên bỏ nếu constraint còn hiệu lực. Foreign key cũng có thể cần index phía bảng con để tăng tốc kiểm tra, join và thao tác xóa/cập nhật bảng cha. Quyết định nên dựa trên mô hình quan hệ, workload và hành vi cụ thể của hệ quản trị.

## 5. Cập nhật khóa index và chi phí page split

B-tree giữ khóa theo thứ tự. Khi insert một khóa mới vào page đã gần đầy, engine có thể phải chia page (*page split*) để tạo chỗ. Page split có thể làm phát sinh thêm page write, log, cập nhật parent page và phân mảnh vật lý.

### Khóa tăng tuần tự

Khóa tăng tuần tự thường chèn vào vùng cuối index. Cách này có thể giảm page split ở các vùng cũ và tăng locality, nhưng dưới tải ghi rất cao, trang cuối có thể trở thành điểm tranh chấp latch/page.

### Khóa ngẫu nhiên

Khóa ngẫu nhiên phân tán vị trí insert trên cây, có thể giảm hot page cuối nhưng tăng insert vào nhiều vùng, gây page split và I/O ngẫu nhiên. Nếu khóa là UUID 128-bit, index cũng có thể lớn hơn khóa số 64-bit.

Không có kiểu khóa tối ưu cho mọi hệ thống. Cần đánh giá insert throughput, page split, latch wait, kích thước index, cache hit và chi phí truy vấn theo khóa.

### Fill factor và khoảng trống page

Một số hệ quản trị cho phép để lại khoảng trống trong page khi build/rebuild index thông qua fill factor hoặc tham số tương tự. Khoảng trống có thể giảm page split với workload có insert/update ở giữa vùng khóa, nhưng làm index lớn hơn và tăng số page cần đọc. Fill factor thấp không phải giải pháp chung cho mọi index; cần thử trên index có page split đáng kể.

## 6. Cập nhật hàng, row width và MVCC

Một lần update không nhất thiết ghi đè tại chỗ. Nhiều engine dùng MVCC hoặc cơ chế phiên bản để cho phép reader và writer hoạt động đồng thời theo snapshot. Khi đó, update có thể tạo phiên bản mới và giữ phiên bản cũ đến khi không còn transaction nào cần nó.

### PostgreSQL: tuple version và HOT update

PostgreSQL dùng MVCC; update thường tạo tuple version mới, còn tuple cũ được đánh dấu không còn là phiên bản hiện hành. Vacuum dọn các phiên bản không còn cần thiết. Nếu update không thay đổi cột được index tham chiếu và page còn đủ chỗ, PostgreSQL có thể dùng HOT (*Heap-Only Tuple*) update để tránh cập nhật index. HOT có thể giảm write amplification đáng kể với bảng cập nhật nhiều.

Các yếu tố cần xem gồm:

- Cột thay đổi có xuất hiện trong index hoặc biểu thức index không.
- Page có đủ chỗ cho tuple mới không.
- Fillfactor của bảng có tạo không gian dự phòng hợp lý không.
- Dead tuples và vacuum có được xử lý kịp thời không.

Không nên hạ fillfactor cho toàn bộ bảng mà chưa đo. Dự phòng chỗ trống làm tăng số page và có thể tăng chi phí đọc.

### SQL Server: row versioning và transaction log

SQL Server dùng transaction log để ghi lại thay đổi cần thiết cho recovery. Tùy isolation level và cấu hình row versioning, phiên bản hàng có thể được lưu trong version store (ví dụ tempdb hoặc persistent version store trong cấu hình phù hợp). Update index key hoặc clustered key có thể làm phát sinh cập nhật trên nhiều index phụ.

Khi cập nhật cột không thuộc index, engine vẫn phải ghi thay đổi hàng và log, nhưng có thể tránh sửa index phụ không liên quan. Nếu cột được thêm vào nonclustered index dưới dạng key hoặc included column, thay đổi giá trị đó cũng tạo chi phí duy trì index.

### MySQL/InnoDB: clustered index, undo và redo

InnoDB lưu hàng trong clustered index, thường dựa trên primary key. Secondary index lưu khóa phụ cùng giá trị primary key để tìm hàng tương ứng. Vì vậy, primary key dài có thể làm mọi secondary index lớn hơn. Thay đổi primary key có thể đắt vì vị trí hàng trong clustered index thay đổi và các secondary index cần được duy trì.

InnoDB dùng undo log để hỗ trợ rollback và consistent read, redo log để phục hồi thay đổi page, cùng các cơ chế flush/doublewrite tùy phiên bản và cấu hình. Update nhiều hàng hoặc giữ transaction lâu có thể làm undo history tăng và gây thêm công việc purge.

### Oracle Database: undo và redo

Oracle dùng undo để hỗ trợ read consistency và rollback, redo để phục hồi thay đổi. Update hàng và index tạo redo; undo record lưu thông tin cần thiết để khôi phục hoặc cung cấp phiên bản nhất quán cho reader. Một giao dịch cập nhật nhiều index có thể tạo lượng redo đáng kể dù payload ứng dụng nhỏ.

Với workload ghi lớn, cần theo dõi redo generation, log switch, log file sync, undo tablespace và I/O trên datafile/index segment. Các thao tác direct-path hoặc bulk có quy tắc logging riêng, phụ thuộc chế độ và cấu hình; không được giả định mọi thao tác bulk đều không ghi redo.

## 7. Transaction log, WAL, redo và undo

Transaction log là một phần quan trọng của chi phí ghi. Database cần lưu đủ thông tin để phục hồi sau crash, rollback transaction và hỗ trợ các cơ chế như replication hoặc point-in-time recovery.

| Cơ chế | Vai trò khái quát |
|---|---|
| WAL / redo log | Ghi thông tin thay đổi để có thể áp dụng lại sau sự cố |
| Undo log / undo segment | Khôi phục trạng thái trước đó hoặc cung cấp phiên bản dữ liệu cũ tùy engine |
| Transaction log | Ghi chuỗi thay đổi và ranh giới transaction để recovery |
| Binary log / logical log | Ghi sự kiện hoặc thay đổi phục vụ replication, CDC và khôi phục tùy hệ quản trị |
| Checkpoint | Đưa một phần dirty page xuống data file và đánh dấu tiến độ recovery |

Một thay đổi logic có thể xuất hiện trong nhiều loại log hoặc cấu trúc. Ví dụ, InnoDB có redo/undo và binary log nếu bật; SQL Server có transaction log và có thể thêm overhead cho CDC/replication; PostgreSQL có WAL và có thể phát sinh thêm WAL cho logical decoding hoặc replica. Không cộng tất cả số liệu log với data write nếu chúng được đo ở các tầng khác nhau hoặc cùng một byte đã đi qua nhiều tầng.

### Commit latency và log flush

Với durability đồng bộ, transaction thường phải đợi log được flush đến vị trí commit cần thiết trước khi trả kết quả thành công. Nếu log device có latency cao, nhiều transaction nhỏ có thể bị giới hạn bởi số lần flush hoặc tốc độ ghi log dù data page chưa cần ghi ngay.

Batching có thể giảm số lần commit và gom nhiều thay đổi vào ít lần flush hơn, nhưng transaction lớn hơn sẽ giữ khóa lâu hơn và tạo log lớn hơn. Cần cân bằng kích thước batch, độ trễ chấp nhận được, khả năng rollback và replication lag.

### Checkpoint và ghi data page

Dirty page được ghi xuống data file theo lịch checkpoint hoặc cơ chế background writer. Nếu checkpoint quá dồn dập, hệ thống có thể tạo write burst và tăng I/O latency. Nếu checkpoint quá thưa, lượng log cần xử lý khi recovery có thể tăng. Cấu hình checkpoint là đánh đổi giữa độ mượt I/O, recovery time và khả năng ghi của storage.

## 8. Trigger, constraint và các công việc ghi phụ

Một lệnh ghi có thể kích hoạt thêm công việc ngoài index maintenance:

- Trigger ghi lịch sử hoặc cập nhật bảng tổng hợp.
- Foreign key kiểm tra quan hệ và có thể cần tìm hàng ở bảng cha/con.
- Unique constraint kiểm tra khóa trùng.
- Cascade update/delete tác động đến các hàng liên quan.
- Audit log hoặc CDC ghi thêm thông tin thay đổi.
- Replication gửi log hoặc sự kiện sang replica/consumer.

Các cơ chế này có thể cần thiết cho tính đúng và kiểm toán, nhưng phải được tính vào ngân sách ghi. Trigger thực hiện nhiều câu SQL bên trong có thể khiến một lệnh ứng dụng đơn giản tạo hàng chục thao tác ghi.

### Kiểm tra đường ghi đầy đủ

Khi một endpoint chậm, không chỉ đọc câu SQL trực tiếp. Hãy kiểm tra trigger, cascade, stored procedure, ORM hook, audit, replication và job đồng bộ có chạy cùng transaction hay không. Đo số hàng bị tác động ở từng bảng và số byte log phát sinh.

## 9. Bulk insert, batching và thứ tự ghi

Khi nạp dữ liệu số lượng lớn, dùng một câu `INSERT` cho từng hàng có thể tạo nhiều round trip, parse/execute overhead và commit. Bulk load hoặc batch insert có thể giảm overhead và tăng thông lượng.

### Batch insert

```sql
INSERT INTO event_log (event_id, tenant_id, event_type, created_at)
VALUES
    (?, ?, ?, ?),
    (?, ?, ?, ?),
    (?, ?, ?, ?);
```

Cú pháp multi-row insert được nhiều hệ quản trị hỗ trợ, nhưng giới hạn số hàng, tham số và kích thước packet khác nhau. Batch lớn giảm round trip nhưng tăng bộ nhớ, log, thời gian transaction và chi phí rollback. Hãy thử nhiều kích thước batch trên môi trường đại diện.

### Bulk load và index maintenance

Với nạp dữ liệu ban đầu hoặc staging, một số hệ quản trị hỗ trợ bulk load, direct-path insert hoặc minimal logging trong điều kiện cụ thể. Có trường hợp tạo index sau khi nạp dữ liệu nhanh hơn duy trì index cho từng hàng. Tuy nhiên, bỏ index trong lúc hệ thống đang phục vụ truy vấn có thể làm truy vấn chậm hoặc phá vỡ constraint nếu index duy nhất bị loại bỏ.

Trước khi dùng chế độ logging tối thiểu hoặc tắt constraint/index, phải kiểm tra recovery model, replication, backup, quyền, tính toàn vẹn và yêu cầu phục hồi. Không được giả định minimal logging nghĩa là không có log hoặc có thể khôi phục theo mọi cách.

### Ghi theo thứ tự khóa

Nếu batch cập nhật nhiều hàng, xử lý theo thứ tự khóa nhất quán có thể giảm deadlock và cải thiện locality ở một số workload. Tuy nhiên, việc sắp xếp batch cũng tốn CPU/bộ nhớ và không loại bỏ mọi dạng contention. Hãy đo trên đúng cấu trúc index và mẫu truy cập.

## 10. Giảm write amplification bằng thiết kế dữ liệu

### Tránh cập nhật không cần thiết

Không gửi `UPDATE` nếu giá trị mới giống giá trị hiện tại, khi điều kiện và semantics cho phép. Một số engine có thể tránh một phần công việc trong một số trường hợp, nhưng không nên dựa vào tối ưu nội bộ mà không đo.

Ví dụ:

```sql
UPDATE customer
SET display_name = :display_name
WHERE customer_id = :customer_id
  AND display_name <> :display_name;
```

Điều kiện này có vấn đề nếu `display_name` có thể `NULL`, vì phép so sánh với `NULL` không trả true. Nếu cột nullable, cần dùng phép so sánh null-safe phù hợp hệ quản trị hoặc bảo đảm schema `NOT NULL`.

### Giảm số index

Loại bỏ index trùng lặp hoặc ít giá trị sau khi xác minh constraint và workload. Mỗi index bị loại có thể giảm CPU, log và page write trên mọi thao tác ghi liên quan.

### Tách cột ít cập nhật và cột cập nhật thường xuyên

Nếu một hàng chứa nhiều cột lớn ít thay đổi nhưng các cột trạng thái nhỏ được cập nhật liên tục, có thể cân nhắc tách nhóm cột theo mẫu truy cập. Tuy nhiên, với MVCC, tách bảng có thể tạo join và transaction bổ sung; chỉ nên làm khi lợi ích đo được vượt chi phí.

### Hạn chế cập nhật khóa index

Nếu cột thay đổi liên tục nhưng nằm trong nhiều index, mỗi lần cập nhật có thể phải sửa nhiều cấu trúc. Hãy đánh giá có cần index cột đó hay không, có thể dùng cột khác ổn định hơn, hoặc có thể tách dữ liệu trạng thái khỏi bảng chứa nhiều index không.

### Dùng kiểu dữ liệu phù hợp

Khóa index dài làm tăng kích thước cấu trúc và số byte ghi. Dùng kiểu số nhỏ hơn, mã hóa khóa nghiệp vụ hợp lý hoặc surrogate key có thể giảm kích thước index, nhưng cần giữ unique constraint cho khóa nghiệp vụ nếu yêu cầu. Không rút ngắn dữ liệu tùy tiện làm mất khả năng phân biệt giá trị.

## 11. Khác biệt đường ghi theo hệ quản trị

Các cơ chế bên dưới có cùng mục tiêu bảo đảm nhất quán và phục hồi, nhưng cách lưu trữ và tên công cụ khác nhau.

### PostgreSQL

PostgreSQL ghi WAL cho thay đổi cần phục hồi. Data page thay đổi được giữ trong shared buffers và ghi ra data file theo checkpoint/background writer. `full_page_writes` có thể ghi full-page image trong WAL cho lần thay đổi đầu tiên của page sau checkpoint nhằm bảo vệ trước torn page; điều này có thể làm WAL tăng, đặc biệt khi checkpoint dày hoặc page nóng. Cần xem WAL bytes, checkpoint statistics, `pg_stat_wal`, `pg_stat_bgwriter` hoặc view thay thế theo phiên bản, cùng `EXPLAIN (ANALYZE, BUFFERS)`.

Update có thể tạo tuple version mới. HOT update giảm index maintenance nếu không đổi cột được index tham chiếu và page còn chỗ. Nhiều index trên bảng cập nhật thường xuyên làm giảm cơ hội HOT. Vacuum cần dọn phiên bản cũ; nếu không theo kịp, bảng và index có thể phình to.

### SQL Server

SQL Server ghi transaction log để hỗ trợ recovery. Data page được ghi bởi checkpoint hoặc lazy writer; commit durability phụ thuộc chế độ delayed durability và cấu hình log. Các index clustered/nonclustered đều có chi phí duy trì. Nonclustered index chứa clustered key làm row locator, nên clustered key dài có thể tăng kích thước tất cả nonclustered index.

Có thể theo dõi log bytes flushed, log flush waits, transaction log usage, page split, index operational stats và Query Store. Các DMV như `sys.dm_db_index_operational_stats`, `sys.dm_io_virtual_file_stats` và `sys.dm_db_log_stats` có thể hỗ trợ điều tra tùy quyền và phiên bản. Không so sánh counter tích lũy nếu chưa lấy chênh lệch theo cùng khoảng thời gian.

### MySQL/InnoDB

InnoDB ghi redo log, undo log và có thể ghi binary log. Dirty page trong buffer pool được flush xuống tablespace; doublewrite buffer hoặc cơ chế tương ứng bảo vệ trước page write không hoàn chỉnh tùy phiên bản/cấu hình. Secondary index lưu primary key, nên primary key dài làm tăng kích thước các index phụ.

Theo dõi redo bytes, log waits, buffer pool dirty pages, page flush, history list length, purge lag, deadlocks và binlog volume. Có thể dùng Performance Schema, `SHOW ENGINE INNODB STATUS` và các status counter. Tên và cách đo thay đổi theo phiên bản.

### Oracle Database

Oracle tạo redo và undo cho thao tác ghi. Redo log buffer được ghi xuống online redo log khi commit hoặc theo các điều kiện flush khác; DBWR ghi dirty buffer xuống datafile. Checkpoint và log switch ảnh hưởng đến đường ghi và recovery. Index maintenance, LOB segment và trigger đều có thể làm redo tăng.

Theo dõi redo size, redo writes, log file sync, log file parallel write, buffer busy waits, undo usage và I/O theo datafile/index segment. AWR/ASH có thể hỗ trợ khi môi trường có quyền sử dụng phù hợp; cũng có thể xem các view động như `V$SYSSTAT`, `V$SYSTEM_EVENT`, `V$SESSION` và `V$SEGMENT_STATISTICS`.

### Bảng đối chiếu

| Hệ quản trị | Log và phiên bản dữ liệu | Nơi ghi data page | Công cụ/điểm quan sát |
|---|---|---|---|
| PostgreSQL | WAL, tuple versions/MVCC | Shared buffers, checkpoint/background writer | WAL bytes, checkpoint, vacuum, HOT update |
| SQL Server | Transaction log, row versioning tùy cấu hình | Buffer pool, checkpoint/lazy writer | Log flush, index operational stats, page split |
| MySQL/InnoDB | Redo, undo, binary log nếu bật | Buffer pool, tablespace flush, doublewrite tùy cấu hình | Redo/binlog bytes, dirty pages, purge, deadlock |
| Oracle | Redo, undo | Buffer cache qua DBWR/checkpoint | Redo size, log file sync, undo và segment I/O |

Đây là mô tả khái quát. Cần xác minh hành vi theo phiên bản, storage engine, recovery mode, replication và cấu hình durability đang chạy.

## 12. Đo write amplification trong thực tế

Để đánh giá đúng, hãy xác định một workload có thể lặp lại và đo chênh lệch counter trước/sau trong cùng khoảng thời gian.

### Đo ở cấp ứng dụng

- Số hàng insert/update/delete thành công.
- Số byte payload logic được gửi.
- Số transaction commit và batch size.
- Tỷ lệ retry, rollback và deadlock.
- p50/p95/p99 của thao tác ghi.

### Đo ở cấp database

- Transaction log/WAL/redo bytes sinh ra.
- Log flush count, bytes và latency.
- Data page writes, dirty page flush và checkpoint activity.
- Index size, page split, index update và số lần tìm kiếm/ghi.
- Undo/version store hoặc dead tuple/purge backlog.
- Temp I/O, sort/hash spill và replication/CDC bytes.

### Đo ở cấp storage

- Host bytes written và IOPS.
- Latency theo loại I/O, queue depth và throughput.
- Nếu có, device-level write amplification và endurance metrics từ hệ thống lưu trữ.

### Ví dụ cách tính

Giả sử trong 60 giây, workload commit 50.000 thao tác insert, mỗi thao tác mang 500 byte dữ liệu logic. Tổng payload logic là 25 MB. Trong cùng thời gian, database ghi 90 MB WAL/log và 35 MB data/index pages. Nếu đo tổng host writes ở database là 125 MB, tỷ lệ ở tầng này xấp xỉ 5 lần so với payload logic.

Con số trên chỉ có ý nghĩa khi 125 MB là lượng ghi host thực tế trong cùng phạm vi, không cộng trùng log và data page nếu chúng đã được tính trong host writes. Cũng cần trừ hoặc kiểm soát background workload, checkpoint từ giai đoạn trước, backup, replication và các tác vụ bảo trì không thuộc workload thử nghiệm.

## 13. Quy trình tối ưu có kiểm soát

1. **Chọn workload:** xác định bảng, câu SQL, tần suất ghi, kích thước payload và yêu cầu durability.
2. **Lập baseline:** đo rows/sec, transactions/sec, log bytes, data writes, CPU, I/O và p95/p99.
3. **Liệt kê cấu trúc phải cập nhật:** primary key, index phụ, unique constraint, foreign key, trigger và bảng audit.
4. **Tìm nguồn chi phí:** index thừa, cập nhật index key, page split, row versioning, LOB, log flush hoặc checkpoint.
5. **Đặt giả thuyết:** bỏ index trùng, thay index ghép, giảm projection/LOB, batch, đổi cách cập nhật hoặc tách nhóm dữ liệu.
6. **Thử một thay đổi:** giữ nguyên dữ liệu và workload; không thay nhiều yếu tố cùng lúc.
7. **Đo lại:** dùng cùng thời lượng, concurrency, tham số, cache state và durability.
8. **Kiểm tra tính đúng:** xác nhận số hàng, constraint, transaction, recovery và replication không sai lệch.
9. **Đánh giá tác động đọc:** index bị bỏ có làm truy vấn đọc chậm hơn hoặc tăng I/O không?
10. **Triển khai có giám sát:** theo dõi log growth, checkpoint, latency, replication lag và storage queue.

### So sánh trước và sau

| Chỉ số | Trước thay đổi | Sau thay đổi | Mục tiêu đánh giá |
|---|---:|---:|---|
| Rows inserted/second | Đo baseline | Đo lại | Throughput ghi |
| Log bytes/row | Đo baseline | Đo lại | Chi phí log trên mỗi hàng |
| Data bytes written/row | Đo baseline | Đo lại | Ghi data/index page |
| Index size | Đo baseline | Đo lại | Dung lượng và cache footprint |
| p95 commit latency | Đo baseline | Đo lại | Độ trễ commit |
| Read query p95 | Đo baseline | Đo lại | Tác động phụ lên workload đọc |
| Replication lag | Đo baseline | Đo lại | Khả năng theo kịp log |

Không chỉ tối ưu tỷ lệ bytes/row. Một thay đổi có thể làm tỷ lệ giảm nhưng tăng latency hoặc giảm durability. Mục tiêu phải gồm throughput, độ trễ, tính đúng và chi phí lưu trữ.

## 14. Những sai lầm thường gặp

1. **Cho rằng một câu INSERT chỉ ghi một hàng:** index, constraint, trigger và log tạo thêm công việc.
2. **Tạo index cho mọi bộ lọc:** chi phí đọc giảm nhưng mọi thao tác ghi phải duy trì thêm cấu trúc.
3. **Xóa index chỉ vì ít được dùng:** có thể phá constraint hoặc ảnh hưởng workload theo mùa.
4. **Đưa cột cập nhật thường xuyên vào nhiều index:** mỗi thay đổi có thể làm phát sinh nhiều index update.
5. **Nhầm log bytes với data file writes:** log flush và checkpoint là hai phần khác nhau của đường ghi.
6. **Cộng trùng số liệu ở nhiều tầng:** WAL, data writes và host writes có thể phản ánh cùng một công việc ở các điểm đo khác nhau.
7. **Tắt durability để tăng benchmark:** kết quả không còn tương đương yêu cầu production và có nguy cơ mất dữ liệu đã xác nhận.
8. **Dùng batch quá lớn:** giảm commit overhead nhưng tăng log, khóa, rollback và replication lag.
9. **Đổi khóa tuần tự thành UUID ngẫu nhiên không đo:** có thể giảm hot page nhưng tăng phân mảnh và I/O ngẫu nhiên.
10. **Bỏ qua MVCC cleanup:** dead tuple, undo history hoặc version store có thể tiếp tục làm tăng dung lượng và I/O.
11. **Dùng minimal logging mà không kiểm tra điều kiện:** recovery, replication và backup có thể bị ảnh hưởng.
12. **Chỉ đo throughput ghi:** cần kiểm tra cả truy vấn đọc, commit latency, log flush và độ bền dữ liệu.

## 15. Danh sách kiểm tra trước khi triển khai

- [ ] Đã xác định rõ tầng đo write amplification và công thức tính.
- [ ] Đã đo số thao tác logic, số transaction commit và bytes payload.
- [ ] Đã liệt kê mọi index, constraint, trigger và bảng phụ bị ảnh hưởng.
- [ ] Đã xác định update có thay đổi cột khóa hoặc cột được index hay không.
- [ ] Đã kiểm tra page split, page density, row width và LOB access.
- [ ] Đã phân biệt WAL/redo/transaction log với data page writes và checkpoint.
- [ ] Đã kiểm tra undo/MVCC cleanup, vacuum/purge/version store khi phù hợp.
- [ ] Đã đánh giá batch size, bulk load và yêu cầu durability/recovery.
- [ ] Đã đo log flush latency, data I/O, CPU, p95/p99 và replication lag.
- [ ] Đã kiểm tra tác động của thay đổi index lên workload đọc và constraint.
- [ ] Đã kiểm thử rollback, recovery và tính đúng của dữ liệu dưới tải đồng thời.
- [ ] Đã so sánh trước/sau trong cùng điều kiện và có kế hoạch theo dõi sau triển khai.

Khuếch đại ghi xuất hiện vì một thay đổi logic phải được phản ánh trên hàng, chỉ mục, cấu trúc phiên bản và nhật ký để duy trì khả năng truy cập cũng như phục hồi. Nhiều index, cập nhật khóa, page split, LOB, MVCC cleanup và log flush đều có thể làm lượng ghi tăng. Hãy đo riêng log, data page và storage ở đúng tầng; sau đó tối ưu số index, hình dạng khóa, cách cập nhật và kích thước batch theo workload. Mọi cải thiện phải được kiểm chứng cùng độ trễ đọc, commit durability, tính toàn vẹn và khả năng phục hồi của hệ thống.
