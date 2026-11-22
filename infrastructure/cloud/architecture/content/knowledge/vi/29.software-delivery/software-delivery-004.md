# Feature flag, triển khai tối và kiểm soát phát hành

## Mục tiêu học tập

Trong hệ thống cloud, đưa một phiên bản phần mềm lên production không có nghĩa phải bật ngay toàn bộ chức năng mới cho mọi người dùng. Một bản deploy có thể chứa code mới nhưng hành vi vẫn được điều khiển bởi cấu hình runtime. Nhờ đó, đội ngũ có thể tách thời điểm triển khai kỹ thuật khỏi thời điểm cung cấp tính năng, thử nghiệm trong phạm vi nhỏ, giảm rủi ro và phản hồi nhanh khi phát hiện vấn đề.

**Feature flag** là cơ chế điều khiển một nhánh hành vi của phần mềm bằng cấu hình hoặc quyết định runtime. **Dark launch** là cách triển khai code hoặc luồng xử lý mới trong production nhưng chưa hiển thị kết quả mới cho người dùng hoặc chưa chuyển quyền xử lý chính sang chức năng mới. **Release control** là tập quy trình, policy và telemetry để quyết định ai được sử dụng tính năng nào, ở thời điểm nào và trong điều kiện nào.

Các kỹ thuật này hỗ trợ progressive delivery, canary release, experimentation và rollback. Tuy nhiên, flag không tự động làm hệ thống an toàn: rule targeting sai có thể lộ tính năng cho sai tenant, một flag cũ có thể tạo thêm nhánh logic, dark launch có thể nhân đôi tải hoặc side effect, còn rollback code có thể không tương thích với schema mới.

Bài học thuộc chương **Phân phối phần mềm**, tập trung vào **feature flag, triển khai tối và kiểm soát phát hành**. Trong Cloud Architecture, release cần gắn với yêu cầu nghiệp vụ, compute, network, data, deployment model, bảo mật, khả năng mở rộng, chi phí và vận hành; các quyết định được đánh giá theo tinh thần Well-Architected.

Sau bài học, bạn có thể:

- Phân biệt deploy, release, feature enablement và rollback.
- Giải thích các loại feature flag và vòng đời của flag.
- Thiết kế dark launch an toàn cho read path, write path và background processing.
- Tạo targeting theo environment, tenant, cohort, region hoặc user attribute đã được phép.
- Triển khai progressive rollout theo phần trăm và theo nhóm có kiểm soát.
- Phối hợp feature flag với canary, blue/green, rolling deployment và schema migration.
- Thiết kế kill switch, fallback và rollback không phá business invariant.
- Đo adoption, latency, errors, conversion, resource cost và side effect.
- Bảo vệ flag configuration bằng authorization, audit, approval và secret handling.
- Kiểm soát flag debt, owner, expiry và quy trình dọn dẹp.
- Xây dựng release checklist, runbook và tiêu chí dừng/mở rộng rollout.
- Đánh giá rủi ro và chi phí của feature management trong môi trường cloud.

## 1. Deploy khác release như thế nào?

**Deploy** là đưa artifact hoặc cấu hình phần mềm vào một môi trường chạy. **Release** là làm cho một capability có thể được người dùng hoặc hệ thống sử dụng. Hai thời điểm có thể trùng nhau nhưng không bắt buộc.

Ví dụ, phiên bản booking API mới chứa hai cách tính giá: thuật toán cũ và thuật toán mới. Code mới được deploy lên toàn bộ production, nhưng flag pricing_v2_enabled vẫn tắt. Sau khi kiểm thử nội bộ, đội ngũ bật flag cho một nhóm nhân viên, sau đó 1% tenant, rồi tăng dần. Nếu số liệu xấu, tắt flag để quay lại thuật toán cũ trong khi artifact vẫn tiếp tục chạy.

| Khái niệm | Câu hỏi | Hành động |
| --- | --- | --- |
| Build | Artifact nào được tạo? | Compile, package, sign |
| Deploy | Artifact chạy ở đâu? | Rollout workload/container/function |
| Enablement | Hành vi mới được bật cho ai? | Evaluate feature flag |
| Release | Người dùng có thể sử dụng capability chưa? | Mở quyền sử dụng theo plan/cohort |
| Rollback | Làm sao khôi phục hành vi/phiên bản? | Disable flag, revert traffic hoặc deploy artifact trước |
| Retirement | Khi nào bỏ code/flag cũ? | Cleanup sau khi migration hoàn tất |

### 1.1. Vì sao tách deploy khỏi release?

Tách hai việc giúp triển khai code trước thời điểm marketing hoặc nghiệp vụ công bố; kiểm chứng runtime behavior trong production với exposure thấp; bật/tắt tính năng nhanh mà không phải build lại image; phân phối theo tenant, region, gói dịch vụ hoặc cohort; giảm rủi ro khi rollout thay đổi lớn; thực hiện migration theo từng bước khi code và data schema cần tương thích nhiều phiên bản.

