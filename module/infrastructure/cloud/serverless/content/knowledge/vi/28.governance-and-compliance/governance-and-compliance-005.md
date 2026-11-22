# Lưu audit log và bằng chứng thay đổi cấu hình

Trong hệ thống serverless, cấu hình có thể thay đổi ở nhiều nơi: mã IaC, pipeline CI/CD, cloud console, API quản trị, runtime setting, IAM policy, API gateway, event source mapping, queue, workflow và secret manager. Một thay đổi nhỏ như mở rộng quyền của function, đổi endpoint, tăng concurrency hoặc sửa retention có thể ảnh hưởng đến bảo mật, chi phí và khả năng phục hồi. Khi có sự cố hoặc cuộc kiểm toán, nhóm cần chứng minh ai đã thay đổi điều gì, vào lúc nào, thông qua quy trình nào, thay đổi đã được phê duyệt chưa và hệ thống thực tế đã nhận cấu hình nào.

Audit log ghi lại sự kiện có ý nghĩa về bảo mật và quản trị. Bằng chứng thay đổi cấu hình tập hợp các artifact liên quan để tái dựng toàn bộ vòng đời của một thay đổi: yêu cầu, commit, plan, policy check, approval, deployment, kết quả sau triển khai và trạng thái thực tế. Hai loại dữ liệu này bổ sung cho nhau. Audit log cho biết hành động đã xảy ra; change evidence giải thích hành động đó được đề xuất, xem xét và triển khai theo quy trình nào.

Trong module **CLOUD_SERVERLESS**, người học xây dựng và triển khai Java function kích hoạt bởi HTTP, message hoặc event, đồng thời xử lý quyền truy cập, trạng thái, retry, idempotency, cold start, mở rộng và chi phí. Bài này tập trung vào việc thu thập, bảo vệ, lưu giữ và truy xuất audit log cùng bằng chứng thay đổi cấu hình trong toàn bộ vòng đời ứng dụng serverless.

## 1. Audit log khác application log như thế nào?

Application log mô tả hoạt động của ứng dụng: request được xử lý, dependency timeout, message retry hoặc workflow step hoàn tất. Audit log ghi nhận hành động cần truy vết về trách nhiệm, quyền hạn hoặc thay đổi trạng thái quan trọng.

| Loại log | Mục đích | Ví dụ |
|---|---|---|
| Application log | Chẩn đoán hành vi runtime | Function xử lý đơn hàng mất 250 ms |
| Security log | Phát hiện và điều tra sự kiện bảo mật | Đăng nhập thất bại, token bị từ chối |
| Audit log | Ghi lại ai thực hiện hành động quan trọng | Principal thay đổi IAM policy |
| Platform/control-plane log | Ghi thao tác quản trị tài nguyên cloud | Tạo function, sửa API route, xóa queue |
| Data-plane audit | Ghi truy cập hoặc thay đổi dữ liệu | Đọc object, sửa record hoặc truy vấn dữ liệu được kiểm soát |
| Change evidence | Chứng minh thay đổi đã qua quy trình nào | PR, IaC plan, approval và deployment record |

Một dòng application log như "configuration updated" không đủ làm bằng chứng kiểm toán nếu thiếu actor, resource, thời điểm, nguồn thay đổi và kết quả. Ngược lại, audit log của cloud provider có thể cho biết API quản trị đã được gọi nhưng không giải thích vì sao thay đổi được chấp thuận hoặc commit nào tạo ra thay đổi đó.

Không dùng application log thay cho audit trail của provider. Ứng dụng có thể bị lỗi, bị sửa hoặc bị chiếm quyền; control-plane audit do nền tảng cloud ghi nhận là một nguồn bằng chứng độc lập hơn cho các thao tác quản trị.

## 2. Hai mặt cần quan sát: control plane và data plane

**Control plane** là nơi quản lý tài nguyên và cấu hình: tạo function, đổi runtime, cập nhật IAM, sửa gateway, thay đổi queue mapping hoặc cấu hình workflow.

**Data plane** là nơi xử lý dữ liệu và request: gọi API, đọc/ghi object, nhận message, truy vấn database hoặc thực thi business operation.

Một hệ thống chỉ bật audit cho control plane có thể biết ai đổi policy nhưng không biết dữ liệu được truy cập bởi principal nào. Chỉ audit data plane lại có thể bỏ sót ai đã thay đổi quyền để cho phép truy cập. Cần xác định cả hai lớp theo rủi ro và yêu cầu tuân thủ.

~~~mermaid
flowchart TD
    A[Human / CI identity] --> B[Cloud control plane]
    B --> C[Function, API, IAM, queue, workflow config]
    D[Client / event producer] --> E[Serverless data plane]
    E --> F[Function and data services]
    B --> G[Control-plane audit]
    E --> H[Data-plane audit]
    C --> I[Change evidence]
    F --> J[Application audit events]
    G --> K[Central audit archive]
    H --> K
    J --> K
    I --> L[Evidence repository]
    K --> M[Search, alert and investigation]
    L --> M
~~~

Không phải dịch vụ nào cũng cung cấp cùng mức audit cho data plane. Có thể cần bật riêng data access logging, database audit extension, object-level event hoặc application-level audit event. Hãy kiểm tra coverage theo từng resource và service tier.

## 3. Mục tiêu của một audit trail đáng tin cậy

Một audit trail nên hỗ trợ các mục tiêu sau:

- **Accountability:** xác định principal hoặc service identity thực hiện hành động.
- **Traceability:** liên kết hành động với request, ticket, commit, deployment hoặc workflow.
- **Integrity:** phát hiện hoặc ngăn sửa/xóa log trái phép.
- **Completeness:** ghi đủ sự kiện quan trọng trong phạm vi đã định.
- **Availability:** có thể truy xuất bằng chứng khi cần điều tra.
- **Confidentiality:** giới hạn ai được đọc audit log và dữ liệu nhạy cảm.
- **Time accuracy:** timestamp có thể đối chiếu giữa nhiều hệ thống.
- **Retention:** lưu đủ thời gian theo policy và nghĩa vụ áp dụng.
- **Non-repudiation support:** có nguồn ghi độc lập, chữ ký hoặc cơ chế bảo vệ phù hợp để tăng độ tin cậy về nguồn gốc.

