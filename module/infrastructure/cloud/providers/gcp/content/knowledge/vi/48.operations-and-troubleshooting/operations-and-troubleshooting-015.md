# Bàn giao runbooks, kiểm kê và dọn tài nguyên sau thực hành

## 1. Vì sao kết thúc bài lab không đồng nghĩa hoàn tất vận hành?

Sau một buổi thực hành Google Cloud, ứng dụng Java/Spring Boot có thể đã chạy được trên Cloud Run hoặc GKE, VM Compute Engine có thể đã phục vụ thử nghiệm, một Eventarc trigger đã gửi sự kiện và Cloud Storage đã chứa dữ liệu mẫu. Tuy nhiên, người thực hiện vẫn còn những trách nhiệm quan trọng:

- **Bàn giao:** người tiếp nhận phải biết hệ thống làm gì, được triển khai thế nào, nơi theo dõi sức khỏe và cách xử lý sự cố.
- **Kiểm kê:** biết tài nguyên nào tồn tại, ở project/region nào, ai sở hữu, phụ thuộc vào ai, có dữ liệu gì và phát sinh chi phí gì.
- **Dọn dẹp:** chấm dứt những tài nguyên thử nghiệm không cần thiết, nhưng không xóa nhầm backup, dữ liệu cần giữ hoặc dependency đang được workload khác sử dụng.
- **Xác minh:** chứng minh dịch vụ được bàn giao vẫn vận hành được, hoặc tài nguyên đã được dọn thật và không còn chi phí/sự cố tồn đọng.

Trong module **CLOUD_PROVIDERS_GCP**, đây là công đoạn nối các kiến thức về tổ chức project, IAM, VPC, Compute Engine, GKE, Cloud Run, database, storage, CI/CD, reliability và quản lý chi phí. Một hệ thống được đánh giá tốt không chỉ bởi việc deploy thành công, mà còn bởi khả năng người khác tiếp quản hoặc hủy bỏ nó một cách an toàn.

Bài học có hai lối kết thúc rõ ràng:

1. **Bàn giao vận hành** cho ứng dụng còn được sử dụng: giữ các tài nguyên cần thiết, tài liệu và trách nhiệm.
2. **Đóng phòng lab**: bảo toàn bằng chứng cần giữ, thu hồi quyền, dọn các tài nguyên còn lại và kiểm tra hóa đơn.

Không trộn hai lối này trong cùng một lệnh tự động. Quyết định giữ/xóa phải được chủ hệ thống xác nhận trước.

## 2. Các đầu ra tối thiểu của một buổi bàn giao

| Đầu ra | Nội dung bắt buộc | Người kiểm tra |
|---|---|---|
| Resource inventory | Project ID, resource name/ID, type, location, owner, môi trường, state | Platform/FinOps |
| Architecture & dependency map | Entry point, dữ liệu, service calls, network, IAM, event flow | Tech lead/operations |
| Deployment guide | Code, image digest, CI/CD, IaC revision, config, rollback | Developer/DevOps |
| Operational runbook | Kiểm tra sức khỏe, alert, xử lý lỗi, escalation, restore | On-call/operations |
| Security & access handoff | Service accounts, IAM roles, secrets, KMS, audit | Security/IAM owner |
| Data & backup decision | Giữ, export, migrate, retention, xóa; RPO/RTO | Data owner |
| Cleanup plan | Tài nguyên mục tiêu, dependency order, rollback, approvals | Resource owner |
| Closure evidence | Logs, inventory trước/sau, test kết quả, cost check | Người bàn giao và người nhận |

**Một lời nhắn “đã xóa hết” không thay được biên bản kiểm kê.** Biên bản nên liên kết với ticket hoặc change request, mã commit IaC, bản build và danh sách tài nguyên cụ thể. Không lưu access token, service account key hoặc secret values trong tài liệu bàn giao.

### 2.1. Tiêu chí nghiệm thu

Bàn giao đạt khi người tiếp nhận có thể thực hiện các công việc sau **mà không phải hỏi lại tác giả**:

1. Xác định đúng project, environment và owner.
2. Tìm dashboard, logs và các cảnh báo quan trọng.
3. Deploy/rollback bằng quy trình được phê duyệt.
4. Chẩn đoán một lỗi auth, network hoặc resource quota thường gặp.
5. Xác định nơi lưu dữ liệu, backup và thời hạn giữ.
6. Biết cách dừng hoặc xóa đúng tài nguyên mà không phá hỏng phần được giữ.

Đối với lab đóng hoàn toàn, nghiệm thu đạt khi có bằng chứng tài nguyên cần xóa không còn, những tài nguyên giữ lại có owner/retention và chi phí còn lại được theo dõi.

## 3. Phân quyền bàn giao: owner, approver và người thực hiện

Trước khi thao tác, lập bảng trách nhiệm theo dạng RACI hoặc mô hình tương đương.

| Công việc | Responsible (thực hiện) | Accountable (chịu trách nhiệm) | Consulted/được tham vấn |
|---|---|---|---|
| Xác minh hiện trạng và alert | SRE/DevOps | Service owner | Developer |
| Xác nhận dữ liệu có thể xóa | Data owner | Business owner | Security/compliance |
| Chốt tài nguyên giữ hay xóa | Resource owner | Project owner | FinOps |
| Review plan Terraform destroy | Platform engineer | Infrastructure owner | Security |
| Thực hiện cleanup | Người có quyền tối thiểu được phê duyệt | Change approver | On-call |
| Xác minh cost/billing | FinOps hoặc project admin | Cost center owner | Platform |
| Lưu evidence và đóng ticket | Người bàn giao | Người nhận bàn giao | Các bên liên quan |

Cùng một service account không nên được cấp quyền tùy tiện để triển khai, xoay secret, hủy database và xóa project. Áp dụng **separation of duties** ở những thao tác không thể đảo ngược.

### 3.1. Phân loại trạng thái mỗi tài nguyên

Một resource phải được gắn một trong các trạng thái bàn giao:

- **KEEP:** còn phục vụ ứng dụng hoặc cần giữ theo retention.
- **DELETE:** chỉ dành cho lab và đã được phê duyệt xóa.
- **MIGRATE:** chuyển dữ liệu/cấu hình sang môi trường mới rồi mới xóa bản cũ.
- **UNKNOWN:** chưa xác định owner/phụ thuộc; **không xóa** cho đến khi làm rõ.
- **BLOCKED:** có retention lock, legal hold, dependency, IAM restriction hoặc sự cố cần giải quyết.

Không dùng sự vắng mặt của traffic vài giờ làm bằng chứng rằng tài nguyên chắc chắn không còn được sử dụng. Một scheduled job chạy mỗi tháng hoặc backup restore path có thể không tạo traffic hằng ngày.

## 4. Mẫu manifest bàn giao tài nguyên

Manifest có thể được lưu trong hệ thống quản lý công việc hoặc dưới dạng file YAML được version-control. Ví dụ mô tả **mẫu đầu ra của người học**, không phải yêu cầu tạo file mới trong STEP 4:

~~~yaml
handoff:
  ticket: "LAB-2026-042"
  project_id: "demo-gcp-sandbox"
  environment: "lab"
  owner: "platform-team"
  decision: "CLEANUP_APPROVED"
  approver: "project-owner"
  approved_at_utc: "2026-11-19T09:00:00Z"
  artifacts:
    git_commit: "COMMIT_SHA"
    image_digest: "sha256:IMAGE_DIGEST"
    terraform_revision: "GIT_REVISION"
  evidence:
    inventory_before: "REFERENCE_TO_INVENTORY"
    architecture: "REFERENCE_TO_DIAGRAM"
    restore_check: "REFERENCE_TO_TEST"
    inventory_after: "PENDING"