Tuy nhiên, việc bật flag cũng là một production change. Nó cần authorization, audit, validation và rollback plan như một deployment.

## 2. Feature flag là gì?

Feature flag là một quyết định runtime điều khiển việc chạy nhánh code hoặc cấp quyền sử dụng capability. Flag có thể được lưu trong config service, feature management platform, database, file config hoặc hệ thống control plane nội bộ.

~~~mermaid
flowchart TD
    R["Incoming request"] --> C["Resolve trusted context"]
    C --> E["Evaluate feature flag"]
    E -->|Enabled| N["New implementation"]
    E -->|Disabled| O["Existing implementation"]
    N --> M["Record outcome/metrics"]
    O --> M
    M --> RSP["Response"]
~~~

Một flag thường có key/name ổn định, description và mục đích, flag type và default value, owner/team, environment scope, targeting rules, start date và expiry/removal date, risk level và approval requirement, audit history, metric hoặc experiment liên quan, fallback khi flag service không khả dụng.

Flag có thể được đánh giá ở client, gateway, service hoặc worker. Vị trí đánh giá quyết định khả năng bảo mật, độ trễ, consistency và nguy cơ lộ logic.

### 2.1. Các loại flag

| Loại flag | Mục đích | Ví dụ | Vòng đời thường thấy |
| --- | --- | --- | --- |
| Release toggle | Bật/tắt tính năng đang phát triển hoặc rollout | New booking workflow | Ngắn đến trung hạn |
| Experiment toggle | Chia cohort để thử biến thể | Checkout A/B test | Có thời hạn theo experiment |
| Operational toggle | Điều khiển hành vi khi vận hành | Tắt export nặng | Có thể dài hạn nếu là control vận hành |
| Permission/entitlement toggle | Quy định capability theo gói/quyền | Enterprise-only report | Dài hạn, cần tích hợp authorization |
| Kill switch | Tắt nhanh chức năng gây sự cố | Disable recommendation provider | Cần luôn được kiểm thử |
| Migration toggle | Chuyển dần sang data store/implementation mới | Read from DB B | Có thời hạn theo migration |

Không nên dùng feature flag để thay thế authorization. Flag có thể điều khiển sản phẩm có sẵn cho một cohort, nhưng quyền truy cập dữ liệu và hành động nhạy cảm vẫn phải được server kiểm tra bằng identity và policy độc lập.

### 2.2. Flag có nhiều trạng thái hơn boolean

Một flag đơn giản có thể bật/tắt. Các hệ thống targeting thường hỗ trợ nhiều biến thể hoặc giá trị: boolean, string/enum, number, JSON/object có schema hoặc multivariate experiment. Flag càng phức tạp thì contract, validation, schema evolution và test càng quan trọng. Không nên biến feature management thành một kho cấu hình tùy ý không có type hoặc governance.

## 3. Thiết kế feature flag contract

Một flag cần được mô tả để người tạo và người vận hành hiểu nó tác động tới điều gì.

Ví dụ metadata:

~~~yaml
key: booking.pricing.v2
type: boolean
description: Enable the new booking pricing calculation
owner: booking-platform
default: false
environments:
  development: true
  staging: true
  production: false
targeting:
  allowed_dimensions:
    - tenant_id
    - region
    - service_tier
risk: high
requires_approval: true
expires_at: 2027-03-31
rollback:
  action: disable_flag
  owner: booking-oncall
~~~

Đây là schema minh họa. Tên field và khả năng thực thi phụ thuộc feature management system. Flag có thể cần approval, security review hoặc change ticket trước khi bật production.

### 3.1. Naming

Tên flag nên mô tả capability/decision, không mô tả người tạo hoặc ngày tháng. Ví dụ booking.pricing.v2 tốt hơn phuong_test_new. Có namespace theo domain/service để tránh trùng key.

### 3.2. Default và fail behavior

Cần quy định khi SDK không tải được config:
- **Fail closed:** dùng false/legacy behavior.
- **Fail open:** cho phép capability hoạt động.
- **Last known good:** dùng config hợp lệ gần nhất trong cache.
- **Static fallback:** dùng default được build/deploy cùng ứng dụng.

Chọn theo hậu quả. Recommendation có thể fail disabled; flag không được làm security boundary; kill switch điều khiển provider đắt tiền có thể cần local fallback và cơ chế vận hành độc lập.

### 3.3. Evaluation context đáng tin cậy

Targeting có thể dựa trên tenant, region hoặc account, nhưng context phải được xác minh server-side. Không tin header/query parameter tùy ý để quyết định user được thấy tính năng Enterprise. Tránh đưa email, số điện thoại hoặc dữ liệu nhạy cảm vào targeting payload nếu identifier giả danh đã đủ.

