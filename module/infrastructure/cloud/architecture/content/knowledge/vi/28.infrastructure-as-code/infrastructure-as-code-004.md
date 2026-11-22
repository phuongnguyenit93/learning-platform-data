# Tách biến môi trường khỏi bí mật và cấu hình nhạy cảm

Infrastructure as Code (IaC) mô tả hạ tầng và cấu hình bằng mã có thể review, version control và triển khai lặp lại. Module IaC thường cần những giá trị thay đổi theo môi trường như region, instance size, endpoint, tên bucket, feature setting, database password, API token và private key. Nếu tất cả đều được xử lý như biến đầu vào thông thường, bí mật có thể lọt vào Git, state file, plan artifact, CI log, image hoặc output của pipeline.

**Tách biến môi trường khỏi bí mật và cấu hình nhạy cảm** là thiết kế ranh giới giữa dữ liệu mô tả hành vi triển khai với dữ liệu cấp quyền truy cập hoặc gây rủi ro khi bị lộ. Mục tiêu không chỉ là đặt password vào secret manager; cần xác định nguồn sự thật, phân loại dữ liệu, cách tham chiếu, identity được phép truy cập, thời điểm cấp phát, vòng đời, rotation, audit và cách ngăn bí mật đi vào artifact không an toàn.

Bài học thuộc chương **Hạ tầng dưới dạng mã** của lộ trình **Cloud Architecture**. Chương trình học cách thiết kế ứng dụng cloud từ yêu cầu nghiệp vụ tới mạng, compute, dữ liệu và mô hình triển khai, cân bằng độ tin cậy, bảo mật, khả năng mở rộng, chi phí và vận hành. Bài này tập trung vào cách tổ chức cấu hình theo môi trường, giữ bí mật ngoài mã nguồn và quản lý việc sử dụng chúng trong pipeline IaC lẫn runtime workload.

Sau bài học, bạn có thể:

- Phân biệt environment variable, application configuration, sensitive configuration, secret và key material.
- Xác định nguồn sự thật và precedence cho cấu hình theo environment.
- Quản lý secret bằng secret manager/vault và workload identity.
- Tránh đưa secret vào Git, IaC state, plan, log, output và artifact.
- Thiết kế module IaC dùng reference thay vì plaintext secret.
- Hiểu giới hạn của sensitive marking, masking và mã hóa state.
- Truyền cấu hình tới VM, container và Kubernetes an toàn.
- Thiết kế bootstrap, rotation, revocation và emergency response.
- Thiết lập policy-as-code, secret scanning và kiểm tra drift.
- Kiểm thử và audit cấu hình xuyên suốt dev, staging và production.

## 1. Phân biệt configuration và secret

Không phải mọi cấu hình đều là bí mật. Nhiều giá trị cần thay đổi giữa các môi trường nhưng không cấp quyền truy cập.

- **Environment-specific configuration:** giá trị mô tả môi trường hoặc hành vi triển khai, ví dụ region, hostname, log level, feature setting và replica count.
- **Application configuration:** tham số điều khiển ứng dụng, ví dụ timeout, retry limit, locale và business threshold.
- **Sensitive configuration:** cấu hình không phải credential nhưng khi lộ có thể tiết lộ topology hoặc policy nội bộ, ví dụ internal endpoint, network layout hay security rule.
- **Secret/credential:** dữ liệu dùng xác thực hoặc cấp quyền truy cập, ví dụ password, API token, client secret và webhook signing secret.
- **Cryptographic key material:** private key, data encryption key (DEK), key-encryption key (KEK) hoặc signing key.
- **Public metadata:** tên service, public endpoint, non-sensitive feature setting hoặc identifier không trao quyền.

| Loại dữ liệu | Ví dụ | Xử lý khuyến nghị |
| --- | --- | --- |
| Non-sensitive config | Region, instance type, port, log level | Version control hoặc config store |
| Environment config | Domain, resource name, replica count | IaC variable/config theo environment |
| Sensitive config | Internal topology, security policy chi tiết | Phân quyền truy cập, hạn chế log/export |
| Secret | DB password, API token, OAuth client secret | Secret manager, short-lived identity khi có thể |
| Private key | TLS/signing private key | KMS/HSM hoặc secret store có protection phù hợp |
| Public key/certificate | Public verification key, public certificate | Integrity, trust chain và version control |
| Wrapped DEK | Encrypted data key | Lưu cùng metadata ciphertext theo thiết kế mã hóa |

