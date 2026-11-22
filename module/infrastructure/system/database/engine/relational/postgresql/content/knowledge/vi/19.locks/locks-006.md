# Phát hiện chuỗi chặn bằng pg_locks và pg_blocking_pids

Một truy vấn PostgreSQL bỗng chạy hàng chục giây dù ngày thường chỉ mất vài mili giây. CPU không cao, `EXPLAIN` không cho thấy kế hoạch quá tệ, và bảng chỉ có vài hàng. Có thể câu lệnh **đang chờ một khóa** (*lock wait*). Điều khó hơn là xác định **ai đang chặn ai**: transaction A giữ khóa, transaction B chờ A nhưng đồng thời giữ khóa khiến transaction C phải chờ B. Nếu chỉ nhìn C hoặc kill nhầm B, bạn có thể bỏ lỡ nguyên nhân gốc và gây rollback không cần thiết.

PostgreSQL cung cấp hai công cụ cốt lõi:

- **`pg_catalog.pg_locks`:** view liệt kê những yêu cầu khóa đã được cấp hoặc đang chờ, kèm loại khóa, chế độ khóa, đối tượng, PID và các metadata liên quan.
- **`pg_catalog.pg_blocking_pids(pid)`:** hàm trả mảng PID của những tiến trình đang **chặn một PID cụ thể** theo cơ chế lock manager, kể cả một số blocker xếp trước trong hàng đợi.

Khi kết hợp với **`pg_catalog.pg_stat_activity`**, bạn có thể trả lời: câu SQL nào đang chờ, chờ từ lúc nào, blocker đang chạy hay đã `idle in transaction`, có một hay nhiều blocker, và chuỗi chặn đi qua những backend nào.

Bài này sẽ hướng dẫn:

1. Hiểu **waiter**, **blocker**, **direct blocker**, **upstream/root blocker**, **wait-for graph** và **chuỗi chặn**.
2. Phân biệt các loại khóa PostgreSQL, đặc biệt **relation lock**, **transactionid lock**, **tuple lock** và **advisory lock**.
3. Đọc đúng các trường `locktype`, `mode`, `granted`, `waitstart`, `pid` và `fastpath` trong `pg_locks`.
4. Dùng `pg_blocking_pids()` để lấy **cạnh chặn trực tiếp** mà không tự suy đoán sai từ một phép self-join `pg_locks`.
5. Viết truy vấn **sơ đồ quan hệ waiter → blocker**, truy vết **nhiều tầng** bằng recursive CTE và nhận diện đầu chuỗi khi có thể.
6. Tái hiện **row-lock contention**, **chuỗi A → B → C**, **hàng đợi DDL** và **deadlock** bằng nhiều session.
7. Nhận diện blocker **idle in transaction**, prepared transaction và session-level advisory lock.
8. Đánh giá khi nào nên chờ, rollback, `pg_cancel_backend`, `pg_terminate_backend` hay sửa ứng dụng.
9. Thiết lập timeout, quan sát bằng `pg_stat_activity` và áp dụng vào Java/JDBC/connection pool.

> **Cảnh báo vận hành:** Các ví dụ cố ý tạo lock wait và có thể giữ transaction mở. Chỉ chạy ở database lab, không chạy trên bảng production. Không sao chép PID từ ảnh/log cũ để gửi `pg_terminate_backend`. Việc hủy backend có thể rollback nghiệp vụ đang xử lý, gây lỗi ứng dụng và ảnh hưởng đến dịch vụ; thao tác này phải được kiểm tra/ủy quyền theo quy trình của hệ thống.

## 1. Khóa là gì và tại sao truy vấn phải chờ?

PostgreSQL sử dụng nhiều cơ chế khóa để phối hợp công việc đồng thời và bảo vệ tính đúng đắn dữ liệu. Một giao dịch muốn sửa cùng hàng với giao dịch khác có thể cần **chờ** cho tới khi giao dịch kia commit hoặc rollback. Một lệnh thay đổi schema có thể cần khóa bảng mạnh, trong khi một giao dịch chỉ đọc đang giữ khóa bảng loại yếu hơn.

Hình dung:

```text
Session A                                    Session B
---------------------------------------      --------------------------------
BEGIN;
UPDATE products SET quantity=8
 WHERE id=1;
-- Giữ transaction mở
                                             UPDATE products SET quantity=9
                                              WHERE id=1;
                                             -- Đang chờ
COMMIT;
                                             -- B có thể tiếp tục
```

**Điểm quan trọng:** Câu `UPDATE` của A đã chạy xong không có nghĩa những khóa của transaction được giải phóng ngay. Nhiều khóa được giữ **cho tới cuối transaction**. Nếu A mở transaction rồi ngồi chờ input từ ứng dụng, B vẫn có thể bị chặn.

### Một số nguyên nhân chờ phổ biến

- Hai transaction cùng `UPDATE`/`DELETE` một hàng.
- `SELECT ... FOR UPDATE`/`FOR NO KEY UPDATE` tranh chấp khóa hàng.
- `ALTER TABLE` cần `AccessExclusiveLock` nhưng đang có query/transaction giữ `AccessShareLock`.
- `CREATE INDEX` và các thao tác DDL cần phối hợp với writer.
- Kiểm tra foreign key hoặc unique constraint phải chờ trạng thái transaction khác.
- Advisory locks được ứng dụng lấy nhưng chưa nhả.
- Transaction đã `PREPARE TRANSACTION` còn giữ khóa mà không còn backend bình thường.

Không phải mọi sự chậm đều do lock. I/O, network, CPU, buffer contention và nhiều loại wait khác cũng gây chậm. Trước hết cần xác định **đúng kiểu chờ**.

## 2. Các thuật ngữ trong wait-for graph

| Thuật ngữ | Ý nghĩa |
|---|---|
| **Waiter / blocked backend** | Backend hiện chưa được cấp khóa cần thiết vì một hoặc nhiều blocker. |
| **Blocker / blocking backend** | Backend giữ khóa xung đột hoặc đứng trước trong hàng đợi, khiến waiter chưa thể tiến lên. |
| **Direct blocker** | Backend đang trực tiếp chặn một waiter theo quy tắc lock manager. |
| **Upstream blocker** | Backend chặn một blocker khác ở tầng phía trên. |
| **Root blocker** | Điểm cuối của chuỗi chặn, không có blocker phía trên **trong đồ thị quan sát được**. |
| **Wait-for graph** | Đồ thị có các nút backend và cạnh `waiter → blocker`. |
| **Blocking chain** | Đường đi gồm nhiều cạnh, chẳng hạn `C → B → A`. |
| **Deadlock** | Chu trình phụ thuộc giữa các transaction/khóa, chẳng hạn `A → B → A`. |

Một chuỗi đơn giản:

```text
   C ── waits for ──► B ── waits for ──► A
   │                  │                  │
   │                  │                  └── Giữ lock gây chặn B
   │                  └── Vừa chờ A, vừa giữ lock gây chặn C
   └── Truy vấn của C đang chờ

   Direct blocker của C = B
   Root/upstream blocker của C = A
```

Một waiter có thể có **nhiều blocker trực tiếp**, và một blocker có thể chặn **nhiều waiter**. Vì vậy đồ thị không nhất thiết là một danh sách tuyến tính duy nhất.

### “Root blocker” là khái niệm từ đồ thị quan sát

Nếu kết quả cho thấy A không có blocker, ta có thể gọi A là **đầu chuỗi đang quan sát**. Điều đó không chứng minh A là “nguyên nhân gốc nghiệp vụ”; A có thể đang chờ remote API, client, network hoặc một tài nguyên không phải heavyweight lock. Để xử lý triệt để còn cần biết **vì sao transaction của A chưa kết thúc**.

## 3. Phân biệt lock wait với các kiểu wait khác

`pg_stat_activity` có các trường:

- `state`: trạng thái của backend, ví dụ `active`, `idle`, `idle in transaction`.
- `wait_event_type`: loại sự kiện chờ, có thể là `Lock`, `IO`, `Client`, `LWLock`... tùy trường hợp và phiên bản.
- `wait_event`: sự kiện cụ thể.

Truy vấn quan sát:

```sql
SELECT
    pid,
    usename,
    application_name,
    state,
    wait_event_type,
    wait_event,
    query_start,
    xact_start
FROM pg_catalog.pg_stat_activity
WHERE datname = current_database()
ORDER BY pid;
```

Một backend có:

```text
state = active
wait_event_type = Lock
```

là dấu hiệu mạnh rằng câu lệnh đang chờ khóa do cơ chế lock tương ứng. Ngược lại, backend `idle in transaction` có thể **không đang chờ khóa nào**, nhưng lại là **blocker** vì giữ khóa từ transaction chưa kết thúc.

### Hai chiều phải đọc cùng nhau

**Waiter:**

```text
state = active
wait_event_type = Lock
query = UPDATE ...
```

**Blocker:**

```text
state = idle in transaction
wait_event_type = Client (có thể)
query = UPDATE ... trước đó
```

Backend blocker có thể đang **đợi client gửi lệnh tiếp theo**, trong khi vẫn giữ lock. Việc tìm truy vấn có `wait_event_type='Lock'` chỉ cho bạn phía **đang chờ**, không nhất thiết cho phía **đang giữ**.

## 4. Chuẩn bị môi trường lab

Tạo schema và một bảng nhỏ đủ để tạo tranh chấp row-level locks:

```sql
CREATE SCHEMA IF NOT EXISTS lesson_lockchain;

CREATE TABLE lesson_lockchain.inventory (
    item_id INTEGER PRIMARY KEY,
    item_name TEXT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity >= 0)
);

INSERT INTO lesson_lockchain.inventory(
    item_id, item_name, quantity
)
VALUES
    (1, 'Bàn phím', 10),
    (2, 'Chuột', 20),
    (3, 'Tai nghe', 30);
```

Các ví dụ tiếp theo giả định bạn có:

- **Session A:** một cửa sổ `psql`, connection riêng.
- **Session B:** cửa sổ `psql` thứ hai.
- **Session C:** cửa sổ thứ ba khi cần tạo chain.
- **Session M:** cửa sổ dùng **chẩn đoán**, không được giữ transaction lab bị blocked.

Kiểm tra mỗi connection bằng:

```sql
SELECT current_database(), current_user, pg_backend_pid();
```

Ghi nhận PID của từng session. Đừng dùng cùng một connection hoặc cùng transaction để giả lập hai backend. Nếu chạy qua PgBouncer transaction pooling, mapping connection tới PostgreSQL backend có thể không ổn định ngoài transaction; để học bài này, ưu tiên các connection trực tiếp.

### Dọn tình huống nếu một session đang mắc kẹt

Sau khi thí nghiệm:

```sql
ROLLBACK;
```

trên những session có transaction còn mở. Nếu query đang **bị chặn**, cần giải phóng transaction blocker ở session khác trước hoặc sử dụng một cách cancel an toàn. Không giữ transaction cố tình chặn nhiều phút chỉ để ngắm đồ thị.

## 5. Tái hiện một row-lock wait

### Bước 1 — Session A giữ khóa

```sql
BEGIN;

UPDATE lesson_lockchain.inventory
SET quantity = quantity + 1
WHERE item_id = 1;

SELECT pg_backend_pid() AS session_a_pid;
-- Giữ transaction mở; KHÔNG COMMIT hay ROLLBACK lúc này.
```

Sau `UPDATE`, A đã sửa hàng 1 nhưng chưa commit. Một transaction khác muốn sửa cùng hàng sẽ phải phối hợp/đợi lock liên quan.

### Bước 2 — Session B cập nhật cùng hàng

```sql
BEGIN;

UPDATE lesson_lockchain.inventory
SET quantity = quantity + 1
WHERE item_id = 1;
-- Lệnh có thể đứng chờ, chưa trả prompt.
```

Trong lúc B đứng chờ, **không chạy thêm lệnh cùng một connection B**; chuyển sang session M để chẩn đoán.

### Bước 3 — Session M quan sát

```sql
SELECT
    a.pid,
    a.state,
    a.wait_event_type,
    a.wait_event,
    a.query
FROM pg_catalog.pg_stat_activity AS a
WHERE a.datname = current_database()
  AND a.wait_event_type = 'Lock'
ORDER BY a.pid;
```

