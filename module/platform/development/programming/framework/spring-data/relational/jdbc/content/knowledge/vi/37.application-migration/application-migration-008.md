# So sánh hành vi, SQL và hiệu năng trước và sau chuyển đổi

Khi chuyển một ứng dụng từ JPA/Hibernate sang **Spring Data Relational JDBC**, việc so sánh hiệu năng không thể chỉ dựa vào thời gian một repository method hoặc số câu SQL được log. Hai framework có thể tạo ra SQL khác nhau, tải object theo cách khác nhau và thực hiện các thao tác ghi khác nhau. Một thay đổi có thể giảm round-trip nhưng tăng số hàng trả về; một thay đổi khác có thể giảm object allocation nhưng làm transaction giữ connection lâu hơn.

So sánh có ý nghĩa phải trả lời được ba câu hỏi:

1. **Hành vi có tương đương không?** Kết quả nghiệp vụ, transaction, locking, cascade/ownership, generated ID và lỗi phải giữ đúng contract.
2. **SQL đã thay đổi thế nào?** Số statement, query shape, bind parameter, rows, joins, write statements và execution plan.
3. **Tổng chi phí thay đổi ra sao?** Latency, throughput, database CPU/I/O, network payload, JVM allocation/GC, lock contention và connection pool.

Hãy xây dựng baseline trước chuyển đổi, chạy cùng workload sau chuyển đổi trên cùng điều kiện dữ liệu/hạ tầng, rồi phân tích từng khác biệt. Không kết luận Spring Data JDBC nhanh hơn hoặc chậm hơn chỉ vì nó phát ít hoặc nhiều câu SQL hơn.

## 1. Xác định baseline trước khi thay đổi

Trước khi sửa persistence implementation, ghi lại hành vi hiện tại của ứng dụng JPA/Hibernate. Baseline phải đại diện cho workload thật, không chỉ một test có một aggregate nhỏ.

Với mỗi use case, ghi:

- Entry point và input.
- Số aggregate/root được đọc hoặc ghi.
- Số child trung bình và phân bố lớn nhất.
- Quan hệ to-one/to-many được truy cập.
- Các field thực sự được trả về cho caller.
- Transaction boundary, propagation và isolation.
- Có optimistic/pessimistic locking hay không.
- Số request đồng thời và tần suất use case.
- Kết quả nghiệp vụ và side effect cần có.
- SQL statements, bind types/values đã mask và thứ tự thực thi.
- Latency, throughput và database/JVM resource.

Ví dụ workload:

| Use case | Dữ liệu | Hành vi cần giữ |
|---|---|---|
| Xem chi tiết đơn hàng | 1 root, 0–30 lines | Root và lines đầy đủ, đúng thứ tự |
| Trang danh sách đơn | 50 roots, customer name và totals | 50 DTO đúng sort/page, không tải toàn aggregate |
| Cập nhật trạng thái | 1 root | Chỉ đổi trạng thái nghiệp vụ, giữ các cột khác |
| Thêm dòng hàng | 1 root, 1 child mới | Child liên kết đúng root, tổng tiền đúng |
| Xóa đơn | 1 root, nhiều owned rows | Xóa/soft-delete đúng contract và không xóa aggregate khác |
| Tìm đơn theo khách hàng | 1.000+ roots | Filter, sort và pagination chính xác |
| Batch import | 5.000 rows/chunk | Không mất ID, không tạo duplicate, transaction boundary rõ |

Không dùng một workload tổng hợp duy nhất cho mọi use case. Một màn hình danh sách, một command cập nhật aggregate và một batch job có mục tiêu hiệu năng khác nhau.

## 2. Xác nhận tính tương đương nghiệp vụ trước khi benchmark

Nếu kết quả nghiệp vụ khác nhau, số đo hiệu năng không còn so sánh cùng một công việc.

Kiểm tra các behavior mà Hibernate có thể đã tự cung cấp:

- Dirty checking và thời điểm flush.
- Cascade persist/merge/remove và orphan removal.
- Lazy loading và fetch strategy.
- Identity map/persistence context.
- Optimistic locking và version increments.
- Entity callbacks/listeners và auditing.
- Generated IDs, sequence và database defaults.
- Transaction rollback, isolation và propagation.
- Null handling, converter, enum và timestamp semantics.
- Thứ tự collection và pagination.
- Soft delete, trigger và FK actions.

Với Spring Data JDBC, object không được quản lý bởi persistence context. Code phải gọi save tường minh; owned entities được lưu theo aggregate; reference đến aggregate khác không cascade; không có lazy proxy. Những khác biệt này cần được chuyển thành test trước khi đo tốc độ.

### Bảng parity

| Behavior | Baseline JPA | Kết quả cần xác nhận ở JDBC |
|---|---|---|
| Thay đổi field | Dirty checking khi entity managed | Chỉ persist khi gọi save hoặc DML tường minh |
| Thêm child | Cascade/relationship mapping | Child thuộc aggregate và được lưu cùng root |
| Bỏ child | orphanRemoval nếu được cấu hình | Owned collection update xử lý row đúng |
| Reference đến Customer | Association/lazy proxy | ID/AggregateReference, query riêng khi cần |
| Version | Optimistic lock khi flush | @Version và failure khi version stale |
| Callback | JPA lifecycle listener | EntityCallback/lifecycle event tương ứng |
| Read-only DTO | JPQL projection/entity graph | SQL projection/RowMapper/read model |
| Rollback | EntityManager và transaction manager | Repository/JdbcTemplate cùng transaction |

Không benchmark một đường JDBC chưa thực hiện cùng business validation hoặc auditing với đường JPA rồi coi thời gian thấp hơn là cải thiện.

## 3. Thu thập SQL từ Hibernate và Spring Data JDBC

Cần thu thập SQL ở cả hai implementation bằng một phương pháp có thể so sánh. Tối thiểu phải có statement, thứ tự, thời gian, số rows và loại operation. Khi cần chẩn đoán bind parameter, dùng instrumentation có kiểm soát và mask dữ liệu.

### Hibernate SQL logging

Với Hibernate 6, có thể bật:

~~~yaml
logging:
  level:
    org.hibernate.SQL: DEBUG
    org.hibernate.orm.jdbc.bind: TRACE
~~~

- org.hibernate.SQL ghi SQL được Hibernate thực thi.
- org.hibernate.orm.jdbc.bind có thể ghi parameter binding chi tiết.

Logger bind có thể làm lộ dữ liệu nhạy cảm. Chỉ bật trong local/test hoặc thời gian điều tra có kiểm soát; mask giá trị trước khi chia sẻ.

Hibernate statistics có thể cung cấp thêm số liệu như entity load/fetch, collection fetch, query execution và cache hits. Bật statistics trong môi trường đo khi cần; không mặc định bật chi tiết ở production nếu chưa đánh giá overhead.

### Spring Data JDBC SQL logging

Spring Data JDBC thực thi SQL qua Spring JDBC. Bật:

~~~yaml
logging:
  level:
    org.springframework.jdbc: DEBUG
~~~

Logger này giúp nhìn statement và thứ tự thực thi. Nếu cần bind values, rows hoặc thời gian chính xác hơn, dùng datasource-proxy, P6Spy hoặc instrumentation JDBC chung cho cả hai phiên bản.

### Dùng cùng một công cụ capture

Một cách so sánh tốt là đặt datasource instrumentation ở cùng vị trí cho cả Hibernate và Spring Data JDBC. Ghi nhận:

- SQL normalized/fingerprint.
- Operation type: SELECT/INSERT/UPDATE/DELETE.
- Bind parameter types và giá trị giả đã mask.
- Query duration.
- Rows returned hoặc update count.
- Connection/transaction/request correlation ID.
- Exception, SQLState và vendor error code.

Không chỉ copy log text rồi đếm dòng. Một số log có thể chứa statement prepare, bind và execute riêng; một số statement có thể được batch. Cần đếm execution thực tế.

## 4. Chuẩn hóa môi trường để so sánh công bằng

Baseline và phiên bản mới phải chạy trên điều kiện tương đương:

| Điều kiện | Cần giữ ổn định |
|---|---|
| Database | Cùng engine và major/minor version |
| JDBC driver | Cùng version nếu có thể |
| Schema | Cùng DDL, index, constraints và triggers |
| Dataset | Cùng số hàng, phân bố, NULL và cardinality |
| Database statistics | Analyze/statistics ở trạng thái tương đương |
| Hardware | CPU, RAM, disk và network |
| Connection pool | Max pool size, min idle, timeout |
| Transaction | Isolation, timeout và boundary |
| Workload | Request mix, concurrency và payload |
| Cache state | Warm/cold cache được định nghĩa rõ |
| JVM | JDK, heap, GC, container CPU/memory limits |
| Observability | Cùng instrumentation và sampling |

Không chạy hai benchmark cùng lúc trên cùng database nếu chúng cạnh tranh CPU/I/O/locks. Chạy theo thứ tự hoặc tách database instance tương đương.

### Dataset phải có phân bố thực tế

Không chỉ tạo 100 orders với đúng 2 lines mỗi order. Hãy mô phỏng:

- Nhiều root không có child.
- Root có một child.
- Root có số child trung bình.
- Một số root có collection rất lớn.
- Giá trị status/filter phân bố lệch.
- Hot keys được nhiều request cập nhật.
- Timestamp trùng nhau.
- NULL/duplicate/legacy values nếu hệ thống có.
- Dữ liệu lớn đủ để index và query plan có ý nghĩa.

Cardinality lệch thường làm query plan và JOIN behavior khác đáng kể so với fixture đồng đều.

## 5. Đo nhiều lớp, không chỉ query count

Các chỉ số tối thiểu:

| Metric | Ý nghĩa |
|---|---|
| Request latency p50 | Thời gian điển hình |
| p95/p99 latency | Đuôi phân phối và trải nghiệm khi tải |
| Throughput | Số request/operation hoàn tất mỗi giây |
| Error rate | Tỷ lệ lỗi SQL, timeout, conflict và rollback |
| SQL statement count | Số lần execute statement |
| Total DB time | Tổng thời gian database xử lý |
| Rows returned/updated | Khối lượng dữ liệu thực tế |
| Bytes transferred | Chi phí network và decode |
| DB CPU/buffer reads | Chi phí query engine và I/O |
| JVM CPU | Chi phí application và mapping |
| Heap allocation/GC | Chi phí materialize object graph |
| Connection pool wait/active | Áp lực lên connection pool |
| Lock wait/deadlocks | Contention khi nhiều transaction |
| Batch size/round-trips | Hiệu quả batch write |

Một câu SQL duy nhất có thể chậm hơn 10 câu SQL có index tốt nếu nó JOIN nhiều collection và trả về hàng nghìn dòng trùng. Ngược lại, 100 round-trip nhỏ có thể tốn latency mạng dù mỗi query rất nhanh.

**Số query là tín hiệu để điều tra, không phải thước đo cuối cùng.**

## 6. So sánh đường đọc aggregate

### JPA/Hibernate

Một repository find có thể tải root trước. Nếu code truy cập collection lazy, Hibernate có thể phát thêm SELECT:

~~~sql
SELECT id, customer_id, status, created_at
FROM purchase_order
WHERE id = ?;

SELECT id, order_id, product_id, quantity
FROM order_line
WHERE order_id = ?;
~~~

Nếu tải nhiều root và truy cập collection trong vòng lặp, có thể xuất hiện N+1:

~~~text
1 query lấy purchase_order
N query lấy order_line theo từng order_id
~~~

JPA có thể giảm query bằng fetch join, entity graph hoặc batch fetching. Nhưng fetch join nhiều collection có thể nhân số hàng và tạo duplicate root rows cần xử lý.

### Spring Data JDBC

Spring Data JDBC tải aggregate theo mapping. Cách mặc định có thể phát query root và query cho owned collections. Không có lazy proxy; collection được xử lý trong quá trình load aggregate.

Single Query Loading từ Spring Data Relational 3.2 có thể tải aggregate bằng một query khi mapping, dialect và repository method đủ điều kiện. Tính năng hiện hành vẫn experimental và có giới hạn; không áp dụng cho mọi derived/@Query method hay mọi aggregate.

