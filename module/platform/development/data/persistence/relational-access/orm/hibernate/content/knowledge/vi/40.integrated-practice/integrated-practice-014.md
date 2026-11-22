# Danh sách kiểm tra trước khi đưa phần truy cập Hibernate vào sử dụng

## 1. Mục đích của checklist triển khai

Một tính năng truy cập dữ liệu có thể chạy đúng trên máy developer nhưng vẫn gặp sự cố khi đưa vào môi trường thật: migration thiếu index, transaction không bao trùm toàn bộ thao tác, query tạo N+1, tenant predicate bị bỏ sót, entity detached bị merge sai, connection pool cạn hoặc cache trả dữ liệu cũ.

Trước khi đưa một phần Hibernate ORM vào sử dụng, cần kiểm tra cả đường đi của dữ liệu:

~~~text
HTTP / Job / Message
        |
        v
Application service + authorization
        |
        v
Transaction boundary
        |
        v
Repository / EntityManager / Hibernate
        |
        v
JDBC driver + connection pool
        |
        v
Database schema + constraints + indexes
        |
        v
Commit / events / cache invalidation
~~~

Checklist này dành cho giai đoạn hoàn thiện một tính năng persistence trước khi merge, release hoặc bật traffic production. Nó giúp nhóm xác nhận mapping, schema, transaction, query, security, performance, test và vận hành đã có bằng chứng phù hợp.

Không phải mọi mục đều áp dụng cho mọi tính năng. Hãy đánh dấu N/A khi có lý do rõ ràng; không bỏ qua một mục chỉ vì test hiện tại chưa phát hiện vấn đề.

### Mục tiêu

Sau bài này, bạn có thể:

1. Kiểm tra phạm vi thay đổi entity/repository/schema trước khi release.
2. Xác nhận mapping và migration thống nhất.
3. Kiểm tra identifier, relationship, constraints và indexes.
4. Xác định transaction boundary và rollback behavior.
5. Kiểm soát entity lifecycle, merge, cascade và dirty checking.
6. Phát hiện N+1, pagination lỗi và query quá rộng.
7. Xác nhận authorization, tenant isolation và data visibility.
8. Kiểm tra concurrency, optimistic/pessimistic locking và idempotency.
9. Xác định cache, event và side-effect consistency.
10. Kiểm tra connection pool, timeout, observability và failure handling.
11. Chạy test trên database production tương ứng.
12. Chuẩn bị rollout, rollback và vận hành sau deploy.

## 2. Cách sử dụng checklist

Mỗi mục nên có một trong ba trạng thái:

| Trạng thái | Ý nghĩa |
|---|---|
| PASS | Có bằng chứng cụ thể cho thấy yêu cầu được đáp ứng |
| N/A | Không áp dụng, có giải thích ngắn |
| BLOCKED | Chưa có bằng chứng hoặc còn vấn đề cần xử lý |

Một checklist tốt không chỉ ghi “đã kiểm tra”. Gắn với mỗi mục một bằng chứng có thể xem lại:

- Tên test hoặc test report.
- Migration version và database version.
- SQL/execution plan.
- Log hoặc metric.
- Link pull request/review.
- Quyết định kiến trúc hoặc risk acceptance.

### 2.1. Phân biệt kiểm tra kỹ thuật và chấp nhận rủi ro

Nếu một query chưa được benchmark nhưng tính năng có traffic rất thấp, nhóm có thể quyết định chấp nhận rủi ro trong phạm vi rõ. Ghi người chịu trách nhiệm, giới hạn traffic và điều kiện đánh giá lại. Không đánh dấu PASS cho một kiểm tra chưa thực hiện.

### 2.2. Checklist theo mức độ thay đổi

- Entity/mapping mới: ưu tiên lifecycle, schema, constraints, fetch plan.
- Query mới: ưu tiên scope, cardinality, pagination, SQL và execution plan.
- Migration: ưu tiên dữ liệu cũ, lock, rollback/forward-fix và compatibility.
- Transaction/concurrency: ưu tiên isolation, locks, version, retry.
- Cache: ưu tiên invalidation, tenant key và stale data.
- Production rollout: kiểm tra toàn bộ đường vận hành và rollback.

## 3. Xác định phạm vi tính năng và chủ sở hữu dữ liệu

- [ ] Mục đích nghiệp vụ của phần truy cập dữ liệu được mô tả rõ.
- [ ] Xác định bảng/entity nào là nguồn dữ liệu chính.
- [ ] Xác định aggregate root và ranh giới ownership.
- [ ] Xác định các service/job/message consumer có thể đọc hoặc ghi cùng dữ liệu.
- [ ] Xác định hệ thống ngoài có truy cập trực tiếp database không.
- [ ] Xác định ai chịu trách nhiệm schema và migration.
- [ ] Xác định dữ liệu nào là authoritative, dữ liệu nào là projection/cache.
- [ ] Xác định yêu cầu consistency và độ trễ chấp nhận được.
- [ ] Xác định dữ liệu nhạy cảm, retention và audit requirements.

### 3.1. Một bảng có thể có nhiều writer

Hibernate không phải lúc nào cũng là writer duy nhất. Dữ liệu có thể được ghi bởi:

- REST API.
- Batch job.
- Message consumer.
- Native JDBC.
- Stored procedure hoặc trigger.
- ETL/import job.
- Admin scripts hoặc hệ thống legacy.

Nếu có nhiều writers, invariants quan trọng nên được bảo vệ ở database khi có thể: NOT NULL, UNIQUE, FK, CHECK, exclusion constraints hoặc trigger có chủ đích. Chỉ validate ở Java không bảo vệ được các đường ghi khác.

### 3.2. Xác định contract với consumer

Nếu entity/table được dùng bởi reporting, ETL hoặc service khác, migration cần xem xét compatibility. Đổi tên column hoặc semantics của status có thể ảnh hưởng consumer không nằm trong cùng repository.

## 4. Mapping entity và schema

- [ ] Mỗi entity có identifier rõ ràng.
- [ ] Table và column names khớp schema production.
- [ ] Nullability trong mapping phù hợp domain và DDL.
- [ ] Column length, precision, scale và SQL type phù hợp dữ liệu.
- [ ] Enum mapping có contract ổn định.
- [ ] Date/time mapping phân biệt instant, local time và timezone.
- [ ] UUID/binary/JSON mapping được kiểm tra bằng driver production.
- [ ] Embedded/value objects có column names không xung đột.
- [ ] Inheritance strategy phù hợp query và schema.
- [ ] Secondary table/join table được khai báo đúng.
- [ ] Access type (field/property) nhất quán và chủ ý.
- [ ] Không có duplicate writable mappings cho cùng column ngoài thiết kế có chủ đích.

### 4.1. Nullability

Nếu domain yêu cầu Customer luôn tồn tại, cả mapping lẫn schema phải phản ánh:

~~~java
@ManyToOne(fetch = FetchType.LAZY, optional = false)
@JoinColumn(name = "customer_id", nullable = false)
private Customer customer;
~~~

DDL cũng cần NOT NULL và FK tương ứng. Annotation không tự chứng minh production migration đã tạo constraint.

### 4.2. Decimal và tiền tệ

