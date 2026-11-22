# Ảnh hưởng của giao dịch chưa kết thúc đến dọn dẹp dữ liệu trong PostgreSQL

PostgreSQL dùng **MVCC (Multi-Version Concurrency Control)** để cho phép nhiều giao dịch đọc và ghi dữ liệu đồng thời mà không buộc mọi lượt đọc phải chờ lượt ghi. Đổi lại, khi một hàng bị cập nhật hoặc xóa, hệ quản trị thường chưa thể xóa ngay phiên bản cũ của hàng đó khỏi các trang dữ liệu. Phiên bản cũ có thể vẫn cần thiết cho một giao dịch đang đọc theo snapshot trước khi thay đổi được commit.

**`VACUUM` và autovacuum** có nhiệm vụ thu hồi khả năng tái sử dụng không gian do các phiên bản hàng hết cần thiết để lại, đồng thời thực hiện các công việc bảo trì khác. Nhưng một giao dịch còn mở quá lâu có thể giữ một **ranh giới hiển thị dữ liệu đủ cũ** khiến VACUUM chưa được phép loại bỏ những phiên bản hàng tưởng như “đã chết”. Hệ quả có thể là bảng và chỉ mục phình to (*bloat*), truy vấn đọc nhiều trang hơn, tăng I/O, tăng áp lực lưu trữ và làm công việc vacuum về sau nặng hơn.

Vấn đề này đặc biệt khó phát hiện khi ứng dụng không hề chạy một câu SQL phức tạp: một kết nối ở trạng thái **`idle in transaction`** có thể để transaction mở trong thời gian dài. Tuy nhiên, không phải cứ thấy session idle trong transaction là kết luận nó đang giữ snapshot cũ gây bloat. Cần phân biệt **thời gian transaction đã mở**, **snapshot/XID thực sự đang giữ chân cleanup**, và **những nguồn giữ horizon khác** như replication slot, standby feedback hoặc prepared transaction.

Bài này hướng dẫn từ cơ chế đến thí nghiệm hai kết nối, cách chẩn đoán qua PostgreSQL system views, lựa chọn xử lý an toàn trong sản xuất và bài tập thực hành.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích vì sao `UPDATE`/`DELETE` không tự động xóa ngay phiên bản hàng cũ.
2. Mô tả sự khác nhau giữa **phiên bản hàng còn cần cho snapshot**, **dead tuple đã có thể dọn**, và **không gian đã được tái sử dụng**.
3. Hiểu khái niệm **visibility horizon** và mối liên hệ của nó với transaction còn mở, `backend_xmin` và `backend_xid`.
4. Chứng minh qua thí nghiệm hai session rằng một snapshot `REPEATABLE READ` giữ lâu có thể hạn chế VACUUM dọn phiên bản hàng.
5. Phân biệt `READ COMMITTED`, `REPEATABLE READ`, `SERIALIZABLE` và những tình huống `idle in transaction`.
6. Theo dõi `pg_stat_activity`, `pg_stat_user_tables`, `pg_stat_progress_vacuum` và các nguồn giữ horizon khác.
7. Giải thích vai trò của autovacuum, freezing và nguy cơ transaction ID wraparound.
8. Phân tích tác động của standby feedback, replication slots và prepared transactions đến bảo trì dữ liệu.
9. Lập quy trình điều tra, giảm thiểu và phòng ngừa mà không hủy giao dịch quan trọng một cách tùy tiện.
10. Chọn giữa `VACUUM`, `VACUUM FULL` và những biện pháp vận hành khác theo đúng nguyên nhân.

## 2. MVCC lưu nhiều phiên bản hàng như thế nào?

Xét một hàng đơn hàng:

```text
id = 101, status = 'pending'
```

Transaction khác thay đổi trạng thái:

```sql
UPDATE orders
SET status = 'completed'
WHERE id = 101;
```

Trong PostgreSQL, về mặt logic hệ quản trị có thể tạo một **phiên bản tuple mới** cho hàng được cập nhật, trong khi phiên bản cũ chưa bị xóa vật lý ngay.

```text
Trước UPDATE:

  [tuple V1: id=101, status=pending]

Sau UPDATE, trước khi mọi snapshot cũ hết cần:

  [tuple V1: id=101, status=pending] ── phiên bản cũ
                  |
                  v
  [tuple V2: id=101, status=completed] ── phiên bản mới

Transaction dùng snapshot cũ: có thể thấy V1
Transaction dùng snapshot mới: có thể thấy V2
```

Đây là sơ đồ **khái niệm**. Nội bộ PostgreSQL dùng các trường transaction ID trong tuple header như `xmin` và `xmax`, thông tin commit/abort và cơ chế visibility để quyết định phiên bản nào visible. Các trường này không nên được suy diễn đơn giản là thời gian đồng hồ hoặc ID của bản ghi nghiệp vụ.

### 2.1. UPDATE và DELETE để lại gì?

- `INSERT` tạo phiên bản hàng mới.
- `UPDATE` thường tạo phiên bản hàng mới và đánh dấu phiên bản cũ không còn là phiên bản hiện hành khi update được xác nhận.
- `DELETE` đánh dấu phiên bản hàng không còn visible cho các snapshot đủ mới khi delete được xác nhận.
- `ROLLBACK` có thể khiến các phiên bản tạo bởi một transaction thất bại trở thành phiên bản không có giá trị sử dụng.

VACUUM làm sạch các phiên bản không còn cần thiết. Nhưng việc một transaction đã commit **không đồng nghĩa mọi tuple cũ của nó ngay lập tức an toàn để loại bỏ**.

### 2.2. Vì sao PostgreSQL không xóa ngay?

Giả sử:

```text
Session A                         Session B
---------                         ---------
BEGIN REPEATABLE READ
SELECT status -> 'pending'

                                  UPDATE status='completed'
                                  COMMIT

SELECT status -> 'pending'
COMMIT
```

Session A phải có khả năng tiếp tục đọc phiên bản phù hợp với snapshot của nó. Nếu B hoặc VACUUM xóa vật lý V1 ngay sau commit của B, A sẽ mất phiên bản mà nó còn quyền nhìn thấy.

Đây là đánh đổi cốt lõi của MVCC: **đọc nhất quán và tính đồng thời** đổi lấy nhu cầu lưu những phiên bản cũ đến lúc có thể loại bỏ an toàn.

### 2.3. “Dead tuple” có nhiều góc nhìn

Từ *dead tuple* trong vận hành thường chỉ những phiên bản hàng cũ không còn thuộc trạng thái hiện hành. Nhưng ở mức visibility:

- Một tuple có thể **không còn visible với snapshot mới** nhưng **vẫn cần** cho snapshot cũ.
- Một tuple có thể đã trở nên **removable** khi không còn snapshot/transaction nào cần nó.
- Một phiên bản do transaction rollback tạo ra có thể trở thành dead vì transaction tạo nó không commit.

Vì vậy đừng nghĩ `UPDATE` xong là tất cả old tuples của nó đều dọn được ngay. Và đừng coi thống kê `n_dead_tup` là phép đếm chính xác theo thời gian thực mọi tuple có thể xóa.

## 3. VACUUM thực hiện những công việc gì?

`VACUUM` là cơ chế bảo trì quan trọng của PostgreSQL. Tùy tình trạng bảng và phiên bản PostgreSQL, nó có thể:

- Xác định tuple đã chết và **đủ an toàn để dọn**, làm không gian trong bảng có thể tái sử dụng cho các thao tác tương lai.
- Dọn các index entries liên quan đến những tuple đã bị loại bỏ, theo các pha và tùy chọn index cleanup.
- Cập nhật visibility map, đánh dấu một số trang toàn-visible hoặc toàn-frozen khi các điều kiện thỏa mãn.
- Đóng góp vào việc **freeze transaction IDs** để tránh vấn đề wraparound.
- Cập nhật những thống kê bảo trì liên quan; khi chạy `VACUUM ANALYZE`, còn có bước phân tích số liệu cho planner.
- Trong một số trường hợp, cắt bớt các trang trống ở cuối tệp bảng nếu điều kiện cho phép.

### 3.1. Điều VACUUM thông thường không bảo đảm

**`VACUUM` thường không trả mọi byte bloat ngay lập tức về hệ điều hành.** Khi cleanup hoàn tất, không gian trong các trang dữ liệu thường trở thành không gian **tái sử dụng bên trong bảng**. Kích thước file có thể không giảm tương ứng.

Muốn thu nhỏ vật lý mạnh hơn có thể cần thao tác rewrite như `VACUUM FULL`, nhưng thao tác ấy đòi thêm không gian, thời gian và khóa mạnh. Chưa xác định nguyên nhân thì chạy `VACUUM FULL` có thể gây gián đoạn lớn mà không giải quyết long-running transaction đang hoạt động.

### 3.2. VACUUM ANALYZE

`VACUUM` và `ANALYZE` giải quyết những mục tiêu liên quan nhưng khác nhau:

- `VACUUM`: dọn phiên bản hàng, visibility information, freezing và bảo trì.
- `ANALYZE`: lấy mẫu/cập nhật thống kê planner như số hàng, phân bố cột để lập kế hoạch truy vấn.

`VACUUM (ANALYZE) schema.table` kết hợp cả hai. ANALYZE không thể “ép” VACUUM loại bỏ phiên bản đang còn cần cho một snapshot.

## 4. Ranh giới an toàn cho việc dọn dẹp (visibility horizon)

VACUUM không thể hỏi đơn giản: “transaction UPDATE đã commit chưa?” rồi xóa tất cả phiên bản cũ. Nó phải xét **những transaction/snapshot nào còn có thể cần nhìn thấy các phiên bản đó**.

Ta có thể hình dung một đường thời gian logic:

```text
       transaction/snapshot cũ                transaction mới
--------------------|------------------|------------------------->
                    A                  B
                    |                  |
              A còn mở snapshot   B UPDATE + COMMIT

Old version trước B:
  - Transaction mới sau B: không cần old version.
  - Snapshot cũ của A:     vẫn có thể cần old version.

VACUUM:
  - Không được dọn old version nếu A vẫn cần nó.
  - Có thể dọn khi không còn snapshot/transaction nào cần,
    đồng thời thỏa các điều kiện an toàn khác.
```

Ranh giới mà VACUUM phải tôn trọng thường được gọi bằng những tên như **oldest xmin**, **cleanup horizon**, hoặc visibility horizon, tùy bối cảnh/phiên bản và cấu trúc nội bộ. Khái niệm chung: PostgreSQL phải biết **mốc giao dịch cũ nhất còn liên quan tới tính hiển thị**.

### 4.1. Phân biệt transaction ID với thời gian thực

PostgreSQL gán **transaction IDs (XIDs)** khi cần để quản lý MVCC. XID không phải:

- Unix timestamp.
- Giá trị `now()`.
- Một ID toàn cục tăng mãi không bao giờ quay vòng.
- ID đơn hàng hay ID phiên kết nối.

Sơ đồ phía trên chỉ minh họa quan hệ cũ–mới, không được dùng làm phép tính chính xác giữa wall-clock và horizon. Trong thực tế cleanup horizon được xác định từ transaction/snapshot và nhiều nguồn khác, không chỉ từ số phút đã trôi.

### 4.2. backend_xmin và backend_xid

`pg_stat_activity` có những trường liên quan:

| Trường | Ý nghĩa thường dùng |
| --- | --- |
| `xact_start` | Thời điểm transaction của backend bắt đầu (nếu có). |
| `backend_xid` | Top-level XID của backend hiện tại, nếu có. |
| `backend_xmin` | Ranh giới `xmin` của snapshot backend đang giữ, khi có. |
| `state` | Trạng thái như `active`, `idle in transaction`, `idle in transaction (aborted)`. |
| `query_start` | Thời điểm query đang chạy bắt đầu khi active; với session idle có thể là query cuối. |
| `state_change` | Thời điểm trạng thái gần nhất thay đổi. |

**Chú ý:** `xact_start` có thể tồn tại khi `backend_xmin` là NULL. Một transaction đã mở từ lâu **không mặc nhiên có snapshot cũ bị giữ liên tục**. Ngược lại, một backend có `backend_xmin` cũ có thể giữ ranh giới liên quan đến việc cleanup ngay cả khi câu truy vấn mà người quản trị nhìn thấy không quá phức tạp.

### 4.3. XID tuổi cao và cleanup horizon

Hệ thống PostgreSQL có thể hiển thị `age(backend_xmin)` hoặc `age(backend_xid)` để giúp định hướng điều tra, nhưng phải hiểu:

- `age(xid)` là **độ tuổi logic của XID** so với hiện tại, không phải phút hay giờ.
- Một phiên giao dịch có tuổi `xact_start` dài chưa chắc có `backend_xmin` không NULL.
- `backend_xid` và `backend_xmin` biểu thị hai khía cạnh khác nhau; cần xem cả hai.
- Cleanup còn chịu ảnh hưởng từ standby feedback, replication slots và prepared transactions, không chỉ backend thông thường.

Chỉ nhìn bảng `pg_stat_activity` rồi tuyên bố “không có transaction cũ” là chưa đủ để kết luận không có nguồn nào giữ chân VACUUM.

## 5. Những gì một giao dịch mở lâu có thể gây ra

Tác động thường hình thành theo chuỗi:

```text
Ứng dụng giữ transaction/snapshot cũ
                     |
                     v
   VACUUM chưa dọn được mọi tuple đã lỗi thời
                     |
                     v
      Dead/old row versions tích tụ
                     |
             +-------+--------+
             |                |
             v                v
      Bảng/index tăng   VACUUM phải làm
       diện tích        thêm việc sau này
             |                |
             +-------+--------+
                     |
                     v
    Tăng I/O, cache pressure, chi phí truy vấn,
    dung lượng đĩa và nguy cơ ảnh hưởng ghi dữ liệu
```

Các tác động cụ thể:

1. **Bloat ở bảng:** nhiều phiên bản cũ còn nằm trong heap pages, bảng có thể mở rộng dù số hàng logic không tăng.
2. **Bloat ở index:** tùy dạng UPDATE và khả năng HOT, các phiên bản mới có thể kéo theo index entries; VACUUM cũng có thể bị hạn chế dọn những mục tương ứng.
3. **Đọc nhiều trang hơn:** sequential scan phải đi qua nhiều dữ liệu vật lý hơn; index scan có thể phải kiểm tra heap nhiều hơn.
4. **Tốn cache:** buffer pool bị chiếm bởi dữ liệu lỗi thời nhưng chưa thể thu hồi để tái sử dụng.
5. **Tăng I/O và WAL:** công việc UPDATE/DELETE tiếp tục tạo thay đổi; các đợt bảo trì sau này có thể nặng.
6. **Áp lực dung lượng:** file bảng/index có thể phình to, dẫn đến cảnh báo dung lượng hoặc hết disk.
7. **Nguy cơ vận hành liên quan wraparound:** transaction ID cũ có thể khiến tiến trình freeze không thể đi đủ xa như cần thiết, làm tăng áp lực anti-wraparound.

Không phải mọi long transaction đều tạo tất cả hậu quả trên. Ví dụ một transaction đọc ở `READ COMMITTED` mà không giữ snapshot cũ, trong khi workload gần như chỉ đọc, có thể chưa gây bloat đáng kể. Phải ghép **thông tin blocker + activity ghi + thống kê bảng + replication** để xác định nguyên nhân thật.

## 6. READ COMMITTED và REPEATABLE READ: sự khác biệt tinh tế

### 6.1. READ COMMITTED

Ở mức isolation mặc định `READ COMMITTED`, các statement thường dùng snapshot phù hợp tại thời điểm bắt đầu statement. Sau khi statement đọc hoàn tất, snapshot dùng riêng cho statement có thể được thả; câu statement sau có thể nhìn dữ liệu commit mới hơn.

Vì vậy, một session:

```sql
BEGIN ISOLATION LEVEL READ COMMITTED;
SELECT COUNT(*) FROM some_table;
-- Để session idle rất lâu.
```

không nhất thiết giữ **chính snapshot của SELECT cũ** xuyên suốt thời gian idle. Tuy nhiên, session vẫn đang mở transaction; nó có thể giữ khóa, có thể đã được gán XID do ghi dữ liệu, có portal/cursor hoặc cơ chế khác giữ snapshot. Không thể kết luận session vô hại chỉ vì mức isolation là READ COMMITTED.

### 6.2. REPEATABLE READ

Ở `REPEATABLE READ`, transaction có snapshot giao dịch được thiết lập theo quy tắc PostgreSQL, thường từ câu statement phù hợp đầu tiên. Những lần đọc tiếp theo trong cùng transaction sử dụng cùng bối cảnh snapshot nhất quán.

Do đó, một transaction đang idle sau SELECT ở REPEATABLE READ có thể **giữ snapshot cũ** trong lúc transaction khác liên tục UPDATE/DELETE.

Ví dụ:

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ;
SELECT COUNT(*) FROM some_table;
-- Không COMMIT hay ROLLBACK trong 30 phút.
```

Đây là kiểu tình huống mà VACUUM có thể chưa được phép dọn các phiên bản hàng bị thay đổi sau snapshot cũ.

### 6.3. SERIALIZABLE

`SERIALIZABLE` bảo đảm ngữ nghĩa tương đương với thứ tự tuần tự hợp lệ thông qua cơ chế của PostgreSQL. Một transaction ở mức này có thể giữ snapshot và các cấu trúc theo dõi phụ thuộc giao dịch theo cách ảnh hưởng vận hành; giao dịch quá dài cũng làm tăng khả năng xung đột serialization.

Không nên dùng `SERIALIZABLE` chỉ để có báo cáo nhất quán mà không hiểu nhu cầu, thời lượng giao dịch và retry policy. Nhưng cũng không nên tùy tiện hạ isolation của nghiệp vụ quan trọng chỉ để giảm bloat.

### 6.4. Đối chiếu

| Tình huống | Có thể giữ snapshot cũ gây hạn chế VACUUM? | Lưu ý |
| --- | --- | --- |
| Một `SELECT` ngắn, autocommit | Thường chỉ trong thời gian statement. | Mốc giữ rất ngắn khi hoàn tất nhanh. |
| Transaction READ COMMITTED, idle sau SELECT | **Không nhất thiết** giữ snapshot đọc cũ. | Vẫn kiểm tra XID, lock, portal và trạng thái. |
| Transaction REPEATABLE READ, idle sau SELECT | **Có thể** giữ snapshot giao dịch cũ. | Thường là tình huống dễ tái hiện trong lab. |
| Transaction đã UPDATE, chưa COMMIT | Có thể giữ XID/khóa và hạn chế cleanup. | Chưa commit nên trạng thái row versions chưa thể kết luận là dead hoàn toàn. |
| Transaction bị lỗi, `idle in transaction (aborted)` | Có thể gây vấn đề về tài nguyên và khóa theo trạng thái thực. | Cần rollback/kết thúc transaction; không thể gửi SQL tùy ý tiếp. |
| Session đóng/transaction rollback | Snapshot/transaction thường kết thúc. | Các nguồn giữ horizon khác vẫn có thể tồn tại. |

## 7. Chuẩn bị phòng thí nghiệm hai session

Chúng ta cố ý tạo một transaction giữ snapshot cũ và quan sát hoạt động của VACUUM từ session khác.

**Quan trọng:** chỉ chạy ví dụ trong database lab hoặc môi trường được phép. Ví dụ thực hiện UPDATE nhiều hàng và dùng `VACUUM`, không phù hợp để tùy tiện chạy trên bảng production. Không chạy những script này trong connection pool đang phục vụ người dùng.

### 7.1. Tạo schema và bảng

Trong một session PostgreSQL:

```sql
CREATE SCHEMA IF NOT EXISTS mvcc_cleanup_lab;

CREATE TABLE mvcc_cleanup_lab.demo_rows (
    row_id bigint PRIMARY KEY,
    payload text NOT NULL,
    generation integer NOT NULL DEFAULT 0
);

INSERT INTO mvcc_cleanup_lab.demo_rows (row_id, payload)
SELECT g, repeat('x', 100)
FROM generate_series(1, 3000) AS g;

CREATE INDEX idx_demo_rows_generation
ON mvcc_cleanup_lab.demo_rows (generation);

ANALYZE mvcc_cleanup_lab.demo_rows;
```

Tập dữ liệu ban đầu có 3.000 hàng, `generation=0`.

Kiểm tra:

```sql
SELECT
    COUNT(*) AS row_count,
    MIN(generation) AS min_generation,
    MAX(generation) AS max_generation
FROM mvcc_cleanup_lab.demo_rows;
```

Kết quả ban đầu:

| row_count | min_generation | max_generation |
| ---: | ---: | ---: |
| 3000 | 0 | 0 |

Lưu ý: `generation` được index, nên UPDATE làm thay đổi nó thường không đủ điều kiện HOT update đối với index này, giúp thí nghiệm tạo index entries và old tuple versions dễ quan sát hơn. Nhưng mức tăng dung lượng thực phụ thuộc cấu trúc pages, fillfactor, phiên bản và cách PostgreSQL thực thi.

### 7.2. Mở hai session độc lập

Chuẩn bị:

- **Session A:** mở transaction REPEATABLE READ, giữ snapshot.
- **Session B:** cập nhật dữ liệu, commit và chạy VACUUM.

Mỗi session phải sử dụng **một kết nối riêng** đến cùng database. Có thể mở hai cửa sổ `psql` hoặc hai tab GUI được cấu hình tạo hai database connections khác nhau. Nhiều tab SQL trong một GUI không mặc nhiên là hai session.

Để xác nhận:

```sql
SELECT pg_backend_pid() AS session_pid;
```

Hai session cần có hai backend PID khác nhau.

## 8. Thí nghiệm: snapshot cũ giữ phiên bản hàng

### 8.1. Session A: khởi tạo snapshot và để transaction mở

Trong **Session A**:

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ;

SELECT
    pg_backend_pid() AS session_a_pid,
    COUNT(*) AS row_count,
    MIN(generation) AS min_generation,
    MAX(generation) AS max_generation
FROM mvcc_cleanup_lab.demo_rows;
```

Kết quả:

```text
row_count = 3000
min_generation = 0
max_generation = 0
```

**Giữ nguyên session A**, không `COMMIT` hay `ROLLBACK`. Lần `SELECT` đã tạo bối cảnh snapshot cho transaction REPEATABLE READ.

### 8.2. Session B: thay đổi hàng sau snapshot của A

Trong **Session B** ở chế độ autocommit:

```sql
UPDATE mvcc_cleanup_lab.demo_rows
SET
    generation = generation + 1,
    payload = repeat('y', 100);

SELECT
    COUNT(*) AS row_count,
    MIN(generation) AS min_generation,
    MAX(generation) AS max_generation
FROM mvcc_cleanup_lab.demo_rows;
```

Kết quả ở B:

```text
row_count = 3000
min_generation = 1
max_generation = 1
```

Session B đã commit UPDATE của statement autocommit. Bây giờ trong database có các phiên bản mới và các phiên bản cũ còn có thể cần cho session A.

### 8.3. Session A vẫn nhìn thấy phiên bản cũ

Quay lại **Session A**:

```sql
SELECT
    COUNT(*) AS row_count,
    MIN(generation) AS min_generation,
    MAX(generation) AS max_generation
FROM mvcc_cleanup_lab.demo_rows;
```

Kết quả vẫn là `generation=0` cho cả 3.000 hàng, vì snapshot REPEATABLE READ của A được giữ.

Hai session có thể trả **hai kết quả khác nhau trên cùng bảng** mà không có lỗi:

| Session | Snapshot | Giá trị nhìn thấy |
| --- | --- | --- |
| A | Được thiết lập trước UPDATE của B. | `generation=0`. |
| B | Snapshot mới sau khi UPDATE commit. | `generation=1`. |

Điều này chính là lý do VACUUM không được xóa tùy tiện các phiên bản `generation=0` trong lúc A vẫn có thể đọc chúng.

### 8.4. Session B chạy VACUUM khi A còn mở

Trong **Session B**:

```sql
VACUUM (VERBOSE, ANALYZE) mvcc_cleanup_lab.demo_rows;
```

Lệnh `VACUUM` thông thường phải được thực hiện **ngoài transaction block**; hãy bảo đảm Session B không nằm trong `BEGIN ... COMMIT` còn mở.

VACUUM có thể chạy thành công và vẫn **không thể loại bỏ những phiên bản cũ mà snapshot A còn cần**. Ở log VERBOSE hoặc thống kê, tùy phiên bản, có thể xuất hiện thông tin về những tuple chưa thể dọn, số version remaining, hoặc mức độ cleanup hạn chế.

Không nên kỳ vọng một dòng log cố định với câu chữ giống nhau trên mọi PostgreSQL major. Tính đúng đắn cần được hiểu từ sự tồn tại của snapshot A và các mốc visibility, không chỉ một con số ước lượng.

### 8.5. Chẩn đoán session A từ Session B

Trong **Session B**, thay `<PID_A>` bằng số PID đã ghi ở Session A, hoặc dùng truy vấn lọc theo database và trạng thái:

```sql
SELECT
    pid,
    state,
    xact_start,
    backend_xid,
    backend_xmin,
    query_start,
    state_change
FROM pg_stat_activity
WHERE datname = current_database()
  AND xact_start IS NOT NULL
ORDER BY xact_start;
```

Session A nhiều khả năng xuất hiện với `state='idle in transaction'`, `xact_start` cũ, và khi snapshot vẫn được giữ có thể thấy `backend_xmin` phản ánh horizon của session.

Một backend ghi khác có thể đang active; những backend và giá trị cụ thể phụ thuộc client, phiên bản và thời điểm quan sát.

### 8.6. Kết thúc Session A

Trong **Session A**:

```sql
COMMIT;
```

Session A không còn cần snapshot cũ. Nếu không còn nguồn giữ horizon khác, PostgreSQL có cơ hội dọn các old tuples trước đó bị chặn.

Trong **Session B**:

```sql
VACUUM (VERBOSE, ANALYZE) mvcc_cleanup_lab.demo_rows;
```

Đây là thời điểm việc cleanup của những phiên bản `generation=0` trở nên khả thi, theo các điều kiện visibility khác.

**Không mong file bảng nhất thiết nhỏ lại sau VACUUM thứ hai.** Không gian có thể được đánh dấu tái sử dụng cho UPDATE/INSERT tương lai. `VACUUM FULL` là thao tác khác, không cần cho thí nghiệm này.

