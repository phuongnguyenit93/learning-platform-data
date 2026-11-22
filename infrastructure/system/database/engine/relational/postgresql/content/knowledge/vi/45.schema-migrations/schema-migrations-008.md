# Mô hình mở rộng rồi thu hẹp để tương thích ứng dụng khi thay đổi lược đồ PostgreSQL

Thay đổi lược đồ (schema) trong một hệ thống đang phục vụ traffic thường diễn ra đồng thời với việc triển khai nhiều phiên bản ứng dụng. Trong một khoảng thời gian, phiên bản cũ và phiên bản mới có thể cùng đọc hoặc ghi vào một database. Nếu một migration đổi tên cột, xóa cột, thay kiểu dữ liệu hoặc thay constraint ngay lập tức, một phiên bản ứng dụng vẫn đang chạy có thể lỗi giữa chừng.

Mô hình **mở rộng rồi thu hẹp** (expand and contract) giải quyết bài toán này bằng cách chia một thay đổi lớn thành các bước nhỏ có thể cùng tồn tại. Trước tiên, mở rộng schema để hỗ trợ cả hành vi cũ và mới. Sau đó triển khai ứng dụng có khả năng dùng schema mới, chuyển dữ liệu và traffic theo từng bước, xác nhận không còn consumer phụ thuộc cấu trúc cũ, rồi mới thu hẹp schema bằng cách loại bỏ phần legacy.

Cách làm này đặc biệt hữu ích cho rolling deployment, blue/green deployment, microservices, hệ thống có background workers và database dùng chung bởi nhiều ứng dụng. Nó cũng áp dụng cho việc đổi tên cột, tách bảng, thay data type, chuẩn hóa dữ liệu, chuyển quan hệ và thay đổi API lưu trữ.

Bài học thuộc chương **Thay đổi lược đồ** của module *Database Engine Relational PostgreSQL*. Nội dung đi từ nguyên tắc tương thích nhiều phiên bản, quy trình expand/migrate/contract, ví dụ SQL PostgreSQL, backfill dữ liệu, dual-write/dual-read, kiểm soát lock, kiểm thử, rollback và checklist vận hành.

> **Nguyên tắc:** Mỗi bước triển khai phải giữ cho mọi phiên bản ứng dụng đang hoạt động có thể sử dụng schema tại thời điểm đó. Chỉ xóa cấu trúc cũ sau khi đã chứng minh không còn reader, writer, job hoặc consumer nào phụ thuộc vào nó.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vì sao thay đổi schema trực tiếp có thể làm hỏng ứng dụng đang chạy.
2. Mô tả mô hình expand, migrate và contract.
3. Thiết kế schema có thể phục vụ đồng thời phiên bản ứng dụng cũ và mới.
4. Phân biệt backward compatibility và forward compatibility trong quá trình rollout.
5. Lập thứ tự deploy migration và application release.
6. Thêm cột, bảng, index và constraint theo từng bước an toàn.
7. Đổi tên cột bằng chiến lược thay thế có thời gian chuyển tiếp.
8. Thay đổi data type bằng shadow column và backfill.
9. Thực hiện backfill theo batch, có thể retry và kiểm soát tải.
10. Thiết kế dual-write và dual-read có nguồn dữ liệu chuẩn rõ ràng.
11. Chuyển reader/writer bằng feature flag hoặc rollout có kiểm soát.
12. Phát hiện consumer cũ trong worker, ETL, BI, CDC và SQL thủ công.
13. Giảm rủi ro lock, table rewrite và index build.
14. Dùng NOT VALID, VALIDATE CONSTRAINT và CREATE INDEX CONCURRENTLY phù hợp.
15. Theo dõi tính nhất quán dữ liệu trong suốt migration.
16. Xây dựng rollback và recovery plan cho từng phase.
17. Thiết kế migration idempotent và có observability.
18. Xác định điều kiện hoàn tất trước khi contract schema cũ.

## 2. Vì sao schema migration có thể làm ứng dụng gián đoạn?

Ứng dụng và database thường được triển khai theo hai nhịp khác nhau. Database là thành phần dùng chung, còn ứng dụng có thể có nhiều replicas, worker processes và service versions chạy đồng thời.

Ví dụ, một bảng đang có cột **full_name**. Phiên bản ứng dụng mới muốn dùng hai cột **given_name** và **family_name**. Nếu migration thực hiện ngay:

```sql
ALTER TABLE customers RENAME COLUMN full_name TO display_name;
```

Mọi process còn truy vấn **full_name** sẽ gặp lỗi. Ngay cả khi deployment pipeline đã bắt đầu rollout phiên bản mới, load balancer có thể vẫn gửi traffic tới instance cũ; background worker cũ có thể chưa restart; một cron job có thể chạy sau vài giờ.

### 2.1. Database schema là contract dùng chung

Schema là giao diện giữa database và:
- API services.
- Background workers.
- Scheduled jobs.
- ETL/ELT pipelines.
- Reporting và BI tools.
- CDC consumers.
- Admin scripts.
- Các service khác dùng chung database.
- Con người chạy truy vấn vận hành.

Một migration chỉ tương thích với API service chính vẫn có thể làm hỏng một worker hoặc báo cáo ít được sử dụng.

### 2.2. Rolling deployment tạo ra giai đoạn mixed-version

Trong rolling deployment, không phải tất cả replicas đổi version cùng một thời điểm. Trong quá trình rollout có thể tồn tại:
- Application v1 và v2.
- Worker v1 và v2.
- Migration đã chạy nhưng app mới chưa rollout hết.
- App mới đã chạy nhưng consumer cũ vẫn tồn tại.
- Một job cũ chưa đến lịch chạy.

Do đó, migration phải xem xét cả trạng thái chuyển tiếp, không chỉ trạng thái cuối.

### 2.3. DDL có thể giữ lock

Một số lệnh DDL cần lock mạnh trên table. Nếu lock phải chờ transaction dài, migration có thể xếp hàng; các query khác sau đó cũng có thể chờ theo. Một lệnh tưởng là metadata-only vẫn có thể cần lock ngắn nhưng gây gián đoạn nếu lock queue bị tắc.

### 2.4. Thay đổi cấu trúc và thay đổi dữ liệu là hai công việc khác nhau

Thêm cột mới không tự chuyển dữ liệu từ cột cũ. Tạo bảng mới không tự đồng bộ rows. Thay kiểu dữ liệu có thể yêu cầu chuyển đổi dữ liệu lâu và tạo tải I/O. Tách migration thành schema change và data backfill giúp kiểm soát từng phần.

## 3. Mô hình expand and contract

Mô hình gồm ba giai đoạn chính:

```text
Current state
    |
    v
EXPAND
  Add new schema while old schema still works
    |
    v
MIGRATE
  Deploy compatible app, dual-write/backfill,
  validate data, switch readers
    |
    v
CONTRACT
  Stop old writes, prove old reads are gone,
  remove legacy schema
    |
    v
Target state
```

### 3.1. Expand

Mở rộng schema bằng cách thêm cấu trúc mới mà không phá cấu trúc cũ:
- Add nullable column.
- Add new table.
- Add new index.
- Add constraint theo cách validate sau.
- Add new enum value hoặc type mới khi phù hợp.
- Add compatibility view hoặc trigger nếu cần.

Mục tiêu là schema mới có thể cùng tồn tại với ứng dụng cũ.

### 3.2. Migrate

Triển khai logic ứng dụng và chuyển dữ liệu:
- Deploy code hiểu cả schema cũ và mới.
- Bắt đầu ghi dữ liệu mới theo chiến lược đã chọn.
- Backfill dữ liệu cũ theo batch.
- So sánh và validate dữ liệu.
- Chuyển reads sang cấu trúc mới.
- Theo dõi mọi consumer và xử lý lag.

### 3.3. Contract

Sau khi không còn consumer phụ thuộc schema cũ:
- Dừng ghi vào cột/bảng cũ.
- Xác nhận không còn đọc từ cấu trúc cũ.
- Giữ một khoảng quan sát theo workload/job schedule.
- Drop cột/bảng/index legacy hoặc loại bỏ trigger compatibility.
- Dọn code và config cũ.

### 3.4. Không gộp ba phase thành một deployment

Nếu add column, backfill, switch reads và drop old column cùng một migration transaction, hệ thống mất khả năng rollout theo từng bước. Hãy tạo các migration và application releases riêng, có trạng thái hoàn tất rõ ràng.

