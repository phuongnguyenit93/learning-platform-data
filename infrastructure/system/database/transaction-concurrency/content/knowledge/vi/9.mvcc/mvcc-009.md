# Thu gom phiên bản cũ và tác động của giao dịch kéo dài

MVCC (Multi-Version Concurrency Control) cho phép nhiều giao dịch cùng làm việc trên một dữ liệu bằng cách lưu giữ nhiều phiên bản của một hàng. Khi một giao dịch cập nhật hoặc xóa hàng, hệ quản trị cơ sở dữ liệu (DBMS) có thể tạo phiên bản mới và giữ phiên bản cũ để những giao dịch đang đọc theo snapshot phù hợp vẫn nhìn thấy dữ liệu nhất quán.

Những phiên bản cũ không thể được giữ mãi. DBMS cần một cơ chế xác định thời điểm chúng không còn cần thiết và thu gom chúng để tái sử dụng bộ nhớ hoặc dung lượng lưu trữ. Trong PostgreSQL, công việc này chủ yếu do `VACUUM` và autovacuum thực hiện; InnoDB của MySQL dùng purge để dọn undo history; SQL Server và Oracle có cách quản lý row version hoặc undo riêng.

Một giao dịch kéo dài có thể giữ snapshot cũ trong thời gian lâu. Khi đó, phiên bản mà giao dịch khác đã thay thế hoặc xóa vẫn có thể cần thiết cho giao dịch đang đọc. Bộ thu gom phải giữ lại phiên bản đó, khiến hàng đợi dọn dẹp tích tụ. Hậu quả có thể là bảng và chỉ mục phình to, undo hoặc version store tăng, truy vấn chậm, áp lực I/O và trong một số hệ thống là nguy cơ cạn dung lượng.

## 1. Vì sao MVCC phải giữ nhiều phiên bản?

Với khóa đọc truyền thống, một thao tác đọc có thể phải chờ thao tác ghi đang giữ khóa xung đột. MVCC giải quyết nhiều trường hợp đọc đồng thời bằng cách cho truy vấn đọc một phiên bản phù hợp với snapshot của nó.

Giả sử hàng `Product(7)` có giá trị `price = 100`:

1. T1 bắt đầu đọc và có snapshot nhìn thấy giá trị 100.
2. T2 cập nhật giá thành 120 rồi commit.
3. T3 bắt đầu sau khi T2 commit nên nhìn thấy giá trị 120.
4. T1 vẫn cần đọc theo snapshot cũ nên phải nhìn thấy phiên bản có giá trị 100.

Nếu DBMS xóa ngay phiên bản 100 sau khi T2 commit, T1 không thể trả về kết quả nhất quán theo snapshot ban đầu. Vì vậy, DBMS giữ các phiên bản cần thiết cho những snapshot còn hoạt động.

```text
Thời gian ------------------------------------------------------------>

T1:  bắt đầu snapshot S1 --------------------------- đọc phiên bản cũ
T2:                cập nhật 100 -> 120 -- COMMIT
T3:                                      snapshot S2 -- đọc phiên bản mới

Phiên bản dữ liệu:
  V1: price=100  [cần cho snapshot S1]
  V2: price=120  [được tạo bởi T2, thấy trong snapshot S2]
```

Đây là ý tưởng chung của MVCC. Cách lưu phiên bản và cách xác định phiên bản nào còn nhìn thấy được phụ thuộc DBMS và isolation level. Không phải mọi hệ thống đều lưu các phiên bản trong cùng một cấu trúc hoặc dùng cùng một thuật ngữ.

## 2. Snapshot và quy tắc nhìn thấy phiên bản

Snapshot mô tả trạng thái giao dịch mà một truy vấn được phép quan sát. Khi DBMS đánh giá một phiên bản, nó xem xét thời điểm tạo, thời điểm xóa hoặc thay thế phiên bản và trạng thái commit của các giao dịch liên quan.

Một snapshot cũ có thể nhìn thấy phiên bản mà snapshot mới không còn nhìn thấy. Ngược lại, snapshot mới thường nhìn thấy phiên bản mới đã commit và bỏ qua phiên bản đã bị thay thế.

Ví dụ khái quát:

| Phiên bản | Thời điểm tạo | Thời điểm bị thay thế | Snapshot cũ S1 | Snapshot mới S2 |
|---|---|---|---|---|
| V1: `price=100` | Trước S1 | T2 cập nhật | Có thể nhìn thấy | Không còn nhìn thấy |
| V2: `price=120` | T2 cập nhật | Chưa bị thay thế | Không nhìn thấy nếu T2 xảy ra sau S1 | Có thể nhìn thấy sau khi T2 commit |