### 8.7. Điều gì xảy ra nếu A ROLLBACK thay vì COMMIT?

Session A trong thí nghiệm chỉ đọc. `ROLLBACK` cũng kết thúc transaction và giải phóng snapshot. Với mục tiêu kiểm chứng retention, `COMMIT` hoặc `ROLLBACK` của A đều làm mốc snapshot đó không còn được giữ.

Nếu A có các UPDATE chưa commit, `ROLLBACK` sẽ hủy những thay đổi của A nữa; vì vậy luôn hiểu transaction đang thực hiện những công việc gì trước khi kết thúc nó.

### 8.8. Kiểm tra kết quả cuối

```sql
SELECT
    COUNT(*) AS row_count,
    MIN(generation) AS min_generation,
    MAX(generation) AS max_generation
FROM mvcc_cleanup_lab.demo_rows;
```

Ở Session B sau UPDATE, bảng vẫn có 3.000 hàng logic với `generation=1`. Các phiên bản cũ được cleanup không có nghĩa số hàng nghiệp vụ giảm. Đây là khác biệt giữa:

- **Số hàng đang visible**.
- **Số phiên bản hàng vật lý từng tồn tại**.
- **Dung lượng file heap/index**.
- **Không gian bên trong file đang được tái sử dụng**.

## 9. Không dựa vào n_dead_tup như một phép đo tuyệt đối

View `pg_stat_user_tables` có trường `n_dead_tup` — **ước lượng** số dead tuples của bảng theo thống kê tích lũy.

```sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup,
    n_tup_ins,
    n_tup_upd,
    n_tup_del,
    n_tup_hot_upd,
    last_vacuum,
    last_autovacuum,
    vacuum_count,
    autovacuum_count
FROM pg_stat_user_tables
WHERE schemaname = 'mvcc_cleanup_lab'
  AND relname = 'demo_rows';
```

Ý nghĩa:

| Trường | Cách diễn giải |
| --- | --- |
| `n_live_tup` | Ước lượng số hàng sống. |
| `n_dead_tup` | Ước lượng số dead tuples, không phải số đếm chính xác từ heap. |
| `n_tup_upd` / `n_tup_del` | Hoạt động UPDATE/DELETE được thống kê. |
| `n_tup_hot_upd` | Số UPDATE có thể dùng Heap-Only Tuple (HOT) theo thống kê. |
| `last_vacuum` | Lần VACUUM thủ công gần nhất có dữ liệu thống kê. |
| `last_autovacuum` | Lần autovacuum gần nhất được thống kê. |
| `vacuum_count` / `autovacuum_count` | Số lượt vacuum theo thống kê. |

### 9.1. Vì sao số liệu có thể “không khớp”?

Số liệu `pg_stat_*`:

- Không phải phép quét heap chính xác ở mỗi truy vấn.
- Có độ trễ/cơ chế flush thống kê tùy phiên bản.
- Có thể bị ảnh hưởng bởi transaction đang mở và caching snapshot thống kê.
- Có thể thay đổi sau VACUUM/ANALYZE và hoạt động đồng thời.
- Có thể được reset theo thao tác quản trị.

Một truy vấn `SELECT n_dead_tup` không đủ để chứng minh riêng session A đã giữ toàn bộ dead tuples hay VACUUM đã/không dọn chính xác bao nhiêu byte.

Khi cần điều tra sâu, kết hợp `pg_stat_activity`, log VACUUM VERBOSE, kích thước quan hệ, tiến độ VACUUM và (nếu tổ chức cho phép) công cụ kiểm tra bloat/extension chuyên dụng.

### 9.2. pg_stat_clear_snapshot khi theo dõi thống kê

Ở các ngữ cảnh có caching snapshot thống kê, `pg_stat_clear_snapshot()` có thể dùng để buộc thông tin thống kê lần đọc sau lấy dữ liệu mới theo cơ chế PostgreSQL:

```sql
SELECT pg_stat_clear_snapshot();
```

Nhưng lệnh này **không dọn heap tuples**, không thay thế VACUUM và không thay đổi snapshot MVCC dùng để đọc dữ liệu trong transaction. Nó chỉ liên quan việc đọc thống kê giám sát.

## 10. Kích thước bảng và index: đo đúng chỉ số

Để quan sát sự phình to vật lý, PostgreSQL có các hàm đo size:

```sql
SELECT
    pg_size_pretty(
        pg_relation_size('mvcc_cleanup_lab.demo_rows')
    ) AS heap_size,
    pg_size_pretty(
        pg_indexes_size('mvcc_cleanup_lab.demo_rows')
    ) AS indexes_size,
    pg_size_pretty(
        pg_total_relation_size('mvcc_cleanup_lab.demo_rows')
    ) AS total_size;
```

### 10.1. Các kích thước khác nhau

- `pg_relation_size(...)`: kích thước fork chính của relation khi dùng một argument trong trường hợp bảng thông thường; không tự bao gồm mọi thành phần khác.
- `pg_indexes_size(...)`: tổng kích thước index của relation được hỏi.
- `pg_total_relation_size(...)`: tổng kích thước relation kể cả các thành phần liên quan như index và TOAST theo cách PostgreSQL tính toán.
- `pg_size_pretty(...)`: chỉ định dạng số byte thành chuỗi dễ đọc.

Để tính bằng số byte khi so sánh, dùng giá trị gốc thay vì chỉ chuỗi pretty:

```sql
SELECT
    pg_relation_size('mvcc_cleanup_lab.demo_rows') AS heap_bytes,
    pg_indexes_size('mvcc_cleanup_lab.demo_rows') AS index_bytes,
    pg_total_relation_size('mvcc_cleanup_lab.demo_rows') AS total_bytes;
```

### 10.2. Vì sao VACUUM không luôn làm total_bytes giảm?

Giả sử file bảng dài 100 MB gồm nhiều trang chứa tuple cũ:

```text
Trước VACUUM:
 [page chứa hàng sống][page chứa tuple cũ][page chứa hàng sống]...

Sau VACUUM:
 [page chứa hàng sống][không gian có thể tái sử dụng][page chứa hàng sống]...
```

PostgreSQL có thể tái dùng khoảng trống trên những page đã tồn tại cho các INSERT/UPDATE sau. Điều này giúp giảm nhu cầu mở rộng file tiếp theo, dù file hiện tại vẫn chiếm dung lượng trên filesystem.

Vì vậy chỉ nhìn `pg_total_relation_size` không giảm sau VACUUM rồi tuyên bố vacuum “thất bại” là không đúng.

## 11. HOT updates, pruning và index cleanup

PostgreSQL có cơ chế **HOT (Heap-Only Tuple) update** trong một số điều kiện, thường khi UPDATE không thay đổi những cột được index theo cách ngăn HOT và có đủ không gian trang.

### 11.1. HOT có liên quan gì đến bloat?

HOT giúp giảm việc phải tạo index entry mới cho từng phiên bản cập nhật, và có thể giúp quá trình pruning của heap page hiệu quả hơn. Tuy nhiên:

- HOT không có nghĩa không phát sinh phiên bản hàng mới.
- Old tuple versions vẫn phải tuân thủ MVCC visibility.
- Một snapshot cũ vẫn có thể hạn chế dọn những phiên bản còn cần.

### 11.2. Page pruning khác VACUUM

PostgreSQL có thể dọn/prune những phần của HOT chain khi truy cập trang, nếu an toàn. Nhưng page pruning cũng không được phép phá vỡ tính hiển thị của snapshot cũ.

**Đừng nhầm:** “autovacuum chưa chạy” không nhất thiết nghĩa chưa có cleanup nào, vì pruning có thể xảy ra ở các thao tác khác. Ngược lại, “autovacuum vừa chạy” không có nghĩa mọi tuple lỗi thời đã có thể loại bỏ.

### 11.3. Index entries

UPDATE thay đổi cột index có thể sinh nhiều mục index tương ứng phiên bản hàng. VACUUM có pha dọn index khi đủ điều kiện, nhưng không thể tự xóa những mục còn cần bảo toàn đường truy cập tới tuple visible của snapshot cũ.

Khi sự cố kéo dài, bloat có thể xuất hiện ở cả **heap và indexes**. Kết thúc blocker rồi chỉ chạy `ANALYZE` có thể không đủ; cần hiểu tình trạng vacuum/index cleanup.

## 12. Autovacuum được kích hoạt như thế nào?

Autovacuum là cơ chế nền PostgreSQL giúp VACUUM/ANALYZE các bảng khi đủ điều kiện. Một mô hình gần đúng cho ngưỡng VACUUM vì UPDATE/DELETE là:

\[
\text{trigger} \approx
\text{autovacuum\_vacuum\_threshold}
+ \text{autovacuum\_vacuum\_scale\_factor}
\times \text{estimated\_table\_size}
\]

Trong các phiên bản và cấu hình hiện đại còn có những cơ chế liên quan insert-driven vacuum, threshold tối đa và điều kiện anti-wraparound, nên công thức trên là **mô hình cơ bản**, không phải bản đặc tả toàn bộ autovacuum.

Ví dụ giả định:

- `autovacuum_vacuum_threshold = 50`.
- `autovacuum_vacuum_scale_factor = 0.2`.
- Bảng ước lượng 100.000 hàng.

Ngưỡng theo mô hình là khoảng `50 + 0.2 × 100000 = 20050` dead tuples trước khi đủ điều kiện kiểm tra vacuum theo tiêu chí này. Cấu hình thực có thể khác.

### 12.1. Xem cấu hình

```sql
SHOW autovacuum;
SHOW autovacuum_vacuum_threshold;
SHOW autovacuum_vacuum_scale_factor;
SHOW autovacuum_analyze_threshold;
SHOW autovacuum_analyze_scale_factor;
SHOW autovacuum_max_workers;
SHOW autovacuum_naptime;
```

Những giá trị mặc định, phạm vi áp dụng và tên tùy chọn có thể thay đổi theo major PostgreSQL. Ngoài cấu hình cấp server còn có thể có **storage parameters** theo từng bảng.

### 12.2. Thay threshold không thể bỏ qua snapshot

Giảm scale factor để autovacuum chạy thường xuyên hơn có thể hữu ích với bảng ghi nhiều, nhưng:

**Autovacuum chạy thường xuyên vẫn không thể xóa phiên bản tuple còn cần cho snapshot/XID hợp lệ.**

Nếu nguồn cản trở là một transaction cũ chưa kết thúc, chỉ tăng số worker hoặc giảm naptime không giải quyết cơ chế retention. Trước hết phải xác định và xử lý nguồn giữ horizon.

### 12.3. Autovacuum không có nghĩa được tắt tùy tiện

Tắt autovacuum lâu dài có thể khiến dead tuples tích tụ và gây nguy cơ transaction ID wraparound. Một số công việc anti-wraparound có cơ chế đặc biệt ngay cả khi các cài đặt thông thường bị hạn chế.

Trong sản xuất, không tự tắt autovacuum như một cách làm giảm I/O tức thời nếu chưa có kế hoạch bảo trì thay thế đã được đánh giá đầy đủ.

## 13. Freezing và nguy cơ transaction ID wraparound

Transaction IDs trong PostgreSQL có không gian định danh hữu hạn; hệ thống phải quản lý việc **quay vòng XID** an toàn.

### 13.1. Freeze làm gì?

VACUUM có thể “freeze” thông tin transaction ID cũ của các tuple đủ điều kiện để chúng tiếp tục được nhìn thấy đúng sau khi số transaction IDs tiến rất xa.

`relfrozenxid` của relation và `datfrozenxid` của database là những mốc liên quan việc tính độ tuổi transaction ID cần được bảo trì.

```sql
SELECT
    current_database() AS database_name,
    age(datfrozenxid) AS database_xid_age
FROM pg_database
WHERE datname = current_database();
```

Và với bảng:

```sql
SELECT
    n.nspname AS schema_name,
    c.relname,
    age(c.relfrozenxid) AS table_xid_age
FROM pg_class AS c
JOIN pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE n.nspname = 'mvcc_cleanup_lab'
  AND c.relname = 'demo_rows';
```

`age(...)` ở đây là **số khoảng transaction IDs**, không phải độ dài bằng phút/giờ.

### 13.2. Tại sao snapshot/XID cũ có thể nguy hiểm?

Một transaction hoặc horizon cũ có thể khiến PostgreSQL chưa được phép tiến xa những mốc cleanup/freeze theo cách có lợi nhất. Nếu lượng transaction mới phát sinh nhanh, khoảng cách tới các ngưỡng bảo vệ wraparound tăng lên.

Khi đạt các ngưỡng bảo vệ, PostgreSQL có thể cần aggressive/anti-wraparound vacuum, cảnh báo vận hành và trong trường hợp nghiêm trọng hạn chế những transaction cần XID mới để tránh mất an toàn dữ liệu.

Đây là rủi ro vận hành, không phải “chỉ mất vài MB ổ đĩa”. Cần theo dõi XID age và giải quyết blocker trước khi chạm ngưỡng nguy hiểm.

### 13.3. Cấu hình liên quan

```sql
SHOW autovacuum_freeze_max_age;
SHOW vacuum_freeze_min_age;
SHOW vacuum_freeze_table_age;
```