B thường hiện `wait_event_type='Lock'`; với tranh chấp row update phổ biến, `wait_event` có thể là `transactionid`. A có thể ở trạng thái `idle in transaction`.

### Bước 4 — Session A giải phóng khóa

```sql
ROLLBACK;
```

Lệnh UPDATE của B có thể tiếp tục. **Session B** sau khi prompt quay lại:

```sql
ROLLBACK;
```

Hai lần rollback giữ bảng lab về số lượng ban đầu.

## 6. Hàm pg_blocking_pids(pid): cách nhanh nhất tìm blocker trực tiếp

Hàm:

```sql
SELECT pg_catalog.pg_blocking_pids(<backend_pid>);
```

trả một mảng `integer[]` chứa PID của những backend đang chặn PID được truyền vào, nếu có.

Với kịch bản A chặn B:

```text
pg_blocking_pids(B_PID) → {A_PID}
```

Trong session M, có thể lấy PID trực tiếp từ `pg_stat_activity` thay vì hardcode:

```sql
SELECT
    a.pid AS waiting_pid,
    pg_catalog.pg_blocking_pids(a.pid) AS blocking_pids,
    a.wait_event_type,
    a.wait_event
FROM pg_catalog.pg_stat_activity AS a
WHERE a.datname = current_database()
  AND a.wait_event_type = 'Lock'
ORDER BY a.pid;
```

Ví dụ kết quả giả định:

| waiting_pid | blocking_pids | wait_event_type | wait_event |
|---:|---|---|---|
| 32102 | `{32101}` | Lock | transactionid |

Đừng copy các số PID trên sang lệnh xử lý thực tế: chúng chỉ có ý nghĩa trên hệ thống tại thời điểm lấy mẫu.

### Mảng rỗng không có nghĩa chưa từng chờ

`pg_blocking_pids()` trả mảng rỗng nếu không có blocker hiện tại mà hàm xác định được. Lock wait có thể **vừa kết thúc** giữa lúc query lấy `pg_stat_activity` và lúc hàm được gọi. Monitoring ở nhiều thời điểm có thể thấy đồ thị thay đổi.

### Hàm trả blocker theo ngữ nghĩa lock manager

`pg_blocking_pids()` xét quan hệ chặn từ lock manager và là công cụ phù hợp hơn việc tự so sánh các tuple của `pg_locks` bằng những điều kiện sơ sài. Hàm còn xử lý khái niệm **soft blocker** đứng trước trong hàng đợi, ngoài những lock holder xung đột trực tiếp.

## 7. Chuyển mảng blocking PIDs thành từng hàng

Để đưa blocker vào một kết quả quan hệ, dùng `unnest()`:

```sql
SELECT
    a.pid AS waiting_pid,
    b.blocking_pid
FROM pg_catalog.pg_stat_activity AS a
CROSS JOIN LATERAL unnest(
    pg_catalog.pg_blocking_pids(a.pid)
) AS b(blocking_pid)
WHERE a.datname = current_database()
ORDER BY a.pid, b.blocking_pid;
```

Giải thích:

1. `pg_stat_activity` cung cấp PID các backend.
2. `pg_blocking_pids(a.pid)` tìm những PID trực tiếp chặn backend `a`.
3. `unnest` tạo **một hàng mỗi blocker**.
4. `CROSS JOIN LATERAL` cho phép hàm bên phải sử dụng `a.pid`.
5. Những backend không bị chặn trả mảng rỗng và **không xuất hiện**.

Ví dụ đồ thị:

```text
waiting_pid  blocking_pid
-----------  ------------
32102        32101
32103        32102
```

Hai dòng trên là hai **cạnh**:

```text
32103 → 32102 → 32101
```

### Một blocker có thể xuất hiện nhiều lần

Nếu ba backend đang đợi cùng một transaction, blocker PID có thể xuất hiện trong ba dòng khác nhau. Nếu một waiter có nhiều blocker, **waiting_pid** sẽ lặp. Đây là bản chất đồ thị nhiều-nhiều, không phải lỗi của `unnest`.

## 8. Truy vấn giám sát waiter và blocker đầy đủ

Một truy vấn dùng trong nhiều tình huống vận hành:

```sql
SELECT
    waiter.pid AS waiting_pid,
    waiter.usename AS waiting_user,
    waiter.application_name AS waiting_application,
    waiter.state AS waiting_state,
    waiter.wait_event_type,
    waiter.wait_event,
    waiter.query_start AS waiting_query_started_at,
    clock_timestamp() - waiter.query_start AS waiting_query_age,
    blocker_ids.blocking_pid,
    blocker.usename AS blocking_user,
    blocker.application_name AS blocking_application,
    blocker.state AS blocking_state,
    blocker.xact_start AS blocking_xact_started_at,
    clock_timestamp() - blocker.xact_start AS blocking_xact_age,
    blocker.state_change AS blocking_state_changed_at,
    waiter.query AS waiting_sql,
    blocker.query AS blocking_last_sql
FROM pg_catalog.pg_stat_activity AS waiter
CROSS JOIN LATERAL unnest(
    pg_catalog.pg_blocking_pids(waiter.pid)
) AS blocker_ids(blocking_pid)
LEFT JOIN pg_catalog.pg_stat_activity AS blocker
  ON blocker.pid = blocker_ids.blocking_pid
WHERE waiter.datname = current_database()
ORDER BY waiting_query_age DESC NULLS LAST,
         waiter.pid,
         blocker_ids.blocking_pid;
```

Các trường giúp nhận diện:

- **`waiting_query_age`:** thời gian từ khi statement bắt đầu, **không nhất thiết là thời gian chờ khóa**. Statement có thể đã xử lý công việc khác trước khi đụng lock.
- **`blocking_xact_age`:** thời gian từ khi transaction của blocker bắt đầu, nếu có.
- **`blocking_state`:** blocker đang chạy hay `idle in transaction`.
- **`blocking_last_sql`:** câu SQL được báo cáo cho blocker. Khi blocker idle, đó có thể là **câu gần nhất**, không phải chắc chắn câu đã lấy lock.

### Vì sao dùng clock_timestamp()?

`now()` là thời điểm bắt đầu transaction. Nếu một connection giám sát cố giữ transaction rất lâu, `now() - query_start` có thể không phản ánh thời gian thực đang trôi. `clock_timestamp()` đọc đồng hồ tại thời điểm gọi. Dù vậy, trong quan sát thường nên chạy các query giám sát ở transaction ngắn.

### Kết quả null ở blocker

`LEFT JOIN pg_stat_activity` có thể không tìm được backend tương ứng trong thời điểm lấy mẫu (backend đã kết thúc, PID đặc biệt hoặc permission/race). Không tự kết luận “không có blocker” chỉ từ `blocking_user IS NULL`; cột `blocking_pid` và ngữ cảnh là thông tin đầu tiên cần kiểm tra.

## 9. Kiểm tra một PID cụ thể

Khi có PID đang chờ từ application log:

```sql
SELECT
    a.pid,
    a.datname,
    a.usename,
    a.application_name,
    a.state,
    a.wait_event_type,
    a.wait_event,
    a.backend_start,
    a.xact_start,
    a.query_start,
    pg_catalog.pg_blocking_pids(a.pid) AS blockers,
    a.query
FROM pg_catalog.pg_stat_activity AS a
WHERE a.pid = 32102;
```

Thay `32102` bằng PID mới vừa được quan sát, không dùng con số minh họa.

**`backend_start` rất quan trọng:** PID hệ điều hành có thể được tái sử dụng sau khi backend cũ kết thúc. Trước khi xử lý một PID, cần kiểm tra lại PID, thời gian tạo backend, user, database, application name và trạng thái ở thời điểm hiện hành.

### Quan sát query text có giới hạn

`pg_stat_activity.query` có thể bị giới hạn độ dài theo `track_activity_query_size` và quyền xem nội dung của role giám sát. Query text cũng có thể chứa dữ liệu nhạy cảm nếu ứng dụng ghép literal trực tiếp. Không xuất toàn bộ SQL của mọi người dùng vào dashboard công khai.

## 10. pg_locks là gì?

`pg_catalog.pg_locks` là view trình bày các khóa đang được yêu cầu trong lock manager của PostgreSQL, bao gồm những khóa **đã cấp** và những khóa **đang chờ**.

Ví dụ xem các khóa có PID:

```sql
SELECT
    pid,
    locktype,
    mode,
    granted,
    waitstart,
    database,
    relation,
    page,
    tuple,
    transactionid,
    virtualxid,
    fastpath
FROM pg_catalog.pg_locks
WHERE pid IS NOT NULL
ORDER BY pid, granted, locktype, mode;
```

**Không thể đọc một hàng `pg_locks` rồi suy ra ngay toàn bộ chuỗi chặn**. Bạn cần hiểu mỗi loại lock dùng khóa định danh khác nhau, mode nào xung đột, và thứ tự hàng đợi. Đó là lý do `pg_blocking_pids` là công cụ ưu tiên cho **quan hệ chặn trực tiếp**.

### Các trường quan trọng

| Trường | Ý nghĩa |
|---|---|
| `pid` | PID backend giữ/yêu cầu lock, có thể `NULL` trong trường hợp như prepared transaction. |
| `locktype` | Loại đối tượng được khóa, ví dụ `relation`, `transactionid`, `virtualxid`, `tuple`, `advisory`. |
| `mode` | Chế độ lock được yêu cầu/cấp; cần xét bảng tương thích để biết xung đột. |
| `granted` | `true` khi yêu cầu khóa đã được cấp, `false` khi còn chờ. |
| `waitstart` | Thời điểm quá trình chờ lock bắt đầu, khi được ghi nhận. |
| `database`, `relation` | OID database/relation tương ứng khi loại lock sử dụng các trường này. |
| `page`, `tuple` | Thông tin định vị row/page đối với locktype phù hợp. |
| `transactionid`, `virtualxid` | Định danh transaction theo loại lock. |
| `classid`, `objid`, `objsubid` | Những trường dùng cho một số loại lock, gồm object/advisory locks. |
| `fastpath` | Cho biết khóa có được lấy qua fast-path cơ chế lock manager hay không. |

### granted=false không luôn có waitstart ngay lập tức

`waitstart` có thể `NULL` trong khoảng rất ngắn ngay sau khi tiến trình bắt đầu chờ vì thông tin ghi nhận không hoàn toàn đồng thời với quá trình cấp trạng thái. Nếu cần xác định đang chờ khóa, xem **`granted=false`**, `wait_event_type='Lock'` và `pg_blocking_pids` cùng nhau.

## 11. Truy vấn những lock request đang chờ

Để xem phần tử có `granted = false`:

```sql
SELECT
    l.pid,
    a.usename,
    a.application_name,
    a.state,
    a.wait_event_type,
    a.wait_event,
    l.locktype,
    l.mode,
    l.waitstart,
    clock_timestamp() - l.waitstart AS lock_wait_age,
    l.database,
    l.relation,
    l.transactionid,
    l.virtualxid,
    a.query
FROM pg_catalog.pg_locks AS l
LEFT JOIN pg_catalog.pg_stat_activity AS a
  ON a.pid = l.pid
WHERE NOT l.granted
ORDER BY l.waitstart NULLS LAST, l.pid;
```

**`clock_timestamp() - l.waitstart`** là chỉ dấu gần hơn về thời gian chờ khóa hiện tại so với `clock_timestamp() - query_start`, khi `waitstart` đã có giá trị.

### Tại sao hai số tuổi khác nhau?

Một statement có thể:

1. Bắt đầu chạy lúc 10:00:00.
2. Quét/lọc dữ liệu 5 giây.
3. Mới đụng một lock lúc 10:00:05.
4. Được quan sát lúc 10:00:08.

Khi đó:

```text
query_age = 8 giây
lock_wait_age = 3 giây
```

Không gán toàn bộ 8 giây của query vào thời gian chờ lock nếu cần phân tích chính xác SLA.

## 12. Tại sao pg_locks không luôn hiện khóa hàng trực tiếp?

Đây là một điểm PostgreSQL rất dễ gây nhầm lẫn.

Khi một transaction `UPDATE` một hàng, thông tin row-level lock thường được ghi **trong tuple trên đĩa**, không phải tất cả đều nằm dưới dạng một hàng `tuple` với `granted=true` trong `pg_locks`.

