# Đổi kiểu dữ liệu, backfill và kiểm soát tác động trong PostgreSQL

Thay đổi kiểu dữ liệu của một cột có vẻ chỉ là một lệnh `ALTER TABLE`, nhưng trong production nó có thể ảnh hưởng đến hàng triệu rows, indexes, constraints, ứng dụng đang chạy, replication và thời gian phục hồi. Một phép chuyển đổi có thể giữ lock mạnh trong thời gian dài, rewrite toàn bộ table, tạo lượng WAL lớn hoặc khiến phiên bản ứng dụng cũ không còn tương thích.

Với database lớn và hệ thống cần uptime cao, nên xem schema migration là một quy trình nhiều giai đoạn. Mẫu thường dùng là **expand – migrate – contract**: mở rộng schema để phiên bản ứng dụng cũ và mới cùng hoạt động, chuyển dữ liệu theo batch có thể kiểm soát, chuyển traffic sang cấu trúc mới, rồi mới loại bỏ cấu trúc cũ sau khi đã xác nhận không còn consumer phụ thuộc.

Bài học này giải thích cách đổi kiểu dữ liệu an toàn, thiết kế shadow column, dual writes, backfill theo batch, kiểm soát lock/I/O/WAL, xác minh kết quả và lập kế hoạch rollback. Các ví dụ dùng PostgreSQL SQL; cần điều chỉnh theo major version, kích thước bảng và workload thực tế.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Đánh giá tác động của `ALTER COLUMN TYPE` trước khi triển khai.
2. Phân biệt metadata-only change với table rewrite và index rebuild.
3. Chọn direct conversion hoặc expand–migrate–contract.
4. Thiết kế shadow column và tương thích giữa nhiều phiên bản ứng dụng.
5. Viết backfill idempotent, chia batch và kiểm soát concurrency.
6. Xử lý dual writes, retries, race conditions và dữ liệu thay đổi trong lúc backfill.
7. Theo dõi lock waits, transaction age, WAL, replication lag và disk headroom.
8. Dùng constraints `NOT VALID`/`VALIDATE CONSTRAINT` và index concurrent khi phù hợp.
9. Kiểm tra completeness, correctness và application behavior trước cutover.
10. Lập rollback/roll-forward plan và điều kiện dừng migration.
11. Triển khai migration theo canary, maintenance window và phased rollout.
12. Ghi nhận tiến độ, metrics, ownership và kết quả sau thay đổi.

## 2. Vì sao đổi kiểu dữ liệu có rủi ro?

### 2.1. Tác động không chỉ nằm ở cột

Một cột có thể được sử dụng bởi:

- Application queries, ORM models và prepared statements;
- Views, materialized views, functions, triggers và generated columns;
- Indexes, unique constraints, primary keys và foreign keys;
- Check constraints, partition keys và partition bounds;
- Logical replication publications/subscriptions;
- ETL, CDC, reporting, BI và downstream services;
- Stored procedures, jobs, exports và API contracts.

Thay đổi type có thể làm thay đổi cast resolution, operator selection, index usability, sort semantics, precision, timezone handling hoặc serialized values.

### 2.2. Lock duration

Nhiều dạng `ALTER TABLE` yêu cầu `ACCESS EXCLUSIVE` lock. Lock này xung đột với hầu hết operations trên relation. Nếu lệnh phải rewrite table lớn, lock có thể được giữ trong phần lớn thời gian rewrite và chặn reads/writes.

Ngay cả khi DDL thực hiện nhanh sau khi lấy được lock, nó có thể chờ lâu để lấy lock. Một DDL đang chờ `ACCESS EXCLUSIVE` có thể làm các queries mới xếp hàng phía sau tùy lock queue và tạo ra outage dây chuyền.

### 2.3. Table rewrite

Nếu conversion không binary-coercible hoặc PostgreSQL cần thay đổi representation vật lý, `ALTER COLUMN TYPE` có thể rewrite table. Rewrite đọc/ghi dữ liệu, cần thêm disk tạm, tạo WAL và ảnh hưởng cache/I/O.

Một số thay đổi type có thể tránh rewrite theo quy tắc cụ thể của PostgreSQL và version, ví dụ tăng giới hạn `varchar` trong một số trường hợp. Không suy ra mọi thay đổi “cùng dữ liệu” đều metadata-only; kiểm tra documentation và thử trên bản sao có kích thước tương đương.

### 2.4. Indexes và constraints

Index phụ thuộc cột có thể cần rebuild hoặc bị ảnh hưởng bởi type/operator class/collation change. Unique/check/foreign key constraints có thể yêu cầu validation hoặc thay đổi semantics. Index rebuild cũng tiêu thụ disk, I/O và WAL.

### 2.5. WAL và replication

Rewrite/backfill lớn có thể sinh WAL nhiều hơn tốc độ standby/archive xử lý. Hệ quả:

- Replication lag tăng;
- Replication slots giữ WAL làm `pg_wal` phình;
- WAL archive backlog;
- Backup/restore window dài hơn;
- DR replica có thể không đạt RPO;
- Disk đầy gây ảnh hưởng toàn cluster.

### 2.6. Ảnh hưởng ứng dụng

Ứng dụng cũ có thể gửi giá trị không còn cast được, mong đợi format cũ hoặc đọc cột trong khi migration đang chuyển đổi. ORM có thể cache schema metadata. Prepared statements có thể cần được refresh khi type/result metadata thay đổi.

### 2.7. Rollback không miễn phí

Sau khi backfill hoặc ghi dữ liệu theo type mới, rollback có thể mất thông tin nếu chuyển đổi ngược không lossless. Ví dụ `numeric` sang `integer` làm mất phần thập phân; `timestamp with time zone` sang `timestamp without time zone` có thể làm mất timezone context. Thiết kế rollback trước khi bắt đầu.

## 3. Đánh giá phép chuyển đổi type

### 3.1. Xác định source và target semantics

Trước tiên ghi rõ:

- Type hiện tại và type đích;
- Nullability;
- Default expression;
- Allowed value range;
- Precision/scale;
- Collation/encoding;
- Timezone semantics;
- Sort/equality semantics;
- Application/API representation;
- Constraint/index dependencies.

“Chuyển dữ liệu không lỗi” chưa đủ; phải giữ đúng ý nghĩa nghiệp vụ.

### 3.2. Kiểm tra dữ liệu trước conversion

Ví dụ chuyển text sang integer:

~~~sql
SELECT
    count(*) AS total_rows,
    count(*) FILTER (WHERE value_text IS NULL) AS null_rows,
    count(*) FILTER (
        WHERE value_text IS NOT NULL
          AND value_text !~ '^[+-]?[0-9]+$'
    ) AS non_integer_rows
FROM public.imported_values;
~~~

Kiểm tra range trước khi cast:

~~~sql
SELECT
    min(value_text::numeric) AS min_value,
    max(value_text::numeric) AS max_value
FROM public.imported_values
WHERE value_text ~ '^[+-]?[0-9]+$';
~~~

Chỉ cast trong query kiểm tra sau khi bảo đảm dữ liệu hợp lệ; không viết query có thể cast lỗi trên một row không được lọc an toàn.

### 3.3. Direct ALTER COLUMN TYPE

Khi table nhỏ, downtime/lock được chấp nhận và conversion đã kiểm tra kỹ, có thể dùng:

~~~sql
ALTER TABLE public.orders
ALTER COLUMN external_id TYPE bigint
USING external_id::bigint;
~~~

`USING` định nghĩa expression chuyển đổi từng giá trị. PostgreSQL có thể tự cast trong trường hợp có cast phù hợp, nhưng expression tường minh làm rõ ý định và xử lý conversion đặc thù.

### 3.4. Conversion có thể fail

Nếu một giá trị không cast được, statement thất bại và transaction rollback. Kiểm tra/clean dữ liệu trước migration; nếu cần map giá trị đặc biệt, biểu diễn mapping rõ ràng trong expression hoặc migration staging.

~~~sql
ALTER TABLE public.customer_codes
ALTER COLUMN code TYPE bigint
USING CASE
    WHEN code ~ '^[0-9]+$' THEN code::bigint
    ELSE NULL
END;
~~~

Ví dụ này chỉ phù hợp khi business chấp nhận map invalid values thành NULL và cột cho phép NULL. Không âm thầm biến dữ liệu lỗi thành NULL nếu làm mất thông tin.

### 3.5. Default expression

Default cũ có thể không tự chuyển đổi được sang type mới. Có thể cần drop default trước, đổi type, rồi set default mới:

~~~sql
ALTER TABLE public.orders
ALTER COLUMN external_id DROP DEFAULT;

ALTER TABLE public.orders
ALTER COLUMN external_id TYPE bigint
USING external_id::bigint;

ALTER TABLE public.orders
ALTER COLUMN external_id SET DEFAULT 0;
~~~

Thực hiện trong một transaction khi phù hợp và khi lock/rewrites nằm trong budget. Đừng dùng default ví dụ `0` nếu nó không có nghĩa nghiệp vụ.

### 3.6. Nullability và constraints

Nếu conversion tạo NULL, cột NOT NULL sẽ khiến migration fail. Xác định null handling trước. Với table lớn, có thể thêm check constraint `NOT VALID`, backfill/clean dữ liệu, validate constraint rồi đặt NOT NULL theo quy trình/version phù hợp.

### 3.7. Numeric precision/scale

Chuyển `numeric(p,s)` sang scale thấp hơn có thể round values; chuyển sang integer có thể cần rounding/truncation rõ ràng. Kiểm tra giá trị lớn nhất, nhỏ nhất, số chữ số thập phân và business rounding rules.

### 3.8. Timestamp semantics

