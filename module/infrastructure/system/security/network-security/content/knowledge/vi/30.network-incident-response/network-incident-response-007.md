# Xử lý credential bị lộ trên network: điều tra, thu hồi và khôi phục tin cậy

**Credential bị lộ trên network** là sự cố trong đó thông tin có thể dùng để **xác thực, ký, giải mã hoặc được cấp quyền truy cập** bị truyền, lưu lại, ghi log, chia sẻ hoặc truy cập ngoài phạm vi được phép thông qua hạ tầng mạng và các hệ thống liên quan. Credential có thể là mật khẩu, API key, OAuth token, session cookie, refresh token, SSH private key, khóa TLS/mTLS, certificate kèm private key, VPN pre-shared key, Wi-Fi PSK, RADIUS shared secret, cloud service-account key hoặc một bí mật máy–máy khác.

Bài **Xử lý credential bị lộ trên network** thuộc chương **Ứng phó sự cố mạng** của module **SECURITY_NETWORK_SECURITY**. Nó liên hệ trực tiếp với phân đoạn mạng, firewall, VPN, IDS/IPS, DNS, mạng không dây, zero trust, cloud networking và phân tích lưu lượng. Trọng tâm là **giảm nguy cơ credential bị lạm dụng, bảo toàn bằng chứng, thu hồi đúng loại quyền, khôi phục dịch vụ mà không mở thêm lỗ hổng và xác minh sự cố thực sự đã được xử lý**.

**Nguyên tắc quan trọng:** một secret xuất hiện trong PCAP/log mà nhóm được phép truy cập **không tự chứng minh đã bị kẻ tấn công lấy được**; ngược lại, chưa tìm thấy dấu vết truy cập trái phép **không chứng minh secret an toàn**. Mức độ ứng phó phải dựa trên **mức lộ, quyền của credential, khả năng thu hồi, thời gian hiệu lực, đường mạng có thể truy cập và bằng chứng sử dụng**. Tài liệu này là hướng dẫn phòng vệ và thực hành trong môi trường được cấp quyền, không phải chỉ dẫn truy cập tài khoản hay thiết bị của người khác.

Các domain **.example**, identity, IP thuộc dải tài liệu và timestamp trong ví dụ đều giả định. **Không đặt secret thật vào Markdown, terminal output, PCAP ví dụ, ticket, chat, SIEM test hoặc ảnh chụp màn hình**. Các command đọc-only chỉ dùng trên tài sản mà người học có quyền xem.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Phân biệt **credential, secret, identity, certificate công khai, private key, bearer token, refresh token, session và quyền thực tế**.
2. Nhận diện các đường lộ qua **plaintext network, reverse proxy, access logs, packet capture, DNS, telemetry exporter, firewall/VPN config, cloud và container**.
3. Đánh giá **khả năng credential đã bị tiếp cận**, không nhầm tín hiệu với bằng chứng đã bị khai thác.
4. Thiết kế quy trình **declare incident → triage → preserve evidence → contain → revoke/rotate → investigate → recover → monitor → improve**.
5. Hiểu lúc nào cần **thu hồi ngay** và lúc nào cần **phát hành credential thay thế theo trình tự an toàn** để giảm gián đoạn.
6. Chọn biện pháp riêng cho **password, OAuth/OIDC, API key, JWT, session cookie, SSH key, TLS/mTLS certificate, VPN/PSK, RADIUS/TACACS+, SNMP và cloud IAM**.
7. Phân tích network telemetry để tìm **thời điểm lộ, nơi chứa bản sao, source/destination flows và dấu vết sử dụng**, với giới hạn của TLS/NAT/DoH.
8. Phối hợp **IAM/IdP, PKI, SRE, SOC, NetworkOps, application owner, privacy/legal** theo phạm vi sự cố.
9. Xác minh **old credential thật sự không còn được chấp nhận** ở mọi enforcement point và sessions/tokens liên quan đã được xử lý.
10. Xây **ma trận kiểm thử, playbook và runbook** có thể áp dụng trong môi trường sản xuất một cách có kiểm soát.

## 2. Định nghĩa: credential khác identity và quyền như thế nào?

Một **identity** là định danh chủ thể: người dùng, thiết bị, workload, service account hoặc tổ chức. **Credential** là bằng chứng hoặc vật liệu dùng trong một cơ chế xác thực để chứng minh hoặc đại diện cho identity. **Authorization** quyết định chủ thể được làm gì với tài nguyên.

| Khái niệm | Ví dụ | Tại sao phải phân biệt? |
|---|---|---|
| **Identity** | Service account orders-api | Tên chủ thể, không tự là secret |
| **Password** | Mật khẩu người dùng | Có thể dùng để thực hiện authentication |
| **API key** | Khóa truy cập partner API | Thường đại diện cho app hoặc tenant; scope tùy provider |
| **Bearer access token** | OAuth access token | Ai giữ token có thể dùng trong phạm vi token nếu verifier chấp nhận |
| **Refresh token** | Token xin access token mới | Có thể duy trì truy cập dài hơn access token |
| **Session cookie** | Session ID cookie | Trỏ tới phiên do server quản lý hoặc session data có cơ chế khác |
| **Private key** | SSH/TLS client key | Dùng cho chữ ký/chứng minh sở hữu; không phải public certificate |
| **Public certificate** | X.509 certificate không kèm private key | Thường được thiết kế để phân phối; không mặc định secret |
| **VPN PSK** | Secret chung cho IKE hoặc kết nối khác | Có thể ảnh hưởng nhiều peers, không chỉ một user |
| **Authorization scope** | read:invoices | Quyền mà credential/identity được cấp |
| **Trust anchor** | Root CA certificate tin cậy | Công khai, nhưng thay đổi truststore có thể làm mở rộng vùng tin cậy |
| **Recovery code** | Mã khôi phục tài khoản | Secret có thể cho phép khôi phục/bỏ qua một số bước xác thực |

### 2.1. Credential lộ không nhất thiết là toàn bộ bí mật

Một packet chứa **server TLS certificate công khai** không có nghĩa server private key bị lộ. Một **JWT header/payload đã giải mã Base64URL** có thể chứa claims công khai đối với người đang có token; tuy nhiên **toàn bộ chuỗi bearer JWT** vẫn có thể là secret dùng để truy cập. Một **hash hoặc fingerprint** của certificate không phải private key.

### 2.2. Bearer token khác proof-of-possession

**Bearer token** có thể được sử dụng bởi bất kỳ ai có token nếu các điều kiện verifier cho phép. **Sender-constrained token** như token ràng buộc với mTLS certificate hoặc DPoP key có thêm điều kiện chứng minh sở hữu khóa. Nếu token lộ nhưng proof key không lộ, rủi ro replay có thể giảm; **không coi rủi ro bằng không** nếu key, endpoint hoặc implementation cũng bị ảnh hưởng.

### 2.3. Authentication khác session lifetime

Đổi password thường **không mặc định xóa mọi session** trên tất cả sản phẩm. Thu hồi refresh token cũng không mặc định hủy **access token tự chứa** đang còn hiệu lực nếu downstream services chỉ xác minh chữ ký và không hỏi authorization server. Phải xác minh behavior của từng IdP/verifier.

## 3. Các mức độ “bị lộ” cần phân biệt

**Tình trạng lộ** là phần của triage, không chỉ trạng thái có/không.

| Tình trạng | Ví dụ | Bằng chứng cần tìm |
|---|---|---|
| **Có thể bị ghi lại** | App truyền Basic Auth qua HTTP nội bộ | PCAP/flow path, TLS presence |
| **Đã nằm trong log/PCAP được quản lý** | Proxy debug log chứa token | Raw storage path, quyền truy cập, thời gian |
| **Đã hiển thị cho người ngoài scope** | Dashboard mở nhầm toàn doanh nghiệp | ACL/access logs, người có quyền xem |
| **Đã bị truy xuất/tải xuống trái phép** | Unauthorized account export PCAP | Query/download audit, storage logs |
| **Có dấu hiệu credential bị dùng** | API calls từ IP/ASN/device lạ với cùng principal | Auth/authorization logs và session binding |
| **Đã xác minh credential bị lạm dụng** | Có confirmed unauthorized resource action | Forensic correlation, resource audit |
| **Mức ảnh hưởng chưa rõ** | Export logs đã hết hạn, không có audit đủ | Ghi uncertainty, ứng phó theo quyền/rủi ro |

**Không chờ bằng chứng khai thác chắc chắn mới xử lý một secret quyền cao còn hiệu lực đã bị public**. Trái lại, không công bố chắc chắn “data exfiltration confirmed” nếu chỉ có sự cố cấu hình log nhưng chưa có bằng chứng truy xuất.

### 3.1. Thời điểm phát hiện, thời điểm phát sinh và thời gian hiệu lực

Cần phân biệt:
- **First exposure**: secret bắt đầu nằm trên đường/bản ghi có thể tiếp cận.
- **First observable access**: lần đầu ghi nhận ai đó đã đọc/export artifact.
- **Last exposure**: lần cuối secret được phát sinh trong log/packet chưa được kiểm soát.
- **Revocation effective**: thời điểm verifier thực sự từ chối secret cũ, có thể khác thời điểm admin bấm “revoke”.
- **Session termination**: lúc các phiên đã tạo không còn dùng được.
- **Investigation window**: có thể cần bắt đầu **trước first known exposure** nếu logs chưa đầy đủ.

## 4. Bề mặt lộ credential trong hạ tầng mạng

| Đường lộ | Ví dụ cụ thể | Điều cần làm rõ |
|---|---|---|
| **Plaintext protocol** | Telnet, FTP, HTTP Basic không TLS, legacy admin API | Secret có thực sự qua wire plaintext không, ai thấy được path |
| **TLS terminated proxy** | Reverse proxy ghi Authorization/Cookie headers | Có raw headers tại proxy/log exporter/backend không |
| **Packet capture** | PCAP lưu payload/headers có credentials | File nằm đâu, ai đọc, retention, download/export |
| **Access logs / tracing** | URL query parameter có API key, trace attributes chứa token | Redaction ở source/collector/storage và bản sao |
| **VPN/network appliance config** | Pre-shared key hay service password trong config backup | Backup encryption/RBAC/config repository |
| **DNS** | API token lỡ đặt trong subdomain/TXT | Query logs, DNS caches, external resolver visibility |
| **Container/Kubernetes** | Secret được in ra startup logs hoặc debug endpoint | Pods/log agents/RBAC, ingress/egress network paths |
| **Cloud** | Cloud access key gửi vào webhook/logging SaaS | IAM audit và region/account scope |
| **Wi-Fi/NAC** | PSK, RADIUS shared secret hoặc EAP password bị lộ | Client/AP/RADIUS scope, sessions, roam effects |
| **Email/chat/ticket** | Công khai configuration snippet có key | Distribution/retention và copy permissions |
| **Third-party monitoring** | SaaS ingest đầy đủ headers hoặc PCAP | Vendor access, contractual incident handling |
| **CI/CD artifacts** | File môi trường chứa VPN/server credentials | Build logs, artifact access, dependency credentials |

### 4.1. TLS không bảo đảm hết nguy cơ lộ

TLS giúp bảo vệ dữ liệu **trên đoạn đường mã hóa** khi được cấu hình/xác thực đúng. Tuy nhiên:
- Tại **client** trước mã hóa hoặc **server** sau giải mã, secret vẫn tồn tại trong process/memory.
- Load balancer, WAF hoặc reverse proxy kết thúc TLS có thể thấy HTTP headers.
- Debug/tracing code có thể ghi token vào logs.
- Proxy re-encryption có thể bảo vệ hop tiếp theo nhưng log tại proxy vẫn lộ secret.
- Một PCAP TLS được mã hóa **không tự chứa plaintext header**, trừ khi có secrets giải mã hoặc endpoint capture.

### 4.2. Điều gì thường không phải credential trong capture?

- TLS certificate công khai không kèm private key.
- Public SSH host key.
- DNS A/AAAA/CNAME thường dùng để phân giải.
- IP/MAC address hoặc service name riêng lẻ.
- Certificate serial number hoặc fingerprint.
- **Trace ID** hoặc correlation ID, trừ khi một ứng dụng thiết kế sai và dùng làm authorization token.

Các dữ liệu này có thể **nhạy cảm về topology/identity**, nhưng không phải vật liệu dùng đăng nhập theo cùng cơ chế với password/API key. Không rotate hàng loạt public certificate chỉ vì thấy certificate chain trong TLS handshake.

## 5. Threat model: actor có thể làm gì với credential?

~~~mermaid
flowchart LR
    EXP[Secret exposed in network/log/artifact] --> ACCESS{Can attacker access secret?}
    ACCESS -->|No / unknown| TRIAGE[Validate visibility and preserve evidence]
    ACCESS -->|Yes| VALID{Credential still accepted?}
    VALID -->|No| INVEST[Investigate historical use]
    VALID -->|Yes| SCOPE[Scopes, trust boundaries and reachable targets]
    SCOPE --> USE[Possible unauthorized access / lateral movement / exfil]
    USE --> RESP[Contain, revoke, recover and verify]
    TRIAGE --> RESP
    INVEST --> RESP
~~~

### 5.1. Hai ranh giới cần phân tích

1. **Data-access boundary:** đối tượng nào có thể xem packet/log/artifact chứa secret?
2. **Credential-use boundary:** nếu có secret, đối tượng đó có thể gọi endpoint nào, từ vị trí mạng nào, với quyền gì?

Ví dụ một VPN PSK bị lộ trong config backup nhưng firewall chỉ cho nguồn từ danh sách IP đối tác có thể giảm nguy cơ từ Internet. Tuy nhiên **IP allowlist có thể thay đổi hoặc bị bypass**, và secret chung có thể ảnh hưởng nhiều peers; không được bỏ qua việc thay key.

### 5.2. Quyền không chỉ nằm trong một token

- Một API key có thể có quyền ghi dữ liệu nhiều tenants.
- Một session cookie có thể cho truy cập user-level nhưng không đủ cho admin step-up.
- Một cloud service-account key có thể nhận permissions từ role bindings thay đổi theo thời gian.
- Một SSH key có thể được chấp nhận trên nhiều servers do copy authorized_keys.
- Một RADIUS shared secret liên quan trust giữa NAD và server, không chỉ một client.
- Một root/intermediate CA private key có **blast radius lớn hơn leaf service certificate key**.

### 5.3. Giới hạn từ góc nhìn network

Nếu traffic đi qua VPN/mTLS/DoH/TLS, một sensor thụ động có thể chỉ thấy **IP/port/bytes/time**; không nên suy rằng đã thấy nội dung secret. Dấu vết xác thực và authorization thường nằm ở **IdP, API gateway, IAM hoặc application audit**, cần quyền truy xuất tương ứng.

## 6. Phân loại mức độ nghiêm trọng dựa trên rủi ro

Không có thang mức độ chung áp cho mọi tổ chức. Dùng khung đánh giá theo **quyền, độ phơi nhiễm, hiệu lực, khả năng reachability, dấu hiệu abuse và hậu quả dữ liệu**.

| Yếu tố | Thấp hơn tương đối | Cao hơn tương đối |
|---|---|---|
| **Quyền của credential** | Read-only, một sandbox resource | Admin, signer, CA, wildcard production scopes |
| **Nơi lộ** | Kho nội bộ mã hóa và audited | Public repo, Internet object, shared dashboard |
| **Thời gian hiệu lực còn lại** | Đã hết hạn và verifier xác nhận từ chối | Long-lived static key còn hoạt động |
| **Khả năng sử dụng** | Proof-of-possession key không bị lộ, mạng cô lập | Bearer token có thể replay từ Internet |
| **Bằng chứng truy cập** | Không có ngoài scope nhưng audit đầy đủ | Có downloads, foreign logins hoặc API actions |
| **Khả năng lan truyền** | Một test device | Shared secret cho nhiều devices/regions |
| **Dữ liệu liên quan** | Public test data | Confidential/restricted, customer records |
| **Khả năng xác minh** | Audit đầy đủ | Logs bị xóa, retention hết, thiếu telemetry |

### 6.1. Cảnh báo về tính điểm số

