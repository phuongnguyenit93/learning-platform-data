# ALTER TABLE, mức khóa và thao tác cần viết lại bảng trong PostgreSQL

`ALTER TABLE` là một trong những lệnh DDL được dùng thường xuyên nhất để thay đổi schema PostgreSQL. Nó có thể thêm hoặc xóa columns, đổi data types, đặt defaults, thêm constraints, đổi ownership, di chuyển tablespace và thay đổi cấu trúc partition. Những thay đổi này có chi phí rất khác nhau: một số chỉ cập nhật catalog metadata, một số phải quét toàn bộ bảng, một số phải tạo lại index, và một số phải viết lại toàn bộ dữ liệu vật lý của table.

Khi chạy trên production, câu hỏi quan trọng không chỉ là câu lệnh có đúng cú pháp hay không. Cần biết **lệnh lấy lock nào, lock được giữ bao lâu, có chặn reads/writes không, có quét hoặc rewrite table không, cần thêm bao nhiêu disk/WAL, ảnh hưởng replica ra sao và có thể triển khai theo từng giai đoạn hay không**.

Bài học thuộc chương **Thay đổi lược đồ**, tập trung vào:

- Cấu trúc và các dạng phổ biến của `ALTER TABLE`.
- PostgreSQL table lock modes và mức khóa của từng nhóm thao tác.
- Khác biệt giữa metadata-only, table scan, index build và table rewrite.
- Tác động của defaults, data type changes, constraints và column removal.
- Cách thêm constraints an toàn bằng `NOT VALID` và `VALIDATE CONSTRAINT`.
- Cách tạo index concurrent và gắn index thành primary/unique constraint.
- Partition attach/detach và tác động lên parent/child tables.
- Lock queue, blocking sessions, timeouts và transaction duration.
- Disk space, WAL, replication lag và các giới hạn MVCC khi rewrite.
- Expand-contract migrations, backfill theo batch và rollout có thể rollback.
- Monitoring, migration runbook và bài thực hành.

> **Nguyên tắc vận hành:** một thao tác metadata-only vẫn có thể cần lock mạnh. “Không rewrite table” không đồng nghĩa “không gây blocking”. Ngược lại, một thao tác scan table chưa chắc phải rewrite dữ liệu. Hãy tách riêng lock behavior, scan cost, rewrite cost và transaction duration khi đánh giá một migration.

## 1. ALTER TABLE hoạt động như thế nào?

`ALTER TABLE` thay đổi định nghĩa của một table hoặc một partitioned table. PostgreSQL lưu định nghĩa schema trong system catalogs, nhưng table data và indexes nằm trong các storage relations riêng.

Một câu lệnh có thể làm một hoặc nhiều việc:

1. Xác thực object, quyền và tính hợp lệ của thay đổi.
2. Lấy lock trên table và có thể trên các relations liên quan.
3. Cập nhật catalog metadata.
4. Quét dữ liệu hiện tại để xác minh constraint hoặc chuyển đổi values.
5. Tạo, xóa hoặc rebuild indexes.
6. Viết lại table storage nếu layout hoặc data representation cần thay đổi.
7. Cập nhật dependencies và các metadata liên quan.
8. Giữ locks cho đến khi transaction kết thúc.

### 1.1. Cú pháp cơ bản

```sql
ALTER TABLE [ ONLY ] table_name
    action [, ... ];
```

`table_name` nên được schema-qualify trong migration:

```sql
ALTER TABLE app.orders
    ADD COLUMN source_code text;
```

Các actions có thể được kết hợp trong một lệnh. Tuy nhiên, gộp nhiều thay đổi không tự động làm cho migration nhanh hơn hoặc an toàn hơn. Một lệnh chứa nhiều subcommands có thể phải lấy lock mạnh nhất cần thiết cho bất kỳ subcommand nào và thực hiện nhiều công việc trong cùng một transaction.

### 1.2. ONLY và inheritance/partitioning

PostgreSQL hỗ trợ table inheritance và declarative partitioning. Với một parent table, thao tác ALTER TABLE thường áp dụng đệ quy tới descendants khi cú pháp cho phép.

- `ALTER TABLE parent ...` thường thay đổi parent và các child tables/partitions liên quan.
- `ALTER TABLE ONLY parent ...` giới hạn thay đổi vào chính parent.
- Một số actions không thể áp dụng riêng parent nếu sẽ làm schema không tương thích với children.
- Một số thao tác có restrictions riêng trên partitioned tables.

Trước khi chạy DDL trên parent lớn, hãy xác định số partitions, trạng thái child tables và lock behavior trên toàn hierarchy. Một lệnh nhìn như chỉ tác động một relation có thể cần locks trên nhiều relations.

### 1.3. Một lệnh ALTER TABLE có thể chứa nhiều actions

Ví dụ:

```sql
ALTER TABLE app.orders
    ADD COLUMN source_code text,
    ALTER COLUMN status SET DEFAULT 'pending';
```

Cả hai actions có thể không cần rewrite table, nhưng lock level của statement vẫn phải đáp ứng yêu cầu của các actions. Nếu một action cần `ACCESS EXCLUSIVE`, đừng giả định action còn lại làm lock tổng thể nhẹ hơn.

### 1.4. DDL thường transactional

Nhiều dạng `ALTER TABLE` có thể chạy trong transaction và rollback nếu transaction thất bại. Tuy nhiên, lock được giữ đến COMMIT/ROLLBACK. Một migration chạy trong transaction dài có thể tiếp tục giữ lock sau khi câu lệnh DDL đã hoàn tất.

Một số lệnh liên quan, đặc biệt `CREATE INDEX CONCURRENTLY` và `DROP INDEX CONCURRENTLY`, không được chạy trong transaction block. Migration tool cần hỗ trợ migration không transaction cho các thao tác đó.

## 2. Table lock modes

PostgreSQL dùng table-level locks để điều phối các thao tác đồng thời. Lock mode quyết định một thao tác có thể chạy cùng reads, writes hoặc DDL khác hay không.

### 2.1. Các lock modes chính

| Lock mode | Ý nghĩa khái quát |
| --- | --- |
| `ACCESS SHARE` | Lock nhẹ nhất; thường được SELECT lấy |
| `ROW SHARE` | Thường dùng bởi SELECT ... FOR UPDATE/SHARE |
| `ROW EXCLUSIVE` | Thường được INSERT, UPDATE, DELETE và MERGE lấy |
| `SHARE UPDATE EXCLUSIVE` | Dùng bởi một số maintenance/DDL operations; tương thích với ROW EXCLUSIVE |
| `SHARE` | Cho phép reads nhưng chặn writers thông thường |
| `SHARE ROW EXCLUSIVE` | Lock mạnh, tự-conflicting và chặn writers |
| `EXCLUSIVE` | Chặn nhiều hoạt động đồng thời, vẫn cho ACCESS SHARE |
| `ACCESS EXCLUSIVE` | Mạnh nhất; xung đột với mọi table lock mode khác |

Tên lock có chữ “ROW” không có nghĩa nó là row-level lock. Đây là các **table-level lock modes**. PostgreSQL còn có row-level locks riêng cho từng tuple.

### 2.2. ACCESS SHARE

SELECT thông thường lấy `ACCESS SHARE`. Lock này cho phép nhiều readers và writers hoạt động đồng thời, nhưng bị chặn bởi `ACCESS EXCLUSIVE`.

Vì vậy, một ALTER TABLE lấy ACCESS EXCLUSIVE có thể chờ các SELECT đang chạy và cũng có thể khiến SELECT mới phải xếp hàng phía sau pending DDL.

### 2.3. ROW EXCLUSIVE

Các câu lệnh sửa dữ liệu như INSERT, UPDATE, DELETE và MERGE thường lấy `ROW EXCLUSIVE` trên table được sửa.

`ROW EXCLUSIVE` tương thích với nhiều locks khác, gồm `ACCESS SHARE` và `SHARE UPDATE EXCLUSIVE`, nhưng không tương thích với `SHARE`, `SHARE ROW EXCLUSIVE`, `EXCLUSIVE` và `ACCESS EXCLUSIVE`.

### 2.4. SHARE UPDATE EXCLUSIVE

`SHARE UPDATE EXCLUSIVE` được dùng bởi một số hoạt động như VACUUM thông thường, ANALYZE, CREATE INDEX CONCURRENTLY và VALIDATE CONSTRAINT. Nó cho phép ordinary DML tiếp tục, nhưng không cho phép một số DDL/maintenance operations xung đột chạy đồng thời.

Lock này tự-conflicting: hai sessions cùng yêu cầu SHARE UPDATE EXCLUSIVE trên cùng table có thể phải chờ nhau.

### 2.5. SHARE ROW EXCLUSIVE

`SHARE ROW EXCLUSIVE` chặn ordinary writers và tự-conflicting. Một ví dụ quan trọng là thao tác ADD FOREIGN KEY, có thể lấy lock này trên table tham chiếu và table được tham chiếu.

Điều này có nghĩa thêm foreign key có thể làm writes trên hai tables phải chờ trong giai đoạn lock, dù việc kiểm tra dữ liệu cũ có thể được tách sang một bước VALIDATE CONSTRAINT.

### 2.6. ACCESS EXCLUSIVE

`ACCESS EXCLUSIVE` là lock mạnh nhất. Nó xung đột với mọi lock mode khác, bao gồm ACCESS SHARE của SELECT.

Nhiều dạng ALTER TABLE mặc định lấy ACCESS EXCLUSIVE. Vì vậy, một thay đổi không rewrite table vẫn có thể làm SELECT/INSERT/UPDATE/DELETE chờ lock.

### 2.7. Lock được giữ đến cuối transaction

PostgreSQL giữ table locks đến khi transaction kết thúc. Ví dụ:

```sql
BEGIN;

ALTER TABLE app.orders
    ADD COLUMN source_code text;

-- Các câu lệnh khác chạy ở đây.

COMMIT;
```

