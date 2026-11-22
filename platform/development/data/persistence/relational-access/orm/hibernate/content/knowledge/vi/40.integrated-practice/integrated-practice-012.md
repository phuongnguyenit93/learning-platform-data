# Thực hiện một thay đổi lược đồ với migration và kiểm thử tương thích

Một tính năng mới yêu cầu mỗi đơn hàng có `external_reference` để đối chiếu với hệ thống đối tác. Trong Java, thêm một field vào entity chỉ mất vài phút. Nhưng nếu production đang chạy nhiều phiên bản ứng dụng, bảng `orders` đã có hàng triệu rows và các worker cũ vẫn ghi dữ liệu, thay đổi schema có thể gây downtime hoặc làm hỏng dữ liệu.

Một thay đổi database an toàn phải phối hợp ít nhất bốn thứ: **schema, dữ liệu hiện có, phiên bản ứng dụng đang chạy và quy trình triển khai**. Hibernate mapping chỉ là một phần của bức tranh. Migration tạo hoặc thay đổi schema; backfill chuyển dữ liệu cũ; compatibility tests chứng minh phiên bản ứng dụng cũ và mới có thể hoạt động trên schema ở từng giai đoạn.

Bài này dùng thay đổi `external_reference` làm ví dụ xuyên suốt. Ta sẽ thêm cột nullable, triển khai ứng dụng có khả năng đọc/ghi tương thích, backfill dữ liệu theo chunks, xác minh dữ liệu, siết constraint và chỉ loại bỏ cấu trúc cũ sau khi mọi phiên bản cũ đã ngừng sử dụng.

~~~text
Thiết kế thay đổi
      |
      v
Expand schema (cột nullable / index mới)
      |
      v
Deploy code tương thích cả schema cũ và mới
      |
      v
Backfill dữ liệu cũ theo chunks
      |
      v
Validate dữ liệu + bật read path mới
      |
      v
Enforce constraints (NOT NULL / UNIQUE)
      |
      v
Contract schema (bỏ cột/logic cũ khi an toàn)
      |
      v
Kiểm thử, quan sát và xác nhận
~~~

**Nguyên tắc cốt lõi:** Migration schema và migration dữ liệu là hai việc liên quan nhưng khác nhau. Thực hiện thay đổi theo các bước tương thích ngược/tiến để mỗi lần deploy đều có thể chạy cùng schema đang tồn tại, kể cả khi nhiều application instances chưa được nâng cấp đồng thời.

> **Phạm vi:** Java 17+, Spring Boot, Spring Data JPA, Hibernate ORM 6.x, Jakarta Persistence, Flyway hoặc Liquibase và PostgreSQL là bối cảnh minh họa. DDL, transactional DDL, online index creation, locking và migration tool syntax khác nhau theo DBMS/version. Ví dụ PostgreSQL phải được điều chỉnh nếu production dùng MySQL, SQL Server, Oracle hoặc database khác.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Lập kế hoạch một thay đổi schema có application instances cũ và mới cùng hoạt động.
2. Phân biệt schema migration, data migration và Hibernate schema generation.
3. Áp dụng chiến lược expand–migrate–contract.
4. Viết migration versioned bằng Flyway hoặc Liquibase.
5. Thiết kế nullable-first rollout và backfill theo chunks.
6. Giữ tương thích giữa application versions trong rolling deployment.
7. Thêm NOT NULL, UNIQUE, index và foreign key an toàn.
8. Kiểm tra Hibernate mapping với schema được quản lý bởi migration.
9. Viết integration tests trên database production-like bằng Testcontainers.
10. Kiểm tra migration từ schema trống và nâng cấp từ schema cũ có dữ liệu.
11. Xây dựng rollback/roll-forward, checkpoint và recovery strategy.
12. Quan sát migration progress và xử lý failure trong production.

## 2. Phân biệt schema migration và data migration

**Schema migration** thay đổi cấu trúc database:

- Thêm/xóa/đổi tên column.
- Tạo index, constraint, table hoặc sequence.
- Thay đổi data type, precision, nullability.
- Thay đổi foreign key hoặc unique constraint.

**Data migration/backfill** thay đổi nội dung rows hiện có:

- Populate cột mới từ dữ liệu cũ.
- Chuẩn hóa values.
- Chuyển enum code.
- Gộp/tách dữ liệu.
- Tạo khóa hoặc reference mới.
- Loại bỏ dữ liệu legacy sau khi đã chuyển.

Ví dụ thêm `external_reference` gồm ít nhất hai việc:

1. `ALTER TABLE orders ADD COLUMN external_reference ...`
2. Tính và ghi giá trị cho những orders đã tồn tại.

Chỉ làm bước đầu không hoàn thành tính năng nếu code mới yêu cầu mọi row có reference.

## 3. Vì sao không dùng Hibernate để tự sửa schema production?

Hibernate có các lựa chọn `hibernate.hbm2ddl.auto` như `none`, `validate`, `update`, `create` hoặc `create-drop` tùy cấu hình/version.

Trong production, nên để một migration tool được quản lý rõ ràng làm source of truth cho schema. Lý do:

- Migration có thứ tự và lịch sử.
- Có thể review trong code review.
- Có thể chạy ở pipeline/operation riêng.
- Có thể kiểm thử upgrade từ version trước.
- Có thể ghi nhận checksum/version.
- Có thể thực hiện data backfill có kiểm soát.
- Tránh mỗi application instance tự thay schema khi khởi động.

`update` không phải một chiến lược migration production đầy đủ: nó không mô tả rõ data transformation, deployment compatibility hoặc rollback.

## 4. Thiết kế thay đổi trước khi viết DDL

Giả sử bảng hiện tại:

~~~sql
CREATE TABLE orders (
    id BIGINT PRIMARY KEY,
    tenant_id VARCHAR(50) NOT NULL,
    source_code VARCHAR(64),
    status VARCHAR(30) NOT NULL,
    created_at TIMESTAMP NOT NULL
);
~~~

Yêu cầu mới:

- Mỗi order có external reference do partner cung cấp hoặc được sinh từ source data.
- Reference phải ổn định.
- Không được trùng trong cùng tenant.
- API mới cần trả reference.
- Các instances cũ có thể vẫn đọc/ghi `source_code` trong thời gian rolling deployment.

Trước khi viết migration, phải quyết định:

- Reference có bắt buộc với mọi historical order không?
- Có thể suy ra từ `source_code` không?
- Nếu không có nguồn, có được sinh giá trị thay thế không?
- Có unique scope toàn hệ thống hay theo tenant?
- Reference có case-sensitive không?
- Có thể thay đổi sau khi tạo order không?
- Dữ liệu mới được ghi bởi những ứng dụng/worker nào?
- Có cần giữ `source_code` lâu dài cho integrations cũ không?

Đây là domain decisions; migration không nên tự bịa business values để lấp NULL.

## 5. Kiểm tra tương thích giữa application và schema

Trong rolling deployment, database schema và application version không đổi cùng một thời điểm. Có thể tồn tại:

| Application | Schema | Tình huống |
|---|---|---|
| App v1 | Schema cũ | Trạng thái ban đầu |
| App v1 | Schema mở rộng | Cũ chạy trên schema mới |
| App v2 | Schema mở rộng | Phiên bản mới chính |
| App v1 + v2 | Schema mở rộng | Rolling deploy |
| App v2 | Schema đã contract | Sau khi instances cũ dừng |
| App v1 | Schema đã contract | Không được phép nếu v1 còn cần cột cũ |

