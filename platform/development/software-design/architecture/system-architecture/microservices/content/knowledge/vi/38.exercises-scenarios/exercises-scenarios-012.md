# Danh sách kiểm tra ranh giới, dữ liệu, phát hành và khả năng vận hành

## 1. Mục tiêu và cách sử dụng

Một hệ thống microservices có thể có nhiều service chạy độc lập nhưng vẫn thất bại ở cấp sản phẩm nếu ranh giới domain không rõ, dữ liệu bị sở hữu chồng chéo, API/event contract thay đổi không tương thích hoặc quy trình phát hành không kiểm soát được tác động xuyên service. Một thiết kế có sơ đồ đẹp vẫn chưa sẵn sàng production nếu thiếu backup, alert, runbook, owner hoặc khả năng khôi phục.

Checklist này giúp nhóm đánh giá một thiết kế hoặc thay đổi kiến trúc qua bốn nhóm:

1. **Ranh giới:** service/domain có ownership và trách nhiệm rõ ràng không?
2. **Dữ liệu:** ai sở hữu dữ liệu, consistency và lifecycle được bảo vệ thế nào?
3. **Phát hành:** thay đổi có thể triển khai, quan sát, dừng và rollback an toàn không?
4. **Khả năng vận hành:** hệ thống có thể được theo dõi, xử lý sự cố và phục hồi trong mục tiêu đã cam kết không?

Checklist phù hợp cho review kiến trúc service mới, thay đổi lớn về domain/API/event/database/deployment, readiness trước production launch, điều tra service đang có sự cố, chuẩn bị game day/DR drill, migration hoặc đánh giá technical debt.

Đây không phải form phải tick hết mọi dòng cho mọi workload. Batch job nhỏ không cần cùng mức kiểm soát như Payment Ledger. Hãy đánh dấu **N/A** có lý do, ghi owner và bằng chứng cho quyết định quan trọng, rồi phân loại rủi ro còn lại.

## 2. Quy tắc đánh giá

Mỗi mục cần có trạng thái và bằng chứng cụ thể.

| Trạng thái | Ý nghĩa | Hành động |
|---|---|---|
| Pass | Có bằng chứng yêu cầu được đáp ứng | Lưu link/artifact và ngày kiểm tra |
| Partial | Đã có một phần nhưng còn gap | Ghi gap, owner, deadline và mitigation |
| Fail | Chưa đáp ứng hoặc rủi ro không chấp nhận được | Chặn gate tương ứng hoặc lập quyết định rủi ro |
| N/A | Không áp dụng cho workload này | Nêu lý do và người xác nhận |
| Unknown | Chưa có dữ liệu đủ để kết luận | Không xem là Pass; giao owner xác minh |

Checkbox không phải bằng chứng. Đánh dấu “backup enabled” chưa chứng minh có thể restore. Bằng chứng tốt hơn là lần restore drill gần nhất, thời gian hoàn tất, dữ liệu đối soát và lỗi đã khắc phục.

### 2.1. Mức độ quan trọng

- **Critical:** vi phạm có thể gây mất dữ liệu, truy cập trái phép, giao dịch sai, outage lớn hoặc vi phạm nghĩa vụ pháp lý.
- **Important:** làm giảm khả năng mở rộng, maintainability, observability hoặc tốc độ phục hồi.
- **Contextual:** hữu ích tùy loại workload, quy mô hoặc roadmap.

Không dùng số lượng Pass để che một Critical Fail. Một service có 95% mục Pass nhưng thiếu authorization ở endpoint nhạy cảm vẫn chưa production-ready.

### 2.2. Phạm vi và giả định

Trước khi review, ghi:

- Tên service/capability và domain owner.
- Môi trường, region và loại workload.
- Người chịu trách nhiệm thiết kế và vận hành.
- Data classification và criticality.
- Dependencies nội bộ/bên ngoài.
- Traffic, throughput và growth assumptions.
- SLO, RPO, RTO và retention targets.
- Thay đổi đang được đánh giá và phạm vi ảnh hưởng.

Nếu không biết một thông tin nền, ghi Unknown và xác minh. Không suy đoán mức tải, quyền dữ liệu hoặc khả năng phục hồi.

## 3. Tổng quan bốn nhóm kiểm tra

~~~mermaid
flowchart TD
    A[Architecture change or new service] --> B[1. Boundaries and ownership]
    B --> C[2. Data and contracts]
    C --> D[3. Release and change safety]
    D --> E[4. Operations and recovery]
    E --> F{Critical gaps remain?}
    F -->|Yes| G[Block or approve explicit risk mitigation]
    F -->|No| H[Readiness decision and evidence]
    H --> I[Observe after launch]
~~~

Bốn nhóm liên kết với nhau. Ranh giới service sai có thể dẫn tới data ownership mơ hồ. Ownership mơ hồ làm migration và rollback khó. Phát hành khó rollback làm tăng yêu cầu observability và recovery. Review cần xem các mối quan hệ này, không chỉ tick từng mục riêng.

## 4. Checklist A — Ranh giới domain và service ownership

### 4.1. Domain responsibility

- [ ] Service có một mục đích nghiệp vụ dễ diễn đạt trong một hoặc hai câu.
- [ ] Có domain owner chịu trách nhiệm cho quy tắc nghiệp vụ.
- [ ] Service boundary và chức năng nằm ngoài phạm vi được ghi rõ.
- [ ] Thuật ngữ nghiệp vụ có định nghĩa nhất quán trong bounded context.
- [ ] Mỗi business invariant có nơi thực thi có thẩm quyền.
- [ ] Không có hai service cùng tuyên bố sở hữu một trạng thái nghiệp vụ.
- [ ] Boundary phản ánh khả năng thay đổi và ownership, không chỉ nhóm bảng database.
- [ ] Quy trình xuyên domain được mô tả bằng contract/workflow rõ ràng.
- [ ] Có lý do cụ thể cho việc tách service thay vì module trong một ứng dụng.
- [ ] Có lý do cụ thể nếu nhiều domain được giữ chung trong một deployment.

**Bằng chứng nên có:** context map, domain glossary, service catalog, dependency map, ADR ghi quyết định boundary và danh sách invariant.

### 4.2. Data ownership