## 4. Dark launch là gì?

Dark launch triển khai một luồng xử lý mới trong production nhưng không để kết quả mới trở thành hành vi chính mà người dùng nhìn thấy. Mục tiêu là quan sát hiệu năng, tính tương thích và kết quả trên dữ liệu/tải thực tế trước khi phát hành.

Các dạng thường gặp:
- Chạy code mới nhưng bỏ kết quả, chỉ ghi metric.
- Shadow request: gửi bản sao request tới hệ thống mới.
- Mirror traffic: sao chép một tỷ lệ traffic sang implementation mới.
- Shadow read: truy vấn data store mới song song nhưng chỉ trả kết quả từ store cũ.
- Background computation: tính kết quả trước, chưa dùng cho response.
- Dark endpoint: deploy endpoint nhưng chưa đưa vào public routing.

~~~mermaid
flowchart LR
    U["Production request"] --> OLD["Existing service"]
    U --> MIRROR["Traffic mirror"]
    OLD --> RESP["User response"]
    MIRROR --> NEW["New service / data path"]
    NEW --> OBS["Compare metrics/results"]
    OBS --> DEC["Release decision"]
~~~

Trong dark launch, đường cũ tiếp tục là nguồn kết quả chính. Hệ thống mới được quan sát để đánh giá parity, latency, resource usage và lỗi.

### 4.1. Dark launch không đồng nghĩa gửi cùng request hai lần tùy tiện

Shadow traffic an toàn nhất với thao tác read-only hoặc mô phỏng được. Nếu request có side effect như charge payment, gửi email, tạo booking, ghi ledger hoặc phát event, mirror trực tiếp có thể tạo giao dịch trùng.

Trước khi mirror phải xác định request có đọc/ghi không, side effect ngoài hệ thống, khả năng dùng sandbox/synthetic identity, khả năng chặn write ở shadow path, scrub PII/secrets, concurrency/QPS và data retention. Không mirror trước khi có cơ chế cô lập và kill switch.

### 4.2. Shadow read và data migration

Khi chuyển database từ A sang B:
1. Replicate/backfill dữ liệu sang B.
2. Ứng dụng vẫn đọc A.
3. Shadow read một phần request từ B.
4. So sánh record, null, ordering, filter, latency và consistency.
5. Sửa sai lệch, lặp lại kiểm thử.
6. Canary chuyển một nhóm reader sang B.
7. Tăng dần traffic và quan sát.
8. Sau khi đủ bằng chứng, chuyển primary read.
9. Giữ rollback window và đường quay lại được kiểm thử.
10. Bỏ A sau khi hết thời hạn và dữ liệu đã được đối soát.

Không chỉ so sánh HTTP status. Cần so sánh semantics: cùng record set, authorization, sorting, pagination, transaction snapshot và thời điểm dữ liệu.

## 5. Rủi ro và kiểm soát dark launch

### 5.1. Tăng tải ngoài dự kiến

Mirror 100% traffic có thể gần như nhân đôi workload. Nếu hệ thống mới gọi dependency ngoài hoặc truy vấn database chung, dark launch có thể làm production chậm hơn dù kết quả bị bỏ.

Controls gồm sampling nhỏ, giới hạn concurrency và queue, bulkhead riêng, query timeout và response size, bỏ request đã quá deadline, kill switch độc lập và theo dõi cost/egress/storage tăng thêm.

### 5.2. Data leakage

Request mirror có thể chứa PII, payment token, session identifier hoặc payload nội bộ. Shadow system cần data minimization/masking, private network và TLS, least privilege, retention giới hạn, không log raw payload nếu không cần, access audit và vùng xử lý phù hợp residency requirement.

### 5.3. Side effect và consistency

Shadow path không nên phát event business hoặc ghi vào hệ thống nguồn. Có thể dùng read-only database identity, mock/sandbox provider, sink riêng cho output shadow, correlation ID đánh dấu traffic shadow, interceptor chặn write/effect hoặc synthetic tenant/data.

Nếu shadow cần write để kiểm chứng, dùng isolated test namespace/database hoặc transaction rollback phù hợp; rollback transaction không đảo được side effect tới hệ thống ngoài.

### 5.4. So sánh output công bằng

Hai implementation có thể đọc dữ liệu ở hai thời điểm khác nhau hoặc dùng version/config khác. Ghi timestamp, data version, input hash, request class và correlation ID. So sánh business field có ý nghĩa, không chỉ serialize JSON rồi so sánh byte nếu thứ tự field hoặc timestamp động khác nhau.

## 6. Targeting và rollout theo cohort

Feature flag có thể nhắm tới environment, internal users, tenant/account, region/zone, service tier, user cohort, percentage ổn định theo identity key hoặc capability/entitlement.

### 6.1. Percentage rollout phải ổn định

