# Giao dịch dài, replication slot và chân trời dọn dẹp trong PostgreSQL

PostgreSQL dùng **MVCC (Multi-Version Concurrency Control)** để cho nhiều transactions đọc và ghi dữ liệu đồng thời. Khi một transaction cập nhật hoặc xóa một hàng, PostgreSQL thường tạo phiên bản hàng mới và giữ phiên bản cũ cho đến khi chắc chắn không còn snapshot nào cần nhìn thấy nó.

**VACUUM** thu hồi những row versions đã không còn cần thiết, cập nhật visibility/free-space metadata và hỗ trợ chống transaction ID wraparound. Nhưng VACUUM không thể xóa mọi tuple đã trở thành dead ngay khi nhìn thấy chúng. Nó phải tôn trọng một ranh giới an toàn gọi là **cleanup horizon** — chân trời dọn dẹp.

Một transaction giữ snapshot lâu, một logical replication slot không được tiêu thụ, hoặc một standby gửi feedback về snapshot cũ có thể làm horizon bị ghim ở quá khứ. Khi đó:

- Dead tuples tiếp tục nằm trong heap.
- TOAST data cũ cũng có thể chưa được thu hồi.
- Autovacuum chạy nhưng không thể dọn những versions còn cần cho snapshot/consumer.
- Bảng và index có thể phình to.
- Replication slot có thể giữ WAL khiến filesystem tăng dung lượng.
- Nếu kéo dài, database có thể gặp áp lực transaction ID wraparound.

Bài **“Giao dịch dài, replication slot và chân trời dọn dẹp”**, thuộc chương **VACUUM** của module **Database Engine Relational PostgreSQL**, giải thích mối quan hệ giữa MVCC snapshots, XID/XMIN, cleanup horizon, long-running transactions, logical/physical replication slots, hot standby feedback, VACUUM, freezing và các công cụ chẩn đoán/khắc phục.

> **Nguyên tắc cốt lõi:** VACUUM chỉ được thu hồi những row versions mà mọi snapshot và cơ chế giữ dữ liệu liên quan đều đã an toàn để bỏ. Muốn xử lý bloat, trước hết phải tìm thứ đang giữ cleanup horizon ở quá khứ.

---

## 1. Vì sao VACUUM không thể xóa ngay tuple cũ?

Giả sử một bảng có hàng:

~~~sql
CREATE TABLE accounts (
    account_id BIGINT PRIMARY KEY,
    balance NUMERIC(14,2) NOT NULL
);

INSERT INTO accounts VALUES (1, 1000.00);
~~~

Transaction A bắt đầu một snapshot và đọc balance:

~~~sql
BEGIN ISOLATION LEVEL REPEATABLE READ;

SELECT balance
FROM accounts
WHERE account_id = 1;
~~~

Transaction B cập nhật:

~~~sql
UPDATE accounts
SET balance = 900.00
WHERE account_id = 1;

COMMIT;
~~~

PostgreSQL không thể đơn giản ghi đè phiên bản 1000 thành 900 nếu transaction A vẫn cần nhìn thấy trạng thái cũ. Theo snapshot của A, hàng cũ vẫn có thể hợp lệ; phiên bản mới được các snapshots phù hợp nhìn thấy.

Vì vậy heap có thể tạm thời chứa:

~~~text
account_id = 1
  |
  +-- row version cũ: balance = 1000
  |
  +-- row version mới: balance = 900
~~~

Khi không còn snapshot nào cần version cũ, VACUUM mới có thể thu hồi nó.

## 2. MVCC và transaction IDs

Mỗi tuple PostgreSQL có metadata MVCC, bao gồm các thông tin liên quan đến transaction tạo và transaction kết thúc hiệu lực của version.

Các trường nội bộ quan trọng thường được gọi là:

- `xmin`: transaction ID tạo tuple version.
- `xmax`: transaction ID xóa, cập nhật hoặc khóa tuple theo ngữ cảnh.

Đây là các trường implementation trong tuple header, không phải các cột business do người dùng khai báo.

### 2.1. xmin trong tuple không giống backend_xmin

Cùng tên `xmin` xuất hiện ở nhiều ngữ cảnh:

- Tuple header `xmin`: XID tạo row version.
- `pg_stat_activity.backend_xmin`: snapshot horizon mà backend đang giữ.
- `pg_replication_slots.xmin`: XID horizon mà replication slot yêu cầu giữ.
- `pg_replication_slots.catalog_xmin`: horizon dành cho catalog tuples trong logical decoding.

Không trộn các trường này với nhau. Chúng liên quan cùng hệ thống MVCC nhưng đại diện những thứ khác nhau.

## 3. Cleanup horizon là gì?

**Cleanup horizon** là ranh giới transaction ID mà PostgreSQL dùng để xác định các row versions cũ nào không còn cần cho bất kỳ snapshot/consumer được bảo vệ nào.

Ở mức khái niệm:

~~~text
Transaction ID cũ --------------------------> mới
       |
       |       Cleanup horizon
       v             |
  Các version        |      Các version còn có
  có thể xem xét     |      thể được snapshot cần
  để dọn             v
~~~

Nếu một tuple đã bị xóa bởi transaction đã commit nhưng transaction ID của thao tác đó chưa nằm đủ cũ so với horizon, VACUUM phải giữ lại.

Tên nội bộ và cách tính horizon có nhiều chi tiết theo version; ứng dụng nên quan sát các nguồn giữ horizon thay vì phụ thuộc vào một biến nội bộ duy nhất.

### 3.1. Horizon không phải thời gian

Cleanup horizon không phải “xóa những hàng cũ hơn 24 giờ”. Nó dựa trên transaction IDs và snapshot visibility. Một transaction chỉ tồn tại vài phút cũng có thể giữ version rất cũ nếu nó giữ snapshot lâu.

## 4. Dead tuple và removable tuple khác nhau

Một tuple có thể không còn được query mới nhìn thấy nhưng vẫn chưa an toàn để xóa.

Phân biệt:

- **Live tuple:** version vẫn có thể được snapshot phù hợp nhìn thấy.
- **Dead tuple:** version không còn là phiên bản hiện hành theo trạng thái transaction.
- **Removable tuple:** version đã cũ hơn cleanup horizon và không còn được snapshot/consumer cần; VACUUM có thể thu hồi.

Vì vậy thống kê dead tuples không đồng nghĩa tất cả đều đã có thể xóa.

Khi chạy VACUUM VERBOSE, PostgreSQL có thể báo số tuples dead nhưng chưa removable. Đây là một dấu hiệu hữu ích khi điều tra long transactions hoặc replication retention.

## 5. Long-running transaction giữ snapshot

Một transaction giữ snapshot cũ có thể ngăn VACUUM thu hồi những row versions mà snapshot đó cần.

Ví dụ:

~~~sql
BEGIN ISOLATION LEVEL REPEATABLE READ;

SELECT *
FROM accounts
WHERE account_id = 1;

-- Ứng dụng giữ transaction mở lâu.
~~~

Trong khi đó, các transactions khác tiếp tục UPDATE/DELETE hàng.

Hệ quả: các versions cũ có thể tiếp tục tích lũy cho đến khi transaction A COMMIT hoặc ROLLBACK.

### 5.1. Transaction dài không nhất thiết chạy query liên tục

Một transaction có thể đang:

- Chờ user nhập dữ liệu.
- Chờ HTTP request khác.
- Chờ message broker.
- Chờ lock.
- Giữ cursor hoặc snapshot.
- Ở trạng thái idle in transaction.

Điều quan trọng không chỉ là query có đang chạy, mà là **backend có còn giữ snapshot/XID khiến cleanup bị giới hạn hay không**.

## 6. READ COMMITTED và REPEATABLE READ

Ở isolation level mặc định `READ COMMITTED`, mỗi statement thường lấy snapshot mới. Khi statement kết thúc, snapshot của statement đó không nhất thiết tiếp tục được giữ đến cuối transaction.