`timestamp without time zone` chỉ là wall-clock timestamp; `timestamptz` lưu instant và hiển thị theo timezone session. Chuyển đổi giữa hai loại cần định nghĩa timezone nguồn. Không cast mù nếu giá trị cũ được ghi ở nhiều timezone hoặc timezone chưa rõ.

### 3.9. Text, varchar và collation

Tăng varchar length limit thường khác với đổi collation hoặc đổi encoding semantics. Collation change có thể ảnh hưởng sort/equality và indexes; kiểm tra collation version và kế hoạch rebuild indexes theo tài liệu.

### 3.10. JSON và JSONB

`json` giữ input text representation; `jsonb` parse và lưu dạng binary chuẩn hóa, hỗ trợ indexing/operators khác nhau. Chuyển sang jsonb có thể fail nếu JSON invalid, tốn CPU và tạo index cần thiết kế lại. Xác minh duplicate keys, number precision và application assumptions.

### 3.11. Enum và domain

Thêm enum value có semantics/transaction restrictions phụ thuộc PostgreSQL version. Đổi enum sang text hoặc domain cần xét constraints, defaults và application serialization. Không dùng enum nếu lifecycle values thay đổi thường xuyên mà migration coordination khó.

### 3.12. Dependency inventory

Trước DDL, kiểm tra indexes/constraints/views/functions/triggers/foreign keys và partition dependencies. Dùng catalog queries, schema migration tooling và source-code search. Không chỉ dựa vào một query catalog để tìm mọi dependency dynamic.

## 4. Quyết định giữa direct conversion và staged migration

### 4.1. Khi direct ALTER phù hợp

Direct conversion có thể phù hợp khi:

- Table nhỏ hoặc maintenance window đủ dài;
- Lock impact được chấp nhận;
- Conversion đơn giản, deterministic và lossless;
- Có đủ disk/WAL headroom;
- Replicas/archives theo kịp;
- Ứng dụng có thể được dừng hoặc deploy đồng bộ;
- Restore/rollback plan đã kiểm thử.

### 4.2. Khi cần staged migration

Dùng expand–migrate–contract khi:

- Table lớn;
- Uptime cao, không thể giữ lock lâu;
- Ứng dụng deploy rolling nhiều phiên bản;
- Type mới cần mapping/backfill;
- Dữ liệu cũ không đồng nhất;
- Nhiều services/consumers đọc hoặc ghi cùng cột;
- Cần kiểm chứng trước khi chuyển traffic.

### 4.3. Expand–migrate–contract

Luồng triển khai:

1. Expand: thêm cột mới/constraint/index theo cách tương thích;
2. Deploy bridge app: hỗ trợ cả schema cũ và mới;
3. Migrate: backfill theo batch và đồng bộ writes mới;
4. Validate: kiểm tra parity, completeness và constraints;
5. Cutover: chuyển reads/writes sang cột mới;
6. Observe: giữ rollback window và theo dõi;
7. Contract: bỏ cột cũ sau khi mọi consumer đã chuyển.

### 4.4. Giai đoạn expand

Thêm cấu trúc mới theo cách tương thích với code hiện tại. Thường thêm shadow column nullable, index mới hoặc constraint chưa validate. Không drop/rename cột cũ trong giai đoạn này.

### 4.5. Giai đoạn migrate

Deploy application có khả năng đọc/ghi schema mới theo policy. Backfill dữ liệu cũ theo batch; đồng bộ các writes phát sinh trong lúc backfill. Theo dõi progress và verify.

### 4.6. Giai đoạn cutover

Chuyển reads sang cột mới, sau đó chuyển writes theo một bước được kiểm soát. Dùng feature flag/canary để giới hạn blast radius. Theo dõi errors, latency và data parity.

### 4.7. Giai đoạn contract

Sau khi mọi application versions, jobs, reports, CDC consumers và integrations không còn dùng cột cũ, mới drop cột/index/constraint cũ. Contract là thay đổi khó rollback; thực hiện sau một khoảng quan sát đủ dài.

### 4.8. Compatibility matrix

| Application version | Schema cũ | Schema mở rộng | Schema sau contract |
| --- | --- | --- | --- |
| Old app | Được hỗ trợ | Phải tiếp tục hoạt động | Không còn được deploy |
| Bridge app | Không nhất thiết | Đọc/ghi tương thích | Cần được nâng cấp trước contract |
| New app | Không nhất thiết | Đọc/ghi cột mới, fallback theo policy | Được hỗ trợ |

Lập bảng này trước rollout để xác định thứ tự deploy và thời điểm có thể bỏ cấu trúc cũ.

### 4.9. Rollback và roll-forward

Trước cutover, có thể rollback app/schema mới nếu cột cũ vẫn authoritative và được đồng bộ. Sau cutover, nếu writes chỉ vào cột mới, rollback app cũ có thể không an toàn. Cần dual-write hoặc reverse synchronization trong rollback window, hoặc chọn roll-forward fix thay vì quay ngược dữ liệu.

## 5. Shadow column và dual writes

### 5.1. Shadow column là gì?

Shadow column là cột mới được thêm cạnh cột cũ để chứa cùng dữ liệu theo type/representation mới. Ví dụ `customer_code` hiện là text nhưng hệ thống muốn chuyển sang bigint:

~~~sql
ALTER TABLE public.customers
ADD COLUMN customer_code_v2 bigint;
~~~

Thêm cột nullable không có default thường là thay đổi metadata nhanh, nhưng vẫn cần lock ngắn để sửa catalog. Lock có thể phải chờ transaction khác; dùng `lock_timeout` và retry có kiểm soát.

### 5.2. Đặt tên và quản lý lifecycle

Tên cột nên thể hiện mục đích, không để suffix v2 tồn tại vĩnh viễn. Theo dõi migration state ở code/config hoặc bảng quản lý migration; tài liệu hóa cột authoritative trong từng phase.

### 5.3. Chọn source of truth

Trước khi backfill, xác định cột nào authoritative:

- Phase A: cột cũ là source of truth; cột mới được đồng bộ từ cũ;
- Phase B: cả hai được ghi cùng transaction; đọc vẫn từ cột cũ;
- Phase C: cutover reads sang cột mới; giữ cột cũ đồng bộ trong rollback window;
- Phase D: cột mới là source of truth; ngừng ghi cột cũ;
- Phase E: contract và drop cột cũ.

Không để application, trigger và backfill tự chọn source of truth khác nhau.

### 5.4. Dual write ở application

Ứng dụng bridge có thể ghi cả hai cột trong cùng transaction:

~~~sql
INSERT INTO public.customers (customer_code, customer_code_v2)
VALUES ('12345', 12345);

UPDATE public.customers
SET customer_code = '67890',
    customer_code_v2 = 67890
WHERE id = 42;
~~~

Nếu conversion có thể fail, application phải validate trước và xử lý lỗi theo business rules. Hai writes trong cùng database transaction giúp atomicity; ghi sang hai systems/database khác nhau cần outbox/CDC hoặc coordination riêng.

### 5.5. Dual write có thể tạo divergence

Nếu app thực hiện hai statements riêng, statement đầu thành công nhưng statement sau fail, hai cột có thể lệch nếu không nằm trong cùng transaction. Nếu retries không idempotent, có thể ghi đè giá trị mới bằng dữ liệu cũ.

Ưu tiên một statement/transaction có cả hai values, hoặc dùng trigger đồng bộ. Ghi metrics đếm mismatch và alert khi xuất hiện.

### 5.6. Trigger làm compatibility bridge

Trigger có thể đồng bộ writes từ phiên bản app cũ chỉ biết cột cũ. Ví dụ trong phase cột cũ authoritative:

~~~sql
CREATE OR REPLACE FUNCTION public.sync_customer_code_v2()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.customer_code IS NOT NULL THEN
            NEW.customer_code_v2 := NEW.customer_code::bigint;
        END IF;
    ELSIF NEW.customer_code IS DISTINCT FROM OLD.customer_code THEN
        NEW.customer_code_v2 := NEW.customer_code::bigint;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER customers_sync_code_v2
BEFORE INSERT OR UPDATE OF customer_code
ON public.customers
FOR EACH ROW
EXECUTE FUNCTION public.sync_customer_code_v2();
~~~

Trigger này minh họa chiều old-to-new. Cần điều chỉnh INSERT behavior nếu application có thể chỉ gửi cột mới, và kiểm tra invalid input trước khi cast. Tránh dùng trigger hai chiều mơ hồ khi cả hai columns có thể thay đổi cùng một statement.

### 5.7. Trigger và dual write cùng tồn tại

Nếu app bridge đã ghi cả hai cột nhưng trigger vẫn xem cột cũ authoritative, trigger có thể ghi đè giá trị v2 từ conversion cột cũ. Điều này chỉ an toàn nếu conversion deterministic và hai values phải bằng nhau. Nên định nghĩa rõ conflict rule, kiểm tra parity và test trigger cùng tất cả app versions.

### 5.8. Chuyển hướng đồng bộ sau cutover

Trong rollback window, có thể đổi trigger để cột mới authoritative và cập nhật cột cũ từ cột mới. Thực hiện thay đổi trigger trong rollout có kiểm soát; xác nhận app cũ đã bị drain hoặc cột cũ vẫn được cập nhật chính xác trước khi cho phép rollback.

### 5.9. Tránh trigger recursion và hidden side effects

Trigger chạy trong transaction của write và có thể tăng latency/WAL. Tránh trigger gọi lại chính nó, tạo nhiều writes không cần thiết hoặc gây recursion qua trigger khác. Kiểm tra ordering, `WHEN` conditions và behavior khi bulk load/replication.

### 5.10. Logical replication và CDC

Shadow column/trigger có thể tương tác với publication column lists, replica identity, subscriber schema và CDC consumers. Kiểm tra schema compatibility hai phía; logical replication không tự động biến đổi mọi type theo mapping mong muốn.