- [ ] Mỗi tập dữ liệu nghiệp vụ có một owner authoritative.
- [ ] Service khác truy cập dữ liệu qua API/event/replica được kiểm soát thay vì sửa trực tiếp database của owner.
- [ ] Shared database có boundary, schema ownership và quyền ghi cụ thể.
- [ ] Read models/cache/search indexes được xác định là dữ liệu dẫn xuất.
- [ ] Có nguồn để rebuild hoặc restore dữ liệu dẫn xuất.
- [ ] Có quy tắc khi source of truth và projection bất đồng.
- [ ] Manual corrections có audit, owner và provenance.
- [ ] Không có service phụ thuộc vào bảng nội bộ chưa được công bố như contract.
- [ ] Việc xóa/đổi field được phối hợp với consumers.
- [ ] Data lifecycle và retention có owner.

Một database server có thể dùng chung vì lý do vận hành, nhưng không có nghĩa các domain được quyền sửa bảng của nhau. Physical sharing và logical ownership là hai quyết định khác nhau.

### 4.3. Dependency và coupling

- [ ] Danh sách synchronous dependencies được ghi.
- [ ] Danh sách asynchronous dependencies và event consumers được ghi.
- [ ] Không có vòng phụ thuộc khiến nhiều service không thể deploy/khởi động độc lập.
- [ ] Critical path không có fan-out không giới hạn.
- [ ] Timeouts, retries, circuit breakers và bulkheads có chủ đích.
- [ ] Service không phụ thuộc thứ tự deploy ngầm giữa nhiều repositories.
- [ ] Shared libraries không chứa business rules làm mất domain ownership.
- [ ] Dependency version và compatibility policy được xác định.
- [ ] Có phương án khi dependency chậm, lỗi hoặc unavailable.
- [ ] Có thể xác định blast radius khi một dependency thay đổi.

### 4.4. Team ownership và lifecycle

- [ ] Có owning team và contact/on-call route.
- [ ] Có repository, CI/CD pipeline và deployment owner.
- [ ] Có runbook và dashboard do owner duy trì.
- [ ] Có lifecycle: active, deprecated, replacement hoặc retirement.
- [ ] Có kế hoạch chuyển ownership khi team thay đổi.
- [ ] Không có critical service mồ côi.
- [ ] Service catalog phản ánh đúng dependencies, tier và data classification.
- [ ] Có tiêu chí xóa service/endpoint/event cũ.

### 4.5. Câu hỏi review ranh giới

1. Nếu service ngừng hoạt động, capability nào bị ảnh hưởng?
2. Ai có quyền quyết định trạng thái nghiệp vụ của nó?
3. Service khác có thể thay đổi dữ liệu này mà không gọi owner không?
4. Có thể deploy service độc lập không? Nếu không, coupling nằm ở đâu?
5. Nếu một team rời tổ chức, ownership có thể chuyển giao không?
6. Service có tồn tại chỉ để proxy request mà không tạo boundary có giá trị không?
7. Một thay đổi domain có buộc nhiều team sửa cùng lúc không?
8. Ranh giới hiện tại có phản ánh cách business thực sự thay đổi không?

## 5. Checklist B — API, event và contract

### 5.1. API contract

- [ ] Endpoint, method và resource có semantics rõ.
- [ ] Request/response schema có versioning hoặc compatibility rules.
- [ ] Error codes và retryability được định nghĩa.
- [ ] Pagination, sorting, filtering và limits có giới hạn.
- [ ] Timeout budget phù hợp end-to-end workflow.
- [ ] Authentication và authorization được kiểm tra ở server.
- [ ] Tenant boundaries được áp dụng ở mọi query và mutation.
- [ ] Idempotency được định nghĩa cho operations có thể retry.
- [ ] Rate limits/quota có owner và hành vi khi vượt ngưỡng.
- [ ] API không để lộ internal fields không cần thiết.
- [ ] PII và sensitive fields được phân loại.
- [ ] Có contract tests hoặc consumer compatibility checks.

### 5.2. Event contract

- [ ] Phân biệt command, domain event và integration event.
- [ ] Event mô tả điều đã xảy ra, không phải yêu cầu chưa hoàn tất.
- [ ] Event có event ID, aggregate/entity key và schema version.
- [ ] Ordering/sequence semantics phù hợp.
- [ ] Có occurred time và recorded time nếu cần phân tích.
- [ ] Correlation/causation metadata hỗ trợ trace workflow.
- [ ] Payload không chứa secret hoặc dữ liệu nhạy cảm không cần thiết.
- [ ] Schema evolution có backward/forward compatibility policy.
- [ ] Consumer xử lý duplicate và retry an toàn.
- [ ] Unknown event versions được quarantine/alert thay vì bỏ qua âm thầm.
- [ ] Retention, compaction và archive được công bố.
- [ ] Event consumers có owner và freshness expectations.

### 5.3. Compatibility và deprecation

- [ ] Có thể deploy producer trước consumer hoặc ngược lại theo rollout plan.
- [ ] Breaking changes có versioned migration path.
- [ ] Consumer cũ được kiểm tra với payload mới.
- [ ] Consumer mới được kiểm tra với payload lịch sử.
- [ ] Có inventory consumers trước khi xóa field/event.
- [ ] Deprecation window được thông báo và đo usage.
- [ ] Có cách rollback nếu consumer không tương thích.
- [ ] Contract thay đổi có release notes và owner.

### 5.4. Failure semantics

- [ ] Xác định request có thể timeout sau khi server đã commit hay không.
- [ ] Client retry không tạo duplicate business operation.
- [ ] Event delivery semantics, ordering và retention được hiểu.
- [ ] Dead-letter/quarantine có quy trình xử lý và replay.
- [ ] Poison messages không chặn vô hạn toàn bộ partition/workflow.
- [ ] Backpressure và consumer lag có giới hạn/alert.
- [ ] Có policy cho late events và out-of-order updates.
- [ ] Compensation được định nghĩa cho workflow không thể atomic.

## 6. Checklist C — Dữ liệu và consistency

### 6.1. Data model và invariant

