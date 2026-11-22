# Nhất quán snapshot và tác động của dump đang chạy trong PostgreSQL

Một bản dump chỉ hữu ích khi dữ liệu bên trong phản ánh một trạng thái database có thể giải thích được. Trong lúc `pg_dump` chạy, ứng dụng vẫn có thể INSERT, UPDATE và DELETE. Nếu công cụ đọc từng bảng vào những thời điểm khác nhau mà không chia sẻ cùng một snapshot, các bảng trong bản dump có thể không khớp nhau: đơn hàng đã được xuất nhưng bản ghi thanh toán tương ứng chưa xuất, hoặc một hàng cha và hàng con phản ánh hai thời điểm khác nhau.

PostgreSQL giải quyết vấn đề này bằng **MVCC snapshots** và transaction isolation. `pg_dump` giữ một snapshot nhất quán trong quá trình đọc database; khi dump song song, các worker dùng synchronized snapshot để cùng nhìn một trạng thái logic. Vì vậy một dump dài vẫn có thể phản ánh dữ liệu tại một thời điểm, trong khi workload khác tiếp tục chạy.

Tuy nhiên, dump đang chạy có chi phí và tương tác vận hành:

- Đọc nhiều dữ liệu, tiêu thụ I/O, CPU, network và cache.
- Giữ snapshot lâu, có thể làm vacuum chưa dọn được các row versions cũ và khiến table/index bloat tăng.
- Lấy `ACCESS SHARE` locks trên các bảng được dump; DML thường vẫn chạy, nhưng DDL cần `ACCESS EXCLUSIVE` có thể phải chờ.
- Dump song song tạo thêm connections và tải đọc đồng thời.
- Sequence là trường hợp đặc biệt vì giá trị sequence không tuân theo MVCC transaction snapshot như row thông thường.

```text
                    pg_dump bắt đầu
                          |
                          v
                 Tạo transaction snapshot
                          |
             +------------+------------+
             |                         |
       Đọc bảng A                 Đọc bảng B
       tại snapshot S             tại snapshot S
             |                         |
             +------------+------------+
                          |
                 Ghi archive / SQL
                          |
                          v
                   Dump hoàn tất

       Trong thời gian đó:
       - INSERT/UPDATE/DELETE vẫn có thể chạy
       - DDL xung đột ACCESS EXCLUSIVE có thể chờ
       - Snapshot lâu có thể giữ dead tuples
```

Bài thuộc chương **Sao lưu** của module *Database Engine Relational PostgreSQL*. Nội dung tập trung vào cách snapshot bảo đảm tính nhất quán của dump và những tác động của một tiến trình dump kéo dài lên workload, vacuum, locks, replication và quy trình vận hành.

Sau bài học, bạn có thể:

1. Giải thích MVCC snapshot và visibility của transaction.
2. Phân biệt snapshot nhất quán với việc khóa toàn bộ database.
3. Giải thích vì sao pg_dump có thể chạy trong khi ứng dụng vẫn đọc/ghi.
4. Phân biệt `READ COMMITTED`, `REPEATABLE READ` và `SERIALIZABLE` trong các quy trình export nhiều câu query.
5. Hiểu cách pg_dump đồng bộ snapshot khi dùng parallel jobs.
6. Dùng exported snapshot để phối hợp nhiều dump/query sessions.
7. Nhận diện tác động của snapshot lâu lên vacuum, dead tuples và bloat.
8. Hiểu `ACCESS SHARE` locks và tương tác với DDL.
9. Đánh giá tải I/O, CPU, network và cache của dump đang chạy.
10. Nhận biết sequence và dữ liệu ngoài database không được bao phủ giống row MVCC.
11. Lập lịch, giới hạn concurrency, giám sát và kiểm thử restore cho backup workflow.

> **Môi trường thực hành:** Ví dụ dùng database lab và lệnh pg_dump/psql. Thay connection string, tên database, thư mục output và số jobs theo môi trường. Không chạy thử DDL gây chặn, benchmark đọc toàn bảng hoặc giữ snapshot lâu trên production khi chưa đánh giá tải và thời gian bảo trì.

---

## 1. Vì sao dump cần một snapshot nhất quán?

### 1.1. Dump nhiều bảng trong lúc hệ thống đang ghi

Giả sử ứng dụng quản lý đơn hàng và thanh toán. Một transaction nghiệp vụ tạo order và payment cùng lúc:

```sql
BEGIN;

INSERT INTO sales.orders(order_id, customer_id, total)
VALUES (501, 12, 900000);

INSERT INTO sales.payments(payment_id, order_id, amount)
VALUES (8801, 501, 900000);

COMMIT;
```

Hai thay đổi thuộc cùng một transaction. Database đảm bảo chúng cùng commit hoặc cùng rollback.

Nếu một quy trình backup tự viết đọc bảng orders trước, sau đó đọc payments ở một thời điểm khác, nó có thể nhìn thấy hai trạng thái không cùng thời điểm:

1. Đọc orders trước khi transaction commit: không thấy order 501.
2. Transaction commit.
3. Đọc payments sau commit: thấy payment 8801.

Dump tự viết sẽ chứa payment tham chiếu tới order không có trong phần dump. Ngược lại, nếu đọc orders sau commit rồi đọc payments trước một transaction khác hoặc với logic lọc khác, các bảng cũng có thể lệch nhau.

### 1.2. Snapshot xác định transaction nào được nhìn thấy

MVCC (Multi-Version Concurrency Control) cho phép PostgreSQL duy trì nhiều phiên bản của một row. Một query đọc dữ liệu theo snapshot và visibility rules, thay vì buộc mọi writer dừng lại.

Snapshot xác định:

- Những transaction nào đã commit và có thể nhìn thấy.
- Những transaction nào còn đang chạy và chưa được nhìn thấy.
- Những transaction nào bắt đầu sau snapshot và không thuộc trạng thái nhìn thấy đó.

Do đó, hai SELECT sử dụng cùng snapshot sẽ nhìn thấy cùng một trạng thái logic của dữ liệu transactional, dù transaction khác tiếp tục thay đổi database.

### 1.3. Ví dụ timeline

Giả sử snapshot S được tạo tại thời điểm T1:

```text
T0       Transaction A commit order 100
T1       pg_dump tạo snapshot S
T2       Transaction B insert order 101, chưa commit
T3       Transaction C update order 100, commit
T4       pg_dump đọc bảng orders
T5       Transaction B commit
T6       pg_dump đọc bảng payments
T7       pg_dump hoàn tất
```

Các query của dump dùng snapshot S:

- Order 100 được nhìn thấy theo phiên bản đã commit tại T1.
- Update của C commit sau T1 nên dump vẫn nhìn phiên bản cũ của order 100.
- Order 101 của B chưa commit tại T1 nên không xuất hiện, dù B commit trước khi dump kết thúc.
- Bảng payments cũng được đọc theo snapshot S, nên các row transactional sau T1 không xuất hiện.

Kết quả là dump thể hiện database theo một thời điểm logic T1, không phải trạng thái mới nhất tại T7.

### 1.4. Vì sao không khóa database để dump?

Khóa toàn database để mọi ghi dừng lại có thể làm backup dễ hình dung nhưng gây gián đoạn ứng dụng. PostgreSQL dùng MVCC để cho phép dump đọc snapshot trong khi DML tiếp tục.

Điều đó không có nghĩa dump hoàn toàn không dùng lock. `pg_dump` lấy các table locks cần thiết để bảo vệ cấu trúc đối tượng trong thời gian đọc. Các lock này tương thích với nhiều hoạt động đọc/ghi thông thường, nhưng xung đột với một số DDL.

---

## 2. MVCC snapshot và visibility

### 2.1. Mỗi row có phiên bản

PostgreSQL lưu thông tin transaction trên tuple để xác định phiên bản row nào có thể nhìn thấy. Khi UPDATE, PostgreSQL thường tạo một row version mới và đánh dấu version cũ không còn là phiên bản hiện hành cho các snapshot mới.

Một snapshot cũ vẫn có thể cần phiên bản cũ để query/dump trả về đúng trạng thái đã nhìn thấy tại thời điểm snapshot được tạo.

### 2.2. Snapshot không phải bản sao vật lý của database

Snapshot không copy toàn bộ bảng vào memory. Nó là một tập thông tin visibility và transaction state mà PostgreSQL dùng khi đọc các row versions.

Vì thế:

- Dump có thể quét hàng tỷ rows mà không cần giữ toàn bộ database snapshot trong RAM.
- Các row versions cũ cần thiết vẫn phải tồn tại cho đến khi không còn snapshot nào cần chúng.
- Snapshot càng lâu, khả năng vacuum phải giữ lại nhiều dead tuples càng tăng.

### 2.3. Transaction đang chạy khi snapshot bắt đầu

Transaction đã bắt đầu nhưng chưa commit tại thời điểm snapshot thường không được nhìn thấy như một transaction đã hoàn tất. Kể cả khi nó commit sau đó, snapshot cũ không tự thay đổi để nhìn thấy commit mới.

### 2.4. Transaction commit sau snapshot

Một transaction commit sau khi snapshot được tạo không xuất hiện trong snapshot đó. Đây là đặc điểm quan trọng để dump có tính nhất quán: dump không “trộn” các commit mới vào một số bảng đã đọc trước đó.

### 2.5. Snapshot và dữ liệu ngoài MVCC