Trong thực tế, DBMS không chỉ dựa vào một mốc thời gian đơn giản. Nó cần biết giao dịch nào đã commit, snapshot nào còn có thể được sử dụng, và các quy tắc isolation đang áp dụng. Một giao dịch ở mức Repeatable Read hoặc Snapshot Isolation thường cần giữ cùng snapshot qua nhiều câu lệnh; ở Read Committed, nhiều hệ thống tạo snapshot mới cho từng câu lệnh.

Điều này giải thích vì sao thời gian chạy của một câu lệnh và thời gian sống của snapshot có thể khác nhau. Một truy vấn rất nhanh nhưng nằm trong transaction đã mở lâu ở mức isolation giữ snapshot có thể tiếp tục ngăn thu gom phiên bản cũ sau khi câu lệnh kết thúc.

## 3. Phiên bản cũ được thu gom khi nào?

Một phiên bản chỉ có thể được thu gom khi không còn snapshot hoặc cơ chế nào cần nó để phục vụ việc đọc nhất quán hay phục hồi. DBMS phải xác định một **horizon** (ranh giới an toàn) cho việc dọn dẹp: các phiên bản cũ hơn ranh giới này có thể không còn cần thiết, còn phiên bản mới hơn có thể vẫn phải được giữ.

Quy trình khái quát gồm:

1. Giao dịch ghi tạo phiên bản mới hoặc đánh dấu phiên bản cũ đã bị xóa/thay thế.
2. DBMS giữ các phiên bản cũ trong khi còn snapshot có thể cần chúng.
3. Khi các snapshot liên quan kết thúc hoặc tiến lên, horizon thu gom có thể tiến về phía trước.
4. Bộ thu gom kiểm tra các phiên bản đã hết khả năng hiển thị.
5. Phiên bản không còn cần thiết được loại bỏ, đánh dấu có thể tái sử dụng hoặc giải phóng khỏi vùng lưu trữ theo cơ chế của DBMS.

Không phải cứ một phiên bản đã bị thay thế là có thể xóa ngay sau commit. Commit xác nhận thay đổi của giao dịch ghi; nó không đồng nghĩa với việc tất cả giao dịch đọc cũ đã kết thúc.

### 3.1. Horizon bị ghim

Nếu có một giao dịch giữ snapshot cũ, horizon dọn dẹp có thể bị ghim (pinned). Các phiên bản được tạo hoặc thay thế sau mốc snapshot đó có thể chưa được thu gom, ngay cả khi nhiều giao dịch mới đã hoàn thành.

```text
Thời gian ------------------------------------------------------------>

T1: BEGIN / lấy snapshot cũ ------------------------------- COMMIT
T2:      UPDATE R1 -> R2 -- COMMIT
T3:                   UPDATE R2 -> R3 -- COMMIT
T4:                                UPDATE R3 -> R4 -- COMMIT

Snapshot của T1 vẫn có thể cần phiên bản R1.
Các phiên bản trung gian R2, R3 cũng có thể phải được giữ
cho những snapshot khác còn hoạt động.
```

Khi T1 kết thúc, horizon có thể tiến lên và cho phép bộ thu gom xử lý thêm các phiên bản đã chết. Nếu có một giao dịch khác hoặc một cơ chế giữ snapshot cũ hơn, việc thu gom vẫn có thể bị trì hoãn.

## 4. Thu gom phiên bản cũ trong PostgreSQL

PostgreSQL triển khai MVCC bằng các tuple trong heap. Một tuple thường có metadata giao dịch như `xmin` (transaction ID tạo tuple) và `xmax` (transaction ID xóa hoặc thay thế tuple, nếu có). Khi một hàng được cập nhật, PostgreSQL thường tạo tuple mới và đánh dấu tuple cũ đã bị thay thế; nhiều phiên bản có thể cùng tồn tại trong heap cho đến khi an toàn để dọn dẹp.

`VACUUM` quét bảng để xác định tuple không còn cần thiết theo visibility horizon. Các tuple chết có thể được loại khỏi cấu trúc có thể nhìn thấy và không gian của chúng được đánh dấu để tái sử dụng trong chính relation. Autovacuum tự động lên lịch vacuum và analyze dựa trên các ngưỡng, thống kê và điều kiện vận hành.