- [ ] Entity/aggregate boundaries phản ánh invariant cần bảo vệ.
- [ ] Unique constraints và foreign keys được dùng phù hợp.
- [ ] Transaction boundary không vượt quá mức có thể đảm bảo.
- [ ] Concurrent updates có optimistic/pessimistic locking strategy.
- [ ] State transitions không hợp lệ bị từ chối ở write path.
- [ ] Financial values dùng decimal/minor units và currency rõ.
- [ ] Timezone, timestamp và business date semantics thống nhất.
- [ ] Soft delete/hard delete có ý nghĩa được định nghĩa.
- [ ] Historical corrections không ghi đè mất audit trail.
- [ ] Data ownership không bị phá bởi cross-service writes.

### 6.2. Consistency model

- [ ] Mỗi use case ghi rõ strong, read-your-writes hoặc eventual consistency.
- [ ] Read model có freshness target.
- [ ] Stale reads có cách xử lý ở UI/API.
- [ ] Giao dịch quan trọng không dựa vào projection có thể trễ.
- [ ] Có idempotency và dedup cho consumers.
- [ ] Version/sequence checks ngăn event cũ ghi đè state mới.
- [ ] Saga/process manager có timeout, retries và compensation.
- [ ] Workflow stuck có thể phát hiện và can thiệp.
- [ ] Cross-region consistency và conflict resolution được định nghĩa.
- [ ] Có reconciliation cho dữ liệu quan trọng.

### 6.3. Database migrations

- [ ] Migration được version và kiểm soát trong source control.
- [ ] Migration đã thử trên dữ liệu có quy mô đại diện.
- [ ] Locking, index build và query plan được đánh giá.
- [ ] Dùng expand–migrate–contract khi cần backward compatibility.
- [ ] Backfill có batch size, throttle, checkpoint và resume.
- [ ] Migration có backup/recovery plan phù hợp.
- [ ] Destructive changes có approval theo risk policy.
- [ ] Rollback/roll-forward strategy được mô tả.
- [ ] Old/new application versions có thể coexist trong rollout window.
- [ ] Data integrity được kiểm trước và sau migration.

### 6.4. Data lifecycle và privacy

- [ ] Data classification được gán.
- [ ] Data minimization được áp dụng.
- [ ] Retention period có owner và lý do.
- [ ] Deletion/correction truyền tới replicas, caches, search và archives theo policy.
- [ ] Backup restore không vô tình hồi sinh dữ liệu đã xóa mà không áp deletion ledger.
- [ ] Encryption at rest/in transit được cấu hình.
- [ ] Key rotation và access audit có quy trình.
- [ ] Data residency/cross-border transfer được đánh giá.
- [ ] Sensitive data không xuất hiện trong logs/traces/metrics.
- [ ] Non-production data được sanitize hoặc kiểm soát quyền truy cập.

### 6.5. Backup và restore

- [ ] Backup cadence phù hợp RPO.
- [ ] Backup có encryption và access restrictions.
- [ ] Backup nằm ngoài failure domain cần bảo vệ.
- [ ] Restore procedure được tài liệu hóa.
- [ ] Đã thử restore thực tế, không chỉ kiểm tra job success.
- [ ] Có kiểm tra integrity/checksum và reconciliation.
- [ ] Backup retention đáp ứng business/legal requirements.
- [ ] Có owner và escalation cho backup failures.
- [ ] Restore time đã đo và phù hợp RTO.
- [ ] Dependencies cần cho restore (keys, schemas, images, configs) cũng được bảo vệ.

## 7. Checklist D — Security và trust boundaries

### 7.1. Identity và access

- [ ] Mỗi workload có identity riêng.
- [ ] Least privilege được áp dụng.
- [ ] Không dùng shared admin credentials cho runtime.
- [ ] Human access và machine access được tách.
- [ ] Secrets được lưu trong secret manager và không commit vào source.
- [ ] Token/credential có rotation và expiry.
- [ ] Service-to-service authentication được xác minh.
- [ ] Authorization kiểm tra resource và tenant scope.
- [ ] Privileged operations có audit và approval phù hợp.
- [ ] Break-glass có TTL, MFA, logging và post-incident review.

### 7.2. Network và workload isolation

- [ ] Ingress/egress được giới hạn theo nhu cầu.
- [ ] Database/broker không public ngoài yêu cầu đã duyệt.
- [ ] Network policies/segmentation được kiểm tra.
- [ ] Workloads nhạy cảm có isolation phù hợp.
- [ ] TLS/mTLS được dùng theo threat model.
- [ ] Container không chạy privileged/root nếu không có lý do được duyệt.
- [ ] Image đến từ registry tin cậy và được pin digest khi cần.
- [ ] Runtime security/audit có coverage.
- [ ] Egress tới external providers được allowlist hoặc giám sát.
- [ ] Không để debug/admin endpoint public.

### 7.3. Supply chain và dependency

- [ ] Dependencies có version được quản lý.
- [ ] Secret scanning, SCA và image scanning được chạy.
- [ ] SBOM/provenance được tạo khi cần.
- [ ] Build/deploy credentials không bị lộ cho untrusted pull requests.
- [ ] Artifact bất biến và truy ngược được commit/build.
- [ ] Critical vulnerabilities có remediation/exception policy.
- [ ] Base images được cập nhật theo lifecycle.
- [ ] CI workflow permissions được giới hạn.
- [ ] Policy changes có review riêng.
- [ ] Third-party integrations có threat/risk review.

## 8. Checklist E — Phát hành và thay đổi an toàn

### 8.1. Build và artifact

- [ ] Build tái lập hoặc provenance đủ để truy vết.
- [ ] Unit/integration/contract tests phù hợp rủi ro.
- [ ] Security/dependency/secret scans pass theo policy.
- [ ] Artifact có version/digest bất biến.
- [ ] Build metadata gắn với commit và pipeline identity.
- [ ] Không deploy mutable tag không kiểm soát.
- [ ] Migration/config/artifact versions được liên kết trong release record.
- [ ] Có kiểm tra license/compliance nếu cần.

### 8.2. Release plan

- [ ] Thay đổi có owner và phạm vi.
- [ ] Risk class được xác định.
- [ ] Dependencies và deployment order được ghi.
- [ ] Rollout strategy được chọn: rolling, canary, blue-green hoặc staged.
- [ ] Blast radius ban đầu được giới hạn.
- [ ] Feature flag/kill switch có owner và default an toàn.
- [ ] Maintenance window được dùng khi có lý do.
- [ ] Rollback/fix-forward plan phù hợp schema và side effects.
- [ ] Runbook/communication được cập nhật nếu hành vi vận hành thay đổi.
- [ ] Có điều kiện dừng/abort rõ.