Không phải mọi state trong PostgreSQL đều tuân theo MVCC như ordinary table rows. Ví dụ:

- Sequence operations như `nextval()` không rollback theo transaction.
- Dữ liệu ở hệ thống ngoài database không nằm trong snapshot PostgreSQL.
- File trên filesystem, object storage hoặc message broker không tự đồng bộ với snapshot.
- Một số trạng thái cấu hình/cluster-level không thuộc phạm vi dump một database.

Khi thiết kế backup nghiệp vụ, hãy xác định rõ những state nào nằm ngoài snapshot.

---

## 3. Isolation level và dump thủ công

### 3.1. READ COMMITTED

`READ COMMITTED` là isolation level mặc định trong PostgreSQL. Mỗi statement bắt đầu với snapshot mới. Trong cùng một transaction, hai SELECT có thể nhìn thấy hai trạng thái khác nhau nếu transaction khác commit ở giữa.

Ví dụ:

```sql
BEGIN ISOLATION LEVEL READ COMMITTED;

SELECT COUNT(*) FROM sales.orders;

-- Transaction khác có thể commit INSERT ở đây.

SELECT COUNT(*) FROM sales.payments;

COMMIT;
```

Hai SELECT có thể dùng hai snapshots khác nhau. Vì vậy, nếu tự export nhiều bảng bằng nhiều SELECT trong một transaction READ COMMITTED, kết quả không nhất thiết là một database-wide snapshot duy nhất.

### 3.2. REPEATABLE READ

`REPEATABLE READ` dùng một snapshot ổn định cho các query trong transaction sau khi snapshot được thiết lập. Những transaction commit sau snapshot không xuất hiện trong các query tiếp theo của transaction đó.

Ví dụ:

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;

SELECT COUNT(*) FROM sales.orders;

-- Transaction khác có thể commit INSERT/UPDATE ở đây.

SELECT COUNT(*) FROM sales.payments;

COMMIT;
```

Hai SELECT dùng cùng một snapshot. Đây là isolation level thường phù hợp khi tự tạo một bộ export nhiều query cần nhìn cùng trạng thái database.

### 3.3. Snapshot được thiết lập lúc nào?

Trong REPEATABLE READ, snapshot được thiết lập khi transaction thực hiện statement đầu tiên cần snapshot, không nhất thiết ngay tại lệnh BEGIN. Sau đó snapshot được giữ ổn định cho transaction.

Nếu cần phối hợp nhiều sessions, hãy tạo snapshot rõ ràng trong transaction nguồn và export nó cho sessions khác.

### 3.4. SERIALIZABLE

`SERIALIZABLE` bổ sung kiểm tra để các transaction concurrent có thể được giải thích như một thứ tự tuần tự hợp lệ. Nó có thể abort transaction nếu phát hiện serialization anomaly.

Đối với dump read-only, PostgreSQL có tùy chọn `SERIALIZABLE READ ONLY DEFERRABLE`. Transaction có thể chờ một safe snapshot trước khi bắt đầu đọc, từ đó tránh một số serialization anomalies liên quan tới snapshot.

`pg_dump --serializable-deferrable` yêu cầu chế độ này. Nó có thể chờ trước khi dump bắt đầu và không phải lựa chọn mặc định cần thiết cho mọi backup.

### 3.5. Bảng so sánh

| Isolation | Snapshot giữa nhiều SELECT | Có thể thấy commit mới giữa các SELECT? | Phù hợp cho export nhiều bảng tự viết |
|---|---|---|---|
| READ COMMITTED | Mỗi statement có snapshot riêng | Có | Không nếu cần một trạng thái chung |
| REPEATABLE READ | Snapshot ổn định trong transaction | Không | Có, thường là lựa chọn phù hợp |
| SERIALIZABLE | Snapshot ổn định kèm serialization checks | Không; có thể chờ/abort theo điều kiện | Dùng khi cần semantics serializable cụ thể |

### 3.6. Export thủ công đúng snapshot

Ví dụ:

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;

COPY (
    SELECT order_id, customer_id, total
    FROM sales.orders
    ORDER BY order_id
) TO STDOUT WITH (FORMAT csv, HEADER true);

COPY (
    SELECT payment_id, order_id, amount
    FROM sales.payments
    ORDER BY payment_id
) TO STDOUT WITH (FORMAT csv, HEADER true);

COMMIT;
```

Đoạn trên minh họa cùng một transaction/snapshot cho nhiều câu COPY TO STDOUT. Client phải ghi hai output streams vào hai file riêng và quản lý lỗi/đóng transaction đúng cách.

Nếu chạy mỗi COPY trong một connection autocommit riêng, bạn không có bảo đảm cùng snapshot.

---

## 4. pg_dump tạo snapshot như thế nào?

### 4.1. Một database, một snapshot logic

`pg_dump` là công cụ logical backup cho một database. Nó kết nối tới server, bắt đầu transaction đọc và lấy snapshot để các thao tác đọc trong dump phản ánh một trạng thái nhất quán.

Trong khi dump chạy, ứng dụng có thể tiếp tục:

- INSERT rows mới.
- UPDATE hoặc DELETE rows hiện có.
- SELECT dữ liệu.
- Commit các transaction bình thường.

Những thay đổi commit sau snapshot không xuất hiện trong bản dump đó. Đây là hành vi mong muốn: dump đại diện cho một mốc logic, không phải một tập dữ liệu thay đổi theo thời gian đọc từng bảng.

### 4.2. pg_dump không cần khóa toàn database

`pg_dump` dùng MVCC để đọc dữ liệu. Nó lấy `ACCESS SHARE` locks trên các bảng cần dump để ngăn các thao tác cần lock xung đột làm thay đổi cấu trúc relation trong lúc đọc.

`ACCESS SHARE` tương thích với các table locks thông thường của SELECT, INSERT, UPDATE và DELETE. Vì vậy ứng dụng thường vẫn hoạt động trong lúc dump.

### 4.3. Snapshot không có nghĩa dump không thể lỗi

Dump vẫn có thể thất bại nếu:

- Không đủ quyền đọc một object.
- Kết nối bị mất hoặc server restart.
- Storage/network đầy hoặc client không ghi được file.
- DDL xung đột với lock của dump.
- Một object thay đổi theo cách khiến dump không thể tiếp tục nhất quán.
- Client bị kill hoặc timeout.

Một file output có kích thước lớn không tự chứng minh dump hoàn tất. Chỉ coi artifact là backup thành công khi pg_dump exit code thành công và quy trình kiểm tra/restore xác nhận.

### 4.4. pg_dump và các transaction chưa commit

Rows được tạo bởi transaction chưa commit tại snapshot không được dump như dữ liệu đã commit. Nếu transaction commit sau khi snapshot bắt đầu, dump vẫn không nhìn thấy rows đó.

Rows đã bị DELETE/UPDATE sau snapshot vẫn có thể xuất hiện theo phiên bản mà snapshot cũ nhìn thấy.

### 4.5. pg_dump là backup theo database

`pg_dump` dump một database. Nó không tạo một snapshot đồng thời của mọi database trong cluster, cũng không thay thế backup cluster-wide.

Những global objects như roles và tablespaces được xử lý bằng `pg_dumpall` hoặc quy trình riêng. `pg_dumpall` có thể dump nhiều database theo các kết nối/transaction khác nhau; không coi toàn bộ cluster dump là một global atomic snapshot xuyên mọi database.

### 4.6. Phạm vi không nằm trong snapshot

Một logical dump không tự bao gồm:

- Toàn bộ WAL history cần cho point-in-time recovery.
- File ngoài database mà ứng dụng tham chiếu.
- State của message broker, object storage hoặc service khác.
- Cấu hình server/OS, secrets và hạ tầng.
- Một snapshot đồng bộ toàn cluster qua tất cả databases.

Hãy kết hợp logical dump với physical backup/WAL archiving hoặc các bản sao của hệ thống ngoài database khi RPO/RTO yêu cầu.

---

## 5. Parallel dump và synchronized snapshots

### 5.1. Vì sao dump song song cần snapshot chung?

Dump một database lớn có thể mất nhiều giờ nếu đọc từng bảng tuần tự. `pg_dump -j N` cho phép nhiều worker đọc các phần dữ liệu đồng thời.

Nếu mỗi worker tự lấy snapshot độc lập, worker A có thể thấy transaction đã commit trong khi worker B không thấy transaction đó. Bản dump có thể không phản ánh một trạng thái database duy nhất.

PostgreSQL giải quyết bằng **synchronized snapshots**: leader tạo snapshot và các worker import cùng snapshot đó trước khi đọc dữ liệu.

### 5.2. Ví dụ lệnh parallel dump

```bash
pg_dump \
  --format=directory \
  --jobs=4 \
  --file=/backup/appdb.dumpdir \
  --dbname=appdb
```

Directory format (`-Fd`) hỗ trợ parallel dump. `--jobs=4` chạy tối đa bốn worker đọc song song; số connections thực tế còn phụ thuộc tiến trình leader và hoạt động dump.

### 5.3. Format và parallel dump

| Format | Cờ | Parallel dump với pg_dump? | Đặc điểm |
|---|---|---|---|
| Plain SQL | `-Fp` | Không | Một script SQL có thể đọc được |
| Custom | `-Fc` | Không cho parallel dump | Archive linh hoạt, chọn object khi restore, hỗ trợ parallel restore |
| Directory | `-Fd` | Có | Một thư mục gồm metadata và các file data, hỗ trợ parallel dump/restore |
| Tar | `-Ft` | Không | Archive dạng tar, khả năng chọn object hạn chế hơn custom |