Ví dụ:

```sql
UPDATE Product
SET price = 120
WHERE product_id = 7;
```

Ở mức khái quát, PostgreSQL tạo tuple mang giá trị mới và tuple cũ trở thành ứng viên dọn dẹp khi không còn snapshot cần nó. Nếu một transaction cũ vẫn giữ snapshot phù hợp, `VACUUM` không thể loại tuple đó an toàn.

### 4.1. VACUUM và việc trả dung lượng cho hệ điều hành

`VACUUM` thông thường chủ yếu làm cho không gian của tuple chết có thể được tái sử dụng bởi các thao tác ghi trong cùng bảng hoặc relation. Nó không nhất thiết làm kích thước file trên đĩa giảm ngay.

Phân biệt ba khái niệm:

- **Tuple được dọn:** phiên bản chết được loại khỏi tập dữ liệu cần duy trì.
- **Không gian được tái sử dụng:** chỗ trống bên trong relation có thể chứa tuple mới.
- **Dung lượng trả lại cho hệ điều hành:** file vật lý giảm kích thước. Việc này có điều kiện riêng; `VACUUM` thường không thu nhỏ toàn bộ file.

`VACUUM FULL` có thể viết lại bảng để thu nhỏ file và trả dung lượng, nhưng cần khóa mạnh trong thời gian thực hiện và tạo thêm công việc I/O, dung lượng tạm. Đây không phải giải pháp thường xuyên cho một transaction đang ghim horizon. Nếu phiên bản vẫn còn cần thiết, viết lại bảng cũng không thể đơn giản xóa nó mà phá vỡ tính nhất quán.

### 4.2. Autovacuum không thể vượt qua snapshot cũ

Autovacuum có thể chạy thường xuyên và vẫn không dọn được các tuple bị giữ lại bởi transaction hoặc cơ chế khác đang giữ horizon. Khi nguyên nhân ghim được giải phóng, những lần vacuum tiếp theo mới có thể thu gom phần lớn lượng tuple chết đó.

Vì vậy, chỉ tăng tần suất autovacuum không giải quyết được transaction giữ snapshot quá lâu. Cần tìm và xử lý nguồn giữ horizon, đồng thời bảo đảm vacuum có đủ tài nguyên để bắt kịp lượng cập nhật và xóa.

## 5. Giao dịch kéo dài giữ lại phiên bản như thế nào?

Một transaction kéo dài có thể làm chậm thu gom nếu nó giữ snapshot cũ. Các tình huống phổ biến gồm:

- Ứng dụng mở transaction, chạy câu lệnh đọc rồi chờ người dùng nhập dữ liệu trước khi commit.
- Transaction thực hiện nhiều công việc bên ngoài cơ sở dữ liệu giữa các câu lệnh.
- Một truy vấn báo cáo chạy rất lâu và giữ snapshot trong suốt thời gian đọc.
- Transaction ở mức Repeatable Read hoặc Serializable giữ snapshot cho nhiều câu lệnh nhưng không kết thúc.
- Một session bị bỏ quên ở trạng thái `idle in transaction` sau khi đã thực hiện câu lệnh lấy snapshot.

Ví dụ về transaction mở quá lâu:

```sql
BEGIN;

SELECT *
FROM Product
WHERE category_id = 12;

-- Ứng dụng giữ transaction mở trong lúc xử lý kết quả,
-- gọi dịch vụ khác hoặc chờ người dùng.

-- COMMIT bị trì hoãn rất lâu.
```

Trong khoảng thời gian đó, những cập nhật ở session khác vẫn có thể commit. Nhưng nếu snapshot của transaction đầu còn cần các tuple cũ, PostgreSQL phải giữ chúng lại. Nhiều transaction khác có thể tạo thêm tuple chết trong khi autovacuum không thể đi qua horizon bị ghim.

### 5.1. Transaction age và snapshot age không hoàn toàn giống nhau

Transaction mở lâu là tín hiệu cần điều tra, nhưng thời gian từ `BEGIN` đến hiện tại không phải lúc nào cũng đồng nhất với thời gian giữ snapshot. Cách lấy snapshot phụ thuộc isolation level, câu lệnh đã chạy và DBMS. Ví dụ, trong PostgreSQL ở Read Committed, mỗi câu lệnh thường có snapshot riêng; một transaction `idle in transaction` chưa chắc luôn ghim cùng loại snapshot như transaction Repeatable Read đã thực hiện truy vấn.

