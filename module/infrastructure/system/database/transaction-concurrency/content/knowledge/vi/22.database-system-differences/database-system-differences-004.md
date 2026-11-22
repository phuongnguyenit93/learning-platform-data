# PostgreSQL: giao dịch kéo dài, VACUUM và phiên bản dữ liệu cũ

PostgreSQL dùng MVCC (Multi-Version Concurrency Control) để cho phép các giao dịch đọc một phiên bản dữ liệu phù hợp với snapshot của chúng trong khi giao dịch khác cập nhật cùng bảng. Khi một dòng được `UPDATE` hoặc `DELETE`, PostgreSQL thường không ghi đè ngay nội dung dòng cũ. Nó tạo phiên bản mới hoặc đánh dấu phiên bản hiện tại đã hết hiệu lực. Các phiên bản cũ chỉ được thu hồi khi chắc chắn không còn giao dịch nào cần nhìn thấy chúng.

**VACUUM** là cơ chế dọn dẹp các phiên bản không còn khả kiến, giải phóng chỗ để PostgreSQL tái sử dụng và duy trì thông tin phục vụ tối ưu truy vấn. Một giao dịch hoặc snapshot tồn tại quá lâu có thể giữ lại những phiên bản cũ mà VACUUM chưa được phép xóa. Hậu quả có thể là bảng và chỉ mục phình to, tăng I/O, tăng chi phí quét, chậm autovacuum và trong trường hợp nghiêm trọng gây rủi ro transaction ID wraparound.

Để hiểu và vận hành tốt PostgreSQL, cần nắm mối liên hệ giữa vòng đời snapshot, tuple cũ, visibility horizon, VACUUM/autovacuum, freezing và các nguồn giữ lại dữ liệu như replication slot.

## 1. PostgreSQL lưu phiên bản dòng như thế nào?

Trong MVCC, một dòng logic có thể tương ứng với nhiều tuple vật lý trong heap. Khi cập nhật, PostgreSQL thường tạo tuple mới và giữ tuple cũ cho đến khi không còn snapshot nào cần nó.

Ví dụ bảng `account` có một dòng:

```sql
CREATE TABLE account (
    account_id BIGINT PRIMARY KEY,
    balance NUMERIC(14, 2) NOT NULL
);

INSERT INTO account VALUES (7, 1000.00);
```

Giả sử T1 cập nhật số dư thành 900:

```sql
UPDATE account
SET balance = 900.00
WHERE account_id = 7;
```

Ở mức khái niệm, PostgreSQL có thể giữ hai tuple:

| Phiên bản | balance | xmin | xmax | Ý nghĩa |
|---|---:|---|---|---|
| V1 | 1000.00 | XID tạo V1 | XID của T1 | Phiên bản cũ, được T1 thay thế |
| V2 | 900.00 | XID của T1 | 0/chưa bị kết thúc | Phiên bản mới |

`xmin` là transaction ID tạo tuple. `xmax` thường ghi transaction ID đã xóa hoặc thay thế tuple; giá trị và cách diễn giải cụ thể còn phụ thuộc trạng thái tuple, lock và các metadata liên quan. Không nên xem `xmin`/`xmax` như timestamp thời gian thực.

Khi T1 commit, giao dịch đọc có snapshot mới có thể nhìn thấy V2. Một giao dịch khác đã lấy snapshot trước khi T1 commit vẫn có thể cần V1. PostgreSQL chưa thể xóa V1 chỉ vì V2 đã commit; nó phải chờ đến khi mọi snapshot có thể nhìn thấy V1 đều kết thúc.

### 1.1. UPDATE tạo phiên bản mới

PostgreSQL thường thực hiện `UPDATE` bằng cách đánh dấu tuple cũ là đã được thay thế và tạo tuple mới. Các transaction khác chọn phiên bản phù hợp dựa trên snapshot, trạng thái commit và metadata tuple.

Nếu cập nhật một cột không thuộc bất kỳ chỉ mục nào và còn đủ chỗ trên cùng heap page, PostgreSQL có thể dùng **HOT update (Heap-Only Tuple)**. HOT giảm việc tạo entry mới trong các index, nhưng vẫn tạo tuple version mới trong heap. Phiên bản cũ vẫn cần được VACUUM thu hồi sau khi hết khả kiến.

### 1.2. DELETE không xóa vật lý ngay lập tức

Lệnh:

```sql
DELETE FROM account WHERE account_id = 7;
```

đánh dấu tuple là đã bị xóa bởi transaction thực hiện thao tác. Nếu một snapshot cũ vẫn cần nhìn thấy tuple trước khi xóa, PostgreSQL phải giữ nó. Sau khi không còn snapshot nào cần tuple đó, VACUUM có thể thu hồi chỗ.

Vì vậy, `DELETE` thành công không đồng nghĩa kích thước file bảng giảm ngay hoặc dữ liệu biến mất khỏi heap ngay lập tức.

## 2. Snapshot và visibility horizon

Snapshot xác định những transaction nào đã commit, đang hoạt động hoặc bắt đầu sau ranh giới quan sát. PostgreSQL dùng snapshot để quyết định tuple version nào được nhìn thấy.

Một transaction chạy ở `REPEATABLE READ` hoặc `SERIALIZABLE` thường giữ snapshot ổn định trong thời gian transaction. Nếu transaction kéo dài, snapshot cũ có thể tiếp tục cần các tuple đã bị transaction khác cập nhật hoặc xóa sau đó.

Ở `READ COMMITTED`, mỗi câu lệnh thường lấy snapshot mới. Vì vậy, một transaction mở lâu nhưng không giữ snapshot giữa các câu lệnh có thể ít cản trở dọn dẹp hơn một transaction giữ snapshot ổn định. Tuy nhiên, transaction đã thực hiện ghi, cursor đang mở, snapshot được export hoặc các cơ chế khác vẫn có thể giữ `xmin` và ảnh hưởng VACUUM. Không nên kết luận chỉ từ trạng thái `idle in transaction`; hãy kiểm tra `backend_xmin` và loại giao dịch thực tế.

