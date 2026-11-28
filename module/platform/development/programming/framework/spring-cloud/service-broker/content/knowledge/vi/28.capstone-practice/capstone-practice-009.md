# Gia cố bảo mật, đo lường vận hành và kiểm tra điều kiện triển khai

Trong module **SPRING_CLOUD_SERVICE_BROKER**, một broker chỉ được xem là sẵn sàng cho production khi không chỉ xử lý đúng Open Service Broker API (OSB API), mà còn bảo vệ được tenant và credentials, phục hồi được sau lỗi provider, cung cấp telemetry đủ để vận hành và có bằng chứng kiểm thử trước khi nhận traffic thật.

Capstone này kết hợp ba nhóm công việc thường bị tách rời: **security hardening**, **operational observability** và **deployment readiness**. Bạn sẽ hoàn thiện một service broker quản lý PostgreSQL service instance và binding, chạy trên Kubernetes, lưu trạng thái trong PostgreSQL, xử lý operation bất đồng bộ qua queue và gọi provider adapter. Broker cần xác thực platform, kiểm tra quyền theo tenant, bảo vệ secret, chống lặp side effect, phát log/metric/trace có thể truy vấn và chỉ được triển khai khi các điều kiện an toàn đã đạt.

Bài thực hành được thiết kế như một nhiệm vụ triển khai có thể review. Kết quả cuối cần cho thấy ai có thể gọi broker, tài nguyên nào thuộc tenant nào, cách phát hiện và phục hồi lỗi, cách đo chất lượng dịch vụ và những kiểm tra nào chặn một release không an toàn.

## 1. Bối cảnh và mục tiêu capstone

Một tổ chức vận hành broker dùng chung cho Cloud Foundry và Kubernetes. Broker công bố PostgreSQL service với các plan small và standard. Platform gửi request provision, update, bind, unbind và deprovision. Broker lưu instance/binding/operation trong PostgreSQL, phát event cho worker, tạo resource thông qua provider adapter và lưu credentials trong secret manager.

Hệ thống hiện đã có các lifecycle path cơ bản. Nhiệm vụ capstone là gia cố và chứng minh khả năng vận hành production.

Các mục tiêu:

1. Xác thực platform client và giới hạn quyền truy cập theo platform/tenant/resource.
2. Bảo vệ originating identity, context, parameters và provider credentials qua trust boundaries.
3. Bảo đảm instance, binding và operation có idempotency cùng state transition an toàn.
4. Thiết lập structured logs, metrics, distributed traces và audit events.
5. Định nghĩa SLI/SLO, alert và dashboard cho lifecycle quan trọng.
6. Triển khai broker trên Kubernetes với TLS, RBAC, resource limits, probes và secret injection.
7. Tạo CI/CD gates dựa trên test, security scan, migration validation và rollout health.
8. Chuẩn bị runbook cho provider outage, queue backlog, credential exposure và rollback.


### 1.1. Phạm vi nghiệp vụ

| Thành phần | Trách nhiệm |
|---|---|
| OSB HTTP API | Catalog và lifecycle endpoints |
| Authentication | Xác thực platform client |
| Authorization | Kiểm tra tenant, instance, binding và operation scope |
| Instance registry | Lưu service ID, plan ID, tenant, provider mapping và state |
| Binding registry | Lưu consumer, principal và secret reference |
| Operation store | Lưu async operation, attempts và terminal result |
| Outbox/queue | Phát và xử lý công việc bất đồng bộ |
| Provider adapter | Tạo, đọc, cập nhật, revoke và xóa resource |
| Secret manager | Lưu credential và certificate an toàn |
| Telemetry | Log, metric, trace và audit |
| Deployment platform | Chạy broker và worker trên Kubernetes |

### 1.2. Ngoài phạm vi

Capstone không yêu cầu xây dựng cloud provider mới hoặc triển khai một hệ thống billing đầy đủ. Provider có thể được thay bằng sandbox hoặc adapter giả lập có contract rõ ràng. Tuy nhiên, test phải xác minh request/response và side effect ở ranh giới provider; không được chỉ mock mọi thứ rồi kết luận broker đã sẵn sàng.

## 2. Kiến trúc mục tiêu

~~~mermaid
flowchart TD
    CF["Cloud Foundry"] --> GW["Trusted ingress / API gateway"]
    K8S["Kubernetes platform"] --> GW
    GW --> AUTH["Authentication and authorization"]
    AUTH --> API["Spring Cloud OSB API"]
    API --> APP["Lifecycle application services"]
    APP --> DB[("PostgreSQL registry")]
    APP --> OUT["Transactional outbox"]
    OUT --> MQ["Message broker"]
    MQ --> WORKER["Async workers"]
    WORKER --> PROVIDER["Provider adapters"]
    PROVIDER --> CLOUD["Database / managed infrastructure"]
    APP --> VAULT["Secret manager"]
    WORKER --> VAULT
    API --> OTEL["Logs / metrics / traces"]
    WORKER --> OTEL
    PROVIDER --> OTEL
    OTEL --> OBS["Observability platform"]
~~~