resources:
  - type: "run.googleapis.com/Service"
    name: "projects/demo-gcp-sandbox/locations/asia-southeast1/services/lab-api"
    owner: "application-team"
    action: "DELETE"
    depends_on: ["artifact-repository"]
  - type: "storage.googleapis.com/Bucket"
    name: "lab-image-output-unique"
    owner: "data-team"
    action: "KEEP"
    reason: "Bằng chứng kiểm thử được lưu 14 ngày"
    expires_at_utc: "2026-12-03T00:00:00Z"
~~~

**Điểm quan trọng:** `expires_at_utc` trong manifest hoặc một label tự đặt không tự làm Google Cloud xóa resource. Muốn tự động cleanup cần lifecycle rule, TTL/policy hoặc scheduler/automation được quản lý riêng, có kiểm tra quyền và phạm vi.

Một manifest tốt ghi rõ **lý do** KEEP/DELETE, người duyệt, phương án khôi phục và liên kết bằng chứng. Không ghi password, service account key, private token hoặc chuỗi kết nối chứa credential.

## 5. Một runbook vận hành tốt cần những mục nào?

Một runbook là thủ tục có thể thực hiện trong tình huống thực tế, không chỉ là bản mô tả kiến trúc.

### 5.1. Cấu trúc gợi ý

| Mục | Nội dung |
|---|---|
| Tiêu đề và phiên bản | Tên tình huống, owner, ngày cập nhật, commit |
| Phạm vi | Project, region, service, môi trường và điều kiện áp dụng |
| Trigger | Alert, lỗi người dùng, deployment failure hoặc yêu cầu cleanup |
| Preconditions | IAM, quyền phê duyệt, maintenance window, backup |
| Blast radius | Dịch vụ/dữ liệu nào có thể bị ảnh hưởng |
| Diagnostics | Lệnh chỉ đọc, dashboard, logs, trace ID |
| Action | Các bước thao tác nhỏ, có checkpoint |
| Verification | Tín hiệu chứng minh đã thành công |
| Rollback/failback | Cách trở lại trạng thái an toàn và hạn chế |
| Escalation | Liên hệ on-call, dữ liệu nào phải đính kèm |
| Evidence | Ticket, log query, output đã lọc thông tin nhạy cảm |
| Closure | Thời gian, kết quả, bài học và việc cần cải tiến |

Lệnh nguy hiểm phải nằm sau một checkpoint rõ ràng. Ví dụ, trước khi xóa Cloud SQL, runbook phải xác minh instance, bản backup cuối, các replicas, deletion protection, consumer và người phê duyệt. Không đưa lệnh `--quiet` nhằm bỏ qua toàn bộ xác nhận trong một script học tập.

### 5.2. Ba loại runbook nên tách biệt

- **Operate:** kiểm tra deployment, logs, metrics, scale và health.
- **Recover:** rollback, restore, failover hoặc sửa lỗi IAM/network.
- **Decommission:** chặn traffic/scheduler, bảo toàn dữ liệu, xóa dependency và kiểm tra chi phí.

Trộn xử lý sự cố với xóa tài nguyên có thể tạo sự cố thứ hai. Một runbook `503 Cloud Run` không nên có bước “xóa toàn bộ project nếu vẫn lỗi”.

## 6. Runbook mẫu: kiểm tra sức khỏe ứng dụng Java trên Cloud Run

Giả sử `orders-api` chạy trong region `asia-southeast1`. Đầu tiên, xác minh environment và thông số đang chọn:

~~~bash
export PROJECT_ID="YOUR_LAB_PROJECT_ID"
export REGION="asia-southeast1"
export SERVICE="orders-api"

gcloud auth list
gcloud config get-value project
gcloud projects describe "$PROJECT_ID" \
  --format="value(projectId,lifecycleState)"
~~~

Không chỉ dựa vào default project của `gcloud`: nhiều lệnh có thể chạy trên project khác nếu account chuyển context. Lệnh nào cũng nên có `--project` cụ thể.

### 6.1. Tìm deployment và bản revision

~~~bash
gcloud run services describe "$SERVICE" \
  --project="$PROJECT_ID" \
  --region="$REGION"

gcloud run revisions list \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --service="$SERVICE"
~~~

Ghi lại revision đang nhận traffic, container image digest, service account, ingress và environment variables **không nhạy cảm**. Không in toàn bộ cấu hình secret vào ticket nếu chứa dữ liệu bí mật.

### 6.2. Xem logs và alert

~~~bash
gcloud run services logs read "$SERVICE" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --limit=100

gcloud logging read \
  'resource.type="cloud_run_revision" AND severity>=ERROR' \
  --project="$PROJECT_ID" \
  --limit=50
~~~

Lọc thêm theo service name và thời gian thực tế trước khi kết luận. `severity>=ERROR` có thể bao gồm lỗi của service khác nếu không bổ sung điều kiện.

### 6.3. Chẩn đoán và xác minh

Một ma trận ngắn:

| Triệu chứng | Kiểm tra đầu tiên | Hướng giải quyết |
|---|---|---|
| 401/403 | ID token, audience, `roles/run.invoker`, ingress | Xác định authn/IAM/business authz |
| 404 sau deploy | URL, path, routing, version | Kiểm tra service/revision |
| 5xx | Logs, dependency health, exception | Rollback hoặc xử lý nguyên nhân |
| Timeout | Cloud Run concurrency, CPU/memory, DB pool | Deadline/retry tuning |
| Không truy cập được DB | Cloud SQL connector, VPC, IAM, firewall | Kiểm tra network và identity |
| Cost tăng đột ngột | Instances/concurrency, retries, log volume | Giảm tải và kiểm tra nguồn chi phí |

Nếu không thể khôi phục trong RTO, kích hoạt escalation. Runbook phải ghi **điểm ra quyết định** giữa tự xử lý, rollback và khởi động quy trình incident.

## 7. Runbook mẫu: rollback và xác minh sau phát hành

Khi revision mới gây lỗi:

1. Xác định revision trước đó đã phục vụ ổn định và tương thích schema.
2. Xem traffic split hiện tại, SLO và phạm vi user bị ảnh hưởng.
3. Kiểm tra migration database có backward-compatible hay không.
4. Nhận approval theo severity/change policy.
5. Chuyển traffic về revision được chọn bằng quy trình deploy/rollback chính thức.
6. Theo dõi 5xx, p95/p99 latency và kết quả giao dịch trong cửa sổ kiểm tra.
7. Ghi sự cố, lý do rollback và hành động cải tiến.

Ví dụ lệnh **chỉ đọc**:

~~~bash
gcloud run services describe "$SERVICE" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --format="yaml(status.traffic)"

gcloud run revisions list \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --service="$SERVICE"
~~~

Một thao tác chuyển traffic là **write operation**, không thực hiện khi chưa xác minh target revision, sự tương thích database và approval. Một số tác vụ có side effects không được rollback chỉ bằng đổi revision; cần outbox, reconciliation hoặc runbook ứng dụng riêng.

## 8. Kiểm kê cấp project bằng Cloud Asset Inventory