Một giá trị có thể không phải secret nhưng vẫn cần bảo vệ vì nó tiết lộ cấu trúc hệ thống. Ngược lại, không nên đánh dấu mọi biến là secret: làm vậy khiến review khó hơn và che mất rủi ro thực sự.

## 2. Environment variable là phương tiện truyền, không phải kho bí mật

Environment variable (env var) truyền cấu hình tới process khi khởi chạy. Nó không tự mã hóa, không cung cấp access policy và không quản lý lifecycle. Giá trị có thể bị lộ qua process inspection, crash dump, debug endpoint, diagnostic bundle, container metadata, orchestration control plane hoặc log do ứng dụng tự ghi.

Có thể dùng env var cho port, region, service mode, log level, non-sensitive endpoint/config và secret reference. Một số runtime có thể nhận secret qua env var nếu platform bảo vệ tốt; nhưng với credential quan trọng hoặc workload chạy lâu, nên ưu tiên identity-based retrieval hoặc mounted secret file có permission chặt nếu nền tảng hỗ trợ.

Những nơi env var có thể xuất hiện gồm process environment, process dump, container/Pod specification, CI task definition, command line, crash dump, telemetry và shell history. Giới hạn quyền host/container control plane, debug permission và log là một phần của bảo vệ env var.

## 3. Ba vùng dữ liệu nên tách

Một kiến trúc cơ bản có thể chia thành ba vùng:

1. **IaC inputs/configuration:** dữ liệu không bí mật hoặc reference tới nguồn cấu hình/bí mật, dùng để mô tả resource và tham số môi trường.
2. **Secret system:** giữ giá trị bí mật, policy, version, rotation và audit.
3. **Runtime workload:** nhận cấu hình cần thiết và lấy secret theo identity đã xác thực, chỉ trong phạm vi được phép.

~~~mermaid
flowchart TB
    G["Git: IaC modules and non-secret config"] --> CI["CI/CD runner"]
    CI --> CLOUD["Cloud API / IaC provider"]
    CI --> ID["Deployment identity"]
    ID --> SM["Secret manager / KMS"]
    SM -->|Controlled reference or injection| RT["Runtime workload"]
    CLOUD --> RT
    RT --> APP["Application uses config and credentials"]
~~~

Secret chỉ nên xuất hiện dưới dạng plaintext tại boundary thực sự cần sử dụng nó và trong thời gian ngắn nhất có thể. Nếu provider resolve reference lúc deploy rồi lưu plaintext vào state, reference vẫn chưa giải quyết được rủi ro; phải kiểm tra data flow thật.

## 4. Nguồn sự thật và precedence của cấu hình

Cấu hình thường đến từ module default, file môi trường, IaC variable, pipeline parameter, config service và runtime override. Nếu không định nghĩa precedence, cùng deployment có thể cho kết quả khác nhau tùy thứ tự inject.

Một precedence có thể là:

**Platform defaults → Environment configuration → Service configuration → Runtime override được cho phép**

Mỗi lớp cần owner và phạm vi. Không phải mọi key được override ở mọi lớp. Region/resource naming có thể do platform quyết định; application timeout do đội service điều chỉnh trong giới hạn; security policy bắt buộc không được tenant hoặc runtime override.

Một config contract nên xác định key/type, required/optional, default, allowed values, range, validation, environment applicability, owner, sensitivity, source of truth, version, compatibility, reload behavior và audit. Không nên đặt tất cả vào một JSON/YAML không schema.

## 5. Cấu trúc file theo môi trường

Có thể lưu cấu hình không nhạy cảm theo từng environment, dùng module chung và file input riêng. Tên file/path cho biết environment nhưng không chứa secret.

~~~text
infra/
  modules/
    app-service/
      main.tf
      variables.tf
      outputs.tf
  environments/
    dev/
      backend.hcl
      app.tfvars
    staging/
      backend.hcl
      app.tfvars
    production/
      backend.hcl
      app.tfvars
  policies/
    require-encryption.rego
    deny-public-storage.rego
~~~

Các file tfvars có thể commit nếu chỉ chứa giá trị non-secret và đã review. Backend config có thể định vị state store nhưng không nên chứa access key tĩnh. Authentication tới cloud/backend nên dựa trên workload identity hoặc credential ngắn hạn.

Ví dụ input không bí mật:

~~~hcl
# environments/production/app.tfvars
environment          = "production"
region               = "ap-southeast-1"
instance_type        = "compute-optimized-medium"
replica_count        = 3
log_level            = "INFO"
public_base_url      = "https://app.example.com"
database_secret_ref  = "secret/production/booking/database"
~~~