- [ ] Precision/scale đủ cho giá trị tối đa.
- [ ] Rounding mode và thời điểm rounding được xác định.
- [ ] Currency được lưu cùng amount khi nghiệp vụ cần.
- [ ] Không dùng floating point cho số tiền cần chính xác thập phân.
- [ ] Test overflow, boundary và scale trên database đích.

### 4.3. Thời gian

- [ ] Dùng Instant/OffsetDateTime/LocalDateTime theo đúng semantics.
- [ ] Timezone lưu trữ và timezone hiển thị được tách biệt.
- [ ] Precision của database column được tính đến.
- [ ] Test range query qua ngày địa phương và DST nếu có.
- [ ] Không dựa vào timezone mặc định của máy chạy test.

### 4.4. Enum

Ưu tiên STRING hoặc converter với stable code khi enum là dữ liệu bền vững. Nếu dùng ORDINAL, đã đánh giá rủi ro reorder/thêm constant và có migration tương ứng.

## 5. Identifier và generator

- [ ] Generation strategy (IDENTITY, SEQUENCE, TABLE, UUID, assigned) được chọn có chủ đích.
- [ ] Không dựa vào AUTO nếu schema cần generator cố định mà chưa kiểm tra behavior của Hibernate version/dialect.
- [ ] Generator name được phân biệt với database sequence name.
- [ ] Sequence/schema/catalog names rõ ràng khi cần.
- [ ] allocationSize khớp optimizer và database sequence increment.
- [ ] Sequence state an toàn so với IDs đã import/backfill.
- [ ] Không có code giả định ID liên tiếp hoặc gapless.
- [ ] Không dùng MAX(id)+1 để cấp primary key.
- [ ] Spring Data new detection đúng với assigned ID/UUID.
- [ ] JDBC batching được đánh giá riêng với generator.
- [ ] Rolling deployment không để hai versions cấp ID từ nguồn không tương thích.

### 5.1. Kiểm tra sau import

Nếu migration/import giữ nguyên IDs:

1. Xác định tất cả bảng dùng sequence.
2. Kiểm tra MAX(id) hoặc toàn bộ ID namespace.
3. Kiểm tra sequence current state và increment.
4. Xác định optimizer đang dùng.
5. Đồng bộ sequence theo đúng generator contract.
6. Tạo entities mới qua Hibernate và xác nhận không collision.

Không chạy reset sequence trong khi application instances vẫn giữ các block IDs đã preallocate.

## 6. Relationship và aggregate ownership

- [ ] Mỗi association có owner/inverse side rõ.
- [ ] mappedBy trỏ đúng property phía owning side.
- [ ] JoinColumn/JoinColumns khớp physical schema.
- [ ] Cascade chỉ được bật khi lifecycle ownership yêu cầu.
- [ ] orphanRemoval phù hợp semantics xóa child.
- [ ] Collection được khởi tạo theo convention nhất quán.
- [ ] Helper methods đồng bộ hai phía của bidirectional relationship.
- [ ] Không cascade REMOVE/MERGE rộng sang shared reference entities ngoài ý muốn.
- [ ] Composite foreign keys được dùng khi cần enforce cùng organization/namespace.
- [ ] Database FK có index hỗ trợ các đường join/delete quan trọng.

### 6.1. Owning side

Với quan hệ hai chiều, database FK thường được điều khiển bởi owning side. Chỉ sửa inverse collection có thể không cập nhật FK như mong muốn. Domain helper nên đồng bộ cả hai phía:

~~~java
public void addItem(OrderItem item) {
    items.add(item);
    item.setOrder(this);
}

public void removeItem(OrderItem item) {
    items.remove(item);
    item.setOrder(null);
}
~~~

### 6.2. Cascade

Không dùng CascadeType.ALL như mặc định cho mọi association. Với Customer/Product/User được chia sẻ bởi nhiều aggregate, cascade remove/merge có thể gây tác động ngoài dự kiến.

### 6.3. Collection semantics

- List nếu thứ tự là một phần domain.
- Set nếu uniqueness là semantics thật và equals/hashCode ổn định.
- Map nếu key có ý nghĩa domain.
- Không đổi List thành Set chỉ để né MultipleBagFetchException.

## 7. Schema migration và compatibility

- [ ] Migration được version hóa bằng Flyway/Liquibase hoặc quy trình tương đương.
- [ ] Migration mới chạy từ database rỗng.
- [ ] Migration upgrade chạy từ schema/data version cũ đại diện.
- [ ] Không sửa migration đã được áp dụng ở môi trường chia sẻ/production.
- [ ] DDL được chạy trên đúng database vendor/version.
- [ ] Indexes, constraints, triggers, functions và policies được kiểm tra riêng.
- [ ] Hibernate ddl-auto không vô tình ghi schema ngoài migration.
- [ ] Production dùng schema policy rõ (thường validate/none khi migration sở hữu schema).
- [ ] Migration có kế hoạch lock, thời gian chạy và tác động dữ liệu.
- [ ] Expand/backfill/contract được dùng khi cần compatibility nhiều phiên bản.
- [ ] Có forward-fix/rollback strategy thực tế.

### 7.1. Expand–migrate–contract

Với thay đổi không tương thích trực tiếp:

1. Thêm column/table/object mới nhưng vẫn giữ đường cũ.
2. Deploy code tương thích cả hai dạng khi cần.
3. Backfill dữ liệu theo batch có thể resume.
4. Chuyển reads/writes sang dạng mới.
5. Đối soát dữ liệu và theo dõi consumers cũ.
6. Xóa object cũ trong release sau.

Không gộp thêm column, backfill hàng triệu rows và drop column cũ vào một thao tác không có kế hoạch lock/rollback.

### 7.2. Index production

Với PostgreSQL, CREATE INDEX CONCURRENTLY có transaction restrictions và operational behavior riêng. Test migration syntax trong database thật; đánh giá thời gian, lock và disk trên dữ liệu gần production.

### 7.3. Schema validation

Hibernate validate hữu ích để phát hiện một số lệch table/column/type, nhưng không thay catalog assertions cho partial indexes, triggers, RLS, grants hoặc function definitions.

## 8. Naming strategy và physical identifiers

- [ ] ImplicitNamingStrategy hiện tại được biết rõ.
- [ ] PhysicalNamingStrategy hiện tại được biết rõ.
- [ ] Spring Boot/Hibernate versions dùng class strategy tương thích.
- [ ] Table/column/sequence/join table names khớp migration.
- [ ] Không nhầm JPQL entity/property names với native SQL physical names.
- [ ] Schema/catalog/search_path được xác định.
- [ ] App runtime role có quyền trên table và sequence.
- [ ] Quoted identifiers/case folding/reserved words được xử lý rõ.
- [ ] Không có identifier collision sau normalization/truncation.
- [ ] Đổi naming strategy có migration và compatibility plan.

### 8.1. Kiểm tra object thực tế

Đọc schema catalog hoặc migration output để xác nhận tên vật lý. Đừng chỉ đọc annotation rồi suy ra Hibernate sẽ dùng chính xác chuỗi đó; physical naming strategy có thể biến đổi logical identifier.

### 8.2. Native SQL

Native query phải dùng physical table/column names và quoting đúng database. JPQL/HQL dùng entity/property names. Hai loại query có namespace khác nhau.