## 4. Backward compatibility và forward compatibility

Hai khái niệm này giúp quyết định thứ tự triển khai.

- **Backward-compatible change:** phiên bản ứng dụng mới vẫn hoạt động với schema cũ hoặc hỗ trợ giai đoạn chuyển tiếp.
- **Forward-compatible change:** phiên bản ứng dụng cũ vẫn hoạt động khi schema đã được mở rộng theo cách mới.

Trong rolling deployment, schema expansion thường cần bảo đảm app cũ vẫn chạy trên schema mới. App mới cũng cần được thiết kế để chạy trong giai đoạn dữ liệu chưa backfill xong.

### 4.1. Ma trận tương thích

Ví dụ khi thêm **display_name** thay cho **full_name**:

| Schema | App v1 | App v2 |
|---|---|---|
| S0: chỉ full_name | Hoạt động | Không được deploy |
| S1: có cả full_name và display_name | Hoạt động | Hoạt động nếu code fallback |
| S2: dữ liệu mới đã đồng bộ | Hoạt động | Hoạt động |
| S3: chỉ display_name | Không hoạt động | Hoạt động |

Trạng thái cần giữ trong rollout là S1/S2 cho đến khi app v1 và mọi consumer cũ đã biến mất. S3 chỉ an toàn sau khi contract được cho phép.

### 4.2. Schema compatibility không tự bảo đảm semantic compatibility

Hai cột có thể cùng tồn tại nhưng mang ý nghĩa khác nhau. Nếu app v1 ghi **full_name** và app v2 ghi **display_name** theo quy tắc chuẩn hóa khác, dữ liệu có thể lệch. Phải định nghĩa mapping và nguồn dữ liệu chuẩn.

### 4.3. Mọi writer đều phải được tính đến

Một service chính có thể đã deploy v2 nhưng worker, trigger, import tool hoặc script cũ vẫn ghi vào schema cũ. Không bắt đầu contract chỉ dựa trên trạng thái deployment của một service.

## 5. Ví dụ xuyên suốt: đổi tên cột

Giả sử bảng:

```sql
CREATE TABLE customers (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    full_name text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
```

Yêu cầu mới muốn tách tên thành:
- **given_name**
- **family_name**

Không thể đơn giản rename **full_name**, vì app cũ vẫn đọc và ghi cột này. Ta sẽ giữ cột cũ trong giai đoạn chuyển tiếp.

### 5.1. Kế hoạch ở mức tổng quan

1. Expand: thêm hai cột mới, ban đầu cho phép NULL.
2. Deploy app tương thích: đọc fallback và ghi cả cấu trúc cũ/mới theo chiến lược đã chọn.
3. Backfill: chuyển rows cũ sang hai cột mới theo batch.
4. Validate: kiểm tra rows đã chuyển và xử lý ngoại lệ.
5. Switch reads: app v2 đọc hai cột mới.
6. Stop legacy writes: xác nhận mọi writer đã cập nhật.
7. Contract: bỏ **full_name** khi hết dependency.
8. Enforce new constraints: áp dụng NOT NULL hoặc constraint mới sau khi dữ liệu đạt yêu cầu.

### 5.2. Định nghĩa mapping trước khi viết code

Không phải lúc nào cũng có thể tách một **full_name** thành hai phần chính xác. Cần quyết định:
- Quy tắc xử lý tên có nhiều thành phần.
- Tên chỉ có một từ.
- Prefix/suffix.
- Khoảng trắng và Unicode.
- Dữ liệu NULL/empty.
- Tên không theo cấu trúc given/family.
- Có cần giữ nguyên giá trị gốc cho audit/display không?

Nếu mapping không thể suy ra chắc chắn, lưu dữ liệu chưa phân loại vào trạng thái cần review hoặc thiết kế field phù hợp hơn. Không dùng một phép split tùy tiện rồi coi kết quả là đúng.

## 6. Phase expand: thêm cấu trúc mới

Migration đầu tiên chỉ thêm các cột mới:

```sql
ALTER TABLE customers
    ADD COLUMN given_name text,
    ADD COLUMN family_name text;
```

Các cột mới cho phép NULL để:
- App v1 vẫn insert mà không cần biết chúng.
- App v2 có thể được deploy trước khi backfill hoàn tất.
- Backfill có thể chạy độc lập.
- Không buộc một table rewrite chỉ để tính giá trị từ cột cũ.

### 6.1. Thêm cột nullable thường là lựa chọn dễ rollout

Trên PostgreSQL, ADD COLUMN không có default hoặc default hằng số có thể được thực hiện bằng thay đổi metadata trong các phiên bản hiện đại; nhưng vẫn cần lock phù hợp trên table. Default volatile hoặc biểu thức cần tính cho từng row có thể làm phát sinh table rewrite. Kiểm tra behavior của đúng major version và kích thước bảng trước khi chạy.

### 6.2. Không thêm NOT NULL trước khi có dữ liệu

Nếu table đang có rows, cột mới không thể lập tức thỏa NOT NULL khi chưa có giá trị. Thêm constraint quá sớm có thể fail hoặc cần scan/rewrite. Hãy backfill, validate rồi mới enforce.

### 6.3. Dùng explicit column lists

Các ứng dụng dùng INSERT không liệt kê tên cột dễ bị ảnh hưởng khi schema thêm cột. Khuyến nghị mọi query insert chỉ định danh sách cột:

```sql
INSERT INTO customers (full_name)
VALUES ('Nguyen Van An');
```

Rà soát stored procedures, test fixtures và scripts có phụ thuộc vào column order.

### 6.4. DDL lock timeout

Có thể giới hạn thời gian chờ lock để migration fail nhanh thay vì xếp hàng lâu:

```sql
BEGIN;
SET LOCAL lock_timeout = '2s';
ALTER TABLE customers
    ADD COLUMN given_name text;
COMMIT;
```

Chọn timeout theo môi trường. Nếu lock không lấy được, retry theo lịch có backoff sau khi xác định blocker. Đừng lặp lại liên tục làm tăng contention.

## 7. Thêm index theo cách giảm blocking

Nếu app mới cần index cho cột mới, có thể tạo index concurrently:

```sql
CREATE INDEX CONCURRENTLY customers_given_name_idx
    ON customers (given_name);
```

### 7.1. CREATE INDEX CONCURRENTLY

Lệnh này cho phép INSERT/UPDATE/DELETE tiếp tục trong phần lớn quá trình build, nhưng cần nhiều bước scan và có thể kéo dài hơn CREATE INDEX thông thường.

Lệnh không được chạy bên trong transaction block. Migration framework phải hỗ trợ migration không transactional hoặc chạy statement riêng.

### 7.2. Index invalid sau lỗi

Nếu CREATE INDEX CONCURRENTLY thất bại, có thể để lại index invalid. Kiểm tra **pg_index.indisvalid** và **indisready**; xử lý index invalid theo runbook trước khi thử lại. Không giả định tên index tồn tại nghĩa là index usable.

### 7.3. Unique index

Nếu cần uniqueness, tạo unique index concurrently rồi có thể gắn constraint bằng ALTER TABLE ... ADD CONSTRAINT ... USING INDEX khi phù hợp. Cần xác nhận index đủ điều kiện và tên/semantics constraint đúng.

### 7.4. Index không phải lúc nào cũng miễn phí

Build index tiêu tốn I/O, CPU, disk tạm và có thể làm tăng replication lag. Theo dõi progress qua **pg_stat_progress_create_index**, disk headroom và workload latency.

## 8. Deploy ứng dụng tương thích

Sau khi schema expansion thành công, deploy ứng dụng v2 có khả năng làm việc trong giai đoạn chuyển tiếp.

### 8.1. Read fallback

Trong lúc backfill chưa xong, app mới có thể đọc cột mới nếu đã có giá trị, nếu không thì fallback sang cột cũ:

```sql
SELECT
    id,
    CASE
        WHEN given_name IS NOT NULL OR family_name IS NOT NULL
        THEN concat_ws(' ', given_name, family_name)
        ELSE full_name
    END AS display_name
FROM customers;
```

Đây chỉ là ví dụ cho trường hợp mapping có thể biểu diễn được bằng cách ghép. Quy tắc business thực tế có thể cần một cột display value riêng hoặc logic ứng dụng.