Secret reference không phải secret value nhưng vẫn có thể tiết lộ tên hệ thống hoặc cấu trúc nội bộ. Hãy phân loại reference và quyền đọc file phù hợp.

## 6. Secret manager và vault

Secret manager/vault cung cấp nơi lưu secret tập trung cùng access policy, version, audit và rotation. Một số dịch vụ hỗ trợ dynamic secret, lease và workload identity integration.

Secret system cần trả lời: ai được tạo/cập nhật; workload nào được đọc secret nào; quyền có scope theo service/environment/tenant không; secret có version/expiry không; rotation có tự động không; có audit read/write/rotate/revoke không; dịch vụ có HA/DR và backup không; làm gì khi store tạm thời không khả dụng; thu hồi session/token/connection đã cấp ra sao.

Centralized không có nghĩa một identity đọc được mọi bí mật. Phải chia namespace, policy và administrative boundary theo environment, domain và mức độ nhạy cảm.

## 7. Workload identity thay credential tĩnh

Workload không nên lưu access key dài hạn chỉ để truy cập secret manager. VM, container, function hoặc CI runner nên dùng identity do platform cấp.

~~~mermaid
sequenceDiagram
    participant W as Workload
    participant I as Cloud identity provider
    participant S as Secret manager
    participant D as Database
    W->>I: Request short-lived identity
    I-->>W: Scoped identity token
    W->>S: Read authorized secret reference
    S-->>W: Secret version/value
    W->>D: Authenticate to database
~~~

Policy nên giới hạn subject, service account, environment, audience, namespace và resource. Deployment runner được phép tạo resource không nhất thiết được phép đọc application runtime secret. Tách deployment identity và runtime identity giúp giảm blast radius.

### 7.1. Bootstrap và secret zero

Để đọc secret đầu tiên, workload vẫn cần cách xác thực. Các hướng thường gặp là managed identity/instance role, OIDC federation từ CI, Kubernetes service account token federation, workload certificate ngắn hạn hoặc bootstrap credential có scope hẹp và TTL ngắn.

Không giải quyết bootstrap bằng cách hardcode master password trong image. Nếu phải dùng bootstrap secret, quản lý nó như tài sản critical và có kế hoạch loại bỏ.

## 8. IaC variables và sensitive marking

Các công cụ IaC thường có cơ chế đánh dấu input/output nhạy cảm. Ví dụ Terraform:

~~~hcl
variable "database_password" {
  type      = string
  sensitive = true
}
~~~

Sensitive marking hữu ích để che một số giá trị khỏi CLI output hoặc UI theo semantics của công cụ. Tuy nhiên, nó **không tự mã hóa hay loại bỏ giá trị khỏi state**. Provider có thể ghi giá trị vào state, plan artifact, debug log hoặc API request. Phải kiểm tra behavior của tool/provider và phiên bản cụ thể.

Ưu tiên truyền secret reference hoặc dùng integration hỗ trợ ephemeral/write-only argument khi resource/provider hỗ trợ đúng semantics. Không cho rằng thêm sensitive = true là đã xử lý xong secret management.

Output được đánh dấu sensitive có thể bị ẩn khi hiển thị nhưng vẫn nằm trong state hoặc được consumer có quyền truy xuất. Không export secret thành output chỉ để module khác dùng; ưu tiên chia sẻ reference/identity và để workload lấy secret trực tiếp.

## 9. IaC state và plan là tài sản nhạy cảm

State file ánh xạ tài nguyên thực tế và có thể chứa input, attribute, connection detail hoặc secret do provider trả về. Plan file cũng có thể chứa giá trị nhạy cảm tùy công cụ/provider.

- Lưu remote state ở backend có encryption at rest/in transit.
- Bật versioning, locking và access control.
- Phân quyền đọc/ghi state theo team/workspace/environment.
- Tách state production khỏi dev/staging.
- Không commit state, plan hoặc backup state vào Git.
- Hạn chế tải plan artifact và đặt retention ngắn.
- Bảo vệ CI log và provider debug output.
- Tránh output secret từ module.
- Kiểm tra state backup/restore và quy trình incident.
- Không cho người không cần thiết đọc state dù họ không có quyền runtime.

Encryption at rest bảo vệ khi lưu trữ, nhưng người có quyền đọc state vẫn có thể lấy nội dung đã giải mã. Cần least privilege, audit và giảm lượng secret đi vào state ngay từ đầu.

