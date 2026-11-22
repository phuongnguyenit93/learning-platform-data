# Khởi tạo môi trường có thể tái tạo và thu hồi tài nguyên

## 1. Môi trường hạ tầng nên được tạo từ một định nghĩa có thể kiểm chứng

Một ứng dụng cloud không chỉ gồm mã nguồn. Để chạy được, nó cần network, subnet, route, identity, compute, database, cache, queue, object storage, policy bảo mật, DNS, logging và nhiều cấu hình phụ thuộc. Nếu mỗi lần tạo môi trường đều thực hiện thủ công qua console hoặc một danh sách thao tác không được quản lý, các môi trường dễ lệch nhau, khó tái tạo và khó biết tài nguyên nào có thể xóa.

**Infrastructure as Code (IaC)** mô tả hạ tầng bằng các tệp định nghĩa có thể quản lý như mã nguồn. Công cụ IaC so sánh trạng thái mong muốn (desired state) với trạng thái đã biết hoặc trạng thái thực tế, rồi lập kế hoạch tạo, sửa hoặc xóa tài nguyên để đưa môi trường về trạng thái mục tiêu.

Trong module **CLOUD_ARCHITECTURE**, thiết kế kiến trúc cloud đi từ yêu cầu nghiệp vụ đến lựa chọn mạng, compute, dữ liệu và mô hình triển khai; đồng thời cân bằng độ tin cậy, bảo mật, khả năng mở rộng, chi phí và vận hành theo Well-Architected. IaC kết nối bản thiết kế với quy trình triển khai có thể lặp lại, review, kiểm thử, audit và thu hồi.

Một môi trường có thể tái tạo không chỉ là “chạy lại lệnh deploy”. Nó cần xác định rõ phiên bản định nghĩa, đầu vào, state, secrets, dependency, quyền thực thi, dữ liệu cần phục hồi và những resource có lifecycle riêng. Một quy trình teardown an toàn cũng quan trọng như quy trình provisioning.

Sau bài này, bạn có thể:

- Giải thích desired state, declarative IaC, imperative automation và idempotency.
- Tổ chức module, environment configuration và versioning để tái tạo môi trường.
- Quản lý state, locking, drift, import và dependency giữa các resource.
- Tạo môi trường ephemeral cho pull request, integration test và preview deployment.
- Quản lý secrets, identity, immutable artifact và dữ liệu seed.
- Thiết kế pipeline validate, plan, approval, apply và post-deploy verification.
- Thu hồi tài nguyên an toàn, bảo vệ dữ liệu và resource cần giữ.
- Đưa quota, chi phí, audit và Well-Architected vào quy trình IaC.

## 2. Desired state và vòng đời môi trường

### 2.1. Desired state là gì?

Desired state mô tả kết quả mà hệ thống cần có, ví dụ:

- Một VPC/VNet với CIDR, subnet và route rõ ràng.
- Một workload identity chỉ được phép đọc secret cần thiết.
- Ba replica của Booking API với image version bất biến.
- Database private, mã hóa at rest, backup và retention theo policy.
- Queue, dead-letter queue và quyền publisher/consumer riêng.
- Log, metric, trace và alert được cấu hình.
- Autoscaling với min/max và resource budget.

Tool IaC đọc định nghĩa và xác định action cần thiết để đạt desired state. Nếu định nghĩa không đổi và provider trả trạng thái đúng, lần apply tiếp theo thường không cần thay đổi gì. Đây là lợi ích lớn của declarative configuration.

### 2.2. Imperative và declarative

| Cách tiếp cận | Mô tả | Điểm mạnh | Rủi ro/đánh đổi |
|---|---|---|---|
| Imperative script | Mô tả tuần tự các lệnh cần chạy | Linh hoạt với workflow hoặc tác vụ đặc biệt | Khó biết trạng thái hiện tại; rerun có thể tạo trùng hoặc sai |
| Declarative IaC | Mô tả trạng thái cuối cần đạt | Có plan/diff, hội tụ về desired state, dễ review | Cần quản lý state, provider semantics và thay đổi ngoài luồng |
| Configuration management | Cấu hình package, file, service trên host | Hữu ích cho OS/application configuration | Có thể cần phối hợp provisioning và lifecycle |
| Image-based provisioning | Đóng gói runtime/config nền thành image/version | Instance khởi tạo nhất quán, giảm drift | Image pipeline và patch lifecycle cần quản lý |

Thực tế có thể kết hợp: IaC tạo network/compute/database; image pipeline tạo artifact; configuration management hoặc cloud-init thực hiện bootstrap nhỏ; deployment controller chạy application release. Cần xác định một nguồn sự thật cho mỗi nhóm cấu hình.

### 2.3. Declarative không có nghĩa mọi thứ tự động an toàn

Một lệnh destroy có thể xóa database hoặc bucket nếu định nghĩa lifecycle cho phép. Một apply có thể thay resource quan trọng do đổi immutable property. State có thể mất hoặc bị ghi đè. Do đó cần plan review, policy guardrail, backup, approval và phân quyền riêng cho thao tác phá hủy.