Không có một cấu hình logging đơn lẻ bảo đảm mọi mục tiêu. Chất lượng audit phụ thuộc vào coverage, identity, quyền ghi/xóa, đồng bộ thời gian, bảo vệ archive và quy trình vận hành.

## 4. Các trường cần có trong audit event

Một audit event thường cần trả lời: ai làm, làm gì, trên tài nguyên nào, khi nào, từ đâu, vì sao và kết quả ra sao.

| Field | Ý nghĩa | Ví dụ |
|---|---|---|
| event.id | ID duy nhất của audit event | aud-7f12 |
| event.time | Thời điểm event xảy ra theo UTC | 2026-11-17T10:15:30Z |
| event.type | Nhóm sự kiện | config.change |
| action | Hành động cụ thể | UpdateFunctionConfiguration |
| actor.id | Principal/user/service identity | ci-deployer-prod |
| actor.type | Loại actor | human, service, workload |
| actor.session | Session/assumed role reference | session-82 |
| source.ip | IP nguồn nếu có và được phép lưu | 203.0.113.10 |
| source.user_agent | Client/tool đã gọi API | terraform/1.x |
| resource.id | ID/ARN/URI tài nguyên | function/orders-api |
| resource.type | Loại tài nguyên | serverless.function |
| environment | Môi trường | production |
| region | Region | ap-southeast-1 |
| change.id | ID yêu cầu thay đổi | CHG-2048 |
| request.id | ID request do provider cấp | req-91a |
| correlation.id | ID liên kết workflow thay đổi | corr-31 |
| outcome | Kết quả | success, denied, failure |
| reason | Lý do/ticket/reference | approved release |
| before/after | Giá trị cấu hình đã lọc hoặc digest | timeout 20 → 30 |
| source | Nguồn phát sinh | cloud.audit, pipeline, app |

Không phải mọi provider đều trả đủ field. Ghi rõ field nào do provider cung cấp, field nào được enrichment bởi pipeline và field nào không có. Không tự suy đoán actor từ địa chỉ IP hoặc user agent.

### Ví dụ audit event JSON

~~~json
{
  "schema_version": 1,
  "event": {
    "id": "aud-7f12",
    "time": "2026-11-17T10:15:30.123Z",
    "type": "configuration.change",
    "action": "UpdateFunctionConfiguration",
    "outcome": "success"
  },
  "actor": {
    "id": "ci-deployer-prod",
    "type": "workload",
    "session": "deploy-run-581"
  },
  "resource": {
    "id": "function/orders-api",
    "type": "serverless.function",
    "environment": "production",
    "region": "ap-southeast-1"
  },
  "change": {
    "id": "CHG-2048",
    "commit": "9c31e4a",
    "before_digest": "sha256:abc...",
    "after_digest": "sha256:def..."
  },
  "source": {
    "system": "cloud-control-plane",
    "request_id": "req-91a"
  },
  "correlation_id": "corr-31"
}
~~~

Ví dụ này minh họa schema chung, không phải định dạng nguyên bản của một cloud provider. Khi ingest, giữ bản ghi gốc hoặc lưu source event reference để không làm mất dữ liệu cần thiết cho điều tra.

## 5. Identity: ghi đúng actor, không chỉ ghi tên người

Actor có thể là:

- Người dùng đăng nhập qua SSO.
- Role được assume bởi một người.
- Service account hoặc workload identity của CI/CD.
- Cloud service principal thực hiện thao tác thay mặt ứng dụng.
- Automation hoặc controller.
- Break-glass identity dùng trong sự cố.

Với assumed role hoặc federated identity, cần giữ được chuỗi liên kết từ session đến principal gốc nếu provider cung cấp. Một event chỉ ghi role name có thể không đủ phân biệt người hoặc pipeline nào đã assume role đó.

Các thực hành tốt:

- Dùng SSO/federation và identity riêng cho từng pipeline.
- Không chia sẻ access key hoặc service account giữa nhiều team.
- Giữ session name/run ID có thể liên kết với CI job.
- Phân biệt actor là human, workload hay provider service.
- Ghi nguồn xác thực và session reference khi có.
- Dùng quyền tối thiểu; audit không thay thế authorization.
- Theo dõi cả việc tạo credential, đổi trust policy và cấp quyền assume role.

Không đưa access token, refresh token, private key hoặc secret vào audit event. Actor ID cần đủ để điều tra nhưng không nên chứa dữ liệu xác thực.

## 6. Nguồn audit từ cloud provider

Các cloud provider có dịch vụ audit/control-plane riêng. Tên, phạm vi và mặc định bật/tắt khác nhau; phải xác nhận đúng loại event, Region, resource và data access coverage.

| Nền tảng | Nguồn audit phổ biến | Điểm cần chú ý |
|---|---|---|
| AWS | CloudTrail management events và data events | Chọn trail, Region, account, resource-level data events và nơi lưu |
| Azure | Azure Activity Log và resource-specific diagnostic logs | Activity Log tập trung vào control plane; data-plane logs thường cần cấu hình riêng |
| Google Cloud | Cloud Audit Logs: Admin Activity, Data Access, System Event, Policy Denied | Kiểm tra Data Access logging, dịch vụ được hỗ trợ và cấu hình project/folder/org |

### AWS CloudTrail

CloudTrail ghi lại hoạt động API của AWS account. Management events bao gồm nhiều thao tác quản trị như tạo, sửa hoặc xóa resource. Data events ghi một số hoạt động truy cập dữ liệu, ví dụ object-level access hoặc function invocation tùy dịch vụ và cấu hình.