Có thể dùng hệ điểm nội bộ cho triage, nhưng **đừng cộng điểm rồi coi là phép đo rủi ro tuyệt đối**. Một private key của intermediate CA hoặc key khôi phục root IAM có thể buộc ưu tiên rất cao dù “số lần truy cập đã thấy = 0”.

### 6.2. Ví dụ ba mức ưu tiên

- **Khẩn cấp:** token admin production công khai và còn hiệu lực; hoặc đã thấy unauthorized use.
- **Cao:** VPN PSK shared nhiều sites nằm trong backup có quyền xem rộng nhưng chưa thấy abuse.
- **Cần xử lý có kế hoạch:** token lab đã expired, audit chứng minh chỉ được lưu trong kho hạn chế, không còn ứng dụng sử dụng.

Đây là **minh họa**, không thay playbook mức độ thực tế hoặc nghĩa vụ báo cáo theo pháp luật/hợp đồng.

## 7. Vai trò, trách nhiệm và kênh phối hợp

| Vai trò | Quyết định/trách nhiệm chính |
|---|---|
| **Incident Commander (IC)** | Tổ chức incident, ưu tiên, timeline, thông báo và quyết định xử lý theo thẩm quyền |
| **SOC / Threat Hunting** | Tổng hợp indicators, phát hiện unauthorized use, giữ chain of evidence |
| **IAM / IdP Owner** | Disable account, revoke sessions, rotate secrets, kiểm tra federation |
| **PKI / Security Engineering** | Key compromise, revoke/reissue certificates, CA trust remediation |
| **NetworkOps** | VPN/NAC/RADIUS/firewall/route segmentation, failover, appliance credential handling |
| **SRE / Platform** | Workload deployment/secret stores/agents, rollback và application SLO |
| **Application Owner** | Token scope, client update, service behavior và business impact |
| **Cloud Security** | IAM policy, cloud keys, service principals, provider audit và STS sessions |
| **Privacy/Legal/Compliance** | Data classification, contractual/regulatory incident considerations |
| **Communications/Support** | Approved internal/partner/user notifications và status updates |

### 7.1. Secure communication khi trao đổi incident

- Dùng incident channel có quyền phù hợp; tránh dán actual secret vào tin nhắn.
- Mỗi secret tham chiếu bằng **secret ID, owner, scope hoặc fingerprint an toàn**.
- Tách nhánh technical containment khỏi thông báo tới rộng rãi.
- Ghi quyết định và người phê duyệt, đặc biệt khi phải gây gián đoạn VPN/identity.
- Nếu cần đối tác rotate shared secret, dùng kênh được xác thực đã thống nhất; không gửi key mới qua email công khai.

### 7.2. Đảm bảo người có thẩm quyền

Người thấy credential trong PCAP không mặc nhiên được phép **dùng thử credential** để xác minh. Thử đăng nhập có thể tạo truy cập trái quyền và làm sai evidence. Xác minh hiệu lực qua **IdP/admin API/audit hoặc test harness được cấp phép**, không dùng credential thật ngoài quy trình.

## 8. Vòng đời ứng phó sự cố lộ credential

~~~mermaid
flowchart TD
    DETECT[Detect / receive report] --> TRIAGE[Triage scope and sensitivity]
    TRIAGE --> PRESERVE[Preserve evidence and stop further logging]
    PRESERVE --> CONTAIN[Contain accounts, network paths and sessions]
    CONTAIN --> ROTATE[Revoke or rotate credentials safely]
    ROTATE --> INVESTIGATE[Investigate historical use and blast radius]
    INVESTIGATE --> RECOVER[Restore business flows with new secrets]
    RECOVER --> VERIFY[Verify old credentials rejected]
    VERIFY --> MONITOR[Heightened monitoring and lessons learned]
    MONITOR --> CLOSE[Incident closure with evidence]
    INVESTIGATE -.New indicators.-> CONTAIN
~~~

**Đây không phải quy trình tuần tự cứng nhắc.** Với credential admin còn hiệu lực và nghi lạm dụng, revoke/disable có thể cần diễn ra **ngay cùng lúc với preserve evidence**. Với shared secret ảnh hưởng core routing/AAA, cần emergency change/HA failover nhưng không trì hoãn vô hạn. Tính chất credential và mức rủi ro quyết định thứ tự.

### 8.1. Những mốc phải có

- Detection timestamp và nguồn báo.
- First/last known exposure, last known valid use.
- Địa điểm storage, telemetry pipeline, hệ thống phụ thuộc.
- Incident severity, owner, approver.
- Credential status per verifier: old accepted/revoked/expired/unknown.
- Session/refresh token state.
- Key replacement deployment status ở clients và servers.
- Negative test results old credential tại scope đã phê duyệt.
- Monitoring window và unresolved uncertainties.

## 9. Triage: 15 quyết định đầu tiên

1. **Đừng sao chép secret ra thêm nơi khác.** Dùng metadata/reference.
2. Xác nhận có đúng là secret hay dữ liệu công khai/đã redact.
3. Xác định secret type: password, API key, bearer/refresh token, private key, PSK, cert.
4. Xác định principal, account/project/tenant, environment và owner.
5. Xác định mức quyền và tài nguyên reachable từ mạng nào.
6. Xác định thời điểm first seen và last seen theo log/PCAP.
7. Xem nơi artifact đã nhân bản: object storage, SIEM, backup, ticket, SaaS.
8. Đánh giá khả năng bên ngoài scope truy cập vào artifact.
9. Kiểm tra secret còn hiệu lực, expiry và khả năng revocation.
10. Tìm dấu hiệu auth/API use bất thường **không cần dùng secret thử đăng nhập**.
11. Xem có sessions, refresh tokens, long-lived connections liên quan không.
12. Đánh giá impact khi thu hồi: production dependencies, VPN, network device, route.
13. Phối hợp IC và đúng owner để chọn **revoke now / staged rotation / emergency isolation**.
14. Khóa nguồn tạo lộ mới: debug logging, excessive capture, unsafe exporter.
15. Ghi quyết định, evidence và điều chưa biết; không tuyên bố “an toàn” khi thiếu logs.

### 9.1. Một incident worksheet

| Trường | Mô tả ví dụ |
|---|---|
| Incident ID | INC-example-2026-007 |
| Secret reference | secrets/payments/partner-key-v2 (không phải giá trị key) |
| Type | Partner API key |
| Owner | payments-platform |
| Environment | production |
| Identity/scope | partner-client, write:invoice |
| First/last exposure | UTC timestamps đã kiểm tra |
| Artifact locations | proxy debug logs + SIEM index + backup |
| Current status | suspected exposure, abuse unconfirmed |
| Containment decision | stop header logging + scope network + rotate |
| Revocation plan | new key provision → deploy → old key revoke, hoặc revoke ngay nếu abuse |
| Dependent services | orders-api, billing-worker |
| Test evidence | new key works, old key denied, no new log leak |
| Remaining uncertainty | storage export audit incomplete |

Đây là **mẫu ghi chép**, không có credential thật.

## 10. Bảo toàn chứng cứ nhưng không nhân bản secret

Một sai lầm là để điều tra “cho chắc” mà chép nguyên **Authorization header, cookie hoặc private key** vào nhiều công cụ. Điều đó tăng phạm vi lộ. Cần phân biệt **raw evidence** được bảo quản trong kho có quyền với **thông tin làm việc** đã redacted.

### 10.1. Evidence có thể cần giữ

- Packet capture/time range từ sensor được cấp phép.
- Auth/authorization audit events (actor, IP, device, method, MFA, result).
- Proxy access logs và collector exporter/version config.
- Cloud IAM API events, role assumption, token issuance và resource actions.
- VPN/NAC/RADIUS/TACACS+ session logs.
- Kubernetes audit/Pod UID/deployment/secrets references.
- Key/certificate issuance/revocation/expiry events.
- Network flow/NAT mapping logs, firewall rules và changes.
- Files/object metadata: creation, permissions, accesses, downloads, copies.
- Evidence of old secret rejection và new secret acceptance.

### 10.2. Chain of custody và hạn chế truy cập

1. Ghi ai thu, khi nào, sensor/tool version, time zone và filter.
2. Lưu bản gốc trong kho mã hóa với quyền hạn chế, audit mọi read/export.
3. Tạo bản phân tích đã redacted khi có thể, không chỉnh sửa bản gốc.
4. Đặt retention theo incident, data classification và nghĩa vụ pháp lý.
5. Không đính kèm raw PCAP có secrets vào ticket/chat rộng.
6. Nếu cần giá trị để khớp record, dùng hệ thống **secret lookup đã được bảo vệ** và phương pháp so khớp hạn chế.
7. Hash plaintext password/token đơn giản có thể bị dictionary/replay offline khi entropy thấp; nếu tạo token fingerprint thì cần cách có **keyed HMAC hoặc hash với secret entropy cao, quyền hạn chế** theo chính sách.
8. Khi báo cáo ngoài đội, chỉ đưa **secret ID/last few characters đã được phép**, không cung cấp full value.
9. Không xóa raw forensic data một cách tùy tiện nếu có legal hold; ngăn access/replication mới và làm theo phê duyệt.
10. Không để log redaction làm mất bằng chứng cần thiết về **actor, timestamp, scope, result**.

### 10.3. Tại sao “xóa dashboard” chưa đủ?

Dữ liệu có thể còn ở collector buffers, SIEM raw index, object storage, replicas, backup, exports, email attachments hoặc third-party monitoring. Chặn hiển thị ở UI chỉ là **một bề mặt**. Incident owner cần inventory tất cả bản sao, thu hẹp quyền ngay và xử lý xóa/retention theo quy trình có kiểm toán.

## 11. Packet capture và network telemetry: thấy gì, không thấy gì?

| Điểm quan sát | Có thể thấy | Giới hạn |
|---|---|---|
| PCAP HTTP plaintext | Headers/payload có thể chứa Basic Auth/token | Chỉ trong đường qua sensor, capture đủ bytes |
| PCAP HTTPS TLS | IP/port, TLS metadata theo version/visibility | Không đọc Authorization header nếu không giải mã hợp lệ |
| Reverse proxy TLS termination | HTTP headers/URL/body nếu logging/inspection | Có thể trở thành nơi lộ secret mới |
| Firewall flow logs | Source/destination/port/bytes/allow/deny | Không xác định credential value |
| NetFlow/IPFIX/sFlow | Network volume/flow metadata, sampled headers khi có | Sampling/coverage và packet privacy |
| VPN/AAA logs | User/device/auth result/tunnel lifecycle | Không chứng minh mọi packet payload |
| DNS query logs | Domains/truy vấn/response theo scope | Không tự biết token dùng ở HTTPS |
| EDR/Endpoint logs | Process, auth attempts, file access theo agent | Cần quyền và coverage |
| Cloud IAM logs | Principal/API/action/result | Có log gaps và thời gian ingestion |
| App audit | Resource operations, tenant/user authZ | App logs có thể bị sửa nếu máy bị chiếm |

### 11.1. TLS private key không truyền trong handshake chuẩn

Trong TLS thông thường, **private key của server/client không được gửi qua handshake**. Certificate công khai có thể xuất hiện tùy phiên bản/ngữ cảnh, còn private key nằm ở endpoint/HSM/keystore. Nếu nghi private key lộ, bằng chứng thường đến từ **key file, config export, backup, memory compromise, CI artifact, source repository hoặc secret store access**, không phải chỉ thấy TLS certificate trong PCAP.

### 11.2. TLS decryption để điều tra phải có thẩm quyền

Có thể tồn tại doanh nghiệp sử dụng proxy giải mã TLS hợp lệ hoặc app-level tracing để xem header. Điều đó làm **tăng trách nhiệm bảo vệ decrypted data**. Không tắt certificate verification, yêu cầu user cung cấp secrets hay tự lấy TLS session keys nếu không có phê duyệt/kiến trúc phù hợp.

### 11.3. Khi lộ secret qua URL hoặc DNS

URL query parameter đôi khi bị ghi qua reverse proxy, browser history, analytics hoặc shared logs. Token nằm trong DNS labels/TXT có thể xuất hiện ở nhiều resolvers, DNS security logs và caches. **Đổi secret và sửa application design**, không chỉ ẩn một dòng log. Với DNS, traffic có thể đi ra authoritative infrastructure của bên ngoài; phải đánh giá phạm vi truy vấn.

## 12. Xác định blast radius và đường lạm dụng

Một credential có thể được cấp cho **một service identity** nhưng chấp nhận ở **nhiều tài nguyên** hoặc môi trường. Blast radius là tổng hợp **quyền + reachability + thời gian + khả năng lạm dụng**, không chỉ số client biết secret.

### 12.1. Lập đồ thị phụ thuộc

~~~mermaid
flowchart TD
    K[Exposed key reference] --> ID[Principal / token audience / permissions]
    ID --> API[API resources / SaaS tenant]
    ID --> CL[Cloud IAM roles / projects]
    ID --> VPN[VPN / network services if applicable]
    API --> DATA[Data classifications and operations]
    CL --> DATA
    VPN --> NET[Reachable network segments]
    NET --> DATA
    K --> DEP[Applications/agents holding old secret]
    DEP --> ROT[Rotation and availability plan]
~~~

### 12.2. Những trường cần xác định

- Credential **type, issuer, tenant, audience, scope, environment và expiration**.
- Who/what: users, Pods, devices, CI jobs, network appliances.
- Where: accepted endpoints, trust domains, resource policies, service accounts.
- Privileges: read, write, admin, token creation, signing, key management.
- Network reachability: Internet, VPN, peering, private endpoint, management zone.
- Distribution: secret store references, environment variables, config backups, PKCS#12 bundles.
- Active sessions/refresh-token families, delegated permissions hoặc chained credentials.
- Old/current consumers và rotation dependencies.
- Monitoring/identity logs đủ để phát hiện unusual use không.

### 12.3. Blast radius có thể gián tiếp

Nếu một cloud key chỉ có quyền đọc Secret Manager, kẻ lạm dụng có thể lấy **nhiều secrets khác**. Nếu một VPN credential cho phép truy cập network management subnet, rủi ro không dừng ở VPN login. Nếu một key là intermediate CA signing key, kẻ có key có thể tạo certificate trông hợp lệ trong phạm vi chain/policy. **Đánh giá khả năng privilege chaining theo authorized security review**, không tự dùng credential để khai thác thử.

## 13. Xử lý mật khẩu người dùng và tài khoản quản trị

Mật khẩu thường tham gia quy trình xác thực **có trạng thái hoặc nhiều bước**: đăng nhập, MFA, session creation, refresh hoặc federation. Khi mật khẩu lộ, chỉ đổi chuỗi ký tự có thể chưa đủ.

### 13.1. Quy trình triage và kiểm soát

1. Xác định user/account ID, system owner, IdP và các hệ thống dùng password trực tiếp.
2. Đánh giá **password đã lộ nguyên văn** hay chỉ hash/trích đoạn; hash bị lộ cũng cần threat assessment riêng.
3. Kiểm tra last successful/failed login, new devices, impossible travel theo độ tin cậy, MFA events và password resets gần đây.
4. Disable hoặc lock account tạm thời nếu mức rủi ro/phạm vi đòi hỏi và theo policy.
5. **Reset password qua kênh được xác thực**, không gửi password mới qua ticket/chat.
6. **Revoke sessions/refresh tokens** theo khả năng IdP/application, kiểm tra session persistence ở downstream.
7. Review MFA enrollment, recovery methods, federated grants và app passwords liên quan.
8. Xem quyền admin/role bindings mới cấp, new API keys và delegated sessions được tạo trong thời gian nghi vấn.
9. Kiểm tra account có dùng cùng password ở hệ thống khác không; thông báo thay đổi theo policy mà không yêu cầu người dùng gửi password cũ.
10. Monitor logins và sensitive resource actions sau remediation.

### 13.2. Service account dùng password

Service account có thể **không có UI MFA**, chia sẻ password giữa ứng dụng hoặc cấu hình không có expiry. Cần:
- Inventory tất cả consumers và target applications.
- Cấp credential mới qua secret manager/quy trình chuẩn.
- Triển khai consumers theo canary/HA để tránh outage.
- Thu hồi credential cũ và xác minh rejected.
- Xem application connection pools/sessions còn sống.
- Chuyển sang workload identity/mTLS/short-lived tokens khi khả thi.