Do đó, khi chẩn đoán PostgreSQL, nên xem thêm `backend_xmin`, `xact_start`, trạng thái session và isolation level thay vì chỉ sắp xếp theo thời điểm `BEGIN`. Các cơ chế khác như replication slot cũng có thể giữ horizon dù session người dùng không có transaction đọc đang chạy.

## 6. Tác động của giao dịch kéo dài

### 6.1. Table bloat và index bloat

Khi tuple chết chưa thể dọn, bảng tiếp tục chứa nhiều phiên bản không còn được snapshot mới nhìn thấy. Các trang dữ liệu có thể chứa ít tuple hữu ích hơn, khiến DBMS phải đọc nhiều trang hơn để tìm dữ liệu cần thiết. Chỉ mục cũng có thể giữ các mục liên quan đến tuple chưa được thu gom, tùy loại chỉ mục và cơ chế vacuum.

Hệ quả thường gặp:

- Relation và index tăng kích thước.
- Cache chứa ít dữ liệu hữu ích hơn vì nhiều trang phải được giữ trong bộ nhớ.
- Sequential scan hoặc index scan có thể phải xử lý nhiều trang và mục chết hơn.
- Backup, restore, replication và thao tác bảo trì có thể tốn thêm dung lượng hoặc thời gian.
- Các thao tác ghi cần thêm I/O để tạo tuple và quản lý trang.

Hiện tượng này thường được gọi là **bloat**. Không phải mọi kích thước lớn đều là bloat: bảng có thể tăng hợp lệ vì dữ liệu thật sự tăng. Cần so sánh số tuple sống, số tuple chết, lịch sử tăng trưởng và kích thước relation trước khi kết luận.

### 6.2. Autovacuum làm việc nhiều nhưng không tiến triển

Autovacuum có thể liên tục quét bảng có nhiều tuple chết, nhưng horizon cũ khiến nó chưa thể loại bỏ các tuple đó. Các lần quét lặp lại tiêu tốn CPU, I/O và làm tăng cạnh tranh tài nguyên. Sau khi transaction giữ horizon kết thúc, vacuum mới có thể thu gom lượng tồn đọng.

Một transaction kéo dài không nhất thiết làm autovacuum dừng hoàn toàn. Vacuum vẫn có thể xử lý phần dữ liệu an toàn và những công việc khác. Vấn đề là các tuple nằm sau ranh giới an toàn không thể bị loại bỏ.

### 6.3. Áp lực dung lượng và nguy cơ transaction ID wraparound

PostgreSQL sử dụng transaction ID có không gian hữu hạn và cần freeze các tuple đủ cũ để tránh diễn giải sai tính hiển thị khi transaction ID quay vòng (wraparound). Một horizon quá cũ có thể cản trở vacuum freeze tiến lên.

Nếu tình trạng kéo dài, tuổi transaction ID của database có thể tiến gần ngưỡng bảo vệ. PostgreSQL có cơ chế autovacuum chống wraparound với mức ưu tiên cao và có thể từ chối một số thao tác ghi khi nguy cơ quá lớn. Đây là lý do vận hành nghiêm trọng hơn chuyện bảng chỉ phình to.

Không nên chờ đến khi có cảnh báo wraparound mới xử lý transaction lâu ngày. Cần giám sát tuổi `datfrozenxid`, transaction giữ `xmin` và hoạt động vacuum định kỳ.

### 6.4. Tác động đến WAL và replication

Trong PostgreSQL, transaction giữ snapshot có thể trì hoãn vacuum qua `xmin`. Replication slot có thể giữ `xmin` hoặc `catalog_xmin` để bảo vệ dữ liệu cần cho replica hoặc logical decoding; slot cũng có thể giữ WAL thông qua vị trí restart LSN. Đây là các cơ chế liên quan nhưng khác nhau.

Một transaction đọc lâu không tự động có nghĩa WAL sẽ bị giữ lại vô hạn. WAL retention thường liên quan đến replication slot, archive, replica chậm hoặc cấu hình checkpoint. Khi điều tra dung lượng đĩa tăng, cần xác định đó là heap/index bloat, WAL đang được giữ, hay cả hai.

### 6.5. Tăng blocking và giảm khả năng bảo trì