## 9. Transaction boundary

- [ ] Transaction bắt đầu ở application service/use-case boundary phù hợp.
- [ ] Đọc và ghi liên quan nằm trong cùng transaction khi cần atomicity.
- [ ] Không để transaction bao quanh network calls lâu không cần thiết.
- [ ] Transaction propagation được hiểu rõ.
- [ ] Checked/runtime exceptions và rollback rules được xác định.
- [ ] REQUIRES_NEW chỉ dùng khi cần transaction độc lập.
- [ ] Self-invocation không vô tình bỏ qua Spring transaction proxy.
- [ ] Async jobs tạo transaction/persistence context riêng.
- [ ] Không chia sẻ EntityManager/managed entities giữa threads.
- [ ] Transaction timeout phù hợp workload.

### 9.1. Service boundary

Ví dụ:

~~~java
@Transactional
public OrderResponse createOrder(CreateOrderCommand command) {
    Customer customer = customerRepository
        .findByIdAndOrganizationId(
            command.customerId(), command.organizationId())
        .orElseThrow(CustomerNotFoundException::new);

    PurchaseOrder order = PurchaseOrder.create(
        command.orderNumber(), customer);

    orderRepository.save(order);
    return mapper.toResponse(order);
}
~~~

Transaction bao trùm load, validate, tạo aggregate và flush/commit. Response DTO được map khi dữ liệu cần thiết còn truy cập được.

### 9.2. Rollback behavior

- [ ] Test constraint violation rollback.
- [ ] Test exception sau một phần writes.
- [ ] Xác nhận audit/outbox rows cùng rollback nếu cùng transaction.
- [ ] Xác nhận side effect ngoài database không xảy ra trước commit nếu không có cơ chế bảo đảm.

### 9.3. Không giữ transaction mở khi chờ external service

Nếu cần gọi payment/email/HTTP, cân nhắc outbox hoặc workflow orchestration. Giữ DB transaction mở trong lúc network call có thể giữ connection/locks quá lâu.

## 10. Entity lifecycle và dirty checking

- [ ] New/managed/detached/removed states được hiểu trong code path.
- [ ] Entity managed được sửa trong transaction.
- [ ] Merge return value không bị bỏ qua.
- [ ] Spring Data save return value được dùng khi có thể merge.
- [ ] Không giả định save luôn persist hoặc luôn merge.
- [ ] Detached objects không được sửa rồi kỳ vọng dirty checking.
- [ ] Không merge entity graph từ HTTP request một cách mù quáng.
- [ ] Partial updates dùng command/DTO với semantics null rõ.
- [ ] Bulk/native DML có kế hoạch clear/refresh persistence context.
- [ ] Flush timing và commit timing không bị nhầm lẫn.

### 10.1. Pattern ưu tiên cho command

Tải managed entity theo ID và scope, kiểm tra quyền/business rule, rồi gọi domain method:

~~~java
@Transactional
public void cancel(Long id, Long organizationId) {
    PurchaseOrder order = repository
        .findByIdAndOrganizationId(id, organizationId)
        .orElseThrow(OrderNotFoundException::new);

    order.cancel();
}
~~~

Không cần gọi save lại sau setter nếu entity đã managed và transaction còn mở.

### 10.2. Merge

Nếu merge là lựa chọn có chủ đích:

- [ ] Source state đầy đủ/authoritative theo contract.
- [ ] Returned managed instance được giữ.
- [ ] Cascade graph được kiểm soát.
- [ ] @Version/stale state được xử lý.
- [ ] Collection/orphan semantics được test.
- [ ] Không tiếp tục sửa source detached sau merge.

## 11. Fetch strategy và query shape

- [ ] Association to-one/to-many được phân biệt.
- [ ] Mapping mặc định không vô tình EAGER graph quá rộng.
- [ ] Mỗi use case có fetch plan phù hợp.
- [ ] Không có N+1 trong vòng lặp hoặc serializer.
- [ ] JOIN FETCH to-many không làm row multiplication vượt kiểm soát.
- [ ] Không fetch nhiều collection bags cùng lúc nếu gây MultipleBagFetchException.
- [ ] Pagination root không kết hợp collection fetch join nguy hiểm.
- [ ] Batch fetch/Subselect được chọn theo access pattern.
- [ ] DTO projection dùng khi chỉ cần read model/các cột cụ thể.
- [ ] Query count, rows và payload size được đo.

### 11.1. List và detail là hai use cases khác nhau

List page thường cần DTO gọn: ID, number, status, customer name, counts. Detail page có thể cần một collection nhỏ. Export lớn cần streaming/chunking. Không tạo một entity graph mặc định tải mọi association cho mọi endpoint.

### 11.2. N+1

Kiểm tra SQL count khi page size tăng từ 10 lên 50. Nếu query count tăng tuyến tính theo số root entities, tìm lazy association bị truy cập trong vòng lặp.

### 11.3. Batch fetching

Đo batch size với cold persistence context và dataset đại diện. Batch fetching giảm round trips nhưng không loại bỏ child rows và không thay thế DTO projection khi chỉ cần aggregate.

### 11.4. Collection fetch pagination

Page IDs trước, rồi fetch to-one/child data theo tập IDs. Bật fail-on-pagination-over-collection-fetch nếu Hibernate version hỗ trợ để phát hiện query nguy hiểm.

## 12. SQL, indexes và execution plan

- [ ] SQL sinh ra được quan sát cho các query quan trọng.
- [ ] Predicate tenant/status/soft-delete được áp dụng đúng.
- [ ] Join keys có indexes phù hợp.
- [ ] Composite indexes theo filter/order được xem xét bằng workload.
- [ ] Foreign key columns có index khi cần cho joins/deletes.
- [ ] Không select columns/collections không dùng.
- [ ] Count query đúng semantics với joins.
- [ ] Query native đã chạy trên đúng database engine.
- [ ] EXPLAIN/EXPLAIN ANALYZE được dùng trên data đại diện cho query quan trọng.
- [ ] Actual rows, buffers, sort/hash spills và plan được xem xét.

### 12.1. Index không phải checklist chỉ dựa trên WHERE

Chọn index dựa trên selectivity, predicate order, sort, join, data distribution và write overhead. Một index làm SELECT nhanh hơn có thể làm INSERT/UPDATE chậm hơn và tăng storage.

### 12.2. Không dùng H2 plan để đánh giá PostgreSQL

Execution plan thuộc database optimizer. Performance test cần engine/version production và data distribution gần thực tế.

### 12.3. Count query

Nếu query root join to-many, COUNT(*) có thể đếm child rows thay vì root entities. Dùng COUNT(DISTINCT root.id) hoặc count query riêng theo business scope.

## 13. Tenant isolation và authorization

- [ ] Tenant/organization ID đến từ trusted principal/context, không tin giá trị client gửi.
- [ ] Mọi read/write query có scope phù hợp.
- [ ] Repository method không cho phép vô tình lookup chỉ bằng ID khi scope bắt buộc.
- [ ] Association references được xác minh cùng tenant.
- [ ] Composite FK được dùng khi cần enforce same-tenant integrity.
- [ ] RLS policies được test bằng runtime role nếu dùng.
- [ ] Superuser/table owner không được dùng làm bằng chứng RLS enforcement.
- [ ] Cache keys chứa tenant scope khi dữ liệu phụ thuộc tenant.
- [ ] Background jobs có tenant context rõ.
- [ ] Admin/global access là quyền riêng, được audit.

