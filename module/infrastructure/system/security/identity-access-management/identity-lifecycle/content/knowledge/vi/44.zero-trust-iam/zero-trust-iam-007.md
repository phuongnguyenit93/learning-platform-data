# Workload posture — Trạng thái tin cậy của workload trong Zero Trust IAM

> **Chương:** Zero Trust IAM  
> **Chủ đề:** Workload posture  
> **Phạm vi module:** Quản lý vòng đời danh tính và quyền truy cập theo mô hình **Joiner–Mover–Leaver (JML)**, từ xác minh, tạo danh tính, cấp quyền đến rà soát và thu hồi khi thay đổi vai trò. Bài học kết nối IdP, SSO, SCIM, RBAC/ABAC, tài khoản dịch vụ, kiểm toán và giảm quyền truy cập tồn dư.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích **workload posture** là tập hợp bằng chứng về nguồn gốc, cấu hình, môi trường, trạng thái và rủi ro của một workload tại thời điểm quyết định; phân biệt với **workload identity** và **authorization**.
2. Nhận diện các tín hiệu posture ở **giai đoạn build, triển khai và runtime**, gồm provenance, image digest/chữ ký, admission, cấu hình bảo mật, cảnh báo và trạng thái vòng đời.
3. Thiết kế quyết định truy cập dựa trên **chủ thể workload + danh tính + posture + action + resource + context**, kết hợp giới hạn quyền theo RBAC/ABAC và nguyên tắc quyền tối thiểu.
4. Mô tả cơ chế bootstrap/attestation danh tính workload, token ngắn hạn, workload identity federation, mTLS và các giới hạn của những bằng chứng này.
5. Gắn việc đăng ký, chuyển chủ/quyền, thay phiên bản và ngừng workload với quy trình **Joiner–Mover–Leaver**, kể cả service account, secret và tích hợp bên thứ ba.
6. Thiết kế cơ chế xử lý tín hiệu posture **mất, quá hạn, thay đổi, trái ngược hoặc bị nghi giả mạo**, cùng đường thu hồi quyền và khoanh vùng sự cố.
7. Xây dựng kiểm thử và chỉ số cho **hiệu lực của chính sách, độ mới tín hiệu, thời gian thu hồi và phạm vi ảnh hưởng**.

## 2. Workload posture là gì?

**Workload** là đơn vị tính toán thực hiện nhiệm vụ: một ứng dụng chạy trên VM, service trong container/Kubernetes, function serverless, batch job, CI runner, pipeline hoặc tiến trình tích hợp. Trong IAM, workload là **chủ thể máy** có thể yêu cầu token, gọi API, đọc secret và xử lý dữ liệu, kể cả khi không có người dùng đăng nhập tương tác.

**Workload posture** là đánh giá về việc workload ấy đang đáp ứng những điều kiện bảo mật và vận hành nào. Nó có thể bao gồm:

- **Nguồn gốc:** artifact do pipeline được ủy quyền tạo ra? Có bằng chứng build/provenance, chữ ký và digest được xác minh?
- **Danh tính và phạm vi:** workload được gắn với principal/namespace/project nào? Quan hệ giữa credential và tiến trình thực đã được chứng minh?
- **Cấu hình triển khai:** image/version được cho phép? Có quyền root, privileged mode, host mount, secret hoặc network permission quá rộng không?
- **Môi trường runtime:** node/cluster/VM có đáp ứng baseline? Runtime có cảnh báo xâm nhập, cấu hình drift hoặc trạng thái bị cách ly không?
- **Vòng đời:** service còn được phê duyệt triển khai? Owner, hợp đồng, environment, version và credential còn hợp lệ?
- **Độ mới của bằng chứng:** posture được kiểm tra khi nào, do nguồn nào phát, có còn đủ mới để làm căn cứ truy cập không?

**Workload identity** trả lời: *“Workload nào đang yêu cầu?”*  
**Workload posture** trả lời: *“Ta có bằng chứng gì về độ tin cậy của workload và môi trường đang chạy?”*  
**Authorization** trả lời: *“Workload đó có được phép thực hiện hành động này trên tài nguyên này không?”*

Ba câu hỏi liên quan nhưng không thay thế nhau. Một service có danh tính hợp lệ vẫn có thể chạy image chưa được phê duyệt hoặc mang quyền cloud quá rộng. Ngược lại, một container được build chuẩn vẫn không tự có quyền đọc dữ liệu khách hàng của tenant khác.

### Tình huống mở đầu

Một job tên **billing-reconcile** dùng workload identity để đọc hóa đơn và ghi kết quả đối soát. Job đã được cấp quyền trong hệ thống cloud, nhưng có hai lần chạy:

| Thuộc tính | Lần chạy A | Lần chạy B |
|---|---|---|
| Chủ thể được khai báo | billing-reconcile | billing-reconcile |
| Artifact | Digest đã phê duyệt, có bằng chứng nguồn gốc | Image được thay bằng bản chưa phê duyệt |
| Nền tảng | Runner/namespace được phép | Runner cá nhân chưa được kiểm chứng |
| Quyền yêu cầu | invoice.read trên tenant A | invoice.read trên tenant A |
| Runtime | Không có cảnh báo rủi ro | Có cảnh báo thay đổi tiến trình bất thường |
| Quyết định mong đợi | Có thể allow nếu AuthN/AuthZ và các điều kiện khác đạt | Deny hoặc cách ly theo policy cho workload nhạy cảm |

Việc cả hai lần chạy trình cùng một service name chưa đủ. Chính sách cần xác nhận bằng chứng được **liên kết với đúng workload instance** đang gọi, đặc biệt khi dữ liệu nhạy cảm hoặc quyền cao.

## 3. Phân biệt posture, identity, attestation và compliance

| Thuật ngữ | Ý nghĩa | Giới hạn |
|---|---|---|
| **Workload identity** | Danh tính được gán cho service/job/instance, ví dụ service principal hoặc SPIFFE ID | Không tự chứng minh mã và môi trường đang chạy an toàn |
| **Authentication** | Kiểm chứng chứng thực như token, chứng chỉ, mTLS hoặc liên kết federation | Xác thực thành công không cấp quyền mọi tài nguyên |
| **Workload attestation** | Quy trình đưa ra và xác minh bằng chứng về thuộc tính workload/môi trường, ở mức nền tảng hỗ trợ | Phạm vi thuộc tính được chứng minh phụ thuộc nguồn, phương pháp và mô hình đe dọa |
| **Artifact provenance** | Bằng chứng về nguồn code, pipeline, thao tác build và artifact đầu ra | Artifact hợp lệ vẫn có thể chứa lỗi hoặc bị lạm dụng runtime |
| **Artifact signature** | Bằng chứng tính toàn vẹn/xác thực của artifact theo khóa và chính sách tin cậy | Chữ ký hợp lệ không tự chứng minh artifact đã được rà soát nội dung |
| **Compliance** | Kết quả so với chính sách/baseline đã định nghĩa | “Compliant” là kết quả tại một thời điểm, không phải trạng thái tin cậy vĩnh viễn |
| **Runtime posture** | Trạng thái thực tế khi workload chạy: cấu hình, cảnh báo, môi trường, rủi ro | Telemetry có thể trễ hoặc bị mất; không có alert không đồng nghĩa tuyệt đối an toàn |
| **Authorization** | Quyết định cho phép action trên resource ở ngữ cảnh cụ thể | Không nên suy ra chỉ từ trạng thái posture hoặc scope token |

