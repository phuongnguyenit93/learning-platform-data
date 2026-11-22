# Khảo sát kiến trúc, cơ sở dữ liệu và luồng thay đổi hiện tại

## 1. Vì sao phải khảo sát trước khi chuyển đổi kiến trúc?

Khi một hệ thống microservices đã vận hành nhiều năm, sơ đồ kiến trúc ban đầu thường không còn phản ánh đầy đủ thực tế. Một service có thể đã được tách thêm worker, một database có thể đang được nhiều ứng dụng truy cập, một API cũ vẫn được sử dụng bởi consumer không ai nhớ, và một luồng thay đổi tưởng như chỉ deploy một service thực chất cần phối hợp nhiều nhóm.

Nếu bắt đầu chuyển đổi từ sơ đồ cũ hoặc giả định của một vài cá nhân, nhóm có thể:
- Bỏ sót dependency và làm gián đoạn luồng nghiệp vụ.
- Tách service nhưng vô tình chuyển dữ liệu đang được nhiều ứng dụng cùng ghi.
- Chọn sai ranh giới transaction hoặc aggregate.
- Tạo migration không tương thích với phiên bản ứng dụng đang chạy.
- Đánh giá thấp thời gian đồng bộ, cutover và rollback.
- Làm mất khả năng truy vết vì log, event và dữ liệu không có định danh thống nhất.
- Đưa thêm nền tảng hoặc công nghệ mới trong khi nguyên nhân chính nằm ở ownership, quy trình release hoặc dữ liệu.

**Khảo sát kiến trúc hiện trạng (current-state architecture assessment)** là hoạt động thu thập, đối chiếu và mô tả bằng chứng về cách hệ thống đang được xây dựng, kết nối, lưu trữ, triển khai và thay đổi. Kết quả phải cho biết **điều gì đang tồn tại, nó hoạt động ra sao, ai sở hữu, rủi ro ở đâu và mức độ tin cậy của từng kết luận**.

Bài này tập trung ba lát cắt liên kết:
1. **Kiến trúc:** thành phần, ranh giới service, giao tiếp, phụ thuộc, runtime và hạ tầng.
2. **Cơ sở dữ liệu:** nguồn dữ liệu, schema, ownership, truy cập, transaction, migration, replication và backup.
3. **Luồng thay đổi:** từ yêu cầu tới code, kiểm thử, phát hành, migration, triển khai, quan sát và xử lý rollback.

Khảo sát hiện trạng là nền tảng cho quyết định chuyển đổi, không phải bước hợp thức hóa một thiết kế mục tiêu đã chọn sẵn. Nhóm cần ghi nhận cả những điểm kiến trúc đang hoạt động tốt, các ngoại lệ có chủ đích và những khoảng trống chưa đủ bằng chứng.

## 2. Mục tiêu và câu hỏi cần trả lời

Một cuộc khảo sát đủ tốt phải giúp người ra quyết định trả lời được:

- Hệ thống phục vụ những năng lực nghiệp vụ nào và luồng nào quan trọng nhất?
- Có những ứng dụng, service, worker, job, gateway và tài nguyên nào đang chạy?
- Mỗi thành phần do ai sở hữu về code, dữ liệu, vận hành và quyết định thay đổi?
- Service giao tiếp bằng HTTP, gRPC, event, file hay truy cập trực tiếp database?
- Ranh giới service có khớp ownership dữ liệu và năng lực nghiệp vụ không?
- Database nào là nguồn sự thật cho từng loại dữ liệu? Có bảng nào bị nhiều service cùng đọc/ghi?
- Một giao dịch nghiệp vụ đi qua những database, broker và external provider nào?
- Thay đổi schema, API, event và cấu hình được phát hành theo thứ tự nào?
- Có thể deploy độc lập, rollback độc lập và phục hồi dữ liệu tới mức nào?
- Điểm nghẽn, rủi ro bảo mật, vận hành, hiệu năng và tổ chức nằm ở đâu?
- Kết luận nào đã được xác minh, kết luận nào chỉ là giả thuyết?

Nên xác định rõ **phạm vi khảo sát** trước khi thu thập. Ví dụ, khảo sát toàn bộ nền tảng commerce có thể quá rộng; đợt đầu có thể giới hạn vào luồng checkout từ lúc người dùng xác nhận giỏ hàng đến lúc đơn được tạo, thanh toán và giữ tồn kho. Phạm vi cần ghi rõ hệ thống, môi trường, khoảng thời gian dữ liệu và những thành phần ngoài phạm vi.

## 3. Nguyên tắc khảo sát dựa trên bằng chứng

### 3.1. Phân biệt kiến trúc được khai báo và kiến trúc đang chạy

Có ít nhất bốn loại bằng chứng:

| Loại bằng chứng | Ví dụ | Điều nó chứng minh |
| --- | --- | --- |
| Khai báo | README, C4 diagram, ADR, API spec | Thiết kế hoặc ý định được ghi lại |
| Mã nguồn | Repository, dependency, SQL, config | Hành vi được triển khai trong code |
| Runtime | Trace, network flow, Kubernetes, DB sessions | Những gì đang thực sự chạy trong thời điểm quan sát |
| Vận hành | Pipeline, incident, change ticket, runbook | Cách hệ thống được thay đổi và xử lý trong thực tế |

Một sơ đồ nói order-service chỉ gọi inventory-service chưa đủ nếu trace cho thấy order-service còn query trực tiếp bảng inventory. Một file OpenAPI có thể cũ hơn endpoint production. Một pipeline có bước migration chưa chắc mọi lần deploy đều chạy theo cùng đường.

Khi các nguồn khác nhau, ghi nhận discrepancy thay vì tự chọn nguồn thuận tiện. Cần nêu thời điểm quan sát, môi trường và cách xác minh.

### 3.2. Không suy luận từ tên gọi

Tên `customer-service` không chứng minh service sở hữu dữ liệu khách hàng. Tên `shared-db` không chứng minh database được dùng chung đúng thiết kế. Một repository có thể chứa nhiều deployable unit; một deployment có thể chạy nhiều process hoặc sidecar.

Phải xác minh qua code, schema, query, deployment và người chịu trách nhiệm.

### 3.3. Không biến khảo sát thành thiết kế lại

Trong giai đoạn hiện trạng, mục tiêu là mô tả **đang có gì và vấn đề được chứng minh ở đâu**. Có thể ghi nhận phương án tiềm năng hoặc câu hỏi cần quyết định, nhưng không âm thầm thay kiến trúc, schema hay quy trình đang chạy. Việc thay đổi production trong lúc khảo sát có thể làm mất baseline và tăng rủi ro.

### 3.4. Ghi độ tin cậy và khoảng trống

Mỗi kết luận nên có:
- Bằng chứng và nguồn.
- Môi trường/phạm vi quan sát.
- Ngày hoặc commit/release được kiểm tra.
- Người xác nhận nếu cần.
- Mức độ tin cậy: đã xác minh, có bằng chứng một phần, giả thuyết, chưa biết.
- Tác động nếu giả thuyết sai.
- Bước tiếp theo để xác minh.

Không dùng từ “chắc chắn” cho một kết luận chỉ dựa trên một lần grep code hoặc một cuộc phỏng vấn.

## 4. Xác định phạm vi nghiệp vụ và luồng quan trọng

Bắt đầu từ **business capability** và hành trình người dùng thay vì chỉ liệt kê repository. Ví dụ một nền tảng thương mại điện tử có:
- Tìm kiếm và xem sản phẩm.
- Quản lý giá và khuyến mãi.
- Giỏ hàng và checkout.
- Đặt giữ tồn kho.
- Thanh toán.
- Xử lý đơn, giao hàng và hoàn tiền.
- Thông báo.
- Đối soát và báo cáo.