Request đi qua ingress đã được tin cậy, authentication và authorization trước khi chạm vào lifecycle. Application service lưu state và outbox event trong transaction phù hợp. Worker claim operation, gọi provider ngoài transaction dài, sau đó lưu kết quả và phát telemetry. Credentials chỉ được đọc từ secret manager khi có nhu cầu và đúng quyền.

### 2.1. Các trust boundaries

- Platform tới ingress: TLS, client authentication và giới hạn request.
- Ingress tới broker: xác định proxy được tin cậy và header được phép chuyển tiếp.
- API tới application service: chỉ truyền actor, tenant và platform scope đã chuẩn hóa.
- Broker tới database/queue: workload identity, network policy và credential tối thiểu.
- Worker tới provider: provider identity riêng, scope hẹp và timeout có giới hạn.
- Broker/worker tới secret manager: quyền đọc đúng secret reference, có audit.
- Telemetry tới log platform: loại bỏ secret/PII trước khi xuất dữ liệu.

## 3. Chốt security baseline trước khi triển khai

Hãy viết một security baseline có thể kiểm tra được, không chỉ ghi các nguyên tắc chung. Mỗi yêu cầu cần có cấu hình, test hoặc bằng chứng vận hành.

| Kiểm soát | Baseline yêu cầu | Bằng chứng |
|---|---|---|
| Transport | TLS cho platform-to-broker và broker-to-provider khi hỗ trợ | TLS test, certificate inventory |
| Platform authentication | Credential riêng theo platform hoặc trust identity tương đương | Negative auth tests |
| Authorization | Tenant/resource ownership được kiểm tra trên mọi lifecycle endpoint | Cross-tenant tests |
| Secret handling | Không log hoặc serialize secret; dùng secret manager | Redaction tests, secret access audit |
| Provider identity | Least privilege, tách credential theo môi trường | IAM/RBAC review |
| Input validation | Validate header, path, query, parameters và context | Contract tests |
| Replay/idempotency | Resource identity và request intent được kiểm tra | Concurrent retry tests |
| Audit | Lifecycle và quyền truy cập có actor, resource, decision | Audit event tests |
| Supply chain | Dependency/image scan và artifact provenance | CI reports |
| Runtime | Non-root, read-only filesystem nếu phù hợp, seccomp/capabilities tối thiểu | Pod security checks |

Baseline phải ghi rõ owner, nơi cấu hình và cách xác minh. Một mục không có bằng chứng kiểm tra được chưa nên được đánh dấu hoàn tất.

## 4. Xác thực platform và bảo vệ trust boundary

Broker cần xác định platform client trước khi tin originating identity hoặc context. Cơ chế có thể là Basic Authentication qua TLS, mTLS hoặc integration-specific identity. Chọn cơ chế tương thích với platform nhưng không dùng một credential quản trị chung cho mọi foundation nếu có thể tách riêng.

Các bước ở API boundary:

1. Xác thực platform principal.
2. Kiểm tra OSB API version header.
3. Xác định platform instance được principal đó phép đại diện.
4. Parse originating identity theo adapter được hỗ trợ.
5. Resolve context thành tenant/platform scope.
6. Tải resource và đối chiếu ownership đã lưu.
7. Kiểm tra quyền operation.
8. Chỉ sau đó mới tạo reservation hoặc gọi application service.

Header X-Broker-API-Originating-Identity là thông tin platform chuyển tiếp, không phải access token. Base64 payload không phải encryption hoặc chữ ký. Ingress phải loại bỏ header cùng tên do client tự gửi trước khi platform assertion được thêm; broker chỉ tin header khi request đến từ đường đi đã xác thực.

### 4.1. Phân biệt identity, context và provider principal

| Giá trị | Dùng để | Không được dùng thay |
|---|---|---|
| Platform principal | Xác thực foundation/client | Actor cuối hoặc tenant owner |
| Originating identity | Audit và policy theo actor | HTTP authentication |
| Context | Resolve platform scope/tenant | Bằng chứng quyền sở hữu |
| Tenant ID đã lưu | Ownership của instance | Platform authentication |
| Provider principal | Gọi cloud/Kubernetes API | User identity từ platform |

Không lấy tenant ID trực tiếp từ parameters hoặc context rồi tin cậy. Resolve tenant qua platform registry và so sánh với owner đã lưu trên instance.

## 5. Authorization theo tenant và resource

Mọi endpoint truy cập instance hoặc binding phải kiểm tra scope. Không đủ nếu chỉ bảo vệ provision và deprovision; retrieve, last_operation, bind và unbind cũng có thể làm lộ dữ liệu hoặc tác động resource khác.

Một policy có thể đánh giá:

- Platform principal được phép dùng platformInstanceId này không?
- Tenant đã resolve có khớp owner của instance không?
- Actor có quyền thực hiện operation không?
- Instance đang ở state cho phép thao tác không?
- Binding có thuộc đúng instance và tenant không?
- Operation token có thuộc platform/resource được yêu cầu không?

Ví dụ bảng authorization matrix:

| Operation | Kiểm tra tối thiểu |
|---|---|
| GET catalog | Platform principal hợp lệ |
| Provision | Platform access, tenant entitlement, service/plan policy |
| Update | Instance owner, plan/update policy, state |
| Bind | Instance owner, bindable, consumer scope, permission profile |
| Retrieve binding | Instance + binding ownership và capability |
| Unbind | Instance + binding ownership |
| Deprovision | Instance owner và lifecycle state |
| Last operation | Platform + instance + operation ownership |