Ở `REPEATABLE READ`, transaction dùng một snapshot nhất quán xuyên suốt transaction; snapshot cũ có thể được giữ đến khi transaction kết thúc.

`SERIALIZABLE` cũng có snapshot semantics riêng và có thể giữ thông tin cần thiết cho việc kiểm soát serialization.

Do đó, một transaction ở REPEATABLE READ/SERIALIZABLE tồn tại lâu có thể giữ cleanup horizon lâu hơn một transaction READ COMMITTED đang idle giữa hai statements.

**Không kết luận chỉ từ state='idle in transaction'.** Hãy kiểm tra `backend_xmin`, `backend_xid`, isolation level và thời gian transaction để biết backend có thực sự giữ snapshot/horizon không.

## 7. Idle in transaction

Một ứng dụng có thể mở transaction:

~~~sql
BEGIN;

SELECT *
FROM orders
WHERE order_id = 100;

-- Chờ người dùng xác nhận trong 30 phút.
~~~

Nếu connection không COMMIT/ROLLBACK, transaction vẫn mở. Với snapshot được giữ, VACUUM có thể phải giữ lại những versions cũ.

Các nguyên nhân thường gặp:

- Code mở transaction trước khi gọi external API.
- ORM transaction scope quá rộng.
- Exception path quên rollback.
- Connection pool trả connection khi transaction chưa kết thúc.
- Một workflow chờ thao tác người dùng trong transaction.
- Worker mở transaction rồi chờ message.

### 7.1. Không phải mọi idle transaction đều có cùng tác động

Ở READ COMMITTED, snapshot của câu SELECT đã kết thúc có thể không còn được giữ trong lúc session idle. Nhưng transaction vẫn có thể giữ locks hoặc XID đã được cấp và tạo vấn đề khác.

Dùng `backend_xmin` và `backend_xid` để điều tra thay vì chỉ nhìn state.

## 8. Exported snapshots

PostgreSQL cho phép export snapshot bằng:

~~~sql
SELECT pg_export_snapshot();
~~~

Một transaction khác có thể import snapshot này theo quy tắc transaction isolation phù hợp.

Snapshot được export chỉ tồn tại trong thời gian transaction export còn mở. Nếu exporter giữ transaction lâu để các workers khác import snapshot, nó cũng có thể giữ một horizon cũ và trì hoãn cleanup.

Đây là một trường hợp đặc biệt thường xuất hiện trong các workflow parallel dump/consistent reads.

### 8.1. Không giữ exporter transaction lâu hơn cần thiết

Hãy thiết kế thời gian sống của exported snapshot rõ ràng. Khi mọi importer đã thiết lập snapshot theo yêu cầu, kết thúc exporter transaction đúng quy trình.

## 9. Prepared transactions và hai-phase commit

Transaction được PREPARE để chờ COMMIT/ROLLBACK trong two-phase commit có thể tồn tại qua thời gian dài và giữ XID/locks.

Quan sát:

~~~sql
SELECT
    transaction,
    gid,
    prepared,
    owner,
    database
FROM pg_prepared_xacts
ORDER BY prepared;
~~~

Prepared transaction bị bỏ quên có thể cản trở maintenance, giữ locks và làm trạng thái transaction tồn tại lâu. Không để các prepared transactions vô chủ kéo dài.

Trước khi COMMIT PREPARED hoặc ROLLBACK PREPARED, phải xác định trạng thái coordinator/distributed transaction; quyết định sai có thể làm các hệ thống tham gia mất nhất quán.

## 10. Replication slot là gì?

**Replication slot** giữ lại những tài nguyên mà một consumer replication/decoding có thể còn cần.

Ví dụ:

- Logical decoding consumer đọc WAL để lấy row changes.
- Physical standby cần WAL để replay.
- Một pipeline CDC tiêu thụ changes bất đồng bộ.

Slot giúp PostgreSQL không loại bỏ WAL cần thiết trước khi consumer xác nhận tiến độ phù hợp.

Nhưng một slot có thể tồn tại dù consumer **không còn kết nối**. Slot inactive vẫn có thể giữ WAL hoặc transaction horizon.

## 11. Hai loại replication slot

| Loại | Mục đích chính | Tài nguyên có thể giữ |
|---|---|---|
| Physical slot | Giữ WAL cho physical replication consumer | WAL từ restart_lsn; có thể liên quan feedback horizon tùy cấu hình |
| Logical slot | Giữ tiến độ logical decoding/CDC | WAL, transaction xmin và catalog_xmin theo trạng thái slot |

Physical và logical slots không có cùng mục đích.

### 11.1. Slot không đồng nghĩa replication connection

Một replication connection có thể disconnect nhưng slot vẫn còn. Slot là state bền vững được lưu trên server cho consumer có thể quay lại.

### 11.2. Slot inactive không tự được xóa

Không có consumer online không có nghĩa slot không còn tác động. Một slot cũ có thể giữ WAL lâu ngày.

## 12. Các trường quan trọng của pg_replication_slots

View `pg_replication_slots` cung cấp thông tin về slot.

| Cột | Ý nghĩa |
|---|---|
| `slot_name` | Tên slot |
| `slot_type` | physical hoặc logical |
| `database` | Database liên quan nếu slot có scope database |
| `active` | Slot hiện đang được sử dụng hay không |
| `active_pid` | PID của process đang dùng slot, nếu active |
| `xmin` | XID horizon slot yêu cầu giữ cho tuple visibility |
| `catalog_xmin` | Horizon giữ catalog tuples cho logical decoding |
| `restart_lsn` | WAL LSN cũ nhất slot có thể còn cần |
| `confirmed_flush_lsn` | Tiến độ flush đã được xác nhận của logical slot theo semantics slot |

Không phải mọi trường đều có giá trị cho mọi loại slot hoặc mọi thời điểm.

### 12.1. xmin và catalog_xmin

`xmin` có thể ngăn VACUUM thu hồi những tuple versions mà consumer còn cần.

`catalog_xmin` bảo vệ các catalog tuples cần thiết cho logical decoding, chẳng hạn metadata schema/type/relations theo snapshot decoder.

Một logical slot có thể gây cả:

- **Heap/table bloat** qua xmin.
- **Catalog bloat** qua catalog_xmin.

### 12.2. restart_lsn là chiều WAL

`restart_lsn` giữ WAL segments cần cho slot. Đây là vấn đề **WAL retention**, không phải cùng thứ với heap cleanup horizon.

Một slot có thể gây disk growth ở `pg_wal` ngay cả khi xmin không ghim heap; hoặc giữ xmin/catalog_xmin làm bloat dù WAL retention được kiểm soát ở một mức khác.

## 13. Logical replication slot và cleanup horizon

Logical decoding cần đọc các changes từ WAL và có thể cần row/catalog versions tương ứng.

Slot giữ `xmin` và `catalog_xmin` theo nhu cầu decoding. VACUUM phải tôn trọng những horizons này để không xóa dữ liệu mà logical decoding vẫn có thể cần.

Một consumer chậm hoặc bị bỏ quên có thể khiến:

~~~text
Logical slot inactive
       |
       +--> restart_lsn cũ
       |       |
       |       +--> WAL tiếp tục được giữ
       |
       +--> xmin cũ
       |       |
       |       +--> dead tuples không được thu hồi
       |
       +--> catalog_xmin cũ
               |
               +--> catalog versions được giữ
~~~

Đây là lý do **inactive logical slot** phải được giám sát, không chỉ xem trạng thái replication connection.

## 14. Physical slot và hot_standby_feedback

Physical replication slot chủ yếu giúp standby có WAL cần thiết để replay. Một cơ chế khác là `hot_standby_feedback`.

Trên standby:

~~~sql
SHOW hot_standby_feedback;
~~~

