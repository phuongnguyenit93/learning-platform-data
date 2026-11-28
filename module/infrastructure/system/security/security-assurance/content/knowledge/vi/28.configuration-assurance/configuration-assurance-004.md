# Cấu hình runtime (Runtime Configuration) trong Configuration Assurance

## 1. Tại sao cấu hình runtime là một chủ đề security assurance?

Một nhóm phát triển kiểm tra repository của Invoice SaaS và thấy cấu hình bảo mật đã đúng: API bắt buộc xác thực, TLS được bật, cookie được gắn các thuộc tính cần thiết, workload không chạy với quyền root và database dùng kết nối mã hóa. Thế nhưng ở production, một instance vẫn nạp biến môi trường cũ cho phép debug endpoints, một ingress route không áp policy mới, một pod dùng service account khác và một feature flag vô tình bật đường export cũ. Tài liệu trong Git đúng, nhưng **trạng thái thực thi tại thời điểm đánh giá** lại khác.

**Cấu hình runtime (runtime configuration)** là tập tham số, policy, feature switches, secrets references và lựa chọn vận hành **được tiến trình, service, container, nền tảng hoặc control plane sử dụng khi hệ thống thực sự chạy**. Chúng ảnh hưởng cách ứng dụng xử lý request, cấp quyền, dùng tài nguyên, ghi log, mã hóa, kết nối tới dependencies và xử lý lỗi.

Trong chương **Configuration assurance**, câu hỏi quan trọng không phải chỉ là “đã có một cấu hình an toàn được viết ra chưa?”, mà là:

> **Cấu hình bảo mật nào đang có hiệu lực trên đúng tài sản, phiên bản, vùng, tenant và thời điểm? Có bằng chứng độc lập đủ tin cậy để chứng minh nó thỏa yêu cầu hay không?**

Đối với module **SECURITY_SECURITY_ASSURANCE**, mục tiêu lớn hơn là xây dựng cách đánh giá có bằng chứng rằng hệ thống đáp ứng các mục tiêu bảo mật, từ phân tích rủi ro, security requirements và controls tới kiểm thử, audit, remediation và bảo đảm liên tục. Runtime configuration là một mối nối quan trọng giữa **control được thiết kế** và **control đang hoạt động**.

Chuỗi lập luận của bài:

**Security objective → testable configuration requirement → approved baseline → actual deployment → effective runtime state → behavior test → evidence → finding/remediation → continuous assurance.**

### Ví dụ xuyên suốt

Bài dùng **Invoice SaaS giả định**, gồm Java/Spring Boot API, worker xuất hóa đơn, Kubernetes, managed database, object storage, API gateway, IdP và cloud IAM. Tất cả hostnames, accounts, values, IDs và kết quả thử trong ví dụ đều minh họa; không phải quan sát của một hệ thống thật.

## 2. Phân biệt cấu hình declared, deployed, loaded, effective và observed

Các trạng thái sau dễ bị đánh đồng nhưng có ý nghĩa assurance khác nhau.

| Trạng thái | Nghĩa | Nguồn ví dụ | Không tự chứng minh |
| --- | --- | --- | --- |
| **Desired/declared** | Cấu hình dự định áp dụng theo thiết kế/IaC/Git. | Spring YAML, Helm values, Terraform, policy repo. | Hệ thống đã triển khai hoặc dùng cấu hình đó. |
| **Approved baseline** | Desired state được policy/risk/change owner chấp thuận. | Versioned hardening baseline, review/approval. | Các control phù hợp mọi workload hay effective. |
| **Deployed/applied** | Config artifact/resource được đưa tới host/cluster. | Deployment history, resource spec, config artifact hash. | Process đã reload hoặc controller đã reconcile. |
| **Loaded** | Process đã đọc một tập settings vào memory/startup state. | Safe in-process diagnostic, startup log có redaction. | Tham số đó thực sự kiểm soát mọi request/path. |
| **Effective** | Chính sách/giá trị đang quyết định hành vi trên một đường thực thi cụ thể. | Security decision, actual policy evaluation, provider API readback. | Mọi đường khác đều tương đương. |
| **Observed behavior** | Kết quả kiểm thử/hệ thống phản hồi dưới preconditions cụ thể. | Authorized negative/positive test, runtime telemetry. | Root cause hoặc toàn bộ control coverage. |
| **Attested state** | Trạng thái được nguồn xác thực/chứng thực theo phạm vi, thời điểm. | Signed release manifest, attestation/source provenance. | Attestation chính xác nếu nguồn đo bị sai/compromised. |

### Một ví dụ rất phổ biến

File Git có `app.security.debug-enabled: false`, nhưng một biến môi trường có độ ưu tiên cao hơn đặt cùng property thành `true`. Việc review Git chỉ xác nhận **declared intent**. Muốn kết luận debug endpoint bị tắt, phải xác minh **property source resolution**, trạng thái process và hành vi tại đúng route.

### Không có “một source of truth” cho mọi assertion

Git có thể là source of truth cho **approved intent**; Kubernetes API cho **desired spec hiện được control plane lưu**; process inspection cho **loaded value**; policy decision logs và negative tests cho **effective behavior**. Chúng hỗ trợ các claim khác nhau. Một nguồn duy nhất không thể tự chứng minh tất cả.

## 3. Runtime configuration khác build-time configuration và code ra sao?

| Loại thay đổi | Ví dụ | Hệ quả khi đánh giá |
| --- | --- | --- |
| **Compile/build-time** | Feature bị compile out, dependency/BOM, build flags, embedded resource. | Cần source→build artifact provenance, không chỉ runtime environment. |
| **Image/package default** | Default config nằm trong container image hoặc OS package. | Cần biết image digest, inherited defaults và overrides. |
| **Deployment-time** | Env vars, Kubernetes Deployment spec, ConfigMap, secret references. | Cần readback deployment và semantics update/restart. |
| **Startup-time loaded** | Spring `@ConfigurationProperties` bind một lần khi tạo bean. | Thay ConfigMap chưa chắc đổi bean đang chạy. |
| **Dynamically evaluated** | Feature flag, authorization policy, service discovery hoặc rate limit từ config service. | Giá trị có thể thay trong lúc process chạy; cần effective evaluation point/time. |
| **Control-plane enforced** | Cloud IAM, ingress policy, security group, object storage policy. | Effective policy có thể nằm ngoài application process. |
| **Data-driven policy** | Tenant plan, role grants, account state hoặc business rule. | Không nên nhầm business data với static YAML; cần kiểm tra policy lifecycle. |

**Cấu hình runtime là giao điểm của nhiều lớp**. Một yêu cầu “chỉ người dùng tenant A được xem invoice A” phụ thuộc không chỉ property security enabled mà còn token validation, role mapping, query scoping, database permissions, cache keys và job worker identities.

## 4. Security objectives và các cấu hình runtime liên quan

| Security objective | Runtime control cần nhìn | Bằng chứng nên dùng |
| --- | --- | --- |
| **Confidentiality** | Tenant isolation, encryption/TLS, object storage access, egress, logging redaction. | Effective policy, controlled access tests, sanitized logs. |
| **Integrity** | Authorization, input/state validation, CI artifact provenance, DB constraints. | Runtime decision/transaction tests, deployed digest. |
| **Availability** | Resource limits, health checks, timeouts, rate limits, replica/quorum settings. | Runtime metrics, failover tests, config readback. |
| **Authentication** | Issuer/audience trust, session rules, MFA/step-up, credential/token lifecycle. | IdP/API controlled tests, trust policy readback. |
| **Least privilege** | Pod/user/service account, capabilities, IAM grants, secret scope, DB roles. | Effective permission inspection và denied-use tests. |
| **Accountability** | Security audit logging, time sync, log shipping, retention, integrity. | Canary events, collector health, reconciliation. |
| **Privacy** | Data minimization, sensitive fields in telemetry, retention/feature flags. | Approved data flows, redaction/retention evidence. |
| **Resilience** | Restart/rollout strategy, dependency retries, degradation mode, backup/restore. | Failure tests, DR rehearsals, operational telemetry. |

### Mối liên kết requirements–controls

Một security objective chung như “Confidentiality” chưa đủ để viết runtime test. Cần cụ thể hóa thành yêu cầu: “Mỗi response truy xuất invoice phải đi qua object-level authorization và không trả record khác tenant; security event phải không chứa customer billing data.” Từ đó mới chọn **thông số runtime, control path và expected/observed tests**.

## 5. Runtime inventory và scope: tài sản nào được đánh giá?

Một cấu hình được xem là đạt trên một pod chưa chắc đúng ở 200 pods khác. Cần định nghĩa **population**:

- Business services và các API versions còn được hỗ trợ.
- Environments: production, DR, staging, development có dữ liệu hoặc quyền nhạy cảm.
- Cloud accounts/projects/subscriptions, regions, zones và network contexts.
- Kubernetes clusters/namespaces/deployments/DaemonSets/Jobs/Pods.
- VM hosts, system services, edge gateways, serverless functions.
- Databases, caches, message brokers, object stores, search indexes.
- Service identities, secrets providers, KMS keys, IAM trust relations.
- Tenants/tier/feature cohorts, canary/blue-green rings và legacy clients.
- Temporary/ephemeral resources và decommissioned-but-still-reachable services.

### Tính mới của inventory

Một snapshot inventory ngày T chưa đủ để khẳng định cluster lúc T+1 vẫn tương đương. Autoscaling, pod replacement, progressive rollout và cloud events có thể làm thay đổi mẫu số từng phút. Các control với assets ngắn hạn cần **event-based evidence** hoặc lịch quan sát phù hợp.

### Mẫu số độc lập

Nếu configuration scanner nhận diện 120 assets và thấy cả 120 compliant, điều đó chỉ là **100% trong scanner-known population**. Cần đối soát account/cluster/service registry độc lập, kể cả những asset scanner chưa biết, để đánh giá completeness.

## 6. Security baseline cho runtime configuration là gì?

**Baseline** là tập yêu cầu cấu hình được phê duyệt theo loại tài sản, môi trường, sensitivity, threat model và policy. Nó phải đủ cụ thể để đo, không chỉ là “đặt cấu hình an toàn”.

### Một baseline tốt có

1. **Control ID** và security requirement/threat tương ứng.
2. **Asset class/scope:** API/worker/DB/pod/gateway/region/tenant tier.
3. **Expected condition:** giá trị, phạm vi hoặc hành vi, kể cả negative case.
4. **Allowed exceptions/variants:** workload nào được đặc biệt và ai duyệt.
5. **Applicable versions:** framework, platform, image hoặc feature tier.
6. **Evaluation method:** readback, effective evaluation, controlled test, sample size.
7. **Evidence schema:** source, timestamp, checksum/provenance, actor, result.
8. **Owner/risk authority:** ai chịu trách nhiệm và xử lý findings.
9. **Freshness/SLA:** bao lâu phải tái đánh giá, triggers cho event-driven checks.
10. **Remediation/retest:** điều kiện đóng và residual risk handling.

### Ví dụ baseline theo loại workload

| Runtime class | Requirement minh họa | Không nên mặc định |
| --- | --- | --- |
| Public Invoice API | Authentication and resource authorization enforced; sensitive debug endpoints disabled. | “Mọi endpoint chỉ cần có 401 là an toàn.” |
| Export worker | Chỉ đọc dữ liệu thuộc job/tenant được xác minh, service role tối thiểu. | “Worker private nên không cần kiểm quyền.” |
| Kubernetes container | Chạy không đặc quyền theo workload, hạn capabilities, phù hợp filesystem model. | “Một securityContext copy cho mọi app luôn đúng.” |
| Managed database | TLS/auth, roles và logging/backup theo data class. | “Port private là đủ.” |
| Object storage | Default private, scoped grants, link lifecycle đúng purpose. | “Tên bucket khó đoán là access control.” |
| Monitoring agent | Bảo toàn security events, redaction và trusted transport. | “Có heartbeat nên logs đều đủ.” |

Các baseline như CIS Benchmarks hoặc NIST control mappings có thể được tham khảo theo **phiên bản/nền tảng và policy thực**. Không lấy một điểm trong benchmark làm bằng chứng compliance của toàn hệ thống hoặc áp đặt cấu hình chung gây lỗi availability mà không đánh giá workload.

## 7. Runtime configuration lifecycle và điểm drift

~~~mermaid
flowchart TD
    A["Approved security requirement and baseline"] --> B["Config as code / deployment intent"]
    B --> C["Review, policy validation and change approval"]
    C --> D["Build/release and deployment"]
    D --> E["Control plane / host applies configuration"]
    E --> F["Process loads or dynamically evaluates settings"]
    F --> G["Effective authorization / transport / resource behavior"]
    G --> H["Independent readback and controlled tests"]
    H --> I{"Meets approved condition?"}
    I -- "Yes with evidence" --> J["Time-scoped assurance record"]
    I -- "No or unknown" --> K["Drift finding, rollback/repair or exception"]
    K --> C
    J --> L["Monitor events, flags, secrets and platform changes"]
    L --> F
~~~

### Các điểm drift khác nhau

**Repository drift:** approved baseline thay nhưng code/config branch không theo.

**Deployment drift:** image/manifest hoặc IaC thực tế khác Git đã duyệt.

**Runtime drift:** process chưa reload, env override khác, control plane chưa converge hoặc feature flag được cập nhật ngoài flow.