Khi transaction B đợi transaction A đã cập nhật hàng ấy, `pg_locks` của B có thể hiện:

```text
locktype      mode        granted   transactionid
------------- ----------- --------- -------------
transactionid ShareLock   false     <XID của A>
```

Trong khi A có khóa `transactionid` liên quan với:

```text
locktype      mode           granted
------------- -------------- -------
transactionid ExclusiveLock  true
```

Đây là **khung kết quả điển hình**, không phải output cố định cho mọi tranh chấp row lock.

### Hệ quả khi debug

Đừng viết truy vấn chỉ tìm:

```sql
WHERE locktype = 'tuple'
```

rồi kết luận không có row-lock contention nếu view trả 0 hàng. Hàng có thể bị khóa trong tuple header, còn waiter chờ trên **transactionid lock**.

### Vì sao đôi khi vẫn có tuple locks trong pg_locks?

Một số trạng thái tranh chấp hàng phức tạp có thể xuất hiện `locktype='tuple'` trong view. Điều này không mâu thuẫn với việc **thông tin row lock chính thường nằm trong heap tuple**, không phải tất cả row locks đều hiện thành một hàng relation-like trong `pg_locks`.

**Phương pháp ưu tiên:** dùng `pg_blocking_pids(waiter_pid)` để xác định blocker, sau đó dùng `pg_locks` để hiểu loại tài nguyên mà waiter đang đợi.

## 13. Locktype thường gặp

| `locktype` | Tình huống điển hình |
|---|---|
| `relation` | Khóa trên bảng, index, sequence hoặc relation liên quan; DML/SELECT/DDL có mode khác nhau. |
| `transactionid` | Chờ một transaction khác hoàn tất, thường gặp trong row-update/unique/FK contention. |
| `virtualxid` | Phối hợp theo virtual transaction ID, có thể gặp trong những thao tác quản trị chờ transaction khác. |
| `tuple` | Một số yêu cầu/đợi khóa ở mức tuple. |
| `page` | Khóa cấp page trong những trường hợp đặc biệt. |
| `object` | Khóa đối tượng database không phải relation, tùy thao tác. |
| `advisory` | Khóa tư vấn do ứng dụng chủ động lấy. |
| `spectoken` | Có thể liên quan speculative insertion/unique handling. |
| `extend`, `frozenid`, các loại khác | Các cơ chế khóa nội bộ theo hoạt động/vùng dữ liệu. |

Không phải mọi `locktype` đều dùng `relation`, `transactionid` hoặc `page`. Những trường không liên quan thường `NULL`. Khi lọc/join hãy căn cứ **loại khóa**, không ép mọi hàng thành tên bảng.

## 14. Mode của relation lock

PostgreSQL có nhiều mode khóa relation, tên mode chứa chữ “Row” hoặc “Share” nhưng **không nên coi chúng là đúng một row-level lock**.

Các mode table-level thường gặp:

| Mode | Ví dụ lệnh thường tạo ra | Tính chất xung đột đáng nhớ |
|---|---|---|
| `AccessShareLock` | `SELECT` thông thường. | Xung đột với `AccessExclusiveLock`. |
| `RowShareLock` | `SELECT ... FOR UPDATE/SHARE`. | Xung đột với `ExclusiveLock`, `AccessExclusiveLock`. |
| `RowExclusiveLock` | `INSERT`, `UPDATE`, `DELETE`. | Xung đột với một số mode DDL/share mạnh hơn. |
| `ShareUpdateExclusiveLock` | Một số thao tác `VACUUM`/`ANALYZE`, tạo index concurrent và hoạt động bảo trì. | Tự xung đột; xung đột với các mode mạnh liên quan. |
| `ShareLock` | Một số thao tác tạo index không concurrent. | Xung đột với các writer có `RowExclusiveLock` và những mode mạnh hơn. |
| `ShareRowExclusiveLock` | Một số DDL/trigger-related operations. | Xung đột với nhiều mode, gồm chính nó. |
| `ExclusiveLock` | Một số tác vụ đặc biệt cần loại trừ các mode mạnh. | Xung đột với phần lớn mode trừ `AccessShareLock`. |
| `AccessExclusiveLock` | Nhiều lệnh `ALTER TABLE`, `TRUNCATE`, một số DDL. | Xung đột với **mọi** table-level lock mode. |

Đây chỉ là bảng tóm tắt định hướng, không thay bảng tương thích khóa chính thức của phiên bản server. Khi phân tích một cặp lock, cần xét **mode, cùng đối tượng khóa và trạng thái hàng đợi**.

### SELECT có thể chặn ALTER TABLE

Một `SELECT` bình thường giữ `AccessShareLock` trên relation trong transaction, và một số `ALTER TABLE` cần `AccessExclusiveLock`. Vì hai mode xung đột, lệnh ALTER có thể chờ tới khi transaction giữ AccessShare kết thúc.

### Tên RowExclusiveLock dễ gây hiểu sai

`RowExclusiveLock` là **mode khóa relation**; nó không có nghĩa “đây là danh sách các hàng đang bị khóa”. Khóa hàng liên quan một cơ chế khác, như đã giải thích ở phần tuple/transactionid.

## 15. Gắn tên đối tượng cho relation lock

Các OID trong `pg_locks` có thể được liên kết tới `pg_class` và `pg_namespace` khi relation thuộc **database hiện tại**:

```sql
SELECT
    l.pid,
    l.locktype,
    l.mode,
    l.granted,
    l.waitstart,
    CASE
        WHEN c.oid IS NOT NULL
        THEN format('%I.%I', n.nspname, c.relname)
        ELSE NULL
    END AS relation_name,
    l.database,
    l.relation,
    l.transactionid
FROM pg_catalog.pg_locks AS l
LEFT JOIN pg_catalog.pg_class AS c
  ON c.oid = l.relation
 AND l.database = (
     SELECT oid
     FROM pg_catalog.pg_database
     WHERE datname = current_database()
 )
LEFT JOIN pg_catalog.pg_namespace AS n
  ON n.oid = c.relnamespace
WHERE l.pid IS NOT NULL
  AND (NOT l.granted OR l.locktype = 'relation')
ORDER BY l.pid, l.granted, l.mode;
```

Vì sao kiểm tra `l.database`?

- `pg_locks` có thể báo khóa liên quan **database khác**.
- `pg_class` chỉ phản ánh catalog relation ở database đang kết nối.
- OID relation ở database khác có thể tình cờ trùng một OID local; join không kiểm tra database có thể tạo **tên sai**.
- Một số lock thuộc đối tượng chia sẻ toàn cluster, có `database` đặc biệt hoặc `NULL`; không nên ép chúng thành local relation.

Khi relation không phân giải được, giữ `database`/`relation`/`locktype` thô để điều tra thay vì tự gán tên bảng đoán mò.

## 16. Vì sao không nên tự self-join pg_locks để tìm blocker?

Một ý tưởng có vẻ tự nhiên:

```sql
SELECT ...
FROM pg_locks waiter
JOIN pg_locks holder
  ON waiter.relation = holder.relation
WHERE NOT waiter.granted
  AND holder.granted;
```

Nhưng **truy vấn phác thảo trên không đủ chính xác**, vì:

1. Hai lock trên cùng relation **có thể tương thích** về mode.
2. Một số chờ khóa hàng xuất hiện bằng `transactionid`, không phải `relation`.
3. Lock định danh bằng nhiều cột khác nhau tùy `locktype`.
4. Có **soft blockers** trong hàng đợi chưa được cấp lock.
5. Các relation OID phải được xét cùng database phù hợp.
6. `pg_locks` lấy dữ liệu từ những thành phần lock manager khác nhau, không hứa một snapshot tuyệt đối đồng thời cho toàn bộ trạng thái.
7. Những tình huống parallel query và prepared transaction phức tạp hơn một cặp PID thông thường.

Vì thế, PostgreSQL cung cấp **`pg_blocking_pids()`** để trả lời câu hỏi blocker một cách trực tiếp theo quy tắc của lock manager.

**Kinh nghiệm vận hành:** dùng `pg_blocking_pids()` dựng đồ thị; dùng `pg_locks` để diễn giải **lock request nào đang chờ và loại resource nào liên quan**.

## 17. Hard blocker và soft blocker

Hai khái niệm:

- **Hard blocker:** backend đang **giữ khóa đã được cấp** xung đột với yêu cầu của waiter.
- **Soft blocker:** backend **đang đứng trước waiter trong hàng đợi** của một đối tượng khóa, và yêu cầu của backend đó xung đột với yêu cầu waiter. Soft blocker có thể chưa được cấp lock.

Ví dụ:

```text
Session A: giữ AccessShareLock trên bảng inventory
Session B: xếp hàng đợi AccessExclusiveLock để ALTER TABLE
Session C: đến sau, muốn AccessShareLock để SELECT
```

Về mặt mode:

- AccessShareLock của C **tương thích** với AccessShareLock của A.
- Nhưng B đang **đợi AccessExclusiveLock** ở vị trí trước.
- Lock manager có thể giữ C chờ phía sau B để duy trì thứ tự/hạn chế starvation.

Sơ đồ:

```text
        Granted
A [AccessShare]
        │
        │ hard conflict
        ▼
B [AccessExclusive waiting]
        │
        │ soft blocking in queue
        ▼
C [AccessShare waiting]
```

Nếu bạn chỉ tự join waiter với `granted=true` holder cùng relation, có thể không mô tả chính xác **vì sao C đang chờ**. `pg_blocking_pids(C_PID)` có thể báo **B** là soft blocker, và đồ thị cho thấy C → B → A.

### Tính chất hàm pg_blocking_pids

Hàm được thiết kế để xét cả hard và soft blocking. Không thể đồng nhất `blocking_pid` với “PID chắc chắn đang có `granted=true` của đúng lock mà waiter đòi” trong mọi trường hợp.

## 18. Thí nghiệm DDL tạo hàng đợi

Đây là thí nghiệm nâng cao với **ba session**, chạy nhanh trên bảng lab.

**Session A:**

```sql
BEGIN;

SELECT COUNT(*)
FROM lesson_lockchain.inventory;

-- Giữ BEGIN mở, giữ AccessShareLock của transaction.
```

**Session B:**

```sql
ALTER TABLE lesson_lockchain.inventory
ADD COLUMN IF NOT EXISTS demo_note TEXT;
-- Có thể đứng chờ AccessExclusiveLock.
```

**Session C**, khi B đang đứng chờ:

```sql
SELECT COUNT(*)
FROM lesson_lockchain.inventory;
-- Có thể phải đợi vì B đang xếp trước trong lock queue.
```

**Session M:**

```sql
SELECT
    a.pid AS waiter_pid,
    pg_catalog.pg_blocking_pids(a.pid) AS blockers,
    a.wait_event_type,
    a.wait_event,
    left(a.query, 180) AS sql_excerpt
FROM pg_catalog.pg_stat_activity AS a
WHERE a.datname = current_database()
  AND a.wait_event_type = 'Lock'
ORDER BY a.pid;
```

**Session A:**

```sql
ROLLBACK;
```

Sau đó B có thể hoàn thành ALTER TABLE, C có thể chạy. Ví dụ `ALTER TABLE` là DDL **có tác động bền vững khi autocommit**, nên nếu muốn giữ nguyên schema lab có thể:

- Chạy `ALTER TABLE` trong `BEGIN ... ROLLBACK` ở B, hoặc
- Chấp nhận cột demo ở lab và xóa có chủ đích khi kết thúc.

Không thực hiện thí nghiệm này trên bảng đang phục vụ traffic thực vì yêu cầu `AccessExclusiveLock` có thể tạo **blocking queue** ảnh hưởng nhiều truy vấn đọc/ghi.

## 19. Tạo chuỗi chặn ba tầng A → B → C

Mục tiêu xây:

```text
C muốn sửa item 2
  │
  ▼
B đang giữ row lock item 2,
  đồng thời B đang chờ sửa item 1
  │
  ▼
A đang giữ row lock item 1

Wait-for chain: C → B → A
```

### Session A — Giữ item 1

```sql
BEGIN;

UPDATE lesson_lockchain.inventory
SET quantity = quantity + 1
WHERE item_id = 1;

-- Giữ transaction mở.
```

