# Kiểm chứng sau triển khai và tự động dừng phát hành lỗi

## 1. Vì sao deployment thành công chưa có nghĩa là release thành công?

Một pipeline có thể build artifact, chạy unit test, tạo image và triển khai workload thành công nhưng ứng dụng vẫn lỗi khi nhận traffic thật. Pod có thể ở trạng thái Ready trong khi request checkout timeout; process có thể sống nhưng không kết nối được database; endpoint health trả HTTP 200 nhưng giao dịch nghiệp vụ tạo đơn hàng thất bại. Một bản phát hành chỉ nên được coi là thành công khi hệ thống sau deploy đáp ứng các tiêu chí kỹ thuật và nghiệp vụ đã xác định.

**Kiểm chứng sau triển khai (post-deployment verification) là bước xác nhận phiên bản mới hoạt động an toàn trong môi trường mục tiêu.** Tự động dừng phát hành (automatic release halt/abort) ngăn việc mở rộng rollout khi tín hiệu cho thấy phiên bản mới gây lỗi. Rollback có thể đưa workload về phiên bản trước, nhưng không phải lúc nào cũng an toàn hoặc đủ để khôi phục dữ liệu và trạng thái hệ thống.

Trong module **CLOUD_ARCHITECTURE**, delivery phải gắn với kiến trúc runtime, observability, data compatibility, resilience và vận hành. Một release gate tốt kiểm tra đúng hành trình người dùng, so sánh cohort mới/cũ, quan sát đủ thời gian, có ngưỡng rõ và xử lý được cả trường hợp rollout dở dang, dependency lỗi hoặc database migration không thể đảo ngược.

Sau bài học, bạn có thể:

- Phân biệt deployment health, application health và business health.
- Thiết kế post-deployment checks ở nhiều lớp từ process tới synthetic transaction.
- Chọn SLI, SLO, error budget và metric để quyết định tiếp tục hay dừng rollout.
- Triển khai progressive delivery với canary, blue/green và phased rollout.
- Thiết kế release gate, observation window, threshold và abort/rollback policy.
- So sánh lỗi của cohort mới với baseline để tránh nhầm lỗi nền.
- Xử lý schema migration, data compatibility, queue consumer và stateful workload khi rollback.
- Kiểm thử cơ chế tự dừng, thông báo, runbook và evidence cho từng release.

## 2. Phân biệt deployment, application và business health

Các lớp health trả lời những câu hỏi khác nhau:

| Lớp | Câu hỏi | Ví dụ kiểm chứng | Giới hạn |
| --- | --- | --- | --- |
| Deployment/platform | Tài nguyên đã được tạo và schedule đúng chưa? | Desired/available replicas, Pod Ready, task running, VM healthy | Workload có thể Ready nhưng chức năng lỗi |
| Process/runtime | Process có sống và phản hồi nội bộ không? | Liveness, startup probe, runtime metrics | Không chứng minh dependency hoặc request thật hoạt động |
| Application | API và dependency có phục vụ đúng không? | Readiness, smoke API, DB/cache connectivity | Có thể vẫn bỏ sót hành trình nghiệp vụ |
| User experience | Người dùng có hoàn thành thao tác không? | Synthetic journey, browser/API transaction, latency | Cần test an toàn, có dữ liệu và cleanup |
| Business outcome | Chỉ số nghiệp vụ có bất thường do release không? | Checkout success, payment authorization, order creation | Chậm hơn và chịu ảnh hưởng traffic mix |
| Security/compliance | Phiên bản mới có vi phạm policy không? | IAM denial spike, secret exposure, audit control, policy scan | Cần policy và detector riêng |

Một release có thể đạt deployment health nhưng trượt business health. Cổng phát hành nên có tín hiệu từ nhiều lớp và xác định lớp nào là hard gate.

### 2.1. Liveness không phải readiness

- **Liveness** trả lời process có cần được restart không.
- **Readiness** trả lời instance có sẵn sàng nhận traffic không.
- **Startup probe** cho phép workload khởi động lâu hơn trước khi áp dụng liveness/readiness theo một số nền tảng.
- **Synthetic check** kiểm tra hành vi qua đường đi gần với người dùng.

Không đưa mọi dependency vào liveness probe. Nếu database tạm chậm khiến tất cả Pod fail liveness, orchestrator có thể restart đồng loạt và làm sự cố nghiêm trọng hơn. Readiness có thể phản ánh dependency thiết yếu nhưng cần tránh loại bỏ mọi replica cùng lúc khi dependency chung đang lỗi.

### 2.2. Smoke test và business transaction

Smoke test kiểm tra một tập nhỏ chức năng thiết yếu sau deploy. Ví dụ:

- API health/version endpoint trả đúng build metadata.
- Tạo và đọc một bản ghi thử trong tenant canary.
- Đọc catalog, truy vấn database và cache.
- Worker nhận và xử lý một message thử.
- Upload/download object trong bucket kiểm thử.
- Xác nhận một payment sandbox hoặc payment authorization giả lập.

Smoke test phải tránh tạo side effect thật như gửi email cho khách, charge thẻ, tạo đơn giả trong báo cáo hoặc tiêu hao tồn kho. Dùng sandbox, synthetic account, idempotency key và cleanup có kiểm soát.