**Behavior drift:** effective response đổi vì cache, IAM, identity claims, policy evaluation, tenant-specific data hoặc dependency.

**Evidence drift:** nguồn đo ngừng hoạt động, script không còn support platform mới, metric vẫn hiển thị trạng thái PASS cũ.

Một công cụ chỉ phát hiện Git drift không tự phát hiện behavior drift; cần các phép đo ở những lớp thích hợp.

## 8. Configuration precedence: nguồn nào thắng?

Hệ thống hiện đại có nhiều nơi khai báo cùng một tham số: application defaults, profile-specific files, env vars, command-line args, cloud config service, feature-flag service hoặc runtime API. **Thứ tự ưu tiên phụ thuộc framework/version và cách ứng dụng bind/refresh**, không có thứ tự tổng quát cho mọi nền tảng.

### Ví dụ Spring Boot

Giả sử app có `security.export.legacy-download-enabled=false` trong configuration file. Nếu một property source có độ ưu tiên cao hơn cung cấp giá trị `true`, ứng dụng có thể nạp trạng thái khác. Khi review cần:

- Framework/runtime version và **property source precedence** theo phiên bản.
- Profile nào đang active, kể cả profile-specific files.
- Environment, JVM system properties, command-line và external configuration.
- Cách bind property vào bean, default value và validation.
- Thời điểm property được đọc: startup hay dynamic refresh.
- Nếu có override, override đó có approved change ID không?
- Behavior trên endpoint/feature thực, không chỉ raw string.

### Không tiết lộ secrets khi inspect

Các endpoint/config dumps như actuator environment/configprops nếu có thể chứa secrets, connection strings hoặc nội bộ nhạy cảm. Không bật công khai để debug. Dùng **role-protected diagnostic**, redacted values, source identity và positive/negative tests thay vì sao chép toàn bộ environment vào ticket.

### Đề xuất mô hình chứng cứ

Lưu `property_key`, `effective_boolean_or_classification`, `origin/source_id`, `application_version`, `instance_id`, `observed_at`, `test_id` và `evidence_ref`; đối với secret chỉ lưu **presence/rotation/version metadata**, không lưu secret value.

## 9. Spring Boot runtime: bind, validation và security defaults

Với Java/Spring Boot, các lớp cấu hình có thể có default trong code, values theo profile, property sources và external dependencies. Một control đáng tin nên có **secure default, startup validation và kiểm thử hành vi**.

### Một số failure modes

- Giá trị `false` trong code bị override bởi external env.
- Property đổi tên khi nâng framework, cấu hình cũ bị bỏ qua.
- Binder dùng default khác mong đợi khi property thiếu.
- Bean chỉ bind khi startup, trong khi operator nghĩ đã refresh động.
- Profile `dev` vô tình active ở production.
- Conditional bean tạo endpoint hoặc filter khác trong một profile.
- Feature flag service trả fallback value “allow” khi network failure.
- Một instance chưa restart, nên mixed config trong rollout.
- Actuator/diagnostic endpoint được expose rộng hơn dự định.
- Cấu hình CORS/security filter match rules khác với route thực.

### Đối chiếu requirement với hành vi

Với yêu cầu “legacy bulk export route phải bị vô hiệu ở production”, có thể dùng **safe in-process state readback**, kiểm tra route registration và gửi **authorized negative request bằng synthetic user**. Việc kiểm tra property `false` trên một pod không đủ nếu alternate ingress đưa traffic tới pod cũ.

## 10. Containers và cấu hình runtime trong image

Container gồm nhiều yếu tố: image layers, default `ENTRYPOINT`/`CMD`, environment, user, filesystem, capabilities, mounts, namespaces, seccomp/AppArmor/SELinux policies (nếu áp dụng), runtime flags và orchestrator policies.

| Lớp | Điều cần xác minh | Tránh suy luận |
| --- | --- | --- |
| **Image** | Digest, base image, embedded defaults, USER, installed packages. | Dockerfile đã đúng nên pod chắc chắn dùng digest đó. |
| **Deployment spec** | Env, args, volumes, service account, securityContext. | Manifest trong Git đồng nhất với live spec. |
| **Admission mutation** | Sidecars, defaults, injected env/mounts, policy changes. | Source manifest là cấu hình sau admission. |
| **Running container** | UID/GID, capabilities, process args, mounts, seccomp status. | `runAsNonRoot` đủ chứng minh mọi process không có quyền ngoài dự kiến. |
| **Runtime networking** | Container/pod traffic, ingress/egress, namespace policies. | NetworkPolicy có mặt là mọi traffic đã bị chặn. |
| **Runtime filesystem** | Read-only root, writable mounts, temp storage permissions. | Read-only root loại hết mọi write path. |

### Build và runtime là hai scope khác nhau

Image được build với fixed setting có thể bị override khi chạy. Ngược lại, một image không đặt `USER` có thể được runtime policy ép không-root theo deployment, nhưng cần readback và kiểm tra compatibility. Kết luận phải nói **cấu hình nào có hiệu lực ở runtime**, không chỉ Dockerfile.

### Process identity

Không nên chỉ ghi “non-root” rồi kết luận least privilege. Cần xét Linux capabilities, privileged mode, hostPID/hostNetwork, mounts, writable paths, service account, cloud IAM và khả năng truy cập kernel interfaces. Quyền ở **nhiều tầng** có thể cộng dồn.

## 11. Kubernetes: desired spec, admission và actual pods

Kubernetes là ví dụ điển hình về **hệ thống có control plane liên tục reconcile desired state**, nhưng điều đó không loại bỏ nhu cầu xác minh trạng thái hiệu lực.

### Đối tượng liên quan

| Đối tượng | Chứa thông tin | Điểm dễ sai |
| --- | --- | --- |
| Deployment/StatefulSet/DaemonSet | Desired workload/template, replicas/strategy. | Pods cũ chưa được rollout hoặc workload khác không dùng template. |
| ReplicaSet/Pod | Actual instantiated spec sau admission và trạng thái containers. | Pod đang Pending, CrashLoop, chưa nhận image/config mới. |
| ConfigMap | Non-secret configuration data. | Update không tự làm app reload trong mọi cách mount. |
| Secret | Secret references/data với base64 encoding trong API representation. | Base64 **không phải mã hóa**, access/rotation cần bảo vệ. |
| ServiceAccount | Workload Kubernetes identity. | IAM/cloud role binding có thể quá rộng. |
| NetworkPolicy | Intended pod ingress/egress rules. | CNI có support/enforce? Policy selection/default-deny có đúng? |
| Ingress/Gateway | Route và policies ở edge. | Alternate direct service path bypass auth controls. |
| Admission controller | Validation/mutation trước khi lưu Pod. | Được bật ở namespace nào? Có failure mode? |
| PodSecurity/RuntimeClass | Các hạn chế security và runtime profile. | Label/policy không tự chứng minh effective process capabilities. |
| HPA/Jobs/CronJobs | Ephemeral instances và scaling. | Snapshot định kỳ bỏ qua pods sống ngắn. |

### Cấu hình có thể thay đổi nhưng app không tự cập nhật

Env vars inject vào container **không tự đổi trong process hiện tại khi ConfigMap/Secret nguồn thay**. Với mounted volumes, Kubernetes có cơ chế cập nhật projected data theo điều kiện nhưng ứng dụng vẫn phải **đọc lại**, và có các ngoại lệ như mount kiểu `subPath` không nhận cập nhật tự động theo cùng cách. Không được khẳng định “đã update ConfigMap” = “tất cả requests đang dùng setting mới”.

### Kiểm chứng triển khai

Từ approved manifest, lấy live Deployment/Pod spec, admission mutations, image digest, actual environment/config source refs (không dump secrets), restart/reload evidence, active route và controlled behavior tests. Đánh giá cả rollout progress/replica convergence, không chỉ một object trong API.

## 12. Secrets, ConfigMaps và dynamic configuration

Configuration management đôi khi cố gắng đưa mọi giá trị vào một nơi, nhưng **secret values, public settings và policy decisions** có yêu cầu kiểm soát khác nhau.

### Những trường hợp dễ sai

- Đặt production API key trong ConfigMap hoặc log/actuator endpoint.
- Dùng Kubernetes Secret nhưng RBAC cho quá nhiều principals đọc; secret vẫn bị in ra stdout.
- Rotate secret ở secret manager nhưng pod vẫn dùng credential cũ trong memory.
- Mất kết nối config service khiến app fallback bật debug hoặc bỏ auth.
- Feature flag có thể bị bật từ UI quản trị không có approval/audit.
- Thông tin nhạy cảm được truyền vào command args khiến process list/log lộ.
- Hai secrets có cùng key name nhưng đến từ namespace/environment khác.

### Secret rotation là một bài toán trạng thái

**Secret store updated → workload loads new credential → target service accepts new one → old credential revoked → negative test proves old no longer works.** Mỗi mốc là một assertion khác nhau. Một ticket “rotation complete” không đủ nếu worker còn dùng key cũ hoặc partner endpoint vẫn chấp nhận key đã thu hồi.

### Fail closed cần được thiết kế theo ngữ cảnh

Nếu không tải được authorization policy, một endpoint quản lý quyền thường cần **deny** thay vì cho phép. Tuy nhiên với một số chức năng availability-critical, yêu cầu có thể là degraded operation an toàn, theo risk policy. Không viết “mọi config failure đều kill process” như một quy tắc phổ quát; xác định **safe failure mode** cho từng security invariant.

## 13. Runtime identity, IAM và quyền hiệu lực

Một ứng dụng có thể khai báo “chỉ dùng read-only role” nhưng **quyền thực tế** phụ thuộc danh tính được gán ở runtime, trust policy, resource policy, role assumption, temporary credentials và điều kiện truy cập.

### Các lớp cần phân biệt

1. **Kubernetes ServiceAccount** hoặc VM workload identity được gắn.
2. **Cloud principal/role** mà workload thật sự nhận được.
3. **Identity trust policy:** ai có thể assume/impersonate role, theo điều kiện nào.
4. **Identity permissions:** action, resource, condition.
5. **Resource policy:** bucket, KMS key, queue hoặc managed service cho phép ai.
6. **Organization guardrails:** SCP/permission boundaries/policy constraints nếu nền tảng có.
7. **Effective request decision:** policy evaluation ở dịch vụ đích.
8. **Cached/rotating credentials:** TTL, revocation và session continuity.

### Sai lầm thường gặp

Pod spec có `serviceAccountName: invoice-reader` nhưng admission, identity binding hoặc annotation trỏ tới cloud role có quyền ghi bucket; hoặc code vô tình nhận credential từ môi trường khác. Việc đọc một tên service account **không chứng minh** effective least privilege.

### Yêu cầu assurance

**REQ-IAM-01:** “Export worker chỉ có quyền đọc invoices của job được xác minh và ghi vào approved export storage; không đọc secrets hoặc KMS keys ngoài purpose.” Điều này đòi kiểm cả **IAM policy effective**, **application-level tenant authorization** và **denied-use tests** trong sandbox với identities tương đương. Quyền cloud rộng có thể không tự tạo cross-tenant leak nếu app kiểm soát đúng, nhưng tăng blast radius nếu app bị compromise.

### Thời điểm đo

Identity sessions, credentials và access policy có thể được cache. Ghi `observed_at`, principal/role ID, resource, evaluated action, decision và policy version; không lưu token thô.

## 14. Network, TLS, ingress/egress và service mesh

Cấu hình bảo mật mạng ở runtime không nằm trong một file duy nhất. Một request có thể đi qua **DNS/CDN → load balancer → ingress/gateway → service mesh/proxy → app**, hoặc đi theo đường tắt.

| Control | Desired state | Effective-state questions |
| --- | --- | --- |
| **TLS termination** | TLS theo approved security profile. | Client kết nối tới endpoint thực với certificate/protocol nào? Backend hop có được bảo vệ? |
| **mTLS** | Service-to-service identity validation. | Đúng source/destination workload identities và paths có policy enforce? |
| **Ingress authN** | Protected routes qua authentication proxy. | Alternate route/direct origin có bypass không? |
| **NetworkPolicy** | Chỉ ingress/egress đã duyệt. | Pod labels, namespace, CNI enforcement, default-deny, selected peers đúng không? |
| **Cloud firewall/security group** | Chỉ cổng/peers cần thiết. | Effective merged rules, route tables và peer permissions có đúng không? |
| **Egress restriction** | Không đi tới arbitrary destinations. | Redirect/proxy/DNS, wildcard destinations và service identity có được kiểm? |
| **WAF/rate control** | Rules áp trên public endpoints. | Rules có theo mọi API versions/paths, actual traffic route và exceptions? |
| **DNS/config discovery** | Chỉ dùng approved services. | Runtime client có pin/allowlist, fallback hoặc stale addresses? |

### Cấu hình có mặt nhưng không được enforce

Một Kubernetes NetworkPolicy có thể được lưu trong API nhưng không có hiệu lực nếu plugin mạng không hỗ trợ enforcement như mong đợi hoặc policy không chọn đúng pods/namespace. Vì vậy phải kết hợp **policy readback, label selection, plugin support và synthetic connectivity checks**.

### Cẩn trọng với TLS claims

“Cổng 443 đang mở” không chứng minh mọi hop được mã hóa, cũng không chứng minh certificate validation đúng ở client. Kiểm tra cần phân biệt **external edge**, **internal service-to-service**, **database** và **vendor integration**, cùng host identity/trust semantics.