### Session B — Giữ item 2, rồi chờ item 1

```sql
BEGIN;

UPDATE lesson_lockchain.inventory
SET quantity = quantity + 1
WHERE item_id = 2;

UPDATE lesson_lockchain.inventory
SET quantity = quantity + 1
WHERE item_id = 1;
-- Chờ A, chưa nhận prompt.
```

### Session C — Chờ item 2

```sql
BEGIN;

UPDATE lesson_lockchain.inventory
SET quantity = quantity + 1
WHERE item_id = 2;
-- Chờ B.
```

### Session M — Quan sát các cạnh

```sql
SELECT
    a.pid AS blocked_pid,
    b.blocker_pid,
    a.state,
    a.wait_event_type,
    a.wait_event,
    left(a.query, 140) AS blocked_sql
FROM pg_catalog.pg_stat_activity AS a
CROSS JOIN LATERAL unnest(
    pg_catalog.pg_blocking_pids(a.pid)
) AS b(blocker_pid)
WHERE a.datname = current_database()
ORDER BY blocked_pid, blocker_pid;
```

Kết quả khái niệm:

```text
blocked_pid  blocker_pid
C_PID        B_PID
B_PID        A_PID
```

### Kết thúc thí nghiệm theo đúng thứ tự

1. **Session A:** `ROLLBACK;` → B hết chờ.
2. **Session B:** sau khi lệnh UPDATE xong, `ROLLBACK;` → C hết chờ.
3. **Session C:** khi lệnh UPDATE xong, `ROLLBACK;`.

Không rollback B trong khi B đang kẹt ở lệnh UPDATE bằng cách gõ tiếp trên cùng session: client có thể chưa gửi lệnh tiếp theo tới backend cho tới khi statement chờ hoàn tất/cancel.

## 20. Truy vết nhiều tầng với WITH RECURSIVE

Mảng blockers chỉ cho **một tầng**. Muốn đi tiếp từ C tới B rồi A, biểu diễn các cạnh thành một CTE và truy đệ quy:

```sql
WITH RECURSIVE edges AS (
    SELECT
        a.pid AS waiting_pid,
        b.blocker_pid
    FROM pg_catalog.pg_stat_activity AS a
    CROSS JOIN LATERAL unnest(
        pg_catalog.pg_blocking_pids(a.pid)
    ) AS b(blocker_pid)
),
paths AS (
    SELECT
        e.waiting_pid AS origin_waiting_pid,
        e.blocker_pid AS current_blocker_pid,
        ARRAY[e.waiting_pid, e.blocker_pid]::integer[] AS pid_chain,
        1 AS depth
    FROM edges AS e

    UNION ALL

    SELECT
        p.origin_waiting_pid,
        e.blocker_pid,
        p.pid_chain || e.blocker_pid,
        p.depth + 1
    FROM paths AS p
    JOIN edges AS e
      ON e.waiting_pid = p.current_blocker_pid
    WHERE p.depth < 16
      AND NOT e.blocker_pid = ANY(p.pid_chain)
)
SELECT
    origin_waiting_pid,
    current_blocker_pid,
    depth,
    pid_chain
FROM paths
ORDER BY origin_waiting_pid, depth, pid_chain;
```

Giải thích:

1. `edges` biến kết quả `pg_blocking_pids` thành các cạnh `waiting_pid → blocker_pid`.
2. Phần đầu của `paths` tạo một đường đi có **hai PID** và `depth=1`.
3. Phần đệ quy nối thêm blocker của **current blocker**.
4. `pid_chain` lưu toàn bộ đường đi đã xét.
5. `NOT e.blocker_pid = ANY(p.pid_chain)` ngăn quay lại một PID đã có trong đường đi.
6. `p.depth < 16` đặt mức trần để tránh truy vấn giám sát chạy không giới hạn trên đồ thị lớn/bất thường.

Với thí nghiệm trên:

```text
origin_waiting_pid  depth  pid_chain
C_PID               1      {C_PID,B_PID}
C_PID               2      {C_PID,B_PID,A_PID}
B_PID               1      {B_PID,A_PID}
```

### Nhiều blocker tạo nhiều nhánh

Nếu C bị chặn bởi cả B và D, kết quả có hai đường:

```text
C → B → A
C → D → E
```

Không ép kết quả thành một “root PID” duy nhất. Hãy giữ các nhánh và xác định từng điểm cuối.

### Giới hạn của truy vấn đệ quy

Đồ thị lock có thể **thay đổi trong lúc truy vấn đang chạy**. Mặc dù `edges` giúp làm việc trên một tập cạnh thu được trong truy vấn, bản thân kết quả gọi các hàm và statistics có thể phản ánh các thời điểm rất gần nhưng không hoàn toàn đồng thời. Truy vấn trên là **ảnh chụp chẩn đoán**, không phải lịch sử lock tuyệt đối.

## 21. Xác định đầu chuỗi trong đồ thị quan sát

Một **điểm cuối** là blocker mà tập cạnh hiện tại **không ghi nhận** có blocker phía trên.

Ví dụ từ tập cạnh:

```text
C → B
B → A
```

thì A là điểm cuối của đường đi từ C.

Truy vấn có thể mở rộng:

```sql
WITH RECURSIVE edges AS (
    SELECT
        a.pid AS waiting_pid,
        b.blocker_pid
    FROM pg_catalog.pg_stat_activity AS a
    CROSS JOIN LATERAL unnest(
        pg_catalog.pg_blocking_pids(a.pid)
    ) AS b(blocker_pid)
),
paths AS (
    SELECT
        e.waiting_pid AS origin_pid,
        e.blocker_pid AS current_pid,
        ARRAY[e.waiting_pid, e.blocker_pid]::integer[] AS path,
        1 AS depth
    FROM edges AS e

    UNION ALL

    SELECT
        p.origin_pid,
        e.blocker_pid,
        p.path || e.blocker_pid,
        p.depth + 1
    FROM paths AS p
    JOIN edges AS e
      ON e.waiting_pid = p.current_pid
    WHERE p.depth < 16
      AND NOT e.blocker_pid = ANY(p.path)
)
SELECT
    p.origin_pid AS blocked_pid,
    p.current_pid AS terminal_blocker_pid,
    p.depth,
    p.path AS observed_path,
    CASE
        WHEN p.current_pid = 0
        THEN 'prepared transaction'
        ELSE 'no upstream blocker in sampled graph'
    END AS terminal_kind
FROM paths AS p
WHERE NOT EXISTS (
    SELECT 1
    FROM edges AS e
    WHERE e.waiting_pid = p.current_pid
)
ORDER BY p.origin_pid, p.depth DESC;
```

**Đọc kết quả đúng phạm vi:**

- `terminal_blocker_pid` là điểm cuối **trong tập cạnh quan sát được**, không nhất thiết là thủ phạm duy nhất.
- Đồ thị có **cycle** hoặc gặp ngưỡng `depth<16` có thể không có điểm cuối đơn giản. Vì vậy, một waiter có thể không xuất hiện trong bảng terminal.
- Với **PID 0**, đây có thể là blocker thuộc **prepared transaction**, không phải process PID 0 cần terminate.
- Một blocker không chờ PostgreSQL heavyweight lock vẫn có thể đang đợi client/network/hệ ngoài.

Không tự động `pg_terminate_backend(terminal_blocker_pid)` chỉ vì truy vấn gọi nó là terminal.

## 22. Chuỗi chặn với blocker idle in transaction

Một nguyên nhân rất thường gặp:

```text
Service A:
BEGIN
UPDATE inventory ...
gọi HTTP API hoặc chờ user
-- Không COMMIT/ROLLBACK

Service B:
UPDATE cùng hàng → chờ

Service C:
UPDATE hàng Service B đang giữ → chờ B
```

Khi đó:

- A có thể ở `state='idle in transaction'`.
- B và C có thể ở `state='active'`, `wait_event_type='Lock'`.
- A **không có wait_event_type='Lock'`** vì nó không phải waiter; nó là holder.

Truy vấn nhận diện các session idle với transaction còn mở:

```sql
SELECT
    pid,
    usename,
    application_name,
    state,
    xact_start,
    clock_timestamp() - xact_start AS transaction_age,
    state_change,
    clock_timestamp() - state_change AS idle_state_age,
    left(query, 300) AS last_reported_sql
FROM pg_catalog.pg_stat_activity
WHERE datname = current_database()
  AND state IN (
      'idle in transaction',
      'idle in transaction (aborted)'
  )
ORDER BY xact_start NULLS LAST;
```

Đây là **danh sách nghi vấn**, không phải chứng minh mỗi session trong đó đang chặn backend khác. Để biết ai thực sự chặn, kiểm tra các cạnh từ `pg_blocking_pids`.

### Tại sao không tự động kill mọi idle transaction?

Một số transaction có thể được giữ có chủ đích cho thao tác nghiệp vụ/backup và chưa chặn ai. Việc terminate sẽ rollback. Ngược lại, transaction “idle” rất ngắn có thể hoàn toàn bình thường.

Quyết định cần dựa vào **thời gian, blocker count, SLA, owner service và mức độ ảnh hưởng**.

## 23. Đếm số waiter bị một blocker ảnh hưởng

Một blocker chặn 20 request có tác động lớn hơn blocker chỉ chặn một request thử nghiệm.

```sql
WITH edges AS (
    SELECT
        a.pid AS waiting_pid,
        b.blocker_pid
    FROM pg_catalog.pg_stat_activity AS a
    CROSS JOIN LATERAL unnest(
        pg_catalog.pg_blocking_pids(a.pid)
    ) AS b(blocker_pid)
)
SELECT
    blocker_pid,
    COUNT(DISTINCT waiting_pid) AS directly_blocked_backends
FROM edges
GROUP BY blocker_pid
ORDER BY directly_blocked_backends DESC, blocker_pid;
```

**`COUNT(DISTINCT waiting_pid)`** đếm các backend bị chặn trực tiếp. Nó không đếm các backend chờ **gián tiếp qua nhiều tầng**. Muốn đánh giá ảnh hưởng toàn chuỗi, dùng các đường đi của recursive CTE rồi đếm riêng `origin_pid` theo terminal blockers.

### Đếm gián tiếp không nên nhân đôi

Trong đồ thị có nhiều nhánh, cùng một waiter có thể đi tới cùng blocker qua các đường khác nhau. Nếu cần số backend bị ảnh hưởng thực, hãy dùng `COUNT(DISTINCT origin_pid)`, không đơn giản `COUNT(*)` trên mọi đường đi.

## 24. pg_locks cho PID waiter và blocker

Sau khi đã xác định cặp PID, dùng `pg_locks` để xem metadata của **hai bên**:

```sql
WITH watched_pids AS (
    SELECT
        a.pid AS waiting_pid,
        b.blocker_pid
    FROM pg_catalog.pg_stat_activity AS a
    CROSS JOIN LATERAL unnest(
        pg_catalog.pg_blocking_pids(a.pid)
    ) AS b(blocker_pid)
)
SELECT
    l.pid,
    CASE
        WHEN l.pid IN (
            SELECT waiting_pid FROM watched_pids
        )
        THEN 'WAITING'
        WHEN l.pid IN (
            SELECT blocker_pid FROM watched_pids
        )
        THEN 'BLOCKING'
        ELSE 'OTHER'
    END AS role_in_graph,
    l.locktype,
    l.mode,
    l.granted,
    l.waitstart,
    l.database,
    l.relation,
    l.transactionid,
    l.virtualxid,
    l.fastpath
FROM pg_catalog.pg_locks AS l
WHERE l.pid IN (
    SELECT waiting_pid FROM watched_pids
    UNION
    SELECT blocker_pid FROM watched_pids
)
ORDER BY l.pid, l.granted, l.locktype, l.mode;
```

Một PID có thể vừa **WAITING vừa BLOCKING** (session B trong chain ba tầng). Biểu thức `CASE` phía trên ưu tiên nhãn `WAITING` khi PID thuộc cả hai tập; nhãn chỉ phục vụ quan sát, không mô tả tất cả vai trò. Nếu cần chính xác, hiển thị **hai cờ boolean**:

```sql
SELECT
    pid,
    EXISTS (
        SELECT 1 FROM pg_catalog.pg_stat_activity AS a
        WHERE a.pid = l.pid
          AND cardinality(pg_catalog.pg_blocking_pids(a.pid)) > 0
    ) AS is_waiting_on_someone