### 13.1. ID không phải authorization

Biết Order ID không có nghĩa caller có quyền truy cập Order. Query theo cả ID và trusted organization ID, đồng thời kiểm tra permission:

~~~java
repository.findByIdAndOrganizationId(orderId, trustedOrgId);
~~~

### 13.2. RLS và application predicate

RLS có thể là lớp bảo vệ bổ sung. Application predicate vẫn giúp query rõ, giảm scan và tránh phụ thuộc hoàn toàn vào session context. Test cả policy database lẫn service authorization.

### 13.3. Tenant context và connection pool

Nếu RLS dùng session variable, đảm bảo context được set/clear theo transaction/connection một cách an toàn. Connection pool tái sử dụng physical connections; tenant context không được rò rỉ sang request tiếp theo.

## 14. Constraints và dữ liệu hợp lệ

- [ ] PK/UNIQUE/FK/CHECK/NOT NULL có trong migration.
- [ ] Business key scope đúng (global, organization, year, store...).
- [ ] Soft-delete uniqueness được mô hình hóa rõ.
- [ ] Composite FK enforce relationship invariants cần thiết.
- [ ] Application validation vẫn cung cấp lỗi thân thiện.
- [ ] Database constraint là lớp bảo vệ cuối cho mọi writer.
- [ ] Error mapping phân biệt unique/FK/check/not-null.
- [ ] SQLSTATE/constraint names được test trên DB đích nếu application dựa vào chúng.
- [ ] Dữ liệu legacy được audit trước khi thêm constraint.
- [ ] Constraint NOT VALID/validation rollout có kế hoạch nếu database hỗ trợ.

### 14.1. Application validation không thay database constraint

Check-then-insert có race condition. UNIQUE constraint vẫn cần nếu business yêu cầu uniqueness dưới concurrency.

### 14.2. Error handling

Không map mọi DataIntegrityViolationException thành “duplicate key”. Xác định root cause/constraint phù hợp; các lỗi FK, CHECK và NOT NULL có ý nghĩa khác.

### 14.3. Đối soát dữ liệu cũ

Trước khi thêm constraint, chạy query tìm duplicate, orphan và out-of-range rows. Xử lý dữ liệu trước khi validate constraint.

## 15. Concurrency và locking

- [ ] Entities có concurrent updates quan trọng dùng @Version khi phù hợp.
- [ ] Stale update được chuyển thành conflict có thể hiểu.
- [ ] Pessimistic lock chỉ dùng khi có lý do.
- [ ] Lock timeout/deadlock được xử lý.
- [ ] Không giữ lock trong lúc gọi network.
- [ ] Retry chỉ áp dụng cho lỗi transient và operation có thể retry an toàn.
- [ ] Idempotency key/unique constraint bảo vệ duplicate commands.
- [ ] Concurrency tests dùng nhiều transactions/connections.
- [ ] Test chạy trên database production khi semantics phụ thuộc vendor.

### 15.1. Optimistic locking

~~~java
@Version
private long version;
~~~

Kiểm tra hai transactions cùng đọc một version, một transaction commit trước và transaction còn lại bị conflict. Không chỉ test một thread.

### 15.2. Pessimistic locking

Nếu dùng PESSIMISTIC_WRITE, NOWAIT hoặc SKIP LOCKED, test SQL/behavior trên database đích. Xác định timeout và retry policy.

### 15.3. Retry

Không retry mọi exception. Retry deadlock/serialization failures có thể hợp lý nếu transaction được chạy lại từ đầu và command idempotent. Unique violation thường là conflict nghiệp vụ, không phải lỗi transient.

## 16. Cache và consistency

- [ ] Xác định có L1, Hibernate L2, query cache hoặc application cache không.
- [ ] Cache region/TTL/eviction policy rõ.
- [ ] Update/delete invalidates đúng cache entries.
- [ ] Cache key có tenant/organization scope.
- [ ] Bulk/native DML có xử lý cache invalidation.
- [ ] Không cache managed entity hoặc lazy proxy như object dùng chung.
- [ ] Cold/warm behavior được đo.
- [ ] Read-your-writes requirement được đáp ứng.
- [ ] Eventual consistency được ghi rõ cho consumer.

### 16.1. L1 cache

L1 sống theo persistence context. Sau bulk DML hoặc native JDBC update, managed entities có thể stale. Clear/refresh đúng lúc và tránh trộn nhiều nguồn ghi.

### 16.2. L2/query cache

Cache có thể làm test query count thấp giả tạo. Kiểm tra cold path và invalidation. Không dùng cache để che N+1 hoặc query shape kém.

### 16.3. Application cache

Nếu cache DTO theo ID, key phải bao gồm scope cần thiết. Một cache key thiếu tenant có thể làm lộ dữ liệu dù database query đã scoped đúng.

## 17. Events và side effects sau commit

- [ ] Email/HTTP/payment/event publish không xảy ra trước khi transaction cần thiết commit.
- [ ] Event payload có stable identifier/version.
- [ ] Consumer idempotent.
- [ ] Nếu cần atomicity DB + message, dùng outbox hoặc cơ chế được chứng minh tương đương.
- [ ] Outbox row được ghi cùng transaction với aggregate change.
- [ ] Publisher retry không phát side effect trùng không kiểm soát.
- [ ] Audit events có actor, time, correlation và business context phù hợp.

### 17.1. @TransactionalEventListener

Nếu dùng AFTER_COMMIT, kiểm tra behavior khi transaction rollback và khi listener lỗi. Listener sau commit không làm side effect trở thành atomic với DB; nếu process chết sau commit nhưng trước publish, outbox có thể cần thiết.

### 17.2. Outbox

Outbox row cùng transaction với entity update. Worker đọc/claim và publish; cần unique event ID, retry, lock/lease và idempotency ở consumer.

### 17.3. Không publish trong lúc giữ transaction lâu

Gọi broker/network trực tiếp trong transaction có thể kéo dài connection/locks. Thiết kế side effect theo transaction semantics rõ.

## 18. Validation, domain invariants và lifecycle callbacks

- [ ] Invariants được đặt ở domain/service phù hợp.
- [ ] Bean Validation constraints phản ánh input contract.
- [ ] Database constraints bảo vệ dữ liệu cuối cùng.
- [ ] @PrePersist/@PreUpdate chỉ làm việc phù hợp lifecycle.
- [ ] Không phụ thuộc callback ORM cho các writers dùng JDBC/native SQL.
- [ ] Audit fields được cập nhật ở đúng tầng.
- [ ] Bulk DML behavior với callbacks/version được kiểm tra.
- [ ] Domain transitions có test state trước/sau.

### 18.1. Callback không phải trigger

JPA lifecycle callback chỉ chạy qua các lifecycle paths được provider quản lý. Native SQL, direct JDBC hoặc ETL có thể bypass callback. Nếu invariant phải áp dụng cho mọi writer, cân nhắc database constraint/trigger hoặc đảm bảo mọi writers dùng shared service contract.

### 18.2. Bean Validation không thay CHECK