## 3. Các khối xây dựng của IaC

### 3.1. Resource

Resource là thành phần hạ tầng cụ thể: network, subnet, firewall rule, VM, container cluster, database, bucket, queue, IAM role, DNS record hoặc monitoring alarm.

Mỗi resource cần:

- Tên và định danh ổn định.
- Owner, environment, service và purpose.
- Region/zone và network/security scope.
- Tag/label cho cost allocation và lifecycle.
- Input/output được khai báo rõ.
- Lifecycle policy, backup và deletion protection nếu cần.

### 3.2. Variable, output và configuration

Variable cho phép dùng cùng module với các environment khác nhau. Output công bố những giá trị cần cho module/workload khác như subnet ID, endpoint hoặc identity reference. Configuration giữ các giá trị environment-specific.

Không nên hardcode password, token, private key hay credential trong variable file được commit. Với secret, dùng secret manager và workload identity; chỉ truyền reference hoặc lấy secret ở runtime theo policy.

### 3.3. Module

Module đóng gói một nhóm resource thành interface có input/output. Ví dụ:

- network-baseline
- private-database
- container-platform
- service-identity
- object-storage-private
- observability-baseline

Module nên phản ánh capability hoặc pattern có lifecycle chung, có validation và documentation. Tránh tạo module quá nhỏ khiến người dùng phải nối hàng trăm interface; cũng tránh module khổng lồ có hàng chục cờ cấu hình khó hiểu.

### 3.4. Provider và version

Provider/plugin chuyển định nghĩa IaC thành API calls tới cloud hoặc nền tảng. Cần pin version trong phạm vi tương thích đã kiểm thử và commit dependency lock file nếu công cụ hỗ trợ.

Không dùng latest ngầm định trong pipeline production. Provider update có thể thay đổi schema, diff behavior, default hoặc resource lifecycle. Update nên là thay đổi có review, plan comparison và test.

## 4. Cấu trúc repository cho nhiều môi trường

Một cấu trúc minh họa:

~~~text
infrastructure/
  modules/
    network/
    database/
    application/
    observability/
  environments/
    dev/
      main.tf
      variables.tf
      backend.hcl
    staging/
      main.tf
      variables.tf
      backend.hcl
    production/
      main.tf
      variables.tf
      backend.hcl
  policies/
    security/
    cost/
    lifecycle/
  tests/
  scripts/
~~~

Tên thư mục và phần mở rộng tùy công cụ; cấu trúc chỉ minh họa cách tách reusable module, environment composition, policy và test.

### 4.1. Tách module khỏi environment

Module mô tả cách tạo capability. Environment configuration chọn module version, input, region, size và policy cho một môi trường cụ thể.

Ví dụ:

~~~hcl
module "network" {
  source              = "../../modules/network"
  environment         = "staging"
  region              = var.region
  cidr                = var.vpc_cidr
  enable_private_link = true
}

module "booking_service" {
  source             = "../../modules/application"
  environment        = "staging"
  image_digest       = var.booking_image_digest
  subnet_ids         = module.network.application_subnet_ids
  database_secret_id = module.database.secret_reference
}
~~~

Đây là ví dụ HCL theo phong cách Terraform; module, input và output phải tồn tại trong implementation thật. Không đưa giá trị secret plaintext vào biến chỉ để module truyền tiếp.

### 4.2. Environment parity

Dev, staging và production nên dùng cùng module và cấu trúc, khác nhau ở input đã kiểm soát:

| Thuộc tính | Dev | Staging | Production |
|---|---|---|---|
| Capacity | Nhỏ, scale thấp | Gần production cho test | Theo demand/SLO |
| Data | Synthetic/seed | Masked hoặc synthetic | Dữ liệu thật được bảo vệ |
| Network | Private, ít tích hợp ngoài | Tương tự prod | Segmentation và egress nghiêm ngặt |
| Identity | Dev-specific role | Staging-specific role | Least privilege, approval |
| Backup | Có thể ngắn hơn | Kiểm thử restore | Policy đầy đủ |
| Observability | Sampling cao hơn | Release validation | SLO, audit và alert |
| Deletion | Ephemeral/auto cleanup | Có guardrail | Protected lifecycle |

Parity không đồng nghĩa dev phải dùng cùng kích thước hoặc cùng dữ liệu thật. Mục tiêu là dùng cùng kiến trúc và behavior có liên quan, trong khi cost, data classification và blast radius phù hợp môi trường.

## 5. Tái tạo môi trường bằng pipeline

### 5.1. Quy trình tổng quát