Chọn các luồng đại diện theo mức độ quan trọng, tần suất và rủi ro. Một luồng checkout có thể bao gồm nhiều synchronous call và event bất đồng bộ; một luồng báo cáo có thể là batch job chạy hàng đêm. Khảo sát chỉ một API CRUD sẽ không phát hiện được coupling qua event, job hoặc dữ liệu dẫn xuất.

### 4.1. Xác định điểm bắt đầu và kết thúc

Với từng luồng, ghi:
- Actor hoặc hệ thống khởi phát.
- Request/event đầu tiên.
- Kết quả nghiệp vụ được coi là hoàn thành.
- Các trạng thái trung gian.
- Side effects như charge payment, reserve stock, send notification.
- Điều kiện thất bại, retry và compensation.
- SLI/SLO liên quan nếu đã có.

Ví dụ `POST /checkout` trả HTTP 202 chưa chắc đơn đã hoàn tất. Cần theo dõi tới trạng thái order được tạo, payment được xác nhận hoặc saga kết thúc theo định nghĩa nghiệp vụ.

### 4.2. Chọn luồng theo rủi ro

Ưu tiên khảo sát:
- Luồng tạo/ghi dữ liệu quan trọng.
- Luồng có thanh toán, quyền truy cập hoặc dữ liệu nhạy cảm.
- Luồng có nhiều service và external provider.
- Luồng thường xuyên xảy ra incident.
- Luồng có deploy/migration phức tạp.
- Luồng mà nhóm đang dự định tách hoặc thay thế.

Không nhất thiết khảo sát mọi edge case ngay trong đợt đầu. Hãy ghi phạm vi coverage để tránh người đọc hiểu nhầm một vài luồng đã đại diện toàn hệ thống.

## 5. Kiểm kê thành phần kỹ thuật

Một inventory hữu ích bao gồm:

| Nhóm | Đối tượng cần tìm | Thông tin cần ghi |
| --- | --- | --- |
| Entry point | Web/mobile API, gateway, ingress, webhook | Owner, route, auth, traffic, environment |
| Service | HTTP/gRPC application, worker | Purpose, repository, runtime, team, deployment |
| Scheduled job | Cron, batch, data pipeline | Schedule, trigger, idempotency, output |
| Event infrastructure | Broker, topic, queue, consumer group | Producer, consumer, schema, retention, lag |
| Data store | SQL/NoSQL, cache, search, object store | Owner, schema, access, backup, retention |
| Platform | Kubernetes, service mesh, DNS, IAM | Team, policy, shared dependency |
| External system | Payment, email, identity, logistics | Contract, quota, timeout, fallback |
| Delivery | CI, CD, registry, GitOps | Build, test, release, migration, rollback |
| Observability | Logs, metrics, traces, alerting | Coverage, retention, owner, dashboard |

Mỗi đối tượng nên có định danh ổn định và trạng thái lifecycle. Ghi rõ môi trường: dev/test/staging/production, region, cluster, namespace. Tránh gộp mọi deployment của cùng service thành một record không thể phân biệt.

### 5.1. Tìm từ nhiều nguồn

- SCM/repository inventory và build files.
- Dockerfile, Helm chart, Kubernetes manifest, Terraform/IaC.
- CI/CD pipeline và release history.
- API gateway routes, service mesh, DNS và network policy.
- Database catalog, schema, grants, query logs.
- Broker topics, consumer groups, schema registry.
- Observability dashboards, traces, alerts và incidents.
- Team directory, on-call schedule, ownership catalog.
- Phỏng vấn service owner, platform, DBA, SRE và product.

Không nên dùng một nguồn đơn lẻ làm toàn bộ inventory. Runtime inventory có thể thấy workload tạm thời nhưng thiếu business purpose; repository scan có thể thấy service đã retired.

## 6. Vẽ bản đồ kiến trúc hiện trạng

Dùng nhiều mức trừu tượng thay vì một sơ đồ quá lớn.

### 6.1. System context

Thể hiện:
- Người dùng/actor.
- Hệ thống đang khảo sát.
- External systems/providers.
- Các trust boundary quan trọng.
- Luồng dữ liệu/hoạt động nghiệp vụ ở mức tổng quát.

### 6.2. Container/component view

Thể hiện application/service, worker, gateway, database, broker, cache và các đường giao tiếp. Ghi protocol, hướng gọi, sync/async và môi trường.

### 6.3. Deployment/runtime view

Thể hiện cluster, region, namespace, replica, load balancer, database topology và shared infrastructure. Phân biệt logical component với deployment cụ thể.

Ví dụ sơ đồ hiện trạng minh họa:

~~~mermaid
flowchart LR
    U[Web / Mobile] --> GW[API Gateway]
    GW --> O[order-service]
    O --> I[inventory-service]
    O --> P[payment-service]
    O --> DB[(orders DB)]
    I --> IDB[(inventory DB)]
    P --> PDB[(payment DB)]
    O --> B[(Kafka)]
    B --> N[notification-worker]
    N --> X[Email/SMS provider]
~~~

Sơ đồ này chỉ là mẫu, không phải khẳng định về hệ thống thực. Khi khảo sát, mỗi mũi tên cần có bằng chứng: route config, code call, trace, event schema hoặc owner xác nhận.

### 6.4. Ghi rõ điểm không biết

Nếu chưa xác định được một kết nối, có thể vẽ nét đứt và ghi `unverified`. Không lấp khoảng trống bằng một mũi tên suy đoán chỉ để sơ đồ trông hoàn chỉnh.

### 6.5. Định nghĩa notation thống nhất

Ví dụ:
- Mũi tên liền: synchronous call.
- Mũi tên đứt: event/message.
- Viền đôi: external provider.
- Hình trụ: datastore.
- Nhãn màu/legend: production, staging, shared platform.
- Dấu hỏi: dependency chưa xác minh.

Legend phải giải thích rõ; không dựa vào màu đơn lẻ vì tài liệu có thể được in hoặc xem ở chế độ không màu.

## 7. Khảo sát ranh giới microservice và ownership

Ranh giới service hiện tại có thể dựa trên domain, team, lịch sử tách monolith hoặc giới hạn kỹ thuật. Cần xác minh bằng dữ liệu và hành vi.

Với mỗi service, ghi:
- Business capability và các use case chính.
- Aggregate/entity nó sở hữu.
- Bảng/database mà nó ghi.
- API/event nó cung cấp và tiêu thụ.
- Những service có quyền gọi hoặc truy vấn dữ liệu.
- Team chịu trách nhiệm code, schema và production.
- Điều kiện release và dependency bắt buộc.
- Các chức năng có thể degrade khi dependency lỗi.

### 7.1. Dấu hiệu ranh giới chưa rõ

- Nhiều service cùng ghi một bảng nghiệp vụ.
- Service gọi trực tiếp database của service khác.
- Một service chỉ là proxy không có ownership hoặc logic rõ.
- Deploy một service buộc phải deploy nhiều consumer cùng lúc.
- Một schema change yêu cầu chỉnh nhiều repository.
- Logic nghiệp vụ được sao chép ở nhiều nơi và cho kết quả khác nhau.
- Team không xác định được ai chịu trách nhiệm cuối cùng khi dữ liệu sai.
- Shared library chứa domain logic thay đổi thường xuyên, tạo coupling release.

Đây là dấu hiệu cần điều tra, không phải kết luận tự động rằng service phải được gộp hoặc tách. Có thể tồn tại lý do hợp lệ như read model, migration tạm thời hoặc bounded context được chia sẻ theo hợp đồng.

### 7.2. Ma trận service–data ownership

| Service | Database/schema | Read | Write | Owner dữ liệu | Ghi chú |
| --- | --- | --- | --- | --- | --- |
| order-service | orders | Có | Có | Order team | Nguồn sự thật đơn hàng |
| checkout-service | orders | Có | Có? | Chưa rõ | Cần xác minh quyền ghi |
| reporting-worker | orders replica | Có | Không | Order team | Read-only/reporting |
| payment-service | payments | Có | Có | Payment team | Độc lập với order DB |

