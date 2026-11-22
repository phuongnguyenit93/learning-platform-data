# Khóa hàng, khóa bảng và cách xác định điểm tranh chấp

## Mục tiêu bài học

Khi nhiều giao dịch cùng truy cập dữ liệu, hệ quản trị phải phối hợp để bảo vệ tính nhất quán. Một giao dịch có thể phải chờ vì giao dịch khác đang giữ khóa trên một dòng, một bảng hoặc một tài nguyên dùng chung. Nếu không xác định đúng phạm vi khóa và phiên đang giữ khóa, việc tối ưu SQL hay tăng tài nguyên có thể không giải quyết được nguyên nhân gây chậm.

Trong chương **Giao dịch và tranh chấp** của module **DATABASE_PERFORMANCE**, bài học này trình bày cách hoạt động của khóa hàng và khóa bảng, cách nhận diện điểm tranh chấp và cách điều tra quan hệ chặn giữa các phiên. Module **DATABASE_PERFORMANCE** rèn phương pháp tối ưu hiệu năng cơ sở dữ liệu dựa trên đo đạc tải, kế hoạch thực thi, thống kê và cơ chế truy cập dữ liệu; nội dung bao gồm thiết kế chỉ mục, cải thiện SQL, nhận diện tranh chấp giao dịch, nút thắt I/O, bộ nhớ và kiểm chứng kết quả sau điều chỉnh. Vì vậy, việc xử lý lock contention cần kết hợp dữ liệu phiên, loại khóa, thời gian transaction, kế hoạch thực thi và phép đo tải trước/sau.

Sau bài học, bạn có thể:

- Phân biệt khóa hàng, khóa bảng và các loại chờ không xuất phát từ khóa.
- Giải thích vì sao một câu lệnh đọc thông thường có thể không chặn cập nhật trong hệ quản trị dùng MVCC.
- Nhận diện các điểm nóng như một dòng được cập nhật liên tục, một nhóm khóa thường xuyên tranh chấp hoặc DDL giữ khóa bảng.
- Dựng quan hệ waiter/blocker và tìm phiên chặn gốc.
- Dùng các view hệ thống của PostgreSQL để xem phiên đang chờ, loại khóa, transaction age và câu SQL liên quan.
- Chọn cách giảm tranh chấp bằng cách rút ngắn transaction, chuẩn hóa thứ tự lấy khóa, chia tải hoặc dùng cơ chế chờ có giới hạn.
- Kiểm chứng kết quả bằng thời gian chờ khóa, p95/p99, thông lượng, deadlock và tài nguyên hệ thống.

## 1. Lock contention là gì?

**Lock contention** (tranh chấp khóa) xảy ra khi một giao dịch cần lấy khóa nhưng khóa đó đang được một giao dịch khác giữ ở chế độ xung đột. Giao dịch yêu cầu khóa phải chờ cho đến khi khóa được giải phóng, yêu cầu bị timeout hoặc hệ quản trị phát hiện deadlock và hủy một giao dịch để phá vòng chờ.

Ví dụ, hai khách hàng cùng mua sản phẩm cuối cùng trong kho. Cả hai giao dịch đều muốn giảm `available` từ 1 xuống 0. Nếu không có cơ chế phối hợp, hệ thống có thể bán vượt tồn kho. Khóa giúp tuần tự hóa các thay đổi xung đột để bảo đảm quy tắc nghiệp vụ.

Tranh chấp khóa là chi phí cần thiết khi các giao dịch thực sự xung đột. Mục tiêu tối ưu là giảm thời gian giữ khóa, giảm số giao dịch cùng tranh một tài nguyên và thu hẹp phạm vi công việc trong transaction, đồng thời giữ nguyên tính đúng đắn.

### 1.1. Phân biệt ba khái niệm

| Khái niệm | Ý nghĩa | Dấu hiệu thường gặp |
|---|---|---|
| Lock | Cơ chế điều phối quyền truy cập tài nguyên | Một phiên giữ khóa; phiên khác yêu cầu khóa xung đột |
| Blocking | Một phiên phải chờ phiên khác nhả tài nguyên | Có quan hệ waiter và blocker; wait event thuộc nhóm Lock |
| Deadlock | Các phiên tạo thành vòng chờ không thể tự tiến triển | Hệ quản trị phát hiện vòng phụ thuộc và thường hủy một transaction |

Một blocking chain có thể được giải quyết khi phiên chặn hoàn tất. Deadlock là một trường hợp đặc biệt có chu trình. Không phải mọi lock wait kéo dài đều là deadlock, và không phải mọi truy vấn chậm đều do khóa.

### 1.2. Lock wait khác với các loại wait khác

Một phiên có thể chậm vì chờ I/O, ghi log, cấp phát bộ nhớ, đồng bộ nội bộ, mạng hoặc ứng dụng nhận kết quả. Trong PostgreSQL, `pg_stat_activity.wait_event_type` giúp phân loại. Giá trị `Lock` cho biết backend đang chờ một khóa do lock manager quản lý; các nhóm như `IO`, `LWLock`, `BufferPin`, `Client` hoặc `IPC` phản ánh cơ chế chờ khác.

Không nên kết luận lock contention chỉ từ thời gian truy vấn dài. Hãy xác nhận trạng thái phiên, `wait_event_type`, `wait_event` và quan hệ blocker. Nếu phiên đang dùng CPU hoặc chờ I/O, biện pháp xử lý sẽ khác.