~~~mermaid
flowchart TD
    CHANGE["IaC change / pull request"] --> FORMAT["Format + lint"]
    FORMAT --> VALIDATE["Validate syntax/schema"]
    VALIDATE --> POLICY["Security / cost / policy checks"]
    POLICY --> PLAN["Generate plan / diff"]
    PLAN --> REVIEW["Peer review + approval"]
    REVIEW --> APPLY["Apply with scoped identity"]
    APPLY --> VERIFY["Post-deploy verification"]
    VERIFY --> READY["Environment ready"]
    VERIFY --> ROLLBACK["Repair / rollback / reconcile"]
~~~

Pipeline nên thực hiện các bước sau:

1. Kiểm tra format, syntax và provider/module version.
2. Validate input, naming, tags, CIDR, region và policy.
3. Chạy security/static analysis và cost estimation.
4. Tạo plan/diff; đính kèm artifact để reviewer kiểm tra.
5. Yêu cầu approval phù hợp với blast radius/environment.
6. Apply đúng plan đã review, bằng identity riêng cho pipeline.
7. Chạy smoke test, health check và security verification.
8. Lưu kết quả, state version, change ID và audit record.

Không tạo lại plan khác sau approval rồi apply mà không review diff mới. Artifact plan có thể chứa sensitive values tùy tool; phải bảo vệ storage và access.

### 5.2. Bootstrap dependency

Một số resource cần tồn tại trước khi IaC state backend hoạt động, ví dụ remote state bucket, lock table, encryption key hoặc CI identity. Đây là bootstrap layer.

Bootstrap cần:

- Tạo một lần theo quy trình riêng có kiểm soát.
- Bảo vệ state backend bằng encryption, versioning và access policy.
- Tách quyền bootstrap administrator khỏi runtime deployment.
- Có recovery document và backup.
- Không để state backend phụ thuộc vào chính state mà nó lưu theo vòng lặp khó phục hồi.

### 5.3. Apply có kiểm soát

Production apply nên dùng role ngắn hạn/assume role hoặc workload identity; giới hạn account/region/resource; không dùng personal admin credential. Các thay đổi destructive hoặc thay network/identity/data tier nên có approval mạnh hơn và maintenance plan khi cần.

## 6. State: dữ liệu quản lý hạ tầng

Nhiều công cụ IaC lưu **state** để ánh xạ resource trong cấu hình với resource thật, giữ ID, metadata và dependency. State có thể chứa thông tin nhạy cảm hoặc giá trị secret tùy provider/resource.

### 6.1. Vì sao cần remote state?

Local state ở laptop phù hợp thử nghiệm nhỏ nhưng gây vấn đề khi nhiều người hoặc CI cùng quản lý:

- Không chia sẻ trạng thái nhất quán.
- Mất file đồng nghĩa mất mapping.
- Khó kiểm soát backup và audit.
- Nhiều người có thể apply đồng thời.

Remote backend tập trung state, hỗ trợ versioning, access control và locking tùy công cụ/backend.

### 6.2. State locking

Lock ngăn nhiều writer cùng thay đổi một state tại một thời điểm. Không tắt locking để “vượt lỗi” nếu chưa biết lock owner và operation còn chạy không.

Nếu pipeline crash:

1. Kiểm tra run/session hiện tại và backend lock metadata.
2. Xác định chắc chắn writer cũ không còn chạy.
3. Dùng quy trình unlock được công cụ hỗ trợ, có approval/log khi cần.
4. Kiểm tra state và resource thực tế trước khi plan/apply lại.

Force unlock sai có thể làm state corruption hoặc hai writer cùng tạo resource.

### 6.3. Tách state theo blast radius

Không nhất thiết lưu tất cả hạ tầng trong một state lớn. Có thể tách foundation/network, data, platform và application để:

- Giảm phạm vi locking và plan.
- Tách quyền deploy theo owner.
- Giảm blast radius khi thay đổi.
- Tránh một service thay đổi state của service khác.

Đổi lại, cần quản lý output/reference và dependency giữa các state rõ ràng. Không tạo vòng phụ thuộc giữa state.

### 6.4. State backup và recovery

State backend cần:

- Encryption at rest và TLS.
- Versioning/backup theo RPO.
- Least privilege cho read/write.
- Audit access và mutation.
- Recovery test và quy trình import/reconcile.

Không commit state plaintext vào source repository. Không gửi state qua chat/ticket nếu có sensitive values. Khi cần share plan/state artifact, dùng secure artifact store và thời hạn ngắn.

## 7. Idempotency, dependency và thứ tự tạo resource

### 7.1. Idempotency của provisioning

Một quy trình provisioning có tính idempotent khi chạy lại với cùng desired state không tạo tài nguyên trùng hoặc làm thay đổi ngoài ý muốn.

Declarative IaC giúp quản lý idempotency, nhưng script bootstrap, provisioner hoặc external API call có thể không idempotent. Với side effect bên ngoài IaC:

- Dùng stable resource ID/idempotency key nếu API hỗ trợ.
- Kiểm tra trạng thái hiện tại trước khi tạo.
- Lưu operation ID và kết quả.
- Có retry/reconcile logic.
- Không dựa vào tên ngẫu nhiên mới mỗi lần chạy.