Nếu không muốn tiết lộ resource có tồn tại ở tenant khác, policy có thể trả 404 thay vì 403. Dù chọn cách nào, behavior phải nhất quán và có test chống enumeration.

## 6. Bảo vệ credentials và secrets

Broker xử lý nhiều loại secret: platform client credentials, provider API tokens, database passwords, binding credentials, certificates và secret-manager access. Mỗi loại cần lifecycle riêng.

Nguyên tắc:

- Không commit secret vào source code, Docker image hoặc manifest plaintext.
- Không log Authorization header, password, token, private key hoặc raw binding response.
- Lưu secret trong vault hoặc external secret manager.
- Database chỉ lưu secret reference hoặc ciphertext theo thiết kế đã review.
- Tách secret theo environment, provider account và tenant khi cần.
- Giới hạn quyền đọc secret cho API/worker đúng use case.
- Có rotation, expiry và revoke process.
- Audit truy cập secret nhưng không ghi secret value.
- Không truyền secret qua queue message hoặc trace attribute.

Ví dụ binding record:

~~~json
{
  "platform_instance_id": "cf-prod",
  "instance_id": "instance-7f3a",
  "binding_id": "binding-billing",
  "principal_id": "provider-user-991",
  "credential_ref": "vault://broker/prod/bindings/7f3a/billing",
  "status": "ACTIVE"
}
~~~

Nếu provider không cho đọc lại password sau khi tạo, broker cần lưu secret an toàn để retry binding có thể trả đúng credential. Nếu secret không thể khôi phục, phải có quy trình rotation/recovery có kiểm soát; không âm thầm tạo principal mới mỗi lần retry.

## 7. Bảo vệ provider adapter và Kubernetes permissions

Provider adapter nên dùng workload identity hoặc service account riêng với quyền tối thiểu. Tách quyền đọc inventory, tạo resource, cập nhật và xóa nếu provider hỗ trợ phân quyền chi tiết.

Với Kubernetes:

- Tách namespace chạy broker khỏi namespace tenant resources.
- Dùng service account riêng cho API và worker nếu quyền khác nhau.
- Ưu tiên Role/RoleBinding theo namespace khi có thể.
- Không cấp cluster-admin cho broker chỉ để đơn giản hóa.
- Chỉ cấp quyền đọc Secret nếu broker thật sự cần.
- Giới hạn egress tới Kubernetes API, provider endpoint, database, queue và vault.
- Dùng NetworkPolicy nếu CNI hỗ trợ.
- Ghi audit provider operation và actor nội bộ đã thực hiện.

Một Role ví dụ:

~~~yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: broker-resource-manager
  namespace: tenant-payments
rules:
  - apiGroups: [""]
    resources: ["services", "persistentvolumeclaims"]
    verbs: ["get", "list", "watch", "create", "update", "patch", "delete"]
~~~

Quyền thực tế cần giới hạn theo resource types và namespaces mà broker quản lý. Không copy manifest mẫu vào production mà chưa review scope và nhu cầu.

## 8. Input validation và error safety

Validate mọi dữ liệu đến từ platform:

- Path IDs: giới hạn độ dài và ký tự.
- Query parameters: parse đúng kiểu, reject duplicate hoặc malformed nếu contract yêu cầu.
- X-Broker-API-Version: parse major/minor và kiểm tra dải hỗ trợ.
- Originating identity: giới hạn header size, Base64 decode có kiểm soát, JSON depth/size limit.
- Context: schema theo platform adapter và allowlist field.
- Parameters: schema theo service/plan/operation.
- Content-Type và request body: validate trước side effect.

Error response cần tuân theo OSB contract. Không trả stack trace, SQL, provider raw body hoặc secret. Dùng status code đúng nguyên nhân: 400 cho request không hợp lệ, 409 cho conflict trạng thái/intent, 412 cho precondition không thỏa như API version không hỗ trợ khi contract yêu cầu, và lỗi downstream theo policy đã định nghĩa.

Không map mọi exception thành 500 hoặc mọi duplicate-key thành 409. Khi có duplicate key, đọc lại record và fingerprint để phân biệt retry cùng ý định với conflict.

## 9. Idempotency và state transition

Mỗi lifecycle resource cần identity ổn định:

- Instance: platform scope + instance ID.
- Binding: platform scope + instance ID + binding ID.
- Operation: operation token trong platform/resource scope.
- Provider resource: provider account + external resource key.

Cùng ID và cùng request intent phải trả hoặc tiếp tục kết quả hiện có. Cùng ID nhưng payload khác phải được phát hiện là conflict. Database unique constraints, optimistic locking và provider-side idempotency cần phối hợp.

State machine instance:

~~~mermaid
stateDiagram-v2
    [*] --> PROVISIONING
    PROVISIONING --> ACTIVE
    PROVISIONING --> FAILED
    ACTIVE --> UPDATING
    UPDATING --> ACTIVE
    UPDATING --> FAILED
    ACTIVE --> DEPROVISIONING
    DEPROVISIONING --> DEPROVISIONED
    DEPROVISIONING --> FAILED