Một migration an toàn cần biết những cặp version nào phải hoạt động. Không chỉ test “app mới chạy với schema mới”.

## 6. Chiến lược expand–migrate–contract

### Expand

Thêm cấu trúc mới theo cách ít phá vỡ code cũ:

- Thêm column nullable.
- Tạo table mới nhưng chưa bắt buộc dùng.
- Thêm index/constraint chưa gây reject dữ liệu cũ.
- Giữ cột cũ.

### Migrate

Chuyển ứng dụng và dữ liệu:

- Deploy code có thể đọc schema mới nhưng vẫn fallback schema cũ khi cần.
- Dual-write trong thời gian tương thích nếu instances cũ còn đọc cột cũ.
- Backfill historical rows.
- Validate dữ liệu.
- Bật read path mới bằng feature flag hoặc rollout có kiểm soát.

### Contract

Sau khi đã chứng minh không còn consumer cũ:

- Đổi cột mới sang NOT NULL nếu domain yêu cầu.
- Thêm unique/FK constraints còn thiếu.
- Ngừng ghi cột cũ.
- Deploy code không còn đọc cột cũ.
- Xóa cột cũ trong migration riêng.

Không gộp expand và contract vào một migration duy nhất nếu cần rolling deployment.

## 7. Compatibility matrix cho ví dụ external_reference

| Giai đoạn | Schema | App behavior | Có tương thích App v1? |
|---|---|---|---|
| Ban đầu | Chỉ `source_code` | V1 đọc/ghi source_code | Có |
| Expand | Thêm nullable `external_reference` | V1 chưa biết cột mới | Có |
| Dual-write deploy | Có cả hai cột | V2 ghi cả hai, đọc fallback | Có nếu logic cũ vẫn được giữ |
| Backfill | Populate cột mới | V1 và V2 cùng hoạt động | Có nếu write paths được phối hợp |
| Read switch | Cột mới đã đầy đủ | V2 đọc external_reference | V1 vẫn có thể chạy nếu cột cũ còn đúng |
| Contract | Cột cũ bị bỏ | Chỉ V2 | Không |

Compatibility matrix giúp quyết định thời điểm an toàn để chạy migration phá vỡ tương thích.

## 8. Bước 0: kiểm kê mọi consumer của schema

Trước khi sửa, tìm các nơi đọc/ghi `orders.source_code`:

- Hibernate entities/repositories.
- Native SQL queries.
- Batch jobs.
- Scheduled tasks.
- ETL/reporting jobs.
- Stored procedures/triggers.
- Other services.
- BI tools hoặc data warehouse pipelines.
- Admin scripts và operational tools.

Một cột có thể không còn xuất hiện trong Java code nhưng vẫn được một integration khác sử dụng. Chỉ drop column sau khi đã xác định consumer và owner của chúng.

## 9. Migration đầu tiên: thêm cột nullable

Flyway SQL migration ví dụ:

`V102__add_external_reference_to_orders.sql`

~~~sql
ALTER TABLE orders
    ADD COLUMN external_reference VARCHAR(64);
~~~

Cột mới nullable để các application instances cũ tiếp tục INSERT mà không biết cột này.

Với PostgreSQL, thêm column nullable không có default thường là thao tác nhẹ hơn việc thêm cột NOT NULL với default trên một số phiên bản/cấu hình, nhưng lock acquisition vẫn xảy ra và phải được kiểm tra trên DB/version thực tế.

Không giả định mọi `ALTER TABLE` đều metadata-only hoặc không block traffic.

## 10. Vì sao thêm NOT NULL ngay từ đầu có thể phá rolling deployment?

Giả sử v1 INSERT:

~~~sql
INSERT INTO orders(id, tenant_id, source_code, status, created_at)
VALUES (?, ?, ?, ?, ?);
~~~

Nếu migration thêm:

~~~sql
ALTER TABLE orders
ADD COLUMN external_reference VARCHAR(64) NOT NULL;
~~~

và không có default phù hợp, INSERT từ v1 sẽ fail vì không cung cấp giá trị cho cột mới.

Ngay cả khi đặt database default, phải xác nhận:

- Default có đúng business meaning không?
- Hibernate insert behavior có bỏ cột để DB default áp dụng không?
- Code cũ có đọc được giá trị đó không?
- Default có gây duplicate references không?
- Có cần backfill historical data không?

Nullable-first thường giúp mở rộng schema an toàn hơn; constraint sẽ được siết sau khi dữ liệu và application đã sẵn sàng.

## 11. Hibernate mapping trong giai đoạn expand

Entity v2 có thể thêm:

~~~java
@Entity
@Table(name = "orders")
public class Order {

    @Id
    private Long id;

    @Column(name = "tenant_id", nullable = false, length = 50)
    private String tenantId;

    @Column(name = "source_code", length = 64)
    private String sourceCode;

    @Column(name = "external_reference", length = 64)
    private String externalReference;

    @Column(name = "status", nullable = false, length = 30)
    private String status;
}
~~~

Trong giai đoạn đầu, `externalReference` vẫn nullable. Không khai báo `nullable=false` trước khi dữ liệu và rollout đã bảo đảm invariant.

Annotation `nullable` là mapping/DDL metadata; schema migration mới là thay đổi thực tế trong database khi dùng Flyway/Liquibase.

## 12. Code mới phải tương thích với dữ liệu cũ

Nếu historical rows chưa được backfill, code đọc cần có policy:

~~~java
public String referenceForDisplay(Order order) {
    if (order.getExternalReference() != null) {
        return order.getExternalReference();
    }
    return legacyReferenceFrom(order.getSourceCode());
}
~~~

Đây chỉ là ví dụ nếu `source_code` thực sự có thể đại diện cho reference theo domain. Nếu không tương đương, không được dùng fallback giả tạo.

Có thể tách logic mapping thành một domain service để API, worker và report dùng cùng một rule. Không lặp fallback logic theo nhiều nơi.

## 13. Dual-write trong thời gian rolling deployment

Nếu app v1 chỉ đọc `source_code`, app v2 cần tiếp tục cập nhật `source_code` trong khi v1 còn chạy.

~~~java
@Transactional
public void assignReference(Order order, String reference) {
    order.setExternalReference(reference);
    order.setSourceCode(reference); // Chỉ khi hai fields có semantics tương đương.
}
~~~

Dual-write cần có owner và thời điểm kết thúc. Nếu hai fields có semantics khác nhau, không copy mù; cần transformation rõ ràng.

Các write paths khác cũng phải được cập nhật:

- API requests.
- Message consumers.
- Scheduled jobs.
- Import pipelines.
- Admin tools.
- Native SQL writers.

Nếu một writer chỉ cập nhật cột cũ sau khi backfill, cột mới có thể stale. Có thể cần database trigger, dual-write ở mọi writers hoặc một cơ chế đồng bộ được kiểm soát.

## 14. Dual-read và feature flag

Trong rollout, có thể triển khai:

~~~java
public String resolveReference(Order order) {
    if (featureFlags.useExternalReference()) {
        return order.getExternalReference();
    }
    return order.getSourceCode();
}
~~~