### 8.2. Deploy app mới trước khi chuyển read hoàn toàn

Ban đầu, app v2 có thể tiếp tục đọc **full_name** và chỉ ghi thêm cột mới. Sau khi backfill/validation đạt, bật feature flag để đọc cấu trúc mới.

### 8.3. Mixed-version safety

Trong rollout, app v1 và v2 có thể cùng ghi. Nếu v1 chỉ cập nhật **full_name**, cột mới phải được đồng bộ hoặc app v2 phải biết fallback. Nếu v2 cập nhật cột mới, cột cũ cũng có thể cần được cập nhật để v1 vẫn nhìn thấy dữ liệu mới.

### 8.4. Không giả định rollout hoàn tất khi deployment controller báo success

Kiểm tra process thực tế, worker pools, scheduled jobs, long-running sessions và client versions. Một pod cũ có thể còn chạy vì termination grace period hoặc job chưa hoàn thành.

## 9. Dual-write: ghi cả schema cũ và mới

Dual-write là cách ứng dụng ghi cùng một thay đổi vào cả cấu trúc cũ và mới trong giai đoạn chuyển tiếp.

Ví dụ:

```sql
UPDATE customers
SET
    full_name = $1,
    given_name = $2,
    family_name = $3
WHERE id = $4;
```

### 9.1. Một transaction cho hai representation

Nếu hai cột nằm trong cùng database/table, ghi cả hai trong cùng transaction giúp chúng commit hoặc rollback cùng nhau. Không tách thành hai request độc lập nếu không có cơ chế consistency rõ ràng.

### 9.2. Chọn một nguồn dữ liệu chuẩn

Trong từng phase phải biết representation nào là authoritative:
- Trước cutover: legacy field có thể là source of truth.
- Trong backfill: legacy field là nguồn, cột mới là projection.
- Sau cutover: cột mới là nguồn, legacy field chỉ còn để app cũ đọc.
- Trước contract: dừng cập nhật legacy khi không còn reader/writer cũ.

Không để cả hai representation tự do ghi đè nhau mà không có conflict policy.

### 9.3. Race giữa backfill và writer

Backfill có thể đọc giá trị cũ, trong khi một request mới cập nhật row. Nếu backfill ghi kết quả đã tính từ snapshot cũ sau request, dữ liệu mới có thể bị ghi đè.

Cách xử lý:
- Dùng update có điều kiện, chỉ backfill khi target columns còn NULL.
- Hoặc dùng trigger/dual-write đồng bộ trong transaction.
- Hoặc dùng version/timestamp để tránh ghi đè update mới hơn.
- Chạy batch nhỏ và kiểm tra concurrent updates.

Ví dụ chỉ lấp giá trị còn thiếu:

```sql
UPDATE customers
SET
    given_name = $1,
    family_name = $2
WHERE id = $3
  AND given_name IS NULL
  AND family_name IS NULL;
```

Cần thiết kế điều kiện để không ghi đè một phần dữ liệu hợp lệ.

### 9.4. Dual-write ở hai hệ thống khác nhau

Nếu legacy và new schema nằm ở hai database/service khác nhau, một transaction PostgreSQL đơn lẻ không bảo đảm atomicity. Cần transactional outbox, CDC, idempotent consumer hoặc reconciliation. Hai lệnh write độc lập có thể tạo partial success.

### 9.5. Theo dõi write divergence

Tạo metric cho số rows không đồng nhất, lỗi đồng bộ, retry và dead-letter events. Không chỉ dựa vào log ứng dụng.

## 10. Dùng trigger để duy trì compatibility

Trong một số trường hợp có nhiều writer cũ không thể nâng cấp cùng lúc, trigger có thể đồng bộ legacy/new columns.

Ví dụ trigger minh họa khi **full_name** là nguồn chuẩn trong giai đoạn đầu:

```sql
CREATE OR REPLACE FUNCTION sync_customer_name_columns()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        -- Thay logic parse bằng quy tắc nghiệp vụ đã thống nhất.
        NEW.given_name := split_part(btrim(NEW.full_name), ' ', 1);
        NEW.family_name := CASE
            WHEN position(' ' IN btrim(NEW.full_name)) > 0 THEN
                nullif(btrim(substring(
                    btrim(NEW.full_name)
                    FROM position(' ' IN btrim(NEW.full_name)) + 1
                )), '')
            ELSE NULL
        END;
    ELSIF NEW.full_name IS DISTINCT FROM OLD.full_name THEN
        NEW.given_name := split_part(btrim(NEW.full_name), ' ', 1);
        NEW.family_name := CASE
            WHEN position(' ' IN btrim(NEW.full_name)) > 0 THEN
                nullif(btrim(substring(
                    btrim(NEW.full_name)
                    FROM position(' ' IN btrim(NEW.full_name)) + 1
                )), '')
            ELSE NULL
        END;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER customers_sync_name_columns
BEFORE INSERT OR UPDATE OF full_name
ON customers
FOR EACH ROW
EXECUTE FUNCTION sync_customer_name_columns();
```

Đây là ví dụ kỹ thuật, không phải parser tên người dùng tổng quát. Với tên phức tạp, cần mapping do domain xác định.

### 10.1. Trigger giúp bảo vệ writer cũ

Writer cũ chỉ biết **full_name**; trigger cập nhật representation mới trong cùng transaction. Điều này hữu ích khi không thể release mọi producer cùng lúc.

### 10.2. Trigger có thể gây xung đột với writer mới

Nếu app v2 ghi **given_name/family_name**, trigger chỉ theo dõi **full_name** sẽ không tự cập nhật cột cũ. Nếu cần đồng bộ hai chiều, phải định nghĩa rõ precedence và tránh vòng lặp.

### 10.3. Trigger không thay thế rollout plan

Trigger làm tăng complexity, latency và khó debug. Cần metric, test concurrency và kế hoạch gỡ trigger sau khi mọi writer đã chuyển.

### 10.4. Trigger order và replication

Kiểm tra trigger firing order, **session_replication_role**, logical replication behavior và bulk import tools. Không giả định mọi đường ghi đều chạy cùng trigger semantics.

## 11. Backfill dữ liệu theo batch

Backfill là quá trình điền giá trị mới cho các rows cũ. Với bảng lớn, không nên mặc định chạy một UPDATE duy nhất cho toàn bộ table.

Ví dụ cập nhật theo khóa chính và giới hạn batch:

```sql
WITH batch AS (
    SELECT id
    FROM customers
    WHERE given_name IS NULL
      AND full_name IS NOT NULL
    ORDER BY id
    LIMIT 1000
    FOR UPDATE SKIP LOCKED
)
UPDATE customers AS c
SET
    given_name = split_part(c.full_name, ' ', 1),
    family_name = nullif(
        substring(c.full_name FROM position(' ' IN c.full_name) + 1),
        ''
    )
FROM batch
WHERE c.id = batch.id;
```

Ví dụ chỉ minh họa batching và locking. Mapping tên cần thay bằng logic đã được domain phê duyệt.

### 11.1. Commit giữa các batch

Mỗi batch nên là transaction ngắn, commit rồi mới tiếp tục. Điều này:
- Giảm thời gian giữ row locks.
- Giảm lượng WAL và áp lực do transaction dài.
- Giúp vacuum có cơ hội xử lý dead tuples.
- Hạn chế replication lag tăng đột ngột.
- Cho phép pause/resume.

### 11.2. Chọn batch size theo tải

Bắt đầu nhỏ, đo thời gian, WAL rate, lock waits, replica lag, disk usage và application latency. Tăng/giảm batch size theo metrics thay vì chọn một số cố định cho mọi bảng.

### 11.3. Dùng SKIP LOCKED có chủ đích

FOR UPDATE SKIP LOCKED cho phép nhiều workers lấy các rows khác nhau và bỏ qua rows đang bị transaction khác lock. Cần bảo đảm vòng lặp cuối cùng xử lý được các rows bị skip; không kết luận hoàn tất chỉ vì một batch trả 0 rows.

### 11.4. Idempotent backfill

Backfill phải có thể chạy lại mà không làm hỏng dữ liệu đã chuyển. Dùng predicate như WHERE new_column IS NULL, trạng thái migration hoặc version marker. Tránh ghi đè rows đã được app mới cập nhật.

### 11.5. Progress tracking

