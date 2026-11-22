# Bản ghi chết, dữ liệu phình to và cơ chế thu hồi dung lượng

## Mục tiêu bài học

Trong hệ quản trị cơ sở dữ liệu dùng MVCC, một thao tác `UPDATE` thường tạo phiên bản dòng mới, còn `DELETE` đánh dấu dòng không còn hiệu lực đối với các snapshot mới. Những phiên bản cũ không thể bị xóa ngay vì transaction khác có thể vẫn cần nhìn thấy chúng. Theo thời gian, các phiên bản không còn cần thiết tích lũy thành dead tuples, làm bảng và chỉ mục chiếm nhiều trang hơn, tăng I/O và kéo dài truy vấn.

Trong chương **Bảo trì dữ liệu** của module **DATABASE_PERFORMANCE**, bài học này giải thích bản ghi chết, dữ liệu phình to (bloat) và các cơ chế thu hồi dung lượng. Module **DATABASE_PERFORMANCE** rèn phương pháp tối ưu hiệu năng cơ sở dữ liệu dựa trên đo đạc tải, kế hoạch thực thi, thống kê và cơ chế truy cập dữ liệu; nội dung hướng dẫn thiết kế chỉ mục, cải thiện SQL, nhận diện tranh chấp giao dịch, nút thắt I/O, bộ nhớ và kiểm chứng kết quả sau điều chỉnh. Vì vậy, bảo trì dữ liệu cần được đánh giá bằng tốc độ phát sinh dead tuples, khả năng tái sử dụng trang, kích thước relation, hoạt động autovacuum và tác động tới workload đọc/ghi.

Sau bài học, bạn có thể:

- Giải thích vì sao MVCC tạo ra nhiều phiên bản dòng và khi nào phiên bản cũ trở thành dead tuple.
- Phân biệt dead tuples, bloat, không gian có thể tái sử dụng và dung lượng đã trả về filesystem.
- Hiểu vai trò của `VACUUM`, `ANALYZE`, autovacuum và freeze.
- Nhận diện transaction dài hoặc replication horizon đang ngăn vacuum dọn dữ liệu cũ.
- Theo dõi dead tuples, tiến trình vacuum, kích thước bảng/index và dung lượng WAL.
- Chọn cách xử lý phù hợp: vacuum thường, điều chỉnh autovacuum, xóa theo batch, partition retention, `VACUUM FULL` hoặc rebuild index.
- Đánh giá rủi ro khóa, I/O, dung lượng tạm và khả năng phục hồi trước khi thu hồi dung lượng.

## 1. Vì sao cơ sở dữ liệu tạo bản ghi chết?

PostgreSQL sử dụng MVCC (Multi-Version Concurrency Control) để cho phép các transaction đọc những phiên bản dữ liệu phù hợp với snapshot của chúng. Khi một dòng được cập nhật, PostgreSQL thường tạo một tuple version mới. Phiên bản cũ vẫn tồn tại cho đến khi chắc chắn không còn snapshot nào cần nhìn thấy nó.

Ví dụ:

```sql
UPDATE accounts
SET balance = balance - 100
WHERE account_id = 101;
```

Về mặt logic, ứng dụng chỉ thấy số dư mới. Nhưng trong heap, PostgreSQL có thể giữ phiên bản tuple cũ và tạo phiên bản mới. Sau khi mọi transaction có thể nhìn thấy phiên bản cũ đã kết thúc, phiên bản cũ trở thành ứng viên để vacuum thu hồi.

Với `DELETE`, dòng không bị xóa vật lý ngay lập tức:

```sql
DELETE FROM sessions
WHERE expires_at < now();
```

Lệnh này đánh dấu phiên bản dòng đã bị xóa theo cơ chế MVCC. Các transaction có snapshot cũ vẫn có thể cần nhìn thấy phiên bản đó. Khi không còn snapshot nào cần nó, vacuum mới có thể loại bỏ phiên bản cũ và làm không gian có thể tái sử dụng.

### 1.1. Vòng đời của một tuple

```text
INSERT
  |
  v
Tuple đang sống
  |
  +---- UPDATE ----> Tạo tuple version mới
  |                     |
  |                     +--> Version cũ chờ hết snapshot liên quan
  |
  +---- DELETE ----> Tuple được đánh dấu đã xóa
                        |
                        v
             Không còn snapshot cần version cũ
                        |
                        v
                   VACUUM
                        |
                        v
          Không gian có thể tái sử dụng
```

Một tuple version không còn được transaction hiện tại nhìn thấy chưa chắc đã có thể xóa ngay. Vacuum phải tôn trọng mọi transaction snapshot, replication horizon và các cơ chế giữ phiên bản cũ khác.

### 1.2. Dead tuple không đồng nghĩa dòng bị xóa khỏi file

Dead tuple là phiên bản dòng không còn cần cho khả năng nhìn thấy dữ liệu theo MVCC. Vacuum có thể loại bỏ tham chiếu của phiên bản đó và đánh dấu không gian tương ứng có thể tái sử dụng. Trang và file thường vẫn được giữ lại để phục vụ các lần ghi tiếp theo.

Vì vậy, số dead tuples cao là tín hiệu cần điều tra, nhưng không thể chỉ dựa vào con số đó để kết luận dung lượng có thể trả về hệ điều hành. Cần xem kích thước relation, phân bố khoảng trống, tốc độ phát sinh dữ liệu mới và khả năng tái sử dụng.

## 2. Bloat là gì và ảnh hưởng hiệu năng ra sao?