State isolation giúp pipeline chỉ đọc phần nó quản lý. State lock tránh ghi đè đồng thời; nó không phải cơ chế phân quyền. Encryption cũng không thay việc hạn chế download/export.

## 10. Secret injection tới VM và container

Các mô hình thường gặp:

- Runtime gọi secret manager qua workload identity.
- Agent/sidecar lấy secret và ghi vào file mount có quyền chặt.
- Orchestrator tích hợp secret provider để mount hoặc sync.
- CI/CD inject lúc deploy nếu runtime platform có cơ chế bảo vệ rõ.

Ưu tiên phương án giữ secret ngoài image và ngoài deployment manifest có thể đọc rộng.

### 10.1. VM

Dùng managed identity/instance profile để instance lấy secret. Nếu ghi ra file, phải đặt owner/mode, kiểm soát filesystem encryption, backup và cleanup. Tránh để secret trong cloud-init/user-data nếu metadata API cho phép người không phù hợp đọc lại.

### 10.2. Container

Không build secret vào image layer bằng Dockerfile ARG/ENV. Giá trị có thể bị giữ trong image history, build cache, registry hoặc runtime metadata. Dùng runtime secret integration, mounted file hoặc identity-based fetch.

Không đặt secret trong label/annotation hoặc image tag. Hạn chế quyền exec/debug vào container production vì người có quyền đó có thể đọc environment hoặc file secret.

### 10.3. Kubernetes

Kubernetes Secret là object quản lý dữ liệu nhạy cảm, nhưng biểu diễn base64 không đồng nghĩa mã hóa. Cần cấu hình encryption at rest cho etcd theo khả năng cluster, RBAC tối thiểu, hạn chế list/watch, audit và network access control.

Có thể dùng External Secrets Operator hoặc secret store CSI integration, workload identity federation, secret volume mount và policy refresh/rollout. Phải bảo vệ etcd backup, API server, RBAC và node access. Base64 chỉ là encoding.

## 11. CI/CD pipeline và bí mật lúc deploy

CI/CD thường có quyền cao: đọc repository, tạo hạ tầng, publish artifact và triển khai production. Pipeline bị compromise có thể lộ secret hoặc sửa hạ tầng.

- Dùng OIDC federation/short-lived credential thay static cloud key.
- Tách identity cho plan, apply, image build và runtime.
- Giới hạn environment approval và protected branch.
- Không in biến môi trường hoặc command line chứa secret.
- Masking log chỉ là lớp giảm rủi ro, không thay kiểm soát output.
- Giới hạn quyền download plan/state/build artifact.
- Không cho fork/untrusted pull request dùng production secret.
- Pin action/plugin/provider version và verify provenance.
- Scan commit, repository history và artifact.
- Audit ai chạy apply và với identity nào.

### 11.1. Plan review và apply identity

Pipeline có thể tạo plan bằng quyền read/plan rồi yêu cầu approval trước apply. Plan artifact cần được bảo vệ vì có thể chứa thông tin nội bộ hoặc nhạy cảm. Apply identity chỉ nên có quyền cần cho scope cụ thể, không dùng administrator toàn account mặc định.

Không cấp production secret cho pipeline chạy code từ fork hoặc branch chưa tin cậy. Tách job build/test không secret khỏi job privileged chạy sau approval.

## 12. Phân tách environment

Dev, staging và production có mức dữ liệu, identity, network và quyền khác nhau. Không nên chỉ đổi một biến ENV rồi dùng chung credential, state hoặc secret namespace.

| Thành phần | Dev | Staging | Production |
| --- | --- | --- | --- |
| Cloud account/project | Isolated dev scope | Isolated preprod scope | Dedicated production scope |
| State backend | Riêng | Riêng | Riêng, quyền chặt |
| Secret namespace | dev/service | staging/service | production/service |
| Workload identity | Dev role | Staging role | Production role |
| Data | Synthetic/test | Masked hoặc synthetic | Production theo policy |
| Apply approval | Tự động trong giới hạn | Có review | Protected approval/change control |
| Network | Non-production isolation | Preprod isolation | Production segmentation |

Không copy production secret sang staging để giống thật. Dùng secret riêng, data synthetic hoặc data đã masking phù hợp. Không dùng cùng API token cho nhiều environment vì khó thu hồi theo phạm vi.

## 13. Sensitive configuration ngoài credential

Một số cấu hình không phải password nhưng có thể tiết lộ security posture hoặc giúp attacker lập bản đồ hệ thống: internal hostname/private IP, route/firewall allowlist, admin endpoint, feature switch bảo mật, KMS key identifier, secret path, fraud threshold và backup topology.

