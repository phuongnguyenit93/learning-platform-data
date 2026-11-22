# GitOps và đồng bộ trạng thái mong muốn với môi trường

## 1. GitOps giải quyết vấn đề gì?

Trong môi trường cloud, một ứng dụng có thể gồm deployment, service, ingress, policy mạng, cấu hình runtime, secret reference, database migration, autoscaling rule và nhiều dependency khác. Nếu mỗi thay đổi được thực hiện thủ công qua console hoặc câu lệnh riêng lẻ, trạng thái thực tế nhanh chóng lệch khỏi tài liệu và khó biết ai đã thay đổi điều gì. Một lần hotfix trực tiếp trên cluster có thể bị mất khi pipeline triển khai tiếp theo chạy; ngược lại, cấu hình trong repository có thể không còn phản ánh môi trường đang phục vụ người dùng.

**GitOps** là phương pháp vận hành trong đó cấu hình khai báo của hệ thống được lưu trong version control, còn một hoặc nhiều controller tự động quan sát repository và môi trường rồi đưa trạng thái thực tế về trạng thái mong muốn đã được phê duyệt. Git cung cấp lịch sử thay đổi, review, quyền truy cập và khả năng tái tạo; controller thực hiện reconciliation liên tục hoặc theo chu kỳ.

GitOps thường dựa trên bốn ý tưởng:

- **Declarative desired state:** mô tả kết quả cần có, chẳng hạn số replica, image version, routing và policy.
- **Versioned change:** thay đổi đi qua commit, pull request, review và lịch sử có thể truy vết.
- **Automated reconciliation:** controller so sánh desired state với actual state và áp dụng thay đổi cần thiết.
- **Observable and recoverable operation:** trạng thái sync, health, drift và lỗi được hiển thị; có thể khôi phục một phiên bản cấu hình đã biết.

GitOps không chỉ là lưu YAML trong Git. Một repository không có controller reconcile chỉ là kho cấu hình. Một pipeline đẩy lệnh imperatively mà không liên tục so sánh trạng thái cũng chưa tạo ra đầy đủ mô hình GitOps.

Trong module **CLOUD_ARCHITECTURE**, GitOps kết nối quy trình phân phối phần mềm với khả năng lặp lại, bảo mật, độ tin cậy và vận hành cloud. Phương pháp này đặc biệt hữu ích khi quản lý nhiều service, cluster hoặc environment, nhưng cần được thiết kế cùng quy trình database migration, secret management, infrastructure provisioning và incident response.

### Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích GitOps, desired state, actual state, reconciliation và drift.
2. Phân biệt pull-based GitOps với pipeline push-based.
3. Tổ chức repository, manifest và promotion giữa dev, staging, production.
4. Thiết kế controller scope, RBAC, trust và separation of duties.
5. Quản lý secret reference và encrypted secret mà không đưa plaintext vào Git.
6. Xử lý drift, manual hotfix, sync failure, prune và rollback.
7. Kết hợp GitOps với progressive delivery, health gate và database migration.
8. Thiết lập observability, audit, policy validation và runbook.

## 2. Các khái niệm cốt lõi

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| **Source of truth** | Nơi có thẩm quyền lưu cấu hình mong muốn | Git repository được bảo vệ |
| **Desired state** | Trạng thái được khai báo cần đạt | 4 replica, image digest cụ thể, network policy |
| **Actual state** | Trạng thái đang tồn tại trong môi trường | 3 pod ready, image đang chạy |
| **Reconciliation** | Quá trình so sánh và xử lý chênh lệch | Controller tạo pod còn thiếu |
| **Controller/operator** | Thành phần quan sát và thực hiện reconcile | GitOps controller, operator quản lý database |
| **Drift** | Actual state khác desired state | Replica bị sửa thủ công |
| **Sync** | Áp dụng hoặc xác nhận desired state với cluster | Apply manifest ở commit đã chọn |
| **Health** | Tình trạng workload sau khi sync | Deployment available và readiness pass |
| **Revision** | Commit/tag/artifact version đang được áp dụng | Git SHA hoặc immutable image digest |

### 2.1. Desired state và actual state

Giả sử repository khai báo Deployment cần 4 replica. Cluster hiện chỉ có 3 pod vì một node bị lỗi. Controller thấy chênh lệch và yêu cầu Kubernetes tạo replica thay thế. Scheduler và controller của Kubernetes tiếp tục xử lý cho tới khi có đủ pod phù hợp; GitOps controller quan sát trạng thái sync/health để báo kết quả.

Một điểm quan trọng: desired state không bảo đảm actual state đạt được. Cluster có thể thiếu quota, node, image registry có thể không truy cập được, policy có thể từ chối resource hoặc ứng dụng có thể crash. Controller sẽ tiếp tục retry theo policy, nhưng cần alert và người vận hành xử lý nguyên nhân.