Các dòng trên chỉ là ví dụ minh họa. Khi khảo sát thật, cần kiểm tra DB grants, query logs, stored procedures, ORM mappings và code path. Bảng mapping này thường phát hiện coupling dữ liệu rõ hơn một sơ đồ service thuần túy.

## 8. Khảo sát giao tiếp và dependency

### 8.1. Synchronous communication

Với HTTP/gRPC, ghi:
- Caller và callee.
- API/operation.
- AuthN/AuthZ.
- Timeout/deadline.
- Retry, backoff, circuit breaker.
- Payload/response size.
- Traffic rate, p95/p99, error rate.
- Version compatibility.
- Criticality: bắt buộc hay tùy chọn.
- Fallback/degraded behavior.

Một call có thể nằm trong critical path checkout dù chỉ mất 20 ms ở baseline; nếu nó fail thì toàn giao dịch không hoàn tất. Cần phân biệt latency trung bình và tail latency, đồng thời xem retry amplification.

### 8.2. Asynchronous communication

Với broker/event, ghi:
- Producer và owner event.
- Topic/queue, partition, retention.
- Schema/version và compatibility policy.
- Consumer group và owner.
- Delivery semantics, retry, DLQ.
- Ordering scope và idempotency.
- Consumer lag, processing time, event age.
- Replay/backfill process.
- Data classification và retention.

Event được publish không đồng nghĩa consumer đã xử lý. Luồng nghiệp vụ có thể kết thúc sau một event chain; cần xác định điều kiện hoàn tất và khả năng đối soát.

### 8.3. Hidden coupling

Một số coupling không hiện rõ trong API graph:
- Dùng chung database schema.
- Dùng chung Redis key namespace.
- Cùng ghi object storage prefix.
- Cùng đọc một topic nhưng không có contract.
- Dùng chung config table hoặc feature flag.
- Dùng chung IAM role/secret.
- Chia sẻ library có logic nghiệp vụ.
- Dùng chung batch file hoặc SFTP.
- Trigger nhau qua cron/job scheduler.

Khảo sát phải bao gồm các đường này, vì tách API mà bỏ sót data/event/identity coupling sẽ không tạo được tính độc lập.

## 9. Khảo sát cơ sở dữ liệu: inventory trước, đánh giá sau

Với mỗi database hoặc datastore, lập hồ sơ:
- Engine và version.
- Environment/region/cluster/instance.
- Database/schema/table count và dung lượng.
- Owner kỹ thuật và owner nghiệp vụ.
- Data classification, residency, retention.
- Read/write client và service account.
- Connection pool, max connection, workload.
- Backup, PITR, replication, failover.
- Migration tool và schema version.
- Encryption, key management và access audit.
- Monitoring, slow query, lock/deadlock.
- Restore/DR test và kết quả gần nhất.

Đừng chỉ liệt kê database server. Một service có thể dùng nhiều schema, read replica, Redis, search index và object storage; một database cluster có thể chứa dữ liệu của nhiều bounded context.

### 9.1. Phân loại datastore

| Loại | Mục đích thường gặp | Điều cần khảo sát |
| --- | --- | --- |
| Relational DB | Transaction và quan hệ dữ liệu | Schema, FK, isolation, locks, migrations |
| Document DB | Aggregate/document linh hoạt | Document ownership, indexes, consistency |
| Key-value/cache | Cache, session, lookup | TTL, invalidation, persistence, key ownership |
| Search engine | Full-text, filtering | Source data, indexing lag, reindex |
| Message broker | Event/job | Retention, ordering, replay, consumer offsets |
| Object storage | File, artifact, export | Access, lifecycle, versioning, backup |
| Data warehouse | Analytics/report | ETL lineage, freshness, cross-domain access |
| Vector store | Embedding/retrieval | Tenant filter, provenance, deletion, rebuild |

### 9.2. Phân biệt nguồn sự thật và bản sao dẫn xuất

Với mỗi loại dữ liệu, ghi:
- System of record.
- Read replica.
- Cache.
- Search projection.
- Analytics copy.
- Event log.
- Export/backup.

Một bản search index có thể là read model được tái tạo từ source; một file export có thể trở thành dữ liệu lưu trữ có nghĩa vụ retention. Không gán mọi bản sao là “cache có thể xóa” nếu có quy trình nghiệp vụ đang dựa vào nó.

## 10. Đọc schema và quan hệ dữ liệu

Khảo sát schema nhằm hiểu **mô hình nghiệp vụ được lưu như thế nào** và service nào có quyền thay đổi.

### 10.1. Entity, key và quan hệ

Với từng bảng quan trọng, ghi:
- Primary key và loại định danh.
- Foreign keys và quan hệ.
- Unique constraints.
- Nullable/default/check constraints.
- Index và partition.
- Created/updated timestamps, version columns.
- Soft-delete/status/lifecycle.
- Tenant/customer scope nếu multi-tenant.
- Data classification và retention.

Không nên chỉ lấy ERD tự động rồi kết luận. Cần đối chiếu schema với query thật và logic application. Một foreign key có thể không tồn tại dù code giả định quan hệ; một cột `status` có thể chứa nhiều giá trị không được tài liệu hóa.

### 10.2. Composite key và ownership

Nếu dữ liệu multi-tenant, cần xác định tenant key có nằm trong PK/FK/index hay chỉ ở application layer. Nếu order của tenant A có thể tham chiếu customer tenant B do thiếu composite constraint, đó là rủi ro dữ liệu và authorization.

### 10.3. Denormalization và dữ liệu lặp

Ghi nhận:
- Field được copy từ service khác.
- Snapshot dữ liệu tại thời điểm transaction.
- Counter/materialized aggregate.
- Search document.
- Cache value.
- Event payload chứa projection.
- Quy trình đồng bộ và phát hiện drift.

Dữ liệu lặp không mặc định sai. Snapshot giá tại thời điểm đặt hàng là cần thiết để giữ lịch sử giao dịch; vấn đề là ai chịu trách nhiệm và quy tắc cập nhật/đối soát có rõ không.

### 10.4. Constraints và integrity

Đánh giá xem tính toàn vẹn được enforce ở đâu:
- Database constraints.
- Application validation.
- Domain event contracts.
- Batch reconciliation.
- Manual operations.

Nếu mọi ràng buộc chỉ nằm ở application code nhưng nhiều service cùng ghi DB, khả năng dữ liệu sai tăng. Nếu constraints quá chặt làm migration online khó, cần ghi nhận trade-off và phương án triển khai, không tùy tiện bỏ constraint.

## 11. Khảo sát query và workload

Schema đẹp chưa chứng minh database đáp ứng tải. Cần chọn các query trọng yếu theo business flow:
- Query có traffic cao.
- Query latency p95/p99 lớn.
- Query có nhiều rows scanned hoặc sort.
- Query chạy trong transaction dài.
- Query thường xuyên timeout/lock.
- Query báo cáo hoặc batch có thể gây noisy neighbor.
- Query được gọi qua nhiều service.

Thu thập:
- Execution plan và index usage.
- Rows estimated vs actual.
- Buffer/cache hit và disk reads.
- CPU, I/O, lock wait.
- Connection pool active/idle/pending.
- Transaction duration.
- Deadlock/retry.
- Query frequency và thời điểm peak.
- Payload size và pagination.

Không chạy truy vấn khám phá nặng trên production mà chưa đánh giá tác động và quyền. Dùng read replica, snapshot hoặc query plan an toàn khi phù hợp. Nếu cần EXPLAIN ANALYZE có thực thi query, phải hiểu side effect và resource cost; không dùng trên câu lệnh ghi tùy tiện.

### 11.1. Phân biệt nguyên nhân chậm