Không mặc định rằng mọi data event đều được ghi miễn phí hoặc đã bật cho mọi resource. Chọn event selector phù hợp, kiểm tra chi phí và xác minh event xuất hiện trong trail. Với nhiều account, cân nhắc organization trail hoặc central logging account theo kiến trúc quản trị.

### Azure Activity Log

Azure Activity Log ghi lại các hoạt động ở control plane của subscription, như tạo hoặc cập nhật resource và thay đổi cấu hình quản trị. Để audit data plane, thường cần diagnostic settings hoặc log riêng của dịch vụ như storage, database hoặc API.

Có thể route Activity Log đến Log Analytics workspace, storage account hoặc event hub theo nhu cầu lưu trữ và phân tích. Phạm vi retention và export cần được cấu hình, không giả định một nơi lưu tự đáp ứng mọi yêu cầu.

### Google Cloud Audit Logs

Google Cloud phân loại audit log thành Admin Activity, Data Access, System Event và Policy Denied. Data Access logs cần được bật/kiểm tra theo dịch vụ và policy; không mặc định tất cả thao tác đọc dữ liệu đều được lưu trong mọi project. Có thể cấu hình sink ở project, folder hoặc organization để tập trung log vào destination phù hợp.

Tên category và mức độ hỗ trợ phụ thuộc dịch vụ. Lập inventory các resource quan trọng rồi xác nhận event thực tế bằng test, thay vì chỉ dựa vào trạng thái cấu hình.

## 7. Lập inventory audit coverage cho serverless

Để tránh khoảng trống, lập danh sách tài nguyên và hành động cần audit.

| Thành phần | Thay đổi cần theo dõi | Truy cập cần theo dõi |
|---|---|---|
| Java function | Runtime, handler, memory, timeout, environment, concurrency, code version | Invocation hoặc data access nếu có yêu cầu |
| IAM role/policy | Attach/detach policy, trust policy, permission boundary | Assume role, denied action |
| API gateway | Route, authorizer, stage, throttling, custom domain | Request/access log theo policy |
| Queue/topic | Policy, encryption, retention, DLQ, redrive config | Send/receive/delete hoặc publish/subscribe |
| Event source mapping | Batch size, retry, filter, enabled state, concurrency | Poll/consume nếu service hỗ trợ |
| Workflow | Definition, role, timeout, retry, state machine version | Start/stop/approve/execute và business audit |
| Storage | Bucket/container policy, encryption, lifecycle, public access | Read/write/delete/list theo data classification |
| Database | Network, parameter, backup, role, audit config | Query/write hoặc privileged access |
| KMS/secret manager | Key policy, rotation, grants, secret version | Decrypt, read secret, rotate |
| Network | VPC, subnet, route, security group, endpoint | Flow logs hoặc network security events |
| Logging platform | Trail configuration, sink, retention, access policy | Search, export, delete, retention change |

Không cần bật mọi data access log cho mọi tài nguyên. Chọn theo độ nhạy cảm, rủi ro và yêu cầu pháp lý; data-plane logging có thể tạo volume và chi phí lớn.

### Audit chính cấu hình audit

Một điểm quan trọng là phải ghi lại việc thay đổi chính audit pipeline:

- Tắt hoặc xóa trail/log sink.
- Thay event selector để bỏ qua data event.
- Hạ retention hoặc tắt archive.
- Thay bucket/container policy.
- Thay đổi cấu hình Object Lock/retention hoặc thử xóa đối tượng đang được khóa.
- Đổi KMS key/policy hoặc thu hồi quyền decrypt.
- Cấp quyền đọc/xóa audit archive.
- Thay đổi alert hoặc export destination.

Nếu attacker có thể tắt audit mà không bị phát hiện, các log còn lại sẽ không đủ để chứng minh khoảng trống đó.

## 8. Ghi nhận thay đổi cấu hình trong Java serverless

Cloud audit ghi nhận thao tác control plane. Ứng dụng vẫn có thể cần business audit event cho các thay đổi nghiệp vụ được thực hiện qua function, ví dụ:

- Người dùng thay đổi thông tin tài khoản.
- Nhân viên phê duyệt hoàn tiền.
- Workflow đổi trạng thái đơn hàng.
- Quản trị viên thay đổi cấu hình tenant trong ứng dụng.
- Một service thay đổi policy nghiệp vụ hoặc feature flag.

Business audit event cần actor đã được xác thực, action, target, kết quả và reference đến request/change. Không ghi event chỉ vì một log message được phát ra; audit event cần schema ổn định và đường lưu bền vững.

### Ví dụ Java audit record

~~~java
public record AuditEvent(
        String eventId,
        Instant occurredAt,
        String actorId,
        String actorType,
        String action,
        String resourceType,
        String resourceId,
        String outcome,
        String requestId,
        String correlationId,
        String changeReference) {
}
~~~

Một service có thể tạo event từ identity context đã được xác thực:

~~~java
public void updateTenantLimit(
        AuthenticatedPrincipal principal,
        String tenantId,
        int newLimit,
        String requestId) {

    transaction(() -> {
        tenantRepository.updateLimit(tenantId, newLimit);

        auditOutboxRepository.insert(new AuditEvent(
            UUID.randomUUID().toString(),
            Instant.now(),
            principal.subject(),
            "human",
            "tenant.limit.updated",
            "tenant",
            tenantId,
            "success",
            requestId,
            currentCorrelationId(),
            currentChangeReference()
        ));
    });
}
~~~

Đây là pseudocode; tenant update và outbox insert phải cùng một database transaction để không có trạng thái nghiệp vụ đã commit nhưng thiếu audit event. Dispatcher đọc outbox rồi gửi đến archive, retry an toàn và deduplicate theo eventId. Identity phải đến từ token/session đã được xác minh, không lấy actorId trực tiếp từ request body. Nếu cần before/after, chỉ ghi giá trị không nhạy cảm hoặc digest đã chuẩn hóa theo policy.

### Tránh mất audit event khi function crash