**Visibility horizon** là ranh giới transaction cũ nhất mà PostgreSQL phải tôn trọng khi xác định tuple nào có thể được thu hồi hoặc đóng băng. Một snapshot cũ làm horizon lùi về quá khứ: tuple từng bị thay thế vẫn có thể cần thiết đối với transaction đang giữ snapshot đó.

### 2.1. Ví dụ snapshot cũ giữ phiên bản cũ

```text
Thời gian -------------------------------------------------------->

T1: BEGIN; SELECT ...       giữ snapshot S1 ---------------- COMMIT
                            |
T2:                         UPDATE row V1 -> V2; COMMIT
                            |
T3:                         UPDATE row V2 -> V3; COMMIT
                            |
VACUUM:                     thấy V1/V2 đã cũ nhưng S1 còn sống
                            nên chưa thể thu hồi phiên bản cần cho S1
```

T1 vẫn có thể nhìn thấy V1 dù T2 và T3 đã commit. VACUUM phải bảo toàn tuple mà S1 có thể nhìn thấy. Khi T1 kết thúc và không còn snapshot/consumer nào cần V1, lần VACUUM tiếp theo có thể dọn tuple đó.

### 2.2. Transaction mở lâu không phải lúc nào cũng giữ cùng một snapshot

Hãy phân biệt:

- Một câu lệnh `SELECT` dài đang thực thi: snapshot của câu lệnh cần tồn tại cho đến khi việc đọc hoàn tất.
- Transaction `REPEATABLE READ`/`SERIALIZABLE` đã đọc dữ liệu rồi nằm im: snapshot ổn định vẫn có thể được giữ đến khi transaction kết thúc.
- Transaction `READ COMMITTED` đang idle sau một câu lệnh: câu lệnh tiếp theo sẽ lấy snapshot mới, nên transaction không có cùng ngữ nghĩa snapshot ổn định như `REPEATABLE READ`. Tuy nhiên, không nên suy ra rằng một transaction đang mở chắc chắn không giữ horizon; transaction đã ghi, cursor, snapshot export và trạng thái backend thực tế vẫn có thể giữ `xmin`.
- Transaction đang mở và có thay đổi chưa commit: các tuple do transaction đó tạo hoặc kết thúc hiệu lực chưa thể được xem là đã hoàn tất để thu hồi như một transaction đã commit.

Điều cần theo dõi là snapshot/XID horizon mà backend thực sự đang giữ, không chỉ tuổi của connection.

## 3. Dead tuple và table bloat

Tuple đã bị thay thế hoặc xóa nhưng chưa thể thu hồi được gọi là **dead tuple** khi nó không còn hữu ích cho snapshot mới, nhưng có thể chưa đủ điều kiện để VACUUM tái sử dụng vì horizon hoặc cleanup chưa tiến tới.

Nếu bảng cập nhật/xóa liên tục, số tuple chết tăng lên. Khi VACUUM không theo kịp hoặc bị snapshot cũ giữ lại, các page chứa nhiều tuple chết vẫn chiếm dung lượng và phải được đọc khi quét. Đây là một nguyên nhân của **table bloat**.

Ví dụ một bảng trạng thái job được cập nhật liên tục:

```text
UPDATE job SET status = 'RUNNING'  WHERE job_id = 1;
UPDATE job SET status = 'DONE'     WHERE job_id = 1;
UPDATE job SET status = 'ARCHIVED' WHERE job_id = 1;
```

Một dòng logic có thể tạo ra nhiều tuple version. Nếu snapshot cũ giữ lại các phiên bản trước, heap page sẽ chứa nhiều tuple không còn được truy vấn mới sử dụng.

### 3.1. Hậu quả của bloat

- **Tăng kích thước heap:** nhiều page chứa tuple chết hoặc khoảng trống chưa được tái sử dụng.
- **Tăng I/O:** sequential scan và một số index/heap access phải đi qua nhiều page hơn để tìm dữ liệu sống.
- **Cache kém hiệu quả:** cùng một lượng RAM chỉ chứa được ít dữ liệu hữu ích hơn.
- **Tăng chi phí VACUUM:** phải quét và xử lý nhiều page, index entry và metadata hơn.
- **Tăng thời gian backup/restore:** dữ liệu vật lý lớn hơn làm một số tác vụ lưu trữ và phục hồi tốn thời gian hơn.
- **Tăng áp lực WAL và replica:** workload ghi lớn cùng cleanup chậm có thể làm hệ thống lưu trữ và replication chịu thêm áp lực; cần phân biệt nguyên nhân giữ tuple với nguyên nhân giữ WAL.

### 3.2. Dead tuple không đồng nghĩa file sẽ tự nhỏ lại

VACUUM thông thường làm cho không gian tuple chết có thể được tái sử dụng bên trong relation. Nó không thường xuyên thu nhỏ file relation trên filesystem ngay lập tức. Nếu page trống nằm ở giữa bảng, PostgreSQL có thể dùng lại page đó cho lần insert/update sau.

Một số page trống ở cuối relation có thể được truncate trong một số điều kiện, nhưng việc đó cần xử lý khóa phù hợp. Muốn viết lại relation và trả lại nhiều dung lượng cho hệ điều hành, có thể cần `VACUUM FULL` hoặc công cụ rewrite chuyên dụng, đi kèm chi phí và lock đáng kể.

## 4. VACUUM làm gì?