## 2. Khóa hàng (row-level lock)

Khóa hàng bảo vệ các dòng dữ liệu cụ thể khi giao dịch đọc có khóa hoặc thay đổi dữ liệu. Nó cho phép các giao dịch không xung đột trên những dòng khác nhau tiếp tục đồng thời, thay vì khóa toàn bộ bảng cho mọi thao tác.

Ví dụ hai giao dịch cập nhật hai tài khoản khác nhau thường có thể tiến hành song song:

```sql
-- Transaction A
BEGIN;
UPDATE accounts
SET balance = balance - 100
WHERE account_id = 101;
COMMIT;

-- Transaction B
BEGIN;
UPDATE accounts
SET balance = balance + 50
WHERE account_id = 202;
COMMIT;
```

Nếu hai giao dịch không đụng tới cùng dòng hoặc tài nguyên xung đột khác, chúng thường không phải chờ khóa hàng của nhau. Tuy nhiên, cả hai vẫn lấy khóa bảng ở mức phù hợp cho lệnh `UPDATE`, và có thể tranh chấp tài nguyên khác như index page, buffer, WAL hoặc CPU.

### 2.1. Khóa hàng trong PostgreSQL và MVCC

PostgreSQL sử dụng MVCC để cho các transaction đọc những phiên bản dữ liệu phù hợp với snapshot của chúng. Một câu `SELECT` thông thường không lấy row lock và thường không bị chặn bởi `UPDATE` đang sửa dòng; ngược lại, `UPDATE` cũng không phải chờ mọi `SELECT` thông thường kết thúc.

Điều này không có nghĩa PostgreSQL không có khóa khi đọc. `SELECT` thông thường lấy table-level `ACCESS SHARE` lock để bảo vệ quan hệ khỏi một số thao tác DDL xung đột. Khóa này tương thích với các thao tác DML thông thường, nhưng xung đột với `ACCESS EXCLUSIVE` như nhiều dạng `ALTER TABLE` hoặc `TRUNCATE`.

Các thao tác như `UPDATE`, `DELETE`, `SELECT FOR UPDATE` và `SELECT FOR SHARE` có thể tạo row-level lock. Khóa hàng thường được giữ đến khi transaction kết thúc bằng `COMMIT` hoặc `ROLLBACK`, không chỉ đến khi câu SQL hoàn tất. Vì vậy, một câu `UPDATE` chạy rất nhanh nhưng transaction vẫn mở có thể tiếp tục giữ khóa và chặn phiên khác.

### 2.2. Các mức khóa hàng trong PostgreSQL

PostgreSQL cung cấp bốn mức row lock thường gặp:

| Mệnh đề | Mục đích | Tính xung đột khái quát |
|---|---|---|
| `FOR KEY SHARE` | Ngăn transaction khác xóa dòng hoặc thay đổi khóa được tham chiếu theo cách xung đột | Nhẹ nhất; vẫn có thể tương thích với một số cập nhật không đổi khóa |
| `FOR SHARE` | Bảo vệ dòng khỏi cập nhật hoặc xóa xung đột trong thời gian transaction | Xung đột với các mức cập nhật mạnh hơn như `NO KEY UPDATE` và `UPDATE` |
| `FOR NO KEY UPDATE` | Khóa dòng để cập nhật không làm thay đổi khóa được dùng trong foreign key | Xung đột với `SHARE`, `NO KEY UPDATE` và `UPDATE` |
| `FOR UPDATE` | Khóa mạnh để cập nhật hoặc xóa dòng | Xung đột với cả bốn mức row lock |

Ví dụ lấy một dòng để cập nhật:

```sql
BEGIN;

SELECT account_id, balance
FROM accounts
WHERE account_id = 101
FOR UPDATE;

-- Kiểm tra và thực hiện các thay đổi liên quan.

UPDATE accounts
SET balance = balance - 100
WHERE account_id = 101;

COMMIT;
```

Phiên khác muốn lấy row lock xung đột trên cùng dòng phải chờ transaction này kết thúc. Chỉ dùng `FOR UPDATE` khi cần bảo vệ dòng khỏi thay đổi đồng thời; khóa trước nhiều dòng hơn mức cần thiết sẽ làm giảm khả năng đồng thời.

### 2.3. Cập nhật nguyên tử để giảm cửa sổ tranh chấp

Một mẫu dễ phát sinh race condition là đọc giá trị, tính ở ứng dụng rồi ghi lại:

```sql
SELECT available
FROM inventory
WHERE sku = 'SKU-01';

-- Ứng dụng tính available - 1 rồi gửi UPDATE riêng.
```

Giữa `SELECT` và `UPDATE`, transaction khác có thể thay đổi tồn kho. Có thể gộp điều kiện và phép cập nhật vào một câu lệnh nguyên tử:

```sql
UPDATE inventory
SET available = available - 1
WHERE sku = 'SKU-01'
  AND available >= 1
RETURNING available;
```

Ứng dụng kiểm tra số dòng được trả về. Nếu không có dòng, sản phẩm không còn đủ hàng hoặc SKU không tồn tại. Cách này giảm round trip và tránh cửa sổ đọc-rồi-ghi ở tầng ứng dụng. Các yêu cầu cùng cập nhật một SKU vẫn phải tuần tự hóa trên dòng đó; nếu SKU trở thành điểm nóng, cần xem thêm cách phân bổ tồn kho hoặc mô hình reservation.