### 13.3. Mật khẩu dùng chung giữa người và dịch vụ

Đây là dấu hiệu thiết kế cần xử lý. Nếu cùng secret dùng cho nhiều người hoặc thiết bị, không thể biết ai đã sử dụng qua chỉ username. Khuyến nghị **per-user/per-service identities**, privileged access management và centralized audit.

### 13.4. Reset và sign-out có thể độc lập

Không hứa “đổi password = logout mọi thiết bị”. Một số ứng dụng có session cookies còn hiệu lực, SSO federation tokens, offline tokens hoặc remembered devices. Phải hỏi product owner và **test post-revocation authorization behavior**.

## 14. OAuth/OIDC, JWT, refresh token và session cookie

Các token thường bị lộ trong **Authorization: Bearer**, Cookie, URL query, redirect logs, traces, crash dumps hoặc debug proxy. Phương pháp xử lý phụ thuộc token issuer và verifier.

### 14.1. Phân loại token

| Loại | Rủi ro khi lộ | Hướng xử lý |
|---|---|---|
| **Opaque access token** | Có thể dùng cho API cho đến khi hết hạn/được revoke theo introspection | Revoke tại authorization server, xác minh resource server kiểm tra trạng thái |
| **Self-contained JWT access token** | Có thể được verifier chấp nhận bằng chữ ký đến expiry | Revoke theo cơ chế cụ thể: denylist/version/short TTL, đổi signing keys chỉ khi cần và có kế hoạch |
| **Refresh token** | Có thể xin access tokens mới trong thời gian dài | Revoke token family/grant, kiểm tra refresh-token rotation và reuse detection |
| **OIDC ID token** | Chứng minh sự kiện xác thực cho client theo audience; cách lạm dụng phụ thuộc client | Xác định misuse path, không tự dùng ID token làm API bearer access |
| **Session cookie/ID** | Có thể đại diện cho authenticated web session | Invalidate server-side session, rotate identifiers và kiểm tra session stores |
| **DPoP/mTLS-bound token** | Có thể yêu cầu proof key/certificate tương ứng | Kiểm tra token và proof credential cùng bị lộ hay không |
| **Signed URL** | Có thể cho phép đọc/ghi object trong scope và hạn hiệu lực | Revoke signing basis/object policy/URL khi provider cho phép, kiểm tra download audit |

### 14.2. JWT không phải “mã hóa an toàn”

Nhiều JWT theo JWS chỉ được **ký**, payload có thể giải mã Base64URL để đọc claims, nhưng **không được sửa claims hay tin chúng khi chưa validate signature/audience/issuer/expiry**. Nếu full JWT bearer bị lộ, đó vẫn có thể là secret được chấp nhận. Không dán raw JWT vào online decoder ngoài quyền.

### 14.3. Revocation cần xét verifier

Một JWT vẫn hợp lệ về chữ ký có thể tiếp tục được chấp nhận nếu API service **không kiểm tra danh sách thu hồi** hoặc token generation version. Nếu buộc xử lý gấp, có thể chọn:
- Disable principal/resource access ở policy/authorization layer.
- Block suspicious sessions/clients theo incident-approved controls.
- Rotate signing key **chỉ nếu có ảnh hưởng signing key**, hoặc chiến lược được owner chấp thuận; làm vậy có thể invalid toàn bộ token khác.
- Chờ expiration với risk acceptance nếu phạm vi thấp và có containment, nhưng **không dùng chờ hết hạn thay cho xử lý rủi ro cao**.

### 14.4. Refresh token có thể nguy hiểm hơn access token ngắn hạn

Một bearer access token sống 5 phút có thể hết hạn nhanh. Nhưng nếu refresh token cùng bị lộ, kẻ nắm nó có thể xin token mới cho đến khi grant bị thu hồi hoặc chính sách rotation/reuse chặn. Phải kiểm tra **refresh family, offline access, device grant, session và delegated permissions**.

### 14.5. Cookie attributes giúp giảm một số nguy cơ, không chữa lộ cookie

Secure, HttpOnly và SameSite hỗ trợ phòng vệ cho các threat classes nhất định. Nếu cookie đã bị đánh cắp qua log/PCAP hoặc tài khoản đã bị xâm nhập, **session invalidation vẫn quan trọng**. Chống CSRF, XSS và session fixation có vai trò riêng.

## 15. API keys, webhooks và SaaS integrations

API keys thường được gắn vào **service integrations** và nhiều providers cho phép tạo key mới trước khi xóa key cũ. Đây là cơ hội giảm downtime, nhưng phải cân đối rủi ro khi key cũ còn có thể bị lạm dụng.

### 15.1. Checklist xử lý API key

1. Xác định issuer/provider và **key ID**, không cần ghi full key trong incident log.
2. Xác minh environments/tenants/regions, scopes và allowed client networks.
3. Tìm tất cả workloads, CI jobs, scheduled tasks, webhooks và partners dùng key.
4. Đọc provider audit về last used IP, API methods, resource access, anomalous actions.
5. Nếu abuse/critical exposure: **revoke/block ngay** theo thẩm quyền, chấp nhận và quản lý gián đoạn cần thiết.
6. Nếu chưa có evidence lạm dụng và downtime nghiêm trọng: phát hành key mới scope nhỏ, chuyển consumers, kiểm thử rồi revoke key cũ nhanh nhất trong change window được phê duyệt.
7. Kiểm tra retry queues, jobs đang chờ và secrets bị cache trong memory/connection pools.
8. Xem key có thể tạo thêm keys hoặc delegated grants không; nếu có, kiểm tra chuỗi quyền phát sinh.
9. Giảm quyền trong IAM/API resources ngay cả khi network chỉ allow đúng SaaS endpoint.
10. Xác minh không có log header/query/body tiếp tục ghi key mới.

### 15.2. Approved destination không đồng nghĩa dữ liệu được bảo vệ

Một API key hợp lệ tới object storage hoặc SaaS logging có thể đưa dữ liệu ra khỏi hệ thống qua **domain nằm trong allowlist**. Egress firewall không thể thay authorization ở ứng dụng và resource-level IAM. Kết hợp **scope, allowed tenant/bucket, DLP, quotas và resource audit**.

### 15.3. Webhook signing keys

Webhook có thể dùng HMAC shared secret để kiểm tra message authenticity. Nếu secret bị lộ, attacker có thể tạo event trông hợp lệ trong phạm vi verifier. Rotation cần:
- Key IDs/versioning, support dual-verification trong khoảng ngắn có giới hạn nếu cần.
- Cập nhật publisher và subscriber theo trình tự.
- Chống replay bằng timestamp/nonce/event ID.
- Theo dõi unsigned/old-key verification failures.
- Thu hồi old key và test signature cũ bị từ chối.
- Không log full shared secret hoặc raw sensitive event body.

**Đừng chỉ thay public webhook URL** nếu signing secret đã bị lộ.

## 16. SSH keys, bastion và quản trị thiết bị

Một **SSH private key** được chấp nhận bởi bastion, Linux servers hoặc network device là credential; **public key** không là bí mật. Phạm vi phụ thuộc nơi public key được authorized và quyền của account.

### 16.1. Quy trình khi SSH private key bị lộ

1. Xác định key fingerprint, principal, owner và nơi public key được cài.
2. Nếu đang dùng SSH CA, xác định **user certificate**, thời hạn và CA/revocation mechanisms riêng.
3. Thu hồi hoặc gỡ quyền đối với public key/SSH certificate cũ trên mọi approved targets.
4. Tạo key pair mới theo approved cryptographic policy, ưu tiên hardware-backed khi phù hợp.
5. Phân phối public key/certificate qua configuration management/CA, không copy private key.
6. Kiểm tra accounts/sudo/authorized_keys changes và bastion audit.
7. Xác minh login bằng key cũ bị từ chối, login bằng key mới thành công trong lab/approved test.
8. Xem active SSH sessions/cached agents/port forwards; thu hồi key không phải lúc nào ngắt sessions đã thiết lập.
9. Giảm quyền bastion/firewall management network và tăng monitoring.
10. Audit ứng dụng/CI/CD đã nhúng private key và xóa/rotate bản sao theo policy.

### 16.2. SSH host key khác SSH user key

- **Host private key compromise** có thể làm tăng nguy cơ giả mạo máy chủ nếu client trust workflow yếu.
- **User private key compromise** có thể cho đăng nhập trên những servers chấp nhận public key đó.
- **SSH CA private key compromise** có thể ảnh hưởng nhiều chứng thư/identity.

Mỗi loại có phạm vi và quy trình đổi khóa khác nhau; không “đổi key trong authorized_keys” là xử lý đủ trường hợp CA bị mất.

### 16.3. SSH agent forwarding

SSH agent forwarding có thể làm agent credential bị lạm dụng trong một số tình huống khi host trung gian bị kiểm soát; private key không nhất thiết bị copy thành file. Điều tra approved logs/bastion sessions và xem quyền của agent sockets. Khi nghi có hành vi lạm dụng, đừng chỉ tìm file private key mới trên server.

## 17. TLS/mTLS private keys, certificate và PKI

Khóa TLS/mTLS bị lộ cần phân biệt **leaf service key**, **client-auth key**, **intermediate CA key**, **root CA key** và **truststore certificate**.

### 17.1. Khi leaf server private key bị lộ

- Xác định key pair/cert serial/SAN, owner, endpoints, clusters/regions và thời gian.
- Thay key pair mới, phát hành certificate phù hợp, rollout tới đúng endpoint.
- **Revoke cert cũ** theo PKI policy khi có điều kiện/hỗ trợ, kiểm tra CRL/OCSP hoặc cơ chế trust control thực tế.
- Loại key cũ khỏi secrets/keystores, backups và CI theo process; đánh giá bản sao không thể xóa ngay.
- Kiểm tra clients vẫn tin đúng certificate chain/trust anchors.
- Đối chiếu server identity, SNI, TLS termination, alternate proxies/load balancers.
- Theo dõi TLS handshake failures, mTLS authorization decisions và service SLO.
- Kiểm tra certificate cũ có còn được chấp nhận ở clients/regions không.

**Lưu ý:** revocation checking hỗ trợ khác nhau giữa TLS stacks và clients; một số cơ chế fail-open hoặc không được áp. Không hứa CRL/OCSP tự ngăn mọi việc dùng certificate cũ mà chưa kiểm chứng.

### 17.2. Khi client mTLS private key bị lộ

Kẻ có client key có thể giả dạng workload/client trong phạm vi trust/policy. Cần thay **key + certificate**, revoke/deny old principal/cert khi cơ chế cho phép, rotate workload identity và **xem authorization của resource servers**. Chỉ thay server certificate không xử lý client-auth key bị lộ.

### 17.3. Khi CA signing key bị lộ

Đây thường là **sự cố cấp trust cao hơn nhiều** so với leaf:
1. IC/PKI lead xác định root/intermediate, signing permissions và certificate population.
2. Dừng/giới hạn issuance trái phép, bảo vệ HSM/CA admin access.
3. Thu thập issuance logs/CT hoặc enterprise cert inventory theo đúng scope.
4. Đánh giá danh sách chứng thư có thể bị giả mạo và những truststores chấp nhận CA.
5. Lập phương án thay CA/trust anchor, reissue leaf certificates, update chains, revoke/distrust bị ảnh hưởng.
6. Thực hiện rollout có kiểm soát để tránh toàn hệ thống mTLS/TLS outage.
7. Xác nhận trust bundles ở Java, browser, OS, ingress, service mesh, VPN, network devices.
8. Theo dõi handshake/trust errors và unauthorized certificate issuance.
9. Không loại root CA trên toàn doanh nghiệp ngay khi chưa có emergency plan trừ khi risk bắt buộc.
10. Kết thúc với bằng chứng trust rotation, certificate revocation và incident review.

### 17.4. HSM/non-exportable keys

Key trong HSM/KMS có thể được thiết kế không exportable; việc lộ **key identifier/certificate** không đồng nghĩa đã xuất được private key. Tuy nhiên nếu attacker chiếm **signing API permissions** thì có thể dùng key mà không cần export. Phải kiểm tra key policy, KMS audit, signature operations và compromise of callers.

### 17.5. Certificate rotation và OCSP/CRL

Các giá trị cần phân biệt:
- **NotBefore/NotAfter:** khoảng hiệu lực certificate.
- **Revocation:** trạng thái do CA và client policy xử lý.
- **Trust anchor acceptance:** client có tin issuer/chain không?
- **Identity binding:** SAN/SPIFFE ID/client principal có khớp policy không?
- **Session reuse:** connection TLS đã thiết lập không mặc định bị cắt khi cert mới được phát hành.

**Negative test quan trọng:** trình xác minh ở client hoặc service đích **phải từ chối cert/key cũ** theo incident policy, không chỉ nhìn thấy cert mới trên server.

## 18. VPN, Wi-Fi/NAC và RADIUS/TACACS+ secrets

Các credential mạng có thể ảnh hưởng **nhiều thiết bị và kết nối tồn tại lâu**, cần phối hợp NetworkOps để tránh tự gây outage.

### 18.1. VPN username/password hoặc MFA session

- Disable compromised user/device access theo mức rủi ro.
- Reset password và revoke VPN/SSO sessions/tokens.
- Kiểm tra active tunnel lifecycle, client certificates, device posture và MFA enrollments.
- Đối chiếu VPN login source IP, device ID, tunnel assigned IP và network flows.
- Xem lateral movement qua VPN tới Mgmt/Prod và tài khoản mới được cấp quyền.
- Đảm bảo firewall segmentation vẫn hạn chế người dùng VPN.

### 18.2. IPsec/IKE PSK hoặc peer certificate

Với **IPsec pre-shared key**, nếu key chung dùng nhiều peers, lộ có thể tác động diện rộng. Kế hoạch thường cần:
1. Inventory peer IDs, IKE versions/authentication methods và HA sites.
2. Xác định khả năng dual-key/overlap an toàn của vendor (nếu có).
3. Phối hợp thay key ở hai đầu và thời điểm rekey.
4. Kiểm tra tunnel establishment, routes, traffic selectors và crypto negotiation.
5. Thu hồi old PSK, xác minh old-auth không còn dùng được.
6. Theo dõi tunnel flaps, routing failover, NAT-T và service availability.

Nếu VPN xác thực bằng **client certificate**, xử lý theo leaf client PKI policy; không tự coi PSK là yếu tố liên quan. Với **WireGuard**, private key của peer khi lộ cần keypair rotation/peer public-key mapping update, ACL/AllowedIPs review và khả năng session còn hoạt động; không có “thu hồi certificate” theo cơ chế X.509 nếu không dùng X.509.

### 18.3. Wi-Fi PSK

WPA-Personal dùng shared passphrase/PSK theo setup; lộ shared credential có thể cho tham gia mạng nếu các điều kiện khác cho phép. Rotate cần:
- Phân biệt SSID/guest/corporate và số lượng clients.
- Update AP/controller và devices theo change plan.
- Thay credential cũ, kiểm tra clients cũ bị từ chối.
- Giữ VLAN segmentation và client isolation.
- Đánh giá chuyển sang **802.1X/EAP-TLS** với per-device identity khi phù hợp.

### 18.4. EAP-TLS và RADIUS

Trong WPA-Enterprise/802.1X, lộ **client private key/cert** khác lộ **RADIUS client–server shared secret**:
- Client certificate/key: revoke/reissue một device/user và kiểm tra identity mappings.
- RADIUS shared secret: đổi giữa NAS/AP/switch/VPN gateway và RADIUS server theo pair/device; có thể ảnh hưởng xác thực nhiều clients nếu mismatch.
- Xem 802.1X sessions đã authorized, reauthentication timers, CoA/Disconnect support và AAA logs.
- Nếu dùng EAP password-based methods, xem credential và server-certificate validation của EAP method cụ thể.

### 18.5. TACACS+ secrets và network admin logins