### 8.3. Progressive delivery

- [ ] Canary có cohort/traffic scope xác định.
- [ ] Có baseline để so sánh trước/sau.
- [ ] Health checks không chỉ dựa vào process liveness.
- [ ] SLO và business metrics được theo dõi.
- [ ] Error budget burn hoặc guardrails có threshold.
- [ ] Rollout dừng khi metric vượt ngưỡng.
- [ ] Auto rollback chỉ bật khi rollback an toàn.
- [ ] Có kiểm tra dữ liệu và side effects.
- [ ] Có cách tăng traffic từng bước.
- [ ] Người trực biết cách pause/rollback.

### 8.4. Database và contract release

- [ ] Old/new app versions tương thích schema trong giai đoạn deploy.
- [ ] Event producers/consumers có compatibility test.
- [ ] Migration không phá consumer đang chạy.
- [ ] Backfill có rate limit và progress visibility.
- [ ] Destructive contract/schema removal diễn ra sau deprecation.
- [ ] Có thể rollback app mà không làm hỏng schema mới.
- [ ] Event replay không kích hoạt external side effects.
- [ ] Cutover read/write targets được điều phối.

### 8.5. Change governance

- [ ] Standard changes có tiêu chí preapproved rõ.
- [ ] High-risk changes được route tới đúng owner/reviewer.
- [ ] Approval gắn với commit/artifact/plan cụ thể.
- [ ] Exceptions có scope, reason, expiry và compensating controls.
- [ ] Emergency changes có incident ID và audit.
- [ ] Policy engine được test và rollout như software.
- [ ] Có record ai thay đổi, khi nào và kết quả.
- [ ] Post-deploy verification có owner.

## 9. Checklist F — Reliability và hiệu năng

### 9.1. SLO và error budget

- [ ] Service/capability có SLI/SLO phù hợp người dùng.
- [ ] Availability, latency, correctness và freshness được xem xét.
- [ ] SLO có window và measurement source rõ.
- [ ] Error budget policy có action cụ thể.
- [ ] SLO liên kết business journey, không chỉ health endpoint.
- [ ] Có phân biệt lỗi do service và dependency.
- [ ] Có dashboard và alert owner.
- [ ] SLO được review khi traffic/product behavior thay đổi.

### 9.2. Resilience patterns

- [ ] Timeout được đặt ở từng hop.
- [ ] Deadline propagation không vượt end-to-end budget.
- [ ] Retry có giới hạn, backoff và jitter.
- [ ] Không retry non-idempotent operations mù.
- [ ] Circuit breaker có threshold và recovery behavior.
- [ ] Bulkhead bảo vệ tài nguyên quan trọng.
- [ ] Queue/backpressure có capacity limit.
- [ ] Rate limiting bảo vệ downstream.
- [ ] Graceful degradation được định nghĩa.
- [ ] Fallback không trả dữ liệu sai như thể là authoritative.

### 9.3. Capacity và performance

- [ ] Traffic assumptions và peak profile được ghi.
- [ ] Load test dùng data/traffic shape đại diện.
- [ ] CPU/memory requests/limits phù hợp.
- [ ] Autoscaling metric và stabilization được thử.
- [ ] DB connection pool không vượt capacity.
- [ ] Queue throughput và consumer lag có budget.
- [ ] Hot partitions/keys được đánh giá.
- [ ] Cache hit ratio và eviction behavior được đo.
- [ ] Network egress/connection limits được kiểm.
- [ ] Capacity khi mất một node/zone vẫn đáp ứng mục tiêu.

### 9.4. Correctness và business invariants

- [ ] Không duplicate charge/reservation/fulfillment do retry.
- [ ] Không oversell hoặc mất đơn đã thanh toán.
- [ ] State transitions hợp lệ.
- [ ] Financial amounts/currency/rounding được kiểm.
- [ ] Reconciliation với ledger/provider có lịch.
- [ ] Out-of-order/late events được xử lý.
- [ ] Idempotency records có retention đủ.
- [ ] Workflow stuck có alert và manual recovery.
- [ ] Business metrics được xác nhận sau rollout.
- [ ] Có kiểm tra dữ liệu sau incident.

## 10. Checklist G — Observability và vận hành hàng ngày

### 10.1. Logs

- [ ] Logs có cấu trúc và correlation fields.
- [ ] Không log secrets, credentials, card data hoặc PII không cần thiết.
- [ ] Log levels phù hợp môi trường.
- [ ] Error logs có context và remediation.
- [ ] Retention và archive có policy.
- [ ] Log volume/cost được theo dõi.
- [ ] Sampling/dedup không loại bỏ audit evidence cần thiết.
- [ ] Có cách tìm một workflow xuyên nhiều services.

### 10.2. Metrics

- [ ] RED metrics (Rate, Errors, Duration) cho request services.
- [ ] USE metrics (Utilization, Saturation, Errors) cho resources.
- [ ] Queue age/lag, retries, DLQ và processing rate.
- [ ] Business outcomes và workflow completion.
- [ ] Projection freshness/read model lag nếu có.
- [ ] Dependency health và connection pool.
- [ ] Cardinality được kiểm soát.
- [ ] Metric labels không chứa raw user/order IDs.
- [ ] Dashboards có owner và được review.
- [ ] Alert thresholds dựa trên SLO hoặc hành động cụ thể.

### 10.3. Tracing

- [ ] Trace context được propagate qua synchronous calls.
- [ ] Async correlation được truyền qua message headers.
- [ ] Sampling strategy phù hợp traffic và incident needs.
- [ ] Span names/attributes có quy ước.
- [ ] Sensitive data không nằm trong span attributes.
- [ ] Trace retention/access có kiểm soát.
- [ ] Có cách xem critical path và dependency latency.
- [ ] Sampling bias được hiểu nếu dùng traces cho analytics.

### 10.4. Alert quality