### Attestation không phải một nút “trust”

Ví dụ một cơ chế workload attestation có thể xác minh service account, namespace, thông tin môi trường hoặc khóa được bảo vệ bởi nền tảng. Nó chỉ chứng minh **những thuộc tính cụ thể mà cơ chế đó thực sự hỗ trợ**. Không thể suy từ việc nhận chứng chỉ workload sang kết luận “image không có lỗ hổng” hoặc “môi trường không bị xâm nhập”.

Các bằng chứng mạnh khác nhau ở **nguồn tin cậy, tính toàn vẹn, độ mới và mức liên kết với tiến trình thực**. Một header do ứng dụng tự gửi như X-Workload-Compliant: true không đáng tin nếu PEP không thể xác minh nguồn phát và binding của bằng chứng.

## 4. Ba thời điểm hình thành posture: build, deploy, runtime

Workload posture thay đổi suốt vòng đời phần mềm. Chỉ kiểm tra lúc build hay lúc khởi động không đủ để bảo vệ mọi request sau này.

| Giai đoạn | Câu hỏi đánh giá | Bằng chứng ví dụ | Điểm kiểm soát |
|---|---|---|---|
| **Build/supply chain** | Artifact đến từ nguồn và pipeline được phê duyệt? | Source revision, provenance, chữ ký, digest, kết quả scan, policy chất lượng | CI gate, artifact registry, release approval |
| **Deploy/admission** | Workload có được chạy tại môi trường này với cấu hình này? | Namespace, service account, image digest, security context, secret mounts, quyền, admission result | Deployment controller, admission policy, workload scheduler |
| **Runtime** | Instance đang chạy có còn đáp ứng policy và rủi ro hiện tại? | Instance/workload ID, trạng thái node, health/EDR, runtime detection, drift, credential state | Runtime monitor, PDP, API/PEP, secret broker, service mesh |
| **Retire/stop** | Workload đã kết thúc có còn key, token, role hoặc kết nối hoạt động? | Registry owner, deployment state, role grants, secret inventory, revocation receipts | Lifecycle orchestration, IAM, reconciliation |

Một image đã được ký và phê duyệt ở build có thể được chạy với quyền **privileged**, hostPath không cần thiết, token cloud quyền rộng hoặc ở một cluster không được phê duyệt. Vì vậy **attestation của artifact không thay kiểm tra cấu hình triển khai**.

Tương tự, workload vượt qua admission lúc 08:00 có thể bị thay đổi hoặc phát sinh tín hiệu rủi ro lúc 10:00. Hệ thống cần quyết định **khi nào phải đánh giá lại và cơ chế thu hồi nào đủ nhanh**.

### Chuỗi kiểm chứng liên tục có thể mô hình hóa

~~~mermaid
flowchart TD
    S["Nguồn code được quản lý"] --> B["Pipeline build có danh tính và kiểm soát"]
    B --> A["Artifact + digest + provenance"]
    A --> G{"Build / release policy"}
    G -->|"Không đạt"| X["Reject / điều tra"]
    G -->|"Đạt"| D["Deploy / admission"]
    D --> C{"Config + môi trường + service identity"}
    C -->|"Không đạt"| X
    C -->|"Đạt"| R["Workload instance"]
    R --> I["Identity issuance / federation"]
    R --> T["Runtime posture / risk signals"]
    I --> P["PEP / API"]
    T --> P
    P --> Q{"PDP: subject + posture + action + resource"}
    Q -->|"Allow"| Z["Thực thi hành động trong phạm vi quyền"]
    Q -->|"Deny / restrict"| X
    E["JML / policy / incident event"] --> T
    E --> I
    Q --> L["Audit & monitoring"]
    L --> E
~~~

Đường nối trong sơ đồ là **luồng trách nhiệm logic**, không có nghĩa mọi hệ thống phải gọi một server tập trung ở từng request. Tổ chức có thể xác minh chứng cứ ở nhiều vị trí, phát hành assertion có thời hạn và truyền sự kiện thu hồi tới PEP.

## 5. Các nhóm tín hiệu cần đánh giá

### 5.1. Nguồn gốc và tính toàn vẹn artifact

- Code và dependency có nguồn đã xác định, truy vết commit/release phù hợp.
- Pipeline build được ủy quyền và tách quyền với workload runtime.
- Image/package được tham chiếu bằng **digest bất biến** khi thích hợp; tag có thể bị chuyển sang artifact khác.
- Chữ ký, provenance và các thuộc tính bắt buộc được xác minh trước triển khai.
- Kết quả rà soát lỗ hổng/chính sách dependency được xử lý theo ngưỡng rủi ro; exception có owner, phạm vi và thời hạn.
- Artifact được triển khai đúng môi trường, đúng release/phê duyệt.

**Không nên hiểu “signed = safe”.** Chữ ký xác thực nguồn hoặc tính toàn vẹn theo mô hình tin cậy; nó không tự bảo đảm code không chứa lỗi, dependency độc hại hoặc khả năng bị khai thác.

### 5.2. Cấu hình triển khai và đặc quyền runtime

- Workload chạy với service account/identity dành riêng cho công việc.
- Không dùng root/privileged mode hay host-level permission khi không cần.
- Giảm Linux capabilities, hạn chế privilege escalation, filesystem write và volume mount theo yêu cầu ứng dụng.
- Secret được lấy từ nguồn được quản lý, không hardcode vào image/repository.
- Giới hạn đường mạng và quyền gọi API; phân biệt kết nối được phép với quyền dữ liệu.
- Chính sách admission và cấu hình môi trường có chủ sở hữu, khả năng audit, xử lý drift.

Không phải mọi kỹ thuật hardening đều áp dụng nguyên trạng cho Windows, VM, serverless và Kubernetes. **Baseline phải theo môi trường thực tế**, song nguyên tắc quyền hẹp và nguồn bằng chứng đáng tin vẫn giữ nguyên.

### 5.3. Trạng thái workload khi vận hành

- Instance còn thuộc deployment/release đã được ủy quyền, chưa bị thu hồi?
- Có cảnh báo runtime đáng tin về hành vi bất thường, thực thi tiến trình lạ, truy cập secret hoặc nâng quyền?
- Node/host/VM có đủ điều kiện để workload nhạy cảm hoạt động?
- Workload có gọi API/tenant ngoài phạm vi thông thường hay tạo credential không dự kiến?
- Posture assertion hiện tại có mới, còn hạn và gắn với đúng instance không?
- Có thay đổi policy, owner, environment hay sự kiện incident khiến quyền phải bị đánh giá lại?

**“Không có cảnh báo” không đồng nghĩa “đã chứng minh an toàn”.** Nguồn giám sát có thể không hoạt động hoặc không bao phủ một loại môi trường. Khi tín hiệu bắt buộc bị mất, hệ thống phải có quy tắc cho trạng thái unknown/stale.

## 6. Workload identity và điểm khởi đầu của chuỗi tin cậy

Để cho một workload truy cập tài nguyên, hệ thống thường cần xác định:

