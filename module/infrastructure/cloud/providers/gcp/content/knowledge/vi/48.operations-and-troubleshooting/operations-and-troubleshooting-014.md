# Quản lý thay đổi API, runtime và thông báo ngừng hỗ trợ

Một dịch vụ Spring Boot có thể chạy ổn định trên Google Cloud nhiều tháng rồi gặp lỗi khi cập nhật GKE cluster, nâng cấp phiên bản PostgreSQL, thay JDK trong container hoặc triển khai lại Cloud Run function sử dụng runtime đã ngừng hỗ trợ. Trước đó, Google Cloud có thể đã thông báo qua release notes, email, chính sách support hoặc deprecation insights. Nếu các thông báo không có người nhận, không được ánh xạ đến tài nguyên đang chạy và không biến thành nhiệm vụ có hạn hoàn thành, sự thay đổi “bất ngờ” thực ra là **nợ kỹ thuật chưa được quản trị**.

Bài học trong chương **Vận hành và xử lý sự cố** của module **CLOUD_PROVIDERS_GCP** xây dựng quy trình theo dõi **API, runtime, phiên bản dịch vụ và thông báo ngừng hỗ trợ** từ khâu phát hiện đến đánh giá tác động, thử nghiệm, triển khai, đo lường và lưu bằng chứng. Kiến thức áp dụng cho các project có IAM/VPC, Compute Engine, GKE, Cloud Run, dịch vụ lưu trữ, Cloud SQL và ứng dụng Java; đồng thời liên hệ bảo mật, tự động hóa phát hành, SLO và chi phí. Mục tiêu là vận hành có kế hoạch chứ không trì hoãn nâng cấp đến khi không thể khởi chạy hoặc triển khai phiên bản mới.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt launch stage, deprecation, end of standard support, extended support, decommission và API removal.
- Xây dựng inventory/API-runtime dependency register có owner, nơi dùng, hạn EOL và bằng chứng.
- Cấu hình kênh nhận tin qua Essential Contacts, product release notes và quy trình tiếp nhận thông báo; không nhầm với cảnh báo sự cố đang diễn ra từ Personalized Service Health.
- Nhận diện tác động từ GKE Kubernetes deprecated APIs, runtime của Cloud Run, Cloud SQL major version, gcloud/SDK và client libraries.
- Lập kế hoạch nâng cấp Java/Spring, Kubernetes manifests và database theo kiểm thử hợp đồng, khả năng tương thích và progressive delivery.
- Viết runbook kiểm soát thay đổi có điều kiện go/no-go, rollback, audit và quy trình xử lý trường hợp quá hạn hỗ trợ.

## 1. Các thuật ngữ vòng đời: đừng gộp tất cả thành EOL

| Thuật ngữ | Ý nghĩa vận hành | Điều cần làm |
|---|---|---|
| Preview/Pre-GA | Tính năng đang thử nghiệm, SLA và bảo đảm thay đổi có thể khác GA | Giới hạn phạm vi dùng; có phương án rút lui nếu API thay đổi |
| GA | Được cung cấp chính thức theo điều khoản và chính sách tương ứng | Theo dõi bản vá, security notices và release notes |
| Deprecated | Google hoặc upstream khuyến nghị ngừng dùng; có thể vẫn hoạt động tạm thời | Dừng phụ thuộc mới, lên kế hoạch migrate |
| End of standard/regular support | Không còn nhận toàn bộ hỗ trợ thường kỳ; một số dịch vụ có Extended | Đánh giá rủi ro bảo mật, phí và hạn nâng cấp |
| Extended support | Tiếp tục hỗ trợ có giới hạn, đôi khi tính thêm phí | Tạm dùng trong thời gian có kế hoạch nâng cấp được phê duyệt |
| End of support (EoS/EOL) | Phiên bản không còn được hỗ trợ theo policy cụ thể | Xử lý như rủi ro cao; có thể bị auto-upgrade hoặc không được hỗ trợ |
| Decommission/removal/shutdown | Không cho tạo/deploy hoặc tính năng/API đã bị loại bỏ; workload cũ có thể dừng | Phải di chuyển trước mốc, rollback sang bản cũ có thể không còn khả dụng |
| Breaking change | Thay đổi hành vi, hợp đồng, quyền, schema hoặc response khiến client không tương thích | Contract tests, kế hoạch triển khai song song và rollback |

**Không tồn tại một mốc thông báo cố định cho mọi dịch vụ GCP.** Điều khoản deprecation của Google Cloud áp dụng theo từng dịch vụ/điều khoản hợp đồng; các tính năng Pre-GA có thể không thuộc cùng chính sách. Runtime, database engine và GKE có chu kỳ riêng. Cần đọc trang lifecycle đúng sản phẩm, phiên bản và vùng triển khai, không lấy “thông thường báo trước 12 tháng” làm cam kết chung.

### Những thứ vẫn có thể hoạt động nhưng đã nguy hiểm

- Container Java 11 vẫn khởi chạy, nhưng base image đã hết cập nhật bảo mật và không còn pipeline build có thể tái tạo.
- PostgreSQL major cũ chạy trong Cloud SQL nhờ extended support, nhưng chi phí tăng và thời hạn deprecation tiếp tục đến gần.
- Kubernetes API `v1beta1` còn xuất hiện trong manifest/template CI, dù resource đang chạy được do được tạo từ trước; sau upgrade, tạo hoặc cập nhật resource có thể thất bại.
- Một API method còn trả 200 nhưng response field mới hoặc enum mới làm parser dùng `switch` cố định bị lỗi.
- Library cũ chưa hỏng hôm nay nhưng build chain dùng TLS/certificate, auth hoặc endpoint không còn được hỗ trợ.

Vận hành cần đo **khả năng deploy/recover mới**, không chỉ tình trạng Running của workload hiện tại.

## 2. Quản trị thay đổi có vòng phản hồi khép kín

Một hệ thống phản ứng có tổ chức với tin ngừng hỗ trợ phải đi qua chuỗi:

~~~mermaid
flowchart LR
  SRC[Nguồn thông báo chính thức] --> IN[Tiếp nhận, phân loại, lưu evidence]
  IN --> MAP[Đối chiếu inventory và dependencies]
  MAP --> RISK[Đánh giá rủi ro và deadline]
  RISK --> PLAN[Owner + kế hoạch upgrade]
  PLAN --> TEST[Compatibility + contract tests]
  TEST --> DEPLOY[Canary / rollout + rollback]
  DEPLOY --> VERIFY[SLO + bảo mật + cost]
  VERIFY --> CLOSE[Đóng ticket, cập nhật inventory]
  CLOSE -. rà soát định kỳ .-> SRC
~~~

**Thông báo không phải hoàn thành công việc.** Mỗi notice cần một ticket có:

- `notice_id`, nguồn URL, ngày phát hành/last update và **ngày hiệu lực** (nếu biết).
- Sản phẩm, API/runtime/version/region/project bị ảnh hưởng và mức độ chắc chắn.
- Owner kỹ thuật, người phê duyệt, deadline nội bộ, priority và trạng thái.
- Danh sách workloads, resource IDs, client/SDK, IaC/config và loại phụ thuộc.
- Phương án migration, test/canary/rollback, cửa sổ thay đổi, SLO theo dõi.
- Link PR/change request, bằng chứng kiểm thử, thời điểm triển khai và điều kiện đóng ticket.

Không đánh dấu “resolved” chỉ vì đã cập nhật một Helm chart trong Git khi thực tế còn CronJob, CI runner hoặc branch deploy đang gọi API cũ. Cần tìm **mọi writer/reader** còn phụ thuộc và xác minh ở môi trường thực.

## 3. Ai chịu trách nhiệm cho phiên bản nào?