### 2.4. Dòng nóng (hot row)

Một dòng nóng là dòng được nhiều transaction cùng cập nhật hoặc khóa trong thời gian ngắn. Ví dụ:

- Một bản ghi đếm lượt xem cho trang phổ biến.
- Một dòng số dư tài khoản nhận nhiều giao dịch.
- Một dòng tồn kho của sản phẩm bán chạy.
- Một bản ghi tổng hợp doanh thu theo ngày và khu vực.
- Một hàng đợi dùng một dòng làm bộ đếm hoặc điểm điều phối.

Nếu nhiều phiên cùng chờ một dòng, tăng số connection hoặc CPU không làm tăng thông lượng của thao tác bị tuần tự hóa. Cần giảm thời gian giữ khóa, phân tán cập nhật, gom batch hoặc thay đổi mô hình dữ liệu.

## 3. Khóa bảng (table-level lock)

Khóa bảng bảo vệ quan hệ ở phạm vi toàn bảng. Nó có thể được lấy tự động bởi DML/DDL hoặc yêu cầu tường minh bằng lệnh `LOCK TABLE`. Khóa bảng không nhất thiết khóa mọi dòng theo cùng một cách; mục tiêu là kiểm soát những loại thao tác nào có thể chạy đồng thời trên quan hệ.

Trong PostgreSQL, các mức table lock phổ biến gồm:

| Mức khóa | Ví dụ sử dụng | Điểm cần chú ý |
|---|---|---|
| `ACCESS SHARE` | `SELECT` thông thường | Tương thích với hầu hết khóa bảng; xung đột với `ACCESS EXCLUSIVE` |
| `ROW SHARE` | `SELECT ... FOR UPDATE/SHARE` | Tên có chữ ROW nhưng đây vẫn là table-level lock |
| `ROW EXCLUSIVE` | `INSERT`, `UPDATE`, `DELETE`, `MERGE` | DML thông thường có thể chạy đồng thời với nhau; xung đột với một số khóa DDL/bảo trì |
| `SHARE UPDATE EXCLUSIVE` | Nhiều thao tác `VACUUM` thường, `ANALYZE`, một số thao tác index concurrently | Có thể xung đột với một tiến trình bảo trì cùng loại và các khóa mạnh hơn |
| `SHARE` | Một số thao tác tạo index không concurrently | Có thể chặn DML lấy `ROW EXCLUSIVE` |
| `SHARE ROW EXCLUSIVE` | Một số thao tác DDL hoặc khóa tường minh | Xung đột rộng hơn `SHARE` |
| `EXCLUSIVE` | Một số thao tác khóa tường minh | Chặn thêm các thao tác lấy `ROW SHARE` |
| `ACCESS EXCLUSIVE` | `TRUNCATE`, nhiều dạng `ALTER TABLE`, `DROP TABLE` | Mức mạnh nhất; xung đột với mọi table lock khác, kể cả `SELECT` thông thường |

Tên khóa và mức thực tế phụ thuộc câu lệnh, biến thể DDL và phiên bản. Bảng trên nêu các mẫu phổ biến để định hướng điều tra; khi xử lý sự cố cần xem `pg_locks` và tài liệu của phiên bản đang chạy.

### 3.1. Vì sao SELECT có thể bị chặn bởi DDL?

Một truy vấn `SELECT` thông thường lấy `ACCESS SHARE`. Một thao tác cần `ACCESS EXCLUSIVE` phải đợi các `ACCESS SHARE` đang tồn tại kết thúc; sau khi `ACCESS EXCLUSIVE` được cấp, các truy vấn mới cần `ACCESS SHARE` cũng phải đợi.

Ví dụ, `TRUNCATE` lấy khóa mạnh trên bảng:

```sql
BEGIN;
TRUNCATE TABLE staging_events;
-- Transaction vẫn mở, ACCESS EXCLUSIVE còn được giữ.
```

Nếu transaction chưa commit, truy vấn đọc bảng có thể bị chặn. DDL hoặc maintenance chạy trong transaction dài có thể tạo hàng đợi lớn dù bản thân lệnh DDL đã hoàn tất.

### 3.2. Khóa bảng không đồng nghĩa với khóa toàn bộ dữ liệu theo mọi nghĩa

`ROW EXCLUSIVE` là tên một table-level lock mà DML thường lấy; nó không có nghĩa câu `UPDATE` khóa độc quyền toàn bộ bảng. Row lock bảo vệ các tuple cụ thể, còn table lock bảo vệ quan hệ trước những thao tác có mức xung đột phù hợp.

Khi điều tra, cần ghi rõ cả hai phạm vi. Một phiên `UPDATE` có thể đang giữ `ROW EXCLUSIVE` trên bảng và row lock trên một dòng; phiên khác có thể chờ row lock của dòng đó hoặc chờ table lock mạnh hơn từ DDL.

## 4. Khác biệt giữa các hệ quản trị

Tên khóa, cách lưu thông tin khóa và chính sách quản lý khác nhau giữa PostgreSQL, MySQL InnoDB và SQL Server. Không nên lấy một quy tắc của hệ quản trị này để suy luận cho hệ khác.