| Triệu chứng | Hướng điều tra |
| --- | --- |
| DB CPU cao | Query plan, scans, joins, concurrency, missing/unused index |
| Connection pending tăng | Pool sizing, leak, transaction dài, DB connection cap |
| Lock wait cao | Transaction overlap, hot row, DDL, lock ordering |
| I/O latency cao | Storage, checkpoint, index bloat, large scans |
| Query nhanh nhưng API chậm | Network, thread pool, serialization, downstream calls |
| Replica lag tăng | Write rate, replication bandwidth, long transactions |
| Storage tăng nhanh | Retention, indexes, duplicated data, audit/log volume |

Không điều chỉnh pool size hoặc thêm index chỉ dựa vào một panel. Cần liên kết trace/API và DB metrics để xác định bottleneck thực.

## 12. Transaction boundary và tính nhất quán dữ liệu

Một giao dịch nghiệp vụ có thể ghi vào nhiều bảng trong một database, hoặc đi qua nhiều service/database. Khảo sát cần ghi rõ:
- Transaction bắt đầu/kết thúc ở đâu.
- Isolation level và locking strategy.
- Có optimistic/pessimistic concurrency không.
- Idempotency key được dùng ở bước nào.
- Outbox/inbox có tồn tại không.
- Có distributed transaction/2PC không.
- Saga/compensation được thiết kế ra sao.
- Khi một bước thất bại, state nào đã commit và state nào chưa.

### 12.1. Ví dụ checkout

~~~text
Client
  → checkout-service
  → pricing-service: xác minh giá
  → inventory-service: reserve hàng
  → payment-service: authorize
  → order-service: tạo đơn
  → Kafka: OrderCreated
  → notification-worker
~~~

Đây là flow minh họa. Khi khảo sát thật, phải xác định thứ tự thực tế, synchronous hay asynchronous, mỗi thao tác commit ở database nào và điều kiện hoàn tất.

Nếu inventory reserve thành công nhưng payment thất bại, hệ thống có release reservation không? Nếu payment authorize thành công nhưng order DB timeout, retry có thể charge lặp không? Nếu event gửi notification trùng, consumer có idempotent không? Đây là câu hỏi về transaction semantics và recovery, không thể trả lời bằng sơ đồ API đơn thuần.

### 12.2. Transactional outbox và event consistency

Nếu service commit DB rồi publish event riêng, có cửa sổ:
- DB commit thành công nhưng publish thất bại.
- Event publish thành công nhưng DB rollback.
- Worker publish lại event gây duplicate.

Outbox ghi event cùng transaction với business record, relay phát sau commit. Cần khảo sát outbox table, polling/CDC, retry, idempotency và event ordering. Không mặc định “Kafka exactly once” giải quyết transaction giữa database và mọi external side effect.

## 13. Data ownership và truy cập chéo database

Trong microservices, mục tiêu thường là service sở hữu dữ liệu nghiệp vụ của mình. Hiện trạng có thể khác:
- Nhiều service cùng query một schema.
- Một service ghi bảng do service khác tạo.
- Shared database chứa nhiều domain.
- Stored procedure được gọi bởi nhiều ứng dụng.
- Reporting service truy vấn trực tiếp OLTP.
- Batch job cập nhật dữ liệu ngoài service owner.

Lập ma trận **service × database/schema/table × operation**:
- Read.
- Insert.
- Update.
- Delete.
- DDL/migration.
- Export/restore.
- Admin access.

Phân biệt quyền cấp database với hành vi thực tế. Một service account có quyền UPDATE toàn schema không chứng minh code đang dùng quyền đó, nhưng đó là blast radius nếu credential bị lộ. Query logs có thể cho thấy truy cập thực nhưng không nhất thiết nhận diện đầy đủ mọi code path.

### 13.1. Các dấu hiệu coupling dữ liệu

- Service A cần biết cấu trúc bảng nội bộ của B.
- B đổi column và phải deploy A ngay.
- Hai service cùng sở hữu status field.
- Một batch job cập nhật bảng của nhiều domain.
- Một transaction nghiệp vụ dựa vào shared DB lock.
- Nhiều ứng dụng dùng cùng stored procedure.
- Không thể restore một domain mà không ảnh hưởng domain khác.

Ghi rõ mức độ: đã xác minh, tần suất, luồng nghiệp vụ liên quan và tác động thay đổi. Không kết luận phải tách database chỉ vì có nhiều schema trong một instance; quyết định cần cân nhắc consistency, vận hành và chi phí.

## 14. Migration và thay đổi schema hiện tại

Migration là nơi kiến trúc dữ liệu và quy trình release gặp nhau. Cần tìm:
- Công cụ (Flyway, Liquibase, migration scripts tự viết).
- Migration chạy khi build, deploy hay theo job riêng.
- Ai có quyền DDL production.
- Migration version được lưu ở đâu.
- Có lock/serialization tránh hai pipeline cùng chạy?
- Migration có thể chạy lặp an toàn không?
- Có backup/PITR trước thay đổi phá hủy?
- Có kiểm thử với dữ liệu gần thực tế?
- Có phân biệt expand, backfill, cutover và contract?
- Rollback code có tương thích schema mới không?

### 14.1. Expand–migrate–contract

Một quy trình tương thích khi old và new app cùng chạy:
1. **Expand:** thêm cột/bảng/index theo hướng backward-compatible.
2. Deploy code mới có thể đọc/ghi cả cấu trúc cũ và mới khi cần.
3. **Migrate/backfill:** chuyển dữ liệu theo batch, đo tiến độ và kiểm tra.
4. Chuyển reader/writer sang cấu trúc mới.
5. Chờ mọi consumer cũ không còn truy cập.
6. **Contract:** xóa cột/bảng cũ sau khi xác minh an toàn.

Không gộp drop column và deploy code mới vào cùng một release nếu instance cũ vẫn còn. Một migration đã commit có thể không đảo ngược được; rollback application không tự rollback dữ liệu.

### 14.2. Migration online và rủi ro lock

Khảo sát:
- DDL có khóa bảng không.
- Thời gian build index.
- Table size và write rate.
- Lock timeout/statement timeout.
- Replication lag.
- Disk headroom.
- Backfill có throttling và checkpoint không.
- Migration có thể resume sau crash không.

Môi trường staging với ít dữ liệu có thể chạy migration trong 2 giây, còn production với hàng tỷ rows có thể khóa hàng phút. Cần benchmark trên snapshot có kích thước đại diện và kiểm tra engine/version cụ thể.

## 15. Luồng thay đổi hiện tại từ yêu cầu đến production

Đừng chỉ đọc file CI. Hãy truy một thay đổi thật từ đầu tới cuối, ví dụ một API field được thêm vào:
1. Yêu cầu nghiệp vụ/ticket được tạo.
2. Owner và phạm vi service được xác định.
3. ADR hoặc thiết kế được review nếu ảnh hưởng kiến trúc.
4. Code/contract/schema được sửa ở repository.
5. Pull request và reviewer phê duyệt.
6. CI chạy lint, unit, integration, contract, security scan.
7. Artifact được build, ký/định danh bằng digest.
8. Migration được tạo và thực thi theo thứ tự.
9. CD deploy staging và kiểm tra.
10. Approval/release gate cho production.
11. Canary/rolling/blue-green rollout.
12. Metrics/alerts theo dõi sau deploy.
13. Rollback/roll forward nếu có lỗi.
14. Change record, release note và tài liệu được cập nhật.

Với mỗi bước, ghi **owner, hệ thống công cụ, input/output, gate, thời gian, lỗi thường gặp và bằng chứng**. So sánh quy trình trên giấy với một số lần release thật, bao gồm cả hotfix và emergency change.

### 15.1. Ma trận change flow

| Giai đoạn | Đầu vào | Đầu ra | Người/nhóm chịu trách nhiệm | Bằng chứng |
| --- | --- | --- | --- | --- |
| Request | Business need/incident | Scope/priority | Product + service owner | Ticket |
| Design | Scope, dependency | ADR/contract | Architect/service team | Design review |
| Implement | Source/schema/spec | Commit/PR | Developer | Git history |
| Verify | Commit | Test/scan results | CI + reviewers | Pipeline run |
| Build | Source + toolchain | Artifact digest | CI identity | Build provenance |
| Migrate | Schema change | New compatible schema | DB/service owner | Migration record |
| Release | Artifact/config | Deployment | CD/release owner | Deployment event |
| Observe | Running workload | SLO/health result | On-call/SRE | Dashboard/alert |
| Close | Outcome | Release record/notes | Service owner | Change record |