| Lớp | Google Cloud quản lý | Người dùng/nhóm vận hành phải quản lý |
|---|---|---|
| Google Cloud managed API/service | Hạ tầng dịch vụ, endpoint và chính sách vòng đời công bố | Contract client, IAM, quota, usage, thay đổi hành vi của API |
| GKE control plane/nodes | Upgrade theo release channel và policy | Chọn channel/maintenance window, Kubernetes manifests, add-ons, app compatibility |
| Cloud Run function dùng Google-managed runtime | Base image/runtime và lifecycle tương ứng | Nâng runtime ID, libraries, code, deploy/tests |
| Cloud Run container do bạn build | Cloud Run vận hành container và platform | Base image OS/JDK, CVEs, rebuild, SBOM và Java/Spring lifecycle |
| Cloud SQL | Managed database engine, maintenance và version policy | Major upgrade planning, driver, schema, extension, query compatibility |
| Cloud Storage/Pub/Sub | Managed services/API | Client library, IAM, schema/event, retry/idempotency và consumer |
| Compute Engine VM | Host virtualization và các dịch vụ managed khác theo policy | Guest OS, JDK, packages, agents, image lifecycle và patching theo cấu hình |
| Terraform/gcloud/SDK | Công bố phiên bản và vòng đời công cụ | Pin phiên bản, cập nhật modules, CI runner, regression tests |

**Shared responsibility** không có nghĩa Google Cloud sẽ nâng giúp JDK trong image do bạn tự tạo. Ngược lại, một hệ quản trị managed có thể áp dụng bản vá hoặc nâng minor version trong maintenance window dù ứng dụng không đổi code; vì thế cần test tương thích và theo dõi release.

### Mẫu RACI

| Công việc | Application owner | Platform/SRE | Security | DBA/Data | Change manager |
|---|---|---|---|---|---|
| Tiếp nhận notice và lưu ticket | C | R | C | C | I |
| Mapping runtime/API đang sử dụng | R | R | C | R khi là DB | I |
| Xác định mức độ ảnh hưởng/SLO | A | R | C | C | I |
| Chọn target version và test plan | R | R | C | R khi là DB | A theo policy |
| Phê duyệt ngoại lệ EOL | A | R | A về security risk | C | A về change window |
| Canary/rollout và rollback | R | R | C | R nếu migration schema | A |
| Xác nhận đóng ticket | A | R | C | C | I |

`R` là thực hiện, `A` là người chịu trách nhiệm/phê duyệt theo quy trình, `C` là tham vấn, `I` là được thông báo. Ma trận chỉ là tham khảo; khi đưa vào doanh nghiệp cần bảo đảm **mỗi quyết định có một owner cuối cùng rõ ràng**, không dùng nhiều `A` mâu thuẫn nhau cho cùng một approval.

## 4. Nguồn thông tin: phân biệt product change với service incident

| Nguồn | Phù hợp để theo dõi | Giới hạn |
|---|---|---|
| Google Cloud **product release notes** và feed | Tính năng mới, thay đổi, bug fix, deprecated functionality, lịch hỗ trợ | Không tự cho biết workload nào của tổ chức đang dùng |
| **Product-specific lifecycle/deprecation pages** | Ngày support và removal của GKE, Cloud Run runtime, Cloud SQL engine... | Mốc có thể được điều chỉnh; phải theo dõi trang gốc |
| **Essential Contacts** | Địa chỉ nhận các thông báo Product updates, Technical, Security, Billing... | Là danh mục contacts, không phải hệ thống trực tiếp gửi/giám sát email |
| **Communication/notification preferences** | Cá nhân đăng ký các thông báo maintenance/upgrade theo project | Thiết lập người dùng, không thay Essential Contacts toàn tổ chức |
| GKE **deprecation insights/Recommender** | Các Kubernetes API/feature được phát hiện đang dùng và sắp bị loại bỏ | Không quan sát được mọi trường hợp, đặc biệt workload hiếm chạy |
| **Cloud Audit Logs** và app telemetry | API callers, deprecated APIs, lỗi sau thay đổi, quyền thực thi | Chỉ thấy hành vi đã được log, có sampling/chi phí Data Access |
| **Personalized Service Health** | Sự cố/disruption có ảnh hưởng đến sản phẩm, vùng và project | Không phải nguồn chính để theo dõi lịch EOL của runtime hoặc API |
| Vendor/upstream security advisories | CVEs và vòng đời Java, Spring, Kubernetes, PostgreSQL, base images | Có thể khác thời gian support của managed service trên GCP |

**Personalized Service Health (PSH)** dùng để nhận biết sự cố đang diễn ra và phối hợp incident response; một notice rằng “Java runtime bị decommission vào năm sau” thuộc **lifecycle/product change management**, cần feed và chính sách riêng. Có thể bổ sung PSH vào dashboard vận hành, nhưng không thay thế theo dõi release notes và Essential Contacts.

### Essential Contacts: cách thiết lập đúng

Google Cloud hỗ trợ các nhóm: `BILLING`, `LEGAL`, `PRODUCT_UPDATES`, `SECURITY`, `SUSPENSION`, `TECHNICAL`, `ALL`. Một tổ chức có thể khai báo contacts tại organization, folder hoặc project; chọn nơi phù hợp phạm vi quản trị. Đặc biệt nên dùng mailbox **nhóm** có người thay thế, ví dụ danh sách phân phối của platform/on-call và security thay vì email cá nhân có nguy cơ nghỉ việc.

~~~bash
# Ví dụ: xem contact trong project hiện tại (chỉ đọc).
gcloud essential-contacts list

# Kiểm tra gcloud CLI/role trước khi thêm hoặc sửa contact bằng console.
gcloud essential-contacts --help
~~~

Để xem contacts của project/folder/organization cụ thể, tra các flags `--project`, `--folder`, `--organization` theo tài liệu phiên bản CLI; **project number** được dùng trong Resource Manager contact resource name, không được nhầm với project ID. Sau khi cấu hình, gửi test email theo hướng dẫn dịch vụ hoặc xác minh mailbox có nhận được thông báo đúng category.

Essential Contacts **không tự gửi email**; nó cung cấp contacts để những dịch vụ Google Cloud khác phát thông báo. Không coi “đã thêm contact” là hoàn tất nếu mailbox không có quy trình phân loại, escalation và tạo ticket.

## 5. Tổ chức inventory: tìm mọi chỗ dùng API và runtime

Một danh sách project GCP là chưa đủ. API/runtime có thể được dùng từ mã nguồn Java, Helm/Kustomize manifests, Terraform state, Cloud Build runner, VM startup script, cron/batch job, SDK container hoặc SaaS integration. Inventory nên mô tả ở cả cấp resource và **client thực tế đang gọi**.

| Field | Ví dụ dữ liệu giả định | Lý do lưu |
|---|---|---|
| Workload/owner | `orders-api` / Commerce | Có người chịu trách nhiệm nâng cấp |
| Environment/project | `prod` / `commerce-prod` | Biết blast radius, IAM và change window |
| Product + resource | GKE `orders-cluster`; Cloud SQL `orders-pg` | Truy ngược phiên bản thực |
| Version/channel | Kubernetes `1.xx`, Release Channel `Regular` | Lập lịch support và upgrade |
| Runtime/toolchain | Java 17, Spring Boot release line, Docker base image digest | Theo dõi EOL cộng đồng và CVE |
| API dependency | `apps/v1`, Google API method, REST `v1` | Kiểm tra deprecated path và compatibility |
| Client libraries | `com.google.cloud:google-cloud-storage` + version | Sửa dependency trong build |
| Exposure confidence | Observed / declared / inferred | Tránh coi “không thấy” là “không dùng” |
| EOL date/source | URL lifecycle + ngày đối chiếu | Theo dõi thay đổi mốc |
| Risk/SLO | High / checkout SLO | Ưu tiên remediation |
| Target version/action | Java 21, K8s API stable... | Đầu ra có thể triển khai |

### Ví dụ inventory CSV (tự định nghĩa)