## 6. Backfill dữ liệu theo batch

### 6.1. Backfill là gì?

Backfill là quá trình điền giá trị cho cột mới từ dữ liệu cũ hoặc nguồn khác sau khi schema đã mở rộng. Với table lớn, nên chia thành các transaction nhỏ để giảm lock duration, WAL burst, rollback cost và replication lag.

### 6.2. Điều kiện tiên quyết

Trước khi chạy:

- Có stable primary key hoặc cơ chế xác định row;
- Có source-of-truth và conversion expression rõ;
- Writes mới đã được đồng bộ;
- Có index hỗ trợ tìm rows chưa backfill nếu cần;
- Có batch size/rate limit;
- Có metrics và stop conditions;
- Có cách resume sau crash.

### 6.3. Backfill idempotent

Điều kiện `WHERE new_column IS NULL` giúp batch chỉ xử lý rows chưa có giá trị mới. Nếu job chạy lại sau lỗi, các rows đã hoàn tất được bỏ qua.

### 6.4. Batch bằng primary key

Ví dụ dùng primary key `id`:

~~~sql
WITH batch AS (
    SELECT id
    FROM public.customers
    WHERE customer_code_v2 IS NULL
      AND customer_code IS NOT NULL
    ORDER BY id
    LIMIT 1000
    FOR UPDATE SKIP LOCKED
)
UPDATE public.customers AS c
SET customer_code_v2 = c.customer_code::bigint
FROM batch
WHERE c.id = batch.id
  AND c.customer_code_v2 IS NULL
RETURNING c.id;
~~~

Mỗi lần thực thi là một batch; commit transaction rồi mới chạy batch tiếp theo. `SKIP LOCKED` cho phép nhiều workers tránh chờ cùng row nhưng có thể bỏ qua rows đang bị khóa; lặp lại các vòng sau để xử lý phần còn lại.

### 6.5. Vì sao không dùng OFFSET?

`OFFSET` lớn buộc PostgreSQL đi qua nhiều rows trước khi tới batch tiếp theo, làm chi phí tăng dần. Dùng keyset pagination (`id > last_id`) hoặc `WHERE new_column IS NULL` với index phù hợp.

### 6.6. Keyset pagination

Một worker đơn có thể giữ cursor logic:

~~~sql
WITH batch AS (
    SELECT id
    FROM public.customers
    WHERE id > :last_id
      AND customer_code_v2 IS NULL
    ORDER BY id
    LIMIT 1000
)
UPDATE public.customers AS c
SET customer_code_v2 = c.customer_code::bigint
FROM batch
WHERE c.id = batch.id
  AND c.customer_code_v2 IS NULL
RETURNING c.id;
~~~

`:last_id` là placeholder của client/job runner, không phải cú pháp bind variable native của SQL server. Chỉ tăng cursor sau khi batch commit thành công. Nếu rows bị skip do concurrent changes, cần một pass reconciliation cuối.

### 6.7. Batch bằng ctid

Khi chưa có primary key, có thể dùng `ctid` trong một statement ngắn:

~~~sql
WITH batch AS (
    SELECT ctid
    FROM public.legacy_records
    WHERE new_value IS NULL
    LIMIT 500
    FOR UPDATE SKIP LOCKED
)
UPDATE public.legacy_records AS t
SET new_value = convert_value(t.old_value)
FROM batch
WHERE t.ctid = batch.ctid;
~~~

`ctid` chỉ ổn định trong phạm vi row version hiện tại; UPDATE/VACUUM FULL/rewrites có thể thay đổi nó. Không lưu `ctid` làm checkpoint lâu dài. Với table lớn, nên có stable key để resume/parallelize đáng tin cậy.

### 6.8. Chọn batch size

Batch nhỏ giảm transaction duration và WAL burst nhưng tăng số round trips/overhead. Batch lớn tăng throughput nhưng có thể gây lock contention, replica lag, autovacuum pressure và rollback lâu. Bắt đầu nhỏ, đo latency/lag và điều chỉnh từ từ.

### 6.9. Nghỉ giữa batches

Job runner có thể pause ngắn giữa batches hoặc rate-limit theo rows/second/WAL bytes. Dùng adaptive throttling: giảm tốc khi replication lag, disk latency hoặc application p95 vượt threshold; tăng lại khi hệ thống ổn định.

### 6.10. Không giữ transaction xuyên suốt backfill

Mỗi batch nên commit riêng. Một transaction kéo dài giữ snapshots, làm vacuum không reclaim tuples, giữ locks và tăng rollback cost. Tránh mở một transaction rồi cập nhật hàng triệu rows qua nhiều vòng.

### 6.11. Concurrent writes trong lúc backfill

Nếu application tiếp tục update source column, cần trigger/dual-write để shadow column nhận giá trị mới. Backfill chỉ lấp các rows còn thiếu; không được ghi đè giá trị mới hơn bằng giá trị đọc từ snapshot cũ.

### 6.12. Race condition

Row locking trong batch cùng điều kiện `new_column IS NULL` giúp giảm overwrite race. Tuy nhiên, logic source-of-truth và trigger vẫn cần đúng. Test tình huống update/delete đồng thời, retry sau deadlock và hai backfill workers cùng chạy.

### 6.13. Rows không thể convert

Tách rows lỗi thành exception set/report. Không lặp lại cùng một batch lỗi vô hạn. Ghi primary key, reason code và remediation; sửa dữ liệu theo business approval rồi cho job chạy lại.

### 6.14. Progress tracking

Ghi mỗi batch:

- Run ID và worker ID;
- First/last key;
- Rows scanned/updated/skipped/failed;
- Duration;
- WAL/replication lag;
- Current throughput;
- Timestamp và error details.

Đếm rows còn thiếu bằng query có thể tốn scan; không chạy `count(*)` toàn table mỗi vài giây. Lấy snapshot thưa hơn hoặc dùng partition/key ranges và progress checkpoint.

### 6.15. Parallel workers

Có thể chạy nhiều workers với `FOR UPDATE SKIP LOCKED`, nhưng phải giới hạn tổng concurrency. Thêm workers không đảm bảo throughput tăng tuyến tính; có thể gây random I/O, lock waits, WAL saturation và contention.

### 6.16. Backfill theo partition

Với partitioned table, xử lý từng leaf partition theo thứ tự ưu tiên. Điều này giúp giới hạn blast radius, đo thời gian từng partition và pause giữa partitions. Kiểm tra parent/child schema consistency và partition attach behavior.

## 7. Kiểm soát lock và tác động lên production

### 7.1. Hiểu lock trước khi chạy DDL

PostgreSQL lock table được giữ tới hết transaction. Một lệnh DDL có thể đợi lock hiện tại; sau khi đã xếp hàng, các statements mới cũng có thể bị ảnh hưởng bởi lock queue. DDL ngắn nhưng chờ lâu vẫn có thể gây queueing.

### 7.2. Preflight lock inspection

~~~sql
SELECT
    a.pid,
    a.usename,
    a.application_name,
    a.state,
    a.xact_start,
    now() - a.xact_start AS xact_age,
    l.locktype,
    l.mode,
    l.granted,
    l.relation::regclass AS relation,
    a.wait_event_type,
    a.wait_event,
    left(a.query, 250) AS query
FROM pg_locks AS l
JOIN pg_stat_activity AS a ON a.pid = l.pid
WHERE l.relation = 'public.customers'::regclass
ORDER BY l.granted, a.xact_start NULLS LAST;
~~~

Query này tập trung vào relation cụ thể; locks có thể liên quan transaction ID, virtual transaction, database hoặc object khác. Dùng `pg_blocking_pids()` để tìm blockers trực tiếp.

### 7.3. lock_timeout

Đặt `lock_timeout` để DDL fail nhanh nếu không lấy được lock trong budget:

~~~sql
BEGIN;
SET LOCAL lock_timeout = '2s';
ALTER TABLE public.customers
ADD COLUMN customer_code_v2 bigint;
COMMIT;
~~~

Nếu timeout, transaction bị lỗi và cần rollback/đóng transaction trước khi retry. Retry với backoff ở maintenance window, không loop liên tục tạo lock queue.

### 7.4. statement_timeout

`statement_timeout` giới hạn thời gian chạy statement, khác `lock_timeout` (chỉ giới hạn thời gian chờ lock). Chọn timeout theo expected duration, table size và rollback cost. Một rewrite lớn bị cancel có thể cần thời gian rollback và tạo thêm load.

### 7.5. DDL lock queue

Nếu DDL chờ lock, xác định transaction đang giữ lock, tuổi transaction, application owner và query. Một session `idle in transaction` có thể giữ lock dù không chạy query. Đừng terminate blocker tự động nếu chưa biết business impact.

### 7.6. Lock timeout không loại bỏ mọi tác động

Sau khi lấy lock, operation vẫn có thể gây I/O, WAL và cache pressure. `lock_timeout` chỉ kiểm soát bước chờ lock, không giới hạn thời gian rewrite hoặc tài nguyên tiêu thụ.

### 7.7. Chọn DDL metadata-only

Ưu tiên các thay đổi nhanh như add nullable column không default khi phù hợp. Dù vậy, metadata changes vẫn cần lock catalog/relation trong một khoảng ngắn và có thể chờ transaction dài. Dùng lock timeout ngắn để tránh chờ vô hạn.

### 7.8. Default khi thêm cột

Các PostgreSQL versions hiện đại có thể thêm cột với constant immutable default mà không rewrite từng row trong nhiều trường hợp (từ PostgreSQL 11). Nhưng volatile defaults hoặc các tình huống đặc biệt có thể yêu cầu rewrite. Kiểm tra version và thử nghiệm; không áp dụng giả định này cho mọi default.