~~~

Không thực hiện provider call khi request đã bị authorization hoặc validation từ chối. Không chuyển instance sang ACTIVE trước khi provider state được xác nhận. Retry worker phải kiểm tra terminal state và provider inventory trước khi lặp side effect.

## 10. Asynchronous operations và recovery

Provision/update/deprovision có thể cần xử lý bất đồng bộ. Broker cần lưu operation token, state, attempt count, provider request ID và timestamps. HTTP 202 chỉ thể hiện request đã được chấp nhận theo contract; platform poll last_operation để biết tiến trình.

Dùng transactional outbox để ghi operation và event trong cùng transaction. Publisher có thể gửi event nhiều lần; worker phải idempotent. Worker claim operation bằng lease hoặc compare-and-set, gọi provider ngoài transaction dài, sau đó cập nhật resource/operation trong transaction mới.

Các failure windows cần xử lý:

| Failure window | Recovery |
|---|---|
| Commit DB nhưng publish queue lỗi | Outbox publisher gửi lại |
| Queue giao message nhiều lần | Worker kiểm tra operation state và idempotency |
| Provider tạo resource nhưng timeout | Tra cứu external key/provider request ID |
| Provider success nhưng broker crash trước commit | Reconcile provider rồi hoàn tất mapping |
| Worker chết khi giữ lease | Lease hết hạn và worker khác claim |
| Secret retrieval thất bại | Không tạo credential mới; retry hoặc đánh dấu cần điều tra |

Last operation GET chỉ đọc state. Polling nhiều lần không được tạo job hoặc gọi provider.

## 11. Thiết kế telemetry có thể vận hành

Mỗi lifecycle event nên có schema ổn định. Field chung gợi ý:

| Field | Mục đích |
|---|---|
| timestamp, level | Thời điểm và mức độ |
| service.name, service.version | Broker build |
| event.name | Hành động nghiệp vụ |
| request.id | HTTP request |
| trace_id, span_id | Distributed trace |
| platform.id | Foundation/cluster đã xác thực |
| tenant.id | Tenant đã resolve |
| service.instance.id | OSB instance |
| service.binding.id | OSB binding |
| operation.id, operation.type | Async operation |
| provider.name, provider.request.id | Provider interaction |
| outcome, duration_ms, retry_count | Kết quả và hiệu năng |
| error.type, error.code | Lỗi đã chuẩn hóa |

Không log raw request/response body. Không đưa credentials, private key, Authorization header hoặc secret vào MDC. ID có cardinality cao có thể nằm trong log, nhưng không nên làm metric label.

### 11.1. Event names theo lifecycle

Ví dụ event names ổn định:

- osb.request.received
- osb.request.rejected
- osb.provision.accepted
- osb.provision.started
- provider.request.sent
- provider.request.completed
- osb.provision.completed
- osb.binding.created
- osb.binding.revoked
- osb.deprovision.completed
- osb.operation.failed

Không nhúng instance ID hoặc tenant ID vào event name. Đặt chúng trong field riêng để query.

### 11.2. Correlation qua worker

Request ID nối một HTTP request; operation ID nối lifecycle kéo dài; trace ID nối span trong một trace. Worker có thể chạy ở pod khác và sau khi HTTP request kết thúc, vì vậy cần lưu operation/correlation metadata trong database hoặc queue message.

MDC dựa trên ThreadLocal không tự động an toàn qua executor hoặc message listener. Dùng TaskDecorator/context propagation phù hợp và luôn clear/restore context sau task. Với reactive pipeline, dùng Reactor context propagation tương thích thay vì giả định ThreadLocal.

## 12. Metrics, SLI và SLO

Chọn metrics trả lời câu hỏi vận hành, không chỉ đếm số request.

| SLI | Cách đo | Ví dụ mục tiêu SLO |
|---|---|---|
| API availability | Request hợp lệ không bị lỗi broker nội bộ / tổng request hợp lệ | 99,9% theo tháng |
| Provision completion | Provision thành công trong ngưỡng thời gian / provision được chấp nhận | 95% trong 5 phút |
| Binding latency | Thời gian từ accept đến ACTIVE | p95 dưới 10 giây |
| Async operation age | Tuổi operation chưa terminal | Không operation bình thường vượt 15 phút |
| Provider error rate | Provider failures / provider calls | Theo từng provider |
| Queue lag | Tuổi message lâu nhất chưa xử lý | p95 dưới 60 giây |
| Secret retrieval success | Secret reads thành công / tổng reads hợp lệ | Theo vault dependency |

Các con số trên là mục tiêu minh họa, cần điều chỉnh theo provider, plan và cam kết sản phẩm. Không gộp 4xx do client gửi sai vào availability numerator/denominator như lỗi broker nếu SLO định nghĩa không tính client error.

### 12.1. RED và USE signals

Với API/service, theo dõi:

- **Rate:** số request theo endpoint và status.
- **Errors:** tỷ lệ lỗi, phân nhóm validation, conflict, provider và internal.
- **Duration:** latency p50/p95/p99.

Với dependency/hạ tầng, theo dõi:

- **Utilization:** CPU, memory, connection pool.
- **Saturation:** queue backlog, thread pool queue, DB pool wait.
- **Errors:** DB, queue, vault và provider failures.

Không dùng instance ID, binding ID hoặc operation ID làm metric labels vì cardinality cao. Dùng platform, operation type, provider và status class nếu tập giá trị hữu hạn.

## 13. Distributed tracing và audit

Trace nên nối API request, application service, database, outbox publisher, worker và provider adapter. Propagate trace context qua queue theo chuẩn instrumentation. Khi operation kéo dài qua nhiều trace, operation ID vẫn là khóa nghiệp vụ bền vững.

Audit cần trả lời: ai thực hiện hành động, trên tenant/resource nào, hành động gì, được phép hay bị từ chối, khi nào và kết quả ra sao. Audit có thể lưu riêng hoặc dùng sink append-only với quyền truy cập hạn chế.

Không coi application log là audit trail bất biến. Không lưu raw identity payload hoặc secret trong audit. Ghi actor subject đã chuẩn hóa, platform, tenant, resource ID, decision, correlation ID và timestamp.

## 14. Dashboard và alert tối thiểu

Dashboard nên có các nhóm:

1. API health: request rate, status distribution, latency.
2. Lifecycle: provision/update/bind/unbind/deprovision success và duration.
3. Async: queue lag, active operations, retry, terminal failures.
4. Provider: latency, timeout, throttling và error rate theo provider.
5. Security: authentication failures, authorization denials, tenant mismatch, secret access anomalies.
6. Runtime: CPU, memory, restart count, DB pool, thread pool.
7. Data integrity: orphan resource, duplicate mapping, stuck reservation và reconciliation drift.

Alert nên gắn với hành động:

| Alert | Điều kiện ví dụ | Hành động đầu tiên |
|---|---|---|
| Broker availability thấp | SLO burn rate vượt ngưỡng | Kiểm tra ingress, pod readiness và dependency |
| Queue backlog tăng | Oldest message vượt threshold | Kiểm tra worker, provider latency và consumer errors |
| Provider timeout tăng | Tỷ lệ timeout vượt baseline | Kiểm tra provider health, quota và network |
| Operation stuck | Operation không đổi state quá ngưỡng | Tra provider state và worker lease |
| Tenant mismatch | Có request scope mismatch | Kiểm tra platform identity/context và audit |
| Secret access denied | Lỗi vault tăng | Kiểm tra workload identity, policy và rotation |
| Pod restart tăng | CrashLoop/OOM | Kiểm tra logs, memory, startup dependency |

Không tạo alert cho mọi exception đơn lẻ. Dùng rate, duration, severity và burn rate để tránh alert noise.

## 15. Kubernetes deployment baseline

Broker nên chạy với image bất biến, non-root user, resource requests/limits, probes và security context phù hợp. API và worker có thể là hai deployment riêng để scale độc lập và cấp quyền khác nhau.

Ví dụ Deployment rút gọn:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: service-broker-api
  namespace: broker-system
spec:
  replicas: 3
  selector:
    matchLabels:
      app: service-broker-api
  template:
    metadata:
      labels:
        app: service-broker-api
    spec:
      serviceAccountName: service-broker-api
      containers:
        - name: broker
          image: registry.example.invalid/platform/service-broker:1.8.0
          ports:
            - name: http
              containerPort: 8080
          env:
            - name: SPRING_PROFILES_ACTIVE
              value: production
            - name: SPRING_DATASOURCE_URL
              valueFrom:
                secretKeyRef:
                  name: broker-database
                  key: jdbc-url
          resources:
            requests:
              cpu: 250m
              memory: 512Mi
            limits:
              cpu: "2"
              memory: 2Gi
          securityContext:
            runAsNonRoot: true
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: http
            periodSeconds: 10
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 20
~~~

Manifest là ví dụ khởi đầu. Production cần image digest, TLS ingress, NetworkPolicy, pod security settings, service account permissions, secret injection và probe configuration phù hợp. Không đưa password vào env literal hoặc commit Secret manifest plaintext.

### 15.1. Readiness khác liveness

- **Liveness** trả lời process có cần restart vì không còn hoạt động đúng không.
- **Readiness** trả lời pod có thể nhận traffic mới không.
- **Startup probe** có thể bảo vệ ứng dụng khởi động chậm khỏi liveness restart quá sớm.

Readiness có thể kiểm tra dependency tối thiểu cần cho API, nhưng tránh làm mọi pod unready chỉ vì một provider phụ trợ tạm thời lỗi nếu broker vẫn có thể phục vụ catalog hoặc các operation khác. Liveness không nên phụ thuộc provider hoặc thực hiện side effect.

## 16. CI/CD gates trước khi deploy

Pipeline cần tạo bằng chứng trước khi thay đổi production.

