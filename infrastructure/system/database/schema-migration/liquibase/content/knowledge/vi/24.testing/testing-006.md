
# Kiểm tra ràng buộc, chỉ mục và dữ liệu sau migration

Trong module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, Liquibase quản lý thay đổi schema và dữ liệu bằng changelog, changeset, precondition, checksum và lịch sử triển khai. Một changeset chạy thành công mới xác nhận Liquibase đã hoàn tất bước thực thi theo trạng thái mà công cụ ghi nhận. Để biết database có thực sự đạt yêu cầu hay không, cần kiểm tra các ràng buộc, chỉ mục và dữ liệu sau migration.

Bài thuộc chương **Kiểm thử** này hướng dẫn xây dựng bộ kiểm chứng hậu migration. Nội dung bao gồm cách xác định invariant, kiểm tra primary key/foreign key/unique/check/not-null, xác minh index tồn tại và hợp lệ, đối chiếu dữ liệu trước/sau, dùng catalog của PostgreSQL/MySQL/SQL Server, kiểm tra execution plan, phát hiện migration một phần và đưa các kiểm tra vào CI/CD. Mục tiêu là phát hiện trường hợp changeset thành công nhưng schema thiếu constraint, index chưa usable hoặc dữ liệu không còn thỏa quy tắc nghiệp vụ.

Phạm vi bài học được xác định bởi **SERVICE_NAME=DATABASE_SCHEMA_MIGRATION_LIQUIBASE**. Theo **SERVICE_NAME_DESCRIBE**, module hướng dẫn quản lý thay đổi schema và dữ liệu bằng changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD.

## 1. Vì sao phải kiểm tra sau migration?

Một migration có thể kết thúc với exit code 0 nhưng kết quả vẫn chưa đáp ứng yêu cầu ứng dụng:

- Changeset tạo foreign key nhưng constraint chưa được validate trên các hàng cũ.
- Unique index không được tạo vì dữ liệu trùng, hoặc index được tạo ở trạng thái chưa hợp lệ.
- Cột mới tồn tại nhưng backfill chưa hoàn tất.
- NOT NULL được áp dụng nhưng dữ liệu ở một nhóm tenant vẫn còn NULL.
- Một index có cùng tên đã tồn tại nhưng định nghĩa sai cột hoặc thứ tự cột.
- Changeset được đánh dấu MARK_RAN nên SQL không thực thi.
- DDL thành công nhưng ứng dụng không thể sử dụng vì quyền, schema hoặc kiểu dữ liệu khác kỳ vọng.
- Data migration cập nhật thiếu hàng do filter, batch checkpoint hoặc điều kiện WHERE sai.

Vì vậy, hậu kiểm phải kiểm tra **kết quả thực tế trong database**. Liquibase history, schema catalog, dữ liệu và hành vi truy vấn là những nguồn bằng chứng khác nhau; cần kết hợp chúng để xác nhận release.

## 2. Phân biệt kiểm tra changelog với kiểm tra database sau migration

Các lệnh và phép kiểm tra có phạm vi khác nhau:

| Kiểm tra | Xác nhận được | Không chứng minh được |
|---|---|---|
| liquibase validate | Changelog có thể được phân tích và các kiểm tra cấu trúc/checksum phù hợp | Constraint, index và dữ liệu thực tế đã đúng |
| liquibase status | Changeset pending theo target và filter hiện tại | Changeset đã chạy tạo ra kết quả nghiệp vụ đúng |
| liquibase update-sql | SQL dự kiến sẽ được gửi khi update | SQL đã chạy thành công hoặc dữ liệu đạt invariant |
| DATABASECHANGELOG | Liquibase ghi nhận changeset và kiểu thực thi | Object/data không bị drift sau đó |
| DBMS catalog | Định nghĩa và trạng thái constraint/index đang có | Dữ liệu hiện tại thỏa mọi quy tắc |
| Data assertions | Các invariant dữ liệu được kiểm tra tại thời điểm chạy | Hiệu năng truy vấn luôn đạt trong mọi tải |
| Application smoke test | Ứng dụng thực hiện được một số luồng đại diện | Toàn bộ dữ liệu và mọi truy vấn đều đúng |

Không dùng một lệnh đơn lẻ thay thế cả bộ kiểm thử. Một release gate tốt có thể kết hợp validate, update, kiểm tra history, catalog assertions, data assertions và smoke test.

## 3. Xác định invariant trước khi viết truy vấn kiểm tra

**Invariant** là điều kiện phải luôn đúng đối với schema hoặc dữ liệu sau migration. Hãy viết chúng thành câu có thể kiểm tra được.

Ví dụ cho bảng order:

- Mỗi order có một khóa chính duy nhất.
- customer_id nếu có giá trị thì phải tham chiếu tới customer tồn tại.
- order_number không được trùng trong phạm vi tenant.
- total_amount không âm.
- status chỉ thuộc tập giá trị hợp lệ.
- created_at không được NULL.
- Index phục vụ tra cứu tenant/status phải có đúng thứ tự cột và trạng thái usable.
- Sau backfill, mọi hàng cũ phải có currency_code hợp lệ.

Mỗi invariant nên có:

1. Mô tả nghiệp vụ.
2. Phạm vi bảng/tenant/partition.
3. Truy vấn hoặc metadata để kiểm tra.
4. Kết quả mong đợi.
5. Mức độ nghiêm trọng khi không đạt.
6. Người chịu trách nhiệm quyết định tiếp tục, dừng hoặc phục hồi.