MVCC thường cho phép reader và writer ít chặn nhau hơn, nhưng transaction kéo dài vẫn có thể giữ các loại lock thông thường. Ví dụ, transaction có thể giữ khóa bảng hoặc khóa hàng sau một câu lệnh ghi; một số thao tác DDL cần khóa mạnh hơn và phải chờ transaction cũ kết thúc.

Vì vậy, một session lâu ngày có thể đồng thời gây hai vấn đề: giữ snapshot làm chậm thu gom phiên bản, và giữ lock làm chặn thao tác khác. Đây là hai đường tác động riêng, cần kiểm tra cả snapshot horizon lẫn lock graph.

## 7. Những cơ chế giữ phiên bản cũ ngoài transaction ứng dụng

Khi điều tra vì sao phiên bản cũ không được thu gom, không nên chỉ tìm transaction của người dùng. Một số cơ chế nội bộ cũng cần lịch sử cũ.

### 7.1. Replication slot và logical decoding trong PostgreSQL

Replication slot giữ trạng thái cần thiết để replica hoặc consumer logical decoding không bỏ lỡ dữ liệu. Một slot có thể giữ `xmin` hoặc `catalog_xmin`, làm vacuum không thể thu gom một số tuple cũ. Nếu consumer dừng lâu, slot không được tiến lên và WAL có thể tích tụ.

Kiểm tra slot cần xem `active`, `restart_lsn`, `xmin`, `catalog_xmin` và lượng WAL đang bị giữ. Không nên xóa slot chỉ để giải phóng dung lượng khi chưa xác định replica hoặc consumer còn phụ thuộc vào nó; xóa slot có thể làm mất khả năng tiếp tục đồng bộ từ vị trí cũ.

### 7.2. Prepared transaction

Prepared transaction trong quy trình two-phase commit có thể giữ lock và trạng thái giao dịch cho đến khi được `COMMIT PREPARED` hoặc `ROLLBACK PREPARED`. Một prepared transaction bị bỏ quên có thể tiếp tục gây blocking và ảnh hưởng horizon tùy trạng thái, DBMS và snapshot liên quan.

### 7.3. Replica và snapshot đồng bộ

Một số cơ chế đồng bộ hoặc standby feedback có thể yêu cầu primary giữ lại tuple cũ để replica đang chạy truy vấn theo snapshot không gặp xung đột với vacuum. Cần xem cấu hình hot standby feedback, replication lag và thông tin slot khi primary không thể tiến horizon.

## 8. Cách PostgreSQL thể hiện vấn đề trong thực tế

Các truy vấn sau là ví dụ để quan sát PostgreSQL. Tên cột và khả năng truy vấn có thể thay đổi theo phiên bản; cần đối chiếu tài liệu của phiên bản đang chạy và quyền giám sát của tài khoản.

### 8.1. Tìm transaction lâu và session idle trong transaction

```sql
SELECT
    pid,
    usename,
    state,
    xact_start,
    query_start,
    backend_xmin,
    wait_event_type,
    wait_event,
    query
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start;
```

Các trường cần chú ý:

- `xact_start`: thời điểm transaction hiện tại bắt đầu.
- `state`: ví dụ `active` hoặc `idle in transaction`.
- `backend_xmin`: xmin mà backend đang giữ, nếu có; đây là manh mối quan trọng về horizon.
- `wait_event_type` và `wait_event`: cho biết session đang chờ sự kiện nào.
- `query`: câu lệnh gần nhất hoặc đang chạy, tùy trạng thái.

Không nên kết luận chỉ từ một dòng có `xact_start` cũ. Hãy xác định transaction đó có giữ snapshot cũ hay lock quan trọng không, ứng dụng nào sở hữu session, và có thể kết thúc an toàn hay không.

### 8.2. Xem lượng tuple chết và lịch vacuum

```sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup,
    last_vacuum,
    last_autovacuum,
    vacuum_count,
    autovacuum_count
FROM pg_stat_user_tables
ORDER BY n_dead_tup DESC;
```

`n_dead_tup` là số liệu ước lượng từ thống kê, không phải phép đếm chính xác tại mọi thời điểm. Dùng nó để tìm bảng đáng điều tra, sau đó đối chiếu kích thước relation, tần suất cập nhật/xóa, tiến độ vacuum và horizon.

### 8.3. Kiểm tra replication slot

```sql
SELECT
    slot_name,
    slot_type,
    active,
    restart_lsn,
    xmin,
    catalog_xmin
FROM pg_replication_slots;
```