## 3. Xây dựng release verification plan

Trước khi triển khai, định nghĩa phiên bản mới sẽ được đánh giá bằng cách nào. Nếu tới lúc release mới chọn metric, nhóm có thể bỏ sót chỉ số quan trọng hoặc điều chỉnh ngưỡng để hợp thức hóa một rollout đang lỗi.

### 3.1. Release manifest

Mỗi lần phát hành nên có:

- Release ID, commit/build ID, artifact digest và version.
- Môi trường, region, cluster, account và service liên quan.
- Thay đổi cấu hình, feature flag và schema migration.
- Cohort/canary target, rollout steps và traffic weights.
- Owner, approver, change ticket và thời điểm bắt đầu.
- Expected impact, known risk và dependency cần theo dõi.
- SLI/SLO, hard gate, warning threshold và observation window.
- Abort, rollback hoặc forward-fix procedure.

Release ID nên xuất hiện trong deployment event, log, trace, metric annotation và incident record để so sánh đúng cohort.

### 3.2. Verification matrix

| Lớp kiểm chứng | Kiểm tra | Điều kiện tiếp tục |
| --- | --- | --- |
| Artifact | Digest/signature, SBOM, provenance và config version | Đúng artifact đã phê duyệt |
| Platform | Replica, readiness, resource, restart, scheduling | Đủ capacity và không có lỗi rollout |
| Application | Smoke API, dependency, startup, error log | Critical endpoint hoạt động |
| User path | Synthetic transaction và journey chính | Hoàn tất với latency/error trong ngưỡng |
| SLO | Error rate, latency, availability, queue age | Không vi phạm hard gate hoặc burn budget quá nhanh |
| Data | Schema compatibility, read/write, migration, replication | Invariant và compatibility được giữ |
| Security | IAM, secret, policy, authz/authn, audit | Không có regression nghiêm trọng |
| Operations | Alert, dashboard, rollback automation, on-call | Người vận hành có thể phát hiện và xử lý |

### 3.3. Pre-deployment baseline

Ghi lại baseline ngay trước rollout: traffic, success rate, latency percentile, saturation, queue backlog, dependency health và business KPI. Baseline cần cùng điều kiện đo với cohort mới. Nếu giờ cao điểm đến đúng lúc deploy, so sánh thô trước/sau có thể gán nhầm tác động tải cho release.

Khi có control cohort chạy phiên bản cũ, so sánh phiên bản mới/cũ cùng khoảng thời gian và cùng traffic segment giúp cô lập tác động tốt hơn. Cần đảm bảo phân phối traffic và workload mix không quá khác nhau.

## 4. Chọn metric làm release gate

Release gate cần đo điều người dùng cảm nhận và giới hạn hệ thống, không chỉ nhìn CPU hay trạng thái instance.

### 4.1. RED metrics cho service

- **Rate:** số request hoặc operation đến mỗi giây.
- **Errors:** số lượng/tỷ lệ request lỗi, timeout, rejected hoặc retry.
- **Duration:** thời gian xử lý, đặc biệt p95/p99.

Có thể bổ sung saturation như CPU throttling, memory pressure, thread/connection pool wait, database lock, queue age và downstream rate limit.

### 4.2. SLI và SLO

SLI là cách đo mức dịch vụ đạt được; SLO là mục tiêu cho SLI trong một cửa sổ thời gian. Ví dụ:

- 99,9% request checkout thành công trong rolling 30 phút.
- p95 latency dưới 250 ms, p99 dưới 800 ms.
- 99% job email bắt đầu xử lý trong 60 giây.
- Tỷ lệ payment authorization thành công không suy giảm vượt biên đã định sau khi loại trừ lỗi từ payment provider theo policy đo.

Đây chỉ là ví dụ; mục tiêu thật phải được owner nghiệp vụ phê duyệt và phản ánh traffic/workload.

### 4.3. Error budget và burn rate

Error budget là phần lỗi được cho phép theo SLO. Burn rate cho biết tốc độ tiêu hao budget so với tốc độ tương ứng với SLO. Khi một phiên bản mới làm burn rate tăng mạnh, pipeline có thể dừng rollout trước khi toàn bộ budget bị tiêu hết.

Không lấy error budget tổng của tháng để bỏ qua một lỗi critical trong vài phút. Có thể đặt alert nhanh theo short window và xác nhận bằng long window nhằm phát hiện sự cố mà giảm false positive.

### 4.4. Metric theo cohort và release

Gắn metric dimension có cardinality kiểm soát như service, version, release channel, region và environment. Tránh gắn request ID hoặc user ID làm metric label. Nếu không phân biệt được cohort mới/cũ, tín hiệu của phiên bản lỗi có thể bị hòa tan trong phần lớn traffic ổn định.

Với canary rất nhỏ, số lượng request có thể thấp khiến percentile không đáng tin. Cần minimum sample count, confidence interval hoặc thời gian quan sát phù hợp; không quyết định chỉ từ một vài request.

## 5. Progressive delivery và phạm vi rollout

Progressive delivery mở rộng mức tiếp xúc của phiên bản theo từng bước, dùng kiểm chứng để quyết định có tiếp tục hay dừng.