Đừng bắt đầu bằng việc viết hàng chục câu SQL rồi mới hỏi chúng chứng minh điều gì. Bắt đầu từ điều kiện chấp nhận, sau đó chọn cách đo phù hợp.

## 4. Các lớp kiểm tra hậu migration

Một bộ kiểm tra đầy đủ thường có sáu lớp:

1. **History:** changeset đúng target đã được ghi nhận với EXECTYPE mong đợi.
2. **Structure:** bảng, cột, kiểu dữ liệu, default, schema và object tồn tại đúng.
3. **Constraints:** primary key, foreign key, unique, check và nullability được tạo, enabled và validated/trusted theo yêu cầu.
4. **Indexes:** index đúng tên/phạm vi/column order/uniqueness/filter và ở trạng thái có thể được optimizer sử dụng.
5. **Data:** row count, duplicate, orphan, NULL, miền giá trị, quan hệ và tổng hợp đạt invariant.
6. **Behavior/performance:** ứng dụng truy vấn đúng; execution plan và latency không suy giảm ngoài ngưỡng.

Không phải mọi migration đều cần mọi phép kiểm tra ở mức sâu như nhau. Tuy nhiên, thay đổi ảnh hưởng dữ liệu hoặc constraint cần có assertion tương ứng trước khi release được coi là hoàn tất.

## 5. Kiểm tra primary key và tính duy nhất

Primary key bảo đảm mỗi hàng có định danh duy nhất và không NULL theo semantics DBMS. Sau migration tạo hoặc đổi primary key, cần xác minh cả metadata lẫn dữ liệu.

Tìm duplicate theo khóa dự kiến:

~~~sql
SELECT
    customer_id,
    COUNT(*) AS duplicate_count
FROM customer
GROUP BY customer_id
HAVING COUNT(*) > 1;
~~~

Kết quả mong đợi: không có hàng nào. Nếu primary key gồm nhiều cột, GROUP BY phải bao gồm toàn bộ cột của khóa.

Kiểm tra NULL:

~~~sql
SELECT COUNT(*) AS null_key_count
FROM customer
WHERE customer_id IS NULL;
~~~

Kết quả mong đợi: 0. Với khóa ghép, kiểm tra từng thành phần theo định nghĩa constraint.

Đừng chỉ kiểm tra tên constraint. Hãy xác nhận cột được liên kết, thứ tự cột nếu là khóa ghép, schema/table đúng và constraint đang được DBMS thực thi.

## 6. Kiểm tra foreign key và hàng mồ côi

Foreign key đảm bảo quan hệ tham chiếu giữa bảng con và bảng cha. Trước khi thêm FK, dữ liệu cũ có thể đã chứa orphan rows.

Ví dụ kiểm tra order tham chiếu customer không tồn tại:

~~~sql
SELECT
    o.id,
    o.customer_id
FROM orders AS o
LEFT JOIN customer AS c
    ON c.id = o.customer_id
WHERE o.customer_id IS NOT NULL
  AND c.id IS NULL;
~~~

Để đếm toàn bộ orphan:

~~~sql
SELECT COUNT(*) AS orphan_count
FROM orders AS o
LEFT JOIN customer AS c
    ON c.id = o.customer_id
WHERE o.customer_id IS NOT NULL
  AND c.id IS NULL;
~~~

Kết quả mong đợi: 0 nếu nghiệp vụ yêu cầu mọi customer_id khác NULL phải tồn tại.

Với tenant-aware relationship, join phải bao gồm tenant_id nếu khóa tham chiếu là cặp tenant_id/customer_id. Join thiếu tenant có thể che lỗi cross-tenant hoặc báo sai orphan.

Cũng cần kiểm tra hành vi ON DELETE/ON UPDATE như CASCADE, RESTRICT hoặc SET NULL. Constraint tồn tại nhưng action sai vẫn có thể gây mất dữ liệu hoặc lỗi nghiệp vụ.

## 7. Kiểm tra unique constraint và duplicate dữ liệu

Trước khi tạo unique constraint/index, hãy tìm dữ liệu trùng theo đúng business key.

Ví dụ email được coi là duy nhất trong mỗi tenant:

~~~sql
SELECT
    tenant_id,
    email_normalized,
    COUNT(*) AS duplicate_count
FROM customer
WHERE email_normalized IS NOT NULL
GROUP BY tenant_id, email_normalized
HAVING COUNT(*) > 1;
~~~

Nếu unique rule có filter, chẳng hạn chỉ áp dụng với hàng chưa xóa mềm, truy vấn kiểm tra phải dùng cùng predicate:

~~~sql
SELECT tenant_id, email_normalized, COUNT(*) AS duplicate_count
FROM customer
WHERE deleted_at IS NULL
  AND email_normalized IS NOT NULL
GROUP BY tenant_id, email_normalized
HAVING COUNT(*) > 1;
~~~

Unique index có thể có semantics khác nhau đối với NULL theo DBMS. Một số DBMS cho phép nhiều NULL trong unique index; filtered/partial index có thể thay đổi phạm vi. Hãy kiểm tra đúng DBMS và định nghĩa thực tế.

Không tự xóa duplicate bằng cách giữ một hàng bất kỳ. Cần quy tắc nghiệp vụ về hợp nhất, khóa tham chiếu, audit và dữ liệu liên quan trước khi làm sạch.