Nếu cập nhật nghiệp vụ thành công nhưng function crash trước khi gửi audit event, hệ thống có thể thiếu bằng chứng. Nếu ghi audit trước rồi business transaction rollback, log lại mô tả một thay đổi chưa xảy ra.

Với database hỗ trợ transaction, có thể ghi business update và audit/outbox record trong cùng transaction. Một dispatcher gửi outbox đến audit archive sau đó. Dispatcher cần retry và idempotency; archive cần giữ event ID để loại duplicate khi ingest.

Nếu audit event phải nằm ngoài transaction nghiệp vụ, xác định rõ guarantee, retry, dead-letter và reconciliation. Không chỉ gọi một HTTP endpoint logging rồi giả định event đã được lưu bền vững.

## 9. Bằng chứng thay đổi cấu hình là một gói, không phải một dòng log

Một thay đổi production nên có một evidence package gắn cùng change ID. Gói này có thể gồm:

- Change request hoặc ticket và lý do thay đổi.
- Người yêu cầu, owner và reviewer.
- Pull request, commit SHA và branch/tag.
- File IaC hoặc application config đã thay đổi.
- Saved plan hoặc diff trước khi apply.
- Policy/security scan result.
- Approval record và thời điểm approve.
- CI/CD run ID, runner identity và environment.
- Artifact digest, image digest hoặc package checksum.
- Deployment record và provider request/operation ID.
- Before/after configuration snapshot đã loại secret.
- Post-deploy verification, smoke test và health result.
- Drift scan hoặc reconciliation sau triển khai.
- Rollback record nếu deployment bị revert.

Audit log của provider chứng minh API quản trị đã được gọi. Evidence package nối sự kiện đó với commit, plan và approval để reviewer có thể trả lời vì sao thay đổi được thực hiện.

## 10. Quy trình change management cho IaC

Một pipeline thay đổi hạ tầng nên có các bước có thể truy vết:

~~~mermaid
flowchart TD
    A[Change request] --> B[Pull request / commit]
    B --> C[Format, validate and scan]
    C --> D[Generate IaC plan]
    D --> E[Policy and security checks]
    E --> F[Human approval]
    F --> G[Apply reviewed plan]
    G --> H[Provider control-plane audit]
    G --> I[Deployment evidence]
    H --> J[Central audit archive]
    I --> K[Evidence repository]
    K --> L[Post-deploy verification]
    L --> M[Drift / reconciliation]
~~~

Mỗi bước nên tạo record có change ID, commit SHA, pipeline run ID và resource/environment liên quan. Approval phải gắn với đúng plan hoặc commit được áp dụng. Nếu plan được tạo lại sau approval, nội dung có thể khác; cần review lại theo policy.

### Plan evidence

Với Terraform/OpenTofu, saved plan có thể giúp apply đúng nội dung đã review. Tuy nhiên plan file có thể chứa dữ liệu nhạy cảm. Không đưa plan lên artifact public hoặc repository. Lưu trong artifact store có quyền truy cập hạn chế, retention ngắn và audit download.

Lưu thêm plan digest, commit SHA, backend/workspace, provider version, timestamp và reviewer reference. Digest chứng minh file được so sánh không bị thay đổi sau khi tạo; nó không chứng minh plan an toàn hay đúng.

## 11. Ghi nhận before/after configuration

Một bản snapshot cấu hình giúp so sánh trạng thái trước và sau thay đổi. Cần chuẩn hóa trước khi tạo digest để tránh khác biệt không có ý nghĩa như thứ tự key hoặc formatting.

Một evidence record có thể lưu:

~~~json
{
  "change_id": "CHG-2048",
  "resource": "function/orders-api",
  "config_version_before": "cfg-104",
  "config_version_after": "cfg-105",
  "before_digest": "sha256:abc123...",
  "after_digest": "sha256:def456...",
  "changed_fields": [
    "timeout",
    "memory_size"
  ],
  "secret_values_included": false,
  "captured_at": "2026-11-17T10:15:30Z"
}
~~~

Không lưu secret value trong snapshot. Với environment variable chứa credential, chỉ ghi tên biến, trạng thái có thay đổi hay không và secret version/reference nếu policy cho phép. Không hash secret đơn giản rồi công khai digest nếu giá trị có entropy thấp; digest có thể hỗ trợ dò từ điển.

### Cấu hình được provider chuẩn hóa

Provider có thể trả cấu hình khác cách biểu diễn trong IaC do default, computed field hoặc normalization. Snapshot cần phân biệt desired config, submitted request và observed config sau deploy. Nếu gộp ba loại này, reviewer có thể hiểu nhầm một giá trị default là thay đổi thủ công.

## 12. Chứng minh nguồn gốc artifact và deployment

Đối với Java function, cần liên kết artifact đã deploy với source code và pipeline:

- Repository và commit SHA.
- Build job/run ID.
- Java version, build tool và dependency lock/version.
- Artifact filename và SHA-256 digest.
- Container image digest nếu dùng image.
- SBOM và kết quả vulnerability scan nếu quy trình yêu cầu.
- Signing/attestation metadata nếu tổ chức áp dụng.
- Function version, alias hoặc deployment revision.
- Provider deployment/request ID.

Tag như latest không đủ chứng minh artifact nào đang chạy. Dùng immutable digest hoặc version ID. Nếu function alias trỏ sang version mới, lưu cả alias update event và version digest.

Artifact signature hoặc provenance attestation có thể chứng minh artifact được tạo bởi pipeline/identity đã khai báo. Nó không tự chứng minh source code an toàn hoặc approval hợp lệ; cần kết hợp build isolation, review và policy.

## 13. Approval và separation of duties

Với thay đổi nhạy cảm, người đề xuất không nên tự phê duyệt và tự triển khai nếu policy yêu cầu separation of duties.

Một ma trận đơn giản:

| Vai trò | Quyền điển hình | Bằng chứng |
|---|---|---|
| Requester | Tạo change request | Ticket/PR author |
| Developer | Thay đổi code/IaC | Commit, PR diff |
| Reviewer | Review nội dung và rủi ro | Review decision |
| Approver | Chấp thuận production change | Approval event |
| CI deployer | Thực thi plan/artifact | Workload identity, run ID |
| Auditor | Đọc evidence | Access audit |
| Security/admin | Quản trị policy và audit system | Privileged action audit |

Không dùng một credential chung cho developer và CI deployer. Pipeline production nên dùng workload identity riêng, quyền ngắn hạn và chỉ có quyền trên scope cần thiết.

Approval phải gắn với đúng tài nguyên, environment, artifact/plan và thời hạn. Một approval chung cho mọi commit hoặc một nút approve không lưu danh tính sẽ không đủ bằng chứng.

## 14. Lưu trữ audit log tập trung và tách quyền

Không nên để audit log chỉ nằm trong cùng account/project mà workload đang được quản lý. Nếu account production bị chiếm quyền, attacker có thể xóa cả tài nguyên lẫn bằng chứng.

Một mô hình phổ biến:

- Mỗi account/project/subscription phát audit event.
- Event được chuyển đến central logging account/project hoặc storage riêng.
- Producer chỉ có quyền ghi vào destination được chỉ định.
- Nhóm điều tra có quyền đọc/search.
- Quyền xóa, thay đổi retention và quản trị key thuộc một role tách biệt.
- Backup/archive có bản sao ở failure domain khác.
- Alert phát hiện thay đổi policy hoặc ngừng delivery.

~~~mermaid
flowchart LR
    A[Production accounts] --> B[Audit trail / diagnostic export]
    C[CI/CD systems] --> D[Change evidence]
    E[Identity provider] --> F[Sign-in audit]
    B --> G[Central logging account]
    D --> H[Evidence repository]
    F --> G
    G --> I[Immutable archive]
    G --> J[Search and SIEM]
    H --> K[Change review]
    I --> L[Investigation / audit]
    J --> L
    K --> L
~~~

Central archive cần tách biệt quyền quản trị với workload. Một role có thể ghi log nhưng không được đọc/xóa; role điều tra được đọc nhưng không được sửa retention; role quản trị archive cần approval và audit riêng.

## 15. Bảo vệ tính toàn vẹn: append-only, WORM và hash

Audit log có giá trị khi người có quyền quản trị hệ thống không thể âm thầm sửa hoặc xóa bằng chứng.

Các cơ chế thường dùng:

- **Append-only access:** producer chỉ được thêm record, không được overwrite/delete.
- **WORM/immutable retention:** object hoặc log được khóa không thể sửa/xóa trong thời hạn đã đặt, theo khả năng dịch vụ.
- **Versioning:** giữ phiên bản object để phục hồi và điều tra.
- **Hash/digest:** tạo fingerprint để phát hiện nội dung thay đổi.
- **Digital signature:** ký event hoặc manifest bằng key được kiểm soát.
- **Hash chain:** mỗi record/segment tham chiếu digest của phần trước để phát hiện thay đổi thứ tự hoặc nội dung.
- **Independent copy:** sao chép sang account hoặc security boundary khác.

Hash đơn lẻ không ngăn attacker thay cả file và digest. Nếu dùng hash chain, anchor hoặc manifest cần được ký/lưu ở một trust boundary độc lập. WORM cũng cần policy, retention và key management đúng; nếu một admin có thể xóa cả archive hoặc key thì bằng chứng vẫn có thể mất.

### WORM và legal hold

WORM/immutable storage thường có chế độ retention theo thời gian hoặc legal hold. Retention lock có thể không thể rút ngắn sau khi bật. Chọn thời hạn theo policy được phê duyệt và nghĩa vụ pháp lý; không đặt thời hạn dài vô hạn theo mặc định.

Legal hold có thể ngăn xóa bằng chứng liên quan đến điều tra hoặc tranh chấp. Cần quy trình ai được tạo/gỡ hold, lý do, phạm vi và audit của chính thao tác đó.

## 16. Encryption và quản lý key

Audit log thường chứa actor, resource ID, IP, request metadata và chi tiết thay đổi. Dù không chứa secret, đây vẫn là dữ liệu nhạy cảm.

Bảo vệ bằng:

- TLS khi truyền giữa producer, collector và archive.
- Encryption at rest cho log store và evidence repository.
- KMS/customer-managed key khi yêu cầu kiểm soát key riêng.
- Key policy tách biệt với quyền ghi log.
- Rotation và audit thao tác key.
- Backup key metadata và kiểm tra khả năng decrypt khi DR.
- Hạn chế quyền export/decrypt cho người điều tra theo nhiệm vụ.

Nếu key bị disable hoặc xóa, archive có thể không đọc được. DR plan phải bao gồm key, policy, grant và quy trình phục hồi quyền giải mã.

## 17. Retention, legal hold và privacy

Retention phải cân bằng nhu cầu điều tra, yêu cầu tuân thủ, chi phí và quyền riêng tư. Không có một thời hạn phù hợp cho mọi loại log.

Có thể phân loại:

| Nhóm | Ví dụ | Chính sách retention cần xác định |
|---|---|---|
| Security audit | Privileged action, denied access | Theo policy security/compliance |
| Control-plane audit | Resource create/update/delete | Theo yêu cầu quản trị và điều tra |
| Data access audit | Đọc/ghi dữ liệu nhạy cảm | Theo classification và nghĩa vụ áp dụng |
| Application audit | Thay đổi nghiệp vụ quan trọng | Theo vòng đời nghiệp vụ và tranh chấp |
| Operational logs | Debug, duration, dependency error | Thường ngắn hơn audit evidence |
| Change evidence | PR, approval, plan digest, deployment | Theo change policy và audit window |

Không tự đặt một thời hạn pháp lý chung. Legal/compliance owner cần xác định yêu cầu theo ngành, khu vực và loại dữ liệu.

### Data minimization

Audit không phải lý do để lưu toàn bộ request body hoặc secret. Chỉ giữ dữ liệu cần để chứng minh hành động:

- Actor ID và role/session reference.
- Resource ID và action.
- Thời điểm và kết quả.
- Change/ticket/commit reference.
- Before/after fields không nhạy cảm hoặc digest.
- Request/trace ID cần thiết cho liên kết.

IP, user agent và tenant identifier cũng có thể là dữ liệu cá nhân hoặc nhạy cảm. Xác định mục đích, quyền truy cập và retention cho các field này.

### Xóa và legal hold

Khi hết retention, xóa theo lifecycle đã được phê duyệt và ghi lại kết quả. Nếu dữ liệu đang chịu legal hold, quy trình xóa phải tạm dừng theo phạm vi hold. Xem cả bản sao, index, export, archive và backup; xóa một dashboard không đồng nghĩa dữ liệu đã bị xóa khỏi hệ thống.

## 18. Đồng bộ thời gian và thứ tự sự kiện

Điều tra thay đổi qua nhiều hệ thống cần timestamp đáng tin cậy. Dùng UTC và giữ độ chính xác phù hợp. Đồng bộ clock bằng dịch vụ time synchronization của nền tảng hoặc NTP được quản lý.

Các điểm cần lưu ý:

- Event time: thời điểm hành động xảy ra ở nguồn.
- Ingest time: thời điểm collector nhận event.
- Archive time: thời điểm ghi vào kho lưu trữ.
- Provider request ID: giúp tra cứu event gốc.
- Sequence/version: giúp xác định thứ tự khi timestamp trùng hoặc clock lệch.

Không sắp xếp mọi event chỉ theo timestamp ingest vì event có thể đến trễ hoặc được retry. Giữ cả event time và ingest time; dùng sequence/request ID khi provider cung cấp.

Nếu clock lệch, một deployment có thể xuất hiện trước approval trong log dù thực tế không phải vậy. Theo dõi clock skew và ghi timezone rõ ràng.

## 19. Delivery reliability và phát hiện audit gap

Audit event có thể không đến archive do network, quota, collector failure, permission hoặc cấu hình sai. Cần giám sát chính pipeline audit:

- Trail/diagnostic export đang bật.
- Last successful delivery time.
- Delivery error và throttling.
- Destination bucket/container/topic còn tồn tại.
- Storage quota và encryption key hoạt động.
- Collector backlog và dead-letter.
- Event volume bất thường giảm về 0.
- Chênh lệch giữa provider event count và archive ingest count nếu có số liệu đối chiếu.

Không phải nguồn audit nào cũng bảo đảm delivery tức thời. Xác định SLA/latency và cách xử lý event trễ. Nếu một khoảng thời gian không có event, phân biệt "không có hoạt động" với "audit pipeline ngừng hoạt động" bằng heartbeat hoặc health signal độc lập khi phù hợp.

### Reconciliation

Định kỳ đối chiếu:

1. Control-plane event source.
2. Central collector/stream.
3. Archive object/index.
4. Change/deployment records.
5. Resource inventory hoặc drift scan.

Mục tiêu là phát hiện event thiếu, duplicate, resource chưa được quản lý hoặc thay đổi không có change reference. Reconciliation không thay thế nguồn audit gốc nhưng giúp tìm khoảng trống.

## 20. Alert cho thay đổi cấu hình rủi ro cao

Không cần alert mọi update nhỏ. Tập trung vào hành động có thể thay đổi security boundary, availability hoặc khả năng lưu bằng chứng.

Ví dụ rule:

- IAM policy cấp quyền wildcard hoặc quyền admin.
- Trust policy cho phép principal mới assume role.
- Public access được bật cho bucket/API/database.
- Function runtime hoặc artifact thay đổi ngoài pipeline.
- Function environment/config chứa biến mới hoặc bị sửa ngoài change window.
- Event source mapping bị disable hoặc đổi retry/batch.
- Queue policy, DLQ hoặc retention bị thay đổi.
- Workflow definition/role/timeout thay đổi.
- KMS key bị disable, policy thay đổi hoặc grant mới.
- Audit trail, sink, retention, object lock hoặc lifecycle bị sửa.
- Người dùng cấp quyền đọc/xóa audit archive.
- Production resource thay đổi nhưng không có change ID/commit/approval tương ứng.

Alert nên bao gồm actor, action, resource, environment, Region, request ID và link đến evidence. Không gửi secret hoặc payload trong notification.

### Correlate với change window

Khi nhận control-plane event, tìm change ID hoặc deployment run tương ứng. Nếu không tìm thấy approval hoặc commit reference, tạo alert để điều tra. Một thao tác ngoài pipeline không nhất thiết là độc hại; có thể là break-glass hoặc thay đổi khẩn cấp, nhưng phải có ticket và post-incident review.

## 21. Phát hiện drift và thay đổi ngoài quy trình

Audit trail cho biết thao tác đã xảy ra; drift detection so sánh cấu hình mong muốn với trạng thái thực tế.

Ví dụ:

- IaC quy định function timeout 30 giây.
- Một người sửa console thành 60 giây.
- Cloud audit ghi nhận API update và actor.
- Plan/refresh phát hiện observed config khác desired config.
- Change evidence không có PR hoặc approval.
- Security alert phân loại đây là thay đổi ngoài quy trình.

Quy trình xử lý:

1. Xác định resource, Region, actor và thời điểm.
2. Tìm request ID và event gốc từ provider.
3. Đối chiếu PR, commit, plan, approval và deployment.
4. Xác định thay đổi là hotfix được phép, automation hợp lệ hay hành động trái phép.
5. Chọn rollback hoặc cập nhật IaC để codify thay đổi đã được duyệt.
6. Chạy plan/reconciliation sau xử lý.
7. Lưu incident/change record và bằng chứng liên quan.

Không tự động revert mọi drift ngay khi phát hiện. Một hotfix có thể đang bảo vệ hệ thống; cần đánh giá tác động và approval trước khi thay đổi lại.

## 22. Break-glass và emergency change