### 15.2. Phân biệt code change, config change và data change

Một deployment có thể không đổi image nhưng thay feature flag, secret, route hoặc resource limit. Một migration có thể thay đổi dữ liệu dù code chưa deploy. Khảo sát phải ghi riêng:
- Code/artifact revision.
- Configuration revision.
- Database schema/data migration version.
- Infrastructure revision.
- Feature flag state.
- Release approval and deployment time.

Nếu chỉ lưu Git SHA của service, không thể tái dựng chính xác trạng thái toàn hệ thống tại thời điểm incident.

## 16. Phân tích lịch sử thay đổi và tần suất release

Dùng dữ liệu 3–6 tháng (hoặc khoảng phù hợp) để xem:
- Deploy frequency theo service.
- Lead time từ merge tới production.
- Change failure rate.
- Time to restore sau deployment incident.
- Hotfix/emergency change frequency.
- Migration failures và rollback.
- Số service cần phối hợp trong một release.
- Thời gian chờ approval/manual step.
- Release window và các freeze period.
- Phân bố lỗi theo loại thay đổi.

Đây là nhóm chỉ số thường gắn với DORA/engineering effectiveness, nhưng không nên dùng để xếp hạng team khi thiếu ngữ cảnh. Một service có ít deploy có thể do domain ổn định hoặc quy trình quá nặng; cần xem lead time, risk và business context.

### 16.1. Tìm coupling trong release

Một thay đổi order-service có buộc payment-service và inventory-service deploy cùng lúc không? Nếu có, lý do là:
- API contract breaking?
- Shared database schema?
- Event schema incompatibility?
- Shared library?
- Config flag được đổi đồng thời?
- Một migration không backward-compatible?

Ghi cụ thể dependency gây đồng bộ release. Không chỉ đếm số repository trong release train; cần xác định ràng buộc kỹ thuật nào khiến chúng phải đi cùng.

## 17. Khảo sát kiểm thử và release gates

Kiểm tra các lớp:
- Unit test và domain test.
- Integration test với database/broker thật hoặc test container.
- Contract test giữa producer/consumer.
- End-to-end test luồng nghiệp vụ.
- Performance/load test.
- Security/dependency/container scan.
- Migration test trên dữ liệu đại diện.
- Smoke test sau deploy.
- Canary analysis và SLO guardrail.

Ghi test nào tự động, test nào manual, thời gian, flaky rate, môi trường và coverage. **Có test suite không đồng nghĩa đã kiểm thử đúng rủi ro.** Ví dụ unit test có thể không phát hiện thiếu tenant predicate hoặc consumer xử lý event trùng.

### 17.1. Release gate hiện tại

Một bảng có thể ghi:
- Điều kiện bắt buộc.
- Công cụ đánh giá.
- Người có quyền bypass.
- Audit của bypass.
- Hành vi khi công cụ unavailable.
- Tiêu chí rollback/roll forward.

Nếu production release phụ thuộc một người duyệt duy nhất đang nghỉ phép, đó là rủi ro quy trình. Nếu security scan chỉ chạy ở main branch sau deploy, đó là khoảng trống bảo vệ cần ghi rõ.

## 18. Quan sát và khả năng truy vết thay đổi

Để liên kết thay đổi với tác động, khảo sát:
- Trace có correlation qua gateway, service và broker không?
- Metric có nhãn service, environment, version không?
- Log có structured fields và request/job IDs không?
- Release marker có xuất hiện trên dashboard?
- Alert có gắn owner/runbook không?
- Retention có đủ để phân tích sau sự cố?
- Có phân biệt lỗi client, service và dependency?
- Có business metrics cho kết quả nghiệp vụ không?

Một service có log local nhưng không có central collection sẽ khó điều tra sự cố sau pod restart. Trace sampling có thể bỏ qua request hiếm nhưng nghiêm trọng; cần kết hợp metric, logs và audit.

### 18.1. Liên kết change record với runtime

Một release record nên có:
- Service ID.
- Commit SHA.
- Image digest.
- Config/infra revision.
- Migration version.
- Environment/region.
- Deployment time.
- Approver/automation identity.
- Test/scan evidence.
- Outcome và incident link nếu có.

Không chỉ dựa vào image tag có thể ghi đè. Artifact digest và config revision giúp so sánh chính xác bản đang chạy.

## 19. Khảo sát security và quyền truy cập

Các câu hỏi quan trọng:
- Service identity và user identity được phân biệt ra sao?
- Service account có quyền gì ở DB, broker, object storage?
- Có credential dùng chung giữa nhiều service không?
- Secret được lưu/rotate ở đâu?
- Database có RLS/tenant isolation hay app-only guard?
- Network egress có giới hạn không?
- PII/payment/secrets có xuất hiện trong log hoặc event không?
- Migration/admin account có quyền quá rộng?
- Có audit access và privileged operation không?
- Dependency/library và base image được quản lý thế nào?

Khảo sát không yêu cầu copy secret hoặc dữ liệu cá nhân vào báo cáo. Chỉ ghi tham chiếu, loại quyền, phạm vi và phát hiện ở mức an toàn. Không xuất query result chứa PII khi không cần; dùng schema metadata hoặc dữ liệu đã khử nhạy cảm.

### 19.1. Data lineage và luồng dữ liệu nhạy cảm

Vẽ đường đi của dữ liệu từ điểm nhập:
- API/webhook/file.
- Service xử lý.
- Database và cache.
- Event broker.
- Search/analytics.
- Export và third-party provider.
- Log/trace/backup.

Với dữ liệu nhạy cảm, ghi purpose, classification, retention, encryption, access owner, region và deletion path. Một field đã xóa khỏi database vẫn có thể còn trong event archive hoặc warehouse.

## 20. Đo hiệu năng và capacity baseline

Khảo sát kiến trúc không nên dừng ở topology. Cần baseline:
- Request/second và business throughput.
- p50/p95/p99 latency theo route.
- Error/timeout/retry rate.
- CPU, memory, GC, thread pool.
- DB connection, query latency, lock, I/O.
- Broker arrival/process rate, lag và event age.
- Cache hit/miss/stale.
- Network egress/latency và external quota.
- Replica count, autoscaling behavior và resource requests/limits.

Ghi giờ cao điểm, traffic mix và điều kiện đo. Không so sánh p95 của hai môi trường có traffic mix hoặc dataset khác nhau rồi kết luận thay đổi kiến trúc làm nhanh hơn.

### 20.1. Capacity và noisy neighbor

Với service dùng chung database/cluster, tìm tenant hoặc workload chiếm tài nguyên. Ghi:
- Top query/workload.
- Pool usage và max connections.
- Queue depth theo consumer.
- CPU/IO của node/database.
- Quota/rate limit.
- Khả năng mở rộng khi một dependency yếu.

Một service có CPU thấp nhưng latency cao có thể đang chờ database hoặc network. Cần trace để xác định critical path.

## 21. Phỏng vấn stakeholder và workshop khảo sát

Phỏng vấn cần bổ sung bằng chứng, không thay thế kiểm tra kỹ thuật.

### 21.1. Nhóm cần tham gia

- Product/business owner: luồng nghiệp vụ, criticality, chấp nhận gián đoạn.
- Service owner/developer: code, domain, API, event, data ownership.
- DBA/data engineer: schema, query, migration, backup/restore.
- Platform/SRE: deployment, networking, observability, on-call, capacity.
- Security/privacy: identity, data classification, compliance.
- QA/test engineer: test coverage, môi trường, regression.
- Support/operations: incident pattern, thao tác thủ công, pain points.