## 8. Kiểm tra NOT NULL và miền giá trị

Khi migration chuyển cột nullable sang NOT NULL, kiểm tra trước và sau:

~~~sql
SELECT COUNT(*) AS missing_status
FROM customer
WHERE status IS NULL;
~~~

Kết quả phải bằng 0 trước khi constraint được áp dụng nếu không có default/backfill xử lý các hàng cũ.

Kiểm tra miền giá trị:

~~~sql
SELECT status, COUNT(*) AS row_count
FROM customer
GROUP BY status
ORDER BY status;
~~~

Nếu tập giá trị hợp lệ là ACTIVE, SUSPENDED, CLOSED, truy vấn phát hiện giá trị ngoài tập:

~~~sql
SELECT COUNT(*) AS invalid_status_count
FROM customer
WHERE status IS NULL
   OR status NOT IN ('ACTIVE', 'SUSPENDED', 'CLOSED');
~~~

Điều kiện có thể khác nếu NULL là trạng thái hợp lệ trong giai đoạn chuyển tiếp. Hãy mô tả chính xác semantics nghiệp vụ; không tự thêm NULL vào tập hợp hoặc ép giá trị mặc định chỉ để test pass.

## 9. Kiểm tra CHECK constraint

CHECK constraint thường biểu đạt điều kiện trên giá trị một hàng, ví dụ số lượng lớn hơn 0, tổng tiền không âm, ngày kết thúc không sớm hơn ngày bắt đầu hoặc trạng thái thuộc tập được phép.

Ví dụ assertion dữ liệu:

~~~sql
SELECT COUNT(*) AS invalid_amount_count
FROM invoice
WHERE total_amount < 0;
~~~

Ví dụ migration tạo CHECK bằng SQL trong Liquibase:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 010-add-invoice-amount-check
      author: billing-team
      changes:
        - sql:
            sql: |
              ALTER TABLE invoice
              ADD CONSTRAINT chk_invoice_total_nonnegative
              CHECK (total_amount >= 0)
~~~

Cú pháp DDL và khả năng thêm/validate constraint có thể khác theo DBMS. Một số DBMS cho phép constraint chưa validate dữ liệu cũ; một số phiên bản có semantics hoặc hỗ trợ khác nhau. Sau update, phải kiểm tra trạng thái enabled/validated/trusted và chạy data assertion độc lập.

Lưu ý CHECK có thể xử lý NULL theo logic ba giá trị; điều kiện total_amount >= 0 không nhất thiết loại NULL. Nếu cột bắt buộc có giá trị, cần NOT NULL riêng.

## 10. Kiểm tra index: tên tồn tại chưa đủ

Một index có thể tồn tại nhưng vẫn sai yêu cầu. Kiểm tra các thuộc tính:

- Database/schema/table chứa index.
- Tên index và trạng thái enabled/valid/ready.
- Unique hay non-unique.
- Thứ tự cột trong index.
- ASC/DESC và collation nếu liên quan.
- Included columns (nếu DBMS hỗ trợ).
- Predicate của filtered/partial index.
- Expression/function index.
- Index method/type, chẳng hạn B-tree, hash hoặc full-text.
- Partition/index alignment.
- Constraint nào đang phụ thuộc index.

Ví dụ yêu cầu index cho truy vấn:

~~~sql
SELECT id, created_at
FROM orders
WHERE tenant_id = ?
  AND status = ?
ORDER BY created_at DESC;
~~~

Một index (tenant_id, status, created_at) có thể phù hợp hơn index chỉ có created_at, nhưng phải đánh giá selectivity, DBMS, cardinality và execution plan. Không kết luận chỉ từ tên index hoặc việc catalog trả về một hàng.

## 11. Kiểm tra index có usable hay không

Một index có thể được catalog ghi nhận nhưng không được optimizer sử dụng do trạng thái invalid/disabled, thiếu statistics, predicate không khớp hoặc query không phù hợp.

Các trạng thái cần quan tâm:

- Index hợp lệ và sẵn sàng phục vụ truy vấn.
- Index đang được build.
- Index build thất bại và để lại object chưa usable.
- Index bị disable hoặc hypothetical.
- Index tồn tại nhưng không được query planner chọn.
- Index bị thiếu statistics hoặc không phù hợp với predicate.

Đặc biệt với PostgreSQL, CREATE INDEX CONCURRENTLY có thể để lại index invalid nếu thao tác thất bại. Kiểm tra pg_index.indisvalid và indisready, không chỉ pg_indexes.

Với SQL Server, index có thể bị disable. Với MySQL, cần xác minh index metadata và trạng thái/engine phù hợp; không suy luận usability chỉ từ CARDINALITY vì đây là thống kê ước lượng.

## 12. Kiểm tra thứ tự cột và định nghĩa index

Ví dụ index ghép:

~~~sql
CREATE INDEX idx_orders_tenant_status_created
ON orders (tenant_id, status, created_at);
~~~

Index này có thứ tự cột cụ thể. Index (status, tenant_id, created_at) không tương đương về mọi truy vấn. B-tree thường tận dụng tốt các điều kiện trên prefix phù hợp, nhưng hiệu quả thực tế phụ thuộc DBMS và query planner.

Khi kiểm tra hậu migration, đối chiếu định nghĩa index với changelog và query workload:

- Cột đầu tiên có phù hợp điều kiện lọc phổ biến?
- Thứ tự cột có đúng yêu cầu?
- Có cần unique?
- Có predicate chỉ index hàng active?
- Có expression index cho lower/normalized value?
- Có included column để cover query?
- Có partition-specific index cần xác minh?

Nếu index phục vụ constraint, kiểm tra cả constraint liên kết. Đừng drop/recreate index chỉ vì tên khác nếu chưa xác minh định nghĩa và phụ thuộc.

## 13. Kiểm tra dữ liệu sau backfill

Data migration thường thay đổi giá trị trên các hàng đã tồn tại. Cần kiểm tra cả độ phủ và nội dung.

Ví dụ thêm currency_code rồi backfill:

~~~sql
SELECT
    COUNT(*) AS total_rows,
    SUM(CASE WHEN currency_code IS NULL THEN 1 ELSE 0 END) AS missing_currency,
    SUM(CASE WHEN currency_code NOT IN ('VND', 'USD', 'EUR')
             THEN 1 ELSE 0 END) AS invalid_currency
FROM invoice;
~~~

Kết quả mong đợi cần được xác định trước. Nếu NULL hợp lệ với một loại invoice, truy vấn phải phân loại theo business rule thay vì áp dụng một điều kiện chung.

Kiểm tra mẫu dữ liệu đại diện, tenant lớn/nhỏ, hàng cũ/mới, dữ liệu biên và hàng được cập nhật gần đây. Không chỉ lấy vài hàng đầu tiên rồi kết luận toàn bộ backfill đúng.

## 14. Đối chiếu số lượng và tổng hợp trước/sau

Khi migration chuyển đổi dữ liệu, có thể đối chiếu:

- Tổng số hàng trong phạm vi.
- Số hàng được chuyển đổi.
- Số hàng bỏ qua theo điều kiện.
- Số hàng lỗi hoặc cần xử lý thủ công.
- Tổng tiền, số lượng hoặc aggregate nghiệp vụ.
- Số khóa duy nhất và quan hệ tham chiếu.
- Số hàng theo trạng thái/tenant/partition.

Ví dụ:

~~~sql
SELECT
    tenant_id,
    status,
    COUNT(*) AS row_count,
    SUM(total_amount) AS total_amount
FROM invoice
GROUP BY tenant_id, status
ORDER BY tenant_id, status;
~~~

So sánh snapshot trước/sau phải tính đến các giao dịch nghiệp vụ diễn ra đồng thời. Nếu ứng dụng vẫn ghi dữ liệu, tổng row count có thể thay đổi hợp lệ. Dùng watermark, snapshot, transaction boundary hoặc tập dữ liệu cố định để phép đối chiếu có ý nghĩa.

Không so sánh tổng tiền kiểu floating point bằng phép bằng tuyệt đối nếu DBMS/kiểu dữ liệu có sai số; dùng DECIMAL phù hợp và tolerance được định nghĩa khi cần.

## 15. Kiểm tra quan hệ và tính nhất quán giữa nhiều bảng

Một migration có thể thay đổi nhiều bảng liên quan. Kiểm tra từng bảng độc lập chưa đủ để chứng minh quan hệ đúng.

Ví dụ chuyển customer_id sang customer_key:

- Mỗi customer cũ có mapping tương ứng.
- Không có hai customer cùng nhận một customer_key nếu key phải unique.
- Mọi order có customer_id hợp lệ đều được map.
- Không có order bị gán sang customer khác.
- Tổng số order trước/sau được đối chiếu.
- Những hàng không thể map có danh sách xử lý riêng.

Truy vấn phát hiện order chưa được map:

~~~sql
SELECT COUNT(*) AS unmapped_orders
FROM orders
WHERE customer_id IS NOT NULL
  AND customer_key IS NULL;
~~~

Truy vấn kiểm tra mapping trỏ tới customer không tồn tại:

~~~sql
SELECT COUNT(*) AS invalid_customer_keys
FROM orders AS o
LEFT JOIN customer AS c
    ON c.customer_key = o.customer_key
WHERE o.customer_key IS NOT NULL
  AND c.customer_key IS NULL;
~~~

Một invariant quan hệ cần xét cả tính đúng của mapping, không chỉ việc cột mới không NULL.

## 16. Kiểm tra dữ liệu theo tenant và partition

Một truy vấn tổng thể có thể che giấu lỗi chỉ xảy ra ở một tenant hoặc partition nhỏ. Ví dụ 99.9% dữ liệu đã backfill nhưng một tenant có hàng triệu bản ghi chưa xử lý.

Hãy phân nhóm theo tenant/customer segment, ngày tạo hoặc khoảng thời gian, partition/shard, trạng thái nghiệp vụ, nguồn nhập dữ liệu và phiên bản ứng dụng đã ghi dữ liệu.

Ví dụ:

~~~sql
SELECT
    tenant_id,
    COUNT(*) AS total_rows,
    SUM(CASE WHEN email_normalized IS NULL THEN 1 ELSE 0 END) AS missing_rows
FROM customer
GROUP BY tenant_id
HAVING SUM(CASE WHEN email_normalized IS NULL THEN 1 ELSE 0 END) > 0;
~~~

Kết quả rỗng có thể là điều kiện cần trước khi bật NOT NULL hoặc chuyển read path. Nếu có tenant được miễn trừ, ngoại lệ phải được liệt kê và phê duyệt, không loại bỏ âm thầm khỏi truy vấn.