### 7.9. Thay đổi type trực tiếp

Trước direct type change, thử trên staging với bản sao có data volume, indexes, constraints và workload tương đương. Đo lock duration, rewrite duration, WAL generated, disk peak và replica catch-up time.

### 7.10. Tránh nhiều DDL cùng lúc

Các DDL trên cùng relation có thể xung đột locks; trên relations khác nhau vẫn cạnh tranh catalog locks, I/O và WAL. Serialize các schema migrations có impact lớn và đặt migration coordinator.

## 8. Constraints và indexes trong staged migration

### 8.1. Add CHECK NOT VALID

Có thể thêm check constraint mà chưa scan/validate toàn bộ dữ liệu:

~~~sql
ALTER TABLE public.customers
ADD CONSTRAINT customers_code_v2_not_null
CHECK (customer_code_v2 IS NOT NULL) NOT VALID;
~~~

Constraint được enforce cho các rows mới/được cập nhật sau khi add, còn dữ liệu cũ chưa được chứng minh. Backfill các rows cũ rồi validate.

### 8.2. Validate constraint

~~~sql
ALTER TABLE public.customers
VALIDATE CONSTRAINT customers_code_v2_not_null;
~~~

Validation scan dữ liệu hiện có và dùng lock nhẹ hơn so với một số thao tác DDL mạnh; vẫn tiêu thụ I/O và cần theo dõi workload. Nếu validation fail, tìm rows vi phạm và sửa trước khi thử lại.

### 8.3. Đặt NOT NULL

Sau khi dữ liệu đã đầy đủ và check constraint được validated, có thể đặt `NOT NULL`:

~~~sql
ALTER TABLE public.customers
ALTER COLUMN customer_code_v2 SET NOT NULL;
~~~

PostgreSQL có thể dùng check constraint đã validate để tránh scan lại trong các versions/điều kiện hỗ trợ, nhưng lệnh vẫn cần lock mạnh ngắn để cập nhật catalog. Xác nhận behavior theo version và đặt lock timeout.

### 8.4. Foreign key NOT VALID

~~~sql
ALTER TABLE public.order_items
ADD CONSTRAINT order_items_customer_v2_fk
FOREIGN KEY (customer_id_v2)
REFERENCES public.customers(customer_code_v2)
NOT VALID;

ALTER TABLE public.order_items
VALIDATE CONSTRAINT order_items_customer_v2_fk;
~~~

Referenced key phải có unique/primary key phù hợp. Dùng pattern này để tách thời điểm add constraint khỏi scan validation, đồng thời theo dõi lock/I/O.

### 8.5. Unique index concurrent

Tạo unique index trên shadow column:

~~~sql
CREATE UNIQUE INDEX CONCURRENTLY customers_code_v2_uidx
ON public.customers (customer_code_v2);
~~~

Unique index build concurrent vẫn kiểm tra uniqueness trong quá trình build và có thể fail nếu duplicates xuất hiện. Xử lý duplicates trước; kiểm tra index validity sau operation.

### 8.6. Attach unique constraint

Khi unique index hợp lệ và đáp ứng điều kiện, có thể gắn nó thành constraint:

~~~sql
ALTER TABLE public.customers
ADD CONSTRAINT customers_code_v2_key
UNIQUE USING INDEX customers_code_v2_uidx;
~~~

Thao tác attach cần lock; đặt `lock_timeout`, chạy trong window và kiểm tra tên/ownership/index compatibility.

### 8.7. Index cho backfill

Nếu backfill chọn rows theo `id` range, primary key thường đã có index. Nếu chọn `WHERE new_column IS NULL`, một partial index có thể hỗ trợ:

~~~sql
CREATE INDEX CONCURRENTLY customers_v2_missing_idx
ON public.customers (id)
WHERE customer_code_v2 IS NULL;
~~~

Partial index làm tăng write/space overhead trong suốt migration. Sau backfill có thể drop index này concurrent nếu không còn mục đích.

### 8.8. Foreign keys và type compatibility

Khi đổi type khóa tham chiếu, cập nhật cả parent/child columns theo trình tự tương thích. PostgreSQL yêu cầu types/operators phù hợp cho foreign key; không cutover một phía trong khi phía còn lại chưa tương thích.

### 8.9. Partitioned indexes

Với partitioned tables, index build/attach có các hạn chế và quy trình riêng theo version. Có thể build indexes trên từng partition concurrently rồi attach vào partitioned index theo hướng dẫn PostgreSQL. Xác minh toàn bộ partitions có index tương ứng trước cutover.

## 9. Validation và data parity

### 9.1. Kiểm tra số rows còn thiếu

~~~sql
SELECT count(*) AS missing_rows
FROM public.customers
WHERE customer_code IS NOT NULL
  AND customer_code_v2 IS NULL;
~~~

Query count toàn table có thể tốn thời gian. Chạy trong window phù hợp, dùng partition/range summaries hoặc checkpoints để theo dõi thường xuyên.

### 9.2. Kiểm tra mismatch

~~~sql
SELECT
    count(*) AS compared_rows,
    count(*) FILTER (
        WHERE customer_code_v2 IS DISTINCT FROM customer_code::bigint
    ) AS mismatch_rows
FROM public.customers
WHERE customer_code IS NOT NULL;
~~~

Chỉ chạy khi mọi source values có thể cast. Với mapping phức tạp, dùng cùng một deterministic conversion function cho backfill và validation để tránh hai định nghĩa khác nhau.

### 9.3. Null parity

~~~sql
SELECT
    count(*) FILTER (
        WHERE customer_code IS NULL AND customer_code_v2 IS NOT NULL
    ) AS unexpected_new_values,
    count(*) FILTER (
        WHERE customer_code IS NOT NULL AND customer_code_v2 IS NULL
    ) AS missing_new_values
FROM public.customers;
~~~

Null semantics phải theo business contract. Có trường hợp cột mới được phép null dù cột cũ không null hoặc ngược lại; quy tắc phải được ghi rõ.

### 9.4. Range và domain validation

Kiểm tra min/max, invalid values, duplicates, allowed ranges và conversion loss. Với decimal/timezone/JSON, validation cần so sánh theo semantics chứ không chỉ so sánh text representation.

### 9.5. Sample validation

Lấy sample theo key ranges, recent rows và hot partitions để kiểm tra conversion. Sample hữu ích để phát hiện lỗi sớm nhưng không thay thế full validation trước contract.

### 9.6. Constraint validation

Xác nhận constraints ở trạng thái validated, index `indisvalid`/`indisready`, foreign keys và unique semantics. Ghi kết quả validation cùng migration run ID.

### 9.7. Application validation

Chạy smoke/integration tests trên phiên bản bridge/new:

- Insert mới;
- Update cột nguồn;
- Update cột đích;
- Null values;
- Boundary values;
- Retry sau timeout;
- Concurrent updates;
- Read path và serialization;
- Reports/ETL/CDC consumers.

### 9.8. Query plan validation

Sau khi tạo index mới hoặc đổi type, so sánh `EXPLAIN (ANALYZE, BUFFERS)` trên representative queries ở staging/canary. Type/operator changes có thể làm planner chọn plan khác; không chỉ kiểm tra index tồn tại.

### 9.9. Count parity không đủ

Hai cột có cùng số non-NULL rows nhưng values vẫn có thể khác nhau. Kết hợp mismatch count, range, checksums/hash theo key ranges, constraints và business invariants.

### 9.10. Validation snapshot

Chạy validation trong transaction/snapshot phù hợp để tránh đếm các trạng thái thay đổi giữa nhiều queries. Với bảng ghi liên tục, dùng trigger/dual-write để duy trì parity rồi lặp validation đến khi mismatch bằng zero hoặc nằm trong policy.

## 10. Cutover và contract

### 10.1. Read cutover

Chuyển reads sang cột mới trước, có thể qua feature flag/canary. Giữ writes đồng bộ và so sánh output giữa old/new paths trong thời gian quan sát.

### 10.2. Write cutover

Sau khi read path ổn định, chuyển cột mới thành source of truth. Xác nhận tất cả writers đã deploy bridge/new version: API, batch jobs, admin scripts, ETL, triggers và integrations.

### 10.3. Shadow reads

Có thể thực hiện shadow reads: truy vấn cả logic cũ và mới, so sánh kết quả nhưng chỉ trả response từ path authoritative. Không để shadow query làm tăng tải vượt budget.

### 10.4. Canary rollout

Chuyển một phần traffic hoặc một nhóm tenant trước. Theo dõi mismatch, errors, latency, lock waits, replica lag và support tickets. Chỉ tăng traffic khi acceptance criteria đạt.

### 10.5. Rollback window

Trong khoảng này:

- Giữ cột cũ;
- Duy trì reverse sync nếu cần rollback app cũ;
- Lưu metrics parity;
- Không xóa index/constraint cũ;
- Xác nhận restore point/backup;
- Ghi điều kiện kết thúc rollback window.

### 10.6. Contract checklist

Trước khi drop cột cũ:

- Không còn app versions đọc/ghi cột cũ;
- Không còn jobs/reports/CDC consumers phụ thuộc;
- Read/write metrics chứng minh usage bằng zero trong thời gian đủ dài;
- Data parity/validation đã hoàn tất;
- Backup/restore path đã kiểm tra;
- Owner/business sign-off;
- Drop operation có lock timeout và rollback/recovery plan.

### 10.7. Drop old column

~~~sql
ALTER TABLE public.customers
DROP COLUMN customer_code;
~~~

Drop column thường cập nhật catalog và không lập tức thu hồi toàn bộ file space; việc reclaim physical space có thể cần rewrite/maintenance khác. Nó vẫn cần lock mạnh ngắn và có thể chờ transaction. Thực hiện riêng trong một migration contract sau khi hết phụ thuộc.