Các tham số có mối liên hệ với mức độ aggressive/freeze của vacuum; không nên tùy tiện hạ/ngẩng ngưỡng chỉ để che cảnh báo nếu chưa hiểu ranh giới an toàn. Thay đổi cấu hình không có nghĩa PostgreSQL được phép bỏ qua snapshot cũ để xóa phiên bản còn visible.

### 13.4. Theo dõi giá trị lớn nhất trong database

```sql
SELECT
    datname,
    age(datfrozenxid) AS xid_age
FROM pg_database
WHERE datallowconn
ORDER BY xid_age DESC;
```

Một cơ sở dữ liệu có tuổi XID cao cần được xem trong mối quan hệ với cấu hình hiện hành, log autovacuum, replication và các nguồn giữ oldest XID khác. Không thể chẩn đoán chỉ từ số tuổi mà không có bối cảnh.

## 14. Lỗi vận hành: vacuum chạy nhưng dead tuples vẫn còn

Một DBA nhận được cảnh báo:

```text
n_dead_tup tăng
autovacuum_count tăng
last_autovacuum mới
heap/index size vẫn tăng
```

Chẩn đoán đúng không phải ngay lập tức kết luận “autovacuum không hoạt động”. Có thể autovacuum đã chạy đúng lịch nhưng bị giới hạn bởi **oldest visibility horizon**.

### 14.1. Những khả năng khác cần phân biệt

1. **Long-running transaction giữ snapshot/XID:** old tuple versions chưa removable.
2. **Write rate quá cao:** vacuum có thể dọn nhưng không theo kịp tốc độ tạo dead tuples.
3. **Cấu hình autovacuum chưa phù hợp:** trigger quá thưa, worker/cost/memory không phù hợp.
4. **Autovacuum bị hủy hoặc tranh lock:** tiến trình không hoàn thành như dự kiến.
5. **Replicas/slots/prepared transactions:** giữ horizon ngoài backend ứng dụng thông thường.
6. **Bloat đã tồn tại trước đó:** VACUUM có thể tái sử dụng không gian mà không làm file nhỏ lại.
7. **Thống kê trễ hoặc estimate:** n_dead_tup không phải số chính xác từng thời điểm.

Phải kiểm tra tình trạng cụ thể trước khi thay đổi tham số server hoặc can thiệp query.

### 14.2. Vì sao chạy VACUUM FULL trước thường là sai hướng?

`VACUUM FULL` rewrite bảng và cần khóa mạnh (`ACCESS EXCLUSIVE` đối với relation đang xử lý), có thể chặn hoạt động đọc/ghi trong thời gian đáng kể. Nó còn cần không gian đĩa để xây dựng lại dữ liệu.

Nếu blocker cũ vẫn còn, sự cố có thể tái diễn sau đó. Đừng biến một vấn đề retention có thể giải quyết ở ứng dụng thành downtime do rewrite bảng không cần thiết.

### 14.3. VACUUM (VERBOSE) sau khi giải quyết blocker

```sql
VACUUM (VERBOSE, ANALYZE) mvcc_cleanup_lab.demo_rows;
```

Sau khi các snapshot cũ hết cần, VACUUM có cơ hội dọn thêm tuple theo điều kiện thực tế. Nếu cần giảm file size ngay, phải đánh giá chiến lược rewrite/reindex và downtime theo phạm vi; đó là một quyết định vận hành riêng.

## 15. Chẩn đoán transaction dài với pg_stat_activity

Đây là truy vấn giám sát quan trọng cho bài học:

```sql
SELECT
    pid,
    datname,
    usename,
    application_name,
    client_addr,
    state,
    clock_timestamp() - xact_start AS transaction_age,
    clock_timestamp() - state_change AS state_age,
    backend_xid,
    backend_xmin,
    CASE
        WHEN backend_xmin IS NULL THEN NULL
        ELSE age(backend_xmin)
    END AS snapshot_xid_age,
    LEFT(query, 150) AS query_sample
FROM pg_stat_activity
WHERE datname = current_database()
  AND xact_start IS NOT NULL
ORDER BY xact_start NULLS LAST;
```

Mục đích:

- Tìm các session có transaction đã mở lâu.
- Xem session đang `active` hay `idle in transaction`.
- Xem có `backend_xmin` và `backend_xid` không.
- Biết user/application/client để xác định owner.
- Xem mẫu query gần nhất (có thể không phải tất cả SQL đã chạy trong transaction).

### 15.1. Diễn giải transaction_age

`transaction_age` là thời gian wall-clock đã trôi từ lúc transaction bắt đầu. Nó giúp ưu tiên điều tra, nhưng **không trực tiếp đo số old tuples bị giữ**.

Một session 30 phút với `backend_xmin` cũ có thể đáng chú ý hơn một session 2 giờ không giữ snapshot hay XID liên quan, tùy workload và hệ thống.

Không đặt một ngưỡng “quá 5 phút chắc chắn gây bloat” áp dụng cho mọi hệ thống.

### 15.2. Diễn giải state_age

`state_age` cho biết backend đã ở trạng thái hiện tại bao lâu. Ví dụ:

- `idle in transaction` 10 phút: ứng dụng có thể đã bỏ kết nối mở transaction mà không có SQL mới.
- `active` 10 phút: có thể query dài, chờ khóa, chạy batch hoặc VACUUM.
- `idle in transaction (aborted)`: transaction đã gặp lỗi và chưa được kết thúc phù hợp.

Để điều tra blocking, có thể bổ sung các cột `wait_event_type` và `wait_event` từ `pg_stat_activity`.

### 15.3. Xem backend_xid và backend_xmin song song

```sql
SELECT
    pid,
    state,
    xact_start,
    backend_xid,
    backend_xmin
FROM pg_stat_activity
WHERE datname = current_database()
  AND (
      backend_xid IS NOT NULL
      OR backend_xmin IS NOT NULL
      OR state LIKE 'idle in transaction%'
  )
ORDER BY xact_start NULLS LAST;
```

Nếu `backend_xmin` NULL, không thể kết luận “session hoàn toàn không gây cản trở vacuum” chỉ từ trường đó: một transaction có XID chưa kết thúc, cursor/portal, prepared transaction hoặc replication feedback có thể cần xem tiếp. Ngược lại, có `backend_xmin` cũng cần so sánh với những horizon khác để xác định mức độ cản trở cụ thể.

### 15.4. Quyền xem thông tin

Thông tin query và session của user khác có thể bị giới hạn theo quyền PostgreSQL. Người giám sát thường cần role/quyền monitoring phù hợp, ví dụ `pg_monitor` hoặc `pg_read_all_stats` tùy chính sách, thay vì cấp superuser tràn lan.

Không xuất nguyên văn `query` chứa dữ liệu bí mật vào ticket hoặc log không được bảo vệ. Trong ví dụ chỉ lấy 150 ký tự để giảm độ dài, nhưng điều đó **không bảo đảm không lộ dữ liệu nhạy cảm** nếu SQL có inline literals.

## 16. Theo dõi VACUUM đang chạy với pg_stat_progress_vacuum

PostgreSQL có view `pg_stat_progress_vacuum` để xem tiến độ VACUUM ở thời điểm đang chạy:

```sql
SELECT
    pid,
    relid::regclass AS relation_name,
    phase,
    heap_blks_total,
    heap_blks_scanned,
    heap_blks_vacuumed
FROM pg_stat_progress_vacuum
ORDER BY pid;
```

Các cột hiện hữu và ý nghĩa chi tiết có thể có thay đổi theo major PostgreSQL, nhưng các pha chính thường liên quan:

- Quét heap để tìm tuple cần dọn.
- Vacuum index theo các chiến lược được chọn.
- Vacuum heap.
- Dọn index/metadata và hoàn tất.

### 16.1. Không có hàng không có nghĩa VACUUM bị tắt

View tiến độ chỉ hiển thị các hoạt động VACUUM đang diễn ra ở thời điểm query. Nếu autovacuum đã hoàn thành, nó sẽ không còn xuất hiện. Hãy kiểm tra `last_autovacuum`/`autovacuum_count` và log khi cần xác nhận lịch sử.

### 16.2. VACUUM có thể hoàn thành mà không dọn được nhiều hàng

Nếu scan gặp dead tuples nhưng visibility horizon không cho phép remove, VACUUM vẫn có thể làm các công việc khác và hoàn thành hợp lệ. Vì vậy:

**Trạng thái “VACUUM hoàn tất” không đồng nghĩa “đã thu hồi toàn bộ row versions cũ”.**

Ngược lại, nếu VACUUM lâu bất thường, cần phân biệt quét bảng lớn, I/O contention, index cleanup, locking và workload ghi liên tục trước khi quy trách nhiệm cho một transaction idle.

## 17. Cơ chế giữ chân khác: standby feedback

Một primary PostgreSQL có thể có replica đọc (*hot standby*) để phục vụ báo cáo hoặc tăng khả năng sẵn sàng. Replica có thể giữ snapshot đọc lâu trong khi primary đang cập nhật/xóa dữ liệu.

### 17.1. Bài toán xung đột cleanup giữa primary và standby

```text
Primary                                Standby
-------                                -------
UPDATE/DELETE
    |
    +-- sinh old tuples
    |
VACUUM muốn loại old tuples
                                       Query dài cần snapshot cũ
    |                                       |
    +---------- xung đột cần xử lý ---------+
```

PostgreSQL có cơ chế xử lý xung đột replay với truy vấn standby. Nếu bật cấu hình phù hợp như `hot_standby_feedback` trên standby, replica có thể gửi thông tin ngưỡng XID tới primary để primary **trì hoãn cleanup** những versions mà truy vấn standby còn cần.

Đánh đổi:

- Có thể giảm số truy vấn trên standby bị hủy do recovery conflict.
- Có thể tăng bloat ở primary vì vacuum phải giữ versions lâu hơn.

### 17.2. Xem cấu hình ở replica

Trên standby phù hợp:

```sql
SHOW hot_standby_feedback;
```

Chỉ đọc cấu hình không cho biết hiện tại có truy vấn nào giữ horizon; cần xem trạng thái streaming/replay và snapshot hiện hữu.

### 17.3. Xem thông tin replication trên primary

Trên primary có quyền phù hợp:

```sql
SELECT
    pid,
    application_name,
    client_addr,
    state,
    backend_xmin
FROM pg_stat_replication
ORDER BY application_name, pid;
```

`backend_xmin` trong thống kê replication có thể phản ánh horizon nhận được qua feedback. Một giá trị cũ là tín hiệu cần điều tra phía standby và chiến lược replication.

### 17.4. Không tắt feedback một cách tùy tiện

Nếu tắt `hot_standby_feedback` để giải phóng cleanup, truy vấn standby dài có thể bị hủy khi replay phải áp dụng thay đổi từ primary. Đây là đánh đổi giữa **bloat primary** và **khả năng truy vấn nhất quán ở standby**, không phải nút “sửa bloat miễn phí”.

Các tham số như `max_standby_streaming_delay` còn liên quan đến cách standby đợi hoặc hủy truy vấn khi phát sinh recovery conflict. Phải xem nhu cầu báo cáo, latency replica và RPO/RTO trước khi đổi cấu hình.

## 18. Replication slots và những ranh giới giữ dữ liệu

Replication slot được PostgreSQL dùng để quản lý những thông tin cần giữ cho quá trình replication. Một số slot có thể có **`xmin` hoặc `catalog_xmin`** liên quan tới việc giữ các phiên bản dữ liệu/catalog, ngoài việc có **`restart_lsn`** liên quan tới WAL retention.

Đây là nguồn ảnh hưởng quan trọng vì **không nhất thiết xuất hiện như một session `idle in transaction` thông thường trong `pg_stat_activity`**.

### 18.1. Xem danh sách replication slots

Trên server có quyền giám sát phù hợp:

```sql
SELECT
    slot_name,
    slot_type,
    active,
    xmin,
    catalog_xmin,
    restart_lsn,
    confirmed_flush_lsn
FROM pg_replication_slots
ORDER BY slot_name;
```

Ý nghĩa:

| Trường | Gợi ý diễn giải |
| --- | --- |
| `slot_name` | Tên slot. |
| `slot_type` | `physical` hoặc `logical`. |
| `active` | Slot có đang được một tiến trình sử dụng hay không. |
| `xmin` | Mốc XID mà slot có thể yêu cầu giữ đối với dữ liệu thường khi có. |
| `catalog_xmin` | Mốc XID liên quan các catalog tuples cần cho logical decoding khi có. |
| `restart_lsn` | Vị trí WAL cũ nhất còn cần giữ cho slot theo trạng thái hiện hành. |
| `confirmed_flush_lsn` | Vị trí xác nhận tiêu thụ trong ngữ cảnh logical slot khi có. |

**Không được hiểu `active=false` là “slot không ảnh hưởng gì”.** Slot không active vẫn có thể giữ các vị trí/horizon cần thiết và dẫn đến tích tụ WAL hoặc ảnh hưởng cleanup tùy trạng thái slot.

### 18.2. Bloat heap và WAL retention là hai vấn đề khác

Một tình huống có thể gây cả hai:

```text
Logical subscriber bị ngừng
          |
          +-- restart_lsn cũ
          |      -> WAL có thể tích tụ
          |
          +-- catalog_xmin cũ
                 -> catalog row versions có thể bị giữ lâu
```

Nhưng không đồng nhất hai chỉ số:

- `restart_lsn` chủ yếu liên quan giữ **WAL** để consumer có thể tiếp tục.
- `xmin`/`catalog_xmin` liên quan tới ranh giới giữ **row versions** phục vụ tính đúng đắn của replication/decoding.

Một slot có WAL lag lớn không tự chứng minh nó đang giữ dead tuples ở bảng nghiệp vụ; một slot giữ `catalog_xmin` cũng không đồng nghĩa nó giữ toàn bộ heap data rows. Cần đọc đúng từng trường.

### 18.3. Xem mức WAL đang giữ theo slot

Trên primary trong bối cảnh phù hợp:

```sql
SELECT
    slot_name,
    slot_type,
    active,
    restart_lsn,
    CASE
        WHEN restart_lsn IS NOT NULL THEN
            pg_size_pretty(
                pg_wal_lsn_diff(
                    pg_current_wal_lsn(),
                    restart_lsn
                )::bigint
            )
        ELSE NULL
    END AS approximate_wal_distance
FROM pg_replication_slots
ORDER BY slot_name;
```

`pg_wal_lsn_diff` ở đây cho **khoảng cách LSN**, không phải cam kết chính xác byte WAL đang nằm trên filesystem chỉ do slot đó giữ. Việc tính còn phụ thuộc primary, vị trí WAL hiện tại, cấu hình và trạng thái replication.

Không áp dụng câu SQL này một cách máy móc trên standby/read-only environment nếu các hàm không phù hợp bối cảnh server.

### 18.4. Nguy cơ xóa slot sai

Không xóa một replication slot chỉ vì thấy nó không active. Slot có thể thuộc:

- Replica tạm ngừng.
- Một connector CDC phục vụ pipeline dữ liệu.
- Hệ thống audit hoặc downstream đã được cấu hình sử dụng.
- Quy trình failover/HA đang phụ thuộc vào tiến độ replication.

Xóa slot có thể làm consumer không còn tiếp tục được từ vị trí cũ, buộc tái đồng bộ và có nguy cơ mất tính liên tục của dữ liệu downstream. Hãy xác định **owner và RPO/RTO**, tình trạng consumer, vị trí đã xác nhận và phương án phục hồi trước khi can thiệp.

## 19. Prepared transactions: không có backend vẫn có thể giữ tài nguyên

PostgreSQL hỗ trợ cơ chế two-phase commit (2PC) qua `PREPARE TRANSACTION`, `COMMIT PREPARED` và `ROLLBACK PREPARED` khi server được cấu hình cho phép.

Một transaction ở trạng thái *prepared* đã tách khỏi session ban đầu nhưng **chưa được commit/rollback cuối cùng**. Nó có thể giữ khóa và các tài nguyên liên quan transaction, cũng như ảnh hưởng horizon phục vụ VACUUM.

### 19.1. Xem prepared transactions

```sql
SELECT
    gid,
    prepared,
    owner,
    database,
    transaction
FROM pg_prepared_xacts
ORDER BY prepared;
```

Ở đây:

- `gid`: định danh prepared transaction.
- `prepared`: thời điểm transaction được prepare.
- `owner` / `database`: thông tin sở hữu.
- `transaction`: transaction ID tương ứng.

Nếu một prepared transaction tồn tại lâu, người điều tra không thể chỉ kiểm tra `pg_stat_activity` rồi dừng: **prepared transaction không còn backend active cùng cách session thông thường**.

### 19.2. Không commit/rollback prepared transaction tùy tiện

Một prepared transaction có thể thuộc coordinator của giao dịch phân tán. Nếu tự `COMMIT PREPARED` hay `ROLLBACK PREPARED` mà không xác định kết quả ở các hệ thống khác, có thể làm hỏng tính nhất quán phân tán.

Quy trình đúng là xác định coordinator, trạng thái các nhánh, transaction GID, kế hoạch phục hồi và quyền quản trị; sau đó mới quyết định hoàn tất hoặc hủy.

### 19.3. Cấu hình 2PC

```sql
SHOW max_prepared_transactions;
```

Trên nhiều hệ thống không sử dụng 2PC, tham số này thường được để ở mức vô hiệu hóa việc chuẩn bị transaction. Nếu hệ thống dùng 2PC, cần giám sát prepared transactions bị bỏ quên như một nhóm đối tượng riêng.

## 20. Tổng hợp các nguồn có thể giữ cleanup horizon

| Nguồn | Cách quan sát | Dấu hiệu cần xem |
| --- | --- | --- |
| Giao dịch ứng dụng đang hoạt động/idle | `pg_stat_activity` | `xact_start`, `backend_xid`, `backend_xmin`, `state`. |
| Truy vấn dài giữ snapshot | `pg_stat_activity` | `state=active`, `query_start`, `backend_xmin`. |
| Giao dịch REPEATABLE READ đang idle | `pg_stat_activity` | Snapshot/XID còn giữ trong thời gian dài. |
| Standby feedback | `pg_stat_replication` trên primary | `backend_xmin` được báo qua replication khi có. |
| Replication slot | `pg_replication_slots` | `xmin`, `catalog_xmin` và vị trí WAL. |
| Prepared transaction | `pg_prepared_xacts` | GID cũ, transaction ID, thời điểm prepare. |
| Một số cursor/portal/snapshot có vòng đời dài | Session/client và công cụ theo dõi liên quan | Ngữ cảnh sử dụng cursor, snapshot còn giữ. |
| Luồng maintenance/write cường độ cao | `pg_stat_user_tables`, logs, progress | Dead tuples sinh nhanh hơn tốc độ dọn. |

**Không có một cột duy nhất luôn chỉ ra chính xác “thủ phạm giữ dead tuple của mọi bảng”.** Mức độ hiển thị phụ thuộc nguồn dữ liệu, phiên bản PostgreSQL, quyền truy cập và trạng thái vào lúc lấy mẫu.

## 21. Trường hợp hay gặp: idle in transaction

Mẫu lỗi ứng dụng:

```text
checkout connection
BEGIN
SELECT dữ liệu
gọi HTTP service bên ngoài
chờ người dùng / xử lý file
ghi log
quên COMMIT/ROLLBACK
để connection trong pool hoặc thread
```

Khi ứng dụng chờ tác vụ bên ngoài trong lúc transaction vẫn mở, session có thể ở trạng thái `idle in transaction`. Nếu snapshot/XID đang được giữ, nó có thể hạn chế VACUUM. Dù không giữ snapshot cũ, nó vẫn có thể giữ locks và chiếm connection.

### 21.1. Cấu hình timeout

PostgreSQL có tham số:

```sql
SHOW idle_in_transaction_session_timeout;
```

Tham số này có thể giới hạn thời gian session được phép **idle trong transaction**. Khi vượt ngưỡng, PostgreSQL có thể kết thúc session theo cơ chế timeout, dẫn đến transaction chưa commit bị hủy.

**Đánh đổi quan trọng:** nếu ứng dụng có luồng xử lý hợp lệ cố ý idle trong transaction lâu, timeout quá ngắn sẽ làm nó mất connection và rollback công việc.

Timeout là **hàng rào bảo vệ**, không phải thay thế sửa code thiếu `commit/rollback`.

### 21.2. statement_timeout không xử lý mọi session idle

`statement_timeout` giới hạn thời gian thực thi một statement trong phạm vi áp dụng. Một session đã hoàn tất SELECT rồi ngồi `idle in transaction` không nhất thiết bị `statement_timeout` kết thúc, vì lúc đó không có statement đang chạy.

Tương tự, `lock_timeout` liên quan thời gian chờ lấy khóa, không thay thế timeout dành cho thời gian idle trong transaction.

### 21.3. Transaction timeout theo phiên bản

Một số PostgreSQL major mới có thêm tham số giới hạn tuổi transaction, nhưng **khả năng hỗ trợ và tương tác các timeout phụ thuộc phiên bản**. Khi triển khai, kiểm tra tham số chính xác trên server thay vì sao chép cấu hình từ major khác.

Đừng tạo một cấu hình mà service bị terminate theo chu kỳ khi đang chạy thao tác hợp lệ, rồi dựa vào retry vô hạn để che lỗi kiến trúc.

## 22. Phòng ngừa tại ứng dụng Java/JDBC

PostgreSQL chỉ nhìn thấy connection và transaction. Nguyên nhân gốc thường nằm trong vòng đời transaction của ứng dụng.

### 22.1. Không để connection mở transaction qua tác vụ lâu

Ví dụ thiết kế có nguy cơ:

```text
BEGIN
SELECT rows
gọi API ngoài trong 20 giây
chờ download
UPDATE rows
COMMIT
```

Nếu không có yêu cầu consistency buộc các bước phải cùng transaction, tách phần **gọi API, xử lý CPU/file, chờ người dùng** ra ngoài transaction:

```text
gọi API ngoài, chuẩn bị dữ liệu
BEGIN
SELECT/UPDATE cần tính nhất quán
COMMIT
ghi nhận kết quả và phát sự kiện sau commit
```

Nhưng không tách mù nếu kết quả đọc/ghi có invariant về giá và tồn kho: cần đánh giá locking, optimistic concurrency, version checks hoặc retry thích hợp.

### 22.2. JDBC: commit và rollback bằng try/catch

Ví dụ khung xử lý giao dịch tường minh:

```java
Connection connection = dataSource.getConnection();

try (connection) {
    connection.setAutoCommit(false);

    try {
        // Chỉ thực hiện các câu SQL thuộc cùng đơn vị nghiệp vụ.
        // Không chờ HTTP call hoặc người dùng quá lâu ở đây.

        try (PreparedStatement statement =
                 connection.prepareStatement(
                     "UPDATE inventory SET quantity = quantity - 1 " +
                     "WHERE product_id = ? AND quantity > 0"
                 )) {
            statement.setLong(1, productId);
            int updated = statement.executeUpdate();

            if (updated != 1) {
                throw new SQLException("Insufficient stock");
            }
        }

        connection.commit();
    } catch (Exception failure) {
        try {
            connection.rollback();
        } catch (SQLException rollbackFailure) {
            failure.addSuppressed(rollbackFailure);
        }
        throw failure;
    }
}
```

Đoạn Java là **khung minh họa**, giả định `dataSource` và `productId` đã được khởi tạo; bảng `inventory` không thuộc schema lab của bài. Trong production, phải xử lý lifecycle, checked exceptions, timeout và transaction manager cụ thể. Mục tiêu là **không có đường thoát exception mà transaction vẫn bị bỏ quên**.

### 22.3. Framework transaction boundaries

Các thư viện ORM hoặc framework có thể mở transaction quanh một service method. Nếu method đó gọi API chậm, tải file, chờ queue hoặc thực thi logic lâu sau khi đã query database, connection có thể giữ transaction mở không cần thiết.

Kiểm tra:

- Method nào thật sự bắt đầu transaction?
- Có call ra mạng trong scope transaction không?
- Exception có bị nuốt làm transaction không kết thúc hoặc rollback-only không?
- Streaming result/cursor có giữ snapshot qua nhiều lần đọc không?
- Timeout của app, pool và database có nhất quán không?
- Có metric thời gian transaction và số connections `idle in transaction` không?

Không coi một annotation transaction trên một method dài là “miễn phí” chỉ vì nó làm code trông an toàn hơn.

## 23. Cursor, streaming và truy vấn báo cáo kéo dài

Không chỉ các session idle mới đáng chú ý. Một report có thể cố ý đọc lượng dữ liệu lớn theo cursor hoặc stream:

```text
BEGIN
DECLARE cursor...
FETCH 1000 rows
xử lý batch trong ứng dụng
FETCH 1000 rows
xử lý batch tiếp
...
COMMIT
```

Vòng đời cursor/portal/snapshot phụ thuộc isolation, loại cursor và cách client sử dụng. Một số mẫu có thể giữ nguồn lực hoặc snapshot lâu trong khi ứng dụng xử lý bên ngoài database.

### 23.1. Không giả định streaming luôn tiết kiệm mọi tài nguyên

Streaming giúp giảm RAM ở application so với tải tất cả hàng một lần, nhưng có thể kéo dài thời gian connection và transaction tồn tại.

Giải pháp tùy bài toán:

- Giảm kích thước/khoảng thời gian query.
- Thực hiện phân trang theo keyset nếu tính đúng đắn cho phép.
- Đưa báo cáo lớn sang replica hoặc môi trường ETL phù hợp, hiểu đánh đổi standby feedback.
- Dùng một snapshot rõ ràng khi cần consistency xuyên nhiều chunk; chấp nhận và quản lý chi phí giữ snapshot.
- Tách processing chậm ra khỏi transaction theo thiết kế.

Không tự đổi sang phân trang từng statement nếu yêu cầu đòi một snapshot nhất quán cho toàn report mà chưa quyết định cách đối soát dữ liệu thay đổi giữa các trang.

### 23.2. Không nhầm khóa với snapshot

Một query dài có thể:

- Giữ snapshot cũ, ảnh hưởng cleanup.
- Giữ một số khóa, gây blocking.
- Cả hai.
- Chỉ làm tốn CPU/I/O mà ít ảnh hưởng cleanup.

Các vấn đề này có **triệu chứng và cách xử lý khác nhau**. `pg_blocking_pids(pid)` giúp phân tích lock blocking, nhưng không thể thay thế việc tìm visibility horizon holder.

## 24. Transaction bị lỗi nhưng chưa rollback