| Hệ quản trị | Cách quản lý thường gặp | Điểm cần lưu ý khi điều tra |
|---|---|---|
| PostgreSQL | MVCC kết hợp row-level lock và table-level lock; row lock thường được lưu cùng tuple metadata | `pg_locks` không hiển thị mọi row lock đã cấp như một mục riêng; phiên chờ row lock thường chờ transaction ID của blocker |
| MySQL InnoDB | Record lock, gap lock và next-key lock trên index; metadata lock cho đối tượng | Isolation level, index và predicate ảnh hưởng phạm vi khóa; xem `performance_schema` và `data_locks`/`data_lock_waits` theo phiên bản |
| SQL Server | Có key, row, page và table locks cùng cơ chế escalation | Có thể tự động nâng nhiều khóa cấp thấp thành khóa phạm vi lớn hơn; xem lock escalation và DMV/Extended Events |

PostgreSQL không tự động nâng hàng loạt row lock thành table lock theo cơ chế lock escalation như SQL Server. Dù vậy, transaction khóa rất nhiều dòng vẫn có thể tiêu thụ tài nguyên và làm các phiên khác chờ. InnoDB có thể khóa khoảng khóa (gap/next-key) để bảo vệ predicate tùy isolation level và access path; vì vậy một câu lệnh có thể chặn thao tác trên khoảng index chứ không chỉ một dòng đã tồn tại.

## 5. Các điểm tranh chấp thường gặp

### 5.1. Một dòng được cập nhật liên tục

Nhiều transaction cùng tăng/giảm một bộ đếm hoặc số dư. Dấu hiệu là nhiều waiter có cùng blocker hoặc cùng tài nguyên, thời gian chờ tập trung ở một nhóm câu SQL.

Hướng xử lý:

- Rút ngắn phần việc trong transaction sau khi lấy khóa.
- Gộp nhiều lần tăng/giảm thành batch khi nghiệp vụ cho phép.
- Chia bộ đếm thành nhiều bucket rồi cộng khi đọc.
- Dùng bảng sự kiện append-only và tổng hợp theo lô.
- Đánh giá lại khóa phân vùng hoặc mô hình reservation.

### 5.2. Transaction giữ khóa quá lâu

Một ứng dụng có thể mở transaction, cập nhật một dòng rồi gọi HTTP service, chờ người dùng hoặc thực hiện tính toán lâu trước khi commit. Trong thời gian đó, khóa vẫn được giữ.

Ví dụ không nên giữ transaction qua lời gọi mạng:

```text
BEGIN
  UPDATE inventory ...
  gọi dịch vụ vận chuyển (chờ vài giây)
  INSERT shipment ...
COMMIT
```

Hãy xem có thể thiết kế lại ranh giới transaction, ghi ý định nghiệp vụ vào outbox hoặc dùng quy trình bất đồng bộ hay không. Không được bỏ tính nguyên tử của các thay đổi cần nhất quán; cần xác định rõ trạng thái trung gian và cách xử lý lỗi.

### 5.3. Nhiều transaction lấy khóa theo thứ tự khác nhau

Giả sử giao dịch chuyển tiền cần khóa hai tài khoản:

```text
Transaction A: khóa account 101 -> chờ account 202
Transaction B: khóa account 202 -> chờ account 101
```

Hai giao dịch tạo thành vòng chờ. Nếu mọi luồng nghiệp vụ khóa tài khoản theo thứ tự ID tăng dần, nguy cơ deadlock giảm:

```text
Transaction A: khóa 101 -> khóa 202
Transaction B: khóa 101 -> khóa 202
```

Một thứ tự khóa nhất quán không loại bỏ mọi deadlock, nhưng loại bỏ một nguồn vòng chờ phổ biến. Cần áp dụng cùng quy tắc ở tất cả đường code và kiểm tra các bảng/tài nguyên khác mà transaction cùng truy cập.

### 5.4. DDL, migration và maintenance

`ALTER TABLE`, `TRUNCATE`, `DROP`, một số thao tác tạo index hoặc migration có thể yêu cầu table lock mạnh. Nếu chạy trong giờ cao điểm hoặc transaction dài, chúng có thể chặn đọc/ghi hoặc bị các transaction cũ giữ lại.

Trước khi chạy migration:

- Xác định mức lock cần thiết và thời gian dự kiến.
- Kiểm tra transaction đang mở và workload truy cập bảng.
- Chọn phương án ít chặn hơn nếu hệ quản trị hỗ trợ, ví dụ tạo index concurrently trong PostgreSQL.
- Đặt giới hạn chờ phù hợp và có kế hoạch hủy/retry.
- Theo dõi hàng đợi lock trong suốt quá trình.

### 5.5. Khóa do foreign key, unique constraint và index

Ràng buộc toàn vẹn có thể làm phát sinh truy cập và khóa bổ sung. Ví dụ, khi chèn dòng con có foreign key, engine cần xác minh dòng cha tồn tại; khi cập nhật unique key, engine phải bảo đảm không có giá trị trùng. Tranh chấp có thể xuất hiện trên dòng cha, index entry hoặc khóa liên quan, không chỉ ở câu SQL nhìn thấy trong ứng dụng.