Slot không hoạt động trong thời gian dài hoặc có vị trí WAL không tiến triển cần được điều tra cùng consumer tương ứng. `xmin` và `catalog_xmin` có thể giải thích vì sao vacuum phải giữ tuple hoặc catalog row cũ.

### 8.4. Theo dõi tuổi transaction ID

```sql
SELECT
    datname,
    age(datfrozenxid) AS xid_age
FROM pg_database
ORDER BY xid_age DESC;
```

Giá trị tuổi càng cao càng cần chú ý đến khả năng freeze và nguy cơ wraparound. Ngưỡng cảnh báo hoặc hành động phải dựa trên giới hạn của phiên bản PostgreSQL, cấu hình và tình trạng vận hành thực tế.

## 9. Cách điều tra một tình huống bloat do transaction kéo dài

Khi dung lượng bảng tăng hoặc autovacuum không dọn được tuple chết, có thể đi theo trình tự sau:

1. **Xác định relation tăng bất thường.** So sánh kích thước heap và index, số tuple sống/chết, tốc độ cập nhật và xóa.
2. **Kiểm tra vacuum.** Xem `last_autovacuum`, thống kê vacuum, log autovacuum và các lần vacuum bị hủy hoặc không hoàn tất.
3. **Tìm snapshot horizon cũ.** Kiểm tra `pg_stat_activity`, đặc biệt transaction lâu, `idle in transaction` và `backend_xmin`.
4. **Kiểm tra nguồn giữ horizon khác.** Xem replication slot, standby feedback, prepared transaction và các cơ chế đồng bộ đang hoạt động.
5. **Xác định nguyên nhân ở ứng dụng.** Tìm transaction mở quá lâu, truy vấn báo cáo kéo dài, luồng xử lý chờ mạng hoặc connection pool không trả session đúng cách.
6. **Giải phóng nguồn giữ snapshot an toàn.** Để ứng dụng commit/rollback đúng transaction hoặc xử lý slot/replica theo quy trình vận hành.
7. **Theo dõi vacuum bắt kịp.** Kiểm tra horizon có tiến lên không, số tuple chết có giảm không và autovacuum có đủ tài nguyên không.
8. **Chỉ cân nhắc rewrite/reindex khi có bằng chứng.** Bảo đảm đã xử lý nguyên nhân giữ phiên bản trước, ước lượng dung lượng tạm, khóa và thời gian bảo trì.

Hủy transaction đang chạy có thể làm mất công việc ứng dụng hoặc khiến request lỗi. Trước khi kết thúc một session, cần xác định chủ sở hữu, tác động và khả năng retry của công việc đó. Đặc biệt, không xóa replication slot hoặc prepared transaction khi chưa hiểu hệ thống phụ thuộc vào chúng.

## 10. Biện pháp thiết kế ứng dụng để tránh transaction kéo dài

Các biện pháp hiệu quả thường bắt đầu từ vòng đời transaction:

- Chỉ mở transaction ngay trước phần công việc cần tính nhất quán giao dịch.
- Commit hoặc rollback ngay khi các thao tác dữ liệu hoàn tất.
- Không chờ người dùng, gọi HTTP, gửi email hoặc thực hiện tác vụ chậm trong khi transaction đang mở.
- Với báo cáo lớn, cân nhắc chia nhỏ công việc, dùng bản sao đọc hoặc cơ chế snapshot/reporting phù hợp với yêu cầu nhất quán.
- Đặt timeout hợp lý cho transaction và câu lệnh; timeout giúp giới hạn thời gian tồn tại nhưng cần xử lý lỗi và rollback đúng cách.
- Theo dõi session `idle in transaction`, transaction age và thời gian giữ snapshot trong môi trường production.
- Kiểm tra connection pool để bảo đảm connection được trả về sau khi transaction kết thúc và không giữ trạng thái transaction ngoài ý muốn.

Không phải lúc nào cũng có thể rút ngắn một transaction lớn. Một quy trình nghiệp vụ có thể cần tính nguyên tử qua nhiều bước. Trong trường hợp đó, cần cân nhắc thiết kế lại thành các bước nhỏ có trạng thái bền vững, dùng khóa nghiệp vụ hoặc mô hình saga khi phù hợp. Chỉ chia transaction khi có thể bảo toàn các bất biến nghiệp vụ và xử lý được tình huống tiến trình dừng giữa chừng.

## 11. Cơ chế thu gom ở các DBMS khác