`VACUUM` quét relation để xác định tuple chết, thu hồi chúng khi an toàn, xử lý index entry liên quan và cập nhật metadata như visibility map. Đây là hoạt động bảo trì thường xuyên của PostgreSQL, không phải thao tác chỉ chạy khi bảng đã phình to.

Ví dụ:

```sql
VACUUM account;
```

Để xem thêm thống kê và đồng thời cập nhật thống kê planner:

```sql
VACUUM (VERBOSE, ANALYZE) account;
```

`VACUUM` thường có thể chạy đồng thời với các thao tác đọc/ghi thông thường trên bảng. Nó vẫn cần khóa và tài nguyên nội bộ, nên có thể xung đột với một số thao tác DDL hoặc bảo trì khác. `VACUUM FULL` có hành vi khóa mạnh hơn đáng kể.

### 4.1. Thu hồi tuple chết

VACUUM chỉ có thể loại bỏ tuple khi transaction horizon cho biết không còn snapshot nào cần tuple đó. Nếu snapshot cũ còn tồn tại, VACUUM có thể chạy nhưng phải giữ lại những tuple chưa an toàn để thu hồi.

Điều này giải thích vì sao chạy `VACUUM` nhiều lần không nhất thiết giải quyết được bloat nếu nguyên nhân là một transaction, replication slot hoặc standby vẫn giữ horizon cũ. Cần tìm và xử lý nguồn giữ horizon trước.

### 4.2. Dọn index entry

Index có thể chứa tham chiếu đến tuple đã chết. Khi heap tuple không còn cần thiết, VACUUM phối hợp cleanup index để loại bỏ entry chết theo cơ chế của loại index. Nếu index bloat đã tích lũy, VACUUM thường không viết lại toàn bộ index để thu nhỏ nó; có thể cần `REINDEX` hoặc công cụ phù hợp trong cửa sổ bảo trì.

### 4.3. Visibility map

Visibility map lưu thông tin page đã có toàn bộ tuple hiển thị với mọi transaction hay chưa, và page đã được freeze ở mức phù hợp hay chưa. Thông tin này giúp PostgreSQL tối ưu một số thao tác:

- **All-visible:** mọi tuple trên page đều hiển thị với mọi snapshot hiện tại theo điều kiện của visibility map. Index-only scan có thể tránh truy cập heap cho page đó.
- **All-frozen:** tuple trên page đã được freeze nên không cần kiểm tra XID cũ theo cách thông thường.

Khi có thay đổi làm mất điều kiện all-visible, bit tương ứng có thể bị xóa và VACUUM phải thiết lập lại sau khi kiểm tra page. Vì thế, workload update liên tục có thể làm giảm cơ hội index-only scan tận dụng visibility map.

### 4.4. VACUUM khác ANALYZE

Hai thao tác có mục tiêu khác nhau:

| Thao tác | Mục đích |
|---|---|
| `VACUUM` | Thu hồi tuple chết khi an toàn, xử lý index cleanup, cập nhật visibility/freeze metadata |
| `ANALYZE` | Thu thập thống kê dữ liệu để planner ước lượng số dòng và chọn execution plan |
| `VACUUM ANALYZE` | Thực hiện cả dọn dẹp và cập nhật thống kê |

Một bảng có thể cần ANALYZE sau khi phân phối dữ liệu thay đổi mạnh dù số dead tuple thấp. Ngược lại, bảng có nhiều dead tuple cần VACUUM ngay cả khi thống kê planner vẫn còn tương đối mới.

## 5. VACUUM thường và VACUUM FULL

Hai lệnh có khác biệt vận hành lớn:

| Tiêu chí | `VACUUM` thường | `VACUUM FULL` |
|---|---|---|
| Cách làm | Thu hồi tuple chết và đánh dấu không gian có thể tái sử dụng | Viết lại relation thành bản compact mới |
| Khóa | Cho phép phần lớn đọc/ghi thông thường tiếp tục | Yêu cầu `ACCESS EXCLUSIVE` trên bảng |
| Dung lượng filesystem | Thường giữ kích thước file, có thể truncate page trống cuối relation khi phù hợp | Có thể trả lại đáng kể dung lượng cho hệ điều hành |
| Tài nguyên | Quét heap/index và xử lý cleanup | Cần thêm dung lượng tạm và I/O để rewrite |
| Mục đích | Bảo trì định kỳ | Thu nhỏ relation khi cần và chấp nhận downtime/lock |

Không nên chạy `VACUUM FULL` như lịch dọn dẹp định kỳ chỉ vì `n_dead_tup` lớn. Trước hết hãy xử lý transaction giữ horizon, để VACUUM thường thu hồi tuple và tái sử dụng không gian. Chỉ cân nhắc rewrite khi cần thu hồi dung lượng vật lý hoặc khắc phục bloat đã tích lũy và có kế hoạch lock/dung lượng.

Lệnh:

```sql
VACUUM FULL account;
```

có thể chặn truy cập bảng trong thời gian rewrite. Cần kiểm tra dung lượng trống, thời gian chạy, lock impact và kế hoạch rollback/maintenance trước khi thực hiện trên bảng lớn.

## 6. Autovacuum hoạt động như thế nào?

PostgreSQL có các tiến trình autovacuum launcher và worker để tự động bảo trì bảng. Autovacuum kiểm tra thống kê hoạt động của relation và khởi chạy VACUUM hoặc ANALYZE khi vượt ngưỡng cấu hình.

Các tham số thường gặp gồm:

- `autovacuum`: bật/tắt cơ chế autovacuum ở cấp cấu hình hệ thống.
- `autovacuum_vacuum_threshold`: ngưỡng dead tuple cơ bản để kích hoạt vacuum.
- `autovacuum_vacuum_scale_factor`: tỷ lệ theo số tuple ước tính của bảng được cộng vào ngưỡng.
- `autovacuum_analyze_threshold` và `autovacuum_analyze_scale_factor`: ngưỡng cập nhật thống kê.
- `autovacuum_vacuum_insert_threshold` và `autovacuum_vacuum_insert_scale_factor`: ngưỡng liên quan đến insert và bảo trì page/visibility map ở các phiên bản hỗ trợ.
- `autovacuum_max_workers`: số worker autovacuum tối đa chạy đồng thời.
- `autovacuum_work_mem`: bộ nhớ dùng cho mỗi worker khi phù hợp với cấu hình.
- `autovacuum_vacuum_cost_limit` và `autovacuum_vacuum_cost_delay`: điều tiết tốc độ I/O của VACUUM.

Với cấu hình mặc định dạng threshold + scale factor, ngưỡng vacuum có thể được hình dung như:

```text
vacuum threshold
  = autovacuum_vacuum_threshold
  + autovacuum_vacuum_scale_factor * estimated_table_rows
```

Ví dụ minh họa: nếu bảng 10 triệu dòng và scale factor là 0,2, phần tỷ lệ đã là khoảng 2 triệu tuple trước khi cộng threshold cơ bản. Với bảng lớn, ngưỡng này có thể quá cao so với tốc độ phát sinh dead tuple và yêu cầu dung lượng của hệ thống.

### 6.1. Điều chỉnh theo từng bảng

Không nhất thiết phải thay scale factor toàn hệ thống. Có thể đặt storage parameter cho một bảng ghi nhiều:

```sql
ALTER TABLE event_log SET (
    autovacuum_vacuum_scale_factor = 0.02,
    autovacuum_vacuum_threshold = 5000,
    autovacuum_analyze_scale_factor = 0.01
);
```

Các giá trị trên chỉ là ví dụ, không phải cấu hình khuyến nghị chung. Cần đo tốc độ update/delete, kích thước bảng, số dead tuple, tốc độ VACUUM và ngân sách I/O trước khi chọn ngưỡng.

### 6.2. Autovacuum không thể dọn tuple đang bị giữ bởi snapshot cũ

Autovacuum có thể chạy đúng lịch nhưng không thu hồi được tuple nếu horizon chưa tiến tới. Trong trường hợp đó, tăng số worker hoặc giảm scale factor không giải quyết gốc rễ. Cần tìm transaction, prepared transaction, replication slot hoặc standby đang giữ xmin cũ.

### 6.3. Không nên tắt autovacuum tùy tiện

Tắt autovacuum có thể khiến dead tuple tích lũy, visibility map không được cập nhật và XID không được freeze kịp thời. PostgreSQL vẫn có cơ chế vacuum khẩn cấp để chống wraparound ngay cả khi autovacuum bị vô hiệu hóa theo cấu hình thông thường; dựa vào cơ chế khẩn cấp không phải chiến lược vận hành an toàn.

## 7. Transaction kéo dài giữ lại phiên bản cũ như thế nào?

Một transaction giữ snapshot cũ có thể ngăn VACUUM loại bỏ tuple mà snapshot đó còn có thể nhìn thấy. Trong lúc transaction chờ, các transaction khác vẫn có thể update/delete hàng nghìn hoặc hàng triệu dòng. Phiên bản mới được tạo liên tục, nhưng các phiên bản cũ cần cho snapshot lâu đời vẫn phải tồn tại.

Một ví dụ thường gặp là ứng dụng mở transaction, đọc một tập dữ liệu rồi gọi dịch vụ ngoài hoặc chờ người dùng trước khi commit:

```text
BEGIN;
SELECT ...;                 -- snapshot được lấy
                              |
                              | ứng dụng gọi HTTP / chờ user
                              | transaction vẫn mở
                              |
COMMIT;
```

Trong thời gian chờ, các transaction khác có thể cập nhật cùng bảng. Nếu snapshot của transaction đầu vẫn được giữ, VACUUM không thể thu hồi một số phiên bản cũ dù chúng đã bị thay thế từ lâu.

Các nguồn phổ biến:

- Transaction `REPEATABLE READ` hoặc `SERIALIZABLE` mở lâu.
- Query hoặc cursor đọc dữ liệu lớn chạy lâu.
- Transaction `idle in transaction` vẫn giữ snapshot.
- Session dùng `pg_export_snapshot()` và transaction xuất snapshot còn mở.
- Prepared transaction chưa `COMMIT PREPARED` hoặc `ROLLBACK PREPARED`.
- Replication slot giữ `xmin` hoặc `catalog_xmin`.
- Standby gửi feedback về xmin cũ thông qua `hot_standby_feedback`.

Không phải tất cả các nguồn này đều là client backend thông thường. Vì vậy, chỉ xem danh sách session ứng dụng có thể chưa tìm ra đầy đủ nguyên nhân giữ horizon.

## 8. Transaction idle in transaction

`idle in transaction` nghĩa là backend đang ở trong transaction nhưng hiện không thực thi câu lệnh. Trạng thái này đáng chú ý vì ứng dụng có thể đã mở transaction rồi chờ một thao tác khác.