### 10.8. Rename không phải bước cutover an toàn duy nhất

Rename cột cũ/mới có thể làm code đang chạy lỗi ngay lập tức. Trong rolling deployment, tên cột là API contract của database. Chỉ rename sau khi mọi consumers đã tương thích và deployment order được kiểm soát.

## 11. Monitoring tác động trong migration

### 11.1. Baseline trước migration

Ghi lại ít nhất:

- Query latency p50/p95/p99 và error rate;
- Transaction throughput và connection count;
- CPU, memory, disk IOPS/latency/throughput;
- Table/index sizes và free disk;
- WAL generation rate;
- Replication send/write/flush/replay lag;
- Archive success/failure và retained WAL;
- Long-running transactions và lock waits;
- Backup age và restore readiness.

Không có baseline thì khó phân biệt migration impact với workload bình thường.

### 11.2. Theo dõi lock waits

~~~sql
SELECT
    pid,
    usename,
    application_name,
    state,
    wait_event_type,
    wait_event,
    xact_start,
    query_start,
    now() - query_start AS query_age,
    pg_blocking_pids(pid) AS blocking_pids,
    left(query, 300) AS query
FROM pg_stat_activity
WHERE array_length(pg_blocking_pids(pid), 1) > 0
ORDER BY query_start;
~~~

### 11.3. Theo dõi replication lag

~~~sql
SELECT
    application_name,
    state,
    sync_state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn,
    write_lag,
    flush_lag,
    replay_lag
FROM pg_stat_replication;
~~~

Kết hợp lag time với LSN distance, WAL generation và workload. Lag columns có thể NULL/không phản ánh chính xác khi không có WAL mới; đừng dùng một cột làm RPO tuyệt đối.

### 11.4. Theo dõi WAL archive

~~~sql
SELECT
    archived_count,
    last_archived_wal,
    last_archived_time,
    failed_count,
    last_failed_wal,
    last_failed_time
FROM pg_stat_archiver;
~~~

Migration lớn có thể tạo WAL burst. Nếu archive failures tăng hoặc disk headroom giảm nhanh, giảm backfill rate hoặc pause job.

### 11.5. Theo dõi replication slots

~~~sql
SELECT
    slot_name,
    slot_type,
    active,
    restart_lsn,
    confirmed_flush_lsn,
    wal_status,
    safe_wal_size
FROM pg_replication_slots
ORDER BY slot_name;
~~~

`wal_status`/`safe_wal_size` phụ thuộc major version. Kiểm tra columns trước khi dùng query trên server cũ. Không drop slot để giải phóng disk nếu chưa hiểu consumer và hậu quả standby/CDC phải reinitialize.

### 11.6. Theo dõi backfill throughput

Đo rows updated mỗi batch, bytes/WAL theo thời gian và thời gian batch. Nếu throughput giảm dần, kiểm tra index scan cost, dead tuples, I/O, lock waits và autovacuum.

### 11.7. Theo dõi disk

Rewrite/backfill có thể làm tăng table/index/WAL/temp usage. Lấy filesystem free space từ OS/cloud monitoring; PostgreSQL relation size functions không thể thay thế số liệu volume.

### 11.8. Theo dõi autovacuum

Backfill UPDATE tạo dead tuples. Kiểm tra `pg_stat_progress_vacuum`, `pg_stat_user_tables.n_dead_tup`, autovacuum logs và transaction age. Không tắt autovacuum trong suốt migration nếu không có kế hoạch kiểm soát rõ.

### 11.9. Theo dõi query plans

Backfill có thể cạnh tranh với application queries; index mới hoặc type change có thể thay đổi plans. So sánh representative `EXPLAIN (ANALYZE, BUFFERS)` và query latency trước/sau ở staging/canary.

### 11.10. Stop conditions

Định nghĩa trước các điều kiện pause/abort:

- Application p95/p99 vượt error budget;
- Lock wait ảnh hưởng transactions quan trọng;
- Replication lag vượt RPO budget;
- WAL archive backlog tăng liên tục;
- Disk free dưới reserve;
- CPU/I/O saturation kéo dài;
- Mismatch hoặc conversion errors vượt policy;
- Backfill không tiến triển hoặc tạo deadlocks liên tục.

### 11.11. Adaptive throttling

Không nhất thiết chạy backfill ở tốc độ tối đa. Điều chỉnh batch size, delay và worker count dựa trên các metrics. Ví dụ: nếu lag tăng, giảm batch frequency; nếu latency ổn định và lag thấp, tăng dần trong giới hạn đã test.

## 12. Migration state và automation

### 12.1. Lưu trạng thái migration

Một bảng điều phối có thể ghi:

~~~sql
CREATE SCHEMA IF NOT EXISTS ops;

CREATE TABLE IF NOT EXISTS ops.schema_migration_progress (
    migration_key text PRIMARY KEY,
    phase text NOT NULL,
    last_processed_id bigint,
    rows_processed bigint NOT NULL DEFAULT 0,
    rows_failed bigint NOT NULL DEFAULT 0,
    started_at timestamptz,
    updated_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz,
    detail jsonb NOT NULL DEFAULT '{}'::jsonb
);
~~~

Lưu checkpoint sau mỗi batch commit. Nếu có nhiều workers, dùng bảng job/range riêng hoặc atomic claim để tránh các workers ghi đè checkpoint chung.

### 12.2. Job runner pseudocode

~~~text
while migration is not paused:
    check stop conditions
    begin a short transaction
    claim one key range or batch
    update only rows that still need backfill
    record rows updated
    commit
    persist checkpoint
    sample replication lag, latency and disk headroom
    adjust batch size or sleep
    if no rows were found:
        run a reconciliation pass
        stop only when validation says complete
~~~

Đây là logic điều phối, không phải script hoàn chỉnh. Xử lý lỗi transaction, deadlock retry, process restart, checkpoint consistency và secrets trong implementation thực tế.

### 12.3. Atomic checkpoint

Nếu checkpoint được lưu trong cùng database, cập nhật progress row trong cùng transaction với batch update để tránh đánh dấu hoàn tất trước khi data commit. Nếu checkpoint ở external queue/store, thiết kế at-least-once execution và đảm bảo batch idempotent.

### 12.4. Advisory lock cho một migration

Session-level advisory lock có thể ngăn hai orchestrators cùng chạy một migration:

~~~sql
SELECT pg_try_advisory_lock(573001::bigint);
~~~

Nếu không lấy được lock, runner nên thoát hoặc chờ theo policy. Giữ cùng session connection suốt job và release lock khi hoàn tất. Advisory lock không ngăn một người dùng khác chạy DDL trực tiếp.

### 12.5. Retry deadlocks

Batch transaction có thể gặp deadlock với application writes. Retry transaction bị deadlock với exponential backoff/jitter, giới hạn attempts và metrics. Giữ batches ngắn và nhất quán về thứ tự row/key để giảm deadlocks.

### 12.6. Resume sau crash

Khi runner restart:

1. Đọc migration phase/checkpoint;
2. Xác định batch cuối đã commit;
3. Kiểm tra schema/trigger/index state;
4. Chạy lại batch idempotent;
5. Reconcile toàn bộ rows còn thiếu;
6. Tiếp tục validation.

Không giả định process exit đồng nghĩa database transaction đã rollback nếu client disconnect trong lúc COMMIT.

### 12.7. Dry run

Dry run nên kiểm tra counts, conversion failures, dependency inventory, estimated rows/bytes, lock requirements và plan. Nó không thực thi write operations; không coi dry run là bằng chứng runtime chính xác.

### 12.8. Canary batch

Bắt đầu bằng một range nhỏ hoặc một partition, xác nhận conversion/parity/latency/WAL impact rồi mới mở rộng. Lưu metrics của canary để chọn batch size cho phần còn lại.

## 13. Rollback, recovery và failure handling

### 13.1. Phân loại rollback theo phase

| Phase | Rollback option | Rủi ro |
| --- | --- | --- |
| Expand | Drop cấu trúc mới nếu chưa có consumer | DDL lock và dependencies |
| Bridge deploy | Roll back application nếu schema vẫn tương thích | App rollback có thể để lại dual-write behavior |
| Backfill | Pause/resume; giữ shadow data hoặc xóa có chủ đích | Không nên reverse từng batch nếu không cần |
| Validation | Sửa dữ liệu và chạy lại | Cần giữ source of truth |
| Read cutover | Chuyển reads về cột cũ nếu parity/sync còn tốt | Cột cũ có thể stale |
| Write cutover | Reverse sync hoặc roll-forward | Dữ liệu mới có thể không chuyển ngược lossless |
| Contract | Restore từ backup/PITR hoặc rebuild cột | Drop column khó rollback nhanh |

### 13.2. Direct ALTER rollback

DDL PostgreSQL thường transactional: nếu `ALTER COLUMN TYPE` fail trong transaction, thay đổi chưa commit sẽ rollback. Nhưng sau khi commit, đổi ngược là một migration mới và có thể rewrite lại table; không phải thao tác undo miễn phí.

### 13.3. Backfill rollback

Với shadow column, có thể giữ dữ liệu mới và pause migration. Xóa shadow column không cần thiết nếu muốn điều tra hoặc thử lại. Nếu conversion làm mất dữ liệu, không thể phục hồi thông tin đã mất chỉ bằng cách cast ngược.

### 13.4. Dual-write mismatch

Nếu mismatch xuất hiện:

1. Pause cutover/backfill;
2. Xác định cột authoritative;
3. Phân loại rows bị lệch và nguyên nhân;
4. Kiểm tra trigger/app version/retry race;
5. Sửa logic đồng bộ;
6. Reconcile dữ liệu;
7. Chạy validation lại trước khi tiếp tục.