### 2.2. Vòng lặp reconciliation

~~~mermaid
flowchart TD
    Git["Git repository: desired state"] --> Observe["GitOps controller observes revision"]
    Observe --> Compare["Compare desired vs actual"]
    Compare --> Diff{"Drift / changes?"}
    Diff -->|No| Health["Check sync and health"]
    Diff -->|Yes| Apply["Apply approved configuration"]
    Apply --> Platform["Cluster / cloud APIs"]
    Platform --> Actual["Actual resources and workload"]
    Actual --> Compare
    Health --> Observe
~~~

Reconciliation là vòng lặp liên tục, không phải thao tác chạy một lần. Khi resource bị xóa ngoài ý muốn, controller có thể tạo lại; khi field bị sửa thủ công, controller có thể ghi đè hoặc báo drift tùy policy.

## 3. GitOps pull-based và push-based delivery

Hai cách phân phối thường được so sánh:

| Tiêu chí | Pull-based GitOps | Push-based pipeline |
|---|---|---|
| Ai lấy cấu hình? | Controller trong môi trường đích pull từ Git/artifact source | CI/CD runner push thay đổi tới môi trường |
| Credential cluster | Thường giữ trong môi trường đích/controller | Runner thường cần quyền truy cập cluster |
| Kết nối mạng | Môi trường đích cần outbound tới source/registry theo thiết kế | Runner cần kết nối tới API môi trường đích |
| Reconciliation | Liên tục hoặc theo chu kỳ | Thường theo lần pipeline chạy, trừ khi có controller khác |
| Drift correction | Có thể tự phát hiện và sửa drift | Thường cần pipeline/job chạy lại hoặc công cụ khác |
| Audit | Commit/revision và controller event | Pipeline run, identity và deployment record |
| Rủi ro chính | Controller có quyền quá rộng hoặc nguồn cấu hình bị compromise | Runner credential bị lộ, quyền push rộng, state drift |

Pull-based thường giúp giảm việc cấp credential cluster cho CI runner. Tuy nhiên, nó không tự động an toàn hơn nếu controller có quyền quản trị toàn cluster, repository không được bảo vệ hoặc token Git bị lộ.

### 3.1. Luồng pull-based điển hình

~~~mermaid
sequenceDiagram
    participant Dev as Developer
    participant Git as Git repository
    participant CI as CI validation
    participant Ctrl as GitOps controller
    participant K8s as Target cluster
    Dev->>Git: Push branch / open pull request
    Git->>CI: Trigger tests and policy checks
    CI-->>Git: Validation result
    Dev->>Git: Merge approved change
    Ctrl->>Git: Poll / receive revision notification
    Git-->>Ctrl: Approved desired state
    Ctrl->>Ctrl: Render and compare
    Ctrl->>K8s: Reconcile resources
    K8s-->>Ctrl: Resource status
    Ctrl-->>Git: Status / revision / health evidence
~~~

CI kiểm tra thay đổi trước khi merge; controller trong target environment mới thực hiện deployment. Notification có thể tăng tốc phát hiện thay đổi, nhưng controller vẫn cần xác minh revision và quyền truy cập theo trust policy.

## 4. Repository là ranh giới quản trị

Tổ chức repository ảnh hưởng đến quyền review, blast radius, promotion và khả năng tái sử dụng.

### 4.1. Một số mô hình repository

| Mô hình | Phù hợp khi | Đánh đổi |
|---|---|---|
| App repo chứa source và deploy config | Team nhỏ, service độc lập | Code và production config có cùng quyền/chu kỳ review |
| Repo platform/environment riêng | Nhiều service và nhiều team | Cần quản lý mapping source version sang deployment version |
| Monorepo nhiều service | Muốn review thay đổi đồng bộ | Repo lớn, CI/path filter và ownership phức tạp |
| Repo per team/service | Team tự chủ và release độc lập | Dễ phân mảnh policy/template nếu thiếu platform standard |
| Repo bootstrap/platform | Quản lý controller, cluster add-on và policy nền | Thay đổi có blast radius rộng, cần quyền và review nghiêm ngặt |

Không có mô hình duy nhất đúng. Cần cân bằng quyền sở hữu, số environment, tốc độ release, mức dùng chung và khả năng audit.

### 4.2. Cấu trúc tham khảo

~~~text
platform-config/
  bootstrap/
    controllers/
    cluster-baseline/
  apps/
    booking/
      base/
      overlays/
        dev/
        staging/
        production/
    payment/
      base/
      overlays/
        dev/
        staging/
        production/
  policies/
    admission/
    network/
    security/
  clusters/
    dev-a/
    staging-a/
    production-a/
~~~

Đây là cách tổ chức minh họa. Một repo thật có thể dùng Helm chart, Kustomize, Jsonnet hoặc plain manifest. Cần xác định rõ path nào được controller theo dõi và ai có quyền sửa từng path.