TACACS+ shared secret thuộc trao đổi giữa network device và AAA server, không là mật khẩu cá nhân admin. Lộ secret này cần đổi ở cả device/AAA config theo lịch an toàn, audit admin commands và xem fallback local accounts. Tính bảo mật giao vận phụ thuộc version/implementation và deployment; không xem shared secret tự bảo đảm mọi network management path đã được mã hóa theo yêu cầu.

## 19. Network devices: SNMP, routing authentication và management secrets

Network devices có thể dùng nhiều loại secret trong cấu hình/backup:
- SNMPv1/v2c **community strings**.
- SNMPv3 authentication/privacy keys.
- NETCONF/RESTCONF/API tokens, SSH admin credentials.
- Routing protocol authentication keys như BGP TCP-MD5/TCP-AO hoặc key chains theo platform.
- OSPF authentication hoặc các cơ chế control-plane integrity theo version.
- Local break-glass admin accounts.
- NTP authentication keys ở những deployments có dùng.
- Secrets cho TACACS+/RADIUS/Syslog/TLS collectors.

### 19.1. SNMPv1/v2c communities

Community strings có thể dùng để query hoặc write theo configuration. Nếu write community bị lộ, rủi ro có thể cao hơn read-only. Phòng vệ:
1. Restrict UDP/161/162 nguồn được phép tại management plane.
2. Rotate community ở device và manager, revoke old string.
3. Review SNMP write permissions và config changes.
4. Di chuyển sang SNMPv3 authPriv khi phù hợp.
5. Giới hạn MIB views và per-manager access; không dựa community đơn độc.

### 19.2. SNMPv3 authentication/privacy

SNMPv3 có users/keys và security levels, nhưng **authNoPriv** không mã hóa toàn bộ dữ liệu nội dung như authPriv. Khi keys lộ, đổi user keys/passwords qua quy trình phù hợp, kiểm tra engine ID/time and manager config; không sao chép secret mới vào SNMP trap logs.

### 19.3. Routing authentication key compromise

Khi BGP/TCP-AO/TCP-MD5/OSPF authentication key bị lộ, cần đánh giá **adjacency/session security** và khả năng on-path/off-path abuse theo network reachability. Kế hoạch thay key phải:
- Inventory neighbors, address families và algorithm/key chain support.
- Dùng key rollover mechanism được thiết bị hỗ trợ khi khả thi.
- Đồng bộ hai bên để tránh route flaps.
- Theo dõi control-plane counters, BGP sessions, routing convergence và route changes.
- Không làm mất Internet/WAN core chỉ vì rotate không có fallback.
- Kiểm tra old key không còn được chấp nhận và policy control-plane vẫn đúng.

### 19.4. Break-glass accounts và configuration backup

Tài khoản cứu hộ có thể không qua central IdP; nếu xuất hiện trong router/switch config backup, cần bảo vệ backup, rotate local credential theo change plan và test access continuity. **Không xóa tài khoản break-glass đang là đường phục hồi duy nhất** khi chưa xác định phương án thay thế có kiểm soát.

## 20. Cloud IAM, access keys và temporary credentials

Cloud có nhiều identity types: long-lived access keys, workload/service principals, temporary security tokens, OAuth grants, managed identities, instance profiles và KMS signing permissions.

### 20.1. Long-lived access key

- Xác định account/project/subscription, principal, key ID và permissions.
- Ngăn phát sinh lộ mới từ CI, config, logs hoặc PCAP.
- Disable/revoke old key theo mức rủi ro, hoặc staged rotation được phê duyệt khi cần giảm outage.
- Review cloud audit events: last use, source IP/VPC endpoint, API actions, new roles/users/keys, policy modifications.
- Kiểm tra resource-level permissions, object access, KMS use, network changes, snapshots và secret reads.
- Tạo new credential trong managed secret store hoặc ưu tiên workload identity nếu được hỗ trợ.
- Triển khai workloads, test services và revoke key cũ.
- Kiểm tra **temporary sessions đã được tạo nhờ key cũ** theo cơ chế của cloud provider; invalidating long-lived key không nhất thiết chấm dứt mọi session phát sinh.
- Monitor privilege escalation/activity bất thường trong giai đoạn exposure và hậu remediation.

### 20.2. Temporary credentials

Temporary access key/token có expiration, session policies và issuer. **Không mặc định không thể revoke**; cũng không mặc định disable parent key sẽ lập tức invalid tất cả issued sessions. Mỗi cloud/STS implementation có semantics khác. Cần provider-specific controls cho session invalidation, principal-policy changes và endpoint authorization checks.

### 20.3. Cloud instance metadata và SSRF

Một app có SSRF có thể tiếp cận metadata endpoints hoặc identity token service ngoài quyền, tùy provider/config. Chặn theo:
- Workload identity và instance metadata hardening theo provider.
- Network/IMDS restrictions, hop limits/headers/tokens khi có.
- Egress policies, URL validation và per-workload IAM scope.
- Cloud audit về issued/used temporary credentials.
- Không tải metadata credentials thật chỉ để “test SSRF”; dùng mock test và policy evidence.

### 20.4. KMS/private keys và permission abuse

Khi private key non-exportable, sự cố có thể là lộ quyền **Sign/Decrypt** hoặc credential gọi KMS. Rotate caller credentials, restrict key policies và audit cryptographic operations. Không suy rằng chưa có exported key file nghĩa signing capability không bị lạm dụng.

## 21. Kubernetes Secrets, ServiceAccounts và container workloads

Kubernetes Secret object có thể chứa credentials; **Secret không tự an toàn chỉ vì nằm trong Kubernetes API**. RBAC, encryption at rest, etcd, audit, node access, Pod mounts, container logs và external secret stores cùng quyết định rủi ro.

### 21.1. Những đường lộ phổ biến

- Secret value bị print khi container start/debug exception.
- Secret nằm trong environment variable bị dump qua process/debug/tooling.
- Secret mounted vào Pod của workload đã bị chiếm.
- Kubernetes API read/list secrets quá rộng.
- Secret xuất hiện trong Helm values, Git manifest hoặc CI logs.
- ServiceAccount token bị copy ngoài Pod scope.
- Secret replicated sang backup/observability.
- Cluster admin/key store policy bị cấu hình sai.

### 21.2. Khi Kubernetes Secret value bị lộ

1. Xác định **Secret name/namespace/type**, owner và consumers, tránh đọc full value khi không cần.
2. Inventory Pods/Deployments/Jobs/ExternalSecrets hoặc consumers dùng secret.
3. Rotate secret tại **source of truth**: vault/cloud manager/provider, không chỉ đổi bản sao Kubernetes.
4. Kiểm tra cách consumer nhận update: environment variables thường cần restart/rollout để nhận giá trị mới; mounted volumes/projected mechanisms có update semantics riêng.
5. Rollout canary và kiểm tra service availability.
6. Revoke old credential tại backend/issuer và test rejection.
7. Xem Pods cũ, Jobs đang chạy, connection pools và cached tokens.
8. Review RBAC to get/list/watch secrets, audit events và service-account permissions.
9. Kiểm tra secret leakage trong logs, events, GitOps revisions và telemetry pipelines.
10. Có kế hoạch thu hồi nếu malicious Pod còn khả năng đọc secret mới.

### 21.3. ServiceAccount tokens

Projected ServiceAccount tokens thường có audience và expiration cùng object binding tùy thiết lập; **legacy tokens có thể sống lâu hơn**. Không mặc định xóa Pod là thu hồi mọi token trong mọi môi trường. Phải xem:
- Token issuer, audience, bound object, expiration.
- API server/authenticator validation behavior.
- RBAC rights và impersonation/role binding changes.
- Token consumers ngoài cluster.
- API audit và cloud workload identity mappings.

### 21.4. Pod identity compromise khác Secret value leak

Nếu attacker còn quyền exec vào Pod hoặc đọc Kubernetes Secrets, rotate một secret nhưng **giữ attacker access** sẽ khiến secret mới bị lấy lại. Containment cần xử lý **compromised workload, service account permissions, node/cluster control plane, egress và audit** trước hoặc song song rollout.

## 22. Service mesh và workload identity

Service mesh mTLS có thể dùng **short-lived workload certificates/SVIDs** và identity policy. Lộ một leaf key/workload token thường có phạm vi khác lộ **signing CA key**, nhưng cả hai đều cần đánh giá trust domain và reachable services.

### 22.1. Xác định scope

- Workload identity: namespace/service account/SPIFFE ID theo platform.
- Certificate key pair, expiry, rotation mechanism, mounted secret store.
- CA/trust domain và cross-cluster trust configurations.
- mTLS STRICT/PERMISSIVE policy và authorization policies.
- Sidecar/ambient/waypoint datapath coverage.
- Source workloads nào có thể giả mạo peer identity nếu key bị lộ.
- Server services nào đang tin identity đó.
- Long-lived connections có được tái xác thực không.

### 22.2. Các bước xử lý

1. Ngăn attacker tiếp tục đọc secrets/workload data.
2. Recreate/reissue compromised leaf identity và revoke/distrust old cert/principal theo cơ chế mesh.
3. Xác minh proxies/sidecars/waypoints nhận trust bundle và policy mới.
4. Kiểm tra old client identity bị từ chối tại destinations.
5. Review AuthorizationPolicy đã giới hạn service-to-service permissions đủ nhỏ chưa.
6. Theo dõi TLS handshake failures, authz denies, new connections và route bypass.
7. Kiểm tra cross-cluster and failover trust behavior.
8. Nếu CA key bị lộ, escalates sang CA incident process, không chỉ restart Pod.

**mTLS workload identity xác thực peer, không thay business user/tenant authorization**. Kẻ có credential được dùng ở mạng có reachability vẫn có thể gọi API được mTLS cho phép nhưng trái nghiệp vụ nếu application authZ yếu.

## 23. Third-party vendors, integrators và credential được chia sẻ

Khi secret dùng chung với đối tác (VPN/IPsec, webhook signing, mTLS client, API key, file transfer, AAA integration), xử lý một phía không đủ.

### 23.1. Quy trình phối hợp

1. Xác nhận incident owner và **approved contact** của từng đối tác.
2. Xác định secret nào thuộc trách nhiệm issuer và bên sử dụng.
3. Gửi **ID/reference, scope, risk, deadline** qua kênh authenticated; không gửi giá trị secret cũ.
4. Chốt thứ tự generate/distribute/activate/disable của các bên.
5. Xác định khả năng key overlap ngắn hoặc dual verification, và thời điểm hết overlap.
6. Test mTLS/API/PSK handshake với secret mới trong môi trường được phép.
7. Xác nhận old credential không còn được chấp nhận ở cả hai đầu.
8. Thu evidence về revoked old credentials và access audit.
9. Ghi contractual notification/SLAs và privacy/compliance involvement khi phù hợp.
10. Review vendor telemetry/backup/retention nếu secret lộ tại hệ thống của đối tác.

### 23.2. Partner outage vs security regression

Một API key mới chạy thành công nhưng old key vẫn được chấp nhận ở partner endpoint là **security issue chưa được xử lý**. Ngược lại, old key bị chặn thành công nhưng new cert không được trust gây outage là **recovery chưa hoàn thành**. Cần **cả positive và negative tests**.

## 24. Thiết kế rotation theo dependency và độ khẩn cấp

Một change có thể chuyển qua nhiều giai đoạn nhưng vẫn phải có **thời hạn thu hồi old credential**. Không để hai keys cùng hoạt động vô hạn.

### 24.1. Quy trình staged rotation cho service credentials

~~~mermaid
sequenceDiagram
    participant IC as Incident Commander
    participant ISS as Secret Issuer
    participant APP as Application Consumers
    participant VER as Resource Verifier
    participant MON as Monitoring
    IC->>ISS: Authorize new scoped secret
    ISS-->>APP: Secure distribution via secret manager
    APP->>VER: New credential test
    VER-->>APP: New authentication accepted
    APP-->>IC: All consumers cut over
    IC->>ISS: Revoke old credential
    ISS->>VER: Old authorization disabled
    VER-->>MON: Old credential rejection evidence
    MON-->>IC: No unexpected old uses / coverage reviewed
~~~

**Quy trình này chỉ phù hợp khi overlap được chấp nhận và không có ongoing compromise đòi revoke ngay.** Nếu attacker đang dùng secret, containment ưu tiên cao hơn availability theo decision của IC.

### 24.2. Áp dụng theo điều kiện

| Điều kiện | Quyết định ưu tiên |
|---|---|
| Confirmed malicious use của admin token | Disable/revoke ngay + isolate nguồn/đích theo policy |
| Shared partner PSK trên core VPN | Emergency coordinated rotation, HA/rollback, risk owner approval |
| API key có nhiều consumers chưa rõ | Inventory nhanh và staged cutover trong window ngắn có giám sát |
| Short-lived token đã expired, không có refresh compromise | Xác minh verifier từ chối và điều tra historical use |
| Signing CA private key compromise | PKI high-impact incident: issuance stop, distrust/reissue strategy |
| SSH private key nằm trong public artifact | Revoke authorized use tất cả servers + review sessions |
| Session cookie bị lộ trên proxy logging | Invalidate sessions, stop header logging, investigate access logs |
| Secret mới vẫn bị app/Pod compromise đọc | Ưu tiên loại bỏ attacker foothold, sau đó rotate lại |

### 24.3. Điều kiện để kết thúc rotation

- New credential đã được phát hành/bảo quản đúng scope.
- All intended consumers đã chuyển, không còn app/agent dùng old value.
- Old credential bị disabled/revoked theo authority.
- Old sessions/tokens phụ thuộc được xử lý theo product semantics.
- Negative test xác nhận old credential từ chối tại representative verifiers.
- Positive test xác nhận new credential và business workflow.
- Logs/telemetry không còn in secret mới.
- Coverage, DR/region, failover và monitoring được nghiệm thu.
- Remaining uncertainty và artifacts chưa thể xóa đã có owner/plan.

## 25. Thu hồi credential: sự khác nhau giữa revoke, disable, rotate và expire

Các thao tác có ý nghĩa khác nhau:

- **Rotate:** phát hành/thay giá trị secret hoặc keypair; không đồng nghĩa old credential đã hết hiệu lực.
- **Revoke:** issuer/authority đánh dấu credential không còn hợp lệ theo cơ chế sản phẩm.
- **Disable account/principal:** ngăn hoặc giới hạn một identity, có thể tác động nhiều credentials.
- **Invalidate session:** chấm dứt authorization/session state đã tạo trước đó.
- **Expire:** credential hết hạn theo thời gian; có thể không đủ nhanh khi sự cố khẩn cấp.
- **Deny policy:** chặn một identity/token/network path tại enforcement point, có thể là containment khi revoke không tức thời.
- **Distrust CA/trust anchor:** loại một nguồn tin cậy khỏi verifier, tác động diện rộng.

### 25.1. Ma trận loại credential và cơ chế hiệu lực

| Credential | Hành động có thể cần | Điểm cần xác minh |
|---|---|---|
| Password | Reset + revoke SSO sessions/refresh | Downstream sessions, app passwords |
| API key | Revoke key ID + deploy new key | Provider API, caches, all consumers |
| Bearer JWT access token | Token denylist/version/policy hoặc đến exp khi chấp nhận rủi ro | Stateless verifiers, clock leeway, audience |
| Refresh token | Revoke grant/family | Access tokens đã phát hành trước đó |
| Session cookie | Invalidate server-side session | Edge/browser/app stores, session replication |
| SSH user key | Remove authorization/cert revoke | Hosts/CA, agent and active sessions |
| Leaf TLS client certificate | New key/cert, revoke/distrust old | mTLS verifiers, trust bundles, CRL/OCSP |
| Root/intermediate signing key | Incident PKI: stop issuance, new chain/distrust/reissue | Every relying party và trust store |
| IPsec PSK | Rotate at both peers | Existing security associations/reauth |
| Wi-Fi shared PSK | Change AP/client secret | Existing associations và reauth |
| RADIUS shared secret | Change on NAD and RADIUS server | Pair mapping, reauth and fallback |
| SNMP community/v3 keys | Change devices + managers | Read/write permissions, monitoring health |
| Cloud IAM key | Disable/delete key, new principal/credentials | STS sessions/resource roles/provider audit |
| Kubernetes SA token | Limit principal/RBAC, invalidate according to issuer/binding | API server/cloud integrations, bound object |
| KMS signing permission | Disable caller permission and audit Sign/Decrypt | Key remains non-exportable but API may be abused |