Nếu nhiều transaction cùng chèn dòng con tham chiếu một dòng cha hoặc cùng ghi một unique key, hãy xem loại tài nguyên chờ, ràng buộc và kế hoạch. Đừng vô hiệu hóa foreign key hoặc unique constraint chỉ để giảm chờ; cần giữ nguyên quy tắc dữ liệu và tìm cách phân tán workload hoặc rút ngắn transaction.

## 6. Cách xác định điểm tranh chấp trong PostgreSQL

PostgreSQL cung cấp `pg_stat_activity`, `pg_locks` và hàm `pg_blocking_pids()` để điều tra phiên đang chờ và phiên chặn.

### 6.1. Tìm phiên đang chờ và blocker trực tiếp

Truy vấn sau liệt kê quan hệ chặn trực tiếp tại thời điểm chạy:

```sql
SELECT
    blocked.pid AS blocked_pid,
    blocker.pid AS blocker_pid,
    blocked.usename AS blocked_user,
    blocker.usename AS blocker_user,
    blocked.application_name AS blocked_application,
    blocker.application_name AS blocker_application,
    blocked.wait_event_type,
    blocked.wait_event,
    blocked.state AS blocked_state,
    blocker.state AS blocker_state,
    blocked.xact_start AS blocked_xact_start,
    blocker.xact_start AS blocker_xact_start,
    clock_timestamp() - blocked.query_start AS blocked_query_age,
    clock_timestamp() - blocker.xact_start AS blocker_xact_age,
    blocked.query AS blocked_sql,
    blocker.query AS blocker_current_or_last_sql
FROM pg_stat_activity AS blocked
CROSS JOIN LATERAL unnest(pg_blocking_pids(blocked.pid)) AS p(blocker_pid)
JOIN pg_stat_activity AS blocker
  ON blocker.pid = p.blocker_pid
WHERE blocked.wait_event_type = 'Lock'
  AND blocked.pid <> pg_backend_pid()
ORDER BY blocker.xact_start NULLS LAST, blocked.query_start;
```

Cách đọc:

- `blocked_pid` là phiên đang chờ; `blocker_pid` là phiên đang chặn trực tiếp.
- `wait_event` cho biết loại tài nguyên khóa đang chờ theo cách PostgreSQL phân loại.
- `blocked_query_age` là tuổi câu truy vấn tính từ `query_start`, **không phải** thời gian chờ khóa chính xác.
- `blocker_xact_age` là tuổi transaction của blocker nếu có `xact_start`; transaction lâu là tín hiệu cần điều tra khi nó đang giữ khóa.
- `blocker_current_or_last_sql` có thể là câu lệnh gần nhất nếu blocker đang `idle in transaction`, không nhất thiết là một câu SQL đang chạy.

Đây là ảnh chụp tại thời điểm truy vấn. Phiên có thể kết thúc hoặc đổi trạng thái ngay sau đó. Muốn biết diễn biến, hãy lấy mẫu lặp lại hoặc dùng hệ thống giám sát lưu lịch sử.

### 6.2. Xem các khóa đang chờ và khóa bảng

`pg_locks` cho biết các lock request và trạng thái đã được cấp hay chưa. Ví dụ:

```sql
SELECT
    l.pid,
    a.usename,
    a.application_name,
    a.state,
    l.locktype,
    CASE
        WHEN l.relation IS NOT NULL THEN l.relation::regclass::text
        ELSE NULL
    END AS relation_name,
    l.mode,
    l.granted,
    l.transactionid,
    l.virtualtransaction,
    a.wait_event_type,
    a.wait_event,
    a.query
FROM pg_locks AS l
LEFT JOIN pg_stat_activity AS a
  ON a.pid = l.pid
WHERE l.granted = false
   OR (l.locktype = 'relation' AND l.granted = true)
ORDER BY l.granted, l.pid;
```

Các cột quan trọng:

- `locktype`: loại tài nguyên được khóa, ví dụ `relation`, `transactionid`, `tuple` hoặc `advisory`.
- `relation_name`: quan hệ liên quan nếu khóa gắn với một relation.
- `mode`: mức khóa được yêu cầu hoặc giữ.
- `granted`: `true` nếu đã được cấp, `false` nếu đang chờ.
- `transactionid`: có thể xuất hiện khi phiên chờ transaction khác kết thúc.

**Lưu ý đặc biệt về row lock trong PostgreSQL:** các row lock đã cấp thường được lưu trong tuple header trên heap và không xuất hiện như một mục riêng cho từng dòng trong `pg_locks`. Khi một phiên chờ row lock, nó thường xuất hiện đang chờ khóa transaction ID của phiên giữ dòng. Dùng `pg_blocking_pids()` để xác định blocker trực tiếp; không kết luận rằng không có row lock chỉ vì không thấy `locktype = 'tuple'`.

### 6.3. Tìm transaction mở lâu

```sql
SELECT
    pid,
    usename,
    application_name,
    client_addr,
    state,
    xact_start,
    clock_timestamp() - xact_start AS transaction_age,
    wait_event_type,
    wait_event,
    left(query, 500) AS current_or_last_query
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
  AND pid <> pg_backend_pid()
ORDER BY xact_start;
```

Transaction mở lâu không tự động là lỗi. Nhưng nếu phiên đó đang chặn nhiều waiter, đang `idle in transaction`, hoặc giữ snapshot lâu gây cản trở vacuum, nó cần được điều tra. Xác định ứng dụng, host, request hoặc job sở hữu phiên trước khi can thiệp.