### Cách so sánh đúng

- Dùng cùng ID/filter và cùng aggregate shape.
- So sánh số statement, rows, bytes và total DB time.
- Kiểm tra aggregate có nested collection/reference/embedded mapping không.
- Đo object allocation và GC khi materialize nhiều child.
- Kiểm tra SQL thực tế, không chỉ nhìn flag Single Query Loading.
- So sánh với JPA fetch plan hiện đang dùng, không so với một JPA path cố tình để N+1.

Nếu use case chỉ cần summary, không nên benchmark load full aggregate JDBC với projection JPA hoặc ngược lại. Hai đường phải trả cùng dữ liệu và có cùng semantics.

## 7. So sánh projection và read model

Một trang danh sách có thể chỉ cần order ID, status, customer name và tổng tiền. JPA có thể dùng DTO projection/JPQL. Spring Data JDBC có thể dùng @Query với custom RowMapper hoặc repository fragment với NamedParameterJdbcTemplate.

SQL có thể có dạng:

~~~sql
SELECT
    po.id,
    po.status,
    c.name AS customer_name,
    COUNT(line.id) AS line_count,
    COALESCE(SUM(line.quantity * line.unit_price), 0) AS total_amount
FROM purchase_order po
JOIN customer c ON c.id = po.customer_id
LEFT JOIN order_line line ON line.order_id = po.id
WHERE po.status = :status
GROUP BY po.id, po.status, c.name
ORDER BY po.created_at DESC, po.id DESC;
~~~

Đo các yếu tố:

- Số cột thực sự được SELECT.
- Rows trả về.
- CPU cho JOIN/GROUP BY.
- Index sử dụng.
- DTO mapping allocation.
- Count query và pagination.
- Có vô tình tải thêm collection qua aggregate mapping không.

Projection có thể cải thiện mạnh nếu trước đây ứng dụng tải toàn bộ entity graph chỉ để hiển thị vài field. Nhưng đó là thay đổi read model, không phải so sánh trực tiếp hai ORM/persistence framework trên cùng một thao tác.

## 8. So sánh JOIN và collection cardinality

JOIN to-one thường không làm tăng số rows root nếu FK/unique đúng. JOIN to-many tạo một row cho mỗi child. JOIN hai collection độc lập có thể nhân số rows.

Ví dụ một order có 5 lines, 3 payments và 4 shipments. JOIN cả ba collection có thể tạo tới 5 × 3 × 4 = 60 rows cho một root.

~~~mermaid
flowchart TD
    A["Một PurchaseOrder"] --> B["5 OrderLine"]
    A --> C["3 Payment"]
    A --> D["4 Shipment"]
    B --> E["JOIN ba collection"]
    C --> E
    D --> E
    E --> F["Tối đa 60 rows"]
~~~

Khi so sánh JPA fetch join với SQL JDBC, đo:

- Result rows sau JOIN.
- Root/child columns bị lặp.
- Bytes trả về.
- CPU và memory để deduplicate.
- Thời gian ResultSet mapping.
- COUNT/SUM có bị nhân đôi hay không.

Có thể aggregate mỗi collection trong subquery/CTE rồi JOIN kết quả một row mỗi root. Hoặc dùng query riêng có index. Đừng ép tất cả collection vào một câu JOIN chỉ để đạt query count thấp.

## 9. So sánh đường ghi: dirty checking và aggregate save

Đây thường là nơi hai framework khác nhau rõ nhất.

### JPA dirty checking

Nếu entity đang managed và chỉ một field thay đổi, Hibernate thường có thể phát một UPDATE cho những cột cần thay đổi, tùy dynamic update/configuration:

~~~sql
UPDATE purchase_order
SET status = ?
WHERE id = ?;
~~~

Khi entity có version, SQL có thể thêm điều kiện version và tăng version.

### Spring Data JDBC save

Spring Data JDBC không dirty-check object. Repository save được gọi tường minh và lưu aggregate theo mapping. Root có thể được UPDATE, còn owned collection có thể cần nhiều statement để đồng bộ trạng thái child.

Ví dụ shape có thể gồm:

~~~sql
UPDATE purchase_order
SET customer_id = ?, status = ?, created_at = ?, version = ?
WHERE id = ? AND version = ?;

DELETE FROM order_line
WHERE order_id = ?;

INSERT INTO order_line (...);
INSERT INTO order_line (...);
~~~

Đây là hình dạng minh họa, không phải cam kết SQL cố định cho mọi version/mapping. Hãy capture SQL thực tế của ứng dụng đang dùng.

### Điều cần đo ở write path

- Số INSERT/UPDATE/DELETE.
- Rows affected.
- Child rows có bị delete/reinsert không.
- Trigger/audit events được kích hoạt bao nhiêu lần.
- Generated ID có thay đổi không.
- FK và unique constraint có làm write thất bại không.
- Lock duration và transaction duration.
- Version increments và optimistic conflict rate.
- Log/CDC volume.
- Tổng latency và throughput khi nhiều request ghi đồng thời.

Nếu aggregate có hàng trăm child và chỉ một field root thay đổi, chiến lược ghi child có thể chi phối chi phí. Hãy xem xét aggregate size, write frequency và ranh giới aggregate trước khi kết luận.

## 10. So sánh batch và bulk operations

Hibernate có JDBC batching cho một số insert/update/delete; hiệu quả phụ thuộc mapping, ID generation, flush mode, batch size và driver. Spring Data JDBC cũng dùng JDBC operations và có thể có đường batch tùy API/phiên bản, nhưng không nên giả định hai framework gom statement giống nhau.

Đo:

- Số round-trip thực tế.
- Số statement trong mỗi batch.
- Batch size.
- Generated key retrieval.
- Transaction size và rollback cost.
- Lock duration.
- Memory dùng để giữ aggregate/batch.
- Throughput khi tăng chunk size.

Một batch lớn giảm round-trip nhưng giữ connection/locks lâu và tăng rollback cost. Chunk nhỏ giảm thời gian mỗi transaction nhưng có thể làm thay đổi atomicity: chunk đã commit không rollback khi chunk sau thất bại.

Không benchmark batch bằng cách bỏ qua validation hoặc callback ở một phiên bản nhưng giữ lại ở phiên bản kia. Giữ cùng semantics hoặc ghi rõ khác biệt.

## 11. Transaction, locking và concurrency

Hai framework có thể chạy SQL khác nhau dù cùng dùng @Transactional.

So sánh:

- Transaction boundary thực tế.
- Isolation level.
- Số connection được giữ.
- Lock mode và thứ tự lấy lock.
- Thời gian từ lock acquisition đến commit.
- Deadlock và lock timeout.
- Optimistic locking failure.
- Retry behavior.
- Tỷ lệ transaction rollback.

JPA có thể trì hoãn SQL đến flush; Spring Data JDBC thực thi statement khi repository/template được gọi. Điều này có thể làm lỗi constraint xuất hiện ở thời điểm khác nhau dù transaction cuối cùng vẫn rollback.

Khi nhiều request cập nhật cùng aggregate, đo throughput và conflict rate. Spring Data JDBC dùng @Version cho optimistic locking; nếu đường ghi trực tiếp SQL không tăng version đúng cách, so sánh sẽ không còn tương đương.

Đừng benchmark chỉ với một thread. Một thiết kế nhanh ở concurrency 1 có thể tệ ở concurrency 32 do lock contention hoặc connection pool saturation.

## 12. Phân tích execution plan của SQL trước và sau

Với query chậm, lấy execution plan trên cùng database và parameter đại diện.

PostgreSQL:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, status, created_at
FROM purchase_order
WHERE status = 'PAID'
ORDER BY created_at DESC, id DESC
LIMIT 50;
~~~

Đối chiếu:

- Estimated rows và actual rows.
- Sequential scan/index scan.
- Join order và join algorithm.
- Sort/memory/disk spill.
- Buffer hits/reads.
- Rows removed by filter.
- Total execution time.
- Index selectivity và statistics.

EXPLAIN ANALYZE thực thi câu query thật. Cẩn thận với câu lệnh ghi; chỉ dùng SELECT phù hợp hoặc transaction rollback trên database thử nghiệm. Trên production, dùng phương pháp quan sát có kiểm soát.