1. **Instance nào đang chạy?** Workload chạy ở đâu, thuộc service/namespace/job/environment nào?
2. **Vì sao được công nhận?** Platform hoặc cơ chế attestation nào xác minh các thuộc tính đó?
3. **Có được phát hành credential không?** Workload có nằm trong policy tin cậy, được phép lấy identity token/chứng chỉ, và credential dành cho audience nào?
4. **Được phép gọi gì?** Authorization kiểm tra action/resource/tenant ở API hoặc dịch vụ đích.
5. **Nếu điều kiện đổi?** Cơ chế nào chặn request, hết hạn credential hoặc thu hồi quyền?

Các mô hình hay gặp:

| Cơ chế | Ví dụ sử dụng | Điều cần kiểm tra |
|---|---|---|
| **Cloud workload identity federation** | CI job/cluster trao đổi OIDC token đáng tin để lấy credential cloud ngắn hạn | Issuer, audience, subject/claim binding, repo/branch/environment phù hợp, chính sách trust của đích |
| **Kubernetes projected service account token** | Pod yêu cầu token theo service account/audience được chỉ định | Namespace, service account, audience, thời hạn, bound object khi hỗ trợ và quyền thực tế |
| **SPIFFE/SPIRE hoặc mô hình tương đương** | Platform xác thực workload và cấp định danh/chứng chỉ ngắn hạn | Trust domain, workload selector, issuance/revocation, ràng buộc instance |
| **mTLS service-to-service** | Hai dịch vụ xác thực danh tính kênh kết nối | Chuỗi chứng chỉ, trust anchor, thời hạn, mapping principal và policy action/resource |
| **Secret/API key truyền thống** | Tích hợp legacy thiếu federation | Kho bí mật, owner, scope, rotation, không dùng chung, thời điểm thu hồi |

**mTLS chứng minh danh tính hai đầu kết nối theo chứng chỉ được tin cậy**, nhưng không tự xác minh image digest, không phát hiện mọi rủi ro runtime và không thay quyền nghiệp vụ. Một workload có chứng chỉ hợp lệ vẫn phải bị từ chối nếu yêu cầu tài nguyên ngoài scope.

### Nguy cơ nhầm lẫn giữa định danh và bằng chứng thực thi

Một service name hoặc namespace được viết trong token có thể là một claim hữu ích. Tuy nhiên phải kiểm tra token được **phát hành bởi nơi có thẩm quyền**, cho đúng audience và gắn với instance đang sử dụng. Nếu secret/token bị đánh cắp, attacker có thể đóng vai workload đó trong thời gian credential còn dùng được, tùy cơ chế ràng buộc. Vì vậy nên cân nhắc credential ngắn hạn, sender constraints và đường đánh giá lại khi có rủi ro.

## 7. Quyết định IAM dựa trên workload posture

Trong Zero Trust, một workload được xác thực không mặc nhiên được truy cập mọi dữ liệu trong mạng nội bộ. **Quyền truy cập phải được kiểm tra theo chủ thể, tài nguyên, hành động và ngữ cảnh**, trong đó posture là một phần ngữ cảnh.

**Decision = Policy(workload_identity, workload_posture, action, resource, runtime_context)**

| Thành phần | Dữ liệu cần xác minh | Ví dụ |
|---|---|---|
| Identity | Principal ID, issuer, audience, credential validity, owner | svc-billing-reconcile |
| Posture | Image digest/phê duyệt, deployment, runtime signal và freshness | Digest đã duyệt; môi trường prod; không bị quarantine |
| Action | Thao tác cụ thể | invoice.read |
| Resource | Tenant, owner, classification, API/data scope | invoices của tenant A |
| Context | Project, namespace, phiên/tokens, rủi ro, JML trạng thái | ns=finance-prod; active; risk=normal |
| Governance | Ngày hiệu lực, lý do và phê duyệt đặc quyền | Được vận hành đến hết hợp đồng dịch vụ |

### Chính sách minh họa

~~~yaml
# Pseudocode: không phải cấu hình chuẩn của một IdP, Kubernetes hay policy engine.
policy_id: finance.reconcile.read
decision: allow_if_all_required_conditions_hold
subject:
  principal_id: svc-billing-reconcile
  lifecycle_state: active
  owner_group: finance-platform
  permitted_environment: production
authentication:
  trusted_issuer: workload-identity-provider
  expected_audience: finance-api
  credential_valid: true
workload_posture:
  artifact_digest_in_approved_release: true
  provenance_verified_for_required_policy: true
  deployment_namespace: finance-prod
  deployment_service_account: billing-reconcile
  runtime_risk: acceptable
  evidence_binding: verified_for_current_instance
  evidence_fresh: true
authorization:
  action: invoice.read
  resource_tenant: tenant-A
  resource_classification: approved_for_reconciliation
on_missing_required_signal: deny
on_policy_error: deny
default: deny
audit:
  include: [principal_id, instance_id, action, resource_scope, posture_version, policy_version, decision]
~~~

Chính sách này chỉ mô tả thiết kế. **Nó không tự động làm workload đáng tin** nếu không có hệ thống cấp bằng chứng, liên kết instance, lấy trạng thái hiện tại và PEP thực thi deny. Không có một ngưỡng runtime risk hoặc freshness chung cho mọi tổ chức; phải căn cứ độ nhạy dữ liệu và giới hạn kỹ thuật.

### RBAC và ABAC trong quyết định

**RBAC** có thể cấp vai trò nền tảng như finance_report_reader cho principal của job. **ABAC** bổ sung điều kiện environment=production, namespace được phê duyệt, tenant=tenant-A, release hợp lệ và posture đạt chuẩn. Với dữ liệu đa tenant, backend lấy **tenant của resource** từ nguồn đáng tin, không cho workload tự điền tenant_id để vượt quyền.

Một job đang dùng đúng image nhưng cố xóa bảng dữ liệu vẫn phải nhận **deny** nếu role chỉ cho phép read. Một job có role read nhưng chạy ở runner chưa được phê duyệt cũng có thể bị deny theo posture policy.

## 8. Cấp phát và đánh giá lại posture qua các điểm kiểm soát

### 8.1. Trước triển khai — chặn artifact/cấu hình sai

Các cổng kiểm soát có thể gồm:

- Chỉ nhận artifact từ registry và pipeline được tin cậy.
- Xác minh digest/chữ ký và provenance theo chính sách release.
- Kiểm tra cấu hình không cấp privileged hoặc quyền cloud quá mức.
- Xác định service account/principal, owner và scope trước khi triển khai.
- Phê duyệt ngoại lệ có thời hạn khi một baseline chưa thể đạt.

Cần biết **ai có quyền thay đổi những chính sách này**. Nếu cùng pipeline có thể vừa phát hành image vừa tự sửa chính sách admission để bỏ qua kiểm tra, ranh giới tin cậy bị suy yếu.

### 8.2. Khi workload khởi động — xác minh instance

Nền tảng có thể cung cấp workload attestation/identity theo các thuộc tính runtime. Các yếu tố như service account, namespace, node, metadata cloud và trạng thái deployment cần được lấy từ **nguồn có kiểm soát**, không chỉ từ environment variable hoặc payload tự khai.

Nếu triển khai ở cluster khác hoặc một phiên bản khác, cần quyết định **có tái sử dụng danh tính và quyền cũ không**. Không nên cấp token cloud quyền production chỉ vì container khai đúng service name.

### 8.3. Khi truy cập API — thực thi ở request