Không nên kiểm kê chỉ bằng trí nhớ hoặc danh sách resource hiện trên một trang console. **Cloud Asset Inventory** cho phép tìm các resource được hỗ trợ trong phạm vi project, folder hoặc organization.

### 8.1. Đọc danh sách tổng quát

~~~bash
gcloud services list --enabled --project="$PROJECT_ID"

gcloud asset search-all-resources \
  --scope="projects/$PROJECT_ID" \
  --format="table(assetType.basename(),name,location,labels)"
~~~

Cần enable Cloud Asset Inventory API và có permission `cloudasset.assets.searchAllResources` trên scope. Không coi kết quả trống là “project không còn tài nguyên” nếu người dùng thiếu IAM, API chưa bật hoặc loại resource chưa được hỗ trợ trong Asset Inventory.

### 8.2. Tìm resource theo nhãn

Ví dụ tìm tài nguyên có nhãn liên quan đến bài lab:

~~~bash
gcloud asset search-all-resources \
  --scope="projects/$PROJECT_ID" \
  --query="labels:lab" \
  --format="table(assetType.basename(),name,location,labels)"
~~~

Search query cần được hiệu chỉnh theo nhãn và loại tài nguyên thật. Một resource không gắn label **không tự động là resource production**; và một resource gắn label lab **không tự động được phép xóa**.

Cloud Asset Inventory không bao phủ toàn bộ asset types, runtime metadata hoặc tài nguyên ở mọi dịch vụ. Hãy đối chiếu với API riêng và hóa đơn.

### 8.3. Trường cần lưu cho mỗi resource

Tối thiểu:

~~~text
project_id
resource_type
resource_full_name
region_or_zone
labels/tags
owner/team
created_at / last_modified_at
service_dependencies
data_classification
backup/retention
state: KEEP | DELETE | MIGRATE | UNKNOWN | BLOCKED
estimated_monthly_cost
approval_reference
~~~

Resource full name quan trọng hơn display name vì cùng một tên rút gọn có thể xuất hiện trong nhiều project và vùng.

## 9. Kiểm kê đối chiếu theo dịch vụ

Cloud Asset Inventory là điểm khởi đầu, không phải nguồn duy nhất. Dùng danh sách **chỉ đọc** theo dịch vụ có mặt trong bài lab.

### 9.1. Compute Engine, GKE và network

~~~bash
gcloud compute instances list --project="$PROJECT_ID"
gcloud compute disks list --project="$PROJECT_ID"
gcloud compute snapshots list --project="$PROJECT_ID"
gcloud compute addresses list --project="$PROJECT_ID"
gcloud compute forwarding-rules list --project="$PROJECT_ID"
gcloud compute reservations list --project="$PROJECT_ID"
gcloud container clusters list --project="$PROJECT_ID"
~~~

Chú ý **unattached persistent disks**, static external IP, reservations, snapshots, instance templates, managed instance groups, load balancers và firewall/network resources. Xóa VM có thể vẫn để lại disks, static addresses hoặc reservations tạo chi phí.

### 9.2. Cloud Run, event processing và Artifact Registry

~~~bash
gcloud run services list --project="$PROJECT_ID"
gcloud run jobs list --project="$PROJECT_ID"
gcloud eventarc triggers list \
  --project="$PROJECT_ID" --location="$REGION"
gcloud pubsub topics list --project="$PROJECT_ID"
gcloud pubsub subscriptions list --project="$PROJECT_ID"
gcloud artifacts repositories list \
  --project="$PROJECT_ID" --location="$REGION"
~~~

Cloud Run service có thể đã xóa nhưng Artifact Registry images còn, Eventarc triggers vẫn còn hoặc Pub/Sub resources/Cloud Tasks queues chưa được kiểm tra. Cloud Run jobs và scheduler jobs có thể khởi tạo workload lại sau khi service chính đã bị ngừng.

### 9.3. Storage, database và automation

~~~bash
gcloud storage buckets list --project="$PROJECT_ID"
gcloud sql instances list --project="$PROJECT_ID"
gcloud secrets list --project="$PROJECT_ID"

gcloud scheduler jobs list \
  --project="$PROJECT_ID" --location="$REGION"
gcloud tasks queues list \
  --project="$PROJECT_ID" --location="$REGION"
~~~

Filestore, BigQuery datasets, GKE persistent volumes, Memorystore, Spanner, Cloud DNS, VPN/Interconnect, Cloud KMS và log buckets cần được kiểm kê **nếu đã sử dụng**. Không chỉ nhìn vào một region; một số resources là global hoặc nằm ở location khác.

Một `gcloud list` bị từ chối quyền hoặc API chưa bật là **kết quả chưa đầy đủ**, không phải bằng chứng đã dọn xong.

## 10. Phân tích phụ thuộc trước khi dọn

Ví dụ ứng dụng upload ảnh từ một bài thực hành:

~~~mermaid
flowchart TB
    USER[Lab uploader] --> IN[(Input bucket)]
    IN --> TRIG[Eventarc trigger]
    TRIG --> RUN[Cloud Run image-worker]
    RUN --> IN
    RUN --> OUT[(Output bucket)]
    RUN --> SA[Runtime service account]
    TRIG --> TSA[Trigger service account]
    RUN --> IMG[Artifact Registry image]
    RUN --> SECRET[Secret Manager secret]
    RUN --> DB[(Optional Cloud SQL)]
    SA --> KMS[Optional KMS key]
    RUN --> LOG[Logs / metrics]
~~~

Phụ thuộc quan trọng: **trigger có thể tiếp tục gửi event khi Cloud Run đã xóa**. Các retries có thể gây lỗi và phát sinh vận hành hoặc chi phí. Vì thế cần dừng nguồn kích hoạt trước khi hủy receiver.

### 10.1. Thứ tự teardown thông dụng

1. Thông báo maintenance/đóng quyền upload hoặc traffic thử nghiệm.
2. Dừng scheduler, Eventarc trigger, Cloud Tasks producers và các nguồn tạo workload.
3. Chờ hoặc xử lý dứt điểm messages đang chờ theo yêu cầu dữ liệu.
4. Backup/export/di chuyển dữ liệu cần giữ.
5. Gỡ public routes, load balancer hoặc DNS sau khi bảo đảm không còn client hợp lệ.
6. Xóa workloads: Cloud Run service/job, GKE deployments/clusters, VM hoặc database theo phạm vi.
7. Xem và xóa **orphan resources**: disks, persistent volumes, reserved IPs, images, snapshots, queues, artifacts.
8. Gỡ IAM bindings, service accounts và secrets không còn dùng.
9. Dọn những tài nguyên chung **sau cùng** và chỉ khi chắc chắn không còn consumer.
10. Kiểm kê lại và theo dõi chi phí sau cleanup.

Đây là thứ tự tư duy; dependency thực tế có thể yêu cầu đổi một số bước. Không xóa VPC hoặc KMS key trước các tài nguyên vẫn phụ thuộc vào chúng.

## 11. Dữ liệu và retention: cổng chặn trước thao tác xóa

Trước khi xóa bucket, database, disk, image hoặc backup, chủ dữ liệu cần trả lời:

- Có thông tin thật/PII/secret hoặc dữ liệu được quản lý bởi policy không?
- Có legal hold, retention lock hoặc yêu cầu kiểm toán không?
- Có cần snapshot/export để rollback hoặc đối chiếu không?
- Bản backup đã được **thử khôi phục** hay mới chỉ tạo xong?
- Có cần giữ image digest, schema, log hoặc evidence để tái lập sự cố?
- Tài nguyên có bị consumer, CI/CD, scheduler hoặc project khác sử dụng không?
- Xóa được không? Nếu không, ai chịu trách nhiệm và khi nào hết hạn giữ?