Khi bật, standby gửi thông tin snapshot horizon về primary để primary tránh dọn những row versions mà query trên standby vẫn cần, từ đó giảm xung đột recovery query.

Đổi lại, feedback có thể giữ cleanup horizon trên primary ở quá khứ và gây bloat.

### 14.1. Feedback khác replication slot

- Replication slot giữ tài nguyên theo trạng thái slot.
- Hot standby feedback gửi thông tin xmin từ standby về primary.
- Chúng có thể cùng tồn tại.
- Không coi việc có physical slot là bằng chứng duy nhất của horizon đang bị giữ.

Trên primary, quan sát `pg_stat_replication.backend_xmin` để thấy xmin mà standby feedback đang báo, nếu có.

## 15. Trade-off của hot_standby_feedback

Khi feedback tắt, primary có thể dọn versions cũ, nhưng query trên standby có thể bị hủy do recovery conflict nếu cần những versions đó.

Khi feedback bật:

- Standby queries ít bị cancel do cleanup conflict hơn.
- Primary có thể phải giữ dead tuples lâu hơn.
- Bloat trên primary có thể tăng nếu standby query lâu.
- Một standby transaction cũ có thể ảnh hưởng VACUUM ở primary.

Không bật/tắt chỉ dựa trên một metric. Cân nhắc SLA query trên standby, storage capacity, vacuum health và replication topology.

## 16. max_slot_wal_keep_size không giải quyết mọi horizon

PostgreSQL có cấu hình `max_slot_wal_keep_size` để giới hạn lượng WAL mà replication slots được phép giữ qua checkpoints theo chính sách server.

~~~sql
SHOW max_slot_wal_keep_size;
~~~

Tham số này điều khiển **WAL retention**, không phải một nút trực tiếp để buộc VACUUM bỏ qua `xmin` hoặc `catalog_xmin`.

Nếu slot vượt giới hạn WAL, slot có thể bị mất hiệu lực vì WAL cần thiết đã bị loại bỏ. Consumer có thể phải tạo lại slot và đồng bộ lại từ nguồn khác.

### 16.1. Không nhầm WAL retention với tuple retention

| Vấn đề | Trường/setting liên quan |
|---|---|
| WAL segments bị giữ | `restart_lsn`, `wal_keep_size`, `max_slot_wal_keep_size` |
| Heap tuples bị giữ | `xmin`, active snapshots, standby feedback |
| Catalog tuples bị giữ | `catalog_xmin` |
| Consumer tiến độ logical | `confirmed_flush_lsn` |

Giới hạn WAL không thay thế việc theo dõi xmin/catalog_xmin.

## 17. wal_keep_size và replication slot

`wal_keep_size` là một thiết lập giữ một lượng WAL tối thiểu cho standby theo cấu hình.

Replication slots có thể giữ WAL dựa trên vị trí cần thiết của từng slot. Hai cơ chế có mục đích liên quan nhưng không giống nhau.

Nếu WAL bị giữ quá lâu:

- `pg_wal` có thể tăng.
- Filesystem có thể hết chỗ.
- Checkpoints/archiving có thể chịu áp lực.
- Replication slot có thể bị invalidated nếu giới hạn slot được áp dụng.

Không giải quyết bằng cách xóa WAL files thủ công trong thư mục data.

## 18. Inactive replication slot là rủi ro

Một slot có thể inactive vì:

- Consumer CDC bị dừng.
- Connector bị xóa nhưng slot chưa cleanup.
- Deployment đổi tên slot.
- Network lỗi kéo dài.
- Consumer không thể xử lý schema change.
- Một slot test bị bỏ quên.
- Failover làm consumer không quay lại đúng primary.

Inactive không đồng nghĩa an toàn để drop. Trước khi xóa, phải biết consumer còn cần dữ liệu từ slot hay không.

## 19. Quan sát replication slots

Query cơ bản:

~~~sql
SELECT
    slot_name,
    slot_type,
    database,
    active,
    active_pid,
    xmin,
    age(xmin) AS xmin_age,
    catalog_xmin,
    age(catalog_xmin) AS catalog_xmin_age,
    restart_lsn,
    confirmed_flush_lsn
FROM pg_replication_slots
ORDER BY slot_name;
~~~

`age(xmin)` biểu diễn tuổi XID theo phép tính transaction age của PostgreSQL. NULL ở xmin/catalog_xmin có thể là trạng thái hợp lệ.

### 19.1. Các cột tùy version

Những PostgreSQL versions mới hơn có thể bổ sung các cột như `wal_status`, `safe_wal_size`, `inactive_since` và `invalidation_reason`. Chỉ dùng query có những cột này khi server version hỗ trợ.

Có thể xem schema view theo version thực tế bằng psql:

~~~text
\d+ pg_replication_slots
~~~

## 20. Quan sát standby feedback trên primary

~~~sql
SELECT
    pid,
    application_name,
    client_addr,
    state,
    backend_xmin,
    age(backend_xmin) AS backend_xmin_age,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn,
    reply_time
FROM pg_stat_replication
ORDER BY application_name;
~~~

`backend_xmin` có thể cho thấy horizon được standby gửi về primary khi hot standby feedback đang hoạt động.

NULL không nhất thiết là lỗi; nó có thể cho biết standby hiện không báo một snapshot xmin cần giữ.

## 21. Tìm backend đang giữ snapshot lâu

~~~sql
SELECT
    pid,
    usename,
    application_name,
    client_addr,
    state,
    xact_start,
    now() - xact_start AS xact_age,
    backend_xid,
    backend_xmin,
    age(backend_xmin) AS backend_xmin_age,
    wait_event_type,
    wait_event,
    left(query, 200) AS query_sample
FROM pg_stat_activity
WHERE datname = current_database()
ORDER BY xact_start NULLS LAST;
~~~

Các cột cần chú ý:

- `xact_start`: thời điểm transaction bắt đầu.
- `backend_xid`: XID của transaction backend nếu đã được cấp.
- `backend_xmin`: snapshot horizon backend đang giữ nếu có.
- `state`: active, idle, idle in transaction và các trạng thái khác.
- `wait_event`: backend đang chờ gì.

### 21.1. Không chỉ sort theo xact_age

Một query active dài có thể đang đọc dữ liệu nhưng không phải luôn là blocker duy nhất. Một session idle có thể giữ snapshot quan trọng. Hãy kết hợp age, backend_xmin và state.

### 21.2. application_name giúp tìm chủ sở hữu

Đặt application_name rõ cho từng service/worker/connector để DBA biết session nào đang giữ transaction. Không đặt chung một tên cho toàn hệ thống nếu cần phân biệt workload.

## 22. Tìm prepared transactions cũ

~~~sql
SELECT
    transaction,
    gid,
    prepared,
    now() - prepared AS prepared_age,
    owner,
    database
FROM pg_prepared_xacts
ORDER BY prepared;
~~~

Prepared transactions không nên tồn tại vô thời hạn. Kiểm tra coordinator và transaction manager trước khi quyết định COMMIT PREPARED hoặc ROLLBACK PREPARED.

## 23. Quan sát dead tuples và vacuum activity

~~~sql
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
~~~

`n_dead_tup` là **ước lượng thống kê**, không phải số đo chính xác từng tuple có thể thu hồi ngay.

Đối chiếu với:

- VACUUM VERBOSE output.
- Long transactions và snapshots.
- Replication slots.
- Standby feedback.
- Table/TOAST relation size.
- Autovacuum logs.

## 24. Quan sát tiến trình VACUUM

Ở những PostgreSQL versions hỗ trợ `pg_stat_progress_vacuum`:

~~~sql
SELECT
    pid,
    datname,
    relid::regclass AS relation,
    phase,
    heap_blks_total,
    heap_blks_scanned,
    heap_blks_vacuumed,
    index_vacuum_count,
    num_dead_tuples,
    max_dead_tuples
FROM pg_stat_progress_vacuum;
~~~