Feature flag cho phép chuyển read path sau khi backfill/validation hoàn tất.

Điều kiện bật flag:

- Backfill complete.
- Không còn unexpected NULLs.
- Duplicate checks pass.
- New writes dual-write đúng.
- Monitoring không thấy mismatch.
- Rollback path đã được chuẩn bị.

Không bật feature flag chỉ vì migration SQL chạy thành công.

## 15. Backfill historical data là một job riêng

Sau khi column đã tồn tại, cần populate rows cũ. Nếu `source_code` là nguồn đúng:

~~~sql
UPDATE orders
SET external_reference = source_code
WHERE external_reference IS NULL
  AND source_code IS NOT NULL;
~~~

Với bảng nhỏ, câu lệnh này có thể phù hợp. Với bảng lớn, một UPDATE toàn bảng có thể tạo lock contention, WAL/transaction log lớn, replication lag và vacuum pressure.

Hãy đo volume và DB behavior trước khi chọn một câu UPDATE duy nhất.

## 16. Backfill theo chunks

Một cách tổng quát:

1. Chọn một nhóm IDs có `external_reference IS NULL`.
2. Cập nhật nhóm đó.
3. Commit transaction.
4. Lưu checkpoint hoặc tiến cursor.
5. Lặp đến khi hết rows.
6. Chạy reconciliation query để xác nhận.

Pseudocode:

~~~java
while (true) {
    List<Long> ids = repository.findNextUnprocessedIds(lastId, 500);

    if (ids.isEmpty()) {
        break;
    }

    transactionTemplate.executeWithoutResult(status -> {
        repository.backfillChunk(ids);
    });

    lastId = ids.get(ids.size() - 1);
    checkpointStore.save(lastId);
}
~~~

Các methods cần được thiết kế để query và update đúng tenant/scope, có ordering ổn định và transaction boundaries rõ. Nếu có nhiều workers, dùng claiming/locking strategy phù hợp để tránh cùng xử lý một chunk.

## 17. Keyset cursor cho backfill

Offset pagination lớn thường tốn chi phí skip rows và dễ thay đổi page boundary khi dữ liệu biến động.

Dùng keyset:

~~~sql
SELECT id
FROM orders
WHERE id > :last_id
  AND external_reference IS NULL
ORDER BY id
LIMIT 500;
~~~

Sau khi xử lý thành công chunk, cập nhật `last_id` đến ID cuối đã commit.

Cần quyết định xử lý các rows được tạo mới trong lúc job chạy. Có thể:

- Ghi nhận một high-water mark lúc bắt đầu.
- Đảm bảo new writers luôn populate cột mới.
- Chạy một reconciliation pass cuối.
- Dùng queue/change capture nếu data source liên tục thay đổi.

Checkpoint phải được ghi sau khi chunk commit để tránh bỏ qua dữ liệu chưa được cập nhật.

## 18. Idempotency của backfill

Backfill nên có thể chạy lại an toàn:

~~~sql
UPDATE orders
SET external_reference = source_code
WHERE id = :id
  AND external_reference IS NULL;
~~~

Predicate `IS NULL` giúp không ghi đè giá trị đã được application v2 gán.

Nếu transformation phức tạp, phải xác định:

- Có deterministic không?
- Chạy hai lần có tạo cùng output không?
- Có thể overwrite dữ liệu mới hơn không?
- Có cần lưu source/version của transformation?
- Có thể resume từ checkpoint không?

Một migration/job có thể fail giữa chừng; idempotency giúp restart mà không làm hỏng rows đã hoàn thành.

## 19. Race condition giữa backfill và live writes

Giả sử backfill đọc `source_code = A`, trong lúc application đổi reference thành B. Nếu backfill sau đó ghi A vào `external_reference`, nó có thể ghi đè dữ liệu mới.

Các cách xử lý:

- Update chỉ khi target vẫn NULL.
- Dual-write đồng thời trong app mới.
- Dùng version/timestamp predicate.
- Lock rows khi xử lý chunk nếu phù hợp.
- Dùng trigger hoặc change capture nếu cần đồng bộ liên tục.
- Reconcile sau backfill.

Không giữ một transaction khóa toàn bảng chỉ để tránh race nếu bảng lớn và production traffic đang chạy.

## 20. Không sinh giá trị giả để lấp NULL

Nếu `source_code` không đủ để tạo `external_reference`, không làm:

~~~sql
UPDATE orders
SET external_reference = 'UNKNOWN'
WHERE external_reference IS NULL;
~~~

Một giá trị giả có thể:

- Vi phạm uniqueness.
- Gây nhầm lẫn khi đối soát.
- Làm downstream coi record đã đồng bộ.
- Che mất dữ liệu nguồn thiếu.
- Không thể khôi phục business meaning.

Thay vào đó, tạo report rows không thể backfill, xác định policy nghiệp vụ: giữ nullable, gửi manual remediation, reject/close record hoặc tạo reference theo thuật toán được domain phê duyệt.

## 21. Kiểm tra completeness và duplicates

Sau backfill:

~~~sql
SELECT COUNT(*) AS missing_count
FROM orders
WHERE external_reference IS NULL;
~~~

Duplicate theo tenant:

~~~sql
SELECT tenant_id, external_reference, COUNT(*) AS occurrences
FROM orders
WHERE external_reference IS NOT NULL
GROUP BY tenant_id, external_reference
HAVING COUNT(*) > 1;
~~~

Kiểm tra mismatch nếu dual-write:

~~~sql
SELECT COUNT(*)
FROM orders
WHERE external_reference IS DISTINCT FROM source_code;
~~~

`IS DISTINCT FROM` là cú pháp PostgreSQL; DB khác cần biểu thức tương đương có xử lý NULL.

Các query này là validation evidence. Nếu bảng lớn, aggregate scans có thể tốn tài nguyên; lập kế hoạch đọc dữ liệu, index và load impact.

## 22. Thêm index và unique constraint

Nếu lookup thường dùng:

~~~sql
SELECT *
FROM orders
WHERE tenant_id = :tenant
  AND external_reference = :reference;
~~~

cân nhắc index:

~~~sql
CREATE INDEX ix_orders_tenant_external_reference
ON orders(tenant_id, external_reference);
~~~

Nếu yêu cầu uniqueness:

~~~sql
ALTER TABLE orders
ADD CONSTRAINT uq_orders_tenant_external_reference
UNIQUE (tenant_id, external_reference);
~~~

Trước khi thêm unique constraint, phải kiểm tra duplicates và xác định semantics với NULL của DBMS. Nhiều DB cho phép nhiều NULL trong unique constraint; behavior có thể khác theo DBMS/index type.

Index build trên bảng lớn có thể block writes hoặc tạo tải đáng kể. Với PostgreSQL, `CREATE INDEX CONCURRENTLY` có thể giảm blocking nhưng có các giới hạn, bao gồm không chạy trong transaction block thông thường; cần cấu hình migration tool cho migration không transactional theo hướng dẫn version cụ thể.

## 23. Thêm NOT NULL sau khi backfill

Chỉ sau khi mọi writers đã populate field và historical rows đã hoàn tất:

~~~sql
ALTER TABLE orders
ALTER COLUMN external_reference SET NOT NULL;
~~~