Lock từ ALTER TABLE có thể vẫn tồn tại trong thời gian các câu lệnh sau đó chạy. Nếu migration tool mở transaction rồi thực hiện nhiều bước hoặc chờ external process trước COMMIT, thời gian blocking có thể dài hơn thời gian DDL thực tế.

### 2.8. Một số lock levels thường gặp

Bảng dưới đây là hướng dẫn thực hành cho các forms phổ biến; lock có thể khác theo subcommand, version, partition hierarchy và object liên quan. Luôn kiểm tra documentation của major version đang chạy.

| Thao tác | Lock thường dùng trên table |
| --- | --- |
| Hầu hết ALTER TABLE forms | ACCESS EXCLUSIVE |
| ADD FOREIGN KEY | SHARE ROW EXCLUSIVE trên table liên quan |
| VALIDATE CONSTRAINT | SHARE UPDATE EXCLUSIVE |
| SET STATISTICS | SHARE UPDATE EXCLUSIVE |
| SET/RESET một số table storage parameters | SHARE UPDATE EXCLUSIVE |
| ATTACH PARTITION | SHARE UPDATE EXCLUSIVE trên parent; lock mạnh hơn trên table được attach |
| DETACH PARTITION thông thường | ACCESS EXCLUSIVE trên parent và partition |
| DETACH PARTITION CONCURRENTLY | SHARE UPDATE EXCLUSIVE trên parent trong các version hỗ trợ |
| CREATE INDEX CONCURRENTLY | SHARE UPDATE EXCLUSIVE |
| VACUUM thông thường | SHARE UPDATE EXCLUSIVE |

Đây không phải danh sách exhaustive. Ví dụ CREATE INDEX thường và nhiều dạng ALTER TABLE khác có lock behavior khác với concurrent index build.

## 3. Lock compatibility và tác động lên traffic

Lock mode chỉ có ý nghĩa khi đặt cạnh các hoạt động đang chạy.

### 3.1. Các tương tác cần nhớ

| Hoạt động đang chạy | ACCESS EXCLUSIVE DDL | SHARE UPDATE EXCLUSIVE DDL |
| --- | --- | --- |
| SELECT thông thường | Bị chặn | Có thể tiếp tục |
| INSERT/UPDATE/DELETE | Bị chặn | Thường có thể tiếp tục |
| VACUUM thông thường | Bị chặn | Có thể xung đột với thao tác cùng mode |
| CREATE INDEX CONCURRENTLY | Bị chặn | Xung đột nếu cùng table |
| Một số DDL khác | Bị chặn | Tùy lock mode của DDL |
| Lock ACCESS EXCLUSIVE khác | Bị chặn | Bị chặn |

Bảng này minh họa các trường hợp thường gặp, không thay thế lock matrix chính thức. Một câu lệnh có thể chạm nhiều tables nên cần xem từng relation.

### 3.2. Metadata-only vẫn có thể block

Ví dụ thêm một nullable column không default thường không rewrite table. Nhưng nó vẫn cần lock mạnh. Nếu table đang có transaction giữ lock lâu, ALTER TABLE có thể chờ.

Đây là lý do cần phân biệt:

- **Rewrite cost:** có tạo lại physical table data hay không.
- **Scan cost:** có đọc rows hiện tại để kiểm tra hay không.
- **Lock cost:** cần lock nào và có thể phải chờ ai.
- **Transaction cost:** lock giữ trong bao lâu.
- **Resource cost:** CPU, I/O, WAL và disk space.

### 3.3. Lock queue và blocking convoy

Giả sử một transaction dài đang giữ ACCESS SHARE trên table. Một ALTER TABLE yêu cầu ACCESS EXCLUSIVE xếp hàng chờ. Các SELECT mới đến sau có thể cũng phải chờ phía sau request lock mạnh đang chờ, tùy lock queue và conflict rules.

Kết quả có thể là:

1. Một query cũ giữ lock lâu.
2. ALTER TABLE chờ ACCESS EXCLUSIVE.
3. Các requests mới xếp hàng.
4. Application pool bị chiếm bởi requests đang chờ.
5. Latency tăng trên cả endpoint không trực tiếp liên quan migration.

Một DDL chờ lock có thể tạo impact lớn trước khi nó thực sự thay đổi schema.

### 3.4. DDL nên có lock timeout

Dùng timeout ngắn để migration fail fast nếu không lấy được lock trong cửa sổ cho phép:

```sql
BEGIN;
SET LOCAL lock_timeout = '2s';
SET LOCAL statement_timeout = '5min';

ALTER TABLE app.orders
    ADD COLUMN source_code text;

COMMIT;
```

`lock_timeout` giới hạn thời gian chờ từng lần lấy lock. `statement_timeout` giới hạn tổng thời gian statement. Các giá trị ví dụ cần điều chỉnh theo SLO và deployment policy.

Nếu lock timeout xảy ra, transaction hiện tại sẽ ở trạng thái aborted cho đến ROLLBACK. Migration runner cần xử lý lỗi và retry toàn transaction một cách có kiểm soát.

### 3.5. Không retry liên tục không backoff

Nếu DDL cứ retry mỗi vài milliseconds, nó có thể liên tục tạo lock pressure. Dùng retry có giới hạn, backoff và jitter; trước mỗi lần thử, kiểm tra blocker và tình trạng workload.

## 4. Metadata-only changes

Metadata-only là các thay đổi chủ yếu cập nhật catalog, không cần rewrite toàn bộ table data. Chúng thường nhanh hơn trên bảng lớn, nhưng lock acquisition vẫn quan trọng.

### 4.1. ADD COLUMN không có default

Ví dụ:

```sql
ALTER TABLE app.orders
    ADD COLUMN source_code text;
```

Trên các PostgreSQL versions hiện đại, thêm nullable column không default thường chỉ cập nhật metadata. PostgreSQL không phải ghi lại mỗi row để lưu NULL cho column mới.

Đặc điểm:

- Không cần scan toàn bộ table để tính giá trị.
- Không rewrite toàn bộ table data.
- Storage cho giá trị mới được ghi khi rows được insert/update sau đó.
- Vẫn cần lock của ALTER TABLE.
- Schema change có thể ảnh hưởng application code và ORM mapping.

Đây thường là cách thêm column ít tốn kém nhất, nhưng cần rollout application tương thích với schema mới.

### 4.2. ADD COLUMN với default hằng số

Ví dụ:

```sql
ALTER TABLE app.orders
    ADD COLUMN source_code text DEFAULT 'legacy';
```

Từ PostgreSQL 11 trở đi, một default expression không volatile có thể được đánh giá một lần khi ALTER TABLE và lưu dưới dạng missing value metadata cho rows cũ. Trong trường hợp này, PostgreSQL không cần rewrite toàn bộ table chỉ để điền default vào mọi row.

Điều này có thể làm thao tác nhanh hơn rất nhiều trên table lớn.

Cần nhớ:

- Default được dùng cho các rows mới.
- Rows cũ đọc column như giá trị đã lưu trong metadata.
- Khi row được rewrite về sau, giá trị được materialize theo storage behavior.
- Thao tác vẫn cần lock.
- Trước PostgreSQL 11, ADD COLUMN với non-NULL default thường rewrite table.

### 4.3. ADD COLUMN với volatile default

Ví dụ:

```sql
ALTER TABLE app.orders
    ADD COLUMN created_token uuid DEFAULT gen_random_uuid();
```

Một volatile expression có thể trả giá trị khác nhau cho từng row. PostgreSQL phải tính giá trị cho các rows hiện có, vì vậy table rewrite có thể cần thiết.

Các function như `random()` hoặc `clock_timestamp()` là ví dụ về volatile expressions. Cần kiểm tra volatility classification của function được dùng trong default.

### 4.4. SET DEFAULT và DROP DEFAULT

```sql
ALTER TABLE app.orders
    ALTER COLUMN source_code SET DEFAULT 'unknown';

ALTER TABLE app.orders
    ALTER COLUMN source_code DROP DEFAULT;
```

Thay đổi default không cập nhật giá trị của rows đã tồn tại và không yêu cầu rewrite table. Nó thay đổi behavior của INSERT hoặc UPDATE bỏ qua column theo semantics của statement.

Đừng nhầm SET DEFAULT với UPDATE toàn bộ rows để gán giá trị mặc định cho dữ liệu cũ.

### 4.5. RENAME COLUMN và RENAME TABLE

```sql
ALTER TABLE app.orders
    RENAME COLUMN source_code TO origin_code;

ALTER TABLE app.orders
    RENAME TO customer_orders;
```

Rename chủ yếu cập nhật catalog metadata, không rewrite data. Tuy nhiên, lock vẫn cần được lấy và ứng dụng có thể hỏng ngay khi deploy nếu code cũ còn tham chiếu tên trước đó.

Rename trong production nên theo expand-contract: thêm cấu trúc mới, chuyển callers, sau đó mới bỏ tên cũ khi đã xác nhận.

### 4.6. DROP COLUMN

```sql
ALTER TABLE app.orders
    DROP COLUMN legacy_code RESTRICT;
```

DROP COLUMN thường không rewrite table ngay. PostgreSQL đánh dấu attribute là dropped trong catalog và không còn hiển thị column đó trong query thông thường.

Tuy nhiên:

- Physical tuple data cũ không được compact ngay.
- Dung lượng file table có thể không giảm sau DROP COLUMN.
- Space có thể chỉ được tái sử dụng khi rows được rewrite/update hoặc table được rewrite bằng thao tác khác.
- Các dependencies có thể khiến DROP RESTRICT thất bại.
- DROP CASCADE có thể xóa objects phụ thuộc.

Không dùng DROP COLUMN với kỳ vọng disk usage giảm ngay lập tức. Nếu cần reclaim space, phải đánh giá riêng phương án rewrite/repack và downtime/lock cost.

### 4.7. ALTER COLUMN SET STATISTICS