## 17. PostgreSQL: kiểm tra constraint trong catalog

PostgreSQL lưu constraint trong pg_constraint. Truy vấn tham khảo:

~~~sql
SELECT
    conname,
    contype,
    convalidated,
    pg_get_constraintdef(oid) AS definition
FROM pg_constraint
WHERE conrelid = 'public.orders'::regclass
ORDER BY conname;
~~~

Các loại constraint thường thấy:

- p: primary key.
- f: foreign key.
- u: unique.
- c: check.
- x: exclusion constraint.

convalidated cho biết constraint đã được validate trên dữ liệu hiện có hay chưa. Một foreign key hoặc check được thêm theo chế độ NOT VALID có thể áp dụng cho thay đổi mới nhưng chưa kiểm tra toàn bộ hàng cũ. Khi yêu cầu release là dữ liệu cũ cũng phải hợp lệ, cần xác nhận convalidated đúng kỳ vọng.

Tên schema/table trong regclass phải được chỉ rõ phù hợp với database đích. Truy vấn catalog cần quyền đọc metadata.

## 18. PostgreSQL: kiểm tra index và trạng thái valid

Liệt kê định nghĩa index:

~~~sql
SELECT
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname = 'public'
  AND tablename = 'orders'
ORDER BY indexname;
~~~

Kiểm tra trạng thái nội bộ:

~~~sql
SELECT
    ns.nspname AS schema_name,
    tbl.relname AS table_name,
    idx.relname AS index_name,
    i.indisunique,
    i.indisvalid,
    i.indisready
FROM pg_index AS i
JOIN pg_class AS idx
    ON idx.oid = i.indexrelid
JOIN pg_class AS tbl
    ON tbl.oid = i.indrelid
JOIN pg_namespace AS ns
    ON ns.oid = tbl.relnamespace
WHERE ns.nspname = 'public'
  AND tbl.relname = 'orders'
ORDER BY idx.relname;
~~~

Với index được tạo concurrent, cần kiểm tra indisvalid và indisready. Nếu thao tác build thất bại, index có thể vẫn tồn tại nhưng không hợp lệ. Không chỉ kiểm tra tên index.

Catalog columns có thể thay đổi theo phiên bản PostgreSQL; kiểm tra tài liệu DBMS đang vận hành trước khi đóng gói query cho nhiều major version.

## 19. MySQL: kiểm tra constraint và index metadata

Có thể xem constraint trong information_schema.table_constraints:

~~~sql
SELECT
    constraint_name,
    constraint_type,
    table_name
FROM information_schema.table_constraints
WHERE constraint_schema = DATABASE()
  AND table_name = 'orders'
ORDER BY constraint_name;
~~~

Xem cột tham gia key:

~~~sql
SELECT
    constraint_name,
    column_name,
    ordinal_position,
    referenced_table_name,
    referenced_column_name
FROM information_schema.key_column_usage
WHERE table_schema = DATABASE()
  AND table_name = 'orders'
ORDER BY constraint_name, ordinal_position;
~~~

Xem index:

~~~sql
SELECT
    index_name,
    non_unique,
    seq_in_index,
    column_name,
    collation,
    sub_part,
    index_type
FROM information_schema.statistics
WHERE table_schema = DATABASE()
  AND table_name = 'orders'
ORDER BY index_name, seq_in_index;
~~~

NON_UNIQUE=0 biểu thị index unique. SEQ_IN_INDEX giúp kiểm tra thứ tự cột. Với functional index, expression và các tính năng mới, cách biểu diễn phụ thuộc phiên bản MySQL/MariaDB.

Không dùng cột CARDINALITY trong statistics làm bằng chứng tính duy nhất hoặc số hàng chính xác; đây là thống kê ước lượng. Kiểm tra dữ liệu thực tế bằng GROUP BY/HAVING khi cần.

## 20. SQL Server: kiểm tra constraint và index

Constraint có thể được xem qua catalog views:

~~~sql
SELECT
    name,
    type_desc,
    is_disabled,
    is_not_trusted
FROM sys.check_constraints
WHERE parent_object_id = OBJECT_ID(N'dbo.orders');
~~~

Foreign key:

~~~sql
SELECT
    name,
    is_disabled,
    is_not_trusted,
    delete_referential_action_desc,
    update_referential_action_desc
FROM sys.foreign_keys
WHERE parent_object_id = OBJECT_ID(N'dbo.orders');
~~~

Index:

~~~sql
SELECT
    i.name,
    i.type_desc,
    i.is_unique,
    i.is_disabled,
    i.has_filter,
    i.filter_definition
FROM sys.indexes AS i
WHERE i.object_id = OBJECT_ID(N'dbo.orders')
  AND i.index_id > 0;
~~~

is_disabled=1 cho biết index/constraint bị disable theo loại object tương ứng. is_not_trusted=1 ở constraint cho biết SQL Server không tin rằng mọi hàng hiện có đã được kiểm tra theo constraint. Cần xem thêm sys.index_columns để xác minh key columns, thứ tự và included columns.

Catalog query cần quyền phù hợp và tên schema/object chính xác. Không áp dụng cùng một query cho PostgreSQL, MySQL và SQL Server.

## 21. Liquibase precondition và hậu kiểm là hai lớp khác nhau

