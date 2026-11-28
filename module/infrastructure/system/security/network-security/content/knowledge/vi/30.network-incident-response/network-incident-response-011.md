# Xác nhận không còn persistence qua network

**Xác nhận không còn persistence qua network** là quá trình kiểm chứng có bằng chứng rằng, sau khi cô lập, điều tra, loại bỏ và khôi phục một hệ thống bị xâm nhập, **các cơ chế giúp đối tượng trái phép duy trì quyền truy cập hoặc tái lập kết nối qua mạng đã được loại bỏ hoặc bị vô hiệu hóa một cách hiệu quả**. Việc kiểm chứng cần bao trùm cả **điểm đặt persistence**, **danh tính/đường truy cập còn hiệu lực**, **luồng điều khiển qua mạng**, **cấu hình hạ tầng**, và **kết quả giám sát trong một khoảng thời gian phù hợp**.

Chủ đề thuộc chương **Ứng phó sự cố mạng** của module **SECURITY_NETWORK_SECURITY**. Kiến thức về **network segmentation, firewall, VPN, IDS/IPS, DNS security, cloud network, Kubernetes, TLS/mTLS, packet capture và telemetry** được áp dụng để đánh giá liệu một hệ thống đã thực sự an toàn để đưa trở lại vận hành hay vẫn tồn tại đường quay lại của kẻ xâm nhập.

Một thiết bị không còn phát sinh alert trong vài phút **không chứng minh persistence đã biến mất**. Một beacon có thể chỉ chạy theo lịch; một tài khoản VPN bị lộ có thể chưa đăng nhập lại; một cloud role hoặc firewall allow rule vẫn còn hiệu lực dù hiện chưa có traffic. Ngược lại, một kết nối outbound tồn tại sau remediation **không tự chứng minh attacker vẫn hiện diện**, vì có thể là traffic nghiệp vụ, security agent, DNS cache hoặc session chưa đóng. Cần **kết hợp bằng chứng cấu hình, kiểm soát định danh, host/network telemetry, hành vi và kết quả thử nghiệm được phép**.

> **Phạm vi và an toàn:** bài hướng dẫn điều tra, xác thực và phòng vệ trong **hệ thống thuộc quyền quản trị**, không chỉ cách thiết lập hoặc che giấu persistence. Các domain, IP, dấu vết, account và tình huống đều là **giả lập**. Không chủ động kết nối tới hạ tầng nghi của attacker, không chạy implant, không thực hiện truy cập vào hệ thống không được cấp quyền. Các phép thử dùng sandbox/synthetic events; production changes phải theo incident commander, change approval và bảo toàn chứng cứ.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Giải thích sự khác nhau giữa **persistence, command-and-control (C2), tái xâm nhập, credential reuse, lateral movement và một kết nối mạng hợp lệ**.
2. Vẽ **attack-path hypothesis** và trust boundaries: endpoint/server, IAM, VPN, remote management, cloud control plane, Kubernetes, DNS/firewall/proxy và external destinations.
3. Liệt kê các **cơ chế persistence có tác động đến network** như remote-access services, scheduled tasks/service startup, unauthorized accounts/keys, VPN/certificate trust, cloud IAM roles, access routes, DNS changes và network-device configuration.
4. Phân biệt **indicator of compromise (IOC)**, **điều kiện cho phép persistence**, **evidence cơ chế đã được gỡ** và **evidence không còn hoạt động theo thời gian**.
5. Thu thập và liên kết **EDR/host audit, process–socket, DNS, proxy, firewall/NAT, VPN/identity, IDS/IPS, PCAP, cloud/Kubernetes audit và application logs**.
6. Xây **inventory nguồn quan sát và blind spots** theo endpoint, network segment, time window, IPv4/IPv6, encrypted/proxied paths, region và failover.
7. Xác định tiêu chí kiểm chứng **không còn đường inbound, outbound, remote access, delegated identity hoặc tự khôi phục** sau xử lý sự cố.
8. Đánh giá **residual risk** và confidence khi không thể chứng minh tuyệt đối sự vắng mặt của persistence.
9. Thiết kế **negative tests an toàn**, synthetic beacons, rule/identity checks, thời gian giám sát, canary và rollback/restore validation.
10. Lập runbook **triage → scope → containment → eradication → recovery → verification → sign-off → enhanced monitoring**.
11. Đưa ra quyết định **rebuild/reimage, credential rotation, revocation, re-enrollment và isolation** dựa trên khả năng tin cậy của thiết bị và bằng chứng.
12. Viết báo cáo kết thúc sự cố với **bằng chứng đủ, nguồn còn thiếu, giả thuyết chưa loại trừ, owner và thời hạn theo dõi**.

## 2. Khái niệm nền tảng: persistence qua network là gì?

### 2.1. Persistence là khả năng duy trì hoặc tái lập quyền truy cập

Trong điều tra an ninh, **persistence** là cơ chế mà đối tượng xâm nhập có thể dùng để giữ hoặc khôi phục sự hiện diện/truy cập dù phiên kết nối kết thúc, tiến trình bị dừng hoặc hệ thống khởi động lại. Không phải mọi persistence đều là một kết nối liên tục. Ví dụ:

- Một dịch vụ tự khởi chạy sau reboot có thể thực hiện **kết nối outbound** theo lịch.
- Một tài khoản/khóa SSH/VPN không được cấp phép cho phép **đăng nhập lại qua inbound path** mà không cần beacon thường xuyên.
- Một rule cloud IAM hoặc trusted federation tồn tại có thể cho phép **tái cấp phiên** về sau.
- Một cấu hình reverse proxy/firewall/NAT không được duyệt có thể giữ **đường network reachability** tới backend nhạy cảm.
- Một workload template/automation bị sửa có thể **tái tạo Pod/agent** sau khi Pod nhiễm bị xóa.

Những yếu tố này không cùng một kỹ thuật tấn công. Một số là **cơ chế chạy mã**, một số là **điều kiện truy cập liên tục**, và một số chỉ tạo **đường có thể bị lạm dụng**. Phải xác định nguyên nhân thực tế và phạm vi thay vì gán tất cả là “C2 beacon”.

### 2.2. Persistence không đồng nghĩa C2

| Khái niệm | Định nghĩa ngắn | Ví dụ quan sát | Kết luận đúng |
| --- | --- | --- | --- |
| **Persistence** | Cơ chế giữ/tái lập truy cập | Service tự khởi động, cloud key chưa thu hồi | Cần kiểm tra cơ chế và quyền |
| **C2** | Trao đổi điều khiển với hệ thống bên ngoài | Outbound connection lặp tới đích đáng ngờ | Có thể là hoạt động điều khiển; cần xác minh nguồn |
| **Beaconing** | Traffic định kỳ hoặc jittered | DNS/HTTPS request lặp có mẫu thời gian | Là tín hiệu, không phải bằng chứng duy nhất |
| **Lateral movement** | Truy cập giữa các hosts/tài nguyên | Remote management từ host A đến B | Điều tra principal, scope, authorization |
| **Re-entry** | Tái truy cập từ outside | VPN/SSH login sau khi remediation | Có thể do credential/access path còn hiệu lực |
| **Residual session** | Phiên cũ còn tồn tại | TCP/VPN/identity session chưa hết | Cần biết timeout/kill semantics |
| **Benign periodic job** | Hoạt động dự kiến | Monitoring, updates, backups | Không gắn nhãn C2 chỉ vì định kỳ |

Một **beacon không xuất hiện** không đủ để loại trừ khả năng re-entry bằng VPN credential; **SSH key còn tồn tại** cũng không chứng minh key đã bị attacker sử dụng. Luôn tách **capability**, **observed usage** và **attribution**.

### 2.3. “Không còn persistence” có thể xác nhận đến mức nào?

Không thể chứng minh tuyệt đối mọi kỹ thuật chưa biết đều vắng mặt. Điều có thể xác nhận là:

1. **Known/credible persistence hypotheses** được định nghĩa từ incident evidence và threat model.
2. Các **cơ chế đã xác định** được xóa/vô hiệu hóa, với readback độc lập.
3. **Credentials, keys, sessions, remote access paths và delegated permissions** liên quan được thu hồi/đổi/quản lý.
4. Thiết bị hoặc workloads bị nghi xâm nhập được **khôi phục từ nguồn tin cậy** khi integrity không còn bảo đảm.
5. Các **đường inbound/outbound và control-plane** đã kiểm tra không cho phép tái truy cập trái quyền.
6. **Telemetry coverage** đủ cho khoảng theo dõi đã chọn; không thấy tái phát trong giới hạn quan sát.
7. Residual risks được **ghi nhận, chấp nhận có thẩm quyền hoặc tiếp tục xử lý**.

Nên viết **“không còn bằng chứng persistence đã biết trong phạm vi và thời gian quan sát X”**, thay vì **“hệ thống sạch 100%, không thể tái nhiễm”**.

### 2.4. Dòng thời gian của một ca điển hình

~~~mermaid
flowchart LR
  A["Detection\nsuspicious network activity"] --> B["Containment\nrestrict access and preserve evidence"]
  B --> C["Scope analysis\nhosts, identities, routes"]
  C --> D["Eradication\nremove mechanisms/revoke access"]
  D --> E["Recovery\nrebuild, restore and harden"]
  E --> F["Verification\nconfig + identity + data plane"]
  F --> G["Enhanced monitoring\ncoverage and recurrence checks"]
  G --> H{"Evidence sufficient?"}
  H -- "No" --> C
  H -- "Yes, with residual risk" --> I["Authorized sign-off\nand scheduled follow-up"]
~~~

**Containment** có thể khiến traffic biến mất ngay cả khi cơ chế persistence vẫn tồn tại trên disk/control plane. Vì vậy phải kiểm tra **eradication và re-entry capability** trước khi đưa tài sản trở lại mạng.

## 3. Bản đồ bề mặt persistence có ảnh hưởng đến network

### 3.1. Endpoint và server

| Nhóm | Cơ chế/điều kiện cần xem | Bằng chứng phòng vệ |
| --- | --- | --- |
| **Startup/service** | Service/daemon, startup entries, scheduled tasks, agent launch | Host inventory, EDR timeline, startup configuration readback |
| **Network listener** | Remote admin, unknown service, unexpected port binding | Process–socket mapping, listening address/interface, owner |
| **Remote identity** | Local/domain accounts, SSH authorized keys, RDP/remote management ACL | User/group/key inventory, identity logins, access policy |
| **Outbound process** | Process mở HTTPS/DNS/TCP/UDP kết nối lặp hoặc bất thường | EDR process lineage, DNS/proxy/flow correlation |
| **Persistence by dependency** | Update scripts, plugins, service hooks, agents | Package/config integrity, service templates, trusted baseline |
| **Credentials** | Tokens/passwords/certificates còn dùng được | IAM/secret store, revocation and authentication audit |
| **Trusted persistence** | Compromised admin/automation tool đẩy config trở lại | Signed deployment, PAM and change-event audit |

Không phải mọi **socket listening** là độc hại; phải so với baseline và service owner. Ngược lại, malware có thể **không listen** mà chỉ gọi outbound hoặc chờ trigger, nên chỉ quét port là không đủ.

### 3.2. Identity/VPN và đường vào từ xa

- **VPN accounts/tokens/certificates** còn active hoặc được tạo trái phép.
- **SAML/OIDC/OAuth** refresh tokens, sessions, service principals và federation grants chưa bị hủy.
- **SSH keys** được thêm vào account có thể truy cập qua bastion/VPN.
- **Remote desktop/management** được bật ngoài quy trình.
- **Firewall/SG/NACL/VPN policy** mở một route vào tài sản.
- **PAM/jump host sessions** kéo dài hoặc session tokens còn hiệu lực.
- **Remote access applications/agents** chưa được kiểm kê.

**Thu hồi một password không tự hủy mọi session/token/SSH key**; xử lý phải theo nhà cung cấp identity, VPN và application. Ngược lại, xóa một account cũng chưa chắc xóa hết service principals, delegated permissions hoặc trust configuration.

### 3.3. Thiết bị mạng và control plane

Một đối tượng có quyền quản trị mạng có thể để lại **đường điều khiển/tái truy cập** bằng sai lệch cấu hình. Bề mặt cần đánh giá:

- Firewall **allow/deny**, NAT, port forwarding, management ACL.
- Routing/PBR, VPN peers/tunnels, remote access portal, split tunneling.
- DNS resolver/forwarder, static host records, dynamic DNS, DNS policy.
- Proxy/PAC/egress gateway routing, inspection bypass, certificate trust.
- WAF/reverse proxy backend exposure hoặc direct-origin access.
- Network-device admin users/keys, AAA/RADIUS/TACACS integration.
- Syslog/NetFlow/IPFIX/exporter configuration và telemetry suppression.
- IaC/controller policy templates tự đẩy cấu hình cũ trở lại.

**Lưu lượng im lặng không chứng minh một port-forward trái phép đã được xóa**. Cần diff config, readback ở tất cả devices/HA members và test reachability đúng đường.

### 3.4. Cloud và Kubernetes

Cloud và container control planes có thể tạo lại tài nguyên dù instance/Pod hiện tại đã bị thay:

- **IAM users/roles/access keys, service principals, trust policies, workload federation**.
- **Automation schedules, managed functions, deployment hooks**, image/AMI/container templates.
- Security groups, cloud network firewall, VPC routes, NAT/VPN/peering/PrivateLink-like endpoints.
- **Compute instance/user-data/bootstrap templates** hoặc startup configurations.
- Kubernetes **Deployments/DaemonSets/Jobs/CronJobs, admission webhooks, operators**, container image references.
- ServiceAccount tokens, projected credentials, RBAC/ClusterRoleBindings, secrets access.
- **Ingress/Gateway/Service LoadBalancer/NodePort**, network policy/CNI, service mesh mTLS rules.
- CI/CD pipelines, GitOps reconciler và shared deployment credentials.

Xóa một Pod có thể **không có tác dụng** nếu Deployment/CronJob template vẫn tạo Pod có image/config bị ảnh hưởng. Một cloud instance thay mới có thể tiếp tục bị truy cập nếu **IAM trust hoặc SG route** trái phép vẫn còn.

### 3.5. DNS và cơ chế hẹn giờ

Một tên miền có thể xuất hiện trong:

- DNS cache, resolver logs, proxy allowlist hoặc application configuration.
- Scheduled automation job/agent config hoặc service discovery.
- DNS-based failover, dynamic records, CDN/cloud DNS, TTL và resolver policies.

**Domain không được truy vấn trong một cửa sổ ngắn** chưa đủ loại trừ persistence hẹn giờ. Kiểm tra cả **scheduler/host config**, nguồn DNS, cache/TTL, đường DoH/DoT, direct IP và thời hạn quan sát.

### 3.6. Network persistence được quan sát ở đâu?

~~~mermaid
flowchart TB
  ID["Identity / VPN / IAM\nsession and credential rights"] --> HOST["Endpoint / server\nservice, task, key, agent"]
  HOST --> SEG["Host firewall / CNI\nnetwork segmentation"]
  SEG --> EGR["Proxy / firewall / NAT\nVPN and cloud routes"]
  EGR --> DST["External peer or\ninternal remote management"]
  DNS["DNS resolver / secure DNS"] -. "Name resolution" .-> HOST
  CTRL["IaC / cluster / device controller"] -. "Re-deploy or config drift" .-> HOST
  CTRL -. "Network policy changes" .-> EGR
  OBS["EDR + DNS + flow + auth + control audit"] -. "Cross-source evidence" .-> SEG
  OBS -. "Readback and activity" .-> ID
  OBS -. "Traffic + mapping" .-> EGR
~~~

Sơ đồ minh họa các **đường kiểm chứng**, không khẳng định mọi packet đi theo đúng một thứ tự. Trong môi trường cloud, Node NAT, hostNetwork, secondary CNI hoặc private peering có thể tạo đường không qua proxy kiểm soát dự kiến.

## 4. Xây giả thuyết điều tra và định nghĩa phạm vi

### 4.1. Không bắt đầu bằng một danh sách IOC vô hạn

Thay vì săn tìm mọi IP/domain trên Internet, bắt đầu từ **case evidence**:

1. **Tài sản đầu tiên** phát hiện bất thường: host, Pod, user, device, service.
2. **Quyền đã có khả năng bị sử dụng**: account, role, tokens, admin credential, VPN.
3. **Tương tác mạng**: source process/IP/identity, domain/IP/port/protocol, thời điểm.
4. **Đường đi**: DNS → proxy/gateway → NAT/cloud route → destination, kể cả alternate paths.
5. **Có cơ chế persistence cụ thể nào?** service/task, key/account, trust policy, route, deployment template.
6. **Tài sản phụ thuộc/liên quan**: cùng credential, subnet, image, cluster, VPC, region, vendor.
7. **Khi nào sự cố bắt đầu?** initial compromise window, log retention, time sync.
8. **Khi nào đã containment/eradication?** để xác định đoạn baseline sau xử lý.

Một địa chỉ IP/port đáng ngờ có thể thay đổi; nếu chỉ tìm IOC cũ, **cơ chế cấp lại quyền hoặc scheduled task** có thể còn. Cần ưu tiên **mechanism-centric verification**.

### 4.2. Bảng scope cho mỗi giả thuyết

~~~text
Hypothesis ID: H-01
Claim:
  Server orders-api might recreate an unauthorized outbound
  network session after reboot or service restart.

Scope:
  Host/VM/Pod UID, owner, image/build revision, region/zone
  Network source identity and current egress routes
  Process/service/scheduler inventory
  Historical DNS, proxy, firewall and EDR events

Evidence required:
  Persistence entry removed or trusted rebuild completed
  Process/socket state verified by EDR/host tools
  Credential/role and config paths verified
  Post-recovery telemetry covers normal duty cycle
  Targeted allow/deny tests and benign functionality PASS

Not sufficient alone:
  No IOC connection observed for 15 minutes
~~~

### 4.3. Nhóm giả thuyết và phép chứng minh phù hợp