### 21.2. Câu hỏi phỏng vấn service owner

1. Service chịu trách nhiệm cho use case nào?
2. Dữ liệu nào service sở hữu và ai khác được ghi?
3. API/event nào là contract công khai?
4. Dependency nào bắt buộc, dependency nào có fallback?
5. Một request quan trọng đi qua những thành phần nào?
6. Khi database hoặc broker lỗi, hành vi hiện tại ra sao?
7. Thay đổi schema/API được phát hành như thế nào?
8. Ai trực và runbook nào đang được sử dụng?
9. Incident gần nhất là gì, nguyên nhân và bài học?
10. Nếu cần rollback, điều gì không thể đảo ngược?
11. Phần nào trong sơ đồ hiện tại không còn đúng?
12. Kết luận nào có thể xác minh bằng trace, query hoặc pipeline?

### 21.3. Cách ghi nhận workshop

Mỗi phát hiện gắn với:
- Statement rõ ràng.
- Người xác nhận/role.
- Evidence link hoặc source.
- Mức tin cậy.
- Disagreement giữa các bên.
- Follow-up owner và due date.
- Phạm vi được xác nhận.

Nếu team A cho rằng service sở hữu bảng orders nhưng DBA nói checkout-service cũng update bảng, không chọn một bên làm “đúng” ngay. Ghi discrepancy và kiểm tra quyền/query history.

## 22. Đánh giá rủi ro và mức độ ảnh hưởng

Một phát hiện nên được phân loại theo **impact × likelihood × detectability** hoặc phương pháp risk scoring được tổ chức chấp thuận. Tránh gán điểm chính xác giả khi chưa có dữ liệu.

Ví dụ risk register:

| Phát hiện | Tác động | Khả năng | Bằng chứng | Ưu tiên xử lý |
| --- | --- | --- | --- | --- |
| Nhiều service ghi bảng orders | Sai dữ liệu, migration khó | Trung bình/cao tùy tần suất | DB grants + query logs | Cao |
| Không có owner cho consumer | Incident kéo dài, contract break | Đang xảy ra/không rõ | Catalog thiếu owner | Cao |
| Retry payment không idempotent | Charge trùng | Thấp/trung bình nhưng impact cao | Code + test gap | Rất cao |
| Migration drop column cùng release | Downtime/rollback fail | Theo release | Pipeline + migration | Cao |
| Dashboard không gắn version | Triage chậm | Cao khi incident | Dashboard labels | Vừa |
| Read replica lag không đo | Dữ liệu cũ | Chưa rõ | Telemetry thiếu | Cần xác minh |

Các dòng chỉ minh họa. Đánh giá cần tách **rủi ro đã xảy ra**, **điểm yếu thiết kế**, **thiếu bằng chứng** và **đề xuất cải tiến**.

### 22.1. Severity khác priority

Severity mô tả tác động khi sự cố xảy ra. Priority còn xét thời gian, chi phí, khả năng xử lý và dependency với chương trình chuyển đổi. Một thiếu sót tài liệu có thể có severity thấp nhưng priority cao nếu sắp diễn tập DR. Một kiến trúc shared DB có thể có impact lớn nhưng không thể tách ngay; cần roadmap theo giai đoạn.

## 23. Deliverables của một đợt khảo sát

Một gói kết quả hữu ích thường gồm:

1. **Scope & assumptions:** hệ thống, môi trường, luồng và giới hạn khảo sát.
2. **System inventory:** service, job, gateway, datastore, broker, external dependency.
3. **Current-state diagrams:** context, container/component, deployment và data flow.
4. **Service ownership matrix:** team, data owner, on-call, lifecycle.
5. **API/event dependency map:** interface, consumer, version, contract.
6. **Database inventory:** engine, schema, table, access, workload, backup.
7. **Data ownership matrix:** read/write/DDL theo service và datastore.
8. **Transaction and consistency map:** luồng commit, saga, outbox, idempotency.
9. **Change/release flow:** từ PR tới production, migration, rollback.
10. **Operational baseline:** SLO, metrics, capacity, incidents.
11. **Risk and gap register:** phát hiện, evidence, impact, confidence, owner.
12. **Open questions:** phần chưa xác minh và cách xử lý.
13. **Decision log:** các quyết định khảo sát đã thống nhất, chưa thống nhất.
14. **Transformation inputs:** các ràng buộc và điểm cần giải quyết trước khi chọn target architecture.

Không nhất thiết tất cả phải là tài liệu riêng. Có thể dùng một portal hoặc repository có liên kết, miễn người đọc tìm được nguồn và biết dữ liệu cập nhật lúc nào.

## 24. Template hồ sơ service hiện trạng

Mẫu Markdown:

~~~markdown
# Service: order-service

## Identity
- Service ID:
- Business domain:
- Purpose:
- Lifecycle:
- Owner team:
- Data owner:
- On-call / escalation:

## Code and delivery
- Repository:
- Runtime / framework:
- Build pipeline:
- Artifact / image digest:
- Deployment environments:
- Release strategy:
- Migration mechanism:
- Rollback constraints:

## Interfaces
- Provided APIs:
- Consumed APIs:
- Published events:
- Consumed events:
- External integrations:

## Data
- Source-of-truth database:
- Schemas / tables owned:
- Other services with read access:
- Other services with write access:
- Cache / search / object storage:
- Transaction boundary:
- Backup / RPO / restore evidence:

## Operations
- SLI / SLO:
- Dashboard:
- Logs / traces:
- Alerts:
- Runbook:
- Capacity baseline:
- Recent incidents:

## Evidence and confidence
- Sources:
- Observed environment:
- Last verified:
- Confirmed facts:
- Assumptions:
- Unknowns:
~~~

Mẫu cần điều chỉnh theo chuẩn catalog của tổ chức. Không ghi password, token, private key, raw PII hoặc snapshot production vào tài liệu.

## 25. Template khảo sát database

| Trường | Nội dung cần điền |
| --- | --- |
| Database ID | Định danh ổn định |
| Engine/version | PostgreSQL, MySQL, MongoDB... |
| Owner | Service/team chịu trách nhiệm dữ liệu |
| Infra owner | Team quản lý engine/cluster |
| Environment/region | Nơi triển khai |
| Schema | Danh sách schema và version |
| Tables/entities | Entity quan trọng và mô tả |
| Clients | Service/job/user/role truy cập |
| Read/write matrix | Operation theo client |
| Transaction | Isolation, boundary, locking |
| Workload | QPS, query latency, storage, connections |
| Backup/replication | Snapshot, PITR, lag, retention |
| Migration | Tool, order, compatibility, approval |
| Security | Grants, encryption, audit, classification |
| Recovery | RTO/RPO, restore test, owner |
| Evidence | Query, config, dashboard, người xác nhận |

## 26. Template khảo sát luồng thay đổi

Với một thay đổi đại diện, ghi:

~~~text
Change ID:
Business reason:
Affected service(s):
Affected database/schema:
Affected API/event:
Code owner/reviewer:
ADR/design review:
Test layers:
Build artifact and digest:
Migration plan and order:
Staging verification:
Production approval:
Deployment strategy:
Observability/rollback:
Result:
Evidence links:
Unknowns / follow-up:
~~~

Nên chọn ít nhất:
- Một release thông thường.
- Một thay đổi schema.
- Một thay đổi API/event ảnh hưởng consumer.
- Một hotfix hoặc emergency change.
- Một lần rollback/incident nếu có.

Một quy trình chỉ khảo sát happy path sẽ bỏ qua những thao tác thủ công và ngoại lệ thường gây rủi ro nhất.

## 27. Phương pháp thu thập bằng chứng theo từng bước

**Bước 1 — Xác định phạm vi.** Chọn business flow, hệ thống, environment, thời gian và mục tiêu khảo sát. Thống nhất người tham gia và cách xử lý dữ liệu nhạy cảm.