## 15. Database runtime settings và effective privileges

Database configuration có thể điều chỉnh trong service startup, database parameter groups hoặc session level, và có settings chỉ có hiệu lực sau restart/reconnect.

### Các nhóm yêu cầu thường gặp

- Network listeners, allowed clients và transport encryption.
- Database role privileges, default roles, schema permissions.
- Row-level security, tenant filters hoặc access-control architecture tương đương.
- Logging/audit và việc che sensitive queries/parameters.
- Backup, point-in-time recovery, replication và restore readiness.
- Password/key storage, credential rotation và connection pool lifecycle.
- Resource/timeouts, connection limits và transaction isolation theo risk.
- Extensions/features không cần thiết hoặc unsafe functions theo baseline.

### Ba lớp dễ bị nhầm

**Server-level config** có thể cho phép TLS, nhưng **client session** vẫn dùng mode không verify server identity nếu policy yếu. **Database role** có thể bị giới hạn, nhưng application connection pool dùng role khác. **RLS policy** có thể tồn tại, nhưng một privileged role hoặc query path có bypass.

### Ví dụ audit question

“Invoice API read queries chạy dưới DB principal nào và có thể đọc records tenant B ngoài scope không?” Để trả lời cần effective session identity, granted permissions, query/policy context và **synthetic cross-tenant negative tests**, chứ không chỉ ảnh chụp một grants file.

### Không lộ data khi kiểm

Đừng chạy truy vấn rộng trên production customer tables chỉ để chứng minh role read. Sử dụng test schema/fixtures, policy simulation hoặc safe readback được phê duyệt.

## 16. API gateway, proxies và authorization policy runtime

API gateway thường dùng các cấu hình cho routing, authentication, header transformation, rate limiting, CORS, caching, TLS và backend selection. **Mỗi route cần được đối chiếu với policy áp dụng thực tế**.

### Các failure modes

1. Route v2 dùng authorization plugin, route v1 không dùng.
2. Gateway xác thực JWT nhưng không kiểm audience/resource hoặc tenant ownership.
3. Proxy tin `X-User-Id` header từ client chưa được loại hoặc ký.
4. Một path có trailing slash/encoding variation đi qua route matcher khác.
5. Backend có direct network access bypass gateway.
6. Plugin config mới chưa được rollout tới một proxy replica.
7. Emergency allow rule vẫn tồn tại sau incident.
8. Cache key bỏ tenant/authorization context.
9. Health/debug route có access control yếu hơn intended.
10. Gateway logs chứa raw Authorization header hoặc sensitive payload.

### Requirement minh họa

**REQ-GW-02:** “Mọi public Invoice API versions phải xác thực principal đúng issuer/audience và định tuyến tới server-side object authorization; không có đường origin bypass ngoài policy.” Chỉ kiểm `JWT_PLUGIN_ENABLED=true` ở một proxy chưa đủ; cần **route enumeration, effective configs và controlled negative behavior** theo supported versions.

### Đừng lạm dụng HTTP status

Một request sai quyền trả 403 có thể vẫn tạo job/side effect nếu authorization xảy ra sau một bước xử lý. Khi claim liên quan integrity và data isolation, cần kiểm observed state tại downstream bằng synthetic records.

## 17. Feature flags và runtime security invariants

Feature flags có thể kiểm soát business rollout, experimentation và circuit breakers. Khi flag ảnh hưởng **security control** hoặc exposure của dữ liệu, nó cần governance chặt hơn một feature UI.

### Các thuộc tính cần ghi

- Flag ID, purpose, approved default và data/security classification.
- Owner, approver, allowed environments, tenants và cohorts.
- Evaluation point: server, client, edge proxy hoặc worker.
- Targeting conditions: role, region, tenant tier, device hoặc percentage.
- Cache TTL, change propagation, emergency override và fail behavior.
- Audit: who/when/why changed, previous/new state và approvals.
- Kill-switch semantics, rollback và compatibility với old consumers.
- Tests cho **on/off/unknown**, version transition và mixed cohorts.

### Một ranh giới quan trọng

Feature flag ở frontend **không phải server-side authorization**. Nếu UI ẩn “Download all invoices”, API vẫn phải kiểm quyền của actor trước tạo job hoặc phát file. Flag chỉ nên quyết định **feature availability** trong scope; security decision vẫn phải do enforcement point đáng tin.

### Fallback danger

Một flag service lỗi và app fallback sang `true` cho “legacy unauthenticated export” có thể mở rủi ro đúng lúc hệ thống gặp sự cố. Định nghĩa safe default theo security requirement và kiểm **dependency outage tests**.

## 18. Configuration propagation, refresh và eventual consistency

Hệ thống phân tán không nhất thiết cập nhật mọi instance tức thì. Sau khi thay một policy, có thể có giai đoạn **mixed runtime states**:

- Proxy A đã nạp rule mới, proxy B vẫn giữ rule cũ.
- Pod mới dùng env config v2, pod cũ dùng v1.
- Feature flag cache hết hạn khác nhau giữa services.
- Authorization grants bị revoke nhưng token/session còn thời hạn.
- Secret store đã rotate, worker long-running giữ old credential.
- Managed database parameter thay nhưng connection pool session chưa tái tạo.

### Định nghĩa propagation window

Một yêu cầu “role revoke có hiệu lực trong tối đa X giây” cần có **approved window, clock sync, measurement method và test cases**. Không tự kết luận FAIL chỉ vì một token còn hoạt động vài giây nếu policy cho phép, cũng không tự coi PASS khi một critical path vẫn hoạt động quá giới hạn.

### Eventual consistency không là giấy phép fail open

Với hành động bảo mật nhạy cảm, thiết kế có thể cần revoke tại server-side decision point hoặc làm mới policy trước hành động. Chiến lược phải cân bằng availability và authorization nhưng không che rủi ro dưới từ “eventually”.

### Mixed-version tests

Cần kiểm tra **old/new API, workers, configuration schemas và database behavior** trong rollout. Nếu policy mới đòi identity claim mà old worker không hiểu, việc phát một ConfigMap mới có thể tạo silent bypass hoặc false deny.

## 19. IaC, GitOps và configuration as code

**Infrastructure as Code (IaC)** và **GitOps** rất hữu ích cho repeatability, review và audit. Nhưng **tồn tại một file được approve không đồng nghĩa runtime tương ứng đã được chứng minh**.

### Ba chiều nên so sánh

1. **Approved intent:** Git commit, code owners, change record, policy evaluations.
2. **Control plane actual state:** cloud/Kubernetes API, provider parameter group, gateway policy.
3. **Runtime effective behavior:** process readback, test identity access decisions, network route/DB results.

### Configuration drift categories

| Drift | Ví dụ | Evidence/trị sửa |
| --- | --- | --- |
| **Out-of-band change** | Admin trực tiếp mở security group trên console. | Cloud audit event, IaC plan diff, revert theo approved change. |
| **Missing deployment** | Git merged nhưng cluster vẫn release cũ. | Reconciler status, live object ID, runtime tests. |
| **Admission mutation** | Webhook inject privileged sidecar. | Effective Pod spec, admission audit/decision. |
| **Ignored setting** | App version mới bỏ property cũ. | Startup diagnostics, behavior tests, config schema validation. |
| **Stale session/instance** | Config mới không reload. | Instance-by-instance effective state. |
| **Dynamic override** | Feature flag UI thay mà Git không đổi. | Flag audit events, approved control registry. |
| **Unsupported resource** | Scanner không hiểu loại cloud service mới. | Source inventory/collector health, UNKNOWN not PASS. |

### Remediation của drift

Trước khi tự động revert, kiểm tra **business owner, break-glass/incident state và potential outage**. Nếu thay đổi khẩn cấp đã được duyệt, cập nhật desired state hoặc tạo exception có thời hạn theo governance; không biến auto-remediation thành nguyên nhân xóa cấu hình đang giữ availability.

## 20. Admission, policy-as-code và runtime verification

Policy-as-code có thể kiểm soát manifests trước merge, tại admission hoặc theo lịch sau deploy. Mỗi thời điểm có hiệu lực/limitations khác nhau.

| Điểm chặn | Ví dụ | Giá trị | Giới hạn |
| --- | --- | --- | --- |
| **Pre-commit/CI** | Phát hiện `privileged: true` hoặc missing owner. | Feedback sớm, policy version rõ. | Không thấy manual changes, actual injected config. |
| **Admission** | Reject pods không đáp ứng required security context. | Chặn tạo resource sai policy ở thời điểm admission. | Existing pods, webhook outage/fail mode, exemptions. |
| **Continuous inventory scan** | So live resources với baseline. | Phát hiện drift sau deploy. | Polling gaps, collector permissions, ephemeral resources. |
| **Runtime observation** | Process UID/capabilities, API authz, egress tests. | Kiểm chứng control hiệu lực. | Không tự chứng minh mọi path/control toàn diện. |

### Bypass logic cần review

- Namespace không được policy chọn.
- Policy có exempt selector quá rộng.
- Admission webhook `failurePolicy` và service availability không phù hợp risk.
- Privileged actor có thể bypass/sửa policy hoặc labels.
- Existing resource không được reevaluate khi policy mới tạo.
- Mutating webhook chạy sau khi một check đặt giả định sai.
- Runtime process có thêm quyền do host/device mounts.

### Kết luận đúng

“Admission đã từ chối canary Pod thiếu securityContext trong namespace X” là bằng chứng cụ thể về một control. Không suy thành “mọi pods trong mọi namespace luôn non-root” nếu không có live inventory/effective checks.

## 21. Environment, tenant và region-specific configuration

Một vấn đề lớn của configuration assurance là **cấu hình có phạm vi điều kiện**, không phải một giá trị chung cho toàn bộ hệ thống.

### Dimension cần đưa vào evidence

| Dimension | Ví dụ | Rủi ro nếu bỏ |
| --- | --- | --- |
| Environment | staging vs production vs DR. | Staging PASS nhưng production override khác. |
| Region/zone | primary vs backup region. | DR ingress không có auth plugin. |
| Tenant tier | enterprise vs free/test. | Feature flag bật tùy tenant ngoài rule. |
| API version | v1 vs v2/legacy. | V1 giữ permissive authorization. |
| Workload role | API vs export worker vs support. | Shared IAM role quá rộng. |
| Release ring | canary vs stable/blue-green. | Canary updated, stable instances cũ. |
| Runtime instance | pod/VM/serverless function ID. | Một instance chưa reload. |
| Time | before/after flag change hoặc revoke. | Snapshot không phản ánh thời điểm sự kiện. |

### Đơn vị đánh giá phải rõ

Không dùng “production cluster” như một asset duy nhất nếu một security requirement áp lên **từng API route/replica**. Tương tự, không nhân số lượng pods thành số độc lập của business services khi tính risk; định nghĩa metric theo **logical control target** và **runtime enforcement point**.

### Ví dụ false confidence

Team demo 1 canary pod dùng non-root, nhưng 30 worker pods trong stable pool có `privileged: true` vì template cũ. Kết luận “Kubernetes workloads compliant” là sai. Báo **sample coverage, exceptions, per-workload population và criticality**.

## 22. Thực hiện readback hiệu lực không làm lộ secrets

Readback nên ưu tiên **mô tả trạng thái kiểm soát** hơn là dump full config.

### Phương pháp theo lớp

- **Application diagnostics:** endpoint nội bộ có authz mạnh chỉ trả trạng thái như `debugEnabled=false`, `authzPolicyVersion`, `configHash`, `buildId`; không in secrets.
- **Kubernetes:** read `Deployment/Pod` specs, identities, imageIDs và status bằng read-only identity; chỉ lấy Secret metadata/version khi đủ.
- **Cloud IAM:** list policy/resource permissions bằng API được phê duyệt; test một denied action trong sandbox nếu cần.
- **Network:** lấy effective routes/policies và synthetic connectivity checks có mục tiêu.
- **Database:** đọc non-sensitive server/session configuration, role grants, thực hiện RLS/tenant negative test trên fixture.
- **Gateway:** export sanitized effective route/auth plugin mapping theo version và test outcomes.
- **Feature flag service:** audit event + effective flag evaluation trên test tenant/cohort, kèm cache TTL.

### “Read-only” không có nghĩa hoàn toàn vô hại

Một config dump có thể chứa API keys, internal hosts, IAM trust topology và user identities. Thông tin này có thể hỗ trợ attacker nếu rò. Collector phải có least privilege, audit, redaction, retention và bảo vệ theo data classification.

### Kiểm tra cả source health

Nếu collector bị thu hồi quyền hoặc API pagination bị lỗi, dashboard có thể giảm assets và báo 100% compliant trên phần còn nhìn thấy. Phải giám sát **permissions, errors, source heartbeat, completeness, scope và lag**, phân biệt **asset deleted** với **source unavailable**.

## 23. Claim–Argument–Evidence ở mức runtime

### Claim

“Trong kỳ đánh giá, tất cả production Invoice API workloads được xác định trong scope đang thực thi tenant object authorization, debug endpoints không exposed và đã đáp ứng cấu hình least privilege theo baseline đã duyệt.”

### Argument