| Giả thuyết | Cơ chế cần loại trừ | Readback/control evidence | Hoạt động cần quan sát |
| --- | --- | --- | --- |
| **H1: outbound C2 tự khôi phục** | Service/task/agent + credential/route | Host integrity, startup entries, build/image | Process–socket, DNS/proxy/flow after restart |
| **H2: remote inbound re-entry** | Account/SSH key/VPN/management ACL | Identity/key/SG/firewall lists | Login attempts/results, denied access |
| **H3: cloud delegated access** | Access key, IAM role/trust, token/sessions | IAM diff, revocation state, cloud audit | New API calls from affected principals |
| **H4: K8s re-deploy** | Deployment/CronJob/operator template | Workload spec, image digest, GitOps commit | Recreated Pods and network flows |
| **H5: network-device backdoor path** | NAT/route/VPN/ACL/AAA config | Config diff, per-member readback | Reachability/flow via direct and alternate paths |
| **H6: malicious DNS/proxy setting** | Resolver, DNS record, PAC/proxy route | Config and delegation validation | DNS/proxy destination and resolution history |
| **H7: persistent identity federation** | OAuth grant, session refresh, workload trust | IdP/API grants, session revocation | Authentication and token issuance audit |
| **H8: lateral movement foothold** | Remote account/service on another host | Cross-host inventory and access rights | East–west remote management/logon activity |

Không phải ca sự cố nào cũng cần kiểm cả tám giả thuyết với cùng độ sâu. **Mở rộng scope theo evidence, asset criticality và attack path**, ghi lý do loại trừ/giới hạn từng hypothesis.

## 5. Chuẩn bị bằng chứng trước khi kết luận đã loại bỏ persistence

### 5.1. Thu thập trước khi làm biến mất dữ liệu dễ mất

Theo **quy trình forensic đã được phê duyệt**, cân nhắc bảo toàn:

- **Volatile state:** running processes, parent–child trees, sockets/listeners, active connections/sessions, memory capture khi cần và có quyền.
- **Host logs:** process creation, service/scheduled-task changes, authentication, endpoint detection, local firewall và name-resolution history.
- **Identity logs:** VPN/SSO/PAM, issuance of access/refresh tokens, service accounts, authorized keys và delegated access.
- **Network telemetry:** DNS, proxy, firewall, IDS/IPS, flow/IPFIX, NAT translation, load balancer, egress gateway, cloud flow.
- **Control plane:** firewall/route/NAT/SG/VPN/AAA, IAM/federation, Kubernetes controllers and admission, IaC revisions.
- **Images/artifacts:** trusted image digest, software inventory, service/task definitions, disk snapshot, package integrity.
- **Timeline:** detection, last confirmed attacker action, containment, rotation/revocation, rebuild, restart và return-to-service.

**Cô lập kịp thời để giảm thiệt hại có thể quan trọng hơn việc thu đủ mọi bằng chứng.** Incident commander cân nhắc tính khẩn cấp, regulatory requirements và mức độ phá hủy evidence khi shutdown/rebuild. Không kéo dài khả năng attacker truy cập chỉ để “có thêm log đẹp”.

### 5.2. Biên bản evidence tối thiểu

~~~yaml
# Dữ liệu giả lập: định dạng hồ sơ, không chứa secret/PCAP thật.
case_id: IR-NET-TRAINING-011
hypothesis_id: H-01
asset:
  environment: production
  cluster_or_site: region-a
  node_or_host_id: host-027
  workload_id: orders-api
  owner: app-security
observation:
  event_time_utc: "2026-11-28T02:00:00Z"
  collection_time_utc: "2026-11-28T02:01:10Z"
  source: edr-synthetic
  evidence_ref: evidence://case/host-027/network-event-01
  integrity_digest_ref: digest-record-001
  visibility: process-and-socket
  data_redacted: true
conclusion:
  mechanism: scheduled-outbound-connection
  mechanism_removed: unknown
  credentials_revoked: unknown
  recurrence_observed: unknown
  evidence_confidence: limited
  analyst: incident-team
~~~

Một case record nên tách **observed facts** (nguồn, timestamp, hoạt động) và **interpretation** (persistence hypothesis, severity). Không tự bổ sung giá trị **actor=attacker** hoặc **mechanism_removed=true** khi chưa kiểm chứng.

### 5.3. Chuỗi bảo quản chứng cứ và tính toàn vẹn

Khi có thể cần forensic/legal:

1. Ghi người/role thu thập, phương pháp, thời gian, timezone, thiết bị và quyền truy cập.
2. Dùng **evidence store** có mã hóa, RBAC, retention, audit và khi cần **tamper-evident** controls.
3. Lưu cryptographic checksum/hash của artifact được phép và **metadata** ở ngoài artifact.
4. Không sửa nội dung gốc khi tạo bản phân tích; dùng working copy/redacted derivative.
5. Phân biệt **raw packet/credential/memory** với metadata an toàn để đưa vào ticket.
6. Ghi sự kiện evidence thiếu, sai clock hoặc collection failure.

Một checksum chỉ cho biết artifact không đổi **so với giá trị hash được ghi**, không tự chứng minh nguồn artifact trung thực hoặc quá trình thu thập không bị attacker kiểm soát. Có thể cần **independent source corroboration**.

### 5.4. Đồng bộ thời gian và sự kiện sau khôi phục

Nhiều nguồn có timestamp khác nhau:

~~~text
Host EDR event time:          10:00:00 UTC
Firewall session start time: 09:59:59 UTC
Proxy log ingest time:       10:01:40 UTC
VPN audit event time:        10:00:04 UTC

Case note:
  collector lag observed
  +/- clock offset measured and documented
~~~

Để tìm persistence có chu kỳ dài, cần đặt các mốc:

- **T0:** last confirmed suspicious action/known compromise.
- **T1:** containment bắt đầu.
- **T2:** known mechanisms removed/identities revoked.
- **T3:** asset rebuilt/recovered and network reconnected.
- **T4:** monitoring window concluded and sign-off.

Một kết nối tại **T2+** có thể bắt đầu **trước T2** hoặc đã bị NAT cache/session persistence giữ lại. Đối chiếu **flow/session start time, new connection attempts, app-layer operations và thiết bị stateful**. Không quy mọi byte sau T2 là kết nối mới.

### 5.5. Phân loại độ tin cậy của nguồn

| Nguồn bằng chứng | Điểm mạnh | Điểm yếu cần ghi |
| --- | --- | --- |
| Host EDR có process lineage | Nối executable với network behavior | Sensor có thể offline/tampered, process attribution incomplete |
| Forensic image/snapshot | Xem persistence configuration tại thời điểm capture | Không thấy cơ chế chỉ nằm ở cloud control plane |
| Device config readback | Xác nhận rule/route/VPN hiện có | Không chứng minh actual packets hoặc compromised admin |
| Identity provider audit | Thấy login/token grants/revocations | Một số sessions/third-party tokens khó revoke tức thì |
| DNS/proxy logs | Thấy destinations/HTTP metadata theo path | DoH/direct IP/opaque TLS/unsupported protocols |
| NetFlow/VPC flows | Thấy network tuples/bytes | NAT sampling, thiếu payload và process identity |
| Packet capture | Quan sát packet/protocol tại sensor | Có thể bỏ lỡ paths, encryption che contents, privacy |
| Egress policy negative test | Đo một path không cho phép | Không chứng minh mọi paths/identities bị deny |
| Trusted rebuild/immutable image | Giảm khả năng host artifact cũ sống lại | Shared credentials/control plane có thể vẫn sai |

**Không nên chọn một nguồn duy nhất làm “bằng chứng sạch”.** Dùng **ít nhất hai nguồn độc lập** khi tài sản/rủi ro đòi hỏi; mức độc lập thực tế phụ thuộc cùng control plane/agent/identity failure domains.

## 6. Network telemetry: tìm dấu hiệu tái kết nối sau remediation

### 6.1. Lớp quan sát và câu hỏi tương ứng

| Layer | Đầu vào | Câu hỏi cần trả lời |
| --- | --- | --- |
| **DNS** | Resolver logs, answer/cache/DoH policy | Workload còn tìm tới host/domain nghi vấn không? |
| **L3/L4** | Firewall, NetFlow/IPFIX, VPC flow, NACL/CNI | Có luồng/attempt mới tới IP/port ngoài allowlist? |
| **NAT** | Translation/session logs | IP nguồn thực trước NAT là workload nào? |
| **Proxy/SWG** | Destination hostname/SNI, HTTP method/status khi có quyền | Có attempts qua egress path được quản lý? |
| **IDS/IPS** | Alerts, protocol anomalies, signatures | Có hành vi giống mẫu đáng ngờ không? |
| **Endpoint** | Process–socket, DNS client, EDR | Process/binary/service nào tạo kết nối? |
| **Identity/VPN** | Authentication and session logs | Account/key nào đang/từng tái truy cập? |
| **Cloud/K8s** | API audit, workload identities, resource creation | Có cấu hình/tài nguyên tự tái tạo đường truy cập? |

**Không thấy một IOC trên proxy** không có nghĩa host không kết nối trực tiếp qua NAT/VPN/IPv6/secondary network. Phải kiểm tra **coverage path** và chéo dữ liệu host/flow.

### 6.2. Beaconing: dấu hiệu cần phân tích, không phải bằng chứng tuyệt đối

Một chuỗi outbound connection lặp đều có thể phát sinh từ **monitoring agent, backup, auto-update, health check, service discovery** hoặc C2. Phân tích:

- **Periodicity:** khoảng cách các events, có jitter hay chỉ do timer?
- **Destination novelty:** endpoint mới so với baseline/owner registry.
- **Process parentage:** tiến trình nào tạo connection, đường dẫn/signature/image digest.
- **Protocol/port:** HTTP(S)/DNS/QUIC/custom, phù hợp workload không?
- **Byte pattern:** kích thước payload tương tự và flow direction.
- **Timing context:** hoạt động sau reboot/redeploy/rotation có quay lại?
- **Behavior context:** có service/task auto-start hoặc newly added network identity?
- **Cross-host correlation:** nhiều hosts cùng chu kỳ/domain, có common approved agent không?

**Jitter không phải dấu hiệu đặc quyền của attacker**, và phiên TLS encrypted có thể làm byte pattern khó giải thích. Không quét nội dung bí mật của người dùng chỉ để đo periodicity; dùng metadata trong phạm vi được phép.

### 6.3. Một bảng flow giả lập

~~~text
Asset: host-027
Window: 2026-11-28 00:00–06:00 UTC

01:00:10  process=backup-agent    dst=backup.example.test:443    status=ALLOW
01:15:05  process=unknown-service dst=198.51.100.77:443          status=ALLOW
01:30:05  process=unknown-service dst=198.51.100.77:443          status=ALLOW
01:45:05  process=unknown-service dst=198.51.100.77:443          status=ALLOW
02:00:00  containment applied
02:15:06  firewall src=host-027 -> 198.51.100.77:443             status=DENY
02:30:06  firewall src=host-027 -> 198.51.100.77:443             status=DENY
03:00:00  known scheduled task removed; service registry corrected
03:15–06:00 no observed new attempts to this IOC
~~~

Giả thuyết có ích: **sau T1, một mechanism vẫn cố kết nối dù network deny**; sau T2 số attempts giảm. Nhưng từ 03:15 đến 06:00 **chưa đủ chứng minh** mọi persistence đã hết: phải xem **task/service removal, credential rights, interval > longest duty cycle, sensors alive và destinations có thể thay đổi**. Dữ liệu trên là tổng hợp, không phải hướng dẫn tạo beacon.

### 6.4. DNS evidence và những điều không thể kết luận

Một truy vấn DNS đến domain đáng ngờ sau T2 có thể đến từ:

- Browser/OS DNS cache refresh hoặc prefetch.
- Service discovery/monitoring/sandbox.
- Application process cũ còn chạy.
- Scheduled task chưa xóa.
- Công cụ IR kiểm tra indicator trên sandbox (nếu có và được phê duyệt).

Quy trình:

1. Gắn resolver query với **client identity/source IP và event time**.
2. Kiểm tra **process attribution** nếu EDR/DNS client telemetry hỗ trợ.
3. Xác định query có dẫn tới **actual connection** không.
4. Kiểm tra DNS response, TTL/cached mapping, split-horizon/forwarding.
5. Xem DoH/DoT/direct IP paths ngoài visibility.
6. Phân loại expected vs suspicious theo **business owner và host baseline**.

**DNS query không tương đương thành công kết nối C2**, và một IP trong DNS answer không xác nhận đó là network path thực được dùng.

### 6.5. TLS/SNI, QUIC và encrypted payload

Network sensors có thể quan sát **destination IP, port, timing, packet counts, TLS handshake metadata/SNI khi có**, nhưng:

- TLS 1.3, ECH, certificate pinning, DoH/DoT và QUIC/HTTP3 có thể làm một số metadata không hiện/khó phân tích.
- CDN/shared IP có thể phục vụ nhiều hosts; IP match không đủ định danh recipient.
- Không phải mọi phiên TLS có HTTP; opaque TCP/custom protocol khác.
- TLS traffic đến một trusted SaaS vẫn có thể là persistence nếu identity/endpoint bị lạm dụng, nhưng **nội dung không thể tự suy từ bytes**.
- Process attribution và cloud/provider audit giúp giải thích những trường hợp encrypted traffic.

Không tắt TLS verification, ép giải mã lưu lượng của người khác hoặc thu credential thật để chứng minh host “sạch”. Nếu cần TLS inspection, phải có **authority, privacy review và scope rõ**.

### 6.6. NAT, IPv6 và các đường không qua sensor

Một cloud NAT public IP có thể đại diện hàng trăm Pods/instances. Vì thế:

- Join NAT records với **source Pod/VM identity, source port, translated port, timestamp**.
- Với overlay CNI, cloud flow có thể chỉ thấy **node/tunnel IP**.
- Xem **IPv4 lẫn IPv6** nếu dual-stack.
- Kiểm tra **secondary interfaces, hostNetwork, VPN, private VPC peering, direct egress bypass**.
- Kiểm tra sensors ở **cả primary và failover/DR path**.
- Ghi rõ NetFlow/IPFIX sampling, flow aggregation, session timeouts.

Một lượng lớn traffic được ghi tại NAT sau T2 **không quy kết được source** nếu không có translation mapping. Khi thiếu mapping, báo **attribution unknown** và tìm thêm CNI/host logs.

### 6.7. So sánh baseline trước/sau theo loại workload

Không dùng một baseline cố định cho mọi host. Ví dụ:

| Workload | Outbound bình thường | Dấu hiệu lệch cần điều tra |
| --- | --- | --- |
| Frontend API | Approved auth/backend endpoints, metrics | New external host, unusual long-lived tunnel |
| Database | Backup/replication/monitoring | Internet egress mới, unauthorized management peer |
| Build runner | Registries/package repos theo job | Secret manager access + unexpected exfil destination |
| DNS resolver | Upstream DNS, known forwarding peers | Unapproved DoH/forwarder, config drift |
| VPN gateway | Registered peers/identity provider | Unknown tunnel peer, admin account changes |
| Kubernetes node | Control plane, registries, monitoring | Host-level connection not attributable to workloads |

Một application deployment hợp lệ có thể làm destination set thay đổi; cần **change ticket, release notes và owner attribution** trước khi gọi IOC. Ngược lại, accepted change vẫn có thể tạo security regression nếu route/identity scope quá rộng.

## 7. Kiểm chứng trên endpoint: cơ chế khởi chạy và process–socket

### 7.1. Vì sao phải quay về host?

Flow logs có thể cho thấy một kết nối kết thúc, nhưng không trả lời **tiến trình nào dự kiến tạo nó sau reboot**. Trong một số ca, attacker foothold là process đang chạy; trong ca khác, chính **scheduled job, service registry, remote access key hoặc template** mới là cơ chế lâu dài. Do đó host inspection phải kết hợp:

- **Processes:** executable, parent, signer/hash, command line đã khử bí mật, user/service identity.
- **Sockets:** local bind, remote peer, protocol, process owner, state, listen vs established.
- **Startup/autostart:** system services, scheduled tasks, user-session startup, service dependencies.
- **Application/runtime artifacts:** startup config, extension/plugin, agent config, package inventory.
- **Authentication:** local/domain users, groups, SSH authorized keys, RDP/remote access config.
- **Security agent:** EDR healthy, policy current, tamper protection và historical alerts.
- **System integrity:** verified image/package hashes, trusted boot/rebuild evidence khi cần.

**Một số persistence không thể xác nhận đã bị xóa chỉ bằng snapshot lúc runtime**, ví dụ một cron job chưa đến lịch, hệ thống đang offline hoặc Cloud controller sẽ tái tạo service sau một sự kiện. Kiểm cả **declarative state và trigger paths**.

### 7.2. Kiểm tra Linux read-only trong môi trường được quản lý

Các lệnh minh họa, **chỉ trên host thuộc quyền quản trị** và khi không làm ảnh hưởng quy trình forensic:

~~~bash
# Socket/listener với PID/process, có thể cần quyền phù hợp.
ss -tulpen
ss -tunap

# Liệt kê services và trạng thái hiện tại.
systemctl list-units --type=service --all
systemctl list-unit-files --type=service

# Timer/scheduler do systemd quản lý.
systemctl list-timers --all

# Xem những processes đang chạy và lineage cơ bản.
ps -eo pid,ppid,user,etime,comm,args

# Danh sách interface và routing để hiểu network path.
ip -brief address
ip route show
ip -6 route show
~~~

Lưu ý:

- Những lệnh đọc trên có thể làm lộ **token trong command line/process environment** nếu phần mềm cấu hình sai. **Không copy output nguyên bản** vào chat/ticket không được bảo vệ.
- Những gì thấy trong **ss/ps** chỉ là snapshot tại thời điểm chạy; kết nối ngắn có thể đã biến mất.
- **systemctl** không bao quát toàn bộ startup/job mechanisms; có thể cần kiểm tra scheduler khác, container runtime, application-level schedules bằng EDR và asset owner.
- Một process lạ không mặc định độc hại; đối chiếu với **package signing/hashes, deployment artifacts, CMDB và change history**.

### 7.3. Kiểm tra Windows read-only theo chính sách vận hành