~~~csv
workload,project,component,observed_version,channel,owner,deadline,status,source
orders-api,commerce-prod,java-runtime,17,,commerce-team,2027-06-01,assessment,cloud-run-runtime-docs
orders-api,commerce-prod,gke-cluster,1.xx,regular,platform-team,TO_VERIFY,discovered,gke-versioning
orders-db,commerce-prod,postgresql,13,,dba-team,2027-01-15,upgrade-planned,cloud-sql-db-versions
~~~

`TO_VERIFY` là giá trị cố ý chưa xác thực, không phải ngày chính thức. Hai ngày ở ví dụ là **deadline nội bộ giả định**, không phải mốc EOL của Google Cloud. Luôn lưu `official_notice_date` và `internal_deadline` trong các trường khác nhau; đừng gộp hai mốc.

### Lệnh kiểm kê mang tính read-only

~~~bash
# Xem project thực tế trước khi thao tác.
gcloud config get-value project

# GKE: cluster version, location, channel (tùy field API hỗ trợ).
gcloud container clusters list \
  --project=PROJECT_ID \
  --format="table(name,location,currentMasterVersion,releaseChannel.channel)"

# Cloud SQL: databaseVersion, tier, region.
gcloud sql instances list --project=PROJECT_ID \
  --format="table(name,region,databaseVersion,settings.tier)"

# Cloud Run: liệt kê services; cần tiếp tục truy Docker image/runtime của từng revision.
gcloud run services list --project=PROJECT_ID --region=REGION

# Các API đã enable không chứng minh có hay không có request sử dụng:
gcloud services list --enabled --project=PROJECT_ID
~~~

Các lệnh cho thấy resource metadata, **không tự phát hiện** tất cả libraries và API callers. Cần so sánh với Git repositories, image SBOM, Maven dependency tree, Terraform lockfile, audit logs, network traces và vendor integrations. Chỉ đọc dữ liệu đúng quyền và không xuất secrets.

## 6. GKE: minor version support, API deprecations và tự động nâng cấp

Kubernetes minor version và Kubernetes API version là **hai thứ khác nhau**:

- Minor version (ví dụ `1.xx`) xác định phiên bản Kubernetes/GKE của control plane và nodes.
- API version (`apps/v1`, `networking.k8s.io/v1`...) xác định schema mà `kubectl`, controllers, Helm chart hoặc CI dùng khi tạo/cập nhật resources.
- Một deprecated Kubernetes API có thể vẫn được server chấp nhận trong một số minor versions nhưng sẽ **bị gỡ** ở bản sau. Resource đã tồn tại không có nghĩa manifest/automation cũ còn dùng được.

### Chu kỳ hỗ trợ theo release channel

Theo tài liệu GKE hiện hành, minor version có khoảng **14 tháng standard support** kể từ lúc vào Regular channel. Extended channel có thể cung cấp **tổng thời gian hỗ trợ lên tới khoảng 24 tháng**, trong đó giai đoạn sau standard tập trung vào security fixes và có thể có **phí bổ sung**. Lịch cụ thể phụ thuộc minor version, channel, vùng, các đợt rollout và cập nhật của Google; hãy xem **GKE release schedule** trước mỗi kỳ review.

| Loại cấu hình | Hành vi cần biết |
|---|---|
| Rapid/Regular/Stable | Tốc độ nhận phiên bản khác nhau; có cơ chế auto-upgrade theo lifecycle |
| Extended channel | Có thể kéo dài hỗ trợ minor version trong giới hạn và có chi phí; không giữ mãi một phiên bản |
| Maintenance window/exclusion | Giúp chọn thời điểm hoặc tạm hoãn theo phạm vi được hỗ trợ; không phải tắt auto-upgrade vĩnh viễn |
| Deprecated API insight | GKE có thể tạm dừng nâng lên minor version gây gỡ API khi phát hiện usage, nhưng không bảo đảm tránh mọi trường hợp |
| End of support | GKE có thể nâng cluster lên bản còn hỗ trợ bất chấp một số ràng buộc hoãn trước đó |

**Không lấy “auto-upgrade đang paused” làm bằng chứng workload an toàn.** Khi minor version không còn được hỗ trợ, bản vá bảo mật và hỗ trợ kỹ thuật bị hạn chế; GKE sẽ thực hiện nâng cấp để tránh duy trì bản không được hỗ trợ. Lịch rollout có thể thay đổi; mọi maintenance exclusion phải có ngày hết hạn, lý do, owner và phương án thay thế.

### Tìm client đang gọi Kubernetes API sắp bị xóa

GKE có **deprecation insights/recommendations** trong Recommender khi phát hiện cluster sử dụng API/feature sẽ không được hỗ trợ ở một minor version sắp tới. Insights có thể kèm dấu vết clients. Một số API chỉ được dùng bởi job chạy theo quý hoặc disaster-recovery script nên **không xuất hiện trong cửa sổ quan sát gần đây**. Tài liệu GKE lưu ý khoảng 30 ngày không thấy deprecated usage có thể dẫn đến việc tiếp tục auto-upgrade; không thể suy ra toàn bộ tổ chức đã sạch API.

Ngoài console, có thể tra Cloud Logging:

~~~text
resource.type="k8s_cluster"
labels."k8s.io/removed-release"="1.XX"
protoPayload.authenticationInfo.principalEmail:("system:serviceaccount" OR "@")
protoPayload.authenticationInfo.principalEmail!~("system:serviceaccount:kube-system:")
~~~

Thay `1.XX` bằng minor version Kubernetes mà API bị remove; xem hướng dẫn cụ thể theo version. GKE Admin Activity audit logs ghi các thao tác write liên quan đến deprecated APIs. Nếu cần quan sát **read calls**, có thể phải bật **Data Access audit logs** tương ứng, đồng thời đánh giá logging volume/chi phí và chính sách dữ liệu.

**Cách tìm hết usage:** kết hợp deprecation insights, các query audit, tìm `apiVersion:` trong Helm/Kustomize/GitOps, manifest Helm template render, CronJobs/Operators và test tạo/update ở staging. Nếu dùng admission webhooks hoặc CRDs, kiểm tra conversion webhook, `admissionReviewVersions` và controller compatibility theo version. Một YAML viết đúng schema mới nhưng controller cũ không hỗ trợ cũng có thể làm rollout hỏng.

### Quy trình nâng GKE không gây bất ngờ

1. Xem release schedule, current control plane/node versions, channel và maintenance window.
2. Dùng staging cluster cùng cấu hình quan trọng, kiểm tra compatibility của Ingress/Gateway, CSI, mesh, policy, CNI, metrics, node OS và các operators.
3. Tìm hết deprecated API usage theo logs và repository; thay manifest, chart, pipeline và client SDK trước khi nâng.
4. Kiểm tra version skew của `kubectl` và các dependencies; test `helm template`, schema validation, integration tests.
5. Nâng control plane/nodes theo quy trình GKE hỗ trợ; với Standard có thể dùng canary node pool và PodDisruptionBudget, với Autopilot cần theo phạm vi điều khiển phiên bản/timing được hỗ trợ.
6. Theo dõi Pod scheduling, readiness, rollouts, 5xx, request latency, cluster events, HPA và Cloud SQL connections.
7. Cập nhật baseline và đóng deprecation insight khi **đã hết usage thật**, không chỉ vì cluster vừa upgrade.

**Rollback Kubernetes minor version không phải thao tác có thể tùy ý dùng** như rollback Deployment. Tùy sản phẩm và giai đoạn nâng, downgrade control plane/node có thể không được hỗ trợ. Cần lập kế hoạch an toàn bằng staging, workload compatibility, node pool rollout và khả năng rollback ứng dụng/IaC, không hứa “gặp lỗi sẽ downgrade GKE”.

## 7. Cloud Run: runtime managed khác container tự build

Đối với **Cloud Run functions** và workload dùng **Google-managed runtime base image**, tài liệu Cloud Run runtime lifecycle quy định các giai đoạn **GA → Deprecated → Decommissioned**. Khi deprecated, một số hoạt động tạo/redeploy có thể còn được phép nhưng không được runtime support như GA. Sau mốc decommission, không thể tạo mới hoặc cập nhật workload dùng runtime đó, và bản đang chạy **có thể bị vô hiệu hóa**. Cloud Run công bố thông báo trước giai đoạn deprecated theo chính sách riêng.