### 7.2. Dependency graph

Ví dụ:

~~~mermaid
flowchart TB
    NET["Network / subnets"] --> SEC["Security groups / endpoints"]
    SEC --> DB["Database"]
    SEC --> CLUSTER["Compute cluster"]
    DB --> SECRET["Secret reference / access policy"]
    CLUSTER --> ID["Workload identity"]
    ID --> APP["Application deployment"]
    DB --> APP
    APP --> OBS["Monitoring / alert"]
~~~

IaC tool có thể suy ra dependency qua resource reference hoặc cần khai báo explicit dependency khi có side effect ngoài graph. Tạo sai thứ tự có thể gây resource tạm thời không an toàn, ví dụ database tồn tại trước khi encryption/network policy được áp dụng.

### 7.3. Bootstrap và race condition

Khi tạo nhiều resource song song, API quota, eventual consistency hoặc DNS propagation có thể làm một bước downstream chạy quá sớm. Có thể dùng readiness check hoặc retry bounded cho dependency provisioning, không chỉ sleep một khoảng thời gian cố định.

## 8. Drift detection và thay đổi ngoài IaC

**Configuration drift** xảy ra khi resource thực tế khác desired state đã khai báo, ví dụ người vận hành mở firewall rule thủ công hoặc console đổi database size.

### 8.1. Phát hiện drift

- Chạy plan/refresh định kỳ ở chế độ chỉ đọc.
- Dùng cloud configuration inventory/rules để tìm resource ngoài chuẩn.
- So sánh tag, IAM/network policy, encryption và public exposure.
- Cảnh báo resource không được quản lý hoặc state mapping bị mất.
- Gắn finding với owner và change record.

### 8.2. Xử lý drift

Không phải mọi drift đều nên tự động ghi đè. Phân loại:

| Loại drift | Hành động |
|---|---|
| Thay đổi khẩn cấp được phê duyệt | Cập nhật IaC sau incident/change window |
| Cấu hình sai, rủi ro cao | Khôi phục desired state theo runbook |
| Resource cần quản lý nhưng chưa import | Import vào state sau review |
| Thay đổi do provider tự quản lý | Xác minh semantics/API; cập nhật expectation nếu đúng |
| Drift không rõ owner | Điều tra và xác định ownership trước khi sửa |

Quy tắc quan trọng: IaC repository là nguồn định nghĩa, nhưng state và cloud resource phải được đối soát trước destructive apply. Không chạy apply một cách máy móc khi chưa hiểu drift.

### 8.3. Import resource hiện có

Nếu resource được tạo thủ công cần chuyển sang IaC:

1. Xác minh owner và mục đích resource.
2. Viết resource definition tương ứng.
3. Import resource ID vào state theo tool.
4. Chạy plan và kiểm tra diff.
5. Điều chỉnh definition để phản ánh cấu hình cần giữ.
6. Chỉ apply sau khi plan không còn thay đổi không mong muốn.

## 9. Ephemeral environment cho PR và kiểm thử

Môi trường ephemeral được tạo cho một mục đích và thời hạn cụ thể, ví dụ pull request preview, integration test, performance experiment hoặc demo.

### 9.1. Lifecycle

~~~mermaid
flowchart TD
    PR["Pull request opened"] --> CREATE["Create isolated environment"]
    CREATE --> SEED["Seed synthetic test data"]
    SEED --> TEST["Run integration / preview"]
    TEST --> REVIEW["Review / feedback"]
    REVIEW --> MERGED{"PR merged or closed?"}
    MERGED -->|"No"| TTL["TTL / owner cleanup check"]
    TTL --> REVIEW
    MERGED -->|"Yes"| DESTROY["Destroy ephemeral resources"]
    TTL -->|"Expired"| DESTROY
    DESTROY --> VERIFY["Verify resource removal"]
    VERIFY --> REPORT["Cleanup report / audit"]
~~~

### 9.2. Mỗi environment cần identity và boundary riêng

Không nên tạo preview environment bằng production administrator. Mỗi environment cần:

- Naming/tag có PR ID, owner, service và expiry.
- Network boundary hoặc namespace riêng phù hợp risk.
- IAM role/service account riêng.
- Synthetic/masked data; không clone production PII tùy tiện.
- Quota/budget và TTL.
- Secret scope ngắn hạn.
- Observability giới hạn retention.

### 9.3. Tránh collision

Nhiều PR có thể chạy song song. Resource naming phải ổn định trong cùng PR nhưng không đụng nhau giữa các PR; DNS hostname, bucket name, DB/schema và namespace cần unique scope. Cân nhắc giới hạn độ dài và ký tự theo provider.

### 9.4. Cleanup tự động và orphan detection

PR đóng có thể không kích hoạt workflow nếu runner bị hỏng hoặc quyền revoke. Cần scheduled cleanup job tìm resource có TTL hết hạn, xác minh owner/state rồi thu hồi theo policy. Không xóa resource chỉ vì tag expiry nếu resource là shared/protected.