Nếu cần dump song song, chọn directory format. Custom format vẫn hữu ích khi cần một archive file dễ lưu trữ và parallel restore.

### 5.4. Worker dùng cùng snapshot

Trong parallel dump:

1. Leader kết nối database và thiết lập transaction/snapshot.
2. Leader lấy các locks cần thiết trên objects được dump.
3. Worker kết nối riêng và import synchronized snapshot.
4. Mỗi worker đọc một phần dữ liệu với cùng visibility rules.
5. Leader điều phối metadata và chờ worker hoàn tất.
6. Snapshot/locks được giải phóng khi dump kết thúc.

Nhờ đó, dữ liệu ở các bảng khác nhau vẫn nhất quán theo cùng một mốc logic dù worker chạy ở thời điểm khác nhau.

### 5.5. Nhiều jobs không tự làm dump “mới hơn”

Parallelism chỉ thay đổi cách chia công việc và thời gian hoàn thành. Snapshot vẫn được thiết lập lúc đầu; worker hoàn thành sau không nhìn thấy các commit mới hơn.

### 5.6. Tác động của số jobs

Tăng `--jobs` có thể:

- Rút ngắn thời gian dump nếu storage/network có dư throughput.
- Tăng số concurrent table scans và random/sequential I/O.
- Tăng CPU cho đọc, encode, compression và network.
- Tăng connections và memory trên server/client.
- Làm cache churn mạnh hơn.
- Tăng cạnh tranh với workload OLTP.

Không chọn jobs bằng số CPU một cách máy móc. Nút thắt có thể là storage bandwidth, network, IOPS, lock waits hoặc CPU compression.

### 5.7. Parallel dump và snapshot cũ

Một worker đọc bảng lớn trong nhiều phút vẫn dùng snapshot của dump. Worker không tự chuyển sang snapshot mới khi bảng khác đã được dump xong.

Đây là điều bảo đảm nhất quán, đồng thời kéo dài thời gian snapshot nếu một object rất lớn làm chậm toàn bộ dump.

### 5.8. Nếu worker thất bại

Parallel dump không nên được coi là hoàn tất khi một worker lỗi. pg_dump báo lỗi và exit code khác 0. Hãy coi directory archive dở dang là artifact chưa hợp lệ; dọn staging theo quy trình và chạy lại.

### 5.9. Không tắt synchronized snapshots để tăng tốc

Không đánh đổi snapshot consistency bằng cách cho workers tự đọc snapshot riêng, trừ khi bạn chủ động chấp nhận semantics không nhất quán và đã đánh giá rõ. Với một bản backup phục hồi database, nhất quán thường quan trọng hơn việc tối ưu một ít thời gian.

---

## 6. Exported snapshot và phối hợp nhiều session

### 6.1. Khi nào cần exported snapshot?

Một quy trình có thể cần:

- Một pg_dump cho schema/data.
- Một query export riêng cho bảng audit.
- Một tiến trình tạo manifest/counts.
- Nhiều pg_dump chạy ở các tiến trình khác nhau nhưng cần cùng một trạng thái dữ liệu.

Nếu mỗi process tự mở transaction độc lập, chúng có thể lấy snapshot khác nhau. PostgreSQL cho phép một transaction export snapshot identifier để transaction khác import snapshot đó.

### 6.2. pg_export_snapshot()

Mở một transaction REPEATABLE READ:

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;

SELECT pg_export_snapshot();
```

PostgreSQL trả một snapshot identifier dạng token. Token này chỉ dùng để import snapshot trong khi transaction export còn mở.

### 6.3. Import snapshot bằng SET TRANSACTION SNAPSHOT

Ở một session khác, trước khi query bất kỳ dữ liệu nào trong transaction:

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;

SET TRANSACTION SNAPSHOT '00000003-0000001B-1';

SELECT COUNT(*) FROM sales.orders;

COMMIT;
```

Chuỗi trong ví dụ là placeholder; phải thay bằng identifier vừa nhận từ `pg_export_snapshot()`. `SET TRANSACTION SNAPSHOT` phải được gọi đúng thời điểm trong transaction và isolation level phải phù hợp.

### 6.4. Lifetime của snapshot token

Transaction export phải tiếp tục mở cho tới khi các transaction consumer đã import snapshot. Nếu transaction export kết thúc trước khi consumer import, token không còn dùng được.

Sau khi consumer đã import snapshot, consumer có thể tiếp tục dùng snapshot đó trong transaction của mình theo quy tắc PostgreSQL.

### 6.5. Dùng --snapshot với pg_dump

`pg_dump` hỗ trợ option `--snapshot` để dùng snapshot đã được export từ một session khác:

```bash
pg_dump \
  --snapshot='00000003-0000001B-1' \
  --format=custom \
  --file=appdb.dump \
  --dbname=appdb
```

Đây là ví dụ minh họa. Session giữ snapshot export phải còn mở cho tới khi pg_dump đã import snapshot. Nếu phối hợp nhiều process, điều phối lifecycle của snapshot transaction và tất cả consumer một cách rõ ràng.

### 6.6. Trình tự phối hợp

```text
Session A (coordinator)
    BEGIN REPEATABLE READ READ ONLY
    pg_export_snapshot() -> SNAPSHOT_ID
    giữ transaction mở
              |
              +----------------------+
              |                      |
              v                      v
        pg_dump process 1       query/export process 2
        import SNAPSHOT_ID      SET TRANSACTION SNAPSHOT
        dump tables A/B         export report C
              |                      |
              +----------+-----------+
                         |
              tất cả consumer đã import
                         |
                         v
             Session A COMMIT/ROLLBACK
```

### 6.7. Các giới hạn

- Snapshot token không phải file backup; nó chỉ định nghĩa visibility state.
- Consumer phải kết nối cùng database phù hợp và dùng transaction semantics tương thích.
- Token không tồn tại vĩnh viễn.
- Transaction giữ snapshot lâu có thể ảnh hưởng vacuum.
- Snapshot không đồng bộ sequence state, external services hoặc các database khác.

---

## 7. Sequence là trường hợp đặc biệt

### 7.1. Sequence không transactional như table rows

`nextval()` và `setval()` không tuân theo rollback semantics thông thường. Nếu transaction gọi nextval rồi rollback, sequence vẫn có thể đã tăng.

Sequence được thiết kế để cấp giá trị duy nhất/đơn điệu theo cơ chế của nó, không phải để tạo một counter transactional không có gap.

### 7.2. Snapshot không đóng băng sequence

MVCC snapshot của pg_dump bảo đảm visibility cho table rows, nhưng sequence state không được đóng băng giống ordinary row versions. Một session khác có thể gọi nextval trong lúc dump đang đọc dữ liệu.

Vì thế, đừng diễn giải câu “dump consistent tại thời điểm bắt đầu” thành “mọi sequence value chính xác tại cùng một instant”.

### 7.3. Hệ quả khi restore

pg_dump lưu trạng thái sequence cần thiết để khôi phục sequence. Vì sequence có thể thay đổi đồng thời trong lúc dump, giá trị được dump không nhất thiết tương ứng hoàn toàn với các rows được nhìn thấy theo snapshot.

Sau restore, hãy kiểm tra sequence state và ứng dụng cấp ID tiếp theo, nhất là khi hệ thống ghi liên tục trong lúc backup.

### 7.4. Kiểm tra sequence

Liệt kê sequence trong schema:

```sql
SELECT
    schemaname,
    sequencename,
    last_value
FROM pg_sequences
WHERE schemaname = 'sales'
ORDER BY sequencename;
```

`pg_sequences` có các trường tùy version; `last_value` có thể NULL nếu role không có quyền đọc sequence hoặc sequence chưa được gọi trong session/state tương ứng. Kiểm tra documentation version đang dùng.

### 7.5. Sequence cache và gap

Sequence có thể cache giá trị trong backend. Khi crash hoặc session kết thúc, gaps có thể xuất hiện. Đây là behavior bình thường, không phải dấu hiệu dump thiếu rows.

---

## 8. Locks của pg_dump và tương tác với DML/DDL

### 8.1. ACCESS SHARE

`pg_dump` lấy `ACCESS SHARE` locks trên các bảng mà nó đọc. Đây là lock mode nhẹ nhất trong nhóm table-level locks của PostgreSQL.

`ACCESS SHARE` tương thích với các thao tác đọc/ghi thông thường:

- SELECT.
- INSERT.
- UPDATE.
- DELETE.
- MERGE theo lock behavior của câu lệnh.

Vì vậy dump thường không khóa ứng dụng khỏi việc ghi dữ liệu.

### 8.2. Lock nào xung đột?

`ACCESS SHARE` xung đột với `ACCESS EXCLUSIVE`. Một số thao tác thường cần lock mạnh này:

- DROP TABLE.
- TRUNCATE.
- VACUUM FULL.
- Nhiều dạng ALTER TABLE thay đổi cấu trúc.
- Một số thao tác maintenance/rewrite relation.

Không phải mọi câu ALTER TABLE đều dùng cùng lock mode; lock phụ thuộc subcommand và PostgreSQL version.

### 8.3. DDL chạy trước dump