Ví dụ:

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ;
SELECT * FROM account WHERE account_id = 7;
-- Ứng dụng chờ người dùng xác nhận trong vài phút.
-- Transaction vẫn giữ snapshot cũ.
```

Trong lúc đó, transaction khác cập nhật hoặc xóa dòng. Snapshot cũ có thể khiến phiên bản cũ không được VACUUM thu hồi.

Ở `READ COMMITTED`, mỗi statement thông thường có snapshot riêng; statement tiếp theo có thể thấy dữ liệu commit mới hơn. Điều này khác với snapshot ổn định của `REPEATABLE READ`/`SERIALIZABLE`, nhưng không phải lý do để bỏ qua transaction đang mở. Transaction có thao tác ghi, cursor, snapshot export hoặc trạng thái backend cụ thể vẫn có thể giữ horizon. Hãy xem `backend_xmin`, `backend_xid`, `xact_start` và isolation level thay vì kết luận chỉ từ nhãn trạng thái.

Có thể dùng `idle_in_transaction_session_timeout` để tự động kết thúc session idle trong transaction quá lâu:

```sql
ALTER ROLE app_user
SET idle_in_transaction_session_timeout = '2min';
```

Thời hạn phải phù hợp với ứng dụng. Khi timeout xảy ra, PostgreSQL chấm dứt session/transaction liên quan; ứng dụng cần xử lý lỗi và không giả định transaction vẫn còn hiệu lực. Timeout không thay thế việc thiết kế transaction ngắn.

## 9. Replication slot và standby cũng có thể giữ phiên bản cũ

Một nguyên nhân thường bị bỏ sót là replication. Primary có thể phải giữ lại tuple version để một standby hoặc logical decoding consumer còn đọc được dữ liệu theo vị trí/snapshot cần thiết.

### 9.1. `xmin` và `catalog_xmin` của replication slot

`pg_replication_slots` có các cột quan trọng:

- `xmin`: giới hạn vacuum trên dữ liệu user table; các tuple có thể còn cần thiết đối với slot phải được giữ lại.
- `catalog_xmin`: giới hạn vacuum trên system catalog tuple cần cho logical decoding/consumer.
- `restart_lsn`: vị trí WAL mà slot vẫn cần; nó có thể khiến WAL cũ không được xóa.
- `confirmed_flush_lsn`: vị trí logical consumer đã xác nhận xử lý, liên quan đến tiến độ logical replication.

`xmin`/`catalog_xmin` và `restart_lsn` bảo vệ các loại tài nguyên khác nhau. Một slot có thể giữ tuple cũ do xmin và đồng thời giữ WAL do restart LSN. Chỉ nhìn kích thước WAL không cho biết trực tiếp table bloat; cần kiểm tra riêng các cột slot.

### 9.2. Hot standby feedback

Khi `hot_standby_feedback` được bật trên standby, standby có thể gửi thông tin xmin về primary để primary tránh dọn tuple mà truy vấn trên standby còn cần. Điều này giảm một số query conflict trên standby, nhưng một truy vấn kéo dài ở standby có thể khiến primary giữ dead tuple lâu hơn và tăng bloat.

Đây là sự đánh đổi:

- Tắt feedback có thể khiến query trên standby bị hủy khi replay WAL cần cleanup tuple.
- Bật feedback có thể giữ lại tuple trên primary lâu hơn, làm tăng dung lượng heap/index và chi phí vacuum.

Không nên bật/tắt chỉ dựa trên một chỉ số. Hãy cân nhắc thời lượng truy vấn standby, yêu cầu báo cáo, dung lượng primary và chính sách chịu query cancellation.

### 9.3. Logical replication và slot bị bỏ quên

Một logical replication slot không còn consumer hoạt động vẫn có thể giữ `xmin`, `catalog_xmin` hoặc WAL nếu không được xử lý. Cần theo dõi slot inactive lâu, consumer lag và chính sách xóa/recreate slot. Xóa slot có thể làm mất khả năng tiếp tục replication từ vị trí cũ; chỉ làm sau khi xác định consumer và kế hoạch khôi phục.

## 10. Transaction ID wraparound và freezing

PostgreSQL dùng transaction ID (XID) 32-bit cho nhiều metadata MVCC. Vì không gian XID hữu hạn, giá trị sẽ quay vòng. PostgreSQL dùng quy tắc so sánh XID theo khoảng và cần **freeze** tuple đủ cũ để tránh hiểu nhầm transaction rất cũ là transaction mới sau wraparound.

VACUUM không chỉ thu hồi tuple chết; nó còn giúp freeze tuple cũ. Khi tuple đã được freeze, PostgreSQL không cần dựa vào XID tạo tuple theo cách thông thường để xác định khả kiến.

### 10.1. Vì sao long transaction làm tăng rủi ro wraparound?

Transaction/snapshot cũ có thể ngăn vacuum tiến qua horizon. Nếu VACUUM không thể freeze các tuple đủ cũ, tuổi XID của database/table tiếp tục tăng. PostgreSQL phải chạy anti-wraparound vacuum để bảo vệ dữ liệu.

Nếu tiến gần ngưỡng nguy hiểm mà không thể vacuum an toàn, PostgreSQL có thể cảnh báo mạnh và cuối cùng từ chối một số thao tác ghi để tránh wraparound làm hỏng tính đúng đắn dữ liệu. Đây là tình huống vận hành nghiêm trọng; không nên chờ tới lúc hệ thống vào chế độ bảo vệ.

### 10.2. Freeze và các tham số liên quan

Các tham số thường gặp gồm:

- `vacuum_freeze_min_age`: tuổi XID tối thiểu để VACUUM cân nhắc freeze tuple.
- `vacuum_freeze_table_age`: tuổi relation mà VACUUM có thể thực hiện quét freeze mạnh hơn.
- `autovacuum_freeze_max_age`: ngưỡng tuổi XID kích hoạt anti-wraparound autovacuum.
- `vacuum_failsafe_age`: ngưỡng failsafe để VACUUM ưu tiên hoàn tất việc chống wraparound trong tình huống khẩn cấp.

Giá trị mặc định và chi tiết hành vi phụ thuộc phiên bản PostgreSQL. Không nên chỉnh các tham số này để che giấu transaction giữ horizon; trước tiên phải loại bỏ nguyên nhân khiến VACUUM không thể tiến lên.

### 10.3. Theo dõi tuổi XID

```sql
SELECT datname,
       age(datfrozenxid) AS xid_age