Nếu SQL shape thay đổi, so sánh cả query plan lẫn payload. Một query mới có thể dùng index tốt hơn nhưng trả nhiều dữ liệu hơn; tổng latency của application có thể vẫn tăng do mapping.

## 13. Thiết kế benchmark có thể lặp lại

Một benchmark tốt cần được định nghĩa trước:

### Workload

- Tỷ lệ đọc/ghi theo production.
- Request mix theo use case.
- Page size và offset/deep pagination.
- Aggregate size distribution.
- Concurrency và think time.
- Tỷ lệ key nóng.
- Payload và response size.

### Chạy benchmark

1. Khởi động database và ứng dụng với cùng resource limit.
2. Nạp dataset giống nhau hoặc restore cùng snapshot.
3. Chạy migration/schema đúng phiên bản.
4. Warm up JVM, connection pool và query plan/cache.
5. Chạy một khoảng ổn định đủ dài.
6. Ghi latency percentile, throughput, error rate và resource.
7. Reset database/state trước lần chạy kế tiếp nếu workload ghi làm thay đổi dữ liệu.
8. Chạy lặp nhiều lần và báo variance.
9. Chạy cả concurrency thấp và cao.
10. Lưu SQL trace và query plan của các operation chính.

Không lấy kết quả của một lần chạy ngắn làm kết luận. Benchmark cần thời gian warm-up và steady-state; kết quả nên kèm environment và phiên bản chính xác.

### Công cụ phù hợp

- JMeter, Gatling hoặc k6 cho HTTP/load workload.
- Micrometer/Actuator và tracing cho request/transaction latency.
- datasource-proxy/P6Spy cho SQL execution và bind observation.
- Hibernate Statistics cho entity/query/cache metrics.
- Database monitoring và EXPLAIN cho execution plan.
- JFR/profiler cho CPU, allocation và GC.
- Connection pool metrics cho active, idle và pending threads.

JMH phù hợp cho microbenchmark thuần JVM như converter/mapping function, nhưng không thay thế integration/load test cho database round-trip và transaction.

## 14. Đọc kết quả bằng ví dụ

Giả sử benchmark cùng use case trả 50 order summaries:

| Metric | JPA baseline | JDBC candidate |
|---|---:|---:|
| Request p50 | 45 ms | 32 ms |
| Request p95 | 110 ms | 96 ms |
| SQL statements | 151 | 1 |
| Rows returned | 500 | 50 |
| DB CPU/request | 8 ms | 11 ms |
| JVM allocation/request | 2.4 MB | 0.8 MB |

Các con số trên chỉ minh họa cách phân tích, không phải kết quả mặc định của framework.

Diễn giải:

- JDBC giảm statement count và rows nhờ query projection tổng hợp.
- Database CPU tăng nhẹ vì GROUP BY, nhưng network payload và JVM allocation giảm.
- p50/p95 cải thiện trong workload này.
- Cần kiểm tra concurrency và query plan trước khi triển khai rộng.

Một kết quả khác có thể ngược lại: một SQL JOIN lớn trả 20.000 rows và làm database CPU tăng. Khi đó, số statement thấp hơn không có nghĩa hiệu năng tốt hơn.

## 15. Kiểm tra regression và tính đúng đắn của dữ liệu

Benchmark phải đi kèm regression test. Với mỗi use case, assert:

- Cùng số aggregate/result DTO.
- Cùng ID và business values.
- Cùng thứ tự collection khi thứ tự là contract.
- Cùng filter/sort/page semantics.
- Cùng generated IDs/default values.
- Cùng transaction rollback behavior.
- Cùng optimistic lock guarantees.
- Không tạo duplicate hoặc orphan rows.
- Không phát side effect thừa qua trigger/callback.
- Không làm mất audit/version/timestamp.

Với write path, so sánh database state trước/sau bằng query hoặc snapshot. Không chỉ assert object trả về vì object trong memory có thể đúng trong khi database có side effect ngoài ý muốn.

## 16. Shadow read và canary rollout