FROM pg_catalog.pg_locks AS l
WHERE NOT l.granted;
```

Kết quả cuối có thể có nhiều dòng cho một PID do `pg_locks` có nhiều lock requests; đó không phải lỗi. Khi cần thống kê PID, dùng `DISTINCT` theo mục tiêu cụ thể.

## 25. pg_locks và database khác

`pg_locks` ở một PostgreSQL instance có thể chứa lock entries từ nhiều database trong cùng instance. Một số khóa liên quan đối tượng toàn cluster, có database OID đặc biệt hoặc null.

Khi gắn `relation` với tên, **chỉ tra catalog relation của database hiện tại** nếu database OID phù hợp. Khi giám sát toàn instance:

```sql
SELECT
    l.pid,
    d.datname,
    l.locktype,
    l.mode,
    l.granted,
    l.database,
    l.relation
FROM pg_catalog.pg_locks AS l
LEFT JOIN pg_catalog.pg_database AS d
  ON d.oid = l.database
ORDER BY l.pid NULLS LAST, l.granted;
```

Không coi `relation=12345` của database A và database B là cùng bảng. Không phải mọi lock đều có relation; với `transactionid`/`virtualxid` hoặc `advisory`, cần đọc đúng loại metadata.

## 26. Advisory lock: blocker không nhất thiết nằm ở bảng

Ứng dụng có thể chủ động lấy **advisory lock**:

```sql
SELECT pg_catalog.pg_advisory_lock(12345);
```

Đây là **session-level advisory lock**. Nếu đã lấy thành công, nó có thể được giữ **qua COMMIT/ROLLBACK** và chỉ được nhả khi gọi unlock phù hợp hoặc session kết thúc.

Một transaction khác/session khác:

```sql
SELECT pg_catalog.pg_advisory_lock(12345);
-- Có thể chờ session đầu tiên nhả lock.
```

Quan sát:

```sql
SELECT
    pid,
    locktype,
    mode,
    granted,
    classid,
    objid,
    objsubid
FROM pg_catalog.pg_locks
WHERE locktype = 'advisory'
ORDER BY pid, granted;
```

### Giải phóng đúng cách

Ở session đã lấy advisory lock:

```sql
SELECT pg_catalog.pg_advisory_unlock(12345);
```

Với **transaction-level advisory lock**:

```sql
BEGIN;

SELECT pg_catalog.pg_advisory_xact_lock(12345);

-- Thực hiện công việc...

ROLLBACK;
-- Transaction-level advisory lock được giải phóng.
```

### Vì sao blocker advisory dễ bị bỏ sót?

Blocker session-level có thể ở `state='idle'`, **không mở transaction**, nhưng vẫn giữ advisory lock. Vì thế, nếu chỉ lọc `idle in transaction` sẽ **không tìm thấy** mọi blocker.

`pg_blocking_pids` vẫn giúp tìm PID đang chặn yêu cầu advisory lock tương ứng. Cần xem `pg_locks.locktype='advisory'` và logic ứng dụng để hiểu vì sao lock còn được giữ.

### Không dùng advisory locks như quyền bảo mật

Advisory locks là cơ chế phối hợp tự nguyện giữa các session có quyền gọi, không phải thay thế unique constraints, row-level security hoặc phân quyền.

## 27. Prepared transaction: blocker có thể không có PID bình thường

PostgreSQL hỗ trợ **two-phase commit** với `PREPARE TRANSACTION` khi được cấu hình phù hợp. Một transaction đã được prepare vẫn có thể **giữ các khóa** nhưng không còn một backend kết nối thông thường giữ vai trò giao dịch đang chạy.

Trong những trường hợp đó:

- `pg_locks.pid` cho khóa do prepared transaction giữ có thể là `NULL`.
- `pg_blocking_pids()` có thể báo giá trị **0** cho blocker thuộc prepared transaction.
- Bạn **không thể** xử lý PID 0 bằng `pg_cancel_backend(0)` hay `pg_terminate_backend(0)`.

Kiểm tra:

```sql
SELECT
    gid,
    prepared,
    owner,
    database,
    transaction
FROM pg_catalog.pg_prepared_xacts
ORDER BY prepared;
```

View này hiển thị những prepared transactions có thể cần được kết thúc theo giao thức của hệ thống.

### Không rollback prepared transaction tùy tiện

Các lệnh:

```sql
-- Ví dụ cú pháp, KHÔNG tự chạy trên production:
-- COMMIT PREPARED 'gid-do-coordinator-cap';
-- ROLLBACK PREPARED 'gid-do-coordinator-cap';
```

có thể làm thay đổi tính nguyên tử của giao dịch phân tán. Phải xác nhận với **transaction coordinator**, ứng dụng và owner trước khi quyết định commit hay rollback. Một prepared transaction còn treo lâu thường là sự cố cần quy trình phục hồi riêng, không chỉ “kill một PID”.

### Nếu pg_prepared_xacts rỗng?

Đừng mặc định mọi kết quả `blocking_pid=0` trên hệ thống đã được giải thích. Cần quan sát lại, xem quyền đọc statistics, đối chiếu toàn instance và kiểm tra tài liệu phiên bản. Tuy nhiên, prepared transaction là nguyên nhân đặc biệt cần luôn kiểm tra khi thấy PID 0.

## 28. Parallel query và PID blocker

Trong các truy vấn parallel, PostgreSQL có leader và parallel workers. `pg_blocking_pids` có các quy tắc ánh xạ PID liên quan parallel query. Kết quả có thể:

- Hiển thị **PID leader** đại diện cho session parallel ở một số ngữ cảnh.
- Có cùng PID xuất hiện hơn một lần trong những trường hợp parallel workers liên quan.

**Không tự giả định mỗi phần tử của mảng trả về luôn đại diện một backend vật lý độc lập cần xử lý riêng.** Nếu cần đếm client sessions, có thể dùng `DISTINCT` theo PID đã quy về leader nhưng vẫn phải hiểu ngữ nghĩa của hàm.

### Vì sao quan trọng với terminate?

Không nên kill một PID nhìn thấy trong kết quả mà chưa xem nó là leader/worker, query đang phục vụ ai, và có phải dịch vụ nền quan trọng không.

## 29. Deadlock khác một chuỗi chặn thông thường

Chuỗi có điểm cuối:

```text
C → B → A
          │
          └── A đang làm việc, có thể COMMIT/ROLLBACK
```

Deadlock có chu trình:

```text
A giữ row 1, chờ row 2
  ▲                 │
  │                 ▼
B giữ row 2, chờ row 1
  └─────────────────┘

Wait-for cycle: A → B → A
```

PostgreSQL có **deadlock detector**. Sau thời gian phát hiện phù hợp, server có thể chọn một transaction làm nạn nhân và trả:

```text
ERROR: deadlock detected
SQLSTATE: 40P01
```

Transaction bị lỗi cần rollback; ứng dụng có thể thử lại **toàn bộ giao dịch** theo policy.

### Thí nghiệm deadlock (chỉ lab)

**Session A:**

```sql
BEGIN;
UPDATE lesson_lockchain.inventory
SET quantity = quantity + 1
WHERE item_id = 1;
```

**Session B:**

```sql
BEGIN;
UPDATE lesson_lockchain.inventory
SET quantity = quantity + 1
WHERE item_id = 2;
```

**Session A:**

```sql
UPDATE lesson_lockchain.inventory
SET quantity = quantity + 1
WHERE item_id = 2;
-- Chờ B.
```

**Session B:**

```sql
UPDATE lesson_lockchain.inventory
SET quantity = quantity + 1
WHERE item_id = 1;
-- Tạo vòng chờ; một transaction có thể bị 40P01.
```

Khi nhận `40P01`, transaction đó đã failed, cần `ROLLBACK`. Transaction còn lại có thể tiếp tục; sau đó cũng `ROLLBACK` ở lab để hoàn nguyên.

### Không kỳ vọng luôn bắt được cycle bằng một SELECT

Deadlock detector có thể xử lý khá nhanh nên đồ thị có cycle có thể chỉ tồn tại trong thời gian ngắn. Khi điều tra deadlock lặp lại, hãy đọc **server logs** và SQLSTATE, không chỉ dựa vào việc bắt kịp cycle bằng query monitoring.

## 30. deadlock_timeout và log_lock_waits

PostgreSQL có các tham số phục vụ quan sát tranh chấp:

- `deadlock_timeout`: khoảng chờ trước khi server thực hiện kiểm tra deadlock; cũng liên quan lúc ghi log lock wait khi cấu hình phù hợp.
- `log_lock_waits`: có thể yêu cầu ghi log cho những lock waits kéo dài đủ ngưỡng.
- `lock_timeout`: giới hạn thời gian **chờ lấy khóa** đối với một statement.
- `statement_timeout`: giới hạn tổng thời gian chạy statement.
- `idle_in_transaction_session_timeout`: có thể kết thúc session idle trong transaction quá lâu.

Kiểm tra runtime:

```sql
SELECT
    name,
    setting,
    unit,
    context,
    source
FROM pg_catalog.pg_settings
WHERE name IN (
    'deadlock_timeout',
    'log_lock_waits',
    'lock_timeout',
    'statement_timeout',
    'idle_in_transaction_session_timeout'
)
ORDER BY name;
```

### Vai trò và quyền đổi setting

Không phải tham số nào cũng có thể thay đổi tùy ý bởi user thường. Một số setting yêu cầu superuser hoặc quyền cấu hình đặc biệt được cấp theo phiên bản PostgreSQL. Đừng chạy `ALTER SYSTEM` hay sửa cấu hình server chỉ để tái hiện một ví dụ.

### log_lock_waits hữu ích ở đâu?

Khi có nhiều lock waits ngắn và không kịp quan sát trực tiếp, log server là nguồn bằng chứng tốt hơn một lần SELECT hiện tại. Các log có thể cho biết PID, lock mode, đối tượng/transaction và thời gian chờ theo định dạng log được cấu hình.

Không bật logging quá chi tiết lâu dài mà không đánh giá dung lượng log, dữ liệu nhạy cảm và chi phí vận hành.

## 31. lock_timeout và statement_timeout: tránh chờ vô hạn

Trong một transaction thử nghiệm:

```sql
BEGIN;

SET LOCAL lock_timeout = '1s';
SET LOCAL statement_timeout = '5s';

UPDATE lesson_lockchain.inventory
SET quantity = quantity + 1
WHERE item_id = 1;