### 25.2. Eventual consistency và propagation

Một admin action thành công trên **control plane** có thể cần thời gian để downstream verifiers cập nhật caches/JWKS/trust bundles/session replication. Vì thế:
1. Ghi thời điểm request revoke được chấp nhận.
2. Xác định propagation limits theo product contract.
3. Kiểm tra nhiều nodes/regions/edge services.
4. Theo dõi old-token/auth failure events và unexpected successful uses.
5. Giữ compensating controls trong propagation window nếu rủi ro cao.
6. Không gắn status “revoked everywhere” khi chỉ một admin API trả 200.

### 25.3. Negative tests đúng cách

Không cần thử full leaked token trên production từ máy người phân tích. Có thể xác minh bằng **issuer/verifier audit state, test identity/key cùng class được phép, automated test harness với bảo vệ secret và signed controls**. Nếu bắt buộc test chính compromised credential để chắc chắn, cần **phê duyệt incident**, môi trường kiểm thử hạn chế, audit rõ và không truyền secret qua ticket/console.

### 25.4. Time-boxed overlap

Dual credentials có thể giúp không downtime nhưng tăng thời gian lộ:
- Chỉ sử dụng khi risk owner cho phép.
- Xác định exact deadline hết overlap.
- Monitor all old-key uses trong thời gian chuyển.
- Thu hồi ngay nếu thấy unauthorized use.
- Khi hết window, chặn old credential rồi nghiệm thu.
- Không gọi policy “dual-key forever” là rotation.

## 26. Containment ở lớp mạng: giảm đường lạm dụng, không phá bằng chứng

Khi credential bị lộ, **network containment** có thể giảm reachable attack surface, hỗ trợ khi issuer chưa revoke kịp. Tuy vậy, firewall không thay authentication và không nên mở rộng sự cố thành outage không cần thiết.

### 26.1. Một số biện pháp có điều kiện

| Biện pháp | Khi hữu ích | Rủi ro/cần cân nhắc |
|---|---|---|
| Chặn compromised endpoint/device ở NAC/EDR | Thiết bị có dấu hiệu bị chiếm | Có thể làm mất forensic access hoặc business workload |
| Hạn chế VPN account/tunnel | VPN credential bị lộ hoặc session lạ | Drop remote access hợp lệ |
| Giới hạn nguồn tới admin ports | Key SSH/network admin bị lộ | Phải giữ break-glass path |
| Egress deny tới domain ngoài quyền | App compromised có thể exfil | Không chặn cả DNS/telemetry thiết yếu |
| Isolate Pod/namespace | Workload tiếp tục đọc secret mới | Dependencies, orchestration, lateral movement |
| Restrict SaaS API by IP/tenant scope | Issuer revocation chậm | IP allowlist chưa đủ, NAT/proxy paths |
| Disable external token endpoint temporarily | Issuer bị lạm dụng | Ảnh hưởng login/refresh toàn bộ users |
| WAF/API gateway deny principal/key ID | Token vẫn còn valid trên backend khác | Cần kiểm tra tất cả bypass routes |

### 26.2. Không thay quyền người dùng bằng IP allowlist

Một token có scope admin chỉ cho dùng từ IP doanh nghiệp **vẫn có thể bị dùng từ môi trường mạng doanh nghiệp đã bị chiếm**, VPN session bị lạm dụng hoặc proxy trusted. IP allowlist là lớp bổ sung, không xác nhận user/workload identity.

### 26.3. Chặn trước hay rotate trước?

Nếu ongoing compromise, **chặn nguồn truy cập của attacker và revoke** có thể ưu tiên cao hơn service continuity. Nếu đang đổi shared BGP/AAA key với rủi ro chưa có lạm dụng và core connectivity nhạy cảm, có thể cần coordinated staged rotation. Quyết định phải dựa severity, approved change/incident owner và phương án khôi phục.

### 26.4. Phạm vi containment nhiều hop

Một đường truy cập:
- VPN user → bastion → management API → device → cloud resource.
- Pod → service mesh → internal API → cloud IAM → object storage.
- Laptop → Wi-Fi NAC → SaaS IdP → API.

Chặn một hop chỉ có tác dụng nếu không có **alternate routes/credentials/delegation**. Kiểm tra VPC peering, PrivateLink, IPv6, hostNetwork, direct Internet, regional DR và admin break-glass paths.

## 27. Phát hiện dấu hiệu sử dụng credential bị lộ

**Hunt** nên dựa trên danh tính và hành động, không chỉ IP. Đặc biệt khi token bị lộ qua proxy logs, attacker có thể dùng VPN/residential/proxy để trùng vùng địa lý với người dùng hợp lệ.

### 27.1. Dấu hiệu có thể theo dõi

| Tín hiệu | Nguồn thường có | Hạn chế |
|---|---|---|
| Logins từ device mới hoặc session không quen | IdP/VPN | Geolocation/VPN NAT có thể gây sai |
| Token used sau khi đã revoke | Auth server/resource server | Token cache/propagation hoặc replay attempts |
| New token grants/refresh requests bất thường | OAuth issuer | Legitimate reauth/recovery flows |
| API gọi resource ngoài baseline | API gateway/app audit | Job mới/role change hợp lệ |
| Cloud role assumption/key create | Cloud IAM audit | Control-plane ingestion lag |
| SSH success tới hosts lạ | Bastion/OS audit | Cần source identity và authorized maintenance |
| Failed mTLS handshakes với old cert | Proxy/mesh/PKI | Có thể là app chưa rotate, không hẳn attacker |
| VPN login và lateral access | VPN + firewall/NDR | Shared NAT, split-tunnel và partial logs |
| Exfil-like outbound bytes | NetFlow/IPFIX/DLP | Backups/exports hợp lệ |
| Secrets/role read bursts | Cloud/secret manager audit | Incident responders cũng có thể đọc |
| Change in AAA/routing device config | TACACS+, network config audit | Firmware upgrade hoặc planned change |
| Log/collector/defense disabled | Cloud/Kubernetes audit | Policy rollout cần verified owner |

### 27.2. Cách dựng dòng thời gian

~~~mermaid
flowchart TD
    T1[Credential first exposed] --> T2[Potential unauthorized read/export]
    T2 --> T3[Authentication/session events]
    T3 --> T4[Resource/API actions]
    T4 --> T5[Network flows and data transfers]
    T5 --> T6[Revocation effective]
    T6 --> T7[Post-revocation verification]
    META[UTC clock and NAT/session mappings] -.Correlate.-> T3
    META -.Correlate.-> T5
~~~

Các bước có thể không xuất hiện/không theo thứ tự nếu logs thiếu hoặc credential đã bị sử dụng trước thời gian lộ được ghi nhận. Mỗi event cần **source, timestamp reliability, principal confidence và action**.

### 27.3. Session attribution: chú ý NAT và cloud intermediaries

Một login từ public IP NAT gateway không chứng minh user cụ thể; một service principal cloud có thể được dùng bởi nhiều workloads. Cần ghép:
- IdP principal và session ID/credential ID.
- Device ID hoặc client certificate identity.
- VPN tunnel assignment logs.
- NAT translation pre/post tuple + timestamp.
- Pod UID/service account/caller workload.
- Cloud trace/request ID và resource audit.
- Region/account/tenant và API action details.

### 27.4. Đừng để điều tra tạo lộ mới

Câu hỏi “token này có ở logs không?” cần được giải quyết bằng **secret scanner nội bộ đã được bảo vệ, fingerprints/metadata và authorized queries**. Một analyst dán full token vào SIEM search có thể tạo thêm bản sao trong query history, logs và ticket. Cần công cụ dành cho secrets an toàn.

## 28. Detection engineering cho lộ credential và hậu thu hồi

### 28.1. Nhóm detections hữu ích

1. Secret scanner phát hiện token pattern trong **outbound logs/CI artifacts** ở source hoặc ingestion stage với quyền phù hợp.
2. Sensitive header logging detector cho Authorization, Cookie, Set-Cookie hoặc signed URLs.
3. Secret manager audit: read volume/unique principals tăng khác baseline.
4. IdP alert: new device, suspicious consent, MFA reset, refresh-token reuse.
5. Cloud: CreateAccessKey, UpdateAssumeRolePolicy, role grants, unexpected secrets read theo platform.
6. Network: SSH/VPN/AAA login ngoài approved source, management segments ngoài baseline.
7. PKI: unexpected cert issuance, key export/sign operations, revocation gaps.
8. Old-credential use after planned revoke cutoff.
9. Telemetry absence: audit source/exporter suddenly stopped.
10. Unauthorized changes to policy/log retention/flow exporter configuration.

### 28.2. Pseudorule: old credential được dùng sau cutoff

~~~yaml
# Detection intent minh họa, KHÔNG phải SIEM rule của một vendor.
rule_id: "old-credential-accepted-after-revocation"
inputs:
  - issuer_audit
  - resource_server_auth_events
match:
  credential_reference: "key-id-or-fingerprint-not-value"
  event_result: "authentication_success"
  event_time: "after_verified_revocation_effective_time"
group_by:
  - issuer
  - credential_reference
  - resource_server
  - principal
action: "raise-high-priority-investigation"
required_context:
  - "clock_quality"
  - "verifier_cache_policy"
  - "revoke_propagation_status"
  - "event_source_trust"
privacy:
  never_index_raw_credential: true
~~~

Một accepted event sau cutoff có thể là **stale verifier**, data delayed ingestion, clock skew hoặc key mapping sai; dù nguyên nhân nào cũng cần xử lý vì khả năng auth vẫn tồn tại. Không mặc định mọi event là attacker confirmed.

### 28.3. Telemetry self-monitoring

Nếu cloud audit, reverse proxy logs hoặc flow exports bị tắt trong incident, cảnh báo security dựa trên chúng có thể “xanh” giả tạo. Theo dõi **last event time, collector received/exported/dropped, ingestion lag, query completeness và audit config changes**.

### 28.4. Alert quality

Alert nên hiển thị **credential reference không bí mật**, risk level, valid revocation state, owner, source confidence, impacted resource, timestamp và playbook. Không đưa full bearer token, private key hoặc hashed low-entropy password lên alert body.

## 29. Điều tra data exfiltration và hậu quả thực tế

Một secret bị lộ có thể được dùng để **đọc dữ liệu**, nhưng không phải mọi access hoặc outbound byte đều là exfiltration.

### 29.1. Ba cấp độ bằng chứng

- **Potential access:** credential có quyền tới dữ liệu, còn hiệu lực, reachable.
- **Observed access:** provider/application audit ghi nhận action đọc/ghi hoặc tải.
- **Confirmed unauthorized disclosure:** chứng cứ cho thấy bên trái phép nhận/tiếp cận dữ liệu, có đối chiếu subject, resource, timestamp và authorization.

Hồ sơ sự cố nên phân biệt các cấp độ để xử lý phù hợp và tránh khẳng định quá mức.

### 29.2. Nguồn dữ liệu giúp điều tra

| Nguồn | Đóng góp | Điểm mù |
|---|---|---|
| Object storage audit | GET/LIST/PUT resource và caller | Có thể thiếu body/consent context |
| Database audit | Queries/rows/export operations theo cấu hình | Không biết traffic ngoài network nếu thiếu mapping |
| Proxy/DLP | Upload source, bytes, classification và policy | TLS visibility/privacy restrictions |
| NetFlow/IPFIX/sFlow | Destination IP/port, bytes và timing | Không biết nội dung payload |
| IdP/IAM logs | Principal/session/role/token use | App dùng shared service principal có thể không biết end-user |
| Endpoint EDR | Process/file activities theo coverage | Không thấy remote SaaS server state |
| Application audit | User/tenant/business actions | App audit có thể thiếu hoặc bị sửa |
| DNS query logs | Domain associations và resolver paths | Domain query không chứng minh connection thành công |

### 29.3. Không cộng bytes qua nhiều observation points

Một transfer có thể đi qua Pod CNI, service mesh, firewall và WAN gateway; cộng tất cả NetFlow records làm tưởng nhiều lần dữ liệu đã ra ngoài. Cần **canonical network boundary**, NAT mapping và application/resource audit. Encrypted traffic khiến content DLP ở network middlebox có giới hạn.

### 29.4. Data classification và thông báo

Nếu có dấu hiệu lộ dữ liệu nhạy cảm, phối hợp privacy/legal/compliance để đánh giá **phân loại dữ liệu, số đối tượng ảnh hưởng, trách nhiệm pháp lý, hợp đồng và yêu cầu thông báo**. Không tự đưa mốc thời gian hoặc ngưỡng thông báo luật định khi chưa xem jurisdiction/contract hiện hành.

## 30. Xử lý nguồn lộ qua logs, traces, packet capture và giám sát

**Chỉ thu hồi secret mà không sửa nguồn lộ sẽ làm secret mới tiếp tục xuất hiện trong telemetry.**

### 30.1. Quy trình sửa nguồn

1. Xác định **điểm phát sinh bí mật**: app logger, proxy, WAF, tracer, debug/packet capture, CI, DNS metadata, crash dump.
2. Thay logging format để **không chứa Authorization/Cookie/PSK/private key/raw URL query**, không chỉ che UI.
3. Tắt temporary debug modes có nguy cơ theo incident authorization.
4. Thực hiện redaction/tokenization ở source và pipeline ingest; không xuất full secret.
5. Xem collector queues, raw indices, replicas, backups, exports, SaaS integrations.
6. Giới hạn access ngay lập tức trong khi xử lý xóa/retention/legal hold.
7. Rotate credential **sau khi nguồn lộ mới được ngăn hoặc đồng thời** nếu rủi ro khẩn.
8. Test bằng **synthetic canary secrets**, không dùng credential thật.
9. Kiểm tra alert về secret leak quay lại bình thường và data minimization.
10. Ghi approved exception nếu một công cụ forensic phải lưu raw evidence tạm thời.

### 30.2. Không log full token để tạo correlation ID

Một token có thể phân biệt bằng **issuer-provided key ID, session reference hoặc keyed fingerprint trong secure pipeline**, không dùng full token làm label hay key. Plain hashing passwords/low-entropy secrets chưa chắc an toàn vì offline guessing. **Do not use secret itself as SQL/index key** khi có giải pháp metadata phù hợp.

### 30.3. Tránh log injection và query amplification

Một HTTP header hoặc URL do client kiểm soát có thể chứa newline/JSON-like content và làm bẩn structured logs; cần escaping và bounds. Token/secret patterns trong analytics có thể tạo cardinality explosion hoặc đánh chỉ mục dữ liệu nhạy cảm; giới hạn fields, length, retention và quyền query.

### 30.4. Khi PCAP đã được xuất tới bên thứ ba

- Xác định đối tác/SaaS nhận raw file, regional storage, access/exports và retention.
- Yêu cầu xóa/giới hạn quyền theo approved security/legal process.
- Xem có bản sao trong case attachments, notebooks và backup.
- Rotate credentials có trong PCAP, đánh giá historical misuse.
- Không hứa “đã xóa toàn bộ” khi chưa có bằng chứng từ bên lưu trữ.
- Lưu chứng cứ đã thông báo và kết quả xử lý của bên thứ ba.

## 31. Phòng ngừa dài hạn: secrets lifecycle và zero trust

Một incident chỉ kết thúc bền vững khi giảm xác suất tái diễn và blast radius.

### 31.1. Secrets management

- Secrets trong **managed secret store** có RBAC/IAM, encryption, audit và access approvals.
- Short-lived/dynamic credentials và auto-rotation khi hợp đồng ứng dụng hỗ trợ.
- **Per-service/per-environment identities**, không shared admin password/API key.
- Principle of least privilege, scopes, audiences, resource/tenant separation.
- Không hardcode secrets vào Git, container images, Helm values hoặc client bundles.
- CI/CD secret scanning và log redaction ở source.
- Software supply-chain controls và provenance của deployment.
- Có credential inventory với owner, expiry, review dates và dependencies.