View cho biết phase và tiến độ của VACUUM đang chạy. Một tiến trình đang hoạt động không đồng nghĩa mọi dead tuples đã được dọn; horizon vẫn giới hạn những gì được phép thu hồi.

## 25. Kiểm tra transaction ID age

Database-level:

~~~sql
SELECT
    datname,
    age(datfrozenxid) AS xid_age
FROM pg_database
ORDER BY xid_age DESC;
~~~

Table-level:

~~~sql
SELECT
    n.nspname AS schema_name,
    c.relname AS table_name,
    c.relfrozenxid,
    age(c.relfrozenxid) AS xid_age
FROM pg_class AS c
JOIN pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE c.relkind IN ('r', 'm')
ORDER BY xid_age DESC
LIMIT 30;
~~~

Tuổi XID lớn có thể báo hiệu cần kiểm tra vacuum/freeze. Không chờ đến sát giới hạn wraparound mới xử lý.

## 26. Cleanup horizon và transaction ID wraparound

PostgreSQL dùng XIDs có không gian hữu hạn. Nếu transaction IDs quay vòng mà các tuples cũ chưa được freeze an toàn, database có nguy cơ diễn giải sai tuổi transaction.

VACUUM có nhiệm vụ **freeze** những tuples đủ cũ và cập nhật frozen-XID metadata để database an toàn qua vòng quay.

Long-running snapshots và replication horizons có thể ngăn VACUUM tiến xa như mong muốn. Đây không chỉ là vấn đề disk bloat mà còn là vấn đề khả năng tiếp tục ghi của database.

### 26.1. Anti-wraparound autovacuum

PostgreSQL có các cơ chế tự động kích hoạt vacuum chống wraparound khi tuổi XID tiến gần ngưỡng cấu hình. Những tiến trình này rất quan trọng và không nên bị chặn/disable tùy tiện.

Nếu cảnh báo wraparound xuất hiện, cần xử lý nguyên nhân giữ horizon, cho vacuum hoàn tất và kiểm tra lại XID ages.

## 27. Freeze horizon khác cleanup dead tuples

VACUUM thực hiện nhiều công việc:

- Thu hồi dead tuples khi an toàn.
- Freeze tuple XIDs đủ cũ.
- Cập nhật visibility map/free space metadata.
- Phân tích statistics khi được yêu cầu qua ANALYZE.

Một cleanup horizon bị ghim có thể cản trở việc thu hồi một số versions. Freeze horizon và chống wraparound là một chiều bảo trì liên quan nhưng không đồng nhất với việc trả dung lượng heap cho hệ điều hành.

Đừng đánh giá sức khỏe vacuum chỉ bằng n_dead_tup hoặc file size.

## 28. Vì sao VACUUM chạy nhưng bloat vẫn tăng?

Các tình huống:

1. VACUUM chỉ có thể thu hồi tuples cũ hơn cleanup horizon.
2. Transaction dài vẫn giữ snapshot cũ.
3. Logical slot giữ xmin/catalog_xmin.
4. Standby feedback gửi backend_xmin cũ.
5. Prepared transaction giữ trạng thái lâu.
6. Long snapshot từ exported snapshot.
7. Autovacuum không theo kịp tốc độ UPDATE/DELETE.
8. Index cleanup và heap cleanup chịu workload/lock.
9. VACUUM tạo space reusable nhưng file không giảm kích thước trên filesystem.

### 28.1. VACUUM không thể vượt qua horizon một cách an toàn

Chạy thêm VACUUM liên tục không giải quyết nguyên nhân nếu transaction/slot vẫn giữ horizon. Hãy tìm blocker trước.

## 29. Lab: chứng minh long snapshot giữ row version

Thực hiện trong database lab.

Tạo bảng:

~~~sql
CREATE SCHEMA vacuum_lab;

CREATE TABLE vacuum_lab.items (
    item_id BIGINT PRIMARY KEY,
    payload TEXT NOT NULL
);

INSERT INTO vacuum_lab.items
VALUES (1, 'original value');
~~~

**Session A — giữ snapshot:**

~~~sql
BEGIN ISOLATION LEVEL REPEATABLE READ;

SELECT payload
FROM vacuum_lab.items
WHERE item_id = 1;
~~~

Kết quả là `original value`. Giữ transaction A mở.

**Session B — cập nhật và vacuum:**

~~~sql
UPDATE vacuum_lab.items
SET payload = 'updated value'
WHERE item_id = 1;

VACUUM (VERBOSE, ANALYZE) vacuum_lab.items;
~~~

VACUUM không được xóa phiên bản cũ nếu snapshot A còn cần nó.

Quay lại session A:

~~~sql
SELECT payload
FROM vacuum_lab.items
WHERE item_id = 1;
~~~

A vẫn thấy `original value` do snapshot REPEATABLE READ.

### 29.1. Kết thúc snapshot và vacuum lại

Session A:

~~~sql
COMMIT;
~~~

Session B:

~~~sql
VACUUM (VERBOSE, ANALYZE) vacuum_lab.items;
~~~

Sau khi snapshot cũ kết thúc, version cũ có thể trở thành removable nếu không còn blocker khác.

Kết quả cụ thể về số tuples phụ thuộc vacuum timing và môi trường; mục tiêu lab là quan sát sự khác biệt giữa snapshot còn mở và đã kết thúc.

## 30. Lab: quan sát backend_xmin

Trong lúc Session A đang giữ transaction, chạy từ session quan sát:

~~~sql
SELECT
    pid,
    state,
    xact_start,
    backend_xid,
    backend_xmin,
    age(backend_xmin) AS xmin_age,
    application_name
FROM pg_stat_activity
WHERE datname = current_database()
ORDER BY xact_start NULLS LAST;
~~~

Tìm PID của session A.

`backend_xmin` có thể cho thấy snapshot horizon mà session đang giữ. Nếu NULL, đừng kết luận session hoàn toàn không có tác động; hãy kiểm tra isolation, transaction ID và locks.

## 31. Lab: quan sát replication slots an toàn

Bắt đầu bằng query read-only:

~~~sql
SELECT
    slot_name,
    slot_type,
    database,
    active,
    active_pid,
    xmin,
    age(xmin) AS xmin_age,
    catalog_xmin,
    age(catalog_xmin) AS catalog_xmin_age,
    restart_lsn,
    confirmed_flush_lsn
FROM pg_replication_slots;
~~~

Xem những slot:

- Inactive lâu.
- Có xmin/catalog_xmin cũ.
- restart_lsn cách xa WAL hiện tại.
- Consumer owner không còn rõ ràng.

**Không drop slot chỉ vì active=false.** Trước hết phải biết consumer có còn cần tiếp tục CDC/replication từ vị trí đó không.

## 32. Tạo logical slot trong lab (tùy chọn)

Chỉ trong database lab cô lập, nếu server đã cấu hình logical decoding:

- `wal_level` cần hỗ trợ logical.
- `max_replication_slots` còn chỗ.
- Plugin output phù hợp đã cài.
- Role có đặc quyền replication phù hợp.

Ví dụ với plugin `test_decoding` nếu được cài:

~~~sql
SELECT *
FROM pg_create_logical_replication_slot(
    'vacuum_lab_slot',
    'test_decoding'
);
~~~

Việc tạo slot có thể bắt đầu giữ WAL và transaction/catalog horizons. **Không chạy tùy tiện trên production**.

Sau khi lab hoàn tất, nếu slot không active và chắc chắn không còn consumer cần nó:

~~~sql
SELECT pg_drop_replication_slot('vacuum_lab_slot');
~~~

Nếu slot đang active, cần dừng/disconnect consumer đúng cách trước. Drop slot có thể khiến downstream không còn khả năng tiếp tục từ checkpoint cũ.

## 33. Đừng bỏ quên logical slot inactive

Một slot inactive có thể:

- Giữ WAL qua restart_lsn.
- Giữ xmin, khiến heap bloat.
- Giữ catalog_xmin, khiến catalog bloat.
- Khiến pg_wal tăng đến mức filesystem thiếu dung lượng.

Kiểm tra slot inventory định kỳ, gắn mỗi slot với một owner/service, theo dõi last activity và alert cho slots không còn consumer.

## 34. max_slot_wal_keep_size và slot invalidation

Khi giới hạn WAL retention cho slot được cấu hình, PostgreSQL có thể đánh dấu slot không còn usable nếu WAL cần thiết đã bị loại bỏ.

Điều này bảo vệ filesystem khỏi việc một slot bỏ quên giữ WAL vô hạn, nhưng có thể yêu cầu consumer **reinitialize/resnapshot**.

Không xem việc slot bị invalidated là “data đã được đồng bộ”. Consumer phải có quy trình khôi phục dữ liệu đầy đủ.

### 34.1. Không tự xóa pg_wal files

Xóa WAL files bằng filesystem commands có thể làm hỏng cluster. Hãy quản lý slot, archiving và cấu hình WAL qua PostgreSQL.

## 35. Hot standby feedback: chẩn đoán trên hai máy

Trên standby:

~~~sql
SHOW hot_standby_feedback;
~~~

Trên primary:

~~~sql
SELECT
    application_name,
    state,
    backend_xmin,
    age(backend_xmin) AS backend_xmin_age,
    replay_lsn,
    reply_time
FROM pg_stat_replication;
~~~

Nếu feedback bật và standby có snapshot cũ, primary có thể phải giữ row versions để tránh recovery conflicts.

### 35.1. Trade-off khi tắt feedback

Tắt feedback có thể giảm bloat trên primary, nhưng các long-running queries trên standby có thể bị cancel khi recovery cần dọn những versions cũ.

Hãy cân nhắc workload read replica, query duration, replication lag và dung lượng trước khi thay đổi.

## 36. Vì sao replication slot và standby feedback có thể cộng dồn?

Một standby có thể vừa dùng physical replication slot vừa bật hot_standby_feedback.

Khi đó:

- Slot giữ WAL theo restart_lsn.
- Feedback có thể giữ cleanup horizon qua xmin.
- Long queries trên standby kéo dài thời gian feedback giữ horizon.

Giám sát từng chiều riêng biệt. Đừng nhìn restart_lsn rồi suy ra heap cleanup đã được giải phóng.

## 37. Remediation: tìm blocker trước khi hành động

Một quy trình điều tra:

~~~text
Bloat / dead tuples tăng
          |
          v
Kiểm tra VACUUM/autovacuum
          |
          v
VACUUM không thể thu hồi tuples?
          |
          v
Tìm backend_xmin lâu nhất
          |
          v
Tìm replication slot xmin/catalog_xmin
          |
          v
Kiểm tra standby backend_xmin/feedback
          |
          v
Kiểm tra prepared transactions/exported snapshots
          |
          v
Xác định owner và mục đích của blocker
          |
          v
Giải phóng đúng nguồn giữ horizon
          |
          v
VACUUM lại và theo dõi
~~~

Không bắt đầu bằng `VACUUM FULL` hoặc xóa slot.

## 38. Kết thúc transaction dài

Nếu ứng dụng vẫn đang dùng transaction, cách đúng thường là để ứng dụng COMMIT hoặc ROLLBACK theo logic nghiệp vụ.

Nếu transaction bị bỏ quên:

- Xác định service/application_name và owner.
- Kiểm tra có đang chờ người dùng hoặc external service không.
- Xem locks và backend query.
- Yêu cầu ứng dụng đóng transaction đúng cách.
- Nếu cần can thiệp DBA, cân nhắc tác động rollback trước khi terminate.

`pg_cancel_backend(pid)` hủy query hiện tại khi có thể; nó **không đảm bảo kết thúc transaction/session**. `pg_terminate_backend(pid)` chấm dứt session và rollback transaction chưa commit, có thể ảnh hưởng nghiệp vụ.

Không terminate chỉ vì age lớn mà chưa xác định hậu quả.

## 39. Xử lý replication slot bỏ quên

Trước khi drop:

1. Xác định slot type, database, plugin và owner.
2. Kiểm tra connector/consumer còn tồn tại không.
3. Xác định checkpoint/LSN cuối cùng đã xử lý.
4. Xác nhận downstream có thể resnapshot nếu cần.
5. Kiểm tra slot có active không.
6. Dừng consumer đúng cách.
7. Chỉ drop khi đã chấp nhận mất khả năng resume từ slot đó.

Lệnh:

~~~sql
SELECT pg_drop_replication_slot('slot_name');
~~~

là thao tác có hậu quả với consumer. Không chạy câu lệnh với placeholder hoặc tên slot production nếu chưa xác minh.

## 40. Advance logical slot có thể bỏ qua changes

PostgreSQL cung cấp function quản trị slot như `pg_replication_slot_advance` ở các phiên bản hỗ trợ.

Advance slot di chuyển vị trí slot tiến lên; các changes trước vị trí mới có thể không còn được consumer đọc từ slot đó.

Đây **không phải nút vacuum**. Chỉ advance khi downstream đã đồng bộ bằng một phương pháp khác hoặc chủ sở hữu chấp nhận bỏ qua đoạn WAL tương ứng.

Sau thao tác, xác minh trạng thái slot và consumer checkpoint. Không dùng advance để che một lỗi CDC chưa được hiểu.

## 41. Autovacuum không thể sửa một horizon bị ghim mãi

Autovacuum có thể chạy thường xuyên, nhưng nếu horizon không tiến:

- Tuples vẫn chưa removable.
- VACUUM có thể quét nhưng không thu hồi được phần bị giữ.
- Table bloat tiếp tục tăng.
- Autovacuum chạy nhiều hơn, tạo thêm I/O/CPU.
- XID freeze progress có thể chịu áp lực.

Tăng autovacuum workers hoặc giảm scale factor không giải quyết gốc nếu blocker vẫn tồn tại.

## 42. Manual VACUUM sau khi horizon được giải phóng

Sau khi transaction/slot/feedback blocker kết thúc, có thể để autovacuum xử lý hoặc chạy:

~~~sql
VACUUM (VERBOSE, ANALYZE) schema_name.table_name;
~~~

VACUUM:

- Thu hồi versions đủ cũ.
- Cập nhật free space/visibility information.
- ANALYZE cập nhật planner statistics nếu được yêu cầu.

Không chạy trong explicit transaction block.

### 42.1. VACUUM thường không trả dung lượng file ngay

Không gian được thu hồi thường trở thành free space có thể tái sử dụng cho những rows mới trong relation. File trên filesystem có thể không nhỏ lại.

Nếu cần thu nhỏ vật lý, phải đánh giá rewrite/pg_repack hoặc VACUUM FULL với lock, downtime và dung lượng tạm phù hợp.

## 43. VACUUM FULL không phải cách sửa horizon

`VACUUM FULL` viết lại relation và cần lock mạnh. Nó không phải cách an toàn để vượt qua một snapshot hoặc replication slot vẫn cần dữ liệu cũ.

Nếu cleanup horizon chưa tiến, rewrite có thể bị chặn/không giải quyết nguyên nhân hoặc gây thêm chi phí vận hành. Hãy giải phóng blocker trước, sau đó đánh giá có thật sự cần thu nhỏ file không.

## 44. Chống wraparound và failsafe

Theo dõi:

~~~sql
SELECT
    datname,
    age(datfrozenxid) AS xid_age
FROM pg_database
ORDER BY xid_age DESC;
~~~

PostgreSQL có ngưỡng freeze/anti-wraparound autovacuum và các cơ chế failsafe theo version. Khi cảnh báo XID age tăng:

- Tìm long transactions và slots.
- Đảm bảo autovacuum có thể chạy.
- Kiểm tra disk space/WAL.
- Không tắt anti-wraparound vacuum.
- Lên kế hoạch cho maintenance cần thiết.
- Theo dõi age sau khi blocker được giải phóng.

Nếu transaction age tiến quá gần giới hạn an toàn, PostgreSQL có thể hạn chế ghi để tránh database corruption do wraparound. Đây là tình huống khẩn cấp.

## 45. Các tham số cần biết

| Setting | Ý nghĩa |
|---|---|
| `autovacuum` | Bật/tắt autovacuum theo phạm vi cấu hình |
| `autovacuum_freeze_max_age` | Tuổi XID kích hoạt vacuum freeze chống wraparound |
| `vacuum_freeze_table_age` | Tuổi liên quan quyết định aggressive vacuum/freeze |
| `vacuum_freeze_min_age` | Tuổi tối thiểu để freeze tuples theo chính sách |
| `max_replication_slots` | Số replication slots tối đa |
| `max_slot_wal_keep_size` | Giới hạn WAL được giữ bởi replication slots |
| `wal_keep_size` | Lượng WAL tối thiểu giữ lại theo cấu hình |
| `hot_standby_feedback` | Standby gửi xmin feedback về primary |
| `idle_in_transaction_session_timeout` | Timeout session idle trong transaction |
| `statement_timeout` | Giới hạn thời gian statement |
| `lock_timeout` | Giới hạn thời gian chờ lock |

Thay đổi setting cần căn cứ PostgreSQL version, workload, topology và SLA. Không áp một giá trị chung cho mọi database.

## 46. idle_in_transaction_session_timeout

Có thể cấu hình để chấm dứt những sessions idle in transaction quá lâu:

~~~sql
SHOW idle_in_transaction_session_timeout;
~~~

Ví dụ cấu hình theo database/role/session cần được review:

~~~sql
ALTER ROLE app_runtime
SET idle_in_transaction_session_timeout = '5min';
~~~

Đây chỉ là giá trị minh họa. Timeout có thể làm session bị terminate, transaction rollback và request ứng dụng thất bại. Phải sửa code transaction scope trước khi dựa vào timeout như hàng rào cuối.

### 46.1. Không thay thế monitoring

Timeout không phát hiện mọi long-running active query hoặc replication slot. Vẫn cần theo dõi backend_xmin, xact age và slot horizons.

## 47. Bảng giám sát tổng hợp

Một số truy vấn read-only:

**Backend snapshots:**

~~~sql
SELECT
    pid,
    application_name,
    state,
    xact_start,
    age(backend_xmin) AS xmin_age,
    backend_xid,
    backend_xmin
FROM pg_stat_activity
WHERE datname = current_database()
ORDER BY age(backend_xmin) DESC NULLS LAST;
~~~

**Replication slots:**

~~~sql
SELECT
    slot_name,
    slot_type,
    active,
    age(xmin) AS xmin_age,
    age(catalog_xmin) AS catalog_xmin_age,
    restart_lsn
FROM pg_replication_slots
ORDER BY age(xmin) DESC NULLS LAST;
~~~

**Dead tuple estimates:**

~~~sql
SELECT
    schemaname,
    relname,
    n_dead_tup,
    last_autovacuum,
    autovacuum_count
FROM pg_stat_user_tables
ORDER BY n_dead_tup DESC;
~~~

**Database XID age:**

~~~sql
SELECT
    datname,
    age(datfrozenxid) AS xid_age
FROM pg_database
ORDER BY xid_age DESC;
~~~

Các truy vấn phải được diễn giải kết hợp. Một backend xmin cũ, một slot xmin cũ hoặc dead tuple estimate riêng lẻ chưa đủ chứng minh toàn bộ nguyên nhân bloat.

## 48. Kịch bản thực tế: CDC consumer bị dừng

Triệu chứng:

- CDC connector đã bị xóa khỏi deployment.
- Replication slot vẫn tồn tại.
- `active=false`.
- `restart_lsn` không tiến.
- `xmin`/`catalog_xmin` giữ ở tuổi cũ.
- WAL directory và/hoặc bảng tăng dung lượng.

Cách xử lý:

1. Tìm owner của slot.
2. Xác nhận connector đã được decommission.
3. Xác định downstream có cần resnapshot.
4. Đánh giá WAL/disk pressure.
5. Dừng consumer nếu còn kết nối.
6. Drop slot sau khi được chấp thuận.
7. Quan sát horizon và chạy vacuum khi phù hợp.
8. Đưa alert cho inactive slot vào monitoring.

Không xóa slot chỉ để metric đẹp nếu pipeline còn cần resume.

## 49. Kịch bản: standby query gây bloat primary

Triệu chứng:

- Primary có dead tuples tăng.
- Autovacuum chạy nhưng không dọn được một số versions.
- Standby có query REPEATABLE READ chạy lâu.
- `hot_standby_feedback` đang bật.
- `pg_stat_replication.backend_xmin` cũ.

Cân nhắc:

- Rút ngắn query/snapshot trên standby.
- Chuyển báo cáo dài sang snapshot/replica phù hợp.
- Điều chỉnh feedback sau khi cân nhắc recovery conflicts.
- Theo dõi primary bloat và standby query cancellations.

Không tắt feedback mà không hiểu tác động đến queries trên standby.

## 50. Kịch bản: idle in transaction từ application pool

Triệu chứng:

- `pg_stat_activity.state = 'idle in transaction'`.
- `xact_start` rất cũ.
- `backend_xmin` có giá trị cũ.
- App request đã hoàn tất nhưng connection chưa commit/rollback.

Cách sửa gốc:

- Thu hẹp transaction scope.
- Không chờ HTTP/network/user input trong transaction.
- Đảm bảo exception path rollback.
- Dùng transaction manager đúng lifecycle.
- Cấu hình idle-in-transaction timeout phù hợp.
- Đặt application_name để truy ngược service.

Nếu phải terminate session, xác định rollback side effects trước.

## 51. Monitoring và alerting

Những metrics hữu ích:

- Tuổi lớn nhất của `backend_xmin`.
- Tuổi lớn nhất của slot `xmin` và `catalog_xmin`.
- Slot inactive duration.
- Khoảng cách WAL giữa restart_lsn và current WAL position.
- WAL directory size và disk free space.
- `age(datfrozenxid)`.
- `n_dead_tup` và relation growth.
- Autovacuum duration/count.
- Số transactions idle in transaction.
- Prepared transaction age.
- Standby backend_xmin và replication lag.

### 51.1. Đặt alert theo xu hướng

Một giá trị lớn trong vài giây có thể bình thường với workload. Một horizon không tiến trong nhiều giờ/ngày kèm WAL/bloat tăng mới là tín hiệu cần ưu tiên. Alert cần threshold theo SLA và dung lượng cụm.

## 52. Remediation không phá dữ liệu

Trình tự an toàn thường là:

1. **Quan sát:** thu thập backend, slot, standby và vacuum metrics.
2. **Quy trách nhiệm:** map PID/slot sang application hoặc consumer owner.
3. **Xác minh nhu cầu:** transaction/slot có còn cần không?
4. **Phối hợp:** để app commit/rollback hoặc consumer resume.
5. **Can thiệp có kiểm soát:** terminate/drop/advance chỉ sau khi đánh giá.
6. **Vacuum:** cho autovacuum hoặc chạy VACUUM sau khi horizon tiến.
7. **Đo lại:** dead tuples, relation size, WAL và XID age.
8. **Ngăn tái diễn:** transaction timeout, slot inventory, alerting và ownership.

Không xóa thủ công heap/TOAST/WAL files.

## 53. Các lỗi hay gặp

### 53.1. Chỉ nhìn n_dead_tup

Đây là estimate, không nói tuple nào removable.

### 53.2. Nghĩ VACUUM sẽ xóa mọi dead tuples

VACUUM phải tôn trọng cleanup horizon.