Theo dõi:
- Rows scanned/updated.
- Rows remaining.
- Rows skipped/failed.
- Last processed key.
- Batch duration.
- WAL generated.
- Replica lag.
- Error count.
- Estimated completion time.

Không chỉ ghi log “backfill started” và “finished”.

### 11.6. Tránh OFFSET cho bảng lớn

Pagination bằng OFFSET tăng chi phí khi offset lớn và có thể bỏ sót/đụng rows khi dữ liệu thay đổi. Dùng keyset pagination theo primary key hoặc work queue có locking.

## 12. Kiểm tra và đối soát dữ liệu

Sau backfill, cần chứng minh representation mới phản ánh đúng nguồn dữ liệu.

### 12.1. Kiểm tra coverage

```sql
SELECT
    count(*) AS total_rows,
    count(*) FILTER (
        WHERE given_name IS NOT NULL OR family_name IS NOT NULL
    ) AS rows_with_new_values,
    count(*) FILTER (
        WHERE given_name IS NULL AND family_name IS NULL
    ) AS rows_without_new_values
FROM customers;
```

Đây là coverage check, không chứng minh giá trị đã đúng.

### 12.2. Kiểm tra mismatch

Nếu có mapping chuẩn hóa được thành một biểu thức deterministic:

```sql
SELECT count(*) AS mismatch_count
FROM customers
WHERE full_name IS DISTINCT FROM
      concat_ws(' ', given_name, family_name);
```

Ví dụ này chỉ đúng nếu quy tắc domain bảo đảm concat_ws tái tạo chính xác full_name. Với dữ liệu có whitespace, prefix, suffix hoặc Unicode normalization, cần comparator phù hợp.

### 12.3. Lấy mẫu mismatch

```sql
SELECT
    id,
    full_name,
    given_name,
    family_name
FROM customers
WHERE /* predicate xác định mismatch theo mapping đã thống nhất */
ORDER BY id
LIMIT 100;
```

Review cả các trường hợp biên, không chỉ lấy random sample thông thường.

### 12.4. Reconciliation định kỳ

Trong giai đoạn dual-write, chạy đối soát định kỳ để phát hiện drift. Ghi metric và owner cho từng mismatch. Có thể dùng checksum/bucket theo key range cho bảng lớn, nhưng checksum phải canonicalize values và không thay validation logic.

### 12.5. Validation không nên khóa toàn bộ table lâu

Chia kiểm tra theo key ranges hoặc snapshot phù hợp. Các truy vấn COUNT lớn vẫn tạo I/O; đo tải và lên lịch.

## 13. Switch reads sang schema mới

Khi backfill đủ coverage và mismatch nằm trong ngưỡng được chấp nhận, chuyển reads sang representation mới.

### 13.1. Feature flag

Có thể dùng flag để điều khiển read path:

```text
customer_name_read_source = legacy | new
```

Flag giúp rollout theo nhóm traffic, tenant hoặc service instance và cho phép chuyển lại read path cũ trong giai đoạn schema cũ còn nguyên.

### 13.2. Canary

Chuyển một tỷ lệ nhỏ traffic trước, so sánh:
- Error rate.
- Response correctness.
- Query latency.
- Null/fallback rate.
- Mismatch metric.
- Database load.

Tăng tỷ lệ khi canary đạt acceptance criteria.

### 13.3. Đọc song song để so sánh

Có thể shadow-read cả hai representation và so sánh kết quả, nhưng chỉ dùng kết quả legacy để trả response trong giai đoạn quan sát. Tránh nhân đôi query nặng không kiểm soát.

### 13.4. Đừng để fallback che lỗi mãi mãi

Fallback hữu ích trong giai đoạn migrate. Nếu app v2 tiếp tục fallback mà không có alert, backfill thiếu dữ liệu có thể tồn tại vô thời hạn. Theo dõi fallback rate và đặt điều kiện để tắt fallback.

### 13.5. Sau switch reads vẫn chưa được drop legacy

Một service có thể đã chuyển read nhưng còn writer cũ. Cần xác nhận cả read và write paths trước contract.

## 14. Stop legacy writes

Sau khi mọi writer đã hỗ trợ schema mới, chuyển nguồn ghi chuẩn sang cấu trúc mới.

Quy trình:
1. Xác nhận toàn bộ app/worker versions đã được nâng cấp.
2. Xác nhận cron, ETL, admin tools và external integrations.
3. Bật new-write mode theo rollout plan.
4. Theo dõi old-column write activity.
5. Giữ compatibility trigger/dual-write trong thời gian quan sát nếu cần.
6. Dừng ghi legacy sau khi không còn old writers.
7. Tiếp tục theo dõi old-column reads.

### 14.1. Không suy ra không có writer từ việc không thấy query trong log ngắn

Một job có thể chạy hàng ngày, hàng tuần hoặc chỉ khi có incident. Quan sát phải bao phủ chu kỳ hoạt động và các operational runbooks.

### 14.2. Ghi nhận old-column access

Có thể dùng query logs, pg_stat_statements, application instrumentation, database audit hoặc trigger instrumentation có kiểm soát để phát hiện usage. Không có một counter mặc định trong PostgreSQL ghi chính xác mọi lần đọc một cột cụ thể.

### 14.3. Xử lý consumers ngoài application

BI, data warehouse extract, CDC, replication, ad hoc notebooks và stored procedures có thể vẫn đọc legacy field. Xác nhận với owner trước khi drop.

## 15. Phase contract: loại bỏ schema cũ

Chỉ bắt đầu contract khi:
- Mọi deployed applications đã dùng schema mới.
- Mọi workers và scheduled jobs đã cập nhật.
- Backfill hoàn tất và được đối soát.
- Read fallback không còn được dùng.
- Legacy writes đã dừng.
- Không còn external consumers.
- Rollback window cho phép loại bỏ legacy representation.
- Owner xác nhận dữ liệu mới là authoritative.

Ví dụ drop cột cũ:

```sql
BEGIN;
SET LOCAL lock_timeout = '2s';
ALTER TABLE customers
    DROP COLUMN full_name;
COMMIT;
```

### 15.1. DROP COLUMN cần lock

DROP COLUMN thường là thay đổi metadata và không lập tức rewrite toàn bộ table, nhưng cần lock mạnh trên relation. Nếu lock không lấy được nhanh, migration có thể chờ. Dùng lock_timeout, kiểm tra active transactions và retry trong maintenance window phù hợp.

### 15.2. Drop không đồng nghĩa disk được thu hồi ngay

PostgreSQL có thể giữ phần vật lý của dropped column trong tuples cũ cho đến khi rows được rewrite/vacuum theo cơ chế liên quan. Không kỳ vọng DROP COLUMN lập tức giảm file size trên filesystem.

### 15.3. Giữ code cleanup riêng

Sau contract, xóa fallback, dual-write, trigger, feature flags và legacy SQL trong các release riêng nếu cần. Code cleanup cũng cần review để không bỏ nhầm compatibility path đang còn được sử dụng.

### 15.4. Xác nhận không còn references

Tìm trong repository, migration history, jobs, database objects, monitoring, dashboards, documentation và runbooks. Kiểm tra cả dynamic SQL và external integrations.

## 16. Thêm NOT NULL và CHECK constraint an toàn

Nếu cột mới cần NOT NULL, không nhất thiết phải thêm constraint ngay từ đầu.

### 16.1. Add CHECK NOT VALID

Ví dụ:

```sql
ALTER TABLE customers
    ADD CONSTRAINT customers_given_name_present
    CHECK (given_name IS NOT NULL) NOT VALID;
```

Constraint mới được áp dụng cho các rows được insert/update sau khi được tạo, trong khi dữ liệu cũ chưa được validate toàn table.

### 16.2. Validate riêng

```sql
ALTER TABLE customers
    VALIDATE CONSTRAINT customers_given_name_present;
```

Validation scan dữ liệu nhưng dùng lock nhẹ hơn so với một số thao tác DDL blocking; vẫn cần đo I/O và lock impact.

### 16.3. Set NOT NULL

```sql
ALTER TABLE customers
    ALTER COLUMN given_name SET NOT NULL;
```

Ở các PostgreSQL versions hỗ trợ tối ưu tương ứng, một CHECK constraint hợp lệ có thể giúp tránh scan lại khi set NOT NULL. Kiểm tra tài liệu đúng major version và lock behavior trước khi áp dụng.

### 16.4. Foreign key

Có thể thêm foreign key dưới dạng NOT VALID, sau đó validate riêng:

```sql
ALTER TABLE orders
    ADD CONSTRAINT orders_customer_id_fkey
    FOREIGN KEY (customer_id)
    REFERENCES customers(id)
    NOT VALID;

ALTER TABLE orders
    VALIDATE CONSTRAINT orders_customer_id_fkey;
```

Đảm bảo index phù hợp ở phía referencing table nếu workload cần. PostgreSQL không tự động tạo index cho cột foreign key ở phía referencing table.

### 16.5. Constraint validation không thay data migration

NOT VALID không sửa dữ liệu cũ. Phải backfill/clean data trước, rồi validate. Nếu validation fail, truy vấn các rows vi phạm và xử lý theo business rule.

## 17. Đổi data type bằng shadow column

Thay kiểu dữ liệu trực tiếp có thể yêu cầu rewrite table hoặc lock lâu, tùy type và conversion. Với bảng lớn, chiến lược shadow column thường dễ kiểm soát hơn.

Ví dụ đổi **amount_text text** thành **amount numeric**:

### 17.1. Expand

```sql
ALTER TABLE invoices
    ADD COLUMN amount_numeric numeric;
```

### 17.2. Deploy compatible writer

App mới parse/validate amount và ghi cả **amount_text** lẫn **amount_numeric** trong transaction. Từ chối hoặc xử lý riêng dữ liệu không parse được.

### 17.3. Backfill

```sql
UPDATE invoices
SET amount_numeric = amount_text::numeric
WHERE amount_numeric IS NULL
  AND amount_text IS NOT NULL;
```

Với table lớn, chia thành batch và xử lý các rows conversion lỗi riêng. Không chạy cast trên toàn bảng nếu dữ liệu có format không hợp lệ mà chưa phân tích.

### 17.4. Validate

So sánh giá trị numeric sau normalization, kiểm tra rounding/scale, precision, overflow và NULL semantics.

### 17.5. Switch reads/writes

Chuyển app đọc và ghi **amount_numeric**, giữ old representation cho rollback window nếu cần.

### 17.6. Contract

Sau khi mọi consumer chuyển, drop **amount_text** hoặc đổi tên cột theo chiến lược rollout đã xác nhận.

### 17.7. Conversion semantics

Đặc biệt chú ý decimal separator theo locale, thousands separators, currency symbols, rounding mode, numeric precision/scale, empty string và NULL, negative values, scientific notation và invalid legacy values.

## 18. Tách hoặc hợp nhất bảng

Expand/contract cũng áp dụng khi thay đổi quan hệ giữa tables.

Ví dụ chuyển thông tin địa chỉ từ **customers** sang **customer_addresses**.

**Expand**
- Tạo bảng mới.
- Tạo primary key/foreign key phù hợp.
- Tạo index.
- Thêm code ghi vào bảng mới hoặc compatibility trigger.

**Migrate**
- Backfill addresses theo customer ID.
- Xử lý duplicate/missing values.
- Đồng bộ writes trong giai đoạn chuyển tiếp.
- Validate row counts và relationships.
- Chuyển reads sang bảng mới.

**Contract**
- Dừng ghi/đọc các address columns cũ.
- Xác nhận consumers đã chuyển.
- Drop columns cũ.
- Giữ bảng mới và constraints theo design cuối.

### 18.1. Cardinality và uniqueness

Khi tách một cột thành bảng quan hệ, xác định một customer có một hay nhiều addresses. Unique constraint và application API phải phản ánh đúng cardinality.

### 18.2. Transaction boundary

Nếu ghi customer và address phải atomic, thực hiện trong cùng transaction trên cùng database. Nếu qua service/database khác, dùng outbox/saga hoặc consistency protocol.

### 18.3. Delete semantics

Xác định ON DELETE behavior, soft delete, retention và orphan handling trước khi chuyển. Một FK mới có thể làm các thao tác delete trước đây thành lỗi.

## 19. Thay đổi enum, lookup table và status model

Enum PostgreSQL có thể phù hợp cho tập giá trị ổn định, nhưng thay đổi tập trạng thái cần rollout cẩn thận khi nhiều app versions cùng chạy.

### 19.1. Thêm enum value

```sql
ALTER TYPE order_status
    ADD VALUE 'awaiting_review';
```

Các chi tiết transaction behavior phụ thuộc PostgreSQL version. Trên các phiên bản hiện đại, có thể thêm enum value trong transaction nhưng không thể sử dụng value mới cho đến khi transaction chứa ALTER TYPE commit. Kiểm tra manual của target version.

### 19.2. App cũ có thể không hiểu status mới

Nếu app v1 parse enum bằng exhaustive switch, một row có status mới có thể làm app lỗi. Vì vậy:
- Deploy code có khả năng nhận diện/ignore status mới trước.
- Thêm enum value sau khi consumers tương thích.
- Chỉ tạo records dùng value mới sau khi rollout đủ.
- Giữ fallback/unknown handling cho clients.

### 19.3. Xóa hoặc đổi enum value

PostgreSQL không cung cấp thao tác đơn giản để drop một enum value. Thường cần tạo type mới, migrate column, đổi dependencies và contract. Đây là migration nhiều bước.

### 19.4. Lookup table

Nếu status cần metadata, lifecycle hoặc frequent changes, lookup table có thể linh hoạt hơn. Tuy nhiên, nó cũng yêu cầu FK, seed data, cache invalidation và application compatibility.

## 20. Thay đổi JSON schema

Một cột JSON/JSONB có thể được dùng bởi nhiều application versions. Thay đổi document structure cũng cần expand/contract.

Ví dụ đổi key **phone** thành **phone_number**:
1. Expand reader để hiểu cả hai keys.
2. Deploy code đọc phone_number nếu có, fallback phone.
3. Deploy writer ghi key mới, có thể giữ key cũ trong giai đoạn chuyển tiếp.
4. Backfill documents theo batch.
5. Validate coverage và mismatch.
6. Dừng ghi key cũ.
7. Xác nhận mọi consumer đã chuyển.
8. Contract bằng cách bỏ key cũ khỏi document và code.

### 20.1. JSONB update tạo WAL

Backfill JSONB có thể rewrite toàn bộ value/toast representation của row, tạo WAL và dead tuples. Batch size, vacuum và replication lag cần được theo dõi.

### 20.2. GIN indexes

Thay đổi JSON structure có thể ảnh hưởng index expression và query predicates. Có thể cần tạo index mới concurrently, switch query rồi drop index cũ.

### 20.3. Validation theo schema

Có thể dùng application validation hoặc database CHECK/function để xác nhận document shape. Định nghĩa versioning cho JSON document nếu nhiều producer/consumer.

## 21. Thay đổi view và stored procedure

View hoặc function cũng là contract với application.

### 21.1. Tạo view mới

Thay vì sửa view hiện tại ngay lập tức, tạo **customer_summary_v2** hoặc một compatibility view có output contract mới. Consumer chuyển dần rồi mới drop view cũ.

### 21.2. CREATE OR REPLACE VIEW

CREATE OR REPLACE VIEW có giới hạn về thứ tự/tên/kiểu của các cột hiện có. Nếu cần thay output contract, tạo view mới hoặc dùng migration có thời gian chuyển tiếp. Kiểm tra dependencies.

### 21.3. Stored procedures

Function signature/return type thay đổi có thể làm client hoặc function dependency fail. Có thể tạo overload hoặc function version mới, chuyển callers, rồi drop signature cũ sau khi xác nhận.

### 21.4. Dependencies

Dùng catalog dependency inspection và DROP ... RESTRICT để phát hiện dependencies. Không dùng CASCADE trong migration production nếu chưa liệt kê đầy đủ objects bị ảnh hưởng.

## 22. Locking, table rewrite và operational safety

Expand/contract giảm phạm vi thay đổi nhưng không tự làm mọi DDL an toàn.

### 22.1. Hiểu lock mode

ALTER TABLE thường cần lock mạnh; loại lock phụ thuộc subcommand. Một thao tác metadata-only vẫn cần lấy lock trên relation. Transaction dài có thể giữ lock và chặn migration.

### 22.2. Kiểm tra blockers trước migration

```sql
SELECT
    a.pid,
    a.usename,
    a.application_name,
    a.state,
    a.xact_start,
    a.wait_event_type,
    a.wait_event,
    a.query
FROM pg_stat_activity AS a
WHERE a.datname = current_database()
  AND a.pid <> pg_backend_pid()
ORDER BY a.xact_start NULLS LAST;
```