1. Population workloads, routes và release rings đầy đủ.
2. Baseline được approve và map đúng security requirements.
3. Deployments và runtime identities/config sources được đối chiếu.
4. Effective authorization và debug behavior được kiểm tra bằng synthetic identities.
5. Least privilege được đánh giá ở process, Kubernetes và cloud IAM, không chỉ một field.
6. Exceptions, collector gaps, stale instances và altered config được phát hiện.
7. Retest sau change cùng source/provenance được lưu.

### Evidence

| Assertion | Evidence | Giới hạn |
| --- | --- | --- |
| Runtime population complete. | Cloud/cluster service registries, live inventory, release history. | Ephemeral/unmanaged workloads ngoài nguồn. |
| Desired security state approved. | Versioned baseline, change approval, policy mapping. | Chưa nói actual. |
| Deployed config matches intended. | Live specs, config refs/hashes, reconciliation status. | Process chưa reload. |
| Effective authorization works. | Cross-tenant API/worker/download negative tests. | Chỉ bao phủ actor/paths đã thử. |
| Debug surfaces disabled. | Effective route inventory, controlled negative checks. | Alternate direct paths chưa được test. |
| Least privilege active. | Effective IAM, container process identity, denied-use tests. | Privilege may change across roles/time. |
| Evidence valid. | Source health, timestamps, immutable refs, reviewed exceptions. | Một tool không chứng minh mọi layer. |

### Phân biệt design effectiveness và operating effectiveness

**Design:** baseline/control placement có phù hợp threat? **Operating:** runtime thực sự enforce, sensor đo đúng, security decision đúng trong evaluation window? Một policy đúng trên Git chưa đủ chứng minh operating effectiveness.

## 24. Evidence collection architecture: desired, actual và behavioral signals

~~~mermaid
flowchart LR
    G["Approved Git / IaC / security baseline"] --> N["Normalized control requirements"]
    K["Kubernetes and workload APIs"] --> O[("Timestamped runtime observations")]
    C["Cloud IAM / network / storage control plane"] --> O
    A["Application diagnostics and dynamic flag audit"] --> O
    D["DB / gateway effective configuration"] --> O
    T["Authorized behavioral and negative tests"] --> R[("Observed security outcomes")]
    N --> X["Reconciliation and control evaluation"]
    O --> X
    R --> X
    X --> F["PASS / FAIL / PARTIAL / UNKNOWN / N-A"]
    X --> E[("Versioned evidence and exception register")]
    F --> E
    E --> M["Remediation / change / retest"]
    M --> O
~~~

### Data model khuyến nghị

**Control target** là một combination có ý nghĩa: `requirement_id + asset/workload + environment + release + effective-policy-layer`.

**Observation** ghi `source`, `source_version`, `collector_identity`, `observed_at`, `asset_id`, `control_id`, `value_class` (không phải secret), `raw_ref`, `quality`.

**Evaluation** ghi `expected`, `observed`, `method`, `test_id`, `status`, `reviewer`, `known_gaps`.

**Remediation** ghi owner, due date, change link, interim control, retest evidence, current residual risk và exception expiration.

### Vì sao phải giữ raw observations?

Nếu một rule thay hoặc collector có bug, reviewer cần truy lại observation gốc và metadata. Ghi đè một cột `compliant=true` không hỗ trợ điều tra historical drift hay chứng minh state trước/sau remediation.

## 25. Ví dụ Java/Spring Boot: kiểm tra security invariants tại startup

Giả sử Invoice API có hai lựa chọn: bật enforcement tenant authorization và bật đường export legacy. Với service này, policy production yêu cầu **tenant authorization luôn bật**, **legacy export luôn tắt**. Một startup guard giúp ngăn một số cấu hình nguy hiểm được nạp, nhưng nó **không tự chứng minh** mọi endpoint thực thi authorization đúng.

### ConfigurationProperties với validation

~~~java
package example.invoice.security;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "assurance.security")
public record RuntimeSecuritySettings(
    @NotNull Boolean strictTenantAuthorization,
    @NotNull Boolean legacyExportEnabled,
    @NotBlank String policyVersion
) {
    public RuntimeSecuritySettings {
        // Illustrative fixed baseline for this specific service.
        if (!Boolean.TRUE.equals(strictTenantAuthorization)) {
            throw new IllegalStateException(
                "Tenant authorization must be enabled");
        }
        if (!Boolean.FALSE.equals(legacyExportEnabled)) {
            throw new IllegalStateException(
                "Legacy export endpoint must be disabled");
        }
    }
}
~~~

Kích hoạt binding cho lớp cấu hình bằng cơ chế `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties(RuntimeSecuritySettings.class)` theo cấu trúc ứng dụng và phiên bản Spring Boot. Project cần cấu hình validation dependency tương ứng. **Không copy ví dụ mà bỏ kiểm tra compatibility, annotation discovery hoặc dependency binding của codebase thực**.

### Cấu hình được phê duyệt minh họa

~~~yaml
assurance:
  security:
    strict-tenant-authorization: true
    legacy-export-enabled: false
    policy-version: "invoice-security-policy-v3"
~~~

### Những điều code guard giúp đạt

- Từ chối startup khi property thiếu/không đáp ứng baseline minh họa.
- Giảm khả năng operator bật `legacy-export-enabled` do override mà không làm startup fail.
- Tạo failure event có thể kiểm chứng trong CI/staging.

### Những điều code guard **không chứng minh**

1. **Filter/authorization thực sự enforce:** property `true` có thể không được dùng hoặc bypass.
2. **Mọi instances dùng guard mới:** pod cũ hoặc service khác có thể vẫn chạy image trước khi guard được thêm.
3. **Cấu hình động không thay sau startup:** nếu tồn tại refresh/dynamic flag ngoài guard, cần kiểm ở evaluation point.
4. **Không có alternate routes:** gateway hoặc worker có thể còn legacy path riêng.
5. **Startup fail luôn đúng với mọi service:** đây là yêu cầu riêng của ví dụ, không phải policy chung cho mọi workload.
6. **Không có secrets lộ qua diagnostics:** code không cấp quyền đọc environment.

### Tests cần thêm

Viết test khởi động khi properties hợp lệ, thiếu, bị override sai và sai kiểu; kiểm tra startup failure. Sau đó dùng **synthetic user/tenant tests** trên HTTP path để bảo đảm object authorization thực thi. Cuối cùng readback runtime instances thuộc production scope để xác minh rollout đầy đủ.

## 26. Ví dụ Java/JUnit: bảo vệ trước cấu hình sai và false PASS

Đây là test đơn vị cho constructor validation ở ví dụ trước. Nó kiểm **configuration contract**, không phải thay thế integration security tests.

~~~java
package example.invoice.security;

import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class RuntimeSecuritySettingsTest {
    @Test
    void acceptsApprovedBaseline() {
        RuntimeSecuritySettings config =
            new RuntimeSecuritySettings(
                true, false, "invoice-security-policy-v3");

        assertEquals("invoice-security-policy-v3",
            config.policyVersion());
    }

    @Test
    void rejectsMissingTenantAuthorization() {
        assertThrows(IllegalStateException.class, () ->
            new RuntimeSecuritySettings(
                false, false, "invoice-security-policy-v3"));
    }

    @Test
    void rejectsReenabledLegacyExport() {
        assertThrows(IllegalStateException.class, () ->
            new RuntimeSecuritySettings(
                true, true, "invoice-security-policy-v3"));
    }

    @Test
    void rejectsNullSecurityBooleans() {
        assertThrows(IllegalStateException.class, () ->
            new RuntimeSecuritySettings(
                null, false, "invoice-security-policy-v3"));
    }
}
~~~

### Một chi tiết validation cần hiểu

Constructor guard minh họa kiểm hai booleans; annotation `@NotBlank` cho `policyVersion` cần **Bean Validation integration** để được thực thi bởi framework trong binding flow. Nếu khởi tạo record bằng `new` trực tiếp, không nên mặc định annotation Bean Validation tự chạy. Đây là ví dụ phân biệt **declared validation annotation** với **effective validation path**.

### Security-negative behavior test

Với synthetic tenants A/B, một HTTP integration test cần chứng minh user A **không đọc được invoice B**, kể cả khi property đã được nạp thành `true`. Nếu test FAIL, một property guard PASS không thể bù cho broken authorization.

## 27. Ví dụ Kubernetes: hardening theo workload và cách kiểm

Một Deployment minh họa cấu hình non-root, privilege reduction và readiness. Đây là **starting point** cho một ứng dụng đã được thiết kế hỗ trợ filesystem chỉ đọc và không cần service account token. Không mặc định mọi workload có thể copy nguyên cấu hình.

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: invoice-api
  namespace: invoice-prod
  labels:
    app: invoice-api
spec:
  replicas: 3
  selector:
    matchLabels:
      app: invoice-api
  template:
    metadata:
      labels:
        app: invoice-api
    spec:
      serviceAccountName: invoice-api
      automountServiceAccountToken: false
      securityContext:
        runAsNonRoot: true
        runAsUser: 10001
        runAsGroup: 10001
        seccompProfile:
          type: RuntimeDefault
      containers:
        - name: api
          image: registry.example.invalid/invoice-api@sha256:REPLACE_WITH_REAL_DIGEST
          ports:
            - containerPort: 8080
          securityContext:
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            capabilities:
              drop: ["ALL"]
          env:
            - name: SPRING_PROFILES_ACTIVE
              value: "prod"
            - name: ASSURANCE_SECURITY_STRICTTENANTAUTHORIZATION
              value: "true"
          volumeMounts:
            - name: temporary-files
              mountPath: /tmp
          resources:
            requests:
              cpu: "250m"
              memory: "512Mi"
            limits:
              cpu: "1"
              memory: "1Gi"
          readinessProbe:
            httpGet:
              path: /health/ready
              port: 8080
            initialDelaySeconds: 5
            periodSeconds: 10
      volumes:
        - name: temporary-files
          emptyDir: {}
~~~

### Các điểm phải hiệu chỉnh trước khi đưa vào hệ thống thật

- `sha256:REPLACE_WITH_REAL_DIGEST` là **placeholder không phải digest hợp lệ**; phải dùng immutable digest của artifact thật, kiểm provenance.
- Biến môi trường Spring Boot và relaxed binding cần kiểm **key format đúng phiên bản, property binding actual và precedence**; đừng coi một tên env tự viết là đã bảo đảm property được áp. Với nhiều từ ghép, dùng test binding/startup và có thể chọn cấu hình approved từ ConfigMap hoặc command-line theo framework.
- `automountServiceAccountToken: false` chỉ phù hợp nếu workload không cần Kubernetes API/workload identity token; nếu cần, thiết kế scoped projected token/trust và đánh giá riêng, không “bật lại tất cả” để sửa.
- `readOnlyRootFilesystem` yêu cầu ứng dụng và dependencies ghi đúng các writable mounts được cho phép.
- Probe path phải được app triển khai và bảo vệ phù hợp; không expose sensitive health data ra public ingress.
- Resource requests/limits, UID/GID và seccomp profile phải theo capacity/risk, không dùng giá trị minh họa như yêu cầu chung.
- NetworkPolicy, cloud IAM, secret access, ingress AuthZ và application authorization **không được bảo vệ chỉ nhờ securityContext**.

### Readback hiệu quả

Đối chiếu **approved Deployment → live Deployment/ReplicaSets → Pod specs/actual images → process identity/capabilities → endpoint behavior**, theo từng ring/region. Nếu chỉ 1/3 replicas dùng digest mới, kết luận FULL PASS là sai.

## 28. Mẫu YAML control specification có điều kiện đánh giá

Đây là **control registry mẫu**, không phải Kubernetes manifest hay metadata của bài học.

~~~yaml
schema_version: "1.0"
record_type: "runtime_configuration_control"
control_id: "CONF-RUNTIME-AUTHZ-001"
service: "invoice-saas"
security_objective: "Prevent cross-tenant access"
requirement: >
  Every supported production invoice read/export path
  enforces server-side object and tenant authorization.
scope:
  environments:
    - "production"
  workload_classes:
    - "invoice-api"
    - "invoice-export-worker"
    - "download-service"
  api_versions:
    - "supported-current"
    - "supported-legacy"
expected:
  approved_policy_version: "invoice-security-policy-v3"
  fail_mode: "DENY_FOR_UNAUTHORIZED_ACCESS"
  raw_debug_config_exposed: false
  identity_binding: "verified-principal-not-client-tenant-id"
sources:
  desired:
    - "approved-policy-repository"
  actual:
    - "kubernetes-live-workload-inventory"
    - "application-sanitized-config-diagnostics"
  effective:
    - "authorized-cross-tenant-negative-tests"
    - "gateway-route-verification"
    - "worker-and-download-data-access-tests"
verification:
  test_ids:
    - "RC-T08"
    - "RC-T09"
    - "RC-T10"
  require_runtime_build_identity: true
  require_source_health: true
  status_if_missing_evidence: "UNKNOWN"
  acceptance: >
    All identified protected paths deny cross-tenant
    access, and authorized own-tenant flows still work.
status: "NOT_EVALUATED"
evidence_refs: []
exceptions: []
owners:
  control: "Application Security Owner"
  operations: "Invoice Platform Team"
  risk: "Invoice Business Risk Owner"
reassessment_triggers:
  - "api-version-added"
  - "authorization-policy-changed"
  - "new-production-workload"
  - "feature-flag-changed"
  - "runtime-digest-updated"
  - "evidence-source-unavailable"
~~~