Ví dụ:

```sql
ALTER TABLE app.orders
    ALTER COLUMN customer_id SET STATISTICS 500;
```

Thay đổi statistics target điều khiển mức chi tiết planner thu thập cho column. Nó không rewrite table, nhưng có thể yêu cầu ANALYZE để statistics mới có hiệu lực. Lock thường nhẹ hơn các ALTER TABLE forms mặc định trên các version hiện hành.

Statistics target cao có thể tăng thời gian ANALYZE và kích thước statistics. Chỉ tăng cho columns có query planning issue rõ ràng.

### 4.8. Storage parameters

Ví dụ:

```sql
ALTER TABLE app.orders
    SET (fillfactor = 85);

ALTER TABLE app.orders
    RESET (fillfactor);
```

Storage parameter thường ảnh hưởng cách các rows/index pages được tạo hoặc duy trì trong tương lai. Thay đổi metadata không tự động rewrite toàn bộ pages hiện có để áp dụng setting mới. Muốn thay đổi layout của dữ liệu cũ có thể cần thao tác rewrite riêng.

## 5. Các thao tác phải quét table

Một table scan đọc rows hiện tại để kiểm tra điều kiện. Scan có thể tốn thời gian trên table lớn, nhưng không nhất thiết tạo physical copy mới.

### 5.1. ADD CHECK constraint

Ví dụ:

```sql
ALTER TABLE app.orders
    ADD CONSTRAINT orders_amount_nonnegative
    CHECK (total_amount >= 0);
```

Nếu thêm constraint ở trạng thái validated mặc định, PostgreSQL phải kiểm tra rows hiện có để xác nhận mọi row thỏa điều kiện. Trên table lớn, scan có thể kéo dài.

### 5.2. ADD CHECK NOT VALID

Có thể tách công việc:

```sql
ALTER TABLE app.orders
    ADD CONSTRAINT orders_amount_nonnegative
    CHECK (total_amount >= 0)
    NOT VALID;
```

`NOT VALID` bỏ qua scan xác minh toàn bộ rows cũ tại thời điểm ADD. Constraint vẫn được áp dụng cho các rows mới hoặc rows được insert/update theo semantics của constraint. Dữ liệu cũ chưa được xác minh.

Sau đó:

```sql
ALTER TABLE app.orders
    VALIDATE CONSTRAINT orders_amount_nonnegative;
```

VALIDATE CONSTRAINT scan dữ liệu hiện tại dưới lock nhẹ hơn ACCESS EXCLUSIVE, thường là SHARE UPDATE EXCLUSIVE. Ordinary DML có thể tiếp tục trong quá trình validation, nhưng vẫn cần theo dõi I/O, CPU và contention.

### 5.3. SET NOT NULL

Ví dụ:

```sql
ALTER TABLE app.orders
    ALTER COLUMN customer_id SET NOT NULL;
```

PostgreSQL phải xác nhận không có NULL trong column. Nếu không có bằng chứng constraint hợp lệ, thao tác có thể scan table.

Có thể dùng CHECK constraint làm bước chuẩn bị:

```sql
ALTER TABLE app.orders
    ADD CONSTRAINT orders_customer_id_not_null_check
    CHECK (customer_id IS NOT NULL)
    NOT VALID;

ALTER TABLE app.orders
    VALIDATE CONSTRAINT orders_customer_id_not_null_check;

ALTER TABLE app.orders
    ALTER COLUMN customer_id SET NOT NULL;

ALTER TABLE app.orders
    DROP CONSTRAINT orders_customer_id_not_null_check;
```

Khi PostgreSQL nhận ra một CHECK constraint đã validated chứng minh column không có NULL, nó có thể bỏ qua full scan khi đặt NOT NULL. Kiểm tra behavior trên đúng major version và giữ các bước trong migration được kiểm soát.

### 5.4. ADD FOREIGN KEY

Ví dụ:

```sql
ALTER TABLE app.order_items
    ADD CONSTRAINT order_items_order_fk
    FOREIGN KEY (order_id)
    REFERENCES app.orders(id);
```

Foreign key cần kiểm tra rows hiện có trong referencing table và đảm bảo các referenced keys hợp lệ. Thao tác lấy SHARE ROW EXCLUSIVE locks trên các tables liên quan theo behavior của PostgreSQL.

### 5.5. Foreign key NOT VALID

```sql
ALTER TABLE app.order_items
    ADD CONSTRAINT order_items_order_fk
    FOREIGN KEY (order_id)
    REFERENCES app.orders(id)
    NOT VALID;
```

Sau đó validate:

```sql
ALTER TABLE app.order_items
    VALIDATE CONSTRAINT order_items_order_fk;
```

Cách này tách lock/setup phase khỏi scan dữ liệu cũ. Constraint vẫn được thực thi cho dữ liệu mới theo semantics của foreign key. Cần bảo đảm application không tiếp tục tạo orphan rows trong thời gian rollout.

### 5.6. ADD NOT NULL bằng CHECK NOT VALID

PostgreSQL không có cùng cú pháp `NOT VALID` cho một NOT NULL constraint trực tiếp. Pattern CHECK constraint có thể giúp triển khai an toàn hơn:

1. Thêm CHECK (column IS NOT NULL) NOT VALID.
2. Deploy code bảo đảm mọi writes mới có value.
3. Backfill các NULL hiện có theo batches.
4. VALIDATE CONSTRAINT.
5. ALTER COLUMN SET NOT NULL.
6. DROP CHECK constraint phụ trợ.

Thứ tự có thể cần điều chỉnh theo cách ứng dụng ghi dữ liệu và transaction model. Không bỏ qua bước xử lý rows cũ.

## 6. Các thao tác phải rewrite table

Table rewrite tạo physical storage mới cho table hoặc chuyển đổi representation của rows. Đây thường là nhóm operation có chi phí lớn nhất trên bảng lớn.

### 6.1. ALTER COLUMN TYPE

Ví dụ:

```sql
ALTER TABLE app.orders
    ALTER COLUMN external_id TYPE bigint
    USING external_id::bigint;
```

Đổi data type thường phải rewrite table nếu representation của old/new types không binary-coercible. Expression USING được đánh giá cho từng row để tạo giá trị mới.

Tác động có thể gồm:

- Đọc toàn bộ table.
- Tính expression cho mỗi row.
- Ghi lại table storage.
- Rebuild indexes liên quan khi cần.
- Sinh WAL và replication traffic.
- Cần disk space cho old/new storage cùng tồn tại trong quá trình rewrite.
- Giữ lock mạnh trong thời gian thao tác.

### 6.2. Khi nào TYPE change có thể tránh rewrite?

Nếu old type và new type binary-coercible và không cần thay đổi physical representation, PostgreSQL có thể chỉ cập nhật metadata. Ví dụ một số chuyển đổi giữa compatible types có thể không cần rewrite.

Không suy luận chỉ từ việc hai types có thể cast qua lại. Cast compatibility không đồng nghĩa binary coercibility. Kiểm tra tài liệu type conversion và thử trên bản sao dữ liệu có kích thước tương đương.

### 6.3. USING expression

`USING` cho phép chuyển đổi dữ liệu:

```sql
ALTER TABLE app.events
    ALTER COLUMN event_time TYPE timestamptz
    USING event_time AT TIME ZONE 'UTC';
```

Expression phải có ý nghĩa với mọi row. Một row không chuyển đổi được có thể làm toàn bộ ALTER TABLE thất bại. Hãy preflight bằng SELECT expression trên dữ liệu, tìm invalid values và kiểm tra timezone semantics trước khi chạy DDL.

`USING` không tự động chuyển đổi column default expression. Nếu default cũ không thể cast sang type mới, có thể cần DROP DEFAULT trước, đổi type, sau đó SET DEFAULT mới.

### 6.4. SET LOGGED và SET UNLOGGED

```sql
ALTER TABLE app.stage_data SET UNLOGGED;
ALTER TABLE app.stage_data SET LOGGED;
```

Thay đổi persistence mode có thể yêu cầu rewrite table. UNLOGGED tables không được bảo vệ bởi WAL theo cách logged tables được bảo vệ và sẽ bị truncate sau crash/recovery theo semantics của PostgreSQL. Không dùng UNLOGGED cho dữ liệu cần durability/replication như bảng nghiệp vụ chính.

### 6.5. SET TABLESPACE

```sql
ALTER TABLE app.orders
    SET TABLESPACE fast_storage;
```

Chuyển table sang tablespace khác cần copy physical data và có thể di chuyển indexes liên quan theo semantics của command. Cần disk capacity ở destination, I/O bandwidth và thời gian giữ lock. Tablespace không phải cơ chế thay thế partitioning hoặc workload isolation.

### 6.6. SET ACCESS METHOD

Trên PostgreSQL versions hỗ trợ:

```sql
ALTER TABLE app.events
    SET ACCESS METHOD heap;
```

Đổi table access method yêu cầu rewrite storage. Đây là thao tác cần đánh giá kỹ về compatibility, extension support, index methods và operational impact.

### 6.7. CLUSTER và VACUUM FULL

Đây không phải ALTER TABLE forms thông thường, nhưng cũng thuộc nhóm thao tác rewrite:

- `CLUSTER` sắp xếp lại table theo index được chọn và viết lại table.
- `VACUUM FULL` tạo bản compacted copy và yêu cầu ACCESS EXCLUSIVE lock.
- Một số repacking tools dùng shadow table hoặc swap strategy để giảm downtime nhưng vẫn cần disk, WAL và lock phases.

Không chạy các thao tác này chỉ vì table size lớn. Xác định bloat, free space reuse, workload và maintenance window trước.

### 6.8. Rewrite không phải chỉ là “UPDATE tất cả rows”

Rewrite thay đổi physical relation storage. Nó có thể tạo một relfilenode mới và cập nhật catalog references. Một full-table UPDATE cũng tạo row versions mới nhưng có semantics, WAL, vacuum và lock behavior khác. Đừng coi hai loại operation là tương đương.