~~~mermaid
flowchart TD
    Build["Build + security/test gates"] --> Deploy["Deploy candidate"]
    Deploy --> Smoke["Platform + smoke checks"]
    Smoke --> Gate1{"Hard gates pass?"}
    Gate1 -->|No| Halt["Halt rollout / investigate"]
    Gate1 -->|Yes| Canary["Route small canary cohort"]
    Canary --> Observe["Observe SLI/SLO and business signals"]
    Observe --> Gate2{"Within thresholds?"}
    Gate2 -->|No| Abort["Abort / rollback or forward-fix"]
    Gate2 -->|Yes| Expand["Increase traffic / rollout step"]
    Expand --> Final{"Full rollout verified?"}
    Final -->|No| Observe
    Final -->|Yes| Complete["Mark release healthy"]
~~~

### 5.1. Canary release

Canary gửi một tỷ lệ nhỏ traffic hoặc một nhóm instance tới phiên bản mới, giữ phần còn lại trên phiên bản ổn định. Có thể mở rộng dần 1%, 5%, 10%, 25%, 50%, 100% tùy workload và khả năng đo; các tỷ lệ chỉ là ví dụ, không phải mặc định.

Canary hữu ích khi:

- Có đủ traffic để tạo sample có ý nghĩa.
- Có thể định tuyến hoặc phân nhóm người dùng.
- Metric phân biệt rõ phiên bản và cohort.
- Rollback/stop có thể hoàn thành trong thời gian chấp nhận.

Không phù hợp nếu traffic quá ít, state không thể tách, dữ liệu dùng chung bị migration phá compatibility hoặc mỗi instance mới ảnh hưởng toàn hệ thống ngay khi khởi động.

### 5.2. Blue/green

Blue/green duy trì hai môi trường tương đương; một môi trường đang nhận traffic, môi trường kia được deploy và kiểm tra trước khi chuyển. Có thể chuyển traffic nhanh và rollback bằng cách route về môi trường cũ, nhưng chỉ khi database, queue, cache và session tương thích giữa hai phiên bản.

Nếu cả blue và green cùng ghi vào một schema đã thay đổi không tương thích, đổi traffic trở lại không khôi phục được dữ liệu. Cần thiết kế expand/contract migration và write compatibility.

### 5.3. Rolling deployment

Rolling deployment thay instance/pod theo từng batch. Readiness, max unavailable, surge capacity và graceful termination quyết định ảnh hưởng tới traffic. Nếu batch đầu có lỗi, controller có thể tiếp tục rollout trừ khi có progressive analysis hoặc pause gate.

### 5.4. Feature flag

Feature flag tách deploy code khỏi bật chức năng. Có thể deploy code nhưng chỉ bật feature cho internal cohort/canary. Flag cần owner, default safe value, targeting rule, audit, expiry và kill switch đã thử. Flag không thay thế kiểm tra phiên bản binary hoặc schema.

## 6. Thiết kế release gate và ngưỡng dừng

Release gate là bộ quy tắc quyết định rollout được tiếp tục, tạm dừng để quan sát hay phải abort. Quy tắc cần rõ ràng trước khi deploy, có thể giải thích và kiểm thử.

### 6.1. Ba trạng thái quyết định

| Trạng thái | Điều kiện ví dụ | Hành động |
| --- | --- | --- |
| Pass / continue | Hard gates đạt, metric trong ngưỡng, đủ sample và observation window | Mở rộng rollout theo bước tiếp theo |
| Hold / pause | Metric chưa đủ sample, telemetry thiếu, tín hiệu xung đột hoặc cảnh báo chưa được xác minh | Giữ tỷ lệ hiện tại, không mở rộng, điều tra |
| Fail / abort | Hard gate vi phạm, SLO burn rate vượt ngưỡng, crash/error nghiêm trọng hoặc invariant dữ liệu lỗi | Dừng rollout; rollback/disable feature/forward-fix theo runbook |

Không coi “không có dữ liệu” là pass. Thiếu metric bắt buộc phải chuyển sang hold hoặc fail-safe theo mức criticality.

### 6.2. Hard gate và soft gate

Hard gate là điều kiện không được vi phạm, ví dụ:

- Readiness của canary không đạt trong timeout.
- Có lỗi authentication/authorization nghiêm trọng.
- Business invariant thất bại như tạo trùng payment/order hoặc mất dữ liệu.
- Error rate hoặc latency vượt ngưỡng đã phê duyệt trong cửa sổ xác định.
- Security scan/runtime policy phát hiện secret exposure hoặc quyền vượt phạm vi.
- Telemetry coverage không đủ để đánh giá một release critical.

Soft gate cảnh báo hoặc yêu cầu quan sát thêm, ví dụ CPU cao hơn baseline nhưng latency vẫn tốt; cache hit giảm nhẹ; metric mới có biến động chưa vượt ngưỡng. Soft gate không được phép che một hard gate.

### 6.3. Chọn threshold

Threshold nên được suy ra từ SLO, baseline, biến động tự nhiên và tác động nghiệp vụ. Ví dụ minh họa:

| Tín hiệu | Điều kiện cảnh báo | Điều kiện abort |
| --- | --- | --- |
| Canary 5xx rate | Cao hơn baseline 1,5 lần trong 3 phút | Trên 3% và sample đủ trong 2 phút |
| p95 latency | Tăng trên 20% so với control | Vượt SLO 2 cửa sổ liên tiếp |
| Crash/restart | Restart tăng so với baseline | Crash loop hoặc không đạt Ready sau timeout |
| Synthetic checkout | Một lần lỗi được retry xác minh | Hai lần lỗi liên tiếp hoặc payment/order invariant fail |
| Queue oldest age | Tăng nhanh so với control | Vượt deadline nghiệp vụ đã phê duyệt |

Các con số chỉ minh họa cách biểu diễn policy. Không dùng nguyên xi cho production nếu chưa benchmark, xác định sample count, SLO và failure impact.

### 6.4. So sánh cohort đúng cách

Khi có canary, so sánh:

- Phiên bản mới và control version trong cùng region/time window.
- Cùng endpoint/workload class/tenant tier hoặc traffic mix tương đương.
- Tỷ lệ lỗi trên cùng denominator, không so số lượng lỗi tuyệt đối khi traffic khác nhau.
- Latency percentile chỉ khi sample đủ và histogram/aggregation tương đương.
- Dependency health để xác định lỗi đến từ candidate hay hệ thống dùng chung.

Nếu toàn bộ region cùng lỗi do database outage, canary có thể trông tệ hơn chỉ do được route vào một dependency đang suy giảm. Pipeline nên hold hoặc áp logic incident suppression; không tự rollback candidate khi chưa có bằng chứng quan hệ nhân quả.

### 6.5. Observation window và minimum sample

Window cần đủ dài để thấy startup, warm-up, traffic pattern và async job completion nhưng ngắn đủ để giới hạn blast radius. API traffic lớn có thể đánh giá nhanh hơn; batch hoặc queue cần chờ job thực sự được xử lý.

Thiết lập:

- Minimum request/job count.
- Minimum observation duration.
- Metric freshness và telemetry coverage.
- Cửa sổ ngắn để bắt lỗi đột biến và cửa sổ dài để xác nhận.
- Timeout tối đa; khi không đủ dữ liệu thì hold hoặc abort theo criticality.

Một canary chỉ nhận 20 request không thể chứng minh p99 ổn định. Ngược lại, chờ cả ngày cho một lỗi crash loop rõ ràng là không cần thiết.

## 7. Auto-halt, abort và rollback controller

Tự động dừng phát hành cần state rõ ràng, quyền hành động tối thiểu và thao tác idempotent. Không nên để một alert bất kỳ có quyền tự động xóa deployment hoặc đổi database endpoint.

### 7.1. State machine của release

~~~mermaid
stateDiagram-v2
    [*] --> Prepared
    Prepared --> Deployed: Candidate deployed
    Deployed --> SmokeCheck
    SmokeCheck --> Paused: Checks inconclusive
    SmokeCheck --> Halted: Hard gate failed
    SmokeCheck --> Canary: Checks pass
    Canary --> Observing
    Observing --> Paused: Missing/stale metrics
    Observing --> Halted: Threshold breached
    Observing --> Expanding: Gate passes
    Expanding --> Observing: Next cohort active
    Expanding --> Completed: 100% and verified
    Halted --> RollbackDecision
    RollbackDecision --> RollingBack: Reversible and approved policy
    RollbackDecision --> ForwardFix: Rollback unsafe
    RollingBack --> Verification
    ForwardFix --> Verification
    Verification --> Recovered: Stable and business checks pass
    Verification --> Incident: Recovery failed
    Paused --> Observing: Evidence available
    Incident --> [*]
    Recovered --> [*]
    Completed --> [*]
~~~

### 7.2. Hành động khi abort

Khi gate fail:

1. Chặn bước rollout tiếp theo và giữ traffic ở mức hiện tại.
2. Ghi release ID, metric, sample/window, threshold và reason code.
3. Xác định candidate có đang nhận traffic hoặc xử lý background job không.
4. Chọn hành động: pause, giảm traffic, disable feature, rollback binary hoặc forward-fix.
5. Thực hiện hành động theo runbook có idempotency và timeout.
6. Chạy post-action verification; không đánh dấu recovery chỉ vì controller trả success.
7. Gửi notification tới owner/on-call, tạo incident hoặc change record.
8. Giữ evidence và chặn tự động retry rollout cho tới khi có quyết định.

### 7.3. Auto-halt khác auto-rollback

Auto-halt thường an toàn hơn: controller ngăn rollout mở rộng, giữ deployment ở trạng thái đã biết và báo người vận hành. Auto-rollback là hành động thay đổi runtime, traffic hoặc schema; cần hiểu tính tương thích và side effect. Nhiều hệ thống nên tự động halt nhưng chỉ auto-rollback khi đã chứng minh thao tác đảo ngược an toàn.

### 7.4. Idempotency và concurrency

Controller có thể nhận nhiều alert đồng thời hoặc restart giữa lúc đang thực hiện. Mỗi release cần lock/lease hoặc concurrency control để không có hai controller cùng thay traffic. Action nên dùng desired state, compare-and-set hoặc API idempotent; lưu trạng thái trước/sau và request ID.

### 7.5. Metric source failure

Nếu monitoring backend hoặc query API lỗi:

- Không tự diễn giải metric null thành zero.
- Dừng mở rộng rollout.
- Giữ cohort hiện tại hoặc chuyển về safe baseline theo policy.
- Dùng monitoring path độc lập/heartbeat để xác định phạm vi telemetry outage.
- Không auto-rollback chỉ vì một backend query timeout nếu không có tín hiệu lỗi khác, trừ khi policy criticality yêu cầu fail-safe.

## 8. Chọn rollback, traffic shift hay forward-fix

Rollback binary là một lựa chọn, không phải phản xạ duy nhất.

| Phương án | Khi phù hợp | Rủi ro/cần xác minh |
| --- | --- | --- |
| Halt only | Chưa rõ nguyên nhân, cần giữ trạng thái để điều tra | Candidate vẫn phục vụ một phần traffic |
| Traffic shift back | Blue/green hoặc canary có control version tương thích | State/schema/queue vẫn có thể đã thay đổi |
| Disable feature flag | Lỗi nằm trong feature có thể tắt độc lập | Flag path và default value phải an toàn |
| Binary rollback | Artifact cũ tương thích với schema/config/state hiện tại | Migration hoặc persisted state có thể không backward-compatible |
| Forward-fix | Rollback gây rủi ro dữ liệu hoặc có hotfix an toàn hơn | Cần kiểm soát thay đổi mới và kiểm chứng nhanh |
| Degraded mode | Dependency hoặc feature phụ lỗi nhưng core service vẫn hoạt động | Phải bảo toàn business invariant và thông báo rõ |

Trước khi rollback, xác định phiên bản cũ có thể đọc dữ liệu do phiên bản mới ghi không, message mới có tương thích consumer cũ không và cache/session có format mới hay không.

## 9. Database migration và backward compatibility

Database thường là lý do khiến rollback ứng dụng không an toàn. Binary cũ có thể không hiểu schema mới; migration xóa cột hoặc thay semantics có thể không thể đảo ngược mà không mất dữ liệu.

### 9.1. Expand-and-contract

1. **Expand:** thêm bảng/cột/index mới theo cách schema cũ vẫn tương thích.
2. Deploy ứng dụng có thể đọc/ghi theo cách tương thích cả schema cũ và mới.
3. Backfill dữ liệu theo batch, kiểm tra completeness và consistency.
4. Chuyển read path sang cấu trúc mới và quan sát.
5. Ngừng ghi vào cấu trúc cũ sau khi mọi writer/consumer đã chuyển.
6. **Contract:** xóa cột/bảng cũ trong release riêng sau thời gian xác nhận.

Tách migration phá tương thích khỏi release ứng dụng giúp binary rollback ít rủi ro hơn. Cần kiểm tra mọi consumer, report, ETL job và service khác vẫn dùng schema cũ.

### 9.2. Migration có thể đảo ngược hay không?

| Thay đổi | Khả năng rollback | Ghi chú |
| --- | --- | --- |
| Thêm nullable column | Thường dễ | Binary cũ thường bỏ qua field mới |
| Thêm index | Thường có thể drop | Có thể lock/ảnh hưởng performance khi tạo |
| Backfill cột mới | Có thể giữ dữ liệu | Kiểm tra dual-write và source of truth |
| Rename/drop column | Khó | Nên dùng expand/contract thay rename trực tiếp |
| Thay enum/format | Phụ thuộc reader/writer | Phải hỗ trợ version tương thích |
| Data transformation mất thông tin | Có thể không đảo ngược | Cần backup/recovery hoặc forward-fix |

### 9.3. Event schema và message compatibility

Queue/stream message có thể tồn tại lâu hơn một deployment. Producer mới cần phát event mà consumer cũ vẫn hiểu trong thời gian rollout. Dùng schema registry, versioned event, optional field và compatibility rules; không đổi semantics của field cũ mà không có migration.

Nếu consumer mới đã xử lý message theo state mới, rollback consumer có thể gây lỗi hoặc duplicate. Cần idempotency, version-aware handler và cách replay/DLQ đã kiểm thử.

### 9.4. Feature flag và kill switch

Feature flag nên có tên/mục đích/owner rõ, default safe khi config service mất kết nối, có thể tắt nhanh nếu phù hợp kiến trúc, hỗ trợ targeting theo cohort/tenant/region, ghi audit người bật/tắt và lý do, đồng thời có expiry để tránh tích lũy flag cũ.

Kill switch phải được thử trước release; không thể giả định flag hoạt động khi backend config hoặc network đang outage.

## 10. Ví dụ triển khai release gate trên Kubernetes

Kubernetes HPA/readiness và Deployment rollout giúp quản lý replica, nhưng bản thân trạng thái rollout không thay thế việc phân tích SLO/business metric. Có thể kết hợp rollout controller, analysis template hoặc pipeline automation với metric provider.

### 10.1. Deployment với readiness và graceful termination

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: checkout-api
spec:
  replicas: 6
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  selector:
    matchLabels:
      app: checkout-api
  template:
    metadata:
      labels:
        app: checkout-api
    spec:
      terminationGracePeriodSeconds: 45
      containers:
        - name: api
          image: registry.example/checkout-api:2.8.1
          ports:
            - name: http
              containerPort: 8080
          startupProbe:
            httpGet:
              path: /startup
              port: http
            periodSeconds: 5
            failureThreshold: 30
          readinessProbe:
            httpGet:
              path: /ready
              port: http
            periodSeconds: 5
            failureThreshold: 3
          livenessProbe:
            httpGet:
              path: /live
              port: http
            periodSeconds: 10
            failureThreshold: 3