Nguyên tắc chung của MVCC là phiên bản hoặc undo information phải tồn tại đủ lâu để phục vụ snapshot còn hiệu lực. Tuy nhiên, không phải DBMS nào cũng có lệnh `VACUUM`.

| DBMS | Nơi lưu thông tin phiên bản | Cơ chế thu gom và tác động của snapshot cũ |
|---|---|---|
| PostgreSQL | Các tuple phiên bản trong heap; metadata giao dịch xác định khả năng hiển thị. | `VACUUM`/autovacuum loại tuple chết khi vượt qua visibility horizon. Snapshot cũ hoặc slot có thể ghim horizon, gây bloat. |
| MySQL InnoDB | Phiên bản cũ được tái dựng từ undo log và read view. | Purge dọn undo history khi không còn read view cần nó. Transaction giữ read view lâu làm history list length tăng và purge tụt lại. |
| SQL Server | Row version store, thường ở `tempdb`; với Accelerated Database Recovery có persistent version store trong user database. | Cleanup phụ thuộc phiên bản còn được transaction hoặc tính năng cần. Snapshot transaction kéo dài có thể làm version store tăng. |
| Oracle | Undo segments lưu thông tin cần cho consistent read và rollback. | Undo được tái sử dụng theo cơ chế quản lý undo và retention. Truy vấn cần undo đã bị ghi đè có thể gặp lỗi snapshot quá cũ như `ORA-01555`. |

Các chi tiết vận hành của từng sản phẩm khác nhau. Ví dụ, PostgreSQL giữ tuple chết trong heap cho đến khi vacuum xử lý; InnoDB purge undo history; Oracle quản lý undo retention; SQL Server quản lý row version store. Không nên áp dụng tên lệnh, ngưỡng hay cách đọc thống kê của một DBMS sang hệ khác.

### 11.1. MySQL InnoDB: purge và history list

InnoDB lưu thông tin undo để có thể dựng lại phiên bản phù hợp với read view. Khi transaction cũ giữ read view, purge thread không thể loại bỏ những undo record mà snapshot đó còn cần. `History list length` tăng có thể là dấu hiệu purge không theo kịp hoặc có read view cũ.

Transaction kéo dài ở Repeatable Read thường đáng chú ý vì read view có thể tồn tại qua nhiều câu lệnh. Cần theo dõi transaction đang mở, history list length và trạng thái purge; không tìm lệnh `VACUUM` trong InnoDB vì cơ chế thu gom khác PostgreSQL.

### 11.2. SQL Server: row version store

Khi bật các cơ chế dựa trên row version như Read Committed Snapshot Isolation (RCSI) hoặc Snapshot Isolation, SQL Server lưu phiên bản hàng trong version store. Transaction snapshot dài có thể khiến cleanup phải giữ các phiên bản cũ lâu hơn. Tùy cấu hình, version store có thể nằm trong `tempdb` hoặc Persistent Version Store khi dùng Accelerated Database Recovery.

Khi version store tăng, cần xem transaction snapshot lâu, phiên bản SQL Server, ADR, dung lượng `tempdb` và thống kê version store. Đây là vấn đề quản lý version store, không phải bloat heap do tuple chết theo cách PostgreSQL.

### 11.3. Oracle: undo retention và consistent read

Oracle dùng undo để tái tạo hình ảnh dữ liệu nhất quán tại thời điểm truy vấn. Nếu một truy vấn chạy lâu cần undo record nhưng vùng undo đã bị tái sử dụng, truy vấn có thể gặp `ORA-01555: snapshot too old`. `UNDO_RETENTION`, dung lượng undo tablespace và tải ghi đều ảnh hưởng khả năng giữ undo đủ lâu.

Thông điệp lỗi này phản ánh không đủ thông tin undo để đáp ứng consistent read, khác với việc PostgreSQL có nhiều tuple chết chờ vacuum. Cách điều tra phải theo công cụ undo của Oracle.

## 12. Phân biệt các triệu chứng thường bị nhầm lẫn