ROLLBACK;
```

Nếu có blocker giữ hàng 1:

- `lock_timeout` có thể hủy statement khi chờ lấy một khóa quá 1 giây, thường với SQLSTATE thuộc lỗi lock not available.
- `statement_timeout` có thể hủy statement nếu tổng thời gian chạy quá 5 giây.
- Trong transaction tường minh, khi statement lỗi, transaction có thể chuyển sang **aborted**. Lệnh tiếp theo không phải lúc nào cũng chạy được trừ `ROLLBACK` hoặc `ROLLBACK TO SAVEPOINT` hợp lệ.

### Hai timeout không thay thế nhau

`lock_timeout` chỉ đo **thời gian chờ khóa**; một query tốn CPU/IO 10 phút mà không đợi lock có thể không bị giới hạn bởi lock_timeout.

`statement_timeout` giới hạn thời gian statement, nhưng một statement mất 5 giây không nhất thiết do lock. Dùng cả hai theo SLA và đo lường đúng nguyên nhân.

### Không đặt lock_timeout bằng 0 khi muốn tránh chờ

Trong PostgreSQL, giá trị `0` thường biểu thị **tắt timeout** chứ không phải “không đợi”. Nếu muốn thất bại ngay ở một khóa hàng cụ thể, có thể dùng `NOWAIT` trong những cú pháp khóa hỗ trợ; hoặc đặt timeout dương rất nhỏ theo yêu cầu.

## 32. Cân nhắc xử lý: chờ, cancel hay terminate?

Sau khi tìm được blocker, có nhiều lựa chọn:

1. **Chờ tự giải phóng** nếu blocker hợp lệ, sắp commit và ảnh hưởng chấp nhận được.
2. **Yêu cầu ứng dụng/owner commit hoặc rollback** nếu transaction idle quá lâu.
3. **Cancel statement** của backend với `pg_cancel_backend(pid)` trong tình huống phù hợp.
4. **Terminate backend** với `pg_terminate_backend(pid)` khi có quyền và được phê duyệt.
5. **Xử lý prepared transaction** qua giao thức riêng nếu không có backend PID.
6. **Sửa thiết kế** để giảm tái phát (transaction ngắn, thứ tự khóa nhất quán, retry, indexes).

### pg_cancel_backend(pid)

```sql
SELECT pg_catalog.pg_cancel_backend(32101);
```

Đây là **cú pháp ví dụ**; không chạy với PID minh họa. Hàm gửi yêu cầu hủy query đang thực thi trên backend mục tiêu, khi quyền cho phép.

**Hạn chế quan trọng:** Nếu blocker đang **idle in transaction**, nó có thể không có một statement đang chạy để cancel. Cancel query không đồng nghĩa tự commit/rollback một transaction đang mở và không đảm bảo giải phóng lock đã được giữ.

### pg_terminate_backend(pid)

```sql
SELECT pg_catalog.pg_terminate_backend(32101);
```

Hàm yêu cầu chấm dứt backend. Transaction chưa commit của session bị ngắt sẽ được PostgreSQL xử lý rollback khi kết thúc theo cơ chế server. Tùy phiên bản/chữ ký, hàm có thể báo việc gửi tín hiệu hoặc có biến thể timeout; không nên coi mọi kết quả boolean là bằng chứng tuyệt đối rằng mọi hậu quả đã hoàn tất tại đúng thời điểm client nhận phản hồi.

### Rủi ro của terminate

- Rollback transaction hợp lệ.
- Làm hỏng request đang xử lý.
- Kích hoạt retry hàng loạt.
- Tạo lỗi HTTP/worker và ảnh hưởng SLA.
- Có thể chạm session quản trị hoặc backend không nên tác động.

Chỉ thực hiện sau khi xác nhận chủ sở hữu và **tác động dự kiến**, không tự động terminate theo một câu query chẩn đoán đơn lẻ.

## 33. Quyền thực thi cancel và terminate

PostgreSQL kiểm soát ai có thể gửi tín hiệu tới backend khác. Một role thông thường không được mặc nhiên cancel/terminate mọi session. Các quyền như membership trong `pg_signal_backend` hoặc quyền superuser có những quy tắc hạn chế theo phiên bản và role mục tiêu.

**Nguyên tắc phân quyền:**

- Chỉ cấp quyền can thiệp backend cho các operator/automation đáng tin.
- Không cấp superuser chỉ để đọc `pg_locks` hoặc `pg_stat_activity`.
- Role xem statistics có thể sử dụng các quyền giám sát thích hợp như `pg_monitor` hoặc `pg_read_all_stats` tùy nhu cầu.
- Phân tách quyền **quan sát** và quyền **tác động**.
- Audit những lần cancel/terminate phục vụ sự cố.

Trước khi tác động PID, kiểm tra lại:

```sql
SELECT
    pid,
    backend_start,
    usename,
    datname,
    application_name,
    state,
    xact_start,
    query_start,
    wait_event_type,
    wait_event,
    left(query, 300) AS query_excerpt
FROM pg_catalog.pg_stat_activity
WHERE pid = 32101;
```

Thay PID ví dụ bằng giá trị mới nhất; không gửi lệnh tác động nếu PID không còn tồn tại hoặc không đúng session mong đợi.

## 34. Đọc query text của blocker đúng ngữ cảnh

`pg_stat_activity.query` rất hữu ích nhưng có thể gây hiểu nhầm.

**Nếu `state='active'`:** `query` thường đại diện statement đang chạy của backend.

**Nếu `state='idle in transaction'`:** `query` thường là statement **gần nhất** được thực thi trước khi backend chờ client, không nhất thiết là câu đã lấy khóa gây tranh chấp.

Ví dụ:

```text
BEGIN
UPDATE inventory SET quantity=... WHERE item_id=1   ← giữ lock
SELECT 1                                             ← câu gần nhất
[idle in transaction]
```

Monitoring có thể thấy `SELECT 1` trong `query` của blocker A, nhưng **lock gây chặn thực sự đến từ UPDATE trước đó**.

Do vậy, muốn biết nguyên nhân chính xác:

- Kết hợp `pg_locks` để xem lock holder và kiểu đối tượng.
- Dùng application logs/tracing có request ID, transaction ID nghiệp vụ hoặc connection identifier.
- Kiểm tra lifecycle code JDBC/Spring.
- Không suy luận “SELECT 1 giữ row lock” chỉ từ `blocking_last_sql`.

### Query text có thể bị cắt ngắn

`track_activity_query_size` giới hạn kích thước query string thu thập. Query được chuẩn bị với parameters cũng không nhất thiết hiển thị toàn bộ giá trị bind. Khi cần chẩn đoán, dùng log ở mức cho phép và tránh lộ PII/secrets.

## 35. Mở nhiều connection để tái hiện chính xác

Một nguồn sai thường gặp trong lab là chạy:

```sql
BEGIN;
UPDATE ...;
UPDATE ...;
```

**cùng một session** rồi nghĩ câu UPDATE thứ hai đang đợi transaction thứ nhất. Trong cùng transaction, bạn thường không tự chặn chính mình bằng cùng row lock theo kiểu hai session độc lập.

Muốn tạo blocker/waiter:

```text
Connection A: transaction T_A
Connection B: transaction T_B
Connection M: monitor, không nằm trong T_A/T_B
```

Với connection pool, nhớ:

- Mỗi JDBC `Connection` đại diện ngữ cảnh giao dịch riêng trong cấu hình trực tiếp phù hợp.
- Một request có thể mượn connection rồi giữ transaction qua nhiều repository calls.
- Framework có thể tự quản lý bắt đầu/kết thúc transaction, nên phải xác định owner transaction trước khi thử.

Không giữ mã thử nghiệm tạo lock chờ trong unit tests chạy song song trên database chung mà không có timeout và cleanup.

## 36. JDBC: đặt application_name để tìm đúng blocker

Một ứng dụng Java có nhiều service/worker có thể cấu hình `application_name` để giúp `pg_stat_activity` nhận diện nguồn kết nối.

Ví dụ URL JDBC minh họa:

```text
jdbc:postgresql://db.example.invalid:5432/demo?ApplicationName=inventory-service
```

Hoặc trong transaction/session khi có chủ đích:

```sql
SET application_name = 'inventory-service';
```

Lưu ý `application_name` là nhãn chẩn đoán, **không phải danh tính được bảo mật/đã xác thực**. Client có thể đặt giá trị theo quyền và driver; không dùng nó làm căn cứ cấp quyền.

### Connection pool

Nếu pool sử dụng chung database role cho nhiều request, `usename` có thể giống nhau trên mọi session. Kết hợp:

- `application_name`.
- `backend_start` và `pid`.
- Request trace/correlation ID ở logs.
- `xact_start` và `query_start`.
- Thông tin service instance khi monitoring hệ thống cho phép.

Không gán PID với một người dùng HTTP duy nhất: backend có thể được sử dụng tuần tự cho nhiều request.

## 37. JDBC transaction bị lỗi sau lock_timeout

Mẫu Java:

```java
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);

    try {
        try (Statement st = connection.createStatement()) {
            st.execute("SET LOCAL lock_timeout = '2s'");
        }

        try (PreparedStatement ps = connection.prepareStatement("""
                UPDATE lesson_lockchain.inventory
                SET quantity = quantity + 1
                WHERE item_id = ?
                """)) {
            ps.setInt(1, 1);
            ps.executeUpdate();
        }

        connection.commit();
    } catch (SQLException | RuntimeException failure) {
        try {
            connection.rollback();
        } catch (SQLException rollbackFailure) {
            failure.addSuppressed(rollbackFailure);
        }
        throw failure;
    }
}
```

Giả định đã có `DataSource`, imports và method khai báo/giải quyết `SQLException`. Ví dụ nhấn mạnh **transaction boundary**:

1. Bắt đầu transaction.
2. Đặt `lock_timeout` trong transaction.
3. Thực hiện SQL.
4. Commit khi hoàn tất hợp lệ.
5. Rollback nếu có lỗi, vì một lock timeout trong transaction có thể khiến transaction aborted.

### SQLSTATE

Với PostgreSQL, lock timeout/NOWAIT thường có thể cho lỗi class lock-related như **`55P03`**; deadlock dùng **`40P01`**, và transaction aborted sau một lỗi có thể dẫn tới **`25P02`** nếu tiếp tục gửi SQL.

Không xây exception handler chỉ tìm chuỗi `"could not obtain lock"` theo message; dùng `SQLException.getSQLState()`, metadata và quy tắc của driver.

## 38. JDBC/Spring: giữ transaction ngắn

Một anti-pattern:

```java
@Transactional
public void updateInventoryAndNotify(long itemId) {
    repository.updateInventory(itemId);   // Giữ row lock.
    remoteHttpClient.callSlowService();    // Chờ network lâu.
    repository.writeAudit(itemId);
}
```

Đây là pseudo-code kiến trúc, giả định các thành phần đã tồn tại. Lock row từ `updateInventory` có thể được giữ cho tới khi transaction kết thúc. Nếu HTTP call mất 30 giây, các transaction khác cập nhật hàng đó có thể bị chặn cả khoảng thời gian ấy.

### Thiết kế tốt hơn

Tùy tính nguyên tử nghiệp vụ:

- Đưa remote I/O ra **ngoài** transaction khi không cần giữ chung lock.
- Dùng **transactional outbox** nếu cần phát thông điệp sau commit đáng tin cậy.
- Giảm số câu SQL và thời gian xử lý giữa `BEGIN` và `COMMIT`.
- Chọn thứ tự cập nhật nhất quán khi phải lock nhiều hàng.
- Chỉ dùng `SELECT FOR UPDATE` khi đúng yêu cầu locking.
- Xem xét optimistic locking khi phù hợp.

**Không tự gửi email/call API trước commit rồi coi rollback database sẽ đảo ngược được tác động ngoài hệ thống.** Nếu transaction cần retry vì deadlock, side effects phải idempotent.

## 39. Giảm deadlock bằng thứ tự khóa nhất quán

Giả sử hai transaction cần sửa item 1 và item 2.

**Thứ tự không nhất quán:**

```text
T_A: lock item 1 → chờ item 2
T_B: lock item 2 → chờ item 1
      = deadlock
```

**Thứ tự nhất quán:**

```text
T_A: lock item 1 → lock item 2
T_B: lock item 1 → lock item 2
      = có thể chờ, nhưng tránh chu trình kiểu này
```

Ví dụ:

```sql
BEGIN;

SELECT item_id
FROM lesson_lockchain.inventory
WHERE item_id IN (1, 2)
ORDER BY item_id
FOR UPDATE;

-- Thực hiện cập nhật theo quy tắc nghiệp vụ.

ROLLBACK;
```

`ORDER BY` và khóa hàng cần được đánh giá với semantics thực tế nếu có join/plan phức tạp; quy tắc quan trọng nhất là **mọi code path dùng cùng thứ tự lock acquisition** đối với các entity tương tranh.

### Không đảm bảo loại mọi deadlock

Deadlock cũng có thể phát sinh từ FK, index, DDL, nhiều loại lock hoặc các câu SQL ẩn trong trigger. Thứ tự lock nhất quán giảm một nhóm deadlock, không là chứng minh không còn deadlock nào.

## 40. SELECT FOR UPDATE NOWAIT và SKIP LOCKED

Khi không muốn chờ:

```sql
BEGIN;

SELECT item_id, quantity
FROM lesson_lockchain.inventory
WHERE item_id = 1
FOR UPDATE NOWAIT;

ROLLBACK;
```

Nếu lock không thể được cấp ngay, câu lệnh có thể lỗi nhanh. Với transaction explicit, phải xử lý rollback sau lỗi.

Đối với worker queue:

```sql
BEGIN;

SELECT item_id
FROM lesson_lockchain.inventory
ORDER BY item_id
FOR UPDATE SKIP LOCKED
LIMIT 2;