Nếu một DDL đã giữ ACCESS EXCLUSIVE lock khi pg_dump cần lấy ACCESS SHARE, pg_dump phải chờ. Nếu DDL kéo dài hoặc có transaction mở lâu, dump có thể không bắt đầu đọc đúng lúc dự kiến.

### 8.4. DDL bắt đầu sau dump

Nếu pg_dump đã lấy ACCESS SHARE lock, DDL cần ACCESS EXCLUSIVE sẽ phải chờ dump giải phóng lock. Một lệnh DROP TABLE hoặc ALTER TABLE có thể đứng chờ trong suốt thời gian dump giữ lock.

### 8.5. Lock queue và tác động dây chuyền

Một DDL đang chờ ACCESS EXCLUSIVE có thể tạo hiệu ứng xếp hàng lock. Các request mới cần lock tương thích với dump nhưng đứng sau DDL trong hàng đợi có thể cũng bị chậm tùy tình huống.

Vì vậy, dù ACCESS SHARE tương thích với DML, một DDL đang chờ có thể làm phát sinh độ trễ ngoài dự kiến cho workload.

### 8.6. Xem locks

```sql
SELECT
    a.pid,
    a.application_name,
    a.state,
    a.xact_start,
    l.locktype,
    l.mode,
    l.granted,
    l.relation::regclass AS relation,
    a.wait_event_type,
    a.wait_event,
    left(a.query, 140) AS query_sample
FROM pg_locks AS l
JOIN pg_stat_activity AS a
  ON a.pid = l.pid
WHERE l.relation IS NOT NULL
ORDER BY l.granted, a.xact_start;
```

Query trên giúp xem table locks và sessions liên quan. Nó không phải báo cáo đầy đủ mọi lock dependency; khi điều tra blocking, xem cả blocker/waiter và lock graph.

### 8.7. Xem blocker

```sql
SELECT
    waiting.pid AS waiting_pid,
    waiting.application_name AS waiting_app,
    waiting.wait_event_type,
    waiting.wait_event,
    blocker.pid AS blocker_pid,
    blocker.application_name AS blocker_app,
    blocker.state AS blocker_state,
    blocker.xact_start AS blocker_xact_start,
    left(blocker.query, 160) AS blocker_query
FROM pg_stat_activity AS waiting
CROSS JOIN LATERAL unnest(pg_blocking_pids(waiting.pid)) AS b(pid)
JOIN pg_stat_activity AS blocker
  ON blocker.pid = b.pid
ORDER BY waiting.pid;
```

`pg_blocking_pids()` cho biết các backend đang block một PID. Cần quyền monitoring thích hợp để xem đầy đủ thông tin sessions khác.

### 8.8. Giới hạn thời gian chờ lock

pg_dump có option:

```bash
pg_dump \
  --lock-wait-timeout=30s \
  --format=custom \
  --file=appdb.dump \
  --dbname=appdb
```

Nếu không thể lấy lock cần thiết trong thời gian cho phép, dump sẽ thất bại thay vì chờ vô hạn. Chọn timeout theo maintenance window và SLA; timeout quá ngắn có thể làm backup thất bại thường xuyên khi DDL hợp lệ đang chạy.

### 8.9. Dump không phải công cụ điều phối schema migration

Trước khi chạy migration có DDL nặng, xác định backup đang chạy và lock behavior. Tương tự, khi backup kéo dài, tránh chạy DDL cần ACCESS EXCLUSIVE nếu không có kế hoạch chờ/đổi lịch.

---

## 9. Snapshot lâu ảnh hưởng vacuum và bloat như thế nào?

### 9.1. Dead tuples

UPDATE/DELETE trong PostgreSQL tạo hoặc để lại row versions cũ. Khi không còn snapshot nào có thể nhìn thấy chúng, VACUUM có thể đánh dấu không gian đó có thể tái sử dụng.

Nếu một transaction giữ snapshot cũ, PostgreSQL phải giữ các tuple versions mà snapshot đó còn có thể cần.

### 9.2. pg_dump giữ snapshot trong thời gian dài

Dump database lớn có thể kéo dài từ vài phút tới nhiều giờ. Trong khoảng thời gian đó:

- Ứng dụng vẫn UPDATE/DELETE.
- Các phiên bản cũ tích lũy.
- Autovacuum vẫn có thể chạy, nhưng không thể loại bỏ những dead tuples còn cần cho snapshot.
- Table/index có thể lớn hơn và dung lượng trống chưa được tái sử dụng.

Đây là một trong những tác động quan trọng nhất của dump đang chạy.

### 9.3. Bloat không nhất thiết xuất hiện ngay trong dump file

Dump đang chạy thường không làm file archive lớn lên vì dead tuples. Tác động là ở database nguồn: vacuum chưa thể thu hồi các phiên bản cũ, khiến relation có thể tăng kích thước trong khi workload tiếp tục ghi.

### 9.4. Vacuum vẫn chạy nhưng bị giới hạn

Không nên nói “pg_dump khóa vacuum”. Autovacuum có thể tiếp tục scan và xử lý nhiều công việc; giới hạn chính là không được loại bỏ tuple versions còn có thể nhìn thấy bởi snapshot cũ.

### 9.5. Quan sát transaction age và backend_xmin

```sql
SELECT
    pid,
    usename,
    application_name,
    state,
    xact_start,
    now() - xact_start AS transaction_age,
    backend_xmin,
    age(backend_xmin) AS xmin_age,
    wait_event_type,
    wait_event
FROM pg_stat_activity
WHERE backend_xmin IS NOT NULL
ORDER BY xact_start NULLS LAST;
```

`backend_xmin` cho biết giới hạn xmin liên quan tới snapshot của backend. Một backend giữ xmin cũ lâu có thể khiến vacuum không dọn được một số dead tuples.

### 9.6. Tìm bảng có nhiều dead tuples

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
ORDER BY n_dead_tup DESC
LIMIT 20;
```

`n_dead_tup` là ước lượng thống kê, không phải số đếm chính xác theo từng tuple tại thời điểm query.

### 9.7. Kiểm tra database age

```sql
SELECT
    datname,
    age(datfrozenxid) AS xid_age,
    datfrozenxid
FROM pg_database
ORDER BY xid_age DESC;
```

Snapshot quá lâu, transaction mở lâu và workload có tốc độ transaction cao có thể làm freeze horizon khó tiến lên. Nếu kéo dài, điều này góp phần tăng áp lực transaction ID wraparound; cần theo dõi age và autovacuum/freeze progress.

### 9.8. Không kết luận từ n_dead_tup đơn lẻ

Dead tuple estimate cao không tự chứng minh pg_dump là nguyên nhân. Cần đối chiếu:

- Thời gian transaction/snapshot.
- backend_xmin.
- Tốc độ UPDATE/DELETE.
- Autovacuum progress và logs.
- Table/index growth.
- Replication feedback/slots.

### 9.9. Không kill snapshot một cách vội vàng

Kết thúc session giữ snapshot có thể cho phép vacuum dọn tuple versions về sau, nhưng sẽ làm dump thất bại hoặc mất tính hoàn chỉnh. Trước khi cancel, xác định:

- Dump đã chạy bao lâu và còn bao nhiêu việc.
- Có file/archive dở dang cần xóa hay giữ lại để điều tra.
- Có thể chờ dump xong trong maintenance window không.
- Có cần chạy lại backup và kiểm tra restore không.

---

## 10. Dump từ primary hay standby?

### 10.1. Dump từ primary

Ưu điểm:

- Không phụ thuộc recovery conflict của hot standby.
- Thường có thể thấy state hiện hành của primary.
- Dễ phối hợp với các nghiệp vụ cần snapshot và role quyền đọc.

Đánh đổi:

- Tải đọc cạnh tranh với workload ghi/đọc chính.
- Snapshot lâu ảnh hưởng vacuum horizon trên primary.
- Dump có thể tăng cache churn và storage I/O.

### 10.2. Dump từ hot standby

Có thể chuyển tải đọc sang standby, giảm một phần I/O trực tiếp trên primary. Nhưng standby đang replay WAL và có thể gặp **recovery conflicts** với query lâu.

### 10.3. Recovery conflict

Một query dài trên standby có thể cần row versions hoặc relation state mà recovery cần loại bỏ/đổi. PostgreSQL có thể chờ một thời gian hoặc cancel query để tiếp tục recovery theo các cấu hình standby delay.

Dump bị cancel giữa chừng không tạo ra backup hợp lệ.

### 10.4. hot_standby_feedback

`hot_standby_feedback` có thể gửi xmin từ standby về primary để primary tránh vacuum cleanup các row versions cần cho query trên standby.

Đánh đổi:

- Giảm một số recovery conflicts/cancel query trên standby.
- Có thể giữ dead tuples trên primary lâu hơn và tăng bloat.
- Không phải giải pháp miễn phí; cần theo dõi vacuum và storage.

### 10.5. Replication lag

Một dump nặng trên standby có thể tiêu thụ I/O/CPU và làm replay chậm lại. Nếu standby lag, các query đọc từ nó cũng phản ánh state cũ hơn primary.

Nếu cần một snapshot đồng bộ với một nghiệp vụ trên primary, phải xác định rõ LSN/timeline và topology; không giả định dump từ standby luôn tương đương trạng thái mới nhất của primary.

### 10.6. Chọn nguồn dump

| Điều kiện | Primary | Standby |
|---|---|---|
| Muốn giảm tải đọc trên primary | Không lý tưởng | Có thể phù hợp |
| Có query dump rất dài | Giữ xmin trên primary | Có thể gặp recovery conflict; feedback có thể gây bloat primary |
| Cần dữ liệu mới nhất theo primary | Trực tiếp | Có thể lag |
| Có DDL thường xuyên | DDL có thể chờ lock dump | DDL/WAL replay có thể gây conflict |
| Hạ tầng standby thiếu I/O | Không bị ảnh hưởng bởi standby read load | Dump có thể làm replay lag |

Lựa chọn dựa trên SLA của primary, replication lag, storage capacity và backup requirements.

---

## 11. Tác động tài nguyên của dump đang chạy

### 11.1. Disk I/O

Dump đọc toàn bộ hoặc phần lớn table data, toast values và metadata. Nó có thể tạo lượng read I/O lớn, nhất là khi database lớn hơn RAM hoặc workload OLTP cũng đang truy cập cùng storage.

### 11.2. CPU

CPU được dùng cho:

- Đọc và giải mã tuple.
- Chuyển đổi dữ liệu thành output format.
- Nén archive.
- Mã hóa transport nếu kết nối SSL.
- Parallel worker coordination.

Compression có thể giảm bytes ghi/network nhưng tăng CPU. Mức compression cao không phải lúc nào cũng nhanh hơn.

### 11.3. Network

Khi client chạy ở máy khác, dữ liệu được truyền qua network. Network throughput, packet loss và client bandwidth có thể trở thành bottleneck.

### 11.4. Client disk

pg_dump ghi archive hoặc SQL file ở client. Nếu filesystem đầy, permission sai hoặc mount bị mất, dump có thể thất bại dù query trên server vẫn đọc được dữ liệu.

### 11.5. Memory và cache

Dump không nhất thiết nạp toàn bộ database vào memory, nhưng nhiều scans song song có thể làm thay đổi cache working set và đẩy dữ liệu thường dùng của ứng dụng ra khỏi cache.

### 11.6. Tăng --jobs không phải lúc nào cũng nhanh hơn

Nếu storage đã bão hòa, tăng worker chỉ tăng queueing và cạnh tranh. Nếu network/client disk chậm, nhiều workers cũng không giải quyết bottleneck.

### 11.7. Nén archive

Các format archive có thể nén data. Cân nhắc:

- CPU client/server theo cách thực thi và version.
- Kích thước archive.
- Thời gian truyền.
- Thời gian restore/decompression.
- Khả năng giữ đủ khoảng trống cho staging và file cuối.

### 11.8. Resource isolation

Nếu dump thường xuyên ảnh hưởng OLTP, cân nhắc:

- Chạy vào giờ tải thấp.
- Dump từ standby có tài nguyên phù hợp.
- Giới hạn `--jobs`.
- Đặt CPU/IO limits ở container/OS/cloud nếu có.
- Dùng backup infrastructure chuyên dụng.
- Theo dõi latency ứng dụng và dừng/điều chỉnh theo ngưỡng đã thống nhất.

Không dùng một mức jobs cố định cho mọi database và mọi giờ trong ngày.

---

## 12. Các lệnh pg_dump thường dùng

### 12.1. Plain SQL format

```bash
pg_dump \
  --format=plain \
  --file=appdb.sql \
  --dbname=appdb