Validation trước persist giúp lỗi thân thiện. CHECK/NOT NULL bảo vệ database trước các đường ghi khác và race conditions.

## 19. Kiểm thử mapping và repository

- [ ] Repository methods được gọi thật trong test.
- [ ] Test có dữ liệu đủ đa dạng và boundary cases.
- [ ] Test flush để buộc SQL phát sinh khi cần.
- [ ] Test clear/EntityManager mới để tránh L1 che lỗi.
- [ ] Test cascade/orphan removal.
- [ ] Test lazy loading và transaction boundaries.
- [ ] Test paging/count/sort.
- [ ] Test native SQL với đúng engine.
- [ ] Test generated IDs/sequence.
- [ ] Test exception/constraint behavior.

### 19.1. Flush trong test

~~~java
repository.save(order);
entityManager.flush();
entityManager.clear();
~~~

Flush gửi pending SQL; clear loại managed objects khỏi L1. Sau đó query lại để kiểm tra đường đọc thực sự. Nếu test cần commit visibility, dùng transaction mới.

### 19.2. SQL độc lập

Với invariant quan trọng, dùng JdbcTemplate query physical columns/joins/constraints để tránh kiểm tra qua cùng mapping đang được test.

### 19.3. Không assert implementation detail mong manh

Tránh assert Hibernate alias, exact SQL whitespace, sequence IDs liên tiếp hoặc error message đầy đủ. Assert dữ liệu, invariant, constraint behavior và các SQL properties thực sự là contract.

## 20. Kiểm thử trên đúng database production

- [ ] Integration suite dùng cùng database vendor.
- [ ] Database image/version được pin.
- [ ] JDBC driver version tương thích.
- [ ] Flyway/Liquibase chạy trước Hibernate validation.
- [ ] Native SQL/functions/operators được thực thi.
- [ ] Types/UUID/timezone/precision được xác nhận.
- [ ] Index/partial index/constraints/triggers được kiểm tra.
- [ ] Isolation/locking/concurrency được kiểm tra nếu liên quan.
- [ ] RLS/permissions dùng runtime role.
- [ ] Testcontainers/CI runtime được cấu hình.

### 20.1. H2 vẫn hữu ích

H2 có thể dùng cho fast feedback về mapping/query portable và logic repository đơn giản. Nhưng H2 không phải PostgreSQL/MySQL thu nhỏ. Không dùng H2 compatibility mode để chứng minh vendor-specific SQL, migration hoặc locking.

### 20.2. @DataJpaTest

Kiểm tra DataSource thực tế mà slice test sử dụng. Spring Boot có thể thay DataSource bằng embedded database nếu cấu hình cho phép. Dùng Replace.NONE khi cần giữ container DataSource và cung cấp connection details thực.

### 20.3. Testcontainers

Dùng container đúng engine/version production. CI phải có Docker-compatible runtime; nếu integration suite không chạy, báo rõ thay vì âm thầm thay bằng H2 rồi coi như đã xác minh.

## 21. Test migration và upgrade path

- [ ] Migration từ schema sạch chạy thành công.
- [ ] Migration từ version trước chạy với dữ liệu đại diện.
- [ ] Backfill có thể resume hoặc có cách xử lý lỗi rõ.
- [ ] Data audit sau migration không còn orphan/duplicate/out-of-range.
- [ ] Index/constraint definitions đúng.
- [ ] Sequence state sau import an toàn.
- [ ] Runtime role có grants cần thiết.
- [ ] Hibernate validate thành công trên schema đã migrate.
- [ ] App version cũ/mới tương thích trong thời gian rollout nếu cần.
- [ ] Rollback/forward-fix được diễn tập.

### 21.1. Migration không chỉ là DDL

Migration có thể thay đổi semantics của dữ liệu, defaults, triggers, indexes, RLS, grants và query performance. Kiểm tra cả data transformation và runtime behavior.

### 21.2. Upgrade tests

Tạo database theo schema release trước, seed dữ liệu cũ, chạy migration mới, rồi khởi động code mới. Đây là bằng chứng mạnh hơn việc chỉ chạy migration trên database rỗng.

## 22. Connection pool và database connectivity

- [ ] Pool implementation và version được xác định.
- [ ] Maximum pool size phù hợp database connection budget.
- [ ] Connection timeout hợp lý.
- [ ] Idle/max lifetime phù hợp môi trường DB/proxy.
- [ ] Leak detection/metrics được bật phù hợp.
- [ ] Connection validation/keepalive theo môi trường.
- [ ] Transaction không giữ connection lâu ngoài nhu cầu.
- [ ] Pool exhaustion được quan sát và cảnh báo.
- [ ] Database max connections đủ cho tổng pods/workers/jobs.

### 22.1. Tính tổng connection budget

Ví dụ có 8 pods, mỗi pod max pool 20:

~~~text
8 × 20 = 160 connections
~~~

Cộng thêm migration jobs, workers, admin tools và các services khác. Không cấu hình pool mỗi pod mà quên giới hạn toàn database.

### 22.2. Pool size không phải càng lớn càng tốt

Quá nhiều connections có thể làm DB contention tăng và throughput giảm. Đo queue time, active connections, DB CPU và latency trước khi tăng pool.

### 22.3. Leak detection

Nếu connection/transaction bị giữ quá lâu, kiểm tra long-running queries, network calls trong transaction, streaming chưa đóng và exception paths.

## 23. Timeout, retry và failure handling

- [ ] Query timeout cho thao tác có SLA rõ.
- [ ] Transaction timeout phù hợp workload.
- [ ] Lock timeout/deadlock được xử lý.
- [ ] Connection acquisition timeout được phân biệt với query timeout.
- [ ] Retry có giới hạn, backoff và jitter khi phù hợp.
- [ ] Retry không lặp side effects không idempotent.
- [ ] Database unavailable được map thành lỗi vận hành phù hợp.
- [ ] Không nuốt exception rồi trả success giả.
- [ ] Rollback state được xác nhận sau lỗi.

### 23.1. Phân loại lỗi

| Loại lỗi | Ví dụ | Cách xử lý thường gặp |
|---|---|---|
| Validation/domain | Status transition không hợp lệ | Trả lỗi nghiệp vụ |
| Constraint | Unique/FK/CHECK violation | Map theo constraint/business rule |
| Optimistic conflict | Version không còn mới | Báo conflict hoặc reload/resolve |
| Deadlock/serialization | Transaction bị abort | Retry toàn transaction nếu an toàn |
| Connection failure | DB/pool không truy cập được | Fail fast, circuit/alert theo kiến trúc |
| Query timeout | Query vượt thời hạn | Điều tra plan/lock/load, không retry vô hạn |

### 23.2. Không retry duplicate key như transient error

Unique violation thường biểu thị conflict hoặc duplicate command. Retry cùng payload ngay lập tức thường tạo cùng lỗi.

### 23.3. Không retry một phần transaction

Với transaction bị abort, retry toàn use case trong transaction mới. Không tiếp tục dùng EntityManager/connection ở trạng thái lỗi.

## 24. Observability: logs, metrics và tracing