~~~powershell
# TCP connections và listening sockets, có owning process IDs.
Get-NetTCPConnection | Select-Object LocalAddress,LocalPort,
  RemoteAddress,RemotePort,State,OwningProcess

# UDP endpoints; UDP không có khái niệm ESTABLISHED giống TCP.
Get-NetUDPEndpoint | Select-Object LocalAddress,LocalPort,OwningProcess

# Services, trạng thái và startup type.
Get-CimInstance Win32_Service |
  Select-Object Name,State,StartMode,PathName,StartName

# Scheduled tasks, chỉ đọc thông tin theo quyền hiện có.
Get-ScheduledTask |
  Select-Object TaskName,TaskPath,State

# Firewall profiles và quy tắc hiện có.
Get-NetFirewallProfile
Get-NetFirewallRule | Select-Object DisplayName,Enabled,Direction,Action
~~~

Trong Windows, **Get-NetTCPConnection** không tự cung cấp đầy đủ process command line/signature; cần join process ID với source EDR/OS audit. Task/service paths cũng có thể chứa credential hay nội dung riêng tư; phải bảo vệ dữ liệu thu thập. Không thay đổi service/task khi đang bảo toàn chứng cứ nếu chưa có approval.

### 7.4. Process–socket correlation cần lịch sử, không chỉ ảnh chụp

Một điều tra tốt liên kết:

~~~text
Host: app-027 (asset identity)
Time: 2026-11-28T03:20:00Z
Process GUID: proc-guid-001
Executable: /opt/app/bin/worker (trusted? pending)
Parent: service-manager
Service/task reference: worker-export-job
Destination: api.vendor.example.test:443
DNS process attribution: matching host DNS event
Proxy/flow: connection observed, TLS valid
Purpose: unknown; owner validation required
~~~

**Process name là bằng chứng yếu** nếu binary có thể đổi tên hoặc một signed process được dùng sai mục đích. Cần kiểm **integrity, origin/deployment, command line, loaded extensions, authorization và lịch sử hành vi** khi incident scope yêu cầu.

### 7.5. Kiểm tra reboot/restart mà không phá production

Đối với nghi persistence bằng startup:

1. Xác nhận **mechanism đã được loại bỏ**, hoặc rebuild host từ **trusted image**.
2. Xác minh process/socket/identity state trên host sau remediation.
3. Nếu cần kiểm thử restart, lên kế hoạch trong **sandbox hoặc maintenance window được phê duyệt**, có recovery owner.
4. Xem service/task **có tự xuất hiện trở lại** không; kiểm tra IaC/config management/deployment controller.
5. Theo dõi **network event sau restart**, gồm source identity và destinations được phép.
6. Chạy **approved positive tests** cho nghiệp vụ, tránh “khôi phục bảo mật” bằng cách cắt tất cả mạng.

Không cố tình reboot một host đang chạy giao dịch nhạy cảm chỉ để có thêm dữ liệu nếu có phương án read-only/reimage canary tốt hơn.

### 7.6. Khi host không còn đáng tin

Nếu attacker có **đặc quyền cao** hoặc nghi can thiệp vào security sensor/OS:

- **In-place cleanup** có thể không đủ confidence.
- Cân nhắc **rebuild/reimage từ image được xác minh**, không chỉ xóa IOC file.
- Kiểm **boot configuration, image provenance, deployment pipeline và external configuration**.
- Rotate/revoke **secrets và identities mà host có thể truy cập**.
- Xem **adjacent systems/shared storage** để tránh recontamination.
- Chỉ kết nối lại mạng khi control plane và egress/ingress policies đã được xác thực.

**Reimage host không khôi phục an toàn nếu tài khoản VPN/cloud IAM key hoặc Kubernetes controller bị sửa vẫn còn quyền tái xâm nhập.**

## 8. Xác nhận không còn đường re-entry qua identity, VPN và remote management

### 8.1. Identity là một đường mạng ngay cả khi không có beacon

Một attacker có thể không cần agent chạy trên máy nếu giữ được **remote credential, session, key hoặc federation trust** để đăng nhập lại. Kiểm tra:

- Identity provider **users, groups, roles, sign-in history, MFA enrollments, recovery methods**.
- OAuth/OIDC **refresh sessions, app registrations, consent grants, client credentials**.
- VPN **accounts, assigned profiles, device certificates, sessions, peer configurations**.
- SSH **authorized keys**, bastion authorized principals, access groups, key rotation.
- RDP/remote management **allowlists, PAM sessions, gateways và privileged groups**.
- Cloud **access keys, assumed roles, cross-account trusts, token issuance and resource grants**.
- Local/admin accounts trên firewall/router/hypervisor.
- Secrets manager **read permissions** và credential issuance logs.

**MFA enable không chứng minh mọi old refresh token/session đã bị revoke**. Mỗi nền tảng có semantics riêng về access tokens, refresh tokens, federation và session lifetimes; ghi rõ những thứ **đã revoke**, **đang chờ TTL** và **không thể revoke tức thời**.

### 8.2. Inventory quyền truy cập từ xa

~~~text
Identity record:
  Principal: svc-automation-prod
  Type: service principal / workload identity
  Issuer: corporate identity provider
  Allowed use: deployment API only
  Trust: region-a workload identity federation
  Network path: management API gateway
  Credential types: short-lived assertion, client certificate
  Last rotated: documented in secret manager
  Active sessions: audited; state from issuer
  Owner: platform-security
  Expected revocation behavior: provider-specific
  Incident action: rotate/revoke compromised rights if scoped
~~~

Một principal có thể có **tên hợp lệ** nhưng privilege hoặc trust policy bị mở rộng, cho phép caller không đúng nguồn xin token. Do đó phải so **trust configuration, issuer/audience, role bindings và permission policies**, không chỉ user list.

### 8.3. Kiểm tra VPN sau containment

Một chuỗi kiểm chứng:

1. Lưu danh sách **VPN peer profiles/accounts/certificates** và session states tại T1/T2.
2. Đối chiếu trước/sau với **known-good inventory** và approved changes.
3. Vô hiệu hóa/revoke credentials hoặc peers liên quan, theo IR authority.
4. Kiểm tra **active sessions/tunnels** đã được chấm dứt hoặc đưa về trạng thái được duyệt.
5. Verify **authorization rules, split-tunnel profiles, management access**, không chỉ VPN login.
6. Xem VPN logs, IdP, firewall flows và remote management usage trong monitoring window.
7. Kiểm thử **negative login/reachability** qua test identity được cấp riêng, không thử sử dụng compromised credential thật trên Internet.

Một “VPN login failed” chưa chứng minh **mọi đường remote access** đã bị vô hiệu, và một tunnel được thiết lập không mặc định malicious nếu đó là site-to-site tunnel có owner.

### 8.4. SSH key và service account quyền cao

Một trong các rủi ro là **authorized key hoặc service account** vẫn được chấp nhận dù password đã đổi. Kiểm chứng:

- Inventory keys/certificates được cấp phép, **fingerprints và owners**.
- Unix/Windows local auth mappings, group privileges và inherited access.
- Bastion/PAM and SSH CA configurations, trusted principals, cert expiration.
- SSH host/access logs và key usage timestamps nếu ghi nhận được.
- **Revocation/reissue** theo chính sách thay vì xóa ngẫu nhiên keys của hệ thống.
- Automation dependencies dùng key đó để tránh outage ngoài kiểm soát.

Không công bố raw private keys hoặc recovery codes trong hồ sơ IR. Public key fingerprints không tương đương private key nhưng vẫn là asset metadata cần quản lý.

### 8.5. OAuth/API và các kết nối SaaS

SaaS connectors/webhooks/service apps có thể có:

- Long-lived refresh token hoặc API key.
- OAuth consent grant với scope rộng.
- Webhook callback URLs và signing key.
- Access đến storage/logging workspace hoặc CI repository.
- Cross-tenant integration chưa được review.

Để xác nhận hết re-entry, kiểm tra **application registrations, grants, tokens, webhooks và audit recipient**. Tắt một endpoint có thể chỉ chặn một route; **API token còn hiệu lực** có thể được dùng từ route khác. Revoke/rotate và giảm scope theo provider guidance.

### 8.6. Điều kiện sign-off cho identity persistence

~~~text
[ ] All incident-affected principals enumerated
[ ] Unauthorized accounts/keys/grants removed or disabled
[ ] Relevant passwords/tokens/certificates rotated/revoked
[ ] Active sessions and refresh paths evaluated/revoked where supported
[ ] VPN/SSH/remote management routes match approved design
[ ] Cross-account / federation trust policy validated
[ ] Approved automation still works under least privilege
[ ] Unauthorized test identity cannot authenticate or reach target
[ ] IdP/VPN/cloud audit telemetry healthy for follow-up period
[ ] Residual provider TTL/unknowns recorded with owner
~~~

**Không kết luận “không còn persistence” nếu chỉ thay password** mà vẫn chưa xem các delegated authorizations hoặc service account tokens đã bị nghi compromise.

## 9. Xác nhận firewall, NAT, routing, DNS và thiết bị mạng không giữ đường truy cập trái phép

### 9.1. “Không có kết nối” khác “không còn đường”

Một firewall có thể cho phép inbound TCP đến một admin service dù hiện chưa có client sử dụng. Một VPN profile có thể sẵn sàng cấp session. Một DNS record có thể trỏ tới endpoint mới nhưng resolver chưa truy vấn. Do đó network persistence verification cần:

- **Configuration diff:** trước/sau incident, so với approved source of truth.
- **Per-device effective readback:** active/standby HA, vùng/VDOM/VRF/VPC/policy contexts.
- **Route reachability:** Internet, partner networks, management, private peering, IPv6, secondary interfaces.
- **Traffic evidence:** observed inbound/outbound sessions và negative/positive tests.
- **Approval and owner:** xác minh không có ngoại lệ không được duyệt hoặc tự khôi phục.
- **Telemetry:** config audit, session logs, NetFlow, DNS, IPS/WAF, collector heartbeat.

### 9.2. Ma trận cấu hình cần đọc lại

| Bề mặt | Cần so sánh | Xác nhận cần đạt |
| --- | --- | --- |
| Firewall ingress | Source/dest/port/protocol/action/zone/priority | Không có unexpected allow hoặc bypass deny |
| Firewall egress | Approved destinations, gateway/proxy dependencies | Workloads không có direct arbitrary egress |
| NAT/port forward | Public/private mapping, exposed ports | Không còn published endpoint trái phép |
| Routing/PBR | Next hop, VRF, VPN/peering, firewall insertion | Không có path bypass enforcement |
| VPN | Peers, identities, tunnel policies, allowed subnets | Chỉ peers đã duyệt, revoked sessions không còn |
| DNS | Records/forwarders/resolvers, dynamic zones, DoH policy | Không còn unauthorized domain steering |
| WAF/reverse proxy | Routes, origin binding, auth/inspection rules | Không có direct origin/auth bypass |
| Security profiles | IDS/IPS, TLS inspection, egress DLP | Controls quan trọng không bị tắt |
| Management plane | Local admins, AAA, API keys, management ACL | Không còn unauthorized privileged access |
| HA/config sync | Revisions, sync status, failover posture | Members cùng approved effective configuration |
| Log export | Destination, filters, transport, retention | Không còn blind spot do configuration |

**Chỉ xem rule name hoặc traffic counters chưa đủ.** Một address group mở rộng hoặc security group attachment thay đổi có thể làm một rule cũ cho phép nhiều nguồn hơn.

### 9.3. Quy trình đọc cấu hình an toàn

1. Lấy **trusted baseline** từ Git/IaC/approved backup (kiểm integrity và thời điểm).
2. Dùng **read-only management API** có xác thực để lấy running config/objects/routes.
3. Redact **VPN PSK, local hashes, private keys, SNMP secrets và API tokens** trước khi xuất diff sang SIEM/ticket.
4. Resolve nested objects/dynamic memberships tại **time of observation**.
5. So policy order/priority, zone, NAT và attachments, không chỉ source/dest fields.
6. Kiểm tra **HA/DR targets** độc lập.
7. Xác minh **admin/audit log** không ghi cấu hình quay lại sau khi cleanup.
8. Ghi đủ **evidence references và uncertainty** nếu một device/controller offline.

**Một rule broad allow trong config không tự chứng minh Internet đã truy cập được**: còn cần route, NAT, zone và other policies. Nhưng đó vẫn là risk cần sửa theo approved baseline, đặc biệt nếu tạo **latent re-entry capability**.

### 9.4. Kiểm chứng inbound path

Ví dụ một chính sách đã khôi phục:

~~~text
Sensitive service:
  backend=10.30.5.12:5432

Allowed:
  orders-api subnet through service firewall + app auth

Denied:
  Internet/partner/dev/untrusted namespaces -> backend port
  Direct management and alternate external routes

Evidence:
  firewall/SG/NACL/route readback
  approved test sources, positive/negative results
  database authentication audit
  HA/DR route parity
~~~

**Network negative test** phải sử dụng nguồn được tổ chức cấp quyền, kiểm tra endpoint thuộc phạm vi, không scan Internet hay đối tác. Nếu test bị SG chặn trước firewall, chứng minh **end-to-end deny**, không được tự ghi chính firewall nội bộ đã match deny.

### 9.5. Kiểm chứng outbound/egress path

Một cơ chế outbound C2 có thể tồn tại khi network egress bị deny, nên cần:

- Đọc **egress policies** tại host, CNI, cloud firewall, proxy/SWG, VPN, egress gateway.
- Xem **DNS/DoH/DoT, IPv4/IPv6, QUIC/UDP, custom TCP**, không chỉ HTTPS proxy.
- Xác nhận **direct NAT, hostNetwork, VPC peering, secondary interface** không bypass bắt buộc.
- Tương quan **denied attempts**: còn attempts từ host sau T2 có thể cho thấy cơ chế chưa xóa.
- Tách **network blockage** khỏi **eradication**: deny có thể ngăn kết nối nhưng không xóa scheduled job.
- Theo dõi rule TTL/exception expiry, không cho broad allow được mở lại tự động.

Đối với một workload đã được rebuild từ trusted image, cần kiểm **controller/IaC/pod template** để không tái tạo đường cũ sau autoscaling.

### 9.6. DNS persistence và quyền quản lý zone

DNS có thể đóng vai trò **destination steering, service discovery hoặc re-entry configuration**. Kiểm tra:

1. **Authoritative zone/record audit**, delegation, registrar/DNS provider admin rights.
2. Resolver config/forwarders, conditional forwarding và proxy/PAC settings.
3. Dynamic DNS updater/service accounts, API tokens và scheduled record updates.
4. DNS changes during incident window và TTL/cache.
5. Query behavior sau T2, bao gồm alternate resolvers được phép.
6. Peer identity/TLS certificate validation tại destination—không chỉ tin một DNS answer.

Không “fix” DNS bằng cách đổi record rồi tin rằng mọi caches trên clients đã cập nhật. DNS TTL, negative caching, split-horizon và CDN can create lag; ghi **expected propagation window và test từ đúng resolver vantage points**.

### 9.7. Thiết bị mạng là tài sản có identity

Router/firewall/VPN concentrator có thể giữ **local admin accounts, SSH keys, API tokens, remote logging destinations hoặc trust relationships**. Nếu thiết bị bị nghi compromise:

- Tham khảo **vendor-supported recovery/reimage** thay vì chỉ đổi một rule.
- Kiểm management plane ACL và **out-of-band access**.
- Rotate secrets/certificates/AAA credentials trong scope incident.
- So firmware/image integrity và config với **approved versions**.
- Xác minh **backup/automation không đẩy lại config độc hại**.
- Theo dõi sessions/tunnels sau khi return-to-service.

Việc “đổi mật khẩu quản trị” không tự hoàn nguyên routing/NAT changes, và “khôi phục config” không tự chứng minh firmware hoặc identity trust còn nguyên vẹn nếu privileged compromise đã xảy ra.

## 10. Cloud/Kubernetes/CI: persistence tái tạo qua control plane

### 10.1. Cloud IAM và automation

Một tài khoản không còn login vào VM vẫn có thể **điều khiển cloud API** nếu access key, role assumption trust hoặc service principal còn hiệu lực. Tối thiểu kiểm:

- IAM users/roles/groups, access keys, federation conditions, trust policies.
- Cloud API calls trong và sau incident window; source identity/resource.
- Auto-scaling launch templates, instance profiles, user data, scheduled jobs/functions.
- Virtual network SG/NACL/firewall, route/NAT/VPN/peering, load balancers.
- Secrets manager, KMS access, token issuance, storage upload grants.
- CI/CD deploy roles và cross-account trusts.
- Approved cloud audit sinks/retention và detector coverage theo **all relevant regions/accounts**.

Một policy IAM sửa sai có thể không tạo network beacon cho đến khi token được dùng. Do đó kiểm **current effective permissions và token revocation state** bên cạnh authentication logs.

### 10.2. Container image và template là nguồn tái nhiễm

Khi một Pod lạ bị xóa:

~~~text
Compromised Pod deleted
  -> Deployment controller reconciles desired replicas
  -> New Pod created from same affected image/template
  -> Suspicious outbound process or access path reappears
~~~

Để xác minh:

1. **Deployment/StatefulSet/DaemonSet/Job/CronJob** specs của owners liên quan.
2. Container **image digest**, provenance, registry access và rollback version.
3. Sidecars/init containers, mounted volumes, config maps, secrets và bootstrap scripts.
4. ServiceAccount/RBAC/cluster role bindings, admission webhooks, operators.
5. Ingress/Service/Gateway/NodePort/LoadBalancer/egress policy và mesh enrollment.
6. GitOps automation reconciliations và unexpected resource recreations.
7. Runtime Pod UID changes, process/network telemetry và actual policy enforcement.

**Không xóa mọi CronJob/DaemonSet** để “dọn persistence”. Chỉ cô lập hoặc gỡ những artifacts đã xác minh theo incident authority, bảo toàn application availability/forensics và kiểm tra owner.

### 10.3. Kubernetes read-only trong sandbox/phạm vi được duyệt