Khi muốn so sánh trên traffic gần production, có thể triển khai shadow read có kiểm soát:

1. Request chính tiếp tục dùng implementation cũ.
2. Một bản đọc mới chạy song song trên cùng snapshot/replica phù hợp.
3. So sánh result ở mức business fields đã chọn.
4. Ghi metric latency và SQL cho implementation mới.
5. Mask dữ liệu nhạy cảm trong diff.
6. Không để shadow path ghi dữ liệu hoặc gây side effect.
7. Giới hạn tỷ lệ traffic để tránh tăng tải database ngoài dự kiến.

Shadow read phải có giới hạn concurrency và timeout. Không chạy hai truy vấn nặng cho mọi request nếu điều đó làm quá tải database.

Sau khi parity ổn định, canary một nhóm nhỏ use case/tenant. Theo dõi error rate, latency, DB CPU, lock wait, pool saturation và data discrepancy. Tăng dần phạm vi khi số liệu ổn định.

## 17. Quyết định giữ, tối ưu hay rollback

Không có một ngưỡng chung cho mọi ứng dụng. Quyết định theo SLO và mức độ rủi ro:

- Giữ thay đổi nếu parity đạt, latency/throughput đáp ứng SLO và resource không tăng quá mức.
- Tối ưu query/index nếu bottleneck là plan hoặc payload.
- Tối ưu aggregate boundary nếu save một aggregate lớn gây nhiều write không cần thiết.
- Dùng projection cho read model nếu đang materialize object graph không cần.
- Dùng Single Query Loading khi aggregate/dialect/method đủ điều kiện và đo thực tế chứng minh lợi ích.
- Rollback/cutover lại nếu xuất hiện data mismatch, constraint errors, deadlocks, tail latency hoặc pool saturation vượt giới hạn.

Trước rollout, xác định cách quay về implementation cũ, tương thích schema và cách xử lý dữ liệu đã ghi bởi phiên bản mới. Không rollback code nếu schema mới đã phá vỡ contract của code cũ; cần migration backward-compatible.

## 18. Những sai lầm thường gặp khi so sánh

| Sai lầm | Vì sao kết luận sai | Cách làm đúng |
|---|---|---|
| Chỉ đếm số SQL | Một query có thể trả nhiều rows hơn nhiều query nhỏ | Đo rows, bytes, DB time và latency |
| So sánh JPA N+1 với JDBC Single Query Loading | Baseline không được tối ưu tương đương | Tối ưu cả hai theo best-known configuration |
| So sánh full aggregate với DTO | Hai bên làm lượng công việc khác nhau | Giữ cùng result shape và semantics |
| Chỉ benchmark một aggregate nhỏ | Không phản ánh cardinality production | Dùng phân bố dữ liệu thật |
| Chạy benchmark trên H2 rồi suy ra PostgreSQL | Dialect, driver và plan khác nhau | Dùng database production-compatible |
| Không warm up JVM/database | Kết quả bị nhiễu bởi startup/cache | Định nghĩa warm-up và steady-state |
| Chỉ đo p50 | Bỏ qua tail latency | Đo p50/p95/p99 và error rate |
| Bỏ qua write side effects | Trigger/audit/child rows có thể tăng chi phí | Capture SQL và so sánh database state |
| Bỏ qua concurrency | Không thấy lock/pool bottleneck | Load test ở mức concurrency đại diện |
| Tăng connection pool để che query chậm | Có thể làm database quá tải hơn | Tối ưu query/transaction và đo pool |
| Không kiểm tra version/callback | Nhanh hơn nhưng mất correctness | Regression test behavior trước benchmark |
| Chạy hai benchmark đồng thời | Hai phiên bản cạnh tranh tài nguyên | Chạy tuần tự hoặc trên instance tương đương |

## 19. Quy trình so sánh trước và sau chuyển đổi