Precondition giúp kiểm tra điều kiện trước khi changeset chạy. Ví dụ yêu cầu bảng orders tồn tại:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 011-add-order-status-index
      author: order-team
      preConditions:
        - onFail: HALT
        - onError: HALT
        - tableExists:
            tableName: orders
      changes:
        - createIndex:
            tableName: orders
            indexName: idx_orders_status
            columns:
              - column:
                  name: status
~~~

Precondition này không chứng minh index sau khi tạo có đúng trạng thái hoặc query plan được cải thiện. Hậu kiểm phải chạy sau update.

Có thể dùng sqlCheck để chặn migration nếu dữ liệu chưa đạt điều kiện:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 012-enforce-customer-status
      author: customer-team
      preConditions:
        - onFail: HALT
        - sqlCheck:
            expectedResult: "0"
            sql: SELECT COUNT(*) FROM customer WHERE status IS NULL
      changes:
        - addNotNullConstraint:
            tableName: customer
            columnName: status
            columnDataType: varchar(20)
~~~

Cú pháp SQL, quoting và kiểu dữ liệu cần phù hợp DBMS. Precondition chạy trước changeset; nếu nó pass, Liquibase mới thực hiện thay đổi. Sau đó vẫn cần hậu kiểm constraint và dữ liệu vì có thể có ghi đồng thời, trigger hoặc behavior khác trong quá trình triển khai.

## 22. Kiểm tra DATABASECHANGELOG sau update

Sau khi migration job thành công, xác minh changeset mong đợi được ghi nhận tại đúng target:

~~~sql
SELECT
    ID,
    AUTHOR,
    FILENAME,
    MD5SUM,
    EXECTYPE,
    DATEEXECUTED,
    ORDEREXECUTED
FROM DATABASECHANGELOG
WHERE ID IN (
    '010-add-invoice-amount-check',
    '011-add-order-status-index',
    '012-enforce-customer-status'
)
ORDER BY ORDEREXECUTED;
~~~

Kết quả cần đối chiếu với release manifest và changelog revision. EXECTYPE có thể là EXECUTED, MARK_RAN hoặc RERAN tùy tình huống. Nếu một changeset được MARK_RAN, hậu kiểm phải chứng minh object/data tương ứng đã tồn tại đúng như yêu cầu.

DATABASECHANGELOG chỉ chứng minh Liquibase đã ghi nhận changeset. Nó không thay thế kiểm tra catalog và data assertions.

## 23. Kiểm tra hiệu năng của index bằng execution plan

Index tồn tại không bảo đảm query dùng index. Sau migration, lấy execution plan cho các truy vấn quan trọng và so sánh với baseline:

- PostgreSQL: EXPLAIN và, khi an toàn, EXPLAIN (ANALYZE, BUFFERS).
- MySQL: EXPLAIN; một số phiên bản hỗ trợ EXPLAIN ANALYZE.
- SQL Server: actual execution plan hoặc các công cụ plan phù hợp.

EXPLAIN ANALYZE thực thi query; không chạy tùy tiện trên câu lệnh có side effect hoặc truy vấn rất nặng ở production. Actual plan có thể cần chạy với dữ liệu và tham số đại diện.

Kiểm tra scan type và index được chọn, estimated rows so với actual rows, join strategy/order, sort/hash spill, logical/physical reads, predicate pushdown, buffer usage và latency p50/p95/p99 trong workload thực.

Optimizer có thể chọn sequential/table scan hợp lý nếu bảng nhỏ hoặc phần lớn hàng được đọc. Không coi việc không dùng index là lỗi nếu execution plan và hiệu năng vẫn tốt.

## 24. Kiểm tra index không gây tác dụng phụ ngoài ý muốn

Index giúp đọc nhưng làm tăng chi phí ghi, lưu trữ và bảo trì. Sau khi thêm index, quan sát:

- Thời gian INSERT/UPDATE/DELETE.
- CPU, I/O và dung lượng.
- Lock wait và replication lag.
- Thời gian build và ảnh hưởng tới workload.
- Index có bị trùng lặp với index hiện hữu không.
- Index có được dùng trong query workload hay không.

Một index gần giống index cũ nhưng khác thứ tự cột có thể hữu ích hoặc dư thừa tùy workload. Không drop index cũ ngay sau khi tạo index mới nếu chưa có thời gian quan sát và kiểm tra mọi truy vấn phụ thuộc.

Với index lớn, lựa chọn online/concurrent build là đặc thù DBMS. Ví dụ PostgreSQL CREATE INDEX CONCURRENTLY có yêu cầu transaction riêng; một changeset Liquibase có thể cần runInTransaction: false cho SQL đó. Phải kiểm thử failure behavior và kiểm tra index invalid sau khi build thất bại.

## 25. Transaction, concurrent writes và race condition khi kiểm tra

Một phép kiểm tra dữ liệu có thể pass rồi dữ liệu lại vi phạm trước khi constraint được áp dụng nếu ứng dụng vẫn ghi đồng thời.

Ví dụ:

1. Query xác nhận không có email trùng.
2. Ứng dụng tạo thêm hai customer có cùng email.
3. Liquibase bắt đầu tạo unique constraint.
4. Migration thất bại do duplicate mới.

Cách kiểm soát:

- Dùng constraint để DBMS là lớp bảo vệ cuối.
- Tạm kiểm soát writer hoặc deploy code tương thích trước.
- Dùng transaction/locking phù hợp với DBMS.
- Thiết kế migration theo expand–migrate–contract.
- Chạy lại data assertion ngay trước bước siết constraint.
- Nếu DBMS hỗ trợ constraint chưa validate, áp dụng theo kế hoạch rồi validate sau.
- Theo dõi race trong thời gian backfill và rollout.

