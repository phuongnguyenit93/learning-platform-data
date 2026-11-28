# Theo dõi thay đổi cấu hình firewall

**Firewall configuration change monitoring** là quá trình liên tục thu thập, chuẩn hóa, đối chiếu, đánh giá rủi ro và kiểm chứng những thay đổi ảnh hưởng đến **chính sách cho phép/từ chối lưu lượng**, bao gồm rule, object/group, zone, NAT, interface, route, logging, policy attachment và các thành phần bảo mật liên quan. Mục tiêu không đơn thuần là ghi nhận “có người đã sửa một rule”, mà là trả lời được: **ai yêu cầu, ai thực hiện, thay đổi điều gì, tại đâu, vì sao, cấu hình nào thực sự có hiệu lực, luồng nào bị ảnh hưởng, việc phê duyệt có hợp lệ không và cần khôi phục như thế nào?**

Trong module **SECURITY_NETWORK_SECURITY**, bài thuộc chương **Giám sát mạng và telemetry** và kết nối những kiến thức về **phân đoạn mạng, firewall, IDS/IPS, VPN, DNS security, cloud networking, Kubernetes, kiểm soát egress và mô hình hóa mối đe dọa**. Firewall vừa là điểm thực thi chính sách mạng vừa là một **hệ thống điều khiển có thể bị cấu hình sai, thay đổi ngoài quy trình hoặc bị lạm dụng quyền**. Một rule mở mới, một rule bị disable, một address group được mở rộng hoặc một thay đổi thứ tự ưu tiên có thể tác động nhiều dịch vụ dù tên rule không đổi.

> **Nguyên tắc thực hành:** ví dụ trong bài sử dụng địa chỉ tài liệu, tên đối tượng, sự kiện và policy giả lập. Không chạy lệnh thay đổi firewall production, ngắt phiên quản trị, thay route, tắt logging/IPS hoặc làm gián đoạn luồng người dùng để kiểm chứng. Ưu tiên **read-only API, cấu hình mẫu, bản sao log đã khử nhạy cảm, sandbox và các bài test mô phỏng**; thay đổi thật phải có quyền, phê duyệt, kế hoạch rollback và khung giờ phù hợp.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Phân biệt **cấu hình mong muốn (desired state), cấu hình ứng viên/chờ commit (candidate), cấu hình đang chạy (running/effective) và hành vi data plane**.
2. Nhận diện các thay đổi nguy hiểm: mở rộng **source/destination, any-any, service port, zone, NAT, route, security group, object group, default policy, log settings và rule priority**.
3. Thiết kế nguồn thu thập từ **firewall audit/syslog, management controller, API, IaC/GitOps, cloud audit, Kubernetes events, flow logs, IDS/IPS và SIEM**.
4. Phân biệt **raw text diff** với **semantic diff** và phân tích tác động trên tập traffic được phép/từ chối.
5. Xây bản ghi audit có **actor, reason, ticket, before/after, scope, approval, commit result, device/revision và timestamp**.
6. Đánh giá rủi ro thay đổi theo **độ rộng rule, sensitivity của tài sản, trust boundary, exposure, tính khẩn cấp, lịch sử và mức chắc chắn của evidence**.
7. Xây detection cho **thay đổi trái phép, ngoài giờ, tắt logging, nâng quyền, drift, rule shadowing và chênh lệch cấu hình–thực thi**.
8. Tương quan log quản trị với **flow, session, NAT, route, IDS/IPS, ứng dụng và hiệu năng** để kiểm chứng tác động.
9. Xây playbook **triage, containment, safe rollback, forensic preservation, peer review và hậu kiểm**.
10. Áp dụng nguyên tắc tương tự cho **cloud security group/NACL, WAF, egress gateway, Kubernetes NetworkPolicy** nhưng không đánh đồng semantics của chúng.
11. Thiết kế **lab không tác động hạ tầng thật** bằng các bản policy/sự kiện giả lập, bộ test positive/negative và dashboard/KPI.
12. Mô tả ranh giới của công cụ: **một log commit thành công không bảo đảm mọi packet đã đi theo policy**, và **không có traffic bị deny không chứng minh đã mở rule trái phép**.

## 2. Firewall change là gì và thay đổi được tính ở tầng nào?

### 2.1. Những lớp trạng thái không nên nhập làm một

Một hệ thống firewall thường có chu trình:

~~~mermaid
flowchart LR
  T["Business request / ticket"] --> D["Desired policy\nIaC / change set"]
  D --> C["Candidate config\nreviewed diff"]
  C --> A["Commit / deploy\nmanagement plane"]
  A --> R["Running/effective config\non target devices"]
  R --> P["Data plane\nactual packet / session behavior"]
  T -. "Approval and owner" .-> A
  P -. "Flow/IDS/app telemetry" .-> V["Verification + evidence"]
  R -. "Snapshot/hash/effective policy" .-> V
  V -. "Drift/incident feedback" .-> D
~~~

Đây là **mô hình khái niệm**. Một firewall vật lý có candidate/running config với commit riêng; một firewall Linux có ruleset nạp vào kernel; một cloud security group có API trạng thái mong muốn và cơ chế phân phối rule; một SaaS WAF có version/activation riêng. Không được giả định tất cả thiết bị hỗ trợ cùng một lệnh **commit**, rollback hoặc trạng thái trung gian.

Phân biệt:

| Thuật ngữ | Câu hỏi | Ví dụ evidence |
| --- | --- | --- |
| **Request/intent** | Ai muốn mở đường và vì sao? | Change ticket, application dependency |
| **Desired state** | Source of truth muốn cấu hình nào? | Git revision, IaC plan |
| **Candidate** | Thay đổi gì được gửi để review? | Structured diff, policy preview |
| **Applied/running** | Thiết bị/controller đã nhận gì? | Config version, API readback |
| **Distributed/effective** | Các nodes/HA members thực sự có rules nào? | Per-device state, sync status |
| **Observed behavior** | Traffic hợp lệ/bị cấm có kết quả đúng không? | Flow/connection tests, app status |
| **Authorization** | Actor có quyền và approval hợp lệ không? | IAM/RBAC, ticket signatures, privileged session logs |

Một audit event **rule_update_requested** khác **rule_update_committed**; một commit thành công khác **rule installed across all HA peers**; và rule đã cài có thể không được traffic match vì route, NAT, earlier rule hoặc interface binding.

### 2.2. Những thay đổi không chỉ là thêm/xóa rule

Firewall policy có thể thay đổi khi:

- **Rule:** thêm, sửa, xóa, disable/enable, copy hoặc reorder.
- **Source/destination:** CIDR, address group, dynamic objects, identity labels.
- **Service:** TCP/UDP ports, application ID, protocol inspectors.
- **Action:** allow, deny, reject, log, inspect hoặc bypass security profile.
- **Zone/interface:** network segment, VPN interface, VRF/virtual context, security domain.
- **Schedule:** thời gian rule hoạt động, exception expiration.
- **NAT/PAT:** source/destination translation, SNAT pools, published service.
- **Routing:** default route, policy-based route, next hop, peering/VPN tunnel path, egress gateway.
- **Inspection:** IDS/IPS profile, TLS inspection, WAF ruleset, anti-malware/decryption bypass.
- **Logging/telemetry:** log-at-start/end, log sink, exporter, event categories.
- **Identity/control:** admin role, API token, authentication method, MFA, management ACL.
- **HA/cluster:** policy sync, failover, active/standby divergence.
- **Cloud security:** SG/NACL association, cloud firewall policy attachment, WAF Web ACL association, Kubernetes NetworkPolicy selection.

**Thay đổi gián tiếp** rất quan trọng: rule có thể vẫn hiển thị nguyên vẹn nhưng address group mà nó tham chiếu vừa được thêm một subnet; hoặc một Service đổi IP khiến allowlist cùng tên trỏ sang backend khác.

### 2.3. Một rule đơn lẻ có thể có phạm vi rất khác nhau

~~~text
Change A:
  source = app-frontend subnet
  destination = orders-api private IP
  service = TCP/8443
  action = allow
  expires = after approved migration

Change B:
  source = any
  destination = production database subnet
  service = any
  action = allow
  expires = none
~~~

Hai changes đều là “allow rule”, nhưng **Change B** có bề mặt truy cập lớn hơn rõ rệt. Tuy nhiên không thể xác định độ nghiêm trọng hoàn toàn từ rule text: cần biết **vị trí rule, zone, route reachability, NAT, object expansion, default rule và policy attachment**.

### 2.4. Cloud security rules không cùng semantics với perimeter firewall

| Công nghệ | Mô hình phổ biến | Lưu ý khi monitor |
| --- | --- | --- |
| **Stateful network firewall** | Sessions, policy order/first match tùy vendor | Rule position, object references, session tables |
| **Stateless ACL/NACL** | Rules theo thứ tự/priority, inbound/outbound riêng | Return traffic/ephemeral ports, deny precedence |
| **Cloud security group** | Stateful allow rules, thường rules được cộng gộp theo resource | Attachment, effective ingress/egress, default/outbound |
| **Cloud network firewall** | Rule sets/policy associations, priority/inspection | Routing through enforcement endpoint |
| **WAF** | HTTP request context, managed/custom rules | Rule version, false positives, origin bypass |
| **Kubernetes NetworkPolicy** | Additive allowlist cho Pods và directions | CNI enforcement, selectors/labels, no standard ordered deny |
| **Service mesh AuthZ** | Workload identity/L7 decisions tại proxy/waypoint | Traffic bypass, protocol classification |

Không áp một thuật toán “first match wins” cho **mọi loại firewall**, và không suy WAF bảo vệ kết nối trực tiếp tới origin nếu traffic không đi qua WAF.

## 3. Vì sao phải theo dõi thay đổi thay vì chỉ giám sát traffic?

### 3.1. Các nguy cơ từ thay đổi cấu hình

- **Misconfiguration:** sai IP/port, thiếu scope, đổi direction.
- **Over-permission:** any-any, dải IP rộng, service group mở thêm port.
- **Shadowed/unused rules:** rule mới bị che bởi rule khác hoặc không còn được dùng, gây hiểu nhầm.
- **Unauthorized change:** thao tác không có ticket hoặc không nằm trong quyền được phê duyệt.
- **Malicious manipulation:** privileged principal cố tắt logging/IPS hoặc mở đường vào tài sản.
- **Drift:** thay đổi trực tiếp trên thiết bị không trở lại Git/source of truth.
- **Asymmetric deployment:** policy chạy trên member A nhưng chưa đồng bộ member B.
- **Route bypass:** một NAT/route thay đổi khiến traffic đi ngoài firewall/WAF/egress gateway.
- **Availability regressions:** deny nhầm DNS, identity provider, database hoặc health checks.

### 3.2. Vì sao flow logs một mình chưa đủ?

Một rule allow quá rộng có thể được thêm lúc 03:00, nhưng không có kết nối nào đi qua nó trước 05:00. **Flow monitoring không phát hiện được rủi ro cấu hình chưa được sử dụng** nếu chỉ báo động khi traffic xuất hiện. Ngược lại, một spike traffic có thể là hành vi hợp lệ không do firewall change.

Các câu hỏi khác nhau:

| Công cụ | Trả lời |
| --- | --- |
| **Config/audit monitoring** | Ai đổi policy, trước/sau là gì? |
| **Drift/compliance checking** | Cấu hình chạy có khớp baseline/desired state? |
| **Topology/path analysis** | Rule có làm đường đến tài sản trở nên reachable? |
| **Flow/IDS/IPS telemetry** | Traffic nào thực đi qua, allow/deny hoặc cảnh báo gì? |
| **App SLO/health** | Ứng dụng có bị ảnh hưởng không? |
| **Incident forensics** | Có dữ liệu/thao tác trái quyền nào xảy ra không? |

Một thiết kế tốt **kết hợp các nguồn**, tránh kết luận chỉ từ một audit event hay từ một chỉ số bytes.

### 3.3. Sự kiện thay đổi và kết quả data plane có thể lệch nhau

Ví dụ:

~~~text
09:00 Change ticket: allow frontend -> orders TCP/8443 approved
09:05 Controller push: success
09:06 Firewall peer A: policy revision 42
09:06 Firewall peer B: policy revision 41
09:07 Health test on path via A: success
09:07 Health test on path via B: denied/timeout
~~~

Hệ thống chỉ ghi “push succeeded” sẽ **bỏ lỡ HA divergence**. Cần **per-target readback, sync status, app/flow tests**, và có thể rollback/staged deployment. Với cloud-managed policy, API readback cũng chưa chứng minh propagation hoặc route attachment đã sẵn sàng; quan sát theo SLA được nhà cung cấp hỗ trợ và test đường thực.

## 4. Xây nguồn dữ liệu tin cậy

### 4.1. Ma trận nguồn telemetry

| Nguồn | Có thể ghi nhận | Giới hạn |
| --- | --- | --- |
| **Firewall management audit** | Login, actor, command/API call, commit/deploy | Không chứng minh data plane đã áp |
| **Full configuration snapshot** | Running ruleset/objects, order, policy version | Có thể chứa credentials/secret references |
| **Git/IaC plan and apply** | Desired diff, approvals, code review, run IDs | Không thấy hotfix ngoài pipeline nếu không kiểm drift |
| **Privileged access/PAM** | Ai mở session quản trị, thời gian, break-glass | Session log không luôn cho biết semantic rule impact |
| **Cloud control-plane audit** | SG/NACL/firewall/WAF policy API mutations, actor | Eventual consistency/attachments phải kiểm riêng |
| **Kubernetes API audit** | NetworkPolicy/labels/namespace mutations | CNI enforcement không tự được chứng minh |
| **Firewall syslog** | Config change alarms, commits, HA/sync/errors | Có thể thiếu before/after chi tiết |
| **Flow logs/NetFlow/IPFIX** | Tuples, bytes, allow/deny theo collector | Không tự chỉ ra ticket/actor; có sampling/NAT |
| **IDS/IPS/WAF logs** | Threat detections, signatures, action | Không phải mọi traffic đều inspect |
| **Routing/NAT/ARP/neighbor telemetry** | Reachability, translation, path changes | Phải đặt trong context vendor/network |
| **Device health/SNMP/streaming telemetry** | CPU, memory, sessions, sync, exporters | Không cho biết quyền rule nếu thiếu config |
| **App monitoring/probes** | DNS/auth/API latency, SLO, connectivity outcomes | Không xác định rule cụ thể nếu chưa correlate |
| **Change system/CMDB** | Business owner, risk, approval, asset criticality | Có thể stale hoặc điền không đúng |

Không thu thập credentials hoặc raw device private keys vào SIEM. **Snapshot bảo mật** phải có RBAC, mã hóa, kiểm soát retention và cơ chế diff an toàn; nhiều config backup chứa **local user hashes, shared secrets, VPN keys, SNMP communities hoặc API tokens** nếu không xử lý.

### 4.2. Management channel phải xác thực

Thu thập phải sử dụng **đường quản trị được duyệt**: API có TLS server validation, SSH với host key được kiểm tra, cloud role với least privilege hoặc telemetry agent theo nền tảng. Cần:

- Service account đọc cấu hình **read-only** khi được hỗ trợ.
- Credential được lưu trong secret manager; không hardcode vào cron/logs.
- Firewall chỉ chấp nhận management connections từ đúng management network.
- Tách **collector identity** khỏi account có quyền thay đổi rule.
- Monitoring collector health và tốc độ nhập dữ liệu.
- Kiểm tra certificate/host key rotation, clock sync và network segmentation.

Nếu một nguồn không cung cấp before/after, hãy **kết hợp event với một snapshot đã xác minh**, không tự tạo “old config” bằng cách suy đoán.

### 4.3. Bốn thời điểm quan trọng trong một event

Một thay đổi có thể được:

1. **Requested** tại thời điểm ticket.
2. **Executed** tại thời điểm admin/API thao tác.
3. **Committed/distributed** khi target nhận config.
4. **Observed** khi SIEM nhận event hoặc khi traffic test chạy.

Nên lưu **event_time, collector_receive_time, device_time, commit_time/activation_time**, timezone và độ tin cậy của nguồn. Đồng bộ thời gian bằng NTP hoặc cơ chế đồng bộ được duyệt, tránh kết luận ticket được tạo “sau” thay đổi chỉ vì hai nguồn lệch clock.

### 4.4. Kiến trúc pipeline tham khảo

~~~mermaid
flowchart TB
  G["Git / IaC / ticket approval"] --> N["Normalize change events"]
  F["Firewall audit/API/config backup"] --> N
  C["Cloud/Kubernetes control-plane audit"] --> N
  N --> DIFF["Semantic diff + object expansion\nrisk/context enrichment"]
  DIFF --> SIEM["SIEM rules + correlation"]
  B["CMDB/asset sensitivity,\nowner, change windows"] --> DIFF
  DP["Flow/IDS/IPS/NAT/DNS/app health"] --> SIEM
  SIEM --> TRIAGE["Triage / peer review\nincident or planned change"]
  TRIAGE --> FB["Validated baseline / rollback\nand detection tuning"]
  FB -. "Feedback" .-> G
~~~

**Pipeline là logic kiến trúc**, không phải yêu cầu mọi traffic/config đi qua một SIEM. Các nguồn có chi phí và hạn chế khác nhau; cần ghi rõ những thiết bị/virtual systems/cloud accounts nằm ngoài coverage.

### 4.5. Mục tiêu toàn vẹn và không chối bỏ

Giữ:

- Event ID duy nhất hoặc vendor sequence ID.
- Thiết bị/tenant/account ID ổn định, policy context/VDOM/VRF/VPC.
- Config revision/hash và trước/sau (nếu được phép).
- Actor identity có kiểm chứng và source auth mechanism.
- Ticket/approval/commit run ID.
- Thiết bị đích/HA members, kết quả áp dụng.
- Dấu thời gian UTC và ingestion timestamps.
- Immutable hoặc tamper-evident audit store phù hợp quy định.

Không dùng **IP đăng nhập** làm danh tính admin duy nhất, vì NAT, bastion/PAM hoặc shared jump host có thể khiến nhiều người có cùng source IP.

## 5. Chuẩn hóa bản ghi thay đổi firewall

### 5.1. Một event có ích cần nhiều hơn “rule modified”

Ví dụ một event **giả lập** ở schema trung lập, không phải raw log của nhà sản xuất:

~~~json
{
  "event_id": "fwchange-lab-0007",
  "event_time": "2026-11-28T03:20:00Z",
  "ingest_time": "2026-11-28T03:20:02Z",
  "event_source": "synthetic-firewall-manager",
  "environment": "production",
  "device_id": "fw-east-01",
  "ha_cluster": "edge-fw-east",
  "policy_context": "corp-prod-vdom",
  "actor": {
    "principal": "ops-user-17",
    "authentication": "sso-mfa",
    "source": "pam-session-ref-111",
    "role": "firewall-change-operator"
  },
  "change": {
    "operation": "rule_update",
    "rule_id": "rule-prod-db-001",
    "before_revision": "r41",
    "after_revision": "r42",
    "before": {
      "source": ["10.20.10.0/24"],
      "destination": ["10.30.5.0/24"],
      "service": ["tcp/5432"],
      "action": "allow",
      "enabled": true,
      "logging": true
    },
    "after": {
      "source": ["0.0.0.0/0"],
      "destination": ["10.30.5.0/24"],
      "service": ["tcp/5432"],
      "action": "allow",
      "enabled": true,
      "logging": true
    }
  },
  "approval": {
    "ticket": null,
    "approved_by": null,
    "emergency": false
  },
  "deployment": {
    "commit_status": "success",
    "effective_verified": false,
    "ha_members_synced": false
  },
  "synthetic": true
}
~~~

Event này cho thấy **source CIDR mở từ một subnet sang mọi IPv4** và chưa tìm được approval tương ứng. Có thể ưu tiên điều tra cao, nhưng **effective_verified=false** nghĩa là chưa có chứng cứ chắc chắn rule hoạt động trên toàn traffic path. Không mặc định thêm “đã bị tấn công” hoặc “đã mở Internet→database” khi chưa biết **zone, NAT, route, rule order, attachment và external exposure**.

### 5.2. Các trường nên chuẩn hóa

| Nhóm | Trường | Mục đích |
| --- | --- | --- |
| **Identity** | event_id, device_id, tenant/account, environment, policy_context | Quy nguồn và tránh trộn contexts |
| **Time** | event_time, ingest_time, commit_time, timezone | Tương quan, thứ tự, đo lag |
| **Actor** | principal, role, auth_method, PAM/session, source IP | Gắn người/quyền thay đổi |
| **Change** | operation, object_type/id, field, before/after | Dựng semantic diff |
| **Policy** | source/dest, port/protocol, app, zone, action, enabled, log, schedule | Đánh giá reachability và detection |
| **NAT/route** | pre/post-NAT tuples, translation, next hop, interface | Kiểm chứng traffic path |
| **Review** | ticket, owner, requested_by, approved_by, window, reason | Phân biệt authorized vs out-of-process |
| **Deployment** | revision, hash, targeted nodes, success/failure, HA sync | Kiểm tra applied/effective |
| **Evidence** | source event refs, snapshot refs, synthetic probe refs | Traceability, không cần raw secrets |
| **Classification** | data sensitivity, trust boundary, blast radius, confidence | Ưu tiên xử lý |

Không cố ép mọi vendor có **cùng những fields**: khi không có approval ID hoặc rule UUID, ghi **unknown/not_available** thay vì điền giả. Phân biệt **missing field** với **empty value có ý nghĩa**.

### 5.3. Rule identity phải ổn định

Không dựa vào **rule number/position** làm định danh bất biến vì reorder/insert có thể thay số thứ tự. Ưu tiên:

1. Vendor-native immutable rule ID/object UUID nếu có.
2. Policy context + stable object reference + revision.
3. Snapshot diff matching khi thiếu immutable ID.
4. Rule name kết hợp scope, nhưng **name có thể đổi/trùng**.
5. Cảnh báo mức chắc chắn thấp khi phép ghép dựa heuristic.

Một rule có thể bị delete rồi recreate cùng tên nhưng khác ID, semantics và priority. Monitoring cần ghi sự kiện **remove/add**, không chỉ “vẫn còn tên giống vậy”.

### 5.4. Cấu hình có dữ liệu nhạy cảm

Một full firewall backup có thể chứa **VPN pre-shared secrets, local user credential hashes, certificates/private keys, SNMP communities, API tokens, tunnel credentials hoặc internal routing topology**. Vì thế:

- Diff tool làm việc với **sanitized config** ở chỗ có thể.
- Bản raw được giữ tại evidence/config vault với **mã hóa và RBAC**.
- SIEM chỉ nhận metadata, field-level diff đã loại secrets hoặc opaque references.
- Không đẩy toàn bộ config vào external LLM/ticket/chat/CI log không được phép.
- Snapshot hash nên được tính trên canonicalized content phù hợp; hash không thay bảo vệ bản raw.
- Quy trình forensic có quyền lấy full config nếu thật sự cần và được phê duyệt.

**Theo dõi cấu hình bảo mật không được vô tình trở thành nguồn làm lộ credential quản trị.**

## 6. Semantic diff: thay đổi nhỏ về văn bản có thể thay lớn về quyền

### 6.1. Vì sao diff dòng không đủ?

Ví dụ source of truth:

~~~yaml
# YAML KHÁI NIỆM: không phải cú pháp nạp vào một hãng firewall.
objects:
  app_frontend:
    members:
      - 10.20.10.0/24
  sensitive_db:
    members:
      - 10.30.5.0/24

rules:
  - id: permit-app-db
    position: 120
    source_object: app_frontend
    destination_object: sensitive_db
    services:
      - tcp/5432
    action: allow
    enabled: true
    log: true
~~~

Rule text giữ nguyên nhưng object **app_frontend** được sửa thành:

~~~yaml
objects:
  app_frontend:
    members:
      - 10.20.10.0/24
      - 10.0.0.0/8
~~~

Nếu chỉ so rule, sẽ báo **“no rule changes”**. Semantic diff phải **resolve object references** và đánh giá tập source có được mở rộng hay không, đồng thời xem zone/routing thực tế. Ngay cả khi dải 10.0.0.0/8 nằm sau network boundary không reachable, đây vẫn là thay đổi phạm vi cho phép cần review.

### 6.2. Các loại diff

| Diff | Ví dụ | Tác động cần kiểm chứng |
| --- | --- | --- |
| **Syntactic** | Chuyển thứ tự YAML keys, đổi comment | Có thể không đổi hành vi |
| **Structural** | Thêm object, đổi group, move rule | Cần resolve references/order |
| **Semantic** | Allowed sources tăng, log disable | Thay đổi quyền/visibility |
| **Topological** | NAT/route/zone đổi | Đường packet thay, rule mới được match |
| **Temporal** | Schedule kéo dài, exception không hết hạn | Exposure tăng theo thời gian |
| **Effective** | Config applied một phần HA members | Behavior khác giữa traffic paths |
| **Operational** | Flows/deny counters thay sau deploy | Bằng chứng tác động thực |

Một diff comment có thể không cần alert high severity, nhưng diff **tắt logging trên Internet-exposed rule** có thể ưu tiên cao dù không đổi allow/deny.

### 6.3. Phân tích tập traffic trước/sau

Định nghĩa khái niệm:

\[
\begin{aligned}
A_{\text{old}} &= \{\text{traffic tuples được chính sách cũ cho phép}\},\\
A_{\text{new}} &= \{\text{traffic tuples được chính sách mới cho phép}\},\\
\text{NewlyAllowed} &= A_{\text{new}}\setminus A_{\text{old}},\\
\text{NewlyDenied} &= A_{\text{old}}\setminus A_{\text{new}}.
\end{aligned}
\]

Đây là **mô hình logic**, không phải phép tính đơn giản chỉ dựa vào CIDR/port. Để tính hiệu quả phải xét **policy order, NAT, app-ID, zones, routing, attachments, stateful sessions, schedules và vendor semantics**. Với Kubernetes NetworkPolicy, nhiều policies cộng gộp nên một rule deny riêng không có semantics giống firewall ordered ACL.

**NewlyAllowed ≠ traffic thực sự đã xảy ra.** Nó cho thấy **đường có khả năng được phép** theo mô hình, sau đó cần kiểm chứng routing/enforcement/data plane.

### 6.4. Phân tích shadowing, redundancy và order

Ví dụ trên firewall **ordered first-match** giả lập:

~~~text
100  deny  src=untrusted  dst=prod-db  tcp/5432
110  allow src=any        dst=prod-db  tcp/5432
120  allow src=frontend   dst=prod-db  tcp/5432
~~~

Trong điều kiện khớp chính xác và cùng context, rule 110 có thể làm rule 120 **không còn tác dụng riêng** (shadowed/redundant). Nhưng:

- Thứ tự/semantics có thể khác với **cloud SG** hoặc các policy system không ordered.
- Rule có thể có **application/user identity, schedule hoặc zone** không hiện trong ví dụ.
- Một deny ở phía khác (SG/NACL/route) có thể vẫn chặn actual flow.
- Counters 0 không chứng minh rule an toàn; nó có thể chưa từng được thử hoặc flow bị chặn ở chặng trước.

**Không tự xóa shadowed rules** trên production khi chưa hiểu mục đích và dependencies. Theo dõi **redundancy, expiry và source owner** để xử lý theo change process.

### 6.5. Các biến đổi nguy hiểm trong semantic diff

- Từ **CIDR hẹp → CIDR rộng**; ví dụ /32 sang /16 hoặc any.
- Từ **port cụ thể → any port**, hoặc thêm management ports.
- Từ **deny/reject → allow**, hoặc disable deny rule.
- Chuyển rule lên vị trí ưu tiên hơn trong ordered policy.
- Đổi **zone/interface** sang Internet-facing hoặc partner-facing.
- Mở schedule từ 1 giờ sang **always on**.
- Xóa **log/IPS/WAF/TLS inspection** ở luồng nhạy cảm.
- Đổi **NAT/publication** khiến backend private reachable từ biên ngoài.
- Đổi **dynamic address group membership** làm mở đường mới.
- Chuyển **policy attachment** sang resource/VM/namespace khác.
- Đổi cloud **security group association** của database/LoadBalancer.
- Bật egress trực tiếp thay vì qua approved gateway.

Các biến đổi này nên có **higher risk score** theo asset/business context, không tự động coi là tấn công thành công.

### 6.6. Giảm noise do canonicalization

Diff tool nên:

1. Chuẩn hóa **IP/CIDR notation** và IPv4/IPv6, nhưng không làm mất sự khác biệt address families.
2. Chuẩn hóa port/service names thành **protocol + numeric port range** khi có mapping tin cậy.
3. Phân biệt **set không có thứ tự** (address group) với **ordered sequence** (firewall rules).
4. Resolve nested/dynamic groups theo snapshot time hoặc ghi unknown khi không đủ dữ liệu.
5. Giữ **rule ID, enabled, priority, direction, zone, context và schedule**.
6. Không bỏ qua thay đổi logging/inspection hoặc attachment vì “không thuộc connectivity”.
7. So cấu hình theo **device target + policy revision**, tránh ghép hai contexts khác nhau.

Canonicalization sai có thể che **thay đổi thực sự về quyền**. Khi resolver/vendor API không đủ, ghi **confidence thấp** và ưu tiên manual review.

### 6.7. Diff theo object graph

~~~mermaid
flowchart TD
  G["Address group changed"] --> REF["Find all referencing rules"]
  REF --> EXP["Expand groups and inherited objects\nat change time"]
  EXP --> SEM["Calculate effective source/dest/service\nand priority impact"]
  SEM --> ATT["Resolve policy attachments,\nzones, NAT, routes"]
  ATT --> IMP["Affected assets/trust boundaries"]
  IMP --> RISK["Risk review + targeted tests"]
~~~

Một object group có thể được tham chiếu bởi **hàng chục rules** và trên nhiều firewall contexts. Thay một member không phải “một rule change” về mặt blast radius; hệ thống nên tính **tập references bị ảnh hưởng**.

## 7. Change control: kết nối kỹ thuật với quyết định phê duyệt

### 7.1. Vòng đời change được đề xuất

1. **Request:** người yêu cầu nêu dependency, source/destination/port, environment, owner, expiry.
2. **Impact analysis:** network/security đánh giá reachability, data classification, trust boundary và khả năng downtime.
3. **Review:** có least-privilege design, peer review và approvals theo độ nhạy.
4. **Plan:** diff, thiết bị/contexts đích, validation/negative tests, rollback và maintenance window.
5. **Apply:** triển khai qua automation/IaC hoặc management system có danh tính rõ.
6. **Readback:** xác nhận từng target đã nhận revision mong đợi.
7. **Traffic verification:** thử những kết nối được phép/bị cấm trong phạm vi đã duyệt.
8. **Monitor:** quan sát drop/allow/IPS/latency/health trong một khoảng phù hợp.
9. **Close:** ghi bằng chứng, người xác nhận, trạng thái, rule owner và expiry.
10. **Revalidate:** recertification định kỳ và xóa ngoại lệ hết nhu cầu.

Không coi approval là một chuỗi ticket ID tự điền: **ticket phải liên kết đúng asset, rule fields, thời điểm, approver và quyền của actor**. Một ticket được duyệt cho TCP/443 tới một host không tự duyệt một rule **any-any**.

### 7.2. Định nghĩa authorized change

Một change được coi là authorized khi:

- Actor có **role** phù hợp và MFA/PAM theo chính sách.
- Thao tác nằm trong **approved scope** (đúng firewall, context, source/dest/protocol, duration).
- Change diễn ra trong **window** hợp lệ hoặc có emergency process rõ.
- Có **peer review** phù hợp mức risk, không chỉ self-approval nếu policy cấm.
- Actual diff **không rộng hơn** nội dung được phê duyệt; mở rộng phải review lại.
- Commit và runtime verification đã được ghi.
- Rule owner và expiry/recertification rõ.

**Authorized không đồng nghĩa secure**: thay đổi đã được phê duyệt vẫn có thể làm service lộ ra ngoài nếu thiết kế/risk review sai. Detection cần bao gồm **risky but approved changes**.

### 7.3. Break-glass và thay đổi khẩn cấp

Đôi khi cần hotfix bảo vệ trước một sự cố đang diễn ra. Thay đổi emergency nên:

- Có **incident reference, operator identity, scope và thời hạn**.
- Ghi lại trạng thái trước, thay đổi và quyết định người chỉ huy sự cố.
- Ưu tiên **containment hẹp**, không tắt firewall/security profiles toàn hệ thống.
- Có thông báo real-time tới SOC/NOC và người chịu trách nhiệm.
- Có **post-implementation review** ngay sau khi ổn định.
- Được đưa trở lại IaC/source of truth, tránh **drift lâu dài**.

Không coi mọi emergency ticket là đáng ngờ; nhưng **emergency bypass nhiều lần hoặc không hậu kiểm** là một anti-pattern cần alert và governance.

### 7.4. Drift là sai khác giữa nhiều nguồn chân lý

Ví dụ:

~~~text
Git desired:
  rule-prod-db-001 source = 10.20.10.0/24

Firewall running:
  rule-prod-db-001 source = 0.0.0.0/0

Ticket system:
  No approved widening

Finding:
  Unauthorized or unreviewed drift (until investigated)
~~~

**Không tự overwrite running firewall** ngay khi thấy diff. Có thể đó là emergency containment hợp lệ chưa được sync về Git, hoặc Git stale. Triage phải xác định **timestamp, actor, active incident, dependency và rollback impact** trước khi reconcile.

### 7.5. Policy-as-code và GitOps

Pipeline phòng vệ có thể:

~~~text
Pull request
  -> schema validation
  -> semantic diff / object resolution
  -> security lint and risk score
  -> approver and owner review
  -> controlled apply
  -> target readback + config hash
  -> positive/negative flow tests
  -> SIEM change event and evidence
~~~

Ưu điểm: rõ người phê duyệt, version, rollback và traceability. Nhưng **admin CLI/API ngoài pipeline** vẫn có thể xảy ra; phải bật audit và **drift scan** độc lập. Kiểm soát truy cập Git/IaC runner và signing/review cũng quan trọng như quản lý firewall.

### 7.6. Segregation of duties

Trong hệ thống rủi ro cao, cân nhắc tách:

- Requester (business/application owner).
- Reviewer/approver (security/network architect).
- Deployer (automation or authorized operator).
- Independent verifier (SOC/NOC/owner).

Với đội nhỏ, có thể dùng risk-based peer review và immutable audit thay vì quy trình cồng kềnh; nhưng **chính sách nhạy cảm không nên do một người vừa đề nghị, vừa phê duyệt, vừa sửa và tự xác nhận mà không để lại dấu vết**.

## 8. Chấm mức rủi ro và ưu tiên điều tra