Những giá trị này không nhất thiết cần secret manager. Có thể lưu trong config store có quyền giới hạn, encrypted state và audit. Phân loại theo impact nếu bị lộ, sửa hoặc xóa; tránh gộp mọi thứ vào cùng một namespace secret.

## 14. Rotation và reload

Secret rotation chỉ hiệu quả nếu consumer thực sự chuyển sang version mới. IaC apply có thể cập nhật secret reference nhưng process vẫn giữ credential cũ trong memory hoặc connection pool.

1. Tạo credential mới ở target system.
2. Lưu version mới trong secret manager.
3. Cấp quyền đọc cho runtime identity.
4. Refresh secret reference hoặc trigger workload reload.
5. Tạo connection/request mới và verify.
6. Theo dõi consumer còn dùng version cũ.
7. Revoke credential cũ sau overlap được giới hạn.
8. Audit và cập nhật inventory.

~~~mermaid
flowchart TD
    A["Create new credential"] --> B["Publish new secret version"]
    B --> C["Refresh workload"]
    C --> D["Verify new connections"]
    D --> E{"All consumers migrated?"}
    E -- "No" --> F["Investigate and retry"]
    F --> C
    E -- "Yes" --> G["Revoke old credential"]
    G --> H["Audit and close rotation"]
~~~

Không revoke ngay credential cũ nếu consumer chưa refresh. Overlap cũng không được kéo dài vô hạn; đặt expiry, owner và alert.

## 15. Secret leakage và incident response

Khi secret xuất hiện trong Git, log hoặc artifact, cần coi là đã lộ cho tới khi chứng minh ngược lại. Xóa dòng trong commit mới không vô hiệu giá trị đã lưu trong history hoặc cache.

1. Xác định secret, owner, quyền và resource mà nó mở.
2. Xác định nơi lộ: commit, artifact, CI log, image, state, dump hay ticket.
3. Thu hồi/rotate credential tại source of authority.
4. Vô hiệu session/token/connection còn hiệu lực nếu có thể.
5. Phát credential mới và deploy theo emergency path.
6. Kiểm tra audit/API/database access và dấu hiệu lạm dụng.
7. Xóa hoặc hạn chế bản sao bị lộ theo policy, giữ evidence cần thiết.
8. Tìm bản sao trong Git history, artifact registry, cache và backup.
9. Rotate dependent secret có thể bị đọc bằng credential đã lộ.
10. Ghi incident, root cause, phạm vi và biện pháp ngăn tái diễn.

Nếu secret trong IaC state bị lộ, cần xử lý cả quyền state, plan artifact, backup và bản export. Xóa file state mà không hiểu backend/versioning có thể phá hỏng quản lý hạ tầng; phối hợp recovery procedure của IaC tool.

## 16. Secret scanning và policy-as-code

Secret scanning phát hiện chuỗi giống token/password trong Git diff, history, artifact hoặc container image. Scanner có thể false positive hoặc bỏ sót secret đã mã hóa/biến đổi; kết quả cần workflow xác minh và remediation.

Policy-as-code có thể cấm plaintext password/token trong resource attribute không được phép; secret trong output/tag/label/user-data/image build argument; static cloud access key trong CI; public storage hoặc security group ngoài policy; runtime workload dùng administrator identity; production resource tham chiếu secret namespace dev; state backend thiếu encryption/locking/access policy; Kubernetes Secret/etcd thiếu encryption/RBAC baseline; credential không có owner/expiry.

Policy cần kiểm tra semantics thật của provider/resource, không chỉ tìm tên field chứa chữ password. Một số resource có write-only argument, một số provider lưu giá trị trong state. Phải hiểu schema và behavior.

## 17. IaC module interface an toàn

Module nên yêu cầu thông tin tối thiểu và ưu tiên reference thay vì plaintext secret.

~~~hcl
variable "environment" {
  type = string
}

variable "database_secret_arn" {
  type        = string
  description = "Reference to a secret managed outside this module"
}

resource "example_app_service" "booking" {
  name        = format("booking-%s", var.environment)
  environment = var.environment
  secret_reference = var.database_secret_arn
}
~~~

Resource/provider ở đây chỉ minh họa. Chỉ dùng kiểu tham chiếu nếu nền tảng đích hỗ trợ runtime secret retrieval; một số provider/resource resolve reference lúc deploy rồi ghi plaintext vào state hoặc API. Cần xác minh data flow trước khi chọn abstraction.