Không tự động copy một chiều toàn bộ rows khi chưa xác định bên nào chứa giá trị đúng.

### 13.5. Backfill tạo replication lag

Giảm worker count/batch size hoặc pause. Xử lý bottleneck ở standby/network/storage/archive, chờ lag giảm rồi resume. Nếu slot giữ WAL làm disk gần đầy, ưu tiên bảo vệ primary disk và giữ đúng WAL cần thiết cho recovery.

### 13.6. Disk pressure

Pause write-heavy migration trước khi volume hết chỗ. Xác định growth ở heap, index, WAL, temp hay backup. Mở rộng volume hoặc chuyển maintenance plan; không xóa file trong data directory/pg_wal bằng filesystem command.

### 13.7. Lock queue/outage

Nếu DDL waiter gây queue:

- Xác định PID DDL và blockers;
- Hủy DDL waiter nếu cần giảm queue;
- Xử lý transaction giữ lock theo incident policy;
- Xác nhận application requests phục hồi;
- Lên lịch lại với lock timeout ngắn và preflight.

### 13.8. Conversion errors

Ghi primary key và invalid value vào error report có kiểm soát access. Sửa source theo business rule hoặc tạo mapping table được phê duyệt. Chạy lại các rows lỗi và kiểm tra không mất/nhầm dữ liệu.

### 13.9. Application incompatibility

Nếu app version mới lỗi, chuyển feature flag về path cũ khi còn đồng bộ. Nếu schema đã contract, có thể cần roll-forward hoặc restore; không giả định deploy app cũ sẽ hoạt động với schema mới.

### 13.10. Khi nào chọn roll-forward

Sau khi new column đã authoritative và reverse mapping không lossless, roll-forward fix thường an toàn hơn rollback data. Giữ cột cũ cho đến khi business sign-off và rollback window kết thúc.

## 14. Ví dụ end-to-end: text ID sang bigint

Tình huống: bảng `customers` có 80 triệu rows. Cột `customer_code` hiện là text chứa chuỗi số; ứng dụng muốn dùng bigint để giảm cast và chuẩn hóa API. Hệ thống cần tiếp tục nhận writes trong migration.

### 14.1. Preflight

Đếm giá trị không hợp lệ:

~~~sql
SELECT
    count(*) AS total_rows,
    count(*) FILTER (WHERE customer_code IS NULL) AS null_rows,
    count(*) FILTER (
        WHERE customer_code IS NOT NULL
          AND customer_code !~ '^[0-9]+$'
    ) AS invalid_rows
FROM public.customers;
~~~

Kiểm tra range và xác nhận mọi value phù hợp bigint. Xem dependencies, indexes, constraints, views, CDC, application versions và query plans. Đo disk/WAL/replication baseline.

### 14.2. Expand schema

~~~sql
SET lock_timeout = '2s';

ALTER TABLE public.customers
ADD COLUMN customer_code_v2 bigint;
~~~

Lệnh cần lock catalog/relation ngắn. Nếu không lấy được lock trong budget, statement fail; retry sau khi xác định blockers.

### 14.3. Triển khai compatibility bridge

Deploy application version có thể đọc old column và ghi old/new values trong cùng transaction. Cài trigger old-to-new cho các writers cũ chưa được nâng cấp. Trong phase này old column vẫn là source of truth.

### 14.4. Backfill batch

Chạy batch 1.000–5.000 rows làm điểm bắt đầu, điều chỉnh theo latency/lag:

~~~sql
WITH batch AS (
    SELECT id
    FROM public.customers
    WHERE customer_code_v2 IS NULL
      AND customer_code IS NOT NULL
    ORDER BY id
    LIMIT 2000
    FOR UPDATE SKIP LOCKED
)
UPDATE public.customers AS c
SET customer_code_v2 = c.customer_code::bigint
FROM batch
WHERE c.id = batch.id
  AND c.customer_code_v2 IS NULL;
~~~

Commit mỗi batch. Job runner ghi checkpoint/rows updated, delay giữa batches và pause khi stop conditions xuất hiện. Chạy reconciliation pass cho rows bị skip.

### 14.5. Validate completeness và parity

~~~sql
SELECT count(*) AS missing_rows
FROM public.customers
WHERE customer_code IS NOT NULL
  AND customer_code_v2 IS NULL;

SELECT count(*) AS mismatches
FROM public.customers
WHERE customer_code IS NOT NULL
  AND customer_code_v2 IS DISTINCT FROM customer_code::bigint;
~~~

Đồng thời kiểm tra null semantics, min/max, duplicate values và business constraints.

### 14.6. Tạo index/constraint mới

~~~sql
CREATE UNIQUE INDEX CONCURRENTLY customers_code_v2_uidx
ON public.customers (customer_code_v2);
~~~

Nếu cần unique constraint, attach index hợp lệ bằng `UNIQUE USING INDEX`. Theo dõi progress, locks, disk và WAL. Nếu unique build fail do duplicates, giải quyết duplicates theo business rule trước.

### 14.7. Cutover reads

Deploy code đọc `customer_code_v2` cho canary tenants hoặc tỷ lệ traffic nhỏ. Shadow compare old/new results, theo dõi latency/errors và data parity. Mở rộng khi acceptance criteria đạt.

### 14.8. Cutover writes

Chuyển source of truth sang bigint. Trong rollback window, giữ reverse sync sang text nếu cần app cũ có thể hoạt động. Xác nhận không còn writer cũ và mọi downstream consumers đã chuyển.

### 14.9. Contract

Sau khi usage cột cũ bằng zero trong thời gian quan sát và business sign-off:

- Drop trigger cũ;
- Drop indexes/constraints cũ sau khi xác minh dependencies;
- Drop cột text cũ trong migration riêng;
- Xóa code compatibility;
- Cập nhật schema docs/ORM/CDC contracts.

### 14.10. Post-check

Đo query plans, p95/p99, table/index size, WAL/archive, replication lag, dead tuples và backup duration. Ghi actual migration duration, rows/sec, error count và lessons learned.

## 15. Ví dụ: integer sang bigint

### 15.1. Direct conversion

Với table nhỏ/maintenance window:

~~~sql
ALTER TABLE public.invoice_items
ALTER COLUMN legacy_id TYPE bigint
USING legacy_id::bigint;
~~~

Đánh giá table rewrite/lock/index impact theo version. Không mặc định đây là metadata-only chỉ vì mọi giá trị integer đều nằm trong range bigint.

### 15.2. Staged conversion

Với table lớn, thêm `legacy_id_bigint`, đồng bộ writes, backfill theo primary key, tạo index concurrent, validate constraints, chuyển application rồi contract. Cách này tốn thêm thời gian và storage nhưng giới hạn lock dài.

### 15.3. Sequence/identity

Nếu cột là serial/identity, kiểm tra sequence type, sequence ownership, default expression, sequence current value và application assumptions. Chỉ đổi column type không đảm bảo sequence đã được điều chỉnh đúng cho range mới.

## 16. Ví dụ: text timestamp sang timestamptz

### 16.1. Xác định timezone nguồn

Nếu text chứa offset, có thể parse thành instant. Nếu text không có timezone, phải biết timezone business/source trước khi cast.

~~~sql
SELECT
    raw_timestamp,
    raw_timestamp::timestamptz
FROM public.event_import
WHERE raw_timestamp IS NOT NULL
LIMIT 20;
~~~

Kết quả hiển thị phụ thuộc session timezone; lưu ý semantics instant khác với wall-clock local time.

### 16.2. Shadow column

~~~sql
ALTER TABLE public.event_import
ADD COLUMN occurred_at_v2 timestamptz;
~~~

Backfill dùng conversion expression đã được kiểm tra và xử lý invalid strings vào error set. Nếu input thiếu timezone, gắn timezone business rõ ràng trong expression thay vì dựa ngầm vào session setting.

### 16.3. Validation

So sánh theo instant/epoch và kiểm tra boundary values quanh daylight-saving transitions nếu nguồn có local times. Kiểm tra API serialization, reporting timezone và partition bounds.

## 17. Ví dụ: JSON sang JSONB

### 17.1. Kiểm tra JSON validity

Nếu cột đã là type `json`, values hợp lệ theo JSON parser. Nếu là text, cần xác định cách phát hiện invalid input trước conversion. Có thể dùng staging table hoặc function try-cast được kiểm soát; không dùng cast trực tiếp trên dữ liệu chưa xác minh.

### 17.2. Chuyển đổi

Với table nhỏ:

~~~sql
ALTER TABLE public.audit_events
ALTER COLUMN payload TYPE jsonb
USING payload::jsonb;
~~~

Với table lớn, dùng shadow column jsonb và backfill theo batch. Sau cutover, đánh giá lại GIN/expression indexes và query operators.

### 17.3. Semantic differences

`jsonb` chuẩn hóa representation và không giữ nguyên whitespace/key order như input text; duplicate object keys không được giữ như nhiều entries độc lập. Nếu consumer phụ thuộc raw payload byte-for-byte, lưu raw text riêng.

## 18. Thay đổi type trong partitioned tables

### 18.1. Parent và partitions

Schema của partitioned parent và partitions phải tương thích. Một số DDL trên parent có thể tác động tất cả partitions và giữ locks trên nhiều relations. Kiểm tra partition count, size skew và maintenance duration trước khi chạy.

### 18.2. Rolling partition migration

Với dữ liệu theo thời gian, có thể migrate từng partition hoặc nhóm partitions, nhưng cần parent schema compatibility. Attach/detach partitions và partition bounds có thể yêu cầu constraints/indexes tương ứng.

### 18.3. New partitions trong lúc backfill

Đảm bảo partition creation job tạo cả old/new columns, triggers, constraints và indexes theo phase hiện tại. Nếu không, rows ở partitions mới có thể không được dual-write/backfill.