### 53.3. Cho rằng idle in transaction luôn giữ cùng snapshot

Tác động phụ thuộc isolation và snapshot thực tế; kiểm tra backend_xmin.

### 53.4. Bỏ quên logical slots inactive

Slot inactive vẫn có thể giữ WAL/xmin/catalog_xmin.

### 53.5. Chỉ kiểm tra restart_lsn

WAL retention khác heap/catalog cleanup horizons.

### 53.6. Nghĩ max_slot_wal_keep_size giải quyết xmin

Nó giới hạn WAL retention; không thay thế kiểm tra tuple/catalog horizons.

### 53.7. Bật hot_standby_feedback mà không theo dõi bloat

Standby queries ít bị cancel hơn nhưng primary có thể giữ versions lâu.

### 53.8. Drop slot chỉ vì active=false

Consumer có thể cần slot để tiếp tục CDC.

### 53.9. Advance slot để “giải phóng vacuum”

Advance có thể làm downstream bỏ lỡ changes; nó không phải lệnh vacuum.

### 53.10. Dùng VACUUM FULL đầu tiên

Nó không xử lý gốc long snapshot/slot horizon và có lock/dung lượng cost cao.

### 53.11. Kill backend mà không biết owner

Có thể rollback giao dịch nghiệp vụ quan trọng.

### 53.12. Tắt anti-wraparound autovacuum

Tạo rủi ro database không thể tiếp tục ghi an toàn.

### 53.13. Xóa WAL files thủ công

Có thể làm hỏng khả năng recovery/replication.

### 53.14. Dùng sequence ID làm cleanup checkpoint

Sequence allocation order không đồng nghĩa commit order.

## 54. Checklist cho DBA

- Có transaction nào giữ backend_xmin cũ?
- Có REPEATABLE READ/SERIALIZABLE transaction kéo dài?
- Có exported snapshots còn mở?
- Có prepared transactions cũ?
- Có replication slots inactive?
- Slot xmin/catalog_xmin có tuổi cao?
- restart_lsn có giữ WAL quá xa?
- Standby feedback có báo backend_xmin cũ?
- Autovacuum có chạy và tiến triển?
- XID age của database/table có an toàn?
- Disk/WAL/archive có đủ chỗ?
- Có biết owner của từng slot và application session?
- Có kế hoạch phục hồi consumer trước khi drop/advance slot?
- Có theo dõi sau khi horizon được giải phóng?

## 55. Bài tập thực hành

### Bài 1 — MVCC

Vì sao PostgreSQL giữ row version cũ sau UPDATE?

**Gợi ý:** snapshot cũ có thể cần đọc version đó.

### Bài 2 — xmin tuple

`xmin` trong tuple header biểu thị gì?

**Gợi ý:** XID tạo tuple version.

### Bài 3 — backend_xmin

`pg_stat_activity.backend_xmin` biểu thị gì?

**Gợi ý:** snapshot horizon backend đang giữ.

### Bài 4 — Cleanup horizon

Vì sao dead tuple có thể chưa removable?

**Gợi ý:** chưa cũ hơn horizon mà snapshot/consumer yêu cầu.

### Bài 5 — READ COMMITTED

Snapshot của READ COMMITTED thường được lấy ở phạm vi nào?

**Gợi ý:** từng statement.

### Bài 6 — REPEATABLE READ

Vì sao transaction REPEATABLE READ dài có thể giữ cleanup horizon?

**Gợi ý:** snapshot nhất quán xuyên transaction.

### Bài 7 — Idle transaction

`idle in transaction` có luôn đồng nghĩa backend_xmin cũ không?

**Gợi ý:** không, kiểm tra isolation và backend_xmin.

### Bài 8 — Exported snapshot

Snapshot export tồn tại đến khi nào?

**Gợi ý:** transaction exporter kết thúc.

### Bài 9 — Prepared xact

View nào liệt kê prepared transactions?

**Gợi ý:** pg_prepared_xacts.

### Bài 10 — VACUUM

Vì sao chạy VACUUM nhiều lần không giải quyết horizon bị ghim?

**Gợi ý:** không thể xóa version còn cần.

### Bài 11 — Logical slot

Logical slot có thể giữ những horizon nào?

**Gợi ý:** xmin và catalog_xmin.

### Bài 12 — restart_lsn

restart_lsn liên quan đến tài nguyên gì?

**Gợi ý:** WAL retention.

### Bài 13 — confirmed_flush_lsn

Trường này biểu thị điều gì trong logical slot?

**Gợi ý:** tiến độ flush đã xác nhận.

### Bài 14 — Slot inactive

Slot inactive có thể giữ tài nguyên không?

**Gợi ý:** có.

### Bài 15 — catalog_xmin

Vì sao catalog_xmin quan trọng?

**Gợi ý:** giữ catalog versions cần cho logical decoding.

### Bài 16 — Physical slot

Physical slot có mục tiêu chính gì?

**Gợi ý:** giữ WAL cho physical standby.

### Bài 17 — Hot standby feedback

Feedback truyền thông tin gì về primary?

**Gợi ý:** xmin snapshot horizon.

### Bài 18 — Trade-off

Bật hot_standby_feedback giảm rủi ro nào và tăng rủi ro nào?

**Gợi ý:** giảm standby query cancellations, tăng primary bloat.

### Bài 19 — pg_replication_slots

Viết query xem slot_name, active, xmin và restart_lsn.

**Gợi ý:** pg_replication_slots.

### Bài 20 — pg_stat_replication

Trường nào có thể quan sát standby feedback xmin?

**Gợi ý:** backend_xmin.

### Bài 21 — Backend diagnostics

Nêu ba trường quan trọng của pg_stat_activity.

**Gợi ý:** xact_start, backend_xid, backend_xmin.

### Bài 22 — Dead tuples

n_dead_tup có phải số tuples chắc chắn removable?

**Gợi ý:** không, là estimate.

### Bài 23 — Progress vacuum

View nào quan sát phase/blocks của VACUUM?

**Gợi ý:** pg_stat_progress_vacuum.

### Bài 24 — XID age

Viết query xem database age(datfrozenxid).

**Gợi ý:** pg_database.

### Bài 25 — Wraparound

Vì sao vacuum freeze quan trọng?

**Gợi ý:** tránh transaction ID wraparound.

### Bài 26 — max_slot_wal_keep_size

Tham số này giới hạn WAL retention hay cleanup xmin?

**Gợi ý:** WAL retention.

### Bài 27 — wal_keep_size

Phân biệt wal_keep_size và replication slot restart_lsn.

**Gợi ý:** WAL minimum retention setting vs per-slot required position.

### Bài 28 — Drop slot

Tại sao không drop slot chỉ vì active=false?

**Gợi ý:** consumer có thể cần resume từ slot.

### Bài 29 — Advance slot

Advance logical slot có thể gây hậu quả gì?

**Gợi ý:** downstream bỏ qua changes trước vị trí mới.

### Bài 30 — Long transaction remediation

Nên yêu cầu app commit/rollback hay terminate ngay?

**Gợi ý:** xác định owner/tác động, ưu tiên lifecycle đúng.

### Bài 31 — Cancel vs terminate

Phân biệt pg_cancel_backend và pg_terminate_backend.

**Gợi ý:** hủy query hiện tại vs chấm dứt session/rollback.

### Bài 32 — VACUUM FULL

Tại sao không phải remedy đầu tiên cho horizon blocker?

**Gợi ý:** không giải quyết gốc và cần lock/rewrite.

### Bài 33 — WAL disk growth

Một slot inactive có restart_lsn cũ có thể gây vấn đề gì?

**Gợi ý:** giữ WAL và làm pg_wal tăng.

### Bài 34 — Catalog bloat

Slot có catalog_xmin cũ có thể giữ những gì?

**Gợi ý:** catalog tuple versions.

### Bài 35 — Replica conflict