### 8.1. Rủi ro phải gắn với tài sản và đường mạng

Một firewall rule được mở rộng ở mạng lab không có dữ liệu thật khác một rule tương tự áp vào **production database/identity provider**. Rủi ro thường chịu ảnh hưởng:

- **Source exposure:** Internet/partner/dev subnet hay workload được quản lý.
- **Destination criticality:** database, secrets manager, DC/identity, payment, control plane hay public web.
- **Service/protocol:** administrative ports, database, VPN, DNS hay traffic nghiệp vụ đã giới hạn.
- **Trust boundary crossing:** Internet→internal, dev→prod, third party→sensitive subnet.
- **Change direction:** allow widened, deny removed, logging/IPS disabled, exception extended.
- **Effective attachment/path:** firewall có thực sự nằm trên route và có rule precedence đúng không?
- **Actor/approval:** account quyền cao, MFA/PAM, maintenance window và ticket hợp lệ.
- **Time and persistence:** mở tạm với expiry, ngoài giờ hoặc permanent.
- **Evidence confidence:** chỉ thấy API request hay đã readback/verified traffic?
- **Compensating controls:** app mTLS, host firewall, IAM, segmentation và independent deny.

### 8.2. Risk scoring minh họa

Một mô hình **đào tạo**, không phải thang điểm chuẩn cho mọi tổ chức:

| Tín hiệu | Điểm gợi ý |
| --- | ---: |
| Mở source thành any / IPv4, IPv6 tương đương | +25 |
| Destination là tài sản Tier-0/Tier-1 | +25 |
| Cho phép quản trị từ vùng không đáng tin | +20 |
| Thay đổi xuyên trust boundary | +15 |
| Bỏ logging/IPS hoặc decryption policy có yêu cầu | +15 |
| Không có approval phù hợp | +20 |
| Ngoài giờ không có emergency reference | +10 |
| Mở permanent từ exception có TTL | +10 |
| Có readback + network path verification cho thấy mở rộng reachability | +10 |
| Có independent block và kiểm chứng deny vẫn hoạt động | −10 |

Điểm minh họa:

\[
\text{RiskScore}=\min\left(100,\max\left(0,\sum \text{các tín hiệu và điều chỉnh}\right)\right)
\]

Đây là **heuristic**. Không dùng điểm tự tạo này như bằng chứng pháp lý/tấn công. Một change chỉ có một tín hiệu cực nghiêm trọng, như **mở bất ngờ Internet tới management API**, vẫn có thể yêu cầu xử lý ngay dù điểm tổng chưa cao. Từng môi trường cần **calibration và mapping sang severity/response**.

### 8.3. Gợi ý phân cấp xử lý

| Mức ưu tiên | Tình huống | Hành động |
| --- | --- | --- |
| **Critical** | Confirmed unauthorized broad allow tới Tier-0 hoặc disable control biên gây exposure | Xác minh nhanh, IR/containment theo quyền |
| **High** | Unapproved any-any, tắt IPS/logging, NAT publish dịch vụ nhạy cảm | SOC/NOC triage ngay theo SLA |
| **Medium** | Approved rule mở rộng đáng kể hoặc drift chưa giải thích | Review ticket, dependency và verification |
| **Low** | Thay đổi mô tả/comment, rule đã hết hạn nhưng chưa được clean, không đổi behavior | Governance backlog với owner |
| **Unknown** | Không đọc được config/diff/target hoặc collector đang lỗi | Alert coverage và thu thập thêm, không coi an toàn |

**High severity không đồng nghĩa confirmed exploitation.** Nó phản ánh **khả năng ảnh hưởng cao từ chính sách/đường mạng**. Nếu flow hoặc application audit xác nhận truy cập trái quyền, severity có thể thay đổi.

### 8.4. Rủi ro chiều Availability

Không chỉ mở rule mới nguy hiểm. Một policy deny sai có thể khiến:

- **DNS** ngưng hoạt động, service discovery fail.
- **Identity provider/SSO** bị chặn khiến hàng loạt services không xác thực được.
- **Database backend** bị cắt, connection pool lỗi.
- **VPN/cloud peering** không chuyển được traffic.
- **Health checks/replication** fail dẫn tới failover.
- **Telemetry exporter** mất kết nối, SOC bị mù.

Vì thế đánh giá cả **NewlyAllowed** và **NewlyDenied**, cùng **blast radius/critical dependencies**, tránh thang điểm chỉ quan tâm security exposure mà bỏ availability.

### 8.5. Rủi ro không thể tính chỉ bằng số lượng IP

Một rule mở một IP /32 của management interface nhạy cảm vẫn có thể nguy hiểm hơn rule mở nhiều IP cho public HTTP API đã được thiết kế bảo vệ. Thang điểm cần biết **asset value, boundary, application authorization, protocol và exposed direction**, không đơn giản “CIDR càng lớn càng nguy hiểm” trong mọi trường hợp.

### 8.6. Confidence khác severity

Ví dụ:

~~~text
Event: remove deny rule
Severity estimate: High
Evidence:
  change API event = yes
  active running config readback = no
  policy attached to target = unknown
  traffic test = not performed

Conclusion:
  High-risk configuration change reported;
  effectiveness and impact still unverified.
~~~

Kết luận đúng nên ghi **severity và evidence confidence riêng**, tránh dùng thiếu evidence làm lý do bỏ qua, cũng tránh báo chắc chắn mở đường khi mới chỉ có một plan chưa apply.

## 9. Detection engineering cho thay đổi firewall

### 9.1. Quy tắc phát hiện kỹ thuật

| ID | Detection | Nguồn | Cảnh báo khi |
| --- | --- | --- | --- |
| FW-01 | Broad allow newly introduced | Semantic diff + asset context | Source/dest/service mở rộng qua boundary |
| FW-02 | Deny rule deleted/disabled | Config diff | Deny quan trọng mất hiệu lực |
| FW-03 | Logging disabled | Diff + telemetry health | Rule nhạy cảm tắt log, giảm visibility |
| FW-04 | IDS/IPS/security profile weakened | Profile diff | Inspection bị bỏ/giảm |
| FW-05 | Rule reordered to higher priority | Ordered policy diff | Rule có thể che deny trước đó |
| FW-06 | Sensitive object group expanded | Object graph diff | References tới tài sản nhạy cảm mở |
| FW-07 | Unapproved actor or ticket mismatch | Audit + IAM/PAM/ITSM | Actor/approval/scope không khớp |
| FW-08 | Out-of-window change | Audit + maintenance calendar | Không có emergency reference |
| FW-09 | Repeated failed admin attempts then change | Auth/PAM + audit | Bất thường đặc quyền cần điều tra |
| FW-10 | Device running vs Git drift | Snapshot + IaC | Sai khác ngoài pipeline |
| FW-11 | Unexpected NAT publication | NAT + route diff | Backend private có thể reachable mới |
| FW-12 | Direct egress route bypass gateway | Route/SG/NAT + flow | New alternate path ngoài egress firewall |
| FW-13 | HA member versions diverge | Per-device readback | Peer A/B khác revision quá ngưỡng |
| FW-14 | Rollback not completed | Deployment events | Thay đổi fail một phần, không về baseline |
| FW-15 | Rule exception expired | Ticket/metadata + config | Rule còn enabled sau hạn |
| FW-16 | Security group attachment changed | Cloud audit | Database/LB gắn SG khác dự kiến |
| FW-17 | NetworkPolicy removed/widened | K8s audit + CNI | Pod isolation giảm |
| FW-18 | WAF exclusion widened | WAF policy diff | Managed rules/path inspection bị bypass |
| FW-19 | Telemetry destination modified | Config + collector health | Logs chuyển nơi khác/tắt exporter |
| FW-20 | Change followed by policy deny spike | Change + flow + SLO | Có thể outage do change |
| FW-21 | Change followed by unexpected allow traffic | Change + flows + asset map | NewlyAllowed path được sử dụng |
| FW-22 | Dynamic group/FQDN resolved set drift | Object resolver audit | Membership thay không qua review |
| FW-23 | Control API used from new location | Admin audit/PAM/IAM | Có thể session/credential abuse |
| FW-24 | Rule/zone altered on failover node only | HA audit | Bypass/availability asymmetry |
| FW-25 | Collector silent during known change window | Collector heartbeat + ticket | Visibility gap không được ghi nhận |

Không tạo một quy tắc **“có change là incident”**. Ưu tiên **prevention cho critical policy violations**, alert contextual và report low-risk routine changes ở mức governance.

### 9.2. Detect approved-but-risky

Một change được ticket phê duyệt vẫn cần cảnh báo nếu:

- Approved scope là một /32 nhưng actual diff là **0.0.0.0/0**.
- Allowed port TCP/443 bị thêm **TCP/22 hoặc port quản trị**.
- Rule được phê duyệt cho 1 giờ nhưng schedule đổi thành **always**.
- Actor dùng đúng quyền nhưng thực thi lên **device/tenant không nằm trong ticket**.
- Approval chỉ cho application subnet nhưng object group references lan sang production secrets subnet.
- Change **tắt logging** dù ticket không đề cập.

Rule engine cần so **approved fields vs actual structured diff**, không chỉ kiểm tra “ticket tồn tại”.

### 9.3. Pseudocode phát hiện

~~~text
function evaluateChange(event, desired, ticket, assets):
    if event.source is untrusted:
        return ALERT("source authenticity unknown", severity="unknown")

    before = normalize(event.before_snapshot)
    after = normalize(event.after_snapshot)
    delta = computeSemanticDiff(before, after, assets)

    result = []
    if delta.newly_allowed_crosses_sensitive_boundary:
        result.append("sensitive_newly_allowed")
    if delta.logging_disabled_on_sensitive_flow:
        result.append("logging_reduced")
    if delta.inspection_profile_weakened:
        result.append("inspection_weakened")
    if not approvedScopeCovers(ticket, event.targets, delta):
        result.append("approval_mismatch")
    if after != desired and not approvedEmergencyException(event):
        result.append("configuration_drift")

    if event.applied_targets != event.expected_targets:
        result.append("partial_deployment")

    emitChangeFinding(
        event_id=event.id,
        indicators=result,
        severity=estimateRisk(delta, assets, ticket),
        confidence=assessEvidence(event),
        snapshot_refs=[event.before_ref, event.after_ref]
    )
~~~

Pseudocode dùng để **mô tả detection design**. Trong triển khai thật cần xử lý **missing snapshots, ambiguous object references, vendor semantics, concurrency, eventual consistency, race conditions, source authentication, deduplication và rule graph expansion**. Không tự gửi lệnh rollback từ một detector chưa được kiểm nghiệm.

### 9.4. Dedupe và correlation windows

Một thay đổi có thể phát ra:

~~~text
03:20 ticket approved
03:21 IaC apply started
03:21 firewall manager edit
03:22 rule change commit
03:22 HA peer sync
03:22 device syslog config changed
03:24 API readback revision r42
~~~

Đây có thể là **một change lifecycle** chứ không phải sáu incidents. Dedupe bằng **change ID / ticket / device-context / revision / actor / correlation window**, vẫn giữ **raw source event references** để không mất evidence. Ngược lại, **nhiều thay đổi liên tiếp có revision khác nhau** không được gộp nhầm vì cùng actor và cùng device.

### 9.5. Baseline theo workload, không theo một số tuyệt đối

Một firewall của hạ tầng mạng thay đổi theo maintenance mỗi tuần; một firewall của Tier-0 identity service có thể rất ít thay đổi. Baseline:

- Thiết bị/zone nào thường thay đổi vào thời gian nào?
- Object/rule owner nào thay thường xuyên do autoscaling?
- Có dynamic DNS address feeds hợp lệ không?
- Các IaC apply có **periodic no-op revisions** không?
- Mức độ rủi ro và approval nào bắt buộc cho production?
- Có hoạt động khẩn cấp đang diễn ra không?

**“Thay đổi lúc nửa đêm” không tự chứng minh malicious** khi đó là maintenance window đã phê duyệt; nhưng vẫn cần kiểm **scope và outcome**.

### 9.6. False positives và false negatives

**False positives:**

- Auto-generated object order thay nhưng semantics không đổi.
- Dynamic group membership do autoscaling hợp lệ.
- Reconciliation làm controller ghi lại config không thay effective state.
- Khác nhau do time-zone/clock skew khiến change có vẻ ngoài window.
- HA failover gây event sync lặp.
- Rule đã disable, diff field service nhưng không có exposure mới.

**False negatives:**

- Audit logging bị tắt trước khi thay rule.
- Object group thay đổi nhưng detector chỉ đọc rule list.
- NAT/route thay đổi ngoài firewall manager.
- Policy chưa readback sau khi commit.
- Một cloud account hoặc cluster không được collector phủ.
- Direct CLI admin hotfix không được IaC ghi nhận.
- Detector bỏ qua IPv6, schedules hoặc policy attachment.

Khắc phục bằng **independent snapshots, gap alerts, full object graph, cross-source correlation và negative tests**. Không tắt một rule phát hiện quan trọng chỉ vì nhiều false positives; điều chỉnh logic bằng ngữ cảnh và đánh giá coverage.

### 9.7. Cảnh báo phải hướng tới hành động

Ví dụ cảnh báo tốt:

~~~text
Finding: Newly allowed broad source to sensitive database service
Severity: HIGH (provisional)
Device: fw-east-01 / corp-prod-vdom
Rule ID: rule-prod-db-001
Changed: source 10.20.10.0/24 -> 0.0.0.0/0
Destination: prod-db / TCP/5432
Actor: ops-user-17 (SSO MFA)
Ticket: not linked
Commit: r41 -> r42, success on manager
Peer sync: not yet confirmed
Effective route: unknown
Next: verify approval, target readback and path;
      contain if unauthorized according to IR authority
Raw secret content: none
~~~

Cảnh báo kém hữu ích là **“Firewall config changed”** mà thiếu rule/actor/impact/context; hoặc **“Database exposed to Internet”** khi mới chỉ thấy field source=any mà chưa xác minh route/zone.

## 10. Kiểm chứng policy trên data plane và tương quan SIEM

### 10.1. Tại sao cần kiểm chứng cả policy lẫn traffic?

Để khẳng định một thay đổi có ý nghĩa bảo mật, có thể cần ba bằng chứng:

1. **Control plane:** rule/object/route mới được yêu cầu và áp lên target đúng.
2. **Data plane:** gói tin của một traffic class phù hợp thực sự đi qua enforcement point và cho phép/từ chối theo policy.
3. **Application/resource:** request được xử lý hoặc bị từ chối ở mức ứng dụng; không suy rằng TCP connect thành công đồng nghĩa có quyền đọc dữ liệu.

Một **deny test** bị chặn ở cloud security group trước khi vào firewall **không chứng minh chính firewall đã deny**, mặc dù overall defense-in-depth có thể hoạt động đúng. Ngược lại, firewall cho phép kết nối TCP tới API nhưng API trả 403 có thể là **authorization vận hành đúng**, không phải misconfiguration của firewall.

### 10.2. Phân tầng kiểm chứng

~~~mermaid
flowchart TD
  S["Change committed / rule diff"] --> T["Readback per target\nrevision and object expansion"]
  T --> R["Topology check\nzones/NAT/routes/attachments"]
  R --> F["Controlled positive/negative flow tests"]
  F --> L["Flow/IDS/IPS/WAF telemetry\nmatched rule and decision"]
  L --> A["Application health/auth audit\nbusiness impact"]
  A --> C["Close or incident with evidence\nowner and rollback"]
~~~

Nếu cấu hình thuộc **cloud-managed firewall**, một số lớp data plane hoặc rule ID có thể không lộ ra. Ghi rõ **khả năng quan sát**, không “điền” synthetic rule verdict vào dữ liệu production.

### 10.3. Positive và negative tests

Giả sử yêu cầu mở duy nhất:

~~~text
Source: application subnet 10.20.10.0/24
Destination: orders API subnet 10.30.20.0/24
Protocol: TCP
Destination port: 8443
Policy: allow scoped; default deny other sources
~~~

Các test tối thiểu:

| Test | Source | Destination | Expected | Ý nghĩa |
| --- | --- | --- | --- | --- |
| T1 | Approved app subnet | Orders TCP/8443 | **Allow** | Luồng nghiệp vụ mới chạy |
| T2 | Unapproved dev subnet | Orders TCP/8443 | **Deny** | Không mở rộng source |
| T3 | Approved app subnet | Orders TCP/22 | **Deny** | Không mở port quản trị |
| T4 | Approved app subnet | Orders TCP/9443 | **Deny** nếu không trong rule khác | Port scope đúng |
| T5 | External/partner zone | Orders TCP/8443 | **Deny** theo policy | Trust boundary đúng |
| T6 | Approved app subnet | Critical DNS/identity dependency | **Still works** | Không gây outage |
| T7 | IPv6 source/destination tương đương (nếu dual-stack) | Orders IPv6 TCP/8443 | Theo policy IPv6 riêng | Không có bypass family |
| T8 | Same test sau failover HA | Orders TCP/8443 | Cùng decision | Sync nhất quán |

Các test chỉ thực hiện từ **test nodes/workloads được cấp quyền**, với đích thuộc quyền sở hữu. **Không scan subnet bên thứ ba hoặc thử brute-force management ports** để chứng minh deny. Một phép thử mạng có thể bị proxy/NAT/app logic ảnh hưởng: ghi **test vantage point, protocol, resolver, TLS policy, route và kết quả từng layer**.