FROM pg_database
ORDER BY xid_age DESC;
```

Để xem relation có `relfrozenxid` cũ:

```sql
SELECT n.nspname,
       c.relname,
       age(c.relfrozenxid) AS xid_age,
       pg_size_pretty(pg_total_relation_size(c.oid)) AS total_size
FROM pg_class AS c
JOIN pg_namespace AS n ON n.oid = c.relnamespace
WHERE c.relkind IN ('r', 'm', 't')
ORDER BY xid_age DESC
LIMIT 30;
```

Các truy vấn này giúp tìm database/relation có tuổi XID lớn. Chúng không tự xác định nguyên nhân; cần kết hợp với session, prepared transaction, replication slot và tiến trình VACUUM.

## 11. Giám sát transaction và snapshot giữ horizon

`pg_stat_activity` là điểm bắt đầu quan trọng để tìm transaction lâu và backend đang giữ xmin:

```sql
SELECT pid,
       usename,
       application_name,
       state,
       xact_start,
       query_start,
       backend_xid,
       backend_xmin,
       age(backend_xmin) AS xmin_age,
       wait_event_type,
       wait_event,
       left(query, 200) AS query_sample
FROM pg_stat_activity
WHERE datname = current_database()
ORDER BY xact_start NULLS LAST;
```

`backend_xmin` cho biết xmin mà backend đang giữ nếu có; `backend_xid` là XID của transaction backend nếu đã được cấp. `age(backend_xmin)` giúp sắp xếp tương đối theo độ cũ. Một giá trị `NULL` không có nghĩa backend không liên quan đến mọi loại giữ horizon; cần kiểm tra các nguồn khác như replication slot hoặc prepared transaction.

Để lọc session đang idle trong transaction:

```sql
SELECT pid,
       usename,
       application_name,
       xact_start,
       now() - xact_start AS transaction_age,
       backend_xmin,
       left(query, 200) AS last_query
FROM pg_stat_activity
WHERE state = 'idle in transaction'
ORDER BY xact_start;
```

Để tìm transaction đã prepare:

```sql
SELECT gid, prepared, owner, database
FROM pg_prepared_xacts
ORDER BY prepared;
```

Prepared transaction tồn tại sau `PREPARE TRANSACTION` và giữ resource cho đến khi được hoàn tất bằng `COMMIT PREPARED` hoặc `ROLLBACK PREPARED`. Một prepared transaction bị bỏ quên có thể giữ khóa và horizon lâu dài.

### 11.1. Theo dõi dead tuple và lịch sử VACUUM

```sql
SELECT schemaname,
       relname,
       n_live_tup,
       n_dead_tup,
       last_vacuum,
       last_autovacuum,
       vacuum_count,
       autovacuum_count,
       last_analyze,
       last_autoanalyze
FROM pg_stat_user_tables
ORDER BY n_dead_tup DESC
LIMIT 30;
```

`n_dead_tup` là ước lượng thống kê, không phải phép đếm chính xác tại thời điểm truy vấn. Hãy dùng xu hướng theo thời gian, kích thước relation và log autovacuum để đánh giá. Một bảng có `n_dead_tup` cao trong thời gian ngắn không nhất thiết đã bị bloat nghiêm trọng nếu VACUUM sắp xử lý được.

### 11.2. Theo dõi replication slot

```sql
SELECT slot_name,
       slot_type,
       active,
       xmin,
       catalog_xmin,
       restart_lsn,
       confirmed_flush_lsn
FROM pg_replication_slots
ORDER BY slot_name;
```

Slot inactive lâu với `xmin` hoặc `catalog_xmin` cũ là dấu hiệu cần điều tra. Slot có `restart_lsn` cũ có thể giữ WAL dù không nhất thiết có cùng nguyên nhân với dead tuple. Không xóa slot tùy tiện vì có thể làm consumer mất điểm tiếp tục.

### 11.3. Theo dõi VACUUM đang chạy

```sql
SELECT pid,
       relid::regclass AS relation,
       phase,
       heap_blks_total,
       heap_blks_scanned,
       heap_blks_vacuumed,
       index_vacuum_count