**Phân biệt quan trọng:** nếu deploy **container image do nhóm bạn xây dựng trực tiếp lên Cloud Run**, policy “Google-managed runtime lifecycle” **không trực tiếp áp dụng cho runtime bên trong image đó**. Nhưng bạn vẫn chịu trách nhiệm OS/JDK/base image vulnerability, library EOL và khả năng rebuild. Không được hiểu điều này thành “container tự build có thể bỏ qua EOL”.

### Ví dụ lịch runtime Java cần tự kiểm tra

Tại thời điểm biên soạn bài (19/11/2026), trang runtime lifecycle của Cloud Run liệt kê ví dụ:

| Runtime Java quản lý | Tình trạng/mốc minh họa từ policy | Hành động |
|---|---|---|
| Java 11 (`java11`) | Deprecated từ 31/10/2024, decommission 31/10/2025 | Không lựa chọn cho deploy mới; lên Java LTS còn hỗ trợ |
| Java 17 (`java17`) | Mốc deprecated dự kiến tháng 10/2027 | Lập kế hoạch nâng phiên bản, xác nhận mốc mới nhất trước khi change |
| Java 21 (`java21`) | Trong giai đoạn hỗ trợ tại thời điểm bài viết; lịch xa hơn theo bảng runtime | Chuẩn hóa Java 21 LTS nếu dependency cho phép và tiếp tục theo dõi |
| Java 25 (`java25`) | Có trong bảng runtime; hỗ trợ theo cấu hình tương ứng | Chọn khi libraries/framework tương thích, không nâng chỉ vì bản mới nhất |

Những mốc này **có thể được điều chỉnh**. Trước mỗi release/upgrade, kiểm tra bảng trực tiếp ở trang Cloud Run runtime lifecycle. Runtime ID trong bảng là dành cho workload dùng managed runtime; **không phải một flag bắt buộc** khi deploy container tự build bằng `gcloud run deploy --image=...`.

### Checklist khi đổi Java runtime

- Kiểm tra Spring Boot/Spring Framework, Jakarta namespace, PostgreSQL JDBC, gRPC, Netty và thư viện mã hóa đang hỗ trợ JDK mục tiêu.
- Kiểm tra `--release` hoặc compiler target, container JVM flags, TLS defaults, truststore, timezone/locale, CA certificates và base OS.
- Build/test trên đúng runtime và image sẽ được đưa lên GCP; không chỉ chạy test bằng JDK của developer.
- Bật health checks và canary traffic, quan sát startup time, CPU, memory, GC, thread, p99 latency và error budget.
- Gắn image digest, SBOM, build provenance và giữ revision cũ **nếu runtime còn cho phép rollback**.
- Với runtime đã decommission, việc tạo lại revision cũ có thể không được phép; xây dựng phương án migrate trước deadline thay vì trông chờ redeploy.

## 8. Cloud SQL: major version, extended support và chi phí trì hoãn

Cloud SQL for PostgreSQL/MySQL có chính sách **regular support**, **extended support** và **deprecation** theo major version. Sau khi phiên bản cộng đồng hết vòng đời, Cloud SQL có thể cung cấp extended support trong **ba năm** nhưng phát sinh **phí bổ sung** cho những database versions liên quan; sau deprecation, một phiên bản có thể bị nâng tự động lên default được dịch vụ công bố. Cloud SQL gửi thông báo tới project owners theo chính sách sản phẩm, nhưng tổ chức vẫn phải duy trì owner/Essential Contacts và theo dõi trang version policy.

Ví dụ theo bảng Cloud SQL for PostgreSQL công bố tại thời điểm bài học:

| PostgreSQL major | Extended support bắt đầu | Ngày deprecation công bố | Ý nghĩa |
|---|---|---|---|
| 13 | 01/02/2026 | 01/02/2029 | Đang thuộc giai đoạn mở rộng, cần kế hoạch nâng major |
| 14 | 01/02/2027 | 01/02/2030 | Hạn standard gần, tránh tạo phụ thuộc mới vào bản này |
| 15 | 01/02/2028 | 01/02/2031 | Vẫn cần kiểm tra extensions/driver và lịch dự kiến |

**Không áp ngày PostgreSQL cho MySQL hoặc SQL Server**. Theo dõi trang engine/version chính thức. Ngày trong bảng có thể thay đổi, và Cloud SQL major deprecation khác lịch minor maintenance: các bản vá **minor** có thể được áp dụng trong maintenance window, còn nâng **major** thường đòi đánh giá tương thích nhiều hơn.

### Thứ tự nâng cấp PostgreSQL production

1. Inventory instance versions, flags, extensions, JDBC driver, schema, read replicas, HA, backup/PITR và workload transactions.
2. Kiểm tra target major được Cloud SQL hỗ trợ, migration prerequisites, extension compatibility và các giới hạn về replica/HA.
3. Khôi phục bản backup vào staging, chạy test migration schema, query correctness, indexes, collations, timezone và performance under load.
4. Chọn chiến lược nâng **in-place** hoặc **migration sang instance mới**, xác định downtime, replication/switchover, DNS/connection string và khả năng rollback.
5. Dừng/điều phối writes theo runbook, tạo checkpoint và đo replication lag, chạy nâng, smoke tests, sau đó mở lại writes.
6. Theo dõi DB CPU/memory, connections, lock contention, slow queries, p95/p99 latency và logic ứng dụng.
7. Chỉ đóng ticket sau khi backup/restore, rollback constraints và integrity được xác nhận, cập nhật database version trong CMDB.

**Không luôn có rollback bằng downgrade major version**. Việc nâng DB có thể thay format dữ liệu, extension và behavior; phương án quay lại thường là khôi phục backup hoặc sử dụng instance cũ còn đồng bộ theo thiết kế, cần xử lý giao dịch phát sinh sau cutover. Đừng cam kết “rollback 5 phút” nếu chưa diễn tập data recovery.

## 9. API versioning và Google Cloud client libraries

Khi API được nâng từ `v1beta1` sang `v1`, hoặc một trường/endpoint bị deprecated, rủi ro không chỉ nằm ở deployment server: client và automation có thể dùng endpoint cũ qua Java SDK, gcloud CLI, Terraform provider, third-party integrations hoặc generated API client.

Phân biệt ba loại thay đổi:

1. **API surface:** method/resource/version/field bị gỡ hoặc đổi quyền bắt buộc.
2. **Behavior/schema:** field mới, enum value mới, default mới, pagination, error code, rate limit hoặc retry semantics thay đổi.
3. **Toolchain/client:** client library major upgrade, Java minimum version, gRPC/protobuf, auth libraries hoặc build plugins thay đổi.

Google Cloud client libraries có version theo artifact; **không đồng nhất** version của Maven package với API service `v1` hay với `gcloud` CLI. Một library cập nhật không đồng nghĩa backend API sẽ thay đổi ngay, và cập nhật API không nhất thiết buộc tăng major library. Phải đọc release notes/changelog riêng.

### Kiểm kê Java dependencies và công cụ

~~~bash
# Chạy trong repository Java của bạn, không chạy trên production.
./mvnw -B dependency:tree

# Với Gradle, nếu project dùng Gradle:
./gradlew dependencies --configuration runtimeClasspath

# Xem SDK/CLI dùng trong CI runner.
gcloud version
kubectl version --client
terraform version
~~~

Đối với Spring Boot, kiểm tra **BOM** quản lý version của `google-cloud-*`, Spring Cloud GCP, JDBC driver, HTTP clients và protobuf. Đừng override từng transitive dependency tùy tiện nếu BOM đã kiểm soát tương thích; ghi lại lý do khi phải override vì CVE và thử nghiệm hồi quy đầy đủ. Sử dụng dependency scanning/SBOM, renovate/dependabot hoặc công cụ tương đương để nhận biết bản cũ; công cụ chỉ tạo PR, nhóm owner vẫn phải đánh giá breaking changes.