Output nên trả resource ID, endpoint, ARN/reference hoặc non-sensitive metadata. Module khác cần credential nên dùng identity để lấy secret từ secret manager theo scope của chính nó; module không nên là kênh truyền plaintext giữa stack.

## 18. IaC state, remote backend và recovery

State backend là nguồn điều khiển IaC. Cần bảo vệ confidentiality, integrity và khả năng phục hồi.

- Encryption at rest/in transit.
- Authentication bằng identity ngắn hạn.
- Least privilege theo workspace/state key.
- State locking để tránh concurrent update.
- Versioning và retention.
- Access log/audit.
- Backup/restore test.
- Không public state bucket.
- Không tải state vào máy cá nhân ngoài quy trình.
- Secure handling cho crash log/debug trace.

Nếu state bị mất, hạ tầng có thể vẫn tồn tại nhưng IaC mất mapping resource. Nếu state bị lộ, resource mapping và có thể cả secret bị lộ. Recovery runbook cần xử lý hai trường hợp riêng.

## 19. Runtime configuration và secret delivery

Sau khi IaC provision hạ tầng, runtime vẫn cần nhận đúng version config/secret.

- **Pull at startup:** lấy config/secret khi khởi động; dễ xác định version nhưng có thể không cập nhật giữa vòng đời process.
- **Pull periodically:** định kỳ kiểm tra version; cần cache, retry và jitter.
- **Push/invalidation:** config service phát event để workload reload; cần xử lý event mất/trùng và rollout.
- **Mounted file refresh:** agent/provider cập nhật file; ứng dụng phải hỗ trợ reload hoặc restart.
- **Environment injection:** platform inject khi process start; thường cần restart/redeploy để nhận version mới.

### 19.1. Last-known-good và fail behavior

Nếu secret manager tạm thời không khả dụng, workload có thể dùng cached secret còn hiệu lực theo policy; không nên dùng stale secret vô hạn. Với entitlement/security config có thể cần fail closed. Với branding/log format, fallback mặc định thường chấp nhận được.

Từng loại cấu hình cần xác định TTL, freshness, fail-open/fail-closed, emergency revoke semantics và cách phục hồi khi store hoạt động lại.

## 20. Drift detection và configuration audit

Drift là khác biệt giữa desired state trong IaC và actual state trên cloud. Manual console change có thể tạo cấu hình chưa review, mở public access hoặc thay secret reference.

- Chạy plan/drift detection định kỳ và trước change quan trọng.
- Ghi actor, time, resource và before/after.
- Xác định emergency hotfix hay thay đổi trái phép.
- Review impact trước khi import/reconcile.
- Tránh tự động overwrite production chỉ vì khác state.
- Cập nhật IaC source of truth sau thay đổi được phê duyệt.
- Theo dõi secret/config version thực tế workload đang dùng.

Drift detection không nên in secret value ra log/report. Dùng diff đã redact và metadata/version.

## 21. Quyền truy cập và separation of duties

| Vai trò | Quyền thường cần | Không nên mặc định có |
| --- | --- | --- |
| Developer | Đọc module, tạo PR, validate non-prod | Production secret/state và production apply |
| CI plan identity | Read API/state cần cho plan | Secret plaintext hoặc quyền phá hủy rộng |
| CI apply identity | Apply trong scope được duyệt | Admin toàn tổ chức |
| Runtime identity | Read secret cụ thể và gọi dependency | IaC state write hoặc secret administration |
| Secret rotator | Tạo version/rotate theo scope | Đọc mọi secret |
| Security operator | Audit, policy và incident response | Sử dụng credential nghiệp vụ tùy ý |
| Break-glass operator | Quyền khẩn cấp có thời hạn | Quyền thường trực không giám sát |

Approval dựa trên environment và impact. Không để cùng identity sửa policy bảo vệ, tự phê duyệt và thực thi thay đổi có thể vô hiệu policy đó.

## 22. Ví dụ end-to-end: booking service

Một booking service cần database connection, payment API và TLS certificate. IaC tạo network, compute, identity, secret reference và monitoring. Credential thực được quản lý ngoài Git.

| Thành phần | IaC quản lý | Secret/certificate system quản lý |
| --- | --- | --- |
| Database | Instance/cluster, subnet, parameter, identity policy | Password hoặc dynamic credential |
| Payment integration | Egress route, runtime permission, secret reference | Provider token/client secret |
| TLS | Load balancer listener, certificate reference | Certificate/private key/renewal |
| Application config | Non-secret env, timeout, region, feature setting | Sensitive endpoint/credential theo phân loại |
| Runtime | Service account/managed identity, deployment | Secret retrieval và refresh |