**Bloat** là phần dung lượng relation hoặc index lớn hơn mức cần thiết cho dữ liệu hữu ích hiện tại, thường do phiên bản tuple cũ, khoảng trống phân tán, cập nhật/xóa nhiều hoặc cấu trúc index không còn gọn. Không phải mọi khoảng trống đều là bloat xấu: một lượng free space trong trang có thể cần thiết cho cập nhật trong tương lai.

### 2.1. Table bloat

Table bloat xuất hiện khi heap relation chứa nhiều trang có dead tuple hoặc free space phân tán. Các truy vấn tuần tự có thể phải đọc nhiều trang hơn để tìm cùng một lượng dòng sống.

Tác động có thể gồm:

- Tăng số trang cần đọc và dung lượng buffer cache cần thiết.
- Tăng I/O tuần tự hoặc ngẫu nhiên cho cùng một tập kết quả.
- Làm index scan phải truy cập heap nhiều hơn.
- Kéo dài backup, restore, scan, vacuum và các thao tác bảo trì.
- Làm tăng dung lượng lưu trữ và chi phí replication/backup.

### 2.2. Index bloat

Index cũng cần bảo trì khi dòng được cập nhật hoặc xóa. Các index entry cũ có thể được loại bỏ trong quá trình vacuum/index cleanup, nhưng các trang index không nhất thiết được trả về filesystem. Với B-tree, page split, churn và phân bố khóa có thể làm cấu trúc lớn hơn mức cần thiết.

Index bloat có thể làm:

- Tăng số trang index cần đọc.
- Giảm hiệu quả cache.
- Tăng chi phí duy trì index khi ghi.
- Làm index scan và range scan tốn thêm I/O.
- Tăng thời gian backup và thao tác index maintenance.

Không nên rebuild mọi index chỉ vì kích thước lớn. Một index lớn có thể phản ánh số lượng khóa hợp lệ hoặc workload thực tế. Hãy đánh giá kích thước, số dòng, số lần sử dụng, mức churn và kế hoạch truy vấn.

### 2.3. Bloat không chỉ là dead tuple

Một bảng có thể ít dead tuples tại thời điểm đo nhưng vẫn chiếm nhiều trang do free space nằm rải rác. Một bảng khác có nhiều dead tuples nhưng vacuum có thể nhanh chóng làm chúng tái sử dụng. Bloat còn phụ thuộc fillfactor, kích thước dòng, cập nhật, page split và khả năng gom các dòng sống.

Các ước lượng bloat thường phụ thuộc giả định về kích thước dòng và mức lấp đầy trang. Để xác nhận, có thể dùng extension như `pgstattuple` hoặc `pgstattuple_approx` khi được phép; thao tác đo chính xác có thể phải quét nhiều dữ liệu và gây I/O, nên cần đánh giá trước khi chạy trên bảng lớn.

## 3. VACUUM làm gì?

`VACUUM` quét relation để xử lý các tuple version không còn cần thiết, cập nhật thông tin phục vụ quản lý không gian và giúp hệ thống tái sử dụng các vùng trống. Nó cũng phối hợp với việc dọn index entry cũ và cập nhật visibility map.

Lệnh cơ bản:

```sql
VACUUM public.orders;
```

Để đồng thời cập nhật thống kê cho optimizer:

```sql
VACUUM (ANALYZE) public.orders;
```

`VACUUM` thông thường có thể chạy đồng thời với phần lớn thao tác `SELECT`, `INSERT`, `UPDATE` và `DELETE`. Nó vẫn tạo I/O, dùng CPU và có thể ảnh hưởng latency nếu chạy quá nhiều hoặc cạnh tranh với workload. Không chạy `VACUUM` trong transaction block thông thường.

### 3.1. Không gian được tái sử dụng bên trong relation

Sau khi vacuum xử lý dead tuples, khoảng trống có thể được tái sử dụng bởi các lần ghi sau. Điều này giúp hạn chế tăng trưởng file khi workload tiếp tục chèn hoặc cập nhật dữ liệu có đặc tính tương tự.

Vacuum thường không compact toàn bộ bảng và không bảo đảm làm file nhỏ lại. Trong một số điều kiện, PostgreSQL có thể truncate các trang trống ở cuối relation và trả phần đuôi đó về filesystem; thao tác truncate có thể cần khóa mạnh trong thời gian ngắn. Phần trống nằm giữa các trang thường được giữ lại để tái sử dụng.

### 3.2. VACUUM và ANALYZE là hai nhiệm vụ khác nhau

`VACUUM` xử lý phiên bản tuple cũ và thông tin không gian. `ANALYZE` lấy mẫu dữ liệu để cập nhật thống kê cho query planner, ví dụ phân bố giá trị và số lượng giá trị khác nhau.

Một truy vấn có thể vẫn chậm sau vacuum nếu thống kê chưa phản ánh dữ liệu mới. Ngược lại, `ANALYZE` có thể cải thiện ước lượng kế hoạch nhưng không loại bỏ dead tuples.

Ví dụ:

```sql
ANALYZE public.orders;
```

Khi vừa bảo trì dữ liệu vừa cần cập nhật thống kê, dùng `VACUUM (ANALYZE)` hoặc chạy hai thao tác theo lịch phù hợp.

### 3.3. VACUUM và visibility map

Visibility map ghi nhận các trang mà tất cả tuple trên đó đều hiển thị với mọi transaction hiện tại (all-visible), và trong một số trường hợp tất cả tuple đã được freeze (all-frozen). Thông tin này giúp PostgreSQL bỏ qua một số trang trong vacuum và hỗ trợ index-only scan không cần kiểm tra heap cho trang all-visible.