### 4.3. CODEOWNERS và review

Nên yêu cầu owner phù hợp review các khu vực nhạy cảm:

- Production overlay: service owner và người có thẩm quyền vận hành.
- Cluster baseline: platform team.
- Admission/security policy: security/platform reviewers.
- Secret reference: workload owner và security khi thay đổi trust.
- Controller configuration: platform admin.

Branch protection, required status checks, signed commit (nếu policy yêu cầu), CODEOWNERS và protected environment giúp giảm khả năng thay đổi trái phép.

## 5. Declarative manifest và template

GitOps phù hợp với cấu hình khai báo. Manifest mô tả tài nguyên cần có; controller và platform xác định trình tự hành động để đạt trạng thái đó.

### 5.1. Ví dụ Deployment khai báo

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: booking-api
  namespace: production
spec:
  replicas: 4
  selector:
    matchLabels:
      app: booking-api
  template:
    metadata:
      labels:
        app: booking-api
    spec:
      serviceAccountName: booking-api
      containers:
        - name: api
          image: registry.example.invalid/booking-api@sha256:REPLACE_WITH_DIGEST
          ports:
            - name: http
              containerPort: 8080
          readinessProbe:
            httpGet:
              path: /ready
              port: http
          resources:
            requests:
              cpu: 250m
              memory: 512Mi
            limits:
              cpu: "1"
              memory: 1Gi
~~~

Đây là cấu hình minh họa, cần điều chỉnh namespace, digest, resource và probe theo service. Dùng image digest hoặc artifact version bất biến giúp cùng một revision triển khai đúng artifact đã kiểm thử; tag mutable như latest làm suy giảm khả năng tái lập.

### 5.2. Template và overlay

Base chứa phần dùng chung; overlay/environment values chứa khác biệt có chủ đích:

- Dev có replica thấp, debug feature theo policy và dependency sandbox.
- Staging gần production về network, resource và integration.
- Production có replica/headroom, autoscaling, policy và alert theo SLO.

Tránh copy toàn bộ manifest giữa môi trường vì các bản sao dễ drift. Nhưng cũng không dùng một template quá tổng quát đến mức không đọc được hoặc hidden default làm thay đổi hành vi production.

### 5.3. Render trước khi merge

CI nên render chart/template thành manifest cuối cùng rồi kiểm tra:

- YAML/schema hợp lệ.
- API version còn được hỗ trợ.
- Resource name/namespace không xung đột.
- Image dùng digest/version đã xác định.
- Resource request/limit và probe hợp lý.
- Security context, service account và network policy đạt policy.
- Diff không vô tình xóa resource quan trọng.

Review source template mà không xem rendered manifest có thể bỏ sót giá trị thực được đưa vào cluster.

## 6. Promotion giữa dev, staging và production

Promotion là quá trình đưa cùng một release/artifact qua các môi trường với các gate phù hợp. Không nên build artifact khác nhau cho mỗi môi trường nếu mục tiêu là chứng minh đúng artifact đã được kiểm thử đang chạy production.

### 6.1. Luồng promotion

~~~mermaid
flowchart LR
    Source["Source commit"] --> Build["Build immutable artifact"]
    Build --> Test["Unit / integration / security scan"]
    Test --> Dev["Deploy to dev"]
    Dev --> Stage["Promote same digest to staging"]
    Stage --> Verify["E2E / performance / policy gates"]
    Verify --> Approval["Production approval"]
    Approval --> Prod["Promote same digest to production"]
    Prod --> Observe["Observe SLO and business signals"]
~~~

Artifact digest nên được giữ nguyên qua các môi trường; cấu hình môi trường có thể khác nhưng phải versioned và review. Nếu cần build khác vì kiến trúc platform, ghi rõ quan hệ giữa source commit, build provenance và deployed artifact.

### 6.2. Promotion không phải copy secret

Mỗi môi trường dùng secret reference và identity riêng. Repository có thể chứa tên secret, external secret reference hoặc encrypted representation theo cơ chế đã chọn; không nên copy production credential sang staging để làm cho manifest giống nhau.

### 6.3. Gate production

Gate có thể bao gồm:

- CI test, vulnerability scan và artifact provenance.
- Rendered manifest và policy check.
- Integration/E2E test ở staging.
- Capacity/performance check cho thay đổi lớn.
- Database migration readiness/compatibility.
- Change approval tùy mức rủi ro.
- Health check và SLO observation sau deploy.

Không phải thay đổi nào cũng cần manual approval; có thể tự động hóa low-risk changes, còn policy/IAM/network/database destructive operation cần gate rõ.

## 7. Drift detection và correction

**Configuration drift** xảy ra khi trạng thái môi trường không còn khớp với cấu hình đã được phê duyệt. Nguồn drift có thể là thao tác thủ công, một controller khác, admission mutation, default của API server, autoscaling, operator hoặc thay đổi cloud provider.