| Gate | Kiểm tra | Điều kiện đạt |
|---|---|---|
| Compile/package | Build ứng dụng | Build thành công |
| Unit tests | Domain policy, state machine, validators | Không test fail |
| Integration tests | PostgreSQL/queue/provider test dependencies | Test và migration pass |
| Contract tests | OSB request/response và catalog | Contract tương thích |
| Security tests | Auth, tenant isolation, redaction | Negative tests pass |
| Dependency scan | CVE và license policy | Không còn finding vượt policy |
| Image scan | OS packages và application layers | Không có critical/high bị chặn |
| SBOM/provenance | Artifact inventory và nguồn build | Được tạo và lưu |
| Migration validation | Upgrade schema từ phiên bản đang chạy | Expand migration pass |
| Deployment smoke | Readiness, catalog, một flow test | Smoke pass |
| Rollout health | Error rate, latency, restart, queue lag | Không vượt rollback threshold |

Không bỏ qua test thất bại chỉ vì unit test pass. Nếu integration test không chạy do Docker unavailable, pipeline cần đánh dấu không đạt hoặc explicit skipped có policy; không coi skipped là pass.

### 16.1. Expand-and-contract database migration

Khi deployment rolling, pod cũ và mới có thể chạy cùng lúc. Migration nên theo trình tự:

1. Expand: thêm bảng/cột/index tương thích với code cũ.
2. Deploy code mới có thể đọc cả dạng cũ và mới.
3. Backfill dữ liệu theo batch có thể chạy lại.
4. Chuyển read/write sang schema mới.
5. Theo dõi và xác minh.
6. Contract: chỉ xóa cột/constraint cũ sau khi không còn consumer.

Không chạy migration destructive trước khi code mới sẵn sàng và rollback plan đã được đánh giá.

## 17. Release readiness checklist

Trước khi cho broker nhận traffic production, cần xác minh:

- [ ] Platform authentication đã bật và test credential sai bị từ chối.
- [ ] Tenant isolation đã test trên instance, binding và operation endpoints.
- [ ] Originating identity/context được validate và không thay thế authentication.
- [ ] TLS, ingress và trusted proxy configuration đã review.
- [ ] Provider credential có least privilege.
- [ ] Secrets không xuất hiện trong logs, traces, error response hoặc queue payload.
- [ ] Idempotency và concurrent lifecycle tests pass.
- [ ] Async operation có outbox, retry, lease và reconciliation.
- [ ] Database migration tương thích với rolling deployment.
- [ ] Catalog và plan IDs tương thích với platform đang dùng.
- [ ] Structured log có platform/instance/binding/operation fields.
- [ ] Metrics, traces, dashboard và alert đã hoạt động.
- [ ] SLO và error budget được owner chấp thuận.
- [ ] Kubernetes requests/limits, probes, RBAC và NetworkPolicy đã review.
- [ ] Dependency/image scan và SBOM gates pass.
- [ ] Backup/restore đã được kiểm chứng.
- [ ] Runbook và on-call ownership đã rõ.
- [ ] Canary và rollback criteria đã định nghĩa.
- [ ] Có smoke test sau deploy và reconciliation sau rollout.

Một release không nên được đánh dấu ready chỉ vì Deployment có đủ replicas. Cần xác nhận application contract, dependency, security và vận hành đều đạt.

## 18. Runbook: provider outage

Khi provider timeout hoặc trả lỗi hàng loạt:

1. Xem provider error rate và latency theo provider/region.
2. Kiểm tra network, credential expiry, provider quota và rate limit.
3. Xác định operation đang RUNNING/RETRYING và queue lag.
4. Tạm giảm concurrency hoặc mở circuit breaker theo policy nếu provider quá tải.
5. Không xóa reservation hoặc đánh dấu FAILED chỉ dựa trên timeout.
6. Reconcile provider resource theo external key/provider request ID.
7. Khi provider phục hồi, cho worker retry theo exponential backoff và jitter.
8. Xác nhận operation terminal và không có duplicate resource.

Không retry không giới hạn. Retry budget và maximum age cần được cấu hình theo operation type.

## 19. Runbook: queue backlog hoặc worker failure

Khi backlog tăng:

- Kiểm tra consumer count, worker restarts và dead-letter queue.
- Phân biệt message chờ xử lý với poison message.
- Kiểm tra DB connection pool và provider latency.
- Kiểm tra lease hết hạn và operation bị claim quá lâu.
- Scale worker trong giới hạn provider concurrency.
- Không purge queue để giảm backlog nếu chưa hiểu message ownership.
- Với message lỗi schema, quarantine và lưu event ID để điều tra.
- Sau khi khôi phục, đối chiếu operation store với provider inventory.

Nếu worker crash sau provider success, reconciliation phải xác định resource đã tồn tại trước khi chạy lại create.

## 20. Runbook: nghi ngờ credential bị lộ

Nếu log, trace hoặc response có thể đã chứa secret:

1. Xác định secret type, secret reference, thời gian và phạm vi exposure.
2. Hạn chế quyền truy cập log/trace có liên quan.
3. Xác định binding hoặc provider account chịu ảnh hưởng.
4. Rotate/revoke credential theo thứ tự không làm mất quyền quản lý resource.
5. Cập nhật secret reference và kiểm tra consumer connectivity.
6. Xóa hoặc hạn chế bản sao dữ liệu theo incident policy và retention rules.
7. Kiểm tra log pipeline, debug level và code path gây rò rỉ.
8. Thêm regression test để ngăn tái diễn.
9. Ghi audit incident và xác nhận credential cũ không còn hiệu lực.