~~~mermaid
flowchart TB
    SRC["IaC source + environment config"] --> PLAN["Validate / plan"]
    PLAN --> APPROVE["Review and approve"]
    APPROVE --> APPLY["Apply infrastructure"]
    APPLY --> WI["Provision workload identity"]
    WI --> DEPLOY["Deploy application with references"]
    DEPLOY --> SM["Secret manager"]
    SM --> APP["Runtime retrieves authorized secret"]
    APP --> DB[("Database")]
~~~

Một quy trình triển khai:

1. Review module/environment config, bảo đảm không có plaintext secret.
2. Provision network, database, workload identity và secret access policy.
3. Tạo/nhập credential vào secret manager bằng quy trình riêng.
4. Cấp quyền tối thiểu cho booking workload đọc reference tương ứng.
5. Deploy ứng dụng với config non-secret và secret reference.
6. Verify workload identity, secret retrieval và database connection.
7. Bật audit/alert cho secret read và failed auth.
8. Thử rotation trong staging, xác minh refresh connection.
9. Kiểm tra IaC state, plan và CI log không chứa plaintext.
10. Thực hiện DR test để xác minh workload phục hồi vẫn truy cập key/secret theo policy.

## 23. Các lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách phòng tránh |
| --- | --- | --- |
| Commit password vào tfvars/env | Credential tồn tại trong Git history | Secret reference và scanning |
| Cho rằng env var tự an toàn | Secret lộ qua process/debug/dump | Workload identity, mount hoặc secret integration |
| Chỉ bật sensitive flag | Giá trị vẫn có thể nằm trong state/plan | Kiểm tra tool/provider, giảm secret trong IaC |
| Lưu static cloud key trong CI | Credential dài hạn, blast radius lớn | OIDC federation/short-lived identity |
| Dùng chung secret dev và production | Một môi trường bị lộ ảnh hưởng môi trường khác | Namespace/account/identity riêng |
| In env/secret trong debug log | Lộ bí mật qua log pipeline | Redaction, test log và không dump environment |
| Đưa secret vào Docker build arg | Có thể lưu trong layer/history/cache | Runtime retrieval hoặc secret mount |
| Nghĩ Kubernetes Secret base64 là encryption | Người có quyền đọc API/etcd lấy được dữ liệu | Encryption at rest và RBAC |
| State backend quyền rộng/public | Lộ resource mapping và secret trong state | Encryption, private access, least privilege |
| Đưa secret thành module output | Lan truyền plaintext sang stack khác | Output reference/metadata |
| Rotation chỉ đổi secret store | Runtime vẫn dùng connection/credential cũ | Refresh, verify, revoke sau overlap |
| Không có secret owner/expiry | Secret orphaned tồn tại vô hạn | Inventory, owner và expiry alert |
| Dùng sensitive config làm secret tùy tiện | Khó quản trị và che mất rủi ro thực | Classification theo impact |
| Drift auto-remediate không review | Ghi đè hotfix hoặc gây outage | Review diff và guarded remediation |
| Không kiểm thử DR key access | Workload phục hồi nhưng không lấy được credential | DR identity/secret/key access test |

## 24. Quy trình thiết kế và triển khai

1. **Phân loại dữ liệu:** config, sensitive config, secret, credential và key material.
2. **Định nghĩa source of truth:** nơi quản lý mỗi key, owner và precedence.
3. **Thiết kế environment boundary:** account/project, state backend, identity và secret namespace riêng.
4. **Thiết kế IaC interface:** input có schema; ưu tiên secret reference; tránh plaintext output.
5. **Thiết lập secret manager:** access policy, version, audit, expiry, rotation và recovery.
6. **Thiết kế workload identity:** trust, subject, audience và least privilege cho deploy/runtime.
7. **Bảo vệ state/plan:** encryption, lock, versioning, access control, artifact retention và log redaction.
8. **Thiết kế secret delivery:** pull, mount, injection, refresh, TTL và failure behavior.
9. **Thiết lập CI/CD guardrail:** protected branch/environment, OIDC, secret scan và policy-as-code.
10. **Thiết kế rotation/incident:** overlap, verify, revoke, leak response và evidence.
11. **Kiểm tra drift/audit:** desired vs actual config, secret version và quyền thực tế.
12. **Diễn tập:** secret leak, rotation, state recovery và runtime restore ở region khác.

## 25. Đánh giá theo Well-Architected