Khi một trang bị cập nhật, trạng thái visibility liên quan có thể bị xóa và cần được vacuum xác nhận lại. Vì vậy, bảng cập nhật liên tục có thể có ít trang all-visible hơn, làm index-only scan phải truy cập heap thường xuyên hơn.

Vacuum đều đặn vừa giúp thu hồi phiên bản cũ, vừa duy trì visibility map. Đây là một lý do khác khiến autovacuum có ảnh hưởng tới hiệu năng đọc.

## 4. VACUUM FULL và các cách viết lại relation

Nếu mục tiêu là trả dung lượng lớn về filesystem, `VACUUM FULL` có hành vi khác vacuum thường.

```sql
VACUUM FULL public.orders;
```

`VACUUM FULL` viết lại toàn bộ relation thành một bản gọn hơn, sau đó thay thế bản cũ. Nó có thể trả nhiều dung lượng về filesystem, nhưng:

- Cần khóa `ACCESS EXCLUSIVE` trên bảng trong quá trình thực hiện, chặn cả đọc và ghi thông thường.
- Cần thêm dung lượng để tạo bản viết lại trước khi bỏ bản cũ.
- Có thể tạo I/O lớn, WAL và thời gian chạy đáng kể.
- Có thể ảnh hưởng replication, backup và workload khác.
- Không phù hợp để chạy tùy tiện trong giờ cao điểm hoặc khi volume gần đầy.

`VACUUM FULL` không phải thao tác “dọn nhẹ”. Trước khi chạy, cần dự báo dung lượng peak, kiểm tra thời gian chặn, lập cửa sổ bảo trì và có phương án phục hồi.

### 4.1. CLUSTER và table rewrite

`CLUSTER` viết lại bảng theo thứ tự của một index được chọn. Nó có thể cải thiện locality cho một số mẫu truy vấn, nhưng cũng cần khóa mạnh, dung lượng làm việc và I/O đáng kể. Thứ tự vật lý không được duy trì tự động sau các lần ghi tiếp theo.

Một số dạng `ALTER TABLE` cũng viết lại relation. Trước khi dùng bất kỳ thao tác rewrite nào, hãy xem yêu cầu khóa, dung lượng tạm và thời gian hoàn tất trên đúng phiên bản PostgreSQL.

### 4.2. Chọn phương án thu hồi dung lượng

| Mục tiêu | Phương án thường xem xét | Đánh đổi chính |
|---|---|---|
| Làm dead tuple có thể tái sử dụng | `VACUUM` thường/autovacuum | Không compact toàn bảng; vẫn tiêu thụ I/O |
| Cập nhật thống kê planner | `ANALYZE` | Không thu hồi dead tuple |
| Trả phần trang trống ở cuối relation | Vacuum truncation khi đủ điều kiện | Có thể cần khóa mạnh ngắn hạn; không thu gọn khoảng trống ở giữa |
| Thu gọn toàn bộ heap và trả dung lượng | `VACUUM FULL` | Khóa `ACCESS EXCLUSIVE`, cần thêm disk và I/O |
| Sắp xếp lại heap theo index | `CLUSTER` | Rewrite, khóa mạnh, thứ tự không tự duy trì |
| Rebuild index phình to | `REINDEX` hoặc `REINDEX CONCURRENTLY` khi hỗ trợ | Cần thêm dung lượng và I/O; phương án concurrently có thêm bước và thời gian |
| Loại dữ liệu cũ theo lô | DELETE theo batch hoặc partition retention | DELETE tạo dead tuples; partition drop/detach cần kiểm tra phụ thuộc và khóa |

## 5. Autovacuum giữ cho dữ liệu được bảo trì tự động

Autovacuum là các tiến trình nền theo dõi thống kê hoạt động của bảng và tự động chạy vacuum hoặc analyze khi vượt ngưỡng. Nếu autovacuum không theo kịp tốc độ ghi, dead tuples và bloat có thể tăng nhanh.

### 5.1. Ngưỡng kích hoạt vacuum

Với một bảng, ngưỡng vacuum truyền thống được tính dựa trên ngưỡng tuyệt đối cộng với tỷ lệ của số tuple ước lượng:

```text
vacuum threshold
  = autovacuum_vacuum_threshold
  + autovacuum_vacuum_scale_factor * estimated table tuples
```

Điều này có nghĩa một bảng rất lớn có thể tích lũy rất nhiều thay đổi trước khi đạt ngưỡng nếu scale factor quá cao. Ví dụ, scale factor 0,2 trên bảng 100 triệu tuple có thể tương ứng hàng chục triệu thay đổi trước khi vacuum được kích hoạt, tùy thống kê và phiên bản.

Các phiên bản PostgreSQL mới còn có ngưỡng riêng cho vacuum dựa trên số dòng insert, giúp xử lý bảng insert-heavy và duy trì visibility map/freeze. Tên tham số thường gặp là `autovacuum_vacuum_insert_threshold` và `autovacuum_vacuum_insert_scale_factor`; hãy xác nhận phiên bản trước khi sử dụng.

### 5.2. Ngưỡng ANALYZE

Ngưỡng autoanalyze cũng dựa trên số thay đổi và tỷ lệ scale factor:

```text
analyze threshold
  = autovacuum_analyze_threshold
  + autovacuum_analyze_scale_factor * estimated table tuples
```