Không xóa audit evidence cần cho điều tra trước khi incident owner xác định cách bảo toàn bằng chứng.

## 21. Runbook: rollback release

Rollback chỉ an toàn khi phiên bản cũ tương thích với database và state đã được phiên bản mới ghi.

Trước rollback:

- Xác định schema changes đã chạy.
- Kiểm tra operation đang chạy và worker queue.
- Xác định có field/state mới mà code cũ không hiểu không.
- Dừng mutation nếu cần để tránh split-brain.
- Giữ một writer duy nhất cho mỗi resource.
- Nếu schema đã expand, code cũ có thể tiếp tục chạy; nếu schema đã contract/destructive, không tự động rollback.
- Kiểm tra secret rotation và provider mapping.
- Chuyển traffic theo routing policy.
- Theo dõi SLO, queue và lifecycle smoke test sau rollback.

Nếu phiên bản mới đã tạo state không tương thích, forward fix thường an toàn hơn rollback mù quáng.

## 22. Kịch bản thực hành capstone

Thực hiện các giai đoạn sau trong một môi trường test/staging có provider sandbox.

### Giai đoạn A — Threat model và baseline

1. Vẽ data flow từ Cloud Foundry/Kubernetes tới broker, database, queue, vault và provider.
2. Liệt kê tài sản cần bảo vệ: platform credentials, binding secrets, provider tokens, tenant mappings và operation records.
3. Xác định trust boundary và attacker scenarios: spoofed identity, cross-tenant access, replay, secret leakage, provider abuse.
4. Viết security baseline và map mỗi control tới một test hoặc configuration.
5. Review provider IAM/RBAC theo least privilege.

**Deliverable:** threat model ngắn, security control matrix và danh sách risk owner.

### Giai đoạn B — Hardening application

1. Bật platform authentication.
2. Validate OSB API version, originating identity và context.
3. Implement tenant/resource authorization cho tất cả endpoint.
4. Bảo vệ secret bằng vault reference.
5. Chuẩn hóa error mapping và redaction.
6. Kiểm tra idempotency, unique constraints và state transitions.
7. Thêm audit event cho allow/deny và lifecycle mutation.

**Deliverable:** cấu hình bảo mật, code path đã harden và test report.

### Giai đoạn C — Observability

1. Chuẩn hóa structured log schema.
2. Propagate request ID, trace context và operation ID.
3. Thêm metrics cho API, lifecycle, provider và queue.
4. Định nghĩa SLI/SLO.
5. Tạo dashboard và alert.
6. Kiểm tra không có secret hoặc high-cardinality metric labels.
7. Viết truy vấn tìm lifecycle theo platform + instance + operation.

**Deliverable:** telemetry schema, dashboard screenshot/export và alert rules.

### Giai đoạn D — Kubernetes và CI/CD

1. Build image bất biến và tạo SBOM.
2. Cấu hình non-root, resource limits, probes, service account và RBAC.
3. Cấu hình TLS ingress, network policy và secret injection.
4. Thêm integration/contract/security tests vào pipeline.
5. Chạy dependency và image scan.
6. Validate database migration theo expand-and-contract.
7. Deploy canary và smoke test.
8. Chỉ mở rộng rollout khi health gate pass.

**Deliverable:** deployment manifests, pipeline configuration, gate results và rollout record.

### Giai đoạn E — Incident simulation

Mô phỏng ít nhất ba tình huống:

- Provider timeout sau khi đã tạo resource.
- Worker bị restart khi queue có message.
- Tenant gửi request truy cập binding của tenant khác.

Với mỗi tình huống, ghi nhận detection signal, log/trace cần truy vấn, hành động runbook, recovery result và regression test.

**Deliverable:** incident timeline, runbook execution record và test bổ sung.

## 23. Acceptance criteria

Capstone được xem là hoàn thành khi reviewer có thể xác minh các điều kiện:

| Nhóm | Tiêu chí chấp nhận |
|---|---|
| Security | Request không xác thực bị từ chối trước side effect |
| Tenant isolation | Không truy cập chéo instance/binding/operation |
| Secret safety | Không có secret trong log, trace, error response hoặc message |
| Idempotency | Retry/concurrent request không tạo resource trùng |
| Async recovery | Provider timeout/worker restart có thể phục hồi |
| Observability | Truy vấn được một lifecycle bằng platform, instance và operation |
| SLO | Có SLI, SLO, dashboard và alert có owner |
| Kubernetes | Probes, resources, RBAC, TLS và secret injection được kiểm tra |
| CI/CD | Test, scan, migration và smoke gates có kết quả lưu lại |
| Rollout | Canary, go/no-go và rollback criteria rõ |
| Operations | Có runbook cho provider outage, queue backlog, secret incident và rollback |

Reviewer nên yêu cầu bằng chứng thực tế: test output, policy/configuration, telemetry query, deployment state và runbook record. Một tài liệu mô tả rằng hệ thống “đã bảo mật” mà không có negative tests hoặc configuration evidence chưa đủ để đạt.

## 24. Bộ test tối thiểu cần có