## 10. Tạo môi trường có thể tái tạo

### 10.1. Pin image và dependency

Để môi trường tái tạo, pin:

- IaC tool/provider/module version.
- Container image digest hoặc immutable artifact version.
- OS/base image và package version.
- Runtime/compiler version.
- Config schema và migration version.
- Database engine/version khi compatibility yêu cầu.

Tag mutable như latest có thể trỏ tới nội dung khác ở lần chạy sau. Image digest giúp xác định artifact chính xác hơn.

### 10.2. Tách configuration khỏi secret

Configuration không nhạy cảm như region, replica count, feature flags có thể nằm trong environment input. Secret cần được lấy từ secret manager bằng workload identity và chỉ ở runtime hoặc trong bước cần thiết.

Không:

- Commit .env chứa production secret.
- In secret ra CI log.
- Đưa secret vào image layer.
- Truyền secret qua command line dễ bị ghi lại.
- Reuse credential giữa dev/staging/production.

### 10.3. Seed data và migration

Môi trường mới cần schema và data để test. Dùng migration có version; seed synthetic data với deterministic IDs khi test cần lặp lại; không import dữ liệu production nếu chưa có phê duyệt, masking và data access control.

Migration phải có compatibility plan: expand → migrate → contract nếu có zero-downtime requirement. IaC tạo database không thay migration công cụ ứng dụng; cần phân rõ owner.

### 10.4. Environment manifest

Có thể phát hành manifest ghi lại:

~~~yaml
environment_id: pr-482
environment_type: ephemeral
owner: booking-team
source_revision: 8b2a4d1
iac_revision: c17f390
image_digest: sha256:example-digest
region: ap-southeast-1
created_at: "2026-11-18T10:00:00Z"
expires_at: "2026-11-19T10:00:00Z"
data_class: synthetic
cleanup_policy: destroy-on-close
~~~

Đây là manifest minh họa. Không ghi secret vào manifest. Lưu metadata ở nơi truy vấn được để cleanup job và audit biết môi trường thuộc ai, tạo từ version nào và hết hạn khi nào.

## 11. Teardown an toàn: thu hồi mà không làm mất dữ liệu cần giữ

Destroy không đơn giản là chạy một lệnh xóa mọi resource. Cần phân biệt tài nguyên tạm, tài nguyên có dữ liệu, shared foundation và resource cần giữ để audit/restore.

### 11.1. Phân loại resource theo lifecycle

| Loại | Ví dụ | Chính sách teardown |
|---|---|---|
| Ephemeral compute | PR namespace, temporary VM, preview LB | Có thể xóa khi environment hết hạn |
| Temporary data | Synthetic DB/schema, test object | Xóa sau test/retention ngắn |
| Persistent data | Production DB, object, backup | Không xóa bởi pipeline environment thông thường |
| Shared foundation | VPC, DNS zone, cluster, KMS key | Lifecycle riêng, approval riêng |
| Audit/telemetry | Deployment record, security audit | Retention theo policy; không xóa cùng app env |
| External side effect | DNS delegation, SaaS project, payment sandbox | Hủy/thu hồi qua workflow riêng và xác minh |

### 11.2. Protect data resources

Với database, bucket, KMS key hoặc backup vault:

- Bật deletion protection/retention lock khi phù hợp.
- Có backup/PITR trước thay đổi phá hủy.
- Tách quyền deploy và quyền destroy.
- Yêu cầu approval hoặc break-glass cho production data.
- Kiểm tra dependency, replication và retention/legal hold.
- Xác minh recovery có thể thực hiện trước khi xóa bản gốc.

Không xóa encryption key khi ciphertext/backup còn cần dùng. Mất key có thể làm dữ liệu tồn tại nhưng không thể khôi phục.

### 11.3. Quy trình teardown

1. Xác minh environment ID, owner, TTL và scope.
2. Kiểm tra resource có shared/protected/data-bearing không.
3. Chặn job/deployment mới và drain workload.
4. Export/backup dữ liệu cần giữ theo policy.
5. Thu hồi credential, endpoint và permission tạm.
6. Xóa resource theo dependency order.
7. Kiểm tra external resource và orphan.
8. Xác minh DNS, public endpoint, IP, role và storage đã được thu hồi.
9. Ghi cleanup report, những resource bị giữ lại và lý do.

~~~mermaid
flowchart TD
    REQUEST["Teardown requested / TTL expired"] --> SCOPE["Resolve environment and resource inventory"]
    SCOPE --> GUARD{"Protected or persistent resource?"}
    GUARD -->|"Yes"| APPROVAL["Require retention/backup/approval decision"]
    APPROVAL -->|"Keep"| RETAIN["Detach from ephemeral stack; retain"]
    APPROVAL -->|"Approved delete"| BACKUP["Backup / verify retention"]
    GUARD -->|"No"| DRAIN["Drain jobs and stop workloads"]
    BACKUP --> DRAIN
    DRAIN --> DESTROY["Destroy in dependency order"]
    DESTROY --> VERIFY["Verify no orphan / public access"]
    RETAIN --> REPORT["Cleanup report + audit"]
    VERIFY --> REPORT