1. **Chọn use case:** ưu tiên đường đọc/ghi có volume hoặc rủi ro cao.
2. **Ghi baseline semantics:** input, output, side effects, transaction và locking.
3. **Capture JPA SQL:** statement, bind types, rows, duration và query plan.
4. **Tạo workload đại diện:** dataset, cardinality, skew, concurrency và page size.
5. **Chuyển implementation JDBC:** giữ nguyên contract, schema và business behavior.
6. **Capture JDBC SQL:** dùng cùng instrumentation và database environment.
7. **So sánh query shape:** JOIN, collection loading, write statements, batching và pagination.
8. **Chạy correctness tests:** result parity, constraints, version, rollback và data diff.
9. **Chạy benchmark:** warm-up, steady-state, p50/p95/p99, throughput, CPU, rows/bytes và JVM.
10. **Phân tích execution plan:** xác định scan, join, sort, index và lock bottleneck.
11. **Tối ưu có mục tiêu:** projection, index, query shape, aggregate boundary hoặc batch size.
12. **Canary và theo dõi:** shadow read/read-only trước, sau đó mở write path theo giai đoạn.
13. **Quyết định:** giữ, tối ưu thêm hoặc rollback theo SLO và data correctness.

### Bảng quyết định nhanh

| Dấu hiệu sau chuyển đổi | Hướng điều tra |
|---|---|
| SQL count giảm nhưng latency tăng | Rows/bytes, JOIN cardinality, DB CPU và mapping |
| Read path giảm allocation | Xác nhận DTO chứa đủ dữ liệu và không bỏ validation |
| Write path tăng DELETE/INSERT | Owned collection save strategy, trigger, FK và aggregate size |
| p50 tốt nhưng p99 xấu | Lock wait, pool wait, GC, query skew và hot keys |
| DB CPU giảm nhưng JVM CPU tăng | ResultSet/object mapping, conversion và aggregation ở application |
| N+1 biến mất | Kiểm tra payload và query plan; không dừng ở query count |
| Optimistic conflicts tăng | Version handling, stale object và write concurrency |
| Test pass nhưng production chậm | Dataset/cardinality, index, plan, hardware và concurrency khác |
| JPA/JDBC cho kết quả khác | Transaction timing, callbacks, defaults, nulls, sort và lifecycle |
| Rollout tạo data discrepancy | Dừng mở rộng, xác định writer/schema/version và khôi phục theo kế hoạch |

**Điểm cốt lõi:** so sánh trước/sau chuyển đổi bằng cùng nghiệp vụ, cùng dữ liệu và cùng môi trường. Capture SQL của cả Hibernate và Spring Data JDBC, rồi đo query count cùng rows/bytes, latency percentile, throughput, database resource, JVM allocation, locks và connection pool. Xác nhận correctness trước khi benchmark, tối ưu theo bottleneck đã đo và rollout theo giai đoạn có đường rollback.

## Tài liệu tham khảo chính thức

- [Spring Data Relational — Persisting Entities and Loading Aggregates](https://docs.spring.io/spring-data/relational/reference/jdbc/entity-persistence.html): aggregate loading, update behavior và Single Query Loading.
- [Spring Data Relational — Query Methods](https://docs.spring.io/spring-data/relational/reference/jdbc/query-methods.html): derived queries, @Query, RowMapper, ResultSetExtractor và pagination.
- [Spring Data Relational — Transactionality](https://docs.spring.io/spring-data/relational/reference/jdbc/transactions.html): transaction boundaries và repository/service behavior.
- [Hibernate ORM User Guide — Statistics](https://docs.jboss.org/hibernate/orm/current/userguide/html_single/Hibernate_User_Guide.html): Hibernate statistics, SQL, fetching và persistence context.
- [Hibernate ORM — Logging](https://docs.jboss.org/hibernate/orm/current/logging/logging.html): SQL and JDBC bind logging categories.
- [Spring Boot — Logging](https://docs.spring.io/spring-boot/reference/features/logging.html): logger configuration and levels.
- [PostgreSQL — EXPLAIN](https://www.postgresql.org/docs/current/using-explain.html): execution plan, actual rows and query costs.
- [PostgreSQL — Monitoring Database Activity](https://www.postgresql.org/docs/current/monitoring-stats.html): database activity and resource monitoring.
- [Testcontainers — Database Modules](https://java.testcontainers.org/modules/databases/): integration testing against real database engines.