### Tương thích hợp đồng API

Đối với API công khai hoặc do nhiều dịch vụ dùng chung:

- Ưu tiên **additive changes**: thêm optional field, giữ semantics của field cũ trong giai đoạn chuyển tiếp.
- Không tự đổi kiểu field, xóa enum value hay bỏ endpoint mà chưa có deprecation window phù hợp.
- Client phải chấp nhận unknown fields/enum values theo khả năng của serialization library; test trường hợp response mở rộng.
- Dùng `consumer-driven contract tests`, OpenAPI/protobuf compatibility checks và end-to-end smoke tests trên staging.
- Nâng server/API và client theo kế hoạch **expand → migrate → contract**; chỉ bỏ field cũ khi chứng minh không còn consumer.
- Với IAM, kiểm tra permission mới trên principal được cấp quyền tối thiểu; lỗi 403 sau upgrade không nhất thiết là service outage.

Nếu API cũ bị decommission, rollback client về bản cũ có thể **không cứu được** vì server không còn phục vụ endpoint. Cần có kế hoạch migration hoàn tất trước ngày gỡ, không lệ thuộc vào rollback sang runtime/API đã bị xóa.

## 10. Thiết kế một change calendar chung cho nhiều sản phẩm

Mỗi thông báo nên được chuyển thành một mục trong **change calendar** có người xử lý, deadline nội bộ và bằng chứng. Không nên đặt duy nhất một lịch “upgrade mỗi quý” rồi bỏ qua các mốc gấp của sản phẩm; cũng không nên đẩy mọi email release note lên kênh paging on-call.

### Phân tầng ưu tiên

| Mức | Dấu hiệu | Thời gian xử lý nội bộ |
|---|---|---|
| P0 — khẩn cấp | Breaking change đã xảy ra gây outage, security risk nghiêm trọng hoặc chức năng mất | Kích hoạt incident response ngay |
| P1 — hạn cận kề | Shutdown/forced upgrade sắp diễn ra, critical workload vẫn còn phụ thuộc | Owner lập kế hoạch ưu tiên, theo dõi hằng ngày |
| P2 — có thời gian chuẩn bị | EOL/deprecation đã có ngày, ảnh hưởng production nhưng đủ thời gian test | Đưa vào sprint/release train và review hằng tuần |
| P3 — theo dõi | Product change chưa rõ tác động hoặc chỉ ở dev | Xác minh inventory, lưu nguồn và review định kỳ |

Đây là **ma trận nội bộ minh họa**, không phải mức severity do Google Cloud công bố. Một notice chỉ tác động sandbox có thể thấp hơn notice ảnh hưởng checkout/payment production; mức độ cần dựa trên dữ liệu bị ảnh hưởng, yêu cầu compliance, SLO, đường rollback và thời gian còn lại.

### Mốc quản trị gợi ý

Với một deprecation có ngày decommission `D` được công bố:

| Giai đoạn gợi ý | Kết quả phải có |
|---|---|
| Ngay sau phát hiện | Ticket, source URL, owner, impacted resources và severity |
| Trước D khoảng 90 ngày nếu đủ thời gian | Target version/architecture decision, design review và test plan |
| Trước D khoảng 60 ngày | Tests ở staging, migration script, compatibility matrix, security review |
| Trước D khoảng 30 ngày | Production rollout/canary, rollback rehearsal và giám sát sau triển khai |
| Trước D khoảng 14 ngày | Đóng toàn bộ usage, kiểm tra backup automation/DR tooling |
| Trước D và sau rollout | Kiểm tra không còn dependency, cập nhật inventory và sign-off |

Khoảng ngày là **mục tiêu đề xuất**, không phải deadline của Google Cloud. Nếu notice chỉ đến khi còn 21 ngày, phải rút ngắn hoặc kích hoạt risk acceptance có chữ ký phù hợp; tuyệt đối không tự cho rằng Google sẽ gia hạn.

### Mẫu lịch ở dạng YAML làm việc (không phải Google API)

~~~yaml
change_id: CHG-2026-014
source_url: https://docs.cloud.google.com/kubernetes-engine/versioning
product: GKE
change_type: kubernetes-minor-upgrade
discovered_at: 2026-11-19
official_effective_at: TO_CONFIRM
internal_deadline: 2027-01-20
affected:
  - project: ecommerce-prod
    workload: orders-api
    resource: orders-gke
    owner: platform-team
impact:
  criticality: high
  possible_breakages:
    - deprecated-api-manifest
    - ingress-controller-compatibility
verification:
  - static-manifest-scan
  - staging-cluster-contract-tests
  - production-canary
rollback:
  - application-rollout-undo
  - restore-previous-compatible-manifests
status: assessment
~~~

`official_effective_at: TO_CONFIRM` nhấn mạnh ngày chính thức cần tra trực tiếp từ GKE release schedule. Ngày `internal_deadline` chỉ minh họa và phải do người quản trị change quyết định. Không ghi token, credential hoặc dữ liệu khách hàng vào ticket.

## 11. Phát hiện tự động nhưng phải có bước xác minh của con người

Có thể xây một quy trình nhận release notes/changelog từ nguồn chính thức và tạo ticket. Google Cloud cung cấp **product release notes**, các trang release notes riêng, feed/RSS tùy sản phẩm và cách tiếp cận release notes qua BigQuery theo tài liệu. Việc polling HTML bằng crawler tự chế dễ gãy khi trang thay bố cục; ưu tiên feed, API hoặc dữ liệu công bố chính thức, đồng thời kiểm tra bản quyền/điều kiện truy cập nếu tích hợp ngoài tổ chức.

Ví dụ luồng hệ thống:

~~~mermaid
flowchart LR
  RSS[Release notes / RSS / BigQuery] --> PIPE[Collector theo lịch]
  EMAIL[Essential Contacts mailbox] --> TRIAGE[Triage / parser email]
  PIPE --> NORMALIZE[Chuẩn hóa URL, ngày, product, type]
  TRIAGE --> NORMALIZE
  NORMALIZE --> DEDUP[Khử trùng thông báo]
  DEDUP --> MATCH[Match CMDB / inventory]
  MATCH --> TICKET[Ticket owner + deadline + priority]
  TICKET --> REVIEW[Human review / phê duyệt]
  REVIEW --> CHANGE[Staging, canary và sign-off]
~~~

**Collector và parser chỉ là thiết kế gợi ý**; chúng không tự có sẵn hoặc tự hoạt động khi đọc bài này. Cần thiết lập quyền truy cập mailbox/BigQuery, budget, log retention và kiểm soát gửi thông báo. Lọc các notice liên quan tới products/projects thực dùng; không tự động thực thi upgrade hoặc xóa resource chỉ vì thấy từ khóa “deprecation”.

### Khử trùng và cập nhật notice

Một notice có thể được cập nhật nhiều lần, đổi tên sản phẩm hoặc dời thời hạn. Khóa khử trùng nên dùng product + official URL + feature/API identifier; lưu revision history, `first_seen`, `last_seen`, `source_updated_at` và timestamp hệ thống quan sát. Nếu ngày ngừng hỗ trợ thay đổi, cập nhật **ticket gốc** và phát notification cho owner; không tạo 5 ticket khác nhau cho một thay đổi.

Đặt lịch kiểm tra độ tin cậy:

- Hằng ngày: triage Product Updates/Technical/Security quan trọng, urgent notices và product-specific deadline.
- Hằng tuần: review tickets chưa có owner, ảnh hưởng production, thay đổi lịch, blocked migration.
- Hằng tháng: audit inventory không được cập nhật, upcoming EOL 90/180 ngày và rủi ro quá hạn.
- Sau mỗi release: cập nhật runtime, image digest, API usage và evidence; quét lại CI/DR jobs ít chạy.

**Bẫy thường gặp:** một group email có 20 người nhưng không ai chịu trách nhiệm chuyển thư thành ticket. Tạo quy tắc route tới nhóm platform/SRE, SLA phản hồi, người trực thay thế và quy trình escalation tới technical owner.