- [ ] SQL logging có thể bật khi diagnostic.
- [ ] Bind parameter logging không lộ PII/secrets.
- [ ] Slow query logs/APM spans được thu thập.
- [ ] Query count hoặc N+1 detection có cách theo dõi.
- [ ] Connection pool metrics được dashboard.
- [ ] Transaction duration và rollback rate được đo.
- [ ] Lock waits/deadlocks được quan sát ở DB.
- [ ] Error rate theo SQLState/exception class được phân loại.
- [ ] Correlation ID liên kết request, service và database spans.
- [ ] Logs không ghi toàn bộ entity graph hoặc dữ liệu nhạy cảm.

### 24.1. Metric hữu ích

- Request latency p50/p95/p99.
- DB query duration.
- Queries per request.
- Connection acquire time.
- Active/idle/pending pool connections.
- Transaction duration.
- Rollback/deadlock/timeout count.
- Rows returned/affected nếu instrumentation có.
- Cache hit/miss/invalidation.

### 24.2. SQL logs trong production

Không bật bind parameter TRACE rộng rãi nếu có dữ liệu cá nhân, token, địa chỉ hoặc thông tin thanh toán. Ưu tiên APM/slow query logging và sampling có kiểm soát.

### 24.3. Correlation

Một request tạo Order nên có thể lần theo request ID tới service log, transaction/DB span, outbox event và consumer processing. Không cần log toàn bộ SQL values để đạt correlation.

## 25. Security của database connection và SQL

- [ ] Credentials lấy từ secret manager/environment phù hợp.
- [ ] App role có least privilege.
- [ ] Migration role tách khỏi runtime role nếu phù hợp.
- [ ] TLS/encryption theo chính sách môi trường.
- [ ] SQL parameters được bind, không nối user input.
- [ ] Dynamic table/column/order expressions được whitelist.
- [ ] Native SQL được review về tenant predicate và injection.
- [ ] RLS/permissions được test bằng đúng role.
- [ ] Credentials không nằm trong logs/test reports/repository.
- [ ] Database network access giới hạn theo environment.

### 25.1. Dynamic sort

Không bind column name bằng JDBC parameter. Nếu sort field đến từ request, map từ whitelist:

~~~java
Map<String, Sort> allowed = Map.of(
    "createdAt", Sort.by(DESC, "createdAt"),
    "orderNumber", Sort.by(ASC, "orderNumber")
);
~~~

Không ghép raw string từ client vào ORDER BY.

### 25.2. Runtime role

App không nên chạy bằng database superuser/owner nếu không cần. Test grants, sequence privileges, schema usage và RLS với role tương ứng production.

## 26. Data retention, deletion và privacy

- [ ] Quy tắc soft delete/hard delete được định nghĩa.
- [ ] Retention period và archival workflow rõ.
- [ ] Foreign key delete behavior phù hợp.
- [ ] PII fields có chính sách access/masking.
- [ ] Logs/traces không ghi dữ liệu nhạy cảm không cần thiết.
- [ ] Backup/restore và deletion obligations được xem xét.
- [ ] Cache và search indexes được invalidated khi dữ liệu bị xóa.
- [ ] Audit trail giữ đúng dữ liệu cần thiết và không lưu thừa.

### 26.1. Soft delete không tự bảo đảm privacy deletion

Nếu dữ liệu phải được xóa vật lý hoặc ẩn danh theo policy, chỉ set deleted_at có thể không đủ. Kiểm tra backup, replicas, caches, exports và downstream systems.

### 26.2. Foreign key và retention

Hard delete parent có thể bị FK chặn hoặc cascade xóa children. Xác định retention của từng bảng trước khi bật cascade.

## 27. Batch jobs, streaming và bulk processing

- [ ] Job có chunk size rõ.
- [ ] Persistence context không phình không giới hạn.
- [ ] Flush/clear được dùng đúng khi batch entity writes.
- [ ] JDBC batching được cấu hình/đo riêng.
- [ ] Read streaming có transaction/cursor lifecycle rõ.
- [ ] Lazy loads trong vòng lặp không tạo N+1.
- [ ] Job có checkpoint/resume/idempotency.
- [ ] Failure giữa batches không tạo trạng thái nửa vời ngoài contract.
- [ ] Job không giữ connection/transaction quá lâu.

### 27.1. Flush/clear theo chunk

~~~java
for (int i = 0; i < items.size(); i++) {
    entityManager.persist(map(items.get(i)));

    if ((i + 1) % 50 == 0) {
        entityManager.flush();
        entityManager.clear();
    }
}
~~~

Sau clear, mọi entity cũ detached. Không giữ references rồi tiếp tục sửa như thể chúng còn managed.

### 27.2. StatelessSession

Hibernate StatelessSession có semantics khác Session stateful: không có persistence context/dirty checking/cascade giống thông thường. Chỉ dùng khi hiểu rõ trade-offs và test riêng.

### 27.3. Job retry

Chunk retry cần idempotency hoặc checkpoint. Một batch có thể đã commit trước khi worker chết; retry không được tạo duplicate rows/side effects.

## 28. Test data và môi trường

- [ ] Test fixture phản ánh cardinality/dữ liệu thực.
- [ ] Test không phụ thuộc thứ tự chạy.
- [ ] Database/schema được cô lập giữa suites/parallel workers.
- [ ] Test transaction rollback được hiểu rõ.
- [ ] Migration test dùng schema sạch và schema cũ.
- [ ] H2 không được coi là thay thế production DB.
- [ ] Testcontainers image/version được pin.
- [ ] Runtime role và permissions được mô phỏng.
- [ ] Cache cold/warm được phân biệt khi benchmark.
- [ ] Dữ liệu test không chứa secrets/PII thật.

### 28.1. Test nhỏ có thể che cardinality

Hai Orders và hai Items không đủ để phát hiện N+1 hoặc row multiplication. Tạo dataset có 20–100 roots, số children không đồng đều và một số root có cardinality lớn.

### 28.2. Data skew

Multi-tenant application thường có tenant nhỏ và tenant lớn. Query plan với 10 rows có thể khác với 5 triệu rows. Include tenant lớn/representative in performance tests.

## 29. Performance acceptance criteria

- [ ] SLA p95/p99 được xác định cho endpoint/job.
- [ ] Query count có giới hạn hợp lý.
- [ ] Rows/bytes trả về không vượt mức cần thiết.
- [ ] Query plans được xem với dataset đại diện.
- [ ] Indexes không tạo write overhead không chấp nhận được.
- [ ] Pool wait time không chiếm phần lớn request latency.
- [ ] Heap/persistence context size được theo dõi cho graph lớn.
- [ ] Load test có concurrency tương ứng traffic dự kiến.
- [ ] Regression baseline được lưu cho query quan trọng.
- [ ] Có ngưỡng cảnh báo và owner xử lý.

### 29.1. Đo nhiều lớp

Một request chậm có thể do:

1. Chờ connection pool.
2. Chờ lock.
3. Database execution.
4. Network/result transfer.
5. Hibernate hydration/dirty checking.
6. DTO mapping/serialization.

Chỉ đo tổng request latency không cho biết bottleneck nằm ở đâu.

### 29.2. Đừng tối ưu chỉ theo query count

Một query trả hàng trăm nghìn rows có thể chậm hơn vài query nhỏ có chủ đích. Đo rows, bytes, DB time, app time và concurrency.