Một PEP tại gateway, service mesh hoặc ứng dụng kiểm tra credential và bối cảnh. API đích tiếp tục kiểm tra authorization ở cấp tài nguyên. Có thể dùng posture assertion ngắn hạn hoặc cache theo policy để tránh mỗi request phải truy vấn toàn bộ pipeline/EDR, nhưng phải có **TTL và invalidation** thích hợp.

### 8.4. Khi tín hiệu thay đổi — chặn đường truy cập đã cấp

Nếu runtime monitor thông báo instance bị quarantine, dự án bị đóng hoặc workload bị thu hồi, hệ thống phải xác định:

- Credential nào cần hết hạn/thu hồi hoặc từ chối ở điểm truy cập?
- API nào cần đánh giá lại quyền? Cache nào cần invalidation?
- Các phiên kết nối đang mở có phải chấm dứt không?
- Có thể cô lập riêng instance mà không ngắt các workload cùng service không?
- Ai được phép khôi phục sau khi đã có bằng chứng mới?

**Posture ban đầu không tạo giấy phép truy cập vô thời hạn.** Sự kiện về workload, credential và policy phải có đường phản ánh vào quyết định tiếp theo.

## 9. Workload posture trong vòng đời Joiner–Mover–Leaver

JML trong module IAM thường nói về người dùng. Với danh tính máy, có thể áp dụng **mô hình tương tự ở mức khái niệm**: một workload hoặc integration được **đăng ký**, **thay đổi vai trò/owner/triển khai** và **ngừng hoạt động**. Không nên giả định mọi hệ thống đều dùng chính giao thức HR Joiner–Mover–Leaver để quản lý máy.

| Giai đoạn | Sự kiện | Posture và danh tính cần xử lý | Quyền cần xử lý |
|---|---|---|---|
| **Joiner / register** | Tạo service/job/integration mới | Xác định owner, mục đích, registry, pipeline, môi trường, identity issuance | Cấp đúng API, action, tenant và thời hạn; hạn chế secret |
| **Mover / change** | Đổi owner, namespace, release, tenant, deployment hoặc môi trường | Đánh giá lại artifact, posture, attestation policy, trust binding | Rút quyền cũ, cập nhật quyền mới; kiểm tra token/secret cũ |
| **Leaver / retire** | Dừng dịch vụ, hết hợp đồng, ngừng integration | Thu hồi chứng thực, đánh dấu principal retired, ngừng/thu hồi instance liên quan | Gỡ role/grant/delegation, xoay secret, xác nhận API đã chặn |
| **Periodic review** | Rà soát theo kỳ hoặc sau incident | Xác nhận owner, trạng thái deployment, nguồn artifact, cảnh báo | Thu hồi principal mồ côi, quyền không dùng và ngoại lệ quá hạn |

### 9.1. Joiner: đăng ký workload có người chịu trách nhiệm

Một service mới cần thông tin tối thiểu:

- Principal/service name và **owner nhóm**;
- Mục đích nghiệp vụ, môi trường và nguồn triển khai;
- Artifact/release được phép, pipeline và policy nguồn gốc;
- Resource/action/tenant cần truy cập;
- Cơ chế xác thực và nơi cấp token/chứng chỉ;
- Điều kiện posture bắt buộc, ngày rà soát/expiry;
- Quy trình xử lý sự cố, revoke credential và shutdown.

Quyền cần được cấp **sau khi có thông tin đáng tin và phê duyệt theo rủi ro**, thay vì gán quyền admin vì workload “là nội bộ”.

### 9.2. Mover: thay đổi môi trường hoặc quyền không được giữ quyền cũ vô hạn

Ví dụ job chuyển từ namespace sandbox sang finance-prod. Đây là thay đổi lớn về mức truy cập. Workflow cần đánh giá lại posture của artifact, runner, owner, service account và chính sách trust federation. Token cũ cấp cho sandbox không nên trở thành credential có quyền production.

Một tình huống khác: nhóm Data Platform bàn giao bot cho Finance. Nếu chỉ thay owner trong bảng quản lý nhưng **API key cá nhân của kỹ sư cũ** vẫn chạy, quyền phụ thuộc vào cá nhân và tồn tại ngoài quy trình. Cần chuyển sang principal workload thuộc nhóm, cấp scope đủ dùng, rồi thu hồi credential cũ có xác nhận.

### 9.3. Leaver: dừng workload và thu hồi đường truy cập phụ

Khi integration ngừng, các việc cần xác nhận gồm:

1. Workload instance đã dừng hoặc không còn được phép khởi chạy.
2. Principal không được cấp token/chứng chỉ mới.
3. Credential đang còn hạn và session được giới hạn hoặc vô hiệu theo cơ chế nền tảng.
4. API key/PAT/secret, quyền cloud, tài khoản database, delegation, webhook và nhóm liên quan được thu hồi.
5. Các chính sách resource vẫn cho phép principal cũ được rà soát và gỡ.
6. Audit có bằng chứng **truy cập thực đã bị chặn** ở những hệ thống quan trọng.

**Gỡ Deployment trong Kubernetes không đồng nghĩa thu hồi IAM role ở cloud**, cũng như disable user tại IdP không bảo đảm mọi access token JWT đã phát hành tự hết hạn tức thì.

### 9.4. JML con người ảnh hưởng thế nào đến workload?

Khi kỹ sư đổi vai trò hoặc rời tổ chức, các workload/bot do người đó quản lý phải được kiểm kê:

- Bot chạy bằng **credential cá nhân**: cần chuyển sang danh tính workload hoặc xử lý ngừng theo quy trình.
- Service account có owner là một cá nhân duy nhất: cần chuyển owner/approver nếu service vẫn cần hoạt động.
- Repository, CI runner, secret store và IAM policy do người cũ quản lý: phải rà soát quyền trực tiếp và quyền kế thừa.
- Các quyền tạm thời được cấp cho người triển khai: gỡ sau khi công việc hoàn tất.

Như vậy **identity lifecycle của người dùng và workload lifecycle** liên kết nhau, nhưng mỗi loại danh tính vẫn cần hồ sơ và kiểm soát riêng.

## 10. Cấu hình hardening và tư thế chạy Kubernetes

Kubernetes là ví dụ dễ hình dung về workload posture, nhưng không phải môi trường duy nhất. Với container, nên đánh giá cả **cluster/node**, **pod/deployment** và **principal**.

### Mẫu cấu hình minh họa

~~~yaml
# Ví dụ minh họa một Pod chạy ứng dụng không cần Kubernetes API token.
# Cần điều chỉnh image, volume, app runtime và policy cho hệ thống thật.
apiVersion: v1
kind: Pod
metadata:
  name: report-reader
  namespace: finance-prod
  labels:
    app: report-reader
spec:
  serviceAccountName: report-reader
  automountServiceAccountToken: false
  containers:
    - name: app
      image: registry.example.invalid/report-reader@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
      securityContext:
        runAsNonRoot: true
        allowPrivilegeEscalation: false
        readOnlyRootFilesystem: true
        capabilities:
          drop: ["ALL"]
        seccompProfile:
          type: RuntimeDefault
      resources:
        requests:
          cpu: "100m"
          memory: "128Mi"
        limits:
          memory: "256Mi"
~~~

Mẫu này chỉ nêu **một số cấu hình giảm đặc quyền**, chưa đầy đủ để triển khai production; image/digest là giá trị giả định. Ứng dụng có thể cần volume ghi được, NetworkPolicy, cấu hình chứng thực riêng, security context ở cấp Pod và yêu cầu khác theo môi trường. **automountServiceAccountToken: false** phù hợp khi tiến trình không cần token Kubernetes API trong Pod; nếu kiến trúc cần projected token cho workload identity, phải cấu hình quyền và audience theo yêu cầu thay vì vô hiệu token một cách máy móc.