~~~bash
# Xác định workload owners, Pods và service accounts.
kubectl get pods -n ir-lab -o wide
kubectl get deploy,statefulset,daemonset,job,cronjob -n ir-lab
kubectl get serviceaccounts -n ir-lab

# Đọc networking config/attachment trong namespace lab.
kubectl get networkpolicy -n ir-lab -o yaml
kubectl get service,ingress -n ir-lab
kubectl get endpointslice -n ir-lab

# Xem Pod/container spec thực tế và events.
kubectl get pod sample-app -n ir-lab -o yaml
kubectl describe pod sample-app -n ir-lab

# Đọc revision/rollout state, không chạy rollout thay đổi.
kubectl rollout history deployment/sample-app -n ir-lab
kubectl rollout status deployment/sample-app -n ir-lab
~~~

Các câu lệnh là **read-only**, nhưng Pod YAML/logs có thể chứa **cấu hình, env, credentials hoặc metadata nhạy cảm** nếu workload đã cấu hình sai. Bảo vệ output; không đưa full YAML vào ticket công khai. **Không list Secrets toàn cluster** chỉ vì đang làm IR nếu quyền/hypothesis không yêu cầu.

### 10.4. Khi một namespace được “làm sạch” nhưng cluster-level entry còn

Một Pod trong namespace đã được rebuild nhưng **ClusterRoleBinding, admission webhook, privileged controller, DaemonSet hoặc API credential** vẫn ở cấp cluster. Vì thế:

- Dùng **scope-based access** để kiểm các resource cluster-level liên quan.
- Giữ audit về **creation/patch/delete** và RBAC permissions.
- Kiểm tra không có **controller tự tái tạo resources** đã loại bỏ.
- Kiểm tra container runtime/hostNetwork policy nếu attack path liên quan node-level.
- Nếu nghi cluster control plane đã bị compromise, xem xét **rebuild/rotate cluster-level trust và certificate material** theo platform security runbook.

Không coi kết quả của một namespace-only scan là bằng chứng cả cluster sạch. Ngược lại, đừng mở rộng điều tra không có căn cứ sang mọi namespace nếu chain of custody/privacy/authority không cho phép.

### 10.5. Service mesh, direct paths và policy scope

Một mesh proxy có thể cung cấp mTLS, authorization và telemetry trên **traffic đi qua data plane của mesh**; nhưng:

- Không phải mọi Pod đã được inject/enroll.
- Một số ports/IP ranges/interfaces có exceptions.
- Ambient/sidecarless mode có enforcement points khác nhau.
- UDP/QUIC/custom protocols có thể không được proxy xử lý như HTTP.
- Direct Pod IP, hostNetwork, VPC peering hoặc egress gateway bypass có thể có coverage khác.

Do đó xác minh **mesh identity/certs/policy** cùng **CNI NetworkPolicy, cloud firewalls và application authorization**. Nếu proxy telemetry im lặng, kiểm **mode/enrollment và collector health** trước khi suy host không còn kết nối.

### 10.6. CI/CD và GitOps là đường persistence có kiểm soát

Automation có thể:

- Đẩy lại image/config bị ảnh hưởng sau mỗi deploy.
- Tạo cloud resources, security groups hoặc IAM grants ngoài review.
- Dùng token đã lộ để đẩy policy vào môi trường khác.
- Reconcile app settings từ một branch/repo chưa được bảo vệ.
- Tự động chạy job theo lịch, duy trì kết nối outbound không có business owner.

Biện pháp:

1. Review audit của **repository/protected branches, workflow definitions, runners và deployment permissions**.
2. Rotate/revoke credentials liên quan; ưu tiên workload/OIDC federation có scope hẹp.
3. Kiểm **signed build artifacts, provenance và approved image digests**.
4. Kiểm release/rollback pipeline không dùng **template hoặc config đã nhiễm**.
5. Dùng controlled dry-run/plan/diff trước khi apply.
6. Theo dõi **post-recovery reconciliation** trong một chu kỳ vận hành thực tế.

**Nếu một workload sạch lại bị tái nhiễm sau deploy**, nguyên nhân có thể nằm ở **source pipeline/controller**, không nhất thiết ở host/network ACL.

### 10.7. Đường sang đối tác và DR/failover

Kiểm chứng cả:

- Cross-region/cloud accounts/secondary clusters.
- DR restoration snapshots chứa secrets/scripts/ACL cũ.
- VPN/partner network tunnels và route propagation.
- Backup agents/service accounts có quyền kết nối rộng.
- Replica images và storage snapshots bị ảnh hưởng.
- Emergency exceptions còn mở trong secondary region.

**Security posture parity** là điều kiện phục hồi: backup/DR site không được trở thành một đường vào thay thế ít kiểm soát hơn.

## 11. Thiết kế tiêu chí xác nhận và khoảng quan sát

### 11.1. Bốn lớp bằng chứng cho mỗi cơ chế

Một persistence hypothesis nên được xác nhận bằng **nhiều loại bằng chứng**, thay vì chỉ “không có IOC”:

| Lớp | Câu hỏi | Ví dụ bằng chứng | Giới hạn |
| --- | --- | --- | --- |
| **Mechanism** | Đã xóa/vô hiệu hóa cơ chế tái khởi chạy/tái cấp quyền? | Trusted rebuild, removed task/key, IAM policy readback | Có thể còn cơ chế khác |
| **Access path** | Còn đường inbound/outbound/identity để tái truy cập? | Firewall/route/VPN/SG/identity tests | Một tested path không bao phủ mọi path |
| **Activity** | Sau remediation có attempts/behavior đáng ngờ? | EDR/flow/DNS/IdP/proxy, event correlation | Sensor gaps, dormant intervals |
| **Durability** | Sau restart/deploy/failover có tái xuất hiện? | Controlled maintenance validation, GitOps/HA checks | Chu kỳ/trigger chưa thử được |

Chỉ khi cả bốn lớp **đủ theo risk/hypothesis**, mới đề xuất close với residual risk rõ. Một số incident có thể **không đủ evidence** và cần giữ enhanced monitoring hoặc tiếp tục containment.

### 11.2. “Không thấy hoạt động” luôn có mẫu số

Không đủ để viết:

~~~text
No C2 events after cleanup.
~~~

Hãy viết có phạm vi:

~~~text
From 2026-11-28T04:00Z to 2026-11-29T04:00Z:
  - 12/12 scoped servers reported EDR heartbeats.
  - 3/3 scoped VPC routes had flow-log coverage.
  - DNS and proxy collectors healthy except 10-minute gap on node B.
  - No observed new connections to investigated IOC destinations.
  - Source tasks/services and affected identities read back as removed/revoked.
  - Alternative path and longer scheduled triggers not yet fully excluded.
Conclusion: No recurrence observed within measured coverage;
            follow-up needed for the recorded gaps.
~~~

**Không dùng ví dụ ngày tháng này như SLA chuẩn.** Khoảng theo dõi cần điều chỉnh theo incident, beacon cycle/cron schedules, business peak, DR schedules, token lifetime, TTL và dữ liệu thực có sẵn.

### 11.3. Chọn thời gian theo dõi có cơ sở

Cân nhắc:

- **Longest observed recurrence interval:** nếu một task chỉ chạy hàng tuần, theo dõi vài giờ là yếu.
- **Trigger-based behaviors:** reboot, login, deploy, job schedule, failover, token refresh.
- **Credential/session TTL:** old tokens có thể có thời hạn hoặc revocation propagation lag.
- **DNS cache/TTL:** dịch vụ vẫn resolve từ cache cũ, direct IP không cần DNS.
- **Business cycles:** batch settlement/backup/maintenance chỉ chạy vào ngày cụ thể.
- **Monitoring availability:** nếu EDR/proxy/offline hơn nửa cửa sổ, thời gian thực có coverage ít hơn.
- **Risk tier:** Tier-0 identity, payment, databases cần nhiều kiểm chứng/monitoring hơn test workload.

**Không nên đợi thụ động đến hết interval mới sửa cơ chế đã biết**. Trước hết phải eradication/readback và giảm quyền, sau đó theo dõi để phát hiện missed mechanisms.

### 11.4. Trigger-based verification quan trọng hơn chỉ chờ

Một cơ chế có thể kích hoạt khi:

- Host/Pod **restart**.
- User/privileged principal **login**.
- **Cron/scheduler window** đến.
- **Service deployment/reconciliation** xảy ra.
- **VPN failover** hoặc cloud DR activation.
- **IAM token/credential refresh** được yêu cầu.
- External business integration reconnect.

Với từng trigger, xác định test có thể chạy **an toàn** không. Nếu không thể thực hiện production failover/reboot, dùng **staging/DR game day, config integrity, historical logs** và ghi untested hypothesis, không giả định test đã PASS.

### 11.5. Coverage matrix

| Bề mặt | Nguồn dự kiến | Current coverage | Cần làm khi thiếu |
| --- | --- | --- | --- |
| Scoped endpoints | EDR + process/socket | All / partial / none | Restore agent, trusted host evidence |
| DNS | Managed resolvers + DoH policy | By network segment | Review alternate resolvers |
| Outbound Internet | Egress proxy + NAT/VPC flows | By route/IPv4/IPv6 | Test direct paths and exporters |
| Private east–west | CNI/firewall/flow | By subnet/cluster | Add host/app audit or collectors |
| Inbound remote access | VPN/PAM/SSH/RDP/IdP | By identity/channel | Enumerate all gateways/accounts |
| Cloud control | IAM/API audit | By account/region | Include DR/shared services |
| K8s control | API audit/registry/GitOps | By cluster | Check cluster-level controllers |
| Device configuration | Read-only snapshots + PAM | By firewall/HA member | Verify offline members separately |
| Applications | Auth/resource audit, SLO | By service | Owner confirms action outcomes |
| Data export | DLP/SWG/object audit | By protocol/resource | Document opaque/bypass paths |

Một row **partial** phải có **reason, owner, compensation và remediation date**, không được hợp nhất vào “100% monitored”.

### 11.6. Đánh giá mức chắc chắn

Một thang mô tả **mang tính hướng dẫn**, không phải xác suất thống kê:

- **Insufficient:** thiếu host/control-plane evidence hoặc sensor offline, chưa biết mechanism.
- **Limited:** vài IOC im lặng và access path bị chặn, chưa đọc lại cơ chế/identity.
- **Moderate:** known mechanisms removed, credentials reviewed, key network paths tested, còn một số trigger/coverage gaps.
- **High within scope:** trusted rebuild/remediation verified, identity revocation/readback, multi-source healthy telemetry, approved negative tests và trigger/HA checks phù hợp; residual risks được ghi.

Không ghi **“99.9% chắc chắn sạch”** nếu không có mô hình xác suất được kiểm định. Mức chắc chắn **không tăng đơn giản bằng số ngày trôi qua** khi logs thiếu hoặc scope sai.

### 11.7. Residual risk và tiêu chí tái mở case

Mỗi unknown phải có:

~~~text
Risk R-01:
  Issue: Quarterly DR scheduled job not exercised after rebuild
  Impact: Could reintroduce old connector configuration
  Compensating control: Egress restrictions and approved image baseline
  Owner: DR operations
  Due: Next approved DR game day
  Trigger for reopening: Unexpected job/image hash or external session
  Status: accepted temporarily by incident authority
~~~

Định nghĩa **reopen triggers**: IOC/destination/behavior tái xuất hiện, access key cũ được dùng, unauthorized login, scheduled task/image tự tạo lại, config drift, collector gap kéo dài hoặc new data-plane path. Một case close về vận hành **không nghĩa mọi risk vĩnh viễn biến mất**.

## 12. Detection engineering và tương quan SIEM sau xử lý

### 12.1. Detection không chỉ dựa trên IP/domain cũ

IOC matching có giá trị nhưng chưa đủ. Kết hợp:

- **Known indicators:** IP/domain/certificate/hash/process lineage liên quan.
- **Behavioral analytics:** new periodic outbound, unexpected remote management, unusual long-lived sessions.
- **Mechanism changes:** new service/task, unauthorized key/grant, new VPN peer, changed route/SG.
- **Policy drift:** firewall/WAF/proxy/egress allow, DNS forwarders, Kubernetes controllers.
- **Response state:** tries after revoke/rotation, failed logins, attempts to blocked destinations.
- **Coverage health:** missing agents/exporters, readback failures, region gaps.

**Cẩn trọng với false positives:** updates, backups, service health checks, recovery tooling và IR triage có thể tạo dấu vết khác baseline. Dùng owner/change history và source attribution.

### 12.2. Ma trận detection sau eradication

| ID | Rule/hypothesis | Nguồn | Dấu hiệu cần điều tra |
| --- | --- | --- | --- |
| P-01 | Known IOC connection after T2 | EDR+proxy/firewall | Post-remediation attempt |
| P-02 | New destination from affected workload | CNI/VPC/DNS+baseline | Potential C2 destination change |
| P-03 | Recurring egress by unexpected process | EDR/process-socket+flow | Residual scheduled agent |
| P-04 | Suspicious process/service restored | EDR/OS config audit | Re-created persistence mechanism |
| P-05 | New scheduled task after cleanup | OS audit/IaC | Reinstated trigger |
| P-06 | Unauthorized listener appears | Host socket/EDR | Remote access surface |
| P-07 | Revoked identity authentication | IdP/VPN/PAM logs | Reuse attempt or revocation gap |
| P-08 | New SSH key/admin group change | Host/identity audit | Unauthorized access path |
| P-09 | Unapproved VPN peer/tunnel | VPN/device audit | Persistent remote route |
| P-10 | Firewall/NAT allow reappears | Config diff/route audit | Network persistence in policy |
| P-11 | DNS forwarder/record drift | DNS/registrar audit | Steering/tunnel configuration |
| P-12 | Egress proxy bypass | NAT/VPC flow vs proxy | Alternate outbound path |
| P-13 | Cloud access key/trust re-created | IAM/API audit | Cloud control-plane persistence |
| P-14 | New privileged role binding | K8s RBAC/cloud audit | Privilege or controller persistence |
| P-15 | Pod/DaemonSet/CronJob recreated | K8s API/GitOps/registry | Template/controller recurrence |
| P-16 | Suspicious image digest on rollout | Registry/deployment audit | Compromised artifact reintroduced |
| P-17 | HA member config divergence | Per-device readback | Re-entry path on failover |
| P-18 | Traffic after denied path | CNI/firewall+app logs | Actual enforcement gap |
| P-19 | Unexpected access to secrets manager | Secret manager/IAM audit | Residual credential authority |
| P-20 | Unapproved SaaS connector/webhook | App/IdP/SaaS audit | Alternate external control channel |
| P-21 | Node metadata/hostNetwork anomaly | Node/CNI/cloud logs | Outside normal Pod policy path |
| P-22 | Unrecognized DNS over HTTPS destination | Egress/DNS governance | Resolver visibility bypass |
| P-23 | EDR/flow collector disappears | Health/heartbeats | Coverage failure during recovery |
| P-24 | Old service principal token issued | IdP federation audit | Trust/grant not truly revoked |
| P-25 | Management device admin account modified | PAM/AAA/config | Privileged network foothold |
| P-26 | Unexpected ingress from partner/VPN | Firewall/VPN+app auth | Re-entry/lateral movement path |
| P-27 | Restore operation reintroduces config | Backup/GitOps/deploy audit | Old persistence in recovery artifact |
| P-28 | Direct Pod IP traffic not seen at mesh | CNI+app+proxy | Potential mesh capture gap |
| P-29 | New certificate/CA trust added | PKI/device/OS audit | Unauthorized identity trust |
| P-30 | Approved backend action after suspicious login | Auth/resource audit | Scope impact beyond network |

Các rule này **không phải tất cả đều tự báo incident**: một change hợp lệ có thể tạo event cùng tên. Thiết kế cần **risk tier, allowlisted actions with actual scope validation, identity attribution và suppressions có thời hạn**.

### 12.3. Correlation với timeline T0–T4

~~~mermaid
flowchart LR
  A["Identity/token audit"] --> C["Normalize:\nasset + principal + event time"]
  B["EDR process/socket"] --> C
  D["DNS, proxy, NAT, CNI and flow"] --> C
  E["Firewall/Cloud/K8s config"] --> C
  C --> F["Case timeline T0–T4\nmechanism hypotheses"]
  F --> G["Recurrence/coverage detection\nseverity + confidence"]
  G --> H["Investigate, contain,\nupdate evidence and tests"]
~~~

**Không nối sự kiện bằng IP hiện tại đơn lẻ**: IP có thể dùng lại bởi Pod/VM khác, NAT public IP dùng chung, dynamic DNS/hostnames đổi theo thời gian. Cần **Pod UID/VM ID, process GUID, token principal, NAT tuple và mapping theo event-time**.

### 12.4. Mẫu SIEM event giả lập

~~~json
{
  "event_id": "IR011-SYN-0009",
  "event_time": "2026-11-28T06:30:00Z",
  "case": "IR-NET-TRAINING-011",
  "asset": {
    "host": "host-027",
    "workload": "orders-api",
    "environment": "production"
  },
  "hypothesis": "H-01 outbound recurrence",
  "source": {
    "type": "edr-network",
    "process_ref": "proc-guid-002"
  },
  "destination": {
    "host": "suspect.example.test",
    "ip": "198.51.100.77",
    "port": 443
  },
  "observation": "attempted_connection",
  "network_decision": "blocked",
  "mechanism_removed": "unknown",
  "priority": "high",
  "evidence_confidence": "moderate",
  "raw_secret_in_event": false,
  "synthetic": true
}
~~~

Một event **blocked connection** cho thấy policy có thể đã chặn data-plane path, **nhưng còn outbound process attempt** cần triage. Nếu correlation cho thấy event thuộc **test script/IR host** chứ không phải workload, phải sửa attribution thay vì báo persistence.

### 12.5. Pseudocode phân loại tái xuất hiện