Một bảng có phân bố dữ liệu thay đổi nhanh cần được analyze đủ thường xuyên để planner có thống kê mới. Vacuum và analyze có thể chạy bởi cùng hệ thống autovacuum nhưng có mục tiêu khác nhau.

### 5.3. Cấu hình autovacuum theo từng bảng

Không phải mọi bảng đều có cùng tốc độ thay đổi. Có thể đặt storage parameter riêng cho bảng ghi nhiều:

```sql
ALTER TABLE public.orders SET (
    autovacuum_vacuum_scale_factor = 0.02,
    autovacuum_vacuum_threshold = 1000,
    autovacuum_analyze_scale_factor = 0.01,
    autovacuum_analyze_threshold = 1000
);
```

Các giá trị trên chỉ minh họa. Cần đo số dòng thay đổi mỗi giờ, kích thước bảng, thời gian vacuum và năng lực I/O trước khi chọn ngưỡng. Scale factor quá thấp có thể làm vacuum chạy quá thường xuyên; quá cao có thể để dead tuples tích lũy nhiều.

Để xem một số storage parameter của bảng:

```sql
SELECT
    c.oid::regclass AS relation_name,
    c.reloptions
FROM pg_class AS c
WHERE c.oid = 'public.orders'::regclass;
```

### 5.4. Các tham số vận hành autovacuum

Một số tham số cần theo dõi:

- `autovacuum`: bật/tắt hệ thống autovacuum.
- `autovacuum_max_workers`: số worker autovacuum tối đa chạy đồng thời.
- `autovacuum_naptime`: khoảng nghỉ giữa các lần worker launcher kiểm tra.
- `autovacuum_vacuum_cost_limit` và `autovacuum_vacuum_cost_delay`: điều tiết công việc vacuum theo chi phí.
- `autovacuum_work_mem`: bộ nhớ dành cho autovacuum nếu được cấu hình riêng.
- Các ngưỡng vacuum/analyze theo database hoặc từng bảng.

Tăng số worker hoặc cost limit có thể giúp xử lý backlog nhanh hơn, nhưng cũng tăng I/O và CPU cạnh tranh với ứng dụng. Giảm quá nhiều có thể khiến vacuum không bắt kịp. Điều chỉnh phải dựa trên số bảng cần vacuum đồng thời, thời gian chạy, storage latency và mức tải production.

Không tắt autovacuum để tránh I/O trong thời gian dài. Việc này có thể làm dead tuples tích lũy, visibility map lỗi thời và transaction ID tiến gần ngưỡng wraparound.

## 6. Transaction dài và vacuum horizon

Một nguyên nhân quan trọng khiến vacuum không thể dọn dead tuples là có transaction hoặc snapshot cũ vẫn cần nhìn thấy các phiên bản đó.

### 6.1. Transaction mở lâu

Ví dụ một ứng dụng mở transaction rồi chờ người dùng hoặc gọi dịch vụ ngoài:

```sql
BEGIN;

SELECT *
FROM orders
WHERE order_id = 1001;

-- Ứng dụng giữ transaction mở trong khi xử lý bên ngoài.
-- Các phiên bản cũ có thể vẫn cần cho snapshot này.

COMMIT;
```

Transaction dài có thể giữ snapshot cũ, làm vacuum không thể loại bỏ một số tuple version. Nó cũng có thể giữ row/table lock, làm tăng bloat và chặn các thao tác khác.

Kiểm tra transaction đang mở:

```sql
SELECT
    pid,
    usename,
    application_name,
    state,
    xact_start,
    clock_timestamp() - xact_start AS xact_age,
    backend_xmin,
    wait_event_type,
    wait_event,
    left(query, 300) AS query
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start;
```

Chú ý các session `idle in transaction`, transaction chạy lâu và `backend_xmin` cũ. Không tự động kết thúc session chỉ dựa trên tuổi; cần xác định ứng dụng sở hữu và tác động rollback.

### 6.2. Replication slot và standby feedback

Replication slot có thể giữ WAL và giữ lại các phiên bản dữ liệu cần cho logical decoding hoặc replica. Các cột `xmin` và `catalog_xmin` trong `pg_replication_slots` có thể giữ vacuum horizon cho dữ liệu hoặc catalog tương ứng.

```sql
SELECT
    slot_name,
    slot_type,
    active,
    xmin,
    catalog_xmin,
    restart_lsn
FROM pg_replication_slots
ORDER BY slot_name;
```

Standby dùng `hot_standby_feedback` có thể gửi xmin feedback về primary để tránh query trên standby bị conflict, nhưng điều này có thể khiến primary giữ lại tuple cũ lâu hơn. Nếu replica bị chậm hoặc slot không được tiêu thụ, bloat và WAL retention có thể tăng.

Không xóa slot đang được sử dụng chỉ để giải phóng dung lượng. Trước tiên cần xác định consumer, khả năng khởi tạo lại replication và tác động mất vị trí đọc.

### 6.3. Prepared transaction

Prepared transaction trong two-phase commit có thể tồn tại lâu và giữ tài nguyên sau giai đoạn prepare. Kiểm tra `pg_prepared_xacts` khi nghi ngờ transaction cũ:

```sql
SELECT
    transaction,
    gid,
    prepared,
    owner,
    database
FROM pg_prepared_xacts
ORDER BY prepared;
```

Chỉ commit hoặc rollback prepared transaction theo trạng thái giao dịch phân tán và quyết định của coordinator. Không tự giải quyết chỉ để vacuum chạy.

## 7. Freeze và ngăn transaction ID wraparound