### 10.4. Gắn rule với traffic mà không suy diễn

Một flow log có thể ghi **matched rule ID** nếu thiết bị hỗ trợ; một số log chỉ có action và tuple. Khi không có rule ID:

- Có thể dùng **policy simulation** và routing context để nêu **candidate rules**.
- Không khẳng định một rule cụ thể đã match nếu thiếu evidence.
- Lưu **pre-NAT và post-NAT 5-tuple** theo những gì collector thật sự cung cấp.
- Đối chiếu zone/interface và direction của flow.
- Xem flow start/end time; session có thể tồn tại **trước khi policy đổi**.
- Kiểm tra thiết bị stateful có grandfather existing connections khi policy update hay không.

**Session continuity** quan trọng: một rule deny mới có thể không ngắt ngay session đã thiết lập, tùy firewall product, policy re-evaluation và session table. Khi incident containment, cần xem **cơ chế xử lý existing sessions** theo change authority.

### 10.5. NAT làm source/destination trông khác

Ví dụ:

~~~text
Before NAT:
  10.20.10.5:50123 -> 198.51.100.10:443

After source NAT:
  203.0.113.20:61001 -> 198.51.100.10:443
~~~

Địa chỉ IP ở external service log có thể là **NAT IP chung**, không phải một Pod/máy duy nhất. Để điều tra source của traffic sau change, cần NAT/session mapping, timestamp và identity/workload context. Không tự ghi source=10.20.10.5 vào một external log nếu chỉ thấy NAT IP và không có translation evidence.

### 10.6. IDS/IPS và WAF sau thay đổi

Một allow rule không tự bảo đảm traffic **được kiểm tra**. Cần xác minh:

- Firewall security profile/IPS có gắn trên rule mới?
- Traffic đi qua **đúng inspection interface/path**?
- TLS inspection được áp khi phù hợp và được cho phép?
- WAF chỉ thấy traffic qua gateway hay có direct-to-origin bypass?
- Log allow/deny/IPS actions có đúng category/retention không?
- Có tăng **false positives** hoặc applications bị block sau change?

**DLP/WAF/IPS không thay thế network access control**, và cũng không nên được tự tắt vì một rule bị lỗi mà không đánh giá ảnh hưởng phòng vệ.

### 10.7. Tương quan sự kiện trong cửa sổ thay đổi

~~~text
13:00Z  change approved for payment gateway TCP/443
13:04Z  firewall policy revision r58 committed
13:05Z  HA peers report r58 synchronized
13:06Z  allowed flows to gateway increase
13:06Z  denied flows to unknown destinations unchanged
13:07Z  payment service p95 latency stable
13:15Z  validator records positive/negative tests PASS
~~~

Đây là chuỗi **phù hợp với triển khai có kiểm soát**, nhưng vẫn cần biết source/ticket/approval và dữ liệu có chính xác không. Ngược lại:

~~~text
13:04Z  firewall rule widened source to any
13:06Z  new allow flows from partner zone to prod-db
13:07Z  IDS reports high-risk access pattern
13:08Z  application audit indicates denied login attempts
~~~

Đây là **tín hiệu điều tra cao** và có thể cần containment, nhưng **denied logins** chưa chứng minh database bị truy cập thành công. Tiếp tục xác định **actor, source identity, resource/action outcome**.

### 10.8. Không “đổ hết lỗi cho firewall”

Khi API latency tăng sau change, nguyên nhân có thể là:

- Firewall session table/CPU/inspection quá tải.
- Route/NAT không đồng bộ.
- Backend app deployment cùng lúc.
- DNS change, certificate renewal hoặc external dependency outage.
- Gateway/WAF/mesh policy khác áp lại.

Tương quan **timeline change + per-hop telemetry + app SLO** giúp điều tra, không phải một phép chứng minh quan hệ nhân quả tuyệt đối. Cần **controlled rollback hoặc canary** khi phù hợp, không tự kết luận vì hai sự kiện xảy ra gần nhau.

## 11. Theo dõi firewall trên môi trường cloud và Kubernetes

### 11.1. Cloud security group: theo rule và attachment

Một cloud security group thường **cho phép traffic theo inbound/outbound rules** và được gắn vào resource/network interfaces. Những thay đổi cần theo dõi:

- Rule add/remove/update, **CIDR/prefix list/source SG**.
- Port/protocol và IPv4/IPv6.
- Resource/ENI/instance/database/LB **attachment changed**.
- Default egress policy và new broad allows.
- Cloud account/project/region/network boundaries.
- IAM identity, assumed role, API session/MFA/audit.
- Effective reachability sau thay đổi routing/NACL/firewall.

Một rule mở TCP/5432 có thể chưa tạo exposure nếu SG chưa attached vào database; **một thay đổi attachment** sau đó mới khiến rule có hiệu lực. Detection phải xây **resource + rule + route graph**.

### 11.2. Cloud network ACL/NACL và return traffic

NACL/stateless ACL trong một số cloud providers có **priority/order và inbound/outbound rules riêng**. Khi thêm deny/allow, phải xem:

- Ephemeral return ports và chiều response.
- Subnet association.
- Thứ tự ưu tiên và rule evaluation semantics.
- IPv4/IPv6 rules.
- Connections đi qua load balancer/NAT/gateway.

Không sao chép giả định **stateful SG** sang **stateless NACL**. Một rule inbound allow TCP/443 không tự làm return traffic thành công nếu outbound stateless policy chặn.

### 11.3. Cloud firewall/gateway attachment và route

Một cloud firewall endpoint có thể hoạt động đúng nhưng **VPC route table** bị đổi cho traffic bypass. Cần monitor:

~~~text
Firewall policy/config changes
+ Route table and next-hop changes
+ Subnet/VPC attachment and associations
+ Transit gateway/peering/VPN connectivity
+ NAT gateway and egress endpoint changes
+ VPC flow logs / cloud audit
~~~

Không chỉ monitor số rule changes. **Security posture có thể giảm dù firewall config bất biến**, nếu route/attachment mới không đi qua điểm enforcement.

### 11.4. WAF là policy HTTP, không phải tường lửa mọi cổng

WAF monitoring nên theo:

- Managed rule set version và automatic updates.
- Custom rules, skip/bypass/allow exceptions.
- Rule order/priority và action changes.
- Origin IP/host restrictions, CDN/LB/Gateway association.
- API paths, request body inspection size, false-positive exceptions.
- Access/attack logs, rate limiting/bot profiles.
- Đường direct-to-origin không qua WAF.

Một WAF managed rule được cập nhật tự động có thể tạo **cấu hình thay đổi không do admin thủ công**. Cần so **rule version, vendor maintenance, effective WAF action và app regressions**, không chỉ alert thiếu ticket.

### 11.5. Kubernetes NetworkPolicy khác ordered firewall

NetworkPolicy chuẩn thường có các đặc điểm:

- Policy chọn **Pod labels trong namespace**, không chọn một service bằng DNS name.
- Ingress/Egress isolation theo policyTypes và tập policies áp lên Pod.
- Các allow rules **cộng gộp**, không theo “rule sau ghi đè rule trước”.
- Tên namespace, labels và Pod selector changes có thể đổi phạm vi policy.
- Không có **standard ordered deny** hoặc **FQDN allowlist** trong Kubernetes NetworkPolicy API cơ bản.
- CNI phải hỗ trợ/enforce; YAML được API server lưu **chưa chứng minh dataplane deny**.
- hostNetwork/secondary interfaces/node-level flows có thể yêu cầu controls khác.

Ví dụ giả lập thay đổi:

~~~yaml
# BEFORE: trong NetworkPolicy cho API
ingress:
  - from:
      - namespaceSelector:
          matchLabels:
            trust-tier: backend
        podSelector:
          matchLabels:
            app: frontend
    ports:
      - protocol: TCP
        port: 8443
~~~

Khi chuyển thành:

~~~yaml
# AFTER: hai items, biểu đạt OR thay vì AND
ingress:
  - from:
      - namespaceSelector:
          matchLabels:
            trust-tier: backend
      - podSelector:
          matchLabels:
            app: frontend
    ports:
      - protocol: TCP
        port: 8443
~~~

**Đổi indentation/list item có thể mở rộng tập nguồn**: bản BEFORE yêu cầu Pod nguồn ở namespace có nhãn trust-tier=backend **và** app=frontend; AFTER cho phép Pods từ mọi namespace khớp trust-tier=backend **hoặc** Pods trong namespace của policy có app=frontend, theo semantics của Kubernetes NetworkPolicy peer selectors. Để đánh giá chính xác cần kiểm tra **namespace của policy và labels tại thời điểm đó**.

### 11.6. Kubernetes audit + CNI telemetry

Theo dõi:

- Create/update/patch/delete NetworkPolicy, namespace/Pod labels.
- CNI global/cluster network policies nếu plugin hỗ trợ, tách khỏi API chuẩn.
- Pod Security/admission thay đổi cho hostNetwork/privileged.
- Ingress/Gateway/Service LoadBalancer/NodePort exposure.
- CNI agent readiness/policy synchronization và flow verdicts nếu có.
- Cluster changes làm PodCIDR, service networking, NAT hoặc routing khác.

**Không phải mọi CNI xuất chính xác rule ID trong flow log**, và việc thiếu event ở CNI exporter không chứng minh flow bị chặn. Dùng app/flow/test results và collector health để đánh giá coverage.

### 11.7. Service mesh, mTLS và firewall đều có vị trí riêng

Một mesh AuthorizationPolicy có thể kiểm soát workload identity hoặc HTTP actions tại **proxy/waypoint**; một NetworkPolicy giới hạn network reachability; một WAF kiểm tra HTTP qua gateway; một firewall vật lý/cloud kiểm soát routes/zones. Theo dõi thay đổi phải giữ **tên control plane và enforcement point** cụ thể.

Nếu sidecar bị bypass, **mesh policy trên control plane không chặn đường khác**; nếu Kubernetes NetworkPolicy bị CNI bỏ qua, policy YAML cũng không đủ. Một hệ thống giám sát chính xác cần map **intent → enrollment/attachment → data plane → business outcome**.

### 11.8. IPv4/IPv6, identity và dynamic objects

Các thay đổi thường bị bỏ quên:

- Rule IPv4 bị deny nhưng rule IPv6 tương đương vẫn allow.
- Cloud SG source SG reference mở khi resource association thay.
- DNS/FQDN-based policy đổi tập IP do DNS/update feed, không có rule edit.
- Identity-based policies thay scope khi role/group labels đổi.
- Một object định danh tenant/app đổi owner và thành **shadow approval**.

Nếu dynamic membership ngoài khả năng audit, ghi **coverage gap và runtime snapshot** thay vì báo semantic diff “không có thay đổi”.

## 12. Theo dõi triển khai, HA và failure modes

### 12.1. Commit thành công nhưng policy chưa đồng bộ

Trên firewall có HA hoặc nhiều policy targets:

~~~text
Change ID CHG-105
  Desired revision: r105
  Manager: success
  fw-east-01: r105 (active)
  fw-east-02: r104 (standby)
  fw-west-01: r105

Conclusion:
  Partial deployment; HA consistency not verified.
~~~

Cần:

- Readback **từng member**, version/config hash trong policy context đúng.
- HA sync status, timestamps và drift duration.
- Kiểm tra failover path (chỉ trong maintenance/sandbox được phê duyệt).
- Cảnh báo khi deployment **partial** hoặc target offline.
- Rollback/reconciliation plan nếu một member không áp.

**Không tự cho rằng active/standby peers có cùng chính sách** chỉ vì cluster health hiển thị green. Cũng không cố failover production để kiểm tra một thay đổi nếu chưa có quyền/khung vận hành.

### 12.2. Session state và thay đổi rule

Stateful firewall có thể duy trì **existing sessions** sau khi rule bị thay hoặc xóa, tùy thiết bị/chế độ re-evaluation. Vì thế:

- Một negative test dùng **connection đã mở trước change** có thể cho kết quả khác connection mới.
- Session tracking/conntrack/NAT state có thể làm traffic tiếp tục một thời gian.
- IDS/IPS/WAF changes có thể áp lên requests mới mà không áp tức thì lên mọi stream đang mở.
- Nếu yêu cầu containment khẩn cấp, quy trình cần chỉ rõ có nên **xóa phiên liên quan** hay không, theo impact/authorization.

Không khuyên “clear all sessions” như mặc định; thao tác đó có thể làm gián đoạn hàng loạt services.

### 12.3. Firewall update và thay đổi không nguyên tử

Một hệ thống có thể triển khai theo:

1. Push config tới manager.
2. Validate syntax.
3. Commit per-device.
4. HA sync.
5. Program policy/hardware acceleration/eBPF tables.
6. Begin matching traffic.

Giữa các bước có thể có **transient inconsistency**. Monitoring cần quan sát **commit failure, reject, policy installation lag và fallback behavior**. Không tự gán cụ thể các bước nội bộ này cho mọi vendor.

### 12.4. Tác động của timezone và độ trễ

Một security alert có thể dựa vào việc thay đổi “ngoài giờ”, nhưng:

- Ticket tạo theo timezone địa phương, device log theo UTC.
- Clock của manager lệch vài phút với SIEM.
- Queue log delayed/replayed.
- Event cùng change ID gửi nhiều lần.
- Cloud audit có thời gian event khác ingestion.

Chuẩn hóa **UTC event time**, giữ timezone gốc khi cần, theo dõi **NTP drift, ingestion lag và event-order confidence**. Nếu event thiếu timestamp đáng tin, không dùng một phép so “ticket trước/sau” làm kết luận tự động.

### 12.5. Bảo vệ kênh logging khi firewall bị thay đổi

Một admin có quyền sửa firewall có thể có quyền **tắt logging hoặc đổi sink**. Để giảm blind spots:

- Gửi logs tới **remote/central collector** với đường truyền xác thực.
- Lưu **independent controller/cloud audit events** nếu có.
- Snapshot định kỳ từ **read-only collector** tách identity.
- Bật **heartbeat/config version query**; alert khi nguồn im lặng.
- Giới hạn quyền sửa log destinations và audit retention.
- Với critical devices, có tamper-evident/immutable storage theo chính sách.

**Không có sự kiện change từ thiết bị trong lúc một IaC apply rõ ràng đã diễn ra** là một tín hiệu coverage, không được im lặng coi “không thay đổi”.

### 12.6. Backup và rollback là hai khả năng khác nhau

Có config backup không đồng nghĩa có thể **rollback an toàn**:

- Backup có thể thuộc firmware/version khác.
- Chỉ rollback rule mà bỏ related object/zone/NAT sẽ không khôi phục semantics.
- Changes khác có thể được apply sau revision đang xét.
- Revert full config có thể xóa **emergency containment** hợp lệ.
- HA members và cloud resources có thể ở versions khác.
- Routing/session state có thể tiếp tục tác động sau revert.

Vì thế rollback cần **targeted diff, dependency analysis, approval, post-rollback readback và traffic validation**. Không áp “restore full snapshot” trên production theo phản xạ.

### 12.7. Change freeze và ngoại lệ

Trong giai đoạn nhạy cảm (sự kiện lớn, kỳ quyết toán, incidents, release freeze), quy trình có thể hạn chế changes. Monitoring cần:

- Gắn **freeze calendar** vào risk context.
- Alert unauthorized change trong freeze.
- Phân biệt **security emergency exception** được phê duyệt.
- Rà mọi exceptions sau freeze.
- Không dùng freeze để trì hoãn containment nguy cấp mà không có risk decision.

### 12.8. Monitoring theo vòng đời rule

Một rule không phải tài sản vĩnh viễn:

~~~mermaid
flowchart LR
  N["Need identified"] --> R["Review & approval"]
  R --> D["Deploy & verify"]
  D --> O["Owner / expiry / usage monitoring"]
  O --> C{"Still justified?"}
  C -- "Yes" --> O
  C -- "No" --> X["Remove via change process"]
  X --> V["Validate no regression\nand archive evidence"]
~~~

Monitoring nên phát hiện **orphan rules, disabled-but-retained policies, expired exceptions, owners đã rời nhóm, broad allows ít được sử dụng** để lập kế hoạch recertification. Không tự động xóa rule “0 hit count” vì counters có thể reset, traffic hiếm gặp hoặc rule bảo vệ DR path.

## 13. Thiết kế dashboard, SLO và đo chất lượng giám sát

### 13.1. Bảng điều hành nên có câu trả lời, không chỉ đồ thị

Một dashboard hữu ích cho SOC/NOC/change manager:

| Nhóm | Thông tin | Quyết định hỗ trợ |
| --- | --- | --- |
| **Change volume** | Tổng thay đổi theo tuần, thiết bị, môi trường, loại rule | Planning và phát hiện đột biến |
| **Risk profile** | High-risk allow/deny/NAT/logging changes | Ưu tiên triage |
| **Approval compliance** | % changes map đúng ticket/owner/approved scope | Governance |
| **Drift** | Số targets lệch desired state, drift age | Remediation backlog |
| **Effective status** | Commit vs per-target readback vs verified | Phát hiện partial deployment |
| **Network outcome** | Allowed/denied flow shifts, SLO errors | Phát hiện regression/exposure |
| **Expired exceptions** | Rule active quá TTL, owner missing | Recertification |
| **Telemetry coverage** | Devices reporting, ingestion lag, audit completeness | Biết dữ liệu bị thiếu |
| **Response performance** | MTTD, MTTA, MTTR/containment, repeat changes | Cải thiện playbook |