~~~text
function assessRecurrence(event, caseState):
    if not sourceIsAuthenticated(event):
        return FINDING("untrusted telemetry source", confidence="low")

    asset = resolveAssetAtEventTime(event)
    if asset not in caseState.scope:
        return REVIEW("new related asset", scope_expansion_needed=true)

    if event.event_time < caseState.verified_eradication_time:
        return HISTORICAL("before eradication", preserve=true)

    if not sensorCoverageVerified(asset, event.event_time):
        return UNKNOWN("coverage insufficient")

    if correlatesWithApprovedTestOrMaintenance(event):
        return REVIEW("approved activity", verify_scope=true)

    if matchesKnownMechanismOrAccessPath(event):
        return ALERT("possible persistence recurrence",
                     confidence=correlateHostIdentityAndNetwork(event))

    if isNewUnapprovedRemoteAccessOrControlPlaneChange(event):
        return ALERT("new re-entry capability", confidence="contextual")

    return BASELINE_REVIEW("not a confirmed persistence indicator")
~~~

Không tự **kill process, revoke identity hoặc rollback firewall** chỉ vì một detector được viết từ pseudocode. Thay đổi production phải có incident authority, evidence review và impact plan.

### 12.6. Kiểm tra false-negative conditions

Tối thiểu đánh giá:

- IOC domain/IP thay đổi, không còn match list cũ.
- Network flow qua **unmonitored path**: IPv6, hostNetwork, VPN, secondary CNI, DR.
- Host EDR offline/tampered, process attribution unavailable.
- Scheduled tasks có interval dài hoặc require login/reboot.
- Identity grants còn hiệu lực dù token chưa sử dụng.
- Cloud resource/Pod recreated từ stale IaC.
- Flow logs sampled hoặc proxy logs không capture encrypted/opaque traffic.
- DNS cache/direct IP bỏ resolver.
- NAT/POD-IP reuse làm sai attribution.
- False log timestamps hoặc ingestion delay.

Đánh giá detection coverage phải kèm **health indicators**, không dùng “no alerts” như tiêu chí duy nhất để kết thúc.

### 12.7. Một detection cũng có thể gây lộ thông tin

Log/EDR có thể chứa **command lines, URLs, session tokens, VPN config, user names, internal IPs, PCAP payloads**. Trong SIEM finding:

- Dùng **evidence references** và redacted fields.
- Giới hạn retention và quyền forensic.
- Không đính kèm raw secret/public IP attribution khi không cần.
- Sử dụng synthetic test markers, không gửi compromised credentials thật để thử detection.
- Khi cần raw evidence, sử dụng **secure case store** và chain-of-custody controls.

**Hệ thống phát hiện persistence phải không tạo thêm đường lộ secret hoặc dữ liệu khách hàng.**

## 13. Lab offline: xác minh một ca nghi persistence qua network

### 13.1. Mục tiêu và điều kiện

Lab này dùng **hồ sơ giả lập và phép phân tích**, không có implant, C2 server thật, credential thật hoặc hành động kết nối ngoài mạng. Người học phải:

1. Khôi phục timeline **phát hiện, containment, eradication, recovery và monitoring**.
2. Phân biệt **attempt bị firewall deny** với **cơ chế đã bị xóa**.
3. Xác định các giả thuyết **host autostart, identity/VPN, route/cloud IAM và Kubernetes controller**.
4. Kiểm tra **tính đầy đủ của evidence và collector health**, không lấy log im lặng làm PASS.
5. Phát hiện **re-entry capability** chưa cần có traffic.
6. Quyết định **được trả lại production hay tiếp tục cách ly** dựa trên coverage/residual risk.
7. Viết **evidence matrix**, runbook và sign-off có uncertainty.

**Không chạy** các sự kiện giả lập trên Internet, không thử đăng nhập bằng credential đã bị nghi lộ và không tạo server beacon để “đo phản ứng” trên hạ tầng người khác. Nếu có sandbox, chỉ tạo **benign synthetic logs** và test một nguồn/đích nội bộ được cấp phép.

### 13.2. Topology

~~~mermaid
flowchart LR
  V["VPN / Identity Gateway"] --> FW["Firewall / NAT\napproved ingress and egress"]
  FW --> APP["app-027\nVM workload"]
  FW --> K8S["Kubernetes cluster\napp controller"]
  APP --> DNS["Managed DNS"]
  APP --> EGR["Egress proxy\nTLS and logs"]
  K8S --> EGR
  EGR --> EXT["Approved external APIs"]
  FW -. "Denied unapproved" .-> BAD["suspect.example.test\nsynthetic IOC"]
  EDR["EDR / host evidence"] -. "Process/socket" .-> APP
  IAM["IdP / Cloud audit"] -. "Sessions/grants" .-> V
  SIEM["SIEM / case timeline"] -. "Collect" .-> EDR
  SIEM -. "Collect" .-> IAM
  SIEM -. "Collect" .-> EGR
  SIEM -. "Collect" .-> FW
~~~

**Đích suspect.example.test chỉ là placeholder**; tuyệt đối không tạo DNS/HTTP request tới một máy bất kỳ ngoài quyền để tái hiện IOC.

### 13.3. Asset/identity inventory giả lập

~~~yaml
case: IR-NET-TRAINING-011
environment: training
incident_window:
  detection: "2026-11-28T01:00:00Z"
  containment: "2026-11-28T02:00:00Z"
  eradication_claimed: "2026-11-28T03:00:00Z"
  recovery: "2026-11-28T04:00:00Z"
assets:
  - id: host-027
    type: linux-vm
    owner: orders-platform
    role: orders-worker
    edr_expected: true
  - id: fw-east-01
    type: network-firewall
    owner: netsec
    policy: ir-egress-baseline
  - id: vpn-gw-01
    type: vpn-gateway
    owner: identity-platform
  - id: k8s-cluster-a
    type: kubernetes
    owner: platform-security
scoped_identities:
  - name: svc-orders
    type: workload-identity
  - name: vpn-legacy-operator
    type: vpn-user
  - name: deploy-agent
    type: cloud-service-principal
indicators:
  - type: destination
    value: suspect.example.test
  - type: ip
    value: 198.51.100.77
notes:
  - "All identifiers are synthetic."
  - "No credential material is included."
~~~

Các mốc của lab **được giả định** để luyện phân loại; khi điều tra thật, không coi **eradication_claimed** là trạng thái đã verified chỉ vì ticket ghi đã hoàn tất.

### 13.4. Dữ liệu synthetic events

~~~json
[
  {
    "id": "IR01",
    "time": "2026-11-28T01:00:00Z",
    "source": "edr",
    "asset": "host-027",
    "event": "unexpected_service_and_outbound_connection",
    "process_ref": "proc-guid-a",
    "destination": "198.51.100.77:443",
    "confidence": "investigate"
  },
  {
    "id": "IR02",
    "time": "2026-11-28T01:15:00Z",
    "source": "proxy",
    "asset": "host-027",
    "event": "outbound_connection",
    "destination": "suspect.example.test:443",
    "decision": "allow"
  },
  {
    "id": "IR03",
    "time": "2026-11-28T02:00:00Z",
    "source": "firewall-change-audit",
    "asset": "fw-east-01",
    "event": "ioc_destination_block_added",
    "revision": "r204",
    "actor": "ir-operator",
    "approved_incident": "IR-NET-TRAINING-011"
  },
  {
    "id": "IR04",
    "time": "2026-11-28T02:15:00Z",
    "source": "firewall-flow",
    "asset": "host-027",
    "event": "connection_attempt",
    "destination": "198.51.100.77:443",
    "decision": "deny"
  },
  {
    "id": "IR05",
    "time": "2026-11-28T02:30:00Z",
    "source": "firewall-flow",
    "asset": "host-027",
    "event": "connection_attempt",
    "destination": "198.51.100.77:443",
    "decision": "deny"
  },
  {
    "id": "IR06",
    "time": "2026-11-28T03:00:00Z",
    "source": "host-remediation",
    "asset": "host-027",
    "event": "suspicious_service_removed",
    "evidence_ref": "remediation-ack-1",
    "verification": "operator-reported"
  },
  {
    "id": "IR07",
    "time": "2026-11-28T03:05:00Z",
    "source": "identity-audit",
    "asset": "vpn-gw-01",
    "event": "unapproved_vpn_user_still_enabled",
    "principal": "vpn-legacy-operator",
    "active_session": false
  },
  {
    "id": "IR08",
    "time": "2026-11-28T03:15:00Z",
    "source": "cloud-audit",
    "asset": "k8s-cluster-a",
    "event": "deploy_agent_role_trust_changed",
    "principal": "deploy-agent",
    "approved_change": "unknown"
  },
  {
    "id": "IR09",
    "time": "2026-11-28T04:00:00Z",
    "source": "host-state",
    "asset": "host-027",
    "event": "restored_from_approved_image",
    "image_digest_verified": true,
    "network_reconnected": true
  },
  {
    "id": "IR10",
    "time": "2026-11-28T04:15:00Z",
    "source": "edr-heartbeat",
    "asset": "host-027",
    "event": "edr_online",
    "healthy": true
  },
  {
    "id": "IR11",
    "time": "2026-11-28T04:30:00Z",
    "source": "firewall-flow",
    "asset": "host-027",
    "event": "no_attempts_to_known_ioc_in_window",
    "coverage": "ipv4_primary_path_only"
  },
  {
    "id": "IR12",
    "time": "2026-11-28T04:45:00Z",
    "source": "k8s-audit",
    "asset": "k8s-cluster-a",
    "event": "unexpected_cronjob_template_present",
    "owner": "unknown",
    "running_pods": 0
  },
  {
    "id": "IR13",
    "time": "2026-11-28T05:00:00Z",
    "source": "collector-health",
    "asset": "fw-east-01",
    "event": "ipv6_flow_exporter_offline",
    "healthy": false
  },
  {
    "id": "IR14",
    "time": "2026-11-28T05:15:00Z",
    "source": "vpn-audit",
    "asset": "vpn-gw-01",
    "event": "vpn_legacy_operator_disabled_and_sessions_revoked",
    "verification": "readback_confirmed"
  },
  {
    "id": "IR15",
    "time": "2026-11-28T05:30:00Z",
    "source": "cloud-identity",
    "asset": "k8s-cluster-a",
    "event": "deploy_agent_trust_restored",
    "verification": "readback_confirmed"
  },
  {
    "id": "IR16",
    "time": "2026-11-28T06:00:00Z",
    "source": "investigation-note",
    "asset": "k8s-cluster-a",
    "event": "unexpected_cronjob_not_yet_investigated",
    "case_state": "open"
  }
]
~~~

Đây là **dataset giả lập**, không phải log thật. **IR03** là containment (block), **IR04–IR05** chứng minh có **outbound attempts bị chặn** sau block, không chứng minh service đã bị loại bỏ; **IR06** là operator-reported, cần readback. **IR07/IR08/IR12** là các đường re-entry/persistence tiềm năng ngoài host-027. **IR11** chỉ bao phủ IPv4 primary path và **IR13** cho thấy một vùng mù. Chưa thể sign-off toàn case ở IR16.

### 13.5. Dựng timeline điều tra

~~~text
01:00–01:15  suspicious process/network evidence (IR01/IR02)
02:00        containment firewall block applied (IR03)
02:15–02:30  connection attempts persist but denied (IR04/IR05)
03:00        host service removal asserted, readback pending (IR06)
03:05        unauthorized VPN account still enabled (IR07)
03:15        suspicious cloud trust change requires investigation (IR08)
04:00        host restored from trusted image (IR09)
04:15        host EDR healthy (IR10)
04:30        no primary IPv4 IOC attempts in observed window (IR11)
04:45        unexpected K8s CronJob template (IR12)
05:00        IPv6 flow logging unavailable (IR13)
05:15–05:30  VPN account and cloud trust remediated (IR14/IR15)
06:00        CronJob hypothesis still open (IR16)
~~~

Hãy viết riêng **fact** và **hypothesis**: “CronJob template present with unknown owner” là fact giả lập, còn “CronJob là attacker persistence” là giả thuyết cần xác minh qua owner, change audit và content. Không xóa CronJob production chỉ vì tên lạ.

### 13.6. Ma trận quyết định giả lập

| Hypothesis | Evidence đã có | Evidence thiếu | Trạng thái |
| --- | --- | --- | --- |
| **H1 host outbound service** | IR01/IR02, deny attempts, trusted rebuild | Config/image cross-check, post-restart/long-cycle monitoring | Partially addressed |
| **H2 VPN re-entry** | User still enabled IR07, revoked/readback IR14 | Negative auth test/audit window | Remediated, verify |
| **H3 cloud IAM trust** | Unauthorized/unknown trust IR08, restored IR15 | Impactful API use/other grants review | Remediated, verify |
| **H4 K8s CronJob recurrence** | Unexpected template IR12, case open IR16 | Owner/provenance/spec/remediation/trigger test | **Unresolved** |
| **H5 network bypass** | Firewall block/primary IPv4 flow | IPv6/private route/HA coverage | **Visibility gap** |
| **H6 IOC recurrence** | No new attempts on primary IPv4 limited window | Longer window, alternate destinations | Not sufficiently excluded |

**Không đóng case chỉ vì H1 có trusted rebuild** nếu H4/H5 còn unresolved hoặc identity chưa hoàn tất.

### 13.7. Bộ phép thử an toàn

| ID | Synthetic test/scenario | Kỳ vọng |
| --- | --- | --- |
| V01 | IOC outbound trước containment | Phát hiện event và asset attribution |
| V02 | Firewall block được ghi | Đọc lại rule, approval và đúng scope |
| V03 | IOC attempts sau block | Mark mechanism still attempted, not clean |
| V04 | Service removal report chưa readback | Mark unverified |
| V05 | Trusted host image rebuild | Digest/provenance verified |
| V06 | Host EDR healthy after restore | Heartbeat and policy version recorded |
| V07 | No IOC flow 30 minutes, task weekly | Không đủ kết luận |
| V08 | VPN account còn enabled dù idle | Re-entry capability exists |
| V09 | VPN revoked but old session active | Verify session termination semantics |
| V10 | VPN revoked/readback + negative test | Verify in scope, with test identity |
| V11 | Cloud trust policy changed | Investigate role assumption and scope |
| V12 | Cloud role restored, other API keys unknown | Residual risk remains |
| V13 | K8s Pod deleted, CronJob template still present | Persistence may recur via controller |
| V14 | CronJob removed in controlled lab | Verify controller does not recreate it |
| V15 | Signed image reused after deploy | Validate provenance and network behavior |
| V16 | IPv6 collector offline | Coverage gap, not “no traffic” |
| V17 | Primary IPv4 flow healthy | Does not cover secondary/VPN/IPv6 |
| V18 | NAT public IP maps to many Pods | Resolve event-time identity |
| V19 | DNS lookup to IOC without connection | Do not claim C2 session established |
| V20 | Proxy log missing, CNI flow present | Investigate bypass vs exporter health |
| V21 | Short-lived approved monitoring beacon | Baseline as legitimate after owner review |
| V22 | Unexpected service appears after reboot | Reopen investigation, check trusted source |
| V23 | Legitimate scheduled backup job | Do not flag solely by periodicity |
| V24 | Old access token used after rotate | Check revocation/lifetime and source |
| V25 | New API credential issued to unknown principal | Prioritize identity/control-plane triage |
| V26 | HA peer has old NAT allow | Partial remediation until per-member fix |
| V27 | Cloud SG closed but VPC peering alternate path exists | Path hypothesis remains |
| V28 | WAF denies public path, direct origin still reachable | Verify backend controls |
| V29 | Port scan of own lab finds listener | Check process/service ownership; not automatic IOC |
| V30 | No listening ports on one host | Does not exclude outbound-only persistence |
| V31 | Alert with raw token embedded | Redact, handle as secondary exposure |
| V32 | Operator uses compromised credential to “test” login | Reject test; use issued test identity instead |
| V33 | Restart scheduled in critical prod without approval | Do not run; plan safe maintenance |
| V34 | Network block prevents app business dependency | Adjust narrow policy with risk review |
| V35 | Snapshot restored from potentially tainted image | Insufficient integrity assurance |
| V36 | All known IOC paths silent, new external host appears | Behavioral/destination owner review |
| V37 | Wrong event timezone shifts post-remediation event | Normalize timestamps before conclusion |
| V38 | DNS DoH path unknown | Mark DNS coverage limited |
| V39 | DR failover untested | Record residual and game-day owner |
| V40 | All mechanisms/readbacks/tests pass with known limited gap | Conditional sign-off with risk owner |

Với V29 chỉ dùng **approved localhost/lab endpoint**. Test “không còn persistence” **không cần thử xâm nhập, không cần chạy malware và không cần gửi payload thật ra Internet**.

### 13.8. Pseudocode ra quyết định

~~~text
function evaluateEradication(caseRecord, hypotheses, evidence):
    decision = "NOT_READY"
    unresolved = []

    for hypothesis in hypotheses:
        if not hasMechanismReadbackOrTrustedRebuild(hypothesis, evidence):
            unresolved.append(hypothesis.id + ": mechanism unverified")
        if not hasAccessPathAndIdentityReview(hypothesis, evidence):
            unresolved.append(hypothesis.id + ": re-entry path unknown")
        if not hasHealthyMultiSourceCoverage(hypothesis, evidence):
            unresolved.append(hypothesis.id + ": telemetry coverage gap")
        if hasConfirmedPostEradicationRecurrence(hypothesis, evidence):
            unresolved.append(hypothesis.id + ": recurrence detected")
        if missingRequiredTriggerBasedTest(hypothesis, evidence):
            unresolved.append(hypothesis.id + ": trigger not tested")

    if unresolved is empty and approvedBusinessTestsPass(evidence):
        decision = "READY_FOR_AUTHORIZED_SIGNOFF"

    return {
      "decision": decision,
      "unresolved": unresolved,
      "evidence_refs": collectRefsWithoutRawSecrets(evidence),
      "residual_risk": caseRecord.acceptedRiskRegister
    }
~~~

Pseudocode không phải sản phẩm forensic tự động. Trong thực tế **evidence confidence**, legal/privacy requirements, asset criticality, IAM provider behavior, baseline và khả năng thử nghiệm quyết định tiêu chí sign-off; automation chỉ hỗ trợ analyst/incident commander.

### 13.9. Mẫu bài thu hoạch