Nếu mỗi request dùng random number độc lập, cùng một người có thể lúc thấy tính năng lúc không. Dùng deterministic assignment theo stable key đã được chọn và bảo vệ, ví dụ hash tenant ID hoặc user ID cùng flag salt. Cần giữ cohort assignment ổn định trong suốt experiment trừ khi có chủ đích tái phân bổ.

### 6.2. Tenant-level rollout

Với B2B SaaS, tenant thường là đơn vị phù hợp hơn individual user vì dữ liệu, workflow và support được quản lý theo account. Cần tránh một tenant có một số user dùng code path mới, số khác dùng code path cũ trong khi họ chia sẻ trạng thái hoặc database schema.

### 6.3. Rollout ladder

| Giai đoạn | Exposure | Mục tiêu |
| --- | ---: | --- |
| Internal | Nhân viên/test tenant | Kiểm chứng chức năng và support |
| Pilot | 1 tenant hoặc cohort nhỏ | Kiểm tra real data và workflow |
| Canary | 1% traffic/tenant phù hợp | Kiểm tra lỗi, latency, resource |
| Early access | 5–10% | Xác nhận xu hướng |
| Broad rollout | 25–50% | Đánh giá capacity và business KPI |
| General availability | 100% theo eligibility | Chuyển sang vận hành bình thường |

Các tỷ lệ chỉ minh họa. Với hệ thống ít traffic, 1% có thể không đủ mẫu; với workload rất đắt hoặc nhạy cảm, có thể cần giới hạn tenant thay vì tỷ lệ request.

### 6.4. Rollout theo region

Region rollout giúp giảm blast radius nhưng không nên giả định region độc lập. Nếu dữ liệu hoặc control plane global, một thay đổi có thể vẫn ảnh hưởng nhiều region. Kiểm tra replication, key, identity, feature config propagation và external dependency.

## 7. Progressive delivery và các chiến lược deployment

Feature flag quản lý exposure ở tầng application behavior. Deployment strategy quản lý cách artifact được đưa lên compute. Chúng có thể phối hợp nhưng không thay thế nhau.

| Strategy | Cách hoạt động | Vai trò của feature flag |
| --- | --- | --- |
| Rolling deployment | Thay instance/pod theo từng batch | Giữ hành vi cũ trong khi code mới được deploy |
| Blue/green | Hai môi trường; chuyển traffic giữa chúng | Điều khiển capability bên trong version |
| Canary deployment | Một phần traffic tới bản mới | Kết hợp exposure nhỏ với version mới |
| A/B experiment | Nhóm người dùng nhận biến thể khác nhau | Duy trì assignment và đo KPI |
| Dark launch | Chạy code mới nhưng không dùng kết quả chính | Bật shadow path có giới hạn |
| Traffic mirroring | Sao chép request sang backend mới | Kiểm soát sampling và behavior shadow |

### 7.1. Hai chiều rollout

Một release có thể có hai bước: deploy code mới tới một phần hoặc toàn bộ fleet nhưng flag vẫn off; sau đó bật feature flag theo cohort, theo dõi và mở rộng.

Hoặc deployment canary đưa version mới tới một phần pod, trong khi feature flag bật cho một cohort nhỏ trên pod đó. Khi kết hợp hai chiều, phải tránh tình huống user được assign feature nhưng request được route tới pod chưa có code mới.

### 7.2. Compatibility giữa version và flag

Khi rolling deploy, trong một thời gian có thể tồn tại pod cũ và pod mới. Feature config phải tương thích với cả hai version hoặc rollout phải bảo đảm chỉ version đủ khả năng nhận flag mới được tiếp xúc. Cần flag key/version có semantics ổn định, code cũ bỏ qua flag chưa biết một cách an toàn, config rollout sau khi artifact sẵn sàng, không bật flag trước khi migration/dependency cần thiết hoàn tất, và telemetry phân biệt application version với flag state.

## 8. Rollback và kill switch

Rollback là đưa hệ thống về trạng thái chấp nhận được. Có thể gồm tắt feature flag để về legacy code path, chuyển traffic khỏi canary/green, rollback application artifact, revert config/schema nếu được hỗ trợ, degrade functionality hoặc chạy compensation/reconciliation cho side effect đã xảy ra.

### 8.1. Kill switch

Kill switch là flag hoặc control cho phép vô hiệu hóa capability nhanh khi có incident. Nó cần owner và quyền kích hoạt rõ; hoạt động ngay cả khi feature config service gặp lỗi; default/fallback an toàn; được kiểm thử định kỳ; có audit trail; không phụ thuộc UI duy nhất nếu control plane có thể outage; và định nghĩa ảnh hưởng tới request đang chạy/job đang queue.

Một kill switch có thể cần local emergency override hoặc cached config. Emergency override cũng phải có authentication, audit và expiry.