```

Plain format tạo script SQL có thể đọc được và nạp bằng psql. Nó tiện cho inspection và chỉnh sửa có kiểm soát, nhưng không có tính năng selective restore/parallel restore như archive formats.

### 12.2. Custom format

```bash
pg_dump \
  --format=custom \
  --file=appdb.dump \
  --dbname=appdb
```

Custom archive phù hợp để lưu thành một file, xem danh mục object và chọn nội dung restore bằng `pg_restore`. Nó hỗ trợ parallel restore.

### 12.3. Directory format và parallel dump

```bash
pg_dump \
  --format=directory \
  --jobs=4 \
  --file=appdb.dumpdir \
  --dbname=appdb
```

Directory format lưu các phần dump thành nhiều file trong một thư mục và hỗ trợ parallel dump. Hãy dùng thư mục staging mới, có đủ dung lượng; chỉ đánh dấu backup hoàn tất khi pg_dump kết thúc thành công.

### 12.4. Dump schema hoặc data riêng

```bash
pg_dump --schema-only --file=schema.sql --dbname=appdb
pg_dump --data-only --file=data.sql --dbname=appdb
```

Hai lệnh chạy riêng sẽ có hai snapshot khác nhau. Nếu schema và data phải thuộc cùng một mốc logic, đừng mặc định ghép hai file riêng từ hai lần dump là một backup nhất quán. Dùng một archive đầy đủ hoặc phối hợp snapshot rõ ràng.

### 12.5. Chỉ dump một schema

```bash
pg_dump --schema=sales --format=custom --file=sales.dump --dbname=appdb
```

Dump một schema vẫn cần snapshot và lock đối với các objects thuộc phạm vi. Foreign keys hoặc dependencies trỏ sang schema khác cần được xem xét khi restore.

### 12.6. Chỉ dump một số bảng

```bash
pg_dump \
  --table=sales.orders \
  --table=sales.payments \
  --format=custom \
  --file=sales-tables.dump \
  --dbname=appdb
```

Một archive chỉ gồm một phần object có thể thiếu dependencies. Hãy kiểm tra extension, type, function, sequence, schema và referenced tables cần thiết trước khi dùng nó làm artifact phục hồi độc lập.

### 12.7. Ghi file staging

```bash
pg_dump --format=custom --file=appdb.dump.part --dbname=appdb

# Chỉ chạy bước publish khi pg_dump exit code = 0:
mv appdb.dump.part appdb.dump
```

Với directory format, dump vào một thư mục staging mới, xác minh thành công rồi đổi tên cả thư mục. Rename có tính atomic phụ thuộc filesystem và vị trí source/destination.

### 12.8. Lock wait timeout

```bash
pg_dump \
  --lock-wait-timeout=30s \
  --format=custom \
  --file=appdb.dump \
  --dbname=appdb
```

Option này giới hạn thời gian chờ lấy shared locks lúc bắt đầu dump. Kiểm tra pg_dump version vì option availability có thể phụ thuộc phiên bản.

### 12.9. Serializable deferrable

```bash
pg_dump \
  --serializable-deferrable \
  --format=custom \
  --file=appdb.dump \
  --dbname=appdb
```

Tùy chọn này yêu cầu một serializable, read-only, deferrable transaction và có thể chờ để lấy safe snapshot. Nó phục vụ nhu cầu semantics cụ thể, không phải một nút tăng tốc dump.

### 12.10. Kiểm tra phiên bản client/server

```bash
pg_dump --version
psql --version
```

pg_dump không thể dump server major version mới hơn major version của chính pg_dump. Thực tế nên dùng client tools tương thích và đã được hỗ trợ cho server đang chạy. Archive được tạo bởi pg_dump thường hướng tới restore vào cùng hoặc phiên bản PostgreSQL mới hơn; không mặc định restore được vào server cũ hơn.

---

## 13. Snapshot nhất quán không đồng nghĩa toàn bộ hệ thống nhất quán

### 13.1. Một database

pg_dump bảo đảm snapshot nhất quán trong phạm vi một database theo transaction snapshot và objects được dump.

### 13.2. Nhiều database

Nếu ứng dụng dùng:

- `appdb` chứa orders.
- `billingdb` chứa invoices.
- `identitydb` chứa users.

ba lần pg_dump độc lập có thể lấy ba snapshots ở ba thời điểm khác nhau. PostgreSQL không cung cấp một MVCC snapshot duy nhất xuyên các databases trong một cluster bằng cách chạy pg_dumpall.

Nếu một business operation cập nhật nhiều databases, cần thiết kế backup/restore coordination ở tầng ứng dụng hoặc hạ tầng, chẳng hạn maintenance/quiesce, application event boundary, coordinated backups hoặc nguồn sự thật có thể reconcile.

### 13.3. Global objects

Roles, tablespaces và một số cluster-level objects không thuộc một database đơn lẻ. `pg_dumpall` có thể xuất chúng cùng nội dung các databases, nhưng không biến mọi database thành một snapshot đồng thời duy nhất.

### 13.4. External systems

Nếu transaction PostgreSQL ghi database rồi gửi message tới Kafka hoặc cập nhật object storage, snapshot PostgreSQL không tự bao gồm message/object đó. Dùng outbox pattern, event offsets, manifests hoặc coordination phù hợp để tạo một recovery boundary có thể kiểm chứng.

### 13.5. Foreign data

Foreign tables và FDW truy cập nguồn dữ liệu ngoài. Snapshot local PostgreSQL không tự bảo đảm nguồn remote có cùng snapshot hoặc cùng thời điểm. Xác định rõ dữ liệu nào thực sự được dump và semantics của FDW/foreign server đang dùng.

### 13.6. Sequence và non-transactional state

Sequence state là ngoại lệ quan trọng như phần trước. Những state không theo MVCC cần được đánh giá riêng nếu yêu cầu backup đúng tuyệt đối theo một business cut.

---

## 14. Theo dõi pg_dump khi đang chạy

### 14.1. Đặt application_name

Nên gắn tên dễ nhận biết cho backup connection bằng connection service/URI hoặc cấu hình libpq:

```text
application_name=nightly_pg_dump
```

Khi đó có thể lọc session trong `pg_stat_activity` theo tên. Cách truyền parameter cụ thể tùy connection string/service file và môi trường.

### 14.2. Xem sessions dump

```sql
SELECT
    pid,
    usename,
    application_name,
    client_addr,
    state,
    xact_start,
    now() - xact_start AS xact_age,
    backend_xmin,
    wait_event_type,
    wait_event,
    left(query, 180) AS query_sample