Một session có thể ở:

```text
idle in transaction (aborted)
```

Khi SQL lỗi trong transaction tường minh, session không thể tiếp tục câu SQL bình thường cho đến khi rollback hoặc xử lý theo savepoint phù hợp. Nếu client bắt exception rồi bỏ quên transaction, session có thể nằm đó lâu.

Ví dụ flow:

```text
BEGIN
UPDATE ...
INSERT trùng unique -> ERROR
application catch SQLException nhưng không rollback
connection vẫn giữ mở
```

Đây là lỗi quản lý transaction cần xử lý. Tuy nhiên **đừng suy luận chỉ từ state string rằng backend chắc chắn đang giữ `backend_xmin`**; kiểm tra snapshot/XID/locks để hiểu ảnh hưởng cụ thể.

Biện pháp chính là ứng dụng phải luôn kết thúc transaction khi lỗi không được phục hồi, và pool phải trả connection về trạng thái sạch.

## 25. Cách tiếp cận an toàn khi phát hiện session đáng ngờ

Khi đang vận hành production, không nên ngay lập tức chạy lệnh chấm dứt kết nối vì nhìn thấy `xact_start` cũ.

Trình tự đề xuất:

1. **Xác minh triệu chứng:** bảng tăng size, autovacuum không theo kịp, XID age tăng, query latency tăng, disk usage tăng hay chỉ một biểu đồ thống kê biến động?
2. **Xác định đối tượng bị ảnh hưởng:** schema/table, thời gian bắt đầu tăng trưởng, các bảng có write rate lớn.
3. **Kiểm tra các backend:** `xact_start`, `state`, `backend_xid`, `backend_xmin`, application/client.
4. **Kiểm tra nguồn ngoài backend:** replication slots, standby feedback, prepared transactions.
5. **Tìm owner:** xác định service, job hoặc người đang chạy query.
6. **Đánh giá khả năng kết thúc an toàn:** transaction có đang phục vụ thanh toán/batch quan trọng hay là session bỏ quên?
7. **Yêu cầu ứng dụng commit/rollback bình thường** khi có thể.
8. **Chỉ can thiệp cưỡng chế theo runbook được phê duyệt** nếu có nguy cơ rõ và owner đã được liên hệ/đánh giá.
9. **Quan sát vacuum lại** sau khi blocker kết thúc.
10. **Sửa nguyên nhân gốc:** transaction boundary, timeout, query, config replication, monitoring và retry policy.

### 25.1. pg_cancel_backend và pg_terminate_backend không giống nhau

Các hàm quản trị có mục đích khác:

- `pg_cancel_backend(pid)`: yêu cầu hủy **query hiện tại** của backend; không đồng nghĩa kết thúc session hoặc rollback toàn transaction trong mọi tình huống.
- `pg_terminate_backend(pid)`: yêu cầu kết thúc **backend session**; transaction chưa commit của session sẽ không được giữ làm transaction đã commit.

Với session `idle in transaction` **không có query đang chạy**, cancel query thường không giải quyết việc transaction vẫn mở. Terminate có thể phá kết nối, làm ứng dụng nhận lỗi và khiến transaction chưa commit bị rollback.

**Bài học không đưa câu lệnh terminate thực thi sẵn**, vì đó là thao tác phá trạng thái có thể gây gián đoạn. Trong production phải xác nhận PID mới nhất, quyền, owner và ảnh hưởng trước khi dùng. PID cũng có thể được tái sử dụng sau khi backend cũ kết thúc; đừng hành động dựa trên một danh sách PID đã cũ.

### 25.2. Không giết autovacuum để làm giảm tải một cách tùy tiện

Autovacuum là cơ chế bảo trì. Nếu nó đang chạy lâu, hãy xác định pha và lý do trước. Hủy lặp lại có thể làm tăng áp lực bloat/freeze. Có những trường hợp cần điều phối với DDL, nhưng phải có kế hoạch vận hành, không phải phản xạ mặc định.

### 25.3. Khóa và nguồn blocker có thể không phải cùng một session

Một session đang chặn VACUUM do lock khác với session giữ horizon khiến VACUUM không được dọn tuple. Trường hợp có thể cùng tồn tại nhưng **không đồng nhất**.

Nếu VACUUM chờ lock, cần phân tích lock holder; nếu VACUUM quét xong nhưng old tuples còn phải giữ, cần xem visibility horizon. Cách sửa của hai vấn đề khác nhau.

## 26. Runbook đọc-only: thu thập bằng chứng trước khi can thiệp

Các truy vấn dưới đây là **read-only** trong phạm vi những view/hàm giám sát được liệt kê. Chúng không dừng backend và không thay đổi table data.

### 26.1. Database và XID age

```sql
SELECT
    datname,
    age(datfrozenxid) AS xid_age
FROM pg_database
ORDER BY xid_age DESC;
```

### 26.2. Những transaction đang mở lâu

```sql
SELECT
    pid,
    datname,
    usename,
    application_name,
    state,
    clock_timestamp() - xact_start AS transaction_age,
    backend_xid,
    backend_xmin,
    CASE
        WHEN backend_xmin IS NOT NULL
            THEN age(backend_xmin)
        ELSE NULL
    END AS backend_snapshot_xid_age
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start;
```

### 26.3. Những bảng có dead tuples ước lượng lớn

```sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup,
    last_autovacuum,
    autovacuum_count
FROM pg_stat_user_tables
ORDER BY n_dead_tup DESC
LIMIT 20;
```

Không diễn giải `n_dead_tup` như phép đo chính xác trong thời gian thực; một bảng lớn có nhiều dead tuples nhưng autovacuum hoạt động bình thường có thể không phải sự cố khẩn cấp.

### 26.4. VACUUM đang thực hiện

```sql
SELECT
    pid,
    relid::regclass AS relation_name,
    phase,
    heap_blks_total,
    heap_blks_scanned,
    heap_blks_vacuumed
FROM pg_stat_progress_vacuum;
```

### 26.5. Replication slots

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

### 26.6. Prepared transactions

```sql
SELECT
    gid,
    prepared,
    owner,
    database
FROM pg_prepared_xacts
ORDER BY prepared;
```

### 26.7. Standby feedback trên primary

```sql
SELECT
    application_name,
    state,
    backend_xmin
FROM pg_stat_replication;
```

**Đọc kết quả dưới dạng tập hợp bằng chứng**, không cố chọn một hàng có timestamp lớn nhất rồi tuyên bố xong nguyên nhân. Nên so với thời điểm bloat bắt đầu, tốc độ UPDATE/DELETE, vacuum logs, config replication và XID horizon của từng nguồn.

## 27. Bảng quyết định theo triệu chứng

| Triệu chứng | Việc nên kiểm tra trước | Không nên làm ngay |
| --- | --- | --- |
| Dead tuples tăng dù autovacuum chạy | Snapshot/XID cũ, slot, feedback, write rate và vacuum logs. | Chạy `VACUUM FULL` trên production. |
| Table size tăng nhưng dead tuples đã giảm | Khả năng tái sử dụng khoảng trống, lịch sử bloat, index size. | Kết luận VACUUM vô dụng. |
| Session `idle in transaction` lâu | Snapshot/XID, locks, owner, transaction boundary. | Terminate mọi session theo tuổi một cách tự động. |
| Primary bloat khi báo cáo trên replica chạy lâu | `hot_standby_feedback`, `pg_stat_replication.backend_xmin`. | Tắt standby feedback mà không đánh giá conflict. |
| WAL directory phình to | Replication slots, restart_lsn, archive, replication lag. | Giả định WAL growth đồng nghĩa heap dead tuples. |
| `pg_prepared_xacts` có GID cũ | Coordinator, giao dịch 2PC chưa hoàn tất. | `ROLLBACK PREPARED` không xác minh. |
| XID age lớn | Autovacuum freeze, old XID holders, log anti-wraparound. | Tắt autovacuum hoặc chỉ tăng threshold. |
| VACUUM chờ lock lâu | Lock holders, `wait_event`, DDL, workload. | Nhầm với visibility horizon ngay lập tức. |
| `n_dead_tup` thay đổi thất thường | Statistics estimates, transaction snapshot khi đọc stats. | Dùng số đơn lẻ làm bằng chứng kết luận. |

## 28. Chiến lược giảm bloat sau khi giải quyết nguyên nhân

Sau khi transaction/horizon cũ đã hết cần, việc tiếp theo phụ thuộc quy mô bloat và mức ảnh hưởng:

### 28.1. VACUUM thông thường

Thường là điểm bắt đầu hợp lý:

```sql
VACUUM (VERBOSE, ANALYZE) mvcc_cleanup_lab.demo_rows;
```

Kết quả mong đợi là làm không gian trong relation có thể tái sử dụng và cập nhật thông tin liên quan theo điều kiện. Đừng yêu cầu kích thước file phải giảm ngay nếu muốn đánh giá thành công.

### 28.2. Để autovacuum duy trì trạng thái ổn định

Với bảng UPDATE liên tục, có thể cần:

- Giảm threshold/scale factor phù hợp kích thước và write rate.
- Điều phối worker/cost settings để vacuum không bị bỏ lại quá xa.
- Bảo đảm đủ I/O và không gian.
- Sửa transaction dài/replication feedback trước.
- Theo dõi kết quả trong thời gian đủ dài để biết có ổn định hay không.

Không nên chỉnh hàng chục tham số một lần rồi mất khả năng xác định cải thiện đến từ đâu.

### 28.3. VACUUM FULL và việc rewrite

`VACUUM FULL` là một lựa chọn khi thực sự cần thu nhỏ relation trên filesystem. Nhưng:

- Cần khóa mạnh và có thể chặn hoạt động trên bảng.
- Có thể tốn không gian đĩa bổ sung trong quá trình rewrite.
- Có thể tạo nhiều WAL/I/O.
- Phải lên lịch và đánh giá với replication, backup và hoạt động ứng dụng.
- Không sửa nguyên nhân gây bloat nếu transaction/ghi dữ liệu tiếp tục giữ horizon bất thường.

### 28.4. Index bloat và REINDEX

Trong một số tình huống index bloat đáng kể, `REINDEX` hoặc giải pháp xây dựng index phù hợp có thể giúp. Cú pháp và khả năng concurrent phụ thuộc loại index/server, còn thao tác có thể cần tài nguyên lớn.

Chỉ thực hiện sau khi xác định **index thực sự bị bloat** và có kế hoạch lock/space/availability. Không coi `REINDEX` là thay thế thường xuyên cho VACUUM hoặc một cách giải quyết snapshot cũ.

### 28.5. Đừng dùng DELETE để “dọn dead tuples”

`DELETE` tạo thêm trạng thái MVCC cần bảo trì; nó không phải công cụ loại bỏ trực tiếp các phiên bản hàng đã chết để giải quyết bloat. Nếu muốn xóa dữ liệu nghiệp vụ theo retention, cần chính sách DELETE/partitioning riêng, rồi vẫn cần VACUUM hoặc bảo trì tương ứng.

## 29. Phòng ngừa bằng kiến trúc và vận hành

### 29.1. Transaction ngắn nhưng đủ để bảo toàn invariant

Thiết kế một transaction chỉ chứa các thao tác phải atomic cùng nhau. Tránh kéo dài qua:

- Thời gian chờ HTTP hoặc message queue.
- Chờ người dùng trả lời.
- Stream dữ liệu chậm qua client.
- Chạy phép tính CPU dài không cần giữ snapshot.
- Sleep/retry không có giới hạn.

“Càng ngắn càng tốt” phải đi cùng “vẫn đủ để đúng về nghiệp vụ”. Đừng tách transaction thanh toán đang cần invariant thành nhiều commit độc lập nếu không có cơ chế nhất quán thay thế.

### 29.2. Timeouts có chủ đích

Sử dụng cấu hình session/role/database thích hợp để giới hạn:

- Câu SQL chạy quá lâu.
- Chờ khóa quá lâu.
- Session idle trong transaction quá lâu.
- Tuổi transaction tổng thể khi major hỗ trợ và phù hợp.

Timeout phải đi kèm retry/idempotency và khả năng quan sát lỗi phía ứng dụng. Không đặt timeout ngẫu nhiên nhỏ hơn thời gian hợp lệ của batch.

### 29.3. Kiểm soát workflow nhập dữ liệu

Thay vì mở một transaction và nhập cả trăm triệu hàng trong một chu kỳ, cân nhắc:

- Nạp vào staging.
- Validate theo tập.
- Chia thành chunk có điểm kiểm soát rõ.
- Dùng khóa idempotency để retry an toàn.
- Chốt trạng thái batch khi hoàn tất.

Việc chia chunk có thể đổi yêu cầu atomic toàn batch; cần thỏa thuận lại với nghiệp vụ trước khi triển khai.

### 29.4. Giám sát replication

Theo dõi:

- Standby feedback và độ dài truy vấn ở replica.
- Replication lag, slot active/inactive.
- `xmin`, `catalog_xmin` và `restart_lsn` theo loại slot.
- WAL disk usage và retention policy.
- Consumer/CDC owner, tình trạng reconnect/resync.

Không sửa bloat ở primary bằng cách làm consumer mất dữ liệu downstream.

### 29.5. Chỉ số cảnh báo nên có

Một dashboard DBA có thể chứa:

| Nhóm | Chỉ số gợi ý |
| --- | --- |
| Transactions | Số session `idle in transaction`, tuổi transaction lớn nhất, phân bố tuổi. |
| Visibility horizon | `backend_xmin`/`backend_xid` già, replication feedback, slot xmin, prepared xacts. |
| Vacuum | `last_autovacuum`, autovacuum count, các phiên đang chạy và pha. |
| Bảng | `n_dead_tup` ước lượng, UPDATE/DELETE rate, table/index sizes. |
| XID safety | `age(datfrozenxid)`, `age(relfrozenxid)`, cảnh báo wraparound. |
| Capacity | Disk free, WAL growth, tốc độ mở rộng relation. |
| Application | Thời gian transaction theo service, lỗi timeout, số pool connections. |

Quan trọng là **theo xu hướng** và biết workload bình thường, không chỉ thiết lập một ngưỡng cứng duy nhất cho mọi bảng.

## 30. Các lỗi suy luận và thao tác phổ biến

### Lỗi 1. “UPDATE xong thì tuple cũ không còn”

Sai. PostgreSQL thường giữ old tuple versions để bảo toàn MVCC; VACUUM chỉ dọn khi đã an toàn.

### Lỗi 2. “Transaction A không đọc lại bảng thì có thể xóa version cũ”

Không chắc. Nếu A giữ snapshot có quyền nhìn thấy phiên bản cũ, hệ quản trị không được dựa vào dự đoán người dùng sẽ không đọc lại để xóa dữ liệu.

### Lỗi 3. “Mọi idle in transaction đều giữ snapshot cũ”

Không. Ở READ COMMITTED, snapshot dùng cho statement có thể được thả sau statement. Cần kiểm tra `backend_xmin`, `backend_xid` và bối cảnh.

### Lỗi 4. “backend_xmin NULL nghĩa là session vô hại hoàn toàn”

Không đủ cơ sở. Có thể còn XID, locks hoặc tình trạng khác; kiểm tra thêm `backend_xid` và nguồn giữ horizon ngoài backend.

### Lỗi 5. “Transaction_age cao nhất chắc chắn là blocker lớn nhất”

Tuổi theo phút không đồng nghĩa XID horizon già nhất. Một session ngắn hơn nhưng snapshot/XID cũ hơn hoặc một replication slot không active cũng có thể quan trọng.

### Lỗi 6. “Autovacuum chạy là mọi dead tuple phải biến mất”

Không. VACUUM chỉ dọn các tuple đã đủ điều kiện theo visibility horizon; autovacuum còn có nhiều nhiệm vụ bảo trì khác.

### Lỗi 7. “n_dead_tup là phép đếm chính xác theo thời gian thực”

Không. Đây là estimate từ statistics và có thể trễ/thay đổi theo cập nhật thống kê.

### Lỗi 8. “VACUUM thành công phải làm file nhỏ lại”

Không. Không gian sau VACUUM thường được tái sử dụng nội bộ. File shrinking có cơ chế/điều kiện riêng.

### Lỗi 9. “VACUUM FULL là giải pháp đầu tiên”

Không. Nó có thể chặn hệ thống và không sửa nguyên nhân gốc nếu vẫn có horizon cũ. Phải điều tra trước.

### Lỗi 10. “Tăng autovacuum worker sẽ vượt được old snapshot”

Không. Tăng tài nguyên không cho phép bỏ qua MVCC visibility.

### Lỗi 11. “REINDEX sửa được mọi vấn đề dead tuples”

Không. Index rewrite không thay thế heap cleanup hay xử lý transaction horizon.

### Lỗi 12. “Xóa replication slot inactive là an toàn”

Không. Slot có thể là điểm tiếp tục CDC/replication cần thiết; xóa sai có thể buộc resync.

### Lỗi 13. “WAL lag bằng dead heap bloat”

Không. `restart_lsn` liên quan WAL retention; `xmin`/`catalog_xmin` liên quan cleanup horizon. Có liên hệ nhưng không đồng nhất.

### Lỗi 14. “Không có backend cũ nên không còn blocker”

Không. Prepared transactions hoặc replication slots/feedback có thể giữ ranh giới cần điều tra.

### Lỗi 15. “COMMIT PREPARED một GID cũ cho xong”

Không. Đây có thể là transaction 2PC của coordinator khác; commit/rollback sai gây inconsistency.

### Lỗi 16. “SELECT một lần sẽ luôn giữ snapshot đến khi connection đóng”

Không đúng nói chung. Vòng đời snapshot phụ thuộc transaction scope, isolation, cursor và hành vi client.

### Lỗi 17. “VACUUM trong BEGIN sẽ là cùng transaction để thử”

Không. VACUUM thông thường không được chạy trong một transaction block tường minh. Thí nghiệm hai session yêu cầu B chạy VACUUM bên ngoài BEGIN.

### Lỗi 18. “Chỉ cần cancel một query là transaction idle biến mất”

Không. Hủy query hiện tại không đồng nghĩa transaction/session được kết thúc; `idle in transaction` cần được giải quyết ở ranh giới giao dịch.

### Lỗi 19. “Terminate session luôn an toàn vì rollback”

Không. Terminate gây lỗi ứng dụng, hủy công việc chưa commit, có thể tác động tới pipeline/người dùng. Cần owner và runbook.

### Lỗi 20. “Giảm transaction timeout thật thấp sẽ chữa mọi bloat”

Không. Timeout quá ngắn có thể phá workload hợp lệ, làm tăng retry và ảnh hưởng dịch vụ.

### Lỗi 21. “Long transaction chỉ gây tốn ổ đĩa”

Không. Nó có thể ảnh hưởng latency, lock contention, vacuum, freeze, cache và nguy cơ wraparound.

### Lỗi 22. “Không có DELETE nên không có dead tuples”

Sai. UPDATE cũng có thể sinh phiên bản hàng cũ; transaction rollback cũng có thể để lại tuple cần dọn.

### Lỗi 23. “HOT update là không sinh tuple cũ”

Sai. HOT chủ yếu giảm nhu cầu tạo index entries mới khi điều kiện phù hợp; MVCC versions vẫn tồn tại.

### Lỗi 24. “Đổi isolation level tùy tiện là cách tối ưu”

Không. Isolation phải đáp ứng tính đúng đắn nghiệp vụ; hạ mức có thể thay đổi kết quả/consistency. Thường cần sửa transaction boundary và workload.

## 31. Bài tập thực hành

Các bài dựa trên schema `mvcc_cleanup_lab` và các system views. Với bài cần hai session, hãy bảo đảm cả hai thực sự dùng **cùng database nhưng khác kết nối**. Các bài liên quan kill backend hoặc sửa replica chỉ yêu cầu **phân tích**, không thao tác phá hoại.

### Bài 1. Vì sao UPDATE tạo nhiều phiên bản?

Giải thích vì sao PostgreSQL không xóa ngay tuple cũ khi một transaction khác UPDATE rồi commit.

### Bài 2. Thiết kế hai session

Nêu các bước tối thiểu để chứng minh session A ở `REPEATABLE READ` còn thấy `generation=0` trong khi B đã thấy `generation=1`.

### Bài 3. VACUUM khi A còn mở

Nếu B chạy `VACUUM (VERBOSE)` khi A vẫn giữ snapshot cũ, tại sao VACUUM có thể hoàn thành nhưng không dọn được mọi old tuple versions?

### Bài 4. Kết thúc A

Sau khi A `COMMIT`, B chạy VACUUM lại. Điều kiện gì khiến cleanup các phiên bản cũ trở nên khả thi hơn?

### Bài 5. READ COMMITTED

Một session chỉ chạy SELECT trong transaction READ COMMITTED rồi idle 30 phút. Có thể kết luận chắc chắn nó giữ snapshot của SELECT suốt 30 phút không?

### Bài 6. Backend XID khác backend xmin

Phân biệt `backend_xid` và `backend_xmin`, giải thích vì sao `xact_start` dài chưa đủ để kết luận giữ dead tuples.

### Bài 7. Đọc pg_stat_activity

Viết truy vấn hiển thị PID, trạng thái, tuổi transaction và `backend_xmin` của các session có transaction đang mở.

### Bài 8. Dead tuples estimate

Viết truy vấn lấy `n_dead_tup`, `last_autovacuum` và `autovacuum_count` của `mvcc_cleanup_lab.demo_rows`. Giải thích vì sao số này có thể trễ.

### Bài 9. Kích thước vật lý

So sánh `pg_relation_size`, `pg_indexes_size` và `pg_total_relation_size`. Tại sao tổng dung lượng không luôn giảm sau VACUUM?

### Bài 10. HOT update

Tại sao việc UPDATE một cột index thường làm giảm khả năng HOT? HOT có loại bỏ nhu cầu tuân thủ snapshot không?

### Bài 11. Autovacuum threshold

Giả định threshold 50, scale factor 0.1 và ước lượng 200.000 hàng. Ngưỡng cơ bản cho dead tuples là bao nhiêu?

### Bài 12. Freezing

Ý nghĩa của `age(datfrozenxid)` là gì? Đó là giây/phút hay transaction ID age?

### Bài 13. Tìm VACUUM đang chạy

Viết truy vấn hiển thị PID, tên relation, phase và số heap blocks đã quét của VACUUM.

### Bài 14. Standby feedback

Giải thích cách `hot_standby_feedback` có thể giảm recovery conflict trên replica nhưng khiến primary giữ dead tuples lâu hơn.

### Bài 15. Replication slot

Phân biệt ý nghĩa của `restart_lsn`, `xmin` và `catalog_xmin`. Vì sao không nên xóa ngay slot `active=false`?

### Bài 16. Prepared transaction

`pg_stat_activity` không có session cũ nhưng XID horizon vẫn lùi. View nào giúp tìm prepared transactions chưa giải quyết?

### Bài 17. Idle timeout

`idle_in_transaction_session_timeout` giải quyết được mọi long-running query không? Điều gì xảy ra nếu timeout kết thúc một session đang giữ transaction chưa commit?

### Bài 18. Xử lý backend đáng ngờ

Phân biệt `pg_cancel_backend` với `pg_terminate_backend` và nêu vì sao không nên terminate tự động chỉ dựa trên tuổi transaction.

### Bài 19. Chẩn đoán theo triệu chứng

Một bảng có `autovacuum_count` tăng, `n_dead_tup` tăng, và một backend giữ `backend_xmin` cũ. Đề xuất ba bước điều tra trước khi thay đổi cấu hình autovacuum.

### Bài 20. Transaction trong Java

Một method mở transaction, đọc vài bảng, gọi API ngoài 90 giây rồi mới commit. Nêu nguy cơ và cách cải tiến mà vẫn bảo đảm invariant nghiệp vụ.

### Bài 21. VACUUM FULL

Trên production có bảng lớn và ứng dụng không chấp nhận downtime. Có nên chạy `VACUUM FULL` ngay khi thấy bloat không? Điều gì cần đánh giá?

### Bài 22. WAL tăng

Khi `pg_wal` tăng nhanh và logical replication consumer dừng, những trường nào của `pg_replication_slots` nên xem? Tại sao không kết luận chỉ số đó là heap bloat?

### Bài 23. MVCC và khóa

Phân biệt một transaction giữ khóa làm query khác đợi với một transaction giữ snapshot làm VACUUM chưa thể dọn tuple.

### Bài 24. Thiết kế dashboard

Chọn tối thiểu sáu chỉ số từ nhiều nhóm (transactions, vacuum, size, XID age, replication, application) để theo dõi nguy cơ cleanup bị trì hoãn.

## 32. Gợi ý lời giải

### Đáp án 1. MVCC giữ phiên bản cho snapshot cũ

Một transaction đã lấy snapshot trước UPDATE có thể vẫn cần tuple phiên bản cũ để đọc nhất quán. Chỉ khi không còn snapshot/transaction phù hợp cần nó thì VACUUM mới được loại bỏ an toàn.

### Đáp án 2. Hai session

Session A:

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ;
SELECT MIN(generation), MAX(generation)
FROM mvcc_cleanup_lab.demo_rows;
-- Giữ transaction mở.
```

Session B:

```sql
UPDATE mvcc_cleanup_lab.demo_rows
SET generation = generation + 1;

SELECT MIN(generation), MAX(generation)
FROM mvcc_cleanup_lab.demo_rows;
```

Quay lại A để SELECT lần nữa trước khi COMMIT. A có thể vẫn thấy `0`, B thấy `1`. Ví dụ giả định bảng ở trạng thái ban đầu với generation=0.

### Đáp án 3. Không xóa version còn cần

VACUUM phải giữ old tuple versions còn cần cho snapshot A. Nó vẫn có thể hoàn thành quét và các công việc bảo trì khác, nhưng không được phá dữ liệu mà A có thể đọc.

### Đáp án 4. Horizon được giải phóng

Khi A kết thúc, snapshot của A không còn. Nếu không còn snapshot/XID holder hay nguồn giữ horizon khác, VACUUM ở B có thể dọn những old tuples trước đó bị chặn.

### Đáp án 5. READ COMMITTED

Không. Snapshot dùng cho một statement READ COMMITTED có thể được thả sau statement. Nhưng transaction mở vẫn có thể giữ lock, XID hoặc nguồn lực khác; phải kiểm tra state và metadata thực tế.

### Đáp án 6. XID và xmin

`backend_xid` là top-level XID khi backend có; `backend_xmin` phản ánh xmin horizon của snapshot backend đang giữ khi có. `xact_start` là thời gian mở transaction theo đồng hồ; chỉ số này một mình không chứng minh snapshot cũ đang được giữ.

### Đáp án 7. Truy vấn giám sát

```sql
SELECT
    pid,
    state,
    clock_timestamp() - xact_start AS transaction_age,
    backend_xmin
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start;
```

### Đáp án 8. Thống kê dead tuples

```sql
SELECT
    n_dead_tup,
    last_autovacuum,
    autovacuum_count