Trước khi chạy:

- `missing_count` phải bằng 0.
- New writes đã ghi field.
- Không còn app version nào bỏ qua field.
- Backfill reconciliation pass đã xong.
- Lock/validation impact được đánh giá.
- Rollback/roll-forward plan sẵn sàng.

Trên PostgreSQL, có thể dùng CHECK constraint `NOT VALID`, sau đó `VALIDATE CONSTRAINT`, rồi chuyển sang NOT NULL theo quy trình phù hợp version để giảm thời gian giữ lock trong một số trường hợp. Đây là kỹ thuật DB-specific; không áp dụng cú pháp đó cho DB khác.

## 24. Dùng CHECK constraint để xác minh trước

Ví dụ PostgreSQL:

~~~sql
ALTER TABLE orders
ADD CONSTRAINT ck_orders_external_reference_present
CHECK (external_reference IS NOT NULL) NOT VALID;
~~~

Sau đó:

~~~sql
ALTER TABLE orders
VALIDATE CONSTRAINT ck_orders_external_reference_present;
~~~

`NOT VALID` cho phép thêm constraint mà chưa scan toàn bộ historical rows ngay tại thời điểm add, nhưng constraint vẫn được áp dụng với rows mới/được sửa theo PostgreSQL semantics. Sau khi validate, có thể dùng để hỗ trợ bước `SET NOT NULL` tùy version/plan.

Phải đọc PostgreSQL docs đúng version và kiểm thử locking. Không dùng CHECK NOT VALID như một cách bỏ qua data backfill.

## 25. Đổi tên hoặc xóa cột cần expand–contract

Một rename trực tiếp:

~~~sql
ALTER TABLE orders
RENAME COLUMN source_code TO external_reference;
~~~

có thể làm application v1 fail ngay khi vẫn truy cập `source_code`.

Thay vào đó:

1. Thêm cột mới.
2. Deploy code đọc/ghi tương thích cả hai.
3. Backfill cột mới.
4. Chuyển read path.
5. Dừng ghi cột cũ.
6. Chờ tất cả old consumers ngừng.
7. Drop cột cũ trong migration riêng.

Giữ migration nhỏ và rõ để mỗi giai đoạn có thể deploy/verify độc lập.

## 26. Flyway versioned migrations

Cấu trúc phổ biến:

~~~text
src/main/resources/db/migration/
    V101__create_orders.sql
    V102__add_external_reference.sql
    V103__create_external_reference_index.sql
    V104__enforce_external_reference_not_null.sql
    V105__drop_legacy_source_code.sql
~~~

Flyway quản lý migration version và ghi lịch sử thực thi trong schema history table. Tên/version phải tăng theo quy tắc dự án.

Một versioned migration đã chạy ở môi trường dùng chung nên được coi là immutable. Nếu phát hiện lỗi, tạo migration mới để sửa trạng thái; không chỉnh file cũ rồi kỳ vọng checksum tự khớp ở mọi môi trường.

## 27. Ví dụ Flyway migration

File `V102__add_external_reference.sql`:

~~~sql
ALTER TABLE orders
    ADD COLUMN external_reference VARCHAR(64);
~~~

File `V103__add_external_reference_index.sql` có thể tạo index sau khi đã đánh giá dữ liệu/lookup requirements:

~~~sql
CREATE INDEX ix_orders_tenant_external_reference
ON orders(tenant_id, external_reference);
~~~

Không nhất thiết phải tạo index ngay khi thêm cột nếu query chưa dùng. Index tăng write cost và storage; chọn theo query workload.

Với PostgreSQL online index creation, tách migration riêng và cấu hình non-transactional execution theo Flyway version/tool conventions. Không đặt `CREATE INDEX CONCURRENTLY` trong một migration transaction thông thường.

## 28. Liquibase changelog

Liquibase mô tả changesets trong XML/YAML/JSON/SQL formatted changelog.

Ví dụ YAML khái niệm:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 102-add-external-reference
      author: platform
      changes:
        - addColumn:
            tableName: orders
            columns:
              - column:
                  name: external_reference
                  type: varchar(64)
                  constraints:
                    nullable: true
~~~

Một changeset có identity và checksum. Nếu changeset đã chạy ở môi trường dùng chung, tránh sửa nội dung đã áp dụng; tạo changeset mới cho correction.

Liquibase preconditions có thể giúp xác định database state trước khi chạy changeset, nhưng không nên biến migration thành script mơ hồ có thể silently bỏ qua thay đổi bắt buộc.

## 29. Migration ordering và ownership

Migrations nên có:

- Version/ID duy nhất.
- Tên mô tả.
- Mục đích rõ.
- DDL/DML giới hạn.
- Owner/reviewer.
- Test evidence.
- Operational notes nếu có lock/backfill lớn.

Tránh hai branches tạo cùng migration version/ID. Khi merge, giải quyết thứ tự migration có chủ đích và kiểm tra schema history của từng environment.

Không chạy migration thủ công ngoài tool rồi để migration history không biết trạng thái; nếu đã có manual intervention, cần reconciliation theo quy trình tool chính thức.

## 30. Chạy migration ở startup hay deployment pipeline?

Có hai cách thường gặp:

**Migration chạy cùng application startup:**

- Dễ cấu hình.
- App không khởi động nếu migration fail.
- Nhiều instances có thể cùng cố migrate, tool cần locking.
- Startup có thể kéo dài.
- DDL lớn ảnh hưởng rollout availability.

**Migration chạy như deployment job riêng:**

- Có thể kiểm soát thời gian/owner.
- Có thể chạy trước rolling deploy.
- Logs/permissions riêng.
- Dễ phối hợp backup, lock monitoring và approval.
- Pipeline phải bảo đảm migration thành công trước bước cần schema mới.

Chọn theo platform. Với production migration lớn/rủi ro, job riêng thường cho khả năng kiểm soát vận hành tốt hơn. Dù chạy ở đâu, chỉ có một cơ chế quản lý schema được tin cậy.

## 31. DDL transaction behavior không giống mọi DB

Một số DB hỗ trợ transactional DDL cho nhiều operations; DB khác có implicit commits hoặc giới hạn transaction. Một migration thất bại có thể:

- Rollback toàn bộ DDL.
- Để lại một phần objects.
- Để lại invalid index.
- Giữ lock tới rollback/connection close.
- Làm migration history chưa ghi success nhưng schema đã đổi một phần.

Trước khi dựa vào rollback, kiểm tra docs DBMS và migration tool. Với operations không transactional, cần recovery instructions và cách phát hiện partial state.

## 32. Hibernate schema validation

Trong Spring Boot:

~~~properties
spring.jpa.hibernate.ddl-auto=validate
~~~

`validate` yêu cầu Hibernate kiểm tra một số mapping/schema compatibility khi khởi động, thay vì tự sửa schema.

Nó hữu ích để phát hiện:

- Table/column thiếu.
- Một số type mismatch.
- Mapping không khớp schema.

Nhưng nó không thay migration tests, không chứng minh data backfill đúng, không kiểm tra mọi index/constraint/trigger và không đảm bảo rolling compatibility với app cũ.

Dùng validation như một lớp kiểm tra bổ sung sau migration.

## 33. Annotation không thay migration

Entity:

~~~java
@Column(
    name = "external_reference",
    length = 64,
    nullable = false
)
private String externalReference;
~~~

Annotation mô tả mapping mong muốn. Nếu production database chưa có cột hoặc còn NULL rows, application có thể fail khi boot/insert/load.

Thứ tự rollout nên là:

1. Migration add nullable column.
2. Deploy code tương thích.
3. Backfill.
4. Validate.
5. Enforce NOT NULL.
6. Deploy mapping/validation chặt hơn nếu cần.

Không đưa `nullable=false` vào code v2 trước khi schema/data thật sự thỏa invariant.

## 34. Tương thích giữa Hibernate schema và migration DDL

Kiểm tra:

- Column SQL type và length.
- Numeric precision/scale.
- Timestamp precision/timezone semantics.
- Nullability/default.
- Identity/sequence strategy.
- Enum representation.
- Naming strategy.
- Foreign key/unique constraints.
- Indexes cần cho query.
- Schema/catalog names.

Hibernate dialect có thể map Java type sang SQL type khác nhau giữa DBMS. DDL migration nên phản ánh schema contract được review, không chỉ copy output từ một database local khác.

## 35. Application v1 và v2 cùng chạy trong rolling deploy

Kịch bản:

~~~text
T0: instances v1, schema cũ
T1: migration add nullable column
T2: instances v1 vẫn chạy trên expanded schema
T3: deploy v2 instances; v1 và v2 cùng nhận traffic
T4: v2 dual-write old + new fields
T5: backfill historical rows
T6: chuyển reads sang new field
T7: scale down/remove toàn bộ v1
T8: contract schema và xóa old field
~~~

Điểm quan trọng: tại T3–T6, cả hai phiên bản có thể ghi cùng bảng. Dual-write và fallback phải xử lý được mọi write paths.

Không chạy contract migration trước T7.

## 36. Code v2 tương thích schema expand

Trong giai đoạn đầu, mapping có thể chứa cả hai fields:

~~~java
@Column(name = "source_code")
private String sourceCode;

@Column(name = "external_reference")
private String externalReference;
~~~

Service:

~~~java
@Transactional
public void updateReference(Order order, String value) {
    order.setExternalReference(value);
    order.setSourceCode(value); // Chỉ khi semantics tương đương.
}
~~~

Nếu source_code có format khác, tạo mapper riêng. Không ép hai fields đồng nhất nếu business meaning khác nhau.

## 37. Xác định lúc chuyển read path

Một feature flag có thể điều khiển read source:

~~~java
String getReference(Order order) {
    if (flags.useExternalReference()) {
        return order.getExternalReference();
    }
    return order.getSourceCode();
}
~~~

Trước khi bật:

- Backfill coverage đạt yêu cầu.
- Mismatch count bằng 0 hoặc có danh sách ngoại lệ được chấp nhận.
- New writes populate cả hai.
- Không còn worker cũ chỉ ghi source_code mà không có đồng bộ.
- Metrics/alerts không báo NULL hoặc duplicate mới.

Rollout flag theo tenant/cohort có thể giảm blast radius, nhưng phải giữ semantics nhất quán khi cùng một order được đọc bởi nhiều consumers.

## 38. Khi nào dừng dual-write?

Chỉ dừng ghi cột cũ khi:

- Không còn application instances v1.
- Không còn scheduled jobs/consumers cũ.
- External integrations không còn đọc cột cũ.
- Backfill đã hoàn tất và reconciliation pass thành công.
- Rollback về v1 không còn là phương án deployment hợp lệ, hoặc đã có compatibility plan khác.
- Observability cho thấy old-column traffic bằng 0 trong cửa sổ đủ dài.

Nếu vẫn cần rollback application version, giữ old column và dual-write thêm thời gian. Contract là bước không thể đảo ngược đơn giản nếu dữ liệu cũ đã bị xóa.

## 39. Test migration từ database trống

Một integration test phải chứng minh:

1. Tạo database trống.
2. Chạy toàn bộ migrations theo thứ tự.
3. Khởi tạo application context.
4. Hibernate schema validation pass.
5. Insert entity bằng mapping mới.
6. Query lại bằng repository/entity manager.
7. Kiểm tra constraints/indexes cần thiết.

Test này phát hiện migration mới không tạo được schema cuối cùng từ đầu.

Nhưng nó không phát hiện lỗi upgrade trên database cũ đã có dữ liệu. Cần thêm test upgrade.

## 40. Test upgrade từ schema version trước

Tạo database ở trạng thái V101 với dữ liệu đại diện:

~~~sql
INSERT INTO orders(id, tenant_id, source_code, status, created_at)
VALUES
    (1, 'tenant-a', 'EXT-001', 'NEW', CURRENT_TIMESTAMP),
    (2, 'tenant-a', NULL, 'NEW', CURRENT_TIMESTAMP),
    (3, 'tenant-b', 'EXT-003', 'PAID', CURRENT_TIMESTAMP);
~~~

Sau đó:

- Chạy V102 add column.
- Chạy backfill process.
- Chạy validation.
- Chạy V103/V104 constraints khi đủ điều kiện.
- Boot app v2.
- Assert historical rows có đúng references hoặc nằm trong exception report theo policy.

Test phải dùng dữ liệu đại diện cho legacy edge cases, không chỉ một row sạch.

## 41. Test application cũ trên expanded schema

Đây là compatibility test quan trọng khi rolling deployment:

1. Tạo schema cũ.
2. Chạy migration expand.
3. Chạy code v1 (hoặc contract test đại diện SQL của v1).
4. INSERT/UPDATE theo write paths cũ.
5. Xác nhận không fail do column mới.
6. Xác nhận default/null semantics phù hợp.
7. Xác nhận v2 có thể đọc rows v1 vừa ghi theo fallback/backfill policy.

Nếu không thể chạy hai application versions trong cùng test suite, ít nhất tạo compatibility tests cho SQL contract và giữ artifact/container của v1 để kiểm tra deployment.

## 42. Test application mới trên expanded schema

App v2 có thể boot và thao tác trước khi contract:

- Entity mapping có nullable column.
- Repository query không giả định NOT NULL quá sớm.
- Fallback logic xử lý historical NULL.
- Dual-write hoạt động.
- API response xử lý record chưa backfill.
- Background jobs không bỏ sót rows.

Đây là schema version mà v2 sẽ gặp trong phần lớn rollout, nên cần test riêng.

## 43. Test old/new writer concurrency

Tạo hai actors:

- Writer v1 chỉ ghi `source_code`.
- Writer v2 ghi cả `source_code` và `external_reference`.

Dùng synchronization barrier để tạo interleaving, sau đó kiểm tra:

- Không có reference mới bị ghi đè bởi backfill cũ.
- Không có row trở thành inconsistent.
- Unique constraint không race.
- Transaction rollback không để một nửa dual-write.
- Reconciliation query phát hiện mismatches.

Nếu writers không thể dual-write cùng lúc (ví dụ service ngoài không sửa được), cần trigger/change capture hoặc một compatibility adapter ở database/integration boundary.

## 44. Test backfill idempotency và restart

Test mô phỏng:

1. Backfill chunk 1 commit.
2. Chunk 2 fail giữa chừng.
3. Job restart từ checkpoint.
4. Chunk 1 không bị overwrite/duplicate.
5. Chunk 2 hoàn thành.
6. Chạy job thêm lần nữa.
7. Kết quả không đổi.