FROM pg_stat_activity
WHERE application_name ILIKE '%dump%'
   OR query ILIKE 'COPY %'
ORDER BY xact_start NULLS LAST;
```

pg_dump thường đọc dữ liệu bằng SELECT statements, nên filter chỉ theo query bắt đầu bằng COPY sẽ bỏ sót nhiều sessions. Application name rõ ràng giúp nhận diện dễ hơn.

### 14.3. Không có pg_stat_progress_pg_dump chung

PostgreSQL không cung cấp một view progress riêng tổng quát cho toàn bộ logical pg_dump tương tự `pg_stat_progress_vacuum`. Các view progress cho COPY hoặc base backup không phải progress tracker của pg_dump SELECT scans.

Theo dõi bằng:

- Output verbose của pg_dump.
- PID/process và elapsed time ở client.
- Kích thước file/archive đang tăng.
- `pg_stat_activity`, locks và wait events.
- I/O, CPU, network và filesystem metrics.

File tăng kích thước là dấu hiệu tiến trình đang ghi dữ liệu, không phải bằng chứng dump đã hoàn tất.

### 14.4. Theo dõi blocking

```sql
SELECT
    pid,
    application_name,
    state,
    wait_event_type,
    wait_event,
    now() - query_start AS query_age,
    now() - xact_start AS xact_age,
    left(query, 200) AS query_sample
FROM pg_stat_activity
WHERE wait_event_type = 'Lock'
ORDER BY query_start;
```

Nếu pg_dump chờ lock, xác định blocker bằng `pg_blocking_pids()` và xem DDL/transaction đang giữ lock. Không terminate session chỉ vì query age cao; trước tiên xác định owner và business impact.

### 14.5. Theo dõi vacuum và dead tuples

Kết hợp:

```sql
SELECT
    pid,
    datname,
    relid::regclass AS relation,
    phase,
    heap_blks_scanned,
    heap_blks_vacuumed,
    index_vacuum_count
FROM pg_stat_progress_vacuum;

SELECT
    schemaname,
    relname,
    n_dead_tup,
    last_autovacuum,
    autovacuum_count
FROM pg_stat_user_tables
ORDER BY n_dead_tup DESC
LIMIT 20;
```

Một snapshot cũ có thể làm vacuum không loại bỏ được một số dead tuples. View progress cho biết vacuum đang làm gì; statistics table cho biết ước lượng dead tuples.

### 14.6. Theo dõi replication

Nếu dump từ standby:

```sql
SELECT
    application_name,
    state,
    sync_state,
    write_lag,
    flush_lag,
    replay_lag
FROM pg_stat_replication;
```

Kiểm tra replay lag trong suốt backup để biết dump workload có làm standby tụt lại hay không.

### 14.7. Theo dõi WAL retention riêng

Logical pg_dump snapshot trên primary không tự động có nghĩa WAL segments sẽ được giữ lại toàn bộ trong suốt thời gian dump. WAL retention thường liên quan archive backlog, replication slots và standby requirements.

Nếu có replication slots:

```sql
SELECT
    slot_name,
    slot_type,
    active,
    restart_lsn,
    confirmed_flush_lsn,
    wal_status,
    safe_wal_size
FROM pg_replication_slots;
```

Các cột có thể khác theo major version. Slot không active hoặc consumer chậm có thể giữ WAL và làm filesystem WAL tăng; điều tra độc lập với snapshot pg_dump.

---

## 15. Lập lịch và tổ chức dump trong production

### 15.1. Chọn cửa sổ backup

Ưu tiên thời điểm:

- Workload ghi thấp hơn.
- Storage có dư read bandwidth.
- Không trùng migration/DDL nặng.
- Có đủ dung lượng archive và staging.
- Có người/automation theo dõi và xử lý lỗi.

Không mặc định chạy ban đêm là luôn an toàn; batch/reporting jobs có thể tạo peak cùng lúc.

### 15.2. Giới hạn parallel jobs

Bắt đầu với số jobs thấp, đo impact rồi tăng dần. Ghi nhận:

- Thời gian dump.
- Commit latency của ứng dụng.
- Storage read/write latency.
- CPU và network throughput.
- Vacuum lag/dead tuples.
- Replication lag.

Mục tiêu là đáp ứng backup window mà không vượt SLA của workload chính.

### 15.3. Không chạy nhiều dump lớn chồng nhau

Hai dump đồng thời có thể quét cùng tables, tăng I/O và giữ nhiều snapshots lâu. Nếu cần backup nhiều database, điều phối lịch và concurrency theo capacity.

### 15.4. Thời gian giữ snapshot

Thời gian dump càng dài, snapshot càng lâu. Có thể giảm duration bằng:

- Tối ưu storage/network.
- Chọn jobs phù hợp.
- Tránh compression quá nặng nếu CPU bottleneck.
- Loại trừ objects thực sự không cần.
- Dùng backup infrastructure chuyên dụng cho database rất lớn.

Không chia một database thành nhiều lần dump độc lập chỉ để rút ngắn từng lần nếu yêu cầu cần một snapshot chung; cách đó có thể làm mất tính nhất quán xuyên các phần.

### 15.5. Kiểm tra disk space

Tính cả:

- Archive đang tạo.
- File .part hoặc thư mục staging.
- Backup đã hoàn tất đang được giữ.
- Temporary files.
- Khoảng trống cho restore test.

Directory format có nhiều file; custom/plain có thể là một file lớn. Filesystem đầy giữa chừng khiến backup chưa hoàn chỉnh.

### 15.6. Timeout và cancellation

Đặt timeout phù hợp cho lock acquisition, client connection và orchestration. Timeout query quá thấp có thể làm dump lớn bị hủy; timeout quá dài có thể giữ snapshot và lock trong nhiều giờ khi hệ thống đã có vấn đề.

### 15.7. Ghi manifest

Sidecar manifest nên ghi:

- Database và server identity.
- PostgreSQL server/client versions.
- Thời gian bắt đầu/kết thúc.
- Dump format và options quan trọng.
- Snapshot identifier nếu có phối hợp.
- File list, size, checksum.
- Exit status.
- Backup retention class.

Không đặt password/secret trong manifest hoặc command line có thể bị process listing/log lộ.

---

## 16. Xử lý khi dump thất bại hoặc bị hủy

### 16.1. Exit code

Backup automation phải kiểm tra exit code của pg_dump. Nếu process bị kill, connection reset hoặc server trả lỗi, file có thể đã chứa một phần dữ liệu.

### 16.2. Không publish artifact dở dang

Ghi vào staging path. Chỉ đổi tên/công bố sau khi:

1. pg_dump kết thúc exit code 0.
2. File/archive có thể đọc metadata.
3. Checksum được tính.
4. Manifest ghi trạng thái thành công.

### 16.3. Custom archive inspection

```bash
pg_restore --list appdb.dump
```

Lệnh này liệt kê table of contents trong archive. Nó kiểm tra archive có thể được đọc ở mức metadata; **không thay thế restore test**.

### 16.4. Directory archive inspection

```bash
pg_restore --list appdb.dumpdir
```

Nếu dump directory chưa hoàn tất hoặc thiếu file, inspection/restore có thể báo lỗi.

### 16.5. Khi cancel một dump đang chạy

Trước khi cancel:

- Xác định backup window và mức độ ảnh hưởng của dump.
- Kiểm tra dump đang block DDL hay chỉ đang đọc.
- Kiểm tra vacuum/bloat và application latency.
- Cân nhắc giảm jobs hoặc dời DDL nếu có thể.
- Nếu cần dừng, gửi tín hiệu terminate theo quy trình và kiểm tra client process đã kết thúc.
- Xóa staging artifact dở dang theo retention/incident procedure.

Không xóa file cuối cùng của một backup thành công trước khi xác minh có bản thay thế.

### 16.6. Retry

Sau lỗi, thông thường chạy lại một dump mới với snapshot mới. Không ghép file data từ các lần dump khác nhau nếu chưa có cơ chế snapshot coordination và archive semantics phù hợp.

---

## 17. Restore test mới là xác nhận backup có thể dùng

### 17.1. Kiểm tra archive

```bash
pg_restore --list appdb.dump
```

Kiểm tra TOC và file checksum. Một archive có TOC đọc được vẫn có thể thiếu object data hoặc restore thất bại do version/extension/privilege dependencies.

### 17.2. Restore custom archive vào database test

```bash
createdb appdb_restore

pg_restore \
  --exit-on-error \
  --dbname=appdb_restore \
  appdb.dump
```

Với archive lớn, có thể dùng `--jobs` cho parallel restore nếu format hỗ trợ và server có đủ tài nguyên.

### 17.3. Restore directory archive song song

```bash
createdb appdb_restore

pg_restore \
  --jobs=4 \
  --exit-on-error \
  --dbname=appdb_restore \
  appdb.dumpdir
```

Parallel restore có thể tăng tải CPU/I/O trên target. Không chạy trên production target khi chưa đánh giá.

### 17.4. Restore plain SQL

```bash
createdb appdb_restore