## 7. Ước tính chi phí table rewrite

Trước khi đổi type hoặc chuyển tablespace, cần tính tài nguyên.

### 7.1. Disk space

Giả sử:

- Table hiện tại 80 GiB.
- Indexes 35 GiB.
- Rewrite cần tạo table mới.
- Indexes cần rebuild.

Trong quá trình thao tác, old và new files có thể cùng tồn tại. Peak disk demand có thể cao hơn tổng dung lượng cuối cùng vì cần temporary headroom, WAL và các hoạt động concurrent.

Một envelope thận trọng:

```text
peak_free_space_needed ≈
    new_table_copy
  + rebuilt_indexes
  + WAL_growth
  + temporary_working_space
  + safety_headroom
```

Đây là mô hình ước lượng, không phải công thức cố định. Đo trên clone có data volume và index layout tương tự.

### 7.2. WAL generation

Logged table rewrite tạo WAL. WAL có thể làm tăng:

- pg_wal disk usage.
- Archive volume.
- Replication traffic.
- Replica replay lag.
- Backup/archive storage cost.

Nếu replica không theo kịp, query trên replica có thể thấy dữ liệu cũ trong một thời gian dài.

### 7.3. CPU và I/O

Rewrite có thể đọc toàn bộ old table, tính expressions, ghi new table và rebuild indexes. Nó cạnh tranh với OLTP workload trên cùng CPU, storage và memory.

### 7.4. Replica impact

Theo dõi:

- WAL bytes generated.
- Replication lag theo time/bytes.
- Replica replay rate.
- Disk usage trên primary và replicas.
- Query latency trên replicas.
- Replication slot retained WAL.

Một replication slot giữ WAL chưa được consumer xác nhận; nếu replica/consumer lag lâu, primary có thể giữ nhiều WAL và disk usage tăng.

### 7.5. Backup và archive impact

WAL archive và base backup có thể tăng kích thước sau rewrite. Nếu dùng incremental backup hoặc storage snapshots, đánh giá mức độ thay đổi blocks và thời gian backup.

### 7.6. Lock duration là một phần chi phí

Nếu operation giữ ACCESS EXCLUSIVE trong suốt rewrite, application traffic có thể bị block. Với các thay đổi lớn, cân nhắc expand-contract hoặc shadow-table migration để chuyển data ngoài cửa sổ lock dài, sau đó swap trong một cửa sổ ngắn được kiểm soát.

## 8. MVCC và table rewrite

PostgreSQL dùng MVCC để các transactions nhìn thấy snapshot nhất quán. Một số rewrite operations có lưu ý quan trọng: table rewrite không MVCC-safe đối với transactions đang giữ snapshot cũ.

### 8.1. Snapshot cũ

Khi table được rewrite, physical storage mới có thể không chứa row versions theo visibility rules của snapshot được tạo trước rewrite. Một transaction dài đã lấy snapshot trước DDL có thể quan sát table như rỗng sau khi rewrite theo behavior được tài liệu hóa.

Điều này đặc biệt quan trọng với transactions chạy lâu, repeatable read/serializable sessions hoặc application workflows giữ transaction mở trong lúc migration diễn ra.

### 8.2. Giảm rủi ro

- Tránh table rewrite khi có long-running transactions.
- Kiểm tra transaction age trước migration.
- Dùng lock_timeout để fail fast khi còn blockers.
- Chọn maintenance window có workload phù hợp.
- Thông báo cho ứng dụng về transaction boundaries.
- Dùng staged migration nếu cần tránh rewrite trực tiếp.

### 8.3. Tìm long-running transactions

```sql
SELECT
    pid,
    usename,
    datname,
    application_name,
    xact_start,
    now() - xact_start AS transaction_age,
    state,
    wait_event_type,
    wait_event,
    left(query, 300) AS query_sample
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start;
```

Không terminate transaction chỉ vì nó lâu. Xác định owner, business operation và tác động rollback trước khi xử lý.

## 9. ADD UNIQUE/PRIMARY KEY an toàn hơn

Unique và primary key constraints thường cần unique index. Tạo index trực tiếp trong ADD CONSTRAINT có thể scan table và giữ lock mạnh.

### 9.1. Thêm constraint trực tiếp

```sql
ALTER TABLE app.customers
    ADD CONSTRAINT customers_email_key
    UNIQUE (email);
```

PostgreSQL tạo unique index cần thiết và xác minh dữ liệu. Nếu table lớn, thời gian lock có thể ảnh hưởng writes/reads.

### 9.2. Tạo unique index concurrently

Có thể tạo index riêng:

```sql
CREATE UNIQUE INDEX CONCURRENTLY customers_email_uidx
    ON app.customers (email);
```

Concurrent build cho phép ordinary INSERT/UPDATE/DELETE tiếp tục trong phần lớn quá trình build, nhưng:

- Cần nhiều scans và các phases chờ transactions.
- Tốn CPU, I/O và disk.
- Có thể kéo dài khi transactions cũ hoặc snapshots giữ lâu.
- Không được chạy trong transaction block.
- Có thể thất bại và để lại invalid index cần xử lý.

### 9.3. Gắn index thành constraint

Sau khi index valid và đáp ứng điều kiện, có thể gắn thành unique constraint:

```sql
ALTER TABLE app.customers
    ADD CONSTRAINT customers_email_key
    UNIQUE USING INDEX customers_email_uidx;
```

Lệnh attach thường chỉ cập nhật metadata và lấy lock cần thiết trong thời gian ngắn hơn build index. Index phải đáp ứng yêu cầu của PostgreSQL: phù hợp unique constraint, không phải partial/expression index và có index method/order phù hợp. Nếu thêm PRIMARY KEY, các columns phải được xác nhận NOT NULL.

### 9.4. Primary key và NOT NULL

Unique index cho phép nhiều NULL theo semantics của unique constraint. Primary key yêu cầu NOT NULL. Nếu column hiện nullable, phải xử lý NULL và đặt NOT NULL trước hoặc trong quá trình tạo primary key.

Có thể dùng CHECK NOT VALID + VALIDATE + SET NOT NULL để tách scan khỏi bước lock mạnh, sau đó tạo unique index concurrently và attach.

### 9.5. Concurrent build thất bại

Nếu CREATE INDEX CONCURRENTLY thất bại, có thể còn index với `indisvalid = false`. Index invalid không được planner dùng bình thường nhưng vẫn có thể tạo write overhead tùy trạng thái.

Kiểm tra:

```sql
SELECT
    n.nspname AS schema_name,
    t.relname AS table_name,
    i.relname AS index_name,
    x.indisvalid,
    x.indisready,
    pg_get_indexdef(x.indexrelid) AS definition
FROM pg_index AS x
JOIN pg_class AS i
    ON i.oid = x.indexrelid
JOIN pg_class AS t
    ON t.oid = x.indrelid
JOIN pg_namespace AS n
    ON n.oid = t.relnamespace
WHERE NOT x.indisvalid
   OR NOT x.indisready;
```

Nếu cần remove index invalid, xác định build đã dừng và dependencies trước. DROP INDEX CONCURRENTLY có thể phù hợp, nhưng phải chạy ngoài transaction block và không thể drop index đang backing constraint.

## 10. ADD FOREIGN KEY và index phía referencing table

Foreign key không tự động tạo index trên columns phía referencing table. Index có thể cần để query joins hoặc để PostgreSQL kiểm tra referenced row deletes/updates hiệu quả.

### 10.1. Thêm foreign key

```sql
ALTER TABLE app.order_items
    ADD CONSTRAINT order_items_order_fk
    FOREIGN KEY (order_id)
    REFERENCES app.orders(id)
    NOT VALID;
```

Sau khi xử lý dữ liệu cũ và kiểm tra writes:

```sql
ALTER TABLE app.order_items
    VALIDATE CONSTRAINT order_items_order_fk;
```

### 10.2. Index cho referencing columns

Ví dụ:

```sql
CREATE INDEX CONCURRENTLY order_items_order_id_idx
    ON app.order_items (order_id);
```

Index này không bắt buộc về mặt cú pháp foreign key, nhưng có thể giảm chi phí khi xóa/cập nhật referenced rows và khi query join từ child tới parent.

### 10.3. Chọn column order

Nếu foreign key gồm nhiều columns, index column order cần dựa trên query patterns. Index composite có thể hỗ trợ prefix predicates; không tạo index chỉ theo thứ tự constraint columns mà chưa xem workload.

## 11. Partition operations

Partitioned tables có parent relation và nhiều child partitions. Một số schema changes phải áp dụng nhất quán lên cả hierarchy.

### 11.1. ATTACH PARTITION

Ví dụ:

```sql
ALTER TABLE app.events
    ATTACH PARTITION app.events_2026_11
    FOR VALUES FROM ('2026-11-01') TO ('2026-12-01');
```

ATTACH PARTITION cần kiểm tra dữ liệu trong table được attach có phù hợp partition bound. Nếu PostgreSQL phải scan table để xác minh, thao tác có thể kéo dài và lấy lock đáng kể.

### 11.2. CHECK constraint để tránh validation scan

Có thể tạo CHECK constraint phù hợp trên table candidate trước:

```sql
ALTER TABLE app.events_2026_11
    ADD CONSTRAINT events_2026_11_bounds_check
    CHECK (
        created_at >= timestamp '2026-11-01'
        AND created_at < timestamp '2026-12-01'
    );
```

Nếu constraint được PostgreSQL nhận diện là chứng minh partition bounds, ATTACH có thể tránh scan table. Constraint cần chính xác với partition key/bounds và không được giả định một expression tùy ý sẽ được nhận diện.

### 11.3. DETACH PARTITION

Thông thường:

```sql
ALTER TABLE app.events
    DETACH PARTITION app.events_2026_01;
```