~~~text
Case: IR-NET-TRAINING-011
Primary question:
  Has network-enabled persistence been eradicated?

Evidence accepted:
  ...
Unknowns:
  ...
High-priority unresolved mechanisms:
  ...
Coverage:
  EDR ... / DNS ... / proxy ... / IPv4 ... / IPv6 ... / IAM ...
Positive/negative tests:
  ...
Current conclusion:
  Not ready for full sign-off because ...
Next owner/action/deadline:
  ...
Proposed triggers for reopening:
  ...
~~~

**Tiêu chí đạt:** người học nêu được tối thiểu **hai bằng chứng thực chứng, hai gaps và ít nhất một lý do không thể kết luận sạch từ một IOC im lặng**, đồng thời mô tả phương án containment/verification an toàn.

## 14. Runbook triển khai thật: từ containment tới sign-off

### 14.1. Vai trò và thẩm quyền

Một ca nghi persistence có thể liên quan:

| Vai trò | Trách nhiệm |
| --- | --- |
| **Incident commander** | Quyết định ưu tiên/containment, risk acceptance, sign-off |
| **SOC/DFIR analyst** | Giả thuyết, timeline, evidence quality, forensic scope |
| **Endpoint/EDR team** | Process/network artifacts, host integrity, rebuild |
| **Identity/IAM team** | Accounts, sessions, keys, federation, token revocation |
| **Network/security team** | Firewall/VPN/DNS/NAT/route readback, segmentation tests |
| **Cloud/platform/K8s team** | Roles, controllers, templates, clusters, CNI/ingress |
| **Application owner** | Business flows, resource-level auth, SLO, dependency inventory |
| **Legal/privacy/compliance** | Evidence handling, notification/retention obligations |
| **Change/recovery owner** | Rollback, rollout, DR, monitoring handoff |

Trách nhiệm cụ thể thay theo tổ chức. **Những việc ảnh hưởng availability, credentials, evidence hoặc private data** cần người có thẩm quyền, không tự suy worker/SOC analyst có quyền thay đổi hệ thống.

### 14.2. Giai đoạn A — Triage và hypothesis register

1. Ghi **alert/source/time**, kiểm tra sensor health và attribution.
2. Xác minh tài sản/identity liên quan bằng **asset and network inventory**.
3. Xây timeline T0–T4 và **last known suspicious event**.
4. Liệt kê mechanisms có thể giải thích case, không chỉ IP IOC.
5. Phân loại **network vs host vs identity vs control plane**.
6. Ước tính **asset criticality và ongoing harm**.
7. Quyết định **đâu phải containment ngay**, đâu có thể thu thập thêm.

Mẫu:

~~~text
Hypothesis Register
H-01 service persists on host-027     OPEN
H-02 VPN account remains usable        OPEN
H-03 cloud role trust persists         OPEN
H-04 K8s CronJob can recreate agent    OPEN
H-05 direct NAT/IPv6 path exists       UNKNOWN

Each H contains:
  owner, asset scope, specific evidence required,
  confidence, remediation, validation and residual risk
~~~

### 14.3. Giai đoạn B — Containment

Theo incident authority và business impact:

- **Isolate** host/segment/workload qua EDR containment, NetworkPolicy hoặc scoped firewall.
- Block **known malicious destinations** tại egress với scope thích hợp, trong khi lưu ý IOC có thể đổi.
- Restrict **inbound VPN/SSH/RDP/management** hoặc isolate account/peer.
- Suspend/revoke **compromised identities/keys/sessions** theo provider and recovery needs.
- Freeze **unauthorized config changes** và bảo toàn current control-plane evidence.
- Giới hạn **automated redeploy** của affected image/template, không xóa toàn fleet mù quáng.
- Duy trì **DNS, identity, telemetry, business-critical recovery dependencies** đã phê duyệt.

**Network deny trước tiên là containment, không chứng minh eradication.** Một service có thể tiếp tục attempt connection và gây IOC-denied logs; việc đó giúp xác định cleanup chưa xong.

### 14.4. Giai đoạn C — Scope mở rộng có căn cứ

Kiểm:

1. Other hosts cùng credential/image/process/hash.
2. Identity sessions/VPN/cloud accounts liên quan.
3. Lateral movement/east–west flows từ compromised source.
4. Firewall/route/SG/VPC/VPN policies bị thay trong incident window.
5. K8s controllers, CI pipelines và DR backups có thể re-create mechanism.
6. Cloud regions, secondary sites, tenants và private partner routes.
7. Monitoring/logging bị tắt hoặc chưa được thu.

**Mở rộng theo attack paths** nhưng không xâm phạm dữ liệu ngoài scope/authority; khi một source mới xuất hiện, xin mở rộng theo quy trình của incident commander.

### 14.5. Giai đoạn D — Eradication

Trọng tâm:

- Gỡ/vô hiệu hóa **verified unauthorized startup/service/job/listener** hoặc rebuild từ trusted image.
- Thu hồi/tách **unauthorized accounts, keys, refresh sessions, service principals, VPN peers**.
- Khôi phục **IAM trust, admin RBAC, K8s controllers/templates, network devices** về approved state.
- Sửa **firewall/NAT/route/DNS/proxy/management ACL** tạo re-entry capability.
- Rotate **secrets bị ảnh hưởng** theo scope incident; đừng thay một password nhưng giữ API keys.
- Kiểm tra deployment/backup pipelines không tái tạo artifact cũ.
- Bảo vệ **logging/monitoring** và dùng evidence references.

**Đừng loại bỏ artifacts không rõ owner chỉ vì tên lạ**; xác minh bằng incident findings và lưu forensic copy trước khi thay đổi, nếu phù hợp với mức độ khẩn.

### 14.6. Giai đoạn E — Khôi phục từ trusted state

Các phương án:

| Tình trạng | Chiến lược |
| --- | --- |
| Host integrity vẫn đáng tin, cơ chế hẹp đã xác định | Targeted cleanup + readback + monitoring |
| Privileged compromise hoặc EDR tampered | Trusted rebuild/reimage, credential reissue |
| Cloud IAM/control plane bị thay | Reset trust/permissions, audit all related resources |
| K8s image/controller bị ảnh hưởng | Rebuild/redeploy từ approved digest and sanitized templates |
| Firewall/router admin compromised | Vendor-supported integrity recovery, policy restoration + credential rotation |
| VPN/identity federation compromised | Revoke/rotate sessions/keys/trust, enforce MFA/least privilege |
| DR/backup artifact nghi bị nhiễm | Validate provenance/restore point before return |

Khi phục hồi, áp **baseline segmentation, host hardening, MFA, logging, certificate verification**, không “temporary allow-all” để các ứng dụng chạy nhanh mà chưa có risk review.

### 14.7. Giai đoạn F — Verification checklist theo giả thuyết

Với từng H:

1. **Owner xác nhận mechanism gì đã bị xóa/rebuild/revoked** và bằng chứng.
2. Đọc lại **running state** từ nguồn độc lập nơi có thể.
3. Xác minh **identity/session/access paths** liên quan.
4. Kiểm **actual network reachability** tại đúng enforcement point.
5. Tương quan host/flow/DNS/IdP/cloud events sau T2.
6. Thử **trigger event** an toàn nếu cần: controlled restart/redeploy/rotation/DR.
7. Kiểm business **positive flows** và denied **negative flows**.
8. Ghi **coverage, confidence và unknowns**.
9. Nếu vẫn thấy post-remediation suspicious attempts, quay về scope/eradication.

### 14.8. Giai đoạn G — Conditional sign-off

Một quyết định sign-off cần:

~~~text
Case ID: ...
Incident commander: ...
Scope of assets/identities/networks: ...
Known mechanisms eradicated: yes/no/partial
Trusted rebuild/restore evidence: ...
Credential/identity revocation state: ...
Network path and route verification: ...
Activity monitoring since T2: ...
Coverage and missing sensors: ...
Trigger-based tests: completed / deferred and why
Business positive/negative tests: ...
Residual risks and risk acceptances: ...
Owners and follow-up dates: ...
Reopen triggers: ...
Decision: return to service / hold isolation / partial return
~~~

**“Return to service” có thể là quyết định có rủi ro còn lại được chấp nhận**, không phải bằng chứng tuyệt đối mọi phương pháp persistence bị loại trừ. Những giả thuyết có nguy cơ lớn hoặc quyền truy cập cao chưa xử lý thường nên giữ **hold isolation** hoặc hạn chế mức phục hồi.

### 14.9. Giai đoạn H — Enhanced monitoring

Sau phục hồi:

- Tăng **monitoring coverage** của affected hosts/identities/path theo thời hạn đã xác định.
- Theo dõi **failed re-entry attempts** và việc cấp credential/trust mới.
- Alert khi **service/task/controller/route/SG rule** bị tái tạo.
- So process/network baseline sau từng deployment/restart.
- Giám sát **direct egress/alternate DNS/IPv6/VPN/DR paths**.
- Kiểm **collector health**, không chỉ số lượng IOC alerts.
- Lên lịch **periodic owner review** và đóng residual issues khi có evidence.

### 14.10. Khi nào phải tái mở điều tra?

Tái mở hoặc mở incident mới nếu:

1. Cơ chế đã loại bỏ xuất hiện trở lại.
2. Identity/credential đã revoke lại được dùng thành công.
3. Xuất hiện **new unauthorized remote sessions, VPN peers, IAM grants**.
4. Pod/controller/image cũ tự tái triển khai sau cleanup.
5. Known/behavioral C2-like traffic quay lại với process attribution đáng tin.
6. Firewall/proxy/NAT/route mở đường ngoài approved baseline.
7. Monitoring source quan trọng **mất coverage** hoặc bị sửa trái phép.
8. Evidence mới cho thấy **incident scope lớn hơn** ước tính.

Một alert đơn lẻ có thể do false positive; nhưng **không bỏ qua** chỉ vì case đã được đóng. Triage theo evidence và update confidence.

## 15. Threat modeling và những tình huống khiến xác nhận sai

### 15.1. STRIDE ở giai đoạn post-incident verification

| STRIDE | Ví dụ rủi ro | Biện pháp |
| --- | --- | --- |
| **Spoofing** | Mạo danh principal hợp lệ qua token còn hiệu lực | Revoke/rotate, IdP audit, trusted identity binding |
| **Tampering** | Sửa host logs, EDR settings, firewall readback hoặc CI templates | Independent sources, config integrity, restricted admin rights |
| **Repudiation** | Tái truy cập qua shared VPN account không gắn người | PAM/session records, MFA, individual identities |
| **Information disclosure** | Secret bị lấy qua restored egress path | Least privilege, DLP, egress allowlist, resource audit |
| **Denial of service** | Containment chặn DNS/identity/business transactions | Targeted deny, SLO monitoring, recovery plan |
| **Elevation of privilege** | Cloud role/ClusterRoleBinding còn quyền cao | IAM/RBAC diff, token rotation, admission |

### 15.2. Ma trận failure modes thường gặp

| ID | Sai lầm | Vì sao kết luận sai | Điều cần làm |
| --- | --- | --- | --- |
| PF-01 | Không có IOC traffic 15 phút → sạch | Mechanism dormant/scheduled | Source config + suitable window |
| PF-02 | Firewall block thành công → sạch | Process vẫn attempt | Host persistence removal/readback |
| PF-03 | Reimage host → sạch | Identity/route/CI vẫn bị sửa | Review shared control plane |
| PF-04 | Xóa Pod → sạch | Deployment/CronJob re-create | Owner/controller/image audit |
| PF-05 | Đổi password → sạch | Refresh token/key/VPN session còn | Revoke all affected auth methods |
| PF-06 | Không thấy DNS query → sạch | Cached/direct IP/DoH | EDR+flow and resolver governance |
| PF-07 | Proxy không thấy traffic → sạch | Direct NAT/VPN/secondary interface | Alternate path/CNI/cloud coverage |
| PF-08 | Cloud SG deny → hết inbound access | Another SG/route/IPv6 attachment | Effective graph and tests |
| PF-09 | Firewall config sạch → device sạch | Firmware/AAA/admin compromise | Device integrity and credential review |
| PF-10 | IDS/IPS không alert → sạch | Signature gaps/encrypted traffic | Behavioral and source telemetry |
| PF-11 | EDR healthy ở 1 host → cluster sạch | Scope limited; other hosts uncovered | Asset coverage denominator |
| PF-12 | Token hết hạn → không còn nguy cơ | Credentials/grants khác hoặc replay window | Identity/audience/scope audit |
| PF-13 | Một negative test PASS → mọi đường deny | Test chỉ một source/path | Path/identity matrix |
| PF-14 | Không có network sessions → không còn persistence | Re-entry capability không cần session | IAM/VPN/SSH/config verification |
| PF-15 | App trả 403 → network đã chặn | Request có thể tới app rồi bị AuthZ deny | Distinguish layers |
| PF-16 | DNS IOC domain đã xóa → mọi hosts an toàn | Alternate IOC/destination/host artifact | Mechanism-centric check |
| PF-17 | Process name không còn → binary sạch | Process có thể renamed/hidden | Integrity + trusted rebuild |
| PF-18 | Collector silence → no activity | Sensor loss/tampering | Heartbeat and independent checks |
| PF-19 | DR site chưa có alerts → safe | Failover dormant/offline | DR config and game-day |
| PF-20 | IOC blocked, then full firewall rollback | Rollback xóa containment | Targeted rollback and revalidation |
| PF-21 | Cloud IAM policy readback OK | Old grants/sessions chưa revoke | Provider token/session lifecycle |
| PF-22 | Host startup items sạch | App/controller schedules tồn tại | Multi-layer trigger inventory |
| PF-23 | NAT IP = một compromised Pod | Shared NAT/IP reuse | Event-time mapping |
| PF-24 | Same hostname = same service | CDN/multi-tenant/DNS change | Peer identity and resource audit |
| PF-25 | “No false positives” = perfect detection | Không đo blind spots/misses | Test corpus and coverage |
| PF-26 | Raw PCAP lưu chung ticket | Tạo privacy/credential exposure thứ cấp | Secure forensic storage |
| PF-27 | Allowed business app hoạt động → persistence hết | Positive test không chứng minh deny | Add negative tests |
| PF-28 | Account disabled, connector webhook vẫn active | Alternate SaaS token/credential | Full integration registry |
| PF-29 | HA peer A fixed, peer B unverified | Failover có thể reintroduce route | Per-member readback |
| PF-30 | CMDB chỉ có primary region | Secondary cloud path không scoped | Cross-region inventory |

### 15.3. Attack tree phòng vệ

~~~mermaid
flowchart TD
  ROOT["Post-incident access can return"] --> M{"Residual mechanism"}
  M --> HOST["Host startup / process\nor affected restore image"]
  M --> ID["VPN/SSH/IAM/refresh token\nor delegated trust"]
  M --> NET["Firewall/NAT/route/DNS\nor alternate egress"]
  M --> CLOUD["Cloud/K8s/CI controller\nrecreates access"]
  HOST --> A["Trusted rebuild + EDR\nprocess/socket and trigger checks"]
  ID --> B["Identity inventory, revoke,\naudit and negative tests"]
  NET --> C["Semantic readback, route graph,\nsegmentation and flow validation"]
  CLOUD --> D["Template/IaC/role audit,\nreconciliation and DR tests"]
  A --> E["Evidence-based sign-off\nwith scope/coverage/residual risk"]
  B --> E
  C --> E
  D --> E
~~~

Đây là **mô hình phòng vệ**; không thể thay thế forensic analysis bằng một sơ đồ. Một incident có thể đồng thời có **host service, stolen token và cloud route drift**, nên xác nhận từng hypothesis độc lập.

### 15.4. Giảm blast radius nếu persistence chưa thể loại trừ hoàn toàn

Khi không thể hoàn thành mọi phép kiểm chứng mà business cần phục hồi:

- Giữ **segmentation** chặt cho asset, không cấp unrestricted inbound/outbound.
- Dùng **least privilege IAM**, short-lived credentials, MFA, scoped service accounts.
- Bảo đảm **application/resource authorization** độc lập với network reachability.
- Dùng egress allowlist, approved DNS resolvers, monitoring of alternate paths.
- Tăng **logging/EDR/SIEM alerting** và on-call response.
- Hạn chế **management/admin** từ những nguồn không được duyệt.
- Đặt **expiry và owner** cho mọi temporary exception.
- Ghi **risk acceptance** có thẩm quyền và điều kiện reopen rõ ràng.

**Compensating controls không biến cơ chế chưa xóa thành “đã được loại bỏ”**. Chúng chỉ giúp giới hạn khả năng khai thác trong khi điều tra/khôi phục tiếp.

## 16. Tình huống thực tế: phân biệt persistence, re-entry và vùng mù

### Tình huống A — Beacon biến mất sau khi firewall chặn IP

Sau sự cố, firewall block một IOC IP và network dashboard không còn thấy session ALLOW. Tuy nhiên firewall **DENY counter vẫn tăng theo chu kỳ** từ host vừa cách ly.

**Phân tích:** containment đã chặn đường dữ liệu nhưng **process/scheduler vẫn tạo attempts**. Cần map process–socket, xác minh mechanism và trusted remediation. Không đóng ca chỉ vì proxy không còn traffic allowed; theo dõi đến khi known mechanism được loại bỏ và negative tests/EDR hợp lệ.

### Tình huống B — Không có beacon vì task chỉ chạy theo tuần

EDR ghi một job xuất hiện trong lúc compromise, nhưng nhóm giám sát chỉ chờ 24 giờ sau cleanup không thấy traffic. Job có lịch chạy cuối tuần.

**Phân tích:** xác minh **task definitions, owner, registered scheduler và trusted build**, không chỉ chờ passive network. Nếu cần trigger test, thực hiện trong sandbox/maintenance được cấp quyền hoặc ghi residual risk cho next scheduled cycle. Đừng chạy job nghi vấn để “xem nó làm gì” trên production.

### Tình huống C — VPN user bị lộ vẫn đăng nhập được

Host ban đầu được reimage và IOC destinations bị chặn, nhưng một VPN account dùng chung còn enabled, chưa reset MFA factors/refresh sessions và management ACL còn rộng.