PostgreSQL dùng transaction ID (XID) có không gian hữu hạn. Để tránh hiện tượng wraparound làm dữ liệu cũ có thể bị diễn giải sai về khả năng hiển thị, vacuum phải freeze các tuple đủ cũ. Đây là nhiệm vụ bảo vệ tính đúng đắn, không chỉ là tối ưu dung lượng.

### 7.1. Freeze là gì?

Freeze đánh dấu tuple cũ theo cách cho phép PostgreSQL không phải tiếp tục so sánh XID ban đầu của tuple trong mọi snapshot tương lai. Vacuum thực hiện freeze theo ngưỡng và chính sách cấu hình.

Nếu vacuum bị trì hoãn quá lâu, database có thể tiến gần ngưỡng anti-wraparound. PostgreSQL có thể khởi chạy vacuum khẩn cấp; nếu không thể hoàn tất trước ngưỡng an toàn, hệ thống có thể từ chối một số thao tác ghi để bảo vệ dữ liệu.

### 7.2. Theo dõi tuổi XID

```sql
SELECT
    datname,
    age(datfrozenxid) AS xid_age
FROM pg_database
ORDER BY xid_age DESC;
```

Có thể xem bảng có `relfrozenxid` cũ:

```sql
SELECT
    n.nspname,
    c.relname,
    age(c.relfrozenxid) AS xid_age
FROM pg_class AS c
JOIN pg_namespace AS n
  ON n.oid = c.relnamespace
WHERE c.relkind IN ('r', 'm')
ORDER BY xid_age DESC
LIMIT 20;
```

Giá trị tuổi XID cần được đối chiếu với ngưỡng cấu hình và cảnh báo của phiên bản đang chạy. Không chờ tới khi database gần ngưỡng tối đa mới xử lý.

### 7.3. Không hy sinh freeze để giảm I/O

Điều chỉnh vacuum freeze age hoặc tắt autovacuum có thể làm trì hoãn công việc trước mắt nhưng tăng rủi ro wraparound. Khi vacuum chống wraparound xuất hiện, nó có thể tạo tải I/O lớn và ảnh hưởng workload nghiêm trọng hơn. Hãy giữ chính sách freeze an toàn, giám sát XID age và xử lý transaction/replication horizon đang cản trở vacuum.

## 8. Theo dõi dead tuples và tiến trình vacuum

### 8.1. Thống kê theo bảng

```sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup,
    last_vacuum,
    last_autovacuum,
    last_analyze,
    last_autoanalyze,
    vacuum_count,
    autovacuum_count
FROM pg_stat_user_tables
ORDER BY n_dead_tup DESC
LIMIT 30;
```

`n_live_tup` và `n_dead_tup` là ước lượng thống kê, không phải phép đếm chính xác tại thời điểm truy vấn. Hãy xem xu hướng qua nhiều snapshot và so sánh với kích thước bảng, tốc độ ghi, thời điểm vacuum gần nhất.

### 8.2. Theo dõi vacuum đang chạy

```sql
SELECT
    p.pid,
    p.relid::regclass AS relation_name,
    p.phase,
    p.heap_blks_total,
    p.heap_blks_scanned,
    p.heap_blks_vacuumed,
    p.index_vacuum_count,
    a.query_start,
    a.wait_event_type,
    a.wait_event
FROM pg_stat_progress_vacuum AS p
LEFT JOIN pg_stat_activity AS a
  ON a.pid = p.pid
ORDER BY p.pid;
```

View `pg_stat_progress_vacuum` cho biết phase và tiến độ của vacuum đang hoạt động. Không phải mọi dạng bảo trì index hoặc rewrite đều xuất hiện ở view này; PostgreSQL có các progress view khác cho một số thao tác như create index.

### 8.3. Theo dõi kích thước relation

```sql
SELECT
    schemaname,
    relname,
    pg_size_pretty(pg_relation_size(relid)) AS heap_size,
    pg_size_pretty(pg_indexes_size(relid)) AS indexes_size,
    pg_size_pretty(pg_total_relation_size(relid)) AS total_size
FROM pg_stat_user_tables
ORDER BY pg_total_relation_size(relid) DESC
LIMIT 30;
```

Theo dõi kích thước theo thời gian để xác định bảng/index nào tăng nhanh. Một lần đo đơn lẻ không phân biệt được tăng trưởng hợp lệ với bloat. Cần kết hợp số dòng, tỷ lệ cập nhật/xóa, dead tuple estimate và dung lượng có thể tái sử dụng.

### 8.4. Đo chi tiết khi cần

Extension `pgstattuple` có thể cung cấp thông tin về tuple sống, tuple chết và free space của relation. `pgstattuple_approx` có thể ước lượng nhanh hơn bằng cách tận dụng visibility map nhưng kết quả là xấp xỉ. Với B-tree, `pgstatindex` có thể giúp quan sát page density và các thuộc tính cấu trúc.

Các phép đo chính xác có thể quét nhiều trang, tiêu thụ I/O và ảnh hưởng workload. Chỉ chạy khi có quyền, đã đánh giá chi phí và có mục tiêu điều tra rõ. Không cài extension hoặc chạy scan nặng chỉ để tạo một con số bloat cho mọi bảng định kỳ.

## 9. Giảm phát sinh dead tuples và bloat

### 9.1. Tránh cập nhật không cần thiết

Một ứng dụng có thể gửi `UPDATE` ngay cả khi giá trị mới giống giá trị cũ. Điều này tạo thêm tuple version và WAL dù dữ liệu logic không đổi.

Ví dụ thêm điều kiện để chỉ cập nhật khi có thay đổi:

```sql
UPDATE customers
SET display_name = :new_name
WHERE customer_id = :customer_id
  AND display_name IS DISTINCT FROM :new_name;
```

`IS DISTINCT FROM` xử lý NULL theo cách so sánh an toàn hơn `<>` trong trường hợp này. Điều kiện giúp tránh tạo version mới khi giá trị không đổi. Hãy đo số dòng thực sự được cập nhật và xem trigger/audit có phụ thuộc vào việc nhận mọi lệnh UPDATE hay không.

### 9.2. Thiết kế HOT update

HOT (Heap-Only Tuple) update cho phép PostgreSQL tạo phiên bản tuple mới trên cùng heap page mà không cần cập nhật mọi index entry, khi các điều kiện cần thiết được đáp ứng. Một điều kiện quan trọng là các cột được cập nhật không nằm trong index cần bảo trì; đồng thời trang phải còn đủ chỗ cho tuple version mới.

Giảm fillfactor của heap table có thể để lại khoảng trống trên trang, tăng cơ hội HOT update:

```sql
ALTER TABLE public.customer_profiles
SET (fillfactor = 80);
```

Giá trị 80 chỉ là ví dụ. Fillfactor thấp hơn làm relation chiếm nhiều trang hơn và có thể tăng chi phí scan/cache. Cần chọn dựa trên tỷ lệ update, kích thước dòng, HOT update ratio và workload đọc.

Theo dõi một số thống kê:

```sql
SELECT
    relname,
    n_tup_upd,
    n_tup_hot_upd,
    CASE
        WHEN n_tup_upd > 0
        THEN round(100.0 * n_tup_hot_upd / n_tup_upd, 2)
        ELSE 0
    END AS hot_update_percent
FROM pg_stat_user_tables
ORDER BY n_tup_upd DESC
LIMIT 20;
```

Nếu tỷ lệ HOT thấp ở bảng cập nhật nhiều, xem các index trên cột thường thay đổi, fillfactor và khả năng đặt lại index. Không bỏ index quan trọng chỉ để tăng HOT update; cần cân bằng đọc và ghi.

### 9.3. Giữ transaction ngắn

Không giữ transaction mở trong lúc gọi API ngoài, chờ người dùng hoặc xử lý batch lâu. Transaction dài giữ snapshot cũ và có thể ngăn vacuum dọn phiên bản tuple. Hãy chia công việc thành transaction ngắn khi nghiệp vụ cho phép và xác định rõ tính nguyên tử.

### 9.4. Dùng retention và partition cho dữ liệu lịch sử

Nếu dữ liệu cũ được xóa theo thời gian, partition theo ngày/tháng có thể giúp loại bỏ cả vùng dữ liệu bằng `DROP TABLE` hoặc detach/drop partition thay vì `DELETE` hàng triệu dòng. Thao tác partition vẫn cần xem khóa, phụ thuộc, foreign key, replication và chính sách lưu trữ.

Đối với bảng không partition, xóa theo batch giúp giới hạn số dòng bị khóa và lượng WAL mỗi transaction:

```sql
WITH batch AS (
    SELECT ctid
    FROM public.events
    WHERE created_at < TIMESTAMPTZ '2025-01-01 00:00:00+00'
    ORDER BY created_at
    LIMIT 5000
    FOR UPDATE SKIP LOCKED
)
DELETE FROM public.events AS e
USING batch AS b
WHERE e.ctid = b.ctid;
```

Chạy câu lệnh theo từng batch trong các transaction riêng và dừng khi không còn dòng phù hợp. `ctid` chỉ là định danh vật lý của tuple trong relation tại thời điểm hiện tại; dùng nó trong cùng statement như ví dụ là phù hợp, không lưu `ctid` làm khóa nghiệp vụ lâu dài. `SKIP LOCKED` có thể bỏ qua dòng đang bị transaction khác khóa; nếu dùng nhiều worker, cần chạy lại các batch để xử lý phần còn lại.

DELETE theo batch vẫn tạo dead tuples. Cần để autovacuum theo kịp sau khi xóa và cân nhắc partition nếu retention là quy trình định kỳ trên lượng dữ liệu lớn.

## 10. Xử lý khi dead tuples tích lũy nhanh

Khi một bảng có dead tuple estimate tăng liên tục, không nên chỉ chạy `VACUUM` lặp lại. Hãy xác định vì sao vacuum không theo kịp hoặc không thể loại bỏ phiên bản cũ.

### 10.1. Kiểm tra tốc độ phát sinh

- Tỷ lệ `UPDATE`/`DELETE` trên bảng.
- Batch job hoặc cleanup chạy theo đợt.
- Ứng dụng cập nhật cùng giá trị nhiều lần.
- Trigger tạo thêm cập nhật hoặc audit row.
- Index quá nhiều làm mỗi update tốn thêm công việc.
- Bảng có row width lớn hoặc cập nhật payload lớn.

### 10.2. Kiểm tra vacuum có được kích hoạt không

Xem `last_autovacuum`, `autovacuum_count`, dead tuple estimate và ngưỡng per-table. Nếu bảng rất lớn, scale factor mặc định có thể khiến ngưỡng tuyệt đối quá cao. Nếu worker thường xuyên bận, bảng có thể phải chờ tới lượt.

### 10.3. Kiểm tra vacuum có bị chặn bởi horizon không

Xem transaction dài, session `idle in transaction`, prepared transaction, replication slot `xmin`/`catalog_xmin` và standby feedback. Nếu snapshot cũ còn tồn tại, tăng số worker hoặc cost limit không làm tuple trở nên có thể xóa.