| Test | Kỳ vọng |
|---|---|
| Platform credential sai | 401, không có provider call |
| Tenant context mismatch | Bị từ chối, không đọc/ghi resource |
| Cross-tenant binding retrieve | Không lộ credentials |
| Originating identity spoof | Không được tin nếu không qua trust boundary |
| Malformed parameters | 400 theo contract, không side effect |
| Unsupported OSB API version | Precondition error theo contract |
| Duplicate provision cùng intent | Một instance/provider resource |
| Duplicate provision khác intent | Conflict |
| Concurrent bind | Một binding/principal |
| Provider timeout sau create | Reconciliation tìm resource đã tạo |
| Worker redelivery | Operation không tạo side effect lần hai |
| Secret redaction | Output không chứa canary secret |
| MDC cleanup | Request sau không nhận context cũ |
| Migration compatibility | Code cũ/mới không phá schema trong rollout |
| Readiness | Pod chỉ nhận traffic khi dependency bắt buộc sẵn sàng |
| Rollback | Không tạo hai writer hoặc làm mất mapping |

Dùng Testcontainers cho database/queue/Redis khi cần kiểm tra behavior thật. Dùng HTTP stub cho provider failure scenarios xác định; dùng sandbox test cho behavior cloud không được emulator mô phỏng đầy đủ.

## 25. Những lỗi thường làm release không an toàn

| Lỗi | Tác động | Biện pháp |
|---|---|---|
| Chỉ bật authentication mà không kiểm tra tenant ownership | Cross-tenant access | Authorization trên từng resource |
| Tin originating identity như token | Identity spoofing | Platform auth và trusted ingress |
| Log toàn bộ binding response | Credential exposure | Allowlist fields và redaction |
| Retry provider không idempotent | Resource/principal trùng | External key và reconciliation |
| Worker nhận message nhưng không persist operation state | Mất khả năng recovery | Outbox và operation store |
| Liveness phụ thuộc provider | Pod restart dây chuyền khi provider outage | Tách liveness/readiness |
| Không có queue lag alert | Operation bị kẹt lâu | SLO/alert cho backlog và operation age |
| Metric label chứa instance ID | Cardinality bùng nổ | Đưa ID vào log/trace |
| Chỉ test H2 khi production dùng PostgreSQL | Bỏ sót migration/transaction bug | Testcontainers với engine thật |
| Rollback sau destructive migration | Broker cũ không đọc được state | Expand-and-contract và forward-fix plan |
| CI bỏ qua security scan | Artifact rủi ro được phát hành | Release gate có policy |
| Không có runbook | Phục hồi tùy hứng, kéo dài incident | Diễn tập và cập nhật runbook |

## 26. Hồ sơ bàn giao cho production owner

Tập hợp các artefact sau để reviewer và on-call có thể tiếp nhận:

1. Sơ đồ kiến trúc và trust boundaries.
2. Threat model và security control matrix.
3. Authentication/authorization policy và provider permission review.
4. Secret inventory, rotation owner và recovery procedure.
5. OSB lifecycle state machine và idempotency design.
6. Structured logging schema và event catalog.
7. Metric definitions, SLI/SLO, dashboards và alert rules.
8. Kubernetes manifests và deployment configuration.
9. CI/CD pipeline gates, SBOM và scan reports.
10. Database migration plan và rollback compatibility notes.
11. Integration/contract/security test results.
12. Runbook và incident simulation records.
13. Release decision, approver và go/no-go evidence.

Không đưa credential hoặc private key vào handoff package. Các secret chỉ được tham chiếu bằng secret reference và owner/quy trình truy cập.

## 27. Checklist cuối cùng

- [ ] Platform identity được xác thực và ràng buộc với platform scope.
- [ ] Originating identity/context được parse, validate và dùng đúng mục đích.
- [ ] Tenant/resource authorization bao phủ mọi endpoint.
- [ ] Provider adapter dùng least-privilege identity.
- [ ] Secrets có vault reference, rotation và audit.
- [ ] Structured logs không chứa secret/PII thừa.
- [ ] Metrics không dùng ID cardinality cao làm label.
- [ ] Trace và operation ID nối được async lifecycle.
- [ ] SLI/SLO có mục tiêu, owner và alert.
- [ ] Idempotency và recovery được kiểm tra bằng integration tests.
- [ ] Kubernetes deployment có TLS, RBAC, probes, resources và network controls.
- [ ] CI/CD có unit, integration, contract, security, image và migration gates.
- [ ] Backup/restore và rollback được diễn tập.
- [ ] Runbook có thể thực hiện bởi on-call.
- [ ] Reviewer có bằng chứng cho từng acceptance criterion.

Một service broker production-ready là hệ thống vừa thực thi đúng contract OSB, vừa bảo vệ quyền sở hữu tài nguyên, phục hồi được khi provider hoặc worker lỗi và cung cấp tín hiệu đủ rõ để người vận hành ra quyết định. Capstone này kết nối security hardening, telemetry, Kubernetes deployment và release gates thành một quy trình có thể review. Khi mỗi tiêu chí đều gắn với test, cấu hình hoặc bằng chứng vận hành, Spring Cloud Service Broker có cơ sở để triển khai an toàn và duy trì chất lượng sau khi production traffic bắt đầu.