Break-glass là quyền truy cập khẩn cấp dùng khi quy trình thông thường không đáp ứng được sự cố. Vì quyền này thường cao, audit phải đặc biệt chặt.

Yêu cầu nên có:

- Identity riêng, không dùng tài khoản chung.
- MFA hoặc cơ chế xác thực mạnh.
- Just-in-time access và thời hạn ngắn.
- Lý do và incident/change reference bắt buộc.
- Alert ngay khi quyền được kích hoạt.
- Ghi lại command/API operation và resource bị thay đổi.
- Review độc lập sau sự cố.
- Thu hồi quyền khi hết thời hạn.
- Reconcile thay đổi thủ công về IaC và baseline.

Không chặn mọi hành động khẩn cấp chỉ vì thiếu PR trước đó. Nhưng phải có quy trình hậu kiểm, ghi nhận người phê duyệt theo cơ chế incident và bổ sung evidence sau khi hệ thống ổn định.

## 23. Truy vấn audit và dựng evidence package

Một cuộc điều tra thường cần trả lời các câu hỏi:

- Ai thay đổi resource X trong production trong khoảng thời gian T?
- IAM policy nào đã được sửa và actor nào thực hiện?
- Function version nào đang chạy sau deployment?
- Thay đổi có PR, approval và plan tương ứng không?
- Ai đã đọc/export audit archive?
- Audit trail có bị disable hoặc retention bị giảm không?
- Secret/key nào được rotate và workload nào bị ảnh hưởng?
- Thay đổi có gây drift hoặc sự cố không?

Một evidence package có thể gồm:

~~~text
CHG-2048/
  request-and-risk.md
  pull-request-reference.json
  commit-and-build.json
  artifact-digest.json
  iac-plan-digest.json
  policy-results.json
  approval-record.json
  deployment-record.json
  provider-audit-events/
  before-after-config.json
  post-deploy-verification.json
  drift-reconciliation.json
  incident-or-rollback.json
  manifest.sha256
~~~

Đây là cấu trúc minh họa. Không nhất thiết lưu mọi file plan nguyên bản trong cùng package nếu chúng chứa secret. Có thể lưu reference, digest và quyền truy xuất tới artifact store bảo mật.

### Manifest và digest

Manifest ghi tên artifact, digest, nguồn, thời điểm và change ID. Digest giúp phát hiện file bị thay đổi sau khi thu thập. Nếu yêu cầu assurance cao, ký manifest và lưu chữ ký ở trust boundary độc lập. Ghi rõ thuật toán hash, key/signing identity và cách xác minh.

## 24. Bảo vệ quyền truy cập audit archive

Audit archive là mục tiêu có giá trị cao. Phân tách quyền:

| Role | Quyền nên có | Không nên có |
|---|---|---|
| Audit writer | Ghi/append event | Xóa, sửa, giảm retention |
| Collector | Đọc source, ghi archive | Quản trị key và policy archive |
| Investigator | Search/read/export theo phạm vi | Sửa/xóa log |
| Compliance reviewer | Đọc evidence được cấp | Thay đổi source hoặc retention |
| Archive administrator | Quản lý retention/key theo approval | Tự xóa evidence mà không audit |
| Workload developer | Đọc application log theo policy | Đọc toàn bộ control-plane/security audit |

Dùng role tách biệt và approval cho thao tác nhạy cảm. Audit cả hoạt động truy cập audit archive: search, export, download, permission change, retention change và deletion attempt.

## 25. Kiểm thử audit coverage và integrity

Không chỉ kiểm tra file log tồn tại. Cần xác nhận đúng event được tạo, đầy đủ field, đi đến archive và không thể bị sửa/xóa ngoài policy.

Test matrix:

| Kịch bản | Kiểm tra | Kết quả mong đợi |
|---|---|---|
| Tạo function | Control-plane event | Có actor, resource, action và time |
| Đổi IAM policy | Audit event và alert | Ghi được policy change, actor và request ID |
| Sửa API route | Event liên kết change ID | Có PR/approval/deployment reference |
| Gọi data plane | Data access event nếu được bật | Có principal/resource/action theo coverage |
| Thay đổi ngoài IaC | Audit + drift scan | Phát hiện và tìm được actor |
| Deploy từ CI | Workload identity và run ID | Liên kết commit, artifact digest và provider event |
| Break-glass | Privileged audit | Alert, incident reference và post-review |
| Disable trail | Audit config event | Alert ngoài chính pipeline bị thay đổi |
| Xóa archive | Retention/Object Lock test | Bị từ chối hoặc tạo alert theo policy |
| Collector outage | Delivery health | Phát hiện gap và có replay/reconciliation |
| Clock skew | Timestamp comparison | Phát hiện lệch thời gian |
| Restore evidence | Archive restore | Có thể đọc và xác minh digest/signature |

Test trên môi trường an toàn với dữ liệu giả. Không thử xóa archive production hoặc thay đổi audit trail thật nếu chưa có phạm vi và phê duyệt phù hợp.

## 26. Quy trình phản ứng khi audit trail bị gián đoạn

Nếu phát hiện audit log không được ghi hoặc archive không nhận event:

1. Xác định thời điểm bắt đầu và phạm vi account/project/Region/service.
2. Bảo toàn log source, collector state, queue backlog và error diagnostics.
3. Kiểm tra permission, destination, key, quota, network và cấu hình trail.
4. Khôi phục delivery bằng change được phê duyệt.
5. Replay event còn trong buffer/stream nếu nguồn hỗ trợ.
6. Đối chiếu control-plane event với provider history, deployment records và resource inventory.
7. Xác định khoảng trống không thể khôi phục.
8. Ghi incident, tác động và risk acceptance nếu cần.
9. Thêm alert/health check để phát hiện sớm.
10. Kiểm tra các thay đổi xảy ra trong khoảng audit gap bằng nguồn độc lập.

Không tự tạo event giả để lấp khoảng trống. Nếu phải dựng timeline từ nguồn khác, đánh dấu nguồn, mức độ tin cậy và phần suy luận rõ ràng.