### 11.1. Cloud Storage

Cloud Storage có soft delete, Object Versioning, retention và Bucket Lock. Xóa object/bucket có thể **không dừng chi phí ngay** nếu soft-deleted objects vẫn được giữ. Mặt khác, xóa nhầm bucket có thể làm mất dữ liệu và tên bucket có thể bị tái sử dụng khi đã được giải phóng.

Đối với bucket chứa dữ liệu lab:

1. Liệt kê objects/versions và dung lượng.
2. Kiểm tra soft delete, versioning, retention/holds và lifecycle rules.
3. Export/copy data cần giữ tới vị trí có owner.
4. Có xác nhận bằng văn bản từ data owner.
5. Chỉ khi đó thực hiện xóa theo quy trình của bucket cụ thể.
6. Xác minh trạng thái objects/bucket và phần dữ liệu còn bị giữ theo policy.

**Không chạy recursive delete** trên một bucket chỉ vì tên có chữ “test”.

### 11.2. Cloud SQL

Cloud SQL là stateful resource. Trước khi delete:

- Kiểm tra replicas, backups, deletion protection và connection consumers.
- Lập final backup/export theo khả năng engine và policy.
- Kiểm tra restore proof trước khi hủy.
- Đảm bảo không còn migration job, scheduler hoặc service đang dùng.
- Xác định retained backups, private endpoints, DNS và các resource mạng liên quan.

Việc xóa instance có thể làm mất dữ liệu/backup; một số Cloud SQL flows hỗ trợ final backup với retention riêng. Không nhầm “delete instance” với “archive database”.

### 11.3. KMS, secrets và chứng chỉ

Không hủy hoặc vô hiệu hóa key version đang dùng để mã hóa snapshot, database hoặc bucket cần giữ. **Hủy key material có thể khiến dữ liệu không thể giải mã.** Cloud KMS cho phép một số thao tác xóa resource theo điều kiện hiện hành, nhưng xóa key/key ring khác với phá hủy key material; phải xem đúng vòng đời sản phẩm và review phạm vi ảnh hưởng.

Với Secret Manager, xác minh secret không còn được application, trigger, CI hoặc rotated credential dùng. Thu hồi IAM/trust relations trước, rồi mới dọn secret khi retention/audit cho phép. Không sao chép secret payload vào bảng bàn giao.

## 12. Xem xét chi phí trước, trong và sau cleanup

### 12.1. Tài nguyên có thể tiếp tục tính phí dù ứng dụng ngừng chạy

| Loại resource | Rủi ro chi phí tồn đọng |
|---|---|
| Persistent disks/Hyperdisk | Disk còn tồn tại dù VM đã xóa |
| Static external IP | Reservation còn hoặc IP không được sử dụng theo pricing |
| Compute reservations / sole-tenant nodes | Vẫn tính phí khi VM bị hủy hoặc không chạy |
| Snapshots, machine images | Storage charges tiếp tục |
| Artifact Registry | Image/versions còn được lưu |
| Cloud SQL | Instance, storage, backup/retained backup hoặc network resource còn |
| Cloud Storage | Live, versioned và soft-deleted objects |
| GKE | Cluster/node, load balancer, persistent disks và external services |
| Cloud Logging | Log retention/sinks/storage theo cấu hình |
| KMS hoặc secret versions | Usage/storage/active versions theo sản phẩm |

Compute reservations và committed-use commitments là hai khái niệm khác nhau; **xóa VM không tự kết thúc cam kết chi tiêu**.

### 12.2. Billing reports và budgets

Trước cleanup, xem Cloud Billing Reports/Cost Table theo project, service, SKU, labels và thời gian. Sau cleanup, đối chiếu xu hướng chi phí vài chu kỳ báo cáo tiếp theo.

**Budgets dạng alerts-only không phải hard spending cap.** Chúng gửi cảnh báo khi đạt threshold nhưng không tự dừng resource. Một số dịch vụ hỗ trợ **spend cap budgets** theo điều kiện và phạm vi riêng; cần xác nhận tính khả dụng và ảnh hưởng tới workload trước khi dùng. Không khẳng định mọi budget đều là giới hạn cứng.

Dữ liệu usage/cost có độ trễ, có thể xuất hiện charges sau khi tài nguyên đã xóa. Do đó:

- Không coi hóa đơn ngay trong phút xóa là bằng chứng chi phí đã về 0.
- Dùng labels và cost attribution để phát hiện orphan resources.
- Xem resource costs, network egress, retained backups và commitments.
- Theo dõi sau khi đóng lab để phát hiện chi phí chưa được dọn.

## 13. Quy trình cleanup an toàn sáu cổng

### Cổng 1 — Identify

Xác định đúng project, organization, region, environment và người thực hiện.

~~~bash
gcloud auth list
gcloud config get-value project
gcloud projects describe "$PROJECT_ID" \
  --format="yaml(projectId,projectNumber,lifecycleState)"
~~~

Nếu project chứa resource dùng chung hoặc production, ngừng quy trình cleanup tổng thể và chỉ thao tác trên từng tài nguyên đã được phê duyệt.

### Cổng 2 — Inventory

Lưu danh sách resources, IAM, dependencies, location, data policies, expected monthly cost. Đối chiếu Asset Inventory với APIs riêng; đánh dấu `UNKNOWN` nếu thiếu owner.

### Cổng 3 — Protect

Export/backup dữ liệu cần giữ, xác minh khả năng khôi phục, xem retention và khóa bảo mật. Ghi lại version image, Terraform revision và migration state.

### Cổng 4 — Preview

Tạo kế hoạch nêu rõ từng resource được xóa, resource được giữ, thứ tự và hậu quả. Nếu dùng Terraform, chạy destroy plan; nếu dùng Artifact Registry cleanup policies, dùng dry run.

### Cổng 5 — Approve and Execute

Yêu cầu approval theo blast radius. Thực hiện thao tác từng nhóm nhỏ, log kết quả, dừng nếu phát hiện resource ngoài kế hoạch hoặc API báo lỗi.

### Cổng 6 — Verify and Close

Inventory lại, xác minh data retention, budget/cost, orphan resources, IAM bindings còn sót và evidence. Chỉ đánh dấu DONE khi người nhận bàn giao đã xác nhận.

~~~mermaid
flowchart TD
    A[Identify project + owner] --> B[Inventory + dependency map]
    B --> C{Data or resource UNKNOWN?}
    C -- Có --> D[Stop: clarify owner / retention]
    C -- Không --> E[Backup, export, restore proof]
    E --> F[Preview deletion plan]
    F --> G{Approval và scope đúng?}
    G -- Không --> H[Stop: no destructive action]
    G -- Có --> I[Disable triggers / execute small batches]
    I --> J[Re-inventory + test + billing follow-up]
    J --> K{Orphans / failed checks?}
    K -- Có --> L[Investigate, reconcile, re-review]
    K -- Không --> M[Close handoff ticket]
~~~

**Một thao tác xóa thành công không có nghĩa cleanup tổng thể hoàn tất** nếu còn dangling dependencies hoặc dữ liệu chưa được di chuyển.