Detach thường cần lock mạnh trên parent và partition. Các version hỗ trợ có thể cung cấp `DETACH PARTITION CONCURRENTLY` để giảm lock trên parent, với restrictions và một số phase pending detach.

### 11.4. DETACH PARTITION CONCURRENTLY

```sql
ALTER TABLE app.events
    DETACH PARTITION app.events_2026_01 CONCURRENTLY;
```

Lệnh này có thể không chạy trong transaction block, có restrictions liên quan default partition và trạng thái detach. Sau khi detach concurrently, cần hoàn tất phase pending detach bằng command phù hợp nếu operation bị gián đoạn. Kiểm tra tài liệu đúng version trước khi automation.

### 11.5. ALTER parent và child locks

Thay đổi column/constraint trên partitioned parent có thể yêu cầu cập nhật child partitions. Số partitions càng lớn, số locks và catalog operations càng nhiều.

Hãy thử migration trên staging với số partitions tương đương production, không chỉ trên một table nhỏ.

## 12. Lock monitoring trước và trong migration

Migration cần được quan sát như một workload production.

### 12.1. Sessions đang chạy hoặc chờ

```sql
SELECT
    pid,
    usename,
    datname,
    application_name,
    state,
    wait_event_type,
    wait_event,
    xact_start,
    query_start,
    now() - query_start AS query_age,
    left(query, 500) AS query_sample
FROM pg_stat_activity
WHERE state <> 'idle'
ORDER BY query_start NULLS LAST;
```

`wait_event_type = 'Lock'` cho biết backend đang chờ lock. Session active không nhất thiết đang dùng CPU; nó có thể đang chờ resource.

### 12.2. Tìm blocking PIDs

```sql
SELECT
    a.pid AS blocked_pid,
    a.application_name AS blocked_app,
    a.usename AS blocked_user,
    a.wait_event_type,
    a.wait_event,
    pg_blocking_pids(a.pid) AS blocking_pids,
    now() - a.query_start AS blocked_duration,
    left(a.query, 400) AS blocked_query
FROM pg_stat_activity AS a
WHERE cardinality(pg_blocking_pids(a.pid)) > 0
ORDER BY a.query_start;
```

Sau đó tìm các blocking PIDs trong pg_stat_activity để biết transaction owner, age và query. Một blocker có thể đang idle in transaction nên query text hiện tại không phải statement đã lấy lock.

### 12.3. Đọc pg_locks

```sql
SELECT
    l.pid,
    l.locktype,
    l.relation::regclass AS relation,
    l.mode,
    l.granted,
    a.application_name,
    a.state,
    a.xact_start,
    left(a.query, 300) AS query_sample
FROM pg_locks AS l
LEFT JOIN pg_stat_activity AS a
    ON a.pid = l.pid
WHERE l.relation IS NOT NULL
ORDER BY l.granted, l.pid, l.relation;
```

`granted = false` cho biết lock đang chờ. Lock relation có thể hiển thị OID relation; với một số lock types, relation có thể NULL hoặc không áp dụng.

### 12.4. Kiểm tra long-running transactions

```sql
SELECT
    pid,
    usename,
    application_name,
    state,
    now() - xact_start AS transaction_age,
    wait_event_type,
    wait_event,
    left(query, 300) AS query_sample
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start;
```

Long-running transactions có thể ngăn DDL lấy lock và giữ snapshots ảnh hưởng vacuum/rewrite. Phối hợp với application owner trước khi cancel/terminate.

### 12.5. pg_blocking_pids

`pg_blocking_pids(pid)` là helper thuận tiện để tìm direct blockers. Với lock chains dài, lặp lại từ blocked sessions tới blocker sessions để xác định root blocker.

## 13. Timeouts và migration transaction design

Timeouts giúp giới hạn thời gian migration chờ và tránh làm queue requests tăng vô hạn.

### 13.1. lock_timeout

`lock_timeout` giới hạn thời gian một statement chờ mỗi lần acquire lock. Ví dụ:

```sql
SET lock_timeout = '2s';
```

Nếu không lấy được lock trong thời gian này, statement lỗi. Có thể đặt ở session hoặc dùng SET LOCAL trong transaction.

### 13.2. statement_timeout

`statement_timeout` giới hạn thời gian statement chạy tổng thể. Với validation hoặc index build lớn, timeout phải được chọn dựa trên thời gian dự kiến và rollback behavior.

### 13.3. idle_in_transaction_session_timeout

Một migration runner không nên mở transaction rồi để session idle lâu. Timeout này có thể kết thúc session idle trong transaction, nhưng cần phối hợp với migration framework và workload.

### 13.4. NOWAIT ở đâu?

Không phải mọi ALTER TABLE form đều hỗ trợ NOWAIT. Nếu cần thử lock mà không chờ, có thể dùng LOCK TABLE với NOWAIT trong một transaction để preflight lock availability:

```sql
BEGIN;
LOCK TABLE app.orders IN ACCESS EXCLUSIVE MODE NOWAIT;
ROLLBACK;
```

Preflight chỉ kiểm tra tại một thời điểm; lock có thể được acquire bởi session khác ngay sau rollback. Vì vậy nó không thay thế lock_timeout trong migration thật.

### 13.5. Một DDL statement trong transaction ngắn

Giữ DDL transaction ngắn:

```sql
BEGIN;
SET LOCAL lock_timeout = '2s';
SET LOCAL statement_timeout = '10min';

ALTER TABLE app.orders
    ADD COLUMN source_code text;

COMMIT;
```

Tránh chèn network calls, manual waits hoặc nhiều bước unrelated trước COMMIT.

### 13.6. Không gộp index concurrently vào transaction

Migration chứa CREATE INDEX CONCURRENTLY phải được chạy trong mode không transaction:

```sql
CREATE INDEX CONCURRENTLY orders_created_at_idx
    ON app.orders (created_at);
```

Migration framework cần đánh dấu migration này không transaction. Nếu framework tự bọc tất cả scripts trong BEGIN/COMMIT, lệnh sẽ thất bại.

## 14. Expand-contract migrations

Với ứng dụng cần uptime cao, thay đổi schema lớn nên chia thành nhiều releases tương thích ngược.

### 14.1. Expand

Thêm cấu trúc mới mà code cũ vẫn hoạt động:

```sql
ALTER TABLE app.customers
    ADD COLUMN display_name_v2 text;
```

Nếu column nullable/no default, thao tác thường metadata-only trên PostgreSQL hiện đại.

### 14.2. Deploy dual-write hoặc compatibility code

Application có thể ghi cả old và new columns trong một giai đoạn. Nếu dữ liệu cần đồng bộ, phải có chiến lược xử lý race conditions và transaction consistency.

### 14.3. Backfill theo batches

Không update hàng chục triệu rows trong một transaction duy nhất nếu có thể chia nhỏ. Ví dụ dùng primary key ranges:

```sql
UPDATE app.customers
SET display_name_v2 = display_name
WHERE id >= 1
  AND id < 10001
  AND display_name_v2 IS NULL;
```

Lặp lại theo ranges và commit từng batch. Batch size cần benchmark theo WAL, locks, replica lag và autovacuum.

Một cách khác dùng CTE và SKIP LOCKED để nhiều workers chia rows:

```sql
WITH batch AS (
    SELECT id
    FROM app.customers
    WHERE display_name_v2 IS NULL
    ORDER BY id
    LIMIT 1000
    FOR UPDATE SKIP LOCKED
)
UPDATE app.customers AS c
SET display_name_v2 = c.display_name
FROM batch
WHERE c.id = batch.id;
```

Worker cần lặp đến khi không còn rows phù hợp. Nếu concurrent writers tiếp tục tạo rows mới, dual-write hoặc trigger/compatibility logic phải bảo đảm không có gaps.

### 14.4. Validate

Khi backfill hoàn tất, kiểm tra:

```sql
SELECT count(*) AS remaining_rows
FROM app.customers
WHERE display_name IS NOT NULL
  AND display_name_v2 IS NULL;
```

Sau đó thêm/validate constraints hoặc indexes cần thiết.

### 14.5. Switch reads

Deploy application đọc từ column mới. Theo dõi error rate, data consistency và query plans. Giữ old column trong thời gian rollback.

### 14.6. Contract

Khi không còn code đọc/ghi old column, drop old structures trong release riêng:

```sql
ALTER TABLE app.customers
    DROP COLUMN display_name RESTRICT;
```

Drop column không nhất thiết reclaim disk ngay. Mục tiêu của contract là loại bỏ schema contract cũ; reclaim storage là quyết định riêng.

### 14.7. Vì sao không đổi type ngay?

Nếu ALTER COLUMN TYPE cần rewrite hàng lớn, expand-contract cho phép tạo column mới, backfill dần và switch application. Cách này tăng complexity và có thể tạm thời tăng storage, nhưng giảm thời gian giữ lock mạnh trên table chính.

## 15. Thay đổi data type theo từng giai đoạn

Ví dụ đổi `varchar` sang `bigint` khi dữ liệu đang lưu số dưới dạng text.

### 15.1. Preflight dữ liệu

```sql
SELECT external_id
FROM app.orders
WHERE external_id IS NOT NULL
  AND external_id !~ '^[0-9]+$'
LIMIT 100;
```

Kiểm tra range overflow:

```sql
SELECT external_id
FROM app.orders
WHERE external_id ~ '^[0-9]+$'
  AND external_id::numeric > 9223372036854775807
LIMIT 100;
```

Không cast trực tiếp mọi rows trước khi xác nhận format/range. Dữ liệu bất thường có thể làm DDL thất bại sau khi đã scan phần lớn table.

### 15.2. Trực tiếp ALTER TYPE

Nếu table nhỏ và maintenance window phù hợp:

```sql
ALTER TABLE app.orders
    ALTER COLUMN external_id TYPE bigint
    USING NULLIF(external_id, '')::bigint;
```

Đánh giá default, indexes, constraints, views, function signatures và application serialization trước.

### 15.3. Expand-contract với column mới

Với table lớn:

1. ADD COLUMN external_id_bigint bigint.
2. Deploy code dual-write.
3. Backfill theo batches.
4. Validate consistency.
5. Tạo indexes concurrently.
6. Chuyển reads sang column mới.
7. Ngừng writes vào column cũ.
8. Drop old column sau deprecation window.

### 15.4. Consistency check

```sql
SELECT count(*) AS mismatched_rows
FROM app.orders
WHERE external_id_bigint IS DISTINCT FROM
      NULLIF(external_id, '')::bigint;
```

Chỉ chạy cast trong consistency query sau khi đã bảo đảm dữ liệu có thể chuyển đổi; nếu không, query có thể lỗi. Với dữ liệu bẩn, dùng guarded conversion hoặc staging column để ghi nhận rows lỗi.

## 16. Thêm constraints online theo pattern

### 16.1. CHECK constraint

Pattern:

```sql
ALTER TABLE app.orders
    ADD CONSTRAINT orders_amount_check
    CHECK (total_amount >= 0)
    NOT VALID;

ALTER TABLE app.orders
    VALIDATE CONSTRAINT orders_amount_check;
```

Tách bước add khỏi validation để giảm thời gian lock mạnh. Monitor validation scan vì nó vẫn đọc dữ liệu và dùng I/O.

### 16.2. Foreign key

```sql
ALTER TABLE app.order_items
    ADD CONSTRAINT order_items_order_fk
    FOREIGN KEY (order_id)
    REFERENCES app.orders(id)
    NOT VALID;

ALTER TABLE app.order_items
    VALIDATE CONSTRAINT order_items_order_fk;
```

Đảm bảo referenced key có PK/unique constraint và xem xét index ở child columns cho workload.

### 16.3. NOT NULL

```sql
ALTER TABLE app.customers
    ADD CONSTRAINT customers_email_nn_check
    CHECK (email IS NOT NULL)
    NOT VALID;

ALTER TABLE app.customers
    VALIDATE CONSTRAINT customers_email_nn_check;

ALTER TABLE app.customers
    ALTER COLUMN email SET NOT NULL;

ALTER TABLE app.customers
    DROP CONSTRAINT customers_email_nn_check;
```

Đảm bảo không còn writers có thể ghi NULL trong thời gian các bước chạy.

### 16.4. Unique constraint

```sql
CREATE UNIQUE INDEX CONCURRENTLY customers_external_id_uidx
    ON app.customers (external_id);

ALTER TABLE app.customers
    ADD CONSTRAINT customers_external_id_key
    UNIQUE USING INDEX customers_external_id_uidx;
```

Nếu dữ liệu trùng, concurrent unique build thất bại. Preflight duplicates:

```sql
SELECT
    external_id,
    count(*)
FROM app.customers
WHERE external_id IS NOT NULL
GROUP BY external_id
HAVING count(*) > 1
ORDER BY count(*) DESC
LIMIT 100;
```

NULL semantics của UNIQUE và PRIMARY KEY khác nhau. Xác nhận business invariant trước khi chọn constraint.

## 17. Locking và rewrite trên partitioned tables

Partitioning làm tăng số relations mà một migration có thể chạm tới.

### 17.1. Thêm column trên parent

```sql
ALTER TABLE app.events
    ADD COLUMN source_system text;
```

PostgreSQL thường propagates column change tới partitions. Lock acquisition có thể liên quan parent và child relations. Số partitions lớn làm catalog/lock work tăng.

### 17.2. ALTER TABLE ONLY

```sql
ALTER TABLE ONLY app.events
    ALTER COLUMN source_system SET DEFAULT 'api';
```

ONLY hạn chế thao tác vào parent. Tuy nhiên, nếu child tables cần giữ schema đồng nhất, thay đổi chỉ parent có thể tạo trạng thái không phù hợp hoặc không được phép cho một số actions.

### 17.3. Type changes trên partitions

Đổi type của partitioned parent có thể yêu cầu thao tác tương ứng trên partitions. Table rewrite trên từng partition có thể tạo peak I/O/WAL lớn. Với historical partitions, có thể thực hiện từng partition nếu schema và application compatibility cho phép.

### 17.4. Lock partition maintenance

ATTACH/DETACH có lock behavior riêng. Nếu có default partition, việc xác minh bounds có thể scan default partition và kéo dài. Tạo CHECK constraint phù hợp trước khi attach để giảm scan khi PostgreSQL có thể chứng minh bounds.

## 18. Migration impact tới replication

DDL và rewrite có thể ảnh hưởng replicas khác nhau tùy replication mode.

### 18.1. Physical streaming replication

Physical replicas replay WAL từ primary. Table rewrite và index build tạo WAL có thể làm replica replay lag. DDL xuất hiện trên replica thông qua WAL replay, không chạy lại migration riêng trên physical standby.

### 18.2. Logical replication

Logical replication không replicate DDL tự động theo cách physical WAL replay làm. Schema change cần được triển khai riêng và đúng thứ tự trên publisher/subscriber.

Nếu subscriber chưa có column/constraint phù hợp, replication apply có thể lỗi khi publisher bắt đầu gửi rows theo schema mới. Thực hiện expand trên subscriber/publisher theo rollout plan.

### 18.3. Replication lag

Theo dõi:

```sql
SELECT
    application_name,
    state,
    sync_state,
    write_lag,
    flush_lag,
    replay_lag,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn
FROM pg_stat_replication;
```

Các lag fields có thể NULL khi không có sample gần đây. Kết hợp LSN byte differences và provider metrics để đánh giá đầy đủ.

### 18.4. Logical replication slots

Slot giữ WAL cho subscriber. Nếu consumer không theo kịp, retained WAL có thể tăng disk usage. Kiểm tra slot activity và retained bytes trong lúc rewrite lớn.

### 18.5. Rollout nhiều regions

Nếu application đọc từ replicas ở nhiều regions, chờ schema changes/replay hoàn tất trước khi deploy code phụ thuộc column mới. Có thể cần feature flag hoặc capability check.

## 19. Migration tool và transaction boundaries

Migration framework có thể tự quản lý transaction, lock timeout và ordering.

### 19.1. Một migration không nhất thiết là một transaction lớn

Các thay đổi metadata nhanh có thể gom trong transaction ngắn. Concurrent index build phải tách ra ngoài transaction. Backfill lớn nên chia batch và commit định kỳ.

### 19.2. Migration lock

Nhiều migration tools dùng advisory lock để bảo đảm chỉ một migration runner chạy tại một thời điểm. Advisory migration lock không thay thế table locks và không ngăn DBA hoặc application thực hiện DDL khác.

### 19.3. Idempotency

`IF EXISTS` và `IF NOT EXISTS` có thể giúp migration an toàn khi object state đã được kiểm tra, nhưng chúng không thay thế schema version tracking. Một index tồn tại nhưng có definition sai vẫn có thể làm CREATE INDEX IF NOT EXISTS bỏ qua việc sửa chữa.

### 19.4. Không chạy DDL không rõ trạng thái

Nếu deployment bị mất kết nối sau khi gửi DDL, client có thể không biết transaction đã commit hay chưa. Trước khi retry, kiểm tra catalog state và migration history. Không chạy lại destructive command mù quáng.

### 19.5. Migration observability

Ghi lại:

- Migration ID/version.
- Start/end timestamp.
- Database/cluster.
- Statement/phase.
- Lock wait duration.
- Execution duration.
- Rows processed.
- WAL bytes và replica lag.
- Error/retry count.
- Application release version.

## 20. Ví dụ migration: thêm column và backfill

Giả sử cần thêm column `normalized_email` vào bảng customers lớn.

### 20.1. Expand schema

```sql
ALTER TABLE app.customers
    ADD COLUMN normalized_email text;
```

Trên PostgreSQL hiện đại, đây thường là metadata-only nếu không có default volatile. Lock vẫn cần được lấy.

### 20.2. Deploy compatibility code

Code mới ghi cả email và normalized_email. Code cũ vẫn đọc email. Không chuyển reads ngay.

### 20.3. Backfill theo batch

```sql
WITH batch AS (
    SELECT id
    FROM app.customers
    WHERE normalized_email IS NULL
    ORDER BY id
    LIMIT 2000
    FOR UPDATE SKIP LOCKED
)
UPDATE app.customers AS c
SET normalized_email = lower(trim(c.email))
FROM batch
WHERE c.id = batch.id;
```

Chạy nhiều lần, commit mỗi batch. Dừng khi không còn rows phù hợp. Có thể cần phân biệt email NULL hợp lệ với rows chưa backfill bằng trạng thái riêng hoặc predicate phù hợp.

### 20.4. Thêm index concurrently

```sql
CREATE INDEX CONCURRENTLY customers_normalized_email_idx
    ON app.customers (normalized_email);
```

Theo dõi progress:

```sql
SELECT
    pid,
    datname,
    relid::regclass AS table_name,
    index_relid::regclass AS index_name,
    phase,
    lockers_total,
    lockers_done,
    blocks_total,
    blocks_done,
    tuples_total,
    tuples_done
FROM pg_stat_progress_create_index;
```

### 20.5. Switch reads

Deploy code đọc normalized_email. Theo dõi nulls, query plans, errors và latency. Giữ compatibility window để rollback.

### 20.6. Contract

Sau khi code cũ không còn chạy:

```sql
ALTER TABLE app.customers
    DROP COLUMN email RESTRICT;
```

Chỉ làm khi business contract và downstream consumers đã chuyển. Drop column không đảm bảo file size giảm ngay.

## 21. Ví dụ migration: thêm foreign key online

Giả sử order_items.order_id cần tham chiếu orders.id trên bảng lớn.

### 21.1. Preflight orphan rows

```sql
SELECT oi.order_id, count(*)
FROM app.order_items AS oi
LEFT JOIN app.orders AS o
    ON o.id = oi.order_id
WHERE oi.order_id IS NOT NULL
  AND o.id IS NULL
GROUP BY oi.order_id
ORDER BY count(*) DESC
LIMIT 100;
```