### Vì sao ba loại sources?

Một policy repo chứng minh **định hướng đã duyệt**; Kubernetes + app diagnostic chứng minh một phần **actual/loaded state**; controlled negative tests là evidence **effective authorization**. Mỗi loại thiếu một phần đều có thể khiến claim chưa đạt.

### Trạng thái NOT_EVALUATED

Mẫu không tạo bằng chứng thật. `status: NOT_EVALUATED` và `evidence_refs: []` có chủ đích để tránh nhầm với control đã kiểm chứng.

## 29. Mẫu JSON runtime observation: ghi đủ mà không lộ bí mật

~~~json
{
  "eventType": "runtime_config_assurance_observation",
  "schemaVersion": "1.0",
  "observationId": "obs-invoice-example-001",
  "observedAt": "2026-11-28T03:00:00Z",
  "environment": "production",
  "region": "region-example",
  "service": "invoice-api",
  "workloadId": "invoice-api-deployment",
  "instanceId": "example-pod-001",
  "artifactDigest": "example-not-a-real-digest",
  "controlId": "CONF-RUNTIME-AUTHZ-001",
  "propertyId": "strict-tenant-authorization",
  "declaredState": "ENABLED",
  "loadedState": "ENABLED",
  "effectiveTestResult": "NOT_TESTED",
  "source": {
    "name": "sanitized-application-diagnostic",
    "version": "illustrative",
    "health": "OBSERVED"
  },
  "evidenceConfidence": "LIMITED_TO_PROPERTY_READBACK",
  "evidenceRef": "restricted-evidence/example-001",
  "containsSecrets": false
}
~~~

### Giới hạn của event

`loadedState: ENABLED` không bảo đảm mọi endpoints hoặc worker paths đang enforce policy. `source.health: OBSERVED` chỉ nói diagnostic trả kết quả, chưa chứng minh collector bao phủ toàn population. Trường `artifactDigest` trong ví dụ là placeholder, không phải một hash thật. Trong production cần format validation, provenance và dedup.

## 30. Ví dụ SQL: đối chiếu expected controls với observations

Khi có nhiều workloads, có thể dùng dữ liệu tập trung để tìm **missing/stale evidence**. SQL minh họa giả định hệ thống có:

- `required_runtime_controls`: control targets từ source population độc lập.
- `runtime_config_observations`: observations có asset/control ID, thời gian, validated result.

~~~sql
-- PostgreSQL-style illustration; :as_of and :freshness
-- must be supplied by an approved evaluation policy.
WITH required AS (
    SELECT
        asset_id,
        control_id,
        environment,
        expected_state
    FROM required_runtime_controls
    WHERE environment = 'production'
      AND in_scope = TRUE
      AND active_at_assessment = TRUE
),
latest_observations AS (
    SELECT
        o.asset_id,
        o.control_id,
        o.observed_state,
        o.source_health,
        o.observed_at,
        ROW_NUMBER() OVER (
            PARTITION BY o.asset_id, o.control_id
            ORDER BY o.observed_at DESC
        ) AS rn
    FROM runtime_config_observations o
    WHERE o.observed_at <= :as_of
      AND o.validation_status = 'VALID'
)
SELECT
    r.asset_id,
    r.control_id,
    r.expected_state,
    o.observed_state,
    o.observed_at,
    CASE
      WHEN o.asset_id IS NULL THEN 'UNKNOWN_NO_OBSERVATION'
      WHEN o.source_health <> 'HEALTHY'
           OR o.observed_at < (:as_of - :freshness)
        THEN 'UNKNOWN_STALE_OR_UNHEALTHY'
      WHEN o.observed_state = r.expected_state
        THEN 'CONFIG_MATCH_REQUIRES_EFFECTIVE_TEST'
      ELSE 'CONFIG_DRIFT'
    END AS configuration_assessment
FROM required r
LEFT JOIN latest_observations o
  ON o.asset_id = r.asset_id
 AND o.control_id = r.control_id
 AND o.rn = 1
ORDER BY r.asset_id, r.control_id;
~~~

### Vì sao query chỉ trả CONFIG_MATCH_REQUIRES_EFFECTIVE_TEST?

Query so desired với **reported observed property**, chưa chứng minh property được enforce. Ví dụ `strictTenantAuthorization=true` nhưng code path bypass vẫn có thể tồn tại. Cần join hoặc đánh giá riêng `effective_behavior_tests` có build/asset identity và test outcome.

### Sai lầm với phép đo “100%”

Nếu bảng `required_runtime_controls` lấy từ cùng scanner và thiếu một cloud account, query có thể báo mọi asset compliant trong population thiếu. **Denominator phải được đối chiếu độc lập và collector health phải được giám sát**. Nếu chưa biết population, trạng thái phải UNKNOWN, không tự cho 100%.

## 31. Threat model cho runtime configuration

Một attacker hoặc sự cố có thể ảnh hưởng cấu hình không chỉ qua source code:

| Threat | Điểm tác động | Security consequence |
| --- | --- | --- |
| **Unauthorized config change** | Cloud console, feature flag UI, ConfigMap, gateway API. | Tắt authz hoặc mở exposure. |
| **Privilege escalation** | IAM role/ServiceAccount, privileged pod, host mounts. | Truy cập DB/secrets/host ngoài mục đích. |
| **Configuration injection** | Env vars, CI variables, user-supplied admin config. | Chạy chế độ debug, sai destination hoặc policy. |
| **Drift/forgotten route** | Legacy ingress, old pod, DR region. | Bypass controls ở một đường ít dùng. |
| **Compromised evidence** | Collector, dashboard, config API, logs. | Giả PASS, che changes/risk. |
| **Unsafe failover** | Policy service/IdP outage, cached stale grants. | Fail open, vượt quyền hoặc false deny. |
| **Secret disclosure** | Config dump, diagnostic endpoint, logs, CI output. | Credential abuse và lateral movement. |
| **Supply-chain config tampering** | Image defaults, IaC module, admission webhook. | Hidden insecure settings sau deploy. |
| **Partial rollout** | Ring/region/pod không converge. | Một phần production có control yếu. |
| **Mis-scoped tenant flag** | Dynamic policy targeting/cohort. | Chức năng nhạy cảm được mở cho tenant sai. |

### Attack-path reasoning

Một đường giả định: admin token của flag service bị lộ → flag bật legacy export endpoint → gateway có route cũ → API thiếu tenant check → object storage file disclosure. Không một “flag=true” đơn lẻ chứng minh toàn bộ attack path, nhưng nó tạo **hypothesis và các security requirements cần xác minh ở từng boundary**.

### Cách tránh overclaim

Nếu thấy legacy flag bật nhưng endpoint đã được gỡ ở runtime, finding có thể là **config drift/policy violation** chứ chưa chắc exploitable data disclosure. Ngược lại, flag tắt nhưng direct route vẫn reachable thì behavior test bác bỏ assurance claim. Phân biệt **policy noncompliance, vulnerability, observable impact và unknown root cause**.

## 32. Ma trận kiểm thử runtime configuration

Những test dưới đây thực hiện trên **môi trường được phép, synthetic identities/data và controlled canaries**. Các canary làm thay đổi cấu hình cần có owner/maintenance/rollback plan. Chỉ kiểm những phạm vi được ủy quyền.

| Test ID | Kịch bản | Expected evidence/outcome |
| --- | --- | --- |
| **RC-T01** | Git baseline yêu cầu debug off nhưng env override bật. | Startup/gate FAIL hoặc runtime drift được phát hiện. |
| **RC-T02** | Spring property thiếu, default khác mong đợi. | Config validation/report UNKNOWN/FAIL theo contract. |
| **RC-T03** | Profile `dev` xuất hiện ở một production pod. | Detection và appropriate fail-safe/escalation. |
| **RC-T04** | Property đổi tên sau framework upgrade. | Binding/behavior tests phát hiện ignored config. |
| **RC-T05** | One pod chưa restart khi ConfigMap đổi. | Per-instance mixed state được báo PARTIAL. |
| **RC-T06** | Secret rotated, worker vẫn dùng old credential. | Old credential revoke/use tests và refresh verification. |
| **RC-T07** | Actuator diagnostic bị mở trên public route. | Unauthorized access DENY, không dump secrets. |
| **RC-T08** | Strict AuthZ property true nhưng endpoint bỏ tenant check. | Cross-tenant behavior test FAIL, không tin flag. |
| **RC-T09** | API v1 bỏ authz trong khi v2 đủ control. | Route/version-specific gap được phát hiện. |
| **RC-T10** | Worker nhận job với tenant context không hợp lệ. | Server-side identity/resource authorization DENY. |
| **RC-T11** | Image digest trong Git khác actual pod imageID. | Deployment drift và release provenance gap. |
| **RC-T12** | Pod chạy root/privileged trái baseline. | Effective process/pod policy FAIL, có owner. |
| **RC-T13** | Admission policy bị bypass bởi exempt namespace. | Scope/exemption review và canary detection. |
| **RC-T14** | NetworkPolicy có resource nhưng không select workload. | Selection audit + connectivity test FAIL. |
| **RC-T15** | CNI không enforce một expected egress restriction. | Effective egress test phát hiện. |
| **RC-T16** | Gateway route v1 không dùng auth plugin. | Route map + negative request chỉ ra deviation. |
| **RC-T17** | Backend direct origin bypass gateway policy. | Authorized route reachability test phát hiện. |
| **RC-T18** | mTLS policy declared nhưng một service-to-service hop plaintext. | Transport readback/controlled check FAIL. |
| **RC-T19** | Database role khác role mong đợi ở connection pool. | Effective session identity/privilege audit. |
| **RC-T20** | DB tenant-scoped control bypass qua privileged role. | Synthetic negative query test FAIL. |
| **RC-T21** | Feature flag targeting bật sai enterprise tenant. | Evaluation matrix detects wrong cohort. |
| **RC-T22** | Flag service unavailable, fallback bật insecure route. | Safe-failure test FAIL. |
| **RC-T23** | Role revoked nhưng cached policy quá approved window. | Timing/revocation test FAIL hoặc PASS theo SLA. |
| **RC-T24** | Config change làm audit log pipeline ngừng hoạt động. | Canary event missing, evidence source UNKNOWN/FAIL. |
| **RC-T25** | Cloud IAM resource policy mở rộng ngoài intent. | Effective grants và negative use tests phát hiện. |
| **RC-T26** | Storage bucket public dù IaC file private. | Provider readback/external approved test FAIL. |
| **RC-T27** | Source collector mất quyền một production account. | Source gap UNKNOWN, dashboard không tự compliant. |
| **RC-T28** | Autoscaled ephemeral pod không có snapshot evidence. | Event-driven discovery/validation capture trong SLA. |
| **RC-T29** | Canary ring secure, stable ring vẫn config cũ. | Population coverage PARTIAL, không full PASS. |
| **RC-T30** | Feature flag emergency change không có approval. | Audit/change governance finding. |
| **RC-T31** | Restore từ backup dùng keys không còn hợp lệ. | Recovery prerequisite test FAIL. |
| **RC-T32** | Runtime control rollback đưa lại unsafe config. | Reopen finding, residual risk assessed. |
| **RC-T33** | Audit log chứa bearer token do debug config. | Redaction test FAIL, secret incident process. |
| **RC-T34** | Rate limit config nạp nhưng alternate API version không enforce. | Per-route bounded behavior test detects. |
| **RC-T35** | Deployment manifest đúng nhưng mutating webhook inject mount rộng. | Live admitted spec và process readback phát hiện. |
| **RC-T36** | Security control telemetry báo healthy nhưng test event không đến. | Source-health and end-to-end evidence test FAIL. |

### Test record cần có

`test_id`, requirement/threat, asset/release, expected state, actor/fixture, observation source/time, actual values **đã giảm nhạy cảm**, behavior result, limitations, PASS/FAIL/PARTIAL/UNKNOWN, evidence refs, owner và retest.

### Không dùng mọi test như benchmark bắt buộc

Nếu service không dùng Kubernetes hoặc feature flag, các tests đó có thể **N/A với rationale**. Nếu technology có nhưng RoE không cho phép test thực, báo **NOT_TESTED/UNKNOWN** thay vì xóa khỏi coverage metric.

## 33. Case study: Cấu hình runtime lệch ở Invoice SaaS đa tenant

### 33.1. Bối cảnh giả định

Invoice SaaS đang triển khai một bản release mới để siết tenant authorization và giảm các endpoints cũ. Kiến trúc gồm:

- Public Invoice API, legacy API v1 và internal support routes.
- Export worker đọc dữ liệu hóa đơn qua queue, lưu file vào object storage.
- Kubernetes ở hai regions, progressive rollout theo canary/stable rings.
- Gateway, service mesh, IdP, managed database, KMS, secret manager.
- Feature flag service điều khiển rollout exports và admin features.
- Logging/metrics pipelines phục vụ incident response và audit.

Đội platform nộp **Git security baseline và Helm values** làm evidence; tất cả scanners chạy trên CI báo cấu hình đáp ứng tiêu chí. Nhưng assessor cần chứng minh **effective runtime state** trên actual production population.

### 33.2. Security requirements quan trọng