### 29.3. Regression threshold

Performance tests nên chạy ở môi trường đủ ổn định. Dùng p95/p99 và nhiều lượt chạy; không đặt một ngưỡng millisecond quá chặt trong unit test trên CI host biến động.

## 30. Deployment và rolling compatibility

- [ ] Migration được triển khai đúng thứ tự so với app version.
- [ ] Schema mới tương thích với app cũ trong thời gian rolling nếu cần.
- [ ] App mới có thể chạy trên schema đã migrate.
- [ ] Background workers/consumers cũng tương thích schema transition.
- [ ] Không có hai versions dùng generator/sequence không tương thích.
- [ ] Feature flag/traffic rollout có kế hoạch.
- [ ] Read/write paths có thể quan sát riêng.
- [ ] Có điều kiện dừng rollout và owner quyết định.
- [ ] Rollback app binary không làm schema mất khả năng đọc dữ liệu đã ghi.

### 30.1. Migration trước hay application trước?

Không có một thứ tự đúng cho mọi thay đổi. Với additive schema thường có thể migrate trước rồi deploy app. Với destructive rename/drop, cần expand–contract và nhiều release. Ghi rõ compatibility matrix.

### 30.2. Feature flag

Nếu thay query path hoặc read model, có thể bật theo phần trăm traffic/tenant. Theo dõi correctness, latency và error rate trước khi tăng rollout.

### 30.3. Consumer lag

Nếu outbox/event consumer chưa xử lý hết dữ liệu cũ, không xóa column/table mà consumer cũ vẫn cần.

## 31. Rollback và recovery

- [ ] Có thể rollback app version mà không mất dữ liệu mới.
- [ ] Migration destructive có recovery/forward-fix plan.
- [ ] Backup/restore point được xác định theo release risk.
- [ ] Có kế hoạch xử lý sequence/identifier state sau rollback.
- [ ] Có kế hoạch xử lý outbox/event đã publish.
- [ ] Cache invalidation có thể chạy lại.
- [ ] Data repair script được review và có dry-run.
- [ ] Có cách phát hiện partial rollout/mixed schema.

### 31.1. Rollback schema không phải lúc nào cũng an toàn

Nếu app mới đã ghi dữ liệu vào column/enum mới, rollback schema có thể làm mất thông tin. Forward-fix thường an toàn hơn rollback DDL. Quyết định phải dựa trên data compatibility.

### 31.2. Recovery script

Script sửa dữ liệu cần:

- Có điều kiện scope cụ thể.
- Có dry-run/report số rows ảnh hưởng.
- Có transaction/chunk strategy.
- Có backup/checkpoint.
- Có kiểm tra sau khi chạy.

## 32. Runbook và vận hành

- [ ] Dashboard database/pool/query có sẵn.
- [ ] Alert cho connection exhaustion, deadlocks, slow queries và error rate.
- [ ] Runbook xác định cách điều tra N+1, lock waits, pool leaks.
- [ ] Có owner/on-call cho database migration và incident.
- [ ] Có quy trình kill/cancel query dài được phê duyệt.
- [ ] Có hướng dẫn scale worker/pool có kiểm soát.
- [ ] Có quy trình restore và verify dữ liệu.
- [ ] Có cách xác định migration version đang chạy.
- [ ] Có cách kiểm tra app version và schema compatibility.

### 32.1. Diagnostic queries

Chuẩn bị query phù hợp database để xem active sessions, locks, long-running queries, sequence state và migration history. Chỉ chạy query có quyền và hiểu tác động trên production.

### 32.2. Không xử lý pool exhaustion bằng tăng pool ngay

Trước tiên xác định connection bị giữ bởi query chậm, transaction dài, streaming chưa đóng, lock wait hay traffic spike. Tăng pool khi DB đã quá tải có thể làm tình hình tệ hơn.

## 33. Checklist theo loại thay đổi

| Loại thay đổi | Các kiểm tra cần ưu tiên |
|---|---|
| Entity mới | Mapping, ID, constraints, indexes, migration, lifecycle |
| Association mới | Owning side, FK, cascade, fetch plan, orphan behavior |
| Repository query mới | Tenant scope, joins, N+1, count, pagination, plan |
| Native SQL | Physical names, parameter binding, vendor integration test, L1/cache |
| Bulk update/delete | Predicate, version, callbacks, clear/refresh, affected rows |
| Migration | Data audit, locks, compatibility, catalog, upgrade/rollback |
| Cache | Key scope, invalidation, staleness, serialization |
| Concurrency | @Version/locks, isolation, idempotency, retry |
| Batch job | Chunking, flush/clear, JDBC batching, resume, pool |
| Identifier change | Generator, optimizer, sequence state, rolling compatibility |
| Naming change | Physical names, migration, native SQL, external consumers |
| Multi-tenant change | Trusted context, composite FK, RLS, cache keys |

## 34. Mẫu ghi nhận quyết định trước release

Có thể ghi kết quả checklist theo mẫu:

~~~text
Feature:
Owner:
Release:
Database vendor/version:
Hibernate/Spring Boot version:
Migration version:

Mapping:
  Status: PASS / N/A / BLOCKED
  Evidence:

Transaction and lifecycle:
  Status:
  Evidence:

Query and performance:
  Status:
  Evidence:

Tenant/security:
  Status:
  Evidence:

Concurrency/cache:
  Status:
  Evidence:

Migration/upgrade:
  Status:
  Evidence:

Tests/CI:
  Status:
  Evidence:

Deployment/rollback:
  Status:
  Evidence:

Open risks:
Accepted by:
Review date:
Revisit condition:
~~~

### 34.1. Risk phải có phạm vi

Không ghi “performance sẽ xem sau”. Ghi endpoint nào, traffic limit nào, metric nào, người chịu trách nhiệm và ngày/điều kiện đánh giá lại.

### 34.2. Evidence có thể tái lập

Link tới test report, migration run, EXPLAIN output đã loại bỏ dữ liệu nhạy cảm hoặc dashboard panel. Người review phải có thể kiểm tra mà không cần tin vào lời xác nhận miệng.

## 35. Điều kiện tối thiểu để đưa phần truy cập Hibernate vào sử dụng

Một tính năng thường chưa sẵn sàng nếu còn một trong các vấn đề sau:

- Schema production không có migration tương ứng.
- Migration chưa chạy trên đúng database vendor/version.
- Entity mapping và physical schema không khớp.
- Transaction boundary chưa rõ hoặc rollback sai.
- Tenant/authorization predicate chưa được kiểm tra.
- Có query N+1 nghiêm trọng hoặc pagination collection fetch không kiểm soát.
- Constraint quan trọng chỉ được validate ở Java, không có database protection khi cần.
- Detached merge bỏ qua returned instance hoặc có nguy cơ null overwrite.
- Concurrency có thể tạo duplicate/lost update nhưng không có constraint/version/locking.
- Cache có thể trả dữ liệu tenant khác hoặc stale sau writes.
- Integration tests cần thiết chưa chạy.
- Không có kế hoạch rollback/recovery cho migration có rủi ro.

### 35.1. Không yêu cầu mọi feature phải có mọi loại test