| Góc nhìn | Câu hỏi thiết kế |
| --- | --- |
| **Độ tin cậy** | Secret/config service có HA? Runtime refresh và last-known-good có policy? State/backup có thể phục hồi? Rotation có tránh downtime? |
| **Bảo mật** | Plaintext có ở Git/state/log/image? Identity least privilege? Environment và tenant secret có tách? Ai đọc/rotate/destroy? |
| **Hiệu quả hiệu năng** | Secret retrieval có gây latency startup/request? Cache TTL và refresh có hợp lý? IaC plan/apply có xử lý đúng phạm vi? |
| **Tối ưu chi phí** | Secret store/KMS call, state retention, log và automation cost có được quản lý? Có credential không còn dùng? |
| **Khả năng vận hành** | Có inventory/owner, audit, drift detection, expiry alert, rotation runbook, policy-as-code và DR test? |

### Checklist nghiệm thu

- [ ] Mỗi biến được phân loại là non-sensitive config, sensitive config, secret hoặc key.
- [ ] Có source of truth, owner, schema, default và precedence.
- [ ] File config/IaC commit không chứa plaintext credential/private key.
- [ ] Environment dev/staging/production có state, identity và secret scope riêng.
- [ ] Runtime/CI dùng workload identity hoặc credential ngắn hạn khi hỗ trợ.
- [ ] Secret manager policy giới hạn theo workload, environment và tenant.
- [ ] IaC sensitive marking không bị coi là encryption hoặc state redaction toàn diện.
- [ ] Remote state có encryption, locking, versioning, access control và restore test.
- [ ] Plan/state/artifact/log không public hoặc tải rộng.
- [ ] Container image không chứa secret trong layer, ARG, ENV hoặc build cache.
- [ ] Kubernetes Secret được bảo vệ bằng encryption at rest, RBAC và audit.
- [ ] Module output trả reference/metadata, không trả plaintext secret.
- [ ] Rotation có overlap, refresh, verify, revoke và audit.
- [ ] Secret leak response gồm Git history, artifact, state, log và dependent credential.
- [ ] Policy-as-code và secret scanning chạy trong CI/CD.
- [ ] Drift detection không làm lộ secret và có remediation guardrail.
- [ ] DR test xác minh workload lấy được secret/key cần thiết khi phục hồi.

## 26. Bài tập áp dụng

Một nhóm triển khai booking service bằng Terraform và Kubernetes. Repository có file production.tfvars chứa database password, API token payment provider được truyền qua CI variable, Kubernetes Secret chứa webhook signing key, và state backend lưu trong object storage. Developer có quyền đọc repository nhưng không cần production secret. Workload chạy tại hai region; rotation credential không được làm gián đoạn giao dịch.

Hãy thiết kế:

1. Phân loại từng giá trị và xác định nơi lưu phù hợp.
2. Làm thế nào loại credential khỏi Git history và xử lý như incident?
3. Thiết kế identity cho CI plan/apply và runtime workload.
4. Module Terraform nên nhận biến gì để cấu hình database và payment integration?
5. Cần kiểm tra gì để chứng minh secret không bị ghi vào state/plan?
6. Bảo vệ remote state/object storage bằng policy nào?
7. Kubernetes workload lấy webhook signing key ra sao và ai được quyền đọc?
8. Thiết kế rotation overlap và cập nhật connection pool/consumer ở hai region.
9. Nếu secret manager tạm thời không khả dụng, workload nào fail open hay fail closed?
10. Kiểm thử DR/audit nào chứng minh sau failover workload vẫn lấy đúng secret mà không mở quyền cross-environment?

Một thiết kế có cơ sở sẽ đưa plaintext khỏi repository, tạo secret mới và revoke credential đã lộ, dùng OIDC/managed identity để cấp quyền ngắn hạn, giữ reference trong IaC và để runtime lấy secret theo identity. Remote state được tách environment, mã hóa, khóa và giới hạn quyền; rotation diễn ra theo cohort với overlap và verification; DR test xác nhận key/secret access mà không sao chép credential production sang staging.

**Điểm cốt lõi:** environment variable chỉ là phương tiện truyền dữ liệu; IaC variable chỉ là giao diện cấu hình; sensitive marking không tự bảo đảm bí mật được loại khỏi state. Thiết kế an toàn tách cấu hình không nhạy cảm khỏi secret, dùng identity để cấp quyền đúng lúc, giới hạn nơi plaintext xuất hiện và quản lý rotation, audit, recovery trong toàn bộ vòng đời.