### 8.2. Rollback không phải lúc nào cũng chỉ tắt flag

Nếu code mới đã ghi dữ liệu theo schema/semantics mới, tắt flag có thể không khôi phục trạng thái cũ. Cần thiết kế expand-migrate-contract:
1. Expand schema để version cũ/mới cùng hoạt động.
2. Deploy code tương thích cả hai.
3. Migrate/backfill data.
4. Chuyển traffic/flag.
5. Quan sát và kiểm chứng.
6. Contract schema cũ sau rollback window và approval.

Không drop column hoặc đổi semantics khi vẫn còn consumer cũ.

## 9. Feature flag trong Java/Spring Boot

Ví dụ có interface để application không phụ thuộc trực tiếp vendor SDK:

~~~java
public interface FeatureDecisions {
    boolean enabled(String key, EvaluationContext context);
}
~~~

Context nên được xây từ identity đã xác minh:

~~~java
public record EvaluationContext(
    String tenantId,
    String userId,
    String region,
    String serviceTier
) {}
~~~

Service sử dụng decision:

~~~java
public PricingResult calculatePrice(
        BookingRequest request,
        EvaluationContext context) {

    if (featureDecisions.enabled("booking.pricing.v2", context)) {
        return newPricingEngine.calculate(request);
    }

    return legacyPricingEngine.calculate(request);
}
~~~

Đoạn code là ví dụ minh họa. Trong production cần default/fallback khi config service timeout, cache và refresh policy, timeout ngắn, metrics theo flag key/version nhưng giới hạn cardinality, unit/integration test cho từng nhánh, context xác thực server-side và quyết định nhất quán trong một operation/transaction.

### 9.1. Không gọi feature service từ xa trên mọi request thiếu kiểm soát

SDK thường cache config hoặc evaluate local. Nếu application gọi remote feature service đồng bộ cho mọi request, feature service trở thành dependency critical và có thể tạo latency/failure chain. Thiết kế cần cache, local evaluation, last-known-good và fallback theo mức criticality.

### 9.2. Server-side enforcement

Client-side flag hữu ích để ẩn UI hoặc điều khiển trải nghiệm, nhưng không được coi là quyền bảo mật. Người dùng có thể sửa JavaScript hoặc gọi endpoint trực tiếp. API phải tự kiểm tra entitlement/authorization.

## 10. Testing feature flag và dark launch

### 10.1. Flag test matrix

Với mỗi flag quan trọng, test enabled, disabled, missing/default, config service unavailable, invalid/unknown value, target match/mismatch, user/tenant đổi plan, mixed app versions trong rolling deployment và expired flag. Không nhất thiết tạo test cho mọi tổ hợp của hàng chục flag; ưu tiên pairwise/risk-based testing và tránh flag interaction không có sơ đồ dependency.

### 10.2. Dark launch validation

Đo output parity/difference rate, error/timeout, latency p50/p95/p99, CPU/memory/DB query/connection, queue lag/retry, egress/data scanned, side effect count, data classification/retention và cost delta.

### 10.3. Experiment correctness

Với A/B test, assignment cần ổn định; cohort không overlap ngoài chủ đích; randomization unit phù hợp; primary metric và guardrail metric được xác định trước; sample size/duration có căn cứ; không dừng sớm chỉ vì kết quả tạm thuận lợi; kiểm tra sample ratio mismatch và instrumentation; tuân thủ consent/privacy policy.

Feature flag phục vụ experimentation không thay thế thiết kế thống kê hoặc phê duyệt privacy.

## 11. Telemetry và release health

Một rollout cần quan sát cả hệ thống và tác động nghiệp vụ. Dashboard nên phân biệt artifact version, flag key/state/version, cohort/region/service tier, endpoint/operation class và release timestamp.

| Nhóm | Metric |
| --- | --- |
| Exposure | Eligible users/tenants, evaluated, enabled, actual exposure |
| Reliability | Error rate, timeout, crash, availability |
| Performance | p50/p95/p99, CPU, memory, DB latency |
| Business | Conversion, booking success, payment completion, abandonment |
| Data | Schema error, reconciliation mismatch, duplicate |
| Background | Queue lag, job duration, retry, DLQ |
| Cost | Compute delta, query scan, egress, storage |
| Safety | Kill switch state, unauthorized targeting, audit failures |

### 11.1. Guardrail metric

Trước rollout, định nghĩa điều kiện dừng: error rate vượt baseline, p95 latency vượt SLO, payment duplicate hoặc reconciliation mismatch khác zero, DB CPU/connection vượt threshold, queue age vượt deadline, business conversion giảm đáng kể, unexpected egress hoặc cost spike.

Ngưỡng phải được định lượng theo baseline và traffic. Một metric tăng nhẹ có thể do seasonality hoặc traffic mix; cần so sánh cohort/canary phù hợp.

### 11.2. Exposure denominator