### 18.4. Retention và archive

Partition cũ sắp hết retention có thể không cần backfill nếu business/legal policy cho phép archive/drop theo kế hoạch. Ghi rõ scope và không bỏ sót dữ liệu cần giữ.

## 19. Operational runbook cho một schema migration lớn

### 19.1. Trước khi triển khai

1. Viết migration design: source/target type, conversion rules và source of truth.
2. Inventory dependencies: applications, jobs, views, functions, triggers, indexes, constraints và CDC.
3. Kiểm tra dữ liệu: invalid values, nulls, range, duplicates và edge cases.
4. Thử nghiệm trên staging với data volume gần production.
5. Đo lock duration, rewrite/backfill throughput, WAL, disk peak và replica catch-up.
6. Xác định maintenance window, on-call, owner và business approver.
7. Đặt baseline và dashboard/alerts.
8. Viết stop conditions, rollback/roll-forward plan và recovery steps.

### 19.2. Expand

- Kiểm tra schema hiện tại và migration version;
- Set lock timeout ngắn;
- Add shadow column/constraint/index cần thiết;
- Xác minh catalog và app cũ vẫn hoạt động;
- Ghi migration phase.

### 19.3. Deploy bridge

- Deploy bridge app theo rolling strategy;
- Xác nhận dual-write/trigger behavior;
- Kiểm tra writes từ API, batch, admin và integrations;
- Theo dõi parity mismatch và errors;
- Không chuyển reads trước khi backfill đủ.

### 19.4. Backfill

- Bắt đầu canary range/partition;
- Đo rows/sec, WAL rate, replication lag và p95;
- Chọn batch size/interval;
- Commit mỗi batch;
- Ghi checkpoint atomic;
- Pause theo stop conditions;
- Chạy reconciliation pass.

### 19.5. Validate

- Missing rows bằng zero hoặc theo exception policy;
- Mismatch bằng zero;
- Range/domain/null/unique/FK checks đạt;
- Index valid/ready;
- Application smoke tests và query plans đạt;
- CDC/ETL/reporting consumers đã xác nhận.

### 19.6. Cutover

- Chuyển canary reads;
- Shadow compare;
- Mở rộng traffic;
- Chuyển writes/source of truth;
- Giữ reverse sync nếu rollback cần;
- Theo dõi errors, latency, parity và support incidents.

### 19.7. Contract

- Chờ rollback window kết thúc;
- Xác minh không còn consumer cũ;
- Lấy business sign-off;
- Drop old triggers/indexes/constraints/cột theo từng change nhỏ;
- Theo dõi lock và query queues;
- Cập nhật code, docs, dashboards và runbooks.

### 19.8. Sau migration

Lưu migration report gồm actual duration, rows converted, mismatch/error count, WAL generated, peak disk, replica lag, query latency trước/sau và follow-up actions. Không đánh dấu hoàn tất chỉ vì DDL cuối cùng đã chạy.

## 20. Bài tập thực hành: đổi kiểu dữ liệu và backfill

Các bài tập nên thực hiện trên lab/staging. Không chạy type rewrite, backfill lớn, lock hoặc destructive DDL trên production chỉ để làm bài. Với các behavior phụ thuộc major version, xác minh documentation tương ứng.

### Bài 1 — Đánh giá type change

Một cột text chứa mã khách hàng cần chuyển sang bigint. Liệt kê các thông tin cần biết trước khi viết migration.

### Bài 2 — Kiểm tra dữ liệu

Viết query đếm NULL, invalid numeric strings và giá trị vượt range bigint trước khi cast.

### Bài 3 — Direct ALTER

Viết lệnh ALTER COLUMN TYPE dùng USING để chuyển text sang bigint. Nêu các lý do khiến lệnh fail.

### Bài 4 — Rewrite risk

Giải thích khác biệt giữa metadata-only change và table rewrite. Nêu các tài nguyên cần đo trước khi đổi type table lớn.

### Bài 5 — Lock

Giải thích vì sao ALTER TABLE cần ACCESS EXCLUSIVE có thể gây outage ngay cả khi DDL đang chờ lock.

### Bài 6 — lock_timeout

Viết transaction add nullable column với SET LOCAL lock_timeout. Giải thích cách retry sau lock timeout.

### Bài 7 — Default expression

Một default cũ không cast được sang type mới. Viết thứ tự DROP DEFAULT, ALTER TYPE và SET DEFAULT.

### Bài 8 — Numeric precision

Chuyển numeric(18,4) sang numeric(12,2). Nêu cách phát hiện values bị overflow hoặc mất precision và định nghĩa rounding rule.

### Bài 9 — Timestamp

Một cột text chứa local timestamp không có offset. Vì sao cần biết timezone nguồn trước khi chuyển sang timestamptz?

### Bài 10 — JSONB

So sánh json và jsonb về representation, duplicate keys và indexing. Khi nào cần giữ raw text?

### Bài 11 — Expand-contract

Vẽ các giai đoạn expand, bridge, backfill, validate, cutover và contract cho một cột lớn.

### Bài 12 — Compatibility matrix

Tạo bảng compatibility cho old app, bridge app và new app qua ba schema states.

### Bài 13 — Shadow column

Viết ALTER TABLE thêm shadow bigint column cho một text column hiện có.

### Bài 14 — Dual write

Viết INSERT/UPDATE ghi cả cột cũ và cột mới trong cùng transaction. Nêu lỗi có thể xảy ra nếu tách thành hai transactions.

### Bài 15 — Trigger bridge

Viết trigger old-to-new cho INSERT và UPDATE. Giải thích source-of-truth và cách xử lý invalid values.

### Bài 16 — Backfill batch

Viết CTE dùng primary key, LIMIT và `FOR UPDATE SKIP LOCKED` để cập nhật 1.000 rows chưa backfill.

### Bài 17 — Idempotency

Vì sao điều kiện `WHERE new_column IS NULL` giúp backfill resume an toàn? Nêu giới hạn nếu source column thay đổi cùng lúc.

### Bài 18 — OFFSET vs keyset

So sánh `OFFSET` pagination với keyset pagination khi backfill hàng trăm triệu rows.

### Bài 19 — ctid

Giải thích vì sao `ctid` có thể dùng trong một statement batch nhưng không nên dùng làm checkpoint lâu dài.

### Bài 20 — Batch sizing

Một batch 5.000 rows mất 20 giây và replica lag tăng. Đề xuất cách điều chỉnh batch size, delay và concurrency.

### Bài 21 — Concurrent updates

Trong lúc backfill, application update source column. Thiết kế trigger/dual-write để shadow column không bị stale.

### Bài 22 — Validation

Viết query đếm missing rows và mismatches giữa text source và bigint shadow column. Vì sao count parity không đủ?

### Bài 23 — NOT VALID

Viết ADD CHECK NOT VALID, VALIDATE CONSTRAINT và SET NOT NULL cho shadow column. Giải thích tác động lock/scan.

### Bài 24 — Unique index

Viết `CREATE UNIQUE INDEX CONCURRENTLY` trên shadow column và mô tả cách attach nó thành unique constraint.

### Bài 25 — Replication monitoring

Viết query xem sent/write/flush/replay LSN và đề xuất stop condition khi migration làm lag vượt RPO budget.

### Bài 26 — WAL capacity

Một backfill sinh 200 GB WAL và standby offline giữ slot. Nêu cách điều tra và bảo vệ primary disk.

### Bài 27 — Rollback

Phân tích khả năng rollback ở các phase expand, backfill, read cutover, write cutover và contract. Phase nào khó rollback nhất?

### Bài 28 — Partition migration

Thiết kế kế hoạch đổi type cho bảng partitioned có 60 partitions. Nêu cách xử lý partitions mới được tạo trong lúc migration.

### Bài 29 — Application cutover

Thiết kế canary rollout và shadow reads cho new column. Xác định metrics/acceptance criteria trước khi tăng traffic.

### Bài 30 — Capstone: migration zero-downtime

Một bảng `orders` có 120 triệu rows. Cột `customer_ref` là varchar nhưng cần đổi sang bigint; hệ thống nhận 8.000 writes/second, có 2 synchronous standbys, một async DR replica, CDC consumer và nhiều phiên bản application chạy rolling deploy. RPO target cho AZ failure là 0 và RTO 5 phút.

**Yêu cầu:**

1. Đánh giá conversion validity, range, nulls, duplicates và dependencies.
2. So sánh direct ALTER với expand–migrate–contract.
3. Thiết kế shadow column, source-of-truth phases và dual-write/trigger.
4. Viết backfill batch idempotent với checkpoint/resume.
5. Chọn batch size/concurrency và adaptive throttling metrics.
6. Thiết kế constraints/indexes và validation trước cutover.
7. Xác định lock timeout, statement timeout, stop conditions và maintenance window.
8. Theo dõi WAL, replication, CDC lag, disk và application latency.
9. Viết read/write cutover, rollback window và contract checklist.
10. Thiết kế failure handling cho invalid rows, deadlocks, disk pressure và mismatch.
11. Lập test matrix với old/bridge/new app versions.
12. Viết migration report và acceptance criteria cho business sign-off.

**Tiêu chí đạt:** migration có thể pause/resume, không ghi đè dữ liệu mới bằng backfill cũ, không vượt RPO/latency/disk budget, có validation chứng minh parity và có kế hoạch rollback/roll-forward cho từng phase.

## 21. Câu hỏi thường gặp

### 21.1. Có thể đổi type trực tiếp trên table lớn không?

Có thể về mặt kỹ thuật, nhưng thường cần lock mạnh và có thể rewrite toàn table. Đánh giá table size, dependencies, conversion, WAL, disk headroom và downtime trước. Với uptime cao, staged migration thường dễ kiểm soát hơn.