Một câu SELECT pass không tạo ra bảo đảm rằng điều kiện vẫn đúng ở thời điểm DDL chạy. Hãy thiết kế thứ tự và cơ chế khóa dựa trên semantics thực tế của DBMS.

## 26. Kiểm tra migration theo batch và checkpoint

Với bảng lớn, backfill có thể chạy theo batch. Cần xác minh:

- Mỗi batch có checkpoint rõ.
- Không bỏ sót khoảng khóa hoặc partition.
- Retry không cập nhật sai hàng đã hoàn tất.
- Hàng mới phát sinh trong lúc backfill được xử lý.
- Tiến độ ghi nhận khớp số hàng thực tế.
- Có thể resume sau process restart.
- Không giữ transaction quá dài gây lock, WAL/undo growth hoặc replication lag.

Ví dụ kiểm tra tiến độ:

~~~sql
SELECT
    COUNT(*) AS total_rows,
    SUM(CASE WHEN normalized_value IS NOT NULL THEN 1 ELSE 0 END) AS completed_rows,
    SUM(CASE WHEN normalized_value IS NULL THEN 1 ELSE 0 END) AS remaining_rows
FROM customer;
~~~

Nếu migration chỉ áp dụng cho subset, phải dùng đúng predicate giống job backfill. Đừng so sánh completed_rows + remaining_rows với toàn bộ bảng nếu một số hàng được loại trừ theo nghiệp vụ.

## 27. Dùng test data và fixture có kiểm soát

Bộ dữ liệu test nên bao gồm:

- Trường hợp hợp lệ điển hình.
- Giá trị NULL/empty nếu được phép.
- Boundary values và giá trị lớn.
- Duplicate hoặc orphan có chủ đích để kiểm tra constraint.
- Unicode, collation và ký tự đặc biệt.
- Nhiều tenant/partition.
- Dữ liệu lịch sử có format cũ.
- Hàng mới được ghi đồng thời trong giai đoạn migration.

Không sao chép dữ liệu production có PII/secret vào môi trường test nếu chưa có quy trình bảo vệ và ẩn danh. Fixture nên nhỏ cho unit/integration test; performance/rehearsal dùng dữ liệu tổng hợp có phân bố gần thực tế.

Sau khi seed fixture, xác nhận test không vô tình chạy trên database production. Dùng target alias rõ và tài khoản test riêng.

## 28. Pipeline kiểm thử hậu migration

Một pipeline có thể chia thành các bước:

~~~text
Build changelog artifact
        |
        v
Validate + status + SQL preview
        |
        v
Apply migration to disposable DB
        |
        v
Check Liquibase history
        |
        v
Check constraints + indexes
        |
        v
Run data invariants
        |
        v
Run query-plan/performance checks
        |
        v
Run application smoke tests
        |
        v
Publish test evidence / approve promotion
~~~

Mỗi bước cần trả exit code rõ ràng. Nếu data invariant quan trọng không đạt, pipeline phải fail và chặn promote. Với kiểm tra hiệu năng có ngưỡng, cần so sánh cùng DBMS/version, dataset và cấu hình tương đương.

Không chạy toàn bộ truy vấn scan bảng lớn trên production trong mỗi deployment nếu chi phí không phù hợp. Chọn kiểm tra nhẹ/targeted cho production và kiểm tra sâu trên clone/rehearsal; những invariant an toàn và cần thiết vẫn phải được kiểm chứng tại target trước khi siết constraint.

## 29. Phân loại lỗi khi hậu kiểm

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Foreign key tạo thất bại | Orphan rows hoặc kiểu/collation không tương thích | Tìm orphan, xác minh mapping và schema hai phía |
| Unique constraint thất bại | Duplicate theo business key | Phân loại, merge hoặc sửa dữ liệu theo rule |
| NOT NULL thất bại | Backfill thiếu hoặc writer cũ tiếp tục ghi NULL | Drain writer, backfill lại, kiểm tra race |
| CHECK không đạt | Dữ liệu cũ vi phạm miền giá trị | Phân loại ngoại lệ và thống nhất rule |
| Index tồn tại nhưng query chậm | Định nghĩa/order/filter không phù hợp hoặc statistics cũ | Đọc plan và workload |
| PostgreSQL index invalid | Concurrent build thất bại | Kiểm tra pg_index, xử lý index invalid theo runbook |
| SQL Server constraint not trusted | Dữ liệu cũ chưa được validate | Xác minh và validate theo quy trình DBMS |
| DATABASECHANGELOG có row nhưng object thiếu | MARK_RAN, drift hoặc thay đổi ngoài Liquibase | Đối chiếu EXECTYPE, catalog và thực tế |
| Changeset thành công nhưng data thiếu | Filter/batch/checkpoint/transaction issue | Đối chiếu watermark, row count và invariant |
| Staging pass, production fail | Dataset/DBMS/version/concurrency khác | Rehearsal với dữ liệu và cấu hình đại diện |

Không xóa history hoặc đánh dấu changeset lại để làm pipeline xanh. Hãy tìm nguyên nhân và tạo forward fix/recovery plan có thể review.

## 30. Bài thực hành: thêm foreign key và index có hậu kiểm