psql \
  -X \
  -v ON_ERROR_STOP=1 \
  --dbname=appdb_restore \
  --file=appdb.sql
```

### 17.5. Kiểm tra dữ liệu

Sau restore, kiểm tra:

- Database và schema tồn tại.
- Bảng, view, function, type, extension được tạo.
- Constraints và indexes hợp lệ.
- Row counts hoặc business invariants quan trọng.
- Sequence state và ID generation.
- Owners, grants và default privileges.
- Large objects nếu ứng dụng dùng.
- Application smoke tests.

Không chỉ so sánh tổng row count; hai database có cùng số rows vẫn có thể khác dữ liệu.

### 17.6. Restore version compatibility

Kiểm tra server đích có extension, locale/collation và quyền cần thiết. Logical dump không mang theo mọi dependency ở OS/cluster. Restore lên major version mới hơn thường là đường nâng cấp được hỗ trợ, nhưng phải kiểm tra compatibility của extensions và SQL objects.

### 17.7. Đo RTO

Ghi thời gian:

- Chuẩn bị target.
- Restore schema/data.
- Tạo indexes/constraints.
- Analyze statistics.
- Smoke test.
- Cutover.

Một file backup được tạo nhanh nhưng restore mất quá lâu vẫn có thể không đáp ứng RTO.

---

## 18. pg_dump, physical backup và point-in-time recovery

### 18.1. Logical dump

`pg_dump` tạo biểu diễn logic của một database: schema và dữ liệu dưới dạng SQL hoặc archive. Nó hữu ích cho:

- Di chuyển database.
- Restore chọn lọc objects.
- Upgrade major version.
- Sao lưu một database/schema.
- Kiểm tra và lưu trữ dữ liệu logic.

### 18.2. Physical backup

Physical backup sao chép data directory ở cấp vật lý theo quy trình PostgreSQL như `pg_basebackup` hoặc giải pháp backup phù hợp. Nó thường dùng cùng WAL archiving để phục hồi cluster tới thời điểm mong muốn.

### 18.3. Snapshot logical không phải PITR

pg_dump phản ánh một trạng thái logic tại snapshot của dump. Nó không tự cung cấp WAL history liên tục để replay tới một timestamp bất kỳ.

Nếu cần point-in-time recovery, cần base backup hợp lệ, WAL archive liên tục và quy trình recovery target đã kiểm thử.

### 18.4. Kết hợp backup

Một chiến lược có thể kết hợp:

- Physical base backups và WAL archiving cho disaster recovery/PITR.
- pg_dump định kỳ cho logical restore, migration và object-level recovery.
- Backup riêng cho roles/global objects khi cần.
- Backup/manifest của external systems.
- Restore drills và retention độc lập.

Không dùng một loại backup để thay thế mọi nhu cầu.

---

## 19. Những hiểu lầm thường gặp

**1. “pg_dump khóa toàn bộ database.”** Không. Nó dùng MVCC snapshot và table locks phù hợp; DML thông thường vẫn có thể chạy.

**2. “Vì DML vẫn chạy nên dump không dùng lock.”** Sai. pg_dump lấy ACCESS SHARE locks; chúng tương thích với DML nhưng xung đột với ACCESS EXCLUSIVE.

**3. “Mỗi bảng được dump tại thời điểm đọc bảng đó.”** Không. Các query dùng snapshot chung nên phản ánh cùng một trạng thái logic.

**4. “Transaction commit trong lúc dump sẽ xuất hiện ở bảng đọc sau.”** Không nếu commit sau snapshot; dump tiếp tục nhìn trạng thái cũ.

**5. “READ COMMITTED đủ cho nhiều SELECT trong một transaction.”** Không nếu cần cùng snapshot; mỗi statement có thể lấy snapshot mới.

**6. “REPEATABLE READ khóa writer.”** Không. Nó giữ snapshot ổn định; DML vẫn có thể chạy theo MVCC.

**7. “Parallel dump mỗi worker tự nhìn snapshot riêng.”** Không. pg_dump đồng bộ snapshot giữa các workers.

**8. “Tăng jobs luôn làm dump nhanh hơn.”** Không. Storage/network/CPU có thể bão hòa và workload OLTP bị cạnh tranh.

**9. “Dump chạy lâu không ảnh hưởng vacuum.”** Sai. Snapshot cũ có thể ngăn vacuum loại bỏ dead tuples còn cần thiết.

**10. “pg_dump khóa vacuum.”** Không. Vacuum vẫn có thể chạy nhưng bị giới hạn trong việc cleanup tuple versions.

**11. “Dead tuples nhiều chắc chắn do pg_dump.”** Không. Cần đối chiếu transaction age, backend_xmin, write workload và autovacuum.

**12. “ACCESS SHARE chặn INSERT/UPDATE/DELETE.”** Không. Nó tương thích với các DML locks thông thường.

**13. “ACCESS SHARE không thể ảnh hưởng DDL.”** Sai. DDL cần ACCESS EXCLUSIVE có thể phải chờ dump.

**14. “Chỉ cần nhìn thấy file dump là backup thành công.”** Không. Cần exit code, archive inspection, checksum và restore test.

**15. “pg_dump tạo snapshot toàn cluster.”** Không. Nó dump một database; pg_dumpall không tạo một snapshot MVCC xuyên mọi database.

**16. “Sequence nằm trong snapshot như table row.”** Không. nextval/setval không transactional theo MVCC thông thường.

**17. “Dump consistent nghĩa external Kafka/object storage cũng đồng bộ.”** Không. External systems cần coordination riêng.

**18. “Dump từ standby luôn không ảnh hưởng primary.”** Không. Standby read load, recovery conflict và hot_standby_feedback có thể ảnh hưởng replication/primary vacuum.

**19. “hot_standby_feedback chỉ có lợi.”** Không. Nó có thể giảm query cancellation nhưng làm giữ dead tuples và tăng bloat trên primary.

**20. “pg_stat_progress_copy theo dõi pg_dump.”** Không. pg_dump thường đọc bằng SELECT; COPY progress view không phải tracker của logical dump.

**21. “pg_dump snapshot tự giữ mọi WAL segments.”** Không. WAL retention thường do archiving, replication slots và standby requirements.

**22. “Hai file schema-only và data-only từ hai lần dump luôn khớp nhau.”** Không. Chúng có thể lấy hai snapshots khác nhau.

**23. “pg_dumpall là atomic backup xuyên database.”** Không. Global objects và từng database được dump theo các thao tác riêng.

**24. “Một archive đọc được bằng pg_restore --list chắc chắn restore được.”** Không. Phải restore thử và kiểm tra dependencies.

**25. “Backup logical thay thế PITR.”** Không. PITR cần base backup và WAL archive liên tục.

---

## 20. Bài tập thực hành và đáp án

### Bài 1 — Snapshot là gì?

**Câu hỏi:** Snapshot xác định điều gì?

**Đáp án:** Tập transaction/row versions mà query được phép nhìn thấy theo MVCC visibility rules tại một thời điểm logic.

### Bài 2 — Commit sau snapshot

**Câu hỏi:** Transaction commit sau khi pg_dump lấy snapshot có xuất hiện trong dump không?

**Đáp án:** Không. Snapshot không thay đổi khi transaction khác commit.

### Bài 3 — READ COMMITTED

**Câu hỏi:** Hai SELECT trong cùng transaction READ COMMITTED có thể thấy hai trạng thái khác nhau không?

**Đáp án:** Có. Mỗi statement có snapshot riêng.

### Bài 4 — REPEATABLE READ

**Câu hỏi:** Vì sao REPEATABLE READ phù hợp với export nhiều query?

**Đáp án:** Các query trong transaction dùng cùng snapshot ổn định.

### Bài 5 — pg_dump và DML

**Câu hỏi:** INSERT/UPDATE/DELETE có phải dừng trong suốt pg_dump không?

**Đáp án:** Không. MVCC và ACCESS SHARE locks cho phép DML thông thường tiếp tục.

### Bài 6 — ACCESS SHARE

**Câu hỏi:** Lock mode nào xung đột với ACCESS SHARE?

**Đáp án:** ACCESS EXCLUSIVE.

### Bài 7 — DDL

**Câu hỏi:** Vì sao DROP TABLE có thể chờ dump?

**Đáp án:** DROP TABLE cần ACCESS EXCLUSIVE, xung đột với ACCESS SHARE mà pg_dump giữ.

### Bài 8 — Parallel dump

**Yêu cầu:** Viết lệnh dump song song bốn jobs.

```bash
pg_dump --format=directory --jobs=4 --file=appdb.dumpdir --dbname=appdb
```

### Bài 9 — Format

**Câu hỏi:** Format nào hỗ trợ parallel dump bằng pg_dump?

**Đáp án:** Directory format.

### Bài 10 — Synchronized snapshots

**Câu hỏi:** Vì sao workers cần synchronized snapshot?

**Đáp án:** Để mọi worker đọc cùng một trạng thái logic, tránh mỗi phần dump phản ánh một thời điểm khác nhau.

### Bài 11 — Exported snapshot

**Yêu cầu:** Lấy snapshot token.

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;
SELECT pg_export_snapshot();
```

### Bài 12 — Import snapshot

