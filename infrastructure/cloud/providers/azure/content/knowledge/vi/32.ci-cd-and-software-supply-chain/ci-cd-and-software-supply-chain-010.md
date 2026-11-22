# Triển khai canary, blue-green và rollback trên Azure

Một dịch vụ đặt hàng chạy trên Microsoft Azure nhận hàng nghìn giao dịch mỗi phút. Phiên bản mới vừa được CI/CD triển khai có chức năng tính phí vận chuyển. Test tự động đều xanh, nhưng chỉ khi gặp người dùng thực, phiên bản này gây lỗi HTTP 500 cho một nhóm giỏ hàng. Nếu triển khai toàn bộ ngay lập tức, phần lớn khách hàng có thể bị ảnh hưởng trước khi đội vận hành kịp phản ứng.

**Canary deployment**, **blue-green deployment** và **rollback** là ba kỹ thuật giảm rủi ro phát hành bằng cách kiểm soát **phiên bản đang phục vụ**, **phần lưu lượng được chuyển sang phiên bản mới**, **điều kiện được phép tăng lưu lượng** và **cách quay về phiên bản an toàn**. Trong Azure, có nhiều cơ chế thực thi: Azure App Service deployment slots, Azure Container Apps revisions, Azure Kubernetes Service (AKS) với các bộ điều khiển routing, Azure Front Door và CI/CD pipelines. Tuy nhiên, không có một lệnh duy nhất bảo đảm rollback được cả application, database, queue và external side effects.

Bài học thuộc chương **CI/CD và chuỗi cung ứng phần mềm** trong mô-đun **CLOUD_PROVIDERS_AZURE**: học cách triển khai, giám sát, bảo vệ và kiểm soát chi phí kiến trúc ứng dụng Azure, gắn với subscription, resource group, Microsoft Entra ID, mạng ảo, tính toán, lưu trữ, cơ sở dữ liệu và nền tảng container.

**Phạm vi thực hành:** dùng tên tài nguyên giả định, subscription và resource group lab được phê duyệt; không thực thi lệnh thay đổi lưu lượng hoặc swap trên production nếu chưa có quyền và change approval. Các ví dụ CLI/YAML thể hiện cơ chế hỗ trợ ở phiên bản Azure/extension/controller tương ứng; trước khi áp dụng phải kiểm tra help, SKU, region, workload và release của công cụ. Thay đổi traffic, revision activation hoặc schema database có thể gây gián đoạn hoặc phát sinh phí.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **rolling**, **recreate**, **canary**, **blue-green**, **feature flag** và **A/B testing**.
2. Giải thích khác biệt giữa deployment, release và traffic cutover.
3. Mô tả luồng **build once, deploy same immutable artifact**, sử dụng image digest và provenance.
4. Thiết kế canary với các mức traffic **1% → 5% → 20% → 50% → 100%**, có hold và rollback gates.
5. Hiểu vì sao traffic percentage không đồng nghĩa chính xác tỷ lệ người dùng hay giao dịch.
6. Thiết kế blue-green có môi trường xanh/dự phòng, smoke tests, switch và rollback window.
7. Thực hiện canary/swap có điều kiện trên **Azure App Service deployment slots**.
8. Điều phối traffic qua **Azure Container Apps revisions** khi bật multiple revision mode.
9. Phân biệt AKS **Deployment rolling update**, blue-green bằng Service selector, và canary qua ingress/Gateway API hoặc service mesh.
10. Giải thích Azure Front Door origin weight/priority, health probes, session affinity và giới hạn traffic split.
11. Thiết lập **progressive delivery gates** dựa vào p95/p99 latency, 5xx, conversion, DB errors, queue lag và business metrics.
12. Phân biệt **instant traffic rollback**, redeploy artifact và **database recovery**.
13. Thiết kế schema migration **expand–migrate–contract** để nhiều phiên bản cùng đọc/ghi được.
14. Xử lý session stickiness, caching, sticky cookies, asynchronous workers và stateful dependencies.
15. Kết hợp Azure DevOps/GitHub Actions approvals, môi trường protected và permission tối thiểu.
16. Kiểm soát secrets qua Key Vault, managed identity/workload identity, ACR và chuỗi cung ứng phần mềm.
17. Lập runbook sự cố, dự báo chi phí chạy song song và diễn tập rollback trên staging.
18. Phân biệt hoàn tất kỹ thuật của pipeline với **bằng chứng bản phát hành thật sự an toàn**.

## 2. Tại sao deploy thành công chưa có nghĩa release thành công?

### 2.1. Deployment và release là hai mốc khác nhau

- **Build:** tạo artifact JAR/container image từ một commit đã xác định.
- **Deployment:** đặt artifact vào một runtime hoặc môi trường/slot/revision.
- **Release:** cho người dùng thực sử dụng tính năng/phiên bản đó.
- **Traffic cutover:** đổi định tuyến từ phiên bản cũ sang mới.
- **Rollout:** quá trình tăng phạm vi sử dụng qua các giai đoạn.
- **Rollback:** trả traffic hoặc code/config về trạng thái đã biết hoạt động; không đồng nhất với khôi phục mọi dữ liệu đã bị sửa.

~~~mermaid
flowchart LR
    C["Git commit"] --> CI["CI: test, scan, build"]
    CI --> A["Immutable artifact + digest"]
    A --> DEP["Deploy revision/slot Green"]
    DEP --> TEST["Warm-up / smoke / security checks"]
    TEST --> G{"Approval + SLO gate"}
    G -->|PASS| TRAF["Progressive traffic"]
    G -->|FAIL| STOP["Keep stable serving"]
    TRAF --> OBS["Observe metrics / traces"]
    OBS --> DEC{"Healthy?"}
    DEC -->|Yes| PROM["Promote to 100%"]
    DEC -->|No| RB["Traffic rollback"]
~~~

Trong một kiến trúc trưởng thành, **artifact đã deploy nhưng chưa nhận user traffic vẫn chưa được release rộng rãi**. Smoke tests giúp phát hiện lỗi sớm, nhưng không thay thế quan sát traffic thực.

### 2.2. Những lỗi chỉ thấy sau release

- Lỗi chỉ xuất hiện trên account có một tập feature flags hiếm.
- Cấu hình Managed Identity có quyền staging nhưng thiếu quyền production.
- Thông số HikariCP/connection pool tạo quá nhiều connections khi scale.
- Azure SQL hoặc Cosmos DB bị throttling do query thay đổi.
- JWT claims hoặc tenant data khác với dữ liệu test.
- Front Door cache giữ nội dung/headers cũ.
- Session affinity khiến một nhóm user chỉ ở phiên bản lỗi.
- Queue consumer mới không đọc được message schema cũ.
- Database migration phá backward compatibility.
- Lỗi HTTP 429 xuất hiện khi traffic thật tăng.
- Một API của bên thứ ba giới hạn quota ở production.

**Điều kiện release phải bao gồm dữ liệu từ vận hành thực** chứ không chỉ trạng thái xanh của build.

### 2.3. Blast radius và khả năng phát hiện

Giả sử có 10.000 requests/phút và bản mới có 2% requests thất bại:

| Lưu lượng vào bản mới | Requests/phút tới bản mới | Số lỗi kỳ vọng/phút ở bản mới |
|---|---:|---:|
| 1% | 100 | 2 |
| 5% | 500 | 10 |
| 20% | 2.000 | 40 |
| 50% | 5.000 | 100 |
| 100% | 10.000 | 200 |

Đây là phép tính minh họa: traffic split chỉ gần đúng, samples không độc lập hoàn toàn và lỗi có thể theo một phân khúc người dùng. **Giảm blast radius** quan trọng, nhưng canary quá nhỏ cũng khiến tín hiệu lỗi hiếm khó phát hiện. Cần cân bằng sample size, hold time và độ nhạy của metric gates.

## 3. So sánh các chiến lược triển khai

### 3.1. Recreate, rolling, blue-green, canary

| Chiến lược | Cách hoạt động | Lợi ích | Rủi ro/giới hạn |
|---|---|---|---|
| **Recreate** | Dừng version cũ rồi chạy version mới | Đơn giản, ít runtime song song | Downtime và rollback chậm |
| **Rolling update** | Thay instances từng đợt trong cùng workload | Ít tốn tài nguyên hơn blue-green | Có hai versions đồng thời; traffic control không chính xác |
| **Blue-green** | Hai môi trường phiên bản hoàn chỉnh, chuyển traffic giữa chúng | Cutover/rollback nhanh khi giữ bản cũ | Tốn chi phí 2 môi trường, database/state phức tạp |
| **Canary** | Bản mới nhận một phần traffic, tăng dần nếu tốt | Giảm blast radius và dựa vào metrics | Cần routing, sample size, phân tích và automation |
| **Shadow/mirror** | Gửi bản sao request tới bản mới nhưng không dùng output | So hiệu năng/hành vi với traffic thật | Không an toàn với side effects; phải sanitize dữ liệu |
| **Feature flag** | Đóng/mở chức năng cho đối tượng nhất định | Tách phát hành code khỏi bật tính năng | Không thay thế rollback binary/schema |
| **A/B testing** | Chia cohort để đo tác động sản phẩm | So conversion/experience | Mục tiêu thí nghiệm khác an toàn release |

Canary và blue-green **có thể kết hợp**: triển khai bản xanh (green) hoàn chỉnh, đưa một phần traffic tới green, rồi tăng lên 100%, giữ blue để rollback.

### 3.2. Canary khác A/B testing

- Canary đánh giá **an toàn và sức khỏe kỹ thuật** của release: error rate, latency, saturation, data correctness.
- A/B testing đánh giá **tác động sản phẩm**: conversion, retention, revenue, hành vi người dùng.
- Canary có thể dùng routing theo tỷ lệ; A/B thường cần cohort assignment ổn định để tránh biến động nhóm.
- Cả hai đều có thể dùng feature flags, nhưng **decision gates** khác nhau.

Không dùng conversion tăng nhẹ làm lý do bỏ qua error rate 5xx đang tăng gấp mười lần. Cũng không kết luận một thuật toán sản phẩm kém hơn chỉ vì 5% canary traffic bị lệch geography/device mix.

### 3.3. Mẫu lựa chọn

~~~mermaid
flowchart TD
    Q{"Có thể chạy song song hai versions?"}
    Q -->|Không| M["Thiết kế backward compatibility / bảo trì"]
    Q -->|Có| S{"Có kiểm soát traffic split?"}
    S -->|Có| C["Canary hoặc blue-green + canary"]
    S -->|Không| B["Blue-green full cutover / rolling"]
    C --> O["Metric gates + rollback runbook"]
    B --> O
    O --> DB{"State/schema compatible?"}
    DB -->|Không| FIX["Expand-contract trước release"]
    DB -->|Có| GO["Phê duyệt deploy"]
~~~

Không phải cứ có Azure Load Balancer là có weighted canary: cân nhắc **khả năng thực của tầng routing** đang dùng.

## 4. Điều kiện cần trước khi triển khai progressive delivery

### 4.1. Immutable artifact và version rõ

Một pipeline tốt có một artifact duy nhất:

~~~text
Git commit: 19a24d... (ví dụ)
  → build + test + scan
  → container image: acrorders.azurecr.io/orders@sha256:<digest>
  → deploy đúng digest đó lên staging/green
  → smoke & approval
  → promote/canary production bằng chính digest
~~~

**Không rebuild từ tag "latest" cho production sau khi test staging**: các dependency hoặc thời điểm build khác có thể tạo artifact khác. Prefer image digest/SBOM/provenance, tag immutable được áp policy.

### 4.2. Tách cấu hình và secrets

- Config theo môi trường nằm trong App Configuration, environment settings hoặc hệ thống config có governance.
- Secret được lấy qua Azure Key Vault/managed identity/AKS workload identity hoặc platform integration thích hợp.
- Cả blue và green phải có permissions/network/DNS đúng.
- Không để test slot vô tình dùng payment production secrets hay ghi vào DB production nếu smoke test tạo dữ liệu.
- Cấu hình cố định theo slot/revision cần được phân biệt với cấu hình đi theo artifact.
- Có diff cấu hình trước khi swap để tránh release thành công nhưng thiếu authorization.

### 4.3. Readiness khác liveness

- **Liveness:** tiến trình còn hoạt động, không deadlock nghiêm trọng.
- **Readiness:** instance có thể phục vụ traffic đúng không (loaded config, warm-up, dependencies quan trọng).
- **Startup probe:** cho thời gian khởi động ứng dụng nặng trước khi liveness kiểm tra quá sớm.
- **Synthetic smoke test:** chủ động gọi một số chức năng qua endpoint của bản mới.
- **Business canary test:** test đường giao dịch chính nhưng không gây side effects production thật.