| Requirement ID | Requirement | Verification approach |
| --- | --- | --- |
| **REQ-RC-01** | Supported Invoice APIs enforce object-level tenant authorization. | Route inventory + cross-tenant negative tests. |
| **REQ-RC-02** | Legacy public export route disabled across all production rings. | Feature flag and route readback + denied behavior. |
| **REQ-RC-03** | Workloads use least-privilege identities and controlled secrets. | Pod/service/cloud IAM actual state + denied-use test. |
| **REQ-RC-04** | Data stores not anonymously exposed, and access uses approved identity. | Effective storage policies + authorized access checks. |
| **REQ-RC-05** | Security-relevant requests produce audit events without raw secrets. | Canary events and redaction/source-health tests. |
| **REQ-RC-06** | Authorization change propagates within approved time window. | Timed revocation test with synthetic accounts. |
| **REQ-RC-07** | Production rollout converges to approved config and artifact. | Per-region/ring/pod config and digest comparison. |

### 33.3. Mười findings minh họa

| Finding | Observation | Loại |
| --- | --- | --- |
| **F-RC-01** | Git bật strict authorization nhưng một API v1 pod dùng profile cũ. | Runtime/rollout drift; possible access gap. |
| **F-RC-02** | Feature flag “legacyExport” tắt ở global default nhưng bật cho cohort enterprise ngoài dự kiến. | Targeting/policy drift. |
| **F-RC-03** | Một gateway origin route không dùng auth plugin. | Edge control drift; requires reachability test. |
| **F-RC-04** | ServiceAccount worker map tới cloud role cho phép đọc nhiều buckets. | Least-privilege gap, blast radius. |
| **F-RC-05** | ConfigMap đã đổi nhưng worker process chưa reload. | Loaded state stale. |
| **F-RC-06** | Một Kubernetes namespace được exempt khỏi admission baseline. | Coverage/exemption gap. |
| **F-RC-07** | Audit agent healthy ở dashboard nhưng canary AuthZ event không có trong SIEM. | Operating-effectiveness evidence gap. |
| **F-RC-08** | Database pool dùng principal khác với approved service role. | Effective identity/config mismatch. |
| **F-RC-09** | Object store private trong Terraform nhưng một temporary access policy vẫn tồn tại sau support incident. | Out-of-band configuration drift. |
| **F-RC-10** | Collector không có quyền đọc DR account region B, dashboard vẫn ghi 100% compliant. | Denominator/source-health failure. |

### 33.4. Đừng gọi tất cả findings là exploit đã xác nhận

Một role quá rộng (F-RC-04) là **least-privilege deviation** và tăng blast radius; chưa tự chứng minh có attacker khai thác. F-RC-03 là route control gap nếu route được bảo vệ bởi control khác hoặc không reachable từ actor tương ứng; cần test. F-RC-07 là **telemetry/control assurance failure** có thể độc lập với authentication correctness.

Ngược lại, nếu synthetic user tenant A đọc được canary invoice B qua v1, đó là **confirmed security requirement violation** trong path/test scope. Reviewer phải báo cả hai loại: **config drift** và **observed security failure**.

### 33.5. Reconciliation theo ba lớp

**Lớp A – Approved:** policy Git commit, Helm release, cloud/IAM baselines, API/flag matrix, exception register.

**Lớp B – Actual:** live Kubernetes Deployment/Pods, admitted specs, runtime artifact digest, cloud roles, flag evaluation results, gateway route policy.

**Lớp C – Effective:** test A→B denied, worker cannot access unauthorized object, wrong-principal download denied, legacy route unavailable, audit canary received.

Nếu chỉ có A và B, vẫn thiếu evidence behavior; nếu có C PASS trên staging nhưng chưa có production equivalence, phải nêu giới hạn.

### 33.6. Kế hoạch remediation minh họa

1. Liệt kê supported API versions/route inventory theo regions và rings.
2. Đối chiếu pod imageIDs, startup properties, feature flag targets và authorization rules.
3. Đóng hoặc bảo vệ origin route theo đúng gateway/ingress policy, kiểm tra không còn alternate bypass.
4. Đưa worker IAM role về approved privileges, review resource policies và synthetic denied-use.
5. Triển khai config refresh/restart/rollout được phê duyệt, có canary và rollback guardrails.
6. Review admission exemptions với risk owner, đưa các namespaces thuộc scope vào kiểm soát.
7. Khôi phục audit pipeline, chạy synthetic event và kiểm tra redaction.
8. Sửa DR account collector permissions, backfill data gaps, đối soát population.
9. Verify effective storage policy và đóng temporary rule sau change/incident workflow.
10. Retest security invariants trên đúng deployment release và ghi residual risk.

### 33.7. Retest matrix của case study

| Claim được kiểm | Evidence cần có | Tình trạng trong ví dụ |
| --- | --- | --- |
| Legacy route bị tắt mọi rings. | Routes, flag evaluations, synthetic unauthorized calls. | PENDING |
| Tenant authorization trên v1/v2. | Paired A/B fixtures, positive/negative API + worker tests. | PENDING |
| Least-privileged worker. | Effective role, resource grants, denied-use test. | PENDING |
| ConfigMap/secret change đã được load. | Per-instance config version/restart and runtime behavior. | PENDING |
| Admission baseline bao phủ namespace. | Policy and live pod spec + canary rejection test. | PENDING |
| Security audit effective. | AuthZ canary event and SIEM source-health evidence. | PENDING |
| DR region population được đo. | Account list, collector health/readbacks, event history. | PENDING |

**PENDING** được giữ nguyên vì ví dụ không hề thực thi hệ thống thật. Việc viết remediation plan không tự cho phép kết luận PATCHED/SECURE.

### 33.8. Kết luận assurance đúng phạm vi

Trước retest: “Approved configuration baselines đã tồn tại nhưng chưa có đủ evidence operating effectiveness ở toàn bộ production rings; đã thấy runtime drift và source-coverage gaps. Không có cơ sở kết luận configuration assurance 100%.”

Sau khi thật sự xác minh, có thể nói: “Đối với assets, regions, release rings, API versions, identity scopes và time window đã định, desired/actual/effective states đã được đối chiếu; các deviations còn lại được báo theo risk/exception.” Không suy ra không còn unknown threats hoặc code vulnerabilities.

## 34. Measurement: KPI/KRI/KCI cho runtime configuration assurance

Một dashboard hữu ích phải tách **compliance của property**, **thực thi security behavior**, **coverage** và **confidence của evidence**.

| Metric ID | Công thức hoặc nguyên tắc đo | Cần công bố |
| --- | --- | --- |
| **RC-M01 Inventory coverage** | Required runtime assets discovered / independent in-scope population. | Mẫu số, unknown accounts/ephemeral assets. |
| **RC-M02 Baseline coverage** | Eligible control targets có approved baseline / total eligible control targets. | Baseline không tự bảo đảm effective. |
| **RC-M03 Declared-to-live alignment** | Live workloads match approved config/version / evaluated eligible workloads. | Hash match khác behavior match. |
| **RC-M04 Effective security test coverage** | Required security invariants có valid observed tests / total required invariants. | Test paths/actors/tenant tiers. |
| **RC-M05 Verified runtime control pass** | Control targets đạt readback và tests cần thiết / evaluated targets. | Tách UNKNOWN/EXCEPTION khỏi PASS. |
| **RC-M06 Drift detection latency** | Time from unauthorized change to detection theo risk tier. | Event timestamps, observer lag. |
| **RC-M07 Drift remediation latency** | Time from confirmed deviation to verified effective fix. | Ticket close khác test completion. |
| **RC-M08 Configuration source health** | Required sources/collectors healthy and complete / required sources. | Quota, permissions, pagination, source gaps. |
| **RC-M09 Runtime config freshness** | Evidence trong per-control SLA / eligible control targets. | Dynamic flags cần SLA ngắn hơn host defaults. |
| **RC-M10 Partial-rollout exposure** | Affected old-config replicas/routes còn tồn tại trong rollout window. | Criticality và exposure hơn average. |
| **RC-M11 Feature-flag governance** | Material flag changes có approval/audit/timed rollout / required changes. | Không tính UI click log là approval. |
| **RC-M12 Unauthorized override count** | Effective deviations không có approved change/exception theo impact. | Khác tolerated temporary controls. |
| **RC-M13 Least-privilege verification** | Eligible workload roles với effective permissions + denied-use tests / eligible roles. | Identity và resource policy cùng xét. |
| **RC-M14 Secret rotation effectiveness** | Required rotations đã load new và revoke old / rotations đến hạn. | Store rotation khác loaded/revoked. |
| **RC-M15 Telemetry canary success** | Expected security canary events tới audit trong SLA / executed valid canaries. | Canary preconditions và collector health. |
| **RC-M16 Runtime readback provenance** | Critical observations có source/time/version/integrity / required observations. | Hash không chứng minh source đúng. |
| **RC-M17 Exception hygiene** | Exceptions có owner/scope/expiry/review and active controls / active exceptions. | Exception không phải compliance PASS. |
| **RC-M18 Reassessment triggers handled** | Material changes có updated verification / identified material changes. | Trigger inventory phải đầy đủ. |
| **RC-M19 Deployment artifact alignment** | Running instances có approved build/imageID / independently known active instances. | Canary vs stable/regions. |
| **RC-M20 Verified unauthorized-access deny** | Controlled negative scenarios đúng expected và không side effect / valid scenarios. | Không suy mọi data paths từ vài cases. |

### Ví dụ số liệu giả định

Trong 100 production pods thuộc population đã đối chiếu, 95 đang dùng image/config được duyệt; 3 còn phiên bản cũ, 2 thiếu runtime evidence. **Approved artifact alignment = 95/100**, nhưng nếu 2 chưa rõ trạng thái và 3 pods cũ chạy ở API public, không được trình bày “95% assets secure”.

### Không trộn đơn vị đo

Một cloud account, một Kubernetes pod và một business API route là **khác đơn vị**. Gộp chúng vào mẫu số chung có thể tạo tỉ lệ vô nghĩa. Báo theo asset class/control target và dùng critical gates, kết quả định tính cho những paths quan trọng.

### Trạng thái khi mẫu số không biết

Nếu DR region collector lỗi, **unknown population** phải được thể hiện riêng thay vì tự đặt denominator = 0. Không thể tính một mức coverage chắc chắn khi không biết tập eligible.

## 35. Findings: phân biệt deviation, noncompliance và exploitable vulnerability

| Loại | Ví dụ | Cách xử lý |
| --- | --- | --- |
| **Configuration deviation** | Một pod có profile khác approved manifest. | Verify source/impact và thay đổi đúng workflow. |
| **Control design gap** | Baseline không yêu cầu resource authorization tại worker. | Update requirements/threat model/control placement. |
| **Operating failure** | Property bật nhưng endpoint không enforce. | Confirm behavior, root cause, fix và retest. |
| **Security vulnerability** | User A thật sự đọc canary B trong authorized test. | Risk severity, containment/remediation và evidence. |
| **Evidence insufficiency** | Collector account mất quyền, không có readback. | Repair source, backfill và qualify conclusion. |
| **Approved exception** | Legacy system chưa thể dùng non-root, có mitigation. | Risk approval/expiry/controls; không mark compliant. |
| **Stale record** | CMDB nói object active nhưng provider xác nhận removed. | Lifecycle reconciliation, remaining routes/secrets/backup. |
| **False positive candidate** | Scanner báo root nhưng container thực dùng UID không-root. | Validate precise rule/runtime scope before disposition. |

### Root cause investigation

Một violation có thể do override precedence, process không reload, wrong service identity, configuration service stale, policy mismatch hoặc direct bypass route. **Quan sát hành vi sai chưa tự xác định root cause**, đặc biệt khi có nhiều enforcement points.

### Finding record

Ghi `finding_id`, control/requirement, affected asset/context, expected vs actual/effective, observation source/time, severity/risk, owner, change/incident context, immediate containment, due date, retest, exception decision và evidence limitations.

## 36. Patch, rollout, rollback và hiệu lực cấu hình

Cấu hình có thể được cập nhật bằng restart, rolling deploy, feature flag evaluation, configuration service push hoặc cloud API; chúng có failure modes khác nhau.

### Một rollout an toàn cần

1. **Baseline and approved change** rõ mục tiêu và risk.
2. **Scope/affected assets** bao gồm region, rings, tenants và legacy paths.
3. **Preconditions:** dependency compatibility, capacity, backup/restore khi cần.
4. **Canary:** đo actual loaded value và security behavior, không chỉ readiness.
5. **Progressive rollout:** theo dõi instances/routing/metrics và mixed states.
6. **Stop condition:** authz regression, secret exposure, availability/data integrity impact.
7. **Rollback/roll-forward:** xem liệu rollback config có mở lại vulnerability không.
8. **Post-change readback:** runtime identities, gateway/storage policies, audit canaries.
9. **Retest:** đúng requirement và affected population.
10. **Evidence:** approved vs actual timeline, owner và residual risk.

### Rollback cũng thay risk

Nếu rollback security policy về trạng thái permissive để khôi phục availability, hệ thống có thể ổn định trở lại nhưng **mất control**. Ticket incident có thể “service restored” song finding security phải được reopen, có interim containment/risk authority và remediation plan mới.

### Partial rollout không tự thất bại nếu được quản trị

Mixed-version state có thể là giai đoạn đã được phê duyệt, với compatibility và giới hạn exposure. Tuy nhiên nếu một critical requirement như tenant isolation vẫn bị bypass trên old ring, cần xét **criticality gate**, không chỉ so current percentage với target.