ROLLBACK;
```

`SKIP LOCKED` có thể bỏ qua các hàng đang bị khóa để worker xử lý hàng khác. Nhưng nó tạo một cái nhìn **không đầy đủ**, không phù hợp cho báo cáo cần tính tất cả hàng hoặc cho những logic không được bỏ qua một entity.

### SKIP LOCKED không “làm hết lock”

Một số loại khóa cấp relation vẫn cần được lấy, và `SKIP LOCKED` không có nghĩa mọi thao tác SQL liên quan đều không thể chờ. Nó áp dụng theo quy tắc của cú pháp row-locking, không phải thiết lập toàn server.

## 41. DELETE/UPDATE từng đợt và lock contention

Một transaction xóa hàng triệu dòng có thể giữ nhiều khóa lâu, tạo WAL lớn và ảnh hưởng tới nhiều writer.

Một hướng thiết kế thường gặp:

1. Chọn phạm vi công việc nhỏ.
2. Xử lý theo batch xác định.
3. Commit giữa các batch **khi nghiệp vụ cho phép**.
4. Có khóa/idempotency để retry.
5. Giám sát chờ khóa và số hàng thực tế.

Ví dụ thay vì giữ một transaction khổng lồ:

```text
Batch 1: 1000 rows → COMMIT
Batch 2: 1000 rows → COMMIT
Batch 3: 1000 rows → COMMIT
```

Đổi lại, dữ liệu có thể ở trạng thái **hoàn thành một phần** giữa các batch. Vì vậy đây là quyết định nghiệp vụ, không phải tối ưu vô điều kiện.

### Index cũng ảnh hưởng lock time

Một câu `UPDATE` chọn hàng theo `WHERE` nhưng thiếu index có thể tốn thời gian quét, khiến transaction sống lâu hơn. Index phù hợp có thể giảm thời gian tìm hàng; tuy nhiên bản thân index không giải quyết mọi tranh chấp khi **nhiều transaction cố sửa cùng một hàng nóng**.

## 42. Quan sát và lưu lịch sử lock waits

Một SELECT vào `pg_locks` chỉ cho **trạng thái gần hiện tại**. Nếu lock wait kéo dài 100 ms rồi biến mất, snapshot thủ công cách nhau 10 giây có thể không bắt được.

Có thể kết hợp:

- **`pg_stat_activity`:** trạng thái/PID/query đang chạy.
- **`pg_blocking_pids`:** blockers hiện tại.
- **`pg_locks`:** loại yêu cầu lock và thời điểm chờ.
- **`log_lock_waits`:** ghi log những lần chờ đủ lâu theo cấu hình.
- **Application tracing:** transaction/request boundaries, SQLSTATE, duration.
- **Metrics:** số session đang chờ lock, lock wait duration, transaction age, pool wait.
- **`pg_stat_statements`** khi được cấu hình: phân tích thời gian và tần suất query ở mức tổng hợp; không tự chỉ ra trực tiếp toàn bộ blocking chain hiện tại.

### Không thu thập vô hạn query text

Query có thể chứa dữ liệu khách hàng hoặc token nếu application gửi literal. Dashboard cần lọc quyền truy cập, che dữ liệu và có thời gian lưu trữ hợp lý.

### Chuẩn hóa dấu hiệu cho alert

Thay vì chỉ cảnh báo “query chạy hơn 5 giây”, cân nhắc alert khi:

- `wait_event_type='Lock'` kéo dài quá SLA.
- Một PID chặn nhiều backend cùng lúc.
- Có transaction `idle in transaction` quá lâu và thực sự đang chặn người khác.
- Lock waits tăng mạnh sau deploy/migration.
- Đã có nhiều lần `40P01`/`55P03`.

Ngưỡng cụ thể phụ thuộc workload và SLO; không có một con số chung phù hợp mọi database.

## 43. Sự khác nhau giữa khóa và snapshot MVCC

Một điểm liên kết quan trọng: **MVCC visibility không có nghĩa các writer không bao giờ chờ nhau**.

```text
Plain SELECT
  → đọc phiên bản visible theo snapshot
  → thường không chờ row UPDATE chỉ vì writer chưa COMMIT

UPDATE/DELETE/SELECT FOR UPDATE
  → muốn sửa/khóa một row
  → có thể phải chờ transaction khác

ALTER TABLE
  → cần relation lock mạnh
  → có thể chặn cả plain SELECT
```

### Ví dụ plain SELECT vẫn trả dữ liệu cũ

Session A:

```sql
BEGIN;

UPDATE lesson_lockchain.inventory
SET quantity = 77
WHERE item_id = 1;

-- Chưa COMMIT.
```

Session B:

```sql
SELECT quantity
FROM lesson_lockchain.inventory
WHERE item_id = 1;
-- Có thể thấy phiên bản đã commit trước đó.
```

Plain `SELECT` của B có thể chạy bình thường vì đọc tuple version visible, nhưng nếu B dùng `UPDATE` cùng row thì có thể phải chờ transaction A. Ngược lại, một `ALTER TABLE` giữ/xếp hàng lock mạnh có thể gây blocking cho plain SELECT ở cấp relation.

Không dùng `pg_blocking_pids` để giải thích chuyện SELECT thấy dữ liệu cũ: đó có thể là **snapshot isolation**, không phải lock wait.

## 44. Các dấu hiệu khác thường và cách phân biệt

| Hiện tượng | Nguyên nhân có thể | Công cụ kiểm tra |
|---|---|---|
| UPDATE chờ, `wait_event='transactionid'` | Row conflict/unique/FK hoặc chờ transaction khác. | `pg_blocking_pids` + `pg_locks` + SQL của hai bên. |
| SELECT thường bị chặn bởi ALTER TABLE | `AccessExclusiveLock` hoặc lock queue. | `pg_locks` relation modes, `pg_blocking_pids`. |
| Blocker `idle in transaction` | Chưa commit/rollback sau DML/SELECT có lock. | `pg_stat_activity.xact_start/state` + blockers. |
| Blocker `idle` nhưng giữ advisory | Session-level advisory lock. | `pg_locks.locktype='advisory'`. |
| PID blocker = 0 | Có thể là prepared transaction. | `pg_prepared_xacts` và quy trình 2PC. |
| Wait event không phải Lock | IO/LWLock/Client/other wait. | `pg_stat_activity.wait_event_type`, diagnostics phù hợp. |
| Không thấy blocker khi query lại | Lock đã được nhả hoặc đồ thị thay đổi. | Sampling/log_lock_waits. |
| Query nhanh nhưng thỉnh thoảng timeout | Lock waits ngắn/tăng theo đợt hoặc contention khác. | Logs, sampling, tracing. |
| Deadlock 40P01 | Chu trình chờ khóa đã được PostgreSQL phát hiện. | Server log, SQLSTATE, thứ tự lock. |
| Transaction failed 25P02 sau lock_timeout | Statement trước đã lỗi, transaction chưa rollback. | Lỗi SQLSTATE đầu tiên và lifecycle transaction. |
| Đọc thấy dữ liệu cũ nhưng không chờ | MVCC snapshot/replica lag/cache. | Isolation, WAL replay, ứng dụng. |

## 45. Quy trình xử lý sự cố lock chain thực tế

Giả sử API inventory đột ngột tăng latency.

### Bước 1 — Xác định có lock wait hay không

```sql
SELECT
    pid,
    state,
    wait_event_type,
    wait_event,
    query_start
FROM pg_catalog.pg_stat_activity
WHERE datname = current_database()
  AND wait_event_type = 'Lock'
ORDER BY query_start;
```

### Bước 2 — Lấy cạnh chặn trực tiếp

```sql
SELECT
    a.pid AS blocked_pid,
    b.blocker_pid
FROM pg_catalog.pg_stat_activity AS a
CROSS JOIN LATERAL unnest(
    pg_catalog.pg_blocking_pids(a.pid)
) AS b(blocker_pid)
WHERE a.datname = current_database();
```

### Bước 3 — Xem blocker có đang chờ tiếp không

Nếu blocker B cũng nằm trong `blocked_pid`, đây là **một tầng giữa trong chuỗi**. Dùng recursive CTE để tìm các đường phía trên.

### Bước 4 — Xem loại lock

```sql
SELECT
    pid,
    locktype,
    mode,
    granted,
    waitstart,
    relation,
    transactionid