**Phân tích:** đây là **re-entry capability** không phụ thuộc host agent. Review principal/identity owner, session revocation, keys, MFA/PAM và VPN policies; dùng test identity được cấp riêng cho negative verification. Reimage không đủ để sign-off.

### Tình huống D — Old SSH key còn trong bastion

Incident team đổi password một Linux server, nhưng SSH authorized key không được duyệt vẫn còn trong một user account được phép đăng nhập qua bastion.

**Phân tích:** mật khẩu đã đổi không xóa access key. Dùng authorized key inventory/fingerprint, audit nguồn tạo, revoke key/trust và kiểm tra principal/session rights; giữ application automation đã được phê duyệt hoạt động.

### Tình huống E — Cloud IAM trust cho phép token mới

Static key đã bị revoke, nhưng IAM role trust policy vẫn cho một external account hoặc service principal không được duyệt assume role. Cloud audit không có API call mới trong 3 giờ.

**Phân tích:** **khả năng cấp lại quyền** vẫn tồn tại. So IAM role trust, federation conditions, audience và authorized callers; sửa trust theo owner, đọc lại policies và theo dõi issuance/use. API im lặng ngắn không chứng minh role trust đã an toàn.

### Tình huống F — Kubernetes Pod nhiễm bị xóa nhưng CronJob còn

Operator delete Pod có network activity đáng ngờ; CronJob spec vẫn dùng image digest cũ, đến lịch sẽ tạo Pod tương tự.

**Phân tích:** một Pod là hiện thân runtime, còn controller/template có thể là cơ chế durable. Review CronJob owner/config, image provenance, scheduled triggers, RBAC, egress and audit; sửa/delete theo approval và xác minh controller không tái tạo tài nguyên trái phép.

### Tình huống G — DaemonSet và hostNetwork nằm ngoài quan sát

Trong cluster, application Pods có NetworkPolicy và sidecar mesh, nhưng một node-level DaemonSet được quyền hostNetwork có outbound flow mà proxy ứng dụng không thấy.

**Phân tích:** không coi không có sidecar logs là không có traffic. Kiểm host-level CNI/EDR/network inventory, DaemonSet identity/config, cloud VPC flows và egress firewall; so với approved node agents. Tránh kết luận tất cả hostNetwork traffic đều malicious.

### Tình huống H — Firewall HA peer vẫn còn NAT rule cũ

Active firewall được sửa, nhưng standby chưa sync, trên standby vẫn có port-forward tới một admin endpoint. Dashboard chỉ hiển thị active config.

**Phân tích:** recovery incomplete. Đọc lại **mọi HA member và VDOM/context**, xác minh sync và planned failover posture. Không thực hiện failover production nếu chưa được phép; giữ containment ở tầng khác đến khi peer đã được xác nhận.

### Tình huống I — VPN tunnel của đối tác không có owner

Một site-to-site VPN tunnel tồn tại sau incident, ít có traffic và không khớp inventory. Một engineer đề xuất xóa ngay vì “persistence”.

**Phân tích:** cần tìm **business owner, remote peer, encryption/identity configuration, approved change**, cùng associated routes. Nếu unauthorized, vô hiệu theo IR authority; nếu là tunnel DR hợp lệ, cập nhật inventory và monitoring. Không cắt business-critical connectivity khi chưa có evidence.

### Tình huống J — DNS IOC bị gỡ nhưng direct IP flow còn

Đội vận hành xóa resolver override trỏ tới suspect domain. DNS logs im lặng, nhưng EDR và firewall vẫn ghi kết nối đến IP cũ.

**Phân tích:** process có thể dùng **cached resolution hoặc direct IP**; sửa DNS không thay cơ chế outbound. Điều tra process–socket và scheduler, áp outbound controls và xác minh không còn attempts sau eradication.

### Tình huống K — DoH bypass làm DNS logs không đầy đủ

Managed resolver không còn ghi domain đáng ngờ, nhưng workload có outbound HTTPS tới resolver không được phê duyệt hoặc network path không qua DNS collector.

**Phân tích:** DNS visibility gap; có thể là SDK bình thường hoặc đường name resolution ngoài governance. Review process/owner, egress allowlist, DoH/DoT controls và flow evidence; không tự tuyên bố exfiltration hay C2 chỉ từ HTTPS to resolver.

### Tình huống L — HTTPS tới CDN không đủ định danh C2

Firewall cho thấy một IP thuộc hạ tầng CDN từng liên quan IOC; đồng thời nhiều ứng dụng hợp lệ sử dụng cùng IP. Detector báo tất cả hosts nhiễm persistence.

**Phân tích:** IP shared hosting có false positives. Cần process owner, HTTP hostname/TLS metadata khi được phép, DNS/recipient identity, request behavior và application baseline; không chặn toàn CDN trên production vì một IP IOC mà chưa đánh giá ảnh hưởng.

### Tình huống M — Network flow sau T2 thực chất là session cũ

Trong firewall có bytes sau khi rule deny được đưa vào, nhưng session start time nằm **trước containment**. Team nghĩ mechanism vẫn đang tạo kết nối mới.

**Phân tích:** tách **existing session** với **new connection attempts** và provider re-evaluation semantics. Nếu containment cần ngắt phiên hiện có, thao tác theo IR authority và chỉ đúng sessions; không clear toàn session table theo phản xạ.

### Tình huống N — IAM token đã revoke nhưng application cache vẫn ghi lỗi

Sau rotation, logs ghi một service tiếp tục thử dùng token cũ và bị authentication failed. Không thấy bất kỳ thành công nào.

**Phân tích:** có thể là **stale legitimate cache** hoặc process persistence chưa dọn; cần xác minh caller/process và credential distribution. **Failed auth** chứng minh provider có thể đang chặn token, nhưng **source process dùng token cũ** vẫn cần giải thích để xử lý root cause.

### Tình huống O — Primary region sạch, DR backup còn bootstrap cũ

Hệ thống primary được rebuild; secondary region không chạy, backup image chứa startup script phiên bản cũ. Chưa có traffic bất thường ở DR.

**Phân tích:** DR là **latent persistence path** nếu restore từ image bị ảnh hưởng. Kiểm image provenance, launch templates và credentials; kiểm thử trong game day được phê duyệt. Không ký duyệt “all environments clean” dựa vào primary telemetry.

### Tình huống P — App trả HTTP 403 sau đường inbound lạ

Firewall ALLOW một kết nối từ partner subnet tới API; API ghi 403 do thiếu quyền truy cập. Một báo cáo gọi đây là “data breach confirmed”.

**Phân tích:** có thể có **network exposure** hoặc unauthorized request nhưng **resource access chưa thành công** theo evidence hiện có. Điều tra auth audit, request IDs, gateway/direct origin path và backend activity; containment network path nếu trái policy, không phóng đại impact.

### Tình huống Q — Application monitor tạo periodic request giống beacon

EDR nhìn thấy một process health agent gửi HTTPS 15 phút một lần đến vendor đã được phê duyệt. Traffic xuất hiện cả trước và sau incident.

**Phân tích:** periodicity không đủ để kết luận C2. So signer/hash, installation owner, fleet baseline và contract/telemetry destination. Nếu hợp lệ, ghi business exception có owner; không whitelist toàn bộ process name vì một binary có thể bị lạm dụng.

### Tình huống R — Cloud SG đã đóng nhưng route peering khác vẫn mở

Security team thu hẹp inbound SG trên VM; một alternate partner VPC route/SG attachment vẫn có đường đến backend. Negative test chỉ chạy từ Internet public.

**Phân tích:** cần **path matrix** cho Internet, private peer, VPN, management subnet, IPv4/IPv6. Một negative test từ public Internet không chứng minh mọi inbound paths bị deny. Xem effective attachments và IAM at backend.

### Tình huống S — EDR offline ngay sau cleanup

Một host không còn cảnh báo kể từ T2, nhưng agent gửi heartbeat cuối cùng trước T2 và service EDR đang stopped.

**Phân tích:** phải báo **insufficient coverage**, không ghi “clean”. Khôi phục sensor hoặc dùng independent forensic/read-only evidence; nếu nghi tampering/higher privilege, cân nhắc trusted rebuild.

### Tình huống T — SIEM attribution dùng IP của Pod hiện tại

Một flow trước T2 phát từ Pod IP 10.244.2.11. Pod đã bị xóa, IP cấp cho Pod khác sau đó; SIEM hiển thị tên Pod mới cho flow cũ.

**Phân tích:** sai attribution do IP reuse. Join **event-time Pod UID/IPAM allocation, node and NAT mapping**; không containment workload mới chỉ vì IP hiện tại trùng.

### Tình huống U — Reverse proxy route còn nhưng không có request

Một reverse proxy giữ mapping cũ tới management backend, hiện chưa ai truy cập. Flow logs im lặng.

**Phân tích:** **latent inbound capability** vẫn tồn tại; config diff/readback và origin ACL cần xác nhận route bị gỡ/giới hạn. Một connection test an toàn từ approved vantage point có thể xác nhận path blocked, nhưng không probe hệ thống ngoài quyền.

### Tình huống V — Collector log bị sửa destination

Management plane logs cho thấy firewall log destination được chuyển sang một sink không được duyệt. SOC SIEM không còn thấy network policy changes.

**Phân tích:** có thể có **evidence tampering/visibility suppression**. Giữ controller/PAM/independent snapshots, kiểm source integrity, readback logging config và bảo vệ credentials. Không kết luận “không change” từ SIEM silence.

### Tình huống W — CI runner còn quyền deploy image cũ

Host bị rebuild, nhưng build runner có token quyền rộng và branch không được kiểm soát vẫn có thể deploy image nghi bị ảnh hưởng.

**Phân tích:** persistence/recurrence có thể nằm ở **software supply chain**. Review repository permissions/CI jobs, artifact provenance, deployed digest, image signing và rotate runner credentials; test GitOps reconciliation.

### Tình huống X — Báo cáo “sạch 100%” dù thiếu IPv6/DoH/DR

SOC không thấy IOC nào trong proxy IPv4 24 giờ, nhưng cluster dual-stack, DoH egress và DR region chưa được giám sát.

**Phân tích:** kết luận phải nêu **observed absence on IPv4 proxy path only**, không khẳng định toàn hệ thống. Ghi residual risks, owner, due date và trường hợp cần giữ isolation. Tài sản Tier-0 có thể không đủ điều kiện return-to-service.

### Tình huống Y — Reimage host nhưng credential đã dùng trên máy khác

Một compromised service account có quyền truy cập nhiều hosts. Host đầu tiên được rebuild, nhưng IdP audit thấy principal này tiếp tục hoạt động từ một máy khác không nằm trong scope ban đầu.

**Phân tích:** mở rộng **identity-centric scoping**; xem quyền, hoạt động authorized/unauthorized và các systems nhận credential. Rotate/revoke theo risk, kiểm affected hosts; không đóng case theo host-only evidence.

### Tình huống Z — Rollback mạng vô tình khôi phục đường C2

Đội vận hành rollback full firewall snapshot để sửa một outage, đồng thời làm mất deny IOC mới được thêm trong IR.

**Phân tích:** rollback phải xét **changes xảy ra sau snapshot**, đặc biệt emergency containment. Dùng targeted diff/readback/negative tests, audit thay đổi và giữ source of truth đồng bộ.

## 17. Checklist nghiệm thu “không còn network persistence”

### 17.1. Xác định scope và giả thuyết

- [ ] Incident case ID, commander, owner, impacted services và severity rõ ràng.
- [ ] T0 detection/last suspicious action, T1 containment, T2 eradication, T3 recovery, T4 monitoring/sign-off được ghi theo UTC.
- [ ] Asset inventory bao gồm **hosts, Pods, VPN, management devices, cloud accounts, clusters, IAM, SaaS integrations và DR** trong phạm vi cần thiết.
- [ ] Mỗi hypothesis có **mechanism, access path, expected evidence, owner và status**.
- [ ] Scope mở rộng theo compromised credentials/common templates/lateral movement nếu evidence yêu cầu.
- [ ] Những out-of-scope systems được ghi rõ, không suy chúng an toàn.
- [ ] Có bản sao evidence cần thiết với chain-of-custody/privacy requirements.

### 17.2. Host và workload integrity

- [ ] Known unauthorized services/tasks/startup mechanisms đã loại bỏ hoặc host được rebuild từ trusted image.
- [ ] Readback **running services, scheduled tasks, listeners, process–socket state** đã được thực hiện.
- [ ] Process lineage/signature/image digest được đối chiếu với approved baseline khi cần.
- [ ] EDR agent **healthy** và có post-recovery heartbeat/alerts.
- [ ] Không thấy mechanism tự tái tạo sau controlled restart/redeploy/trigger tests thích hợp.
- [ ] Nếu privileged compromise, **trusted rebuild/reimage** hoặc lý do chấp nhận in-place cleanup đã được documented.
- [ ] Credentials/secrets mà affected host truy cập được đã được review và rotate/revoke theo scope.
- [ ] Không tự coi no-listening-ports hoặc no-current-connections là bằng chứng đủ.

### 17.3. Identity, VPN và remote access

- [ ] Unauthorized accounts, SSH keys, admin group memberships, VPN peers/profiles đã được rà.
- [ ] Passwords, API keys, refresh tokens, certificates, cloud keys và delegated grants liên quan đã được xử lý.
- [ ] **Active sessions/session revocation** được xác nhận theo behavior của provider.
- [ ] Federation trust, role assumption policies, token audiences/scopes được xem xét.
- [ ] Remote access ACL, management subnet, bastion/PAM/AAA đúng approved baseline.
- [ ] Có negative auth/path tests từ **test identity được cấp phép**, không dùng credential nghi lộ.
- [ ] Authentication/cloud/VPN logs trong follow-up window đủ, collector healthy.
- [ ] Những token TTL/refresh paths chưa thể revoke ngay được ghi residual risk.

### 17.4. Network configuration và reachability

- [ ] Firewall ingress/egress rules, address/service groups, schedules, policy order và inspection profiles được đọc lại.
- [ ] NAT/port forwarding, route/PBR/VRF, VPC peering, VPN và cloud SG/NACL attachments không còn unauthorized path.
- [ ] DNS records/forwarders/proxy/PAC/resolver policies và dynamic updates được review.
- [ ] HA/DR members có **approved effective revision**, không có hidden peer cũ.
- [ ] Egress proxy/SWG/IDS/IPS/DLP/WAF/mesh controls có đúng path enrollment/inspection.
- [ ] Direct-to-origin/direct Pod IP, hostNetwork, secondary interface và IPv4/IPv6 được xét.
- [ ] UDP/QUIC/DoH/DoT và other non-HTTP traffic có controls theo use case.
- [ ] New negative tests **chứng minh denied paths**, positive tests chứng minh approved business paths.
- [ ] Existing stateful sessions và NAT mapping được đánh giá khi containment cần hiệu lực ngay.
- [ ] Rule/route exceptions có owner, scope, expiry và review.

### 17.5. Cloud, Kubernetes và CI/CD

- [ ] Cloud IAM roles/trust/access keys và account/region audit được rà.
- [ ] Instance launch templates, user-data/bootstrap, scheduled automation đã được kiểm.
- [ ] K8s **Deployments, DaemonSets, CronJobs, controllers, operators và admission webhooks** liên quan được đọc lại.
- [ ] Image digests/signing/provenance và registry permissions được xác nhận.
- [ ] Workload ServiceAccounts/RBAC/ClusterRoles, secret access và projected tokens được review.
- [ ] NetworkPolicy/CNI/Ingress/Gateway/LoadBalancer/NodePort không tạo lại đường trái quyền.
- [ ] GitOps/CI runners/permissions/pipelines không tự deploy compromised artifacts.
- [ ] DR/backup images/config/snapshots được so với trusted restore point.
- [ ] Không dùng việc xóa một Pod/VM làm bằng chứng toàn control plane đã sạch.

### 17.6. Telemetry và khoảng thời gian

- [ ] EDR/host process–socket logs được thu ở tất cả scoped assets hoặc có documented exceptions.
- [ ] DNS/managed resolver và proxy/SWG logging có coverage rõ.
- [ ] Firewall/NAT/VPC/CNI/IDS/IPS/flow logs có attribution event-time ở paths cần kiểm.
- [ ] IdP/VPN/PAM/cloud/K8s admin audit được lưu và correlatable.
- [ ] **Collector heartbeat, ingestion lag, clock skew, log retention/sampling** đã được đánh giá.
- [ ] Khoảng theo dõi dựa trên **duty cycle/trigger/token TTL/risk tier**, không phải một số giờ tùy ý.
- [ ] Các paths không thấy được (IPv6, DoH, secondary network, DR) có owner và compensating controls.
- [ ] Không có recurring suspicious behavior theo known mechanisms trong **phạm vi quan sát đã khai báo**.
- [ ] Không tự tuyên bố absence ở paths không được monitor.

### 17.7. Phân loại mức bằng chứng và sign-off

- [ ] Mỗi hypothesis đánh giá **mechanism removal, access path, activity và durability** riêng.
- [ ] Phân biệt **attempt blocked**, **active connection**, **re-entry capability** và **confirmed unauthorized action**.
- [ ] False-positive causes và legitimate periodic traffic đã được xem theo owner/baseline.
- [ ] Evidence thiếu/ambiguous được ghi **unknown**, không tự điền PASS.
- [ ] Unresolved high-risk persistence được giữ open hoặc có quyết định isolation phù hợp.
- [ ] Residual risk có **risk owner, approval, due date, mitigating control**.
- [ ] Có triggers **reopen incident** và playbook on-call.
- [ ] Return-to-service có **incident commander/application owner/security review** theo chính sách.
- [ ] Báo cáo không chứa raw credentials, private keys hoặc PCAP nhạy cảm ngoài secure store.

### 17.8. Bảng nghiệm thu theo lớp