- [ ] Alert có severity và owner.
- [ ] Alert gắn với user/business impact.
- [ ] Có runbook/action link.
- [ ] Không alert chỉ vì metric tăng mà không có hành động.
- [ ] Dedup/grouping tránh alert storm.
- [ ] Paging ngoài giờ dành cho vấn đề cần phản ứng ngay.
- [ ] Có escalation nếu owner không phản hồi.
- [ ] Alert test/drill được thực hiện.
- [ ] Có review false positives và missed incidents.
- [ ] Alert routing cập nhật khi ownership đổi.

## 11. Checklist H — Incident response và khả năng phục hồi

### 11.1. Incident readiness

- [ ] Có service owner và incident contact.
- [ ] Severity/impact definitions rõ.
- [ ] Có runbook cho top failure modes.
- [ ] Có cách disable feature/traffic/consumer an toàn.
- [ ] Có access khẩn cấp đã chuẩn bị.
- [ ] Có communication path tới stakeholder.
- [ ] Logs/metrics/traces đủ để xác định blast radius.
- [ ] Có quy trình evidence preservation khi cần.
- [ ] Có cách phân biệt symptom và root cause.
- [ ] Có post-incident review và action tracking.

### 11.2. RPO và RTO

- [ ] RPO được business owner chấp nhận.
- [ ] RTO được đo trong restore/DR drill.
- [ ] Backup/replication đáp ứng RPO.
- [ ] Restore dependencies được liệt kê.
- [ ] DNS, certificates, secrets, IAM và network có recovery plan.
- [ ] Event history/archive/snapshots có coverage.
- [ ] Derived data có rebuild strategy.
- [ ] Cross-region failover có consistency/conflict plan.
- [ ] Có quy trình failback sau khi region chính phục hồi.
- [ ] Người ra quyết định failover/failback được xác định.

### 11.3. Disaster recovery drill

- [ ] Scenario và success criteria được xác định trước.
- [ ] Drill dùng môi trường và data volume đại diện.
- [ ] Đo thời gian detect, diagnose, restore, validate và cutover.
- [ ] Kiểm integrity và business invariants sau restore.
- [ ] Kiểm deletion/privacy records không bị hồi sinh.
- [ ] Kiểm downstream consumers và external integrations.
- [ ] Ghi manual steps và hidden dependencies.
- [ ] Có người không phải tác giả runbook thực hiện.
- [ ] Findings có owner/deadline.
- [ ] Drill được lặp lại sau thay đổi lớn.

### 11.4. Backup không đồng nghĩa recovery

Backup job xanh chỉ chứng minh job đã chạy theo trạng thái hệ thống báo. Nó không chứng minh bản backup đọc được, khóa giải mã còn dùng được, schema tương thích, restore đủ nhanh hoặc dữ liệu sau restore đúng.

Readiness cần bằng chứng restore và reconciliation thực tế. Với event-sourced system, kiểm coverage lịch sử và upcasters. Với database truyền thống, kiểm PITR, transaction logs và dependencies. Với search/cache/read models, xác định rebuild hay restore là lựa chọn phù hợp.

## 12. Checklist I — Cost, capacity và hiệu quả vận hành

- [ ] Resource có owner/team/cost center tags.
- [ ] Direct và shared costs được phân biệt.
- [ ] Usage driver phù hợp CPU, memory, storage, network và observability.
- [ ] Idle capacity và resilience headroom có owner.
- [ ] Cost per request/journey được đo nếu có ý nghĩa.
- [ ] Retries/failures không bị ẩn khỏi unit economics.
- [ ] Budget/forecast/anomaly alerts có owner.
- [ ] Logs/traces/metrics retention có policy.
- [ ] Autoscaling không gây churn hoặc overprovisioning.
- [ ] Optimization được đo trước/sau cùng workload profile.
- [ ] Không hy sinh SLO/security/privacy để giảm bill.
- [ ] Phân biệt allocated, marginal và avoidable cost.

## 13. Checklist J — Developer experience và maintainability

- [ ] Service template/golden path có defaults an toàn.
- [ ] Local development có hướng dẫn rõ.
- [ ] Tests chạy được trong CI với thời gian hợp lý.
- [ ] Developer hiểu và xử lý được policy failures.
- [ ] API/event contracts có documentation.
- [ ] Dependency upgrades có owner và cadence.
- [ ] Code ownership và review rules rõ.
- [ ] Không có quy trình thủ công lặp lại có thể tự động hóa an toàn.
- [ ] Developer không cần quyền production rộng cho công việc thường ngày.
- [ ] Onboarding không phụ thuộc quá nhiều vào truyền miệng.
- [ ] Runbooks và ADR dễ tìm.
- [ ] Technical debt có owner và kế hoạch.

Quy trình vận hành an toàn nhưng quá khó dùng sẽ tạo áp lực bypass. Developer experience là một phần của control design: đường đúng cần dễ hiểu, nhanh và có phản hồi hữu ích.

## 14. Readiness gate trước production

Không nên cộng điểm tất cả mục rồi tự động launch. Có thể dùng bốn gate với owner rõ.

### Gate 1 — Boundary readiness

- [ ] Domain/service owner được xác định.
- [ ] Data ownership và dependency map rõ.
- [ ] Critical invariants có nơi thực thi.
- [ ] API/event contracts có compatibility rules.
- [ ] Blast radius đã được đánh giá.

### Gate 2 — Data and security readiness

- [ ] Data classification, privacy và retention được duyệt.
- [ ] Access control và workload identity hoạt động.
- [ ] Backup/restore đáp ứng RPO/RTO.
- [ ] Migration/replay có kế hoạch.
- [ ] Financial/business correctness được kiểm nếu áp dụng.

### Gate 3 — Release readiness

- [ ] Build/test/scan/artifact provenance đạt policy.
- [ ] Rollout/canary/abort criteria rõ.
- [ ] Rollback/fix-forward tương thích schema và side effects.
- [ ] Feature flags và emergency controls có owner.
- [ ] Release evidence gắn với artifact cụ thể.

### Gate 4 — Operations readiness

- [ ] SLO, dashboard, alerts và on-call route sẵn sàng.
- [ ] Runbooks và incident response được thử.
- [ ] Capacity và dependency failure modes được kiểm.
- [ ] DR/recovery strategy có bằng chứng.
- [ ] Ownership chuyển giao tới đội trực vận hành.