## 14. Ví dụ CLI: kế hoạch cleanup Cloud Run và Eventarc

Giả sử lab có Eventarc trigger `images-finalized` gọi Cloud Run service `image-worker`. Các tên dưới đây là placeholder, không phải tài nguyên của người học.

### 14.1. Preflight chỉ đọc

~~~bash
export PROJECT_ID="YOUR_LAB_PROJECT"
export REGION="asia-southeast1"
export TRIGGER="images-finalized"
export SERVICE="image-worker"

gcloud eventarc triggers describe "$TRIGGER" \
  --project="$PROJECT_ID" \
  --location="$REGION"

gcloud run services describe "$SERVICE" \
  --project="$PROJECT_ID" \
  --region="$REGION"

gcloud run revisions list \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --service="$SERVICE"
~~~

Xem liệu trigger có gửi event tới service dùng chung không, có backlog/retry nào đang cần xử lý và có data owner nào yêu cầu giữ output không.

### 14.2. Lệnh dọn sau approval

**Chỉ chạy khi ticket đã duyệt và các preconditions đạt:**

~~~bash
# 1) Stop event delivery before deleting the receiver.
gcloud eventarc triggers delete "$TRIGGER" \
  --project="$PROJECT_ID" \
  --location="$REGION"

# 2) Delete the Cloud Run service after confirming no consumer remains.
gcloud run services delete "$SERVICE" \
  --project="$PROJECT_ID" \
  --region="$REGION"
~~~

Xóa Cloud Run service **không tự xóa** container images ở Artifact Registry và **không tự xóa** Eventarc triggers. Khi xóa service, revisions của service đó được xóa, nhưng repository vẫn phải được xử lý riêng theo retention.

### 14.3. Verify

~~~bash
gcloud eventarc triggers list \
  --project="$PROJECT_ID" --location="$REGION"
gcloud run services list --project="$PROJECT_ID"
gcloud artifacts repositories list \
  --project="$PROJECT_ID" --location="$REGION"
~~~

Nếu còn repository, cần phân biệt image nào thuộc lab và image nào được dùng bởi service/job khác. Không xóa cả repository chỉ vì một Cloud Run service đã bị xóa.

## 15. Artifact Registry: dùng dry run và retention hợp lý

Artifact Registry giữ container images, tags, digests và versions. Những image này có thể tồn tại sau khi service đã xóa hoặc deploy image mới.

Một kế hoạch cleanup nên:

1. Inventory repositories và packages theo project/location.
2. Xác định image digests đang được Cloud Run/GKE/job/rollback sử dụng.
3. Xác định retention: giữ các bản release được yêu cầu.
4. Định nghĩa cleanup policy với **delete conditions** và **keep rules**.
5. Chạy **dry run**, xem audit/preview của candidate deletions.
6. Chỉ chuyển sang active delete sau approval và review tác động.

Ví dụ **minh họa preview** khi đã có policy file được review:

~~~bash
gcloud artifacts repositories set-cleanup-policies LAB_REPOSITORY \
  --project="$PROJECT_ID" \
  --location="$REGION" \
  --policy=REVIEWED_POLICY_FILE.json \
  --dry-run
~~~

Không có sẵn file JSON trong bài này; người học phải tạo và review policy riêng, không chạy lệnh với placeholder. Cleanup policies có thể chạy nền và cần thời gian để quan sát kết quả. Keep policy giúp giữ release artifacts dù matching một delete rule.

Đừng xóa image digest mà production/staging đang tham chiếu; một revision đang chạy có thể vẫn phục vụ nhưng lần scale/deploy lại có thể gặp vấn đề nếu image không còn khả dụng theo cơ chế của dịch vụ.

## 16. Compute Engine: VM, disks, static IP và reservations

### 16.1. Vì sao chỉ xóa VM là chưa đủ?

Một VM có thể gắn boot/data disks với chính sách auto-delete khác nhau, static external IP, persistent snapshots và reservations. Khi VM biến mất, một số resource vẫn tồn tại và có thể tiếp tục tính phí.

Trước khi hủy VM:

~~~bash
gcloud compute instances describe LAB_VM \
  --project="$PROJECT_ID" --zone=LAB_ZONE

gcloud compute disks list --project="$PROJECT_ID"
gcloud compute addresses list --project="$PROJECT_ID"
gcloud compute reservations list --project="$PROJECT_ID"
~~~

Trong instance description, kiểm tra `disks.autoDelete`, địa chỉ IP, metadata, service account, labels và managed instance group membership. Nếu VM thuộc MIG, phải quản lý qua MIG thay vì xóa instance thủ công rồi để autohealing tạo lại.

### 16.2. Chuỗi cleanup sau approval

1. Xác nhận data disk có thể xóa hoặc đã backup.
2. Xem VM có thuộc MIG/autoscaler hay không.
3. Dừng trigger/scheduler tạo lại VM.
4. Xóa VM theo đúng policy bảo toàn/xóa disks.
5. Liệt kê lại unattached disks, reservations, addresses, snapshots và load balancer.
6. Xóa từng resource còn lại **theo ID cụ thể và approval riêng**.
7. Kiểm tra costs và project inventory.

**Không sử dụng wildcard xóa toàn bộ disks hoặc snapshots**. Snapshot có thể là điểm khôi phục cần giữ dù source disk đã biến mất. Một số instant snapshots gắn với disk có lifecycle đặc thù; cần đọc policy trước khi xóa.

## 17. GKE: resource do cluster quản lý và resource còn sót

GKE tạo ra nhiều resource phụ thuộc: node pools/Compute instances, load balancers, external IPs, persistent volumes, disks, network endpoints, logging và identities.

Trước khi decommission cluster:

- Xuất Kubernetes manifests/Helm values hoặc GitOps revision cần giữ.
- Xem persistent volumes và reclaim policy; tìm storage dùng chung.
- Kiểm tra `Service type=LoadBalancer` và static IP.
- Xác nhận workload không dùng chung Cloud SQL, Pub/Sub hay bucket production.
- Xem node pools/autoscaling, cluster mode và network.
- Ghi nhận các backup đã được xác minh trước khi xóa.

Lệnh chỉ đọc:

~~~bash
gcloud container clusters list --project="$PROJECT_ID"

# Với kubeconfig/context được admin xác nhận:
kubectl config current-context
kubectl get namespaces
kubectl get services --all-namespaces
kubectl get pv
kubectl get pvc --all-namespaces
~~~

**Không xóa PVC/PV hoặc cluster trước khi kiểm tra reclaim policy và dữ liệu.** Một disk có thể vẫn tồn tại sau khi cluster bị xóa hoặc ngược lại bị xóa theo policy; cả hai trường hợp phải được dự liệu.

Sau khi xóa cluster có approval, đối chiếu lại GKE list, Compute disks, addresses, forwarding rules và storage resources. Nếu cluster dùng Shared VPC, không tự xóa network của host project.

## 18. Cloud SQL và dữ liệu có trạng thái

Cloud SQL thường là tài nguyên có rủi ro xóa cao nhất trong một lab vì chứa dữ liệu và có thể được nhiều dịch vụ sử dụng.

### 18.1. Checklist trước khi hủy