Một HTTP 200 từ **/** không chứng minh JDBC connection, quyền Key Vault hoặc Service Bus sender hoạt động. Readiness cũng không nên hard-fail vì một optional analytics service tạm lỗi nếu việc đó làm cả cluster mất serving capacity.

### 4.4. Đường rollback phải tồn tại trước đường promote

Trước khi chuyển 1% traffic cần xác nhận:
1. Stable version/image digest nào có thể chạy lại?
2. Stable slot/revision/pods còn được giữ và healthy?
3. Có lệnh hoặc IaC để định tuyến về stable?
4. Feature flags/config có thể quay lại không?
5. Schema database vẫn cho stable code chạy không?
6. Event payload từ version mới có được stable worker đọc không?
7. Có runbook xử lý những writes đã commit bởi version mới?
8. Quy trình approval/permissions khi rollback có kịp RTO không?
9. Có ai chịu trách nhiệm quyết định và đo xác nhận sau rollback?

**Rollback chưa từng diễn tập thường chỉ là giả định, không phải năng lực đã chứng minh.**

## 5. Thiết kế traffic splitting đúng

### 5.1. Phân biệt request %, user % và business %

Nếu routing chuyển 10% HTTP requests tới canary, điều đó không bảo đảm:
- 10% unique users được thấy bản mới.
- 10% đơn hàng đi qua canary.
- 10% messages nền được xử lý bởi worker mới.
- 10% requests trên mỗi region/device/tenant.
- 10% CPU hoặc chi phí.
- 10% các đường xử lý có rủi ro cao như payment.

Một user có thể gửi 100 requests khi user khác chỉ gửi một. Sticky cookies/session affinity có thể làm tỷ lệ phân bổ khác request-weight mong muốn. Client retries và CDN cache cũng ảnh hưởng lượng thực tế đến origin.

### 5.2. Chia theo traffic weight và theo cohort

| Cách | Dùng khi | Vấn đề cần cân nhắc |
|---|---|---|
| Random weighted request | Hệ thống stateless, request độc lập | Một user có thể đổi phiên bản giữa requests |
| Sticky session | Session state hoặc cần nhất quán user experience | Session persistence, uneven traffic |
| Stable hash theo user | Canary theo cohort rõ | PII và hash/routing config governance |
| Header/cookie route | QA/nhân viên kiểm thử version mới | Không tin header do user tự khai nếu có security impact |
| Geographic ring | Canary từng region/site | Khác profile traffic, latency, compliance |
| Tenant allowlist | Enterprise pilot có thỏa thuận | Một tenant có lưu lượng rất lớn |
| Feature flag cohort | Bật hành vi theo user/tenant | Không giải quyết binary crashes khi toàn bộ process vẫn nhận traffic |

### 5.3. Cần có hold window

Mỗi mức traffic phải giữ đủ lâu để:
- Thu đủ request count/signal.
- Chờ telemetry ingestion delay.
- Ghi nhận startup spikes và cache warm-up.
- Quan sát p95/p99 latency.
- Gặp cron/background jobs quan trọng.
- Kiểm tra queue backlog và eventual consistency.
- Quan sát chi phí và downstream load.

Giữ 10% trong 30 giây chỉ vì dashboard xanh thường không đủ khi lỗi xảy ra vào batch job mỗi 15 phút. Ngược lại, giữ quá lâu có thể không phù hợp với security hotfix khẩn cấp; khi đó áp risk-based approval và rollback plan rõ.

## 6. Tín hiệu quyết định promote hay rollback

### 6.1. Metric gate không chỉ có HTTP 200

Một canary khỏe cần nhiều nhóm tín hiệu:

| Nhóm | Ví dụ signal | Cần so với |
|---|---|---|
| Availability | 5xx, request failure, crashloop | Stable version và SLO |
| Latency | p50/p95/p99 theo route | Baseline cùng thời điểm/region |
| Saturation | CPU, memory, GC, thread pool, HikariCP | Stable và capacity limit |
| Dependencies | SQL timeouts, Cosmos RU throttling, Key Vault 403/429 | Release trước, quota |
| Messaging | Service Bus active messages, DLQ, processing lag | Consumer baseline |
| Business | Orders completed, payment failures, duplicate invoices | Business thresholds |
| Security | Auth failure spike, access denied, unusual egress | Security policy |
| Telemetry quality | Trace/metric coverage, log ingestion health | Monitoring pipeline |
| Cost | Requests tới Azure APIs, egress, replicas, DB load | Expected budget |

Có thể định nghĩa critical gates (fail → rollback ngay) và warning gates (hold/investigate) thay vì một tổng điểm che mất lỗi nghiêm trọng.

### 6.2. Một chính sách canary minh họa

~~~text
Canary stages: 1% → 5% → 20% → 50% → 100%
Hold windows: 10m → 15m → 20m → 30m

Trong mỗi hold:
  min requests to canary: >= 500
  canary HTTP 5xx <= 1.0%
  canary 5xx <= stable 5xx + 0.5 percentage point
  canary p95 <= 1.25 × stable p95
  payment failure rate <= approved business threshold
  no critical data-integrity incident
  no new high-severity security failure
  sufficient telemetry freshness/coverage

On critical gate failure:
  stop promotion
  route traffic back to stable
  disable dangerous feature flags if needed
  preserve evidence
  verify recovery
~~~

**Đây là ví dụ, không phải ngưỡng Microsoft Azure hay ngưỡng dùng được cho mọi ứng dụng.** Đặt ngưỡng thật theo SLO/business risk, baseline có ý nghĩa, sample size và độ chính xác metric. Với traffic nhỏ, điều kiện 500 requests có thể khiến hold kéo dài hơn kế hoạch.

### 6.3. Mẫu số và những tín hiệu nhiễu

5xx rate = 5xx / total requests phải được tính trên **traffic của đúng version**, tránh trộn traffic stable/canary. Cần loại hoặc phân loại:
- Health probe URLs.
- Synthetic test traffic.
- User-cancelled requests.
- Expected 4xx validation.
- App retries/gateway retries.
- Time range chồng chéo.
- Traffic khác tenant/geography có baseline khác.

Một canary 1% chỉ nhận 100 requests mà có 1 lỗi đã là 1%. Không rollback vì một lần 404 dự kiến; nhưng **một lỗi mất dữ liệu/thu phí hai lần** có thể là critical gate dù chưa đủ sample size.

### 6.4. Quan sát bằng Azure Monitor

Nguồn có thể gồm:
- Application Insights AppRequests/AppDependencies/AppExceptions.
- Azure Monitor metrics và alert rules.
- Log Analytics KQL / Workbooks.
- App Service metrics, slot-specific telemetry khi cấu hình được.
- Azure Container Apps revision metrics/logs.
- AKS kube-state metrics/Container Insights/managed Prometheus khi cấu hình.
- Azure SQL/Cosmos DB/Storage/Service Bus metrics.
- OpenTelemetry traces có service.version/role.

**KQL có ingestion delay và sampling**: đừng chỉ dựa vào sampled traces để tính toàn bộ tỷ lệ request lỗi nếu không hiểu weights. Một gate dùng metrics cần nguồn đủ mới và có thể phân tách version. Nếu không có telemetry (no data), chính sách an toàn thường là **hold**, không tự động promote.


## 7. Azure App Service: deployment slots và blue-green

### 7.1. Deployment slot là gì?

**Deployment slots** cho phép cùng một Azure App Service có nhiều môi trường runtime như production, staging hoặc test trên các gói dịch vụ hỗ trợ. Một slot có:
- Endpoint riêng để smoke test.
- Phiên bản application code/container riêng.
- Bộ app settings/connection strings và cấu hình có quy tắc **slot-specific/sticky**.
- Cơ chế **slot swap** để chuyển phiên bản đã kiểm thử sang production.
- Khả năng routing một tỷ lệ traffic tới slot không phải production khi dịch vụ hỗ trợ.

**Điều kiện:** deployment slots phụ thuộc App Service plan và tính năng SKU; thường dùng các gói **Standard, Premium hoặc Isolated** hỗ trợ slots, không giả định Free/Shared/Basic có sẵn tính năng. Kiểm tra loại app (Windows/Linux/container), region, plan và lệnh Azure CLI thực tế.

### 7.2. Sơ đồ blue-green với slots

~~~mermaid
flowchart LR
    U["Users"] --> PROD["Production hostname"]
    PROD --> B["Production slot: Blue v1"]
    STAGE["Staging slot URL"] --> G["Staging slot: Green v2"]
    Q["QA + smoke tests"] --> STAGE
    G -. "swap after approval" .-> PROD
~~~

**Trước swap:** production đang chạy Blue v1; staging chứa Green v2. **Sau swap thành công:** production nhận Green v2; staging thường giữ phiên bản trước đó của production để có đường đảo ngược, tùy swap/config behavior. Cả hai slots có thể chia sẻ App Service plan capacity; **slot không nhất thiết là môi trường compute hoàn toàn tách biệt**.

### 7.3. Preflight không thay đổi tài nguyên

~~~bash
RG="rg-orders-lab"
APP="app-orders-lab"

az account show --query "{subscription:id,tenant:tenantId}" -o json

az webapp show \
  --resource-group "$RG" \
  --name "$APP" \
  --query "{name:name,state:state,host:defaultHostName,plan:serverFarmId}" \
  -o json

az webapp deployment slot list \
  --resource-group "$RG" \
  --name "$APP" \
  -o table
~~~

Đây là các lệnh đọc metadata. Nếu không thấy staging slot, không tự tạo ở production vì slot có thể phát sinh cấu hình, capacity và chi phí vận hành.

### 7.4. Tạo staging slot trong lab được phép

~~~bash
az webapp deployment slot create \
  --resource-group "$RG" \
  --name "$APP" \
  --slot staging
~~~

Thao tác này thay đổi Azure resource và cần IAM phù hợp. Một số phương án cho phép clone configuration từ source slot; **không sao chép toàn bộ production secrets/connection strings sang staging mà không kiểm soát**.

Sau khi tạo, deploy bản Green vào staging bằng CI/CD từ **artifact đã build/test và được phê duyệt**. Không deploy lại từ nhánh source không cố định khi production dùng artifact khác.

### 7.5. Slot-specific settings và bí mật

Một số app settings/connection strings có thể được đánh dấu **deployment slot setting** (sticky), ở lại với tên slot khi swap. Điều này rất quan trọng:

- Application Insights connection string cho staging/production cần đúng target và telemetry attribution.
- Database connection strings của staging có thể phải trỏ sandbox DB.
- Managed identity, networking, hostnames/certificates và những settings khác có swap semantics riêng.
- Feature flags phải được kiểm tra trước khi promote.
- Không assume tất cả App Settings sẽ swap cùng code, hoặc tất cả settings sẽ đứng yên.

**Smoke test phải dùng tài nguyên test hoặc thao tác không gây side effects**. Nếu staging trỏ cùng production database và chạy migration khi khởi động, bản Green có thể làm hỏng dữ liệu production trước khi nhận 1% traffic.

### 7.6. Warm-up và health checks

Trước cutover, cần:
1. Đảm bảo Green process đã khởi động.
2. Warm up JIT, connection pools/cache và dependency clients.
3. Kiểm tra đúng startup configuration/identity.
4. Chạy GET readiness path hoặc smoke tests có giới hạn.
5. Kiểm tra memory, GC, CPU và HTTP dependencies.
6. Đo lỗi trong staging log/telemetry.
7. Xác nhận stable slot vẫn khỏe.

App Service có các cấu hình **swap warm-up** như WEBSITE_SWAP_WARMUP_PING_PATH và WEBSITE_SWAP_WARMUP_PING_STATUSES tùy runtime/version. **App Service Health Check** và **slot swap warm-up** là các khả năng riêng; cấu hình một health endpoint không tự đảm bảo swap wait behavior như mong muốn.

### 7.7. Swap staging → production

Khi đã được phê duyệt và preflight PASS:

~~~bash
az webapp deployment slot swap \
  --resource-group "$RG" \
  --name "$APP" \
  --slot staging \
  --target-slot production
~~~

Đây là lệnh **có tác động tới production traffic**; không chạy trong lab nếu URL đó đang phục vụ khách thật. Swap không phải phép “đổi DNS thủ công”; App Service áp swap mechanics, có bước áp dụng config/warm-up theo capabilities của platform.

**Swap with preview** có thể hỗ trợ kiểm tra cấu hình trước hoàn tất trong một số App Service environments, nhưng có giới hạn theo OS/app type; không coi nó luôn có trên Linux/container workloads.

### 7.8. Rollback bằng swap ngược

Nếu sau cutover Green lỗi:
1. Dừng promote/feature flag đáng ngờ.
2. Xác nhận staging còn chứa Blue v1 và vẫn khởi động được.
3. Kiểm tra DB/schema, secrets và queues vẫn backward compatible.
4. Nếu đáp ứng, thực hiện **swap trở lại**:

~~~bash
az webapp deployment slot swap \
  --resource-group "$RG" \
  --name "$APP" \
  --slot staging \
  --target-slot production
~~~

Cùng hướng lệnh được gọi lần thứ hai trên trạng thái sau swap để đưa phiên bản trước về production. **Không bảo đảm rollback bằng swap nếu** staging đã bị deploy đè, configuration drift, migration phá schema, slot bị xóa hoặc phiên bản cũ không còn chạy được.

Nếu không chắc trạng thái từng slot, kiểm tra **deployment version/hash, host và response headers đã sanitize** trước khi swap; đừng làm theo thói quen.

## 8. Canary trên App Service bằng traffic routing

### 8.1. Cơ chế phân phối vào deployment slots

Khi có staging slot hỗ trợ traffic routing, App Service có thể chuyển một tỷ lệ request tới staging. Mô hình:

~~~mermaid
flowchart LR
    U["Client requests"] --> ROUTER["App Service routing"]
    ROUTER -->|"90% target"| BLUE["Production slot v1"]
    ROUTER -->|"10% target"| GREEN["Staging slot v2"]
    BLUE --> OBS["Metrics by version"]
    GREEN --> OBS
~~~

Traffic split **không phải số requests tuyệt đối**. App Service có cơ chế **routing cookie** (ví dụ cookie x-ms-routing-name) để giữ client vào slot khi phù hợp. Việc thử bằng curl, browser và load generator cần xem cookies/session stickiness nếu muốn đo đúng phân phối.

### 8.2. Lệnh đặt tỷ lệ canary

Trong App Service lab đủ SKU và đã deploy Green:

~~~bash
RG="rg-orders-lab"
APP="app-orders-lab"

# Chuyển một phần lưu lượng production-hostname tới staging.
az webapp traffic-routing set \
  --resource-group "$RG" \
  --name "$APP" \
  --distribution staging=10

# Kiểm tra cấu hình thực tế trên ứng dụng.
az webapp traffic-routing show \
  --resource-group "$RG" \
  --name "$APP"
~~~

Các lệnh chỉ dùng sau approval vì thay đổi traffic người dùng. Cần xác nhận **staging slot readiness, auth/config và endpoints** trước. Nếu lệnh thiếu hoặc khác cú pháp theo Azure CLI version, xem az webapp traffic-routing --help trong môi trường quản trị được phép; không tự suy ra tính năng có trên mọi plan.

### 8.3. Lộ trình tăng traffic

~~~text
T0: Staging Green đã deploy, warm-up, smoke PASS
T1: App Service routing staging=1%
    → chờ đủ request count + quan sát
T2: staging=5%
    → đo error rate và p95 theo version
T3: staging=20%
    → kiểm tra DB/queue/business metrics
T4: staging=50%
    → capacity, frontend/session behavior
T5: promote/swap hoặc đưa Green lên production theo plan
~~~

Khi traffic đã được chuyển 100% tới staging bằng routing, trạng thái deployment slots/cấu hình vẫn khác với thực hiện **swap**. Phải chọn rõ **mục tiêu cuối cùng**: traffic routing hay cutover qua swap; không đặt 100% staging rồi mặc định code đã chuyển thành production slot.

### 8.4. Hủy traffic routing là rollback của giai đoạn canary

Khi staging Green lỗi và production Blue còn khỏe:

~~~bash
az webapp traffic-routing clear \
  --resource-group "$RG" \
  --name "$APP"
~~~

Lệnh này đưa routing về mặc định (production slot), theo cấu hình đang áp dụng. **Nó không rollback code đã swap**. Nếu production slot đang là Green vì swap đã xảy ra, clear routing chỉ bỏ tỷ lệ, không quay lại Blue; cần xem trạng thái slot và chiến lược rollback riêng.

### 8.5. Session stickiness và tác động đo lường

- Browser có thể mang cookie quyết định slot qua nhiều requests.
- Traffic test dùng một cookie jar duy nhất có thể đều rơi vào một version.
- Một request đầu tiên chưa chắc được xử lý đúng tỷ lệ trong mẫu cực nhỏ.
- Long-lived connections/WebSocket có behavior khác request stateless.
- Authentication redirect/hostnames có thể ảnh hưởng session.
- Kết quả canary cần phân tách theo version/slot, không chỉ domain.

Đừng gửi **production secrets** vào header chỉ để ép routing. Nếu QA cần kiểm tra staging URL/slot, sử dụng các cơ chế thử được bảo vệ và test accounts.

### 8.6. Hạn chế slot isolation

Cả staging và production slots có thể chia sẻ App Service plan CPU/memory. Một Green v2 memory leak có thể làm **Blue v1 chậm** dù Green chỉ nhận 5% traffic. Vì vậy canary phải giám sát **stable health** song song; “canary 5%” không phải blast radius chỉ 5% trong mọi tình huống.

## 9. Azure Container Apps: revisions và traffic splitting

### 9.1. Revision là gì?

**Azure Container Apps revision** là snapshot bất biến của một tập **revision-scope** settings: image, command, env vars, scaling template và cấu hình tương ứng. Thay đổi một số thuộc tính sẽ tạo revision mới; các thay đổi application-scope như secrets/ingress có semantics khác.

Container Apps có các **revision modes**:
- **Single:** thường duy trì một active revision phục vụ traffic tại một thời điểm; hỗ trợ rollout theo platform nhưng không cho phép bạn chủ động giữ hai active revisions với tỷ lệ traffic như multiple.
- **Multiple:** nhiều revisions có thể active, cho phép gán **traffic weights** qua ingress, phục vụ canary và blue-green.

Một revision tồn tại không đồng nghĩa nó active hoặc có healthy replicas. Cần kiểm tra cả trạng thái, ingress và scale.

### 9.2. Sơ đồ

~~~mermaid
flowchart LR
    C["Internet / private ingress"] --> ING["Container Apps ingress"]
    ING -->|"95%"| R1["orders--stable revision"]
    ING -->|"5%"| R2["orders--canary revision"]
    R1 --> DB["Shared database / services"]
    R2 --> DB
    R1 --> MET["Revision metrics / logs"]
    R2 --> MET
~~~

Ingress traffic splitting áp cho HTTP ingress như được hỗ trợ; **không tự chia 5% Azure Service Bus messages** giữa workers tiêu thụ queue. Queue-driven background workers có scale rules và cạnh tranh consumer riêng, phải thiết kế migration/compatibility tách biệt.

### 9.3. Đọc trạng thái app và revisions

~~~bash
RG="rg-orders-lab"
APP="ca-orders-lab"

az containerapp show \
  --resource-group "$RG" \
  --name "$APP" \
  --query "{name:name,activeMode:properties.configuration.activeRevisionsMode}" \
  -o json

az containerapp revision list \
  --resource-group "$RG" \
  --name "$APP" \
  --output table

az containerapp show \
  --resource-group "$RG" \
  --name "$APP" \
  --query "properties.configuration.ingress.traffic" \
  -o json
~~~

Không đoán revision names chỉ từ tag; tên thật có suffix được tạo theo rollout/revision suffix và được trả về từ API.

### 9.4. Bật multiple revisions mode trong lab

~~~bash
az containerapp revision set-mode \
  --resource-group "$RG" \
  --name "$APP" \
  --mode multiple
~~~

Lệnh làm thay đổi cách app quản lý revisions, chỉ chạy khi đã có approval. Trong hệ thống đang live, thay mode hoặc active revisions có thể thay đổi traffic/scale behavior. Xác minh Azure Container Apps CLI extension/version theo môi trường.

### 9.5. Đặt trọng số 95/5

Giả sử đã có hai revisions **active**, healthy và được xác minh tên:

~~~bash
STABLE="ca-orders-lab--stable123"  # Thay bằng revision thật
CANARY="ca-orders-lab--new456"     # Thay bằng revision thật

az containerapp ingress traffic set \
  --resource-group "$RG" \
  --name "$APP" \
  --revision-weight "$STABLE=95" "$CANARY=5"
~~~

Trọng số của các traffic destinations được cấu hình phải tổng 100 theo contract của ingress. **Không deploy revision rồi lập tức chuyển traffic** khi readiness/startup và secrets chưa kiểm tra. Nếu một revision có scale-to-zero, cần xem cold-start và readiness khi canary nhận request đầu.

### 9.6. Rollback traffic về stable

Khi gate thất bại:

~~~bash
az containerapp ingress traffic set \
  --resource-group "$RG" \
  --name "$APP" \
  --revision-weight "$STABLE=100" "$CANARY=0"
~~~

Sau đó kiểm tra ingress weights và health của stable. **Không deactivate/delete canary ngay lập tức** nếu còn connections, logs cần thu, side effects hoặc evidence cần giữ. Deactivate/delete phải có approval riêng và retention policy.

### 9.7. Blue-green bằng revisions và labels

Một phương án là:
- Green revision deploy song song, không nhận production traffic.
- Test bằng revision-specific URL/label URL khi môi trường hỗ trợ.
- Gán traffic stable 100% → Green 100% khi pass.
- Giữ Blue active đủ rollback window.
- Khi lỗi, trả traffic 100% về Blue.

Container Apps có cơ chế **revision labels** để cung cấp endpoint ổn định cho revision theo khả năng ingress và cách cấu hình. Labels hữu ích cho test/cutover nhưng **label URL không tự tương đương traffic weight**. Phải kiểm tra routing config thật.

### 9.8. Revision-scope, secrets và configuration drift

- Thay image/env template thường tạo revision.
- Thay application-scope secrets không nhất thiết tạo revision hoặc reload secrets trong process.
- Managed identity/network/registry auth phải phù hợp với cả revisions.
- Revision rollback không tự rollback external secret value.
- Một revision cũ có thể không còn khởi động nếu image đã bị xóa khỏi ACR hoặc key đã rotate.
- Custom domains/TLS/certificates/cookies cần kiểm thử ở đúng ingress.
- Workers không có HTTP ingress không dùng traffic weights như một HTTP app.

**Giữ một revision cũ chỉ hữu ích khi artifact, identity, network và data schema vẫn cho phép nó phục vụ được.**


## 10. AKS: rolling update không tự tương đương canary có trọng số

### 10.1. Deployment rolling update

Kubernetes Deployment hỗ trợ chiến lược **RollingUpdate** với **maxSurge** và **maxUnavailable**. Ví dụ:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders
  namespace: commerce
spec:
  replicas: 4
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  selector:
    matchLabels:
      app: orders
  template:
    metadata:
      labels:
        app: orders
        version: v2
    spec:
      containers:
        - name: orders
          image: acrorders.azurecr.io/orders@sha256:<approved-digest-v2>
          ports:
            - containerPort: 8080
          readinessProbe:
            httpGet:
              path: /ready
              port: 8080
            periodSeconds: 5
            failureThreshold: 3
          resources:
            requests:
              cpu: 250m
              memory: 512Mi
            limits:
              memory: 1Gi
~~~

Đây là **YAML minh họa cần thay digest, namespace, resource settings và cấu hình image pull/trust**. Phải tạo namespace, identity/ACR authorization, networking và readiness endpoint trong lab trước khi apply; không copy thẳng vào production.

Ý nghĩa:
- maxSurge: 1 cho phép tối đa một Pod mới tăng thêm so với desired replicas, cần cluster capacity.
- maxUnavailable: 0 cố giữ số Pod available trong điều kiện thông thường, dựa vào readiness và termination.
- Rollout vẫn có thể thất bại vì node quota, pending Pods, readiness sai hoặc external dependencies.
- Một Service trỏ vào tất cả Pods ready có thể phục vụ đồng thời versions cũ và mới trong giai đoạn rollout.

**RollingUpdate không đảm bảo 10% request traffic vào v2.** Số Pods mới không tự phản ánh request distribution, vì connection reuse, session affinity và tải các Pods không đồng nhất.

### 10.2. Kiểm tra rollout và lịch sử

~~~bash
NS="commerce"
DEP="orders"

kubectl rollout status \
  deployment/"$DEP" \
  -n "$NS" \
  --timeout=5m

kubectl get deployments,pods \
  -n "$NS" \
  -l app=orders \
  -o wide

kubectl rollout history \
  deployment/"$DEP" \
  -n "$NS"
~~~

Các lệnh trên chỉ kiểm tra trạng thái. **kubectl rollout status thành công không bảo đảm business metrics pass**: readiness probes có thể xanh trong khi 5% orders bị tính sai phí.

### 10.3. Rollout undo trong trường hợp phù hợp

Khi một rolling update lỗi và phiên bản trước vẫn còn trong history:

~~~bash
kubectl rollout undo deployment/orders -n commerce
kubectl rollout status deployment/orders -n commerce --timeout=5m
~~~

**Giới hạn:**
- Chỉ phục hồi Deployment Pod template/revision được Kubernetes giữ; không hoàn tác schema/secret/external writes.
- Không chắc image cũ còn tải được nếu đã bị xóa khỏi Azure Container Registry.
- Nếu GitOps (Flux/Argo CD) hoặc pipeline vẫn reconcile desired state v2, lệnh undo thủ công có thể bị ghi đè trở lại.
- Phải sửa **source of truth** (GitOps manifests/release config) và reconcile có kiểm soát; đừng để production liên tục flip-flop.

### 10.4. Pod readiness và graceful termination

Để rollback không mất traffic:
- readinessProbe phải loại Pod khỏi endpoints khi nó không còn phục vụ được.
- preStop hook và terminationGracePeriodSeconds cho request inflight kết thúc phù hợp.
- App/nginx/sidecar cần hỗ trợ graceful shutdown.
- Tránh readiness kiểm tra database bằng write không được phép.
- Thiết kế PodDisruptionBudget theo khả năng cluster và maintenance.
- HPA/Cluster Autoscaler/Node pools phải đủ capacity cho surge và hai versions.
- Cần theo dõi 502/503 do connection draining khi cắt traffic.

Nếu có một worker tiêu thụ queue, readiness/termination chưa đủ: phải dừng nhận messages mới, hoàn thành hoặc trả message lock/offset đúng để tránh duplicate hoặc mất việc.

## 11. AKS blue-green với hai Deployments và một Service

### 11.1. Mô hình tách phiên bản bằng labels

Có hai Deployments độc lập:
- orders-blue: Pods có labels **app=orders, track=blue**.
- orders-green: Pods có labels **app=orders, track=green**.
- Một Kubernetes Service **orders** chọn một trong hai nhóm bằng selector track.

~~~mermaid
flowchart LR
    R["Ingress / Gateway"] --> S["Service orders"]
    S -->|"selector track=blue"| B["Deployment orders-blue"]
    S -. "switch selector" .-> G["Deployment orders-green"]
~~~

Green có thể được smoke test qua Service riêng (orders-green-preview) hoặc route internal được bảo vệ, không nhận production traffic trước cutover.

### 11.2. Service chọn Blue

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: orders
  namespace: commerce
spec:
  selector:
    app: orders
    track: blue
  ports:
    - name: http
      port: 80
      targetPort: 8080
  type: ClusterIP
~~~

Hai Deployments cần dùng Pod labels tương ứng và có readiness; **không tự sửa selector của Deployment** sau khi tạo vì có giới hạn immutability. Trong một blue-green design, tạo và giữ hai Deployments thay vì đổi tên/selector liên tục.

### 11.3. Cắt traffic Blue → Green

Chỉ trên môi trường có approval:

~~~bash
kubectl patch service orders \
  -n commerce \
  --type merge \
  -p '{"spec":{"selector":{"app":"orders","track":"green"}}}'
~~~

Sau đó phải kiểm tra Endpoints/EndpointSlices, readiness, 5xx, session draining và telemetry:

~~~bash
kubectl get service orders -n commerce -o yaml
kubectl get endpointslice -n commerce \
  -l kubernetes.io/service-name=orders
~~~

**Cập nhật Service selector không phải switch nguyên tử với zero connection loss ở mọi lớp.** kube-proxy/ingress/controller update và existing connections có độ trễ. Nếu gắn GitOps, thay đổi phải được commit vào manifest desired state hoặc hệ thống sẽ đưa selector về Blue.

### 11.4. Rollback ngay ở tầng routing

Khi Green có sự cố và Blue còn ready:

~~~bash
kubectl patch service orders \
  -n commerce \
  --type merge \
  -p '{"spec":{"selector":{"app":"orders","track":"blue"}}}'
~~~

Đây chỉ là traffic rollback. Nếu Green đã chạy migration không tương thích, Blue có thể lỗi sau khi traffic quay về. Nếu Green đã publish messages schema v2, Blue worker có thể không đọc được. Trước cutover phải có chứng minh **backward compatibility**.

### 11.5. Chi phí blue-green AKS

Khi duy trì đồng thời 4 Blue Pods + 4 Green Pods, có thể phải thêm nodes hoặc giảm resource quota cho các workloads khác. Một Azure Standard Load Balancer hoặc Application Gateway cũng có chi phí/giới hạn riêng; canary traffic 5% **không có nghĩa chỉ trả 5% chi phí cho Green**, vì Pods và dependencies vẫn chạy/warm.

## 12. AKS canary qua Gateway API hoặc service mesh

### 12.1. Vì sao Kubernetes Service chưa đủ?

Kubernetes Service chuẩn chọn Endpoints theo labels; nó **không có field chuẩn để đặt 90% request sang version A và 10% sang version B**. Để điều khiển weights ở tầng HTTP/L7, cần một **routing controller** hỗ trợ:

- Gateway API HTTPRoute backendRefs weights.
- Service mesh như Istio với VirtualService/DestinationRule.
- Ingress controller có tính năng canary riêng.
- Azure Front Door phía trước hai origins ở mức edge khi kiến trúc phù hợp.

Các API/CRDs phải được cài, controller phải hỗ trợ tính năng; **không phải mọi AKS cluster hỗ trợ weighted HTTPRoute hoặc Istio chỉ vì đã tạo cluster**.

### 12.2. Gateway API HTTPRoute minh họa

Có hai Services:
- orders-stable → Pods version stable.
- orders-canary → Pods version canary.

Controller phải có Gateway tên **orders-gateway** được cấu hình, và hỗ trợ HTTPRoute weighted backendRefs:

~~~yaml
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: orders-route
  namespace: commerce
spec:
  parentRefs:
    - name: orders-gateway
  hostnames:
    - "orders.example.test"
  rules:
    - matches:
        - path:
            type: PathPrefix
            value: /
      backendRefs:
        - name: orders-stable
          port: 80
          weight: 95
        - name: orders-canary
          port: 80
          weight: 5
~~~

**Đây là mẫu cần tích hợp với GatewayClass/controller thực tế.** Route chưa được Accepted/Programmed thì không có hiệu lực; kiểm tra status conditions, Gateway readiness, DNS, TLS, backend namespaces và NetworkPolicy. Controller hoặc Azure service tương ứng có thể chỉ hỗ trợ một tập con của Gateway API. Không coi mọi backendRef weight được thực thi nếu chưa xác minh controller capabilities.

### 12.3. Service mesh Istio minh họa

Khi AKS đã cấu hình service mesh/ingress theo support matrix, có thể dùng **DestinationRule subsets** và **VirtualService traffic weights**:

~~~yaml
apiVersion: networking.istio.io/v1beta1
kind: DestinationRule
metadata:
  name: orders-subsets
  namespace: commerce
spec:
  host: orders.commerce.svc.cluster.local
  subsets:
    - name: stable
      labels:
        track: stable
    - name: canary
      labels:
        track: canary
---
apiVersion: networking.istio.io/v1beta1
kind: VirtualService
metadata:
  name: orders-routing
  namespace: commerce
spec:
  hosts:
    - orders.commerce.svc.cluster.local
  http:
    - route:
        - destination:
            host: orders.commerce.svc.cluster.local
            subset: stable
          weight: 90
        - destination:
            host: orders.commerce.svc.cluster.local
            subset: canary
          weight: 10
~~~

Đây là **mẫu routing nội bộ trên service host**; một ingress external cần Gateway/host configuration bổ sung. Để subsets có tác dụng, service chọn Pods của cả hai track, labels khớp; traffic đi qua mesh data plane được cấu hình. Một ứng dụng chưa tham gia mesh hoặc client bypass sidecar sẽ không chịu VirtualService weights theo cách mong đợi.

### 12.4. Các cơ chế khác

- Một ingress controller có thể có canary annotations/properties **riêng**; không chuyển YAML của ingress controller A sang controller B mà kỳ vọng giống nhau.
- Azure Application Gateway for Containers hoặc các Gateway API implementations có tính năng/phiên bản riêng; kiểm tra hỗ trợ weighted backendRef trước khi thiết kế production.
- Azure Load Balancer cơ bản phục vụ L4 traffic, **không tự cung cấp canary HTTP weights theo release**.
- Kubernetes native rollout chỉ thay Pods theo batches, không có automatic SLO analysis.

### 12.5. Rollback về stable trong mesh/Gateway API

Khi canary fails:
1. Update routing configuration thành **100/0** stable/canary.
2. Đảm bảo stable deployment có capacity.
3. Kiểm tra controller báo route programmed và upstream traffic phân phối lại.
4. Kiểm tra request inflight/websockets/session persistence.
5. Giữ canary Pods để thu evidence nếu cần, sau đó scale down có kiểm soát.
6. Commit GitOps manifest đã rollback; đừng để reconcile đẩy lại 90/10.

**Thao tác rollback của routing không nhất thiết rollback container image ở canary Deployment**. Hai bước là khác nhau và cần trạng thái rõ.

## 13. Azure Front Door: canary/blue-green ở lớp edge

### 13.1. Khi nào cần Front Door?

**Azure Front Door Standard/Premium** có thể định tuyến ở edge đến các backend origins, health probes, TLS/WAF và những khả năng bảo vệ khác. Một kiến trúc có thể dùng hai origins độc lập:

~~~mermaid
flowchart LR
    U["Users across regions"] --> FD["Azure Front Door"]
    FD -->|"High weight"| B["Blue origin / old app"]
    FD -->|"Low weight"| G["Green origin / new app"]
    B --> M["Metrics/logs"]
    G --> M
~~~

Ví dụ origins là hai App Services riêng biệt, hai Container Apps endpoints hoặc hai ingress gateways; **không tự chia lưu lượng đến hai code versions nếu chỉ có một origin address**.

### 13.2. Weight, priority và health

- **Priority:** có thể dùng để chọn preferred/failover origins theo routing semantics.
- **Weight:** chia traffic tương đối giữa các origins eligible có cùng priority khi weighted routing được áp dụng.
- **Health probe:** origin lỗi có thể bị loại khỏi tập lựa chọn, làm actual weights thay đổi.
- **Latency-based selection:** một số cài đặt/routing logic có thể ảnh hưởng tới phân phối.
- **Session affinity:** cùng user có thể gắn một origin trong thời gian nhất định.
- **Caching:** edge có thể trả response từ cache mà không gửi request tới origins.

Ví dụ đặt trọng số Blue=900, Green=100 chỉ là **tỷ lệ tương đối mục tiêu khoảng 90/10 khi routing conditions phù hợp**, không phải cam kết 10% unique users.

### 13.3. Không dùng priority thay weight để làm canary

Nếu đặt Blue ưu tiên cao hơn Green, hệ thống có thể chọn Blue gần như toàn bộ khi Blue healthy, và chỉ đưa Green vào khi Blue bị loại (failover). Đây **không phải 10% canary**. Cần cấu hình weights/priorities theo nguyên tắc của origin group thực tế và kiểm tra log phân phối.

### 13.4. Cache, state và security

- Với API dynamic nhạy cảm, cần Cache-Control/no-store hoặc cấu hình caching đúng để không gây rò rỉ dữ liệu cross-user.
- WAF policy/rule sets phải nhất quán giữa traffic stable/canary.
- Origins cần kiểm tra hostname, TLS certificate, origin host header và allowlist.
- Một feature flag/route rule có thể chỉ ảnh hưởng một region/path.
- Cloud-specific data residency có thể giới hạn đưa traffic giữa regions.
- Dùng Azure Front Door access logs để so origin distribution, không chỉ client metrics.

### 13.5. Azure Traffic Manager không phải request-level canary

Azure Traffic Manager điều phối DNS-level responses theo profile/methods như weighted routing. DNS TTL, resolver caching và client behavior làm traffic rất khó chính xác theo HTTP requests. Có thể phù hợp cho region/routing policy nhưng **không phải lựa chọn thay thế trực tiếp Front Door/Gateway L7** cho một canary 1% đòi độ chính xác.

### 13.6. Multi-region release

Khi có khu vực Đông Nam Á và Tây Âu:
1. Canary một region có business mix phù hợp.
2. Giữ baseline/stable ở region khác.
3. Đánh giá data residency, latency và cross-region dependencies.
4. Mở rộng sang ring tiếp theo khi pass.
5. Theo dõi failover/weighted routing và đừng coi region failover traffic là canary bình thường.
6. Có rollback theo region và global kill switch nếu cần.

Canary ở một region **không tự chứng minh release an toàn ở mọi region**, vì network, database topology, availability zones và data mix khác nhau.


## 14. Database migration: vì sao rollback application không đủ?

### 14.1. Mối nguy từ state dùng chung

Blue và Green thường cùng truy cập:
- Azure SQL Database/PostgreSQL/MySQL.
- Azure Cosmos DB.
- Azure Storage.
- Azure Cache for Redis.
- Azure Service Bus/Event Hubs.
- Key Vault/App Configuration.
- Các SaaS APIs bên ngoài.

Nếu bản Green tự động **xóa cột**, đổi ý nghĩa dữ liệu hoặc ghi một format mới mà Blue không đọc được, việc route 100% về Blue có thể tạo thêm lỗi. Điều này đúng ngay cả khi Green chỉ nhận 1% requests.

### 14.2. Mẫu expand–migrate–contract

~~~mermaid
flowchart LR
    A["Stable v1 reads schema A"] --> E["EXPAND: add compatible fields"]
    E --> B["v1 + v2 compatible"]
    B --> M["MIGRATE/BACKFILL data gradually"]
    M --> C["All consumers on v2"]
    C --> D["CONTRACT: remove legacy only after window"]
~~~

**Expand:** thêm cột/bảng/index/API fields mới mà v1 vẫn hoạt động. Không drop/rename một phần dữ liệu v1 cần.

**Migrate:** chuyển dần dữ liệu cũ sang format mới, dual-read hoặc dual-write khi cần, giám sát lỗi và backfill.

**Contract:** chỉ xóa cấu trúc/behavior cũ khi:
- Tất cả applications/workers đã chuyển.
- Không còn dự kiến rollback về v1.
- Retention/offline clients/replay windows đã hết.
- Migration/backfill được xác minh và có backup/recovery plan.
- Governance/change approvals hoàn tất.

### 14.3. Azure SQL minh họa

Giả sử v1 ghi bảng Orders với cột Status; v2 cần thêm ShippingStatus.

**Expand (có chủ đích, lab/T-SQL):**

~~~sql
-- Chỉ minh họa: phải review lock, size, transaction,
-- index, backup và deployment order trước production.
ALTER TABLE dbo.Orders
ADD ShippingStatus nvarchar(32) NULL;
~~~

Phiên bản v1 tiếp tục hoạt động vì cột mới nullable. Phiên bản v2 có thể dùng ShippingStatus và fallback đúng khi dữ liệu cũ còn NULL. **Không được viết code v2 giả định tất cả rows có giá trị mới ngay lập tức**.

**Migrate/backfill:** thực hiện theo batches có kiểm soát, tránh lock kéo dài trên bảng lớn; ghi tiến độ và audit data correctness.

**Contract:** chỉ khi rollback window đã đóng mới xét bỏ trường cũ, điều chỉnh NOT NULL/constraint hoặc bỏ dual-write logic. Mỗi bước phải có kiểm thử trên staging với dữ liệu có kích thước và đặc điểm phù hợp.

### 14.4. Một schema change không đảo ngược nhanh

Ví dụ xấu:

~~~sql
-- KHÔNG dùng trong giai đoạn canary / rollback window
-- nếu v1 vẫn cần trường này:
ALTER TABLE dbo.Orders
DROP COLUMN Status;
~~~

Sau khi chạy, bản Blue v1 có thể fail ngay. Khôi phục schema không tự phục hồi dữ liệu đã bị drop, và restore backup có thể gây mất các writes mới. Khi migration destructive đã thực hiện, đôi lúc chỉ còn phương án **forward fix**, restore có RPO/RTO hoặc recovery phức tạp, không còn traffic rollback đơn giản.

### 14.5. Feature flags giúp giảm rủi ro nhưng không thay schema design

Cần phân biệt:
- **Flag OFF:** app vẫn chạy code v2 nhưng không kích hoạt logic mới.
- **Traffic rollback:** route về v1.
- **Schema rollback:** thay database structure/data (có thể phá dữ liệu).
- **Data correction:** sửa records được v2 ghi sai.

Nếu v2 đã ghi dữ liệu mới, tắt feature flag không tự xóa chúng. Flag code path phải có compatibility khi OFF và phải được thử trong cả hai trạng thái.

### 14.6. Rollback window và retention

Một tổ chức có thể giữ v1 trong 24–72 giờ sau release v2 tùy SLO, nhưng không có thời hạn bắt buộc chung. Thời hạn cần bao phủ:
- Delayed jobs, scheduled jobs và batch ETL.
- Cache TTL/session lifetime.
- In-flight requests và queue backlog.
- Mobile/edge clients vẫn dùng API v1.
- Replication delays/backups.
- Những reports hoặc downstream consumers theo ngày.
- Khả năng khôi phục secret và image digest cũ.

Contract schema sau 30 phút khi background message retry có thể kéo dài một ngày thường là quá sớm.

## 15. Async workloads: queue workers và event contracts

### 15.1. HTTP canary không tự chia queue consumers

Với Azure Service Bus, nếu v1 và v2 workers cùng nhận trên **một queue**, chúng thường cạnh tranh messages theo broker dispatch, concurrency/prefetch và availability. Gán HTTP ingress 10% **không có nghĩa v2 chỉ nhận 10% messages**.

~~~mermaid
flowchart LR
    SB["Azure Service Bus queue"] --> W1["Worker v1"]
    SB --> W2["Worker v2"]
    W1 --> DB["Shared DB"]
    W2 --> DB
~~~

Mọi worker phải đọc được message format đang tồn tại trong queue hoặc nên có partition/subscription routing theo phiên bản. Nếu không, rollback HTTP API có thể vẫn để lại worker v2 gây side effects.

### 15.2. Kế hoạch chuyển worker an toàn

Các phương án:
- Deploy v2 worker chỉ vào **staging queue/subscription** với dữ liệu giả.
- Dùng feature flag để giới hạn code path nhận job v2 nếu framework cho phép.
- Chia workload bằng subscriptions/filters hoặc routing topology có kiểm soát.
- Canary theo **consumer replicas** chỉ khi có bằng chứng về phân phối; không coi replicas là traffic percentage.
- Đảm bảo cả v1 và v2 workers **tương thích ngược** với schema event chung.
- Với workloads yêu cầu isolation, dùng queue riêng và kế hoạch migration.

### 15.3. Schema versioning cho messages

~~~json
{
  "schemaVersion": "1.1",
  "messageId": "invoice-order-123",
  "eventType": "InvoiceRequested",
  "orderId": "demo-123",
  "occurredAtUtc": "2026-11-20T10:00:00Z",
  "payload": {
    "currency": "VND",
    "totalMinorUnits": 125000
  }
}
~~~

Ví dụ dùng ID giả. Contract cần quy định:
- Fields bắt buộc/tùy chọn.
- Default values.
- Unit và timestamp.
- Version migration strategy.
- Unknown fields nên bị ignore hay reject.
- DLQ và replay policy.
- Idempotency key ổn định.

**Không phá v1 worker** bằng cách v2 producer đột ngột thay toàn bộ eventType hoặc đổi đơn vị tiền mà không version.

### 15.4. Graceful draining của consumer

Khi rollback worker v2:
1. Dừng nhận **new messages**.
2. Cho in-flight jobs kết thúc trong timeout phù hợp.
3. Renew/release locks hoặc checkpoint đúng theo service/client.
4. Không xóa/complete message chưa hoàn tất business transaction.
5. Bật lại v1 worker hoặc thay route theo kế hoạch.
6. Giám sát queue age, DLQ, duplicates và failed side effects.
7. Giữ stable handler còn tương thích dữ liệu v2 đã xuất ra.
8. Reconcile những jobs đã làm dở.

Azure Service Bus message delivery thường có thể retry/redeliver; **tracing không bảo đảm exactly-once**. Cần stable message ID, unique constraints, outbox/saga hoặc deduplication theo yêu cầu nghiệp vụ.

### 15.5. Long-running jobs và canary

Những job chạy 45 phút không nên bị cắt giữa chừng chỉ vì HTTP canary vừa fail. Có thể cần:
- Drain trước khi terminate process.
- Durable checkpoints.
- Resume/retry semantics.
- Version-compatible persisted state.
- Job-level feature flags.
- Owner riêng cho rollback background processing.

**Một rollback runbook chỉ nói "chuyển HTTP traffic 100% về v1" là chưa đầy đủ cho hệ thống có asynchronous processing.**

## 16. Các loại rollback và mức độ phục hồi

### 16.1. Rollback là một họ thao tác

| Đối tượng | Thao tác có thể thực hiện | Điều không được đảm bảo |
|---|---|---|
| HTTP traffic | Trả 100% về stable slot/revision/origin | DB và code config được hoàn tác |
| Application binary | Redeploy digest v1 | External side effects được xóa |
| Feature flag | Tắt chức năng rủi ro | Runtime crashes unrelated flag biến mất |
| Configuration | Revert app settings/IaC | Secret values đã rotate trở lại hợp lệ |
| Database schema | Forward-compatible migration hoặc restore theo plan | Không mất dữ liệu khi restore |
| Business data | Compensation/reconciliation | Đảo ngược mọi giao dịch tức thời |
| Queue/worker | Drain, route lại, restart stable consumers | Exactly-once message handling |
| Network/IAM | Revert firewall/RBAC theo approval | Token caches và DNS tức thì cập nhật |
| CDN/cache | Invalidate hoặc dùng content-hashed assets | Mọi client không còn cache cũ ngay |

### 16.2. Traffic rollback khác disaster recovery

**Traffic rollback** thường diễn ra vài giây/phút nếu stable capacity sẵn. **Disaster recovery** liên quan mất region, dữ liệu hoặc service, có RPO/RTO riêng. Không mô tả App Service swap hoặc ACA revision weight như một giải pháp DR đầy đủ.

### 16.3. Thời gian khôi phục thực tế

~~~text
Detection time
  + alerting/decision delay
  + authorization/approval
  + traffic rollback execution
  + propagation/draining
  + stable warm-up/capacity
  + verification/reconciliation
  = incident mitigation time
~~~

Nếu stable đã scale-to-zero và image pull mất hai phút, lệnh traffic rollback hoàn tất trong một giây **không đồng nghĩa user-facing service hồi phục trong một giây**.

### 16.4. Khi nào rollback, khi nào roll forward?

**Rollback** khi:
- Phiên bản trước còn tương thích dữ liệu và dependencies.
- Có đường đổi traffic/code nhanh, ít rủi ro hơn sửa nóng.
- Lỗi do release mới gây ra rõ ràng.
- Không có migration phá rollback.

**Roll forward/fix forward** khi:
- Schema destructive đã chạy hoặc dữ liệu v2 không tương thích v1.
- Security patch bắt buộc không được phép đưa vulnerable v1 trở lại.
- Một lỗi được sửa bằng config/flag rất an toàn.
- Rollback gây tác động lớn hơn fix và có bằng chứng chấp thuận.
- Service provider đã đổi API khiến v1 không thể kết nối.

Không quyết định vì phản xạ “luôn rollback”; dùng incident severity, RTO/RPO, data integrity và security context.

### 16.5. Runbook rollback tối thiểu

~~~text
Incident identified:
  Release ID / commit / image digest:
  Runtime (App Service / ACA / AKS / Front Door):
  Affected region / tenant / cohort:
  Stable version and availability:
  DB schema compatibility verified:
  Message compatibility verified:
  Current traffic weights:
  Source of truth / GitOps change:
  Approved action:
  Rollback action:
  Verification metrics and time:
  Outstanding in-flight work:
  Data correction / follow-up owner:
  Evidence links / timeline:
~~~

Không ghi secrets, raw customer payment data hoặc tokens trong incident ticket. Dùng Azure resource IDs, trace IDs và logs theo quyền truy cập thích hợp.

## 17. Feature flags và kill switches

### 17.1. Vì sao tách code rollout và feature rollout?

Một image v2 có thể chứa nhiều tính năng:
- Thuật toán tính phí mới.
- Cơ chế cache mới.
- Email template mới.

Nếu bật tất cả ngay khi container được triển khai, một lỗi trong feature có thể buộc rollback toàn binary. **Feature flags** giúp deploy code trước nhưng chỉ bật hành vi theo cohort, sau đó disable nhanh khi cần.

Azure App Configuration Feature Management và những giải pháp flag phù hợp có thể:
- Bật cho nhóm QA.
- Bật 5% người dùng.
- Bật một tenant/site.
- Dùng kill switch để tắt một code path lỗi.
- Đo kết quả tính năng.

### 17.2. Feature flag không đồng nghĩa routing 5% requests

Một flag gán 5% **users** có thể chỉ thay hành vi bên trong code v2; toàn bộ requests vẫn chạy trên v2 process. Một bug startup/cpu leak có thể ảnh hưởng 100% dù flag OFF.

Ngược lại, App Service routing 5% requests sang Green không bảo đảm 5% users được bật feature. Hai trục cần được đo riêng:

~~~text
Deployment cohort:
  Which binary handles request?

Feature cohort:
  Which behavior executes in that binary?
~~~

### 17.3. Flag evaluation và session consistency

- Stable assignment bằng user/tenant key đã được phê duyệt.
- Không lưu PII thô trong feature flag logs.
- Các microservices phải hiểu cùng feature state khi business transaction cần nhất quán.
- Caching của config/flags có TTL, refresh và rollback semantics.
- Có fallback khi App Configuration lỗi.
- Audit ai đã thay flag và thời điểm nào.
- Xóa flags cũ sau khi release ổn định để giảm technical debt.

### 17.4. Security kill switch

Một kill switch chỉ có ích nếu:
- Nó không phụ thuộc một control plane đang lỗi.
- Có quyền và cơ chế thay đổi khẩn cấp được kiểm soát.
- Đã test OFF path.
- Không tạo inconsistent writes khi bật/tắt giữa workflow.
- Có observability xác minh tác dụng.
- Không làm lộ admin control cho client.

Không nhầm một flag “disable payment” với việc thu hồi payment token bị lộ; rủi ro bảo mật còn cần revoke/rotation và điều tra.

## 18. Chuỗi cung ứng phần mềm của release

### 18.1. Build once, release many

Một chuỗi lành mạnh:

~~~mermaid
flowchart LR
    S["Protected Git branch + reviewed PR"] --> C["CI unit/integration tests"]
    C --> SCAN["SAST / SCA / secrets scan"]
    SCAN --> BUILD["Reproducible container build"]
    BUILD --> SBOM["SBOM / provenance / image signing"]
    SBOM --> ACR["Azure Container Registry by digest"]
    ACR --> STAGE["Staging deploy + tests"]
    STAGE --> APPROVE["Approval / policy gate"]
    APPROVE --> CANARY["Canary traffic"]
    CANARY --> PROM["Promote same digest"]
~~~

### 18.2. Image digest quan trọng hơn mutable tag

~~~text
Không an toàn để xác định release:
  acrorders.azurecr.io/orders:latest

Định danh cụ thể:
  acrorders.azurecr.io/orders@sha256:<approved-digest>
~~~

Một tag có thể bị trỏ sang digest khác theo policy, trong khi digest xác định manifest content. Việc pin digest hỗ trợ rollback chính xác và provenance checks. Tuy vậy, digest không tự chứng minh artifact an toàn: cần **nguồn build, signature verification, vulnerability scanning và SBOM** khi yêu cầu.

### 18.3. Azure Container Registry (ACR)

Cần:
- Registry network access từ runners/nodes.
- Managed identity hoặc workload identity phù hợp cho image pull/push.
- Role assignments đủ hẹp theo permission model.
- Chính sách không xóa image digest vẫn trong rollback window.
- Retention/cleanup policy không purge stable image sớm.
- Image scanning và remediation.
- Secrets/credentials của registry không hard-code vào pipeline.
- Replica/network/egress phù hợp với region/capacity.

**Không có khả năng rollback nếu artifact cũ đã bị xóa khỏi registry hoặc runtime không thể pull nó.**

### 18.4. Provenance và attestation

Có thể lưu:
- Commit SHA, build run ID, build-time toolchain.
- SBOM (Software Bill of Materials).
- SCA/secret scan results.
- Artifact/image digest.
- Chữ ký và attestation theo tổ chức.
- Deployment target, môi trường, revision/slot.
- Approval và release decision.
- Canary metrics/correlation IDs.

Không lưu token/secret values trong attestation. Một chứng cứ deploy “v2 signed image” giúp audit artifact nguồn gốc, nhưng **không chứng minh v2 có thể xử lý database schema**; cần cả compatibility tests.

### 18.5. Identity của pipeline

Với GitHub Actions, Azure DevOps hoặc runner khác:
- Ưu tiên **OpenID Connect workload identity federation** với Entra ID khi hỗ trợ.
- Giới hạn token issuance theo repo/branch/environment/subject.
- Cấp Azure RBAC tối thiểu tới resource group/app/registry cần triển khai.
- Không dùng subscription Owner hoặc service principal client secret lâu hạn chỉ để chạy deploy.
- Dùng protected environments, reviewers và branch protection.
- Không ghi azure login credentials, Key Vault values hoặc SAS vào logs.
- Phân biệt CI identity build/push và CD identity deploy/traffic/promote.

Một pipeline được phép deploy image chưa chắc cần quyền sửa Key Vault network, xóa DB hoặc gán RBAC cho toàn subscription.


## 19. CI/CD pipeline: stage, approval, gates và promotion

### 19.1. Một pipeline progressive delivery chuẩn

~~~mermaid
flowchart TD
    A["Pull request reviewed"] --> B["CI: tests, SCA, SAST, SBOM"]
    B --> C["Build & push immutable digest to ACR"]
    C --> D["Deploy Green to staging"]
    D --> E["Readiness + integration/smoke tests"]
    E --> F{"Security/owner approval"}
    F -->|Fail| STOP["Stop release / preserve stable"]
    F -->|Pass| G["Canary 1%"]
    G --> H{"Metrics gate 1"}
    H -->|Fail| R["Rollback traffic + incident evidence"]
    H -->|Pass| I["Canary 5% → 20% → 50%"]
    I --> J{"Metrics + business gates"}
    J -->|Fail| R
    J -->|Pass| K["Promote 100% / swap"]
    K --> L["Observe + retain stable rollback window"]
    L --> M["Close release / eventual contract"]
~~~

Một release **không được coi là thành công** ngay khi API create deployment trả 200. Pipeline cần chờ readiness, thu tín hiệu thực và ghi quyết định.

### 19.2. Những trạng thái rõ ràng

Có thể dùng các release states:

~~~text
CREATED
BUILT_AND_SIGNED
DEPLOYED_GREEN
SMOKE_PASSED
APPROVED
CANARY_1
CANARY_5
CANARY_20
CANARY_50
PROMOTED_100
VERIFIED
COMPLETED

Trạng thái lỗi:
HOLD
ROLLBACK_REQUESTED
ROLLBACK_IN_PROGRESS
ROLLED_BACK
NEEDS_DATA_REPAIR
FAILED
~~~

Đây là **state machine tham khảo** cho pipeline/Release Management, không phải enum API có sẵn của Azure. Mọi transition có owner, timestamp, inputs và evidence. Nếu pipeline restart giữa Canary 20% và 50%, phải **đọc trạng thái traffic hiện tại** trước khi tiếp tục, không assume workflow run lại từ 0%.

### 19.3. Azure DevOps environments và approvals

Trong Azure Pipelines:
- **Deployment jobs** gắn với **Environment** để ghi deployment history, scope/approvals và checks khi cấu hình.
- **Approvals and checks** được quản lý trên Environment/resource/service connection tùy tổ chức, không chỉ bằng một dòng YAML.
- Có thể dùng branch control, required template, business-hours, Azure Monitor alert checks hoặc REST checks theo khả năng hiện hành.
- CI nên build/test; CD sử dụng artifact đã publish/digest cố định.
- Production service connection cần permission tối thiểu.

Ví dụ YAML rút gọn cho **một bước routing ở lab đã đủ approval**:

~~~yaml
trigger: none

variables:
  resourceGroup: rg-orders-lab
  appName: app-orders-lab

stages:
  - stage: Canary10
    displayName: Canary 10 percent in approved lab
    jobs:
      - deployment: RouteCanary
        environment: orders-lab-approval
        strategy:
          runOnce:
            deploy:
              steps:
                - task: AzureCLI@2
                  inputs:
                    azureSubscription: sc-orders-lab-federated
                    scriptType: bash
                    scriptLocation: inlineScript
                    inlineScript: |
                      az webapp traffic-routing set \
                        --resource-group "$(resourceGroup)" \
                        --name "$(appName)" \
                        --distribution staging=10
~~~

**Bản YAML chỉ minh họa một deployment job, không phải pipeline production hoàn chỉnh.** Nó chưa chứa build/test, read-before-write check, traffic verification, KQL gates hoặc rollback. Approval chỉ xảy ra nếu Environment **orders-lab-approval** đã được cấu hình Approvals and checks thật. Không copy tên service connection giả vào pipeline production.

### 19.4. GitHub Actions protected environments

Một workflow dùng GitHub Actions có thể:
1. Build và ký artifact trong job không có production credentials.
2. Publish digest + SBOM.
3. Deploy staging với OIDC scoped identity.
4. Chạy smoke/integration.
5. Dùng job **environment: production** với protection rules đã cấu hình.
6. Azure login qua OIDC; hạn chế permission **id-token: write**, contents: read.
7. Chạy canary bước một.
8. Query gates, yêu cầu approvals thêm khi tăng lớn.
9. Promote hoặc rollback.
10. Ghi audit trail run ID, commit, digest, result.

**environment: production** tự nó **không tạo approval nếu repository/environment chưa bật required reviewers/branch restrictions**. Không đưa client secret lâu hạn vào GitHub Actions secrets nếu tổ chức có thể dùng workload identity federation và các policy phù hợp.

### 19.5. Separation of duties

- Developer review code và tests.
- Platform team quản lý release tooling và routing.
- Security team/automation kiểm tra image signing, SBOM và vulnerability policy.
- Product/business owner phê duyệt thay đổi có ảnh hưởng tài chính.
- SRE/on-call theo dõi canary và có quyền rollback theo incident policy.
- Database owner phê duyệt migration destructive/restore.

Không buộc một cá nhân phải giữ subscription Owner chỉ để chạy canary. Cũng không tạo quy trình approval chậm hơn RTO đã cam kết cho critical rollback; **quyền rollback khẩn cấp** cần được thiết kế từ trước và audit.

### 19.6. Idempotency của pipeline

Một rerun có thể vô tình:
- Deploy revision khác do image tag mutable.
- Swap slots hai lần, trở về bản cũ mà không biết.
- Tăng traffic từ 10% lên 50% không có gate.
- Áp migration hai lần.
- Purge stable image trước khi hết rollback window.

Do đó mỗi stage phải:
1. Read current state.
2. Verify expected source and target releases.
3. Check target readiness/configuration.
4. Apply idempotent desired change hoặc fail-safe HOLD.
5. Readback actual state.
6. Record audit/evidence.
7. Chỉ tiến lên khi gate PASS.

**Slot swap là hành động có trạng thái; chạy lặp lệnh swap không được coi là idempotent.**

## 20. Automated metric gates và KQL

### 20.1. Phải gắn release/version vào telemetry

Để so sánh v1 và v2, cần:
- AppRoleName ổn định theo service.
- Deployment version/digest attribute hoặc CustomDimensions/Properties.
- Slot/revision-specific tagging hoặc App Insights resources riêng.
- Time window và region/tenant segmentation.
- Đủ sample count.
- Nguyên tắc xử lý missing telemetry.

Nếu cả v1 và v2 dùng cùng AppRoleName và không có version property, KQL tổng không đủ để quyết định canary an toàn.

### 20.2. Ví dụ KQL có version attribute do ứng dụng tạo

Giả sử instrumentation đã thêm property **deployment.release** vào AppRequests:

~~~kusto
let windowStart = ago(15m);
AppRequests
| where TimeGenerated >= windowStart
| where AppRoleName == "orders-api"
| extend Release = tostring(Properties["deployment.release"])
| where Release in ("v1", "v2")
| extend Is5xx = toint(ResultCode) between (500 .. 599)
| summarize
    Requests = sum(ItemCount),
    Errors5xx = sumif(ItemCount, Is5xx),
    P95Ms = percentile(DurationMs, 95)
  by Release, bin(TimeGenerated, 5m)
| extend ErrorRate5xx =
    iff(Requests > 0, todouble(Errors5xx) / Requests, real(null))
| order by TimeGenerated asc, Release asc
~~~

**Đây là query minh họa**: property deployment.release phải được gắn có thật, đúng schema; AppRequests dùng **Properties** dynamic column trong workspace-based Application Insights theo cấu hình. ItemCount có thể biểu diễn sampling weight. Percentile trên samples không tự weighted; để dựng automated SLO gate có độ tin cậy cao, nên dùng metric/source đảm bảo thống kê phù hợp và có tests trên dữ liệu thật.

### 20.3. KQL so lỗi theo release không có version property

Nếu telemetry của stable và canary nằm ở hai App Insights resources/workspaces riêng và querying cross-resource được phân quyền, có thể tính metrics riêng rồi join sau. Nếu dùng Azure Container Apps, có thể kết hợp revision-specific metrics/logs phù hợp.

Không dùng cách “v2 gửi traffic 10% nên lấy 10% errors của tổng request” — vì các errors có thể phân bổ không đều.

### 20.4. Lưu ý sampling

- Application Insights sampling có thể khiến một request cụ thể không xuất hiện.
- Trong một số query, sum(ItemCount) ước lượng volume theo sampling weight.
- Sampled p95 có độ không chắc chắn với canary nhỏ.
- Nếu sampling lệch giữa stable và canary, một phép so raw count có thể sai.
- Metrics ở ingress/app có thể hữu ích hơn để đo SLI toàn bộ traffic.
- Traces phù hợp chẩn đoán lỗi cụ thể, không phải lúc nào phù hợp làm mẫu số toàn SLO.

### 20.5. Gate decision algorithm

~~~text
Input:
  canaryRelease
  stableRelease
  window = last 15 minutes
  minRequests = 500

if telemetry unavailable or stale:
    HOLD; notify owner
elif canaryRequests < minRequests:
    HOLD; extend observation
elif criticalDataIntegrityIncident or securityCritical:
    ROLLBACK immediately
elif canary5xxRate > absoluteThreshold:
    ROLLBACK
elif canary5xxRate > stable5xxRate + allowedDelta:
    ROLLBACK
elif canaryP95 > stableP95 * allowedRatio:
    HOLD or ROLLBACK per severity
elif queueDLQSpike or businessConversionCrash:
    HOLD + investigate / ROLLBACK
else:
    PASS; eligible for next stage
~~~

Đây là **pseudocode chính sách**, không phải code Azure DevOps task có sẵn. Implementation cần double-check query permissions, cardinality, time window, saturation và false positives.

### 20.6. Tránh race condition khi rollback tự động

Một auto-rollback controller có thể cùng lúc với operator đang promote. Cần:
- Một **single release owner/controller** hoặc lease/lock.
- Compare-and-set trên expected current release/traffic weights.
- Idempotent rollback desired state.
- Central audit và incident state.
- Pause/resume mechanism với approval.
- Atomicity ở khả năng platform hỗ trợ; nếu không có, verify/readback.
- Không để CI promotion job đẩy v2 lên lại ngay sau auto-rollback.

**Một hệ thống tự động rollback nhưng pipeline vẫn liên tục redeploy version lỗi sẽ tạo outage loop.**

## 21. Quy trình vận hành từng giai đoạn

### 21.1. Pre-deployment

- Kiểm tra artifact digest, signature, SBOM, security scan results.
- Kiểm tra release manifest chứa version/config/schema compatibility matrix.
- Kiểm tra production baseline metrics và active incidents.
- Kiểm tra stable runtime healthy, rollback capacity và image retained.
- Kiểm tra DB migration expand đã áp/được phê duyệt.
- Kiểm tra queues, secret expiration, managed identities và network.
- Kiểm tra smoke tests không tạo payment/order thật.
- Kiểm tra approvers và giờ có support/on-call.
- Kiểm tra canary routing controller đang hoạt động và telemetry version tagging.

### 21.2. Deployment và warm-up

1. Deploy Green/canary digest tới staging slot/revision/Deployment.
2. Đợi startup/readiness/health checks.
3. Warm caches/connection pools.
4. Thử endpoint nội bộ/label/slot URL được bảo vệ.
5. Chạy auth, DB read, storage/queue sandbox integration.
6. Kiểm tra log không có secret, policy deny hoặc TLS errors.
7. Đánh dấu DEPLOYED_GREEN và ghi artifact ID/UTC timestamp.

### 21.3. Canaries theo vòng

Ví dụ:
- Vòng 1: 1% hoặc allowlist nội bộ.
- Vòng 2: 5%, đủ sample size.
- Vòng 3: 20%, load/queue metrics.
- Vòng 4: 50%, gần quy mô production hơn.
- Vòng 5: 100% và close monitoring.

Giữa các vòng:
- Ghi routing weights thực.
- Đợi hold time đủ.
- Kiểm tra HTTP lỗi/latency và business invariants.
- So baseline ổn định theo region/tenant.
- Review telemetry freshness.
- Phê duyệt đi tiếp hoặc tự động rollback theo policy.
- Ghi ai/phần mềm nào ra quyết định.

### 21.4. Sau 100%

- Không xóa Blue/stable quá sớm.
- Tiếp tục theo dõi các batch jobs, cron và queues.
- Giữ image v1 và configs tương thích trong rollback window.
- Theo dõi exceptions/CPU/DB/queue theo release.
- Kiểm tra migration backfill/dual-write.
- Chỉ contract schema khi owners xác nhận no-rollback-needed.
- Cập nhật release audit, cost, post-release notes.

**100% traffic không tự đóng nghĩa vụ hỗ trợ rollback**.

## 22. Mức tự động hóa nào phù hợp?

### 22.1. Manual blue-green

Phù hợp với:
- Workloads ít release, rủi ro cao.
- Không có telemetry đủ phân tách version.
- Cần DBA/business sign-off.
- Muốn kiểm soát thời điểm cutover.

Điều kiện: runbook đủ chi tiết, automation lệnh cho operator để tránh thao tác nhầm, readback và blast-radius controls.

### 22.2. Semi-automated canary

- Pipeline tự deploy/route 1–5%.
- Automated alerts/gates đánh giá metrics.
- Human approval ở 20% hoặc 100%.
- Auto-rollback với critical conditions.
- Manual review cho dữ liệu/business anomalies.

Phù hợp khi đã có observability nhưng chưa có nhiều dữ liệu lịch sử để calibrate gate thresholds.

### 22.3. Fully automated progressive delivery

Có thể sử dụng Azure Pipelines, GitHub Actions, controllers/operator chuyên dụng hoặc GitOps automation khi đáp ứng:
- Version-aware telemetry có chất lượng.
- Concurrency/locking.
- Fail-safe HOLD khi no data.
- Correct rollbacks và business compatibility.
- Anomaly handling và human override.
- Evidence/approval requirements.
- Chi phí/scope hạn chế.
- Staging fault-injection/rollback tests định kỳ.

Không mặc định Azure Pipelines tự thực hiện SLO-based canary chỉ vì bạn thêm stage “Canary”; metric evaluation và traffic operations cần script/task/controller thật.

### 22.4. Progressive delivery và GitOps trên AKS

Trong GitOps (Flux/Argo CD) model:
- Git chứa desired image digest, Deployment/Service/HTTPRoute/VirtualService.
- Pipeline thay release manifest và tạo PR được review.
- Controller reconcile desired state.
- Rollback phải cập nhật **Git source of truth**.
- Không dựa vào kubectl patch tạm thời nếu GitOps sẽ sửa lại.
- Có thể dùng progressive delivery controller có tương thích GitOps và metric analysis, nhưng phải kiểm tra phiên bản, ownership và support thực tế.

**“kubectl rollout undo PASS” trong khi GitOps vẫn trỏ v2 là rollback chưa hoàn tất.**


## 23. Lab: canary và rollback trên Azure Container Apps

### 23.1. Mục tiêu lab

Dùng một Container App **đã có sẵn trong lab** với HTTP ingress, stable revision và new revision. Người học sẽ:

1. Đọc hiện trạng và kiểm tra quyền.
2. Xác minh hai revisions active, healthy.
3. Chuyển 5% traffic sang Green.
4. Chạy smoke/load tests an toàn.
5. So metrics theo version.
6. Giả lập một gate fail bằng test data.
7. Route lại 100% traffic sang Stable.
8. Kiểm tra thực tế, ghi audit.
9. Giữ evidence và không xóa stable trước rollback window.

### 23.2. Điều kiện

- Có subscription/resource group **lab riêng** và budget.
- Có Container Apps environment + một HTTP ingress app.
- Hai revisions đã được triển khai từ digests xác định.
- App không gọi payment/email/database production.
- Azure CLI containerapp extension đúng và người thao tác được cấp quyền.
- Có revision metrics/logs hoặc response header version trong lab.
- Có rollback command đã được test trước buổi diễn tập.

### 23.3. Thu thập hiện trạng read-only

~~~bash
RG="rg-orders-lab"
APP="ca-orders-lab"

az account show --query "{subscription:id,name:name}" -o json

az containerapp show -g "$RG" -n "$APP" \
  --query "{mode:properties.configuration.activeRevisionsMode,traffic:properties.configuration.ingress.traffic}" \
  -o json

az containerapp revision list -g "$RG" -n "$APP" -o table
~~~

Ghi **tên revisions chính xác**, trạng thái active/healthy và trọng số traffic trước test. Đừng dựa vào giả định revision vừa deploy sẽ tự nhận 5% lưu lượng.

### 23.4. Thiết lập 95/5 sau approval

~~~bash
STABLE="<exact-stable-revision>"
GREEN="<exact-green-revision>"

# Chỉ thực hiện trong lab sau khi preflight và approval.
az containerapp revision set-mode -g "$RG" -n "$APP" \
  --mode multiple

az containerapp ingress traffic set -g "$RG" -n "$APP" \
  --revision-weight "$STABLE=95" "$GREEN=5"

# Readback tỷ lệ thật:
az containerapp show -g "$RG" -n "$APP" \
  --query "properties.configuration.ingress.traffic" -o json
~~~

Nếu Green chưa active/healthy, **không chuyển traffic**. Khi testing, tránh chỉ gửi 10 requests từ một browser cookie; sample rất nhỏ và sticky session có thể không đủ đại diện.

### 23.5. Smoke tests

Định nghĩa endpoint lab:

~~~text
GET /ready
  → HTTP 200 khi readiness phù hợp

GET /version
  → JSON {"release":"v1"|"v2","healthy":true}

POST /orders/dry-run
  → không ghi DB production, không gọi payment/queue thật
  → trả 200 hoặc 202 theo contract lab
~~~

Đây là những routes **do dự án test định nghĩa**, không phải endpoints Container Apps có sẵn. Nếu app không có các endpoint này, chọn API tests tương đương và tránh side effects.

### 23.6. Cố tình làm canary gate fail trong lab

Trong **staging**, có thể bật một test feature flag làm Green trả 503 cho requests giả đã được allowlist. Tuyệt đối không bật lỗi giả trên production public endpoint.

Sau đó:
- Đo Green 5xx rate theo revision/version.
- Xác minh Stable không bị ảnh hưởng.
- Xem metrics/logs và ingestion delay.
- Đánh dấu **HOLD/ROLLBACK_REQUESTED** với evidence.
- Rollback theo runbook.

### 23.7. Rollback về stable

~~~bash
az containerapp ingress traffic set -g "$RG" -n "$APP" \
  --revision-weight "$STABLE=100" "$GREEN=0"

az containerapp show -g "$RG" -n "$APP" \
  --query "properties.configuration.ingress.traffic" -o json
~~~

Kiểm tra:
- Traffic đã về Stable theo dữ liệu thực.
- Stable đủ replicas/capacity.
- Requests inflight drain phù hợp.
- HTTP errors trở về baseline.
- Queues/workers không bị ảnh hưởng.
- Evidence logs/metrics còn lưu.

Không xem một exit code 0 là bằng chứng đủ về hồi phục; **phải xác minh health người dùng**.

### 23.8. Cleanup có kiểm soát

- Tắt flag lỗi giả.
- Giữ Green logs/evidence cho postmortem.
- Deactivate/cleanup revision theo approval/retention.
- Không xóa Container App hoặc resource group nếu là lab dùng chung.
- Ghi số replicas, traffic, storage/logging cost của buổi diễn tập.
- Nếu chỉ có quyền read-only, dừng ở bước 23.3; không chạy traffic mutation.

## 24. Lab: blue-green trên App Service và rollback bằng swap

### 24.1. Điều kiện

- App Service plan hỗ trợ deployment slots.
- Production slot Blue và staging slot Green có artifact IDs rõ.
- Slot-specific settings/managed identity/network đã kiểm tra.
- Smoke test không làm hỏng database/queue.
- Green đã warm-up qua slot URL hoặc preview mechanism tương thích.
- Có approval, monitoring và recovery plan.

### 24.2. Ghi evidence trước swap

~~~text
App Service resource ID:
Production slot release digest:
Staging slot release digest:
Production configuration fingerprint (redacted):
Staging slot-specific settings verified:
Database schema / compatibility:
Warm-up and readiness status:
Azure Monitor alert state:
App Service plan capacity:
Release approval ID:
~~~

Không ghi actual passwords/access tokens. Nếu thiếu trường critical, **HOLD**.

### 24.3. Chạy swap có kiểm soát

~~~bash
RG="rg-orders-lab"
APP="app-orders-lab"

az webapp deployment slot list \
  --resource-group "$RG" \
  --name "$APP" \
  -o table

# Chỉ sau smoke tests, compatibility và approval:
az webapp deployment slot swap \
  --resource-group "$RG" \
  --name "$APP" \
  --slot staging \
  --target-slot production
~~~

Nếu dùng **swap with preview**, phải theo đúng feature support và commands theo loại app; không chạy swap thường song song với preview đang chờ.

### 24.4. Kiểm tra sau swap

- Production hostname trả đúng release ID bằng endpoint được sanitize.
- App Insights p95/5xx không xấu đi.
- Slot/sticky settings và Key Vault identity còn đúng.
- DB migrations backward-compatible.
- Không có lỗi Service Bus/Blob do cấu hình.
- Staging còn một phiên bản stable rollback được.
- Traffic routing (nếu đã dùng) có trạng thái hiểu rõ.

Nếu lỗi, sau khi xác minh trạng thái từng slot, swap trở lại theo mục 7.8 hoặc redeploy stable theo kế hoạch. Không tự swap hai lần liên tiếp mà không đọc state mỗi lần.

### 24.5. Những bài học cần rút ra

- Warm-up giảm cold-start nhưng không thay SLO gate.
- DB migration destructive có thể phá rollback.
- Smoke test GET / bỏ sót các quyền Storage/Key Vault.
- Sticky cookie ảnh hưởng traffic test.
- Cần giữ artifact và stable slot đủ lâu.
- Readback sau swap quan trọng như lệnh swap.
- Operator cần quyền rollback theo RTO đã cam kết.


## 25. Kiểm thử và fault injection trước production

### 25.1. Ma trận kiểm thử

| Kịch bản | Cách thử trong staging/lab | Điều kiện PASS |
|---|---|---|
| Green khởi động chậm | Delay startup hợp lý | Readiness chưa nhận traffic quá sớm |
| Green liveness fail | Process crash có kiểm soát | Router/controller loại unhealthy target |
| Green trả 503 | Inject lỗi trên test cohort | Gate rollback đúng |
| Green p95 gấp đôi Stable | Inject artificial latency | Hold/rollback theo ngưỡng |
| Canary 1% traffic thấp | Hạn chế test volume | No-data/insufficient-samples → HOLD |
| Azure Monitor unavailable | Ngắt exporter lab | Không auto-promote vì thiếu telemetry |
| Traffic cutover | 95/5 → 50/50 → 100/0 | Realized distribution được đo |
| Rollback traffic | 10% → 0% | Stable nhận traffic trở lại |
| Blue not ready | Stable thiếu capacity | Không promote nếu rollback path không sẵn |
| Database expand migration | Thêm cột nullable | Cả v1 và v2 đọc/ghi được |
| Database destructive change | Đánh dấu migration incompatible | Pipeline chặn release trước cutover |
| Secret rotation | Đổi test token trong Key Vault | Cả revisions dùng credential hợp lệ |
| HTTP session affinity | Browser có cookies | Session flow không hỏng |
| Service Bus worker v2 | Gửi schema v1/v2 test | Workers xử lý, DLQ không tăng |
| Worker graceful stop | Terminate khi job đang chạy | Không mất message/duplicate side effects |
| Front Door cache | Test Cache-Control/headers | Không rò dữ liệu, không che canary |
| GitOps reconcile | Manual patch rồi reconcile | Desired rollback được cập nhật |
| ACR image cũ unavailable | Simulate missing digest ở lab | Rollback preflight phát hiện |
| Pipeline rerun | Chạy lại cùng release state | Không swap nhầm hoặc promote vô điều kiện |
| Region failover | Origin/region lab unavailable | Failover không giả dạng canary PASS |

### 25.2. Test traffic phải có phân khúc

Nếu production có:
- 60% người dùng mobile.
- 30% desktop/tablet.
- 10% API integration.
- 2% enterprise tenants với request volumes rất cao (có thể chồng các nhóm trên).

Canary cần kiểm tra **cohort representation** hoặc test ring riêng cho các luồng có rủi ro. 1% random requests có thể không gặp enterprise protocol cũ hoặc giao dịch cuối tháng.

Đừng trộn synthetic requests 100% success vào mẫu số của SLO để che mất lỗi thật; cần tag/split synthetic traffic khỏi user-facing traffic.

### 25.3. Data integrity tests

Một release có thể trả HTTP 200 nhưng:
- Ghi trùng order.
- Tính sai tiền thuế/đơn vị tiền.
- Gửi invoice hai lần.
- Bỏ message im lặng.
- Ghi Blob với schema không tương thích.
- Làm mất tenant isolation.

Canary cần business assertions:
- Unique idempotency keys.
- Referential integrity.
- Không duplicate payment capture.
- Orders accepted vs persisted được reconciliation theo cửa sổ.
- Service Bus sent/processed/DLQ counts được kiểm tra.
- Schema versions hợp lệ cho stable/green.
- Không lộ PII giữa tenants.

**HTTP error rate thấp là điều kiện cần, không đủ cho release có dữ liệu quan trọng.**

### 25.4. Network và managed identity tests

- Green có DNS/Private Endpoint tới Azure SQL/Storage/Key Vault không?
- Azure Container Apps revision có quyền ACR pull?
- AKS workload identity annotations/ServiceAccount có đúng?
- App Service slot có identity/slot-specific settings hợp lệ?
- Front Door origin TLS/host header/WAF có tương thích?
- CI runner deploy bằng quyền tối thiểu, không cần subscription Owner?
- Token refresh hoạt động sau khi token hết hạn?
- Khi quay về Blue, credentials đã rotate có còn được chấp nhận?

Không khắc phục canary 403 bằng cách mở public network hoặc cấp Administrator role vô cớ.

### 25.5. Tiêu chí chấp nhận của buổi diễn tập rollback

~~~text
Canary release intentionally fails in isolated lab.
Alert/gate detects issue within target window.
Pipeline/orchestrator stops promotion.
Traffic returns to healthy stable release.
Readback confirms routing state.
User-facing error rate returns to baseline.
In-flight jobs and DB records are reconciled.
No unauthorized manual changes remain.
Evidence and UTC timeline are preserved.
Operator can explain what was and was not rolled back.
~~~

Nếu lab chỉ chạy một lệnh traffic set mà không kiểm tra phục hồi ở phía người dùng, bài thực hành rollback chưa đạt.

## 26. Security, governance và blast radius

### 26.1. Quyền least privilege

| Principal | Quyền cần thiết | Không nên mặc định có |
|---|---|---|
| CI build identity | Pull source, push image vào ACR | Production slot swap |
| CD deploy identity | Deploy revision/slot đúng scope | Subscription Owner |
| Traffic controller | Update routing/weights đúng app | Key Vault Administrator |
| Runtime managed identity | Đọc secrets/data resources cần thiết | Sửa IAM resource group |
| On-call rollback operator | Route traffic về stable theo runbook | Xóa database/registry |
| DB migration identity | Thao tác schema đã phê duyệt | Global DB admin không cần thiết |
| Audit/observer | Xem logs/metrics/deployment history | Secret values hoặc sửa production |

Azure RBAC cần kiểm tra role definitions/actions và scope theo resource; không suy rằng một tên role chung luôn có quyền traffic routing cho mọi dịch vụ.

### 26.2. Tách preview/staging khỏi tác động production

- Staging slots/preview URLs có thể nằm trên Internet nếu không bảo vệ.
- Test routes không nên bypass WAF/auth.
- Test accounts và fake payments phải được cấp có policy.
- Không dùng production payment token cho synthetic transactions.
- Preview/green chỉ truy cập được qua test IP/VNet hoặc auth phù hợp.
- Giám sát truy cập staging hostnames/label URLs.
- Không in Azure credentials/connection strings trong pipeline logs.

### 26.3. Rủi ro supply-chain compromise

Một canary nhận 1% traffic nhưng có thể đọc **toàn database hoặc vault** nếu runtime identity có quyền quá rộng. **Canary traffic 1% không có nghĩa blast radius bảo mật chỉ 1%.**

Cần:
- Image signature/provenance verification.
- Least-privilege runtime identity.
- NetworkPolicy/private endpoints.
- Egress controls.
- Secret scan, SAST/SCA và vulnerability policies.
- Protected runners/service connections.
- Audit người có quyền override gates/approvals.
- Giữ image stable và kiểm tra tính toàn vẹn rollback.

### 26.4. IaC và configuration drift

Khi operator sửa traffic weights hay Service selector trực tiếp:
- Terraform/Bicep/ARM/GitOps source of truth phải được cập nhật/đối soát.
- Có drift detection theo khả năng.
- Tách emergency rollback khỏi routine config changes.
- Không để auto-deploy đẩy lại version lỗi ngay.
- Ghi actual state sau mọi automation.
- Giữ release history rõ.

Bicep/Terraform có thể quản lý app/ingress, nhưng **không nhất thiết phù hợp làm controller cho từng nấc 1% canary** nếu plan/apply gây nhiều side effects; cần chủ sở hữu cơ chế routing nhất quán.

### 26.5. Compliance và audit

Release evidence nên có:
- Artifact digest, commit, SBOM/signature reference.
- Subscription/resource group/region chịu ảnh hưởng.
- Environment/tenant/rings.
- Approval IDs, thời gian UTC.
- Migration/schema version và backup evidence.
- Traffic weights trước/sau.
- Metric/KQL evidence đã redact.
- Rollback tests và owners.
- Business verification và incident actions.
- Cleanup/contract authorization.

Không đưa JWT, PII, SAS hoặc payment details vào báo cáo chỉ để minh họa rollback.


## 27. Capacity planning, chi phí và giới hạn của blue-green

### 27.1. Blue-green có thể tăng gấp đôi mức compute yêu cầu

Giả sử Blue trên AKS chạy 6 Pods, mỗi Pod yêu cầu 0,5 vCPU và 1 GiB memory. Để chạy Green cùng cấu hình trước cutover:

~~~text
Blue capacity reservations:
  6 pods × 0.5 vCPU = 3 vCPU
  6 pods × 1 GiB = 6 GiB memory

Green capacity reservations:
  6 pods × 0.5 vCPU = 3 vCPU
  6 pods × 1 GiB = 6 GiB memory

During overlapping window:
  6 vCPU and 12 GiB requested
  before system pods, overhead, failover capacity
~~~

Đây là **requests/reservations của Pods**, không phải hóa đơn AKS; chi phí phụ thuộc VM/node SKUs, autoscaler, node utilization, region, networking, storage và cách tính tiền. Cần đảm bảo cluster còn capacity hoặc có thể scale trước khi canary.

### 27.2. Canary 1% không có nghĩa tính tiền 1%

Một Green có 4 replicas ở trạng thái warmed, nhận 1% traffic, vẫn dùng:
- CPU/memory để giữ app process.
- Sidecar/agent overhead.
- Connection pool/database connections.
- Logs/metrics/traces.
- Image storage/registry egress.
- Cache memory.
- Load balancer/gateway/Front Door charges.

Với Container Apps, chi phí phụ thuộc resource profile, consumption/dedicated plan, active replicas, requests và scale rules; tính theo billing model thực tế. Với App Service slots trên cùng plan, một slot mới có thể **chia sẻ capacity**, dẫn đến performance contention dù không có plan riêng.

### 27.3. Các cấu phần chi phí

~~~text
Progressive delivery total cost =
    Stable compute
  + Green/canary compute during overlap
  + Extra gateway/routing/Front Door costs
  + Database and cache load from both versions
  + Registry image storage and artifact retention
  + Azure Monitor/Log Analytics ingestion/retention
  + CI/CD runner/build minutes and artifact scans
  + Migration/backfill jobs
  + Synthetic/load tests
  + Incident/approval operations
~~~

Không nên tối ưu bằng cách xóa Blue ngay sau promote nếu rủi ro rollback cao. Quyết định thời gian giữ Stable là trade-off giữa **recovery readiness** và chi phí.

### 27.4. Các đòn bẩy tối ưu

- Warm Green đủ tối thiểu theo readiness/SLO, không scale quá mức trước traffic.
- Đo CPU/memory/connection pools thực tế và dùng autoscaler khi hỗ trợ.
- Hạn chế chạy cùng lúc nhiều release candidates.
- Dùng image retention policy theo rollback window, không để mọi builds vĩnh viễn.
- Điều chỉnh tracing/sampling/retention.
- Không tạo quá nhiều cross-region origins nếu business không cần.
- Chạy migration/backfill theo batch để tránh scale database vô lý.
- Dùng release windows phù hợp traffic mix và on-call.
- Tự động deactivate/cleanup sau khi hết hold window và có approval.

### 27.5. Những metric cost cần theo dõi

| Metric | Ý nghĩa |
|---|---|
| Extra compute-hours per release | Chi phí giữ song song |
| Mean rollback time | Hiệu quả đầu tư capacity ổn định |
| Failed-release incidents | Chất lượng release |
| Percentage of canaries auto-rolled back | Chất lượng gates và sản phẩm |
| App Insights GB ingested per release | Observability budget |
| Deployment frequency vs rollback frequency | Cân bằng tốc độ và độ tin cậy |
| Registry/artifact storage retained | Supply-chain và recovery |
| DB/network spend during migration | Chi phí thay đổi data plane |
| Customer-visible failed requests | Chi phí tác động thực |
| Time spent in HOLD | Có đủ telemetry/samples hay không |

Tổng chi phí sở hữu không chỉ là vài phút chạy Pod mới; một lần rollback không chuẩn gây mất dữ liệu có thể tốn hơn nhiều lần giữ Green standby.

## 28. Troubleshooting và runbooks

### 28.1. Bảng triệu chứng

| Triệu chứng | Nguyên nhân thường gặp | Hành động |
|---|---|---|
| Staging slot không tồn tại | App Service plan không hỗ trợ/slot chưa tạo | Kiểm tra SKU và slot list |
| Slot swap fail | Warm-up/config/permissions | Đọc swap diagnostics, sticky settings |
| Traffic routing 10% nhưng không thấy Green | Cookie affinity, traffic nhỏ, route chưa áp | Xem slot metrics, cookies, actual requests |
| Swap rollback không về Blue | Blue đã bị redeploy hoặc config drift | Kiểm tra slot digests và backup |
| ACA revision không nhận traffic | Single mode/inactive/unhealthy revision | Xem activeRevisionsMode/status, probes |
| ACA weights không khớp kỳ vọng | Revision names sai hoặc ingress config | Readback traffic config |
| AKS rollout treo | Readiness/image pull/quota/pending Pods | kubectl describe/events, ACR |
| kubectl undo bị ghi đè | GitOps vẫn desired v2 | Revert source of truth |
| AKS canary không chia 90/10 | Không có route controller/mesh support | Gateway API/Istio status/mesh participation |
| Service selector rollback xong vẫn 502 | Connection draining/endpoints chưa sync | Đo readiness/EndpointSlices/ingress |
| Front Door Green không có traffic | Priority/health probe/route/caching | Kiểm tra origins và access logs |
| 5% traffic nhưng 50% users lỗi | Session affinity hoặc tenant skew | Phân tích cohort/user distribution |
| Stable cũng chậm khi Green lỗi | Shared compute/database/registry | Scale/cô lập resource, review quotas |
| Database fail sau rollback | Destructive migration | DB recovery/forward fix |
| Worker v1 không đọc message v2 | Event schema incompatible | Versioned contracts và DLQ/runbook |
| Traffic = 0 nhưng requests v2 còn | In-flight, sticky sessions, background jobs | Drain/observability, không xóa ngay |
| Alerts im lặng | Telemetry ingestion/delay/sampling | Fail-safe HOLD, monitor export health |
| Auto-rollback lặp/redeploy lại lỗi | Two controllers/GitOps conflict | Release lock và desired state |
| Release mới mất quyền Key Vault | Identity/slot/revision/IAM khác | Kiểm tra data-plane roles/network |
| ACR pull lỗi sau rollback | Digest bị xóa/registry denied | Retain artifact, identity fixes |
| Chi phí log tăng đột biến | Duplicate telemetry/higher traffic | Sampling, tags, cost breakdown |
| HTTPS health probe xanh nhưng checkout lỗi | Probe quá nông | Business canary test/critical metrics |
| Front Door cache khiến user chưa thấy v2 | Stale cached content | Cache policy/content hashing |
| Pipeline ghi status success nhưng user lỗi | Chỉ kiểm tra command exit code | Post-deploy metrics/business gates |

### 28.2. Runbook A: canary 5xx tăng

1. Ghi release ID, UTC time, platform, canary weights và impacted cohort.
2. Xác định metric 5xx **theo version** (không lấy tổng gộp).
3. Kiểm tra request count và ingest delay.
4. Phân loại severity: data integrity/security cần xử lý nhanh hơn sampling wait.
5. **HOLD** tất cả nấc promote tiếp theo.
6. Nếu gate rollback đạt điều kiện, route 100% traffic về Stable.
7. Readback weights/service selectors/front door origins.
8. Xác minh Stable readiness/capacity và error rate hồi phục.
9. Xem in-flight/background jobs và dữ liệu bị Green ghi sai.
10. Giữ traces/logs/evidence; viết incident timeline, không redeploy lỗi.

### 28.3. Runbook B: mất khả năng rollback vì database

1. Ngăn tiếp tục promote và các migrations mới.
2. Xác định migration version và affected tables/rows.
3. Kiểm tra v1 còn tương thích schema hiện tại không.
4. Nếu có, traffic rollback theo plan và verify.
5. Nếu không, **không tự đưa v1 vào production** khi biết nó fail.
6. Làm việc với DBA để chọn forward fix/recovery/compensation.
7. Xác minh backup, RPO/RTO, replication và dữ liệu writes mới.
8. Có approval thay đổi schema/data.
9. Test read/write của stable và target versions trong môi trường an toàn.
10. Sau recovery, cập nhật expand–contract gates và migration pipeline.

### 28.4. Runbook C: GitOps hoàn tác rollback thủ công

1. Xác định Flux/Argo CD hoặc controller đang reconcile resource.
2. Pause promotion automation để chặn bản lỗi.
3. Ghi current live state và desired state trong Git.
4. Commit revert image digest/HTTPRoute/Service selector về Stable.
5. Review/merge theo emergency policy.
6. Đợi reconcile và quan sát trạng thái controller.
7. Verify traffic và Pods thực tế; không chỉ nhìn Git commit.
8. Kiểm tra release lock/automation đã dừng retry v2.
9. Resume CI/CD sau khi root cause được xử lý.
10. Lưu audit changes và lessons learned.

### 28.5. Runbook D: App Service swap lỗi sau 100%

1. Kiểm tra production đang chạy Green hay Blue bằng release ID.
2. Kiểm tra staging còn giữ artifact Blue đủ điều kiện rollback không.
3. Kiểm tra slot settings, identity và DB compatibility.
4. Nếu các điều kiện đúng, swap trở lại có approval/incident policy.
5. Đọc lại slot versions và production hostname.
6. Kiểm tra cookies/traffic routing không trỏ nhầm staging.
7. So p95, error rate, Key Vault/DB errors.
8. Kiểm tra queues/inflight.
9. Nếu staging đã bị deploy đè, dùng approved stable digest redeploy, không swap mù.
10. Ghi nguyên nhân và cải thiện state verification.

### 28.6. Runbook E: không có dữ liệu telemetry

1. Ngăn promote; **no data ≠ healthy**.
2. Kiểm tra version tagging/Cloud Role Name.
3. Kiểm tra App Insights connection string/Log Analytics permissions.
4. Kiểm tra sampling, ingestion delay và query time window.
5. Kiểm tra egress/DNS/TLS/proxy của exporter.
6. Kiểm tra 429/5xx và dropped telemetry.
7. Dùng nguồn đo độc lập từ ingress/gateway/metrics khi có.
8. Nếu vẫn không có evidence, HOLD release và giải quyết monitoring.
9. Không tắt toàn bộ logging security controls để lấy raw data.
10. Diễn tập lại metric gate trong staging sau khi khắc phục.

### 28.7. Runbook F: rollback thành công nhưng phát sinh side effects

1. Xác định khoảng thời gian Green đã nhận traffic.
2. Liệt kê operation IDs và records theo nguồn có quyền.
3. Đối chiếu orders accepted/persisted/charged.
4. Xem Service Bus deliveries, DLQ và worker retries.
5. Không xóa hàng loạt dữ liệu chỉ vì “đến từ v2”.
6. Chạy idempotent reconciliation/compensation được business owner duyệt.
7. Xác minh không duplicate payments/invoices.
8. Thông báo incidents theo policy và legal requirements.
9. Giữ audit trail, PII redaction.
10. Chỉ đóng incident khi data correctness đã được xác nhận.

## 29. Case study: đơn hàng bị lỗi phí vận chuyển

### 29.1. Kiến trúc

Một doanh nghiệp triển khai:
- Orders API Spring Boot trên Azure Container Apps.
- Pricing API trên AKS.
- Azure SQL Database lưu orders.
- Azure Service Bus cho Invoice Worker.
- Azure Blob Storage lưu hóa đơn.
- Azure Key Vault quản lý partner API token.
- Azure Container Registry lưu image digests.
- Azure Monitor Application Insights và Log Analytics.
- Azure DevOps dùng Environment approvals.

~~~mermaid
flowchart TD
    U["Users"] --> ING["Container Apps ingress"]
    ING -->|"95%"| BLUE["Orders stable v1"]
    ING -->|"5%"| GREEN["Orders canary v2"]
    BLUE --> P["Pricing API AKS"]
    GREEN --> P
    BLUE --> SQL["Azure SQL"]
    GREEN --> SQL
    BLUE --> SB["Service Bus"]
    GREEN --> SB
    SB --> W["Invoice Worker"]
    W --> B["Blob Storage"]
    BLUE -. "Telemetry" .-> M["Application Insights"]
    GREEN -. "Telemetry" .-> M
~~~

### 29.2. Trước canary

- CI tạo image v2 và SBOM, kiểm tra digest.
- DB migration chỉ **expand**, thêm ShippingRuleVersion nullable.
- Worker v1 đọc được messages của cả v1 và v2.
- Green đã smoke test với đơn giả.
- Stable v1 còn 6 ready replicas.
- Telemetry được tag release v1/v2.
- Có quyền rollback và metric gates trong pipeline.
- Cost/hold window được phê duyệt.

### 29.3. Lưu lượng và tín hiệu

Giả sử tổng request rate đều đặn **6.000 requests/phút** và routing đạt gần đúng 95/5:

~~~text
Canary v2:
  ~300 requests/min × 15 min = 4,500 requests
  5xx rate = 2.0% → 90 errors

Stable v1:
  ~5,700 requests/min × 15 min = 85,500 requests
  5xx rate = 0.2% → 171 errors

Relative rate:
  Canary 2.0% vs Stable 0.2% = 10× error rate
~~~

Dù Stable có nhiều failed requests hơn về **số tuyệt đối**, canary tệ hơn rõ về **tỷ lệ lỗi**. Đây là ví dụ thống kê đơn giản: production cần phân tích confidence intervals, theo route/cohort, time window và telemetry sampling. Lỗi thực là v2 không xử lý một loại postal code khiến tính phí vận chuyển phát sinh exception.

### 29.4. Ra quyết định

- Canary đã có hơn 500 requests.
- Canary 5xx vượt ngưỡng tuyệt đối 1%.
- Canary vượt Stable + 0,5 percentage point.
- Business error logs xác nhận lỗi checkout.
- Không có migration phá backward compatibility.
- Stable capacity còn tốt.

Quyết định: **ROLLBACK traffic ngay** về v1, sau đó điều tra root cause. Không đợi tăng traffic lên 20% để “lấy thêm dữ liệu”.

### 29.5. Thao tác

Trong release controller:
1. Dừng promotion pipeline.
2. Đặt traffic weights Stable 100% / Canary 0%.
3. Readback ingress config.
4. Kiểm tra App Insights/ingress metrics về baseline.
5. Kiểm tra orders do Green tạo có duplicate/partial writes không.
6. Kiểm tra Service Bus DLQ và invoice worker.
7. Retain Green image + logs, mở incident với trace IDs.
8. Sửa code/validation trong một commit khác.
9. Build artifact v3, chạy CI/test và canary **mới** với approval.
10. Chỉ contract DB schema sau khi không cần rollback nữa.

### 29.6. Nếu v2 đã drop DB column?

Kết luận hoàn toàn khác: nếu Green migration đã xóa cột Status mà v1 cần, **không đưa 100% traffic về v1 mà chưa khôi phục schema/compatibility**. Cần lựa chọn recovery/forward fix với DBA và dữ liệu đã ghi mới. Đây là lý do migration/rollback preflight phải xảy ra **trước** canary đầu tiên.

### 29.7. Tiêu chí thành công

- Incident được phát hiện trước khi 100% traffic vào v2.
- Hạn chế số requests bị ảnh hưởng.
- Không có dữ liệu bị phá do rollback mù.
- App/worker/DB/queue được reconcile.
- Stable SLO được phục hồi trong RTO đã đề ra.
- Pipeline không tự promote lại v2.
- Metrics/evidence đủ để sửa root cause.
- Có SBOM/digest và audit hoàn chỉnh cho v3.


## 30. Checklist production: canary, blue-green và rollback

### 30.1. Artifact và supply chain

- [ ] Git commit/branch đã qua review và branch protection.
- [ ] CI unit/integration/security tests PASS.
- [ ] Secret scanning/SAST/SCA/vulnerability checks đạt policy.
- [ ] Có SBOM/provenance/signature evidence khi tổ chức yêu cầu.
- [ ] Image digest/JAR version bất biến, không phụ thuộc tag latest.
- [ ] Artifact đã test staging chính là artifact promote production.
- [ ] ACR giữ Stable image trong rollback window.
- [ ] CI/CD identity dùng federation/managed identity khi phù hợp.
- [ ] Service connections và runner permissions đủ hẹp.
- [ ] Không có credentials/PII trong logs và pipeline artifacts.

### 30.2. Platform readiness

- [ ] SKU/App Service plan hỗ trợ slots và routing cần dùng.
- [ ] Slot-specific settings/connection strings đã xác minh.
- [ ] App Service warm-up và health checks được test.
- [ ] Container Apps multiple revision mode khi cần weight splitting.
- [ ] Stable/Green revisions active và healthy.
- [ ] AKS Pods có readiness/startup/liveness probes phù hợp.
- [ ] AKS có surge capacity/PodDisruptionBudget theo workload.
- [ ] Gateway API/Istio/controller supports weighted routing được kiểm tra.
- [ ] Front Door origins/TLS/WAF/health probes hoạt động.
- [ ] Không dùng DNS weighted routing cho request-level precision mà chưa đánh giá.
- [ ] Preview/staging URLs được bảo vệ và không bypass auth/WAF.
- [ ] Graceful termination/draining đã được thử.

### 30.3. Dữ liệu và backward compatibility

- [ ] Expand schema trước khi deploy v2.
- [ ] v1 và v2 cùng đọc/ghi schema trong rollback window.
- [ ] Migration/backfill được batch và có dữ liệu kiểm chứng.
- [ ] Chưa drop/rename/NOT NULL hóa trường v1 còn cần.
- [ ] Message schema có version/default/unknown fields policy.
- [ ] Service Bus consumers v1/v2 có chiến lược tương thích.
- [ ] Worker draining/lock/offset/duplicates đã được thử.
- [ ] Stable secret/identity vẫn hợp lệ sau rotation.
- [ ] Session, cache, long-lived connections và CDN được kiểm tra.
- [ ] Có compensation/reconciliation nếu v2 đã ghi side effects.
- [ ] Database restore/forward-fix plan rõ nếu traffic rollback không đủ.

### 30.4. Canary metric gates

- [ ] Có baseline Stable theo route/region/cohort.
- [ ] Có release/version tags cho logs/metrics/traces.
- [ ] Có 5xx, p95/p99, CPU/memory, DB errors và queue lag.
- [ ] Có business correctness metrics (orders, payments, invoices).
- [ ] Có sufficient sample size/hold windows.
- [ ] Health probes và synthetic traffic không che SLO.
- [ ] Hiểu sampling/ingestion delay của Application Insights.
- [ ] No data/telemetry stale dẫn đến HOLD, không promote.
- [ ] Critical security/data incident dẫn đến rollback/mitigation ngay.
- [ ] Gate thresholds/decision owners đã phê duyệt.
- [ ] Có readback actual traffic weights ở mỗi vòng.
- [ ] Canary không làm Shared Stable capacity suy giảm đáng kể.

### 30.5. Rollback và automation

- [ ] Stable revision/slot/deployment có sẵn và healthy.
- [ ] Stable artifact/digest có thể pull/download.
- [ ] Commands traffic rollback đã được diễn tập.
- [ ] Pipeline dừng promote sau rollback, không loop redeploy v2.
- [ ] GitOps source of truth có cơ chế revert đồng bộ.
- [ ] Rollback không yêu cầu gán quyền admin mới lúc incident.
- [ ] Readback trạng thái sau rollback là bắt buộc.
- [ ] Có cách kiểm tra user-facing metrics trở lại baseline.
- [ ] Inflight sessions/jobs và queue workers có drain plan.
- [ ] Có incident owner và communication plan.
- [ ] Có phê duyệt riêng khi chuyển sang DB restore/forward fix.
- [ ] Evidence trước/sau rollback được lưu không chứa secrets.

### 30.6. Chi phí, governance và closeout

- [ ] Đã tính compute overlap/registry retention/monitoring costs.
- [ ] Có budget/alerts theo subscription/resource group/tags.
- [ ] Managed identities, Key Vault và network access được kiểm tra.
- [ ] Có Azure RBAC scopes/approval audit.
- [ ] Có monitoring ingestion/retention và redaction policy.
- [ ] Có giới hạn số canaries cùng chạy và resource quotas.
- [ ] Có quy định giữ stable version đủ rollback window.
- [ ] Contract schema chỉ sau khi rollback window đóng.
- [ ] Có post-release report và lessons learned.
- [ ] Release được đóng bằng business/technical verification, không chỉ CLI success.

## 31. Câu hỏi tự kiểm tra

1. **Deployment khác release thế nào?** Deployment đặt artifact vào runtime; release cho người dùng dùng phiên bản/tính năng đó.
2. **Canary là gì?** Cho phiên bản mới nhận một phần traffic/cohort, tăng dần theo gates.
3. **Blue-green là gì?** Hai môi trường/version song song, chuyển serving giữa chúng.
4. **Rolling update là gì?** Thay instances theo từng đợt, thường không có weighted HTTP traffic rõ.
5. **Recreate có rủi ro gì?** Có thể downtime và khó rollback.
6. **Feature flag có thay container rollback không?** Không, chỉ điều khiển behavior được flag bảo vệ.
7. **A/B testing khác canary ở đâu?** A/B đo tác động sản phẩm, canary ưu tiên an toàn release.
8. **Vì sao immutable artifact quan trọng?** Bảo đảm artifact được test là artifact được promote/rollback.
9. **Image digest khác tag latest thế nào?** Digest nhận diện image content cụ thể; tag có thể thay đổi.
10. **SBOM giúp gì?** Biết thành phần/thư viện trong artifact để đánh giá supply-chain risk.
11. **Provenance/attestation phục vụ gì?** Chứng minh nguồn build, quy trình và artifact metadata theo policy.
12. **Sao không tự rebuild ở production?** Dễ tạo artifact khác với bản đã test.
13. **Readiness khác liveness thế nào?** Readiness quyết định nhận traffic; liveness cho biết container cần restart khi kẹt.
14. **Smoke test GET / có đủ?** Không, cần kiểm tra dependencies/business paths.
15. **Canary 10% requests có chắc 10% users không?** Không, sticky/caching/traffic patterns khác.
16. **Sticky cookie ảnh hưởng gì?** Một client có thể tiếp tục vào một slot/revision.
17. **Hold window dùng để làm gì?** Thu đủ samples/telemetry và kiểm tra delayed effects.
18. **Nếu không có metrics thì promote hay HOLD?** HOLD theo chính sách fail-safe.
19. **App Service deployment slot dùng để làm gì?** Deploy/test một phiên bản trước khi swap/route.
20. **Tất cả App Service plans đều có slots không?** Không, phụ thuộc tier/SKU.
21. **Swap staging/production làm gì?** Chuyển code/config theo swap mechanics giữa slots.
22. **Swap có rollback database không?** Không.
23. **Slot settings sticky nghĩa gì?** Một số config ở lại với slot theo cài đặt, không swap cùng code.
24. **App Service traffic-routing dùng khi nào?** Chia một phần HTTP traffic tới staging slot.
25. **traffic-routing clear có rollback code đã swap không?** Không, chỉ thay routing.
26. **App Service slots có luôn compute độc lập không?** Không, có thể chia sẻ App Service plan.
27. **Container Apps revision là gì?** Snapshot của revision-scope template/config.
28. **Muốn chia traffic nhiều revisions cần mode nào?** Multiple active revisions mode.
29. **Revision inactive có tự nhận weight traffic được không?** Không, phải xem activation/health/ingress.
30. **ACA HTTP traffic weights có chia queue consumer messages không?** Không.
31. **ACA label URL có giống weight không?** Không, test/endpoint labeling khác routing weights.
32. **AKS Deployment RollingUpdate có chính xác 10% request canary không?** Không.
33. **maxUnavailable: 0 nghĩa gì?** Cố giữ số Pods available theo rollout/readiness, cần capacity.
34. **kubectl rollout undo hoàn tác những gì?** Deployment Pod template/history, không phải DB/data/config ngoài scope.
35. **GitOps có thể làm mất rollback thủ công không?** Có, nếu desired state vẫn v2.
36. **AKS blue-green bằng Service selector hoạt động thế nào?** Service chọn Pods track blue hoặc green.
37. **Kubernetes Service có trường traffic weight native không?** Không có weighted HTTP fields chuẩn.
38. **Gateway API HTTPRoute hỗ trợ gì?** Có thể định tuyến giữa backendRefs theo weight nếu controller hỗ trợ.
39. **Istio dùng gì để traffic shift?** VirtualService/DestinationRule subsets theo mesh setup.
40. **Front Door origin priority khác weight thế nào?** Priority ưu tiên/failover; weight chia giữa eligible origins cùng priority.
41. **Vì sao Front Door weights không hoàn toàn chính xác?** Health, affinity, cache, routing selection và traffic volume.
42. **Traffic Manager DNS weighted có request-level precision không?** Không do DNS caching/TTL.
43. **Schema expand–migrate–contract là gì?** Mở rộng tương thích, chuyển dữ liệu, chỉ loại bỏ phần cũ khi an toàn.
44. **Đổi schema destructive sớm gây gì?** Bản v1 không thể rollback phục vụ.
45. **Data migration rollback có thể chỉ là restore backup không?** Không, có thể mất writes mới và cần DBA/forward fix.
46. **Message schema versioning quan trọng vì sao?** Worker v1/v2 cùng xử lý queue/replay an toàn.
47. **Dừng worker v2 cần làm gì?** Drain messages/locks/checkpoints và chống duplicate.
48. **Idempotency giúp gì khi retry?** Ngăn side effects trùng dù message/request được thực hiện lại.
49. **Traffic rollback là gì?** Route về stable; không tự hoàn tác code config/data.
50. **Feature flag kill switch cần điều kiện gì?** Có OFF path đã test, access control, audit và data consistency.
51. **Metric gate cần so cái gì?** Canary vs Stable theo same window/cohort, thresholds và đủ samples.
52. **Có nên dùng sampled traces làm mẫu số duy nhất của error SLO?** Không nếu không hiểu sampling/weights.
53. **Một lỗi data corruption có cần đủ 500 requests mới rollback?** Không, critical gate có thể kích hoạt ngay.
54. **Vì sao pipeline cần readback traffic sau mutation?** Để biết trạng thái thật thay vì chỉ tin exit code.
55. **Vì sao swap không idempotent khi chạy hai lần?** Lần thứ hai có thể đảo ngược kết quả lần đầu.
56. **Azure DevOps environment: production tự tạo approval không?** Không, phải cấu hình approvals/checks.
57. **GitHub Actions environment tự động yêu cầu reviewer không?** Không nếu protection rules chưa bật.
58. **OIDC federation giảm rủi ro nào?** Hạn chế cần lưu service principal secret dài hạn.
59. **Canary 1% có giới hạn mức truy cập DB chỉ 1% không?** Không, identity có thể truy cập toàn DB theo quyền.
60. **Tại sao giữ Stable sau promote 100%?** Để rollback nhanh khi lỗi muộn xuất hiện.
61. **Có nên xóa image v1 khỏi ACR ngay?** Không trước khi hết recovery/rollback window.
62. **Khi release có 5xx rate thấp nhưng ghi trùng payments nên làm gì?** Critical rollback/mitigation và data reconciliation.
63. **Auto-rollback có thể gây loop thế nào?** Promotion/GitOps controller đẩy version lỗi trở lại.
64. **Khi nào roll forward hợp lý hơn rollback?** Khi data/schema hoặc security khiến v1 không còn an toàn.
65. **Canary 5% traffic nhưng Green gây memory contention cho Blue được không?** Có khi dùng chung plan/DB/nodes.
66. **Vì sao chi phí Green không bằng 5% Stable?** Green vẫn chạy replicas, monitoring và dependencies.
67. **Một runbook rollback phải có gì?** Release ID, stable status, data compatibility, action, readback, evidence.
68. **Khi Front Door origin health check failed thì actual weights sao?** Có thể đổi vì origin bị loại khỏi eligible set.
69. **Để xem canary trên Application Insights cần gì?** Role/release metadata và query phân tách versions.
70. **Một release hoàn tất khi nào?** Các gates, user-facing SLO, business integrity và evidence đều được xác nhận.

## 32. Tài liệu tham khảo

Các nguồn dưới đây là điểm tra cứu chính thức. API, hỗ trợ SKU, giới hạn CLI và phiên bản controller có thể thay đổi; kiểm tra tài liệu theo môi trường đang sử dụng trước khi áp dụng thực tế.

### Azure App Service

- [Set up staging environments in Azure App Service](https://learn.microsoft.com/en-us/azure/app-service/deploy-staging-slots) — slots, swap, sticky settings, warm-up và traffic routing.
- [Azure App Service overview](https://learn.microsoft.com/en-us/azure/app-service/overview) — hosting, app plan/SKU và capabilities.
- [App Service health check](https://learn.microsoft.com/en-us/azure/app-service/monitor-instances-health-check) — kiểm tra instance health.
- [Azure CLI webapp traffic-routing](https://learn.microsoft.com/en-us/cli/azure/webapp/traffic-routing) — lệnh show/set/clear và distribution.
- [Azure CLI webapp deployment slot](https://learn.microsoft.com/en-us/cli/azure/webapp/deployment/slot) — swap/create/list.

### Azure Container Apps

- [Azure Container Apps revisions](https://learn.microsoft.com/en-us/azure/container-apps/revisions) — revision scopes/modes và lifecycle.
- [Traffic splitting in Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/traffic-splitting) — weights, canary và labels.
- [Azure Container Apps health probes](https://learn.microsoft.com/en-us/azure/container-apps/health-probes) — startup/liveness/readiness behavior.
- [Azure Container Apps CLI](https://learn.microsoft.com/en-us/cli/azure/containerapp) — revisions và ingress commands.

### AKS, Gateway API và Istio

- [Kubernetes Deployments](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/) — RollingUpdate, ReplicaSets, rollout history.
- [Kubernetes Services](https://kubernetes.io/docs/concepts/services-networking/service/) — selectors, Endpoints, traffic basics.
- [Gateway API traffic splitting](https://gateway-api.sigs.k8s.io/guides/traffic-splitting/) — HTTPRoute weighted backendRefs.
- [Istio traffic shifting](https://istio.io/latest/docs/tasks/traffic-management/traffic-shifting/) — VirtualService/DestinationRule.
- [AKS Istio service mesh add-on](https://learn.microsoft.com/en-us/azure/aks/istio-about) — capabilities, limitations và vận hành.
- [AKS applications](https://learn.microsoft.com/en-us/azure/aks/concepts-clusters-workloads) — workloads, capacity và operational design.
- [GitOps with Flux v2 on AKS](https://learn.microsoft.com/en-us/azure/azure-arc/kubernetes/conceptual-gitops-flux2) — desired state và reconciliation.

### Azure Front Door và traffic steering

- [Azure Front Door routing methods](https://learn.microsoft.com/en-us/azure/frontdoor/routing-methods) — priority/weight/latency.
- [Azure Front Door origins and origin groups](https://learn.microsoft.com/en-us/azure/frontdoor/origin) — origin weights, probes và health.
- [Azure Traffic Manager routing methods](https://learn.microsoft.com/en-us/azure/traffic-manager/traffic-manager-routing-methods) — weighted DNS, TTL và limitations.

### CI/CD, observability, bảo mật, chi phí

- [Azure DevOps deployment jobs](https://learn.microsoft.com/en-us/azure/devops/pipelines/process/deployment-jobs) — environment-bound deployments.
- [Azure DevOps approvals and checks](https://learn.microsoft.com/en-us/azure/devops/pipelines/process/approvals) — environments, approvals và resource checks.
- [GitHub Actions with Azure OpenID Connect](https://learn.microsoft.com/en-us/azure/developer/github/connect-from-azure-openid-connect) — identity federation.
- [Azure Container Registry best practices](https://learn.microsoft.com/en-us/azure/container-registry/container-registry-best-practices) — registry, artifact lifecycle và reliability.
- [Azure Monitor Application Insights](https://learn.microsoft.com/en-us/azure/azure-monitor/app/app-insights-overview) — errors, latency và dependency diagnostics.
- [AppRequests table reference](https://learn.microsoft.com/en-us/azure/azure-monitor/reference/tables/apprequests) — request telemetry/KQL schema.
- [Azure SQL Database](https://learn.microsoft.com/en-us/azure/azure-sql/database/) — schema/data operations và resilience.
- [Azure Service Bus](https://learn.microsoft.com/en-us/azure/service-bus-messaging/) — queue delivery/retries/DLQ semantics.
- [Azure Well-Architected safe deployment practices](https://learn.microsoft.com/en-us/azure/well-architected/operational-excellence/safe-deployments) — progressive rollout, ring deployment và rollback.
- [Azure Cost Management](https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/) — chi phí, budget và allocation.
- [Azure Chaos Studio](https://learn.microsoft.com/en-us/azure/chaos-studio/chaos-studio-overview) — thực hành fault injection theo policy.

**Kết luận:** canary, blue-green và rollback trên Azure không chỉ là lệnh **swap slot**, **đặt revision weight** hay **kubectl rollout undo**. Một release an toàn bắt đầu từ **artifact bất biến, identity/ACR và approval**, tiếp tục bằng **deploy song song, readiness, traffic được kiểm soát, metric gates dựa trên bằng chứng**, và kết thúc bằng **xác minh business correctness cùng năng lực phục hồi**. App Service deployment slots, Azure Container Apps revisions, AKS Gateway API/service mesh và Azure Front Door cung cấp những cơ chế định tuyến khác nhau; chọn đúng theo runtime/SKU, session state, traffic và chi phí. Quan trọng nhất, **rollback traffic không hoàn tác schema, dữ liệu, messages, secrets hoặc side effects**. Vì vậy phải thiết kế expand–migrate–contract, message versioning, stable artifact retention, drift control, incident runbooks và diễn tập rollback **trước** khi tăng lưu lượng vào phiên bản mới.