Kiểm tra pg_locks để xác định relation locks và blocker chain. Cần quyền xem đầy đủ session details theo policy.

### 22.3. lock_timeout và statement_timeout

lock_timeout giới hạn thời gian chờ lock. statement_timeout giới hạn thời gian chạy statement. Đặt SET LOCAL trong migration transaction khi phù hợp; tránh global setting ảnh hưởng mọi ứng dụng.

### 22.4. Transaction dài

Không giữ transaction mở trong lúc backfill nhiều giờ. Transaction dài có thể giữ snapshots, cản vacuum và làm tăng storage pressure.

### 22.5. Table rewrite

Các thay đổi type/default/column semantics có thể rewrite table tùy version và expression. Ước lượng disk space, I/O, WAL, replica lag và downtime trước khi thực hiện.

### 22.6. DDL queue

Một DDL đang chờ AccessExclusiveLock có thể khiến các query mới xếp hàng phía sau. Nếu migration không lấy được lock nhanh, hủy/retry có kiểm soát thay vì để queue kéo dài.

## 23. Migration framework và quản lý thứ tự

Dùng migration framework có version history và cơ chế deploy rõ ràng.

### 23.1. Tách migration theo phase

Ví dụ:
- V101__add_new_columns.sql
- V102__add_indexes_concurrently.sql
- Application release hỗ trợ dual-read/write.
- Backfill job.
- V103__add_not_null_check.sql
- Application release chuyển read path.
- V104__drop_legacy_columns.sql

Tên file chỉ minh họa. Thứ tự thực tế phải theo compatibility matrix và framework.

### 23.2. Transactional migrations

Nhiều DDL có thể chạy trong transaction. Một số lệnh như CREATE INDEX CONCURRENTLY không chạy trong transaction block. Framework phải cấu hình đúng, không tự động bọc mọi migration vào transaction.

### 23.3. Idempotency

Migration versioned thường chỉ chạy một lần, nhưng operational scripts/backfill jobs có thể retry. Thiết kế các bước có thể kiểm tra trạng thái trước khi thực hiện và tránh tạo objects trùng.

### 23.4. Không sửa migration đã chạy

Giữ migration history bất biến. Nếu cần sửa logic, tạo migration mới. Thay nội dung file migration đã chạy có thể làm các environment lệch nhau.

### 23.5. Migration ownership

Xác định ai chạy DDL, ai deploy app, ai theo dõi backfill và ai được phép contract. Tránh việc application startup tự động chạy destructive migration khi nhiều replicas khởi động cùng lúc.

## 24. Observability trong suốt migration

Mỗi phase cần metric và log đủ để quyết định tiếp tục hay dừng.

**Schema**
- Migration version/current state.
- Constraint validation state.
- Index validity/readiness.
- Column/table presence.

**Backfill**
- Rows remaining.
- Rows processed per second.
- Error/retry count.
- Oldest/newest key processed.
- Mismatch count.
- Last successful batch.

**Application**
- App version distribution.
- Old/new read path usage.
- Fallback count.
- Legacy write count.
- Dual-write failure count.
- Request errors/latency.

**Database**
- Lock waits.
- Long-running transactions.
- CPU/I/O.
- WAL generation.
- Replication lag.
- Dead tuples/autovacuum progress.
- Disk headroom.

### 24.1. Feature flag metrics

Log flag state cùng app version/tenant/traffic cohort. Nếu flag bật nhưng code path không được quan sát, không thể biết rollout đã thật sự chuyển.

### 24.2. Alert migration-specific

Tạo alert khi:
- Backfill không tiến triển.
- Mismatch tăng.
- Dual-write failure xuất hiện.
- Replica lag vượt budget.
- Lock wait vượt thời gian.
- Index invalid.
- Disk headroom thấp.
- Old-column usage còn sau deadline.

### 24.3. Audit trail

Lưu migration ID, deploy version, actor, timestamp, batch range, result và approval. Tránh ghi dữ liệu cá nhân hoặc secrets vào logs.

## 25. Rollback theo từng phase

Rollback không giống nhau ở mọi phase.

| Phase | Tình huống | Hướng xử lý |
|---|---|---|
| Expand | Add column/index mới lỗi | Dừng rollout; sửa migration; drop object mới chỉ khi chắc chắn không có dependency |
| App compatible | App v2 lỗi nhưng legacy còn | Rollback app về v1; giữ schema mở rộng |
| Backfill | Batch lỗi/slow | Pause worker; giữ tiến độ; sửa và resume |
| Read switch | Read mới có lỗi | Tắt flag, quay về legacy read nếu legacy vẫn được đồng bộ |
| New source of truth | Legacy sync đã dừng | Khôi phục dual-write/reconcile trước khi quay về app cũ |
| Contract | Cột cũ đã drop | Không thể chỉ rollback app; cần restore/recreate/repopulate hoặc forward-fix |

### 25.1. Expand thường dễ rollback nhất

Cấu trúc mới chưa được dùng có thể bỏ đi, nhưng chỉ sau khi kiểm tra app/trigger/index/constraint không còn phụ thuộc. Giữ schema mở rộng trong lúc điều tra thường an toàn hơn vội drop.

### 25.2. Sau khi switch writes, rollback phức tạp hơn

Nếu new column là source of truth và app cũ không hiểu nó, phải đồng bộ dữ liệu về legacy representation trước khi rollback app. Không thể chỉ tắt feature flag nếu legacy values đã stale.

### 25.3. Contract là điểm irreversible về mặt ứng dụng

Drop old column có thể không mất dữ liệu ngay lập tức ở mức page, nhưng application contract cũ đã bị xóa. Nếu cần rollback, phải phục hồi schema và dữ liệu từ nguồn đáng tin cậy hoặc dùng forward fix.

### 25.4. Ưu tiên forward-compatible fixes

Trong production incident sau contract, đôi khi sửa app để tương thích schema mới nhanh và an toàn hơn khôi phục schema cũ. Runbook cần chỉ rõ decision owner và recovery options.

## 26. Ví dụ lịch trình rollout

Giả sử có service API và worker chạy nhiều replicas.

| Thời điểm | Database | Application | Điều kiện tiếp tục |
|---|---|---|---|
| T0 | Schema cũ S0 | App v1 | Baseline và backup sẵn sàng |
| T1 | Expand S1: thêm cột mới | App v1 | App v1 vẫn chạy |
| T2 | S1 | App v2 đọc fallback, dual-write | Tất cả instances/worker tương thích |
| T3 | S1 + backfill | App v2 | Backfill tiến triển, mismatch được xử lý |
| T4 | S1, dữ liệu mới đầy đủ | App v2 đọc cột mới | Canary và regression pass |
| T5 | S1 | App v2 chỉ ghi schema mới | Không còn legacy writer |
| T6 | S1, legacy không còn dùng | App v2 | Hết observation window |
| T7 | Contract S2: drop cột cũ | App v2 | Không còn legacy readers |
| T8 | S2 | App v2 đã cleanup | Monitoring ổn định |

### 26.1. Observation window

Chọn khoảng quan sát bao phủ:
- Longest scheduled job interval.
- Worker restart/rolling cycle.
- Batch import frequency.
- Reporting schedule.
- CDC lag.
- Maintenance and failover exercises.

Một ngày không đủ nếu có job chỉ chạy hàng tuần.

### 26.2. Không để phase treo vô thời hạn

Schema expand có thể tồn tại lâu, nhưng cần owner, deadline và metric. Legacy columns/dual-write kéo dài làm tăng complexity và tạo nguy cơ drift.

## 27. Những pattern phổ biến

### 27.1. Additive column

Thêm cột nullable, deploy app tương thích, backfill, switch reads, enforce constraints và drop old fields khi hết usage.

### 27.2. Rename column

Không dùng ALTER TABLE ... RENAME COLUMN như bước đầu trong rolling deployment. Tạo cột mới, đồng bộ, chuyển consumers, rồi drop cột cũ.

### 27.3. Change data type

Tạo shadow column với type mới, viết song song, backfill conversion, validate, switch và contract. Tránh cast toàn table khi chưa đánh giá rewrite/lock.

### 27.4. Split table

Tạo table mới, dual-write hoặc trigger, backfill, validate FK/uniqueness, switch reads và bỏ columns cũ.