Tắt hot_standby_feedback có thể ảnh hưởng query standby thế nào?

**Gợi ý:** recovery conflict có thể cancel query.

### Bài 36 — Monitoring

Nêu năm metrics để theo dõi vacuum horizon.

**Gợi ý:** backend xmin age, slot xmin, catalog_xmin, restart_lsn, xid age, dead tuples.

### Bài 37 — Transaction snapshot lab

Viết hai-session experiment chứng minh REPEATABLE READ thấy old row version.

**Gợi ý:** A BEGIN REPEATABLE READ, B UPDATE, A SELECT lại.

### Bài 38 — Consumer outage

Nêu các bước trước khi drop slot của CDC connector đã dừng.

**Gợi ý:** xác định owner/checkpoint/resnapshot/stop consumer.

### Bài 39 — Anti-wraparound

Có nên disable autovacuum khi XID age tăng cao?

**Gợi ý:** không.

### Bài 40 — Root cause

Bloat tăng dù VACUUM chạy đều. Liệt kê ít nhất bốn nguồn giữ horizon.

**Gợi ý:** long snapshot, logical slot, standby feedback, prepared xact, exported snapshot.

## 56. Câu hỏi thường gặp

### Cleanup horizon có phải một timestamp không?

Không. Nó là ranh giới transaction visibility/XID, không phải tuổi dữ liệu theo ngày.

### Dead tuple có phải luôn được VACUUM xóa?

Không. Tuple chỉ removable khi không còn snapshot hoặc consumer cần nó và đã an toàn theo cleanup horizon.

### Vì sao một transaction không chạy query vẫn có thể gây bloat?

Nếu nó giữ snapshot cũ (ví dụ REPEATABLE READ) hoặc trạng thái transaction có liên quan, VACUUM phải giữ những versions cần thiết. Kiểm tra backend_xmin thay vì chỉ nhìn state.

### READ COMMITTED có giữ snapshot đến cuối transaction không?

Thông thường snapshot được lấy theo từng statement. Hành vi cụ thể còn phụ thuộc cursor/statement/session context; không suy chỉ từ transaction age.

### Replication slot inactive có nguy hiểm không?

Có thể. Slot vẫn có thể giữ WAL và các xmin/catalog_xmin horizons.

### restart_lsn có phải xmin không?

Không. restart_lsn là WAL position; xmin là transaction horizon cho tuple retention.

### catalog_xmin dùng để làm gì?

Giữ catalog tuple versions cần thiết cho logical decoding.

### max_slot_wal_keep_size có ngăn heap bloat không?

Không trực tiếp. Nó giới hạn WAL retention; cần giám sát xmin/catalog_xmin riêng.

### hot_standby_feedback có tốt hay xấu?

Có trade-off. Nó giảm recovery conflicts/cancelled standby queries nhưng có thể giữ dead tuples lâu trên primary.

### Có thể drop mọi slot inactive không?

Không. Xác định consumer/checkpoint và khả năng resnapshot trước.

### pg_cancel_backend có giải phóng transaction không?

Nó hủy query đang chạy nếu có thể; transaction có thể vẫn mở. Terminate session mới chấm dứt session và rollback transaction.

### VACUUM FULL có giải phóng horizon không?

Không phải giải pháp cho một transaction/slot vẫn giữ snapshot cũ. Phải giải phóng blocker trước.

### Vì sao disk file không giảm sau VACUUM?

VACUUM thường làm không gian reusable bên trong relation. Muốn shrink filesystem file cần rewrite, ví dụ VACUUM FULL, với chi phí/lock riêng.

### Tại sao phải theo dõi XID age?

Để phát hiện nguy cơ wraparound trước khi PostgreSQL phải hạn chế ghi hoặc buộc xử lý khẩn cấp.

## 57. Tổng kết

Những view và trường nên nhớ:

~~~sql
-- Backend transactions và snapshots.
SELECT
    pid,
    state,
    xact_start,
    backend_xid,
    backend_xmin,
    age(backend_xmin)
FROM pg_stat_activity
WHERE datname = current_database();

-- Replication slots và retention horizons.
SELECT
    slot_name,
    slot_type,
    active,
    xmin,
    age(xmin),
    catalog_xmin,
    age(catalog_xmin),
    restart_lsn,
    confirmed_flush_lsn
FROM pg_replication_slots;

-- Standby feedback trên primary.
SELECT
    application_name,
    backend_xmin,
    age(backend_xmin),
    replay_lsn
FROM pg_stat_replication;

-- Prepared transactions.
SELECT *
FROM pg_prepared_xacts;

-- Dead tuple estimates.
SELECT
    schemaname,
    relname,
    n_dead_tup,
    last_autovacuum
FROM pg_stat_user_tables
ORDER BY n_dead_tup DESC;

-- XID age theo database.
SELECT datname, age(datfrozenxid)
FROM pg_database
ORDER BY age(datfrozenxid) DESC;

-- Notification/replication không liên quan trực tiếp ở đây;
-- dùng pg_stat_progress_vacuum để xem VACUUM đang chạy.
SELECT * FROM pg_stat_progress_vacuum;
~~~

Các nguyên tắc quan trọng:

1. **VACUUM tôn trọng cleanup horizon**; dead không đồng nghĩa removable.
2. **Long-running snapshots** có thể giữ old row versions.
3. `backend_xmin` giúp nhận diện snapshot horizon; `backend_xid` là XID của transaction backend.
4. REPEATABLE READ/SERIALIZABLE và exported snapshots có thể giữ snapshot lâu.
5. Idle in transaction cần được điều tra theo isolation và snapshot thực tế, không chỉ state.
6. Prepared transactions bỏ quên có thể giữ locks/XID và cản maintenance.
7. Logical replication slot có thể giữ `xmin` và `catalog_xmin`.
8. `restart_lsn` giữ WAL, khác với heap cleanup horizon.
9. Slot inactive vẫn có thể giữ tài nguyên.
10. `hot_standby_feedback` giảm standby recovery conflicts nhưng có thể gây bloat trên primary.
11. `max_slot_wal_keep_size` giới hạn WAL retention, không thay thế theo dõi xmin/catalog_xmin.
12. VACUUM có thể chạy mà không dọn được những tuples còn cần.
13. VACUUM thường không thu nhỏ file; VACUUM FULL là rewrite/lock operation riêng.
14. XID age và freeze progress phải được theo dõi để tránh wraparound.
15. Không drop/advance slot hoặc terminate backend khi chưa xác định owner và hậu quả.
16. Sau khi giải phóng horizon, chạy/để VACUUM hoàn tất và đo lại.
17. Dùng transaction timeouts, application_name, slot inventory và alerts để ngăn tái diễn.

Sơ đồ điều tra:

~~~text
Dead tuples / storage / WAL tăng
              |
              v
     Quan sát VACUUM progress
              |
              v
   Backend snapshot xmin cũ?
        /           \
      Có             Không
      |                |
Tìm transaction     Kiểm tra slots
long/exported       xmin/catalog_xmin
snapshot/prepared       |
      |                 v
      |           Standby feedback?
      |                 |
      +--------+--------+
               |
               v
       Xác định blocker owner
               |
               v
       Giải phóng có kiểm soát
               |
               v
        VACUUM và theo dõi lại
               |
               v
      Kiểm tra bloat và XID age
~~~

**Kết luận:** Giao dịch dài, replication slots và standby feedback đều có thể giữ PostgreSQL ở một cleanup horizon cũ, khiến VACUUM không thể thu hồi những tuple versions mà hệ thống vẫn phải bảo vệ. Chẩn đoán đúng cần xem đồng thời **backend_xmin, slot xmin/catalog_xmin, restart_lsn, standby feedback, prepared transactions và XID age**. Khi đã xác định nguồn giữ horizon, giải phóng nó theo lifecycle ứng dụng/replication rồi mới để VACUUM dọn dữ liệu an toàn.