**Cấu hình được viết trong manifest chưa đủ** nếu cluster không thực thi chính sách hoặc có một con đường triển khai khác bỏ qua admission. Cần kiểm tra **cấu hình thực tế được áp dụng** và audit khi có thay đổi.

### Câu hỏi rà soát ở Kubernetes

- Có thể thay image bằng tag không kiểm soát hoặc image từ registry khác không?
- Pod có dùng service account chung có quyền rộng ở namespace/cluster không?
- Có quyền privileged, hostPath, hostNetwork, hostPID hoặc capability vượt nhu cầu không?
- Pod có quyền truy cập token/secret mà nó không cần không?
- Chứng thực cloud có gắn đúng namespace/service account và environment không?
- Network egress có bị giới hạn ở API cần gọi không?
- Kết quả admission và cảnh báo runtime có ảnh hưởng đến việc cấp quyền dữ liệu nhạy cảm không?
- Khi Pod bị xóa hoặc thay phiên bản, credential nào còn dùng được ở bên ngoài cluster?

Đừng xem mọi thuộc tính trên là một Boolean đơn giản. Ví dụ việc dùng hostNetwork có thể có lý do hợp lệ đối với một daemon hệ thống, nhưng sẽ cần phạm vi, phê duyệt, giám sát và biện pháp bổ sung khác.

## 11. Phiên, token và độ mới của posture

### 11.1. Một credential hợp lệ vẫn có thể mang thông tin cũ

Giả sử lúc 08:00, workload được xác minh hợp lệ và lấy access token đến 09:00. Đến 08:15, runtime detector xác nhận instance bị xâm nhập và đánh dấu **quarantined**. Nếu API chỉ kiểm tra chữ ký/expiration của token JWT, nó có thể tiếp tục cho phép request đến 09:00, dù posture đã thay đổi.

Cần hiểu ba trạng thái tách biệt:

- **Identity issuance:** nguồn danh tính còn cấp credential mới không?
- **Token/session validity:** credential đã cấp còn được API chấp nhận không?
- **Current authorization/posture:** workload hiện có được thực hiện action này không?

Giảm rủi ro bằng cách kết hợp token ngắn hạn, thu hồi khi hỗ trợ, kiểm tra trạng thái/quyền hiện tại, sự kiện invalidation và thời hạn cache được thiết kế theo rủi ro.

### 11.2. Dòng thời gian đánh giá lại

~~~text
08:00  release A được triển khai, posture đạt, workload nhận credential.
08:10  workload gọi finance-api với quyền invoice.read hợp lệ.
08:15  runtime monitor đánh dấu instance có rủi ro nghiêm trọng.
08:16  policy state chuyển instance sang quarantined.
08:17  PEP nhận event/invalidate cache hoặc kiểm tra trạng thái mới.
08:18  workload dùng token cũ gọi finance-api.
08:18  API từ chối action nhạy cảm theo posture hiện tại.
08:25  Đội vận hành loại bỏ instance và thu hồi/rotate credential liên quan.
08:40  release được kiểm tra lại, instance mới có chứng cứ và identity riêng.
~~~

Nếu không có bước 08:17, việc gắn trạng thái quarantined vào dashboard có thể không ảnh hưởng đến API. **Biện pháp chặn cần được xác nhận tại data plane**, không chỉ ở hệ thống quản trị.

### 11.3. Độ mới và thứ tự sự kiện

Một event “healthy” cũ đến sau event “quarantined” mới có thể vô tình phục hồi quyền nếu xử lý sai thứ tự. Nguồn trạng thái nên có **version/epoch hoặc mốc hiệu lực**, kiểm tra nguồn phát và chống replay, xử lý idempotent khi event lặp lại. Nếu event bị mất, reconciliation với nguồn tin cậy cần phát hiện khác biệt.

| Loại dữ liệu | Biến đổi điển hình | Chiến lược độ mới |
|---|---|---|
| Artifact digest của release | Theo mỗi lần phát hành | Gắn immutable digest và release approval |
| Owner/role/service principal | Theo JML hoặc điều chỉnh quyền | Registry authoritative và event/update |
| Deployment namespace/config | Mỗi lần rollout/patch | Admission + kiểm tra drift |
| Runtime threat/quarantine | Có thể đổi rất nhanh | Event, introspection hoặc trạng thái đủ mới cho thao tác nhạy cảm |
| Token/chứng chỉ | Theo lifetime/rotation | Thời hạn hẹp, issuer/audience, kiểm tra/revocation |
| Resource scope/tenant | Theo nghiệp vụ | Lấy từ backend ở thời điểm quyết định |

Không có TTL phổ quát cho mọi loại posture. Cần thiết kế theo **SLA thu hồi và mức nhạy cảm** của hành động, rồi kiểm thử bằng token và instance thực.

## 12. Phản ứng khi posture không đạt hoặc không xác định

Không phải mọi workload không compliant đều đã bị xâm nhập. Nhưng **thiếu bằng chứng bắt buộc không thể tự được coi là đạt**.

| Trạng thái | Ý nghĩa | Hành vi tham chiếu |
|---|---|---|
| **Compliant / verified** | Có bằng chứng đủ mới, đạt policy và gắn đúng instance | Có thể allow nếu AuthN/AuthZ cũng đạt |
| **Noncompliant** | Một hoặc nhiều điều kiện rõ ràng không đạt | Chặn action nhạy cảm, áp dụng remediation có kiểm soát |
| **High risk / quarantined** | Có dấu hiệu mạnh hoặc quyết định cô lập theo sự cố | Chặn đường truy cập thuộc phạm vi; điều tra và thu hồi credential |
| **Unknown** | Không có đủ bằng chứng | Không tự allow dữ liệu nhạy cảm; theo chính sách có thể giới hạn chức năng |
| **Stale** | Bằng chứng từng hợp lệ nhưng quá thời hạn | Đánh giá lại hoặc fail closed với tác vụ cần freshness |
| **Indeterminate / policy service error** | Không thể đánh giá đáng tin | Hành động nhạy cảm fail closed; có cảnh báo và đường vận hành dự phòng đã phê duyệt |

### Khi nguồn posture mất kết nối

Với một API đọc dữ liệu ít nhạy cảm, có thể cho phép dùng **quyết định cache còn hạn và phạm vi nhỏ** nếu chính sách đã đánh giá và chấp nhận rủi ro. Với action như thay IAM policy, đọc secret production hoặc xuất lượng lớn dữ liệu, **fail closed** thường là hướng thiết kế phù hợp khi thiếu tín hiệu bắt buộc.

Đặc biệt, cần tránh “posture service lỗi thì đánh dấu mọi workload trusted để hệ thống chạy tiếp”. Hành vi này phá lớp bảo vệ đúng lúc hệ thống đang suy giảm.

### Khôi phục an toàn sau sự cố

Chỉ trả workload về trạng thái được phép khi:

1. Đã xác định nguyên nhân hoặc tình trạng rủi ro;
2. Image/config/instance mới đáp ứng chính sách;
3. Danh tính/credential cũ bị nghi lộ đã được xử lý;
4. Bằng chứng mới có nguồn và binding đáng tin;
5. Quyền được đánh giá lại, chỉ cấp đúng scope cần thiết;
6. Nhật ký/kiểm thử xác nhận luồng truy cập hợp lệ hoạt động và đường xấu bị chặn.

Không nên đặt trạng thái “healthy” thủ công trên dashboard rồi coi như đủ bằng chứng để mở quyền.

## 13. Rủi ro đặc biệt: chuỗi cung ứng, CI/CD và quyền triển khai

CI/CD là nơi **artifact và danh tính workload được sinh ra**, vì vậy chính nó cũng cần posture.

### Các đường rủi ro thường gặp

- Runner dùng chung lưu credential giữa các job không cùng mức tin cậy.
- Pipeline nhận code/PR không đáng tin nhưng có thể lấy token production.
- Job build và job deploy dùng cùng service account quyền admin.
- Artifact được duyệt nhưng tag bị thay mà không kiểm digest.
- Bí mật được đưa vào image hoặc log build.
- Chính sách admission có thể bị sửa bởi chính principal mà nó đang kiểm soát.
- Một job bị dừng nhưng vẫn còn refresh token hoặc secret dài hạn.

### Quyền tối thiểu theo từng giai đoạn

| Hoạt động | Nhu cầu quyền | Tránh cấp |
|---|---|---|
| Build/test | Đọc source, dependency, ghi artifact build | Quyền sửa IAM production |
| Sign/attest | Phát hành chứng cứ cho đúng build/release | Khóa ký dùng chung không kiểm soát |
| Deploy staging | Triển khai vào staging namespace/project | Quyền production |
| Deploy production | Triển khai release đã phê duyệt trong scope hẹp, có điều kiện | Admin toàn cluster/cloud |
| Runtime của ứng dụng | Chỉ gọi API, dữ liệu cần để làm nghiệp vụ | Credential deploy hoặc quản trị pipeline |
| Audit/monitoring | Đọc telemetry được ủy quyền | Quyền sửa/xóa toàn bộ log không kiểm soát |

Ví dụ pipeline deployment được phép tạo một workload **không đồng nghĩa** bản thân workload runtime nên kế thừa quyền deploy. Tách các principal và thời hạn credential giúp giảm phạm vi thiệt hại nếu app bị chiếm quyền.

## 14. Quan hệ với IdP, SSO, SCIM và danh tính con người

Các thành phần quen thuộc trong IAM vẫn liên quan, nhưng chức năng khác nhau:

- **IdP/SSO cho con người:** xác thực kỹ sư/owner, quản trị quyền duyệt release, tạo credential hoặc thao tác trên CI/CD. MFA và JIT bảo vệ những thao tác này.
- **Workload IdP/issuer:** cấp danh tính/credential cho service, runner hoặc instance theo bằng chứng phù hợp; không nhất thiết là cùng hệ thống IdP tương tác của con người.
- **SCIM/provisioning:** có thể dùng để quản lý principal/user/group tại ứng dụng tích hợp; không phải công cụ chuẩn để đo runtime posture hoặc tự quyết định quyền trên mỗi request.
- **RBAC/ABAC:** ràng buộc quyền của người quản lý và service principal; posture là một trong những điều kiện ABAC quan trọng.
- **PAM/privileged access:** áp dụng cho thao tác triển khai, vận hành, quyền admin của con người và các luồng service principal đặc quyền khi phù hợp.
- **Audit:** liên kết ai phê duyệt, workflow nào triển khai, artifact nào được chạy và workload instance nào truy cập dữ liệu.

Một quyết định an toàn thường phải truy được cả hai lớp trách nhiệm: **người hoặc nhóm đã ủy quyền phiên bản/quyền** và **workload instance đã thực hiện request**. Không nên biến danh tính người quản lý thành danh tính runtime của bot, vì khi người đó rời tổ chức, quyền tồn dư sẽ khó phát hiện.

## 15. Kiểm toán và phát hiện sai lệch posture

### Sự kiện cần ghi

| Nhóm | Sự kiện có giá trị |
|---|---|
| Release/build | Commit/build ID, artifact digest, provenance verification, policy result |
| Admission | Workload principal, namespace, environment, image digest, cấu hình và kết quả admit/deny |
| Identity issuance | Issuer, principal ID, audience, credential lifetime, auth policy; không ghi secret |
| Runtime posture | Status, nguồn tín hiệu, observed time, confidence/version, incident/quarantine |
| Authorization | Subject, instance, action, resource, tenant, policy version, allow/deny và reason code |
| JML/change | Owner đổi, principal retire, grant thu hồi, credential rotation, đích đã xác nhận |
| Incident | Ai quyết định cách ly/phục hồi, bằng chứng và mốc chặn request tại API |

### JSON audit minh họa

~~~json
{
  "timestamp": "2026-11-23T10:12:15Z",
  "event_type": "authorization_decision",
  "correlation_id": "req-a731",
  "principal_id": "svc-billing-reconcile",
  "workload_instance": "job-820",
  "artifact_digest_ref": "sha256:approved-release-digest-ref",
  "deployment_environment": "production",
  "posture_source": "workload-posture-service",
  "posture_version": 42,
  "posture_status": "quarantined",
  "posture_observed_at": "2026-11-23T10:11:50Z",
  "resource": "finance-api/invoices",
  "resource_scope": "tenant-A",
  "action": "invoice.read",
  "decision": "deny",
  "reason_code": "WORKLOAD_QUARANTINED",
  "policy_id": "finance.reconcile.read",
  "policy_version": 12
}
~~~

Đây là schema minh họa; digest tham chiếu không phải SHA-256 hợp lệ để dùng trực tiếp. **Không log access token, refresh token, private key, API key, toàn bộ biến môi trường hay dữ liệu khách hàng nguyên văn**. Bảo vệ tính toàn vẹn log và tách quyền vận hành workload khỏi quyền xóa audit.

### Phát hiện drift

Một hệ thống có thể so **desired posture** với **observed posture**:

~~~text
Desired:
  artifact = release đã phê duyệt
  namespace = finance-prod
  service principal = svc-billing-reconcile
  privileged = false
  tenant scope = tenant-A

Observed:
  artifact = release đã phê duyệt
  namespace = finance-prod
  service principal = svc-billing-reconcile
  privileged = true       <-- lệch cấu hình
  tenant scope = tenant-A

Outcome:
  Không coi workload đạt posture cho truy cập nhạy cảm.
  Tạo alert, xác định chủ sở hữu thay đổi, khắc phục cấu hình.
~~~

Drift phải được đánh giá trên **trạng thái áp dụng thực tế**, vì một manifest mong muốn có thể khác cấu hình runtime do mutating webhook, thao tác thủ công hoặc vấn đề triển khai.

## 16. Kiểm thử workload posture

Một bộ kiểm thử hữu ích nên cố tình tạo trường hợp **danh tính/credential hợp lệ nhưng posture sai**, và **posture tốt nhưng authorization sai**.