## 12. Kiểm thử tương thích trước triển khai

Một thay đổi runtime hoặc API có thể gây tác động gián tiếp: CPU/memory/G1 GC khác, JVM TLS truststore mới, serialization error, điều kiện IAM chặt hơn, query planner PostgreSQL khác, webhook sai version hoặc CRD không tương thích Kubernetes control plane.

### Bốn tầng test

| Tầng | Cần kiểm tra | Bằng chứng |
|---|---|---|
| Static/inventory | Dependency tree, SBOM, IaC manifests, API versions bị deprecated | CI report, tìm kiếm usages và scan output |
| Unit/contract | Schema/API tương thích, validation, enum/field mới, serialization/deserialization | Unit tests, Pact/OpenAPI/protobuf contract tests |
| Integration | Auth/IAM, DB driver, transaction, Pub/Sub retry, secrets, network/TLS | Staging tests dưới target runtime/service version |
| Operational/nonfunctional | Latency p95/p99, CPU/memory, GC, scale, failover, rollback, RTO/RPO | Load tests, canary metrics, game-day evidence |

**Không chỉ thử đường thành công.** Thử API response có unknown field, `null`, enum chưa biết, timeout, HTTP 429/403, schema migration từng bước, chạy cùng lúc phiên bản app cũ/mới và hành vi reconnect sau DB maintenance. Nếu dùng idempotency, thử retry sau mất phản hồi.

### Expand–migrate–contract

Ví dụ muốn đổi cột `customer_name` thành `customer_display_name`:

1. **Expand:** thêm cột mới hoặc view tương thích, triển khai code có thể đọc cả hai.
2. **Migrate:** backfill dữ liệu, update writers/readers từng service, đo số lần field cũ được đọc/ghi.
3. **Contract:** chỉ xóa cột cũ sau khi mọi consumers, batch và DR scripts đã ngừng sử dụng.

Làm tương tự với REST endpoint, Pub/Sub event schema và Kubernetes API manifests. Việc xóa ngay field cũ trong một release là rủi ro lớn khi các client được deploy ở nhiều project/region với nhịp nâng cấp khác nhau.

## 13. Progressive delivery, verification và rollback

Khi đã xử lý tương thích, triển khai theo từng bước:

1. Ghim image/base image/tool version hoặc digest để có build tái lập và dễ so sánh.
2. Deploy bản mới vào sandbox/staging; tạo baseline request latency, error rate, memory, database connections.
3. Chạy smoke/contract/integration tests, scan quyền và cấu hình.
4. Canary theo tỉ lệ nhỏ hoặc chuyển một nhóm workloads/node pool trước; theo dõi SLO và security signals.
5. Promote theo checkpoint nếu error budget không bị tiêu thụ bất thường; có người phụ trách stop/go.
6. Đóng rollout sau khi xác nhận mọi client paths còn hoạt động; cập nhật inventory, tài liệu và ticket.

### Phân biệt thứ có thể rollback

| Thay đổi | Khả năng rollback | Phương án khi không thể quay lại trực tiếp |
|---|---|---|
| Spring Boot Deployment image | Thường có thể rollout undo về image tương thích | Giữ image digest, config và schema backward-compatible |
| Cloud Run revision | Chuyển traffic về revision cũ khi revision/runtime còn dùng được | Build lại runtime mới, không phụ thuộc runtime đã decommission |
| GKE minor/control plane | Downgrade không phải phương án mặc định được hỗ trợ | Thử staging, canary node pool, tương thích manifest trước nâng |
| Cloud SQL major version | Downgrade trực tiếp có thể không khả dụng | Backup/restore hoặc migration sang instance khác, reconcile writes |
| API removal phía nhà cung cấp | Client cũ không thể “khôi phục” endpoint đã xóa | Hoàn tất API migration trước deadline |
| Terraform provider/module | Có thể pin version cũ nhưng không bảo đảm compatible state/resource | Plan/state backup, review provider notes, nâng tuần tự |

**Rollback phải là thao tác đã thử**, không chỉ một dòng trong change ticket. Đối với dữ liệu, nếu bản mới đã ghi dữ liệu không đọc được bởi schema/code cũ, rollback application có thể làm tình trạng nặng hơn. Với sự cố liên vùng, đưa hệ thống về read-only/degraded mode an toàn có thể tốt hơn “quay về bằng mọi giá”.

## 14. Runbook tiếp nhận thông báo và xử lý nguy cơ quá hạn

### Bước A — Khi có notice

1. Kiểm tra tính xác thực: URL chính thức, thông báo qua console/email đúng domain, không mở link đáng ngờ.
2. Đọc nội dung đầy đủ: product, location, support phase, old/new APIs, ảnh hưởng tới create/update/run, ngày bắt đầu và ngày ngừng cuối.
3. Tạo ticket/record, lưu bản trích thông tin tối thiểu và link nguồn; phân công owner.
4. Đối chiếu inventory: projects, service accounts, client libraries, Terraform/CI/Helm, runtime images, batch/DR scripts.
5. Phân loại mức rủi ro; nếu không đủ dữ liệu, ghi rõ `unknown` và deadline kiểm tra.

### Bước B — Lập kế hoạch

6. Xác định target GA/supported version và tài liệu migration chính thức.
7. Đánh giá tương thích của ứng dụng, IAM, network, database và data consistency.
8. Lập test plan, rollout windows, canary cohort, go/no-go criteria và rollback constraints.
9. Phê duyệt change và truyền thông tới owners/on-call/khách hàng nếu SLA đòi hỏi.

### Bước C — Triển khai

10. Chạy staging, integration/load/security tests và rehearsal.
11. Deploy theo từng phase, xem error rates, latency, backlog, DB health, cluster events và logs.
12. Khi vi phạm ngưỡng, dừng promotion, rollback phần **có thể rollback**; nếu không thể, kích hoạt incident runbook.
13. Xác nhận không còn usage cũ bằng audit, inventory, repository scan, metrics và test các job hiếm chạy.

### Bước D — Đóng vòng

14. Ghi change result, resource versions, time window, SLO impact, incident link nếu có.
15. Đóng ticket chỉ khi hết exposure hoặc risk acceptance có chữ ký và thời hạn rõ ràng.
16. Review nguyên nhân nếu notice bị bỏ qua, cập nhật alert/owner/CI guardrails và lịch tiếp theo.

### Nếu đã quá hạn hoặc production đang sử dụng phiên bản không hỗ trợ

Không vội xóa resource hoặc nâng thẳng production nếu chưa có plan. Xác minh cấp độ khẩn cấp và khả năng sản phẩm còn chạy; giới hạn thêm thay đổi mới; lập mitigation tạm như network isolation, giảm exposure, tăng logging nếu phù hợp; liên hệ vendor/Google Cloud Customer Care theo quyền support để xác minh supported path. Có thể cần emergency change với rollback giới hạn và DR plan. Một waiver chỉ chấp nhận rủi ro **có thời hạn**, không biến phiên bản unsupported trở thành có hỗ trợ.

## 15. Tình huống thực tế: Spring Boot trên GKE, Cloud SQL và Cloud Run

**Giả định hệ thống:** một công ty vận hành `orders-api` bằng Java/Spring Boot trên GKE, `billing-worker` là Cloud Run function dùng managed Java runtime, PostgreSQL trên Cloud SQL và một pipeline GitOps có Helm charts. Dữ liệu checkout có SLO cao. Nhóm vừa phát hiện ba notice:

1. GKE đang tiến gần cuối giai đoạn standard support của Kubernetes minor version hiện tại; một Helm chart cũ còn dùng Kubernetes API bị deprecated.
2. `billing-worker` đang dùng runtime Java cũ, không có integration tests sau khi nâng JDK.
3. Cloud SQL PostgreSQL 13 đã bước vào extended support từ 01/02/2026, gây rủi ro hỗ trợ và phí.

### Inventory rút gọn