Assert cả checkpoint và row values. Nếu checkpoint nằm trong cùng database, có thể lưu trong cùng transaction chunk để data và progress commit nguyên tử; nếu khác storage, cần thiết kế consistency protocol.

## 45. Test constraint migration

Trước khi thêm NOT NULL/UNIQUE:

- Seed NULL rows.
- Seed duplicate values.
- Chạy validation query.
- Xác nhận migration không thể contract khi data invalid.
- Sửa/backfill dữ liệu.
- Chạy lại validation.
- Thực hiện constraint migration.
- Thử INSERT NULL/duplicate sau migration và xác nhận DB từ chối.

Migration nên fail rõ ràng khi precondition không đạt, thay vì âm thầm xóa/ghi đè dữ liệu.

## 46. Test Hibernate validate sau từng giai đoạn

Có thể chạy schema validation ở các milestones:

| Milestone | Entity mapping cần tương thích |
|---|---|
| Schema expand | Mapping nullable field |
| Backfill | Mapping đọc cả NULL và non-NULL |
| Constraint enforced | Mapping mới có thể khai báo required |
| Contract | Mapping không còn old column |

Nếu v1 và v2 có mappings khác nhau, test cả hai trên schema expand. Không kỳ vọng mapping v1 pass sau khi cột cũ đã bị drop.

## 47. Test migration rollback

Rollback migration không phải lúc nào cũng an toàn.

Với thêm nullable column, rollback có thể drop column nếu chưa có dữ liệu quan trọng. Sau khi v2 đã ghi external references, drop column sẽ mất data mới.

Trước rollback:

- Xác định dữ liệu đã được ghi chưa.
- Có backup/restore strategy không?
- Có thể giữ cột mới và rollback app code không?
- Có cần copy data về cột cũ trước?
- App version rollback có hiểu values mới không?

Trong nhiều hệ thống, **roll-forward migration** sửa lỗi bằng một migration mới an toàn hơn việc cố đảo ngược DDL đã chạy.

## 48. Rollback application khác rollback schema

Nếu v2 có bug:

- Có thể rollback binary về v1 trong khi giữ expanded schema.
- Điều này thường an toàn hơn nếu schema vẫn tương thích v1.
- Không cần drop cột mới ngay.
- Dual-write/fallback có thể tiếp tục.
- Sửa code rồi deploy lại.

Đó là một lợi ích chính của expand–contract: app rollback không nhất thiết yêu cầu schema rollback.

Sau contract migration, v1 có thể không còn chạy được. Vì vậy contract thường được trì hoãn qua một release/observation window.

## 49. Migration failure và partial schema state

Nếu migration fail:

1. Đọc tool history và database state.
2. Xác định DDL đã rollback toàn bộ hay partial.
3. Kiểm tra locks/invalid indexes/constraints.
4. Không tự chạy lại file migration mù quáng.
5. Dùng repair/recovery mechanism chính thức của tool khi cần.
6. Viết corrective migration hoặc thực hiện documented manual recovery.
7. Re-run tests trên snapshot có cùng trạng thái lỗi.

Không xóa schema history row hoặc sửa checksum thủ công nếu chưa hiểu trạng thái thực của DB. Điều đó có thể khiến tool tin schema đã ở version khác với thực tế.

## 50. DDL và lock impact

Một migration nhỏ trong file có thể ảnh hưởng lớn trên bảng production:

- `ALTER TABLE` có thể cần metadata lock hoặc table lock.
- Index creation có thể scan toàn bảng.
- Type conversion có thể rewrite table.
- Adding constraints có thể scan rows.
- Backfill update có thể tạo WAL/undo và replication lag.
- Long-running transactions có thể cản DDL lock acquisition.

Trước khi chạy:

- Xác định row count/table size.
- Xem DB version và DDL behavior.
- Kiểm tra lock timeout/statement timeout.
- Kiểm tra replica lag.
- Chọn maintenance window nếu cần.
- Chạy thử trên dataset gần production.
- Chuẩn bị abort/recovery steps.

## 51. Backfill quan sát được

Log theo chunk:

~~~text
job=external-reference-backfill
chunk=120
selected=500
updated=497
skipped=3
last_id=60500
duration_ms=820
committed=true
~~~

Metrics nên theo dõi:

- Rows scanned/updated/skipped.
- Missing count còn lại.
- Duplicate count.
- Chunk duration.
- Retry/failure count.
- DB CPU/IO.
- Lock waits.
- WAL/replication lag.
- Connection pool usage.

Không đưa `last_id` hoặc tenant ID có cardinality cao vào metric labels. Dùng structured logs/checkpoint table cho chi tiết.

## 52. Data reconciliation trước contract

Một quy trình reconciliation:

1. Đếm total rows trong scope.
2. Đếm NULL target values.
3. Đếm duplicates theo unique scope.
4. So sánh target với source transformation.
5. Kiểm tra sample records theo tenant/time/status.
6. Kiểm tra các writers sau backfill có tiếp tục dual-write.
7. Chạy lại reconciliation sau một cửa sổ traffic.
8. Lưu kết quả và owner sign-off theo quy trình tổ chức.

Không chỉ dựa vào log “job completed”. Job có thể hoàn thành nhưng bỏ qua rows không có source data.

## 53. Migration và tenant scope

Với bảng multi-tenant, backfill/validation cần giữ tenant boundary:

~~~sql
UPDATE orders
SET external_reference = source_code
WHERE tenant_id = :tenant
  AND external_reference IS NULL
  AND source_code IS NOT NULL;
~~~

Nếu migration chạy trên toàn bảng, cần đảm bảo transformation không trộn dữ liệu giữa tenants và unique constraints dùng đúng scope `(tenant_id, external_reference)`.

Nếu mỗi tenant dùng schema/database riêng, migration phải chạy trên toàn bộ tenant schemas/databases với tracking và failure handling rõ ràng.

## 54. Index strategy trong rollout

Không tạo index chỉ vì cột mới được thêm. Xem query workload:

~~~sql
SELECT id, status
FROM orders
WHERE tenant_id = ?
  AND external_reference = ?;
~~~

Index `(tenant_id, external_reference)` có thể phù hợp nếu filter thường dùng theo tenant và reference.

Kiểm tra:

- Selectivity/cardinality.
- Column order.
- Query predicates.
- Sort requirements.
- Write amplification.
- Index size.
- Existing indexes có prefix phù hợp không.
- Explain plan trước/sau.

Index không thay unique constraint nếu business yêu cầu uniqueness; một non-unique index chỉ tối ưu lookup.

## 55. Migration data type và precision

Nếu thay đổi numeric column:

~~~sql
ALTER TABLE invoice
ALTER COLUMN amount TYPE NUMERIC(19, 4);
~~~

có thể gây rounding, reject hoặc table rewrite tùy DBMS/type conversion. Trước khi chạy:

- Profiling values hiện tại.
- Tìm values vượt range/scale.
- Quyết định rounding mode.
- Test boundary cases trên DB production-like.
- Back up/record rejected rows.
- Xác nhận application types (`BigDecimal`) và validation.
- Kiểm tra dependent indexes/views/functions.