Tỷ lệ flag enabled không nhất thiết là tỷ lệ người dùng thực sự dùng tính năng. Cần phân biệt eligible, targeted, evaluated, enabled và feature used. Flag bật cho một tenant nhưng user không mở trang mới; adoption thấp dù enablement 100%.

## 12. Governance: owner, expiry và flag debt

Flag tạo thêm nhánh logic. Nếu không dọn dẹp, codebase có thể chứa hàng trăm flag cũ, khiến test matrix phình to và hành vi khó dự đoán.

~~~mermaid
stateDiagram-v2
    [*] --> Proposed
    Proposed --> Approved
    Approved --> Active
    Active --> Expiring
    Expiring --> Removed
    Active --> Disabled
    Disabled --> Removed
    Approved --> Rejected
~~~

Mỗi flag nên có owner/team, purpose/business ticket, type/risk, created/review/expiry date, default per environment, targeting rule, dependent code/schema, rollback instruction, metric/experiment link và removal PR/retirement ticket.

### 12.1. Temporary flag phải có expiry

Đến hạn, owner quyết định:
- Promote: giữ implementation mới và xóa flag/legacy branch.
- Rollback: tắt feature và xóa code chưa dùng.
- Extend: ghi lý do, approver và ngày mới.
- Convert: operational control thực sự cần lâu dài được quản trị như capability khác.

Không để flag tạm thời trở thành cấu hình vĩnh viễn chỉ vì không ai nhớ tới.

### 12.2. Flag debt metrics

Theo dõi flag không owner, quá expiry, không còn được evaluate, code path chưa xóa, quá nhiều targeting rules, owner nghỉ/chuyển team, config không có audit và rollback chưa được test.

## 13. Bảo mật và kiểm soát thay đổi flag

Feature config có thể thay đổi hành vi production mà không deploy artifact, do đó quyền chỉnh flag tương đương quyền thay đổi production.

Controls:
- RBAC theo environment và flag namespace.
- Tách quyền author, approver và operator cho high-risk flags.
- MFA/SSO cho console quản trị.
- Audit actor, old/new value, target, timestamp và reason.
- Approval/change ticket cho payment, security, data migration hoặc tenant-wide flags.
- Two-person review cho kill switch hoặc critical release khi policy yêu cầu.
- Signed/config versioned rollout và rollback.
- Rate limit cho config update.
- Secret không lưu trong flag value.
- Tenant targeting không được vượt data access policy.
- Break-glass có expiry và post-change review.

Không expose toàn bộ flag catalog ra browser nếu tên/key/metadata tiết lộ capability nội bộ. Client chỉ nhận decision cần thiết và không chứa secret hoặc điều kiện bảo mật.

## 14. Các lỗi thường gặp

| Lỗi | Hệ quả | Cách khắc phục |
| --- | --- | --- |
| Dùng flag thay authorization | Client bypass được quyền | Server-side entitlement/security check |
| Dark launch mirror write request | Duplicate payment/event/email | Read-only, sandbox hoặc side-effect guard |
| Mirror 100% không giới hạn | Tăng tải và chi phí production | Sampling, bulkhead, timeout |
| Bật flag trước khi code deploy đủ | Request vào pod chưa hỗ trợ flag | Phối hợp deployment/config order |
| Target bằng header client tự khai | Lộ tính năng/tenant sai | Trusted identity context |
| Không có default khi flag service lỗi | Request phụ thuộc control plane | Cache/fallback và local safe behavior |
| Percentage ngẫu nhiên mỗi request | User thấy hành vi không nhất quán | Stable assignment key |
| Tắt flag nhưng schema không tương thích | Rollback thất bại | Expand-migrate-contract |
| Một flag điều khiển quá nhiều behavior | Blast radius và test phức tạp | Tách flag theo capability |
| Flag không owner/expiry | Flag debt, nhánh code tồn tại lâu | Lifecycle metadata và cleanup |
| Chỉ đo enabled rate | Không biết adoption thực | Đo eligible/evaluated/used |
| Không audit flag update | Không điều tra được thay đổi production | Immutable audit trail |

## 15. Case study: rollout pricing v2 cho nền tảng booking

### 15.1. Bối cảnh

Nền tảng booking muốn thay thuật toán tính giá để hỗ trợ discount theo thời gian thực. Pricing v2 đọc thêm dữ liệu campaign và có logic rounding mới. Rủi ro gồm giá hiển thị không khớp giá thanh toán, tăng latency, query database nặng và sai số theo currency.

Yêu cầu: không thay giá của toàn bộ booking cùng lúc; so sánh output v1/v2 trên production traffic; không charge payment hai lần; rollback behavior trong vài phút khi sai lệch; audit tenant/cohort đã nhận giá mới.

### 15.2. Các giai đoạn