### 6.4. Dựng blocking chain và tìm root blocker

Truy vấn `pg_blocking_pids()` ở trên cho biết blocker trực tiếp. Để tìm gốc của chuỗi:

1. Lấy một `blocked_pid` đang chờ.
2. Xem `blocker_pid` của nó.
3. Kiểm tra PID đó có xuất hiện như `blocked_pid` trong một quan hệ chờ khác không.
4. Nếu có, lần tiếp về blocker của phiên đó.
5. Tiếp tục cho tới phiên không bị chặn trong chuỗi quan sát được.

Phiên cuối cùng này thường là **root blocker** của chuỗi hiện tại. Một root blocker có thể chặn nhiều nhánh waiter. Nó không nhất thiết dùng CPU cao; có thể đang nhàn rỗi nhưng transaction chưa commit.

Không nhầm root blocker với nguyên nhân nghiệp vụ sâu nhất. Ví dụ, phiên A là root blocker trực tiếp nhưng transaction của nó kéo dài vì ứng dụng đang chờ dịch vụ ngoài. Muốn xử lý bền vững phải truy tìm cả luồng ứng dụng và ranh giới transaction.

## 7. Quy trình điều tra một sự cố lock contention

### Bước 1 — Xác định phạm vi và thời điểm

Ghi lại thời điểm sự cố, endpoint hoặc job bị ảnh hưởng, nhóm người dùng, mức tải và thay đổi triển khai gần đó. Đối chiếu p50/p95/p99, thông lượng, timeout, số kết nối và tỷ lệ lỗi.

### Bước 2 — Xác nhận phiên đang chờ khóa

Lấy mẫu `pg_stat_activity`, lọc `wait_event_type = 'Lock'`, ghi lại PID, user, application, state, query, `xact_start` và `wait_event`. Phân biệt với phiên đang chờ I/O hoặc đang chạy CPU.

### Bước 3 — Tìm blocker trực tiếp

Dùng `pg_blocking_pids()` và `pg_locks` để xác định PID chặn, loại tài nguyên, quan hệ và mức khóa. Lưu ảnh chụp theo thời gian nếu sự cố kéo dài.

### Bước 4 — Dựng chuỗi và đánh giá phạm vi

Lần theo các quan hệ waiter/blocker để tìm root blocker. Đếm số waiter trực tiếp và gián tiếp, xác định bảng hoặc nhóm khóa liên quan. Nếu nhiều phiên cùng chờ một dòng hoặc một nhóm tài nguyên, ưu tiên điều tra điểm nóng.

### Bước 5 — Kiểm tra transaction của blocker

Xem transaction age, trạng thái `active` hay `idle in transaction`, câu SQL hiện tại/gần nhất, ứng dụng và host. Tìm các lời gọi mạng, thao tác người dùng, batch hoặc công việc xử lý dài nằm trong transaction.

### Bước 6 — Kiểm tra câu SQL và access path

Nếu blocker đang thực thi SQL, xem `EXPLAIN (ANALYZE, BUFFERS)` trong môi trường phù hợp. Một câu `UPDATE` có thể quét nhiều dòng do thiếu index hoặc điều kiện không chọn lọc, giữ khóa trên nhiều tuple lâu hơn dự kiến. Kiểm tra estimated/actual rows, index condition, filter và số buffer.

### Bước 7 — Phân biệt blocking với deadlock

Kiểm tra log deadlock và thông báo lỗi. Blocking đơn hướng có thể được giải quyết khi blocker commit/rollback. Deadlock có chu trình phụ thuộc và hệ quản trị thường hủy một transaction. Với deadlock, thu thập thông tin về các khóa và thứ tự truy cập của tất cả transaction liên quan.

### Bước 8 — Chọn biện pháp theo nguyên nhân

Rút ngắn transaction, sửa thứ tự lấy khóa, giảm phạm vi dòng bị cập nhật, bổ sung index sau khi kiểm tra kế hoạch, chia batch, phân tán dòng nóng hoặc điều chỉnh lịch DDL. Không tự động hủy phiên chỉ vì transaction age lớn.

### Bước 9 — Đo lại và xác nhận

So sánh lock wait count/time, số waiter, độ dài blocking chain, deadlock, p95/p99, throughput, CPU, I/O và lỗi sau điều chỉnh. Chạy tải đại diện có cùng mức đồng thời để xác nhận thay đổi giải quyết nguyên nhân và không tạo điểm nghẽn mới.

## 8. Biện pháp giảm tranh chấp khóa

### 8.1. Rút ngắn transaction

Chỉ giữ transaction mở trong khoảng cần thiết để bảo đảm tính nguyên tử. Không chờ người dùng, gọi dịch vụ ngoài hoặc thực hiện tính toán dài khi đang giữ khóa nếu có thể thiết kế lại.

### 8.2. Khóa theo thứ tự nhất quán

Khi transaction cần cập nhật nhiều dòng hoặc nhiều bảng, truy cập theo cùng một thứ tự ở mọi luồng. Ví dụ, khóa các tài khoản theo `account_id` tăng dần để giảm nguy cơ deadlock. Nếu cần khóa nhiều dòng, có thể lấy chúng theo thứ tự xác định và giữ transaction ngắn.

### 8.3. Chỉ khóa những dòng cần thiết