### 7.1. Phân loại drift

| Loại drift | Ví dụ | Cách xử lý |
|---|---|---|
| Unauthorized manual change | Sửa replicas hoặc image bằng console/kubectl | Cảnh báo và reconcile về Git sau khi xác minh |
| Emergency hotfix | Tăng limit để xử lý incident | Ghi lại thay đổi vào Git sau khi ổn định |
| Expected dynamic state | HPA điều chỉnh replicas | Không ép controller ghi đè field thuộc HPA |
| Platform-managed mutation | API default hoặc admission webhook thêm field | Dùng diff customization/ownership rõ |
| External dependency update | DNS target/provider setting thay đổi | Đồng bộ nguồn quản trị hoặc import state có kiểm soát |
| Resource deletion | Resource bị xóa ngoài ý muốn | Recreate nếu Git vẫn khai báo và policy cho phép |

### 7.2. Reconcile có thể gây ghi đè

Nếu Git khai báo replicas = 4 trong khi HPA quản lý scale từ 4 đến 20, hai controller có thể tranh quyền trên cùng field. Cần xác định field ownership: HPA quản lý replicas, GitOps quản lý HPA spec và các field khác. Tương tự, operator có thể quản lý resource sinh ra; tránh khai báo chồng lấn.

### 7.3. Manual hotfix trong incident

Có tình huống cần thao tác trực tiếp để phục hồi nhanh. Nên có quy trình:

1. Ghi nhận incident, actor, resource, thời gian và lý do.
2. Áp dụng thay đổi tối thiểu có thể đảo ngược.
3. Xác minh tác động và khôi phục service.
4. Tạo pull request cập nhật desired state tương ứng.
5. Review và merge sau khi xác minh.
6. Để controller reconcile và xác nhận drift đã hết.

Nếu hotfix không được đưa về Git, lần reconcile tiếp theo có thể undo hotfix và tái tạo incident.

## 8. Sync policy, prune và deletion safety

Một controller có thể tự động apply thay đổi và xóa resource không còn khai báo. Quyền xóa cần được xem xét riêng vì xóa nhầm database, namespace, storage hoặc network resource có thể gây mất dữ liệu/outage.

### 8.1. Các chế độ sync

- **Manual sync:** operator xác nhận thời điểm áp dụng.
- **Auto sync:** controller tự apply revision đủ điều kiện.
- **Prune:** xóa resource được quản lý nhưng không còn trong desired state.
- **Self-heal:** tự sửa drift khi actual state bị thay đổi ngoài nguồn.
- **Selective sync:** chỉ áp dụng một phạm vi/resource theo capability của tool.

Tên và semantics chính xác khác nhau giữa GitOps controller. Cần hiểu rõ controller có tự prune, self-heal, retry và thay thế resource nào.

### 8.2. Guardrail cho prune

- Không bật prune không giới hạn cho mọi resource nhạy cảm.
- Dùng protected namespace/resource hoặc policy ngăn xóa.
- Review diff có deletion rõ ràng.
- Với database/storage có state, dùng retention/finalizer/backup và quy trình riêng.
- Có owner và approval cho destructive change.
- Kiểm tra ownerReferences/finalizers để tránh resource bị giữ lại hoặc xóa dây chuyền.

Git là nguồn sự thật của cấu hình, nhưng không nên suy ra rằng mọi resource biến mất khỏi Git đều có thể xóa ngay. Việc xóa persistent data cần policy và lifecycle riêng.

## 9. Secret management trong GitOps

Git history tồn tại lâu và có thể được clone/fork/cache. Commit secret plaintext rồi xóa ở commit tiếp theo vẫn để lại giá trị cũ trong history.

### 9.1. Mẫu quản lý secret

| Mẫu | Cách hoạt động | Lưu ý |
|---|---|---|
| External secret manager | Manifest chứa reference; controller/runtime lấy secret từ vault | Identity có quyền đọc đúng secret và version |
| Sealed/encrypted secret | Repository chứa ciphertext; controller giải mã bằng key ở cluster | Bảo vệ private key, rotation và backup |
| Runtime workload identity | App lấy token/secret từ cloud identity endpoint | Không nhúng credential vào image hoặc Git |
| Secret injection at deploy/runtime | Secret được inject bởi platform/sidecar | Kiểm soát log, process environment và file permission |

Ưu tiên secret manager và workload identity. Nếu phải lưu encrypted secret trong Git, bảo đảm plaintext không xuất hiện trong diff, build log, rendered artifact hoặc debugging output.

### 9.2. Tách cấu hình và bí mật

Có thể version các giá trị không bí mật như service name, feature flag mặc định hoặc secret reference. Giá trị secret thực tế được quản lý bên ngoài repository, có access policy, rotation và audit riêng.

