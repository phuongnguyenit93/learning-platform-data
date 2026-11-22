# Đọc execution plan và thiết kế chỉ mục theo truy vấn thực tế

Trong Spring Data JPA, repository method có thể sinh SQL gồm WHERE, JOIN, ORDER BY và truy vấn phụ. Hiệu năng phụ thuộc SQL thật, phân bố dữ liệu, statistics, index hiện có và plan optimizer chọn. Thiết kế index phải bắt đầu từ **truy vấn thật và execution plan**. Index giảm dữ liệu đọc nhưng tốn dung lượng và làm chậm INSERT, UPDATE, DELETE.

## 1. Repository đến SQL

Spring Data tạo truy vấn từ derived method, @Query, Criteria hoặc Specification; Hibernate chuyển thành SQL theo dialect. Ví dụ:

~~~java
List<RecentOrderView>
findTop20ByTenantIdAndStatusOrderByCreatedAtDesc(
        Long tenantId, OrderStatus status);
~~~

SQL tương đương:

~~~sql
SELECT id, created_at, total_amount FROM purchase_order
WHERE tenant_id = ? AND status = ?
ORDER BY created_at DESC LIMIT 20;
~~~

Lấy SQL và bind parameter thật bằng Hibernate logger: Hibernate 6 dùng org.hibernate.SQL và org.hibernate.orm.jdbc.bind; Hibernate 5 thường dùng org.hibernate.type.descriptor.sql.BasicBinder. Kiểm tra projection, lazy loading và N+1; bảo vệ parameter trong log.

## 2. Access path và plan

- **Sequential/table scan:** đọc toàn bảng; có thể tốt với bảng nhỏ hoặc truy vấn lấy nhiều dòng.
- **Index scan / index-only scan:** tìm qua index; index-only còn phụ thuộc visibility map và heap fetch.
- **Bitmap scan:** PostgreSQL kết hợp vị trí index rồi đọc heap theo nhóm.
- **Nested loop join:** tốt khi phía ngoài nhỏ và phía trong có index; đắt nếu lặp nhiều.
- **Hash/merge join:** lựa chọn khác tùy số dòng, bộ nhớ và thứ tự dữ liệu.
- **Sort, hash/group aggregate:** xử lý ORDER BY/GROUP BY, có thể tốn bộ nhớ.

MySQL EXPLAIN type gồm const, eq_ref, ref, range, index, ALL. ALL là table scan; index là quét toàn index, không phải lookup chọn lọc. Xem possible_keys, key, rows, filtered và Extra. Using filesort không khẳng định ghi ra đĩa.

## 3. PostgreSQL/MySQL EXPLAIN

PostgreSQL dùng EXPLAIN cho estimated plan và EXPLAIN (ANALYZE, BUFFERS) cho actual plan. MySQL dùng EXPLAIN/FORMAT=JSON; MySQL 8.0.18+ có EXPLAIN ANALYZE cho SELECT. **ANALYZE thực thi truy vấn**; DML có thể đổi dữ liệu. Chỉ thử trong môi trường an toàn; rollback không hoàn tác mọi sequence, trigger hoặc tác động ngoài database.

So sánh estimated rows với actual rows. Sai lệch lớn có thể làm optimizer chọn join/sort kém. PostgreSQL cost là đơn vị nội bộ, không phải millisecond; xem actual time, loops, buffers và Rows Removed by Filter. Actual time thường là trung bình mỗi loop. MySQL có rows, filtered và actual rows/loops.

## 4. Cardinality, selectivity và statistics

Cardinality là số giá trị phân biệt; selectivity là tỷ lệ dòng thỏa điều kiện, càng nhỏ càng chọn lọc. Index đơn trên status ít hữu ích nếu mỗi trạng thái chiếm nhiều dòng; tenant_id có thể chọn lọc hơn. Kết hợp nhiều cột có thể tốt hơn một cột đơn.

PostgreSQL dùng ANALYZE/autoanalyze và extended statistics; MySQL dùng ANALYZE TABLE và histogram tùy phiên bản. ANALYZE cập nhật thống kê planner; VACUUM xử lý tuple chết. Kiểm tra statistics trước khi thêm index.

## 5. Composite, covering, partial và expression index