FROM pg_stat_user_tables
WHERE schemaname = 'mvcc_cleanup_lab'
  AND relname = 'demo_rows';
```

`n_dead_tup` là estimate theo hệ thống thống kê, không phải exact real-time heap count.

### Đáp án 9. Kích thước

```sql
SELECT
    pg_relation_size('mvcc_cleanup_lab.demo_rows') AS heap_bytes,
    pg_indexes_size('mvcc_cleanup_lab.demo_rows') AS index_bytes,
    pg_total_relation_size('mvcc_cleanup_lab.demo_rows') AS total_bytes;
```

VACUUM thông thường làm khoảng trống tái sử dụng, không nhất thiết làm file vật lý nhỏ đi.

### Đáp án 10. HOT

Nếu cột index đổi, PostgreSQL thường phải cập nhật index entries và không còn điều kiện HOT phù hợp. HOT vẫn sinh row versions trong heap và vẫn bị ràng buộc bởi MVCC visibility.

### Đáp án 11. Ngưỡng cơ bản

`50 + 0.1 × 200000 = 20050` dead tuples theo mô hình cơ bản. Còn phụ thuộc các điều kiện/điều chỉnh autovacuum khác của server.

### Đáp án 12. XID age

`age(datfrozenxid)` là độ tuổi logic theo transaction IDs, không phải elapsed time theo phút hoặc ngày. Nó là tín hiệu theo dõi an toàn wraparound.

### Đáp án 13. VACUUM progress

```sql
SELECT
    pid,
    relid::regclass AS relation_name,
    phase,
    heap_blks_total,
    heap_blks_scanned
FROM pg_stat_progress_vacuum;
```

### Đáp án 14. Hot standby feedback

Replica có thể báo horizon cho primary để giảm xung đột replay với truy vấn replica cần old tuples. Primary vì thế có thể trì hoãn cleanup, tăng bloat; khi tắt feedback, query replica dài có thể bị hủy theo conflict policy.

### Đáp án 15. Slot fields

`restart_lsn` liên quan WAL retention; `xmin` giữ horizon dữ liệu khi có; `catalog_xmin` liên quan catalog versions phục vụ decoding. Slot không active vẫn có thể giữ mốc cần thiết và thuộc consumer phải tiếp tục; xóa sai có thể mất khả năng resume.

### Đáp án 16. Prepared transactions

```sql
SELECT gid, prepared, owner, database, transaction
FROM pg_prepared_xacts;
```

Không tự commit/rollback GID chưa xác định owner.

### Đáp án 17. Idle timeout

Không. Nó nhắm tới session idle trong transaction, không phải mọi query đang active. Nếu timeout kết thúc session có transaction chưa commit, công việc chưa commit sẽ rollback, có thể gây lỗi phía ứng dụng và cần retry theo chính sách.

### Đáp án 18. Cancel và terminate

Cancel yêu cầu hủy query hiện tại; terminate yêu cầu kết thúc backend/session. Terminate có thể rollback transaction chưa commit và phá hoạt động service. Phải xác định owner, mục tiêu, horizon và ảnh hưởng, không dựa vào một timestamp đơn.

### Đáp án 19. Ba bước điều tra

1. Dùng `pg_stat_activity` xác định `backend_xmin`/`backend_xid`, trạng thái và owner của backend cũ.
2. Kiểm tra `pg_replication_slots`, `pg_stat_replication`, `pg_prepared_xacts` để loại trừ nguồn khác.
3. Đối chiếu `pg_stat_user_tables`, VACUUM VERBOSE/progress, kích thước heap/index và write rate để biết dead versions có thực bị giữ do horizon và mức độ ảnh hưởng.

Sau đó mới chọn phương án ứng dụng kết thúc transaction và quan sát vacuum trở lại.

### Đáp án 20. Java transaction boundary

Giữ transaction mở trong 90 giây chờ API có thể giữ snapshot/XID/locks và chiếm pool connection. Cải tiến bằng cách thực hiện API chậm ngoài transaction nếu hợp đồng nghiệp vụ cho phép, dùng transaction ngắn cho đọc/ghi cần atomic, triển khai khóa/version check và retry để bảo toàn invariant.

### Đáp án 21. VACUUM FULL

Không chạy ngay. Cần xem blocker còn tồn tại không, khả năng tái sử dụng free space, yêu cầu giảm file size, disk headroom, lock/downtime, replication lag và các phương án bảo trì ít gián đoạn hơn phù hợp với server.

### Đáp án 22. WAL tăng

Xem `active`, `restart_lsn`, `confirmed_flush_lsn` và trạng thái consumer của logical slot; đồng thời quan sát `xmin`/`catalog_xmin` nếu điều tra cleanup horizon. WAL retention và old tuple cleanup là hai cơ chế liên quan nhưng không đồng nhất.

### Đáp án 23. Khóa và horizon

Lock blocking khiến câu SQL khác phải đợi lấy khóa; old snapshot/XID horizon khiến VACUUM chưa được xóa một số phiên bản hàng dù nó vẫn có thể chạy. Cần quan sát wait events/locks cho trường hợp thứ nhất, visibility metadata và vacuum output cho trường hợp thứ hai.

### Đáp án 24. Dashboard

Ví dụ tám chỉ số:

1. Số session `idle in transaction` theo service.
2. Tuổi transaction lớn nhất và thứ hạng backend có `backend_xmin` cũ.
3. `n_dead_tup` ước lượng theo bảng.
4. Tuổi `last_autovacuum` và `autovacuum_count`.
5. `pg_total_relation_size`/index size theo thời gian.
6. `age(datfrozenxid)` và bảng có `age(relfrozenxid)` cao.
7. Slot `restart_lsn` lag và `xmin/catalog_xmin`.
8. `pg_stat_replication.backend_xmin` và long-running queries ở standby.

Dashboard cần giữ thêm tốc độ UPDATE/DELETE và cảnh báo disk/WAL để đặt những giá trị trên trong đúng ngữ cảnh.

## 33. Tình huống tổng hợp: sự cố sau một đợt ETL

Giả định đội vận hành quan sát:

```text
Ngày đầu:
  orders có 2 triệu hàng live
  autovacuum chạy định kỳ
  heap size khá ổn định

Sau khi triển khai ETL mới:
  một worker mở transaction REPEATABLE READ
  worker đọc orders rồi chờ API ngoài rất lâu
  nhiều dịch vụ khác liên tục UPDATE trạng thái đơn

Một ngày sau:
  heap/index tăng size
  n_dead_tup estimate tăng
  last_autovacuum vẫn được cập nhật
  một session idle in transaction giữ backend_xmin cũ
```

### 33.1. Chẩn đoán

Không kết luận chỉ từ một metric. Kết hợp:

- `pg_stat_activity` xác nhận worker, `xact_start` và `backend_xmin`.
- `pg_stat_user_tables` cho thấy UPDATE rate, estimate dead tuples, autovacuum history.
- `pg_relation_size` và `pg_indexes_size` cho thấy phình vật lý.
- `pg_replication_slots`/`pg_stat_replication`/`pg_prepared_xacts` để kiểm tra những horizon khác.
- Log VACUUM và tình trạng I/O/disk.

### 33.2. Ứng phó an toàn

1. Báo owner ứng dụng/ETL, xác nhận transaction đó có thể kết thúc hoặc retry không.
2. Ưu tiên worker **commit/rollback đúng luồng ứng dụng**, thay vì terminate không rõ ràng.
3. Nếu rủi ro vận hành nghiêm trọng và cần can thiệp, theo runbook có phân quyền/đánh giá tác động.
4. Sau khi blocker được xử lý, quan sát autovacuum hoặc chạy VACUUM có kiểm soát.
5. Theo dõi n_dead_tup estimate, table size, XID age và disk headroom.
6. Sửa worker: không giữ snapshot xuyên API call, tách transaction scope, thiết lập timeout và logging.

### 33.3. Kết quả mong đợi

Khi blocker hết:

- Các old tuple versions đủ điều kiện có thể được VACUUM dọn.
- Không gian trong relation có thể được tái sử dụng.
- Tốc độ phình to có thể giảm nếu workload và autovacuum cân bằng lại.
- Kích thước file **không bắt buộc trở về mức ban đầu**.

Với hệ thống bị bloat lớn sẵn, một quyết định riêng về physical compaction có thể cần thiết. Đừng lấy “disk file chưa thu nhỏ” làm lý do cho rằng việc xử lý root cause không có tác dụng.

## 34. Checklist xác định nguyên nhân và xử lý

Trước khi đưa ra kết luận “giao dịch chưa kết thúc làm VACUUM không dọn được”:

1. **Biết đối tượng:** bảng nào, workload nào, số hàng live và tốc độ update/delete ra sao?
2. **Biết thời điểm:** bloat bắt đầu khi nào, tương quan deployment/job nào?
3. **Xem snapshot/XID:** `backend_xmin`, `backend_xid`, `xact_start`, `state`.
4. **Kiểm tra isolation:** transaction READ COMMITTED hay REPEATABLE READ, có cursor/portal không?
5. **Kiểm tra replication:** `hot_standby_feedback`, replication slots, `xmin/catalog_xmin` và WAL lag.
6. **Kiểm tra 2PC:** prepared transaction nào bị giữ lâu?
7. **Đọc thống kê đúng nghĩa:** `n_dead_tup` chỉ estimate; `last_autovacuum` không bảo đảm mọi tuple đã dọn.
8. **Xem tiến độ VACUUM:** đang quét, vacuum index hay bị chờ khóa?
9. **Xem XID age:** có nguy cơ freeze/wraparound đang tăng không?
10. **Phân biệt reuse và shrink:** size không giảm không luôn đồng nghĩa vacuum không giúp.
11. **Đánh giá owner và tác động:** không terminate transaction quan trọng chưa có kế hoạch.
12. **Cẩn thận 2PC/replication:** không xóa slot hay kết thúc GID chưa hiểu.
13. **Có kế hoạch quan sát lại:** sau khi blocker hết, verify vacuum tiến triển và workload ổn định.
14. **Sửa nguyên nhân gốc:** rút ngắn transaction, timeout hợp lý, sửa code pooling/streaming.
15. **Đảm bảo không phá nghiệp vụ:** mọi thay đổi isolation, retry, batch boundaries và replication policy cần được đánh giá.

## 35. Tổng kết

MVCC cho phép PostgreSQL phục vụ nhiều transaction đồng thời bằng những phiên bản hàng có quy tắc hiển thị theo snapshot. Cơ chế này khiến việc dọn dẹp dữ liệu có điều kiện quan trọng: **VACUUM chỉ được loại bỏ một phiên bản hàng khi không còn transaction/snapshot hợp lệ nào cần nó**.

Những điều cần nhớ:

- **UPDATE/DELETE không xóa ngay mọi tuple cũ.** Phiên bản đã cũ với snapshot mới vẫn có thể cần cho snapshot cũ.
- **Transaction mở lâu có thể giữ cleanup horizon.** Điều đó có thể làm heap/index bloat, tăng I/O/disk và tạo áp lực freezing.
- **Không phải mọi session idle in transaction đều đang giữ snapshot cũ.** Xem `backend_xmin`, `backend_xid`, isolation và nguồn lực thực tế; thời gian `xact_start` chỉ là một tín hiệu.
- **Autovacuum vẫn có thể chạy mà chưa dọn được old tuples.** Tăng số worker hay giảm scale factor không bỏ qua quy tắc MVCC.
- **`n_dead_tup` là estimate** và VACUUM thông thường thường **tái sử dụng không gian trong file** chứ không thu nhỏ file ngay.
- **Nguồn giữ horizon không chỉ là application backend.** Standby feedback, replication slots và prepared transactions cũng cần được giám sát.
- **Freezing và XID age** khiến việc xử lý old transactions còn là vấn đề an toàn lâu dài, không chỉ hiệu năng.
- **Không xử lý vội bằng VACUUM FULL, terminate backend hay xóa replication slot.** Hãy xác định owner, nguyên nhân, ảnh hưởng và hướng phục hồi trước.
- **Cách phòng ngừa bền vững** là transaction có phạm vi phù hợp, timeout được thiết kế tốt, xử lý lỗi/rollback đúng, monitoring và cấu hình vacuum/replication theo workload.

Một nguyên tắc vận hành hữu ích:

> Khi VACUUM chưa thể dọn các phiên bản cũ, hãy hỏi **“Ai hoặc cơ chế nào còn quyền cần nhìn thấy chúng?”** trước khi hỏi **“Làm sao ép VACUUM chạy mạnh hơn?”**.

Đó là điểm mấu chốt để bảo trì PostgreSQL đúng theo MVCC mà vẫn giữ tính toàn vẹn và tính sẵn sàng của hệ thống.