### 31.2. Network architecture

- Segment Dev/Prod/Mgmt và limit remote admin/network appliance access.
- Restrict egress tới approved destinations, proxy/identity controls.
- Use mTLS/SSH/TLS theo protocol, verified peer certificate; không dùng plaintext auth trên untrusted networks.
- VPN/NAC với MFA/device posture và per-device credentials khi phù hợp.
- Cloud private endpoints và IAM/resource policies có scope.
- Audit/IDS/IPS/NDR placement đúng để thấy connection attempts và abuse, nhưng không capture mọi payload tùy tiện.
- Independent monitoring cho secret store, IdP, issuer, network config, collector health.
- DR/failover phải giữ nguyên identity, firewall và rotation controls.

### 31.3. Chu kỳ credential

~~~mermaid
flowchart LR
    REQ[Request approved identity/scope] --> ISS[Issue securely]
    ISS --> DIST[Distribute via secret manager]
    DIST --> USE[Use with verified transport]
    USE --> AUD[Audit and monitor]
    AUD --> ROT[Rotate on schedule/event]
    ROT --> REVOKE[Revoke old credential]
    REVOKE --> VERIFY[Verify rejection and retention]
    VERIFY --> REQ
~~~

### 31.4. Người dùng và đội vận hành

- Dạy người dùng **không gửi password/token** cho nhân viên hỗ trợ qua chat/email.
- Khi nhận screenshot/log có token, thu hẹp scope và tạo incident reference.
- Review quyền xem PCAP, access logs và telemetry dashboards.
- Diễn tập response giữa IAM/SOC/PKI/Network/SRE, có owner cho mỗi bước.
- Giảm default debug logging và secret exposure in exceptions.
- Thử xử lý old-session invalidation định kỳ theo sản phẩm.

## 32. Một kế hoạch triển khai thực tế theo giai đoạn

### Giai đoạn 1 — Inventory

1. Liệt kê credential types trong network/service workflows.
2. Xác định storage owners, issuers, verifiers và expected lifetimes.
3. Gắn criticality, scope, trust domain, tenant và production dependencies.
4. Kiểm tra secret có trong telemetry/tickets/build artifacts không.
5. Ghi các cơ chế revoke và session invalidation được hỗ trợ.
6. Kiểm tra break-glass procedures và DR dependencies.

### Giai đoạn 2 — Bảo vệ trước sự cố

1. Bật redaction policies ở app/proxy/collector.
2. Bật audited secret-manager access, issuer auth logs và cloud audit.
3. Tạo alert cho exposure indicators và suspicious token use.
4. Chuẩn hóa metadata key ID/fingerprint không chứa secret.
5. Cấu hình least privilege và network segmentation.
6. Duy trì test identities/secrets cho diễn tập mà không lộ credentials thật.

### Giai đoạn 3 — Diễn tập incident

1. Dùng **synthetic credentials** trong lab.
2. Giả lập một proxy log có header/token giả nhưng không cho network traffic thật đi ra.
3. Kích hoạt alert/triage và bảo toàn evidence được redact.
4. Thực hiện approved revocation trong lab issuer.
5. Test new secret works, old secret rejected.
6. Test sessions/revoke propagation và stale caches.
7. Theo dõi application SLO, retries, failure messages.
8. Review access controls trên SIEM/capture storage.
9. Đánh giá khả năng truy vết timeline từ IdP/flow/app logs.
10. Ghi gap/owner/deadline sau diễn tập.

### Giai đoạn 4 — Production operations

1. Thực hiện canary rotation cho một noncritical integration.
2. Đo propagation/time-to-revoke và xác nhận failover verifiers.
3. Gắn secret owner và alert nearing expiry.
4. Giám sát old-key usage, unredacted log incidents, permission changes.
5. Review runbooks mỗi khi thay IdP, cloud, CA, VPN appliance, mesh hoặc CNI.
6. Kiểm tra region/cluster DR vẫn xử lý old credentials.
7. Đảm bảo mọi exception có expiry và approval.

## 33. Thực hành đọc-only trong môi trường được cấp quyền

Các lệnh chỉ giúp **xem metadata/trạng thái**, không thu hồi, không bật capture, không xuất credential và không đăng nhập thay người khác. Output như names, network topology, certificate subjects hay RBAC vẫn có thể nhạy cảm; chia sẻ chỉ sau khi phân loại/redaction.

### 33.1. Quan sát network routes và sessions của chính host lab

~~~bash
# Chỉ chạy trên host/container lab được cấp quyền
date -u
ip -4 route show
ip -6 route show
ss -tun
~~~

**ss -tun** hiển thị kết nối/sockets theo quyền người dùng; không tự suy session authentication. Nếu xem remote address sau NAT, cần mappings để xác định workload/user. Không dùng một socket ESTABLISHED làm bằng chứng credential còn được chấp nhận.

### 33.2. Kubernetes: xem metadata, không đọc values

~~~bash
# Kiểm tra quyền của principal hiện tại, không đọc Secret
kubectl auth can-i list secrets -n payments-lab
kubectl auth can-i get secrets -n payments-lab

# Chỉ hiển thị metadata; tên Secret cũng có thể nhạy cảm
kubectl get secrets -n payments-lab \
  -o custom-columns=NAME:.metadata.name,TYPE:.type,CREATED:.metadata.creationTimestamp

# Đọc danh sách workload identities/tên Pods được phép xem
kubectl get serviceaccounts -n payments-lab
kubectl get pods -n payments-lab -o wide
~~~

**Không chạy kubectl get secret -o yaml/json hoặc base64 decode** khi mục tiêu chỉ là inventory vì có thể tiết lộ values. Tên namespace trong ví dụ là giả định; dùng đúng scope đã được cấp quyền.

### 33.3. Kiểm tra một public certificate offline

~~~bash
# Tập tin chỉ chứa CERTIFICATE công khai, không phải key/private PKCS#12
openssl x509 -in approved-public-cert.pem \
  -noout -subject -issuer -serial -dates -ext subjectAltName
~~~

Lệnh đọc metadata của public certificate file có sẵn. Không đọc private key vào terminal, không in password, không đưa public certificate metadata nhạy cảm lên public ticket nếu không cần.

### 33.4. Xem tình trạng secret mà không biết giá trị

Ví dụ an toàn là đọc issuer dashboard theo **Key ID**, trạng thái “active/disabled”, scope, last-used timestamp và audit logs đã redacted. Nếu công cụ chỉ có API xuất raw secrets, không dùng API đó để phục vụ mục đích metadata; đề nghị product owner cấp một audit/status endpoint có kiểm soát.

### 33.5. Phân tích logs bằng dữ liệu giả

~~~json
{
  "timestamp_utc": "2026-11-28T08:00:00Z",
  "incident_id": "INC-example-007",
  "principal": "svc-payments-lab",
  "credential_ref": "api-key-id-lab-02",
  "secret_value_present": false,
  "source_type": "proxy-access-log",
  "resource": "invoice-api-lab",
  "auth_result": "denied",
  "reason_class": "credential_revoked",
  "policy_version": "lab-v4"
}
~~~

Đây là **schema ví dụ**, không phải log native của một IdP. Các trường cần gắn provenance; result=denied có thể do auth, firewall hoặc app authorization ở những điểm khác nhau, vì vậy xác định decision layer.

## 34. Tiêu chí nghiệm thu kỹ thuật sau khôi phục

Không đánh dấu “resolved” chỉ vì credential mới đã được phát hành. Cần xác minh:

1. **Exposure stopped:** nguồn ghi secret vào log/PCAP/ticket đã ngừng.
2. **Old credential rejected:** các verifiers liên quan đã từ chối.
3. **New credential accepted:** users/services hợp lệ đã phục hồi theo least privilege.
4. **Sessions addressed:** sessions/refresh grants/long-lived network tunnels phù hợp policy.
5. **Privilege integrity:** không có role/grant/key mới trái phép chưa xử lý.
6. **Data impact assessed:** API/resource audit đã review theo window và gaps.
7. **Telemetry complete:** auth/network/issuer logs không có silent loss nghiêm trọng.
8. **Network controls effective:** Mgmt/Prod/egress access vẫn áp least privilege.
9. **DR parity:** cluster/region/standby trust stores và identity policies đồng bộ.
10. **Evidence protected:** raw artifacts được hạn chế, retention/review rõ.
11. **Business availability:** SLO, error rates, retry storms, VPN/session health ổn.
12. **Post-incident monitoring:** suspicious reuse/replay alerts hoạt động.
13. **Third-party confirmation:** partners xác nhận revoke/cutover khi họ là verifier.
14. **Outstanding uncertainties:** có owner và action plan, không bị giấu.

### 34.1. Bằng chứng tốt

Một báo cáo nghiệm thu chứa:
- Key ID/cert serial/reference (không chứa giá trị secret).
- Issuer revocation status và timestamp.
- Verifier policy/config versions.
- Test case IDs với positive/negative evidence.
- Affected systems/clients count và rollback status.
- Capture/log data classification và storage scope.
- Incident commander phê duyệt close.
- Follow-up tickets về thiếu sót mang tính hệ thống.

### 34.2. Bằng chứng chưa đủ

- “Đã reset password”: chưa biết session state.
- “Đã đổi certificate”: chưa biết old cert bị từ chối.
- “Không thấy login lạ”: logs có thể thiếu hoặc attacker dùng legitimate network.
- “Firewall chặn IP ngoài”: token có thể dùng trong trusted network.
- “Đã xóa dòng log”: raw copies có thể còn.
- “Mọi client đều online”: có thể một legacy client vẫn dùng old key.
- “Cloud key inactive”: temporary sessions/other keys có thể còn hoạt động.

**Kiểm tra hiệu quả thu hồi, không chỉ kiểm tra sự kiện quản trị đã diễn ra.**

## 35. Ma trận kiểm thử incident response khi credential bị lộ

Mọi trường hợp dưới đây là **kế hoạch test**, không phải kết quả đã được thực thi. Phải sử dụng **lab identities, synthetic secrets và tài sản được cấp quyền**, không cố tình làm lộ secrets production để thử cảnh báo. Với case ảnh hưởng routing/VPN/AAA/CA, triển khai trong **lab hoặc approved change window** để tránh gây gián đoạn dịch vụ thật.

Mỗi test cần ghi: **ID, owner, môi trường, secret type/reference (không phải value), issuer/verifier, source/scope, policy version, expected result, actual result, timestamp UTC, status PASS/FAIL/BLOCKED/NOT_RUN, evidence đã redacted và rollback**.

| ID | Tình huống | Kỳ vọng | Bằng chứng |
|---|---|---|---|
| C01 | Chỉ thấy public TLS certificate trong PCAP | Không gắn nhãn private-key leak | Certificate/public-key metadata |
| C02 | Synthetic bearer token bị ghi trong HTTP lab log | Phát hiện exposure và tạo incident | Redacted alert + log rule |
| C03 | TLS capture không có decryption | Không tự tuyên bố nhìn thấy Authorization | PCAP/TLS details |
| C04 | Reverse proxy debug ghi raw Cookie header | Log pipeline được sửa tại nguồn | Before/after synthetic test |
| C05 | Secret xuất hiện trong SIEM index và backup | Có inventory bản sao/retention | Data lineage/audit |
| C06 | Dashboard log bị mở rộng RBAC | Phát hiện access exposure và thu hẹp quyền | ACL diff + access logs |
| C07 | Một token read-only bị lộ | Blast radius đúng scopes/resources | Issuer resource scope |
| C08 | Admin credential còn hiệu lực và nghi dùng trái phép | Containment/revoke ưu tiên | IC decision + issuer audit |
| C09 | Service API key cần staged rotation | New works trước old revoke theo risk decision | Provider + app metrics |
| C10 | Old key còn accepted tại một region | Fail, cần xử lý stale verifier | Per-region negative checks |
| C11 | Password reset nhưng session cookie còn hoạt động | Phát hiện độc lập session invalidation | IdP/app session audits |
| C12 | Refresh token family bị nghi lộ | Family/grant được xử lý | Issuer revoke result |
| C13 | JWT stateless còn valid sau admin revoke | Có compensating control hoặc risk plan | Verifier decision |
| C14 | Token có audience không đúng resource | Resource server từ chối | API auth logs |
| C15 | Sender-constrained token không có proof key | Kẻ giữ token trần không tự được truy cập | Lab token binding test |
| C16 | Session logout nhiều nodes | Mọi session stores được xử lý | Multi-node audit |
| C17 | Webhook HMAC secret thay đổi | New signatures pass; old signatures reject | Signed test events |
| C18 | SSH user private key lộ | Old login permission revoked ở all hosts | Bastion/authorized keys audit |
| C19 | SSH host private key lộ | Host trust remediation/known-hosts plan | Client trust test |
| C20 | SSH user-CA signing key lộ | Escalate CA trust incident, không chỉ rotate một user | PKI rollout evidence |
| C21 | Leaf TLS server key bị lộ | New key/cert works, old chain handling đúng | TLS verifiers/PKI audit |
| C22 | One client vẫn chấp nhận revoked certificate | Phát hiện CRL/OCSP/trust limitations | Client behavior test |
| C23 | Intermediate CA private key bị lộ trong giả lập | PKI emergency workflow có owner/rollout | CA recovery tabletop |
| C24 | mTLS client key lộ | Old client cert/identity bị deny | Destination auth decisions |
| C25 | KMS key không exportable nhưng caller permission bị lộ | Chặn signing/decrypt API unauthorized | KMS IAM/audit |
| C26 | IPsec PSK rotation hai sites | Old-auth reject, tunnel new-auth stable | IKE/tunnel logs |
| C27 | WireGuard peer key rotation | Peer mapping cập nhật, old key không còn | Peer config/handshake audit |
| C28 | VPN user reset nhưng tunnel còn sống | Active tunnel/session được xử lý theo policy | VPN session state |
| C29 | Wi-Fi shared PSK rotation lab | Old PSK denied, managed clients hoạt động | WLAN controller logs |
| C30 | EAP-TLS device certificate revoked | Device ngoài quyền không còn NAC access | RADIUS/NAC logs |
| C31 | RADIUS shared secret thay hai đầu | Auth ổn, old shared secret không dùng nữa | RADIUS/NAD logs |
| C32 | TACACS+ device-to-server secret rotate | Admin audit continuity, access recovery | AAA config and tests |
| C33 | SNMPv2c write community bị lộ | Community revoked, manager update | SNMP ACL/config audit |
| C34 | SNMPv3 authPriv key change | Manager tiếp tục monitor, old key disabled | Read-only SNMP status |
| C35 | BGP routing auth key rotation | Adjacency ổn, old key removed | BGP neighbor health |
| C36 | Break-glass password rotation | New emergency access tested, old removed | Approved break-glass record |
| C37 | Cloud long-lived key revoke | Key disabled, no unexpected use | Cloud IAM audit |
| C38 | STS temporary sessions sau key disable | Không suy automatic revocation; kiểm soát theo provider | Temporary session test |
| C39 | Compromised principal đọc nhiều secrets | Phát hiện downstream credential blast radius | Secret manager audit |
| C40 | Kubernetes Secret env var đổi | Pod dùng new value sau approved rollout | Deployment/test events |
| C41 | Projected SA token/legacy token case | Expiry/audience/binding evaluated correctly | API server auth logs |
| C42 | Mesh cert được rotate ở hai clusters | Trust/policy parity; old identity denied | mTLS/authz metrics |
| C43 | Cloud private endpoint vẫn cho old principal | Resource IAM được xử lý, không chỉ Internet firewall | Endpoint audit |
| C44 | Proxy egress chặn unauthorized use | Không coi IP policy thay token revocation | Proxy + issuer logs |
| C45 | Synthetic bulk export qua approved domain | DLP/app audit hỗ trợ đánh giá đúng | Test data classification |
| C46 | Secret scanner phát hiện log sample giả | Báo mà không in raw token | Scanner synthetic run |
| C47 | Proxy/header redaction deployed | New logs không chứa token | Lab synthetic ingestion |
| C48 | SIEM old copies còn trong backup | Có access restriction và retention/legal plan | Artifact inventory |
| C49 | Collector bị tắt giữa incident | Telemetry absence alert | Collector liveness metrics |
| C50 | UTC clock lệch giữa VPN, IdP và firewall | Timeline ghi uncertainty/normalize | Clock sync diagnostics |
| C51 | DR region standby verifier stale | Negative tests trong failover | DR acceptance evidence |
| C52 | Vendor partner revoke delayed | Có owner/ETA/compensating controls | Partner acknowledgment |
| C53 | RBAC cho phép reader xem toàn PCAP | Least privilege và query audit | Storage ACL review |
| C54 | Một IP dùng chung nhiều principals qua NAT | Không quy kết actor sai | Session + NAT mapping |
| C55 | Rotation gây 401 spike cho legitimate clients | Availability rollback/consumer inventory | App SLO, access logs |
| C56 | Incident closure request | Chỉ close khi old denied, new works, logs safe | Closure checklist + IC approval |