- [ ] Instance đúng project và region, owner đã xác nhận DELETE.
- [ ] Không còn application connections hoặc replication/backup consumers.
- [ ] Đã xem replicas và deletion protection.
- [ ] Đã export hoặc tạo final backup khi chính sách yêu cầu.
- [ ] Đã thử phục hồi dữ liệu mẫu hoặc xác minh backup có thể sử dụng.
- [ ] Đã xác định retained backups/retention TTL.
- [ ] Đã kiểm tra CMEK và service agent phục hồi.
- [ ] Đã xác định private endpoint, PSC, DNS và network resource cần dọn riêng.

Một số luồng xóa Cloud SQL hỗ trợ tạo **final backup** và giữ theo thời hạn, có thể còn phát sinh chi phí. Không khẳng định xóa instance luôn xóa mọi backup ngay lập tức; đọc chính sách cấu hình và tài liệu engine tương ứng.

### 18.2. Không thử xóa để biết hệ thống có cần hay không

Nếu không chắc một instance còn được sử dụng, dùng metrics, connection logs, service configuration và ý kiến owner để xác minh. Không vô hiệu hóa deletion protection hoặc xóa replicas chỉ để ép lệnh delete thành công.

## 19. Cloud Storage, Pub/Sub, Secret Manager và automation

### 19.1. Cloud Storage

~~~bash
gcloud storage buckets list --project="$PROJECT_ID"
gcloud storage ls "gs://LAB_BUCKET/"
gcloud storage buckets describe "gs://LAB_BUCKET"
~~~

Những lệnh này chỉ đọc. Khi cleanup:

- Xem live và noncurrent/soft-deleted objects, retention và holds.
- Export dữ liệu quan trọng.
- Review application đang dùng bucket và signed URLs.
- Xóa object/bucket theo phạm vi được duyệt, không dùng wildcard vô điều kiện.
- Kiểm tra chi phí soft-deleted storage và early deletion charges nếu áp dụng.

### 19.2. Pub/Sub và queues

Pub/Sub subscriptions có thể chứa message chưa được ack; Cloud Tasks queues có thể có tasks đang chờ. Trước khi xóa:

1. Dừng producers/trigger/scheduler.
2. Đối chiếu backlog và business transactions.
3. Quyết định xử lý hết, lưu hoặc hủy message theo data owner.
4. Chỉ sau đó xóa subscriptions/topics/queues liên quan.
5. Xác minh các event consumers khác không dùng chung topic.

Một topic dùng chung có thể còn consumers ở project khác. Không xác định ownership chỉ dựa trên project nơi topic được tạo.

### 19.3. Secret Manager, IAM và service accounts

Không xóa service account ngay khi workload bị dừng nếu còn backup restore process, workload khác hoặc audit requirement. Gỡ quyền theo thứ tự:

- Thu hồi IAM binding của workload đã dừng trên resource đích.
- Xác minh service account không còn được Cloud Run, GKE, Compute, Cloud Build hoặc trigger dùng.
- Xem key không còn sử dụng và chính sách rotation/revocation.
- Xóa service account theo phê duyệt; lưu evidence về IAM changes.
- Xem workload identity pools/provider hoặc workforce mappings còn phụ thuộc.

Secrets cần được xử lý theo retention/data policy. Không hiển thị secret value để “lưu bằng chứng” cleanup.

### 19.4. Scheduler, Eventarc và Cloud Tasks

Một job định kỳ có thể tạo lại resource vừa xóa, gọi một endpoint không còn hoặc làm phát sinh chi phí. Vì vậy hãy tìm và dừng producers trước khi xóa consumers. Ghi rõ các **cross-project** dependency để không bỏ sót.

## 20. Cleanup bằng Terraform và Infrastructure as Code

### 20.1. Không destroy tùy tiện cả workspace

Terraform giúp mô tả tài nguyên trong code, nhưng `terraform destroy` có thể xóa **mọi tài nguyên đang được quản lý trong state đang chọn**, không chỉ tài nguyên lab vừa tạo. Đừng chạy khi chưa kiểm tra backend, workspace, project vars và state content.

Một workflow an toàn:

~~~bash
terraform workspace show
terraform state list
terraform plan -destroy -out=destroy.tfplan
terraform show destroy.tfplan
~~~

Các lệnh trên là ví dụ cho người học trong **thư mục Terraform của lab đã được xác nhận**, không thực thi trong STEP 4. Bản plan nên được lưu trong workspace được kiểm soát; plan files có thể chứa thông tin nhạy cảm nên không đưa vào repository công khai.

Sau khi người có thẩm quyền đã review resource list và approve:

~~~bash
terraform apply destroy.tfplan
~~~

Không dùng `-auto-approve` trong lab có tài nguyên dữ liệu thật hoặc shared infrastructure. Nếu state có resource cần giữ, hãy thay đổi mô hình quản lý/migration theo quy trình thay vì xóa bừa.

### 20.2. Vấn đề state, drift và resource ngoài Terraform

Một số resources có thể được tạo bằng Console/CLI, Cloud Run source deploy, Kubernetes controller hoặc service agents; chúng có thể **không nằm trong Terraform state**. Vì vậy cần thêm Cloud Asset Inventory/API inventory sau destroy.

Nếu Terraform báo resource không xóa được vì phụ thuộc, dừng và kiểm tra nguyên nhân. Không xóa thủ công những resource khác ngoài plan chỉ để cưỡng ép apply thành công.

Với tài nguyên đã được import/shared, cần xem xét các thuộc tính bảo vệ như `prevent_destroy` và nguồn chân lý của state. State có thể chứa secrets; bảo vệ backend, quyền truy cập và audit.

## 21. Khi nào nên xóa cả project?

Trong một **sandbox project độc lập hoàn toàn**, sau khi kiểm kê và bảo toàn dữ liệu, shutdown project có thể đơn giản hơn việc dọn hàng trăm tài nguyên. Nhưng cần hiểu hậu quả:

- Project shutdown làm project không sử dụng được và ngắt liên kết Cloud Billing.
- Có **thời hạn phục hồi thông thường 30 ngày** trước khi xóa vĩnh viễn.
- Một số resource như Cloud Storage hoặc Pub/Sub có thể bị xóa sớm hơn, không được bảo đảm có thể khôi phục dù restore project trong 30 ngày.
- Project ID không thể tái sử dụng sau khi xóa hoàn toàn.
- Project có thể tiếp tục tính trong quota đến khi xóa hẳn; charges liên quan đến chu kỳ sử dụng có thể được ghi nhận muộn.
- Khi restore project, liên kết Billing không tự động được khôi phục.

**Chỉ shutdown project khi project owner xác nhận không có workload, billing, data hoặc IAM/shared infrastructure còn cần giữ.** Không dùng project deletion để dọn một vài resource trong project dùng chung.

Lệnh mô tả trạng thái (chỉ đọc):

~~~bash
gcloud projects describe "$PROJECT_ID" \
  --format="yaml(projectId,lifecycleState,parent)"
~~~

Lệnh xóa project có tính phá hủy và chỉ thuộc runbook riêng có approval/impact assessment; bài này không đưa nó vào script cleanup mặc định.

## 22. Kiểm kê lại sau khi dọn

Sau khi thực thi, lặp lại **cùng các truy vấn inventory** như trước cleanup và so sánh:

~~~bash
gcloud asset search-all-resources \
  --scope="projects/$PROJECT_ID" \
  --format="table(assetType.basename(),name,location,labels)"

gcloud compute disks list --project="$PROJECT_ID"
gcloud compute addresses list --project="$PROJECT_ID"
gcloud run services list --project="$PROJECT_ID"
gcloud sql instances list --project="$PROJECT_ID"
gcloud storage buckets list --project="$PROJECT_ID"
~~~