<badge color="warning">No-go condition</badge> Nếu còn Critical Fail liên quan unauthorized access, data loss, duplicate financial side effects, tenant isolation, destructive migration hoặc không có cách phục hồi dữ liệu quan trọng, cần xử lý trước launch hoặc có quyết định rủi ro minh bạch từ đúng người có thẩm quyền. Không dùng số lượng mục Pass để override một rủi ro nghiêm trọng.

## 15. Mẫu ghi nhận finding

Mỗi finding cần đủ thông tin để biến thành hành động:

| Trường | Nội dung |
|---|---|
| Finding ID | Mã duy nhất |
| Category | Boundary / Data / Release / Operations |
| Requirement | Mục checklist liên quan |
| Status | Pass / Partial / Fail / N/A / Unknown |
| Evidence | Link PR, test, dashboard, runbook, restore report |
| Impact | Người dùng, dữ liệu, availability, security, cost |
| Severity | Critical / High / Medium / Low |
| Owner | Team/người chịu trách nhiệm |
| Mitigation | Hành động giảm rủi ro tạm thời |
| Due date | Thời hạn xử lý |
| Decision | Block / Accept risk / Defer / N/A |
| Approver | Người có thẩm quyền với loại rủi ro |
| Review date | Ngày xem xét lại |

Ví dụ:

~~~text
Finding: DATA-014
Category: Data and Recovery
Requirement: Restore test completed
Status: Partial
Impact: Order history could exceed RTO after regional loss
Evidence: Backup job dashboard only; no full restore drill
Severity: High
Owner: Order Platform
Mitigation: Restore latest snapshot into isolated environment
Due date: Before production launch
Decision: Block readiness gate until evidence exists
~~~

Đây là ví dụ giả định. Evidence nên trỏ tới nguồn thực, không chỉ ghi “đã kiểm tra”.

## 16. Rủi ro thường bị bỏ sót giữa các nhóm

### 16.1. Ranh giới đúng nhưng data boundary sai

Service A có ownership rõ nhưng Service B vẫn được quyền ghi trực tiếp vào bảng của A. Khi A thay schema, B hỏng ngoài contract. Cần kiểm quyền database, dependency scans và access logs, không chỉ đọc sơ đồ kiến trúc.

### 16.2. API contract ổn nhưng workflow không có idempotency

Client timeout sau khi server commit và gửi lại request. Nếu command không có idempotency key/business uniqueness, hệ thống có thể tạo hai đơn hoặc capture hai lần. Test crash window và retry behavior.

### 16.3. Deploy thành công nhưng read model stale

Pod Ready và HTTP 200 không chứng minh projection đã xử lý hết event. Kiểm lag, business outcomes và reconciliation.

### 16.4. Rollback code nhưng không rollback được data

Migration đã drop field hoặc thay semantics. Bản app cũ không thể đọc schema mới. Dùng expand–migrate–contract và xác định roll-forward/restore path.

### 16.5. Monitoring có nhưng không ai nhận alert

Alert không có owner hoặc on-call routing sai vẫn là gap. Kiểm notification delivery, escalation và người thực sự trực.

### 16.6. Backup có nhưng key/identity không còn

Backup được mã hóa nhưng key đã rotate/xóa; restore role không có quyền; image/schema version không còn. Recovery inventory phải gồm keys, IAM, artifacts và dependencies.

### 16.7. Security policy tạo outage

Admission rule sai có thể chặn scale-out hoặc recovery. Policy engine cần staging, audit mode, rollback và break-glass có kiểm soát.

### 16.8. Cost optimization làm giảm resilience

Scale down node pool có thể tiết kiệm nhưng làm hệ thống không chịu được zone failure. Cost review phải đi cùng capacity/SLO review.

## 17. Tình huống thực hành — Tách Order và Payment

Một team muốn tách Payment khỏi Order vì release cadence khác nhau.

**Ranh giới**
- Payment intent, authorization, capture và refund do service nào sở hữu?
- Order có quyền sửa payment tables không?
- Domain events và integration contracts là gì?
- Workflow checkout có process manager/saga owner không?

**Dữ liệu**
- Payment ledger có authoritative không?
- Idempotency/business keys nào ngăn duplicate capture?
- Có đối soát với PSP?
- PII/payment tokens được lưu ở đâu?

**Phát hành**
- Có backward-compatible contract rollout?
- Payment và Order có thể deploy độc lập?
- Migration dữ liệu cũ có checkpoint và reconciliation?
- Có canary và rollback/compensation?

**Vận hành**
- Có dashboard payment outcome và unknown state?
- Alert khi capture không đối soát?
- On-call owner rõ?
- RPO/RTO của ledger được thử?

Kết quả review phải nêu boundary mới có giảm coupling hay chỉ thêm network hop và distributed transaction.

## 18. Tình huống thực hành — Thay đổi event schema

Order Service muốn thêm currency và đổi tên một field trong event được nhiều consumers sử dụng.

1. Ai sở hữu schema và compatibility policy?
2. Consumers hiện tại là những ai?
3. Field mới có default/historical semantics không?
4. Có versioning hoặc upcaster?
5. Producer và consumer có thể rollout theo thứ tự nào?
6. Event history cũ có thể đọc bằng code mới?
7. Có test với payload cũ và mới?
8. Unknown version có quarantine và alert?
9. Có kế hoạch deprecate field cũ?
10. Có thể rollback producer mà không làm consumer hỏng?

Không xóa field cũ ngay sau khi producer mới deploy; chờ consumer inventory và usage evidence.

## 19. Tình huống thực hành — Backup chưa từng restore

Một service có backup hằng ngày và dashboard job success. Chưa ai thử restore. Business yêu cầu RPO 15 phút và RTO 60 phút.

- Backup cadence có đáp ứng RPO 15 phút không?
- Có transaction logs/PITR không?
- Restore full data mất bao lâu?
- Encryption keys và IAM có sẵn ở region dự phòng không?
- Schema migration có chạy được trên backup?
- Downstream projections cần rebuild hay restore?
- Có cách validate record counts và business invariants?
- Ai ra quyết định failover/failback?

Không thể kết luận RTO/RPO đạt chỉ từ trạng thái backup job. Cần drill có đo thời gian và kiểm correctness.

## 20. Tình huống thực hành — Rollback có thể nguy hiểm