~~~

Đây là ví dụ cấu trúc. Endpoint phải phân biệt startup/readiness/liveness và có timeout/threshold phù hợp; readiness không nên kiểm tra quá nhiều dependency chung đến mức mọi Pod bị loại khỏi Service khi một dependency ngoài đang gặp sự cố.

### 10.2. Analysis gate dạng pseudo-config

~~~yaml
releaseAnalysis:
  target:
    service: checkout-api
    candidateVersion: "2.8.1"
    controlVersion: "2.8.0"
  steps:
    - trafficWeight: 5
      observation: 5m
      minimumRequests: 500
    - trafficWeight: 20
      observation: 10m
      minimumRequests: 2000
    - trafficWeight: 50
      observation: 15m
      minimumRequests: 5000
  gates:
    - metric: canary_5xx_ratio
      comparator: less_than
      threshold: 0.02
      action: abort
    - metric: checkout_p95_ms
      comparator: less_than
      threshold: 250
      action: abort
    - metric: telemetry_freshness_seconds
      comparator: less_than
      threshold: 60
      action: hold
  onAbort:
    haltRollout: true
    notify: checkout-oncall
    rollbackMode: manual_approval
~~~

Pseudo-config này diễn tả ý tưởng, không phải schema chuẩn của Kubernetes hoặc một controller cụ thể. Công cụ thực tế có thể dùng Argo Rollouts, Flagger, service mesh, pipeline hoặc custom release controller; cần xác minh metric query, permission, timeout và semantics của phiên bản đang dùng.

### 10.3. Hành vi controller

Controller cần đọc metric qua authenticated identity chỉ có quyền query. Nó nên gắn release ID/version vào query, tính tỷ lệ lỗi từ numerator/denominator cùng cohort, kiểm tra freshness/sample count/no-data, tôn trọng observation window, chỉ mở traffic khi mọi hard gate pass, pause khi metric unavailable và ghi quyết định/action vào audit trail.

Không nhúng token backend monitoring vào image hoặc ConfigMap plain text. Dùng workload identity/secret manager và rotate credential.

## 11. Verification sau rollback hoặc forward-fix

Rollback không kết thúc incident. Phải xác minh ứng dụng và dữ liệu sau khi hành động.

### 11.1. Post-action verification

- Candidate version không còn nhận traffic ngoài phạm vi được chấp nhận.
- Control version Ready và có capacity phục vụ tải.
- Error rate, latency, timeout và restart trở lại vùng ổn định.
- Synthetic business journey pass.
- Database/schema/event compatibility không bị phá.
- Queue backlog, retry và DLQ không tăng bất thường.
- Không có duplicate payment/order hoặc invariant sai.
- Feature flag ở trạng thái safe.
- Alert/monitoring và rollback controller hoạt động bình thường.

### 11.2. Giữ lại bằng chứng

Lưu release ID, artifact digest, deployment diff, traffic weights, metric windows, gate decision, query links, logs/traces đã redacted, actor và timestamp. Evidence giúp postmortem xác định phiên bản gây lỗi và liệu gate có hoạt động đúng.

### 11.3. Chống rollback loop

Nếu automation rollback xong rồi pipeline tự khởi chạy rollout lại từ desired state GitOps, hệ thống có thể dao động qua lại. Cần ghi trạng thái release failed/blocked, đặt hold hoặc require explicit approval cho retry cùng artifact. Retry phải có nguyên nhân đã xử lý và release attempt ID mới.

## 12. Kiểm thử release gate và auto-halt

Không chờ production gặp lỗi mới biết controller không dừng. Cần kiểm thử cả rule logic và hành vi thực tế.

### 12.1. Unit/contract tests cho gate

Kiểm tra tỷ lệ lỗi khi denominator khác nhau; metric thiếu/null/stale/query timeout; minimum sample/observation window; hard gate ưu tiên soft gate; cohort filter đúng; alert duplicate; counter reset, histogram bucket và delayed metrics.

### 12.2. Integration test

1. Deploy phiên bản khỏe và chứng minh gate pass.
2. Deploy candidate có endpoint trả lỗi có kiểm soát và chứng minh halt.
3. Tạo latency regression để xác minh threshold.
4. Ngắt telemetry exporter để xác minh hold thay vì pass.
5. Làm dependency dùng chung suy giảm để kiểm tra incident suppression/hold.
6. Gọi abort nhiều lần để xác minh idempotency.
7. Khởi động lại controller giữa action để xác minh state recovery.
8. Kiểm tra notification, audit và owner.

### 12.3. Game day và fault injection

Thử crash loop sau deploy, memory leak/CPU throttling chỉ ở candidate, database migration tương thích một chiều, queue consumer không tương thích, monitoring backend chậm/mất region, global load balancer health probe sai, rollback API timeout nhưng action đã hoàn tất và GitOps reconcile lại release đã abort.