Dashboard nên có **filters** theo cluster/device, business owner, trust tier, environment, source/dest zones và change window. Không hiển thị **raw config chứa secrets** ở trang chung.

### 13.2. SLO/metric quan trọng

| Metric | Định nghĩa mẫu | Lưu ý |
| --- | --- | --- |
| **Coverage rate** | Số firewall targets có audit+readback / số targets kỳ vọng | Denominator từ CMDB/inventory đáng tin |
| **Event ingestion lag** | SIEM ingestion time − event time | Clock skew, batch delivery |
| **Change detection latency** | First meaningful alert − actual commit time | Event lifecycle, không đo từ ticket |
| **Approval-match rate** | % changes khớp đầy đủ ticket scope | Không chỉ có ticket string |
| **High-risk change MTTA** | First analyst acknowledgment − alert time | On-call/timezone |
| **Effective verification rate** | % deployed changes có readback và tests theo policy | Không mọi change cần live probes |
| **HA sync compliance** | % critical HA pairs cùng expected revision | Theo desired target rollout |
| **Expired-rule age** | Thời gian rule còn active sau expiration | Governance |
| **Unexpected drift age** | Từ khi thấy drift đến khi được giải thích/sửa | Ưu tiên theo risk |
| **Alert precision** | Confirmed actionable findings / investigated alerts | Phụ thuộc review sampling |
| **Negative-test coverage** | Sensitive paths có deny tests / sensitive paths inventory | Đừng đo chỉ từ sample thuận tiện |
| **Logger health** | Collectors reporting heartbeat / expected sources | Silence detection |

Không tự đặt SLO chung như “100% changes được phát hiện trong 1 giây” khi thiết bị/cloud audit có độ trễ hoặc snapshot polling. Chọn **mục tiêu đo được theo criticality**, và ghi rõ exclusions/late events.

### 13.3. Ước tính coverage một cách trung thực

Ví dụ:

~~~text
Inventory:
  15 physical/virtual firewalls
  8 cloud firewall policies
  2 Kubernetes clusters with network policies

Covered:
  15 devices with syslog
  11 devices with config readback
  8 cloud policies with API audit
  1 Kubernetes cluster with CNI flow verdicts

Correct report:
  Syslog coverage for devices: 15/15
  Readback coverage for devices: 11/15
  Cloud audit coverage: 8/8
  K8s CNI enforcement visibility: 1/2 clusters
~~~

Không gộp thành một con số **“100% monitored”** vì syslog đủ nhưng 4 devices không có snapshot readback, hoặc 1 cluster không có CNI flow visibility.

### 13.4. Quy trình alert tuning có quản trị

1. Thu thập sample **synthetic/approved historical events**, không sử dụng raw secret config trong test chung.
2. Kiểm tra detector phân biệt **actual changes vs no-op reconciliation**.
3. Phân tích false positives do dynamic objects, HA sync và vendor-generated updates.
4. Thêm asset context, approved window, change scope và ownership.
5. Định nghĩa thresholds theo **Tier-0/Tier-1 vs normal infrastructure**.
6. Có alert dedupe nhưng giữ original evidence.
7. Đánh giá false negatives bằng **red team/tabletop/synthetic change scenarios** trong sandbox.
8. Review detector versions, approvals và rollback của SIEM rules.

Không để một exception rộng “ignore all changes from automation account” vì **automation role có thể bị compromise hoặc IaC plan sai**. Chỉ giảm noise khi change match **policy-approved scope và revision**.

### 13.5. Dữ liệu lịch sử và retention

Để điều tra một incident tháng trước, có thể cần:

- Historical config revisions/snapshots.
- Audit actor/approval timeline.
- Object group memberships theo thời điểm.
- NAT/flow/session records với retention đủ.
- Device/HA role assignment history.
- Asset criticality và service owner tại thời điểm change.
- Related application deployments và SLO history.

Retention cần theo **chính sách tổ chức/pháp luật và data classification**, tránh lưu raw credentials trong central logs quá dài. Xem **immutable evidence** và privacy impact tương ứng.

### 13.6. Biến logging thành kiểm soát độc lập

Đối với các firewall targets quan trọng, có thể kết hợp:

- Device syslog/config audit.
- Controller/cloud API audit.
- Periodic read-only config snapshot.
- Git/IaC pipeline records.
- Independent route/flow telemetry.
- App health synthetic probes.

Khi một nguồn biến mất, nguồn khác có thể phát hiện **coverage gap**. Tuy nhiên **độc lập về công cụ không đủ nếu chúng dùng cùng credentials/admin network**; kiến trúc cần xem xét failure domains thực.

## 14. Lab tổng hợp: phát hiện thay đổi cấu hình firewall bằng dữ liệu giả lập

### 14.1. Mục tiêu và ràng buộc

Lab được thiết kế **offline**, chỉ phân tích các tài liệu policy/audit giả lập. Không yêu cầu đăng nhập firewall thật, mở port, xóa rule, tắt IPS hay gửi traffic vào mạng production. Người học phải:

1. Phân biệt **approved change, high-risk drift, attempted/uncommitted change và verified effective change**.
2. Tạo **structured semantic diff** bao gồm referenced objects.
3. Liên kết **actor–ticket–asset–revision–approval**.
4. Chấm rủi ro và xác định **evidence confidence**.
5. Lập **positive/negative test plan** để đội có quyền kiểm chứng sau này.
6. Xây SIEM findings **không lưu secrets**.
7. Xử lý **HA partial deployment** và một đoạn telemetry bị thiếu.

### 14.2. Mô hình mạng giả lập

~~~mermaid
flowchart LR
  INTERNET["Internet / partner network"] --> EDGE["Edge firewall\nHA pair"]
  DEV["Development subnet\n10.40.0.0/16"] --> EDGE
  WEB["Web/frontends\n10.20.10.0/24"] --> EDGE
  EDGE --> API["Orders API\n10.30.20.0/24"]
  EDGE --> DB["Sensitive DB\n10.30.5.0/24"]
  EDGE --> EGR["Approved egress gateway"]
  EGR --> EXT["External service\n198.51.100.10"]
  CTRL["Management / GitOps"] -. "policy versions" .-> EDGE
  OBS["SIEM + flow telemetry"] -. "audit and outcome" .-> EDGE
~~~

**Tất cả IP đều dùng cho tài liệu/lab**, không đại diện mạng thật. Khi triển khai trong sandbox, thay bằng địa chỉ được chỉ định; không scan những dải public trong ví dụ.

### 14.3. Baseline policy giả lập

~~~yaml
# Training policy: conceptual YAML, NOT a vendor firewall CLI.
policy_id: corp-edge
revision: r100
context: corp-prod
address_objects:
  frontend:
    - 10.20.10.0/24
  orders:
    - 10.30.20.0/24
  db:
    - 10.30.5.0/24
  dev:
    - 10.40.0.0/16
rules:
  - id: deny-dev-db
    priority: 10
    source: dev
    destination: db
    protocol: tcp
    ports: [5432]
    action: deny
    enabled: true
    log: true
  - id: allow-front-orders
    priority: 20
    source: frontend
    destination: orders
    protocol: tcp
    ports: [8443]
    action: allow
    enabled: true
    log: true
  - id: allow-front-db
    priority: 30
    source: frontend
    destination: db
    protocol: tcp
    ports: [5432]
    action: allow
    enabled: true
    log: true
  - id: baseline-deny
    priority: 999
    source: any
    destination: any
    protocol: any
    ports: [any]
    action: deny
    enabled: true
    log: true
~~~

**Giả định riêng của lab:** các rules được xét theo **priority tăng dần, first match**, object references được resolve đúng, không có NAT, mọi zone có route theo sơ đồ và policy attached vào đúng traffic path. Đây **không phải semantics phổ quát của cloud security group, Kubernetes NetworkPolicy hay mọi firewall**.

### 14.4. Bộ sự kiện giả lập

~~~json
[
  {
    "id": "C01",
    "time": "2026-11-28T01:00:00Z",
    "actor": "netops-01",
    "ticket": "CHG-100",
    "approved_scope": "frontend->orders tcp/8443",
    "operation": "change_rule_description",
    "rule_id": "allow-front-orders",
    "commit": "success",
    "device_revision": "r101"
  },
  {
    "id": "C02",
    "time": "2026-11-28T02:00:00Z",
    "actor": "netops-02",
    "ticket": null,
    "operation": "set_source",
    "rule_id": "allow-front-db",
    "before": ["10.20.10.0/24"],
    "after": ["0.0.0.0/0"],
    "commit": "success",
    "device_revision": "r102",
    "ha_sync": "unknown"
  },
  {
    "id": "C03",
    "time": "2026-11-28T02:01:00Z",
    "actor": "netops-02",
    "ticket": null,
    "operation": "disable_logging",
    "rule_id": "allow-front-db",
    "before": true,
    "after": false,
    "commit": "success",
    "device_revision": "r103"
  },
  {
    "id": "C04",
    "time": "2026-11-28T02:05:00Z",
    "actor": "automation-ci",
    "ticket": "CHG-101",
    "operation": "add_object_member",
    "object_id": "frontend",
    "before": ["10.20.10.0/24"],
    "after": ["10.20.10.0/24", "10.40.0.0/16"],
    "commit": "requested",
    "device_revision": "r103"
  },
  {
    "id": "C05",
    "time": "2026-11-28T02:10:00Z",
    "actor": "cloud-admin",
    "ticket": "CHG-102",
    "operation": "change_route",
    "route": "orders-subnet",
    "before_next_hop": "firewall-endpoint",
    "after_next_hop": "direct-egress-gateway",
    "commit": "success"
  },
  {
    "id": "C06",
    "time": "2026-11-28T02:20:00Z",
    "actor": "breakglass-01",
    "ticket": "INC-001",
    "operation": "add_temporary_deny",
    "source": "suspect-subnet",
    "destination": "orders",
    "expires_at": "2026-11-28T04:20:00Z",
    "commit": "success"
  },
  {
    "id": "C07",
    "time": "2026-11-28T02:30:00Z",
    "actor": "netops-03",
    "ticket": "CHG-103",
    "operation": "restore_rule_source",
    "rule_id": "allow-front-db",
    "after": ["10.20.10.0/24"],
    "commit": "success",
    "target_revisions": {
      "fw-east-01": "r104",
      "fw-east-02": "r103"
    }
  },
  {
    "id": "C08",
    "time": "2026-11-28T03:00:00Z",
    "actor": "netops-04",
    "ticket": "CHG-104",
    "operation": "delete_deny_rule",
    "rule_id": "deny-dev-db",
    "commit": "failed_validation",
    "device_revision": "r104"
  }
]
~~~

Đây là **sự kiện độc lập phục vụ bài tập**, không giả định mỗi change đều đã merge thành một state duy nhất. Các events **commit=requested** và **failed_validation** không được coi tự động là running changes. Với C07, trạng thái HA không đồng bộ là một finding dù change có ticket.

### 14.5. Cách phân tích C01–C08

| Event | Nhận định sơ bộ | Bằng chứng còn thiếu |
| --- | --- | --- |
| **C01** | Thay description, có ticket, có thể low risk | Ticket scope, running diff đúng only description |
| **C02** | Broad allow source tới DB, thiếu ticket, high/critical review | Zones/routes, rule order, readback/flows, actor approval |
| **C03** | Logging disabled trên DB rule, visibility giảm | Effective logging config, alternate collector, ticket |
| **C04** | Object group expansion được **request**, chưa commit | Approvals, references, actual apply/readback |
| **C05** | Route có thể bypass firewall endpoint | Exact route/attachment, path, owner/approval |
| **C06** | Emergency deny có incident/TTL | Authorized scope, post-review, expiry removal |
| **C07** | Rollback/source restore chưa đồng bộ HA | Active member, per-target state, validation |
| **C08** | Xóa deny **không deploy thành công** theo event | Confirm running config vẫn có deny |

**C02 chưa chắc Internet đến DB** nếu firewall không nằm trên Internet-facing zone/route; tuy nhiên việc mở source=any là một **config risk đáng xử lý**. **C04** cần chú ý references của frontend object tới cả Orders và DB rules nhưng không coi requested là effective.

### 14.6. Dữ liệu giả lập về telemetry hậu thay đổi

~~~json
[
  {
    "id": "F01",
    "time": "2026-11-28T02:11:00Z",
    "source": "synthetic-flow",
    "device": "fw-east-01",
    "src_zone": "partner",
    "dst_zone": "production",
    "dst": "10.30.5.12",
    "dst_port": 5432,
    "action": "allow",
    "matched_rule_id": "allow-front-db",
    "synthetic": true
  },
  {
    "id": "F02",
    "time": "2026-11-28T02:12:00Z",
    "source": "synthetic-application",
    "service": "orders-api",
    "http_status": 403,
    "request_id": "req-002",
    "synthetic": true
  },
  {
    "id": "F03",
    "time": "2026-11-28T02:33:00Z",
    "source": "synthetic-device-readback",
    "devices": {
      "fw-east-01": "r104",
      "fw-east-02": "r103"
    },
    "synthetic": true
  },
  {
    "id": "F04",
    "time": "2026-11-28T02:35:00Z",
    "source": "synthetic-collector-health",
    "collector": "firewall-audit-fw-east-02",
    "healthy": false,
    "synthetic": true
  }
]
~~~

**F01** tăng confidence rằng một flow partner→DB đã được **firewall log allow và match rule ID** tại một device trong lab. Nó **chưa chứng minh đăng nhập DB thành công** hoặc traffic qua member khác. **F02** là HTTP 403 của Orders API, không phải database; không được ghép F02 như bằng chứng DB attack success. **F03/F04** cho thấy HA divergence và telemetry gap, cần phân biệt với absence of change.

### 14.7. Bài toán semantic diff với object expansion

Giả sử C04 sau đó được commit (chỉ **mô phỏng tính toán**, không thực thi firewall):

~~~text
Frontend group before:
  10.20.10.0/24

Frontend group after:
  10.20.10.0/24
  10.40.0.0/16

Referenced by:
  allow-front-orders -> Orders TCP/8443
  allow-front-db     -> DB TCP/5432

Potential newly-allowed:
  Dev subnet -> Orders TCP/8443
  Dev subnet -> DB TCP/5432

Caveat:
  deny-dev-db priority 10 is earlier than allow-front-db,
  so DB path may still be denied in first-match lab policy.
~~~

Đây là lý do cần **ordered rule evaluation**, không kết luận một source được thêm vào group là mọi referenced destinations trở nên reachable. Nếu C08 vẫn failed_validation và deny-dev-db vẫn effective, DB path từ Dev có thể bị deny mặc dù allow-front-db match về điều kiện sau object expansion.

### 14.8. Pseudocode đánh giá cấu hình giả lập

~~~text
function analyzeSyntheticChanges(changes, baseline, approvals, assets):
    stateByTarget = snapshotOf(baseline)
    findings = []

    for change in sortByEventTime(changes):
        if change.commit not in ["success", "active"]:
            findings += notice("not deployed", change.id)
            continue

        if missingRequiredEvidence(change):
            findings += notice("incomplete evidence", change.id)

        for target in change.expectedTargets:
            if not confirmedReadback(target, change):
                findings += warning("unverified target", target)
                continue
            stateByTarget[target] = applyObservedSnapshot(
                stateByTarget[target],
                change.observedAfter
            )

        delta = computeEffectivePolicyDiff(stateByTarget, assets)
        if not approvedScopeCovers(approvals, change, delta):
            findings += finding("approval mismatch", change.id)
        if delta.opensNewSensitivePath:
            findings += finding("new sensitive allow", change.id)
        if delta.lossOfLogging:
            findings += finding("visibility reduced", change.id)
        if not allTargetsSameApprovedRevision(stateByTarget):
            findings += finding("partial deployment", change.id)

    return findings
~~~

Pseudocode giáo dục **không parse mọi vendor grammar** và không tự resolve cloud routing. Đặc biệt **observedAfter** phải đến từ snapshot/readback có xác thực, không được lấy nguyên trường **requested** rồi tự xem là running. Trong thực tế nhiều events không chứa full state; hệ thống phải lưu **unknown** và yêu cầu thu thập bổ sung.

### 14.9. Ma trận test cases