Một release đổi schema từ field amount sang amount_minor_units, đồng thời app mới đã ghi dữ liệu theo semantics mới. Sau 20 phút, error rate tăng và team muốn rollback image cũ.

- App cũ có đọc schema mới không?
- Dữ liệu đã ghi có thể chuyển ngược mà không mất precision?
- Có dual-read/dual-write hoặc compatibility window?
- Có thể pause rollout và fix-forward?
- Có migration rollback an toàn không?
- Có payment/financial invariants cần reconcile?
- Ai là owner quyết định rollback hay roll-forward?

Không mặc định deploy lại image cũ luôn là rollback hợp lệ.

## 21. Tình huống thực hành — Projection lag sau campaign

Search và Customer History projections chậm 20 phút trong campaign lớn. Command path vẫn hoạt động.

- Queue lag/oldest event age và throughput là bao nhiêu?
- Có hot partition hoặc consumer rebalance?
- Read model stale ảnh hưởng user journey nào?
- Có thể tăng consumer capacity mà không overload DB?
- Retry/DLQ có đang làm backlog nặng hơn?
- Có read-your-writes fallback cho order mới?
- Có thể degrade search/filter nào an toàn?
- Có replay/recovery plan nếu consumer bỏ sót event?
- Khi nào cần pause campaign hoặc giảm traffic?

Không chỉ scale consumer vô hạn; phải xác định bottleneck và tác động tới live dependencies.

## 22. Tình huống thực hành — Chi phí cao nhưng owner không rõ

Cluster cost tăng 35%, billing tags chỉ có environment, không có service/team. Platform nói product teams chịu trách nhiệm; product teams nói cluster là shared.

- Có service catalog và owner metadata?
- Có per-workload CPU/memory/storage/network telemetry?
- Có direct/shared/unallocated pools?
- Idle headroom và system overhead được tách?
- Có cost driver và confidence?
- Cost per business journey có đo được?
- Có dispute workflow và owner remediation?
- Có baseline/forecast theo growth?

Bước đầu là khôi phục cost visibility và ownership. Không chargeback bằng tỷ lệ tùy tiện chỉ để phân bổ đủ tổng bill.

## 23. Tình huống thực hành — Service mới phụ thuộc năm services khác

Một service mới cần gọi Customer, Pricing, Inventory, Payment và Notification trong một request.

- Có cần tất cả calls synchronous không?
- Critical path có vượt latency budget?
- Failure của Notification có nên làm checkout fail?
- Có thể dùng event-driven workflow cho bước không cần response ngay?
- Timeout/retry có gây retry amplification?
- Có bulkhead và circuit breaker?
- Ai sở hữu saga/workflow?
- Có correlation/tracing xuyên service?
- Có contract tests và compatibility plan?
- Có graceful degradation và compensation?

Mục tiêu là giảm coupling trong runtime, không chỉ giảm số đường nối trên sơ đồ.

## 24. Tình huống thực hành — Disaster recovery đa vùng

Region chính mất hoàn toàn. Region dự phòng có replication trễ 8 phút; business yêu cầu RPO 5 phút.

- RPO hiện tại có vượt mục tiêu?
- Nguồn authoritative nào xác định giao dịch đã commit?
- Có dual-writer/split-brain risk?
- Có conflict resolution cho aggregate versions?
- Secrets, keys, certificates và IAM đã sẵn sàng?
- Event archive/snapshots có đủ coverage?
- DNS/failover và dependency providers hoạt động?
- Có reconciliation cho payment/order?
- Ai chấp thuận failover và failback?
- Business có chấp nhận degraded mode không?

Nếu replication lag vượt RPO, phải ghi nhận data-loss exposure và quyết định theo incident/business process; không tuyên bố đáp ứng mục tiêu bằng cách đổi cách đo.

## 25. Ma trận quyết định Go / Conditional Go / No-Go

| Quyết định | Điều kiện |
|---|---|
| **Go** | Không còn Critical/High gaps chưa xử lý; owner, evidence, rollout và operations sẵn sàng |
| **Conditional Go** | Còn gap phạm vi nhỏ, mitigation cụ thể, owner, expiry/deadline và approver phù hợp; không vi phạm control bắt buộc |
| **No-Go** | Có Critical gap, dữ liệu/quyền/side effects không an toàn, không có rollback/recovery cần thiết hoặc chưa có người chịu trách nhiệm |

Conditional Go phải nêu điều kiện launch, scope traffic/tenant/region, risk owner, approver, compensating controls, expiry/review date, trigger dừng/rollback và kế hoạch khắc phục đầy đủ. Không dùng Conditional Go để kéo dài ngoại lệ vô thời hạn.

## 26. Mẫu Architecture Readiness Record

~~~yaml
review:
  id: "ARR-2026-0403"
  subject: "order-workflow"
  environment: "production"
  owner_team: "team-order"
  reviewer: "architecture-review"
  reviewed_at: "2026-11-12"

scope:
  domains:
    - order
    - payment
    - inventory
  regions:
    - apac
  data_classification: "confidential"
  criticality: "tier-1"

targets:
  availability_slo: "99.9%"
  rpo: "5m"
  rto: "60m"

gates:
  boundaries: "pass"
  data_security: "partial"
  release: "pass"
  operations: "pass"

findings:
  - id: "DATA-014"
    severity: "high"
    status: "open"
    owner: "team-order"
    due: "before-launch"
    mitigation: "restore drill in isolated environment"

decision:
  result: "conditional-go"
  approver: "accountable-risk-owner"
  expires_at: "2026-11-20"
~~~

Đây là cấu trúc minh họa, không phải schema tiêu chuẩn. Môi trường thực cần xác định nơi lưu, quyền sửa, audit history, allowed values và cách tự động kiểm expiry.

## 27. Cách tổ chức buổi review hiệu quả

### Trước buổi review

- Người đề xuất gửi scope, sơ đồ, ADR và thay đổi cụ thể.
- Service owner cung cấp catalog, dependencies và on-call.
- Data owner cung cấp classification, consistency, retention và migration plan.
- SRE cung cấp SLO, capacity, recovery và runbooks.
- Security/Compliance tham gia theo risk scope.
- Reviewers đọc trước và ghi câu hỏi dựa trên evidence.