Mỗi thử nghiệm cần scope, synthetic data, tiêu chí dừng và không gây side effect thật.

## 13. Ownership, incident và vận hành release gate

Tự động dừng release là một phần của production operations. Phải biết ai sở hữu gate, ai quyết định khi tín hiệu xung đột và ai chịu trách nhiệm khôi phục.

| Vai trò | Trách nhiệm |
| --- | --- |
| Service owner | Xác định SLO, critical journeys, dependency và release risk |
| Release/deployment owner | Lập rollout plan, artifact/version, traffic steps và change record |
| Platform/SRE | Vận hành controller, metric query, routing, alert và rollback capability |
| Data owner | Xác nhận schema migration, recovery point, data compatibility và invariant |
| Security | Kiểm tra policy/authz/secrets và xử lý security hard gate |
| Incident commander | Điều phối khi abort gây outage hoặc rollback thất bại |
| Business owner | Chấp thuận degraded mode, risk exception và tác động người dùng |

### 13.1. Alert và release event

Thông báo khi gate hold/fail cần có service/environment/region/release ID; candidate/control version và traffic weight; metric/threshold/window/sample count; dashboard/query link; action đã thực hiện; owner/on-call và incident/change ID.

Không chỉ gửi “deployment failed”. Người trực cần biết rollout đã dừng ở đâu và có rollback hay chưa.

### 13.2. Manual override

Override phải có approver và lý do, gắn đúng release/gate, có thời hạn/scope, ghi audit và có compensating monitoring. Không dùng manual override để bỏ qua security hard gate hoặc business invariant.

### 13.3. Post-incident review

Review root cause, blast radius, gate detection time, false positive/negative, metric freshness/sample/cohort, controller idempotency/audit, schema/queue compatibility và cải tiến threshold/window/ownership. Không tăng ngưỡng chỉ để giảm số lần halt.

## 14. Cost và tốc độ phát hành

Chi phí có thể gồm hai môi trường blue/green, capacity canary, synthetic tests, observability ingest/query, giữ phiên bản cũ, schema compatibility, manual approval và on-call. So sánh với chi phí outage, data repair, customer support và incident response.

Observation window nên phù hợp loại workload: API traffic cao có thể đủ sample nhanh; queue/batch cần chờ completion/deadline; workload định kỳ cần synthetic input đại diện; region ít traffic có thể cần canary traffic kiểm soát.

Theo dõi deployment frequency, lead time, change failure rate, rollback/forward-fix rate, mean time to detect regression, mean time to halt/restore, tỷ lệ hold do thiếu telemetry, false positive/negative và cost per release. Không tối ưu một metric đơn lẻ.

## 15. Well-Architected: kiểm chứng và dừng release

| Góc nhìn | Quyết định thiết kế | Đánh đổi |
| --- | --- | --- |
| **Operational Excellence / Vận hành** | Release manifest, gate automation, runbook, audit và owner | Tự động hóa tăng tốc nhưng policy phải dễ kiểm thử và giải thích |
| **Security / Bảo mật** | Artifact provenance, policy gate, JIT approval và secret hygiene | Thêm bước kiểm tra nhưng giảm rủi ro đưa artifact/cấu hình không an toàn vào production |
| **Reliability / Độ tin cậy** | Canary, SLO gates, auto-halt, safe rollback và data compatibility | Rollout chậm hơn nhưng giới hạn blast radius |
| **Performance Efficiency / Hiệu quả hiệu năng** | Đo latency/saturation theo cohort, capacity và dependency | Cần sample/telemetry phù hợp và tránh metric gây cardinality cao |
| **Cost Optimization / Tối ưu chi phí** | Right-size canary/blue-green, observation window và signal retention | Tăng chi phí test/capacity để giảm expected incident cost |
| **Sustainability / Bền vững** | Loại bỏ retry loop, rollout churn và tài nguyên test dư | Gate tốt giảm compute lãng phí do release lỗi và rollback lặp |

## 16. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Chỉ kiểm tra Pod Ready | Ứng dụng có thể lỗi khi nhận request thật | Kết hợp smoke, synthetic và business checks |
| Chỉ dùng CPU làm gate | Bỏ lỡ latency, errors, queue và downstream wait | Dùng RED, saturation và nghiệp vụ |
| Không gắn metric với version/cohort | Canary bị hòa vào baseline | Release ID, version labels và control cohort |
| Canary quá nhỏ hoặc quá ngắn | Sample không đủ để kết luận | Minimum sample và observation window |
| Coi no-data là success | Rollout tiếp tục khi mất monitoring | Hold/fail-safe khi telemetry stale hoặc thiếu |
| Auto-rollback mọi alert | Có thể rollback nhầm do dependency chung | Phân loại hard/soft gate và shared incident |
| Rollback binary mà không xét schema | Phiên bản cũ không đọc được dữ liệu mới | Expand/contract và compatibility testing |
| Bật/tắt feature flag không audit | Hành vi production khó giải thích | Owner, expiry, targeting và audit |
| Rollback xong pipeline tự deploy lại | Release loop và flapping | Block failed release, require new attempt/approval |
| Chỉ kiểm thử happy path | Controller không xử lý outage/timeout | Fault injection, idempotency và restart tests |
| Gate dùng ngưỡng tùy ý | False positive hoặc phát hiện muộn | Suy threshold từ SLO, baseline và impact |
| Không verify sau rollback | Binary cũ chạy nhưng business/data vẫn lỗi | Post-action synthetic và invariant checks |