### 10.4. Kiểm tra vacuum có đủ tài nguyên không

Xem phase và tiến độ vacuum, I/O latency, CPU, index cleanup, storage throughput và autovacuum log. Nếu vacuum bị throttling quá mạnh, có thể điều chỉnh cost limit/delay hoặc lịch chạy; nếu I/O đã bão hòa, tăng tốc vacuum có thể làm truy vấn ứng dụng chậm hơn.

### 10.5. Kiểm tra index riêng biệt

Nếu heap đã được vacuum nhưng index vẫn lớn hoặc page density thấp, đánh giá index bloat bằng công cụ phù hợp. Chỉ rebuild index khi có bằng chứng về dung lượng dư hoặc hiệu năng giảm. Cân nhắc `REINDEX CONCURRENTLY` khi phiên bản hỗ trợ và cần giảm thời gian chặn ghi; phương án này cần thêm dung lượng, thời gian và I/O, đồng thời có các giai đoạn khóa ngắn.

## 11. Kế hoạch thu hồi dung lượng an toàn

Trước khi chọn công cụ, xác định mục tiêu:

- **Tái sử dụng trong database:** vacuum thường thường là lựa chọn đầu tiên.
- **Trả dung lượng về filesystem:** cần thao tác có thể thu nhỏ relation hoặc loại bỏ file/partition; vacuum thường không bảo đảm điều này.
- **Giảm kích thước index:** xem xét index cleanup, reindex hoặc thay đổi index không còn cần.
- **Giảm tăng trưởng tương lai:** giảm update không cần thiết, dùng HOT, retention và partition.

### 11.1. Bảng quyết định

| Triệu chứng | Kiểm tra trước | Hướng xử lý có thể phù hợp |
|---|---|---|
| `n_dead_tup` tăng nhanh | Tốc độ update/delete, autovacuum threshold, vacuum history | Điều chỉnh autovacuum, giảm churn, xử lý horizon |
| Vacuum chạy lâu | Relation size, I/O, index cleanup, transaction horizon | Tối ưu lịch/tài nguyên, kiểm tra index và blocker |
| Bảng lớn nhưng ít dead tuples | Số dòng sống, row width, fillfactor, lịch sử tăng trưởng | Có thể là dung lượng hợp lệ; không rewrite chỉ vì file lớn |
| Heap có nhiều free space phân tán | Bloat estimate, page density, workload update | Cân nhắc rewrite khi lợi ích vượt chi phí khóa và disk |
| Index lớn bất thường | Index usage, page density, churn, số index | Reindex có kiểm soát hoặc loại index không cần sau phân tích |
| Cần xóa lịch sử theo thời gian | Retention, partition layout, phụ thuộc | Drop/detach partition thay cho delete lớn nếu mô hình cho phép |
| XID age tăng cao | Transaction horizon, replication slot, vacuum progress | Ưu tiên xử lý freeze/anti-wraparound an toàn |

### 11.2. Chuẩn bị trước VACUUM FULL hoặc REINDEX

Trước thao tác rewrite/rebuild lớn:

1. Đo kích thước heap, index và dung lượng trống của volume.
2. Ước lượng dung lượng cần thêm trong lúc tạo bản mới.
3. Kiểm tra backup gần nhất và khả năng restore.
4. Xác định mức khóa, thời gian chặn và các truy vấn phụ thuộc.
5. Kiểm tra WAL generation, replication lag và archive capacity.
6. Chọn thời điểm tải thấp hoặc cửa sổ bảo trì.
7. Theo dõi I/O, free space và tiến độ trong lúc chạy.
8. Xác nhận kích thước, hiệu năng và khả năng ghi sau thao tác.

Không chạy rewrite khi volume chỉ vừa đủ chứa file hiện tại. Bản viết lại cần chỗ để tồn tại đồng thời với bản cũ trong một phần quá trình.

## 12. Ví dụ thực hành: bảng sự kiện ghi nhiều

Giả sử bảng `events` nhận hàng triệu sự kiện mỗi ngày. Một job xóa dữ liệu cũ chạy một lần mỗi tuần bằng một câu `DELETE` lớn. Sau một thời gian, kích thước bảng tăng, truy vấn theo thời gian chậm và autovacuum thường xuyên hoạt động.

### Bước 1 — Đo hiện trạng

Thu thập `n_live_tup`, `n_dead_tup`, `last_autovacuum`, kích thước heap/index, temp usage và tốc độ WAL. Dùng `EXPLAIN (ANALYZE, BUFFERS)` cho truy vấn đọc quan trọng để xác định số trang phải đọc.

### Bước 2 — Kiểm tra nguyên nhân

Xem job xóa có tạo một transaction quá lớn không, autovacuum có được kích hoạt sau batch không, có transaction dài hoặc replication slot giữ xmin không. Kiểm tra các index trên `created_at` và các cột cập nhật thường xuyên.

### Bước 3 — Cải thiện retention

Nếu dữ liệu được lưu theo tháng và có thể partition theo thời gian, tạo partition mới theo lịch và loại bỏ partition hết hạn theo chính sách. Nếu chưa thể partition, xóa theo batch nhỏ, commit giữa các batch và theo dõi lock/WAL.

### Bước 4 — Điều chỉnh autovacuum

Đặt threshold/scale factor riêng cho bảng theo tốc độ thay đổi. Theo dõi số lần vacuum, thời gian chạy, dead tuples sau mỗi chu kỳ và I/O. Không tăng worker chỉ để làm sạch nhanh hơn nếu storage đã bão hòa.