FROM pg_catalog.pg_locks
WHERE NOT granted
ORDER BY waitstart NULLS LAST;
```

### Bước 5 — Xác định owner và thời gian

Xem `usename`, `application_name`, `backend_start`, `xact_start`, `state_change` và logs/tracing. Phân biệt câu SQL **đang chờ** với câu SQL **đã lấy lock trước đó**.

### Bước 6 — Đánh giá ảnh hưởng

Đếm blocker đang chặn trực tiếp/gián tiếp bao nhiêu request, độ dài wait, SLO của API, lock có phải DDL hay prepared transaction.

### Bước 7 — Giải phóng có kiểm soát

Ưu tiên để owner commit/rollback nếu có thể. Cân nhắc cancel/terminate chỉ khi đã xác minh PID và tác động. Nếu blocker=0, xử lý qua quy trình prepared transaction, không kill PID 0.

### Bước 8 — Tìm nguyên nhân gốc trong code

Một số lỗi thường gặp:

- Transaction mở khi gọi HTTP API.
- Exception bị catch nhưng không rollback.
- Endpoint đọc giữ transaction/lock lâu không cần thiết.
- DDL chạy giờ cao điểm.
- Batch update quá lớn.
- Các code path lấy row locks theo thứ tự khác nhau.
- Advisory lock không được nhả.
- Connection pool bị cạn hoặc giữ backend quá lâu.

### Bước 9 — Ngăn tái phát

Đặt timeout hợp lý, giảm transaction scope, làm rõ ownership, thêm metric/alert, cân nhắc retry deadlock và tổ chức migration tránh lock contention.

## 46. Những hiểu nhầm phổ biến

**“Backend có `state='active'` nghĩa là đang dùng CPU.”** Không. Backend active có thể đang chờ `Lock`, `IO` hoặc loại wait khác.

**“Blocker cũng phải có `wait_event_type='Lock'`.”** Không. Blocker có thể `idle in transaction` hoặc `idle` khi giữ advisory lock.

**“`pg_locks.granted=false` chính là một blocker.”** Không. Đây là một **yêu cầu khóa đang chờ**. Blocker có thể nằm ở một hàng khác hoặc ở phía trước trong queue.

**“Mọi row lock đều hiện `locktype='tuple'`.”** Không. Chờ row update thường thể hiện qua `transactionid`.

**“Cùng relation OID nghĩa là hai lock xung đột.”** Không. Cần xét database, mode và lock queue.

**“Một waiter có đúng một blocker.”** Không. `pg_blocking_pids` trả **mảng**; có thể nhiều PID và các nhánh.

**“`pg_blocking_pids` chỉ trả những session đã được cấp khóa.”** Không. Nó có thể trả soft blockers phía trước queue.

**“Root blocker luôn là câu query đang chạy lâu nhất.”** Không. Root có thể `idle in transaction`, `idle` với advisory lock, hoặc prepared transaction.

**“PID 0 là một backend cần terminate.”** Không. PID 0 có thể biểu diễn prepared transaction blocker.

**“Lệnh `pg_cancel_backend` chắc chắn nhả lock của idle transaction.”** Không. Cancel statement không tự kết thúc transaction đang mở.

**“Lệnh `pg_terminate_backend` chỉ dừng SELECT nhưng không ảnh hưởng dữ liệu.”** Không. Session chưa commit có thể bị rollback và ảnh hưởng ứng dụng.

**“Xóa lock bằng cách DELETE ở pg_locks.”** Không. `pg_locks` là view quan sát, không phải bảng bạn có thể sửa để can thiệp lock manager.

**“Có thể xác định thời gian chờ khóa từ query_start hoàn toàn chính xác.”** Không. Statement có thể làm việc trước khi bắt đầu chờ; ưu tiên `waitstart` khi có.

**“`pg_locks` là snapshot tuyệt đối nguyên tử của mọi lock.”** Không. Trạng thái lock có thể thay đổi nhanh và view thu dữ liệu từ nhiều thành phần.

**“Không thấy blocker khi kiểm tra lần hai nghĩa giám sát lần đầu sai.”** Không. Transaction có thể vừa commit/rollback và lock wait đã kết thúc.

**“Thấy `SELECT 1` trong blocker.query nghĩa `SELECT 1` lấy row lock.”** Không. Với blocker idle, query text có thể là lệnh gần nhất, không phải lệnh lấy khóa.

**“Advisory lock luôn được nhả khi transaction commit.”** Không. Session-level advisory lock tồn tại qua commit/rollback; transaction-level mới được nhả theo transaction.

**“Tăng lock_timeout sẽ làm hết contention.”** Không. Timeout thay đổi hành vi thất bại/chờ, không giải quyết tài nguyên nóng.

**“Deadlock là chỉ một query chậm bất thường.”** Không. Deadlock là chu trình chờ và PostgreSQL có cơ chế phát hiện/abort nạn nhân.

**“SKIP LOCKED bảo đảm mọi câu SQL không chờ.”** Không. Nó áp dụng theo phạm vi của row-locking clause và vẫn có những loại lock khác.

**“Mọi blocker đều cần được kill.”** Không. Nhiều blocker đang chạy giao dịch hợp lệ, tốt hơn để kết thúc tự nhiên hoặc sửa code/transaction scope.

## 47. Checklist chuẩn cho dashboard theo dõi

Một dashboard hoặc runbook có thể hiển thị:

| Trường/metric | Vì sao quan trọng |
|---|---|
| Waiting PID và backend_start | Nhận diện đúng backend; tránh nhầm PID tái sử dụng. |
| Waiting user, database, application_name | Xác định service chịu ảnh hưởng. |
| Waiting query và query_age | Biết statement nào đang chờ và tổng thời gian đã chạy. |
| wait_event_type, wait_event | Phân biệt heavyweight Lock với IO/LWLock/Client. |
| pg_locks.locktype/mode/granted/waitstart | Biết loại lock request và thời gian chờ khi có. |
| Direct blocker PIDs | Cạnh của wait-for graph. |
| Blocking chain/path | Tìm upstream/terminal blocker. |
| Blocking state/xact_age | Phát hiện blocker idle trong transaction lâu. |
| Số waiter trực tiếp/gián tiếp | Ưu tiên giải quyết theo mức ảnh hưởng. |
| PID 0/prepared_xacts | Tránh xử lý sai prepared transactions. |
| Tần suất lock timeouts/deadlocks | Theo dõi xu hướng contention. |
| Event log và trace ID | Tìm SQL thực sự lấy lock và nguyên nhân trong code. |

Đừng xây hệ thống tự terminate chỉ từ **một lần lấy mẫu**. Đồ thị thay đổi nhanh; nên kiểm tra lại và cần sự phê duyệt/policy rõ.

## 48. Bài tập thực hành

### Bài 1 — Quan sát wait_event

Tạo hai session: A `BEGIN; UPDATE item_id=1` rồi giữ transaction; B `UPDATE` cùng hàng. Session M đọc `pg_stat_activity`. Ghi lại `state`, `wait_event_type` và `wait_event` của B. A và B khác gì nhau?

### Bài 2 — Tìm direct blocker

Ở tình huống bài 1, dùng `pg_blocking_pids(B_PID)` tìm PID của A. Giải thích vì sao hàm trả mảng, không phải một số duy nhất.

### Bài 3 — unnest blocking PIDs

Viết truy vấn từ `pg_stat_activity` kết hợp `CROSS JOIN LATERAL unnest(pg_blocking_pids(pid))` để tạo mỗi cạnh `waiting_pid → blocking_pid` một hàng.

### Bài 4 — Đọc granted và waitstart

Tìm các hàng `pg_locks` có `granted=false`. So sánh `clock_timestamp()-waitstart` với `clock_timestamp()-query_start` của waiter. Vì sao hai khoảng có thể khác nhau?

### Bài 5 — Row lock không hiện tuple

Trong lab, quan sát tranh chấp UPDATE cùng hàng. Tìm `locktype='transactionid'` và `mode='ShareLock'` của waiter khi có. Vì sao không thấy `granted=true` của `tuple` không chứng minh không có row-level lock?

### Bài 6 — Mode của relation lock

Giải thích vì sao `AccessShareLock` từ SELECT có thể chặn `AccessExclusiveLock` của ALTER TABLE, nhưng hai SELECT thường không xung đột chỉ vì cùng bảng.

### Bài 7 — Hàng đợi DDL

A giữ transaction sau SELECT, B chạy ALTER TABLE chờ, C đến sau SELECT. Quan sát `pg_blocking_pids` của C. Giải thích vai trò soft blocker.

### Bài 8 — Tạo chuỗi ba tầng

A khóa item 1; B khóa item 2 rồi chờ item 1; C chờ item 2. Dùng truy vấn cạnh trực tiếp vẽ `C → B → A` và giải phóng ba transaction theo thứ tự an toàn.

### Bài 9 — Recursive CTE

Dùng recursive CTE theo `edges(waiting_pid,blocker_pid)` để xây `pid_chain`. Tại sao cần giới hạn depth và chống lặp PID?

### Bài 10 — Nhiều nhánh chặn

Giả sử W bị chặn trực tiếp bởi B1 và B2, B1 chờ A. Vẽ đồ thị và giải thích vì sao không nên ép W thành một root blocker duy nhất.

### Bài 11 — Đếm ảnh hưởng

Viết truy vấn đếm `COUNT(DISTINCT waiting_pid)` theo blocker PID. Phân biệt số waiter trực tiếp với tổng origin waiters qua mọi tầng.

### Bài 12 — Kiểm tra blocker idle in transaction

Chạy UPDATE trong transaction A rồi một câu `SELECT 1`, sau đó để A idle. B chờ row lock của A. Tại sao `pg_stat_activity.query` của A có thể hiện `SELECT 1` mà nguyên nhân lock thực là UPDATE trước đó?

### Bài 13 — Advisory lock

A lấy `pg_advisory_lock(12345)`; B cố lấy cùng key. Dùng `pg_locks` và `pg_blocking_pids` tìm blocker. Kết thúc bằng `pg_advisory_unlock` ở A. So sánh với `pg_advisory_xact_lock`.

### Bài 14 — Prepared transaction

Không cần thực sự tạo prepared transaction: giải thích vì sao một blocker PID 0 không thể xử lý bằng terminate, và view nào dùng để kiểm tra prepared transactions.

### Bài 15 — Deadlock

Hai session khóa item 1 và item 2 theo thứ tự ngược nhau. Quan sát `40P01` và mô tả vì sao transaction bị chọn làm nạn nhân cần rollback trước khi thử lại.

### Bài 16 — lock_timeout

Trong transaction lab, đặt `SET LOCAL lock_timeout = '1s'` rồi chạy UPDATE trên hàng đã bị khóa. Ghi SQLSTATE đầu tiên; sau đó giải thích vì sao câu SELECT tiếp theo có thể nhận `25P02` nếu chưa rollback.

### Bài 17 — statement_timeout khác lock_timeout

Đưa ra hai tình huống: query chậm vì tính toán/IO nhưng không đợi lock, và query chậm vì bị chặn. Timeout nào đo đúng mỗi tình huống? Vì sao không coi `query_age` là `lock_wait_age`?

### Bài 18 — pg_cancel_backend

Một blocker đang `idle in transaction` và không có statement chạy. Tại sao `pg_cancel_backend` có thể không giải phóng lock? Khi nào có thể cần owner rollback hoặc terminate theo quy trình?

### Bài 19 — Xác minh PID trước khi terminate

Đề xuất các trường cần so sánh trước khi gửi lệnh tác động PID: `pid`, `backend_start`, `usename`, `application_name`, `state` và mục tiêu nghiệp vụ. Tại sao PID lấy từ log cũ không đủ an toàn?

### Bài 20 — Application log và blocker query

Một blocker `idle in transaction` đang hiện query `SELECT 1`. Hãy mô tả cách dùng request tracing để tìm câu UPDATE đã lấy lock trước đó mà không suy đoán sai từ query text.

### Bài 21 — pg_locks trên nhiều database

Vì sao không thể join `pg_locks.relation` với `pg_class.oid` của database hiện tại mà bỏ qua `pg_locks.database`? Viết truy vấn có điều kiện OID database phù hợp.

### Bài 22 — Phân biệt các wait types

Một session chậm có `wait_event_type='IO'`, một session khác là `Lock`. Khi nào `pg_blocking_pids` hữu ích? Tại sao không nên gọi mọi wait là lock wait?

### Bài 23 — Connection pool

Một endpoint Spring `@Transactional` sửa inventory rồi chờ HTTP API 30 giây. Giải thích cách hình thành chain và đề xuất thay đổi để transaction ngắn hơn.

### Bài 24 — Alert theo số waiter

Xây ý tưởng alert khi một blocker chặn trực tiếp từ 10 request trở lên quá 5 giây. Bạn sẽ lấy dữ liệu nào từ `pg_blocking_pids`, `pg_stat_activity` và `pg_locks`? Vì sao nên lấy mẫu nhiều lần?

### Bài 25 — Root blocker không phải root cause

Đồ thị cho thấy C → B → A; A không có blocker, nhưng đang chờ client gửi COMMIT. Phân biệt **đầu chuỗi khóa** với **nguyên nhân gốc của ứng dụng**.

### Bài 26 — Thứ tự lấy khóa

Hai transaction cần update item 1 và item 2. Mô tả thứ tự bất nhất gây deadlock, rồi thiết kế thứ tự khóa nhất quán để giảm rủi ro. Những loại deadlock nào vẫn có thể xảy ra?

### Bài 27 — SKIP LOCKED

Với hai worker lấy job theo `FOR UPDATE SKIP LOCKED`, giải thích tại sao có thể giảm tranh chấp hàng và tại sao kết quả không phù hợp cho báo cáo cần thấy toàn bộ job.

### Bài 28 — Tổng hợp runbook

Viết một quy trình 8–10 bước để xử lý API timeout vì khóa: nhận diện wait event, tìm direct blockers, truy chain, phân loại locktype/mode, xác minh owner/transaction age, đánh giá ảnh hưởng, quyết định giải phóng, rollback/retry và ngăn tái phát.

## Kết luận

**`pg_blocking_pids()` và `pg_locks` phục vụ hai câu hỏi khác nhau nhưng bổ sung cho nhau.** `pg_blocking_pids(pid)` trả lời **“backend này đang bị backend nào chặn?”** theo ngữ nghĩa lock manager, bao gồm hard blockers và một số soft blockers trong hàng đợi. `pg_locks` trả lời **“những yêu cầu khóa nào đang có, loại nào, mode nào đã được cấp và mode nào đang chờ?”**. Khi kết hợp `pg_stat_activity`, bạn có đủ thông tin để nhìn thấy một phần quan trọng của tình trạng chờ khóa đang diễn ra.

Muốn hiểu **chuỗi chặn**, hãy dựng cạnh `waiter → blocker`, sau đó truy ngược nhiều tầng bằng recursive CTE thay vì chỉ nhìn waiter đầu tiên. Một backend có thể vừa là **waiter** vừa là **blocker**; một waiter có thể có nhiều blocker; điểm cuối trong đồ thị quan sát không nhất thiết là nguyên nhân nghiệp vụ. Những trường hợp như **row lock hiển thị qua transactionid**, **soft blockers đứng trước hàng đợi**, **advisory locks** và **prepared transactions với PID 0** cần được xử lý riêng, không được suy đoán từ một phép self-join đơn giản trên `pg_locks`.

Trong vận hành, **ưu tiên xác minh và xử lý transaction owner** trước khi cancel/terminate backend. Đọc `xact_start`, `waitstart` và trạng thái ứng dụng; nhớ rằng blocker `idle in transaction` có thể chỉ hiện statement gần nhất chứ không phải statement đã giữ khóa. Kết hợp timeout, log lock waits, transaction ngắn, thứ tự lấy khóa nhất quán và retry có giới hạn cho deadlock. Khi đó, việc phát hiện blocking chain không chỉ giúp “giải phóng một truy vấn đang đứng” mà còn giúp sửa thiết kế giao dịch để giảm contention và bảo vệ tính đúng đắn của hệ thống PostgreSQL.