~~~

### 11.4. Partial failure khi destroy

Teardown có thể xóa một phần rồi thất bại vì quota/API/network/permission. Không giả định stack đã sạch chỉ vì command trả lỗi hoặc state ghi một phần.

Phải:

- Lưu log/result của từng operation.
- Chạy inventory và plan/reconcile sau lỗi.
- Xác định resource còn lại và owner.
- Retry operation idempotent, không tạo lại stack.
- Tách resource cần xử lý thủ công và ghi rõ lý do.
- Alert khi orphan tồn tại quá TTL.

## 12. IaC security và policy guardrail

### 12.1. Least privilege cho pipeline

Pipeline identity nên:

- Chỉ quản lý account/project/region/environment được giao.
- Dùng federated/short-lived credential khi provider hỗ trợ.
- Tách plan/read role với apply/write role nếu khả thi.
- Không có quyền xóa data/backup/key trong pipeline ephemeral.
- Ghi audit cho apply/destroy và state access.
- Yêu cầu approval cho quyền hoặc resource đặc biệt.

### 12.2. Policy as code

Trước apply, policy check có thể từ chối:

- Database/object storage public ngoài policy.
- Resource không bật encryption.
- Security group mở management port tới Internet.
- IAM wildcard hoặc quyền administrator không có ngoại lệ.
- Resource thiếu owner, environment hoặc cost tag.
- Instance/volume vượt size/quota/budget.
- Backup/retention/deletion protection thiếu ở data tier.
- Secret plaintext trong config.

Policy nên có test và version; ngoại lệ cần owner, reason, scope và expiry.

### 12.3. Supply chain của IaC

IaC module, provider, action và CI plugin đều là dependency có thể ảnh hưởng hạ tầng. Chỉ dùng source được tin cậy, pin version, review change, scan module và hạn chế quyền pipeline. Không chạy module/script không rõ nguồn bằng cloud administrator credential.

## 13. Drift, replace và lifecycle hazard

Một số thuộc tính không thể update tại chỗ và buộc tool replace resource. Ví dụ thay CIDR, encryption setting, immutable identifier hoặc disk type tùy provider.

Plan cần nhận diện:

- Resource nào sẽ create/update/delete/replace?
- Có downtime hoặc data loss không?
- Replacement resource có tạo song song được không?
- DNS/traffic cutover và connection drain thế nào?
- Data migration/replication có cần bước riêng?
- Rollback có khả thi không?

### 13.1. Lifecycle guard

Một số công cụ có lifecycle rule như prevent destroy, create before destroy, ignore changes hoặc retain resource. Các rule này có semantics riêng:

- Prevent destroy có thể chặn cả pipeline teardown nếu resource đang được bảo vệ.
- Create before destroy cần quota đủ cho cả resource cũ và mới.
- Ignore changes có thể che drift thật nếu dùng quá rộng.
- Retain resource có thể tạo orphan cần owner và cleanup workflow riêng.

Không bật ignore-changes để làm plan “sạch” mà không hiểu nguồn thay đổi.

## 14. Quota, capacity và cost của environment lifecycle

Tạo thêm environment tiêu thụ quota và capacity. Nếu mỗi PR tạo cluster/database riêng, số lượng môi trường có thể vượt quota hoặc làm tăng cost nhanh.

### 14.1. Budget cho ephemeral environment

Định nghĩa:

- Số environment tối đa đồng thời.
- TTL mặc định và TTL extension policy.
- CPU/memory/storage maximum.
- Số database/cluster/endpoint được phép.
- Cost budget theo PR/team.
- Rate limit tạo môi trường để không flood cloud API.

### 14.2. Cost allocation

Mỗi resource nên có tag như environment_id, owner, service, cost_center, created_by và expires_at. Dùng billing export/cost API để đối chiếu resource tồn tại và chi phí.

### 14.3. Tái sử dụng hay tạo mới?

| Mô hình | Ưu điểm | Đánh đổi |
|---|---|---|
| Environment riêng mỗi PR | Isolation cao, kiểm thử gần production | Chi phí và quota tăng |
| Shared test environment | Chi phí thấp, ít resource | Test ảnh hưởng nhau, dữ liệu/network dễ collision |
| Namespace/stack ephemeral trên platform chung | Tái sử dụng cluster/foundation | Cần quota, namespace isolation và cleanup tốt |
| Dedicated environment theo team | Cân bằng ownership/isolation | Có idle capacity, vận hành nhiều stack |

Chọn mô hình theo risk, data sensitivity, test fidelity, concurrency và chi phí.

## 15. Kiểm thử IaC và khả năng tái tạo

### 15.1. Các lớp test