**Giai đoạn A — deploy dark:** Deploy pricing v2 nhưng flag tắt với mọi tenant. Unit/integration test chạy trên staging. Production code vẫn trả kết quả v1.

**Giai đoạn B — shadow computation:** Một tỷ lệ nhỏ request đi qua pricing v2 ở chế độ read-only. Kết quả v2 được ghi vào shadow result store với correlation ID; response user vẫn đến từ v1. Không gọi payment provider từ shadow path.

**Giai đoạn C — internal pilot:** Bật cho nhân viên và synthetic tenant. So sánh pricing parity, rounding, currency và latency.

**Giai đoạn D — tenant canary:** Bật cho nhóm tenant nhỏ được phê duyệt. Theo dõi booking conversion, payment completion, price mismatch và database load.

**Giai đoạn E — progressive rollout:** Tăng cohort theo các bước đã xác định. Tại mỗi bước, chờ đủ sample và review guardrail metrics trước khi mở tiếp.

**Giai đoạn F — general release và cleanup:** Khi v2 ổn định, chuyển thành default, loại bỏ v1 sau compatibility window, xóa release flag và cập nhật documentation.

~~~mermaid
flowchart LR
    D["Deploy v2, flag off"] --> S["Shadow compute"]
    S --> P["Internal pilot"]
    P --> C["Tenant canary"]
    C --> R["Progressive rollout"]
    R --> GA["General availability"]
    GA --> CLEAN["Remove flag and v1 path"]
    S -. "Mismatch / load issue" .-> STOP["Stop / disable"]
    P -. "Guardrail breach" .-> STOP
    C -. "Business or reliability issue" .-> STOP
~~~

### 15.3. Release guardrails

- Pricing mismatch vượt tolerance: dừng rollout.
- Payment duplicate: immediate stop và reconciliation.
- API p95 vượt SLO: không mở cohort kế tiếp.
- Database query load tăng ngoài budget: giảm shadow sampling hoặc tắt shadow.
- Conversion giảm ngoài ngưỡng: phân tích cohort và business mix.
- Config service unavailable: giữ last-known-good/default safe behavior.

### 15.4. Bằng chứng kết thúc

Parity report theo currency và booking type; error/latency theo application version và flag state; tenant exposure list có quyền truy cập hạn chế; payment ledger reconciliation; cost delta của shadow workload; approval record và rollout timeline; cleanup PR xóa flag/legacy code.

## 16. Quy trình release có kiểm soát

1. Xác định business goal, owner và blast radius.
2. Phân loại thay đổi: release, experiment, operational, entitlement hay migration.
3. Chọn flag strategy và default/fallback.
4. Thiết kế targeting theo identity đã xác thực.
5. Đảm bảo version/schema compatibility.
6. Viết test cho enabled/disabled/default/error và mixed version.
7. Thiết kế dark launch có giới hạn side effect và capacity.
8. Xác định metrics, guardrails và stop conditions.
9. Deploy artifact qua CI/CD có provenance và approval.
10. Bật cohort nhỏ và quan sát đủ sample.
11. Tăng exposure theo stage; có người chịu trách nhiệm quyết định.
12. Khi có sự cố, disable flag/rollback traffic theo runbook.
13. Khi GA, retire flag, xóa legacy code và cập nhật docs.
14. Đối soát usage/cost/audit nếu thay đổi ảnh hưởng billing hoặc dữ liệu.

Một release decision record nên chứa release ID/artifact digest, flag key/version/config snapshot, environment/region/tenant cohort, approver/operator, start/end time, rollout steps, guardrail thresholds, quyết định continue/pause/rollback, incident reference, evidence links và cleanup owner/expiry.

## 17. TCO và tác động vận hành

Feature management platform giúp centralize targeting/audit nhưng cũng tạo chi phí:
- License/seat/MAU/request theo vendor.
- Network dependency và SDK traffic.
- Config caching/refresh.
- Telemetry và event retention.
- Engineering integration và test.
- Operational support, RBAC và audit.
- Shadow compute, duplicate query và storage.
- Flag cleanup và code maintenance.

Một hệ thống nhỏ có thể dùng config service đơn giản và local evaluation. Nền tảng nhiều tenant/region cần consistency, targeting, audit, approval và SDK resilience mạnh hơn. Không chọn nền tảng chỉ theo số flag; cần đo latency, availability, propagation semantics, offline behavior và data handling.

~~~text
Release experiment cost
  = Feature management cost
    + Shadow/canary compute
    + Additional database/network usage
    + Telemetry and storage
    + Engineering and operational effort
~~~

Đánh đổi chính: centralized flag service giảm duplication nhưng thêm dependency; local config giảm runtime dependency nhưng khó đồng bộ nhanh; dark launch tăng confidence nhưng tăng compute/query cost; cohort rollout giảm blast radius nhưng kéo dài release; long-lived flags hỗ trợ vận hành nhưng tăng complexity và test cost.