Khi secret rotate, consumer phải reload/restart theo cách phù hợp; health check xác minh auth mới; key cũ chỉ revoke sau khi mọi consumer chuyển. GitOps controller không tự giải quyết credential lifecycle nếu chưa có integration.

## 10. RBAC và ranh giới tin cậy của controller

Controller thường có quyền đọc repository và tạo/sửa resource trên cluster. Nếu controller hoặc credential bị compromise, phạm vi quyền có thể rất lớn.

### Nguyên tắc thiết kế

- Một controller/project scope chỉ quản lý namespace/cluster cần thiết.
- Service account có quyền tối thiểu; tách quyền quản trị controller khỏi quyền deploy workload.
- Repository deploy production cần branch protection, review và identity rõ.
- Token source chỉ được đọc repo cần thiết, dùng token ngắn hạn nếu hỗ trợ.
- Network policy giới hạn controller tới Git, registry, API endpoint và secret manager cần thiết.
- Admission policy chặn privileged container, hostPath, image không tin cậy hoặc resource vi phạm chuẩn.
- Audit ghi nhận actor, commit SHA, controller identity và resource action.
- Không để developer tự sửa controller trust hoặc cluster-admin binding qua repo ứng dụng.

### 10.1. Multi-tenancy

Nhiều team cùng dùng một cluster cần boundary:

- Namespace/project scope.
- RBAC theo team/service.
- Resource quota và limit range.
- Network policy.
- Secret isolation và service account riêng.
- Policy ngăn escalation hoặc sửa resource ngoài ownership.

Namespace tự nó không phải ranh giới bảo mật tuyệt đối. Cần kết hợp RBAC, network isolation, admission policy và identity.

## 11. GitOps cho nhiều cluster và environment

Khi có nhiều cluster, cần xác định cấu hình nào dùng chung và khác biệt nào được phép.

### 11.1. Mô hình quản lý

- Một management/bootstrap cluster quản lý config cho workload cluster.
- Mỗi cluster chạy controller riêng để giảm phụ thuộc vào một control plane trung tâm.
- Repo chứa overlays/cluster inventory; controller chỉ watch đúng path.
- Cluster registration và credential được quản lý bởi platform identity, không để repo app tự thêm target tùy ý.

### 11.2. Trade-off

| Thiết kế | Ưu điểm | Rủi ro/chi phí |
|---|---|---|
| Central controller | Quản trị tập trung, ít thành phần | Blast radius lớn, phụ thuộc network và controller trung tâm |
| Controller per cluster | Cô lập tốt, cluster reconcile độc lập | Nhiều controller cần nâng cấp/monitor |
| Shared config repo | Dễ chuẩn hóa và xem toàn cảnh | Quyền repo rộng, thay đổi có thể ảnh hưởng nhiều cluster |
| Repo per environment | Ranh giới approval rõ | Khó giữ đồng bộ template và promotion |

Không để một cluster có thể tự cấp quyền quản lý các cluster khác chỉ bằng cách commit một manifest nếu trust boundary chưa được thiết kế.

## 12. Progressive delivery cùng GitOps

GitOps controller quản lý desired state; progressive delivery controller có thể quản lý cách đưa release tới người dùng theo từng bước.

### 12.1. Rolling, canary và blue-green

- **Rolling update:** thay replica dần, giữ một phần capacity cũ.
- **Canary:** đưa một tỷ lệ traffic nhỏ tới phiên bản mới, quan sát metric rồi tăng dần.
- **Blue-green:** duy trì hai environment/replica set và chuyển traffic khi bản mới đạt gate.

~~~mermaid
flowchart TD
    Commit["Approved release revision"] --> DeployCanary["Deploy canary"]
    DeployCanary --> Smoke["Smoke / readiness checks"]
    Smoke --> Metrics["Observe error, latency, business SLI"]
    Metrics --> Decision{"Pass analysis?"}
    Decision -->|Yes| Increase["Increase traffic / continue rollout"]
    Increase --> Complete["Promote to 100%"]
    Decision -->|No| Abort["Abort / rollback traffic"]
    Abort --> Stable["Keep stable version"]
~~~

### 12.2. Metrics cần đánh giá

- Error rate và latency p95/p99.
- Resource saturation và restart count.
- Business conversion, payment success hoặc job completion.
- Dependency errors và queue age.
- Data correctness/reconciliation khi release ảnh hưởng dữ liệu.

Chỉ dựa vào CPU hoặc pod readiness chưa đủ để kết luận canary an toàn. Một phiên bản có thể ready nhưng tính giá sai hoặc tạo booking duplicate.

### 12.3. Rollback

Rollback ứng dụng có thể là revert manifest/image digest hoặc chuyển traffic về stable release. Nhưng rollback không tự đảo ngược database schema/data migration hay side effect đã xảy ra. Cần thiết kế backward-compatible migration và forward-fix strategy.

## 13. Database migration và stateful workload