| Resource/owner | Exposure | Rủi ro | Cách xử lý |
|---|---|---|---|
| GKE `orders-gke` / Platform | Minor version cần nâng; Helm chart/Operator còn API cũ | CI deploy thất bại hoặc controller hỏng sau upgrade | Tìm deprecation insights + audit logs + static chart scan; nâng chart/controller |
| Cloud Run function `billing-worker` / Billing | Managed Java runtime cũ | Không tạo/redeploy được sau decommission, thiếu patch | Nâng Java LTS được hỗ trợ, test framework/auth, deploy revision mới |
| Cloud SQL `orders-pg` / DBA | PostgreSQL 13 extended support | Phí, rủi ro đến deprecation; driver/extension không tương thích khi nâng | Backup/PITR + clone/staging upgrade, benchmark query, cutover có rollback |
| GitOps/CI / Developer Experience | `kubectl`/Helm/provider cũ | Tool không tương thích cluster mới | Pin + nâng theo compatibility matrix, scan repository |

**Quan trọng:** một thay đổi có thể kéo theo thay đổi khác. Nếu nâng Spring Boot cần JDK mới, đồng thời Cloud SQL major nâng driver, nhóm không nên tự động gom cả ba vào một cutover cuối tuần. Hãy chia thành các thay đổi nhỏ độc lập khi có thể, với mỗi change có SLO baseline và rollback riêng. Những thay đổi bắt buộc phối hợp phải có integration/DR test chung.

### Kế hoạch triển khai gợi ý

**Wave 0 — Inventory & rủi ro:** owner xác nhận phiên bản thực, ngày EOL từ link chính thức, tất cả clients, CI jobs/DR scripts, network identity và khối lượng dữ liệu.

**Wave 1 — Thử tương thích:** sửa Helm templates và controllers, nâng Java trong môi trường test, build Spring Boot với JDK mới, clone Cloud SQL để thử migration. Chạy API contract tests, database query correctness và load tests.

**Wave 2 — Nâng ứng dụng/automation:** deploy phiên bản client và manifests tương thích cả trước và sau upgrade, đợi confirmation từ logs về việc không còn API cũ.

**Wave 3 — Nâng control plane và DB theo change riêng:** đặt maintenance window, chuẩn bị on-call, backup/restore, metric gates; quan sát SLO và rollback hợp lệ.

**Wave 4 — Đóng risk:** evidence từ production về versions/API usage, kiểm tra các tài nguyên DR và workflow hiếm chạy, update CMDB/BOM và đóng ticket.

### Ví dụ tình huống sự cố trong lúc nâng

Sau khi đổi GKE minor version, `kubectl apply` của GitOps báo `no matches for kind` do chart còn API bị gỡ. **Không chạy `kubectl delete --all` để giải quyết nhanh.** Dừng sync tự động nếu đang phá resource, xác định chart/version và API version mới, render manifest tương thích, thử ở staging, rồi áp dụng change đã review. Kiểm tra running workloads và health metrics, đừng coi lỗi apply là bằng chứng mọi Pod đã ngừng chạy.

Nếu nâng Cloud SQL major có lỗi query planner khiến p99 latency vượt SLO, không mặc định “downgrade”. Tìm slow queries/index/extension, rollback application change nếu thực sự tương thích, hoặc áp dụng recovery/migration plan đã chuẩn bị. Với runtime đã decommission, cách xử lý là chuyển sang runtime được hỗ trợ; **không thể trông chờ gcloud cho deploy lại phiên bản đã bị rút khỏi dịch vụ**.

## 16. Báo cáo, cảnh báo và chỉ số điều hành

Change management không phải chỉ là compliance checklist; nó ảnh hưởng trực tiếp đến uptime, security và chi phí. Xây dashboard quản trị hỗ trợ vận hành:

| Chỉ số | Cách đọc | Hành động |
|---|---|---|
| Workloads có owner và runtime/version đã xác minh | Coverage inventory | Tìm owner cho tài nguyên orphan |
| Số ngày còn lại tới deadline | Exposure window | Escalate các notice gần hạn |
| Số deprecated APIs đang còn được gọi | Đo theo logs/insights | Sửa automation/clients còn dùng |
| Unsupported/EOL runtime count | Security/support risk | Đặt remediation và waiver expiry |
| Cloud SQL instances trong extended support | Chi phí và rủi ro nâng major | So sánh upgrade cost với phí duy trì |
| Success rate của upgrade/canary | Chất lượng thay đổi | Cải thiện test và rollout |
| Change failure rate, rollback frequency | Khả năng triển khai an toàn | Thu hẹp blast radius, thêm contract tests |
| MTTD/MTTR cho sự cố sau change | Năng lực phát hiện/khắc phục | Cập nhật alerts và runbook |
| Tuổi của Essential Contacts chưa kiểm tra | Rủi ro không nhận thông báo | Test mailbox và người trực thay thế |

Có thể đặt một **internal policy** như “mọi production workload phải có owner/version inventory và không có deprecation notice P1 chưa có plan trước 30 ngày”. Đây là quy định nội bộ đề xuất, không phải SLA hoặc yêu cầu bắt buộc của Google Cloud.

### Tách thông báo khỏi paging

- **Pager:** chỉ khi có gián đoạn đang xảy ra, security threat nghiêm trọng hoặc shutdown gây ảnh hưởng trước mắt.
- **Ticket + chat/email:** deprecation date, runtime EOL, policy change cần nghiên cứu và migration có kế hoạch.
- **Change calendar:** maintenance windows, rollout/phê duyệt, DR rehearsals.
- **Knowledge base:** links chính thức, lessons learned, migration patterns, known incompatibilities.

Không biến tất cả product release notes thành pager alert: alert fatigue sẽ khiến đội vận hành bỏ qua thông báo nguy hiểm thật.

## 17. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách phòng tránh |
|---|---|---|
| Chỉ thêm một email cá nhân vào Essential Contacts | Thông báo mất khi người đó nghỉ hoặc không trực | Group mailbox, backup owner, test delivery |
| Tưởng Personalized Service Health là feed EOL | Bỏ lỡ deadline API/runtime dù không có outage | Product release notes + lifecycle tracker riêng |
| Nhầm deprecation với decommission | Đến ngày deadline mới phát hiện deploy bị từ chối | Tách support phase và ngày stop-create/update/run |
| Tưởng GKE tự nâng mà không cần sửa manifest | Deprecated API bị gỡ, GitOps/CI không áp dụng được | Audit/API scan + staging upgrade |
| Chỉ dựa vào GKE insight không có cảnh báo | Không phát hiện batch/cron hiếm dùng API cũ | Scan IaC + logs đủ chu kỳ + owner sign-off |
| Dùng maintenance exclusion vô thời hạn | Cluster hết hỗ trợ và có thể bị forced upgrade | Có expiry và kế hoạch remediation |
| Nhầm Cloud Run managed runtime với custom image | Không nâng JDK/OS do team tự sở hữu | SBOM/base image scanning và rebuild policy |
| Cố nâng tất cả runtime/DB/GKE cùng lúc | Khó khoanh vùng lỗi, rollback phức tạp | Chia wave, test và checkpoint riêng |
| Không tính phí Cloud SQL extended support | Tăng chi phí và bỏ lỡ quyết định upgrade | Inventory engine lifecycle + FinOps review |
| Không test client API dưới response field/enum mới | Parser lỗi hoặc tính toán sai | Contract tests, forward compatibility |
| “Rollback” về API đã bị gỡ | Không thể khôi phục service | Hoàn tất migration trước removal, kiểm tra rollback feasibility |
| Chỉ đo trạng thái `Running` | Không thấy lỗi giao dịch, timeout hoặc dữ liệu sai | SLO, synthetic transactions, consistency tests |
| Không ghi source/last checked | Dùng ngày EOL lỗi thời | Link chính thức, timestamp và review định kỳ |

## 18. Bài tập thực hành