| ID | Đầu vào thử trong offline lab | Kỳ vọng |
| --- | --- | --- |
| L01 | Chỉ đổi description/comment | Không báo sensitive reachability |
| L02 | Source /24 → 0.0.0.0/0 tới DB | High-risk broadening finding |
| L03 | Source /32 → /24 tới public web | Risk theo asset/context, không mặc định Critical |
| L04 | Rule allow đổi từ TCP/8443 sang any | Port-scope widening finding |
| L05 | Disable deny trước broad allow | New possible reachability |
| L06 | Rule reorder làm allow che deny trong ordered policy | Priority/shadow impact |
| L07 | Object group mở rộng, rule text không đổi | Detect transitive impact |
| L08 | Nested address groups | Resolve toàn reference graph |
| L09 | Same membership nhưng đảo thứ tự trong set | Không alert semantic change |
| L10 | Rule bị disable nhưng field service đổi | Ghi change, effective risk đúng |
| L11 | Tắt log trên sensitive allow | Visibility finding |
| L12 | Bỏ IPS inspection profile | Inspection weakening finding |
| L13 | NAT publish backend private | Exposure review theo path |
| L14 | Route table bypass firewall, rule không đổi | Detect topology change |
| L15 | Ticket có ID nhưng scope khác diff | Approval mismatch finding |
| L16 | Emergency change có incident reference + expiry | Ghi exception, đòi post-review |
| L17 | Rule active sau expiry | Expired exception alert |
| L18 | Apply failed validation | Không đánh dấu running change |
| L19 | Commit success nhưng readback thiếu | Mark unverified/evidence gap |
| L20 | HA peer A r104, peer B r103 | Partial deployment finding |
| L21 | Collector fw-east-02 offline | Coverage alert, không coi peer an toàn |
| L22 | Two syslogs cùng commit ID | Dedupe lifecycle, giữ source refs |
| L23 | Two revisions từ cùng actor | Không gộp mất change |
| L24 | Ticket UTC vs device local time | Normalize time trước alert ngoài giờ |
| L25 | Source role hợp lệ nhưng MFA/PAM unknown | Identity confidence thấp |
| L26 | Cloud SG rule không attached | Config risk vs effective exposure tách riêng |
| L27 | SG attachment thay trên database | Effective exposure reassessment |
| L28 | Kubernetes peer selector từ AND thành OR | Expansion finding |
| L29 | Kubernetes policy deleted nhưng CNI không enforce | Chia intent/drift vs dataplane evidence |
| L30 | WAF rule skip mở rộng trên origin | WAF inspection risk, direct-path check |
| L31 | IPv4 deny có nhưng IPv6 allow | Dual-stack policy gap |
| L32 | Positive test passed nhưng negative test unexpectedly allows | Incomplete security validation |
| L33 | Sessions mở trước deny mới | Kiểm tra stateful session behavior |
| L34 | Flow allow trên partner→DB sau rule widening | Impact evidence, chưa chứng minh DB auth success |
| L35 | App 403 sau allow change | Không tự coi firewall failure |
| L36 | Flow metrics 0 khi exporter offline | Coverage gap, không kết luận zero traffic |
| L37 | New NAT IP làm attribution mơ hồ | NAT mapping/time required |
| L38 | Revert full snapshot xóa emergency block | Rollback safety finding |
| L39 | Dynamic FQDN group thay IP không có config event | Membership/drift monitoring cần bổ sung |
| L40 | Policy-as-code PR được duyệt, device runtime khác | Drift finding độc lập approval |

**Đầu ra kỳ vọng** là file báo cáo/worksheet của người học có **risk/severity, confidence, affected contexts, missing evidence, approval decision, containment/reverification plan**, không phải một file cấu hình sẽ áp thẳng lên firewall.

### 14.10. Mẫu báo cáo bài lab

~~~json
{
  "finding_id": "lab-finding-02",
  "related_events": ["C02", "C03", "F01"],
  "target": "fw-east-01/corp-prod",
  "policy_revision": "r103",
  "change_summary": [
    "rule source widened",
    "logging disabled"
  ],
  "risk": "high",
  "confidence": {
    "config_changed": "high",
    "ha_consistency": "unknown",
    "network_path": "partially_verified",
    "application_compromise": "not_established"
  },
  "approval": "not_found",
  "recommended_action": "verify and contain via approved IR process",
  "evidence_refs": ["fw-audit-ref-02", "flow-ref-01"],
  "contains_secrets": false,
  "synthetic": true
}
~~~

### 14.11. Tiêu chí chấm lab

- **Phân biệt requested/committed/running:** không đánh dấu C04/C08 như effective.
- **Semantic accuracy:** tính group references, priority, shadowing, NAT/route.
- **Evidence quality:** không kết luận attacker success chỉ từ flow allow/HTTP 403.
- **Change governance:** ticket scope, actor, expiry và emergency process.
- **Operational safety:** không đề xuất “disable firewall/IPS” hoặc “clear all sessions” như bước mặc định.
- **Coverage:** nêu HA peer/collector missing và alternate paths.
- **Actionability:** có next steps, owner, rollback/positive-negative verification.

## 15. Threat modeling: thay đổi cấu hình firewall là một đường ảnh hưởng an ninh

### 15.1. Những tài sản cần bảo vệ

- **Firewall policy và đối tượng tham chiếu:** rules, groups, service definitions, NAT, routing, zones, inspection profiles.
- **Management plane:** API, CLI, web UI, console, automation runner, IAM/PAM sessions.
- **Source of truth:** Git/IaC repositories, approval/ticket store, change history.
- **Data-plane enforcement:** firewall devices, HA members, cloud firewall endpoints, CNI agents, WAF associations.
- **Network trust boundaries:** Internet, partners, management plane, dev/staging/prod, database, identity systems.
- **Business data/service availability:** ứng dụng có thể lộ dữ liệu hoặc bị deny nhầm.
- **Telemetry và bằng chứng:** audit logs, snapshots, flow logs, IDS/IPS, app traces và SIEM.
- **Recovery capability:** snapshots, rollback plan, per-device version, emergency deny controls.

Threat model phải phân biệt **control plane đã bị chỉnh**, **data plane đã nhận thay đổi** và **đã có hành vi trái quyền**. Ba trạng thái có thể nối tiếp nhưng không tự đồng nhất.

### 15.2. STRIDE áp dụng vào firewall change management

| STRIDE | Kịch bản | Kiểm soát chính |
| --- | --- | --- |
| **Spoofing** | Dùng shared admin account, token giả mạo hoặc thông tin ticket không đúng actor | SSO/MFA, PAM session binding, least privilege, auditable identity |
| **Tampering** | Sửa rule/route/NAT/logging ngoài pipeline, thay config snapshots | RBAC, GitOps, tamper-evident audit, independent readback |
| **Repudiation** | Operator phủ nhận đã mở rule, log không có actor/timestamp | Immutable centralized audit, change IDs, source refs |
| **Information disclosure** | Rule mở rộng làm sensitive service reachable hoặc log config lộ VPN secret | Semantic diff, network segmentation, redacted config backups |
| **Denial of service** | Deny nhầm DNS/identity backend, partial HA sync | Impact analysis, canary, rollback, SLO monitoring |
| **Elevation of privilege** | Caller có quyền sửa nhóm object hoặc cloud attachment để vòng qua review rule | Fine-grained RBAC, admission, approval scope verification |

### 15.3. Ma trận rủi ro theo chuỗi thay đổi

| ID | Rủi ro | Điều kiện cần | Hậu quả tiềm năng | Phòng vệ |
| --- | --- | --- | --- | --- |
| FWT-01 | Admin credential bị dùng trái phép | MFA/PAM/identity yếu, token lộ | Cấu hình bị đổi ngoài quy trình | PAM, MFA, token scope, audit |
| FWT-02 | Any-any allow trong production | Thiết bị/route áp rule | Lateral/external reachability tăng | Semantic diff, high-risk approval, deny tests |
| FWT-03 | Disable deny/logging | Actor có quyền policy | Mất isolation hoặc visibility | Baseline controls, diff alerts, remote audit |
| FWT-04 | Object group expansion | References tới multiple rules | Mở rộng quyền gián tiếp | Object graph diff, asset mapping |
| FWT-05 | Rule reorder/shadowing | Ordered policy và higher-priority match | Deny không còn tác dụng | Rule order analysis, negative tests |
| FWT-06 | NAT/route bypass | Alternate next hop/attachment | Không đi qua gateway/inspection | Route drift, cloud audit, path tests |
| FWT-07 | Cloud SG attachment changed | Resource gắn group rộng | Database/LB exposure | Attachment inventory + IAM |
| FWT-08 | IPv6 rules thiếu | Dual-stack paths | IPv4 deny bị vòng qua IPv6 | Family-specific policy validation |
| FWT-09 | WAF exception quá rộng | Managed rule skip/allow | HTTP threats không được inspect | WAF semantic diff, origin controls |
| FWT-10 | K8s peer selector AND→OR | Labels/namespace semantics | Pods mới được reach dịch vụ | CNI policy simulation + negative tests |
| FWT-11 | HA partial apply | Member lệch revision | Failover thay security posture | HA readback + sync alerts |
| FWT-12 | Session persistence sau deny | Stateful table re-eval không tức thời | Flow cũ tiếp tục | Session-aware containment runbook |
| FWT-13 | Monitoring disabled | Logs/snapshots collector không hoạt động | Thay đổi không được thấy | Independent heartbeat/snapshots |
| FWT-14 | Git drift không được reconcile | CLI hotfix tồn tại | Desired vs runtime lệch lâu | Scheduled drift review, expiry |
| FWT-15 | Backups chứa credentials | Raw snapshot xuất sang SIEM/CI/ticket | Quản trị/VPN keys bị lộ | Config vault/RBAC/redaction |
| FWT-16 | Emergency exception không hết hạn | Ticket thiếu expiry/owner | Temporary broad allow tồn tại | Expiry review/recertification |
| FWT-17 | Automation compromised | CI/CD runner có quyền deploy cao | Mass policy change | Least privilege, PR approval, run attestation |
| FWT-18 | Rollback nhầm full config | Changes hợp lệ sau đó bị revert | Security regression/outage | Targeted diff + independent review |
| FWT-19 | Dynamic FQDN feed bị thay | External feed membership thay | Trust boundary mở không có rule edit | Feed integrity and membership logs |
| FWT-20 | False high-risk alert quá nhiều | Detector không có context | Analyst fatigue, bỏ sót finding thật | Precision tuning + independent coverage tests |

**Risk matrix mô tả điều kiện**, không chứng minh một attacker đã dùng các đường này. Cần forensic evidence để phân biệt cấu hình sai, hoạt động hợp lệ và compromise.

### 15.4. Attack tree theo hướng phòng vệ

~~~mermaid
flowchart TD
  ROOT["Rủi ro: firewall thay đổi\nlàm giảm bảo vệ mạng"] --> Q{"Nguồn thay đổi"}
  Q --> MAN["Manual/API change\nwithout correct approval"]
  Q --> IA["IaC plan/pipeline\nscope or credentials wrong"]
  Q --> REF["Referenced object/NAT/route\nchanges effective path"]
  Q --> GAP["HA/version divergence\nor telemetry unavailable"]
  MAN --> C1["Identity/PAM/audit\nand scope validation"]
  IA --> C2["Peer review, semantic diff,\nleast privilege CI"]
  REF --> C3["Object-graph + path analysis\nand negative tests"]
  GAP --> C4["Per-device readback,\nheartbeat and failover checks"]
  C1 --> IR["SIEM triage, containment,\nrollback and verification"]
  C2 --> IR
  C3 --> IR
  C4 --> IR
~~~

Sơ đồ trình bày **điểm phòng vệ**, không phải hướng dẫn vượt firewall. Mục tiêu là xây controls phân biệt **request, commit, effective path và observed impact**.

### 15.5. Trust boundaries trong quản trị firewall

Những ranh giới thường gặp:

1. **Developer → Git/IaC**: quyền sửa rule objects và code review.
2. **Git runner → Firewall API**: automation token và deploy permissions.
3. **Operator → PAM/jump host → Management plane**: danh tính và audit.
4. **Management plane → HA members/cloud resources**: phân phối config/activation.
5. **Firewall → SIEM**: logs/authenticity và coverage.
6. **Production data plane → External/partner networks**: traffic enforcement.
7. **Forensic backup → Evidence store**: protection of sensitive configs.

Khi một user có quyền thay **address group** nhưng không có quyền sửa rule, họ vẫn có thể làm thay đổi phạm vi rule references—**phân quyền phải xét cả object dependencies**, không chỉ tên API endpoint.

### 15.6. Biện pháp giảm blast radius

- Tách **management networks** khỏi business/user traffic.
- Dùng read-only collector identity khác deployment identity.
- Hạn chế scope API token theo device/context/policy; tránh shared global admins.
- Yêu cầu **peer review** cho changes Tier-0/Tier-1, NAT publication và broad allow.
- Deploy theo **cụm mục tiêu/canary** thay vì toàn cầu khi kiến trúc hỗ trợ.
- Gắn TTL/owner cho temporary exceptions, recertify định kỳ.
- Duy trì **app authentication, NetworkPolicy, host firewall và IAM** để một network allow sai không tự cấp quyền dữ liệu.
- Có independent audit/monitoring cùng plan khôi phục bảo mật.

## 16. Incident response khi phát hiện thay đổi firewall bất thường

### 16.1. Phân cấp phát hiện

| Mức | Ví dụ | Phản ứng |
| --- | --- | --- |
| **Posture drift** | Running config khác Git nhưng không có evidence truy cập | Xác minh change/owner và risk; lập reconciliation |
| **Suspicious unapproved change** | Broad allow, tắt logging, không có approval | Ưu tiên triage, có thể containment theo rủi ro |
| **Confirmed unauthorized policy modification** | Audit/forensic xác nhận actor hoặc automation đổi ngoài quyền | Kích hoạt security incident và preserve evidence |
| **Confirmed exposure/reachability** | Flow/test chứng minh untrusted path mới được allow | Contain path, đánh giá data/app access |
| **Confirmed unauthorized access/use** | App/DB audit ghi hành động trái quyền sau policy change | Full IR, đánh giá dữ liệu/tài nguyên |
| **Telemetry gap** | Collector down/readback thiếu | Coverage incident; không suy không có changes |

Không chờ bằng chứng tấn công thành công mới sửa một **confirmed broad allow nguy hiểm**, nhưng báo cáo phải tách rõ **rủi ro reachability** và **confirmed malicious activity**.

### 16.2. Quy trình điều tra

~~~mermaid
flowchart TD
  A["Alert firewall change"] --> B["Triage: actor, change ID,\nasset and approval"]
  B --> C{"Actual diff verified?"}
  C -- "No" --> D["Collect audit and readback\nper target, mark uncertainty"]
  C -- "Yes" --> E["Semantic diff + route/NAT,\nzone and HA impact"]
  D --> E
  E --> F{"Unauthorized/high risk?"}
  F -- "Yes" --> G["Contain with IR authority\npreserve evidence"]
  F -- "No" --> H["Validate change scope,\napplication and negative tests"]
  G --> I["Investigate flow/IDS/IPS/app audit\ncredential and data impact"]
  I --> J["Targeted fix/rollback\nper target"]
  H --> J
  J --> K["Readback, retest, monitoring,\nclose with owner"]
~~~

### 16.3. Bước 1 — Xác định và bảo toàn evidence

Ghi:

- Event ID, firewall/cluster/account, context/zone, rule UUID.
- Actor/role/PAM session/API credential reference, auth/MFA state.
- Ticket, requester, approver, approved scope, maintenance window.
- Before/after snapshots hoặc diff an toàn, revision/hash, config timestamps.
- HA members, target status, deployment run IDs.
- NAT/route/security group attachment và topology tại **thời điểm change**.
- Flow/IDS/IPS/WAF/DNS/app logs trong cửa sổ liên quan.
- Clock skew, ingestion lag và collector health.

**Không ghi raw VPN private keys, shared secrets hoặc quản trị credentials vào SIEM/ticket** trong quá trình điều tra. Nếu cần raw backup, dùng kho forensic được ủy quyền và hash/checksum để bảo toàn chain of custody theo chính sách.

### 16.4. Bước 2 — Kiểm tra scope và nguyên nhân

Một thay đổi thiếu ticket có thể là:

- Emergency containment đang diễn ra.
- Automation được phê duyệt nhưng ticket sync lỗi.
- Drift bởi operator cấu hình nhầm.
- Vendor/cloud auto-generated policy update.
- Credential abuse hoặc insider misuse.

Không tự kết luận malicious chỉ vì thiếu ticket. Tuy vậy nếu rủi ro cao, **chặn đường nguy hiểm theo thẩm quyền IR** có thể phải ưu tiên hơn việc chờ phân loại intent.

### 16.5. Bước 3 — Containment an toàn

Các lựa chọn:

- Thêm/khôi phục **deny policy hẹp** cho đường trái quyền.
- Thu hẹp source/destination/service scope theo chính sách đã duyệt.
- Ngắt exposure bằng **cloud SG/NACL/firewall/route** hoặc disable một published endpoint.
- Tạm ngưng **automation runner/API token** có dấu hiệu compromise theo quy trình.
- Giới hạn **privileged admin access**, bắt buộc PAM review.
- Khôi phục logging/IDS/IPS bị tắt và giám sát nguồn thay thế.
- Với app/DB access trái quyền, áp authorization/IAM containment ở tài nguyên đích.

**Không xóa toàn bộ firewall rules, disable firewall, clear all sessions hoặc rollback full config không kiểm soát** như bước phản xạ. Những thao tác đó có thể mở đường khác, ngắt dịch vụ quan trọng hoặc xóa emergency protection.

### 16.6. Bước 4 — Targeted rollback

Rollback cần:

1. Xác định **revision trước thay đổi** và mọi changes hợp lệ sau đó.
2. Dựng **reverse semantic diff** cho rule/object/NAT/route liên quan.
3. Kiểm tra dependencies và ownership.
4. Xin approval theo IR/change authority.
5. Áp lần lượt từng target/HA member hoặc atomic unit được vendor hỗ trợ.
6. Readback cấu hình **trên mọi target**.
7. Chạy **positive/negative flow tests** và app/identity/DNS health.
8. Xác minh existing sessions nếu có yêu cầu containment.
9. Lưu evidence và cập nhật Git/source of truth.

**Rollback không nhất thiết phải trả mọi thiết bị về cùng snapshot cũ** nếu các changes khác đã xảy ra; chọn những sửa đổi cần thiết, không đạp lên fixes bảo mật khác.

### 16.7. Bước 5 — Đánh giá impact

Hỏi:

- Rule mới **có được apply và trên đường route nào**?
- Trong khoảng exposure, **flow sources/destinations** nào được phép?
- Có IPS/IDS/WAF alerts hoặc application auth failures/successes nào?
- Có bằng chứng **đọc/sửa dữ liệu, đăng nhập thành công hoặc privilege change** không?
- Có DLP/data export incident do egress path bypass không?
- Những workloads/tenants/regions/HA nodes nào bị ảnh hưởng?
- Có outage, dropped requests, retry storms hoặc SLA breaches không?

Kết luận nên phân lớp: **policy gap**, **network exposure**, **unauthorized request**, **confirmed data access** và **known data loss**—không gộp thành một nếu bằng chứng không đủ.

### 16.8. Bước 6 — Hậu kiểm

Sau remediation:

- Cập nhật detection cho root cause/semantics đã bị bỏ sót.
- Điều chỉnh PAM/RBAC/IaC review và rule ownership/expiry.
- Bổ sung snapshot source độc lập nếu log bị mất.
- Thử lại deny/allow paths sau HA failover, IPv6 và cloud route changes.
- So approved scope với actual diff và phát hiện mismatches.
- Đo **time to detect/contain**, false positive và telemetry gaps.
- Ghi các giới hạn chứng cứ/các dấu hiệu không thể kết luận.

### 16.9. Mẫu incident handoff

~~~text
Incident: FW-CHANGE-EXAMPLE-001
Finding: Unapproved source expansion on sensitive DB rule
Change: rule-prod-db-001 / r41 -> r42
Affected policy context: corp-prod-vdom
Actor: ops-user-17 (PAM session ref; validation pending)
Approval: no matching ticket found
Effective state: fw-east-01 verified; fw-east-02 unknown
Traffic: partner -> DB TCP/5432 ALLOW observed on fw-east-01
Business action: no confirmed DB login/data access yet
Containment: narrow source via authorized emergency change
Rollback: per-target diff and readback planned
Evidence: audit/config/flow refs, no raw secrets
Owner: network + security incident commander
Open questions: route scope, other HA peer, sessions, data audit
~~~

Bản handoff có thể dùng **unknown/pending** thay vì suy đoán; điều đó làm quyết định containment và forensic có cơ sở hơn.

## 17. Tình huống vận hành: phát hiện đúng thay đổi, tránh kết luận vội

### Tình huống A — Rule allow mở rộng từ một subnet sang mọi nguồn

Một operator sửa source của rule kết nối database từ 10.20.10.0/24 thành 0.0.0.0/0 và commit thành công. SIEM báo Critical ngay rằng “Database hiện public Internet”.

**Phân tích:** đây là **high-risk policy widening**, nhưng tuyên bố Internet exposure cần kiểm **source zone, rule priority, route, NAT, SG và policy attachment**. Hành động đúng là đối chiếu ticket, readback trên target, đánh giá đường mới và containment phù hợp. Nếu route từ Internet không tồn tại, finding vẫn cần xử lý vì rule quá rộng nhưng **không gọi confirmed public exposure**.

### Tình huống B — Một address group được thêm subnet, rule list không đổi

Object **app-frontends** vừa thêm network của một môi trường test, còn rule allow vào production database vẫn không đổi text.

**Phân tích:** diff rule-only bỏ sót thay đổi. Semantic diff cần **resolve group membership, nested objects và tất cả references**. Sau đó đánh giá rule order/deny và routes; không tự cho rằng subnet mới có thể truy cập nếu còn một deny ưu tiên hơn.

### Tình huống C — Rule mới bị một rule khác che

Admin thêm allow TCP/443 cho frontend, nhưng một deny theo zone đứng trước trong firewall ordered first-match. Ticket đã đóng vì commit success nhưng ứng dụng tiếp tục timeout.

**Phân tích:** cần **policy order/shadowing analysis, matched-rule logs và positive connectivity test**. Không mở source=any để “tạm sửa”; điều chỉnh rule/zone đúng qua change approval rồi kiểm tra negative tests.

### Tình huống D — Cloud security group attachment làm thay đổi exposure

Một SG vốn có allow TCP/5432 từ partner CIDR được chuyển sang gắn vào database instance. Không hề có API event thêm/sửa rule, chỉ có **attachment change**.

**Phân tích:** monitor chỉ SG rule mutations sẽ bỏ sót. Tính lại **effective SG rules + resource attachment + NACL + VPC route**, xem database auth và sự kiện truy cập. Alert cần ghi cả **resource ID, account/region và actor**.

### Tình huống E — Route bypass egress gateway nhưng policy không đổi

Một VPC route table đổi next hop từ network firewall endpoint sang direct NAT gateway. Egress rule vẫn đúng, nhưng data plane có thể không đi qua firewall/DLP.

**Phân tích:** cần **topology drift**, network path tests và VPC flow logs, không chỉ diff firewall rules. Chặn direct route nếu governance yêu cầu egress qua gateway; xác định những luồng dữ liệu đã đi qua path mới và controls ở ứng dụng.

### Tình huống F — HA sync không đồng đều

Manager báo policy r205 đã apply, member active có r205 nhưng standby còn r204. Trong failover có thể xuất hiện allow/deny khác.

**Phân tích:** yêu cầu **per-member readback, sync alerts, failover readiness**. Đừng coi một commit successful trên manager là nghiệm thu xong; rollback hoặc sync theo vendor runbook sau khi xác định scope. Không thử failover production tùy tiện.

### Tình huống G — Deny rule mới nhưng TCP connection cũ vẫn chạy

Security phát lệnh deny một source đang mở kết nối lâu dài. Sau commit, flow data vẫn xuất hiện trong session đã thiết lập trước change.

**Phân tích:** firewall stateful có thể không re-evaluate mọi existing sessions lập tức. Cần kiểm tra **session age, re-evaluation semantics và containment yêu cầu**, không vội kết luận rule bị bypass. Nếu cần xóa phiên, chỉ thao tác đúng sessions với IR authority, không clear all.

### Tình huống H — Tắt logging trên một allow rule

Rule đến production secrets manager tiếp tục allow, nhưng flag log chuyển true→false. Hệ thống kiểm compliance chỉ xem allowed CIDRs nên báo không có thay đổi quan trọng.

**Phân tích:** đây là **visibility reduction**, có thể nghiêm trọng dù không đổi network reachability. Phát hiện log settings/security profile diff, xem actor/approval và kiểm tra **remote audit, collector heartbeat** trước khi kết luận không có traffic.

### Tình huống I — Log collector chết đúng lúc deploy

IaC pipeline ghi firewall deploy success, nhưng syslog của một thiết bị im lặng 20 phút. SOC dashboard chỉ hiển thị zero changes từ thiết bị đó.

**Phân tích:** **zero events ≠ zero changes**. Bật health alert, API readback từ independent collector, so controller audit và version. Ghi coverage gap, không gán mức compliance PASS cho thiết bị chưa xác minh.

### Tình huống J — Ticket có nhưng diff rộng hơn approval

Ticket cho phép app-server /32 kết nối Orders API TCP/8443 trong 2 giờ. Rule thực tế source=any, port=any và schedule=always.

**Phân tích:** ticket ID hợp lệ không đồng nghĩa **scope hợp lệ**. Detector phải so **actor, target, source/dest/ports, schedule và expiry**. Ưu tiên remediation/containment theo rủi ro; yêu cầu review lại thay đổi.

### Tình huống K — Emergency deny chưa được đưa về Git

Incident commander yêu cầu tạm chặn một CIDR. Admin áp rule khẩn trực tiếp, nhưng desired Git không có. Drift monitor tự động muốn xóa rule vì khác source of truth.

**Phân tích:** emergency containment có thể hợp lệ và quan trọng. Cần **incident reference, expiry và reconciliation process**; không auto-revert blindly. Update source of truth sau khi review, không để ngoại lệ tồn tại vô chủ.

### Tình huống L — Auto-generated WAF managed ruleset update

Nhà cung cấp cập nhật managed WAF rule set, không có ticket nội bộ. Một API endpoint bắt đầu trả 403 do false positive.

**Phân tích:** auto-update có thể nằm trong **vendor maintenance policy**, không mặc định unauthorized. Theo dõi vendor ruleset version, WAF actions, matched rule IDs, application SLO, false positives; đặt exception hẹp có owner/expiry, không tắt toàn bộ WAF.

### Tình huống M — Kubernetes NetworkPolicy AND thành OR

Một developer tách namespaceSelector và podSelector từ cùng network peer thành hai entries riêng. Review text tưởng chỉ là định dạng.

**Phân tích:** semantics có thể đổi từ **AND sang OR**, mở rộng tập nguồn. Monitor AST/structured diff và kiểm tra Pod/namespace labels, CNI enforcement; chạy negative tests. Không dùng “một YAML field thay đổi” làm đơn vị đánh giá risk.

### Tình huống N — Policy được tạo nhưng CNI không thực thi

Kubernetes API chấp nhận NetworkPolicy default-deny trong một cluster, nhưng CNI không hỗ trợ feature này hoặc policy agent lỗi. Test từ Pod không đáng tin vẫn kết nối được.

**Phân tích:** phải tách **intent** và **data-plane enforcement**. Readback Kubernetes API chưa đủ; xem CNI compatibility, agent health, actual connection result và cloud/host controls. Không báo đã đạt isolation khi negative test fail.

### Tình huống O — IPv6 không được cập nhật song song

IPv4 rule thu hẹp từ any thành approved subnet, nhưng IPv6 rule tương đương vẫn allow ::/0; DNS có AAAA record.

**Phân tích:** dual-stack phải review **hai families**, route, object references và flow/test. Một IPv4-only scanner không chứng minh deny trên IPv6.

### Tình huống P — Rule zero hit count nhưng vẫn cần cho DR

Rule TCP/443 phục vụ disaster recovery replication có hit count bằng 0 trong tháng bình thường. Bộ governance tự đề xuất xóa.

**Phân tích:** zero hit có thể do **traffic hiếm, counters reset, flows ở member khác hoặc DR chưa kích hoạt**. Cần owner/business continuity review, thử DR trong sandbox/game day và TTL/recertification, không auto-delete.

### Tình huống Q — Rollback full config xóa một emergency block

Một operator khôi phục snapshot trước deploy gây lỗi DNS, nhưng snapshot đó chưa có emergency block vừa được SOC đặt để ngăn một source đáng ngờ.

**Phân tích:** rollback full config có thể gây **security regression**. Dựng targeted reverse diff, kiểm tất cả changes sau snapshot, phối hợp IR và nghiệm thu block còn hiệu lực sau rollback.

### Tình huống R — Proxy/WAF báo deny nhưng application trả 200

Một request qua WAF bị 403, nhưng ứng dụng ghi một request khác từ cùng source IP trả 200. Team kết luận WAF bị bypass.

**Phân tích:** phải kiểm tra **request ID, route, timestamp, NAT/IP sharing, headers có trust được không, direct-to-origin path và resource**. Cùng source IP không đủ chứng minh đó là cùng request. Có thể là retry, request hợp lệ khác hoặc direct path cần điều tra.

### Tình huống S — Device audit ghi unapproved operator nhưng thực ra là PAM identity mismatch

Firewall chỉ ghi local shared admin username, trong khi PAM session logs ghi từng operator. Detector báo “unknown actor” dù thao tác có approval hợp lệ.

**Phân tích:** tăng **actor attribution quality** bằng PAM/session ID và management login correlation; không suy cá nhân từ shared account hay jump-host IP. Dù thao tác hợp lệ, shared admin credentials vẫn là risk cần giảm.

### Tình huống T — Dynamic FQDN object đổi IP mà không có rule edit

Một allow rule dùng dynamic FQDN object. DNS/feed resolution đổi IP membership, khiến traffic giờ có thể đi tới host khác, nhưng diff static config không đổi.

**Phân tích:** cần snapshot **resolved memberships theo thời gian**, feed authenticity và destination identity. Network reachability được mở rộng có thể không xuất phát từ administrator rule change; vẫn cần governance và alert theo giá trị/tài sản đích.

### Tình huống U — DLP gateway tạm rớt khỏi đường egress

Sau một thay đổi NAT, dữ liệu outbound từ application vẫn tới SaaS nhưng proxy DLP logs gần như zero. Cloud flow cho thấy NAT connection tăng.

**Phân tích:** có thể **egress bypass** hoặc telemetry exporter mất. Kiểm tra app route/attachment/CNI/cloud telemetry, collector health và data-classification controls. Không khẳng định secret đã rò chỉ từ NAT bytes; nếu path trái policy, containment có thể cần trước khi forensic xong.

### Tình huống V — Rule rủi ro cao nhưng chưa được commit

Một change plan đề xuất open TCP/22 từ Internet, reviewer phát hiện và từ chối. SIEM thấy IaC plan chứa 0.0.0.0/0:22 rồi báo “SSH public exposure”.

**Phân tích:** đây là **prevented risky proposal** chứ chưa là applied exposure nếu commit/attachment thực không thay. Cần lưu finding cho prevention/governance, xác minh runtime snapshot, tránh tạo incident breach sai.

### Tình huống W — Mất thông tin NAT làm quy nhầm nguồn

Flow log external service thấy một NAT public IP và source port, SOC gắn toàn bộ traffic cho một Pod đang có egress. Vài trăm Pods cùng NAT gateway.

**Phân tích:** bắt buộc dùng **NAT/session mapping, Pod UID/IPAM time window và per-source telemetry**, không dùng NAT IP như principal. Nếu dữ liệu không có, ghi attribution **unknown**.

### Tình huống X — Thay đổi đúng scope nhưng SLO suy giảm

Một firewall rule mới cho thêm TLS inspection profile theo ticket, nhưng CPU proxy tăng và ứng dụng latency vọt lên.

**Phân tích:** security intent có thể đúng nhưng **availability impact** vẫn chưa đạt nghiệm thu. Tương quan config diff, session rate, CPU/memory, TLS handshake failures và app p95; xử lý bằng capacity/tuning/rollback đã review, không tắt toàn bộ security inspection vô điều kiện.

## 18. Checklist triển khai theo dõi thay đổi cấu hình firewall

### 18.1. Inventory và quyền sở hữu

- [ ] Có danh sách **physical/virtual firewalls, cloud firewall policies, SG/NACL, WAF, Kubernetes clusters/CNI policies** thuộc phạm vi.
- [ ] Mỗi thiết bị/tài nguyên có **business owner, operator, security owner, environment và sensitivity tier**.
- [ ] Lưu **vendor/version, HA members, policy context, zone/VRF/VPC/tenant/account**.
- [ ] Biết rõ **cấu hình nào là source of truth**, nơi chứa desired và running state.
- [ ] Có snapshot/index cho rule IDs, address/service objects, group memberships, NAT, routes, logging/inspection.
- [ ] Mọi temporary exceptions có **reason, owner, start/end time và recertification**.
- [ ] Quyền thay rule/object/route/logging được review cùng PAM/IAM/RBAC.
- [ ] Không dùng shared admin identity nếu có thể; có MFA/PAM correlation.

### 18.2. Thu thập dữ liệu và coverage

- [ ] Firewall manager/device **audit events được gửi về collector xác thực**, có event IDs.
- [ ] IaC/Git/code review/apply logs được lưu với commit/revision/ticket refs.
- [ ] Có **periodic read-only running config snapshot** ở mức phù hợp với risk.
- [ ] Cloud audit bao gồm **security rules, resource attachments, routes, NAT và WAF policy associations**.
- [ ] Kubernetes audit theo **NetworkPolicy/labels/namespace/CNI config** đúng phạm vi.
- [ ] HA/version sync và deployment failure states có monitoring.
- [ ] Data-plane flow/IDS/IPS/WAF logs có source/target mapping khi sản phẩm hỗ trợ.
- [ ] Collector heartbeat, ingestion delay, clock skew và silent-device alerts hoạt động.
- [ ] Các blind spots **IPv6, private peering/VPN, hostNetwork, secondary interface, direct-to-origin** được review.
- [ ] Config snapshots/logs không lộ **VPN keys, local credential secrets hay private keys** trong SIEM.

### 18.3. Diff và risk

- [ ] Diff engine phân biệt **text, structural, semantic, topology và effective** changes.
- [ ] Resolve **nested address/service groups, dynamic memberships, rule references**.
- [ ] Biết policies nào **ordered** và policies nào **additive**, không dùng một thuật toán chung.
- [ ] Phân tích **newly allowed và newly denied** theo zones, NAT, route và attachments.
- [ ] Đánh dấu broad source/dest/service, sensitive ports, removed denies, IPS/logging disabled.
- [ ] Kiểm tra scope **ticket vs actual fields**, không chỉ có ticket ID.
- [ ] Có severity **và** evidence confidence riêng.
- [ ] Change requested/failed validation không bị gắn nhãn đã active.
- [ ] Có risk review cho **approved-but-risky** và emergency exceptions.
- [ ] Diff noise do comments/order set/no-op reconciliation được quản lý mà không che semantic risk.

### 18.4. Triển khai và kiểm chứng

- [ ] Mọi change rủi ro cao có approved plan, rollout/rollback owner và window.
- [ ] Đã readback **mỗi target/HA member/cloud resource** sau apply.
- [ ] Có negative tests cho untrusted source/management port/IPv6/private path theo risk.
- [ ] Có positive tests cho approved apps và critical dependencies.
- [ ] Theo dõi **session state** trên firewall stateful khi containment cần hiệu lực ngay.
- [ ] Chỉ kết luận rule effective khi có bằng chứng về **attachment/route/capture path** phù hợp.
- [ ] SLO, flow allow/deny/IPS alerts được so trước/sau change.
- [ ] Partial deployment, failover difference và rollback regressions có runbook.
- [ ] Không disable firewall/IPS hoặc open all để sửa lỗi chưa rõ.