### 21.2. ALTER COLUMN TYPE luôn rewrite table?

Không. Một số conversions có thể binary-coercible hoặc metadata-only theo type/version; một số conversions yêu cầu rewrite. Xác minh documentation và thử trên bản sao tương đương production.

### 21.3. ALTER TABLE có thể gây outage dù lệnh chưa chạy?

Có. DDL đang chờ lock mạnh có thể tạo lock queue và làm queries khác bị chặn. Dùng lock timeout ngắn, preflight và retry có backoff.

### 21.4. Thêm nullable column có an toàn không?

Thường là metadata change nhanh nếu không có default cần rewrite, nhưng vẫn cần lock ngắn và có thể chờ transaction dài. Dùng lock timeout và xác minh behavior theo version.

### 21.5. Có nên dùng default khi thêm cột lớn?

PostgreSQL versions hiện đại có tối ưu cho một số constant immutable defaults, nhưng volatile expressions hoặc version cũ có thể rewrite table. Kiểm tra version và test trước.

### 21.6. Vì sao cần shadow column?

Nó cho phép cột cũ và mới cùng tồn tại trong rollout, backfill dữ liệu theo batch và chuyển traffic có kiểm soát. Điều này giảm nhu cầu giữ lock rewrite dài trên table lớn.

### 21.7. Dual write nên làm ở application hay trigger?

Application dual-write rõ ràng khi mọi writers được nâng cấp; trigger giúp tương thích với writers cũ. Có thể kết hợp trong một phase, nhưng phải định nghĩa source-of-truth/conflict rule và test mọi write paths.

### 21.8. Dual write có đảm bảo hai cột giống nhau không?

Chỉ khi writes nằm trong cùng transaction hoặc được đồng bộ atomic, conversion deterministic và retries không ghi đè dữ liệu mới. Cần metrics parity và reconciliation.

### 21.9. Backfill nên chạy trong một transaction không?

Không nên cho table lớn. Chia thành batches và commit riêng để giới hạn locks, snapshots, WAL burst và rollback cost.

### 21.10. Batch size bao nhiêu là đúng?

Không có con số chung. Bắt đầu nhỏ, đo batch duration, throughput, latency, WAL và replication lag; tăng/giảm theo stop conditions.

### 21.11. FOR UPDATE SKIP LOCKED có thể bỏ sót rows không?

Có thể bỏ qua rows đang bị lock ở vòng hiện tại. Chạy reconciliation pass và chỉ đánh dấu hoàn tất khi validation chứng minh không còn rows cần backfill.

### 21.12. OFFSET có phù hợp backfill lớn không?

Thường không. OFFSET lớn làm database phải đi qua nhiều rows trước mỗi batch. Dùng keyset pagination theo stable key hoặc tìm rows còn thiếu.

### 21.13. Có thể dùng ctid làm checkpoint không?

Không nên. ctid có thể đổi khi row được update/rewrite. Chỉ dùng ctid trong một statement batch ngắn; dùng primary key/range cho checkpoint lâu dài.

### 21.14. Backfill có ghi đè concurrent update không?

Có thể nếu logic không khóa/kiểm tra source-of-truth đúng. Dùng row locking, điều kiện chỉ update rows thiếu, dual-write/trigger và test race conditions.

### 21.15. Làm sao biết backfill đã hoàn tất?

Không chỉ dựa vào cursor hoặc số rows processed. Chạy reconciliation, missing/mismatch checks, domain/range validation và xác nhận writes mới tiếp tục được đồng bộ.

### 21.16. NOT VALID có nghĩa constraint không enforce?

Không. Constraint chưa validate dữ liệu cũ nhưng vẫn được enforce đối với rows mới/được sửa theo semantics của constraint. Chạy VALIDATE CONSTRAINT để kiểm tra dữ liệu hiện có.

### 21.17. VALIDATE CONSTRAINT có block writes không?

Nó dùng lock nhẹ hơn một số DDL mạnh và cho phép nhiều DML tiếp tục, nhưng vẫn scan dữ liệu và tiêu thụ I/O. Theo dõi workload và version-specific lock behavior.

### 21.18. CREATE INDEX CONCURRENTLY có cần disk thêm không?

Có. Index mới được build trước khi thay thế/attach; cần space cho old/new indexes, WAL và temporary work. Build có thể fail nếu duplicates xuất hiện.

### 21.19. Vì sao cần kiểm tra sequence khi đổi integer sang bigint?

Serial/identity dùng sequence riêng. Cần kiểm tra sequence type, ownership, default và current value; đổi column type không tự đảm bảo sequence capacity phù hợp.

### 21.20. Có nên đổi parent type trước rồi đổi partitions sau?

Không tùy tiện. Partitioned parent và partitions phải tương thích; DDL trên parent có thể tác động nhiều relations. Lập kế hoạch theo version, partition count và attach/detach requirements.

### 21.21. Backfill có ảnh hưởng autovacuum không?

Có. UPDATE tạo dead tuples và WAL; autovacuum có thể cần chạy nhiều hơn. Không tắt autovacuum mặc định; theo dõi dead tuples, freeze age và worker capacity.

### 21.22. Backfill làm replication lag tăng thì sao?

Pause hoặc giảm batch/concurrency, xác định bottleneck network/standby I/O/replay/archive và resume khi metrics ổn định. Không promote hoặc drop slot chỉ để che lag.

### 21.23. Có thể rollback sau cutover không?

Chỉ khi cột cũ còn đồng bộ và conversion ngược lossless. Sau khi cột mới authoritative hoặc dữ liệu bị mất khi chuyển đổi, roll-forward có thể an toàn hơn rollback.

### 21.24. Khi nào được drop cột cũ?

Khi mọi app versions, jobs, reports, CDC consumers và integrations đã chuyển; parity/validation đạt; usage cột cũ bằng zero đủ lâu; rollback window kết thúc và business owner sign-off.

### 21.25. Schema migration có cần backup riêng không?

Cần có backup/PITR recovery point phù hợp trước migration lớn, nhưng backup không thay thế validation/rollback plan. Kiểm tra WAL archive và restore path; một backup chưa được restore test không chứng minh có thể phục hồi đúng RTO.

## 22. Tài liệu PostgreSQL chính thức

Chọn tài liệu theo major version đang chạy vì lock behavior, DDL optimizations, catalog columns và feature support có thể thay đổi:

- [ALTER TABLE](https://www.postgresql.org/docs/current/sql-altertable.html): đổi type, add/drop columns, constraints và locks.
- [Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html): lock modes và conflict behavior.
- [Concurrency Control](https://www.postgresql.org/docs/current/mvcc.html): MVCC và transaction snapshots.
- [Data Type Conversion](https://www.postgresql.org/docs/current/typeconv.html): cast resolution và type conversion.
- [CREATE INDEX](https://www.postgresql.org/docs/current/sql-createindex.html): concurrent index creation.
- [REINDEX](https://www.postgresql.org/docs/current/sql-reindex.html): rebuild indexes.
- [Progress Reporting](https://www.postgresql.org/docs/current/progress-reporting.html): theo dõi index build và VACUUM.
- [Constraints](https://www.postgresql.org/docs/current/ddl-constraints.html): CHECK, UNIQUE và foreign keys.
- [Routine Vacuuming](https://www.postgresql.org/docs/current/routine-vacuuming.html): autovacuum và cleanup sau UPDATE/backfill.
- [Monitoring Database Activity](https://www.postgresql.org/docs/current/monitoring-stats.html): activity, locks và replication statistics.
- [Replication Configuration](https://www.postgresql.org/docs/current/runtime-config-replication.html): WAL senders, slots và replication settings.
- [Logical Replication](https://www.postgresql.org/docs/current/logical-replication.html): publications, subscriptions và schema compatibility.
- [pg_cron](https://github.com/citusdata/pg_cron): scheduler extension; kiểm tra release tương thích.
- [pg_repack](https://github.com/reorg/pg_repack): table/index reorganization tool; kiểm tra version, requirements và operational limits.

## 23. Tổng kết

Đổi kiểu dữ liệu an toàn là một bài toán về compatibility, dữ liệu, lock, tài nguyên và rollout. Với table nhỏ, direct `ALTER COLUMN TYPE` có thể phù hợp nếu conversion đã kiểm tra và lock window được chấp nhận. Với table lớn hoặc ứng dụng rolling deploy, expand–migrate–contract cho phép schema cũ/mới cùng tồn tại trong thời gian backfill và cutover.

| Thành phần | Vai trò |
| --- | --- |
| Type assessment | Xác định semantics, range, precision, timezone và conversion errors |
| Expand | Thêm shadow column/index/constraint tương thích |
| Dual write/trigger | Đồng bộ writes trong thời gian chuyển đổi |
| Batched backfill | Điền dữ liệu theo transaction ngắn, có thể resume |
| Validation | Chứng minh completeness, parity và constraints |
| Cutover | Chuyển reads/writes sang type mới theo canary |
| Rollback window | Giữ khả năng quay lại hoặc roll-forward an toàn |
| Contract | Loại bỏ cấu trúc cũ sau khi hết consumer |
| Monitoring | Kiểm soát lock, latency, WAL, replication và disk |

Không chạy một lệnh rewrite lớn chỉ vì DDL ngắn. Hãy thử trên dữ liệu tương đương production, chia backfill thành batches idempotent, giữ writes mới được đồng bộ, theo dõi WAL/replication/disk và xác minh dữ liệu trước cutover. Khi contract đã hoàn tất, rollback thường trở nên khó hơn đáng kể.

**Một migration tốt có thể pause, resume, validate và giải thích được source of truth ở mọi giai đoạn.** Điều đó giúp thay đổi schema mà vẫn giữ dữ liệu chính xác và giới hạn tác động lên ứng dụng đang phục vụ người dùng.