| ID | Kịch bản | Kết quả mong đợi |
|---|---|---|
| W1 | Workload đúng principal, image/release được duyệt, quyền đúng tenant | Allow nếu mọi điều kiện khác đạt |
| W2 | Artifact chưa được phê duyệt nhưng dùng tên service hợp lệ | Từ chối deploy hoặc action yêu cầu posture |
| W3 | Image được ký nhưng cấu hình runtime bật quyền privileged không được phép | Không đạt baseline, chặn/khắc phục theo policy |
| W4 | Workload trình token đúng issuer nhưng sai audience | Deny tại resource server |
| W5 | Workload đúng identity/posture nhưng gọi API tenant khác | Deny ở cấp tài nguyên |
| W6 | Service account chỉ read nhưng thử tạo IAM policy | Deny theo authorization |
| W7 | Runtime detector đánh dấu instance quarantined sau khi token được cấp | Chặn action nhạy cảm trong SLA đã đặt |
| W8 | Posture assertion hết TTL | Không tiếp tục coi compliant vô hạn |
| W9 | Sự kiện healthy cũ đến sau event quarantined mới | Không ghi đè trạng thái mới bằng event cũ |
| W10 | Posture service không khả dụng | Fail closed cho action yêu cầu tín hiệu bắt buộc |
| W11 | Principal bị retire nhưng còn secret/API key cũ | Không cấp credential mới; đường cũ được thu hồi theo SLA |
| W12 | Pipeline staging thử federation lấy quyền production | Deny theo audience/subject/environment policy |
| W13 | Artifact tag thay đổi nhưng digest không trùng release đã duyệt | Từ chối nếu policy yêu cầu digest cụ thể |
| W14 | Workload không có owner hoặc owner đã Leaver | Gắn cờ rà soát, thu hồi hoặc chuyển ownership có phê duyệt |
| W15 | Admission đã từ chối nhưng có đường chạy khác bỏ qua kiểm tra | Phải phát hiện/bịt đường bypass và kiểm thử lại |
| W16 | Runtime được khôi phục với credential/bằng chứng mới sau incident | Chỉ được cấp quyền trong scope đã duyệt, audit đầy đủ |

**W7, W11 phải được xác nhận ở điểm truy cập dữ liệu.** Chỉ nhìn thấy Pod bị xóa, principal bị disable hoặc event được gửi thành công chưa bảo đảm mọi token/secret cũ đều hết giá trị.

### Quy trình kiểm thử thu hồi có mốc thời gian

1. Ghi thời điểm quyết định quarantine/retire hoặc Mover có hiệu lực.
2. Ghi thời điểm issuer/IAM/admission/runtime đã nhận thay đổi.
3. Dùng workload/token kiểm thử có ủy quyền để gọi một action từng được phép.
4. Ghi thời điểm request cuối cùng còn được allow và thời điểm deny có hiệu lực.
5. Kiểm tra đường phụ: service principal kế thừa, secret, local credential, resource policy.
6. Đối soát log với desired state và xác nhận mọi đích quan trọng đã chặn.

## 17. Chỉ số đánh giá khả năng kiểm soát

| Chỉ số | Cách hiểu/đo | Tác dụng |
|---|---|---|
| **Workload inventory coverage** | Tỷ lệ workload/service principal có owner, environment, mục đích và lifecycle state | Phát hiện danh tính máy mồ côi |
| **Provenance verification coverage** | Tỷ lệ release thuộc phạm vi bắt buộc được xác minh artifact/provenance | Đo độ phủ kiểm soát trước deploy |
| **Admission policy coverage** | Tỷ lệ đường triển khai có kiểm tra cấu hình bắt buộc | Phát hiện đường bỏ qua kiểm soát |
| **Runtime posture freshness** | Độ tuổi bằng chứng tại lúc ra quyết định, p95/p99 và số lần quá TTL | Phát hiện telemetry chậm/stale |
| **Posture-to-enforcement latency** | Từ event rủi ro/quarantine tới lúc API chặn action nhạy cảm | Đo phản ứng data plane |
| **Credential revocation latency** | Từ retire/incident tới khi token/secret không thể dùng ở đích | Đo quyền tồn dư |
| **Desired–observed drift** | Số workload khác baseline đã duyệt, phân theo mức nhạy cảm | Phát hiện cấu hình vượt quyền |
| **Standing privilege footprint** | Principal máy có quyền cao thường trực, scope và owner | Giảm phạm vi tác động khi credential lộ |
| **Unknown/stale decision rate** | Tỷ lệ action phải đánh giá khi thiếu bằng chứng | Đánh giá tính sẵn sàng nguồn posture |
| **False posture deny rate** | Số deny được xác minh sai theo tổng điều tra | Cải thiện chất lượng policy và tín hiệu |
| **Orphaned credential count** | Key, token, service account không owner/không còn deployment hợp lệ | Tìm đường truy cập tồn dư |

Không nên đo thành công chỉ bằng “100% image có chữ ký”. Một hệ thống vẫn có thể thất bại nếu **chữ ký không được xác minh, cấu hình runtime có quyền quá rộng hoặc API không kiểm tra quyền hiện tại**.

## 18. Bài tập tình huống: một job có danh tính hợp lệ nhưng posture thay đổi

### Bối cảnh

Công ty có hệ thống Finance dùng một batch job **invoice-sync** để đọc hóa đơn tenant A qua API. Job được triển khai từ CI/CD với workload identity federation, lấy token ngắn hạn. Môi trường production yêu cầu image được phê duyệt, runner đúng nhóm, service principal riêng, quyền invoice.read trên tenant A và không chạy privileged.

Diễn biến:

- **08:00:** Release R1 được phê duyệt, digest D1, job chạy ở finance-prod với posture compliant.
- **09:00:** Một kỹ sư chuyển bộ phận (Mover). Kỹ sư này vẫn sở hữu một API key cũ của integration Invoice Legacy.
- **09:10:** Một pipeline staging cố lấy quyền production bằng token OIDC của runner staging.
- **09:15:** Có deploy mới dùng cùng service account invoice-sync, nhưng image digest D2 chưa có phê duyệt và security context bật privileged.
- **09:18:** Instance mới vẫn gọi finance-api với token của principal hợp lệ.
- **09:20:** Runtime detector phát hiện hành vi truy cập secret khác thường và đánh dấu instance quarantined.
- **09:22:** Access token phát hành trước 09:20 chưa hết hạn.
- **10:00:** Nhóm quyết định ngừng Invoice Legacy; cần thu hồi key cũ mà không ngắt job hợp lệ đang dùng identity riêng.

### Câu hỏi

1. Những yếu tố nào về identity, posture và authorization cần kiểm tra ở 09:10, 09:15 và 09:18?
2. Vì sao một token hợp lệ của invoice-sync không đủ để cho phép instance chạy image D2?
3. Khi runtime chuyển sang quarantined lúc 09:20, cách nào khiến request lúc 09:22 bị từ chối dù token còn hạn?
4. JML của kỹ sư và việc ngừng Invoice Legacy liên quan những credential/quyền nào? Cần tránh nhầm lẫn gì?
5. Thiết kế hai chỉ số và ba kiểm thử để chứng minh đường truy cập production đã được bảo vệ.

### Hướng giải tham khảo

**1. Xác minh theo thời điểm.** Lúc 09:10, federation kiểm tra issuer/audience/subject và ràng buộc runner staging với production trust policy; token staging không được đổi lấy quyền production. Lúc 09:15, admission phải xác minh digest D2 và security context, từ chối workload nếu không đạt. Lúc 09:18, PEP/PDP kiểm tra credential, principal, instance posture, action và tenant thực tại API; nếu D2 chưa phê duyệt hoặc privileged sai chính sách thì deny theo yêu cầu.