Một lookup read-only đơn giản có thể không cần concurrency test riêng. Một workflow thanh toán hoặc cấp số hóa đơn cần kiểm tra sâu hơn. Chọn test theo rủi ro và invariant, ghi N/A có lý do.

### 35.2. Không dùng checklist để thay code review

Checklist giúp không quên nhóm rủi ro. Reviewer vẫn cần đọc mapping, query, migration, service logic và test code.

## 36. Bài thực hành tổng hợp

### Bài A — Chuẩn bị một aggregate mới

1. Tạo Order và OrderItem entities.
2. Chọn identifier strategy và sequence.
3. Khai báo owning/inverse relationships.
4. Tạo migration PK/FK/UNIQUE/CHECK/index.
5. Viết service transaction tạo aggregate.
6. Kiểm tra generated ID và persisted rows bằng SQL.
7. Chạy Testcontainers trên database production.

### Bài B — Thêm list endpoint

1. Xác định DTO fields cần thiết.
2. Viết query có organization predicate.
3. Chọn JOIN to-one và projection/count cho to-many.
4. Kiểm tra pagination/count query.
5. Đo query count và actual rows.
6. Kiểm tra EXPLAIN với data đại diện.
7. Test không có IDOR/cross-tenant access.

### Bài C — Thêm workflow cập nhật trạng thái

1. Nhận command DTO.
2. Load managed Order theo trusted scope.
3. Kiểm tra authorization và state transition.
4. Dùng @Version.
5. Commit update và outbox event cùng transaction.
6. Test stale update và duplicate command.
7. SQL độc lập xác nhận row/version/outbox.

### Bài D — Thêm soft delete

1. Chọn deleted_at semantics.
2. Tạo partial unique index nếu cần.
3. Cập nhật repository filters.
4. Xác định restore behavior.
5. Test native SQL/JDBC writers.
6. Kiểm tra cache invalidation.
7. Đối soát duplicate active business keys.

### Bài E — Nâng cấp Hibernate

1. Ghi lại version/dialect/generator/naming hiện tại.
2. Nâng dependency trên branch riêng.
3. Chạy migration từ schema cũ.
4. Kiểm tra sequence/optimizer và physical names.
5. Chạy repository/native SQL integration tests.
6. Kiểm tra generated SQL và schema catalog.
7. Test rolling compatibility/rollback nếu cần.

### Bài F — Kiểm tra production readiness

1. Đi qua toàn bộ checklist.
2. Gắn bằng chứng cho mỗi mục PASS.
3. Ghi rõ N/A và BLOCKED.
4. Xác định open risks và owner.
5. Chạy CI/DB integration/performance suites theo scope.
6. Diễn tập migration và recovery.
7. Chỉ bật traffic khi các điều kiện release đã được đáp ứng.

## 37. Checklist tổng hợp ngắn để review pull request

### Schema và mapping

- [ ] Entity/column/relationship đúng schema.
- [ ] Migration chạy trên DB production.
- [ ] PK/FK/UNIQUE/CHECK/NOT NULL đúng.
- [ ] Indexes và generator/naming strategy đã kiểm tra.

### Application và transaction

- [ ] Transaction boundary rõ.
- [ ] Managed/detached lifecycle đúng.
- [ ] Merge/save return value được dùng.
- [ ] Authorization/tenant scope được kiểm tra.
- [ ] Cascade/orphan removal có chủ đích.

### Query và performance

- [ ] Không có N+1 không kiểm soát.
- [ ] Fetch plan phù hợp cardinality.
- [ ] Pagination/count đúng.
- [ ] Query/rows/plan đã đo khi cần.
- [ ] Pool/timeout phù hợp workload.

### Consistency và security

- [ ] @Version/locking/idempotency phù hợp.
- [ ] Cache invalidation và tenant keys đúng.
- [ ] Events/outbox có consistency contract.
- [ ] SQL parameters bind an toàn.
- [ ] Runtime DB role có least privilege.

### Tests và operations

- [ ] Unit/repository/integration tests pass.
- [ ] Database-specific tests dùng đúng engine.
- [ ] Migration upgrade path được test.
- [ ] Logs/metrics/alerts có thể quan sát.
- [ ] Rollout/rollback/runbook rõ.

## 38. Tổng kết: chỉ đưa vào sử dụng khi có bằng chứng ở đúng tầng

~~~mermaid
flowchart TD
    A[Hibernate feature ready for review] --> B[Mapping + schema]
    B --> C[Transaction + lifecycle]
    C --> D[Query + performance]
    D --> E[Security + consistency]
    E --> F[Production DB tests]
    F --> G[Migration + rollout]
    G --> H[Observability + recovery]
    H --> I{Critical checks PASS?}
    I -->|Có| J[Release theo rollout plan]
    I -->|Không| K[Block / xử lý risk]
~~~

Những nguyên tắc cần nhớ:

1. **Một tính năng Hibernate không chỉ là entity và repository.** Nó còn bao gồm schema, transaction, security, query behavior, cache và vận hành.
2. **Mapping phải khớp migration và database thật.** Annotation không tự tạo bằng chứng rằng production schema đã đúng.
3. **Database constraints bảo vệ mọi writers.** Application validation cung cấp lỗi thân thiện nhưng không thay UNIQUE/FK/CHECK/NOT NULL khi invariants cần được enforce ở DB.
4. **Transaction boundary quyết định atomicity.** Xác định commit, rollback, propagation và side effects ngoài database.
5. **Managed entity được dirty-check; detached entity thì không.** Sau merge phải dùng managed result, còn command update thường nên load-then-update.
6. **Fetch plan phải theo use case và cardinality.** Kiểm tra N+1, row multiplication, pagination và DTO projection.
7. **Tenant isolation phải được kiểm tra ở mọi đường đọc/ghi.** ID không phải authorization; cache, jobs và RLS cũng cần scope.
8. **Concurrency cần constraint/version/locking/idempotency phù hợp.** Một test đơn luồng không chứng minh workflow an toàn dưới race.
9. **Cache và events có consistency contract riêng.** Invalidation/outbox/retry phải được kiểm tra cùng transaction behavior.
10. **Test trên đúng database khi behavior phụ thuộc vendor.** H2 không chứng minh PostgreSQL migrations, native SQL, locking hoặc query plans.
11. **Performance cần đo nhiều lớp.** Query count một mình không cho biết rows, bytes, DB time, hydration, pool waits và concurrency.
12. **Migration phải có upgrade và recovery plan.** Schema cũ, data cũ, rolling deployment và rollback đều là một phần của release.
13. **Observability phải có trước khi traffic tăng.** Logs, metrics, traces, alerts và runbook giúp phát hiện và xử lý vấn đề.
14. **PASS cần bằng chứng, N/A cần lý do, BLOCKED cần owner.** Checklist là công cụ ra quyết định release có thể kiểm tra lại.

Phần truy cập Hibernate sẵn sàng khi nhóm hiểu dữ liệu đi qua những tầng nào, các invariant được bảo vệ ở đâu và có bằng chứng cho những rủi ro quan trọng. Hãy dùng checklist theo phạm vi thay đổi, gắn từng mục với test/migration/metric cụ thể và ghi nhận các rủi ro còn lại trước khi bật traffic. Điều đó giúp release có thể dự đoán, quan sát và khôi phục khi hành vi production khác kỳ vọng.