**Bước 2 — Tạo inventory sơ bộ.** Thu thập repository, deployment, database, API, event, job và resource từ nguồn hiện có. Gắn nguồn và timestamp.

**Bước 3 — Phỏng vấn owner.** Xác nhận business capability, ownership, các ngoại lệ và điểm chưa rõ.

**Bước 4 — Theo dõi luồng runtime.** Dùng trace, gateway, broker, query logs và network metadata để xác minh đường gọi và đường dữ liệu trong môi trường được phép.

**Bước 5 — Khảo sát database.** Đọc schema, grants, query/workload, transaction, migration, replication và backup.

**Bước 6 — Truy vết thay đổi thật.** Chọn PR/release/migration đại diện và đi từ ticket tới production, bao gồm approval, gate, rollback.

**Bước 7 — Đối chiếu nguồn.** So sánh diagram, code, runtime, pipeline và phỏng vấn; ghi discrepancy.

**Bước 8 — Đánh giá baseline và rủi ro.** Đo latency, error, capacity, coupling, data consistency và operational gaps.

**Bước 9 — Xác nhận phát hiện.** Review với owner để tránh hiểu sai; phân biệt sự thật, giả thuyết và quyết định.

**Bước 10 — Bàn giao kết quả.** Cung cấp sơ đồ, inventory, ownership, database map, change flow, risk register và open questions có owner.

## 28. Các kỹ thuật khảo sát có thể sử dụng

### 28.1. Static analysis và repository inspection

Tìm:
- Build modules và deployable artifacts.
- Dependency giữa modules.
- REST/gRPC clients, Feign, WebClient, RestTemplate.
- Kafka producers/consumers, listener, queue.
- ORM entities, repositories, JDBC/SQL, stored procedures.
- Migration scripts và schema version.
- Config keys, feature flags, secret references.
- Dockerfile, Helm, Kubernetes, IaC.
- Test classes, contract tests và CI workflow.

Static scan giúp tìm candidate nhưng có thể bỏ lỡ dynamic routing, reflection, config injection, SQL sinh động và traffic từ service ngoài repository.

### 28.2. Runtime tracing

Distributed trace giúp nhận diện call graph thực tế, critical path, retries, downstream latency. Khi dùng tracing:
- Chọn cửa sổ và workload đại diện.
- Kiểm tra sampling rate.
- Bao gồm async context propagation.
- Phân biệt span client/server và parent/child.
- Không cộng duration lồng nhau một cách sai.
- Bảo vệ trace attributes khỏi PII/secret.

Trace cho biết request đã đi đâu, không nhất thiết bao phủ mọi đường ít dùng hoặc batch chạy ngoài cửa sổ khảo sát.

### 28.3. Database metadata và query telemetry

Có thể dùng:
- System catalogs/information schema.
- Grants/roles và ownership.
- Migration history.
- Query statistics.
- Slow query logs.
- Connection/lock metrics.
- Replication status.
- Backup catalog và restore records.

Quyền truy cập phải phù hợp; tránh chạy full table scans hoặc export dữ liệu production không cần thiết.

### 28.4. CI/CD và Git history

Đối chiếu:
- Commit, PR, reviewer, branch policy.
- Pipeline definitions và run history.
- Artifact digest.
- Deploy event và environment.
- Migration execution.
- Approval, exception và manual action.
- Rollback/roll-forward record.

Một file pipeline thể hiện khả năng được cấu hình; lịch sử run mới cho biết nó đã được thực thi ra sao.

## 29. Những sai lầm thường gặp khi khảo sát

1. **Chỉ đọc tài liệu thiết kế:** bỏ qua runtime drift và thao tác thủ công.
2. **Chỉ grep repository:** bỏ sót traffic từ external clients, job và config động.
3. **Chỉ phỏng vấn một architect:** không thấy các ngoại lệ mà on-call/DBA xử lý hằng ngày.
4. **Không ghi timestamp:** so sánh trace tuần này với diagram năm ngoái mà không nhận ra khác biệt.
5. **Coi database server là data owner:** không biết service nào chịu trách nhiệm nghiệp vụ.
6. **Chỉ liệt kê bảng:** bỏ qua query, grants, triggers, stored procedure và batch writer.
7. **Không khảo sát event:** bỏ sót dependency bất đồng bộ và replay.
8. **Chỉ xem pipeline happy path:** bỏ qua emergency release, migration và rollback.
9. **Gộp tất cả lỗi thành technical debt:** không phân biệt rủi ro thực tế và cải tiến tùy chọn.
10. **Vẽ sơ đồ quá chi tiết ngay đầu:** tốn thời gian nhưng không trả lời câu hỏi quyết định.
11. **Tự động hóa inventory mà không xác nhận owner:** tạo danh sách đẹp nhưng sai trách nhiệm.
12. **Đề xuất target architecture trước khi hiểu hiện trạng:** dẫn tới khảo sát thiên lệch theo giải pháp đã thích.
13. **Ghi secret/PII vào evidence:** biến báo cáo khảo sát thành nguồn rò rỉ mới.
14. **Không xác định điều gì chưa biết:** tạo cảm giác chắc chắn giả.
15. **Không review phát hiện với các nhóm liên quan:** kết luận sai về ranh giới và quy trình.

## 30. Từ khảo sát hiện trạng tới quyết định chuyển đổi

Sau khi có evidence, mới phân nhóm quyết định:
- **Giữ nguyên:** cấu trúc đang hoạt động tốt, có owner và đáp ứng mục tiêu.
- **Cải thiện tại chỗ:** thiếu observability, automation, tests hoặc guardrails.
- **Tách ranh giới:** coupling dữ liệu/ownership gây khó release hoặc scale.
- **Hợp nhất:** các thành phần phân tán giả tạo, cùng thay đổi và cùng sở hữu.
- **Thay thế:** công nghệ/ứng dụng hết hỗ trợ hoặc không đáp ứng yêu cầu.
- **Di trú dữ liệu:** cần thay schema, database engine hoặc ownership.
- **Loại bỏ:** thành phần không còn consumer hoặc business value.

Mỗi quyết định cần có:
- Evidence hiện trạng.
- Mục tiêu/constraint.
- Lợi ích dự kiến.
- Rủi ro và chi phí.
- Dependency/migration sequence.
- Owner và approval.
- Success criteria và rollback/recovery plan.

Không phải mọi vấn đề đều cần microservice mới. Một shared database có thể được cải thiện bằng ownership, permissions, schema boundary và migration process trước khi tách physical database. Một service chậm có thể do query kém chứ không do kiến trúc monolith/microservices.

## 31. Ví dụ xuyên suốt: khảo sát hệ thống order hiện tại

Giả sử một hệ thống có order-service, checkout-service, inventory-service, payment-service và notification-worker. Sơ đồ tài liệu nói mỗi service có database riêng. Qua khảo sát, nhóm tìm thấy:
- order-service ghi bảng orders.
- checkout-service cũng cập nhật cột `payment_status` trong orders.
- reporting-worker query trực tiếp orders DB.
- payment-service phát event PaymentAuthorized.
- order-service nhận event nhưng không có idempotency key rõ ràng.
- Migration của orders DB chạy khi pod order-service khởi động.
- Pipeline checkout deploy trước migration nhưng không kiểm tra schema compatibility.
- Dashboard chỉ gắn service name, không gắn image version.
- Runbook payment escalation link tới lịch trực đã ngừng dùng.

### 31.1. Những gì đã xác minh

Ma trận read/write và query logs xác nhận hai writer cho bảng orders. Consumer code xác nhận event payment có retry. Pipeline và migration scripts xác nhận DDL được thực hiện trong startup path. Đây là bằng chứng hiện trạng, không chỉ là nhận định trong buổi phỏng vấn.

### 31.2. Rủi ro và câu hỏi mở