### 18.5. Vận hành SOC/NOC/IR

- [ ] Detection rules nhận biết **unapproved changes, broad allow, tắt logging, object expansion, route bypass, SG attachment, expired rule**.
- [ ] Alerts có **device/context, actor, ticket, before/after, criticality, revision, confidence, next action**.
- [ ] Collector outage được coi là coverage incident, không tự hiểu zero change.
- [ ] Có **triage/on-call SLA**, change owner và security incident escalation.
- [ ] Có protocol preserve evidence, hạn chế lưu raw secrets trong ticket.
- [ ] Rollback theo **targeted semantic diff** và review changes xảy ra sau snapshot.
- [ ] Báo cáo rõ **configuration gap, reachability, unauthorized request, confirmed action/data loss**.
- [ ] Sau remediation, readback, negative tests và app SLO đều được xác minh.
- [ ] Có review định kỳ alert precision, false negatives và ownerless exceptions.

### 18.6. Ma trận nghiệm thu

| Kiểm tra | Evidence | PASS khi |
| --- | --- | --- |
| **Audit source** | Device/controller/cloud API logs | Có actor/time/context, không thiếu targets |
| **Change scope** | Structured before/after + approved ticket | Actual change nằm trong approved fields |
| **Semantic diff** | Expanded objects, rule order, NAT, route | Không bỏ sót quyền thay gián tiếp |
| **Running state** | Per-target config hash/revision | Target nhận đúng revision, HA không lệch |
| **Effective path** | Topology/attachments + tests | Rule áp đúng traffic path |
| **Security negative test** | Untrusted source/port results | Traffic phải chặn vẫn bị chặn |
| **Availability positive test** | Health/probe/SLO | Luồng nghiệp vụ hợp lệ vẫn hoạt động |
| **DLP/inspection** | Security profile/logs/coverage | Không bị vô hiệu hóa trái yêu cầu |
| **Governance** | Actor/PAM/ticket/owner/expiry | Không có exception vô chủ/quá hạn |
| **Observability** | Collector heartbeat, timestamps, flow audit | Không có vùng mù chưa được chấp nhận |
| **Recovery** | Targeted rollback/readback evidence | Có thể khôi phục an toàn không mất controls hợp lệ |

**Nghiệm thu không kết thúc ở “commit thành công”**: phải có readback và các phép thử **đúng tầng**. Một policy đúng về cấu hình nhưng không nằm trên route không phải enforcement; và một flow bị chặn ở lớp khác không chứng minh chính firewall target đã chặn.

## 19. Bài tập thiết kế và câu hỏi ôn tập

### 19.1. Bài tập kiến trúc: chương trình firewall change monitoring toàn tổ chức

Tình huống:

~~~text
Sites and systems:
  Datacenter east:
    HA firewall pair, IPS profiles, VPN to on-prem partner
  Cloud region A:
    Network firewall, security groups, NACLs, NAT, transit gateway
  Cloud region B (DR):
    Independent firewall/route policy revision
  Kubernetes:
    Two clusters with different CNI vendors
  Web:
    WAF at ingress CDN/Gateway

Applications:
  Tier-0 identity service
  Tier-1 payment/orders databases
  Tier-2 web APIs
  Dev/test workloads

Change sources:
  GitOps/IaC + manual emergency admin via PAM
  Cloud API and Kubernetes API
  Vendor-managed WAF ruleset updates

Detection:
  SIEM with flow/IDS/IPS and application SLO
  Config snapshot collector
~~~

Yêu cầu:

1. Vẽ **data-flow và trust-boundary diagram** giữa management plane, IaC, devices, telemetry và SIEM.
2. Tạo **asset inventory** cho mỗi firewall/cloud SG/Kubernetes cluster/WAF với owner, context, sensitivity.
3. Định nghĩa **event schema** đủ actor, ticket, before/after, target, version, effective state.
4. Thiết kế **semantic diff** cho nested address groups, priority changes, NAT/route and attachments.
5. Phân biệt **ordered firewall, additive Kubernetes NetworkPolicy và stateful cloud SG**.
6. Viết logic phát hiện **broad allow, deny removed, logging/IPS weakened, approval mismatch, expired exceptions**.
7. Thiết kế **drift reconciliation** cho emergency hotfix khi Git chưa cập nhật.
8. Đề xuất **risk score** theo Tier-0/Tier-1, exposure, reachability và evidence confidence.
9. Xác minh **per-HA member revision** và failover readiness.
10. Tạo **positive/negative test plan** cho frontend→Orders, dev→DB, partner→management, IPv6.
11. Chỉ rõ khi nào **flow allow chưa chứng minh application authorization**.
12. Đề xuất monitoring cho **cloud SG attachment và transit route bypass** dù firewall rule không đổi.
13. Phân tích một **WAF automatic update** gây 403 trong maintenance window.
14. Đặt **SLO về coverage/MTTD/MTTA/effective verification** và đo false positives.
15. Thiết kế **incident rollback** không xóa emergency deny hoặc mất telemetry.
16. Mô tả **config backup hygiene** để không đưa secrets vào SIEM.
17. Lập kế hoạch **periodic recertification** các rules ít dùng hoặc có TTL.
18. Phân tích một **HA split-version** cùng một source IP có NAT khiến forensic phức tạp.

**Tiêu chí đạt:** có thể truy từ **change request → actor/approval → semantic diff → effective path → observed behavior → rollback/verification**, biết chỗ thiếu evidence và không tự kết luận data breach chỉ từ network allow.

### 19.2. Câu hỏi tự kiểm tra

**Câu 1.** Firewall configuration change monitoring là gì?

*Gợi ý:* Thu thập, đối chiếu và xác minh thay đổi chính sách/đối tượng/route cùng actor, approval và tác động.

**Câu 2.** Vì sao một commit success không chứng minh policy đã được thực thi trên toàn traffic?

*Gợi ý:* Có thể thiếu HA sync, attachment, route hoặc data-plane installation.

**Câu 3.** Candidate config và running config khác nhau thế nào?

*Gợi ý:* Candidate là thay đổi chờ hoặc đang được chuẩn bị; running là cấu hình thực tế đã áp trên target theo sản phẩm.

**Câu 4.** Vì sao không chỉ monitor số rule mới?

*Gợi ý:* Rule cũ có thể đổi object group, priority, logging, NAT, zone hoặc attachment.

**Câu 5.** Một comment đổi trong policy có cần alert Critical không?

*Gợi ý:* Không nếu chỉ metadata và semantics không đổi; vẫn cần audit theo governance.

**Câu 6.** Address group thêm một subnet tác động tới bao nhiêu rules?

*Gợi ý:* Có thể tất cả rules tham chiếu trực tiếp hoặc gián tiếp; cần object graph.

**Câu 7.** Vì sao rule name không phải định danh duy nhất đáng tin?

*Gợi ý:* Name có thể đổi/trùng/tái sử dụng; cần stable ID + context/revision.

**Câu 8.** Trong firewall ordered first-match, rule priority quan trọng thế nào?

*Gợi ý:* Rule trước có thể che rule sau, làm allowed/denied tập thay dù fields không đổi.

**Câu 9.** Có được áp “first match” cho Kubernetes NetworkPolicy chuẩn không?

*Gợi ý:* Không. Policies thường là additive allowlist.

**Câu 10.** Một cloud SG rule không attached có gây exposure thật ngay không?

*Gợi ý:* Không chắc. Cần resource attachment, route và các controls khác.

**Câu 11.** Vì sao SG attachment change cần monitor?

*Gợi ý:* Effective access có thể đổi dù rule text không đổi.

**Câu 12.** Network ACL stateless khác stateful firewall ở điểm nào?

*Gợi ý:* Thường cần xét ingress/egress return traffic, ephemeral ports và thứ tự rules.

**Câu 13.** Một WAF rule thay đổi có chặn direct-to-origin path không?

*Gợi ý:* Chỉ requests qua WAF chịu policy đó; origin phải được bảo vệ riêng.

**Câu 14.** NAT thay đổi làm forensic sai nguồn ra sao?

*Gợi ý:* External log có thể chỉ thấy shared translated IP; cần session mapping/time.

**Câu 15.** Vì sao “source=any” chưa tự chứng minh Internet exposure?

*Gợi ý:* Zone, route, NAT, attachment, earlier rules và other firewalls quyết định actual path.

**Câu 16.** NewlyAllowed khác observed allow flow ra sao?

*Gợi ý:* Một cái là tập traffic có thể được phép theo model, cái kia là sự kiện kết nối được ghi.

**Câu 17.** Vì sao logging disabled cần alert dù allow/deny không đổi?

*Gợi ý:* Mất visibility/detection/forensic evidence.

**Câu 18.** Approval ticket ID có đủ chứng minh change được phép không?

*Gợi ý:* Không. Actual diff phải nằm trong scope/target/time/owner approved.

**Câu 19.** Emergency rule ngoài Git có luôn phải rollback ngay không?

*Gợi ý:* Không. Có thể là containment đang có hiệu lực; cần incident context và sync source of truth.

**Câu 20.** Drift detection cần làm gì khi Git và running khác?

*Gợi ý:* Xác minh actor/incident/timestamp/effective state trước reconcile; không overwrite mù.

**Câu 21.** Vì sao “no syslog” không đồng nghĩa “no change”?

*Gợi ý:* Collector, device logging hoặc đường truyền có thể lỗi; cần heartbeat và nguồn độc lập.

**Câu 22.** HA peers khác revision gây nguy cơ gì?

*Gợi ý:* Traffic/failover có thể nhận quyết định khác nhau.

**Câu 23.** Một firewall stateful đã deny rule mới, existing session có bắt buộc đóng ngay không?

*Gợi ý:* Tùy session re-evaluation; cần xem sản phẩm và quyền xử lý sessions.

**Câu 24.** WAF auto-update không có ticket có luôn là unauthorized không?

*Gợi ý:* Không. Có thể thuộc approved vendor maintenance; vẫn cần version/SLO impact monitoring.

**Câu 25.** Vì sao một flow TCP/443 ALLOW không chứng minh API action được phép?

*Gợi ý:* Application/TLS identity/resource authorization có lớp kiểm soát riêng.

**Câu 26.** Một negative test bị cloud SG deny có chứng minh firewall bên trong đã deny không?

*Gợi ý:* Không. Nó chứng minh end-to-end deny tại một lớp; để chứng minh target cần evidence ở target.

**Câu 27.** Vì sao cần ghi event time và ingestion time?

*Gợi ý:* Để xử lý clock skew, log delay, ordering và đo detection latency.

**Câu 28.** Thay đổi FQDN dynamic address group có thể xảy ra mà không sửa rule không?

*Gợi ý:* Có, khi resolved membership/feed thay; monitor effective set theo thời gian.

**Câu 29.** Một rule có hit count 0 có thể xóa ngay không?

*Gợi ý:* Không, có thể dành DR/traffic hiếm hoặc counters reset.

**Câu 30.** Các trường nào không nên gửi trong full config snapshot lên SIEM?

*Gợi ý:* Raw VPN secrets, private keys, auth tokens, credential hashes và dữ liệu quản trị nhạy cảm.

**Câu 31.** Actor source IP ở jump host có xác định chắc admin cá nhân không?

*Gợi ý:* Không. Cần PAM/session identity/MFA and audit correlation.

**Câu 32.** Vì sao risk severity khác evidence confidence?

*Gợi ý:* Một config gap có thể rủi ro cao trong khi effective path chưa được xác minh.

**Câu 33.** NetworkPolicy peer từ namespaceSelector+podSelector cùng item chuyển sang hai items sẽ ra sao?

*Gợi ý:* Có thể đổi AND sang OR, mở rộng nguồn; kiểm chứng labels/namespace.

**Câu 34.** IPv4 deny có mặc định chặn IPv6 traffic không?

*Gợi ý:* Không. Cần kiểm tra family-specific rules/routing.

**Câu 35.** Rollback full snapshot có thể gây vấn đề gì?

*Gợi ý:* Xóa các changes hợp lệ/emergency block đã được áp sau snapshot.

**Câu 36.** MTTD và MTTA đo gì?

*Gợi ý:* Độ trễ phát hiện meaningful change và thời gian analyst acknowledgment, với timestamp definitions rõ.

**Câu 37.** Vì sao không có flow IDS không chứng minh một rule mở rộng an toàn?

*Gợi ý:* Rule có thể chưa được sử dụng, sensor không nằm trên path hoặc exporter lỗi.

**Câu 38.** CI/GitOps approval có đủ để không cần drift scan không?

*Gợi ý:* Không. Manual/API hotfix, vendor/cloud changes hoặc automation drift vẫn có thể xảy ra.

**Câu 39.** Khi F01 log partner→DB ALLOW, có thể kết luận DB login thành công không?

*Gợi ý:* Không. Cần authentication/application/database audit.

**Câu 40.** Điều kiện cơ bản để đóng finding thay đổi firewall nguy hiểm là gì?

*Gợi ý:* Root cause/scope rõ; quyền/approval và effective state được xác minh; đường sai bị thu hẹp/khôi phục; positive-negative tests, HA sync, SLO và evidence đạt.

### 19.3. Phân tích nhật ký giả lập

~~~text
08:00Z CHG-202 approved frontend->Orders TCP/8443
08:05Z IaC plan shows frontend->Orders TCP/8443
08:06Z Apply API reports success
08:07Z Device A readback r220
08:07Z Device B readback r219
08:09Z New allow flow: partner-zone->Orders TCP/8443 on Device A
08:10Z Orders API returns HTTP 403 for request ID req-100
08:11Z SIEM detects changed object group now includes partner-zone
08:12Z Collector Device B heartbeat missing
~~~

**Yêu cầu phân tích:**

1. Vì sao approval lúc 08:00 chưa đủ cho một source **partner-zone**?
2. Sự kiện nào cho thấy **HA partial deployment**?
3. Có thể kết luận partner đã đọc dữ liệu Orders không khi API trả 403?
4. Làm sao object group thay đổi làm traffic newly allowed dù IaC plan chỉ thấy một rule?
5. Collector Device B im lặng ảnh hưởng confidence ở điểm nào?
6. Những negative tests nào cần chạy khi quyền và scope đã được phê duyệt?
7. Nếu route NAT làm partner source bị biến đổi, cần evidence bổ sung gì?
8. Lập một SIEM finding có severity, confidence, asset owner, effective state và next action.

**Đáp án định hướng:** Device A/B khác revision nên chưa thể tuyên bố toàn HA đã sync. Partner→Orders flow là tín hiệu mở đường hoặc policy khác đang allow, cần matched-rule/route evidence. HTTP 403 không chứng minh data disclosure, và có thể phản ánh app authorization đang chặn đúng. Source group mở rộng phải được so với approved scope. Collector im lặng đòi independent readback; không suy Device B không có changes.

## 20. Tổng kết

- **Theo dõi firewall change không chỉ là đếm rule edits**. Cần giám sát **rule/object/NAT/zone/route/inspection/logging/attachment/HA changes** và các đường gián tiếp ảnh hưởng traffic.
- Tách rõ **request/desired/candidate/running/effective/data-plane state**. Một ticket, IaC plan hoặc commit success **không tự chứng minh** policy đã thực thi trên mọi thiết bị và traffic path.
- **Semantic diff** phải resolve address/service groups, rule order/priority, zones, dynamic memberships và topology; chỉ text diff có thể bỏ sót thay đổi quyền quan trọng.
- **Risk scoring phải gắn với trust boundary, asset criticality, source/destination/service scope, approvals và evidence confidence**, chứ không chỉ CIDR rộng hay số dòng thay.
- **Cloud security group/NACL, WAF, Kubernetes NetworkPolicy và service mesh policy có semantics khác nhau**. Không áp một bộ suy luận first-match hoặc deny/allow cho mọi nền tảng.
- Thu thập **device/controller/cloud/Kubernetes audit, IaC/Git, PAM, config snapshots, CNI/VPC/flow, IDS/IPS/WAF và application health** để liên kết actor–change–outcome.
- **Flow allow không tự chứng minh app authorization hoặc data breach**, và thiếu logs có thể là **telemetry gap**, không phải không có traffic.
- **HA divergence, existing sessions, dynamic FQDN objects, NAT translation, IPv6 và direct route bypass** là những lý do phải kiểm tra chính sách ở data plane thay vì chỉ UI cấu hình.
- **Change control** cần ticket scope, peer review, maintenance window, emergency exceptions, rule owner/expiry, per-target readback, positive/negative tests và rollback được kiểm chứng.
- **Incident response** phải vừa bảo vệ availability vừa khôi phục segmentation: preserve evidence, kiểm tra effective path, containment đúng quyền, targeted rollback, retest và hậu kiểm—không tự tắt firewall hoặc mở allow-all.
- **Telemetry vận hành tốt phải có coverage metrics và heartbeat**: biết thiết bị nào được thu log, snapshot, readback, traffic verification; không dùng “0 alerts” thay cho đánh giá an toàn.
- Mục tiêu cuối cùng là duy trì **chuỗi bằng chứng có thể kiểm toán**: **ai và vì sao sửa chính sách → quyền/luồng nào có thể đổi → policy nào thực sự được áp → traffic/app chịu tác động gì → kiểm soát nào đã xác nhận đúng hoặc cần khôi phục**.