Ngoài ra:

1. Kiểm tra Eventarc, Scheduler, Pub/Sub và Cloud Tasks không còn trigger tới endpoint đã xóa.
2. Kiểm tra Artifact Registry, snapshots, static IP, reservations và backups.
3. Kiểm tra IAM bindings/service accounts không còn quyền thừa.
4. Kiểm tra retention: giữ lại đúng dữ liệu đã được phê duyệt và có owner.
5. Kiểm tra error logs sau cleanup, đặc biệt 404/403 tăng đột ngột.
6. Theo dõi Billing Reports khi usage data cập nhật để xác minh xu hướng chi phí.
7. Đóng ticket kèm before/after inventory, result và những ngoại lệ còn mở.

### 22.1. Mẫu báo cáo cleanup

~~~text
TICKET: LAB-2026-042
PROJECT: demo-gcp-sandbox
OPERATOR: platform-engineer
APPROVER: project-owner
APPROVED SCOPE: Eventarc trigger + Cloud Run lab service
START / END: [UTC timestamps]

PRECONDITIONS:
- Data owner approval: PASS
- Backup/export if required: PASS
- Dependency review: PASS
- Terraform state review: N/A

ACTIONS:
- Trigger images-finalized: DELETED
- Cloud Run image-worker: DELETED
- Artifact Registry repository: KEPT (shared with another lab)
- Input/output buckets: KEPT until retention expiry

VALIDATION:
- Post-cleanup inventory: PASS
- Error logs: PASS
- Cost check: PENDING (usage data delay)
- IAM review: PASS
- Residual risks: retained storage costs

FOLLOW-UP OWNER: FinOps / Data owner
FOLLOW-UP DATE: YYYY-MM-DD
~~~

Đây là một **mẫu**; không nên ghi “cost = 0” ngay nếu retained storage và billing lag chưa được đối chiếu.

## 23. Case study: bàn giao và dọn hệ thống Java trên GCP

Một nhóm đã triển khai ứng dụng thực hành gồm:

- Cloud Run `orders-api` dùng Java/Spring Boot.
- Eventarc trigger phát sự kiện từ input Cloud Storage bucket.
- Một Pub/Sub topic để gửi thông báo.
- Cloud SQL instance giữ đơn hàng mẫu.
- Artifact Registry chứa images.
- Secret Manager chứa API key thử nghiệm.
- Một Compute Engine VM làm bastion/worker tạm.
- Terraform quản lý một số resource; những resource khác được tạo bằng `gcloud`.

### 23.1. Giai đoạn A — bàn giao vận hành

Nhóm xác định `orders-api` vẫn cần dùng trong 14 ngày để demo. Họ phải:

1. Ghi architecture diagram, URL không nhạy cảm, runtime service account và dependency map.
2. Lưu runbook xem Cloud Run logs và kiểm tra 401/403, 5xx, Cloud SQL connectivity.
3. Ghi rõ mỗi service dùng project/region nào và ai phê duyệt IAM.
4. Chốt SLA nội bộ, cách rollback và dữ liệu nào được giữ.
5. Đặt ngày hết hạn demo trong ticket và người chịu trách nhiệm.
6. Giữ những backup/retention points cần thiết; không xóa khi demo còn cần.

### 23.2. Giai đoạn B — chuẩn bị cleanup

Sau 14 ngày, project owner chấp thuận đóng lab, nhưng data owner yêu cầu giữ một export không chứa PII để đánh giá.

Nhóm tiến hành:

1. Xác minh export đã được kiểm tra, có checksum và chính sách retention.
2. Tắt source upload/scheduler và Eventarc trigger.
3. Chờ xử lý/giải quyết Pub/Sub backlog hợp lệ.
4. Kiểm tra Cloud Run/Cloud SQL không còn consumer.
5. Đối chiếu Terraform plan với resource thực.
6. Xóa ứng dụng, VM, Cloud SQL và resources liên quan theo approval.
7. Giữ export và evidence đúng thời hạn, gỡ IAM không còn cần.
8. Inventory lại để phát hiện static IP, disk, image, snapshot hoặc topic còn sót.
9. Theo dõi hóa đơn trong những ngày sau, không kết luận tức thì.

### 23.3. Phát hiện sự cố khi đối chiếu

Sau cleanup, inventory phát hiện:

- Một persistent disk bị detached nhưng còn tính phí.
- Một Artifact Registry repository còn images của lab.
- Một static IP vẫn reserved.
- Eventarc trigger đã xóa nhưng Pub/Sub topic `orders-events` còn consumer của nhóm khác.
- Một retained Cloud SQL backup còn thời hạn giữ.

**Quyết định đúng:** không xóa topic dùng chung và không phá backup trái retention. Tạo follow-up cho disk/IP/artifacts thật sự thuộc lab, gắn owner cho backup và xem chi phí còn lại. Cleanup **không phải thành công tuyệt đối** nếu bỏ qua các ngoại lệ; nó thành công khi mọi tài nguyên đều được quyết định minh bạch và có người chịu trách nhiệm.

## 24. Các lỗi và anti-pattern thường gặp

| Anti-pattern | Hậu quả | Cách cải thiện |
|---|---|---|
| Chỉ gửi link console khi bàn giao | Người nhận không biết runbook hoặc owner | Tài liệu, inventory và evidence có version |
| Tin mọi resource có label lab đều được xóa | Xóa nhầm shared resource | Approval theo resource full name |
| Tin Asset Inventory liệt kê 100% resources | Bỏ sót loại chưa hỗ trợ hoặc thiếu quyền | Đối chiếu với APIs riêng và billing |
| Xóa Cloud Run nhưng bỏ trigger | Retry lỗi, noise/chi phí | Dừng event source trước |
| Xóa VM mà không kiểm tra disk/IP | Phát sinh phí tồn đọng | Re-inventory Compute resources |
| Xóa bucket không xem soft delete | Chi phí còn và mất dữ liệu/không đúng retention | Data review, bucket policy inspection |
| Xóa Cloud SQL để “xem còn cần không” | Mất database | Owner, backup/export, connectivity review |
| Chạy Terraform destroy với workspace nhầm | Xóa nhầm nhiều môi trường | Workspace/state/plan/approval |
| Dùng `--quiet` để bỏ qua cảnh báo | Mất checkpoint con người | Phê duyệt từng scope |
| Xóa KMS version trước backup | Không giải mã được dữ liệu | Kiểm tra key dependency và policy |
| Coi budget email là hard cap | Vượt ngân sách | Phân biệt alerts-only và spend cap hỗ trợ |
| Chỉ đo Billing ngay sau delete | Kết luận sai do billing lag | Follow-up nhiều kỳ dữ liệu |
| Không thu hồi IAM và service account | Dư thừa quyền lâu dài | Access review/least privilege |
| Xóa project dùng chung để dọn lab | Mất resource của nhóm khác | Cleanup scoped resources |
| Chạy cleanup lặp mà không idempotent | Script fail/đụng resource mới | Reconcile state, kiểm tra precondition và stop-on-drift |

## 25. Checklist tổng hợp cho người học

### A. Bàn giao hệ thống đang vận hành