Giải quyết orphan rows trước khi validate.

### 21.2. Add NOT VALID

```sql
ALTER TABLE app.order_items
    ADD CONSTRAINT order_items_order_fk
    FOREIGN KEY (order_id)
    REFERENCES app.orders(id)
    NOT VALID;
```

Đánh giá lock window trên cả child và parent. Lệnh có thể chờ transaction đang giữ conflicting locks.

### 21.3. Validate

```sql
ALTER TABLE app.order_items
    VALIDATE CONSTRAINT order_items_order_fk;
```

Theo dõi I/O, active transactions và lock waits. Validation vẫn đọc rows hiện tại.

### 21.4. Post-check

```sql
SELECT
    conname,
    convalidated,
    pg_get_constraintdef(oid, true)
FROM pg_constraint
WHERE conrelid = 'app.order_items'::regclass
  AND conname = 'order_items_order_fk';
```

Xác nhận convalidated true và application writes không còn tạo orphan data.

## 22. Các thao tác có thể làm migration lâu dù không rewrite

Không rewrite table không có nghĩa thao tác tức thì.

### 22.1. Constraint validation

Validation scan có thể đọc toàn bộ table. Chi phí I/O gần với full scan tùy cache, table size và concurrency.

### 22.2. Index creation

Index build đọc table, sort/index tuples và ghi index storage. Concurrent build có thêm phases và waits để bảo đảm consistency.

### 22.3. SET NOT NULL

Nếu không có CHECK proof hợp lệ, PostgreSQL phải xác nhận không có NULL. Trên table lớn, scan là đáng kể.

### 22.4. Partition attach

PostgreSQL có thể scan table candidate hoặc default partition để xác minh partition constraints nếu không có CHECK constraint phù hợp.

### 22.5. DROP COLUMN

Catalog operation nhanh nhưng không reclaim physical space ngay. Nếu sau đó cần rewrite để reclaim, chi phí lớn sẽ xuất hiện ở bước khác.

## 23. Preflight checklist trước ALTER TABLE

Trước khi chạy DDL trên production, trả lời:

### 23.1. Object scope

- Table có bao nhiêu rows và bao nhiêu GB?
- Có partitions/inheritance children không?
- Có indexes, constraints, triggers, views hoặc foreign keys liên quan không?
- Có replication/CDC consumers không?

### 23.2. Lock behavior

- Subcommand lấy lock mode nào?
- Có cần lock trên referenced tables hoặc partitions không?
- Có transaction dài đang giữ conflicting locks không?
- Có pending DDL hoặc maintenance job không?
- Lock timeout và statement timeout đã đặt chưa?

### 23.3. Rewrite/scan behavior

- Operation có rewrite table không?
- Có scan rows hiện tại không?
- Có rebuild indexes không?
- Có thể dùng NOT VALID/VALIDATE hoặc concurrent index build không?
- Có thể dùng expand-contract không?

### 23.4. Resource capacity

- Disk free trên tablespace chứa table/index?
- WAL capacity/archive throughput?
- Replica lag headroom?
- CPU/I/O headroom?
- Backup window và retained WAL?
- Có đủ room cho old/new files đồng thời không?

### 23.5. Application compatibility

- Old/new application versions có thể chạy đồng thời không?
- ORM/schema cache có cần refresh không?
- Prepared statements có bị ảnh hưởng bởi rename/type change không?
- Có feature flag để switch reads/writes không?
- Rollback có khả thi sau khi backfill không?

## 24. Monitoring migration progress

### 24.1. CREATE INDEX progress

`pg_stat_progress_create_index` hiển thị phase, blocks và tuples processed cho index builds đang chạy.

### 24.2. VACUUM progress

`pg_stat_progress_vacuum` theo dõi vacuum operations. Nếu maintenance đi cùng migration, dùng progress view tương ứng để tách chi phí.

### 24.3. Table locks

Dùng pg_locks kết hợp pg_stat_activity để phát hiện sessions đang giữ hoặc chờ locks. Theo dõi pending DDL trước khi nó gây lock convoy.

### 24.4. WAL và replication

Theo dõi WAL generation, archive backlog, replication slot retention và replica replay lag. Với rewrite lớn, đặt alert theo disk headroom và lag budget.

### 24.5. Application metrics

Theo dõi:

- Request p95/p99 latency.
- Connection pool wait.
- Database timeout/error rate.
- Queue depth.
- Transaction retry count.
- Endpoint availability.
- Background job backlog.

Migration thành công về mặt SQL nhưng làm API timeout vẫn là migration thất bại về mặt vận hành.

## 25. Rollback và recovery

Không phải mọi schema migration đều có thể rollback bằng một lệnh đơn giản.

### 25.1. Metadata-only change

ADD COLUMN có thể rollback bằng DROP COLUMN nếu không có data/dependencies mới cần giữ. Rename có thể rename ngược, nhưng application versions có thể đã sử dụng tên mới.

### 25.2. Type change

Đổi type ngược có thể mất dữ liệu nếu conversion không reversible. Ví dụ bigint sang integer có thể overflow hoặc text normalization có thể mất original formatting.

### 25.3. Backfill

Backfill thường không thể rollback bằng cách set column về NULL nếu application đã bắt đầu ghi values mới. Cần xác định source of truth và reconciliation strategy.

### 25.4. Index creation

Index có thể drop nếu không backing constraint và không cần bởi workload. Concurrent index cleanup cần chạy ngoài transaction block.

### 25.5. DDL sau khi commit

Sau COMMIT, rollback cần một migration mới hoặc restore/recovery strategy. Không giả định transaction rollback có thể undo một migration đã commit trong release trước.

### 25.6. Recovery plan

Trước operation rủi ro cao:

- Có backup/restore point phù hợp.
- Kiểm tra backup có thể restore.
- Lưu DDL và current definitions.
- Có migration inverse hoặc forward-fix plan.
- Xác định người quyết định abort.
- Đặt thresholds cho disk, lag, latency và lock wait.

## 26. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| ALTER TABLE chờ rất lâu | Conflicting transaction giữ lock | Dùng pg_blocking_pids, tìm transaction owner |
| SELECT mới cũng bị chờ | ACCESS EXCLUSIVE DDL đang xếp hàng | Điều tra lock queue, dừng retry burst, xử lý blocker |
| ADD COLUMN mất nhiều thời gian | Volatile default hoặc version cũ cần rewrite | Kiểm tra default volatility và server version |
| ALTER TYPE làm disk tăng mạnh | Table/index rewrite và WAL | Ước tính disk/WAL, staged migration |
| ADD CHECK làm writes chờ | Validation/lock behavior | Dùng NOT VALID rồi VALIDATE |
| SET NOT NULL scan table lâu | Chưa có CHECK proof hợp lệ | Backfill, validate check, rồi set not null |
| CREATE INDEX CONCURRENTLY thất bại | Duplicate values, old snapshots hoặc cancellation | Kiểm tra logs, invalid index và blocker |
| ADD FK thất bại | Orphan rows | Preflight và sửa dữ liệu trước |
| Replica lag tăng | WAL burst từ rewrite/index build | Giảm batch/concurrency, theo dõi replay |
| Disk đầy giữa rewrite | Thiếu headroom cho old/new files/WAL | Dừng rollout theo runbook, mở rộng capacity |
| DROP COLUMN không giảm disk | Column chỉ bị đánh dấu dropped | Đánh giá rewrite/repack riêng |
| Migration tool báo concurrent index trong transaction | Script bị auto-wrap BEGIN/COMMIT | Đánh dấu migration non-transactional |
| Partition attach scan lâu | Thiếu CHECK constraint chứng minh bounds | Thêm/validate constraint trước attach |
| Schema đổi nhưng app lỗi | Old/new code không tương thích | Expand-contract và feature flags |
| Rollback mất dữ liệu | Type/backfill conversion không reversible | Dùng forward fix hoặc restore/reconciliation |

## 27. Runbook triển khai ALTER TABLE trên production

**Bước 1 — Xác định thay đổi.** Ghi rõ table, columns, constraints, indexes, partitions và application behavior trước/sau.

**Bước 2 — Phân loại operation.** Xác định metadata-only, table scan, index build hay rewrite. Ghi lock mode và relations liên quan.

**Bước 3 — Kiểm tra workload.** Tìm long-running transactions, blockers, peak traffic và maintenance đang chạy.

**Bước 4 — Kiểm tra capacity.** Ước tính table/index size, disk headroom, WAL/archive throughput và replica lag budget.

**Bước 5 — Chuẩn bị migration.** Chọn lock_timeout, statement_timeout, transaction boundaries, batch size và rollback/forward-fix plan.

**Bước 6 — Thử trên staging.** Dùng data volume, indexes, partitions và concurrency gần production; đo lock wait, runtime, WAL và disk.

**Bước 7 — Thực hiện theo phase.** Ưu tiên expand, concurrent index, NOT VALID/VALIDATE và batch backfill khi phù hợp.

**Bước 8 — Theo dõi realtime.** Xem pg_stat_activity, pg_locks, progress views, replication lag, disk và application metrics.

**Bước 9 — Abort nếu vượt budget.** Dừng batch hoặc cancel operation theo runbook nếu latency, disk hoặc lag vượt ngưỡng đã định.

**Bước 10 — Verify schema và data.** Kiểm tra catalogs, constraints, index validity, row consistency và application behavior.

**Bước 11 — Switch traffic.** Bật feature flag/read path mới sau khi schema và replicas đã sẵn sàng.

**Bước 12 — Contract sau deprecation.** Drop old objects trong release riêng khi không còn callers và dependencies.

## 28. Bài thực hành

Thực hiện trên PostgreSQL lab riêng. Không thử rewrite lớn, lock contention hoặc DDL destructive trên production.

### Bài 1 — ALTER TABLE metadata