### Bước 5 — Đánh giá bloat và reclaim

Sau khi vacuum bắt kịp, kiểm tra phần trống nội bộ và kích thước relation. Nếu dung lượng có thể tái sử dụng trong tương lai, không nhất thiết phải rewrite. Nếu cần trả dung lượng về filesystem và bloat được đo xác nhận, lập kế hoạch rewrite/repack phù hợp với giới hạn khóa, dung lượng và thời gian bảo trì.

### Bước 6 — Xác nhận

Đo lại latency truy vấn, buffer reads, throughput ghi, dead tuple trend, vacuum duration, WAL, replication lag và dung lượng volume. Giữ thay đổi khi workload ổn định hơn và chính sách retention không tạo backlog mới.

## 13. Những nhầm lẫn thường gặp

- **“DELETE giải phóng dung lượng ngay.”** DELETE tạo trạng thái xóa theo MVCC; vacuum mới xử lý phiên bản cũ khi không còn snapshot cần.
- **“VACUUM luôn làm file nhỏ lại.”** Vacuum thường chủ yếu làm không gian tái sử dụng bên trong relation; chỉ có thể truncate phần trang trống ở cuối khi đủ điều kiện.
- **“VACUUM FULL giống VACUUM.”** VACUUM FULL viết lại relation, cần `ACCESS EXCLUSIVE` và dung lượng bổ sung.
- **“ANALYZE dọn dead tuples.”** ANALYZE cập nhật thống kê planner, không thay thế vacuum.
- **“n_dead_tup là số đếm chính xác.”** Đây là ước lượng thống kê; cần xem xu hướng và đo sâu khi cần.
- **“Tăng autovacuum worker luôn tốt.”** Worker nhiều hơn có thể tăng I/O và CPU cạnh tranh với ứng dụng.
- **“Vacuum không chạy được thì cứ tăng cost limit.”** Transaction horizon cũ có thể ngăn xóa tuple; cần xử lý snapshot/replication trước.
- **“Tắt autovacuum sẽ giảm tải lâu dài.”** Dead tuples, bloat và nguy cơ XID wraparound sẽ tăng.
- **“Bảng lớn chắc chắn bị bloat.”** Kích thước lớn có thể phản ánh dữ liệu sống, payload rộng hoặc retention hợp lệ.
- **“Reindex thu gọn cả bảng.”** Reindex chỉ xây dựng lại index; heap table cần phương án riêng.
- **“Xóa dữ liệu cũ bằng một transaction lớn là nhanh nhất.”** Transaction lớn tạo nhiều dead tuples, WAL, lock và áp lực vacuum; batch hoặc partition có thể phù hợp hơn.
- **“Replication slot không ảnh hưởng vacuum.”** Slot và standby feedback có thể giữ horizon, ngăn dọn tuple cũ và giữ WAL.
- **“Có thể chạy VACUUM FULL khi đĩa gần đầy để lấy chỗ.”** Rewrite cần thêm dung lượng trước khi file cũ được giải phóng.

## 14. Checklist bảo trì dead tuples và bloat

- [ ] Đã xác định bảng/index có dead tuple hoặc tăng trưởng bất thường bằng số liệu.
- [ ] Đã phân biệt dead tuples, free space nội bộ và dung lượng filesystem.
- [ ] Đã đo xu hướng `n_live_tup`, `n_dead_tup`, kích thước heap/index và tốc độ ghi.
- [ ] Đã kiểm tra lần vacuum/analyze gần nhất và tiến độ autovacuum.
- [ ] Đã kiểm tra transaction dài, `idle in transaction`, prepared transaction và replication horizon.
- [ ] Đã xem XID age và tình trạng anti-wraparound.
- [ ] Đã kiểm tra query churn, update không đổi giá trị, HOT update và fillfactor.
- [ ] Đã chọn đúng công cụ: VACUUM, ANALYZE, VACUUM FULL, REINDEX hoặc partition retention.
- [ ] Đã tính I/O, WAL, dung lượng peak, thời gian khóa và ảnh hưởng replication.
- [ ] Đã tránh transaction xóa quá lớn; có batch/retention phù hợp.
- [ ] Đã kiểm tra backup và khả năng restore trước thao tác rewrite.
- [ ] Đã đo lại latency, buffer reads, throughput, dead tuple trend và dung lượng sau bảo trì.

## Kết luận

Dead tuples phát sinh tự nhiên từ cơ chế MVCC khi cập nhật và xóa dữ liệu. Vacuum xử lý các phiên bản không còn cần thiết, làm không gian có thể tái sử dụng và duy trì visibility map; analyze cập nhật thống kê cho planner. Autovacuum cần theo kịp tốc độ thay đổi, nhưng transaction dài, replication slot hoặc standby feedback có thể giữ horizon và ngăn dọn dữ liệu cũ.

Bloat cần được xác nhận bằng xu hướng kích thước và phép đo phù hợp. Vacuum thường không compact toàn bảng hoặc bảo đảm trả dung lượng về filesystem; `VACUUM FULL`, `CLUSTER` và reindex có chi phí khóa, I/O và dung lượng riêng. Hãy ưu tiên giảm churn, giữ transaction ngắn, điều chỉnh autovacuum theo từng bảng và dùng retention/partition hợp lý. Chỉ thực hiện rewrite khi lợi ích đã được đo và đã chuẩn bị đủ dung lượng, cửa sổ bảo trì cùng phương án phục hồi.