- [ ] Architecture diagram và data-flow đã được cập nhật.
- [ ] Project, region, resource full names và owners rõ ràng.
- [ ] Image digest, Git commit, IaC revision và deployment pipeline được ghi lại.
- [ ] IAM, service accounts, secrets, KMS và network dependencies được kiểm tra.
- [ ] Dashboard/alerts, SLI/SLO và runbooks chẩn đoán/rollback có thể dùng.
- [ ] Data owner đã xác nhận backup/retention và RPO/RTO.
- [ ] Người nhận đã thực hiện thử một thao tác kiểm tra và xác nhận tiếp quản.

### B. Kiểm kê và lập kế hoạch xóa

- [ ] Cloud Asset Inventory đã chạy, có đối chiếu API các dịch vụ.
- [ ] Có danh sách Compute disks/IP/reservations/snapshots.
- [ ] Có danh sách GKE nodes/PVs/load balancers nếu đã dùng.
- [ ] Có Cloud Run/Eventarc/Pub/Sub/Scheduler/Tasks inventory.
- [ ] Có Cloud SQL, Storage, Secret Manager, Artifact Registry inventory.
- [ ] Không còn resource `UNKNOWN` trong kế hoạch xóa.
- [ ] Owner/approver đã duyệt scope và đánh giá blast radius.
- [ ] Dữ liệu cần giữ đã export/backup và kiểm chứng.

### C. Thực thi và xác minh

- [ ] Đã dừng producers/triggers trước consumers khi phù hợp.
- [ ] Terraform plan đã được review nếu dùng IaC.
- [ ] Các thao tác nguy hiểm không dùng wildcard/`--quiet` bừa bãi.
- [ ] Post-cleanup inventory đã hoàn thành.
- [ ] IAM bindings và service accounts dư thừa đã được xử lý.
- [ ] Retained data/backup có owner và ngày rà soát.
- [ ] Logs không có lỗi mới do resource đã xóa.
- [ ] Billing follow-up đã được lên lịch theo độ trễ usage data.
- [ ] Đã lưu ticket, evidence và các khoản chi phí còn lại.

## 26. Bài tập thực hành

### Bài tập 1 — Viết runbook

Một Spring Boot service chạy trên Cloud Run trả HTTP 503. Hãy viết runbook gồm trigger, danh tính người kiểm tra, ba bước chẩn đoán chỉ đọc, điều kiện rollback, kiểm chứng và escalation. Nêu cách phân biệt lỗi Cloud Run runtime với lỗi Cloud SQL hoặc service dependency.

### Bài tập 2 — Lập inventory

Trong một sandbox project, lập bảng gồm ít nhất: Cloud Run, Artifact Registry, bucket, Pub/Sub, VM, disk, static IP, IAM service account và Cloud SQL nếu có. Với mỗi dòng ghi full name, owner, location, action KEEP/DELETE/UNKNOWN và chi phí dự kiến. So sánh Cloud Asset Inventory với lệnh list theo dịch vụ.

### Bài tập 3 — Review kế hoạch cleanup

Một bạn đề xuất:

~~~text
1. Delete Cloud Run service.
2. Delete project immediately.
3. Later decide which Cloud Storage object to keep.
~~~

Hãy chỉ ra ít nhất năm rủi ro và sửa kế hoạch để có data owner approval, export, stop triggers, dependency review, post-validation và billing follow-up.

### Bài tập 4 — Terraform destroy plan

Trong môi trường lab đã được cho phép, xác định đúng workspace/state và xem `terraform plan -destroy`. Phân loại resource không nằm trong state, resource shared, resource có dữ liệu và resource cần giữ. **Không thực thi apply** nếu chưa có approval.

### Bài tập 5 — Biên bản nghiệm thu

Viết báo cáo cuối gồm những resource đã xóa, resource còn giữ, chi phí tồn đọng, cảnh báo còn mở, thời gian follow-up và người nhận chịu trách nhiệm. Không được ghi “PASS” cho cost verification khi billing report chưa cập nhật.

## 27. Câu hỏi tự kiểm tra

1. Vì sao deploy thành công không có nghĩa hệ thống đã sẵn sàng bàn giao?
2. Một runbook khác kiến trúc overview ở điểm nào?
3. Khi nào tài nguyên mang label `lab` vẫn không được xóa?
4. Cloud Asset Inventory có thể bỏ sót resource vì những lý do nào?
5. Vì sao cần kiểm kê disk và static IP sau khi xóa VM?
6. Vì sao xóa Cloud Run không đồng nghĩa xóa Eventarc trigger và image?
7. Những yếu tố nào phải kiểm tra trước khi hủy Cloud SQL?
8. Khi nào phải giữ retained backup dù muốn giảm chi phí?
9. Tại sao soft-deleted Cloud Storage objects có thể tiếp tục tính phí?
10. Vì sao alerts-only budget không phải hard spending cap?
11. Vì sao Terraform destroy cần xác nhận workspace và state trước?
12. Một event subscription còn backlog gây rủi ro gì khi xóa consumer?
13. Cloud KMS key version bị hủy ảnh hưởng backup mã hóa thế nào?
14. Khi nào nên chọn shutdown cả project và khi nào không?
15. Nếu inventory sau xóa không còn VM nhưng Billing vẫn tăng, bạn sẽ kiểm tra gì?
16. Những bằng chứng nào giúp xác nhận cleanup đạt và người nhận có thể tiếp quản?

## Tài liệu tham khảo

- [Cloud Asset Inventory: Search for resources](https://docs.cloud.google.com/asset-inventory/docs/search-resources)
- [Cloud Asset Inventory: searchAllResources API](https://docs.cloud.google.com/asset-inventory/docs/reference/rest/v1/TopLevel/searchAllResources)
- [Resource Manager: Delete and restore projects](https://docs.cloud.google.com/resource-manager/docs/delete-restore-projects)
- [Cloud Billing: Budgets and budget alerts](https://docs.cloud.google.com/billing/docs/how-to/budgets)
- [Cloud Billing: Spend cap budgets](https://docs.cloud.google.com/billing/docs/how-to/budgets-spend-caps)
- [Cloud Billing: Billing reports](https://docs.cloud.google.com/billing/docs/how-to/reports)
- [Compute Engine: Delete instances and preserve resources](https://docs.cloud.google.com/compute/docs/instances/deleting-instance)
- [Compute Engine: Persistent disks deletion](https://docs.cloud.google.com/compute/docs/reference/rest/v1/disks/delete)
- [Cloud Run: Manage and delete services](https://docs.cloud.google.com/run/docs/managing/services)
- [Eventarc Standard: Manage triggers](https://docs.cloud.google.com/eventarc/standard/docs/managing-triggers)
- [Artifact Registry: Configure cleanup policies](https://docs.cloud.google.com/artifact-registry/docs/repositories/cleanup-policy)
- [Cloud Storage: Delete buckets](https://docs.cloud.google.com/storage/docs/deleting-buckets)
- [Cloud Storage: Soft delete](https://docs.cloud.google.com/storage/docs/soft-delete)
- [Cloud SQL: Delete instances](https://docs.cloud.google.com/sql/docs/mysql/delete-instance)
- [Cloud KMS: Destroy and restore key versions](https://docs.cloud.google.com/kms/docs/destroy-restore)
- [Cloud KMS: Delete resources](https://docs.cloud.google.com/kms/docs/delete-kms-resources)
- [Terraform CLI: Destroy infrastructure](https://developer.hashicorp.com/terraform/cli/commands/destroy)
- [Google Cloud Well-Architected Framework: Operational excellence](https://docs.cloud.google.com/architecture/framework/operational-excellence)