## 18. Bài tập thực hành

Một nền tảng SaaS muốn phát hành search v2. Search v2 dùng index mới, query nhiều field hơn và có ranking model mới. Traffic đạt 8.000 request/giây; có 600 tenant ở ba region. Một số tenant có dữ liệu restricted và yêu cầu residency. Search có thể trả stale result tối đa 2 phút, nhưng authorization/filter tenant phải chính xác.

Hãy thực hiện:

1. Phân biệt deploy và release cho search v2; xác định loại flag cần dùng.
2. Thiết kế feature flag contract gồm owner, default, environment, targeting, expiry và rollback.
3. Chọn đơn vị cohort: tenant, user hay request; giải thích tính ổn định và isolation.
4. Thiết kế dark launch/shadow read để không lộ kết quả mới và không tăng tải vượt capacity.
5. Nêu cách bảo vệ tenant filter, data residency và restricted data trong shadow path.
6. Xây rollout ladder từ internal tới GA, kèm sample/observation requirement.
7. Định nghĩa guardrail cho latency, error, search relevance, DB/index load và cost.
8. Thiết kế kill switch nếu search v2 lỗi hoặc index lag.
9. Phân tích compatibility giữa application versions cũ/mới và index schema.
10. Xây test matrix enabled/disabled/default/config service unavailable/target mismatch.
11. Thiết kế telemetry và cách so sánh output v1/v2 có cùng snapshot.
12. Tính capacity nếu mirror 10% traffic và mỗi shadow request tiêu thụ trung bình 70% compute của request chính.
13. Viết runbook pause/rollback và kế hoạch cleanup flag sau GA.
14. Viết ADR lựa chọn feature management service và mức độ centralized/local evaluation.

**Gợi ý tự đánh giá:** Bài làm đạt khi dark launch không tạo side effect hoặc rò dữ liệu, targeting không thể bị client giả mạo, rollout có điều kiện dừng, rollback tương thích schema và cost của shadow traffic được kiểm soát.

## 19. Checklist trước production

- [ ] Deploy, enablement và release được phân biệt.
- [ ] Mỗi flag có type, key, description, owner, purpose và expiry.
- [ ] Default/fail behavior được chọn theo hậu quả nghiệp vụ.
- [ ] Targeting context lấy từ identity đã xác thực.
- [ ] Feature flag không thay authorization hoặc entitlement enforcement.
- [ ] SDK/config cache có timeout, fallback và last-known-good policy.
- [ ] Dark launch không phát side effect ngoài chủ đích.
- [ ] Mirror traffic có sampling, concurrency, timeout và cost guardrail.
- [ ] PII/secret được loại hoặc bảo vệ trong shadow path và telemetry.
- [ ] Mixed application version tương thích với flag/config.
- [ ] Rollout có cohort, stages, owner và decision authority.
- [ ] Guardrail metrics, stop conditions và rollback runbook được định nghĩa.
- [ ] Kill switch đã được test và có quyền truy cập phù hợp.
- [ ] Schema/data migration hỗ trợ rollback window.
- [ ] Audit log ghi actor, target, old/new value, reason và time.
- [ ] Flag expiry và cleanup ticket được theo dõi.
- [ ] Experiment có randomization, metric, privacy và sample plan.
- [ ] Cost delta của canary/dark launch được đo.

## 20. Đánh giá theo Well-Architected

| Trụ cột | Câu hỏi khi review feature flag và release control |
| --- | --- |
| **Operational Excellence** | Flag có owner, expiry, audit, rollout decision, runbook và cleanup process không? |
| **Security** | Targeting dùng identity đáng tin; flag update có RBAC/approval; shadow data được bảo vệ không? |
| **Reliability** | Default/fallback, kill switch, canary, rollback và schema compatibility có được kiểm chứng không? |
| **Performance Efficiency** | Evaluation latency, SDK refresh, mirror load, cache và rollout capacity có phù hợp không? |
| **Cost Optimization** | Shadow compute, duplicate query, telemetry, vendor license và flag debt có được theo dõi không? |
| **Sustainability** | Có dọn code/flag cũ, tránh chạy shadow vô thời hạn và giảm tài nguyên thử nghiệm không? |

**Kết luận:** Feature flag tách việc deploy code khỏi việc phát hành hành vi; dark launch cho phép quan sát implementation mới trước khi dùng kết quả; release control giới hạn ai được tiếp cận, khi nào mở rộng và lúc nào cần dừng. Ba kỹ thuật chỉ hữu ích khi có contract, identity đáng tin, fallback an toàn, guardrail, audit và lifecycle cleanup. Hãy kiểm soát side effect và capacity của shadow traffic, đảm bảo rollback tương thích dữ liệu, rồi mở rộng theo bằng chứng từ telemetry và mục tiêu nghiệp vụ theo tinh thần Well-Architected.