| Lớp | Bằng chứng tối thiểu | Điều kiện PASS |
| --- | --- | --- |
| **Host integrity** | Trusted image/config + process/service/scheduler readback | Không còn known mechanism; integrity theo scope |
| **Identity re-entry** | IAM/VPN/SSH/OAuth review + revocation state | Unauthorized principal/keys/grants không còn quyền |
| **Network path** | Firewall/NAT/DNS/VPN/route snapshots + tests | Đường ngoài policy không còn reachable |
| **Control plane** | Cloud/K8s/CI/GitOps diff + audit | Template/role/controller không tái tạo foothold |
| **Activity** | EDR/DNS/proxy/flow/IdP correlated post-T2 | Không có recurrence trong observed coverage |
| **Durability** | Approved restart/redeploy/failover/job-trigger tests | Known mechanism không tự xuất hiện |
| **Business recovery** | Positive connectivity, health, SLO và auth checks | Không phá luồng hợp lệ hoặc hạ bảo mật |
| **Telemetry** | Source inventory, heartbeat, time/retention coverage | Gaps được sửa/chấp nhận có thẩm quyền |
| **Evidence handling** | Secure refs, hash, audit, redaction | Bảo toàn, không tạo secondary exposure |
| **Sign-off** | Hypotheses, confidence, risks, owners/dates | Quyết định phục hồi dựa trên evidence |

**Một hàng PASS không bù cho hàng FAIL có ảnh hưởng lớn.** Chẳng hạn **host đã rebuild** không cho phép đóng case nếu **VPN account trái phép vẫn có thể đăng nhập**. Khi chưa thể kiểm một hàng, ghi **NOT TESTED/UNKNOWN** cùng lý do.

### 17.9. Mẫu biên bản xác nhận

~~~yaml
case_id: IR-NET-TRAINING-011
asset_scope:
  - host-027
  - vpn-gw-01
  - k8s-cluster-a
identity_scope:
  - svc-orders
  - vpn-legacy-operator
  - deploy-agent
known_persistence_hypotheses:
  total: 5
  verified_resolved: 3
  pending: 2
controls:
  trusted_rebuild: verified
  identity_revocation: partial
  network_path_tests: partial
  data_plane_telemetry: limited
  controller_templates: unverified
decision: HOLD_SIGNOFF
evidence:
  - forensic-ref-001
  - identity-audit-ref-002
open_items:
  - owner: platform-security
    issue: unexpected_cronjob_template
    status: investigating
  - owner: network-security
    issue: ipv6_flow_coverage
    status: incomplete
synthetic: true
~~~

**Mẫu cố ý giữ HOLD_SIGNOFF**: dù một số controls đã PASS, không thể khẳng định hết persistence khi CronJob và IPv6 path chưa được kiểm đúng.

## 18. Bài tập thiết kế và câu hỏi ôn tập

### 18.1. Bài tập kiến trúc: xác nhận hệ thống sạch sau network incident

Giả sử một tổ chức vận hành:

~~~text
Production:
  - Two datacenter regions with HA firewalls
  - Site-to-site VPNs and remote-user VPN gateways
  - A cloud Kubernetes cluster, plus one DR cluster
  - Orders API, Payments API, database and object storage
  - Central DNS, SWG/egress gateway, IDS/IPS and SIEM
  - Cloud IAM, PAM/SSO and workload identities

Incident:
  - Repeated outbound HTTPS from one VM
  - Unknown privileged service found by EDR
  - VPN service account potentially compromised
  - Cloud audit shows IAM trust change
  - One K8s CronJob template cannot be attributed
  - Firewall block stops external sessions, but some denied
    attempts continue after containment

Recovery:
  - VM reimaged from verified baseline
  - Known IOC blocked
  - Password changed, some active sessions not reviewed
  - Primary IPv4 egress proxy shows no new IOC traffic
  - Secondary region and IPv6 paths not yet covered
~~~

**Yêu cầu:**

1. Vẽ **trust-boundary map**: host, identities, VPN, firewall, K8s/CI, cloud control plane, DNS/proxy/DR.
2. Nêu tối thiểu **sáu hypotheses** về persistence hoặc re-entry.
3. Với từng hypothesis, ghi **mechanism evidence, access-path evidence, activity evidence, durability test và owner**.
4. Vạch timeline T0–T4, phân biệt **containment applied** với **eradication verified**.
5. Giải thích vì sao **firewall DENY attempts tiếp tục** là dấu hiệu cần xem host.
6. Thiết kế kiểm **VPN/SSO/OAuth/API sessions, keys, SSH access và IAM federation** mà không lộ secret.
7. Review **Firewall/NAT/route/SG/VPC peering**, HA/DR và IPv4/IPv6.
8. Review **Kubernetes Deployments/DaemonSets/CronJobs, image digest, RBAC, CI/GitOps**.
9. So EDR process–socket với DNS/proxy/NAT flow logs, mô tả cách join identity qua NAT.
10. Chọn **observability coverage matrix** và phương án khi collector offline.
11. Xây **positive tests** cho ứng dụng hợp lệ và **negative tests** cho remote access không được phép.
12. Đề xuất **monitoring window/trigger tests** theo longest likely scheduler/credential TTL.
13. Viết detection cho **IOC recurrence, new destination, re-created service, unexpected IAM grant, controller re-deploy**.
14. Lập phương án **isolation/rebuild/rotation** không phá business dependencies.
15. Viết **risk acceptance register** cho những gì chưa thể kiểm, cùng reopen conditions.
16. Nêu khi nào được **conditional return to service** và khi nào phải **HOLD_SIGNOFF**.
17. Lập báo cáo 1 trang **facts vs interpretations vs unknowns**.
18. Đề xuất hành động hậu kiểm để cải thiện **segmentation, logging, IAM và supply-chain controls**.

**Tiêu chí đạt:** không dùng “không có C2 traffic” làm bằng chứng duy nhất; xử lý cả **host mechanism, identity, network path, cloud controller và temporal coverage**. Quyết định có mức chắc chắn và giới hạn cụ thể, cùng owner cho mọi hypothesis chưa đóng.

### 18.2. Câu hỏi tự kiểm tra

**Câu 1.** Persistence qua network là gì?

*Gợi ý:* Cơ chế giúp một đối tượng duy trì/tái lập truy cập hoặc kết nối qua network, không nhất thiết luôn phát sinh traffic.

**Câu 2.** C2 và persistence có đồng nghĩa không?

*Gợi ý:* Không. C2 là trao đổi điều khiển; persistence là cơ chế duy trì/tái lập quyền truy cập, có thể không cần beacon liên tục.

**Câu 3.** Vì sao firewall block IOC không chứng minh đã eradication?

*Gợi ý:* Process/service/identity có thể vẫn tồn tại và tiếp tục attempts, chỉ bị chặn ở network.

**Câu 4.** Firewall DENY events tiếp tục sau containment gợi ý điều gì?

*Gợi ý:* Có thể còn cơ chế tạo kết nối; cần host process–socket/scheduler attribution.

**Câu 5.** Tại sao một IOC domain im lặng vài phút không đủ?

*Gợi ý:* Scheduled trigger, caching, alternate destination, offline host hoặc telemetry gap.

**Câu 6.** Ba nguồn nào giúp liên kết process với outbound connection?

*Gợi ý:* EDR process/socket, DNS client/proxy và firewall/CNI/NAT flow theo event-time.

**Câu 7.** Vì sao process name riêng lẻ là bằng chứng yếu?

*Gợi ý:* Có thể đổi tên hoặc signed process được dùng ngoài intended purpose; cần lineage/provenance.

**Câu 8.** “Không có listening ports” có loại trừ outbound persistence không?

*Gợi ý:* Không. Outbound-only service hoặc cloud identity re-entry không cần listener.

**Câu 9.** Host reimage từ trusted image có giải quyết stolen VPN token không?

*Gợi ý:* Không. Identity/VPN/refresh session phải được xem và revoke riêng.

**Câu 10.** Thay password có tự revoke mọi SSH keys không?

*Gợi ý:* Không. Cần key inventory, revoke và xác minh sshd/bastion access.

**Câu 11.** Vì sao idle VPN account vẫn có thể là residual risk?

*Gợi ý:* Nó còn khả năng xác thực/tái đăng nhập dù chưa có traffic hiện tại.

**Câu 12.** OAuth refresh token/consent grant phải được xem thế nào?

*Gợi ý:* Đây là authorization/credential path có thể cấp phiên mới; xem issuer/session revocation và scopes.

**Câu 13.** Cloud access key đã revoke có đủ nếu IAM role trust còn sai?

*Gợi ý:* Không. Trust policy có thể cho principal khác assume role và xin token.

**Câu 14.** Xóa Pod nhiễm có đủ nếu CronJob/Deployment còn template cũ không?

*Gợi ý:* Không. Controller sẽ có thể recreate Pod; kiểm spec, image digest và GitOps.

**Câu 15.** Vì sao một DaemonSet hostNetwork có thể tạo blind spot?

*Gợi ý:* Nó có thể nằm ngoài capture scope của app-sidecar/CNI policy thường.

**Câu 16.** Firewall running config sạch có chứng minh Router firmware integrity không?

*Gợi ý:* Không. Privileged compromise có thể cần vendor-supported recovery và image integrity.

**Câu 17.** NAT public IP có phải danh tính một Pod duy nhất không?

*Gợi ý:* Không. Cần NAT tuple/port/time cùng Pod UID/IP allocation.

**Câu 18.** DNS không có query tới IOC có thể bỏ sót những gì?

*Gợi ý:* Direct IP, cache, alternate resolver, DoH/DoT, dormant process.

**Câu 19.** TLS encrypted traffic cho phép suy payload luôn không?

*Gợi ý:* Không. Flow thường chỉ có metadata; process/endpoint/resource audit cần bổ sung.

**Câu 20.** Vì sao HTTPS tới CDN IP giống IOC có thể false positive?

*Gợi ý:* Shared IP/hosting nhiều tenants, cần domain/peer identity/process context.

**Câu 21.** Data-plane deny test bị cloud SG chặn có chứng minh WAF cũng chặn không?

*Gợi ý:* Không. Chỉ chứng minh end-to-end deny ở một lớp; cần evidence tại WAF để kết luận WAF enforcement.

**Câu 22.** Cơ chế persistence dormant sau containment khác active C2 như thế nào?

*Gợi ý:* Dormant không hiện activity cho tới trigger, nhưng capability vẫn tồn tại.

**Câu 23.** Vì sao phải kiểm Cloud/K8s control planes sau rebuild VM?

*Gợi ý:* IAM/controller/template/route có thể tạo lại foothold hoặc đường truy cập.

**Câu 24.** “No alerts from EDR” có đáng tin nếu heartbeat cũng mất không?

*Gợi ý:* Không. Đó là coverage gap; cần khôi phục sensor và chứng cứ độc lập.

**Câu 25.** Nên chọn monitoring window dựa trên gì?

*Gợi ý:* Duty cycle/known trigger, token lifetime, business schedules, risk tier và data coverage.

**Câu 26.** Reboot/failover test có nên chạy production ngay khi chưa được phê duyệt?

*Gợi ý:* Không. Dùng sandbox/maintenance/DR game day hoặc ghi untested residual.

**Câu 27.** Bốn lớp evidence cần kiểm cho một persistence hypothesis là gì?

*Gợi ý:* Mechanism, access path, activity và durability/trigger-based validation.

**Câu 28.** Vì sao không thể chứng minh “100% sạch” chỉ từ không có IOC?

*Gợi ý:* Unknown methods, blind spots, dormant mechanisms, alternate destinations và thời gian quan sát hữu hạn.

**Câu 29.** Mức certainty cao có bằng số ngày giám sát dài không?

*Gợi ý:* Không. Coverage, identity/mechanism verification, trigger tests và nguồn độc lập quan trọng.

**Câu 30.** Một existing TCP session sau deny mới có bắt buộc chứng minh new connection không?

*Gợi ý:* Không. Xem session start/end và stateful firewall re-evaluation.

**Câu 31.** Vì sao asset IP mapping cần theo event time?

*Gợi ý:* Pod/VM IP reuse, NAT và dynamic allocation khiến current snapshots gắn sai nguồn.

**Câu 32.** Điều gì còn cần kiểm khi VPN peer không có traffic?

*Gợi ý:* Peer/account/cert/profile, routing/ACL và authorization, không chỉ session logs.

**Câu 33.** Một traffic spike tới vendor đã duyệt có luôn là C2 không?

*Gợi ý:* Không. Kiểm process, business purpose, release, owner và destination identity.

**Câu 34.** Source log cho known IOC attempt bị deny nhưng app không nhận request: kết luận?

*Gợi ý:* Network containment có thể hoạt động; source mechanism chưa chắc được loại bỏ.

**Câu 35.** Vì sao full firewall rollback có thể gây tái mở persistence path?

*Gợi ý:* Nó có thể xóa emergency deny hoặc khôi phục NAT/route cũ; cần targeted diff.

**Câu 36.** Cần làm gì khi IPv6 collector offline mà cluster dual-stack?

*Gợi ý:* Ghi coverage gap, dùng kiểm soát khác/khôi phục telemetry, không tuyên bố mọi egress sạch.

**Câu 37.** Một CronJob không có running Pods có chắc an toàn không?

*Gợi ý:* Không. Template vẫn có thể tạo Pod vào kỳ kích hoạt.

**Câu 38.** Việc ứng dụng trả HTTP 403 có chứng minh network deny không?

*Gợi ý:* Không. HTTP 403 có thể là app authorization sau khi network đã allow connection.

**Câu 39.** Tại sao sign-off cần residual risk owner và reopen triggers?

*Gợi ý:* Không thể loại trừ mọi blind spot; phải có người chịu trách nhiệm và tiêu chí tái điều tra.

**Câu 40.** Điều kiện tối thiểu để trả một tài sản vào production sau persistence incident?

*Gợi ý:* Known mechanisms/identities/access paths được xử lý và readback; monitoring/positive-negative/trigger tests phù hợp; residual risks được quyết định theo thẩm quyền.

### 18.3. Bài tập phân tích nhật ký tổng hợp

~~~text
00:30Z EDR detects unknown service opening outbound HTTPS
01:00Z Firewall adds temporary deny for known destination
01:15Z Firewall logs new denied attempts from same host
02:00Z Operator stops suspicious service, reports removed
02:30Z Host rebuilt from trusted image
03:00Z No further primary IPv4 proxy events for known IOC
03:10Z VPN audit shows legacy-operator account still enabled
03:15Z Cloud IAM audit shows trust policy grants external principal
03:20Z Kubernetes audit shows CronJob owner unknown; not currently running
03:30Z IPv6 flow-exporter reports offline
04:00Z Operations asks SOC to mark incident resolved
~~~

**Câu hỏi:**

1. Điều gì được chứng minh tại 01:00 và điều gì **chưa được chứng minh**?
2. Các attempts 01:15 có thể chỉ ra gì về host mechanism?
3. Rebuild 02:30 đủ để close những hypotheses nào, còn điều gì phải xác minh?
4. Vì sao không có primary IPv4 IOC events sau 03:00 chưa đủ?
5. Ba bề mặt **không cần hiện C2 beacon** nào còn tại 03:10–03:20?
6. IPv6 exporter offline làm thay đổi evidence confidence thế nào?
7. Những negative tests/readbacks nào cần cho VPN/IAM/cluster?
8. Viết kết luận phù hợp tại 04:00 theo ba phần: **facts, unresolved risks, decision**.

**Đáp án định hướng:** firewall deny là containment; attempts bị chặn có thể đến từ cơ chế còn chạy. Trusted rebuild hỗ trợ H1 host integrity nhưng không giải quyết VPN user, IAM trust hoặc CronJob. IPv4 proxy silence là **bounded observation**, còn IPv6 gap. Vì thế **không đủ điều kiện sign-off toàn sự cố**; cần xử lý từng hypothesis và bổ sung coverage theo risk.

## 19. Tổng kết

- **Persistence qua network** có thể tồn tại dưới dạng **service/task, remote credential, VPN/SSH account, IAM trust, cloud role, firewall/NAT/route, DNS/proxy config hoặc Kubernetes/CI controller**. Không phải mọi cơ chế đều phát sinh traffic liên tục.
- **Containment khác eradication**: firewall deny có thể chặn kết nối trong khi process vẫn attempt, còn host reimage không thu hồi cloud/VPN credentials hoặc khôi phục controllers bị sửa.
- **C2/beaconing là một nguồn bằng chứng**, không phải định nghĩa toàn bộ persistence. Traffic định kỳ có thể hợp lệ; không thấy IOC có thể do dormant schedule, path khác hoặc thiếu sensor.
- Xác nhận phải kết hợp **cơ chế đã gỡ, quyền/đường vào còn hiệu lực, hoạt động sau T2 và độ bền sau restart/deploy/rotation/failover**.
- **EDR process–socket, DNS, proxy, firewall/NAT, CNI/VPC/IDS, VPN/identity và cloud/K8s audit** cần được tương quan theo **event time và principal/asset ID**, tránh quy nhầm qua NAT hoặc IP tái sử dụng.
- **Firewall/route/DNS/VPN/SG/K8s readback** phát hiện latent re-entry paths ngay cả khi chưa có traffic. Đừng coi một rule đã được tạo hoặc một API commit là bằng chứng data-plane enforcement.
- **Monitoring window** phải dựa trên triggers, cycle/lifetime và **coverage thật**; no-alerts khi sensor offline không chứng minh an toàn.
- **Trusted rebuild, credential revocation, IaC/template verification và segmented recovery** giúp ngăn tái nhiễm; cần bảo đảm normal business services vẫn hoạt động với least privilege.
- **SIEM detection** phải bao gồm IOC/behavior, mechanism recreation, privilege/remote access changes và telemetry-health gaps, không chỉ domain/IP matches.
- **Incident sign-off** là quyết định có thẩm quyền với **evidence, confidence, residual risk, owner, follow-up date và reopen conditions**. Không tuyên bố hệ thống “sạch tuyệt đối” nếu một phần identity, network path hoặc controller chưa được kiểm chứng.
- Mục tiêu cuối cùng của ứng phó sự cố mạng là **chặn đường truy cập trái phép, loại bỏ khả năng tái lập foothold, khôi phục dịch vụ từ trạng thái đáng tin và duy trì quan sát đủ để phát hiện tái phát**, với kết luận tương xứng bằng chứng.