FROM pg_stat_progress_vacuum;
```

View `pg_stat_progress_vacuum` cho biết tiến trình VACUUM đang ở phase nào và tiến độ quét heap. Nó hữu ích để phân biệt VACUUM chưa chạy, đang chạy chậm hay đang chạy nhưng không thể thu hồi các tuple do horizon.

## 12. Tìm đúng nguyên nhân VACUUM không dọn được

Khi dead tuple tăng liên tục, hãy điều tra theo thứ tự:

1. Xác định bảng có tốc độ update/delete cao và thời điểm `last_autovacuum` gần nhất.
2. Xem `n_dead_tup`, kích thước heap/index và xu hướng tăng theo thời gian.
3. Tìm backend có `backend_xmin` cũ, transaction `REPEATABLE READ`/`SERIALIZABLE` lâu hoặc query/cursor đang chạy lâu.
4. Kiểm tra session `idle in transaction` và transaction có `xact_start` quá cũ.
5. Kiểm tra `pg_prepared_xacts` để tìm prepared transaction bị bỏ quên.
6. Kiểm tra `pg_replication_slots.xmin` và `catalog_xmin` của slot inactive hoặc consumer lag.
7. Kiểm tra standby và `hot_standby_feedback` nếu có replication read workload.
8. Kiểm tra tuổi `datfrozenxid` và `relfrozenxid` để xác định áp lực freeze/wraparound.
9. Xem log autovacuum và `pg_stat_progress_vacuum` để biết worker có chạy, bị cancel hay bị giới hạn tài nguyên.
10. Chỉ sau khi giải phóng horizon mới đánh giá lại VACUUM có thể thu hồi tuple và tốc độ bloat giảm hay chưa.

Không nên chạy `VACUUM FULL` ngay khi thấy bảng lớn. Nếu snapshot cũ vẫn giữ tuple, rewrite có thể không giải quyết được nguồn gốc vấn đề và còn gây lock/downtime lớn.

## 13. Cách xử lý giao dịch kéo dài

### 13.1. Giữ transaction ngắn

Mở transaction ngay trước phần SQL cần tính nguyên tử và commit ngay sau khi hoàn thành. Không đặt các hoạt động sau vào giữa transaction nếu không cần thiết:

- Gọi HTTP hoặc RPC.
- Chờ người dùng xác nhận.
- Đọc file lớn hoặc xử lý CPU lâu.
- Chờ một message hoặc tác vụ trong queue.
- Stream kết quả cho client trong thời gian dài khi snapshot không cần giữ.

Nếu cần làm việc dài, chia thành các batch có checkpoint rõ ràng. Mỗi batch commit riêng và có thể tiếp tục an toàn sau lỗi. Cần thiết kế idempotency hoặc keyset pagination để không xử lý lặp hoặc bỏ sót dữ liệu.

### 13.2. Dùng isolation level phù hợp

Không dùng `REPEATABLE READ` hoặc `SERIALIZABLE` cho toàn bộ quy trình nếu chỉ một vài thao tác cần snapshot ổn định. `READ COMMITTED` tạo snapshot mới theo statement trong đa số truy vấn thông thường, có thể giảm thời gian giữ snapshot. Tuy nhiên, isolation level phải đáp ứng đúng bất biến nghiệp vụ; không hạ mức cô lập chỉ để giảm bloat nếu làm xuất hiện anomaly.

### 13.3. Đóng cursor và kết thúc transaction đúng lúc

Server-side cursor hoặc transaction dùng để stream hàng triệu dòng có thể giữ snapshot trong suốt quá trình đọc. Nếu cần export dữ liệu dài, cân nhắc snapshot/export protocol có kiểm soát, phân trang theo khóa ổn định hoặc bản sao/replica dành riêng cho báo cáo. Mỗi lựa chọn có trade-off nhất định về tính nhất quán và tài nguyên.

### 13.4. Đặt timeout hợp lý

`idle_in_transaction_session_timeout` giúp kết thúc session bỏ quên transaction. `statement_timeout` có thể giới hạn câu lệnh quá lâu. Timeout nên được đặt theo role/database và workload; không nên đặt quá thấp khiến truy vấn hợp lệ liên tục bị hủy.

Timeout là hàng rào vận hành. Ứng dụng vẫn phải rollback/đóng transaction khi xử lý lỗi, trả connection về pool ở trạng thái sạch và không giữ snapshot qua các bước không cần thiết.

### 13.5. Xử lý replication slot có chủ đích

Theo dõi consumer lag và tuổi của slot. Nếu một consumer không còn dùng, cần xác nhận trạng thái và xóa slot theo quy trình. Nếu consumer cần tiếp tục, khôi phục consumer hoặc xử lý backlog. Không xóa slot chỉ để làm `xmin` tiến lên mà chưa đánh giá hậu quả replication/WAL.

## 14. Các lưu ý vận hành về VACUUM

**Không chạy VACUUM bên trong transaction block.** Lệnh VACUUM thông thường phải chạy như một lệnh bảo trì riêng, không nằm trong `BEGIN ... COMMIT` của ứng dụng.

**VACUUM không phải phép compact toàn bộ bảng.** Nó chủ yếu làm không gian có thể tái sử dụng. Muốn trả dung lượng file về hệ điều hành, cần xem xét rewrite như `VACUUM FULL` hoặc công cụ tương đương, với kế hoạch lock và dung lượng.

**Autovacuum có thể cần thêm worker và ngân sách I/O.** Nếu nhiều bảng lớn cùng phát sinh dead tuple, một worker count thấp hoặc cost delay quá bảo thủ có thể khiến vacuum backlog tăng. Nhưng tăng worker quá cao cũng gây tranh chấp I/O/CPU và bộ nhớ.

**Bảng partition cần theo dõi từng partition.** Partition lớn hoặc ghi nhiều có thể cần storage parameter riêng. VACUUM trên parent không nên được hiểu là luôn thay thế việc kiểm tra các partition có dữ liệu.

**Temporary table không được autovacuum worker xử lý như bảng thông thường.** Session tạo temporary table cần tự quản lý ANALYZE/VACUUM khi workload phù hợp; chi tiết phụ thuộc cách sử dụng và phiên bản.

**Autovacuum log rất hữu ích.** Có thể bật `log_autovacuum_min_duration` ở mức phù hợp để ghi nhận thời gian, số tuple và lý do worker chạy. Log giúp nhận ra bảng nào vacuum lâu, bị skip hoặc thường xuyên không theo kịp.

## 15. Một kịch bản thực tế: bảng lớn bị phình do snapshot cũ

Giả sử bảng `orders` có 50 triệu dòng và được cập nhật trạng thái liên tục. Một báo cáo chạy trong transaction `REPEATABLE READ` mở suốt 45 phút. Trong thời gian đó, ứng dụng xử lý đơn hàng và cập nhật hàng triệu tuple.

Diễn biến:

1. Báo cáo lấy snapshot S1 và giữ transaction mở.
2. Các worker cập nhật `orders`, tạo tuple version mới.
3. Tuple cũ không còn được snapshot mới nhìn thấy, nhưng S1 vẫn có thể cần chúng.
4. Autovacuum chạy, quét bảng nhưng phải giữ các tuple chưa an toàn để thu hồi.
5. `n_dead_tup` và kích thước relation tăng.
6. Khi báo cáo kết thúc, horizon có thể tiến lên.
7. VACUUM tiếp theo có thể thu hồi các tuple chết; không gian được tái sử dụng cho các lần ghi sau.

Các bước điều tra:

```sql
-- Tìm transaction/snapshot cũ.
SELECT pid, state, xact_start, backend_xmin,
       age(backend_xmin) AS xmin_age,
       left(query, 200) AS query_sample