### 27.5. Merge tables

Tạo representation mới, backfill từ các bảng cũ, xử lý conflict/duplicate, switch consumers rồi retire tables cũ.

### 27.6. Change enum/status

Mở rộng consumer để hiểu value mới trước khi producer tạo value. Đổi/xóa value cũ thường cần type replacement hoặc lookup table.

### 27.7. JSON key migration

Reader hiểu cả key cũ/mới, writer chuyển sang key mới, backfill documents, đo fallback và loại key cũ.

## 28. Anti-patterns cần tránh

- Rename/drop column trong cùng release với code đổi tên.
- Deploy app mới trước khi schema expansion tồn tại.
- Drop old schema khi một worker hoặc cron job chưa nâng cấp.
- Chạy backfill toàn bảng trong một transaction dài.
- Backfill ghi đè rows vừa được application update.
- Dual-write không có nguồn dữ liệu chuẩn.
- Hai hệ thống ghi độc lập mà không có consistency mechanism.
- Fallback read không có metric hoặc deadline.
- Dùng trigger hai chiều mà không có conflict/loop policy.
- Dùng SELECT * và insert theo column order.
- Tạo index lớn bằng lệnh blocking trong giờ cao điểm mà chưa đánh giá.
- Chạy CREATE INDEX CONCURRENTLY bên trong transaction block.
- Đặt NOT NULL trước khi dữ liệu hoàn chỉnh.
- Dùng DROP ... CASCADE để làm migration chạy qua.
- Coi deployment success là bằng chứng không còn old consumers.
- Xóa legacy schema ngay khi canary thành công.
- Không rehearsal rollback sau khi switch writes.
- Không lưu progress/evidence của backfill.

## 29. Kiểm thử compatibility

Kiểm thử phải bao phủ mọi tổ hợp schema/app có thể xuất hiện trong rollout.

| Schema | App version | Kết quả mong đợi |
|---|---|---|
| S0 cũ | App v1 | Pass |
| S1 expanded | App v1 | Pass |
| S1 expanded | App v2 | Pass |
| S1 partially backfilled | App v2 | Pass với fallback/guard đã thiết kế |
| S1 migrated | App v2 | Pass, reads mới |
| S1 migrated | Worker v1 | Pass nếu worker vẫn còn trong window |
| S2 contracted | App v2 | Pass |
| S2 contracted | App v1 | Không còn được hỗ trợ; phải chứng minh đã loại bỏ |

### 29.1. Test rollout order

Test đúng thứ tự migration và deploy, không chỉ dựng schema cuối rồi chạy app mới.

### 29.2. Test concurrent writes

Chạy đồng thời app v1, app v2 và backfill worker. Tạo update/delete/insert trên cùng key để phát hiện race.

### 29.3. Test retry và duplicate execution

Giả lập worker crash sau khi update nhưng trước khi ghi progress marker. Chạy lại và xác nhận không nhân đôi hoặc ghi đè dữ liệu.

### 29.4. Test lag và failure

Giả lập replica chậm, lock contention, network interruption, app rollout pause và migration retry. Kiểm tra operator có thể pause/resume an toàn.

### 29.5. Test old consumer detection

Tạo worker/job mẫu chạy theo lịch để xác minh telemetry phát hiện usage. Kiểm tra observation window có bao phủ lịch thực tế.

## 30. Ví dụ migration SQL đầy đủ theo phase

Ví dụ dưới đây minh họa thay **full_name** bằng **display_name** cho trường hợp có thể giữ nguyên string. Với thay đổi domain phức tạp, cần mapping riêng.

### Phase A: expand

```sql
ALTER TABLE customers
    ADD COLUMN display_name text;
```

### Phase B: compatible write

Trong ứng dụng mới, ghi cả hai cột trong cùng transaction:

```sql
UPDATE customers
SET
    full_name = $1,
    display_name = $1
WHERE id = $2;
```

Trong giai đoạn này, app cũ vẫn chỉ ghi **full_name**. Nếu có old writers, dùng trigger hoặc một cơ chế đồng bộ khác để lấp **display_name**.

### Phase C: backfill

Chạy batch lặp lại từ worker/job:

```sql
WITH batch AS (
    SELECT id
    FROM customers
    WHERE display_name IS NULL
      AND full_name IS NOT NULL
    ORDER BY id
    LIMIT 500
    FOR UPDATE SKIP LOCKED
)
UPDATE customers AS c
SET display_name = c.full_name
FROM batch
WHERE c.id = batch.id
  AND c.display_name IS NULL;
```

Commit sau mỗi batch. Đo rows updated, WAL, lag và mismatch.

### Phase D: validate

```sql
SELECT count(*) AS rows_missing_display_name
FROM customers
WHERE full_name IS NOT NULL
  AND display_name IS NULL;
```

Đối chiếu các giá trị:

```sql
SELECT count(*) AS mismatches
FROM customers
WHERE display_name IS DISTINCT FROM full_name;
```

Query mismatch này chỉ đúng khi business rule là hai strings giống nhau.

### Phase E: switch read

App v2 chuyển sang đọc **display_name**; canary trước, sau đó tăng traffic. Giữ fallback và old column trong observation window.

### Phase F: stop legacy write

Sau khi mọi writers đã nâng cấp, dừng ghi **full_name**. Theo dõi old-column references qua instrumentation/logging.

### Phase G: contract

Khi đã hết legacy readers và rollback window đã đóng:

```sql
BEGIN;
SET LOCAL lock_timeout = '2s';
ALTER TABLE customers
    DROP COLUMN full_name;
COMMIT;
```

Xóa trigger, dual-write code và fallback trong các release phù hợp. Migration này không thể rollback bằng cách đơn giản revert app; phải có phương án phục hồi dữ liệu nếu cần.

## 31. Checklist trước khi bắt đầu

- [ ] Xác định schema hiện tại và schema mục tiêu.
- [ ] Liệt kê tất cả application versions và consumers.
- [ ] Xác định readers, writers, workers, jobs, ETL, BI và CDC.
- [ ] Chọn nguồn dữ liệu chuẩn trong từng phase.
- [ ] Định nghĩa mapping và xử lý dữ liệu ngoại lệ.
- [ ] Kiểm tra DDL lock/rewrite behavior trên đúng PostgreSQL version.
- [ ] Ước lượng disk, WAL, I/O và replication impact.
- [ ] Chọn batch size và pause/resume strategy.
- [ ] Xác định index/constraint rollout.
- [ ] Xây dựng compatibility matrix.
- [ ] Thiết kế feature flags và observability.
- [ ] Xác định rollback boundary.
- [ ] Rehearse trên staging có dữ liệu đại diện.
- [ ] Chỉ định owner và người phê duyệt contract.

## 32. Checklist expand

- [ ] Schema mới chỉ thêm cấu trúc cần thiết.
- [ ] Schema cũ vẫn tồn tại và hoạt động.
- [ ] Cột mới cho phép NULL nếu cần backfill.
- [ ] Default không tạo rewrite ngoài dự kiến.
- [ ] DDL có lock_timeout phù hợp.
- [ ] Index lớn được tạo bằng phương thức phù hợp.
- [ ] Constraint có thể được validate theo phase.
- [ ] App v1 vẫn pass trên schema mới.
- [ ] Migration history được ghi nhận.
- [ ] Metrics và alerts đã sẵn sàng.

## 33. Checklist migrate

- [ ] App mới hiểu cả trạng thái dữ liệu cũ và mới.
- [ ] Writer đồng bộ representations theo một source of truth.
- [ ] Trigger/dual-write có conflict policy rõ ràng nếu dùng.
- [ ] Backfill chia batch và có thể retry.
- [ ] Batch commit ngắn, có pause/resume.
- [ ] Backfill không ghi đè concurrent updates.
- [ ] Rows remaining và mismatch được theo dõi.
- [ ] Replication lag và disk headroom trong budget.
- [ ] Canary read switch thành công.
- [ ] Fallback rate tiến về zero.
- [ ] Không còn old writers sau cutover.

## 34. Checklist contract