Điều kiện `WHERE` phải đủ chọn lọc và có access path phù hợp. Một câu lệnh cập nhật vô tình tác động nhiều dòng có thể mở rộng phạm vi khóa và làm tăng thời gian xử lý. Trước khi thêm index, kiểm tra kế hoạch và chi phí duy trì index trên đường ghi.

### 8.4. Dùng NOWAIT hoặc SKIP LOCKED đúng mục đích

PostgreSQL hỗ trợ các tùy chọn khóa:

```sql
-- Thất bại ngay nếu dòng cần khóa đang bị transaction khác giữ.
SELECT job_id, payload
FROM jobs
WHERE job_id = 1001
FOR UPDATE NOWAIT;
```

`NOWAIT` phù hợp khi ứng dụng muốn trả lỗi hoặc thử lại thay vì chờ. Nó không làm khóa biến mất; ứng dụng phải xử lý lỗi lock-not-available có kiểm soát.

Với hàng đợi công việc, nhiều worker có thể dùng `SKIP LOCKED` để lấy các job chưa bị worker khác khóa:

```sql
BEGIN;

SELECT job_id, payload
FROM jobs
WHERE status = 'READY'
ORDER BY job_id
FOR UPDATE SKIP LOCKED
LIMIT 10;

-- Đánh dấu các job đã nhận trong cùng transaction.

COMMIT;
```

`SKIP LOCKED` tránh chờ các dòng đang bị khóa, nhưng cố ý trả về một góc nhìn không đầy đủ: dòng bị khóa bị bỏ qua dù vẫn thỏa điều kiện. Đây là lựa chọn phù hợp cho hàng đợi có nhiều worker, không phù hợp khi người dùng cần danh sách đầy đủ hoặc thứ tự tuyệt đối.

### 8.5. Chia tải ở điểm nóng

Nếu một dòng đếm lượt xem hoặc tổng hợp doanh thu bị cập nhật liên tục, có thể chia thành nhiều bucket theo shard key, worker hoặc khoảng thời gian rồi cộng khi đọc. Cách này giảm tranh chấp ghi nhưng làm đường đọc phức tạp hơn. Phải đo cả hai phía.

### 8.6. Quản lý DDL và maintenance

Lên lịch migration vào thời điểm phù hợp, chọn phương thức ít chặn hơn khi có thể, giới hạn thời gian chờ lock và theo dõi các transaction lâu. Trong PostgreSQL, `CREATE INDEX CONCURRENTLY` giảm một số dạng chặn DML so với `CREATE INDEX` thông thường nhưng vẫn có chi phí và các giai đoạn chờ; nó không chạy bên trong transaction block.

## 9. Timeout và xử lý chờ có kiểm soát trong PostgreSQL

Các cấu hình timeout có mục đích khác nhau:

| Cấu hình | Tác dụng |
|---|---|
| `lock_timeout` | Giới hạn thời gian một lệnh chờ để lấy khóa; hết hạn thì lệnh bị hủy |
| `statement_timeout` | Giới hạn tổng thời gian thực thi câu lệnh, bao gồm thời gian chờ khóa |
| `deadlock_timeout` | Thời gian chờ trước khi PostgreSQL chạy kiểm tra deadlock; không phải timeout để hủy transaction bị chặn |

Có thể đặt `lock_timeout` cục bộ cho một transaction:

```sql
BEGIN;
SET LOCAL lock_timeout = '2s';

UPDATE inventory
SET available = available - 1
WHERE sku = 'SKU-01'
  AND available >= 1;

COMMIT;
```

Nếu không lấy được khóa trong thời gian cho phép, câu lệnh bị hủy và transaction cần được xử lý đúng theo trạng thái lỗi (thường phải rollback trước khi tiếp tục). Timeout giúp giới hạn thời gian chờ và bảo vệ hệ thống khỏi hàng đợi kéo dài; nó không thay thế việc tìm nguyên nhân tranh chấp.

Đặt timeout quá ngắn có thể tạo lỗi giả trong giờ cao điểm và làm ứng dụng retry liên tục, khiến tải tăng thêm. Retry cần có giới hạn, backoff và tính idempotent. `deadlock_timeout` chỉ điều khiển thời điểm kiểm tra deadlock; tăng nó không phải cách sửa deadlock.

## 10. Ví dụ thực tế: chuyển tiền giữa hai tài khoản

Một thao tác chuyển tiền cần giảm số dư tài khoản nguồn và tăng số dư tài khoản đích. Nếu hai request chạy đồng thời với thứ tự khóa ngược nhau, deadlock có thể xảy ra.

### 10.1. Thứ tự không nhất quán

```text
Transaction A: BEGIN
  khóa tài khoản 101
  chờ khóa tài khoản 202

Transaction B: BEGIN
  khóa tài khoản 202
  chờ khóa tài khoản 101
```

Hai transaction tạo vòng chờ. Hệ quản trị phát hiện deadlock và hủy một transaction. Ứng dụng cần nhận biết lỗi deadlock và có thể retry toàn bộ transaction theo chính sách có giới hạn.

### 10.2. Thứ tự khóa ổn định

Một cách giảm nguy cơ là luôn khóa hai tài khoản theo ID tăng dần, bất kể tài khoản nào là nguồn hay đích:

```sql
BEGIN;

SELECT account_id, balance
FROM accounts
WHERE account_id IN (101, 202)
ORDER BY account_id
FOR UPDATE;

-- Ứng dụng kiểm tra số dư và xác định số tiền chuyển.

UPDATE accounts
SET balance = CASE account_id
    WHEN 101 THEN balance - 100
    WHEN 202 THEN balance + 100
END
WHERE account_id IN (101, 202);

COMMIT;
```

Ví dụ minh họa giả định tài khoản 101 là nguồn và 202 là đích. Ứng dụng phải kiểm tra cả hai dòng tồn tại và số dư nguồn đủ trước khi cập nhật. Trong triển khai thật, cần xử lý trường hợp hai ID giống nhau, tiền tệ, giới hạn số dư, ghi sổ kép và kiểm tra kết quả. Thứ tự khóa nhất quán giảm một dạng deadlock nhưng không loại bỏ mọi vòng chờ từ các tài nguyên khác.

## 11. Những sai lầm thường gặp khi xử lý lock contention

- **Chỉ nhìn câu SQL đang chờ:** phiên đó thường là nạn nhân; cần tìm phiên đang giữ khóa.
- **Cho rằng query age là lock wait duration:** `query_start` chỉ cho biết câu truy vấn bắt đầu khi nào; cần lấy mẫu wait event hoặc số liệu lịch sử để ước lượng thời gian chờ.
- **Cho rằng mọi SELECT đều không thể bị chặn:** SELECT thông thường trong PostgreSQL có thể bị chặn bởi `ACCESS EXCLUSIVE` table lock.
- **Nhầm `ROW EXCLUSIVE` là khóa toàn bộ dòng:** đây là table-level lock mode mà DML thường lấy; row lock là cơ chế riêng trên tuple.
- **Tìm row lock bằng cách chỉ lọc `locktype = 'tuple'`:** row lock đã cấp trong PostgreSQL thường không xuất hiện như mục riêng trong `pg_locks`; waiter có thể đang chờ `transactionid`.
- **Tăng connection để giải quyết hàng đợi khóa:** thêm phiên có thể làm nhiều transaction cùng tranh một dòng và tăng tải.
- **Tăng timeout để che sự cố:** hàng đợi dài hơn có thể giữ kết nối và transaction lâu hơn.
- **Hủy blocker mà chưa xem rollback:** rollback có thể kéo dài, sinh I/O và ảnh hưởng nghiệp vụ; cần xác định chủ sở hữu và tác động.
- **Thêm index mà không xem kế hoạch:** index có thể giảm số dòng bị quét nhưng cũng tăng chi phí ghi; cần xác định câu SQL nào đang giữ khóa lâu.
- **Dùng SKIP LOCKED cho truy vấn cần đầy đủ dữ liệu:** tùy chọn này cố ý bỏ qua dòng đang khóa.
- **Cho rằng PostgreSQL tự escalation row lock thành table lock như SQL Server:** hai hệ quản trị có cơ chế khác nhau; phải đọc đúng tài liệu engine.

## 12. Checklist điều tra và giảm tranh chấp

- [ ] Đã xác định thời điểm, workload và người dùng bị ảnh hưởng.
- [ ] Đã xác nhận phiên thực sự chờ `Lock`, không nhầm với I/O, CPU hoặc client wait.
- [ ] Đã thu thập PID, application, query, wait event và transaction age.
- [ ] Đã xác định blocker trực tiếp bằng công cụ của hệ quản trị.
- [ ] Đã lần theo blocking chain để tìm root blocker và phạm vi ảnh hưởng.
- [ ] Đã phân biệt row lock, table lock, metadata lock và các tài nguyên khác.
- [ ] Đã kiểm tra transaction `idle in transaction`, lời gọi bên ngoài và công việc dài trong transaction.
- [ ] Đã xem kế hoạch thực thi, index và số dòng thực tế của câu SQL giữ khóa.
- [ ] Đã kiểm tra thứ tự truy cập tài nguyên và log deadlock.
- [ ] Đã chọn biện pháp phù hợp: rút ngắn transaction, thứ tự khóa ổn định, chia tải, batch hoặc timeout.
- [ ] Đã đánh giá tác động rollback trước khi kết thúc phiên blocker.
- [ ] Đã đo lại lock wait, deadlock, p95/p99, throughput, CPU và I/O sau điều chỉnh.

## Kết luận

Khóa hàng cho phép các giao dịch không xung đột tiếp tục đồng thời, còn khóa bảng điều phối các thao tác ở phạm vi quan hệ. Trong PostgreSQL, MVCC giúp `SELECT` thông thường và DML ít chặn nhau hơn, nhưng row lock vẫn được giữ tới khi transaction kết thúc và các table lock mạnh vẫn có thể chặn đọc/ghi. Cách hiển thị khóa cũng khác giữa PostgreSQL, InnoDB và SQL Server.

Khi xảy ra tranh chấp, hãy xác nhận wait event, tìm waiter và blocker, lần theo chuỗi tới root blocker, rồi kiểm tra transaction age, câu SQL và access path. Biện pháp bền vững thường là rút ngắn transaction, lấy khóa theo thứ tự nhất quán, giảm số dòng bị tác động hoặc phân tán điểm nóng. Chỉ kết luận sau khi đo lại thời gian chờ, deadlock, độ trễ và thông lượng dưới tải đại diện.