## 37. Exceptions và residual risk của cấu hình không thể sửa ngay

Có workload legacy chưa chạy được non-root, ứng dụng cũ chưa hỗ trợ strict TLS profile hoặc business process cần thời gian đổi IdP token validation. Những trường hợp đó có thể cần **exception quản trị**, không phải “đánh dấu PASS”.

### Một exception đầy đủ

- Exact asset/release/tenant/environment và security requirement chưa đạt.
- Lý do kỹ thuật/biz constraint và verified expected vs actual state.
- Risk: exposure, affected data, capabilities, potential impact, uncertainty.
- Interim/compensating controls và evidence hiệu lực.
- Remediation owner, risk owner đúng thẩm quyền, expiry/review date.
- Action plan/milestones và scope-limited acceptance criteria.
- Triggers: incident, new route, exploit intelligence, dependency/platform change.
- Regulatory/contractual constraint đã được chuyên trách xem xét.
- Retest conditions để đóng.

### Viết đúng trạng thái

**ACCEPTED_RISK:** requirement chưa đạt nhưng được phê duyệt trong giới hạn.

**COMPENSATED:** một control khác giảm exposure được verify; underlying deviation còn.

**VERIFIED_FIXED:** actual/effective state đáp ứng baseline và tests trên scope.

**UNKNOWN:** thiếu evidence. Không dùng accepted risk để biến technical control status thành PASS.

### Ví dụ

Một appliance không hỗ trợ required cipher profile và chưa thể thay. Network isolation, vendor-supported gateway hoặc replacement plan có thể giảm rủi ro, nhưng cần đo effective isolation và đánh giá loại dữ liệu/paths, không ghi “TLS compliant” chỉ vì exception được ký.

## 38. Continuous configuration assurance và change triggers

Static monthly scans khó bắt kịp thay đổi feature flags, cloud IAM grants, autoscaling, API routes và credentials. Chương trình trưởng thành thường cần cả **event-driven checks** và **periodic independent reconciliation**.

### Trigger nên giám sát

- Thay Git baseline, Helm/Terraform, gateway/ingress, cloud policies.
- New cloud account, namespace, workload, API route, region hoặc SaaS integration.
- Restart/redeploy, image digest, platform/security library upgrade.
- Secret rotation, key/cert/IdP metadata, role grants hoặc revocation.
- Feature flag rollout, emergency override, targeting rule.
- Database schema/role/parameter group change.
- Admission policy change, exception, direct console alteration.
- Monitoring/log collector outage hoặc schema change.
- Security incident, pentest finding, failed restore hoặc suspicious behavior.

### Continuous loop

~~~mermaid
flowchart TD
    A["Approved baseline, asset and control inventory"] --> B["Change event / scheduled evaluation"]
    B --> C["Collect desired, actual, loaded and behavioral evidence"]
    C --> D["Validate source health, scope and provenance"]
    D --> E{"Applicable control effective?"}
    E -- "Yes" --> F["Record versioned PASS with limitations"]
    E -- "No" --> G["Finding, owner, containment and remediation"]
    E -- "Unknown" --> H["Evidence gap, source repair and investigation"]
    G --> I["Approved fix and change rollout"]
    H --> C
    I --> C
    F --> J["Monitor events, rollback and risk changes"]
    J --> B
~~~

### Một event không phải toàn bộ population

Nhận cloud config-change event là tốt, nhưng phải xử lý **missed events, replay, dedup, out-of-order updates, permissions changes, regional outages**. Periodic independent reconciliation giúp phát hiện gaps mà event stream không thấy.

### Trigger theo risk

Một change tới tenant authorization policy hoặc KMS access có thể cần retest ngay. Một thay đổi log format ít impact có thể được đánh giá theo cửa sổ policy khác. Freshness và SLA phải là quyết định **risk-based**, không áp cùng chu kỳ “quét 30 ngày” cho mọi control.

## 39. RACI và trách nhiệm của các lớp runtime configuration

Một vấn đề runtime thường trải qua nhiều teams: Dev sở hữu defaults, Platform sở hữu cluster, Cloud team sở hữu network/IAM, AppSec sở hữu requirements, Product sở hữu feature rollout và SRE sở hữu uptime. Không có accountable owner rõ, những drift nghiêm trọng có thể được chuyển vòng qua nhiều nhóm.

| Vai trò | Trách nhiệm chính |
| --- | --- |
| **Business/service owner** | Định nghĩa nghiệp vụ, criticality, protected data, expected tenant/role behavior. |
| **Application development owner** | Secure defaults, property binding, startup validation, authorization và application tests. |
| **Platform/SRE owner** | Workload orchestration, process/user identity, effective deployment, restart/rollout/capacity. |
| **Cloud/IAM/network owner** | Cloud roles, trust/resource policies, ingress/egress, KMS, object storage. |
| **Data/DB owner** | Effective database roles, encryption, row access, backup/restore và audit. |
| **Feature flag/change owner** | Targeting, control-impact approval, rollout history, audit và rollback. |
| **Security control owner** | Baseline definitions, control IDs, risk-based tests, exception workflow. |
| **Security assurance assessor** | Evidence independence, completeness, effective-state tests, qualified conclusions. |
| **SOC/incident response** | Detect changes, verify security events, monitor abuse và trigger containment. |
| **Business/risk owner** | Chấp nhận residual risk đúng thẩm quyền và review exceptions. |

### RACI minh họa

**R** = thực hiện, **A** = chịu trách nhiệm cuối cùng, **C** = tham vấn, **I** = được thông báo.

| Hoạt động | App | Platform | Security | Assurance | Risk owner |
| --- | :---: | :---: | :---: | :---: | :---: |
| Viết secure defaults và validation | **A/R** | C | C | I | I |
| Deploy workload và thu live specs | C | **A/R** | C | I | I |
| Định nghĩa baseline và test requirements | C | C | **A/R** | C | I |
| Giám sát source health và config drift | C | **A/R** | R | C | I |
| Controlled security behavior tests | R | R | **A/R** | C | I |
| Independent evidence/closure review | C | C | C | **A/R** | I |
| Risk acceptance của exception | C | C | C | C | **A/R** |

RACI cần điều chỉnh theo tổ chức, nhất là khi app nằm trên managed platform có shared responsibility. Với controls critical, cân nhắc **separation of duties** giữa người thay configuration, người đánh giá effectiveness và người chấp nhận rủi ro.

### Owner của UNKNOWN

Ngay cả khi chưa xác định asset owner, phải có **triage owner** cho gap. “Unknown” không được treo không thời hạn; cần deadline/escalation dựa criticality.

## 40. Scorecard và cách báo cáo runtime assurance

Một scorecard có tính quản trị nên tách **state, control effectiveness, evidence confidence và risk**.

| Control domain | Approved intent | Actual/live state | Effective behavior | Evidence confidence |
| --- | --- | --- | --- | --- |
| **Application AuthZ** | Tenant/role policy version R. | Loaded config + running build. | Synthetic A→B DENY across supported paths. | High khi tests + source health đầy đủ. |
| **Kubernetes privilege** | Non-root/least privilege theo workload. | Pod/admitted/process specs. | Container/user capabilities và denied actions. | Phụ thuộc privileges/time/scope. |
| **Cloud IAM** | Scoped worker role/resources. | Effective principal and policies. | Allowed/denied-use checks. | Chỉ theo actions/resources đã thử. |
| **Network/TLS** | Restricted ingress/egress, trusted identities. | Gateway/net policy effective readback. | Controlled connectivity/identity tests. | Có thể bỏ alternate paths. |
| **DB/Storage** | TLS/private/tenant policy. | Role, bucket/database configs. | Test reads/writes và tenant isolation. | Phụ thuộc fixture/role. |
| **Feature flags** | Reviewed targeting/fail mode. | Flag rules/evaluation state. | Tenant/cohort tests và outage behavior. | TTL và mixed states cần nêu. |
| **Secrets** | Scoped secret access và rotation. | Metadata, workload load version. | Old credential denied/new works. | Không lộ secret values. |
| **Audit** | Sensitive events with redaction. | Agent/collector configuration. | Canary events delivered, data sanitized. | Collector health, retention window. |

### Không tô xanh cho thiếu dữ liệu

Chỉ ghi PASS khi **đủ required evidence** cho claim. Nếu cloud account không được inventory hoặc collector im lặng, không dùng “không có findings” làm pass; dùng UNKNOWN/INSUFFICIENT_EVIDENCE.

### Phân loại confidence

- **HIGH (within scope):** nhiều nguồn tương đối độc lập, freshness đáp ứng, behavior test đủ cho critical paths, không có unresolved conflict material.
- **MEDIUM:** desired/actual readback đáng tin nhưng một số important behavior tests chưa đủ.
- **LOW:** chỉ có declarative config, stale snapshot hoặc self-reported checkbox.
- **UNKNOWN:** nguồn không hoạt động, population không xác định hoặc test preconditions không thể xác minh.

Đây chỉ là **quy ước gợi ý**, phải được tổ chức định nghĩa bằng tiêu chí đo cụ thể; không biến confidence labels thành “security grade” duy nhất.

## 41. Anti-patterns và những ngộ nhận về cấu hình runtime

| Anti-pattern | Hậu quả | Cách sửa |
| --- | --- | --- |
| **Git is runtime truth** | Bỏ manual override hoặc stale instances. | Live readback và behavior tests. |
| **Deployment success means effective** | Process chưa reload hoặc route chưa đổi. | Loaded/effective verification. |
| **`securityEnabled=true` đủ** | Code path có thể bỏ qua flag/control. | Negative tests theo invariant. |
| **All pods giống nhau** | Canary/stable/region có mixed states. | Per-population inventory và readback. |
| **ConfigMap changed = app reloaded** | Env/stale bean/process chưa nhận update. | Test reload semantics và restart. |
| **Secret stored in Kubernetes = safe** | RBAC/log/dump/rotation vẫn có thể lộ. | Least privilege, secret lifecycle, redaction. |
| **Base64 là encryption** | Nhầm dữ liệu đã được bảo vệ. | Xem encryption at rest, access and key management. |
| **Non-root = least privilege hoàn toàn** | IAM/capabilities/mounts vẫn quá rộng. | Cross-layer privilege analysis. |
| **NetworkPolicy exists = enforced** | Labels/CNI/namespace không match. | Effective connectivity tests. |
| **TLS at edge = end-to-end TLS** | Backend hop/DB connection có thể plaintext. | Per-hop transport/trust verification. |
| **Private IP means no risk** | Compromised internal workload vẫn lateral movement. | Threat model, effective role/net controls. |
| **DB RLS exists = all queries scoped** | Privileged role hoặc worker bypass. | Effective session/tenant tests. |
| **UI flag hides security function** | Backend route vẫn reachable. | Server-side enforcement/route tests. |
| **Feature flag fallback always allow** | Dependency outage làm mở bypass. | Safe failure semantics. |
| **Revoke role = immediate everywhere** | Cache/token propagation window không được quản. | Approved SLA và timed tests. |
| **Admission policy covers existing pods** | Pods tạo trước còn unsafe. | Live inventory + enforcement reassessment. |
| **All exceptions compliant** | Risk acceptance bị nhầm với control PASS. | Exception status/risk separate. |
| **Collector healthy = complete** | Thiếu account/region/resource types. | Independent population reconciliation. |
| **No drift findings = zero risk** | Scanner thiếu capability hoặc blind spot. | Source health và critical negative tests. |
| **One runtime config snapshot is forever** | Flags, IAM, images và roles đổi liên tục. | Event-driven + periodic assurance. |
| **Rollback returns system secure** | Có thể rollback về cấu hình dễ tổn thương. | Reopen finding và risk treatment. |
| **A canary passed so all rings pass** | Stable instances chưa updated. | Deployment population + per-ring verification. |
| **Copy full env to ticket** | Lộ secrets và internal topology. | Sanitized evidence fields. |
| **All config noncompliance is exploitable** | Overclaim root cause/impact. | Tách deviation và observed vulnerability. |
| **Good aggregate percentage erases critical gap** | Một privileged/public path chưa kiểm. | Criticality gates và stratified reporting. |

### Khi reviewer nghe “đã cấu hình rồi”

Hỏi tiếp: **“Đã cấu hình ở đâu? Đã deploy chưa? Process nào nạp? Có override không? Đang áp lên những assets/regions/tenants nào? Phép thử nào chứng minh behavior? Evidence thu lúc nào và source có khỏe?”** Những câu này chuyển câu trả lời từ design claim thành operating-evidence discussion.

## 42. Checklist kiểm toán Runtime Configuration

Checklist nên được dùng với **evidence IDs, scope, owner, kết quả PASS/FAIL/PARTIAL/UNKNOWN/N/A và next action**, không chỉ đánh dấu checkbox.