Thực hiện trên database disposable, không dùng production.

### Bối cảnh

Bảng orders có customer_id, bảng customer có id. Hệ thống muốn bảo đảm mọi order có customer hợp lệ và tăng tốc truy vấn theo tenant/status.

### Bước 1 — Kiểm tra dữ liệu trước migration

Chạy truy vấn orphan, NULL và duplicate theo business key. Lưu số lượng và tập ngoại lệ trên fixture. Nếu có orphan, không tiếp tục thêm FK cho tới khi đã xử lý theo rule.

### Bước 2 — Thêm changeset

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 020-add-orders-customer-fk
      author: order-team
      preConditions:
        - onFail: HALT
        - tableExists:
            tableName: orders
        - tableExists:
            tableName: customer
      changes:
        - addForeignKeyConstraint:
            baseTableName: orders
            baseColumnNames: customer_id
            referencedTableName: customer
            referencedColumnNames: id
            constraintName: fk_orders_customer
  - changeSet:
      id: 021-add-orders-tenant-status-index
      author: order-team
      changes:
        - createIndex:
            tableName: orders
            indexName: idx_orders_tenant_status
            columns:
              - column:
                  name: tenant_id
              - column:
                  name: status
~~~

Ví dụ giả định các bảng ở schema/default schema phù hợp và customer.id có unique/primary key. Trong dự án thật, khai báo schema/catalog nếu cần, xác minh kiểu dữ liệu tương thích và xem xét thứ tự changeset theo dữ liệu.

### Bước 3 — Chạy migration và kiểm tra history

Chạy validate, status, updateSQL, review rồi update trên database thử nghiệm. Truy vấn DATABASECHANGELOG để xác nhận hai changeset được ghi nhận với EXECTYPE mong đợi.

### Bước 4 — Hậu kiểm constraint và index

Dùng catalog query của DBMS để xác nhận foreign key trỏ đúng bảng/cột, index có đúng thứ tự tenant_id/status, trạng thái valid/enabled phù hợp. Chạy lại truy vấn orphan và duplicate.

### Bước 5 — Kiểm tra hành vi và hiệu năng

Thử insert order tham chiếu customer không tồn tại; thao tác phải bị DBMS từ chối theo constraint. Chạy query workload đại diện và đọc execution plan. So sánh latency/read/write cost với baseline.

### Bước 6 — Mô phỏng lỗi

Trên fixture riêng, tạo orphan rồi thử migration để quan sát failure. Xác minh pipeline dừng, history không bị đánh dấu sai và dữ liệu ngoại lệ được báo cáo. Sửa dữ liệu theo rule rồi chạy lại trên database disposable; không sửa tay history.

## 31. Checklist nghiệm thu sau migration

- [ ] Đã xác định invariant nghiệp vụ và kết quả mong đợi trước khi chạy.
- [ ] Đã xác minh target, DBMS/version, database và schema.
- [ ] DATABASECHANGELOG ghi nhận đúng changeset và EXECTYPE.
- [ ] Bảng, cột, kiểu dữ liệu, default và nullability đúng.
- [ ] Primary key có đủ cột, đúng thứ tự và không có duplicate/NULL.
- [ ] Foreign key trỏ đúng bảng/cột và không có orphan ngoài phạm vi cho phép.
- [ ] Unique constraint/index đúng business key và predicate.
- [ ] CHECK constraint được bật và validated/trusted theo yêu cầu.
- [ ] Index đúng tên/phạm vi/column order/uniqueness/filter/include/expression.
- [ ] Index ở trạng thái valid/ready/enabled phù hợp DBMS.
- [ ] Data backfill đạt row count, NULL, duplicate, range và relationship invariants.
- [ ] Đã kiểm tra theo tenant/partition/time range để không che lỗi cục bộ.
- [ ] Đã đối chiếu số lượng/tổng hợp với snapshot hoặc watermark phù hợp.
- [ ] Đã đánh giá concurrent writes và race condition trước khi siết constraint.
- [ ] Execution plan và hiệu năng truy vấn quan trọng không suy giảm ngoài ngưỡng.
- [ ] Đã kiểm tra lock, transaction, replication lag và chi phí index build.
- [ ] Đã phân biệt precondition trước changeset với hậu kiểm sau migration.
- [ ] Kiểm tra production dùng quyền đọc phù hợp và không gây scan quá nặng.
- [ ] Pipeline fail khi invariant bắt buộc không đạt.
- [ ] Đã thử trên database disposable/clone với fixture có trường hợp biên.
- [ ] Có log, release ID, target, revision, kết quả và owner cho từng assertion.
- [ ] Có kế hoạch xử lý partial failure, forward fix và rollback dữ liệu/schema.

**Ghi nhớ:** Hậu kiểm migration phải xác nhận cả **cấu trúc, trạng thái constraint/index và dữ liệu thực tế**. Một row trong DATABASECHANGELOG hoặc một index cùng tên chưa chứng minh database đã đúng. Hãy định nghĩa invariant trước, kiểm tra metadata trong catalog của đúng DBMS, chạy truy vấn phát hiện duplicate/orphan/NULL và đối chiếu dữ liệu theo tenant/partition. Sau đó đánh giá execution plan và hành vi ứng dụng. Đưa các assertion bắt buộc vào CI/CD và chặn promotion khi chúng không đạt; đây là cách biến kết quả Liquibase update thành bằng chứng database sẵn sàng vận hành.