Không dùng `CAST` để âm thầm làm mất precision nếu business chưa chấp thuận.

## 56. Migration enum representation

Đổi enum ordinal sang string là data migration thực sự.

Ví dụ legacy values:

~~~text
0 -> NEW
1 -> PAID
2 -> SHIPPED
~~~

Migration cần map chính xác ordinal theo enum order cũ:

~~~sql
UPDATE orders
SET status_text = CASE status_ordinal
    WHEN 0 THEN 'NEW'
    WHEN 1 THEN 'PAID'
    WHEN 2 THEN 'SHIPPED'
    ELSE NULL
END;
~~~

Trước khi switch application mapping:

- Xác định values ngoài range.
- Tạo report/abort khi có unknown ordinal.
- Deploy code có thể đọc representation mới.
- Backfill.
- Validate no NULL/unknown.
- Enforce constraint.
- Chuyển reads/writes.
- Xóa old column ở contract phase.

Không dùng ordinal order của enum code mới để giải nghĩa dữ liệu cũ sau khi enum đã reorder.

## 57. Migration rename type hoặc column bằng dual schema

Nếu cần đổi `customer_name` thành `display_name`, không rename trực tiếp khi app cũ vẫn chạy.

Pattern:

1. Add `display_name` nullable.
2. Deploy code dual-write `customer_name` + `display_name`.
3. Backfill `display_name = customer_name`.
4. Verify parity.
5. Switch read path.
6. Stop writing `customer_name`.
7. Wait old app/readers are gone.
8. Drop `customer_name`.

Nếu hai fields có semantics khác nhau, cần transformation/validation chứ không chỉ copy.

## 58. CI pipeline cho migration và compatibility

Một pipeline có thể gồm:

~~~text
Compile / unit tests
        |
        v
Start production-like database container
        |
        v
Apply all migrations from empty DB
        |
        v
Run schema validation + repository tests
        |
        v
Restore/seed previous schema + legacy data
        |
        v
Upgrade to current schema
        |
        v
Run backfill + compatibility tests
        |
        v
Run old/new application compatibility suite
        |
        v
Run constraint/rollback tests
        |
        v
Build deployment artifact
~~~

Không cần mọi pipeline chạy toàn bộ production-scale backfill. Dùng fixture đại diện và một separate performance/load test cho quy mô lớn.

## 59. Testcontainers và migration integration test

Ví dụ cấu trúc:

~~~java
@Testcontainers
@SpringBootTest
class OrderSchemaMigrationTest {

    @Container
    static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");

    // Configure datasource to container.
    // Apply Flyway/Liquibase migrations.
    // Verify schema and exercise repositories.
}
~~~

Wiring datasource có thể dùng `@DynamicPropertySource` hoặc `@ServiceConnection` tùy Spring Boot/Testcontainers versions.

Test cùng engine/version gần production để xác nhận DDL, constraints, timestamp/numeric behavior, indexes và SQL syntax. H2 có thể hữu ích cho test nhanh nhưng không thay thế dialect-specific migration tests.

## 60. Test từ schema cũ có data

Một test upgrade nên seed schema version cũ **trước khi** chạy migration mới. Nếu chỉ tạo schema từ đầu bằng tất cả migrations, bạn không test được transformation của dữ liệu legacy.

Cấu trúc:

~~~text
Create database
  -> Apply migrations through V101
  -> Insert legacy fixtures
  -> Run V102 expand
  -> Run backfill job
  -> Validate data
  -> Run V103 constraints
  -> Start application v2
  -> Assert rows and queries
~~~

Nếu migration tool chỉ chạy toàn bộ latest migrations tự động, dùng test harness riêng để dừng ở version trước hoặc tạo fixture schema version cũ tương ứng.

## 61. Test tương thích nhiều application versions

Có thể giữ hai test artifacts:

- `app-v1` được build từ release trước.
- `app-v2` từ branch hiện tại.

Test matrix:

| Schema | App v1 | App v2 |
|---|---|---|
| Old | Expected pass | Có thể fail nếu chưa expand |
| Expanded | Phải pass | Phải pass |
| Contracted | Không còn được hỗ trợ | Phải pass |

Đây là integration/deployment compatibility test. Nếu không thể chạy binary v1 trong CI, có thể test SQL contracts và giữ smoke test thủ công/automated trong pre-production.

## 62. Kiểm thử migration rollback và roll-forward

Tách hai câu hỏi:

- Có thể rollback migration không mà không mất data?
- Có thể rollback application binary không trong khi giữ schema mới?

Với expand migration, thường có thể rollback app về v1 mà không cần đảo schema. Với contract migration, app v1 không còn tương thích.

Ưu tiên corrective/roll-forward migration nếu schema đã có data mới quan trọng. Migration rollback script chỉ an toàn khi đã chứng minh không làm mất dữ liệu cần giữ và DBMS hỗ trợ transactional DDL theo cách dự kiến.

## 63. Runbook triển khai thay đổi schema

**Trước deploy**

- Review domain semantics và compatibility matrix.
- Backup/restore point theo policy.
- Kiểm tra migration trên production-like dataset.
- Đo DDL lock/statement duration.
- Chuẩn bị dashboard và abort criteria.
- Xác định migration owner/on-call.

**Expand**

- Chạy migration add nullable column/index phù hợp.
- Xác nhận schema history.
- Xác nhận application v1 vẫn hoạt động.
- Deploy v2 với fallback/dual-write.
- Kiểm tra write paths và error rate.

**Migrate**

- Chạy backfill chunks.
- Theo dõi progress/lag/locks.
- Reconcile NULL, duplicate và mismatch counts.
- Chạy lại pass nếu cần.
- Bật read feature flag theo cohort khi dữ liệu sẵn sàng.

**Contract**

- Xác nhận không còn v1/legacy consumers.
- Dừng dual-write.
- Enforce constraints.
- Deploy code bỏ legacy mapping.
- Drop legacy column trong migration riêng.
- Theo dõi lỗi SQL/ORM sau contract.

## 64. Lỗi thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
|---|---|---|
| Thêm NOT NULL ngay khi expand | App cũ INSERT fail | Add nullable, backfill, enforce sau |
| Dùng Hibernate `ddl-auto=update` production | Schema changes khó review/replay | Flyway/Liquibase |
| Rename/drop cột ngay | Rolling instances lỗi | Expand–migrate–contract |
| Backfill toàn bảng trong một transaction lớn | Lock/WAL/replication pressure | Chunked backfill |
| Checkpoint trước commit | Restart bỏ sót dữ liệu | Checkpoint sau commit hoặc cùng transaction |
| Backfill ghi đè live write | Data regression | Conditional update/dual-write/reconcile |
| Điền placeholder vào NULL | Sai business meaning/duplicate | Remediation policy rõ |
| Tạo unique constraint trước cleanup | Migration fail | Detect/resolve duplicates trước |
| Tạo index thường trên bảng lớn không đánh giá | Blocking/IO load | Online/concurrent strategy theo DB |
| Chỉnh migration đã chạy | Checksum/history mismatch | Tạo migration mới |
| Chỉ test schema mới từ đầu | Bỏ sót upgrade/data migration | Test từ version cũ có fixtures |
| Chỉ test app mới | App cũ có thể fail trong rollout | Compatibility matrix |
| Contract trước khi v1 dừng | Old app fail | Chờ hết legacy consumers |
| Giả định DDL rollback được | Partial schema state | Kiểm tra DBMS/tool semantics |
| Tin `validate` là đủ | Không kiểm tra data correctness | Migration + data + integration tests |