1. **Security objectives:** control cần đạt confidentiality/integrity/availability hoặc requirement nào?
2. **Risk/threat:** threat scenario và protected data/asset đã được mô tả?
3. **Population:** accounts, clusters, regions, release rings, workloads, APIs, tenants đã xác định?
4. **Independent scope source:** inventory có nguồn đối chiếu ngoài scanner?
5. **Baseline:** expected values/behaviors được duyệt, version và applicability rõ?
6. **Desired state:** Git/IaC/Helm/config files có commit/change ID đúng?
7. **Configuration precedence:** profile, env, external config, flags, JVM args có được xét?
8. **Deployment:** live specs và immutable build/image digests trùng approved release?
9. **Loading semantics:** restart/reload/dynamic refresh đã được xác minh?
10. **Mixed versions:** old/new instances, nodes, API versions có state tracking?
11. **Runtime diagnostics:** không expose raw sensitive config hoặc secrets?
12. **Application security:** authentication/authorization/validation effective?
13. **Tenant boundaries:** synthetic A/B negative tests trên supported paths?
14. **Container identity:** UID, capabilities, privileged mode, filesystem/mounts đúng?
15. **Kubernetes:** admission, PDB/rollout, actual pod specs, namespace policies phù hợp?
16. **Secrets:** scope, store, rotation, old revoke và redacted evidence?
17. **IAM:** effective principal/role/resource policies và denied-use outcomes?
18. **Network:** ingress/egress, mTLS/TLS, direct bypass, CNI/network policy tests?
19. **Gateway:** route versions, auth plugin, headers, cache và admin paths?
20. **Database:** effective session role, RLS/tenant scoping, transport và backups?
21. **Object storage:** effective public/private permissions và link lifecycle?
22. **Feature flags:** approved targeting, override audit, fallback và outage behavior?
23. **Time windows:** propagation/revocation/mixed states đo với clock/timestamps?
24. **Drift:** manual changes, stale configs, unsupported resources được phát hiện?
25. **Collector health:** permissions, pagination, errors, source freshness và gaps?
26. **Security tests:** positive/negative tests có expected and observed outcomes?
27. **Audit:** security event canaries, redaction, source completeness/retention?
28. **Evidence:** provenance, asset/release identity, time, integrity, limitations?
29. **Privacy:** evidence collection tối thiểu hóa dữ liệu nhạy cảm và access controls?
30. **Findings:** config deviation, actual vulnerability, unknowns có được phân loại?
31. **Remediation:** fix có approved change, canary, runtime retest, rollback plan?
32. **Exceptions:** owner, expiry, interim effective controls và risk authority?
33. **Criticality gates:** một public/privileged failure không bị average che?
34. **Reassessment:** triggers/SLAs cho config, identity, feature flag và releases?
35. **Assurance conclusion:** claim chỉ áp dụng đúng population/time và evidence?

### Sử dụng checklist với dữ liệu chưa chắc chắn

Nếu một câu chưa có evidence, ghi **UNKNOWN/PENDING**. Nếu không áp dụng công nghệ, ghi **N/A kèm rationale**. Nếu chỉ có approved design nhưng chưa có runtime readback/test, ghi PARTIAL thay vì PASS cho claim về operating effectiveness.

## 43. Bài tập tình huống và gợi ý giải

### Bài tập A — YAML tắt debug, production vẫn mở endpoint

Repository có `debug=false`; một operator thấy production route diagnostic trả internal configuration.

**Gợi ý:** Kiểm tra property precedence, process-loaded state, alternate routes, gateway, active profiles và deployed artifact. Ghi **observed exposure**, không tự kết luận nguyên nhân cho đến khi đối chiếu. Đừng dump thêm secrets để chứng minh.

### Bài tập B — ConfigMap đổi nhưng worker không nhận

Đội Platform update ConfigMap và tuyên bố đã tắt legacy export. Worker pods chạy lâu vẫn xử lý jobs cũ.

**Gợi ý:** Phân biệt resource update, mounted volume/env semantics, application reload và job behavior. Readback từng worker, triển khai controlled restart/rollout với backup/availability guardrails, kiểm denied behavior rồi đóng.

### Bài tập C — Container non-root nhưng đọc được nhiều buckets

Pod dùng UID 10001, read-only filesystem và seccomp RuntimeDefault. Cloud role lại cho phép đọc tất cả S3-compatible exports.

**Gợi ý:** Process privileges và cloud IAM là hai lớp khác nhau. Least privilege cần hiệu lực ở workload identity/resource policy và application job authorization; kiểm bằng read-only policy eval/denied-use fixtures.

### Bài tập D — NetworkPolicy không chặn traffic

Một `NetworkPolicy` được apply nhưng synthetic forbidden egress request vẫn tới canary.

**Gợi ý:** Xem label selector, namespace, CNI enforcement, other paths, policy union/selection và observability. Chứng minh effective behavior qua test; resource có mặt không đồng nghĩa enforce.

### Bài tập E — Feature flag điều khiển UI

Frontend ẩn nút “Bulk Export” khi flag off nhưng API vẫn nhận request hợp lệ từ Viewer.

**Gợi ý:** Flag UI không phải authorization. Xác minh server-side function/resource checks, expected role policy, async side effects và alternate API versions; thêm negative tests.

### Bài tập F — Secret manager xoay khóa nhưng khóa cũ vẫn hoạt động

Rotation log báo thành công; worker chưa reload credential; credential cũ vẫn được service đích chấp nhận.

**Gợi ý:** Tách store update, workload load, downstream acceptance và revoke. Kiểm key version metadata/controlled authentication tests; không in secret vào report. Chưa đánh dấu rotation effective.

### Bài tập G — Canary PASS nhưng stable pool cũ

Một trong hai release rings có 10/10 pods dùng approved digest; ring còn lại 90 pods chạy bản cũ.

**Gợi ý:** Kết luận theo 10/100 hoặc theo từng ring với population đối chiếu; canary chỉ hỗ trợ rollout gate của ring đó, không chứng minh toàn production. Đánh giá material risk của stable exposure.

### Bài tập H — Audit dashboard xanh nhưng không có canary event

Monitoring agent heartbeat healthy, nhưng security event từ controlled denied request không vào SIEM.

**Gợi ý:** Source health và end-to-end delivery khác nhau. Kiểm pipeline, event schema, filters, clock/lag, collector permissions; báo evidence/operating gap và retest.

### Bài tập I — Một collector không thấy DR cloud account

Dashboard ghi 100% compliant trên 120 resources, nhưng DR account không được cấp read permission.

**Gợi ý:** Mẫu số thiếu. Báo UNKNOWN population, cấp quyền phù hợp, reconcile account/region/resource classes, chạy canary và tính lại metrics. Không lấy 120/120 làm bằng chứng toàn organization.

### Bài tập J — Data access policy đã khai nhưng session dùng role admin

DB có role `invoice_reader` giới hạn nhưng application connection pool dùng role có bypass policy.

**Gợi ý:** Đọc effective DB session principal, grants, role inheritance, RLS semantics và query paths. Test synthetic A/B và sửa pool identity; không tin chỉ file SQL provisioning.

### Bài tập K — TLS tại edge nhưng backend plaintext

External clients dùng TLS, trong khi proxy→service hoặc application→DB không có transport protection theo baseline.

**Gợi ý:** Scope per hop, effective certificate/identity/trust check, backend path inventory và risk assessment. Không gọi “end-to-end encrypted” chỉ vì 443.

### Bài tập L — Admission policy không áp cho namespace mới

Admission validation chặn privileged pod trong `invoice-prod`, nhưng một namespace automation mới nằm ngoài selector.

**Gợi ý:** Kiểm coverage/exemption logic, namespace lifecycle, existing workloads, canary theo scope và policy failure mode. Fix policy và readback all active pods.

### Bài tập M — Hai tenants có flag khác dù policy giống

Một tenant enterprise được bật legacy export khi default global off do targeting condition còn từ migration.

**Gợi ý:** Đánh giá flag effective per cohort, audit changes, approved exceptions và route behavior. Gắn tenant scope, không chỉ chụp global default value.

### Bài tập N — Rollback cấu hình làm service sống lại nhưng yếu bảo mật

Sau deploy policy strict, client cũ lỗi. Team rollback proxy authorization và restore availability.

**Gợi ý:** Tách service recovery và security compliance; xem old policy exposure, containment, compatibility migration, owner/risk decision, restart/retest. Không để finding ở VERIFIED_FIXED.

### Bài tập O — Scanner báo root nhưng process dùng UID không-root

Manifest source thiếu `runAsUser` nhưng admission mặc định áp policy non-root, process readback UID 10001.

**Gợi ý:** Đây có thể là false positive cho effective runtime claim hoặc vi phạm baseline khai báo; phân loại theo requirement và scope. Đối chiếu admission, actual pod/process, capabilities, IAM, không auto-dismiss mọi finding chỉ vì UID.

### Bài tập P — Tài khoản support có quyền KMS quá rộng

Support API dùng service identity có quyền decrypt nhiều keys dù chỉ cần xem audit metadata.

**Gợi ý:** Least privilege gap; đánh giá effective permissions, purpose/allowed action, access paths và blast radius. Có thể cần role split, scoped resources, denied-use verification và review support just-in-time controls.

### Bài tập Q — Rate limit đã nạp nhưng đường bypass tồn tại

API gateway công bố limit theo tenant, nhưng direct origin test route không đi qua gateway.

**Gợi ý:** Cần actual route topology, firewall/ingress policy và safe bounded tests theo RoE. Kết luận config loaded ở gateway không chứng minh mọi paths được enforce.

### Bài tập R — Cấu hình đúng nhưng test object B không tồn tại

Một cross-tenant test gửi invoice ID giả của B và nhận 404, rồi chấm AuthZ PASS.

**Gợi ý:** Precondition chưa đạt. Phải chứng minh B object tồn tại bằng authorized B identity và A không có quyền; sau đó controlled negative test và state readback. 404 của nonexistent object không xác nhận tenant isolation.

## 44. Câu hỏi tự kiểm tra và tư duy phản biện

### 44.1. Vì sao configuration parity không đồng nghĩa behavioral parity?

Hai pods có cùng environment variables nhưng một pod dùng artifact cũ với route matcher khác hoặc feature flag cache khác. Cùng raw values không bảo đảm cùng effective behavior. Cần **runtime build identity, evaluation context và tests**.

### 44.2. Một policy đã apply có thể là control failure không?

Có. Policy có thể không chọn đúng target, bị bypass bởi direct route, có exception rộng hoặc không có enforcement backend. Readback của policy phải đi cùng **selection check và effective behavior**.

### 44.3. Có nên luôn fail closed?

Với authorization quyết định truy cập dữ liệu nhạy cảm, việc không có policy hợp lệ thường cần deny. Với các systems availability-critical, thiết kế có thể yêu cầu degraded service mà vẫn không vi phạm invariant. Kết luận phải dựa **threat model và approved safe-failure contract**; không áp “fail closed” một cách máy móc mà không xét tác động.

### 44.4. “No findings” có đủ làm bằng chứng không?

Không. Nó chỉ có ý nghĩa nếu biết **population, collector health, relevant rule coverage, freshness, evidence source và behavior tests**. Sự vắng mặt findings khi scanner mù là unknown, không phải an toàn.

### 44.5. Bao giờ cần reviewer độc lập?

Khi control ảnh hưởng data sensitive, privileged identities, cross-tenant isolation, signing keys, incident recovery hoặc release gates high impact. Reviewer độc lập giúp challenge assumptions và evidence, nhưng cần **quy định cụ thể theo risk policy**, không mặc định mọi change nhỏ cần quy trình nặng tương tự.

### 44.6. Cấu hình có thể đúng tại T nhưng sai tại T+1 không?

Có. Dynamic flags, IAM policy, secret rotation, autoscaling, deploy và token caches có thể đổi ngay khi đang hoạt động. Vì vậy assurance có **time scope và reassessment triggers**, không phải giấy xác nhận vĩnh viễn.

## 45. Kết luận

**Cấu hình runtime** là điểm mà ý định thiết kế gặp **hành vi thực** của hệ thống. Trong **Configuration assurance**, file Git, Helm values, Terraform hoặc policy-as-code có giá trị rất lớn cho thiết kế, review và kiểm toán, nhưng không tự chứng minh application, container, database, cloud IAM, network gateway, feature flag và secrets **đang vận hành đúng security requirements**.

Với **SECURITY_SECURITY_ASSURANCE**, kết luận có bằng chứng cần nối được:

**Approved baseline → independent asset population → deployed/live configuration → loaded/effective runtime state → security behavior tests → reviewed evidence → findings/remediation/retest → continuous reassessment.**

Các rủi ro cốt lõi gồm **property precedence sai, profile/flag overrides, non-converged rollouts, ConfigMap/Secret chưa reload, IAM quá rộng, admission/NetworkPolicy không chọn đúng target, TLS chỉ bảo vệ một hop, gateway route bypass, database role không đúng, collector source gap và những ngoại lệ không được quản lý**. Chúng đòi đánh giá theo **scope, actor, resource, environment, region, release, tenant và thời điểm**, thay vì một nhãn “configured”.

Một báo cáo tốt phân biệt **đã khai báo**, **đã triển khai**, **đang nạp**, **có hiệu lực** và **đã kiểm chứng hành vi**, đồng thời công bố **unknowns, evidence limitations, residual risk và reassessment triggers**. Nếu chưa đủ bằng chứng thì ghi UNKNOWN/PARTIAL; nếu risk được chấp nhận thì ghi EXCEPTION chứ không biến control thành PASS.

**Mục tiêu cuối cùng là chứng minh bằng trạng thái runtime và những phép thử có thể tái lập rằng cấu hình bảo mật thật sự bảo vệ tài sản và dữ liệu trong phạm vi được đánh giá, rồi duy trì sự tin cậy đó khi hệ thống tiếp tục thay đổi.**