| Triệu chứng | Nguyên nhân có thể | Điều cần kiểm tra |
|---|---|---|
| Bảng PostgreSQL tăng kích thước dù số hàng sống ổn định | Tuple chết tích tụ, vacuum không thể vượt horizon hoặc không theo kịp | `n_dead_tup`, vacuum, `backend_xmin`, slot và kích thước heap/index |
| WAL PostgreSQL tăng nhanh | Replication slot giữ WAL, replica/archive chậm hoặc checkpoint/WAL workload | `restart_lsn`, WAL lag, archive và cấu hình retention |
| InnoDB history list length tăng | Purge không theo kịp, read view cũ hoặc tải cập nhật lớn | Transaction mở, read view, purge state và tốc độ ghi |
| SQL Server version store tăng | Snapshot transaction kéo dài hoặc cleanup không theo kịp | Snapshot transaction, version store, `tempdb` hoặc PVS |
| Oracle báo snapshot too old | Undo cần cho consistent read không còn sẵn | Undo retention, undo tablespace, thời gian truy vấn và tải ghi |
| DDL hoặc thao tác ghi bị chặn | Transaction giữ lock hoặc chờ khóa xung đột | Lock/wait graph, transaction age và câu lệnh đang giữ lock |

Một hệ thống có thể gặp nhiều triệu chứng cùng lúc, nhưng chúng không nhất thiết có cùng nguyên nhân. Ví dụ, PostgreSQL heap bloat và WAL retention đều làm tăng dung lượng đĩa nhưng cần hai hướng xử lý khác nhau.

## 13. Ví dụ diễn tiến: một snapshot cũ làm vacuum bị trì hoãn

Giả sử bảng `orders` có một triệu hàng. T1 mở transaction ở Repeatable Read và đọc dữ liệu. Sau đó ứng dụng giữ transaction mở để xử lý báo cáo. Trong lúc T1 còn sống, các giao dịch T2, T3 và T4 cập nhật hoặc xóa nhiều hàng trong bảng rồi commit.

```text
T1: BEGIN; SELECT ...; ------------------------------ COMMIT
             snapshot S1 được giữ lâu

T2:          UPDATE nhiều hàng; COMMIT
T3:                 UPDATE/DELETE; COMMIT
T4:                          UPDATE/DELETE; COMMIT

VACUUM:     quét bảng ---- gặp tuple vẫn cần cho S1 ---- không thể loại
```

Các giao dịch ghi đã commit, nhưng snapshot S1 của T1 vẫn có thể cần phiên bản trước cập nhật. Vacuum phải giữ những tuple đó. Nếu autovacuum tiếp tục chạy mà T1 không kết thúc, lượng tuple chết có thể tích tụ và relation tăng kích thước.

Khi ứng dụng hoàn tất và T1 commit, snapshot S1 được giải phóng. Horizon có thể tiến lên; các lần vacuum tiếp theo có thể dọn những tuple đã an toàn. Không gian sau đó có thể được tái sử dụng trong bảng. File vật lý không nhất thiết giảm ngay, nên kích thước relation có thể vẫn lớn dù số tuple chết đã giảm.

Nếu trong cùng thời gian một replication slot cũng giữ `xmin` cũ, kết thúc T1 vẫn chưa đủ để horizon tiến qua mốc của slot. Vì thế, điều tra cần tìm tất cả nguồn giữ horizon.

## 14. Những điểm cần ghi nhớ

- MVCC giữ nhiều phiên bản để các snapshot khác nhau đọc được trạng thái dữ liệu phù hợp.
- Phiên bản cũ chỉ được thu gom khi không còn snapshot hoặc cơ chế nào cần nó.
- Transaction kéo dài có thể giữ snapshot cũ, ghim visibility horizon và làm vacuum hoặc purge không dọn được lịch sử.
- Trong PostgreSQL, `VACUUM`/autovacuum dọn tuple chết khi an toàn; vacuum thông thường chủ yếu giúp không gian được tái sử dụng bên trong relation, không nhất thiết trả file cho hệ điều hành.
- Tuple chết tích tụ có thể gây table/index bloat, tăng I/O, áp lực cache và nguy cơ transaction ID wraparound nếu horizon bị giữ quá lâu.
- Replication slot, standby feedback và prepared transaction cũng có thể ảnh hưởng khả năng thu gom; không chỉ transaction ứng dụng mới giữ phiên bản cũ.
- Các DBMS dùng cơ chế khác nhau: PostgreSQL vacuum tuple, InnoDB purge undo, SQL Server cleanup version store, Oracle quản lý undo retention.
- Khi điều tra, cần phân biệt snapshot age, transaction age, lock duration, heap bloat và WAL/version-store retention.
- Thiết kế transaction ngắn, không chờ thao tác bên ngoài trong transaction và giám sát session lâu ngày giúp giảm nguy cơ tích tụ phiên bản cũ.