- [ ] Tất cả app instances đã dùng schema mới.
- [ ] Tất cả workers và scheduled jobs đã dùng schema mới.
- [ ] BI/ETL/CDC/external consumers đã xác nhận.
- [ ] Không còn legacy reads trong observation window.
- [ ] Không còn legacy writes.
- [ ] Backfill và reconciliation đã hoàn tất.
- [ ] New constraints/indexes đã validate.
- [ ] Rollback window và approval đã được xác nhận.
- [ ] DDL lock impact đã được kiểm tra.
- [ ] Drop legacy objects bằng migration có audit.
- [ ] Xóa trigger, feature flag và compatibility code.
- [ ] Monitoring không còn phát hiện old schema usage.

## 35. Runbook khi migration gặp sự cố

### 35.1. DDL không lấy được lock

1. Kiểm tra **pg_stat_activity** và **pg_locks**.
2. Xác định transaction giữ lock.
3. Kiểm tra DDL có đang xếp hàng và chặn query mới không.
4. Hủy migration nếu vượt lock_timeout/maintenance budget.
5. Xử lý transaction blocker theo incident policy.
6. Retry trong cửa sổ ít tải với lock_timeout ngắn.

### 35.2. Backfill chậm hoặc gây lag

1. Pause worker.
2. Kiểm tra WAL generation, replica lag, I/O và vacuum.
3. Giảm batch size hoặc concurrency.
4. Xác định index/trigger làm tăng write amplification.
5. Resume từ progress marker/idempotent predicate.
6. Theo dõi mismatch và remaining rows.

### 35.3. Dual-write divergence

1. Tạm dừng rollout hoặc new-write flag.
2. Xác định representation authoritative.
3. Tìm nguyên nhân: old writer, trigger, race, retry hoặc partial commit.
4. Chọn reconciliation direction.
5. Sửa logic và test concurrent updates.
6. Reconcile dữ liệu theo batch.
7. Chỉ bật lại rollout khi mismatch trở về ngưỡng chấp nhận.

### 35.4. App mới không đọc được schema mới

1. Tắt read flag/canary.
2. Quay về legacy read nếu legacy còn được đồng bộ.
3. Giữ schema expanded.
4. Thu thập SQLSTATE và failing query.
5. Sửa app hoặc migration theo hướng forward-compatible.
6. Re-run regression trước khi switch lại.

### 35.5. Contract đã chạy nhưng app lỗi

1. Ngừng rollout và đánh giá traffic.
2. Xác định old dependency còn ở đâu.
3. Chọn forward fix hoặc phục hồi schema.
4. Nếu recreate column, xác định data source đáng tin cậy để repopulate.
5. Không tạo cột rỗng rồi coi rollback đã hoàn tất.
6. Validate dữ liệu và consumer behavior trước khi mở traffic.

## 36. Best practices

- Chia thay đổi destructive thành additive expansion và contract riêng.
- Thiết kế app v2 đọc được schema ở trạng thái chuyển tiếp.
- Giữ một nguồn dữ liệu chuẩn trong mỗi phase.
- Đưa backfill ra khỏi migration transaction dài.
- Dùng batch, keyset pagination và idempotent predicates.
- Theo dõi old reads/writes, fallback và data divergence.
- Dùng CREATE INDEX CONCURRENTLY khi phù hợp và xử lý index invalid.
- Dùng NOT VALID/VALIDATE CONSTRAINT cho constraints hỗ trợ.
- Đặt lock_timeout và kiểm soát DDL queue.
- Test mixed-version và concurrent writes trên staging.
- Xem worker, cron, BI, ETL và CDC là application consumers.
- Chỉ contract khi có evidence không còn dependency cũ.
- Giữ rollback path rõ ràng trước khi chuyển source of truth.
- Dọn trigger, feature flags và legacy code sau khi schema transition hoàn tất.
- Lưu migration ID, owner, progress, metrics và evidence.

## 37. Những hiểu lầm thường gặp

### 37.1. “Thêm cột là luôn an toàn”

Không phải luôn luôn. App có thể dùng SELECT *, insert theo column order, ORM schema assumptions hoặc row serialization phụ thuộc số cột. DDL vẫn cần lock.

### 37.2. “Đổi tên cột là thao tác metadata nên không ảnh hưởng”

DDL có thể nhanh nhưng mọi query cũ dùng tên cột sẽ lỗi ngay khi rename commit.

### 37.3. “Backfill chạy xong nghĩa có thể drop cột cũ”

Còn phải xác nhận readers/writers, scheduled jobs, external consumers, fallback usage và rollback window.

### 37.4. “Dual-write luôn bảo đảm dữ liệu đồng nhất”

Chỉ khi có transaction/consistency mechanism, source of truth và conflict policy rõ ràng. Hai writes độc lập có thể partial success.

### 37.5. “Trigger xử lý được mọi writer”

Trigger có thể không chạy theo cùng cách ở bulk load, replication hoặc session settings đặc biệt; logic hai chiều có thể tạo loop và conflict.

### 37.6. “CREATE INDEX CONCURRENTLY không ảnh hưởng workload”

Lệnh giảm blocking nhưng vẫn tiêu thụ I/O/CPU, cần nhiều scan và có thể để lại invalid index khi thất bại.

### 37.7. “Drop column lập tức giải phóng disk”

Không nhất thiết. Physical space có thể được thu hồi theo quá trình rewrite/vacuum và các thao tác khác.

### 37.8. “Rollback chỉ cần deploy lại app cũ”

Nếu app mới đã ghi dữ liệu vào representation mới hoặc old schema đã bị drop, app cũ có thể không nhìn thấy dữ liệu mới. Cần reverse sync/reconciliation hoặc forward fix.

## 38. Tài liệu chính thức tham khảo

- [PostgreSQL — ALTER TABLE](https://www.postgresql.org/docs/current/sql-altertable.html): thêm/xóa cột, constraint validation và table alteration.
- [PostgreSQL — CREATE INDEX](https://www.postgresql.org/docs/current/sql-createindex.html): index build, CONCURRENTLY và lưu ý transaction.
- [PostgreSQL — Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html): table locks và lock modes.
- [PostgreSQL — System Catalogs](https://www.postgresql.org/docs/current/catalogs.html): catalog metadata và dependencies.
- [PostgreSQL — Monitoring Statistics](https://www.postgresql.org/docs/current/monitoring-stats.html): session, progress và database statistics.
- [PostgreSQL — Progress Reporting](https://www.postgresql.org/docs/current/progress-reporting.html): theo dõi tiến độ các hoạt động dài.
- [PostgreSQL — CREATE TRIGGER](https://www.postgresql.org/docs/current/sql-createtrigger.html): trigger behavior.
- [PostgreSQL — ALTER TYPE](https://www.postgresql.org/docs/current/sql-altertype.html): thay đổi enum và các data types.
- [PostgreSQL — Constraints](https://www.postgresql.org/docs/current/ddl-constraints.html): CHECK, NOT NULL, UNIQUE và foreign keys.
- [PostgreSQL — Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html): snapshot và concurrent transaction behavior.

Các chi tiết về lock, table rewrite, enum transaction semantics và tối ưu DDL có thể khác theo major version. Kiểm tra tài liệu của đúng phiên bản production/target và rehearsal trên staging có dữ liệu đại diện trước khi chạy migration lớn.

## 39. Tổng kết

Expand and contract giúp thay đổi schema trong khi nhiều phiên bản ứng dụng cùng hoạt động. Thay vì đổi cấu trúc và deploy code trong một bước, ta thêm schema mới, triển khai code tương thích, chuyển dữ liệu, chuyển traffic và chỉ loại bỏ schema cũ khi mọi dependency đã biến mất.

1. **Expand:** thêm cột/bảng/index/constraint mới theo cách schema cũ vẫn hoạt động.
2. **Migrate:** deploy app tương thích, dual-write hoặc trigger khi cần, backfill theo batch và validate dữ liệu.
3. **Switch:** chuyển reads và writes bằng rollout/canary, theo dõi fallback, mismatch và old consumers.
4. **Contract:** dừng legacy writes, xác nhận không còn legacy reads, rồi mới drop cấu trúc cũ.
5. **Operate safely:** giới hạn lock, WAL, I/O và transaction duration; quan sát tiến độ và giữ pause/resume.
6. **Recover:** xác định rollback boundary trước khi chuyển source of truth; sau contract có thể cần forward fix hoặc phục hồi dữ liệu.

Một schema migration chỉ thực sự hoàn tất khi ứng dụng, workers, jobs và các consumer liên quan đều dùng contract mới, dữ liệu đã được xác minh và cấu trúc legacy có thể được gỡ bỏ an toàn.