**Tình huống giả định:** một nhóm có GKE `app-cluster`, Cloud Run function Java 17, Cloud SQL PostgreSQL 13 và 10 repositories Spring Boot. Hãy thực hành trên môi trường đọc-only hoặc sandbox có quyền phù hợp, **không tự nâng/xóa production resources**.

1. **Tạo inventory:** danh sách 10 repositories, owner, JDK, Spring Boot, Docker base image, SDKs, Helm charts, GKE/Cloud SQL/Cloud Run versions.
2. **Kiểm tra nguồn:** tìm các trang lifecycle chính thức cho GKE, Cloud Run Java và Cloud SQL PostgreSQL; ghi thời điểm truy vấn, ngày support thực tế và liên kết.
3. **Khảo sát contact:** xác định contacts cho Product Updates/Technical/Security, ai nhận mailbox và quy trình tạo ticket. Chỉ xem metadata theo quyền.
4. **Tìm Kubernetes deprecated APIs:** chạy scan trong source/manifests và tham khảo deprecation insights; xác minh một CronJob chạy hiếm không bị bỏ sót.
5. **Lập impact matrix:** phân loại P1/P2/P3 cho mỗi notice theo SLO, time-to-EOL, security và dependency.
6. **Viết migration plan:** Java 17 → một Java LTS được hỗ trợ theo runtime và dependency thực tế; PostgreSQL 13 → target major được Cloud SQL hỗ trợ; nâng GKE release channel/minor phù hợp.
7. **Kiểm thử:** mô tả contract tests, database restore/performance test, staging cluster upgrade, canary và timeout/error handling.
8. **Lập rollback:** chỉ rõ thay đổi nào rollback được, thay đổi nào cần recovery path thay thế; có checkpoint và người phê duyệt.
9. **Thiết kế thông báo:** một workflow nhận RSS/email, chuẩn hóa metadata, tạo ticket và chống duplicate.
10. **Tạo bảng nghiệm thu:** chứng minh không còn deprecated API calls, runtime đã cập nhật, SLO không giảm và các tài liệu on-call/DR đã sửa.

### Mẫu bảng đánh giá kết quả

| Tiêu chí | Điểm |
|---|---:|
| Inventory đầy đủ, đúng owners/resources | 20 |
| Phân biệt support phases, ngày và nguồn chính thức | 15 |
| Impact/dependency analysis có bằng chứng | 15 |
| Test plan và security review | 20 |
| Canary/rollback/DR kế hoạch khả thi | 20 |
| Thông báo, audit, closure và FinOps | 10 |
| **Tổng** | **100** |

Hồ sơ nộp bài: inventory CSV/YAML **đã loại thông tin nhạy cảm**, ba link lifecycle với ngày kiểm tra, change ticket minh họa, contract test plan, rollout/rollback plan và dashboard chỉ số quản trị. Không cung cấp project credentials, service account keys hoặc email cá nhân nếu không được phép.

## 19. Checklist vận hành định kỳ

- [ ] Có danh mục tài sản gắn owner, môi trường, runtime, API version, client library, toolchain và source URL.
- [ ] Từng Product Updates/Technical/Security notice có mailbox nhóm, người trực thay thế, quy trình triage và ticket.
- [ ] Product release notes và lifecycle pages được review định kỳ; không dựa duy nhất vào service incident feeds.
- [ ] Có danh sách GKE cluster versions, release channels, maintenance window và end-of-support dates.
- [ ] Deprecated Kubernetes APIs được scan từ Git/Helm/GitOps, audit logs và Recommender; bao phủ cả workload hiếm.
- [ ] Có inventory Cloud Run managed runtimes và **riêng** các container images tự build với JDK/OS EOL.
- [ ] Có inventory Cloud SQL engine major versions, extended support, lịch maintenance, backup/PITR và chi phí.
- [ ] Maven/Gradle dependencies, SDKs, gcloud, `kubectl`, Terraform/providers có phiên bản và update process.
- [ ] Các notices có ngày hiệu lực chính thức, deadline nội bộ, owner, độ ưu tiên và đường escalation.
- [ ] Test plan chứa compatibility, contract tests, IAM, migration, performance, security và failure injection.
- [ ] Production rollout có canary/traffic gating và ngưỡng SLO rõ ràng.
- [ ] Rollback chỉ được hứa nếu thực sự khả thi; schema/major version/API removal có recovery riêng.
- [ ] Bản cập nhật đã được kiểm tra trên DR scripts, batch jobs, CronJobs và third-party callers.
- [ ] Change records có evidence, approver, version deployed, SLO impact và closing timestamp.
- [ ] Không có ngoại lệ EOL không owner/expiry; mỗi waiver có remediation plan và review.
- [ ] Dashboard phân biệt alert sự cố hiện tại với backlog notice/ngừng hỗ trợ.

## 20. Kết luận

**Quản lý thay đổi API, runtime và ngừng hỗ trợ là một vòng đời vận hành, không phải việc đọc release notes khi rảnh.** Google Cloud quản lý nền tảng và công bố chính sách của từng sản phẩm, nhưng nhóm ứng dụng vẫn phải biết mình đang dùng API/JDK/DB version nào, thông báo đi tới ai, tác động nằm ở đâu và có thể kiểm thử/rollout/khôi phục bằng cách nào. Essential Contacts, release notes, GKE deprecation insights, Cloud SQL/Cloud Run lifecycle pages và các nguồn telemetry bổ sung cho nhau, **không nguồn đơn lẻ nào thay được inventory và owner validation**. Khi mọi notice thành ticket có deadline, test plan, change gates và bằng chứng đóng, tổ chức giảm được rủi ro security, lỗi triển khai bất ngờ, downtime và phí extended support không cần thiết.

## Tài liệu tham khảo

- [Google Cloud — Services subject to the Deprecation Policy](https://cloud.google.com/terms/deprecation)
- [Google Cloud — All release notes](https://cloud.google.com/release-notes)
- [Google Cloud — Essential Contacts overview](https://docs.cloud.google.com/resource-manager/docs/managing-notification-contacts)
- [Google Cloud — Manage Essential Contacts](https://docs.cloud.google.com/resource-manager/docs/manage-essential-contacts)
- [Google Cloud — Notification preferences](https://docs.cloud.google.com/resource-manager/docs/managing-notifications)
- [Personalized Service Health — Overview](https://docs.cloud.google.com/service-health/docs/overview)
- [Personalized Service Health — Incident communication](https://docs.cloud.google.com/service-health/docs/incident-communication)
- [GKE — Versioning and support](https://docs.cloud.google.com/kubernetes-engine/versioning)
- [GKE — Release schedule](https://docs.cloud.google.com/kubernetes-engine/docs/release-schedule)
- [GKE — Feature and API deprecations](https://docs.cloud.google.com/kubernetes-engine/docs/deprecations)
- [GKE — View deprecation insights and recommendations](https://docs.cloud.google.com/kubernetes-engine/docs/deprecations/viewing-deprecation-insights-and-recommendations)
- [GKE — Kubernetes deprecated API migration guidance](https://docs.cloud.google.com/kubernetes-engine/docs/deprecations/apis-1-32)
- [Cloud Run — Runtime lifecycle](https://docs.cloud.google.com/run/docs/runtime-support)
- [Cloud Run — Java runtime](https://docs.cloud.google.com/run/docs/runtimes/java)
- [Cloud SQL — Database version policies](https://docs.cloud.google.com/sql/docs/db-versions)
- [Cloud SQL for PostgreSQL — Database versions](https://docs.cloud.google.com/sql/docs/postgres/db-versions)
- [Cloud SQL for PostgreSQL — Major version upgrade](https://docs.cloud.google.com/sql/docs/postgres/upgrade-major-db-version-inplace)
- [Google Cloud CLI — Release notes](https://cloud.google.com/sdk/docs/release-notes)
- [Spring Boot — Reference documentation](https://docs.spring.io/spring-boot/reference/)
- [Kubernetes — Deprecation policy](https://kubernetes.io/docs/reference/using-api/deprecation-policy/)