| Lớp | Nội dung |
|---|---|
| Format/lint | Style, naming, dead code, deprecated attributes |
| Validate | Syntax, type, required input và provider schema |
| Unit/policy test | Rule/tag/identity/network policy theo expectation |
| Plan review | Diff và resource replacement/destruction |
| Integration test | Tạo thật trong sandbox, verify connectivity/function |
| Drift test | Thay đổi ngoài luồng được phát hiện |
| Rebuild test | Destroy ephemeral rồi tạo lại từ cùng revision |
| Teardown test | Xóa đúng resource và giữ resource protected |

### 15.2. Reproducibility test

Một bài kiểm thử tốt:

1. Tạo stack từ revision xác định.
2. Ghi lại image digest, provider/module version và inputs.
3. Chạy smoke/integration test.
4. Chạy plan lần hai và xác nhận không có diff ngoài dự kiến.
5. Destroy stack ephemeral.
6. Kiểm tra resource inventory không còn orphan.
7. Tạo lại từ cùng revision/input.
8. So sánh topology, policy, config và behavior.

Không nhất thiết ID resource phải giống nhau; điều cần tái tạo là cấu trúc, cấu hình, policy và behavior được cam kết.

### 15.3. Test negative

- Pipeline dev không thể xóa database production.
- Environment không có owner/TTL bị từ chối tạo hoặc được quarantine.
- IaC plan mở public database bị policy chặn.
- State lock đang giữ thì apply thứ hai không ghi đè.
- Destroy ephemeral stack không xóa shared network hoặc KMS key.
- Secret không xuất hiện trong plan/log/artifact không được bảo vệ.
- Provider quota exceeded tạo lỗi rõ, không retry vô hạn.

## 16. Quan sát và vận hành IaC

### 16.1. Metric và event

Theo dõi:

- Provisioning duration và success/failure rate.
- Số resource create/update/delete/replace.
- Plan drift count.
- Apply/destroy failure và retry.
- State lock contention/age.
- Quota exceeded và API throttling.
- Environment count, age và orphan count.
- Cleanup completion time.
- Cost per environment và idle resource cost.

Ghi event cho PR opened/closed, plan generated/approved, apply started/completed, policy violation, drift detected, destroy started/completed và manual exception.

### 16.2. Audit record

Mỗi lần apply/destroy nên có:

- Principal/pipeline identity.
- Repository, revision và module/provider versions.
- Environment/account/region.
- Plan artifact ID hoặc digest.
- Approver/change ticket.
- Resource changes.
- Kết quả và correlation ID.

Không lưu plaintext credential trong audit; bảo vệ plan/state artifact vì có thể chứa sensitive configuration.

### 16.3. Runbook

Runbook nên hướng dẫn xử lý:

- State lock bị treo.
- State backend unavailable.
- Provider API throttling/quota exceeded.
- Resource drift do emergency change.
- Apply failed giữa chừng.
- Destroy partial/orphan resource.
- Protected resource chặn teardown.
- Credential/certificate hết hạn.
- Provider/module upgrade gây diff bất ngờ.

## 17. Ví dụ pipeline cho BookingCloud

~~~yaml
name: provision-preview
on:
  pull_request:
    types: [opened, synchronize, reopened, closed]

jobs:
  validate:
    if: github.event.action != 'closed'
    steps:
      - run: iac fmt-check
      - run: iac validate
      - run: policy-check infrastructure/
      - run: cost-estimate infrastructure/
      - run: iac plan -out=preview.plan

  apply:
    needs: validate
    if: github.event.action != 'closed'
    environment: preview-approval
    steps:
      - run: iac apply preview.plan
      - run: smoke-test preview
      - run: record-environment-manifest

  destroy:
    if: github.event.action == 'closed'
    steps:
      - run: verify-preview-owner-and-scope
      - run: iac plan-destroy
      - run: policy-check-destroy-plan
      - run: iac destroy
      - run: verify-no-orphans
~~~

Đây là pseudoworkflow, không phải syntax dùng trực tiếp cho một CI provider. Thực tế cần tách validate/apply artifact, kiểm soát event context, quyền apply/destroy, concurrency group, state lock, approval và bảo vệ nhánh. Không chạy apply/destroy chỉ dựa trên dữ liệu PR chưa được tin cậy.

## 18. Đánh giá theo Well-Architected

| Góc nhìn | Câu hỏi review | Bằng chứng cần có |
|---|---|---|
| **Operational Excellence** | Môi trường có thể tạo lại, review, audit và thu hồi bằng quy trình chuẩn? | Pipeline, state backup, runbook, manifest, cleanup report |
| **Security** | Pipeline có least privilege? Secret/state/artifact có được bảo vệ? | IAM policy, secret scan, state encryption, approval và audit |
| **Reliability** | Apply/teardown lỗi giữa chừng có thể reconcile và phục hồi? | Locking, backup, idempotency, drift checks, rebuild/restore tests |
| **Performance Efficiency** | Provisioning time, shared platform và capacity có phù hợp? | Provision duration, warm pool, quota/capacity tests |
| **Cost Optimization** | Ephemeral/idle resources có TTL, budget và owner? | Cost tags, orphan alerts, TTL cleanup, per-environment cost |
| **Sustainability** | Có tài nguyên nhàn rỗi, log/state phình to hoặc rebuild thừa? | Lifecycle policy, reuse strategy, utilization và cleanup efficiency |