### 35.1. Vì sao cần cả positive và negative tests?

- **Positive test:** credential mới và luồng nghiệp vụ hợp lệ hoạt động.
- **Negative test:** credential cũ hoặc identity trái quyền bị từ chối.
- **Authorization test:** scope/resource ngoài quyền vẫn không được truy cập.
- **Security pipeline test:** log/tracing/DLP không ghi secret mới.
- **Availability test:** HA, VPN, AAA, network routes, application SLO không giảm bất thường.
- **Audit test:** issuer/verifier/network logs cung cấp bằng chứng đầy đủ và UTC timestamps.

Một service trả 200 sau thay key **không chứng minh key cũ đã bị revoke**. Một old-key test 401 ở một gateway **không chứng minh toàn bộ các verifiers khác cũng đã từ chối**.

### 35.2. Trường hợp không được làm trên production ngoài phê duyệt

- Cố tình làm lộ token thật cho một đối tác.
- Thử đăng nhập bằng leaked admin credential từ máy không thuộc scope.
- Tắt toàn bộ VPN/AAA/PKI signing infrastructure.
- Thử exploit SSRF để lấy cloud metadata real credentials.
- Phát tán raw PCAP hay private key để “nhờ xác minh”.
- Tạo tải quét mạng hoặc DDoS nhằm kiểm tra containment.

**Không có điều kiện lab an toàn thì đánh dấu NOT_RUN hoặc BLOCKED; không bịa kết quả PASS.**

## 36. Mười tám tình huống phân tích và đáp án gợi ý

### Tình huống A — Mật khẩu trong HTTP Basic Auth nội bộ

Một legacy admin portal dùng HTTP Basic qua VLAN nội bộ. Một PCAP thuộc quyền chứa username/password nguyên văn.

**Phân tích:** đây là plaintext exposure trong phạm vi packet path, không mặc định attacker đã lấy. Cần stop plaintext auth hoặc chuyển HTTPS đúng TLS, reset password, revoke related sessions, xem sensor/PCAP access và quản trị đường truy cập management.

### Tình huống B — Token nằm trong reverse proxy debug log

Một ingress proxy ghi Authorization: Bearer vào raw access log sau bật debug. SIEM export logs sang bên thứ ba.

**Phân tích:** xử lý source logging, restrict raw indices/exports, đánh giá third-party access, rotate token và invalidate sessions liên quan. Chỉ ẩn token trong dashboard không đủ.

### Tình huống C — Thấy public certificate, báo lộ private key

Analyst thấy TLS certificate chain trong packet capture và báo rằng server private key bị đánh cắp.

**Phân tích:** public certificate thường được phân phối công khai. Private key không truyền trong TLS handshake thông thường; cần evidence key file/API permissions compromise trước khi khẳng định key leak.

### Tình huống D — Đổi password nhưng web session vẫn hoạt động

Một user bị lộ password; IdP reset thành công, nhưng application session cookie cũ vẫn được chấp nhận.

**Phân tích:** password và session lifecycle độc lập tùy sản phẩm. Cần invalidate session stores, refresh tokens, remembered devices và review sign-in history.

### Tình huống E — JWT access token vẫn hợp lệ sau revoke

Resource server tự xác minh JWS signature và chỉ kiểm exp, không gọi IdP introspection.

**Phân tích:** token có thể còn được chấp nhận tới expiry hoặc khi verifier áp denylist/version/policy. Cần compensating controls và đánh giá propagation, không mặc định admin revoke làm mọi JWT vô hiệu tức thì.

### Tình huống F — Refresh token được lưu trong trace attributes

Tracing SDK ghi refresh token vào span; source logs đã redact nhưng tracing backend còn bản sao.

**Phân tích:** revoke refresh family/grant, xem access tokens đã phát hành, restrict trace storage, dọn replication/retention và test SDK không ghi secret mới.

### Tình huống G — API key cũ vẫn dùng từ một batch worker

Các pods chính đã chuyển new key, nhưng cron job chạy một lần mỗi đêm vẫn dùng key cũ.

**Phân tích:** inventory cần gồm batch/CI/scheduled tasks. Nếu key đang bị lộ và rủi ro cao, không giữ key cũ qua nhiều ngày chỉ để chờ job; có giải pháp canary/change có owner.

### Tình huống H — Private SSH key trong artifact build

CI artifact chứa private key dùng để SSH vào nhiều application servers.

**Phân tích:** revoke authorization trên tất cả targets, rotate key pair, xem artifact downloads và bastion/sudo actions, review agent forwarding và credentials downstream. Xóa artifact không tự thu hồi key.

### Tình huống I — VPN PSK chung giữa nhiều sites

Một file cấu hình VPN bị public trong ticket. IPsec PSK được chia sẻ giữa bốn peers.

**Phân tích:** phải phối hợp rotation hai đầu, đánh giá session/rekey/HA và review network reachability. Không làm rớt core WAN thiếu approved change, nhưng không trì hoãn vô thời hạn.

### Tình huống J — RADIUS shared secret bị nhầm là user password

NAC logs chứa secret giữa switch và RADIUS server; đội support reset mật khẩu người dùng.

**Phân tích:** đây là shared secret ở protocol/device relationship; cần thay trên NAD và RADIUS server, rà soát AAA trust, không chỉ reset user passwords.

### Tình huống K — Wi-Fi PSK đã đổi nhưng thiết bị cũ vẫn nối

AP đã dùng PSK mới nhưng một số client vẫn duy trì association trong thời gian chuyển.

**Phân tích:** đánh giá phiên hiện có, reauthentication timers, controller disconnect capabilities và policy. Test old PSK bị từ chối cho new authentication, không chỉ xem SSID online.

### Tình huống L — Cloud key bị xóa nhưng STS sessions còn sống

Owner xóa long-lived access key, audit vẫn thấy temporary credential do session trước đó tạo.

**Phân tích:** session semantics tùy cloud provider. Review issuer/resource policy, session duration, session invalidation options và monitor API actions. Không suy “parent key deleted = tất cả sessions chấm dứt”.

### Tình huống M — Kubernetes Secret thay nhưng Pod vẫn dùng giá trị cũ

Secret manager đã thay key; container nhận secret qua environment variable chưa restart và đang lỗi 401.

**Phân tích:** env vars không tự đổi theo Secret update trong process đang chạy. Rollout Pod/consumer được phê duyệt, kiểm tra old-key revoke và sửa source secret nếu có GitOps/ExternalSecret replication.

### Tình huống N — Mesh cert rotate nhưng cluster DR vẫn tin CA cũ

Primary region dùng CA/trust bundle mới; DR cluster chưa update, một số old client identities còn được trust.

**Phân tích:** kiểm tra trust bundles/CA issuer ở mọi region, xDS/SDS config propagation, mTLS authz and explicit negative tests. Không hạ mTLS STRICT để chữa lỗi trust.

### Tình huống O — Leaf cert hết hạn nhưng “compromise” được báo quá mức

Monitoring thấy server certificate NotAfter đã qua; không có evidence private key từng bị đọc/export.

**Phân tích:** có **certificate expiration outage** hoặc misconfiguration, khác **private-key disclosure**. Cần renew/redeploy và xác minh, nhưng không tự công bố key compromise.

### Tình huống P — SaaS upload qua approved domain bị nghi exfil

Một workload dùng exposed API key upload dữ liệu lớn tới cloud storage domain nằm trong allowlist.

**Phân tích:** flow bytes là tín hiệu, chưa biết payload/data class. Cần resource IAM, object access, application audit, DLP và identity events; allowed domain không chứng minh hành vi hợp lệ.

### Tình huống Q — SIEM không thấy logins lạ sau sự cố

Cloud audit ingestion đã ngừng 45 phút trước first exposure, nhưng dashboard nói “no suspicious activity”.

**Phân tích:** thiếu telemetry không là absence of attack. Ghi audit gap, dùng nguồn độc lập, quyết định containment theo quyền/rủi ro và khắc phục monitoring.

### Tình huống R — Credential mới bị lộ lại ngay sau rotation

Developer sửa API key nhưng proxy vẫn log toàn bộ Authorization header và collector gửi ra dashboard chung.

**Phân tích:** nguyên nhân phát sinh chưa được xử lý. Ngăn log leak tại source, restrict stored copies, rotate lại sau khi fix, test synthetic secret và thêm regression guardrail.

## 37. Troubleshooting theo triệu chứng

### 37.1. Old API key đã revoke nhưng một verifier vẫn trả 200

**Khả năng:** stale cache/region lag, nhiều issuers cùng tên, request thực dùng credential khác, auth fallback, proxy caching hoặc test đang đi khác route.

**Kiểm tra:** issuer/key ID, verifier logs, actual auth decision, policy version, UTC propagation window, request identity. Không kết luận “provider không revoke” chỉ từ HTTP 200 nếu API có public endpoint.

### 37.2. New key triển khai xong nhưng app liên tục 401

**Khả năng:** app Pod chưa reload, secret manager version mismatch, token audience/scope sai, clock skew, provider endpoint khác, alternate region còn dùng old key.

**Kiểm tra:** deployment revision, issuer status, secret reference/version (không value), app auth error code, rollout map và retries.

### 37.3. VPN tunnel down sau PSK rotation

**Khả năng:** IKE peer chưa đổi key, identity/profile không khớp, lifetimes/rekey, NAT-T, route/traffic selectors hoặc HA peer stale.

**Kiểm tra:** approved VPN debug metadata không chứa secret, tunnel status, peer config version, route health. Thực hiện rollback/roll-forward theo change plan; không mở anonymous VPN authentication.

### 37.4. SNMP monitoring mất dữ liệu sau thay secret

**Khả năng:** manager vẫn dùng community/key cũ, SNMPv3 authPriv profile mismatch, source ACL, engine ID/session config hoặc device policy.

**Kiểm tra:** per-manager agent status và authorized read-only tests, không log key mới.

### 37.5. TLS handshake failures sau thay certificate

**Khả năng:** trust CA missing, SAN mismatch, incorrect chain, cert chưa active, mTLS peer identity drift, client pinning hoặc clock skew.

**Kiểm tra:** public certificate metadata, issuance chain, client truststore, SNI, mTLS authz, service proxy logs. Không dùng TLS verification bypass làm biện pháp phục hồi mặc định.

### 37.6. Cloud API vẫn có hoạt động sau khi IAM key bị disable

**Khả năng:** temporary sessions, role assumption, alternate keys, workload identity hoặc delayed audit events.

**Kiểm tra:** credential ID/session principal, eventTime vs ingestionTime, resource account, STS token scope và provider session controls.

### 37.7. Xóa Kubernetes Secret nhưng workload vẫn truy cập được

**Khả năng:** application cached value, environment variable còn trong process, mounted data, sessions/refresh tokens hoặc backend key chưa revoked.

**Kiểm tra:** backend issuer status, Pod rollout state và session behavior; không coi delete Secret object là thu hồi credential ở hệ thống đích.

### 37.8. Log đã redact nhưng scanner vẫn tìm ra token

**Khả năng:** raw old index/backup, queued collector data, trace attributes khác pipeline, third-party replica hoặc application log source khác.

**Kiểm tra:** data lineage, source vs processed event time, policy version và retention/access control. Không xóa forensic data vô tổ chức.

### 37.9. Không có auth audit quanh thời điểm nghi bị lộ

**Khả năng:** telemetry disabled, export lag, region/source ngoài scope, logger sampling, retention đã hết hoặc attacker sửa logs.

**Kiểm tra:** collector self-metrics, separate audit sources, clock sync, service behavior và earliest available logs. Đánh dấu uncertainty.

### 37.10. IdP cho thấy login từ vùng địa lý lạ

**Khả năng:** compromised session, VPN exit location, proxy/NAT, mobile roaming hoặc IP geolocation sai.

**Kiểm tra:** device/session binding, MFA, account behavior, IP/ASN confidence, resource actions; không dựa vào geo đơn lẻ.

### 37.11. Data transfer tăng sau rotation

**Khả năng:** legit recovery/backfill, queued retries, partner re-sync hoặc actual exfil.

**Kiểm tra:** resource audit, data classification, business change, network boundary, DLP và source identity. Không coi throughput alone là exfil confirmed.

### 37.12. Partner khẳng định old PSK đã đổi nhưng traffic vẫn qua

**Khả năng:** IPsec security association cũ chưa rekey, peer khác, cert-based auth/alternate tunnel hoặc PSK chưa có hiệu lực trên standby.

**Kiểm tra:** IKE/SA lifecycle, peer config status, old-auth negative test theo approved lab/change và HA path.

### 37.13. Old SSH key bị xóa nhưng session vẫn active

**Khả năng:** SSH connection được xác thực trước khi key bị gỡ, session multiplexing, agent forwarding hoặc alternate identity.

**Kiểm tra:** bastion/host session audits, session termination policy, authorized_keys/SSH CA updates và account permissions.

### 37.14. Một DR region chấp nhận old token

**Khả năng:** replication lag, token verifier config, cached JWKS/trust bundle hoặc region-specific issuer.

**Kiểm tra:** per-region issuer/verifier policy, independent deny tests và failover route. Không gắn “global revoked” dựa vào primary region.

## 38. Runbook ứng phó sự cố credential lộ trên network

### Giai đoạn A — Declare, phân loại và bảo vệ evidence

1. Ghi incident ID, UTC, reporter, scope và bản chất dấu hiệu.
2. Xác định secret có thực sự nhạy cảm hay chỉ public certificate/fingerprint.
3. Phân loại credentials, issuer, owner, identities, permissions và affected systems.
4. Xác định first/last exposure và mọi artifact/collector/storage copies.
5. Bảo vệ raw evidence trong approved encrypted store, không dán secret vào channel/ticket.
6. Kiểm tra telemetry completeness, capture drops và auth log ingestion delay.
7. Phân severity theo hiệu lực, quyền, reachability, data class và evidence use.
8. Kích hoạt IC và các nhóm IAM/PKI/Network/SRE/Cloud/Legal phù hợp.

### Giai đoạn B — Stop exposure và contain

1. Dừng log/capture/header export phát sinh bí mật mới mà không phá chứng cứ.
2. Restrict artifact access, SIEM query/export permissions và third-party access.
3. Disable compromised principal/revoke key/sessions ngay nếu rủi ro cấp thiết.
4. Dùng network segmentation/NAC/VPN/firewall để ngăn đường lạm dụng khi phù hợp.
5. Xác định attacker foothold còn đọc secret mới không; xử lý compromised devices/Pods.
6. Giữ break-glass/DR path với owner/approval, không mở default Internet egress.
7. Ghi chính xác action, approver, effective time và uncertainties.

### Giai đoạn C — Rotate, revoke và kiểm chứng

1. Xác định issuer/verifier mechanics theo credential type.
2. Với key service có consumers, tạo/deploy new scoped credential nếu overlap được chấp nhận.
3. Với confirmed malicious use, ưu tiên revoke/disable ngay và khôi phục có kiểm soát.
4. Invalidate refresh/session grants hoặc token families khi cần.
5. Với PKI, reissue/revoke/distrust certificates/chains đúng phạm vi.
6. Với VPN/AAA/routing keys, phối hợp peers và kiểm tra session/route health.
7. Với cloud/K8s, xem temporary sessions, current Pods, stale env values và alternate keys.
8. Kiểm tra new credential tại approved service.
9. Negative tests old credential tại representative verifiers/regions.
10. Theo dõi old-key use, unauthorized actions, SLO và telemetry health.