## 65. Checklist review migration

**Thiết kế**

- [ ] Có nêu business invariant mới?
- [ ] Có xác định nguồn dữ liệu cho backfill?
- [ ] Có compatibility matrix app/schema?
- [ ] Có liệt kê mọi readers/writers?
- [ ] Có quyết định rollback/roll-forward?

**Migration**

- [ ] Version/ID và tên duy nhất?
- [ ] DDL phù hợp production DB/version?
- [ ] Lock/rewrite/index build impact được đánh giá?
- [ ] Có preconditions/validation?
- [ ] Không sửa migration đã chạy?
- [ ] Transactional/non-transactional behavior rõ?

**Data**

- [ ] Backfill idempotent?
- [ ] Chunk/checkpoint có?
- [ ] Race với live writes được xử lý?
- [ ] NULL/duplicate/mismatch được reconcile?
- [ ] Không sinh business placeholder tùy tiện?
- [ ] Tenant scope được giữ đúng?

**Application**

- [ ] Mapping khớp schema expand?
- [ ] App cũ chạy được trên schema expand?
- [ ] Dual-write/read fallback được test?
- [ ] Feature flag có guard conditions?
- [ ] Contract chỉ chạy sau khi legacy consumers dừng?

**Tests/operations**

- [ ] Empty database migration test?
- [ ] Upgrade test từ schema cũ có data?
- [ ] Testcontainers dùng DB gần production?
- [ ] Hibernate schema validation?
- [ ] App v1/v2 compatibility tests?
- [ ] Backfill restart/idempotency tests?
- [ ] DDL/backfill observability và abort criteria?

## 66. Bài tập thực hành

1. Tạo bảng `orders` với `source_code`; thêm `external_reference` bằng migration nullable.
2. Viết entity mapping cho cả hai columns và chạy Hibernate schema validation.
3. Chạy application v1 insert row sau migration expand; xác nhận không fail.
4. Viết v2 dual-write path và test atomic update hai fields.
5. Backfill historical rows theo keyset chunks, checkpoint sau commit.
6. Tạo race test giữa backfill và live writer; chứng minh không overwrite reference mới.
7. Viết reconciliation query cho missing/duplicate/mismatch values.
8. Thêm index `(tenant_id, external_reference)` và so sánh EXPLAIN trước/sau.
9. Enforce NOT NULL và UNIQUE sau backfill; test invalid inserts bị DB từ chối.
10. Dùng Testcontainers chạy migrations từ database trống.
11. Dùng fixture schema V101 có legacy data rồi upgrade đến latest.
12. Chạy app v1 và v2 trên expanded schema để kiểm tra rolling compatibility.
13. Mô phỏng migration fail sau một DDL step và viết recovery procedure.
14. Thử rollback binary v2 về v1 trong khi giữ expanded schema.
15. Viết contract migration drop `source_code` chỉ sau khi legacy consumers dừng.
16. Đo backfill throughput/replication lag với chunk sizes khác nhau.
17. Chuyển enum ordinal sang string bằng migration có explicit mapping.
18. Viết CI job kiểm tra migration history/checksum và Hibernate `validate`.

## 67. Sơ đồ quyết định

~~~mermaid
flowchart TD
    A["Có thay đổi schema/data"] --> B["Xác định invariant + consumers"]
    B --> C{"Có rolling deployment?"}
    C -- "Có" --> D["Expand: thêm nullable/compatible structure"]
    C -- "Không" --> E["Vẫn dùng migration có version và test"]
    D --> F["Deploy code đọc/ghi tương thích"]
    E --> F
    F --> G["Backfill theo chunks + checkpoint"]
    G --> H["Reconcile NULL/duplicates/mismatches"]
    H --> I{"Dữ liệu và writers đã sẵn sàng?"}
    I -- "Chưa" --> G
    I -- "Rồi" --> J["Switch read path / enforce constraints"]
    J --> K{"Legacy app/consumer còn tồn tại?"}
    K -- "Có" --> L["Giữ old schema + dual-write"]
    L --> K
    K -- "Không" --> M["Contract: bỏ cấu trúc cũ"]
    M --> N["Monitor và đóng migration"]
~~~

## 68. Tài liệu tham khảo

- [Flyway Documentation](https://documentation.red-gate.com/flyway) — versioned migrations, schema history, validation và recovery.
- [Liquibase Documentation](https://docs.liquibase.com/) — changelogs, changesets, preconditions và deployment.
- [Hibernate ORM User Guide](https://docs.hibernate.org/orm/current/userguide/html_single/Hibernate_User_Guide.html) — schema tooling, mappings, validation và SQL generation.
- [Spring Boot Database Initialization](https://docs.spring.io/spring-boot/how-to/data-initialization.html) — schema/data initialization và migration tool integration.
- [Testcontainers for Java](https://java.testcontainers.org/) — database containers cho integration tests.
- [PostgreSQL ALTER TABLE](https://www.postgresql.org/docs/current/sql-altertable.html) — column changes, constraints và locking notes.
- [PostgreSQL CREATE INDEX](https://www.postgresql.org/docs/current/sql-createindex.html) — index creation, concurrent mode và transaction restrictions.
- [PostgreSQL Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html) — lock modes và contention.

Tài liệu `current` có thể mô tả version mới hơn production. Đặc biệt DDL locks, transactional behavior, concurrent index creation và migration tool configuration phải được xác nhận theo đúng DBMS/tool versions.

## 69. Tổng kết

**Một thay đổi schema production an toàn là một chuỗi rollout tương thích, không phải một lệnh ALTER TABLE đơn lẻ.**

- Dùng **versioned migrations** làm source of truth; Hibernate `validate` hỗ trợ phát hiện mapping/schema mismatch.
- Bắt đầu bằng **expand** tương thích: thêm nullable columns/structures trong khi code cũ vẫn chạy.
- Deploy application có **fallback/dual-write** khi nhiều phiên bản còn cùng hoạt động.
- Chạy **backfill theo chunks**, idempotent, có checkpoint và bảo vệ race với live writes.
- Reconcile NULL, duplicates và mismatches trước khi enforce NOT NULL/UNIQUE/FK.
- Đánh giá DDL lock, index build, transaction behavior, WAL và replication lag trên database production-like.
- Kiểm thử từ database trống **và** upgrade từ schema cũ có dữ liệu; test cả app cũ và app mới trên schema expand.
- Chỉ **contract** sau khi mọi legacy readers/writers đã dừng và rollback strategy không còn phụ thuộc cấu trúc cũ.
- Ưu tiên roll-forward khi rollback DDL có nguy cơ mất dữ liệu.

Với ví dụ `external_reference`, đường đi an toàn là **thêm cột nullable → deploy code tương thích → dual-write → backfill → reconcile → chuyển reads → enforce constraints → ngừng old writers → drop cột cũ**. Khi mỗi bước có migration, compatibility tests và evidence rõ ràng, thay đổi database có thể tiến hành theo từng giai đoạn mà không buộc toàn hệ thống dừng cùng lúc.