## 27. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách tránh |
|---|---|---|
| Chỉ lưu application log | Bỏ sót thao tác quản trị cloud | Bật control-plane audit |
| Chỉ bật control-plane audit | Không biết ai truy cập dữ liệu | Xác định data-plane audit cần thiết |
| Dùng chung role ghi và xóa log | Attacker có thể xóa bằng chứng | Tách writer, reader và archive admin |
| Lưu audit trong cùng account workload | Sự cố account có thể phá cả bằng chứng | Central archive ở security boundary khác |
| Không audit việc tắt trail | Audit gap không được phát hiện | Alert trên thay đổi audit configuration |
| Chỉ lưu event mà không có change ID | Khó liên kết với ticket/approval | Correlation với change request và deployment |
| Không giữ artifact digest | Không biết package nào thực sự deploy | Lưu immutable digest/version |
| Approval không gắn với plan | Có thể apply nội dung khác đã review | Bind approval với commit/plan digest |
| Lưu raw secret trong before/after | Bằng chứng trở thành nơi rò rỉ credential | Redact hoặc lưu secret version reference |
| Dùng hash đơn lẻ như chống sửa | Attacker có thể thay cả file và hash | Ký/anchor digest ở trust boundary khác |
| Retention tùy tiện | Thiếu bằng chứng hoặc lưu dữ liệu quá lâu | Retention theo classification và policy |
| Không đồng bộ clock | Timeline điều tra sai thứ tự | UTC, time sync và ingest timestamp |
| Không kiểm tra delivery | Có thể mất event âm thầm | Health metric, gap alert và reconciliation |
| Alert mọi thay đổi nhỏ | Alert fatigue | Ưu tiên hành động rủi ro cao |
| Failover không có audit | Không tái dựng được quyết định khẩn cấp | Ghi incident, actor, fencing và route change |

## 28. Quy trình thiết kế audit và change evidence

1. **Phân loại tài nguyên/dữ liệu:** xác định resource quan trọng, data sensitivity và hành động cần audit.
2. **Lập coverage matrix:** control plane, data plane, identity, application và CI/CD.
3. **Chuẩn hóa schema:** actor, action, resource, time, source, outcome, request/change ID.
4. **Chọn nguồn độc lập:** cloud audit service, identity provider, application audit và pipeline.
5. **Tập trung log:** central account/project, archive riêng và quyền writer hạn chế.
6. **Bảo vệ integrity:** append-only/WORM, versioning, digest/signature và audit quyền archive.
7. **Thiết kế change package:** request, PR, plan, policy, approval, artifact, deployment và verification.
8. **Bảo vệ dữ liệu:** encryption, redaction, access control và retention.
9. **Thiết lập alert:** IAM, public exposure, trail disable, retention change và manual production change.
10. **Kiểm tra delivery:** heartbeat, collector health, gap detection và reconciliation.
11. **Diễn tập điều tra:** truy vấn actor/resource/change và xác minh digest.
12. **Review định kỳ:** coverage, retention, role access, cost và thay đổi provider.

## 29. Checklist production

- **Coverage:** đã xác định control-plane, data-plane, identity, application và CI/CD audit.
- **Identity:** actor là human/workload/service được nhận diện; session và source được liên kết khi có.
- **Schema:** event ID, timestamp UTC, action, resource, outcome, request/change reference có quy ước.
- **Provider audit:** trail/Activity Log/Audit Logs đã được bật đúng scope và Region.
- **Data access:** log truy cập dữ liệu nhạy cảm được bật theo risk và chi phí.
- **Serverless resources:** function, IAM, API, queue, event mapping, workflow, storage, KMS và secret được đưa vào coverage.
- **Change evidence:** PR, commit, plan/diff, policy, approval, artifact digest, deployment và post-check được liên kết.
- **Approval:** decision gắn với đúng commit/plan/artifact và có separation of duties.
- **Integrity:** central archive có append-only/WORM hoặc cơ chế bảo vệ tương đương.
- **Access:** writer, investigator, reviewer và archive admin có quyền tách biệt.
- **Encryption:** transport, storage và key policy được kiểm soát; DR có thể decrypt.
- **Retention:** có thời hạn theo classification, legal hold và quy trình xóa.
- **Privacy:** không lưu secret/raw payload; IP và identifier có policy.
- **Time:** UTC, time synchronization, event time và ingest time được phân biệt.
- **Delivery:** có health monitoring, gap alert, backlog và reconciliation.
- **High-risk alert:** IAM escalation, public exposure, trail disable, retention/key change và manual production change.
- **Testing:** audit coverage, tamper resistance, restore, break-glass và evidence retrieval đã được thử.
- **Cost:** data event, ingestion, retention, query và cross-Region archive có budget.

## 30. Kết luận

Audit log và bằng chứng thay đổi cấu hình là hai lớp bổ sung để chứng minh hệ thống đã được quản trị như thế nào. Audit log cho biết actor, action, resource, time, source và outcome. Change evidence nối sự kiện đó với yêu cầu, commit, plan, policy check, approval, artifact và kết quả triển khai. Khi hai nguồn được liên kết bằng change ID, request ID và deployment run ID, nhóm có thể tái dựng một thay đổi từ lúc đề xuất đến trạng thái thực tế.

Với serverless, cần audit cả control plane lẫn data plane: function configuration, IAM, API gateway, queue, event source mapping, workflow, storage, database, KMS và secret. Bảo vệ archive bằng quyền tách biệt, encryption, append-only/WORM, retention và kiểm tra delivery. Audit chính audit pipeline để phát hiện việc tắt trail, thay destination hoặc giảm retention.

Không lưu secret hay toàn bộ payload chỉ để có bằng chứng. Dùng schema ổn định, snapshot đã lọc, artifact digest và manifest có thể xác minh. Diễn tập truy vấn, restore, break-glass và phát hiện audit gap để bảo đảm bằng chứng thực sự dùng được khi có sự cố hoặc kiểm toán.