### Giai đoạn D — Investigate historical impact

1. Tạo timeline exposure → access → token issuance → API action → revoke.
2. Correlate IdP/auth, cloud IAM, resource/app audit, EDR, VPN/NAC, firewall, NetFlow/IPFIX.
3. Dùng timestamp + identity/session/NAT/Pod mappings, không gán actor theo IP chung.
4. Đánh giá credential chaining, role escalations, new keys và downstream secrets reads.
5. Tách potential/observed/confirmed unauthorized data access.
6. Ghi data classes/resources affected, audit gaps và confidence.
7. Thông báo partners/privacy/legal theo chính sách/nghĩa vụ tương ứng.
8. Nếu phát hiện thêm credential phụ thuộc bị lộ, mở rộng containment/rotation.

### Giai đoạn E — Recovery và close

1. Xác nhận business functions, user/API/VPN/mTLS/AAA routes phục hồi.
2. Xác nhận old credential bị từ chối ở tất cả known verifiers và DR paths.
3. Xác minh không còn lộ secret mới trong logs/traces/tickets/PCAP pipelines.
4. Kiểm tra quyền hiện tại least privilege và network segmentation còn hiệu lực.
5. Kiểm tra telemetry completeness và alert post-revocation replay attempts.
6. Có xử lý quyền/access/retention đối với các bản raw evidence.
7. Hoàn thành incident report có outcomes, evidence, limitations và follow-ups.
8. IC phê duyệt đóng incident sau khi known gaps có owner/deadline.

## 39. Những sai lầm thường gặp

1. **Coi public TLS certificate trong PCAP là private-key leak.** Khác loại thông tin.
2. **Coi không thấy misuse là an toàn.** Audit có thể thiếu.
3. **Coi có secret trong log là exfil confirmed.** Cần access evidence.
4. **Dán token thật vào SIEM search/chat để điều tra.** Tạo bản sao mới.
5. **Ghi secret vào incident ticket.** Mở rộng audience.
6. **Tắt log toàn hệ thống mà không lưu evidence.** Mất khả năng điều tra.
7. **Chỉ xóa token trên dashboard.** Raw index/backup vẫn chứa.
8. **Chỉ rotate, không revoke key cũ.** Hai credentials còn sống.
9. **Chỉ revoke, không sửa source leak.** Key mới sẽ lộ.
10. **Đổi password rồi coi mọi sessions đã logout.** Cần session invalidation.
11. **Thu hồi refresh token rồi mặc định access JWT hết hiệu lực ngay.** Verifier semantics khác.
12. **Coi JWT ký số là payload được mã hóa.** JWS thường đọc được claims.
13. **Coi ID token là API bearer token.** Audience/mục đích khác.
14. **Bỏ token binding khi đánh giá risk.** DPoP/mTLS có additional proof conditions.
15. **Coi token expiry đủ cho admin secret public.** Rủi ro có thể khẩn cấp.
16. **Tắt CA root trên production không có rollout plan.** Có thể gây outage diện rộng.
17. **Đổi leaf cert nhưng giữ compromised private key.** Không xử lý lộ key.
18. **Chỉ revoke cert nhưng client không kiểm revocation.** Cần verify.
19. **Coi TLS handshake gửi private key.** Thường không hề gửi.
20. **Coi HSM non-exportable không thể bị lạm dụng.** Signing API credentials có thể bị chiếm.
21. **Coi disable cloud access key tự chấm dứt mọi temporary sessions.** Cần provider-specific review.
22. **Chỉ xóa Kubernetes Secret object.** Workloads/backend có thể giữ value.
23. **Không restart Pods dùng environment vars sau secret update.** App vẫn dùng old value.
24. **Rotate secret khi attacker vẫn có Pod access.** Secret mới tiếp tục bị lấy.
25. **Coi ServiceAccount token luôn hết hạn ngắn.** Legacy setups tồn tại.
26. **Chỉ đổi VPN password mà quên active tunnels.** Sessions có thể còn.
27. **Đổi PSK một đầu mà không phối hợp peer.** VPN down.
28. **Coi WireGuard key giống X.509 certificate.** Revocation khác cơ chế.
29. **Rotate RADIUS shared secret nhưng không cập nhật NAD.** Network auth hỏng.
30. **Nhầm SNMP read community với write community.** Blast radius khác.
31. **Bỏ SNMPv3 authPriv khi thiết kế bảo mật.** Privacy/auth level quan trọng.
32. **Thay routing auth key thiếu HA/key chain plan.** BGP/OSPF flaps.
33. **Xóa break-glass account duy nhất trước khi test replacement.** Mất recovery.
34. **Coi IP allowlist thay credential revocation.** IP/trusted network có thể bị lạm dụng.
35. **Coi một 401 ở gateway đủ chứng minh global revoke.** Có alternate verifiers.
36. **Không test DR region/standby.** Old key có thể còn ở đó.
37. **Không inventory batch jobs/legacy integrations.** Old credential còn dùng.
38. **Cho old/new keys song song vô hạn.** Tăng exposure window.
39. **Không rà downstream delegated credentials.** Quyền phát sinh còn sống.
40. **Coi public IP là end-user identity.** NAT/VPN/shared proxies.
41. **Coi NetFlow volume là data exfil confirmed.** Không thấy payload/resource.
42. **Coi DNS query tới domain lạ là credential abuse confirmed.** Cần correlation.
43. **Không giám sát collector/IdP audit loss.** Dashboard xanh giả tạo.
44. **Không xét clock skew và log ingestion lag.** Timeline sai.
45. **Không giới hạn quyền query PCAP/SIEM.** Internal exposure tăng.
46. **Sử dụng hash đơn giản của password yếu để tạo fingerprint public.** Có thể bị đoán offline.
47. **Tin policy redact sau khi index raw data là đủ.** Raw copies còn.
48. **Không tách observed access và potential access.** Báo cáo quá mức.
49. **Không có key owner/review_due.** Không ai chịu trách nhiệm.
50. **Dùng secrets thật trong tabletop tests.** Tạo incident không cần thiết.
51. **Đóng incident ngay khi app hoạt động lại.** Chưa xác minh old key reject.
52. **Không giữ data classification/legal review khi PCAP đã xuất ra ngoài.** Dễ bỏ nghĩa vụ.
53. **Mặc định credential issuer và resource verifier cùng một service.** Có cache/replicas.
54. **Không xem egress/management reachability.** Thiếu blast radius.
55. **Không có plan trước khi rotate network-wide CA/AAA.** Availability mất kiểm soát.

## 40. Checklist xử lý credential bị lộ trên network

- [ ] Đã có Incident Commander, owner, incident ID và phạm vi xử lý.
- [ ] Xác định credential type và phân biệt với public certificate/fingerprint.
- [ ] Chỉ lưu secret references, không full values trong ticket/chat.
- [ ] Có chính xác first/last known exposure UTC và audit limitations.
- [ ] Đã phân loại mức độ lộ: captured/stored/viewed/downloaded/used/confirmed.
- [ ] Phân loại quyền, audience, tenant, environment, expiry, reachability.
- [ ] Xác định issuer, verifiers, revocation mechanisms và propagation.
- [ ] Đã inventory source consumer applications, agents, scheduled jobs và partners.
- [ ] Đã inventory raw PCAP/log/tracing/SIEM/backup/third-party copies.
- [ ] Bảo vệ evidence gốc và chain of custody.
- [ ] Source leak qua headers/URL/debug/capture đã được ngăn.
- [ ] Có data minimization/redaction regression tests bằng secret giả.
- [ ] Có đủ incident-approved access controls tới raw artifacts.
- [ ] Kiểm tra user password reset không làm quên sessions/refresh.
- [ ] Kiểm tra JWT access token vs opaque vs ID token behavior.
- [ ] Kiểm tra session invalidation nhiều resource servers/regions.
- [ ] Kiểm tra scope/tenant/IAM resource rights ngoài network permissions.
- [ ] Nếu SSH key lộ, đã thu hồi authorized use ở mọi approved hosts.
- [ ] Nếu SSH CA/PKI key lộ, đã mở đúng high-impact process.
- [ ] Nếu leaf cert/key lộ, đã phát hành key mới, xử lý cert cũ.
- [ ] Đã đánh giá CRL/OCSP/truststore validation limitations.
- [ ] Nếu VPN PSK lộ, hai peers/HA sites đã phối hợp rotate.
- [ ] Nếu WireGuard peer key lộ, đã sửa mapping/revoke peer cũ.
- [ ] Nếu Wi-Fi shared PSK lộ, đã xử lý AP/client enrollment.
- [ ] Nếu EAP-TLS cert lộ, đã revoke/reissue đúng device identity.
- [ ] Nếu RADIUS/TACACS+ secret lộ, đã cập nhật device/server peers.
- [ ] Nếu SNMP community/key lộ, đã cập nhật manager/device, giới hạn permissions.
- [ ] Nếu routing auth keys lộ, có coordinated key rollover và route monitoring.
- [ ] Break-glass recovery path được duy trì và test theo thẩm quyền.
- [ ] Nếu cloud key lộ, đã kiểm tra temporary STS sessions và delegated rights.
- [ ] Nếu KMS signing API permission bị lộ, đã audit cryptographic operations.
- [ ] Nếu Kubernetes Secret lộ, source of truth và Pod consumption được xử lý.
- [ ] Nếu ServiceAccount token lộ, đã kiểm issuer/audience/expiry/binding.
- [ ] Nếu service mesh identity lộ, đã kiểm mTLS trust/AuthorizationPolicy và DR.
- [ ] Các third-party verifiers đã xác nhận revoke/cutover.
- [ ] Đã quyết định immediate revoke hay staged cutover có risk owner.
- [ ] Old-key overlap có deadline và monitoring rõ.
- [ ] Không có attacker foothold tiếp tục đọc credential mới.
- [ ] Positive test new credential works.
- [ ] Negative test old credential rejected với approved test process.
- [ ] Đã test resource/tenant permissions ngoài quyền vẫn deny.
- [ ] Đã kiểm active sessions/refresh grants/long-lived connections.
- [ ] Đã kiểm all regions/clusters/standby verifiers, không chỉ primary.
- [ ] Network segmentation, VPN/NAC/egress restrictions vẫn có hiệu lực.
- [ ] SLO của services/VPN/AAA/routes được kiểm tra sau thay đổi.
- [ ] Có detection old-credential reuse và suspicious resource access.
- [ ] Telemetry exporter/collector/audit logs đủ coverage, freshness và integrity.
- [ ] Đã kiểm unusual key creation, role changes, secret reads và data transfers.
- [ ] Data impact được phân loại potential/observed/confirmed với evidence.
- [ ] Privacy/legal/compliance review được thực hiện nếu có dữ liệu nhạy cảm.
- [ ] Có plan cho raw evidence retention/deletion/legal hold và third-party copies.
- [ ] Có post-incident report, root cause, owner, deadline và regression tests.
- [ ] Incident close chỉ sau khi IC review unresolved gaps.

## 41. Thuật ngữ nhanh

| Thuật ngữ | Giải thích |
|---|---|
| **Credential** | Vật liệu dùng xác thực/đại diện identity, có thể là secret hoặc key |
| **Secret** | Thông tin cần bảo vệ khỏi truy cập trái phép |
| **Bearer token** | Token mà người giữ có thể dùng nếu verifier chấp nhận |
| **OAuth access token** | Token cho phép gọi resource API theo scope/audience |
| **Refresh token** | Token xin access tokens mới theo grant/session |
| **JWT/JWS** | Token theo JSON Web Token/JSON Web Signature format; không mặc định mã hóa |
| **Session cookie** | Cookie mang session ID/data theo cơ chế ứng dụng |
| **DPoP / sender-constrained** | Cơ chế ràng buộc token với bằng chứng sở hữu khóa |
| **API key** | Credential xác thực ứng dụng/tích hợp theo issuer |
| **Private/public key** | Key riêng cần bảo vệ và key công khai để xác minh/mã hóa tùy thuật toán |
| **X.509 certificate** | Certificate liên kết identity/public key với issuer chữ ký số |
| **Leaf / intermediate / root CA** | Chứng thư cuối, CA trung gian và trust anchor cấp cao |
| **Revocation** | Làm credential không còn hiệu lực theo issuer/verifier policy |
| **Rotation** | Phát hành và chuyển sang credential mới |
| **Session invalidation** | Chấm dứt trạng thái phiên đã xác thực |
| **Propagation delay** | Khoảng thời gian control-plane revoke đến mọi verifiers |
| **mTLS** | TLS xác thực hai phía theo certificate/keys |
| **SVID / SPIFFE** | Workload identity document và định danh chuẩn theo hệ SPIFFE |
| **PSK** | Pre-shared Key dùng trong VPN/Wi-Fi/hoặc protocol khác |
| **IKE/IPsec** | Key exchange và bảo mật network-layer VPN |
| **WireGuard peer key** | Key material xác thực peer theo thiết kế WireGuard |
| **NAC / 802.1X** | Network Access Control / port-based access authentication |
| **RADIUS/TACACS+** | AAA protocols giữa network devices và servers |
| **SNMP community/authPriv** | Legacy shared string và SNMPv3 authentication/privacy mechanisms |
| **BGP TCP-MD5/TCP-AO** | Các cơ chế bảo vệ phiên TCP routing theo cấu hình |
| **Cloud IAM / STS** | Identity/permissions và dịch vụ cấp temporary credentials |
| **ServiceAccount** | Identity cho workload/Kubernetes API access |
| **Secret Manager / KMS/HSM** | Secret store, cryptographic key management và hardware-backed protection |
| **Blast radius** | Phạm vi quyền/tài sản có thể bị tác động |
| **Containment** | Hạn chế khả năng lạm dụng trước/đồng thời remediation |
| **Chain of custody** | Hồ sơ ai thu/quản lý/đã truy cập bằng chứng |
| **DLP** | Data Loss Prevention |
| **NDR/IDS/IPS** | Network detection, intrusion detection/prevention |
| **Canary rollout** | Triển khai từng phần và đo tác động trước mở rộng |
| **Positive/negative test** | Xác minh điều được phép hoạt động và điều cũ/trái quyền bị chặn |
| **RBAC/ABAC** | Quyền theo vai trò/thuộc tính |
| **IdP** | Identity Provider |
| **Rekey** | Đổi material key/session theo thiết kế protocol |

## 42. Tổng kết

**Credential bị lộ trên network** không chỉ là một chuỗi token hoặc password xuất hiện trong PCAP. Sự cố còn bao gồm **những nơi credential được ghi lại, ai có thể truy cập, credential còn hiệu lực ở hệ thống nào, quyền gì có thể bị lạm dụng và những sessions/delegated credentials phát sinh từ đó**. Do vậy, xử lý phải gắn **bằng chứng, quyền, issuer/verifier, network trust boundary và tính sẵn sàng của ứng dụng** vào cùng một kế hoạch.

Phương pháp đúng là **ngăn nguồn lộ tiếp diễn, bảo toàn evidence có giới hạn quyền, thu hồi hoặc rotate theo loại credential, chấm dứt sessions cần thiết, điều tra historical usage và xác minh old credential bị từ chối thực tế**. Password khác JWT, refresh token khác session cookie, SSH user key khác CA signing key, VPN PSK khác mTLS certificate, và cloud long-lived access key khác temporary STS session. Không thể dùng một thao tác “reset secret” cho tất cả.

Trong module **SECURITY_NETWORK_SECURITY**, ứng phó tốt kết hợp **phân đoạn mạng, firewall/egress controls, VPN/NAC, DNS/NetFlow, IDS/IPS, cloud/Kubernetes/IAM, PKI, observability và DLP** để khống chế lạm dụng cũng như kiểm chứng phục hồi. **Chỉ đóng incident khi có bằng chứng credential cũ không còn được chấp nhận theo phạm vi đã xác minh, credential mới hoạt động an toàn, nguồn lộ đã được sửa, telemetry đầy đủ và các rủi ro còn lại có owner**.