### Trong buổi review

1. Xác nhận business goal và scope.
2. Xem boundary/ownership trước khi bàn implementation.
3. Theo luồng dữ liệu từ command tới storage, event, projection và consumer.
4. Đi qua rollout và failure scenarios.
5. Kiểm RPO/RTO, observability và incident ownership.
6. Phân loại findings và quyết định gate.
7. Chốt owner, deadline, approver và evidence cần bổ sung.

### Sau buổi review

- Lưu quyết định và lý do.
- Gắn findings vào tracker có owner.
- Cập nhật ADR/service catalog nếu boundary thay đổi.
- Xác minh điều kiện Conditional Go trước expiry.
- Theo dõi post-launch metrics và incident.
- Review lại khi scope, data classification hoặc architecture thay đổi đáng kể.

Review không nên biến thành tranh luận sở thích công nghệ. Mọi yêu cầu cần liên hệ với invariant, risk, SLO, lifecycle hoặc chi phí vận hành.

## 28. Anti-pattern khi dùng checklist

1. Tick Pass mà không có evidence.
2. Xem Unknown như Pass.
3. Áp cùng checklist/threshold cho mọi workload.
4. Dùng tổng điểm để override Critical Fail.
5. Giao finding cho cá nhân nhưng không có team owner.
6. Ghi “fix later” không deadline.
7. Review thiết kế một lần rồi bỏ qua thay đổi lớn.
8. Chỉ kiểm CI mà không kiểm runtime/production access.
9. Coi Pod Ready là bằng chứng business workflow đúng.
10. Coi backup job success là bằng chứng restore được.
11. Có alert nhưng không có on-call route/runbook.
12. Rollback code mà không kiểm schema/data compatibility.
13. Không tính async consumers và background jobs trong blast radius.
14. Không kiểm privacy deletion trên archive/projections.
15. Gộp cost, reliability và security thành score không giải thích được.
16. Dùng N/A để tránh một kiểm soát khó.
17. Dùng Conditional Go không expiry.
18. Không cập nhật service catalog sau khi ownership đổi.
19. Không chạy lại checklist sau migration/region expansion.
20. Tạo quá nhiều checklist trùng nhau khiến teams không biết nguồn nào là chuẩn.

## 29. Checklist rút gọn cho thay đổi nhỏ

Với bug fix hoặc config change risk thấp:

- [ ] Owner và service scope rõ.
- [ ] Không mở rộng quyền hoặc data access.
- [ ] API/event/schema tương thích.
- [ ] Tests và policy checks pass.
- [ ] Artifact/config version được ghi.
- [ ] Rollout có health/business checks.
- [ ] Có pause/rollback action phù hợp.
- [ ] Dashboard/alert/on-call vẫn đúng.
- [ ] Không thay đổi retention/backup/security controls.
- [ ] Release evidence được lưu.

Nếu thay đổi chạm database destructive, payment logic, IAM, public exposure, data residency hoặc shared platform có blast radius lớn, chuyển sang risk-based review đầy đủ.

## 30. Checklist rút gọn trước production launch

- [ ] Có business owner và service owner.
- [ ] Domain boundaries và data ownership rõ.
- [ ] API/event contracts có compatibility.
- [ ] Authentication, authorization và tenant isolation đã kiểm.
- [ ] Data classification, privacy và retention đã duyệt.
- [ ] Backup/restore và RPO/RTO có bằng chứng.
- [ ] Build, tests, scans và immutable artifact đạt policy.
- [ ] Migration và rollout plan đã thử.
- [ ] Canary, stop criteria và rollback/fix-forward rõ.
- [ ] SLO, dashboards, alerts và on-call sẵn sàng.
- [ ] Runbooks và incident response đã thử.
- [ ] Capacity, dependency failure và DR đã đánh giá.
- [ ] Critical findings đã đóng hoặc có quyết định rủi ro hợp lệ.
- [ ] Người có thẩm quyền xác nhận readiness.

## 31. Chỉ số cải tiến sau review

| Chỉ số | Ý nghĩa |
|---|---|
| Critical findings before launch | Rủi ro nghiêm trọng phát hiện trước production |
| Escaped defects | Lỗi boundary/data/release phát hiện sau launch |
| Conditional Go age | Thời gian điều kiện chưa được đóng |
| Restore drill pass rate | Mức sẵn sàng khôi phục |
| SLO attainment | Kết quả người dùng sau triển khai |
| Change failure rate | Tỷ lệ thay đổi gây rollback/incident |
| Mean time to detect | Tốc độ phát hiện sự cố |
| Mean time to restore | Tốc độ phục hồi |
| Contract break incidents | Sự cố do compatibility |
| Unknown ownership spend | Chi phí chưa xác định owner |
| Alert actionability | Tỷ lệ alert dẫn tới hành động có ích |
| Repeated findings | Gap tái diễn giữa các service |

Không tối ưu số lượng findings thấp bằng cách giảm độ nghiêm túc của review. Giai đoạn đầu có nhiều findings có thể là dấu hiệu visibility được cải thiện.

## 32. Ghi nhớ cốt lõi

Một kiến trúc microservices sẵn sàng vận hành phải trả lời được bốn câu hỏi:

- **Ranh giới:** ai sở hữu capability, invariant và dữ liệu?
- **Dữ liệu:** nguồn sự thật, consistency, privacy, migration và recovery được bảo vệ ra sao?
- **Phát hành:** thay đổi được kiểm chứng, giới hạn blast radius, dừng và rollback thế nào?
- **Vận hành:** ai nhận alert, xử lý incident và phục hồi trong RPO/RTO?

Hãy dùng checklist như công cụ đối thoại dựa trên bằng chứng. Đánh dấu Pass khi có thể chỉ ra test, contract, dashboard, runbook, restore report hoặc quyết định cụ thể. Ghi Unknown/Partial thành action có owner và thời hạn. Phân loại rủi ro thay vì yêu cầu mọi service phải giống nhau.

**Readiness không phải số ô được tick. Readiness là khả năng chứng minh service có ranh giới và owner rõ, dữ liệu được bảo vệ, thay đổi có thể phát hành an toàn, và đội vận hành có thể phát hiện, xử lý, khôi phục khi điều xấu xảy ra.**