IaC làm thay đổi hạ tầng nhanh và nhất quán; vì vậy quyền của pipeline và guardrail phải mạnh tương ứng. Môi trường tái tạo tốt phải cùng revision cho kết quả tương đương; teardown tốt phải giải phóng phần tạm thời và bảo toàn dữ liệu, audit, key cùng foundation cần giữ.

## 19. Bài thực hành: tạo và thu hồi môi trường preview

BookingCloud muốn tạo một preview environment cho mỗi pull request để kiểm thử booking flow:

- Một application namespace/compute workload.
- Database nhỏ với synthetic seed data.
- Cache và queue riêng hoặc namespace riêng.
- Private ingress, DNS preview và TLS.
- Workload identity chỉ truy cập secret của preview.
- Log/metric/trace với retention ngắn.
- TTL 24 giờ sau lần activity cuối.
- Tự teardown khi PR đóng.

Hãy thực hiện:

**Bài 1 — Resource inventory:** liệt kê resource, owner, dependency, quota, tag và lifecycle class.

**Bài 2 — Module design:** chia module network/platform/data/application/observability; định nghĩa input/output.

**Bài 3 — State:** chọn remote backend, state scope, locking, encryption và recovery.

**Bài 4 — Pipeline:** thiết kế validate, policy check, plan artifact, approval, apply, smoke test và manifest.

**Bài 5 — Security:** tạo workload identity, secret access, private ingress/egress, policy chống public database và credential leakage.

**Bài 6 — Reproducibility:** pin IaC/provider/module/image version, seed synthetic data và migration.

**Bài 7 — Teardown:** phân loại ephemeral/persistent/shared resource; thiết kế backup/approval/retention và orphan verification.

**Bài 8 — Drift/failure:** mô phỏng manual change, mất state lock, provider quota exceeded và destroy partial.

**Bài 9 — Cost:** đặt concurrency cap, TTL, resource size, budget và cảnh báo orphan.

### Khung kết quả tự kiểm tra

| Quyết định | Cần chứng minh |
|---|---|
| Cùng module giữa env | Khác biệt nằm ở input có review, không phải copy/paste cấu hình |
| Remote state | Lock, access, encryption, backup và recovery có kiểm tra |
| Immutable artifact | Revision/image digest/provider version xác định được |
| Ephemeral identity | Không dùng production admin hoặc secret |
| Safe destroy | Không xóa data/foundation/audit cần giữ |
| Drift handling | Có owner, phân loại và reconcile trước destructive apply |
| Cleanup | TTL, orphan detection và report xác nhận kết quả |
| Rebuild | Cùng revision/input tạo topology/policy/behavior tương đương |

## 20. Checklist trước khi đưa IaC workflow vào production

- [ ] Desired state, resource owner, tag, environment và lifecycle được khai báo.
- [ ] Module, input/output và environment composition có version.
- [ ] Provider/module/tool version được pin và update có review.
- [ ] Remote state được mã hóa, khóa, backup và giới hạn quyền.
- [ ] Plan/diff được lưu an toàn và review trước apply.
- [ ] Pipeline identity ngắn hạn, least privilege và tách quyền destroy.
- [ ] Secret không nằm trong source, image, plan artifact hoặc CI log plaintext.
- [ ] Network, identity, data và policy được tạo theo dependency order.
- [ ] Image, runtime, migration và seed data có version xác định.
- [ ] Có drift detection, import/reconcile và state recovery procedure.
- [ ] Ephemeral environment có owner, TTL, budget và identity riêng.
- [ ] Teardown phân biệt ephemeral, persistent, shared và protected resource.
- [ ] Có backup/retention/deletion protection cho data và key cần giữ.
- [ ] Destroy có plan, guardrail, approval phù hợp và orphan verification.
- [ ] Có load/quota/cost check trước khi tạo nhiều environment.
- [ ] Rebuild, partial failure, state lock và teardown đã được test.

Khởi tạo môi trường có thể tái tạo đòi hỏi định nghĩa desired state, version hóa đầu vào, quản lý state và thực thi qua pipeline có review. Thu hồi an toàn đòi hỏi phân loại lifecycle, bảo vệ dữ liệu và foundation, kiểm tra dependency, rồi xác minh resource thực sự đã được giải phóng. Khi hai quy trình này cùng được tự động hóa và kiểm chứng, đội ngũ có thể tạo môi trường nhất quán cho dev/test/staging/production, giảm drift, kiểm soát chi phí và thu hẹp rủi ro vận hành.