GitOps phù hợp quản lý declarative resources nhưng không biến mọi thay đổi stateful thành thao tác apply có thể lặp vô hại.

### 13.1. Expand-migrate-contract

1. Expand: thêm schema/field/index tương thích với phiên bản cũ.
2. Deploy app hỗ trợ cả schema cũ/mới.
3. Migrate: backfill/chuyển dữ liệu có checkpoint và đối soát.
4. Chuyển traffic/code sang schema mới.
5. Contract: chỉ xóa schema cũ sau khi mọi consumer đã chuyển và có approval.

Migration job cần identity riêng, lock/idempotency, timeout, status và runbook. Không chạy destructive migration tự động chỉ vì một manifest xuất hiện trong Git.

### 13.2. StatefulSet và persistent storage

GitOps có thể quản lý StatefulSet, PVC template, StorageClass và operator configuration. Tuy nhiên:

- PVC lifecycle và reclaim policy cần hiểu rõ.
- Xóa claim/workload không đồng nghĩa dữ liệu có thể bỏ.
- Backup, restore và consistency cần quy trình riêng.
- Operator có thể tạo resource con ngoài manifest ban đầu.
- Version upgrade có thể yêu cầu thứ tự và compatibility.

Không bật prune rộng cho persistent volume hoặc database resource mà chưa có deletion protection và kiểm tra backup.

## 14. Policy-as-code và validation trước khi reconcile

Mọi manifest có thể tác động security posture, chi phí và reliability. Nên kiểm tra policy trước khi merge và ở admission/runtime.

### 14.1. Các lớp validation

- Syntax/schema validation.
- Render/chart lint và API compatibility.
- Security policy: runAsNonRoot, read-only filesystem, capability, image trust.
- Resource policy: request/limit, quota, replica floor/ceiling.
- Network policy: ingress/egress chỉ cần thiết.
- IAM/RBAC: tránh wildcard/admin và cross-namespace escalation.
- Compliance policy: encryption, region, labels, retention, audit.
- Change risk: deletion, secret reference, public exposure và data migration.

### 14.2. Hai lớp kiểm soát

CI policy check phản hồi sớm trước merge; admission policy kiểm tra lại khi resource được tạo/đổi. CI không đủ vì có thể bị bypass hoặc môi trường thay đổi; admission không thay thế review vì lỗi chỉ được phát hiện lúc apply có thể gây delay/reconcile failure.

Policy exception cần owner, lý do, thời hạn và review; tránh annotation “skip policy” vô thời hạn.

## 15. Observability cho GitOps

GitOps cần quan sát cả source, controller và target environment.

| Metric/event | Ý nghĩa |
|---|---|
| Sync status | Revision đã được áp dụng hay còn chờ |
| Health status | Workload/resource có healthy không |
| Reconciliation duration | Mất bao lâu từ commit đến trạng thái mong muốn |
| Drift count | Số resource lệch cấu hình |
| Failed sync count | Số lần apply/reconcile thất bại |
| Reconciliation retry | Controller có đang lặp lỗi không |
| Revision age | Môi trường đang chạy commit cũ bao lâu |
| Deployment lead time | Từ merge tới usable release |
| Rollback frequency | Tần suất phải quay lại phiên bản trước |
| Prune/deletion events | Resource nào bị xóa và do revision nào |
| Controller health/queue | Controller có xử lý kịp thay đổi không |

### 15.1. Dashboard nên trả lời

1. Environment đang chạy revision nào?
2. Revision mới nhất đã qua CI/review chưa?
3. Có drift ngoài Git không? Resource nào và ai thay đổi?
4. Reconcile đang chờ hay thất bại ở bước nào?
5. Workload đã sync nhưng chưa healthy ở đâu?
6. Có destructive prune hoặc policy denial nào không?
7. Release có ảnh hưởng business SLI hay dependency không?

### 15.2. Alert

- Production không sync với revision được phê duyệt quá thời gian mục tiêu.
- Drift ở resource nhạy cảm hoặc thay đổi ngoài quy trình.
- Controller mất kết nối Git/registry/cluster.
- Reconcile lặp lỗi, queue tăng hoặc apply throttling.
- Workload sync thành công nhưng health fail.
- Unexpected prune/delete event.
- Revision production cũ hơn release policy hoặc artifact bị thu hồi.

Không alert cho mọi diff không có ý nghĩa. Cần phân biệt field do autoscaler/operator quản lý, defaulting và drift thực sự.

## 16. Incident response và runbook

Khi GitOps làm môi trường không đồng bộ hoặc triển khai sai:

1. Xác định cluster/environment, application, revision và controller.
2. Kiểm tra sync status, health status, rendered diff và resource event.
3. Xác định thay đổi từ Git, manual mutation, another controller hay platform default.
4. Nếu release gây lỗi, ngừng promotion/rollout và giữ evidence.
5. Chọn rollback manifest/image hoặc forward fix; cân nhắc migration/stateful side effect.
6. Nếu có emergency hotfix, ghi nhận chính xác và cập nhật Git sau khi phục hồi.
7. Kiểm tra controller có thể tiếp tục overwrite hotfix hay không; dùng suspend có kiểm soát nếu cần và có thời hạn.
8. Reconcile lại từ revision đã phê duyệt.
9. Xác nhận workload health, business SLI, drift và controller status.
10. Ghi root cause, commit, actor, impact và corrective action.

Không xóa controller hoặc tắt self-heal như giải pháp lâu dài. Nếu cần suspend reconcile để ngăn thay đổi tiếp diễn trong incident, phải có người chịu trách nhiệm, phạm vi và điều kiện bật lại.

## 17. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách cải thiện |
|---|---|---|
| Chỉ lưu YAML trong Git rồi gọi là GitOps | Không có reconcile/drift correction | Dùng controller và theo dõi sync/health |
| CI runner giữ cluster-admin credential | Runner compromise có thể chiếm cluster | Pull-based controller, short-lived identity và RBAC |
| Một controller quản lý mọi namespace | Blast radius lớn | Project/namespace scope và least privilege |
| Mutable image tag | Cùng revision có thể chạy artifact khác nhau | Pin digest hoặc immutable version |
| Copy manifest giữa môi trường | Cấu hình lệch và promotion khó kiểm chứng | Base/overlay và same artifact promotion |
| Commit plaintext secret rồi xóa | Secret vẫn còn trong Git history | Secret manager, encrypted workflow và rotation |
| Auto-prune không giới hạn | Xóa nhầm stateful resource | Deletion guard, approval và backup |
| Git và HPA cùng quản lý replicas | Controller tranh field và tạo drift | Field ownership rõ ràng |
| Sync thành công được coi là release thành công | Ứng dụng có thể unhealthy hoặc business sai | Health/SLO/business gates |
| Rollback app mà không xét DB migration | Code cũ không tương thích schema mới | Expand-migrate-contract và recovery plan |
| Hotfix không commit lại | Reconcile tiếp theo undo hotfix | Quy trình emergency change về Git |
| Không pin controller/API version | Upgrade làm manifest thay đổi semantics | Version control, compatibility test và staged upgrade |
| Không quan sát controller | Drift/sync failure kéo dài | Dashboard, alert và runbook |

## 18. Case study: GitOps cho nền tảng đặt phòng nhiều môi trường

**Bối cảnh:** nền tảng đặt phòng có Booking API, Payment service, Notification worker và Inventory service. Hệ thống chạy dev, staging và production; mỗi môi trường có cluster riêng. CI hiện build image rồi dùng kubeconfig có quyền rộng để deploy. Một số hotfix được thực hiện bằng kubectl và không cập nhật repository.

### 18.1. Kiến trúc mục tiêu

~~~mermaid
flowchart TD
    Dev["Developer"] --> PR["Protected pull request"]
    PR --> CI["CI: tests, scan, render, policy"]
    CI --> Merge["Approved merge"]
    Merge --> Config["Environment config repo"]
    Config --> DevCtrl["Dev GitOps controller"]
    Config --> StageCtrl["Staging GitOps controller"]
    Config --> ProdCtrl["Production GitOps controller"]
    DevCtrl --> DevCluster["Dev cluster"]
    StageCtrl --> StageCluster["Staging cluster"]
    ProdCtrl --> ProdCluster["Production cluster"]
    Registry["Immutable image registry"] --> DevCluster
    Registry --> StageCluster
    Registry --> ProdCluster
    Vault["Secret manager"] --> DevCluster
    Vault --> StageCluster
    Vault --> ProdCluster
    ProdCluster --> Telemetry["SLO / business / infrastructure telemetry"]
~~~

### 18.2. Luồng release

1. Developer commit code và mở PR.
2. CI chạy unit/integration test, scan dependency/image, render manifest và policy check.
3. Artifact được publish với digest bất biến.
4. PR cập nhật digest/config ở dev; controller reconcile.
5. E2E test chạy trên dev, sau đó promotion cùng digest tới staging.
6. Staging chạy integration, performance và migration compatibility checks.
7. Production overlay được review/approval theo risk.
8. Production controller reconcile, progressive delivery đưa traffic theo từng bước.
9. SLO, payment success, booking confirmation và dependency metrics được theo dõi.
10. Nếu gate fail, dừng rollout và rollback traffic/manifest theo runbook; kiểm tra migration trước khi revert code.

### 18.3. Xử lý hotfix

Nếu production cần tăng replicas trong incident:

- Operator ghi incident ID, resource và thay đổi.
- Thực hiện thay đổi khẩn cấp trong phạm vi cần thiết.
- Controller có thể báo drift; policy xác định giữ hay reconcile sau khi đánh giá.
- Khi ổn định, tạo PR phản ánh desired state mới.
- Review/merge và xác nhận controller đã reconcile.
- Đóng incident khi không còn drift ngoài ý muốn và SLO phục hồi.