- Ai là owner cuối cùng của `payment_status`?
- Có transaction/locking ngăn race giữa checkout và order không?
- Event duplicate có thể chuyển state sai không?
- Khi pod restart nhiều replica, migration lock có hoạt động đúng?
- Rollback code có tương thích schema vừa migrate?
- Reporting query có ảnh hưởng latency giao dịch?
- Ai trực payment-service sau khi lịch cũ ngừng?

### 31.3. Đầu vào cho chuyển đổi

Nhóm có thể đề xuất:
- Xác lập ownership state và API/event contract.
- Thay đổi migration chạy theo pipeline/job được kiểm soát.
- Thêm idempotency và consumer deduplication.
- Tách reporting workload qua replica/read model nếu phù hợp.
- Gắn version/digest vào dashboard và deployment record.
- Khôi phục on-call/runbook link.

Những đề xuất là hướng cần thiết kế và phê duyệt sau khảo sát. Không tự động áp dụng trong giai đoạn inventory.

## 32. Cách trình bày báo cáo cho lãnh đạo và nhóm kỹ thuật

Một báo cáo hiện trạng nên có hai lớp:

**Executive view:**
- Phạm vi và mục tiêu.
- Số service/database/dependency đã xác định.
- Các luồng nghiệp vụ quan trọng.
- Rủi ro lớn nhất và ảnh hưởng kinh doanh.
- Những điểm đang hoạt động tốt.
- Các quyết định cần lãnh đạo/owner.
- Mức tin cậy và phần chưa khảo sát.

**Engineering appendix:**
- C4 diagrams.
- Service/data ownership matrix.
- API/event/dependency graph.
- Schema/query/transaction findings.
- CI/CD/change flow.
- Runtime metrics, capacity và incident evidence.
- Risk register, open questions, links.

Không đưa hàng trăm dòng inventory vào executive summary. Mọi kết luận ngắn cần liên kết tới evidence chi tiết để nhóm kỹ thuật kiểm tra được.

### 32.1. Cách diễn đạt phát hiện

Nên viết:
> Trong 4 tuần quan sát production, checkout-service và order-service đều có quyền UPDATE bảng orders. Query logs ghi nhận hai service thực hiện cập nhật cột payment_status. Hiện chưa tìm thấy một ownership contract mô tả thứ tự ghi. Rủi ro là trạng thái có thể bị ghi đè khi event retry hoặc hai request chạy đồng thời. Cần xác nhận với Order và Checkout owners trước khi chọn migration path.

Tránh viết:
> Database thiết kế sai và phải tách ngay.

Cách thứ nhất nêu phạm vi, bằng chứng, rủi ro và câu hỏi cần xác minh; cách thứ hai là kết luận/giải pháp chưa được chứng minh.

## 33. Bài tập thực hành

Một nền tảng bán hàng có:
- API gateway và năm microservices Java.
- Một PostgreSQL cluster với ba schema.
- Redis dùng chung.
- Kafka có các topic order-created, payment-result và inventory-updated.
- Hai batch job chạy ban đêm.
- Một data warehouse nhận CDC.
- CI/CD deploy từng service nhưng migration nằm trong startup code.
- Các nhóm báo rằng có thể deploy độc lập, nhưng incident gần đây phải deploy đồng thời ba service.

**Yêu cầu A — Xác định phạm vi:** chọn hai business flow quan trọng, ghi start/end, state transition và external side effects.

**Yêu cầu B — Inventory:** tạo danh sách service, worker, API, event, database, cache, batch, external dependency và owner. Gắn source/evidence/time.

**Yêu cầu C — Kiến trúc:** vẽ context, container và runtime view. Phân biệt synchronous, asynchronous và direct database access. Đánh dấu dependency chưa xác minh.

**Yêu cầu D — Data ownership:** lập matrix read/write/DDL theo service/schema/table. Tìm bảng được nhiều service cùng ghi và xác minh qua grants, code, query logs.

**Yêu cầu E — Database:** chọn các bảng quan trọng, đọc PK/FK/index/constraint, query workload, transaction boundary, backup, replication và migration path.

**Yêu cầu F — Change flow:** truy vết một thay đổi API, một migration và một hotfix từ ticket tới production. Xác định bước nào khiến ba service phải release cùng lúc.

**Yêu cầu G — Rủi ro:** phân biệt finding đã xác minh, giả thuyết và khoảng trống. Xếp ưu tiên theo business impact, likelihood và effort.

**Yêu cầu H — Deliverable:** tạo current-state diagrams, service catalog extract, database map, change flow, risk register và open questions. Không triển khai thay đổi production.

Một kết quả tốt cho phép người chưa tham gia khảo sát hiểu hệ thống hiện tại, truy được bằng chứng và biết chính xác những điều cần xác minh trước khi quyết định chuyển đổi.

## 34. Câu hỏi tự kiểm tra

1. Vì sao cần đối chiếu diagram, source code, runtime và change history?
2. Service inventory khác dependency graph như thế nào?
3. Một service có thể tồn tại trong nhiều deployment và một repository có thể chứa nhiều service ra sao?
4. Vì sao tên service không chứng minh data ownership?
5. Cần những bằng chứng nào để xác định service nào đang ghi một bảng?
6. Tại sao database inventory cần bao gồm cache, broker, search và object storage?
7. Làm sao phân biệt source of truth với read replica, cache và analytics projection?
8. Khi nào schema change yêu cầu expand–migrate–contract?
9. Tại sao migration chạy trong application startup có thể tạo rủi ro khi scale nhiều replica?
10. Làm sao phát hiện hidden coupling không thể hiện trong API diagram?
11. Tại sao trace không đủ để chứng minh dependency graph đầy đủ?
12. Những thông tin nào cần truy vết từ ticket tới deployment?
13. Làm sao phân biệt code, config, infrastructure và data change?
14. Vì sao rollback application không đồng nghĩa rollback database?
15. Những metric nào cần thu thập để tạo performance baseline?
16. Làm sao ghi một discrepancy giữa lời phỏng vấn và runtime evidence?
17. Tại sao cần confidence level và timestamp cho từng finding?
18. Làm sao tránh việc target architecture làm thiên lệch khảo sát?
19. Những tài liệu nào giúp incident responder nhanh chóng hiểu service?
20. Khi nào nên giữ nguyên, cải thiện, tách, hợp nhất hoặc thay thế thành phần?
21. Vì sao một release được mô tả là độc lập nhưng thực tế vẫn phải deploy nhiều service?
22. Bằng chứng nào cho thấy backup có thể restore, không chỉ chạy thành công?
23. Những thao tác nào trong production cần tránh khi đang khảo sát?
24. Khi nào kết quả khảo sát đủ tin cậy để đưa ra quyết định chuyển đổi?

## 35. Ghi nhớ

- **Khảo sát hiện trạng bắt đầu từ bằng chứng**, không bắt đầu từ giả định rằng kiến trúc tài liệu phản ánh runtime.
- **Kiến trúc, database và change flow phải được khảo sát cùng nhau** vì ranh giới service, ownership dữ liệu và khả năng phát hành phụ thuộc lẫn nhau.
- **Data ownership cần được chứng minh bằng schema, grants, code, query và người chịu trách nhiệm**, không suy ra từ tên database hoặc repository.
- **Dependency bao gồm API, event, database, cache, batch, file, IAM và external provider**; chỉ vẽ HTTP call sẽ bỏ sót coupling quan trọng.
- **Transaction, idempotency, migration và rollback** quyết định khả năng thay đổi an toàn, nhất là khi nhiều service cùng tham gia một luồng nghiệp vụ.
- **Change flow cần được truy vết qua release thật**, bao gồm approval, migration, config, deployment, observability và emergency path.
- **Mỗi finding cần có nguồn, timestamp, phạm vi và confidence**; giả thuyết và phần chưa biết phải được ghi rõ.
- **Khảo sát mô tả hệ thống đang có và rủi ro được chứng minh**; quyết định target architecture cần được đưa ra sau khi hiểu đầy đủ constraint và trade-off.