FROM pg_stat_activity
WHERE backend_xmin IS NOT NULL
ORDER BY age(backend_xmin) DESC;

-- Xem bảng có nhiều dead tuple.
SELECT relname, n_live_tup, n_dead_tup,
       last_autovacuum, autovacuum_count
FROM pg_stat_user_tables
WHERE relname = 'orders';

-- Xem tiến trình vacuum.
SELECT * FROM pg_stat_progress_vacuum;
```

Giải pháp dài hạn có thể là kết thúc báo cáo theo batch ngắn, dùng replica dành cho báo cáo, giảm thời gian giữ snapshot, điều chỉnh ngưỡng autovacuum cho partition ghi nhiều và cảnh báo transaction giữ `backend_xmin` quá lâu. Chỉ tăng tần suất VACUUM mà không xử lý snapshot S1 sẽ không giúp thu hồi tuple đang cần thiết.

## 16. Những nhầm lẫn thường gặp

**VACUUM xóa ngay mọi dòng đã DELETE.** Không đúng. Tuple chỉ được thu hồi khi không còn snapshot nào có thể cần nó.

**Một transaction mở lâu luôn giữ snapshot cũ trong mọi isolation level.** Không đúng. Snapshot của `READ COMMITTED` thường theo từng statement; `REPEATABLE READ`/`SERIALIZABLE` giữ snapshot ổn định. Hãy kiểm tra `backend_xmin`, loại transaction và các nguồn giữ horizon khác.

**Chạy VACUUM nhiều lần sẽ luôn làm file bảng nhỏ lại.** Không đúng. VACUUM thường làm không gian có thể tái sử dụng bên trong relation; muốn trả dung lượng vật lý về hệ điều hành thường cần rewrite.

**VACUUM và ANALYZE là cùng một việc.** Không đúng. VACUUM dọn tuple và cập nhật metadata; ANALYZE thu thập thống kê cho planner.

**Autovacuum chạy nghĩa là dead tuple chắc chắn được dọn hết.** Không đúng. Horizon cũ có thể ngăn thu hồi tuple; worker cũng có thể chưa xử lý hết relation hoặc bị giới hạn tài nguyên.

**Replication slot chỉ giữ WAL.** Không đúng. `restart_lsn` giữ WAL; `xmin` và `catalog_xmin` có thể giữ tuple trong user table/system catalog.

**Bật `hot_standby_feedback` chỉ có lợi.** Không đúng. Nó giảm một số query conflict trên standby nhưng có thể khiến primary giữ dead tuple lâu hơn.

**`VACUUM FULL` là cách dọn định kỳ tốt hơn.** Không đúng. Nó rewrite bảng và cần `ACCESS EXCLUSIVE`, có thể gây downtime và cần dung lượng tạm.

**Tắt autovacuum giải quyết được contention.** Không đúng. Việc tắt có thể làm bloat và XID age tăng, dẫn đến vấn đề nghiêm trọng hơn.

## 17. Quy trình kiểm tra nhanh khi bảng phình to

Khi phát hiện một bảng PostgreSQL tăng kích thước bất thường, hãy đi theo trình tự:

1. Xem `n_dead_tup`, `last_autovacuum`, `autovacuum_count` và tốc độ update/delete.
2. Tìm backend giữ `backend_xmin` cũ, transaction/cursor chạy lâu và session idle in transaction.
3. Kiểm tra `pg_prepared_xacts`.
4. Kiểm tra `pg_replication_slots.xmin`, `catalog_xmin`, `restart_lsn` và consumer lag.
5. Kiểm tra standby feedback nếu có hot standby.
6. Kiểm tra `age(datfrozenxid)` và `age(relfrozenxid)` để đánh giá rủi ro wraparound.
7. Đọc log autovacuum và `pg_stat_progress_vacuum`.
8. Giải phóng nguồn giữ horizon theo quy trình an toàn.
9. Để VACUUM thường thu hồi tuple và theo dõi khả năng tái sử dụng không gian.
10. Chỉ lên kế hoạch `VACUUM FULL`/rewrite khi cần thu nhỏ vật lý và có cửa sổ bảo trì phù hợp.

## 18. Kết luận

PostgreSQL giữ nhiều tuple version để thực hiện MVCC. VACUUM chỉ có thể thu hồi phiên bản cũ khi không còn snapshot hoặc cơ chế nào cần chúng. Transaction kéo dài, snapshot ổn định bị giữ quá lâu, prepared transaction, replication slot và standby feedback đều có thể làm visibility horizon lùi lại, khiến dead tuple tích lũy và bảng phình to.

VACUUM thường thu hồi không gian để tái sử dụng và cập nhật metadata; autovacuum tự động chạy công việc này theo ngưỡng; freezing giúp bảo vệ database khỏi XID wraparound. `VACUUM FULL` viết lại relation để có thể trả dung lượng vật lý nhưng cần khóa mạnh và kế hoạch bảo trì. Khi xử lý bloat, hãy tìm nguồn giữ horizon trước, theo dõi `pg_stat_activity`, `pg_stat_user_tables`, `pg_replication_slots` và tuổi XID, rồi mới điều chỉnh autovacuum hoặc lên kế hoạch rewrite.

Thiết kế ứng dụng cũng quan trọng như cấu hình database: giữ transaction ngắn, không chờ dịch vụ ngoài khi đang giữ snapshot/lock, đóng cursor đúng lúc, đặt timeout hợp lý và chia công việc dài thành batch có checkpoint. Nhờ vậy PostgreSQL có thể dọn phiên bản cũ đúng lúc, tái sử dụng không gian và duy trì hiệu năng ổn định.