### 18.4. Tiêu chí nghiệm thu

- CI runner không giữ credential quản trị cluster production.
- Mỗi environment chỉ reconcile path/target đã đăng ký.
- Release cùng image digest đi qua dev, staging và production.
- PR có required review và rendered manifest/policy checks.
- Secret production không nằm trong Git và không bị copy sang staging.
- Drift có thể phát hiện, phân loại và xử lý theo owner.
- Prune không tự xóa database/PVC quan trọng.
- Rollback được diễn tập cùng database migration và progressive delivery.
- Dashboard chỉ rõ revision, sync, health, drift và business SLI.

## 19. Checklist review GitOps

### Source of truth và repository

- [ ] Repository/branch/path có owner và protection phù hợp.
- [ ] Desired state khai báo rõ, versioned và review được.
- [ ] Image/artifact dùng digest hoặc immutable version.
- [ ] Base/overlay hoặc template có cấu trúc dễ hiểu.
- [ ] Rendered manifest được kiểm tra trước merge.

### Controller và trust

- [ ] Pull/push model được chọn theo network và threat model.
- [ ] Controller có least privilege theo cluster/namespace/project.
- [ ] Git/registry/secret credentials được bảo vệ và rotation.
- [ ] RBAC, admission policy và multi-tenant boundary được kiểm tra.
- [ ] Field ownership giữa GitOps, HPA, operator và platform rõ ràng.

### Reconciliation và recovery

- [ ] Sync, self-heal, prune và retry semantics được cấu hình rõ.
- [ ] Destructive deletion có guardrail, backup và approval.
- [ ] Drift được phát hiện và có runbook/manual hotfix process.
- [ ] Rollback application không gây sai lệch database/state.
- [ ] Stateful workload có retention, backup và migration policy riêng.

### Delivery và observability

- [ ] Promotion dùng cùng artifact digest qua môi trường.
- [ ] Progressive delivery có health, technical và business gates.
- [ ] Secret không xuất hiện plaintext trong Git/log/rendered artifact.
- [ ] Dashboard theo revision, sync, health, drift, reconcile duration và SLO.
- [ ] Alert có owner/severity/runbook.
- [ ] Controller upgrade và API compatibility được thử nghiệm trước production.

## 20. Bài tập thực hành

**Bối cảnh:** công ty có ba cluster dev/staging/production. CI hiện dùng kubeconfig admin để deploy; production thường được sửa thủ công khi incident; image dùng tag latest; chart có secret plaintext; HPA scale replicas nhưng manifest Git cũng khai báo replicas cố định; auto-prune đang bật cho toàn bộ resources.

Hãy thiết kế lại mô hình:

1. Chọn pull-based hay push-based delivery và giải thích network/credential boundary.
2. Thiết kế repository/path cho app, environment overlay, cluster baseline và policy.
3. Xác định branch protection, CODEOWNERS và approval cho production.
4. Thay latest bằng artifact digest và mô tả promotion cùng artifact qua môi trường.
5. Thiết kế workload identity cho controller và secret manager integration.
6. Xác định field ownership giữa GitOps và HPA.
7. Chia scope controller và viết nguyên tắc RBAC/admission policy.
8. Thiết kế drift/hotfix reconciliation và guardrail cho prune.
9. Đề xuất progressive delivery, health/SLO gate và rollback khi có DB migration.
10. Xây dashboard, alert và runbook cho sync failure, drift, unexpected deletion.

**Gợi ý tự kiểm tra:** Git chỉ là source of truth khi repository được bảo vệ và được controller sử dụng để reconcile. Auto-sync không đồng nghĩa mọi thay đổi đều an toàn; prune có thể phá hủy dữ liệu. Rollback image không đảo ngược side effect hoặc schema migration. HPA và GitOps không được tranh quyền trên cùng field.

## 21. Ghi nhớ

GitOps dùng cấu hình khai báo đã được version và review làm desired state; controller liên tục so sánh với actual state rồi reconcile. Pull-based delivery thường giữ credential deploy trong môi trường đích và hỗ trợ drift correction, nhưng an toàn phụ thuộc vào quyền controller, source trust và repository governance.

Một triển khai tốt cần repository/path ownership, immutable artifact, promotion có gate, secret management riêng, RBAC tối thiểu, field ownership rõ giữa các controller, deletion safety và observability. Reconcile thành công chưa đủ chứng minh release khỏe; cần health, SLO và business metrics. Hotfix phải được đưa lại vào Git, còn database migration và persistent data cần quy trình recovery riêng. GitOps phát huy giá trị khi thay đổi có thể truy vết, lặp lại, kiểm soát và phục hồi mà không làm mất an toàn của workload.