**2. Danh tính không bảo đảm posture.** Service account invoice-sync xác định principal; nó không xác minh image D2 hoặc môi trường chạy đang đáp ứng chuẩn. Workload instance có thể dùng cùng danh tính trong khi cấu hình đã bị đổi.

**3. Đánh giá lại.** Event quarantined được xác minh nguồn, mang version/epoch và được truyền đến PEP/PDP; cache cũ bị vô hiệu hoặc API kiểm tra trạng thái đủ mới. Thu hồi/giới hạn credential và kiểm tra quyền hiện hành theo kiến trúc. Nếu API chỉ kiểm chữ ký JWT offline, cần thiết kế lại khả năng thu hồi và chặn action nhạy cảm.

**4. Vòng đời.** Kỹ sư Mover phải mất quyền quản trị không còn cần và API key cá nhân không còn ủy quyền. Invoice Legacy được retire thì thu hồi riêng principal/key/role của integration đó. **Không thu hồi nhầm** principal của job invoice-sync vẫn còn nghiệp vụ; đồng thời không giữ key Legacy chỉ vì sợ ngắt job khác. Cần đối chiếu owner, đường sử dụng credential và dependency trước khi thay đổi.

**5. Kiểm thử và chỉ số.** Test token staging không nhận quyền production; D2 bị từ chối admission dù service account đúng; sau quarantine dùng token cũ gọi finance-api và phải deny; test cross-tenant. Chỉ số: thời gian từ posture quarantine đến API deny, và số credential không owner/quá hạn còn truy cập được; có thể thêm coverage admission/provenance.

## 19. Checklist triển khai

- [ ] Có danh sách workload/service principal với **owner, môi trường, mục đích và trạng thái vòng đời**.
- [ ] Đã phân biệt identity, artifact provenance, workload attestation, deployment compliance và runtime posture.
- [ ] Bằng chứng posture có **nguồn đáng tin, phiên bản, thời điểm, hạn sử dụng và liên kết instance**.
- [ ] Kiểm tra artifact/release, digest và chính sách chuỗi cung ứng trước triển khai theo mức rủi ro.
- [ ] Admission/hardening ngăn đặc quyền và cấu hình vượt nhu cầu, có cách phát hiện bypass/drift.
- [ ] Mỗi workload dùng principal riêng, token/chứng chỉ có scope, audience và lifetime phù hợp.
- [ ] CI/CD build, deploy production và ứng dụng runtime không dùng chung quyền admin.
- [ ] API/PDP kiểm tra **principal + posture + action + resource + tenant**, deny mặc định khi thiếu điều kiện bắt buộc.
- [ ] Có đường đánh giá lại/thu hồi khi instance bị quarantine, quyền đổi, service retire hoặc credential bị lộ.
- [ ] Hiểu giới hạn của JWT đã phát hành và SCIM/provisioning bất đồng bộ.
- [ ] Workload và owner được rà soát theo JML; principal/secret ngừng sử dụng có xác nhận thu hồi.
- [ ] Event/cached posture xử lý stale, duplicate, out-of-order, service outage và reconciliation.
- [ ] Audit đủ liên kết người phê duyệt, pipeline, artifact, instance và quyết định API mà không ghi secret.
- [ ] Kiểm thử đúng token nhưng sai posture, đúng posture nhưng sai quyền, quarantine giữa phiên và cross-tenant.
- [ ] Đo được posture-to-enforcement latency, credential revocation latency, drift và principal mồ côi.

## 20. Thuật ngữ và tài liệu đọc tiếp

| Thuật ngữ | Ý nghĩa |
|---|---|
| **Workload posture** | Bằng chứng về nguồn gốc, cấu hình, môi trường và rủi ro của workload ở thời điểm quyết định |
| **Workload identity** | Danh tính đại diện cho service/job/instance khi xác thực |
| **Workload attestation** | Xác minh một số thuộc tính của workload/môi trường theo phương pháp tin cậy |
| **Artifact provenance** | Thông tin chứng minh nguồn và quy trình tạo artifact |
| **Image digest/signature** | Tham chiếu nội dung bất biến / bằng chứng tính toàn vẹn và nguồn theo mô hình khóa |
| **Admission policy** | Quy tắc đánh giá trước khi workload được chấp nhận chạy |
| **Runtime posture** | Tình trạng thực tế và tín hiệu rủi ro khi workload đang hoạt động |
| **SPIFFE ID / SVID** | Các khái niệm về định danh/bằng chứng danh tính workload trong hệ sinh thái SPIFFE |
| **Federation** | Tin cậy có điều kiện giữa nguồn phát hành danh tính và dịch vụ cấp credential đích |
| **PEP / PDP** | Điểm thực thi truy cập / thành phần đánh giá chính sách |
| **RBAC / ABAC** | Phân quyền theo vai trò / thuộc tính và ngữ cảnh |
| **JML** | Joiner–Mover–Leaver, áp dụng trực tiếp cho người dùng và theo phép tương tự cho vòng đời workload |
| **Posture freshness** | Độ mới và thời hạn chấp nhận của bằng chứng posture |
| **Residual access** | Quyền, token, secret hoặc phiên còn được sử dụng dù không còn ủy quyền |
| **Quarantine** | Giới hạn/cô lập workload khi có tín hiệu rủi ro theo quy trình |

### Tài liệu tham khảo khái niệm

- **NIST SP 800-207 — Zero Trust Architecture:** mô hình truy cập dựa trên danh tính, ngữ cảnh và quyết định chính sách.
- **NIST SP 800-207A — A Zero Trust Architecture Model for Access Control in Cloud-Native Applications in Multi-Cloud Environments:** định hướng chi tiết hơn về kiểm soát truy cập trong môi trường ứng dụng cloud-native.
- **NIST SP 800-190 — Application Container Security Guide:** các rủi ro và kiểm soát của container, image, runtime và orchestration.
- **NIST SP 800-218 — Secure Software Development Framework:** thực hành phát triển phần mềm an toàn và bảo vệ chuỗi cung ứng.
- **NIST SP 800-53 — Security and Privacy Controls:** nhóm kiểm soát truy cập, cấu hình, định danh, kiểm toán và giám sát.
- **SPIFFE/SPIRE:** tham khảo mô hình danh tính workload, cấp chứng thực và attestation.
- **SLSA và Sigstore:** tham khảo bằng chứng provenance, xác minh artifact và các điều kiện tin cậy tương ứng.
- **Kubernetes Security và Pod Security Standards:** tham khảo giới hạn đặc quyền và cấu hình runtime theo môi trường Kubernetes.
- **RFC 7643/7644 — SCIM:** đồng bộ danh tính và nhóm, hữu ích khi tích hợp lifecycle vào ứng dụng nhưng không thay runtime posture.

**Điểm cần nhớ:** Workload posture giúp trả lời **“workload đang gọi API có nguồn gốc, cấu hình, môi trường và trạng thái đủ tin cậy cho hành động này ở thời điểm này không?”**. Câu trả lời chỉ có ý nghĩa khi bằng chứng được xác minh, gắn đúng instance, có độ mới phù hợp và **được dùng cùng danh tính và quyền trên tài nguyên thật**. Trong Zero Trust IAM, posture phải được quản lý suốt vòng đời workload, phản ứng với thay đổi JML/incident và chứng minh được rằng **credential hoặc quyền tồn dư không tiếp tục mở đường truy cập trái phép**.