## 17. Bài thực hành: tự động dừng release checkout lỗi

Một nền tảng thương mại điện tử triển khai checkout-api bằng Kubernetes rolling/canary. Phiên bản 2.8.1 thay đổi xử lý retry payment và bổ sung một cột trong database. Phiên bản 2.8.0 vẫn đang phục vụ 95% traffic; candidate nhận 5%. Trong 4 phút đầu:

- Candidate có 5xx ratio 2,8%, control là 0,4%.
- Candidate p95 latency 310 ms, control là 180 ms; SLO p95 là 250 ms.
- Synthetic checkout có hai lần timeout nhưng order database vẫn ghi một order cho mỗi attempt.
- Queue retry payment tăng, database connection bình thường.
- Dashboard chung ghi nhận payment provider có một đợt latency tăng nhẹ.

**Yêu cầu bài làm:**

1. Xác định gate nào pass, hold hoặc fail; giải thích candidate/control comparison và SLO.
2. Định nghĩa sample minimum, observation window và ngưỡng hard/soft phù hợp.
3. Thiết kế action tự động: halt rollout, giữ traffic 5%, giảm về control hay disable retry feature.
4. Đánh giá liệu provider latency có phải nguyên nhân chung hay candidate làm retry khuếch đại lỗi.
5. Kiểm tra idempotency và business invariant để chứng minh không có duplicate order/payment.
6. Đánh giá migration cột mới có backward-compatible không; xác định rollback binary có an toàn.
7. Thiết kế queue drain/retry policy sau khi halt để không tạo thêm payment attempt.
8. Xác định thông báo cho on-call và evidence phải lưu.
9. Mô tả post-action verification sau rollback hoặc forward-fix.
10. Viết integration/fault tests cho metric outage, controller restart và auto-reconcile của GitOps.

### Gợi ý đánh giá

Với số liệu hiện tại, candidate vi phạm p95 SLO và error ratio cao rõ rệt so với control; gate nên ít nhất halt mở rộng ngay và điều tra retry behavior. Vì hai lần synthetic timeout nhưng chỉ có một order mỗi attempt, cần kiểm tra thêm payment provider transaction reference và idempotency ở mức side effect trước khi quyết định forward-fix/rollback.

Provider latency tăng nhẹ là một yếu tố gây nhiễu cần đối chiếu trace và control cohort; nó không đủ để bỏ qua chênh lệch candidate. Nếu schema migration tương thích ngược, traffic có thể chuyển về control và rollback binary. Nếu migration đã làm thay đổi state không tương thích, giữ rollout halted, tắt feature nếu an toàn hoặc forward-fix theo quy trình.

## 18. Checklist trước khi bật auto-halt/rollback

- [ ] Mỗi release có ID, artifact digest, version, owner và change record.
- [ ] Có verification matrix từ platform tới business journey.
- [ ] Readiness/liveness/startup probes đúng semantics và không tạo restart storm.
- [ ] Smoke/synthetic tests không gây side effect thật hoặc có cleanup/idempotency.
- [ ] Baseline và control cohort được xác định trước rollout.
- [ ] SLI/SLO, error budget, hard/soft gates và thresholds được phê duyệt.
- [ ] Metric có release/cohort labels, minimum sample và observation window.
- [ ] Missing/stale telemetry dẫn tới hold/fail-safe, không pass.
- [ ] Progressive rollout có bước traffic, timeout, pause và stop criteria.
- [ ] Auto-halt tách biệt auto-rollback; rollback chỉ chạy khi data/state tương thích.
- [ ] Database migration theo expand/contract hoặc có recovery path đã thử.
- [ ] Queue/event schema và consumer tương thích trong thời gian rolling deployment.
- [ ] Feature flag/kill switch có owner, audit, expiry và safe default.
- [ ] Controller có concurrency control, idempotency, state persistence và audit.
- [ ] Shared dependency outage không làm auto-rollback nhầm candidate.
- [ ] Post-action verification kiểm tra SLO, synthetic journey, data invariant và backlog.
- [ ] GitOps/pipeline không tự deploy lại release đã bị abort.
- [ ] Alert có release ID, metric, threshold, window, action và runbook.
- [ ] Có test gate logic, missing metrics, rollback timeout, controller restart và fault injection.
- [ ] On-call, service owner, data owner và incident commander đã rõ vai trò.
- [ ] Có post-incident review và version hóa threshold/policy.

**Ghi nhớ:** Release chỉ thành công khi phiên bản mới hoạt động tốt với traffic, dữ liệu và hành trình nghiệp vụ thực tế. Kiểm chứng sau deploy cần baseline, cohort, SLI/SLO, sample và observation window rõ ràng. Khi có dấu hiệu lỗi, tự động halt rollout trước; chỉ rollback khi binary, schema, message và persisted state tương thích. Sau mọi hành động phải kiểm tra lại business invariant, telemetry và backlog. Kiểm thử controller như một hệ thống production để nó dừng đúng lúc, không bỏ qua lỗi và không tự tạo vòng deploy/rollback.