Ví dụ composite B-tree:

~~~sql
CREATE INDEX idx_order_tenant_status_created
ON purchase_order (tenant_id, status, created_at DESC);
~~~

Equality thường đứng trước range/sort. Leftmost prefix của (tenant_id, status, created_at) là tenant_id; tenant_id + status; rồi cả ba. Truy vấn chỉ lọc status thường không tận dụng tốt index này. PostgreSQL B-tree có thể quét ngược; MySQL 8 hỗ trợ descending index.

Covering index chứa cột lọc/trả về; PostgreSQL hỗ trợ INCLUDE, MySQL thường thêm cột vào index. Partial index chỉ chứa dòng thỏa predicate; PostgreSQL hỗ trợ, MySQL không có tương đương trực tiếp. Expression/functional index hỗ trợ lower(email); PostgreSQL hỗ trợ expression index, MySQL 8.0.13+ hỗ trợ functional key parts.

## 6. Sargability, JOIN, GROUP BY và ORDER BY

Predicate sargable giúp tìm qua index. Hàm/cast trên cột có thể cản index. Thay DATE(created_at) = ... bằng khoảng từ đầu ngày đến trước đầu ngày kế tiếp thường thân thiện hơn với B-tree. Tránh implicit cast. LIKE '%text%' thường không dùng B-tree để tìm chuỗi con; cân nhắc trigram/full-text search.

Kiểm tra index trên cột JOIN/foreign key; database không nhất thiết tự tạo index cho mọi foreign key. Nested loop tốt khi phía ngoài nhỏ; hash/merge join tùy cardinality. ORDER BY có thể cần sort; GROUP BY có thể cần sort/hash aggregate. Đọc Sort, HashAggregate, GroupAggregate, Using filesort và Using temporary cùng actual rows/time/buffers.

## 7. Chi phí, workflow và xác thực

INSERT thêm entry index; UPDATE cột indexed có thể đổi entry; DELETE cập nhật index. Index rộng chiếm page, I/O, cache; index trùng lặp tăng chi phí ghi. Kiểm tra primary key, unique constraint và index hiện có; đánh giá cả workload đọc/ghi.

Workflow: entity PurchaseOrder có tenantId, status, createdAt, totalAmount, id; OrderStatus là enum. Tạo projection RecentOrderView có getter id/createdAt/totalAmount; repository dùng method ở phần 1; service gọi method trong @Transactional(readOnly = true). Đặt class/interface riêng trong Spring Boot có spring-boot-starter-data-jpa và driver. Gọi qua endpoint hoặc integration test với dữ liệu đại diện; thu thập SQL/bind values, thay dấu hỏi bằng giá trị thật rồi chạy EXPLAIN trên đúng PostgreSQL/MySQL.

Nếu plan phải đọc nhiều dòng trước LIMIT, thử index tenant/status/createdAt bằng Flyway/Liquibase; chạy lại cùng query/parameter rồi so sánh plan, thời gian và buffers/reads. JPA @Index phù hợp index đơn giản; migration phù hợp covering/partial/expression index. PostgreSQL CREATE INDEX CONCURRENTLY có giới hạn, không chạy trong transaction block thường; MySQL algorithm/lock tùy engine/phiên bản.

OFFSET lớn có thể bỏ qua nhiều dòng; keyset pagination theo createdAt/id có thể tốt hơn. Index không giải quyết N+1; cân nhắc projection, fetch join, EntityGraph hoặc batch fetching.

Xác thực bằng dữ liệu gần production và nhiều bind values; cập nhật statistics; chạy EXPLAIN trước; chỉ dùng EXPLAIN ANALYZE khi chấp nhận truy vấn thực thi. Không chạy DML ANALYZE trên dữ liệu thật nếu chưa có môi trường an toàn. So sánh estimated/actual rows, loops, join/sort, buffers; benchmark endpoint và INSERT/UPDATE/DELETE; bảo vệ bind values trong log.

Execution plan biến tối ưu database từ phỏng đoán thành quyết định dựa trên bằng chứng. Lấy SQL Hibernate sinh ra, đọc plan PostgreSQL/MySQL, thiết kế index cho mẫu truy vấn rồi đo lại.