Tạo table nhỏ và thêm nullable column không default. Quan sát catalog changes và giải thích vì sao operation không cần điền NULL vào từng row.

### Bài 2 — Lock mode

Trong một session mở transaction SELECT trên table. Ở session khác chạy ALTER TABLE ADD COLUMN. Quan sát lock wait và giải thích ACCESS SHARE/ACCESS EXCLUSIVE conflict.

### Bài 3 — Lock queue

Tạo một transaction giữ lock lâu, cho ALTER TABLE chờ và gửi thêm SELECT. Quan sát queue behavior và request latency.

### Bài 4 — lock_timeout

Đặt lock_timeout ngắn rồi thử ALTER TABLE khi có blocker. Xác nhận statement fail fast và transaction cần rollback.

### Bài 5 — statement_timeout

Chạy validation hoặc query lâu trong lab với statement_timeout ngắn. So sánh timeout với lock_timeout.

### Bài 6 — ADD COLUMN không default

Tạo table nhiều rows, thêm nullable column và so thời gian với table nhỏ. Ghi nhận lock và file size.

### Bài 7 — ADD COLUMN constant default

Trên PostgreSQL 11+, thêm column với constant default. So với behavior của version cũ hơn hoặc tài liệu version tương ứng.

### Bài 8 — ADD COLUMN volatile default

Thêm column với volatile default trong lab. Quan sát runtime và tìm hiểu vì sao existing rows cần giá trị riêng.

### Bài 9 — SET/DROP DEFAULT

Thay đổi default và xác nhận các rows cũ không tự thay đổi.

### Bài 10 — DROP COLUMN

Drop một column trong lab và kiểm tra pg_attribute.attisdropped. So sánh logical schema với physical relation size.

### Bài 11 — RENAME COLUMN

Rename column và thử application query dùng tên cũ/mới. Viết rollout tương thích ngược.

### Bài 12 — ALTER TYPE rewrite

Đổi text column sang bigint bằng USING trên table lab có nhiều rows. Đo thời gian, disk và WAL.

### Bài 13 — Binary-coercible conversion

Tìm một type conversion được tài liệu PostgreSQL xác định là binary-coercible. So sánh behavior với conversion phải rewrite.

### Bài 14 — Default conversion

Tạo default không cast được sang target type. Thử DROP DEFAULT, ALTER TYPE và SET DEFAULT lại.

### Bài 15 — CHECK validation

Thêm CHECK constraint bình thường trên table có dữ liệu. Quan sát scan và so với ADD CHECK NOT VALID rồi VALIDATE.

### Bài 16 — NOT NULL proof

Tạo rows có NULL, backfill, thêm CHECK NOT VALID, validate rồi SET NOT NULL. Quan sát behavior và lock.

### Bài 17 — Foreign key NOT VALID

Tạo orphan rows, add FK NOT VALID và quan sát dữ liệu mới được kiểm tra. Sửa orphan rồi validate constraint.

### Bài 18 — FK referencing index

Tạo child table có foreign key. Thử delete parent rows khi chưa có index child, sau đó tạo index và so query/lock impact.

### Bài 19 — Unique index concurrently

Tạo unique index concurrently trên table lớn trong lab. Theo dõi pg_stat_progress_create_index.

### Bài 20 — Concurrent index failure

Tạo duplicate data và thử unique index concurrently. Kiểm tra invalid index còn lại và quy trình cleanup.

### Bài 21 — Attach index as constraint

Tạo unique index concurrently rồi dùng ADD CONSTRAINT USING INDEX. Kiểm tra constraint/index catalog relationship.

### Bài 22 — Transaction boundary

Chạy ALTER TABLE trong transaction dài và quan sát lock vẫn tồn tại sau statement đến khi COMMIT.

### Bài 23 — Rewrite disk estimate

Đo table/index size và ước tính peak free space cho rewrite. So với disk consumption trên lab.

### Bài 24 — WAL và replica lag

Trên lab có physical standby, chạy rewrite có kiểm soát và quan sát WAL generation/replay lag.

### Bài 25 — MVCC rewrite caveat

Tạo long-running snapshot transaction và thử rewrite trong môi trường test. Quan sát behavior theo version và giải thích cảnh báo MVCC-safe.

### Bài 26 — Partition attach

Tạo partitioned parent và candidate table. Attach partition; so behavior khi có/không có CHECK constraint chứng minh bounds.

### Bài 27 — Partition detach

Thử DETACH PARTITION thông thường và CONCURRENTLY nếu version hỗ trợ. Quan sát lock modes và restrictions.

### Bài 28 — Parent ALTER TABLE

Thêm column trên partitioned parent. Quan sát schema/locks của child partitions và thử ONLY trong lab.

### Bài 29 — Expand-contract

Thực hiện migration thêm column mới, dual-write, batch backfill, switch reads và drop old column trên application lab.

### Bài 30 — Batch backfill

So một UPDATE lớn với nhiều batches. Đo WAL, transaction duration, replica lag và autovacuum impact.

### Bài 31 — Blocking diagnosis

Tạo blocker và blocked DDL. Dùng pg_stat_activity, pg_locks và pg_blocking_pids để tìm root transaction.

### Bài 32 — Migration timeout

Thiết kế migration dùng SET LOCAL lock_timeout và statement_timeout. Xác nhận rollback behavior khi timeout.

### Bài 33 — Migration framework

Cấu hình một migration không transaction cho CREATE INDEX CONCURRENTLY. Xác nhận framework không tự bọc BEGIN/COMMIT.

### Bài 34 — Preflight report

Viết read-only report gồm table size, index size, partitions, long transactions, locks, replication lag và disk headroom trước DDL.

### Bài 35 — Production rollout plan

Viết runbook cho một ALTER COLUMN TYPE trên table lớn, gồm preflight, staged migration, batch size, monitoring, abort thresholds và recovery plan.

## 29. Tổng kết

Những điểm cốt lõi khi sử dụng **ALTER TABLE, mức khóa và thao tác cần viết lại bảng**:

1. ALTER TABLE có nhiều forms với lock, scan và rewrite costs khác nhau.
2. Hầu hết ALTER TABLE forms cần ACCESS EXCLUSIVE; ADD FOREIGN KEY và VALIDATE CONSTRAINT là các ngoại lệ lock quan trọng.
3. Metadata-only không có nghĩa không blocking: lock mạnh vẫn có thể chặn reads/writes.
4. Lock được giữ đến cuối transaction, vì vậy migration transaction cần ngắn.
5. ADD COLUMN nullable không default thường không rewrite; constant default có fast path từ PostgreSQL 11, volatile default có thể rewrite.
6. SET/DROP DEFAULT và RENAME chủ yếu thay đổi metadata.
7. DROP COLUMN không reclaim physical disk ngay.
8. ADD CHECK/FK NOT VALID giúp tách việc tạo constraint khỏi scan dữ liệu cũ; VALIDATE CONSTRAINT dùng lock nhẹ hơn.
9. SET NOT NULL có thể tránh full scan khi có validated CHECK proof phù hợp.
10. ALTER COLUMN TYPE thường rewrite table nếu physical representation cần thay đổi; USING expression phải được preflight.
11. Unique index concurrently và ADD CONSTRAINT USING INDEX có thể giảm thời gian giữ lock mạnh.
12. Concurrent index build tốn I/O, có nhiều phases và có thể để lại invalid index khi thất bại.
13. Partition attach/detach có lock behavior và restrictions riêng.
14. Rewrite cần disk, WAL, CPU, I/O và có thể làm replica lag; nó cũng có MVCC caveats.
15. Expand-contract, batch backfill, bounded timeouts và monitoring giúp giảm rủi ro production.

Một schema migration an toàn bắt đầu bằng việc hiểu lock mode và physical work mà PostgreSQL phải thực hiện. Khi tách được metadata change, validation scan, index build và table rewrite, đội vận hành có thể chọn đúng rollout pattern, dự trù tài nguyên và giảm nguy cơ DDL biến thành outage.

## 30. Tài liệu PostgreSQL chính thức

- [ALTER TABLE](https://www.postgresql.org/docs/current/sql-altertable.html)
- [Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html)
- [Table-Level Lock Modes](https://www.postgresql.org/docs/current/explicit-locking.html#LOCKING-TABLES)
- [MVCC and Table Rewriting](https://www.postgresql.org/docs/current/mvcc-caveats.html)
- [ALTER TABLE and Constraints](https://www.postgresql.org/docs/current/ddl-constraints.html)
- [CREATE INDEX](https://www.postgresql.org/docs/current/sql-createindex.html)
- [CREATE INDEX Progress Reporting](https://www.postgresql.org/docs/current/progress-reporting.html#CREATE-INDEX-PROGRESS-REPORTING)
- [Partitioning](https://www.postgresql.org/docs/current/ddl-partitioning.html)
- [ALTER TABLE Partition Operations](https://www.postgresql.org/docs/current/sql-altertable.html)
- [Runtime Client Connection Defaults](https://www.postgresql.org/docs/current/runtime-config-client.html)
- [Monitoring Database Activity](https://www.postgresql.org/docs/current/monitoring-stats.html)
- [pg_locks](https://www.postgresql.org/docs/current/view-pg-locks.html)
- [pg_stat_activity](https://www.postgresql.org/docs/current/monitoring-stats.html#MONITORING-PG-STAT-ACTIVITY-VIEW)
- [Progress Reporting](https://www.postgresql.org/docs/current/progress-reporting.html)
- [Warm Standby and Streaming Replication](https://www.postgresql.org/docs/current/warm-standby.html)
- [Logical Replication](https://www.postgresql.org/docs/current/logical-replication.html)

Các liên kết `current` trỏ tới tài liệu PostgreSQL hiện hành. Lock modes, fast defaults, partition operations, catalog fields và concurrent DDL restrictions có thể khác theo major version. Trước khi triển khai, kiểm tra `SHOW server_version` và tài liệu tương ứng với version đang chạy.