**Yêu cầu:** Import token trong session khác.

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET TRANSACTION SNAPSHOT 'snapshot-token';
```

Token phải được thay bằng giá trị thật và transaction exporter còn mở cho tới khi consumer import xong.

### Bài 13 — Sequence

**Câu hỏi:** nextval() có rollback cùng transaction không?

**Đáp án:** Không. Sequence operations không transactional như row updates.

### Bài 14 — Vacuum

**Câu hỏi:** Vì sao snapshot lâu có thể tăng bloat?

**Đáp án:** Vacuum không thể loại bỏ các dead tuple versions còn có thể được snapshot cũ nhìn thấy.

### Bài 15 — backend_xmin

**Yêu cầu:** Xem backend giữ xmin.

```sql
SELECT pid, application_name, xact_start, backend_xmin
FROM pg_stat_activity
WHERE backend_xmin IS NOT NULL
ORDER BY xact_start;
```

### Bài 16 — Dead tuples

**Yêu cầu:** Xem bảng có nhiều dead tuple estimate.

```sql
SELECT schemaname, relname, n_dead_tup
FROM pg_stat_user_tables
ORDER BY n_dead_tup DESC
LIMIT 10;
```

### Bài 17 — Standby

**Câu hỏi:** Dump từ standby có thể bị cancel vì lý do nào?

**Đáp án:** Recovery conflict khi query lâu cần row versions hoặc relation state mà WAL replay cần xử lý.

### Bài 18 — hot_standby_feedback

**Câu hỏi:** Feedback có tradeoff gì?

**Đáp án:** Có thể giảm query cancellation trên standby nhưng giữ dead tuples lâu hơn trên primary.

### Bài 19 — Multi-database

**Câu hỏi:** pg_dumpall bảo đảm snapshot đồng thời xuyên nhiều database không?

**Đáp án:** Không. Các database được dump qua các thao tác riêng.

### Bài 20 — Monitoring

**Câu hỏi:** Có view pg_stat_progress_pg_dump tiêu chuẩn không?

**Đáp án:** Không có progress view tổng quát riêng cho logical pg_dump; dùng verbose output, pg_stat_activity và OS metrics.

### Bài 21 — Lock timeout

**Yêu cầu:** Giới hạn chờ lock 30 giây.

```bash
pg_dump --lock-wait-timeout=30s --format=custom --file=appdb.dump --dbname=appdb
```

### Bài 22 — Custom archive

**Yêu cầu:** Kiểm tra TOC.

```bash
pg_restore --list appdb.dump
```

### Bài 23 — Restore test

**Yêu cầu:** Restore custom archive vào database test.

```bash
createdb appdb_restore
pg_restore --exit-on-error --dbname=appdb_restore appdb.dump
```

### Bài 24 — PITR

**Câu hỏi:** pg_dump có tự cung cấp point-in-time recovery tới một timestamp bất kỳ không?

**Đáp án:** Không. Cần physical base backup và WAL archive liên tục.

### Bài 25 — Dump bị lỗi

**Câu hỏi:** File .part đã được tạo có được công bố khi pg_dump exit code khác 0 không?

**Đáp án:** Không. Giữ staging để điều tra hoặc cleanup theo quy trình; tạo dump mới và publish chỉ khi thành công.

### Bài 26 — Tác động tải

**Câu hỏi:** Vì sao tăng jobs có thể làm ứng dụng chậm hơn?

**Đáp án:** Nhiều scans cùng lúc cạnh tranh storage I/O, CPU, network và cache.

### Bài 27 — Snapshot ngoài database

**Câu hỏi:** Snapshot pg_dump có bao gồm Kafka message được phát sau commit không?

**Đáp án:** Không. Cần outbox/offset/coordination với hệ thống ngoài.

### Bài 28 — Dump schema/data riêng

**Câu hỏi:** Hai lần dump schema-only và data-only có cùng snapshot không?

**Đáp án:** Không mặc định; mỗi lần có thể bắt đầu transaction snapshot riêng.

### Bài 29 — Application name

**Yêu cầu:** Đặt tên connection dễ nhận biết.

**Đáp án:** Cấu hình libpq connection parameter `application_name`, ví dụ `nightly_pg_dump`, rồi lọc trong pg_stat_activity.

### Bài 30 — Backup validation

**Câu hỏi:** Điều gì xác nhận backup có thể dùng?

**Đáp án:** Restore test thành công và kiểm tra schema, data, sequence, permissions, dependencies cùng application smoke tests.

---

## 21. Checklist trước, trong và sau dump

### Trước dump

1. Xác định database, schema/object scope và mục tiêu backup.
2. Chọn logical dump hay physical backup/PITR.
3. Kiểm tra PostgreSQL server/client version.
4. Chọn plain/custom/directory format.
5. Chọn jobs theo capacity, không theo CPU count đơn thuần.
6. Kiểm tra quyền đọc, extensions, large objects và dependencies.
7. Kiểm tra disk space, network và client destination.
8. Kiểm tra migration/DDL đang chạy.
9. Đặt application_name để nhận diện session.
10. Chọn backup window và lock timeout.

### Trong dump

11. Theo dõi exit status và verbose output.
12. Theo dõi CPU, I/O, network, archive size và filesystem free space.
13. Theo dõi xact_start/backend_xmin và transaction age.
14. Theo dõi dead tuple estimates và autovacuum progress.
15. Theo dõi lock waits và DDL blockers.
16. Nếu dump từ standby, theo dõi recovery conflicts và replay lag.
17. Không tăng jobs khi storage/network đã bão hòa.
18. Không terminate snapshot lâu trước khi đánh giá tác động và kế hoạch chạy lại.

### Sau dump

19. Xác nhận pg_dump exit code bằng 0.
20. Kiểm tra archive TOC hoặc SQL output.
21. Tính checksum và ghi manifest.
22. Publish staging artifact theo quy trình.
23. Restore thử vào database riêng.
24. Kiểm tra schema, constraints, data invariants, sequences và permissions.
25. Chạy application smoke tests.
26. Đo RTO và lưu kết quả restore drill.
27. Xóa staging/dump cũ theo retention policy.
28. Kiểm tra vacuum có cleanup backlog cần theo dõi sau khi snapshot kết thúc.

---

## 22. Tổng kết

Snapshot nhất quán là nền tảng để một bản dump nhiều bảng phản ánh cùng một trạng thái database. PostgreSQL dùng MVCC; `pg_dump` giữ snapshot trong lúc đọc, còn parallel workers dùng synchronized snapshots để không trộn các thời điểm logic khác nhau.

Những điểm cần nhớ:

- Commit sau snapshot không xuất hiện trong dump; row versions mà snapshot cũ cần vẫn có thể được nhìn thấy.
- pg_dump không khóa toàn database. ACCESS SHARE locks cho phép DML thường chạy, nhưng DDL cần ACCESS EXCLUSIVE có thể chờ.
- READ COMMITTED tạo snapshot mới cho mỗi statement; REPEATABLE READ phù hợp cho export nhiều query cần cùng snapshot.
- Parallel dump dùng synchronized snapshots; directory format hỗ trợ parallel dump.
- Exported snapshots có thể phối hợp nhiều sessions/processes, nhưng transaction exporter phải còn mở tới khi consumer import.
- Sequence operations không theo MVCC snapshot như table rows.
- Snapshot lâu có thể giữ dead tuples, làm vacuum cleanup chậm và tăng bloat; theo dõi backend_xmin, transaction age và autovacuum.
- Dump từ standby có thể gặp recovery conflicts; hot_standby_feedback giảm một số cancellation nhưng có thể tăng bloat trên primary.
- Dump tiêu thụ I/O, CPU, network và cache; tăng jobs chỉ có ích khi tài nguyên còn dư.
- pg_dump là logical backup của một database, không phải snapshot xuyên cluster hoặc backup PITR.
- Chỉ publish artifact sau exit code thành công, archive inspection, checksum và restore test.

**Câu hỏi tự kiểm tra:** Một dump kéo dài hai giờ trong khi ứng dụng liên tục UPDATE rows. Vì sao file vẫn có thể nhất quán, tại sao autovacuum có thể chưa dọn được một số dead tuples, và vì sao một lệnh ALTER TABLE có thể phải chờ? Nếu giải thích được snapshot MVCC, xmin horizon và ACCESS SHARE/ACCESS EXCLUSIVE, bạn đã nắm phần cốt lõi của tác động dump đang chạy.

### Tài liệu PostgreSQL chính thức

- [pg_dump — extract a PostgreSQL database](https://www.postgresql.org/docs/current/app-pgdump.html).
- [pg_dumpall — extract a PostgreSQL cluster](https://www.postgresql.org/docs/current/app-pg-dumpall.html).
- [Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html).
- [MVCC Introduction](https://www.postgresql.org/docs/current/mvcc-intro.html).
- [System Information Functions — Snapshot Synchronization](https://www.postgresql.org/docs/current/functions-info.html).
- [Explicit Locking — Table-level Lock Modes](https://www.postgresql.org/docs/current/explicit-locking.html).
- [Routine Vacuuming](https://www.postgresql.org/docs/current/routine-vacuuming.html).
- [Monitoring Statistics — pg_stat_activity and pg_stat_user_tables](https://www.postgresql.org/docs/current/monitoring-stats.html).
- [Warm Standby — Hot Standby and Recovery Conflicts](https://www.postgresql.org/docs/current/hot-standby.html).
- [pg_restore](https://www.postgresql.org/docs/current/app-pgrestore.html).
- [Backup and Restore](https://www.postgresql.org/docs/current/backup.html).
