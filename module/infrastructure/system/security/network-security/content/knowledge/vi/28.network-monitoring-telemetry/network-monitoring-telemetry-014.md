# Bảo vệ hệ thống giám sát khỏi bị can thiệp

> **Chương:** Giám sát mạng và telemetry  
> **Mô-đun:** SECURITY_NETWORK_SECURITY  
> **Bối cảnh:** Nắm vững các lớp phòng vệ mạng gồm phân đoạn, firewall, VPN, IDS/IPS, xác thực kết nối, DNS, mạng không dây và cloud; biết phân tích lưu lượng, mô hình hóa mối đe dọa, phát hiện xâm nhập và kiến trúc mạng an toàn.  
> **Trọng tâm:** Bảo vệ **sensor, agent, packet capture, luồng truyền, collector, queue, storage, truy vấn, detection rule và alerting** khỏi bị tắt, làm giả, sửa/xóa, trì hoãn, đánh cắp hoặc làm mù. Kết hợp **identity, mTLS, least privilege, integrity checks, immutable retention, giám sát chính hệ thống giám sát, điều tra và khôi phục**.

## 1. Vì sao phải bảo vệ hệ thống giám sát?

Giả sử một tổ chức có firewall, IDS/IPS, SIEM, packet capture và hệ metrics đầy đủ. Một kẻ tấn công xâm nhập được máy chủ production có thể không cần phá hết firewall để che dấu hoạt động; họ có thể thử **tắt agent, đổi log level, xóa nhật ký local, sửa pipeline lọc sự kiện, chặn đường gửi telemetry hoặc thay đổi detection rules**.

Một rủi ro khác nằm ở **bản thân hệ giám sát**: tài khoản quản trị SIEM bị chiếm, bucket log không có retention lock, collector nhận dữ liệu từ nguồn không xác thực, hàng đợi tràn, đồng hồ sai hoặc dashboard chỉ báo “0 alerts” vì pipeline đã ngừng hoạt động.

**Bảo vệ hệ thống giám sát khỏi bị can thiệp** là bảo đảm các tín hiệu bảo mật được thu thập và sử dụng theo những thuộc tính rõ ràng:

1. **Authenticity (xác thực nguồn):** biết sự kiện đến từ thiết bị/agent/workload nào và có bằng chứng nhận dạng đáng tin ở mức phù hợp.
2. **Integrity (toàn vẹn):** phát hiện thay đổi trái phép trên bản ghi, batch, cấu hình pipeline hoặc evidence.
3. **Availability (sẵn sàng):** sự kiện quan trọng vẫn được thu thập, truyền và truy vấn trong SLO; khi lỗi có cảnh báo và cơ chế phục hồi.
4. **Completeness/coverage (độ bao phủ):** thấy những nguồn được kỳ vọng, phát hiện mất event, mất sensor hoặc vùng giám sát bị bỏ trống.
5. **Timeliness (đúng thời điểm):** có timestamp và độ trễ đủ để phát hiện/ứng phó.
6. **Confidentiality (bí mật):** telemetry có thể chứa IP nội bộ, user IDs, tokens, payload, bí mật kinh doanh; phải giới hạn quyền đọc/chuyển tiếp.
7. **Accountability (truy cứu):** biết ai sửa rule, cấu hình, lịch retention, quyền truy cập và bằng chứng; có thể dựng timeline điều tra.
8. **Recoverability (khôi phục):** có cấu hình/version/backup và runbook để khôi phục collector, detection và nơi lưu trữ không làm mất bằng chứng.

Một dashboard không báo cảnh báo **không chứng minh mạng an toàn** nếu chính dashboard, nguồn dữ liệu hoặc pipeline có thể bị làm mù.

### Mục tiêu học tập

Sau bài học, người học có thể:

- Vẽ dataflow từ **network sensor/flow exporter → collector → queue/processor → SIEM/data lake → detector → responder** và chỉ ra trust boundaries.
- Phân biệt **mất log thật**, **sampling bình thường**, **truyền chậm**, **đồng hồ lệch**, **lọc do cấu hình** và **can thiệp ác ý**.
- Thiết kế **mTLS, xác thực agent, giới hạn ingest, chống log injection, kiểm tra integrity và retention có chống sửa/xóa**.
- Hiểu **hash, MAC, digital signature, hash chain, trusted timestamp, WORM** làm được gì và **không** làm được gì.
- Bảo vệ **cloud logging, Kubernetes audit, IDS/IPS sensors, SIEM detection content, alert destinations và CI/CD cấu hình**.
- Giám sát chính đường telemetry bằng **heartbeat, sequence/gap, canary synthetic event, queue/backpressure, coverage và end-to-end latency**.
- Thực hiện runbook **onboarding nguồn an toàn, phát hiện telemetry bị tamper, bảo toàn chứng cứ và khôi phục**.
- Kiểm thử **ALLOW hợp lệ, DENY dữ liệu không tin, DETECT can thiệp, RECOVER sau lỗi** mà không xâm phạm production.

## 2. Cần phân biệt dữ liệu với hệ thống tin cậy sinh ra dữ liệu

Một security event gồm nhiều lớp bằng chứng:

| Lớp | Ví dụ | Câu hỏi cần hỏi |
|---|---|---|
| **Nguồn thực** | Firewall, router, IDS, endpoint, Kubernetes API | Nguồn đó có đang hoạt động và bị chiếm quyền không? |
| **Sự kiện** | DNS query, flow record, login, policy deny | Event được tạo từ phép quan sát gì? Có sampling không? |
| **Danh tính nguồn** | Device certificate, agent workload identity | Collector xác thực peer nào? Credential có bị dùng chung? |
| **Bản ghi** | JSON, syslog message, metric sample, span | Có thể inject, sửa, giả format hoặc truncate không? |
| **Kênh truyền** | TLS/mTLS, VPN, OTLP, syslog, queue | Có peer authentication, encryption, retry và loss reporting không? |
| **Bộ xử lý** | Parser, enrichment, filters, sampler | Rule nào đổi/dropped events? Ai được sửa? |
| **Nơi lưu** | SIEM index, object storage, TSDB, PCAP archive | Có quyền overwrite/delete hoặc thay retention không? |
| **Phát hiện** | Query, rule, correlation, alert manager | Rule có bị disable, đổi threshold, tắt notification không? |
| **Người phản ứng** | SOC analyst, SOAR, incident commander | Evidence nào đủ tin để hành động? |
| **Nguồn đối chứng** | Cloud control-plane audit, firewall flow, auth logs | Có một góc nhìn độc lập không? |

**Tính toàn vẹn của file log không tự chứng minh event đã phản ánh đúng sự thật**. Một endpoint bị compromise có thể gửi những sự kiện **được ký hợp lệ nhưng sai sự thật**. Cần **cross-source correlation và trust assumptions**.

## 3. Thuật ngữ quan trọng

| Thuật ngữ | Nghĩa | Giới hạn |
|---|---|---|
| **Telemetry** | Log, metric, trace, event, network flow và packet capture | Không phải mọi loại có cùng mức chi tiết |
| **Sensor** | Thành phần quan sát traffic/host/application | Bị thiếu traffic nếu placement sai |
| **Collector** | Nhận, chuẩn hóa, batch/forward telemetry | Có thể bị lỗi, backlog hoặc tamper |
| **Pipeline** | Các bước ingest, parse, enrich, filter, store, alert | Mỗi processor là một trust boundary |
| **Data provenance** | Nguồn gốc/đường đi của dữ liệu và biến đổi | Phải bảo vệ provenance metadata khỏi giả mạo |
| **Tampering** | Thay, xóa, chèn, tạo giả hoặc làm sai diễn giải dữ liệu/cấu hình | Không chỉ là xóa log |
| **Log injection** | Chèn ký tự/field giả để qua mặt parser/người đọc | Không đồng nghĩa có quyền sửa storage |
| **WORM** | Write Once Read Many trong phạm vi chế độ/cấu hình | Không chứng minh dữ liệu đầu vào là đúng |
| **Immutable storage** | Hạn chế sửa/xóa dữ liệu trong retention window | Chi tiết khác nhau theo provider/mode |
| **Cryptographic hash** | Digest để phát hiện thay đổi khi digest được bảo vệ | Hash tự lưu cùng dữ liệu có thể bị thay cùng lúc |
| **Digital signature** | Xác minh chữ ký với khóa công khai và signer key | Khóa signer compromise → nguồn giả có thể được ký |
| **Hash chain** | Liên kết thứ tự các bản ghi/batches bằng digest | Cần anchor đáng tin để chống rewrite cả chain |
| **Sequence gap** | Thiếu số thứ tự trong một stream | Có thể do sampling, retry, source restart, không tự là tấn công |
| **mTLS** | TLS xác thực hai phía theo certificate | Không tự xác minh nội dung event gốc khi source bị compromise |
| **Heartbeat** | Tín hiệu sống/health từ một nguồn/pipeline | Heartbeat vẫn có thể chạy dù một lớp event bị lọc |
| **Canary event** | Event kiểm thử có chủ đích từ nguồn tới rule/alert | Không thay được coverage của traffic thật |
| **Chain of custody** | Nhật ký ai giữ/chuyển/xác minh evidence | Cần quy trình người-và-hệ thống, không chỉ một hash |

## 4. Kiến trúc giám sát nhiều lớp và điểm có thể bị can thiệp

~~~mermaid
flowchart LR
    N[Router/Firewall/IDS Sensor] --> C1[Local Agent / Flow Exporter]
    W[Host/Container/K8s Audit] --> C2[Local Collector]
    C1 --> G[Authenticated Ingest Gateway]
    C2 --> G
    G --> Q[Queue / Buffer]
    Q --> P[Parse / Enrich / Filter / Normalize]
    P --> S[SIEM / Logs / Metrics / PCAP Store]
    S --> D[Detections / Dashboards / Rules]
    D --> A[SOC / SOAR / Alert destination]
    IAM[Independent IAM / Change Approval] -. Limit edit access .-> G
    IAM -. Protect pipeline .-> P
    IAM -. Protect rules .-> D
    R[WORM/Independent Audit Archive] <-- Integrity / replicas --> S
    H[Telemetry Watchdog / Canary] -. Check health / gaps .-> G
    H -. Verify end-to-end delivery .-> S
    H -. Alert outside primary path .-> A
~~~

Một yêu cầu thiết kế quan trọng: **watchdog và audit không hoàn toàn phụ thuộc vào chính pipeline đang bị nghi vấn**. Nếu telemetry và cảnh báo về "telemetry mất" đều gửi qua một collector duy nhất, khi collector bị tắt ta có thể mất cả cảnh báo.

### 4.1. Trust boundaries

1. **Sensor → agent:** ai kiểm soát sensor firmware/runtime, mirror port, BPF hooks, capture permissions?
2. **Agent → ingest gateway:** có auth/mTLS, cách rotate cert, revocation và chống replay?
3. **Ingest → queue:** có authz, topic ACL, encryption, durable acknowledgements và backpressure?
4. **Queue → parser:** parser có thể bị log injection, enrichment poisoning hoặc crash từ dữ liệu không tin?
5. **Processor → storage:** ai có quyền write, overwrite, delete, chỉnh index/retention?
6. **Storage → detection:** ai có quyền sửa query, threshold, suppressions, dashboards?
7. **Detection → alert:** webhook/chat/email/on-call route có bị thay, tắt hoặc giả mạo?
8. **Control plane → data plane:** policy/config change có bắt buộc đi qua review, signed artifact và có drift detection?

## 5. Threat model STRIDE cho telemetry

| STRIDE | Đường can thiệp | Ví dụ | Bảo vệ |
|---|---|---|---|
| **Spoofing** | Nguồn telemetry giả | Attacker gửi fake firewall DENY với tên thiết bị thật | Device certificates, per-source identity, ingest auth |
| **Tampering** | Bản ghi/config bị đổi | Xóa alert “malicious outbound” khỏi index | RBAC, WORM, signed audit, reconciliation |
| **Repudiation** | Chối hành vi sửa log | Admin đổi retention rồi xóa history | Out-of-band control-plane audit, SoD |
| **Information disclosure** | Logs chứa secrets/PII | Quyền analyst rộng, export SIEM index | Classification, redaction, encryption, least privilege |
| **Denial of service** | Collector/queue bị quá tải | Flood fake events làm backlog, drop critical logs | Quotas, backpressure, isolation, fail-safe alerts |
| **Elevation of privilege** | Sửa detection/access | Analyst bị chiếm có thể disable rules và grant roles | Separate roles, approvals, immutable change trail |

### 5.1. Kẻ tấn công có thể ở đâu?

- **External adversary** có quyền gửi requests tạo log injection/noise.
- **Compromised endpoint/workload** có thể tắt/giả agent hoặc gửi dữ liệu gian.
- **Compromised admin account** có thể sửa collector config, retention, rule hoặc IAM.
- **Supply-chain attacker** can thiệp image/agent/processor plugin/CI artifact.
- **Malicious insider** cố xóa dấu vết hoặc truy cập dữ liệu telemetry không cần.
- **Accidental operator** triển khai filter sai, cấu hình sampling quá lớn, mất time sync.

Thiết kế phải phòng được cả **ác ý lẫn lỗi vận hành**, với bằng chứng đủ phân biệt chúng khi điều tra.

## 6. Các kiểu dữ liệu giám sát và nguy cơ riêng

| Dữ liệu | Công dụng | Điểm bị làm mù / sai lệch |
|---|---|---|
| **NetFlow/IPFIX/sFlow** | Ai nói chuyện với ai, volume, metadata | Sampling, exporter mất packet, template mismatch, NAT visibility |
| **DNS logs** | Query, domain trends, suspicious resolutions | Encrypted DNS bypass, cache, resolver ngoài tầm giám sát |
| **Firewall logs** | Allow/deny, NAT session, rule hit | Log disabled, rule logging off, asynchronous export |
| **IDS/IPS alerts** | Signature/anomaly detection | Rule disabled, packet loss, evasion, sensor bypass |
| **PCAP** | Phân tích packets/forensics | SPAN oversubscription, loss, encrypted payload, retention |
| **Host/EDR telemetry** | Process, file, network, driver events | Agent stopped, root/kernel compromise |
| **Kubernetes audit** | API actor, verbs, resource changes | Audit policy quá hẹp, sink/flags bị chỉnh |
| **Cloud audit** | Control-plane API mutations | Logging exclusion, scope/region/account gap, access abuse |
| **Application logs** | Request ID, status, app errors, business actions | Forged headers, missing authorization events |
| **Metrics** | Packet drops, queue depth, latency, error rates | Counter reset, lost scrape, high-cardinality poisoning |
| **Distributed traces** | Path request qua microservices | Sampling, missing spans, trace ID spoof, exporter failure |
| **Auth/identity events** | Login/MFA/token, role changes | Late events, stale tokens, IdP export gap |
| **DLP events** | Blocked data transfers, classification | TLS visibility, exclusions, sensor failures |

**Tính im lặng** khác nhau giữa các loại: một IDS không báo alert có thể vì không thấy attack, nhưng cũng có thể vì không còn traffic mirrored đến sensor. Phải biết **expected signal volume, source inventory và coverage model**.

## 7. Những hình thức can thiệp cần nhận diện

### 7.1. Tắt giám sát ở nguồn

Attacker hoặc cấu hình lỗi có thể dừng log service/agent, disable audit policy, chỉnh logging level, chặn agent outbound, gỡ sensor interface, thay BPF program hoặc stop container collector. **Ghi watchdog về trạng thái sensor**, đối chiếu kỳ vọng từ inventory/cloud/agent management.

### 7.2. Làm sai nội dung

Fake syslog priority/hostname, chèn JSON fields, escape/control characters, spoof X-Forwarded-For, đổi log parser mapping, gửi flow record từ exporter chưa xác thực. **Nguồn dữ liệu không tin phải parse như dữ liệu**, không cho phép nó sửa danh tính peer đã xác thực.

### 7.3. Xóa hoặc thay đổi ở đích

Quyền xóa index, bucket, log group, retention policy, SIEM rule, alert route hoặc dashboard có thể được lạm dụng để xóa lịch sử/giảm khả năng phát hiện. Phải tách **write-only ingest identity** khỏi **delete/retention management identity**, đưa audit sang miền tin cậy khác.

### 7.4. Làm chậm hoặc làm tràn

Một flood event có thể làm quá tải parser, queue, cost budget hoặc SIEM ingest, dẫn tới **sampling/drop/truncation**, khiến high-value events mất. Dùng **rate controls có ngữ cảnh, queue isolation, priority/critical channel và drop observability**; tránh công thức "drop mọi events vượt ngưỡng" trên log audit nhạy cảm.

### 7.5. Tạo “không có cảnh báo”

Attacker có thể không cần xóa logs nếu đổi **detection threshold, query source, enabled flag, mute/silence period, alert recipient hoặc notification route**. Số lượng alert bằng 0 phải được đọc cùng **rule evaluation count, data freshness và synthetic alert coverage**.

## 8. Không phải mọi “lỗ hổng log” đều là tấn công

| Triệu chứng | Nguyên nhân hợp lệ có thể có | Kiểm tra |
|---|---|---|
| Không còn DNS events | Client dùng cache, DNS policy thay đổi | Resolver metrics, flow/capture |
| Ít IDS alerts | Traffic sạch hơn, rule update | Sensor packet counters, rule revisions |
| Flow rate đột ngột giảm | sFlow sampling, exporter restart, outage | Exporter state/sequence numbers |
| Missing host logs | Agent stopped, instance terminated/recreated | Inventory, lifecycle/audit |
| Timestamp nhảy ngược | NTP correction, timezone parsing, clock skew | Source clock, ingest time |
| Duplicate events | At-least-once retry, collector replay | Event IDs, source sequence, pipeline semantics |
| Out-of-order events | Batching, async queue, multi-region ingest | Event time vs ingest time, source stream ID |
| Missing traces | Head/tail sampling, quota, unsampled request | Sampling config and probability |
| SIEM count giảm | Query/index mapping changed, retention | Detection version, raw archive |
| Alert silence | Approved maintenance, muted channel | Silence owner/expiry/revision |

Không ghi “đã có can thiệp” chỉ dựa trên thiếu một metric; tạo **correlated hypothesis** và phân biệt known maintenance, expected sampling với malicious manipulation.

## 9. Các mục tiêu bảo vệ cụ thể

Nên định nghĩa từng **security objective** có test được:

- **Only approved senders:** collector từ chối unknown device/workload identity.
- **No silent stop:** khi source/agent không gửi event theo ngưỡng expected, watchdog tạo incident.
- **No silent drop:** queue/processor drop/error counters có alerts và khả năng đối chiếu.
- **No uncontrolled deletion:** không ai có thể sửa/xóa raw evidence trong retention được bảo vệ, trừ cơ chế được chính sách cho phép và kiểm toán.
- **No undetected rule suppression:** rule change/mute/config update đi qua review hoặc có alert độc lập.
- **Timely detection:** event có thể được truy vấn/đối chiếu trong ingest latency SLO.
- **Minimal data exposure:** log viewers không có quyền đọc secret/raw packet ngoài nhiệm vụ.
- **Recoverable state:** có IaC/config backup, schema/version và rehearsal.
- **Forensic reliability:** original bytes, metadata, hash/signatures và chain-of-custody có thể xác minh.

### 9.1. SLO cần nói rõ phạm vi

Ví dụ *“P99 events từ firewall type A đến ingest trong 60 giây”* khác *“P99 alert được gửi trong 60 giây”*. Cần đo theo **event class, region, traffic priority, source inventory**, không gộp tất cả events và che critical gaps.

## 10. Nguồn telemetry và xác thực danh tính

Một collector nên biết peer gửi dữ liệu là **agent, network appliance hoặc workload đã được đăng ký**, không lấy danh tính từ trường self-reported trong log.

### 10.1. Biện pháp

1. **mTLS** giữa agent/collector khi hỗ trợ, cert gắn device/workload principal với trust domain, expiry và rotate.
2. **Per-source credentials/identities**, không dùng chung một API key tĩnh cho hàng nghìn agents nếu có lựa chọn tốt hơn.
3. **Certificate verification và authorization**: chain và SAN phù hợp, source được phép dùng đúng tenant/log stream; không chỉ “cert do CA nội bộ ký”.
4. **Network allowlist/segmentation** ở cấp host/VPC/CNI như lớp bổ sung.
5. **Rate limits theo identity**, capacity management và phát hiện invalid-auth floods.
6. **Provisioning/termination registry**: agent mới phải được onboard, agent rời mạng phải revoke quyền gửi.
7. **Separate ingest and admin APIs**: workload chỉ được **append events**, không có quyền đọc/xóa log storage.

### 10.2. Cẩn trọng khi đọc metadata nguồn

Trong một syslog record có thể có **HOSTNAME, APP-NAME, PROCID, MSGID**, nhưng đây là **trường trong payload**, có thể bị nguồn giả/compromised thiết lập. Collector nên giữ riêng **authenticated_ingest_peer**, **network source context** và **claimed_event_hostname**, không dùng claimed hostname làm chứng cứ xác thực.

### 10.3. Agent đã xác thực vẫn có thể gửi thông tin sai

Nếu endpoint bị compromise, agent credential có thể vẫn hợp lệ. Bằng chứng chỉ nói record đến qua **credential thuộc agent**, không chắc event mô tả đúng OS. Cross-check **network TAP, cloud API audit, DNS/firewall telemetry, identity logs** và chỉ rõ trust boundary trong incident report.

## 11. Bảo mật đường truyền telemetry

### 11.1. TLS/mTLS và yêu cầu tối thiểu

- Sử dụng **TLS phiên bản/cipher suites phù hợp chính sách tổ chức**, tránh plaintext telemetry trên network không đáng tin.
- Xác minh **server hostname/identity và CA**, đừng tắt validation vì “certificate lỗi”.
- Với nguồn nhạy cảm, dùng **mutual TLS hoặc token được bảo vệ**, có audience/expiry/scope chính xác.
- Giới hạn **inbound collector ports**, chống resource exhaustion và quota connection.
- Rotate cert/token, cảnh báo trước expiry, có plan đổi CA/trust bundle.
- Nếu đi qua proxy/LB, ghi rõ **TLS termination điểm nào** và bảo vệ từng hop.
- Không tin **X-Forwarded-For** hoặc hostname tự khai để tạo source identity.

### 11.2. TLS bảo vệ vận chuyển, không bảo đảm lưu trữ

TLS che khỏi nghe lén/sửa traffic **trên hop được bảo vệ**, nhưng khi event đến collector và được parse/lưu, **quyền chỉnh pipeline/storage** vẫn có thể thay event. Muốn phát hiện thay dữ liệu sau ingest, cần **protected archive/integrity verification/signing**.

### 11.3. VPN không thay event integrity

Site-to-site VPN có thể bảo vệ đường truyền thiết bị–DC, nhưng **credential bị dùng chung, giả hostname payload, sửa collector filter hoặc xóa index** không được VPN ngăn. Cần xác thực sender và kiểm soát control plane riêng.

## 12. Bảo vệ network sensor và endpoint agent

Một sensor có thể là **SPAN/TAP appliance, IDS probe, flow exporter, host EDR, agent chạy trên VM hoặc collector DaemonSet**. Quyền thao tác với sensor thường có đặc quyền cao vì cần xem packets, kernel events hoặc host logs.

### 12.1. Hardening theo vòng đời

| Giai đoạn | Kiểm soát | Bằng chứng |
|---|---|---|
| **Provision** | Asset inventory, owner, trusted image, signed release | Image/package digest, provisioning audit |
| **Enrollment** | Identity riêng, certificate/key, source scope | Attestation/agent registration |
| **Configuration** | Baseline version, least privilege, read-only configs khi phù hợp | Git commit, effective config checksum |
| **Runtime** | Host isolation, secure boot/kernel hardening tùy platform, minimal services | Compliance/EDR, immutable baseline comparison |
| **Transport** | Mutual auth, encrypted channels, bounded retries | Peer verification/connection metrics |
| **Monitoring** | Heartbeat, packet/queue drop counters, tamper alerts | Source coverage dashboard |
| **Upgrade** | Signed artifacts, canary, rollback, version audit | Deployment/change logs |
| **Retirement** | Revoke credential, remove keys, archive evidence/asset state | Decommission record |

### 12.2. Quyền agent là một trust boundary

Một host agent đọc process/packet/kernel events có thể yêu cầu **root, elevated Windows permissions, eBPF privileges, host PID/network mounts hoặc access đến file log nhạy cảm**. Đừng biến service account agent thành **cluster-admin** chỉ vì cần collect Pod metadata; tách data collection từ các quyền control-plane.

Giảm:

- **Write permissions** không cần thiết lên thư mục logs, kubelet, firewall configs và secrets.
- Khả năng **chạy arbitrary scripts hoặc remote commands** nếu không thuộc design.
- **HostPath mounts** quá rộng cho collector Pod, privileged containers và Docker socket.
- Quyền sửa **policy retention, storage delete, SIEM rules** từ chính identity dùng gửi logs.
- Các network routes cho agent ngoài **collector endpoints** và update channels được duyệt.

### 12.3. Làm sao phát hiện agent bị tắt?

Một **heartbeat** nên chứa *instance identity, node/workload reference, software version, config revision, event counters, last-send timestamp, queue status*. Khi không còn heartbeat, so cùng **asset inventory, node live status và remote health checks**. Một agent có thể bị attacker làm giả “healthy” nên **không chỉ tin self-reported heartbeat**.

### 12.4. Agent chạy nhưng không quan sát được

Ví dụ eBPF probe attach sai interface/namespace, Windows event channel chưa bật, container không mount đúng log directory, IDS capture filter bị đổi. Phải có **synthetic canary event** hoặc **đối chứng số requests/flows** tại nguồn độc lập, không chỉ trạng thái process=running.

## 13. Bảo vệ mạng thu thập: TAP, SPAN, flow exporter, IDS/IPS

### 13.1. TAP và SPAN có khả năng khác nhau

- **Physical/network TAP** sao chép traffic trên link theo cấu hình; thiết bị và đường mirror vẫn có thể mất dữ liệu do lỗi/capacity.
- **Switch SPAN/port mirror** có thể bị oversubscription, mirror không đầy đủ direction/VLAN, hoặc cấu hình sai khi switch topology đổi.
- **RSPAN/ERSPAN** chuyển mirrored traffic qua mạng; cần bảo vệ route, filtering và quan sát packet drops; bản mirror có thể bị mất do queue/network congestion.
- **NetFlow/IPFIX/sFlow** là dạng export **metadata/thống kê** hoặc sampled packet info, không tương đương lưu toàn bộ packet content.
- **IDS/IPS inline** có thêm yêu cầu fail-open/fail-closed liên quan availability; **sensor monitoring mode** và **inline prevention mode** không có semantics giống nhau.

### 13.2. Kiểm tra bằng counters độc lập

| Đối tượng | Metric cần đo | Dấu hiệu can thiệp/không bao phủ |
|---|---|---|
| Switch mirror | SPAN session config, mirrored input/output | Session disabled, sai VLAN/port |
| TAP/capture NIC | Link up, RX bytes, RX drops | Link down, buffer overflow |
| Packet capture | Captured packets, kernel drops, file rotation | File nhỏ bất thường, missing segments |
| Flow exporter | Record count, template state, sequence/loss when available | Export stops, invalid template, gap |
| IDS engine | Packets inspected, rule set version, alerts, decode errors | Sensor sees traffic nhưng rules disabled |
| Firewall | Rules, logging flags, allow/deny counters | Logging off trong khi flow counter tăng |
| DNS resolver | Query/response count, upstream reachability | Query log tắt hoặc client chuyển resolver |
| Asset inventory | Expected interfaces/sources, owner | New subnet chưa mirror, removed agent |

Không mặc định **1 packet trên wire = 1 packet đến sensor**; aggregation, sampling, filtering và hardware offload có thể ảnh hưởng counters. Xây baseline theo topology và lưu config version.

### 13.3. Mirror traffic cũng là dữ liệu nhạy cảm

PCAP có thể chứa credentials trong plaintext protocols, hostname, metadata riêng tư hoặc nội dung khách hàng. Mirror ports và capture storage phải nằm ở **management/security segment**, không để người dùng thường có thể mirror/copy traffic tùy ý.

## 14. Syslog: định dạng, TLS và chống giả mạo

Syslog vẫn phổ biến với routers, firewalls, VPN gateways, IDS/IPS và Linux appliances.

### 14.1. Chuẩn liên quan

- **RFC 5424** định nghĩa format syslog có header fields và structured data.
- **RFC 5425** định nghĩa syslog transport qua **TLS**; cung cấp bảo vệ kênh theo cấu hình, không bảo đảm log source gốc là đáng tin khi thiết bị bị compromise.
- **RFC 5848** mô tả syslog signatures cung cấp cơ chế chứng minh authenticity/integrity/sequence theo triển khai, nhưng không phải appliance nào hỗ trợ.
- **RFC 6587** mô tả framing của syslog qua TCP kiểu legacy; **TCP framing không tự có encryption/peer authentication**.

### 14.2. Syslog over UDP và TCP không được thần thánh hóa

| Transport | Lợi điểm | Điều phải đánh giá |
|---|---|---|
| UDP syslog | Đơn giản, ít state | Packet loss, spoofing khi thiếu bảo vệ, không có ack delivery |
| TCP syslog legacy | Có reliable byte stream ở tầng transport | Không bảo vệ nội dung khỏi MITM nếu không TLS, app queue có thể drop |
| TLS syslog | Encrypt/authenticate kênh theo cấu hình | Phải verify certificates; không tự có immutable storage |
| Signed syslog | Có thể chứng minh signer/sequence theo đặc tả | Cần key lifecycle, signature verification và support thực |
| Store-and-forward agent | Giảm mất dữ liệu khi disconnect | Disk exhaustion, duplicate retry và key/storage protection |

### 14.3. Ví dụ tách danh tính đã xác thực và hostname payload

~~~json
{
  "ingest_peer": {
    "authentication": "mutual_tls",
    "certificate_principal": "router-edge-17",
    "verified": true
  },
  "event_claims": {
    "syslog_hostname": "router-core-1",
    "app_name": "firewall",
    "message": "ACL deny src=192.0.2.10 dst=203.0.113.11"
  },
  "validation": {
    "hostname_matches_registered_peer": false,
    "quarantine_reason": "CLAIMED_SOURCE_MISMATCH"
  }
}
~~~

**Schema tự xây để minh họa**, không phải chuẩn output của rsyslog/syslog-ng. Một bản ghi mạo danh hostname khác peer đã xác thực cần quarantine hoặc flag, không được silently rewrite source identity.

### 14.4. Khi thiết bị chỉ hỗ trợ syslog plaintext

Không coi đây là phương án lý tưởng. Có thể dùng **management VLAN/VPN/tunnel qua relay tin cậy** như kiểm soát bù, hạn source, bảo vệ relay và log các giới hạn provenance. Đừng dùng ngôn ngữ "end-to-end authenticated syslog" nếu thiết bị thực tế phát UDP plaintext rồi relay ký/tạo TLS: relay chỉ chứng thực **đã nhận bản ghi**, không chứng minh nguồn gốc mật mã từ appliance.

## 15. OpenTelemetry và các dạng telemetry pipeline hiện đại

**OpenTelemetry (OTel)** thường có SDK, Collector, receivers, processors, exporters cho **logs, metrics và traces**. Hệ này có khả năng mở rộng nhưng cũng tạo điểm chỉnh sửa và mất dữ liệu.

### 15.1. Luồng chính

~~~mermaid
flowchart LR
    APP[App instrumentation / Host agent] --> RC[OTel Collector Receiver]
    RC --> PR[Processors: memory limit, resource attrs, filter, batch]
    PR --> EX[Exporter]
    EX --> OT[OTLP TLS / Queue]
    OT --> SIEM[Telemetry backend / SIEM]
    C[Protected config repo] -. Version + approvals .-> RC
    C -. Version + approvals .-> PR
    H[Watchdog] -. Receiver accepted/dropped + queue + exporter failures .-> EX
    H -. Synthetic end-to-end event .-> SIEM
~~~

### 15.2. Các ranh giới bảo mật

- **Receiver** có thể bị gửi dữ liệu giả hoặc input quá lớn; cấu hình **listen interface, TLS/mTLS/auth, max request size và resource limits** theo component.
- **Processor** có thể drop events bằng **filter, sampling, transform**; protect config và log số lượng trước/sau transform.
- **Exporter** có thể gặp **TLS errors, permission denied, queue full, retry storms, timeout**.
- **Batching** có thể thêm độ trễ và điều chỉnh event order; không mặc định end-to-end exactly-once.
- **Persistent queues/remote storage** có thể giảm mất sự kiện nhưng cần mã hóa/quyền, disk capacity, restore và duplicate handling.
- **Resource attributes** như service.name/host.name có thể do application tự khai; giữ phân biệt **authenticated receiver peer** với client-controlled labels.

### 15.3. Pseudoconfig collector — chỉ minh họa security intent

~~~yaml
# Không phải OTel Collector config có thể apply trực tiếp.
telemetry_ingest:
  receiver:
    listen: "private-listener-only"
    protocol: "OTLP"
    tls:
      verify_client_certificate: true
      trusted_ca: "approved-agent-ca"
      server_identity: "otel-ingest.internal.example"
    allowed_agent_principals: ["approved-inventory-agents"]
    max_request_size: "bounded-by-capacity-plan"
  pipeline:
    filters:
      require_change_approval: true
      emit_drop_counters_per_reason: true
    queue:
      durable: true
      encrypted_at_rest: true
      alert_on_backpressure: true
  exporter:
    verify_siembackend_certificate: true
    rotate_credentials: true
    do_not_log_secrets: true
  watchdog:
    synthetic_canary: true
    send_alert_via_independent_channel: true
~~~

**OTel YAML thực tế khác theo version/distribution và extensions**; các field này là ý định thiết kế, không phải API native. Phải kiểm tra receiver/exporter authentication, pipeline telemetry naming và storage extension được hỗ trợ ở bản đang chạy.

### 15.4. Tránh tự phá availability

Đặt **memory limits** quá thấp gây drop; queue giới hạn quá nhỏ gây mất log khi backend chậm; batching quá dài gây delay SOC. Đo load test theo event class và chọn **critical audit path** có bảo đảm lưu/chuyển tốt hơn telemetry tổng hợp.

## 16. Message queue, buffer và backpressure

Queue là điểm dễ làm mù vì bên gửi có thể báo “đã giao thành công” khi dữ liệu mới chỉ nằm trong memory của relay, chưa được lưu bền.

### 16.1. Câu hỏi cần xác minh

- **Ack nghĩa là gì?** Socket write, broker accept, replicated commit hay SIEM index success?
- **Delivery semantics:** at-most-once, at-least-once, effectively-once qua dedup; **không tự tuyên bố exactly-once end-to-end**.
- **Capacity:** queue depth, oldest event age, disk free, memory, retry và dead-letter count.
- **Permissions:** publisher chỉ append vào topic/stream của mình, không delete hoặc consume dữ liệu nhạy cảm.
- **Resilience:** broker replication, failover, persistent volumes, network partitions và disaster recovery.
- **Integrity:** TLS/mTLS, message authentication/signature nếu cần, immutable source archive.
- **Poison messages:** một event malformed có làm parser retry vô tận và chặn toàn partition không?
- **Ordering:** per-partition ordering khác global ordering; timestamp và sequence có thể lặp/reset.

### 16.2. Thiết kế chống queue exhaustion

| Biện pháp | Lợi ích | Tác dụng phụ cần quản lý |
|---|---|---|
| Quota/rate theo authenticated source | Chặn một nguồn lấn toàn pipeline | Critical events của nguồn đó có thể bị drop |
| Hàng riêng cho audit/security critical | Hạn chế noisy app logs ảnh hưởng | Tăng cấu hình và capacity |
| Durable disk buffer | Chịu backend outage | Disk full, encryption, lifecycle |
| Backpressure | Tránh overload downstream | Source có thể không đủ buffer |
| Bounded retries + dead-letter | Tránh poison-event block | Dead-letter cũng cần audit/retention |
| Schema validation trước ingest | Giảm parser crash/poison | Quarantine event cần điều tra |
| Replay với event ID | Recover after outage | Duplicates và timeline ambiguity |
| Out-of-band pipeline health | Phát hiện mất telemetry | Cần hệ giám sát độc lập |

### 16.3. Không đánh đổi mất log để giảm cost mà không ghi rõ

Sampling có thể hợp lý với high-volume traces/flows, nhưng **audit records phục vụ điều tra hoặc nghĩa vụ pháp lý** có thể đòi retention khác. Document rõ **source sampling, sampling ratio, filters, error budget và excluded event classes**; nếu thay config phải qua change review.

## 17. Parser, enrichment và nguy cơ poisoning

### 17.1. Bản ghi ngoài Internet là dữ liệu không tin

Ví dụ user gửi HTTP User-Agent có newline hoặc chuỗi giả log:

~~~text
User-Agent: demo-client
[2026-11-28 INFO] firewall: ALL CLEAR
admin_role=superuser
~~~

Nếu ứng dụng chèn thẳng User-Agent vào text log không escape, SOC có thể nhìn nhầm dòng thứ hai thành event mới hoặc parser tách sai. Đây là **log injection**, không phải bằng chứng firewall thật sự gửi ALL CLEAR.

**Kiểm soát:** structured logging, escape/control-character sanitization, length limits, normalized fields, schema validation và phân biệt **source-observed fields** với **untrusted request fields**.

### 17.2. Hạn chế quyền của parser và enrichment

- Dùng **schema allowlist**, kiểm tra required fields/type/ranges.
- Parser không thực thi code hoặc truy vấn mạng tùy ý chỉ vì event chứa URL.
- Enrichment từ CMDB/GeoIP/asset catalogs phải ghi **source/version/time**; không coi reverse DNS hoặc user header là identity đã xác minh.
- Sandboxing, dependency scanning và resource limits cho custom processors/plugins.
- Log bản ghi bị **parse error, truncated, rejected, quarantined** kèm counts và sample an toàn.
- Không silently drop "unknown event" trong security-critical stream khi chưa có triage plan.

### 17.3. Không đánh đồng log được chuẩn hóa với bản gốc

Một hệ SIEM có thể rename field, parse time, enrich asset owner hoặc redact body. Khi điều tra, cần biết **raw original bytes** (nếu retention cho phép), transformation version, parse status và provenance metadata. **Normalized event không phải original evidence**.

### 17.4. Threat của label/metadata cardinality

Prometheus/OTel metrics có thể bị tấn công qua label chứa random user ID/request ID khiến số time series tăng không kiểm soát, ảnh hưởng CPU/memory/storage và alert evaluation. Dùng **bounded labels, field normalization, cardinality quotas và record-level logs** cho high-cardinality details.

## 18. Hash, chữ ký và hash chain: làm gì và không làm gì?

### 18.1. Hash một file

Một hàm băm mật mã như SHA-256 có thể phát hiện file **khác bytes** nếu digest gốc được bảo vệ đáng tin.

~~~text
original_file_bytes  --SHA-256--> expected_digest
current_file_bytes   --SHA-256--> observed_digest

Nếu observed_digest != expected_digest:
  Có thay đổi bytes hoặc quy trình đọc/chuẩn hóa khác.
Nếu observed_digest == expected_digest:
  File khớp digest đã đối chiếu;
  CHƯA chứng minh nguồn tạo file là trung thực.
~~~

**Đừng lưu hash ngay cạnh file trong cùng một thư mục mà attacker có quyền sửa cả hai** rồi gọi là tamper-proof. Dùng trusted manifest/signature hoặc timestamp anchor ngoài cùng trust boundary.

### 18.2. Digital signature so với HMAC

| Cơ chế | Chứng minh được gì? | Giới hạn |
|---|---|---|
| **Hash đơn** | Bytes không đổi so với digest được tin | Không xác minh ai tạo record nếu digest có thể giả |
| **HMAC** | Bên có shared secret đã tạo MAC | Mọi bên giữ secret có thể tạo MAC; khó phân định signer cá thể |
| **Digital signature** | Bên giữ signing private key ký nội dung | Key compromise vẫn có thể tạo dữ liệu giả |
| **Hash chain** | Thứ tự/quan hệ giữa các records được gắn | Có thể rewrite toàn chain nếu attacker kiểm soát anchor |
| **Signed batch + external anchor** | Bảo vệ tính toàn vẹn batch và kiểm tra chống rewrite | Phụ thuộc trust/availability của khóa và external anchor |
| **WORM archive** | Chặn các thao tác rewrite/delete trong retention theo mode | Không chống false data được ingest từ đầu |

### 18.3. Hash chain theo batch

~~~text
h0 = trusted_initial_anchor
h1 = SHA256(h0 || canonical(event_batch_1))
h2 = SHA256(h1 || canonical(event_batch_2))
h3 = SHA256(h2 || canonical(event_batch_3))

Định kỳ:
  sign(h3, dedicated_signing_key)
  publish signed_anchor ngoài nơi lưu log chính.
~~~

Đây là **sơ đồ lý thuyết**, không phải định dạng ký/serialization triển khai. Production phải định nghĩa **canonical encoding, domain separation, hash algorithm, key rotation, timestamp/sequence, empty batches, ordering và verification procedure**. Nếu signer/collector bị compromise trước khi ký, **sự kiện giả có thể trở thành dữ liệu đã ký**.

### 18.4. Gap không mặc nhiên là log đã bị xóa

Nếu stream có event sequence 101,102,104, có thể thiếu 103 do **sampling, exporter restart, loss hoặc tamper**. Thiết kế sequence per-source/per-epoch và ghi **restart indicator**, sampling policy, counters. Chỉ kết luận deletion khi có bằng chứng từ **trusted anchor, raw archive hoặc independent sensor**.

## 19. Immutable storage, WORM và bản sao độc lập

### 19.1. Tại sao cần immutable retention?

Nếu một compromise actor có quyền xóa event trong SIEM, họ có thể xóa bằng chứng sau xâm nhập. Một **raw audit archive append-only/immutable trong retention window** giảm khả năng đó và giúp đối chiếu với index đã parse.

### 19.2. Ba lớp lưu trữ

~~~mermaid
flowchart LR
    S[Authenticated telemetry ingress] --> A[Protected raw archive / WORM]
    S --> Q[Parse / Enrich pipeline]
    Q --> I[Searchable SIEM Index]
    A -. Rebuild / compare .-> I
    A --> V[Integrity verifier + signed manifest]
    V --> O[Independent audit / Alert path]
~~~

| Lớp | Mục tiêu | Cần bảo vệ |
|---|---|---|
| **Raw archive** | Giữ bản gốc để forensic/replay | Retention lock, KMS, access logs, storage policy |
| **Searchable index** | Truy vấn/phát hiện nhanh | RBAC, index lifecycle, snapshots, audit |
| **Independent proof/manifest** | Chứng minh phiên bản/sequence/retention | Signing keys tách biệt và external anchor |

### 19.3. WORM không giống nhau trên mọi nền tảng

Ví dụ object storage có **retention lock** với chế độ quản trị khác nhau. **Governance mode** có thể cho phép các identity đặc quyền bypass theo cơ chế provider; **compliance mode** thường chặt hơn trong retention window theo ràng buộc sản phẩm. Trước khi tuyên bố “không thể xóa”, phải review **mode, object versioning, retention/legal hold, quyền bypass, bucket/account policy, KMS key lifecycle và replication**.

### 19.4. Backup chưa phải immutable archive

Backup thường giúp **recover file/index**, nhưng nếu admin bị compromise có thể xóa cả backup hoặc encryption keys, bằng chứng có thể biến mất. Nên có **out-of-band/cross-account/cross-region copy** theo risk, tách quyền điều khiển và định kỳ restore/test integrity. Cross-region copy vẫn có thể bị tác động nếu cùng khóa/role/root control.

### 19.5. Retention và privacy

Không giữ raw payload vô thời hạn chỉ để phòng xóa log. Xác định **data classification, lawful purpose, retention period, deletion obligations và access approval**, đồng thời chọn retention lock tương thích yêu cầu pháp lý. WORM retention quá dài có thể tạo rủi ro riêng tư và chi phí.

## 20. Timestamp, sequence và đối chiếu nhiều đồng hồ

Một SOC timeline sai có thể khiến điều tra nhầm thứ tự "login → policy change → data transfer".

### 20.1. Giữ các mốc thời gian khác nhau

| Time | Ý nghĩa |
|---|---|
| **event_time** | Nguồn quan sát sự kiện lúc nào (có thể sai nếu clock bị chỉnh) |
| **source_sent_at** | Agent/exporter đẩy bản ghi khi nào |
| **collector_received_at** | Ingest gateway nhận record lúc nào |
| **broker_committed_at** | Queue nhận bền khi nào (nếu hỗ trợ) |
| **indexed_at / ingest_time** | SIEM có thể tìm kiếm lúc nào |
| **detected_at** | Detection rule phát hiện lúc nào |
| **alert_delivered_at** | Notification tới người nhận khi nào |

Không ghi một trường **timestamp** duy nhất rồi coi mọi clock là đồng nhất.

### 20.2. NTP/time hardening

- Đồng bộ **NTP hoặc thời gian tin cậy** theo platform, kiểm soát ai có quyền đổi clock/time service.
- Giám sát **offset, clock steps, timezone parsing, leap-second/rollover behavior** khi liên quan.
- Có **ingest time đáng tin hơn source** để đánh giá nguồn clock compromise.
- Signature timestamp từ hệ tách biệt có thể tăng bằng chứng, nhưng không tự chứng minh payload đúng.
- Tính **event lag = collector_received_at - event_time** sau khi xét clock skew; nếu âm có thể do clock, không phải du hành thời gian.
- Không dùng số timestamp do HTTP client gửi để quyết định anti-replay của telemetry mà không xác minh.

### 20.3. Sequence và stream epochs

Một exporter có thể restart làm sequence reset. Dùng **source identity + boot/session epoch + sequence** khi có, so counters và known sampling. Nếu protocol không có sequence tin cậy, dùng **heartbeat/canary, traffic-independent counters và archival manifests**; đừng bịa "guaranteed gap detection".

## 21. IAM, RBAC và Separation of Duties cho hệ giám sát

### 21.1. Các vai trò không nên gom

| Vai trò | Quyền cần | Quyền phải hạn chế |
|---|---|---|
| **Telemetry sender** | Append/publish vào stream được cấp | Delete logs, edit retention, read mọi tenants |
| **Collector operator** | Deploy/maintain collector | Tự thay audit/retention và tắt alert không review |
| **Pipeline engineer** | Sửa parser/enrichment qua CI | Sửa raw archive hoặc access keys |
| **Detection engineer** | Viết/test rules | Deploy production rule không approval nếu nhạy cảm |
| **SOC analyst** | Search/read scoped data, create incident | Delete index/raw logs và tắt global alerts |
| **SIEM admin** | Quản lý hệ/availability | Không tự tắt audit/retention mà không được theo dõi |
| **Storage archive admin** | Retention/backup maintenance | Bypass WORM/erase archive tùy ý |
| **Security auditor** | Verify access, policies, integrity | Không cần sửa source data |
| **Incident responder** | Time-bound break-glass scope | Permanent role, unrestricted export |
| **CI deployment role** | Apply reviewed config | Grant IAM admin, change protected branch/audit sink |

### 21.2. SoD không chỉ là hai người bấm nút

Một người có quyền sửa **CI policy evaluation, CODEOWNERS, secret store, identity provider role grants hoặc audit sink** có thể vô hiệu review dù trên UI có hai approvals. Protect **control-plane resources, CI configuration, versioned policies và role assumptions**, audit bằng hệ tách biệt.

### 21.3. Break-glass

Khi incident nghiêm trọng cần tăng quyền read/restore SIEM, phải có **verified incident ID, time-bound elevation, two-person review khi khả thi, session recording/audit, reason và post-review**. Không dùng emergency làm cách giữ quyền SIEM admin vô thời hạn.

### 21.4. Đọc log cũng có thể gây rò rỉ

SIEM search có thể truy cập **source IPs, usernames, request headers, secrets bị log nhầm, packet payload và topology**. Hạn **query/export, cross-tenant search, large result downloads và raw PCAP** theo roles, purpose và audit. Đừng gửi raw evidence qua chat/ticket công khai.

## 22. Change management và supply-chain cho monitoring

Một sửa đổi nhỏ như **filter debug logs**, **exclude Kubernetes Secrets audit**, hoặc **suppress IDS signature** có thể làm mù SOC dù agent vẫn khỏe.

### 22.1. Những thay đổi cần review

- Sensor capture filter, SPAN/TAP mirror session, IDS/IPS rule sets.
- Agent version, processor/collector plugins, binary/OCI image, runtime permissions.
- OTel/syslog receiver authentication, parser mappings và event drop filters.
- Queue topic ACL, capacity/quota, retention và retry/dead-letter policy.
- SIEM index lifecycle, detection queries, mute/silences, notification routes.
- Cloud audit logging scope, excluded event types, sink destination và retention.
- Terraform/GitOps modules, CI workflows, signing keys và deployment roles.
- Time synchronization, DNS/certificate trust và firewall routes đến collectors.

### 22.2. Pipeline bảo vệ thay đổi

~~~mermaid
flowchart TD
    R[Configuration change PR] --> T[Schema lint + unit/negative tests]
    T --> S[Security review for sensitive filters]
    S --> A{Authorized approver + exact revision?}
    A -- No --> X[Reject]
    A -- Yes --> P[Protected CI + signed artifact]
    P --> C[Canary rollout]
    C --> V{Expected events/canaries and detections intact?}
    V -- No --> B[Rollback + incident review]
    V -- Yes --> G[Progressive rollout]
    G --> M[Audit, config drift and pipeline watchdog]
~~~

### 22.3. Detection rule là security control

Thay **threshold** hoặc **enabled flag** của rule high-severity cần audit và approval tương tự thay firewall policy. Một **temporary suppression** cần owner, ticket, bounded TTL, alert khi gần hết hạn và post-review; tránh mutes vô thời hạn.

### 22.4. Signed artifacts không bằng provenance thực thi

Image signature hoặc Git commit có thể bảo đảm bạn triển khai artifact đã được ký; không chứng minh artifact **không có bug/backdoor**. Bổ sung dependency vulnerability management, SAST, SBOM, protected CI, runtime admission và canary tests.

## 23. Cloud logging: bảo vệ cả control plane và data plane

Với cloud, log có thể phát từ control-plane API services, network resources và managed products. Cần review **log coverage ở mọi account/project/subscription/region**, quyền thay đổi logging và sink/retention.

### 23.1. AWS — ví dụ mối quan tâm

| Thành phần | Dữ liệu/đích | Rủi ro và kiểm soát |
|---|---|---|
| **CloudTrail** | Management/data events theo cấu hình | Trail/event selector bị sửa/tắt; central org logging |
| **VPC Flow Logs** | Network flow metadata | Coverage VPC/subnet/ENI thiếu, filter/aggregation, IAM |
| **CloudWatch Logs** | Log groups/streams, retention | Delete group/stream, PutRetentionPolicy, IAM, export |
| **S3 archive** | Raw log objects | Versioning/Object Lock, access policies, KMS, cross-account |
| **CloudWatch alarms/EventBridge** | Detection/notification | Disable alarm, change event rules, sink tamper |
| **AWS Config** | Resource configuration state | Recorder/scope drift; không thay flow log |

Một **organization/central logging account** có thể giảm việc workload account tự xóa chứng cứ, nhưng vẫn cần bảo vệ **org IAM, SCPs, break-glass, KMS and retention rules**. Không khẳng định tất cả CloudTrail data events mặc định được log; phải cấu hình đúng resource/event selectors.

### 23.2. Azure — ví dụ mối quan tâm

- **Azure Activity Log** và resource diagnostic logs có phạm vi khác nhau; đừng nhầm subscription control-plane events với mọi packet flow.
- **Diagnostic settings, Log Analytics workspace, Event Hub, storage account** cần RBAC hẹp, retention protection và audit thay đổi.
- **NSG flow logs/virtual network flow logs** có sản phẩm/version lifecycle khác nhau; xác minh tính khả dụng và scope hiện hành.
- Bảo vệ **Azure Monitor alert rules, action groups, Microsoft Sentinel analytics/automation, role assignments** và các export paths.
- Xem **Azure resource locks/immutability storage** theo loại resource và security goals; resource lock không thay WORM/evidence integrity.

### 23.3. Google Cloud — ví dụ mối quan tâm

- **Cloud Audit Logs** có các loại events và coverage/retention khác nhau; không mặc định mọi Data Access logs được bật/giữ ở mọi dịch vụ.
- **Cloud Logging sinks, buckets, exclusions, retention settings và Log Router** là config rất nhạy cảm, cần IAM/organization policy theo khả năng.
- **VPC Flow Logs/Firewall Rules Logging** cung cấp metadata với sampling/config riêng, không phải packet capture.
- Protect **logging bucket/retention, CMEK keys, cross-project destination, alerting policies và Cloud IAM**.
- Đánh giá khả năng **bucket retention lock** và guardrails của từng product; không dùng tên tính năng như bằng chứng chưa thể thay đổi dữ liệu.

### 23.4. Tổng hợp nguyên tắc multi-cloud

1. Xác định **source/service/region/account inventory**.
2. Bật loại audit/flow logs cần theo risk, ghi rõ **sampling, coverage và retention**.
3. Chuyển raw audit sang **security logging boundary** không do app admin kiểm soát.
4. Giới hạn quyền tắt log, đổi sink, xóa bucket hoặc revoke KMS key.
5. Monitor **control-plane changes và data-plane health** độc lập.
6. Kiểm thử **gián đoạn, threat-induced disable và restore** trong scope được phép.

## 24. Kubernetes: audit, collectors và bảo vệ workload

### 24.1. Kubernetes API audit khác Pod/application logs

**Kubernetes audit logs** ghi nhận request/response metadata của Kubernetes API Server tùy **audit policy và backend**; log ứng dụng/Pod từ stdout/stderr là nguồn khác. Một security case như **Pod cấp quyền privileged, sửa NetworkPolicy hoặc patch ConfigMap** cần API audit coverage; một ứng dụng trả HTTP 403 cần application/access logs.

### 24.2. Rủi ro Kubernetes riêng

| Điểm | Nguy cơ | Kiểm soát |
|---|---|---|
| **API audit policy/backend** | Loại event nhạy cảm bị omit, log sink outage | Reviewed audit policy, control-plane logging health |
| **Collector DaemonSet** | Privileged Pod/hostPath quá rộng | Pod security, restricted RBAC/mounts và image policy |
| **Kubelet/node logs** | Root/node compromise sửa/xóa local logs | Fast off-node forwarding, node security |
| **ServiceAccount** | Có quyền list/get Secrets ngoài scope | Least privilege RBAC, token audience, automount review |
| **NetworkPolicy** | Ngăn collector gửi hoặc cho attacker gọi ingest | Dedicated egress allow + authenticated receiver |
| **ConfigMap/Secret** | Pipeline filters, credentials bị sửa | GitOps, restricted patch, secret lifecycle |
| **Admission** | Không inject collector hoặc chấp nhận malicious Pod | Governance/admission logs và instance inventory |
| **Namespace deletion** | Xóa các app/collector log resources | Central audit storage không phụ thuộc namespace |
| **Node drain/autoscale** | Chuyển node làm agent mất coverage | DaemonSet rollout, source lifecycle, queue drain |
| **Service mesh** | TLS/mTLS hoặc sidecar capture khác kỳ vọng | Trust and traffic tests, not blanket bypass |

### 24.3. Ví dụ Kubernetes RBAC đọc theo nhu cầu

~~~yaml
# Minh họa Role rất hẹp cho Pod inventory trong namespace observability.
# Không phải quyền cần thiết mặc định của mọi collector.
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: collector-pod-reader
  namespace: observability
rules:
  - apiGroups: [""]
    resources: ["pods"]
    verbs: ["get", "list", "watch"]
~~~

Đây chỉ là quyền **Pod metadata trong một namespace**, chưa phải cấu hình collector đầy đủ và không cấp đọc **node-wide Pods, Kubernetes audit hoặc host logs**. Nếu cần multi-namespace/cluster-wide, review ClusterRole riêng theo năng lực và protect SA.

### 24.4. DaemonSet privilege và hostPath

Collector đọc /var/log/containers, journald hoặc eBPF có thể yêu cầu mounts/capabilities cụ thể. Việc đọc host logs có rủi ro **lộ secrets, root filesystem**; cần **read-only mounts, securityContext thích hợp, restricted service account** và review Pod Security Standards/trust boundaries. Không mặc định **privileged: true** cho mọi logging Pod.

### 24.5. Admission và audit là đối chứng

Nếu attacker sửa Kubernetes **audit policy**, chính audit stream có thể không phản ánh thay đổi theo kỳ vọng. Bổ sung **cloud control-plane logs, GitOps changes, etcd/control-plane access audit** theo kiến trúc và bảo vệ nơi lưu ngoài cluster. Không phụ thuộc duy nhất collector Pod trong cluster để chứng minh cluster không bị thao túng.

## 25. Zero Trust và phân đoạn mạng cho hệ giám sát

Một hệ monitoring thường có quyền **đọc dữ liệu rộng hơn ứng dụng**, vì vậy ingest endpoints, admin interfaces và storage không nên cùng nằm trong một flat subnet dễ đi ngang.

### 25.1. Tách các vùng tin cậy

| Zone | Thành phần | Đường đi cần thiết |
|---|---|---|
| **Telemetry source zone** | Router, firewall, endpoint agent, application | Gửi tới relay/collector đã phê duyệt |
| **Collection zone** | Syslog/OTLP receivers, network sensors | Nhận từ sources đã xác thực, gửi queue |
| **Processing zone** | Queue, parser, enrichment, normalization | Nhận từ collector; ghi output sang archive/index |
| **Storage zone** | SIEM index, raw WORM archive, backup | Chỉ write/read theo service roles cụ thể |
| **Detection zone** | Query engines, rule runners, alert managers | Đọc search index; gửi alert channels |
| **Management zone** | CI/CD, control plane, IAM/admin access | MFA/JIT, approved maintenance, change audit |
| **Independent audit zone** | Immutable audit archive, watchdog | Nhận telemetry về **chính pipeline** ngoài single point |

### 25.2. Mẫu ma trận kết nối

| Source | Destination | Protocol/identity | Decision |
|---|---|---|---|
| Registered agent | Ingest proxy | TLS/mTLS verified source | ALLOW scoped |
| Unknown workload | Ingest proxy | No valid identity | DENY |
| Ingest proxy | Broker topic A | Broker mTLS + topic ACL append | ALLOW |
| Ingest proxy | Raw archive delete API | Không cần cho chức năng | DENY |
| Parser service | SIEM index writer | Only write into scoped index | ALLOW |
| SOC read-only user | Raw archive deletion | Không có nghiệp vụ | DENY |
| Deployment CI | Approved monitoring config API | Short-lived identity, reviewed artifact | ALLOW |
| Workload app Pod | Collector admin API | Không được phép | DENY |
| Untrusted Internet | Monitoring dashboard/admin | Không trực tiếp exposed | DENY |
| Independent watchdog | Pager/secondary incident channel | Verified channel scoped | ALLOW |

**NetworkPolicy/firewall chỉ kiểm soát đường đi**; **application/queue/IAM authorization** cần bảo vệ topic, document index, retention và query. Không mở mọi port của collector trong Kubernetes chỉ để việc debugging nhanh hơn.

### 25.3. Điểm yếu của chung trust root

Nếu app admin cũng có quyền KMS, IAM, log sink và WORM retention policy, một account compromise có thể vô hiệu mọi lớp. Thiết kế **dedicated security account/project/subscription, protected organization policy, SoD và out-of-band alert channel** theo risk.

## 26. Bảo vệ SIEM detection, dashboard và alert pipeline

### 26.1. Sửa detection cũng là sửa biện pháp bảo mật

Một attacker có thể ẩn hoạt động bằng:

- Disable rule hoặc thay **query** loại trừ user/source của mình.
- Tăng threshold quá cao hoặc giảm evaluation frequency.
- Đổi **index pattern/data source** sang index ít events.
- Tạo **suppression/maintenance window** kéo dài bất thường.
- Sửa rule để **ignore chính event type "log deletion"**.
- Đổi **notification route, pager integration, email/webhook** hoặc xóa subscriber.
- Tạo search permission khiến analysts không thấy log của một tenant/account.
- Gắn nhãn event severity thấp làm triage bỏ qua.

### 26.2. Biện pháp ở rule lifecycle

| Giai đoạn | Kiểm soát |
|---|---|
| Design | Rule owner, threat hypothesis, source dependency, severity |
| Review | Second-person approval cho critical rules |
| Test | Known-bad synthetic event và known-benign sample |
| Deploy | Signed/versioned artifact, approved CI, immutable change log |
| Run | Rule enabled state, evaluation success, latency, output count |
| Silence | Owner, reason, expiration, alert khi kéo dài |
| Update | Change diff, policy/tests/rollout |
| Recovery | Known-good version và rule restore rehearsal |

### 26.3. Alert channel phải được kiểm thử

Một rule có thể chạy và ghi alert trong SIEM nhưng không tới SOC do **webhook key revoked, mail routing lỗi, pager service disabled, rate limit hoặc API quota**. Nên có **synthetic safe alert** kiểm tra từ source qua pipeline đến **actual response channel**, với cơ chế ngăn tạo incident giả/tốn kém.

### 26.4. Đừng để rule tự kiểm tra rule

Nếu kiểm tra "critical rule enabled" bằng chính rule đó, khi rule bị tắt thì kiểm tra cũng chết. Dùng **đầu giám sát độc lập** kiểm tra API/config state hoặc CI desired-state drift, gửi alert qua **đường khác**.

## 27. Log forgery, replay và injection

### 27.1. Ba kiểu khác nhau

- **Forgery:** một nguồn không được phép tạo event giả dưới danh tính thiết bị khác.
- **Replay:** dùng lại event/batch cũ làm tưởng như đang có hoạt động mới, hoặc tạo false positives.
- **Injection:** dữ liệu người dùng chèn ký tự/fields để parser/log viewer hiểu sai.

### 27.2. Các kiểm soát chống replay và giả mạo

1. Verify **authenticated sender identity** qua mTLS/token có issuer/audience/expiry và per-source ACL.
2. Giữ riêng **source_observed_time, collector_received_time, stream_epoch, sequence, event ID** theo protocol.
3. Dedupe theo **stable source+event ID**, không loại bỏ bản ghi khác nhau có timestamp giống nhau.
4. Với signed batches, xác minh **signature, signer permission, sequence/anchor và validity**, không chỉ chữ ký đúng format.
5. Bảo vệ **log parsers** khỏi control characters, multiple-line spoofing, duplicate JSON keys và oversized payload.
6. Giới hạn **clock skew window**, nhưng không tự drop forensic evidence quan trọng chỉ vì event_time quá cũ; có thể quarantine và annotate.
7. Dùng **independent comparison** khi endpoint bị compromise; chữ ký của nó có thể vẫn hợp lệ.

### 27.3. Cẩn trọng với JSON duplicate keys

Một JSON event chứa hai field **user_role** có thể bị các parsers xử lý khác nhau (first wins/last wins). Nếu SIEM và detector hiểu khác, attacker có thể làm lệch policy. Dùng **schema validation/canonical decoding** và reject/quarantine duplicate keys ở security-critical fields.

### 27.4. Ví dụ schema normalized — danh tính nguồn không được lấy từ payload

~~~json
{
  "event_id": "evt-demo-117",
  "event_time": "2026-11-28T11:00:00Z",
  "collector_received_at": "2026-11-28T11:00:01.540Z",
  "transport": {
    "protocol": "tls",
    "peer_principal": "fw-branch-17",
    "peer_verified": true
  },
  "payload_claims": {
    "hostname": "fw-branch-17",
    "device_type": "firewall",
    "message_type": "ACL_DENY"
  },
  "pipeline": {
    "collector_id": "syslog-ingest-a",
    "parser_version": "network-events-v7",
    "schema_valid": true,
    "source_registry_match": true,
    "raw_archive_pointer": "archive-demo/2026/11/28/batch-17",
    "integrity_verification": "NOT_YET_VERIFIED"
  }
}
~~~

**Đây là schema minh họa**; trường **peer_verified=true** phải do collector/proxy tạo sau khi kiểm chứng, không được copy từ payload gửi đến.

## 28. Availability và ngăn denial of telemetry

### 28.1. Vì sao hệ giám sát dễ bị flood?

Attacker có thể tạo hàng triệu requests bị từ chối, khiến **WAF logs, authentication logs, DNS logs, IDS alerts hoặc OTel traces** tăng vọt. Không cần xóa log; họ có thể làm **queue đầy, SIEM vượt ingest quota, index lag, parser timeout hoặc retention ngắn vì cost**.

### 28.2. Thiết kế chịu tải

- **Capacity planning:** expected EPS (events per second), event size, burst factor, peak network flows.
- **Priority isolation:** critical audit/config-change/security events không chia cùng finite queue với debug traces không giới hạn.
- **Bounded resource usage:** receiver max body size, parser CPU/memory limits, backpressure.
- **Durable buffering:** đảm bảo đúng khả năng disk/HA/replication; đo oldest item age.
- **Retry with backoff:** tránh thundering herd và duplicate storms.
- **Quota by authenticated sender:** không để một source lấn toàn broker.
- **Schema quarantine:** poison-message được cách ly nhưng event gốc vẫn có metadata và evidence theo retention.
- **Alternative monitoring:** watchdog ngoài đường chính báo queue full/drops.
- **Cost anomaly detection:** alert khi ingestion cost/retention settings đổi đáng kể.

### 28.3. SLO theo loại dữ liệu

Một loại **debug trace** có thể chấp nhận sampling, nhưng **IAM privileged changes, cloud audit configuration changes hoặc incident evidence** có thể đòi độ phủ/retention cao hơn. Không nên silently giảm audit coverage khi traffic tăng. Nếu phải degrade, có **explicit degradation mode**, owner/risk approval và incident notification.

### 28.4. Phòng DoS không được biến thành xóa chứng cứ

Nếu một source gửi quá nhiều events bất thường, toàn bộ event burst có thể là bằng chứng. Tùy risk/chi phí, có thể lưu **sample + count + signed summary/quarantine** và document chính xác **đã drop/sampled những gì**; không báo “full capture” nếu chỉ còn một phần.

## 29. Giám sát chính hệ thống giám sát

Một telemetry watchdog phải phát hiện được **chết âm thầm (silent failure)** ở nhiều lớp.

### 29.1. Health metrics tối thiểu

| Giai đoạn | Metric | Dấu hiệu |
|---|---|---|
| Source/agent | Last heartbeat, events generated, version/config checksum | Agent tắt hoặc config drift |
| Network sensor | RX/packet drops, mirror session state | Mất traffic ở capture plane |
| Ingest gateway | Auth failures, accepted/rejected count, connected sources | Source bị giả, mất kết nối |
| Queue | Depth, oldest age, retry, failed/dead-letter | Backpressure và backlog |
| Parser | Parse success/fail, filtered/dropped count, schema version | Rule lọc mới, poison message |
| Exporter | Send failures, target TLS/auth errors, batch retries | Backend unreachable |
| Index/storage | Indexed vs accepted count, retention state, write errors | Mất dữ liệu ở storage |
| Detection | Enabled/evaluation count, rule version, execution errors | Rule tắt hoặc query sai |
| Alert delivery | Notification send/delivery/ack, silence list | SOC không nhận thông báo |
| Archive | Raw file count, signed manifest, hash verification | Rewrite/deletion/tamper |
| Control plane | IAM changes, config rollout drift, audit policy | Attacker sửa enforcement |
| Time | Source/collector clock offset, event lag | Timeline không đáng tin |

### 29.2. Heartbeat chưa chứng minh coverage

Một app gửi heartbeat **mỗi phút** dù không còn log auth events. Phải có **expected event classes**, canary và đối chứng. Ví dụ với API gateway, số request processed nên tương quan được với access log entries sau khi tính **sampling/filtering/missing requests**; không đòi so đúng 1:1 với gRPC multiplexing/tracing.

### 29.3. Synthetic canary từ đầu tới cuối

~~~mermaid
sequenceDiagram
    autonumber
    participant W as Independent Canary Generator
    participant S as Test Source / Agent
    participant C as Ingest / Queue / Parser
    participant I as Searchable SIEM + Raw Archive
    participant D as Detection / Alert Manager
    participant A as Independent Watchdog
    W->>S: Generate benign test event with canary ID
    S->>C: Send authenticated telemetry
    C->>I: Store original/normalized event
    I-->>A: Event can be queried by canary ID
    I->>D: Detection matching synthetic event
    D-->>A: Safe test notification received
    A->>A: Compare expected time, source, gaps and policy version
    A-->>W: Pass/Fail with phase-specific evidence
~~~

**Canary là event lành tính**, có chủ đích, không chứa PII/secrets, không mở port hay chạy exploit. Test phải có **unique ID, TTL và alert routing an toàn** để không gây incident giả hoặc overload.

### 29.4. Out-of-band alert

Nếu primary SIEM down, alert monitoring outage phải đi qua **independent pager or cloud monitoring channel** không cần nhận log từ chính SIEM đó. Dù không thể có hệ hoàn toàn độc lập, phải nêu rõ **shared dependencies**: cùng IdP/KMS/network/region vẫn có thể mất đồng thời.

### 29.5. Coverage theo inventory

Nên xây bảng **expected_sources** gồm asset ID, owner, environment, critical event classes, last known active, expected frequency, agent/control-plane endpoint. So với **observed_sources** để phát hiện thiếu. Tránh alert false-positive khi VM/Pod bị autoscale hoặc asset được retire đúng quy trình.

## 30. Detection và truy vấn đối soát telemetry

Dữ liệu dưới đây giả định đã được chuẩn hóa. **Không có một schema SQL duy nhất** cho mọi SIEM; chỉnh theo OpenSearch/Splunk/Kusto/BigQuery/Snowflake/Sentinel hoặc product khác.

### 30.1. Tìm source mất heartbeat

~~~sql
-- Bảng synthetic: expected_sources và source_heartbeats.
SELECT e.source_id, e.environment, e.owner,
       MAX(h.observed_at) AS last_heartbeat
FROM expected_sources e
LEFT JOIN source_heartbeats h
  ON h.source_id = e.source_id
 AND h.observed_at >= TIMESTAMP '2026-11-28 08:00:00'
WHERE e.expected_enabled = TRUE
GROUP BY e.source_id, e.environment, e.owner
HAVING MAX(h.observed_at) IS NULL
    OR MAX(h.observed_at) < TIMESTAMP '2026-11-28 10:00:00';
~~~

Khi dùng thực tế, **time window phải động theo hiện tại** và theo SLA của mỗi source. Không coi toàn bộ hosts không gửi log là bị hack nếu đã decommission theo inventory.

### 30.2. Đối soát accepted và indexed theo source

~~~sql
-- Metrics đã normalize theo time buckets, không phải SQL tiêu chuẩn của OTel.
SELECT source_id, bucket_start,
       SUM(accepted_events) AS accepted,
       SUM(indexed_events) AS indexed,
       SUM(dropped_events) AS dropped
FROM normalized_pipeline_counters
WHERE bucket_start >= TIMESTAMP '2026-11-28 09:00:00'
GROUP BY source_id, bucket_start
HAVING SUM(accepted_events) >
       SUM(indexed_events) + SUM(dropped_events);
~~~

**Điểm cần thận trọng:** pipeline có batching/lag/retry/duplication, do đó so **cùng khoảng nhận và theo trạng thái đã settle**, không kết luận mất dữ liệu chỉ vì accepted > indexed trong phút hiện tại. Phải tính **in-flight queue, filter counters và event IDs**.

### 30.3. Phát hiện thay detection rules hoặc retention

~~~sql
SELECT event_time, actor_identity, action, target_resource,
       previous_version, new_version, change_id, approval_state
FROM normalized_monitoring_control_plane_audit
WHERE action IN (
  'DISABLE_DETECTION_RULE',
  'CHANGE_LOG_RETENTION',
  'DELETE_LOG_INDEX',
  'CHANGE_INGEST_FILTER',
  'UPDATE_ALERT_DESTINATION'
)
ORDER BY event_time DESC;
~~~

Chỉ trả các event **được thu thập**; nếu attacker có thể disable control-plane audit, không có row không phải bằng chứng không có thay đổi. So thêm **IaC repo, cloud activity, raw archive/independent controls**.

### 30.4. Khoảng trống bất thường trong source stream

~~~sql
SELECT source_id, stream_epoch, event_time, sequence_number
FROM normalized_source_events
WHERE source_id = 'fw-edge-lab-1'
  AND event_time >= TIMESTAMP '2026-11-28 09:00:00'
ORDER BY stream_epoch, sequence_number;
~~~

Đây mới là raw inspection query, chưa phải gap detector hoàn chỉnh. Xử lý **sequence wrap, restart epochs, sampling và out-of-order events** theo protocol trước khi kết luận.

### 30.5. Tìm những sự kiện quá hạn ingest

~~~sql
SELECT source_id, event_time, collector_received_at, indexed_at,
       pipeline_version, parse_result
FROM normalized_security_events
WHERE indexed_at > event_time + INTERVAL '10' MINUTE
  AND event_time >= TIMESTAMP '2026-11-28 08:00:00'
ORDER BY indexed_at DESC;
~~~

Không đánh đồng source clock skew với pipeline lag; so **collector_received_at → indexed_at** để ước lượng lag nội bộ và **event_time → collector_received_at** để đánh giá source/transport.

### 30.6. Những detection rules đáng ưu tiên

- **Critical source missing** hoặc packet receive zero khi uplink traffic vẫn có.
- **New/unknown ingest peer**, failed mTLS auth hoặc certificate principal bị dùng ở nhiều vị trí bất thường.
- **Logging config/retention/alert route** thay ngoài approved change.
- **Filter/drop counters** tăng bất thường sau rollout.
- **Queue oldest age/disk full/producer rejected** vượt SLO.
- **Raw archive hash/manifest** không khớp hoặc anchor không xuất hiện.
- **Rule evaluation stops** nhưng SIEM ingest vẫn bình thường.
- **Synthetic canary fails** ở một hoặc nhiều tầng.
- **SIEM read/export anomaly** hoặc storage delete attempts.
- **Time sync changes**, clock offset vượt ngưỡng.
- **Cross-sensor discrepancy**: firewall flow tăng nhưng corresponding telemetry stream biến mất.

## 31. Lệnh chẩn đoán chỉ đọc và an toàn

Chỉ thực hiện trong cluster/host/cloud scope được cấp phép. Một số lệnh trả thông tin nhạy cảm về identities, network topology, agent config và event contents; không đưa raw token, key, PCAP hoặc full logs vào ticket công khai.

### 31.1. Linux/systemd

~~~bash
# Read-only: agent/service status, không restart/disable.
systemctl status rsyslog --no-pager
systemctl is-active rsyslog

# Tùy distro và agent, thay tên service đã được phê duyệt.
journalctl -u rsyslog --since "2026-11-28 00:00:00 UTC" \
  --no-pager --output=short-iso

# Dung lượng ổ để đánh giá spool queue.
df -h

# Đồng bộ thời gian nếu systemd-timesyncd/timedatectl có mặt.
timedatectl status
~~~

### 31.2. Kubernetes

~~~bash
kubectl config current-context
kubectl get daemonsets --all-namespaces
kubectl get pods -n observability -o wide
kubectl get serviceaccounts -n observability
kubectl get configmaps -n observability
kubectl get networkpolicies -n observability
kubectl auth can-i patch configmaps -n observability

# Đọc trạng thái Pod cụ thể; thay tên thuộc scope đã duyệt.
kubectl describe pod COLLECTOR_POD_NAME -n observability
~~~

**Giới hạn:** Deployment/ConfigMap tồn tại không chứng minh data plane thực sự gửi log. Một config source đã thay nhưng Pod chưa restart có thể khiến **desired version và effective version** khác nhau. Không đọc Secrets chỉ để xem trạng thái pipeline.

### 31.3. AWS

~~~bash
aws sts get-caller-identity
aws cloudtrail describe-trails --region us-east-1
aws cloudtrail get-trail-status \
  --name EXAMPLE_TRAIL_NAME --region us-east-1

aws logs describe-log-groups --region us-east-1
aws ec2 describe-flow-logs --region us-east-1
~~~

Chọn đúng account, region và organization scope. **CloudTrail status** là một dấu hiệu của trail, không chứng minh mọi event classes/regions/data events đã được cấu hình và ingest bền.

### 31.4. Azure

~~~bash
az account show
az monitor log-analytics workspace list --resource-group example-observability-rg
az monitor activity-log list --max-events 20

# Chỉ xem resource-level diagnostic settings khi đã có Resource ID thật.
az monitor diagnostic-settings list \
  --resource EXAMPLE_RESOURCE_ID
~~~

Cấu hình Azure Monitor/Sentinel/flow log thay đổi theo loại tài nguyên và dịch vụ; xem coverage theo **subscription/resource/diagnostic category** và retention thật.

### 31.5. Google Cloud

~~~bash
gcloud config get-value project
gcloud logging sinks list --project=example-project-id
gcloud logging buckets list \
  --location=global --project=example-project-id
gcloud logging read \
  'logName:"cloudaudit.googleapis.com%2Factivity"' \
  --project=example-project-id --limit=20
~~~

Đây là lệnh điều tra không mutate resource. Nếu Cloud Logging bucket nằm ở **region khác global** thì phải chọn đúng location; không kết luận mất bucket chỉ từ một lệnh list ở global.

### 31.6. Kiểm tra mạng bằng traffic test

Chỉ dùng **test event/canary** và endpoint đã được cấp phép. Gửi syslog/OTLP packet để test ingest là **tác động network**, không phải hoàn toàn read-only; không gửi data thật hoặc mở rộng network scan. Đừng sử dụng **curl -k / --insecure** để “chữa lỗi certificate” trong security pipeline.

## 32. Runbook triển khai hệ giám sát chống can thiệp

### Bước 1 — Xác định tài sản và mục tiêu

Liệt kê **routers, switches, firewalls, VPN, IDS, DNS, Kubernetes, cloud audit, host agents, applications và SaaS**, owner, critical event classes, coverage và retention. Lập threat model về những thành phần attacker có thể thay đổi.

### Bước 2 — Thiết kế trust boundaries

Tách **source, collector, queue, processing, search index, raw archive, detection, alert và admin plane**. Xác định **ai có write, read, edit, delete, retention, mute và CI rights** tại từng tầng.

### Bước 3 — Provision identity và transport

Cấp identities riêng cho devices/agents, xác thực mTLS/certificate nếu hỗ trợ, bảo vệ keys, giới hạn ports và network paths, lập kế hoạch rotation. Với thiết bị legacy chỉ UDP plaintext, ghi control bù và provenance limitation.

### Bước 4 — Chọn định dạng, schema và processing contract

Dùng structured logs khi phù hợp, parse dữ liệu ngoài tin cậy với escapes/size limits, giữ source-authenticated metadata riêng, lưu raw copy trước transform với retention/legal requirements. Ghi parser version và drop reasons.

### Bước 5 — Thiết kế buffer và storage

Giám sát queue accepted/retried/dropped, capacity/backpressure; có immutable/raw archive, integrity proof và verify schedule, tách quyền xóa storage với ingest role. Cân nhắc disaster recovery, key retention và privacy.

### Bước 6 — Bảo vệ rules và alert destinations

Đưa configs/rules vào protected GitOps/IaC, review critical suppressions, versioned deployments, canary alert/test routes và out-of-band pipeline watchdog. Tách quyền SOC read với SIEM admin/delete.

### Bước 7 — Kiểm thử cả ngược và xuôi

- **Positive:** source hợp lệ → event đến ingest → raw archive → SIEM → detector → SOC.
- **Negative:** nguồn lạ, cert invalid, payload injection, sai tenant bị từ chối/quarantine.
- **Failure:** stop one collector, queue full, backend unavailable, rotation trust mismatch, late clock.
- **Tamper:** attempt unauthorized deletion, retention change, detector disable trong lab và verify alert.
- **Recovery:** replay/restore/drift rollback, không mất integrity evidence.

### Bước 8 — Canary rollout và SLO

Rollout source group nhỏ, so expected vs observed events, monitor p95/p99 latency, source coverage, queue age, error counters và alert delivery. Không chờ đến production incident mới thử thất bại của pipeline.

### Bước 9 — Bảo vệ vận hành

Bật periodic **access reviews, identity rotation, retention audits, rule diffs, config drift, backup restore drills, independent canaries** và giám sát vulnerability của agents/parsers.

### Bước 10 — Chứng minh production readiness

Đưa ra evidence về **nguồn, data paths, cryptographic keys/trust, immutable retention window, policy approvals, test cases, SLO, incident runbooks và known limitations**. Không nói “tamper-proof” khi chỉ có TLS hoặc admin dashboard.

## 33. Runbook ứng phó khi telemetry có dấu hiệu bị can thiệp

### Tình huống giả định

SOC thấy **firewall flow bytes vẫn tăng**, nhưng dashboard SIEM không có egress events từ firewall A trong 25 phút. Trong cùng thời gian, change audit xuất hiện một thao tác cập nhật log filter bởi admin account không thuộc change ticket.

### Giai đoạn 1 — Xác minh trạng thái và phạm vi

1. Ghi **incident ID, event_time/ingest_time, asset ID, owner, collector/PEP instance, pipeline version**.
2. Kiểm tra **firewall real traffic counters, packet sensor, flow export, collector heartbeat, queue depth, parser drop counters**.
3. Xác minh **log filter change** có approval/digest/actor/CI evidence không; không mặc định admin account thật đã tự chủ động thay.
4. Xem **other independent sources**: cloud audit, DNS resolver, VPN, network TAP và SIEM raw archive để xây timeline.
5. Kiểm tra **clock/NTP, event lag, sampling và planned maintenance** để loại trừ lý do hợp lệ.
6. Phân loại sơ bộ **sensor stopped, transport blocked, queue overflow, parser filter, storage deletion, rule/alert suppression hoặc source compromise**.

### Giai đoạn 2 — Containment có kiểm soát

- Hạn privileges của principal nghi ngờ trên **filter/config/retention/IAM**, bảo vệ signing keys và audit sinks.
- Giữ **original evidence**, snapshot cấu hình/versions theo forensic process; tránh ghi đè mất dấu vết.
- Nếu mất coverage khiến critical detection không còn, dùng **control bù**: independent sensor, temporary safe alerts, network restriction hoặc tăng monitoring tại nguồn khác.
- Đừng tắt toàn logging hoặc mở collector vô danh để phục hồi quá nhanh.
- Nếu nguy cơ log poisoning/ingest flood còn diễn ra, **quarantine source/partition** thay vì drop cả security event stream mà không có record.

### Giai đoạn 3 — Điều tra integrity

| Câu hỏi | Bằng chứng |
|---|---|
| Source đã phát những events nào? | Source spool, signed batches, flow counters, event IDs |
| Đường đi có mất dữ liệu không? | Queue/retry/drop/collector metrics, network telemetry |
| Parser có thay/suppress event không? | Protected config revision, raw vs normalized comparison |
| Storage đã bị rewrite/delete không? | Raw archive hash/signature, object version/retention audit |
| Detection có bị disable không? | Rule diff, CI, evaluation metrics, independent rule monitor |
| Có traffic exfiltration trong blind spot không? | Cloud egress, DNS, DLP, peer network sensor, app audit |

**Không thể khôi phục đầy đủ điều không bao giờ được ghi nếu thiếu nguồn đối chứng.** Ghi rõ **coverage uncertainty và time window** trong incident report, không dựng events đoán mò.

### Giai đoạn 4 — Khôi phục

1. Restore known-good config bằng protected CI, không patch trực tiếp để che change history.
2. Rotate compromised credentials/keys theo phạm vi, restore receiver certificates và authorization.
3. Khôi phục queue/backlog; replay có **dedup/source epoch** và phân biệt event_time với ingest time.
4. Compare raw archive và index; verify signed manifests/retention.
5. Chạy **synthetic canary + legitimate source test + negative auth test**.
6. Đảm bảo alert đến SOC qua primary và out-of-band paths.
7. Giữ monitored guardrails sau khôi phục, hoàn thành post-incident remediation.

### Giai đoạn 5 — Hậu kiểm

Đánh giá **TTP, root cause, affected data classes, attack duration, events lost vs delayed, visibility gaps, detection delay, human decision timeline, policy/SoD failings**. Bổ sung tests và controls, phân biệt **confirmed tampering** với uncertainty.

## 34. Runbook bảo toàn và xác minh bằng chứng số

### 34.1. Phạm vi chứng cứ

Một cuộc điều tra có thể cần **raw syslog, flow export, PCAP, cloud API audit, raw object versions, CI diffs, SIEM query results, alert history và event processing configs**. Không lấy bằng chứng ngoài thẩm quyền, không copy unrestricted packets/logs vào kênh cộng tác công khai.

### 34.2. Chuỗi xử lý

1. **Identify:** ghi nguồn, custodian, hệ thống, asset ID, thời gian, mức nhạy cảm.
2. **Acquire:** lấy **read-only export/snapshot** theo procedure; tránh làm thay đổi nguồn, ghi tool/version.
3. **Hash:** tính cryptographic digest trên **bytes gốc** và bảo vệ digest/manifest bên ngoài nơi attacker có thể sửa.
4. **Preserve:** lưu bản gốc trong archive có retention phù hợp, hạn quyền delete/overwrite và quản lý keys.
5. **Document:** ghi **UTC timestamp, identity thao tác, reason, system state, file size/hash, transfer path**.
6. **Analyze on copies:** chạy parser/normalization trên bản sao, không sửa original.
7. **Verify:** trước và sau chuyển giao, so hashes/signatures, signed anchors, storage versions khi có.
8. **Report:** tách findings, evidence, assumptions và known blind spots.
9. **Retain/dispose:** theo chính sách bảo mật, quyền riêng tư và legal hold nếu áp dụng.

### 34.3. Ví dụ manifest chứng cứ — mẫu logic

~~~json
{
  "evidence_id": "EVID-DEMO-102",
  "incident_id": "INC-DEMO-009",
  "source_system": "syslog-archive-prod-a",
  "capture_window_start": "2026-11-28T10:00:00Z",
  "capture_window_end": "2026-11-28T11:00:00Z",
  "artifact_name": "firewall-events-demo.raw",
  "byte_length": 1048576,
  "hash_algorithm": "SHA-256",
  "sha256_digest": "EXAMPLE_REPLACE_WITH_COMPUTED_DIGEST",
  "acquired_by": "forensic-analyst-1",
  "acquired_at": "2026-11-28T11:15:00Z",
  "original_storage": "protected-raw-archive",
  "evidence_storage": "separate-security-account",
  "signature_status": "PENDING_VERIFICATION",
  "chain_of_custody_record": "COC-DEMO-102"
}
~~~

**Không dùng các giá trị demo như bằng chứng thật**. Hash phải được tính từ bytes thật bằng công cụ đã được duyệt, còn chain-of-custody phải có người xác nhận/giao nhận và logging.

### 34.4. Khả năng kiểm chứng và giới hạn

Một hash trùng khớp chỉ cho biết bytes không đổi so với **digest tham chiếu tin cậy**; nó không chứng minh log chứa đủ sự kiện hoặc sensor chưa bị xâm nhập. Kết luận điều tra nên dựa trên **đa nguồn, metadata provenance, cryptographic integrity và quy trình lưu giữ**.

## 35. Mười hai tình huống thực tế

### A — Đăng nhập thành công nhưng cloud audit mất đột ngột

**Triệu chứng:** cloud IAM/admin activity vẫn tăng, nhưng security archive không còn nhận control-plane audit events từ một project/account.

**Khả năng:** audit sink/selector thay, credentials của exporter hết hạn, resource coverage thiếu, pipeline backlog hoặc actor cố tình tắt log.

**Xử lý:** so **cloud control-plane audit configuration, organization guardrails, collector/queue, raw archive và inventory**; dùng out-of-band alert, giữ evidence config changes. Không tự kết luận an toàn vì SIEM không có failed login events.

### B — Firewall gửi syslog nhưng HOSTNAME là thiết bị khác

**Triệu chứng:** TLS sender certificate thuộc **fw-branch-17**, payload syslog claim **fw-core-1**.

**Nguyên nhân có thể:** thiết bị đổi hostname nhưng registry chưa cập nhật, relay gom logs, hoặc một thiết bị/credential bị compromise.

**Xử lý:** giữ **authenticated peer principal và claimed hostname** thành hai fields, flag mismatch, tra inventory/relay mapping và policy; không silently sửa cả hai thành cùng identity.

### C — SPAN capture rơi packet khi traffic peak

**Triệu chứng:** IDS thấy ít packets/alerts đúng lúc network throughput tăng; switch SPAN oversubscribed.

**Giải thích:** sensor không còn nhìn đủ traffic. Bổ sung **mirror counters, capture drop metrics, capacity planning, TAP/alternate vantage points**, không báo "không có IDS alerts nghĩa là clean".

### D — Agent heartbeat đều nhưng thiếu security events

**Triệu chứng:** host agent process healthy và heartbeat tới collector, nhưng không có process execution events.

**Nguyên nhân:** agent logging level/filter disabled, kernel hook attach lỗi hoặc audit policy changed.

**Xử lý:** canary event đúng class, compare config hash/effective policy, host counters và independent EDR/cloud audit; heartbeat một mình không đạt coverage.

### E — Attacker gửi hàng loạt requests làm SIEM queue tràn

**Triệu chứng:** WAF logs tăng 100 lần, queue oldest age tăng, ingest delay khiến privileged IAM event bị phát hiện muộn.

**Giải pháp:** quotas theo authenticated source, critical audit channel riêng, bounded retry/durable spool, alert drop/backlog và cost; không drop toàn bộ nguồn WAF mà không ghi coverage loss.

### F — Detection rule bị đổi ngưỡng im lặng

**Triệu chứng:** dữ liệu DNS/firewall bình thường nhưng rule phát hiện exfiltration threshold bị tăng mạnh và alert hết xuất hiện.

**Xử lý:** kiểm tra **Git diff, CI approval, SIEM rule version/evaluation metrics, independent rule watchdog**, synthetic tests và rollback known-good rule. Không chỉ chạy lại query trên index hiện tại.

### G — Cloud logging bucket có retention nhưng admin vẫn xóa được

**Triệu chứng:** nhóm ứng dụng có quyền sửa hoặc delete objects do cấu hình **governance bypass** hoặc không có retention lock thực.

**Giải thích:** tên bucket “immutable” hoặc bật versioning không chứng minh WORM. Review **effective retention mode, bypass permissions, object versions, KMS access và cross-account copy**; test xóa **trên dummy objects** có phép, không thử xóa evidence production.

### H — Một hash manifest trùng khớp nhưng nguồn event sai

**Triệu chứng:** file archive có chữ ký đúng, song sensor bị compromise đã gửi event gian.

**Giải thích:** tính toàn vẹn storage chỉ xác nhận bytes được giữ; không xác minh mọi quan sát ở nguồn là thật. Đối chiếu **TAP, independent DNS/cloud audit, device runtime/agent integrity** và ghi uncertainty.

### I — Time sync bị đổi làm SOC timeline đảo thứ tự

**Triệu chứng:** nhiều firewall logs có event_time chạy ngược 15 phút so với collector_received_at.

**Nguyên nhân:** NTP misconfiguration, timezone, clock manipulation hoặc replay.

**Xử lý:** giữ **cả source và ingest timestamps**, xem clock offset và changes, correlation bằng sequence, broker time và independent audit; không overwrite original timestamp mất dấu.

### J — Không gửi được telemetry sau certificate rotation

**Triệu chứng:** agents vẫn tạo events, nhưng ingest gateway từ chối mTLS do trust bundle chưa rollout đồng đều.

**Xử lý:** xem cert expiry/issuer, SAN/trust domain, collector endpoint, agent queue; staged **trust overlap và cert rotation** có canary. **Không disable TLS verification** để đưa data vào bằng mọi giá.

### K — Một Kubernetes collector bị cấp cluster-admin

**Triệu chứng:** DaemonSet collector có SA cluster-admin và privileged hostPath, dù chỉ cần đọc Pod metadata/logs.

**Rủi ro:** collector compromise có thể sửa resources, đọc secrets hoặc phá monitoring/control plane.

**Xử lý:** giảm RBAC theo API groups/resources/verbs, limit mounts/capabilities, protect images/SA, tách control-plane audit khỏi collector; thử permissions trong staging và xem functional coverage.

### L — Xóa index và tắt notification cùng một lúc

**Triệu chứng:** một admin account đổi index lifecycle, xóa SIEM index cũ, rồi chỉnh action group/webhook thông báo.

**Phân tích:** đây là **control-plane tamper chain** đáng ưu tiên. Dùng **independent cloud audit/CI logs**, raw WORM archive, alert config audit và incident containment. Nếu raw archive giữ nguyên, có thể replay/rebuild index sau khi bảo toàn evidence; nếu không, phải báo rõ missing evidence window.

## 36. Ma trận 50 kiểm thử bảo vệ telemetry

**Phạm vi an toàn:** chỉ chạy trên lab, sandbox, namespace hoặc source được cấp phép. Synthetic events phải vô hại, không chứa user data/credentials thực; không thử xóa log chứng cứ production, flood hệ giám sát hoặc tắt security agents trên máy người khác.

| ID | Kịch bản | Kết quả mong đợi | Bằng chứng |
|---|---|---|---|
| **T-01** | Agent đúng mTLS certificate kết nối ingest | ALLOW đúng source/stream | Peer identity, ingest metrics |
| **T-02** | Source không có credential gửi event | DENY/quarantine | Ingest auth failure |
| **T-03** | Certificate từ CA không tin | DENY handshake | TLS trust error |
| **T-04** | Certificate có SAN không match registered principal | DENY/flag identity mismatch | Peer auth log |
| **T-05** | Certificate hết hiệu lực trong lab | DENY new connection | Expiry error |
| **T-06** | Rotation CA với overlap đúng | Canaries và ingest liên tục | Agent/collector TLS |
| **T-07** | mTLS source claim syslog HOSTNAME khác peer | Quarantine/flag, giữ both fields | Source registry check |
| **T-08** | Replay event ID trong same source epoch | Nhận diện duplicate theo policy | Event ID/dedup status |
| **T-09** | Sự kiện có newline giả event line | Escape/parse, không ghi fake event | Raw vs normalized |
| **T-10** | JSON có duplicate security-critical keys | Reject/quarantine theo schema | Parser validation |
| **T-11** | Event payload vượt size limit | Bounded rejection, alert; không crash parser | Ingest error counter |
| **T-12** | Parser nhận malformed encoding | Quarantine với safe metadata | Parse error log |
| **T-13** | Enrichment source không có authority | Không ghi đè authenticated peer ID | Provenance check |
| **T-14** | Agent stopped trong lab | Missing-heartbeat alert | Watchdog |
| **T-15** | Agent còn heartbeat nhưng tắt một event class | Canary/class-coverage fail | Synthetic event |
| **T-16** | SPAN mirror port cấu hình sai ở lab | Packet counter discrepancy detected | Switch/sensor counters |
| **T-17** | TAP/sensor RX drops tăng | Alert drop rate/capacity | NIC/sensor counters |
| **T-18** | Flow exporter reboot sequence reset | Epoch-aware analysis, không false tamper | Exporter lifecycle |
| **T-19** | Thử thiếu sequence event theo policy lab | Gap detection có xét sampling | Source sequence audit |
| **T-20** | NTP drift vượt threshold | Clock alert, giữ nguyên event_time | Clock/ingest timestamps |
| **T-21** | Collector TLS outage | Agent buffers/retries và outage alert | Queue/TLS errors |
| **T-22** | Collector restart trong lab | Recovery và event reconciliation | Agent/collector counters |
| **T-23** | Broker partition unavailable | Alert backlog, reliable retry theo design | Queue metrics |
| **T-24** | Queue disk gần đầy | Early alert, không silent loss | Disk/oldest age |
| **T-25** | Poison malformed event trong queue | Bounded retry/quarantine | Dead-letter/retry count |
| **T-26** | Exporter backend trả permission denied | Failure alert, event buffering theo design | Exporter errors |
| **T-27** | SIEM index lag cao hơn SLO | Detect lag và escalation | Received vs indexed timestamps |
| **T-28** | Filter rule mới drop security-critical class | CI test/review hoặc watchdog catches | Config diff/drop counters |
| **T-29** | Sensor bị tháo khỏi asset inventory không có approval | Detect inventory/coverage drift | CMDB/change audit |
| **T-30** | Privileged account attempt change retention | DENY without authorized role | IAM policy/audit |
| **T-31** | Attempt delete protected archive test object | DENY theo retention mode | Storage audit |
| **T-32** | Governance bypass role trong lab | Detected/blocked theo organizational guardrail | Effective IAM check |
| **T-33** | Raw archive bytes bị đổi trong sandbox | Hash/signature mismatch alert | Integrity verification |
| **T-34** | Hash cùng nơi lưu bị thay cùng dữ liệu | External anchor reveals mismatch | Independent manifest |
| **T-35** | Validly signed but false event từ compromised lab source | Cross-source mismatch detected/investigated | Independent sensor |
| **T-36** | Attempt unauthenticated SIEM search | DENY | Search auth log |
| **T-37** | Analyst role attempt delete index | DENY | Role/API audit |
| **T-38** | Operator disable critical detection outside CI | DENY/alert | Rule-change audit |
| **T-39** | Approved rule change trong canary | Rule version và synthetic tests pass | CI + rule metadata |
| **T-40** | Expired alert mute vẫn active | Watchdog alert và restore | Silence inventory |
| **T-41** | Alert notification webhook broken in lab | Independent canary detects delivery gap | Pager receipt |
| **T-42** | SIEM offline nhưng pipeline watchdog hoạt động | Out-of-band alert delivered | Secondary monitoring |
| **T-43** | Primary SIEM + shared IAM outage | Runbook xác nhận remaining coverage/limitations | Tabletop evidence |
| **T-44** | Telemetry ingest flood giới hạn trong sandbox | Quota/backpressure, critical path protected | Load test metrics |
| **T-45** | Metrics label cardinality spike synthetic | Budget guardrail/cost alert | TSDB metrics |
| **T-46** | Kubernetes Collector SA yêu cầu Secrets ngoài scope | DENY | kubectl auth can-i/audit |
| **T-47** | Kubernetes audit rule bỏ event PATCH quan trọng trong lab | Policy test detects missing class | Audit canary |
| **T-48** | Cloud account mới chưa có audit sink | Inventory coverage detects missing source | Account/sink reconciliation |
| **T-49** | Replay raw archive vào index staging | Dedup/ordering and lineage correct | Rebuild report |
| **T-50** | Restore collector/rule config after simulated compromise | Legit events and negative tests both PASS | Runbook + canary + audit |

### 36.1. Kiểm thử ALLOW, DENY, DETECT và RECOVER

- **ALLOW:** agent hợp lệ gửi event, index/search/detection nhận đủ class theo sampling policy.
- **DENY:** nguồn lạ, credential sai, role quá quyền, attempt delete archive bị từ chối.
- **DETECT:** tampered raw bytes, log gap, rule disable, queue drop, alert delivery failure có cảnh báo.
- **RECOVER:** restore config, replay queue/archive an toàn, rotate identity, verify coverage và alert channels.

Một bài test chỉ nhìn **HTTP 200/ACK** ở ingest chưa chứng minh event đã đến archive và detector; theo dõi **end-to-end canary ID** qua mọi tầng.

### 36.2. Phải kiểm tra cả positive và negative

Nếu unknown sender bị DENY nhưng authorized devices cũng không gửi được sau CA rotation thì hệ thống chưa đạt availability. Nếu authorized agent gửi được nhưng một untrusted client cũng gửi fake HOSTNAME, authenticity chưa đạt. Cần cả **positive/negative tests**.

### 36.3. Không biến thử nghiệm thành xóa chứng cứ

Tamper tests chỉ nên làm trên **dummy objects/log events, test-only SIEM indices, sandbox cloud resources, synthetic alert rules**, có owner và rollback. Không dùng evidence thật hoặc làm ngừng production network security logging để chứng minh một mô hình.

## 37. Những ngộ nhận thường gặp

| Ngộ nhận | Cách hiểu đúng |
|---|---|
| **“Có SIEM nghĩa là không thể che dấu tấn công.”** | Sensor, agent, collector, pipeline, storage và detection đều có thể bị làm mù. |
| **“Không có alert nghĩa không có attack.”** | Rule bị tắt, nguồn mất hoặc alert channel lỗi có thể làm im lặng. |
| **“mTLS làm log thành sự thật.”** | mTLS xác thực kênh/peer, không chữa source đã bị compromise. |
| **“Syslog HOSTNAME là identity đã được chứng thực.”** | Đây là payload claim, cần peer identity/registry match. |
| **“TCP tự bảo đảm SIEM đã lưu mọi event.”** | TCP truyền bytes, không bảo đảm durable end-to-end indexing. |
| **“TLS biến storage thành immutable.”** | TLS bảo vệ hop, không chặn xóa/sửa sau ingest. |
| **“SHA-256 cạnh file đủ chống tamper.”** | Attacker có thể thay cả file và digest nếu cùng quyền. |
| **“Signed log chứng minh không có event thiếu.”** | Chữ ký chỉ xác minh nội dung đã ký; source suppression vẫn có thể xảy ra. |
| **“Một hash chain không cần trusted anchor.”** | Rewrite cả chain có thể không phát hiện nếu không có anchor ngoài trust domain. |
| **“WORM chứng minh nội dung log đúng.”** | WORM bảo vệ dữ liệu đã nhận, không bảo đảm sensor quan sát trung thực. |
| **“Bật bucket versioning bằng compliance immutability.”** | Retention lock/mode/permissions cần được xác minh riêng. |
| **“Admin cloud/root không thể ảnh hưởng telemetry.”** | Control plane, KMS, policy hoặc source coverage vẫn có risk rất lớn. |
| **“Một backup là đủ bằng chứng pháp lý.”** | Cần provenance, chain-of-custody, integrity và quyền lưu giữ. |
| **“Agent healthy nghĩa thu đủ mọi events.”** | Agent có thể không hook đúng event class/capture filter. |
| **“SPAN mirror luôn có đủ 100% traffic.”** | Oversubscription, topology và configuration có thể drop/miss packets. |
| **“Flow records là PCAP đầy đủ.”** | Flow logs thường là metadata, có sampling/aggregation. |
| **“Số sequence tăng nghĩa không hề mất dữ liệu.”** | Protocol/reset/sampling và receiver gaps cần phân tích. |
| **“Mọi duplicate là tấn công replay.”** | Retries at-least-once cũng sinh duplicates hợp lệ. |
| **“Log timestamp của endpoint luôn chính xác.”** | Source clock có thể sai hoặc bị thao túng; giữ ingest time. |
| **“Một event có thời gian lùi là giả.”** | NTP correction và delayed export có thể gây lệch hợp lệ. |
| **“Packet count giảm chắc đã có sabotage.”** | Sampling, giảm traffic và maintenance có thể hợp lý. |
| **“OTel Collector tự có immutable logs.”** | Collector nhận/xử lý/export; storage integrity cần thiết kế riêng. |
| **“Processor filter là chuyện hiệu năng, không cần security review.”** | Filter có thể loại events liên quan incident/detection. |
| **“Sửa parser không thể ảnh hưởng điều tra.”** | Parser poisoning/schema mismatch có thể che hoặc giả events. |
| **“Một JSON có duplicate keys luôn được parse như nhau.”** | Parsers có thể first-wins/last-wins khác nhau. |
| **“Nhiều logs hơn luôn an toàn hơn.”** | Flood/cardinality có thể phá availability và privacy. |
| **“Sampling không ảnh hưởng forensic.”** | Sampling có thể bỏ qua events hiếm; phải document tỷ lệ/coverage. |
| **“Queue có retry nghĩa không mất log.”** | Retry/disk capacity/ack semantics và poison messages vẫn quan trọng. |
| **“Detection rule enabled nghĩa nó đang đánh giá tốt.”** | Rule query/source/status và synthetic evaluation phải được kiểm tra. |
| **“Một alert đã tạo là SOC đã nhận.”** | Webhook/pager/e-mail có thể lỗi; phải test delivery. |
| **“Vùng monitoring riêng có nghĩa mọi user trong đó đều được tin.”** | Cần IAM/mTLS/least privilege ngay bên trong monitoring network. |
| **“Kubernetes audit tương đương container stdout.”** | API Server audit khác app logs/host events. |
| **“Collector có quyền cluster-admin là bình thường.”** | Chỉ cấp đúng quyền cần; privileged agent là bề mặt compromise lớn. |
| **“CloudTrail hay Cloud Audit Logs mặc định ghi mọi event.”** | Coverage, event category và exclusions khác nhau theo cấu hình. |
| **“Không có raw archive vẫn có thể chứng minh event không bị sửa.”** | Chỉ index mutable khó có original evidence; cần integrity architecture. |
| **“Bảo vệ logs chỉ là việc của SOC.”** | Platform, IAM, NetSec, SRE, app teams và data governance đều có trách nhiệm. |

## 38. Checklist production cho hệ giám sát chống can thiệp

- [ ] Có inventory nguồn telemetry, owner, region/account/cluster và event classes quan trọng.
- [ ] Có sơ đồ trust boundaries sensor → collector → queue → parse → store → alert.
- [ ] Có baseline expected source/heartbeat/counters và asset lifecycle.
- [ ] Sensor/TAP/SPAN placement bao phủ đúng VLAN, interface, direction và traffic path.
- [ ] Giám sát packet drops, exporter restarts, sequence gaps và sampling configurations.
- [ ] Agent binaries/images được quản lý version, provenance và patching.
- [ ] Agent/service account chỉ có permissions cần thiết, không mặc định root/cluster-admin.
- [ ] HostPath, kernel/eBPF privileges, runtime mounts và secrets được bảo vệ.
- [ ] Mỗi nguồn có authenticated sender identity phù hợp; không dùng chung API key rộng khi tránh được.
- [ ] Collector xác minh certificate chain, SAN/trust domain/issuer và source entitlement.
- [ ] Có cert rotation và trust-bundle rollover đã kiểm thử.
- [ ] Các nguồn chỉ dùng syslog UDP/TCP plaintext được ghi rõ limitation và control bù.
- [ ] Network ingress đến collector nằm trong segmentation và allowlists cần thiết.
- [ ] Monitoring admin APIs không public/untrusted reachable.
- [ ] Agent egress chỉ mở tới approved endpoints và update channels.
- [ ] Collector không dùng payload hostname/user headers làm verified principal.
- [ ] Có schema validation, escape control chars, reject/quarantine duplicate security keys.
- [ ] Raw original event được giữ trong phạm vi phù hợp trước transform/parse.
- [ ] Parser/enrichment/filter versions được ghi và bảo vệ thay đổi qua CI.
- [ ] Pipeline có per-source accepted/rejected/dropped counters với reason.
- [ ] Queue/broker có TLS/auth, stream ACL, durable capacity và replay plan.
- [ ] Queue disk/oldest age/retries/dead-letter/poison events được monitor.
- [ ] Critical audit events không bị silent sampling/drop để giảm chi phí.
- [ ] OTel/agent resource attributes không được xem là authenticated identity nếu client tự khai.
- [ ] SIEM index lifecycle/retention/xóa dữ liệu chỉ do roles có quyền đã được duyệt.
- [ ] Có raw archive immutable/retention lock với mode và bypass permissions đã review.
- [ ] Root/issuer/KMS/signing keys có lifecycle, least privilege và backup/recovery.
- [ ] Hash/digital signatures/manifest được anchored ngoài cùng trust boundary khi cần.
- [ ] Integrity verifier có alert khi mismatch, thiếu batch hoặc signed anchor.
- [ ] Dữ liệu log được mã hóa ở storage/transfer, truy cập search/export có audit.
- [ ] Logs được redaction và data minimization, không lưu keys/tokens/raw PII thừa.
- [ ] Retention phù hợp security, legal, privacy, incident preservation và dispose rules.
- [ ] Cloud audit/log sinks được enable đúng account/project/subscription/region.
- [ ] Cloud audit policy/exclusion/filter/retention changes được giám sát từ boundary độc lập.
- [ ] Kubernetes API audit và application/container/host logs được phân biệt.
- [ ] Kubernetes collectors có scoped RBAC, securityContext, safe mounts và CNI rules.
- [ ] Detections có rule owner, policy version, tested query và evaluation health.
- [ ] Critical rule disables/threshold edits/mutes cần approval và independent change audit.
- [ ] Alert webhooks/pagers/action groups được bảo vệ và có synthetic delivery checks.
- [ ] Có source heartbeat và **event-class coverage**; heartbeat không được tính thay log events.
- [ ] Có synthetic end-to-end canary đến raw archive, index, detector và SOC channel.
- [ ] Telemetry watchdog có kênh cảnh báo ngoài primary pipeline.
- [ ] Metrics ingestion age, index lag, lost queue batches và alert latency có SLO.
- [ ] Event_time, collector_received_at, indexed_at được giữ riêng, kiểm soát NTP/clock offset.
- [ ] Có detection unauthorized ingest peer, retention changes, rule suppression, logging gaps.
- [ ] Có multi-source cross checks (DNS, firewall, cloud audit, packet sensors) để phát hiện source fraud.
- [ ] Có data integrity/retention và access review định kỳ, chứng minh config effective.
- [ ] Có negative tests unauthorized sender, parser poisoning, delete attempts và rule disable.
- [ ] Có load tests queue/backpressure và failure-mode tests trong lab.
- [ ] Có rollback collector/parser/detection rules và replay/dedup recovery test.
- [ ] Có incident runbook giữ original evidence, hash/manifest, chain-of-custody.
- [ ] Break-glass access ngắn hạn, đầy đủ audit và post-review.
- [ ] Không tuyên bố “tamper-proof” nếu chỉ có TLS, hash tự lưu, backup hoặc SIEM dashboard.

## 39. Câu hỏi tự kiểm tra

**1. Vì sao hệ giám sát cần được bảo vệ như một tài sản nhạy cảm?**  
Vì nó có thể chứa dữ liệu cá nhân/topology/secrets và là nơi attacker muốn che dấu truy cập, thay cảnh báo hoặc xóa bằng chứng.

**2. mTLS giữa agent và collector chứng minh được gì?**  
Kênh/peer được xác thực theo chứng thư và giảm nguy cơ MITM trên hop được bảo vệ; không chứng minh event sinh ra từ host compromise là trung thực.

**3. Vì sao syslog HOSTNAME không phải identity đáng tin?**  
Đó là một trường do sender khai; cần giữ riêng peer identity từ TLS/registry và payload claim.

**4. Sự khác nhau giữa WORM và digital signature?**  
WORM giới hạn sửa/xóa storage theo retention mode; signature xác minh nội dung đã ký và signer key. Cả hai không bảo đảm nguồn quan sát đủ/đúng.

**5. Hash file lưu cùng file có đủ chống giả mạo?**  
Không nếu attacker có thể sửa cả hai. Phải có digest anchor/signature/manifest được bảo vệ độc lập.

**6. Tại sao hash chain cần external anchor?**  
Nếu attacker sửa cả chuỗi và các hash nội bộ thì chain mới vẫn nhất quán; trusted anchor bên ngoài giúp phát hiện rewrite.

**7. Vì sao heartbeat Agent Healthy chưa đủ?**  
Agent có thể không collect critical event class hoặc parser drop mọi auth events; cần canary và counters/independent source comparison.

**8. SPAN/TAP khác flow logs như thế nào?**  
SPAN/TAP sao chép packet traffic theo cấu hình; flow logs/IPFIX tổng hợp metadata/flows và có thể sampled, không phải PCAP đầy đủ.

**9. Hệ metrics bị cardinality flood như thế nào?**  
Labels chứa user/request IDs ngẫu nhiên tạo hàng triệu time series; cần bounded dimensions và quota.

**10. Vì sao accepted_events không luôn bằng indexed_events tại cùng phút?**  
Có batching, retries, queue in-flight, sampling/filters và duplicates; phải đối soát theo settled window và event identity.

**11. Khi timestamp nguồn đi ngược, có luôn là giả mạo không?**  
Không. NTP correction, timezone parsing, delayed export cũng gây lệch; giữ source time, ingest time và clock state.

**12. Vì sao kiểm tra signed log chưa đủ kết luận không có events bị bỏ?**  
Ký chứng minh nội dung đã ký; source có thể không tạo/gửi event ngay từ đầu hoặc lọc trước ký.

**13. Làm sao bảo vệ SIEM rule khỏi bị tắt âm thầm?**  
Protected CI/approval, rule version/desired-state diff, watchdog rule evaluation và out-of-band alert.

**14. Nếu SIEM down, hệ thống phát hiện mất giám sát bằng cách nào?**  
Dùng pipeline watchdog/canary và secondary alerting channel không phụ thuộc hoàn toàn vào chính SIEM.

**15. Vì sao quyền delete raw archive không nên thuộc agent gửi logs?**  
Agent compromise có thể xóa dấu vết của chính mình; tách append-only ingest với retention/delete/admin roles.

**16. Một collector Kubernetes cần cluster-admin không?**  
Thông thường phải xác định đúng quyền từng chức năng; không cấp cluster-admin nếu chỉ cần Pod metadata và đọc host logs.

**17. Khi thấy một DNS log gap, phải điều tra điều gì trước?**  
Nguồn, resolver/caching, sampling, exporter health, queue, parser, clock và planned maintenance; đối chiếu flow/cloud audit để tránh kết luận sớm.

**18. Bảo toàn chứng cứ số cần những gì ngoài SHA-256?**  
Original bytes, trusted source/ownership, protected digest, acquisition timestamp/tool, transfer/access history, storage controls và chain-of-custody.

**19. Tình huống một SIEM index bị xóa nhưng raw WORM archive còn, phải làm gì?**  
Bảo toàn audit evidence, xác minh integrity của archive, khôi phục known-good parser/rules và replay/rebuild trên hệ an toàn theo incident plan.

**20. Bộ kiểm thử tối thiểu để nói telemetry được bảo vệ?**  
Agent hợp lệ ALLOW, source giả DENY, tampering/delete/rule disable DETECT, outage pipeline ALERT, recovery/replay PASS và canary đầu-cuối tới SOC.

## 40. Tài liệu tham khảo

- [NIST SP 800-92 — Guide to Computer Security Log Management](https://csrc.nist.gov/pubs/sp/800/92/final): kiến trúc thu thập/lưu trữ/kiểm soát nhật ký bảo mật.
- [NIST SP 800-53 Rev. 5 — Security and Privacy Controls](https://csrc.nist.gov/pubs/sp/800/53/r5/upd1/final): AU (Audit and Accountability), SI (System and Information Integrity), AC (Access Control), CM (Configuration Management).
- [NIST SP 800-86 — Guide to Integrating Forensic Techniques into Incident Response](https://csrc.nist.gov/pubs/sp/800/86/final): quy trình bảo toàn/đánh giá chứng cứ số.
- [NIST SP 800-61 Rev. 3 — Incident Response Recommendations and Considerations](https://csrc.nist.gov/pubs/sp/800/61/r3/final): phát hiện, ứng phó và cải thiện sau sự cố.
- [NIST SP 800-207 — Zero Trust Architecture](https://csrc.nist.gov/pubs/sp/800/207/final): phân quyền dựa trên identity và kiểm tra liên tục.
- [RFC 5424 — The Syslog Protocol](https://www.rfc-editor.org/rfc/rfc5424): cấu trúc syslog messages.
- [RFC 5425 — Transport Layer Security (TLS) Transport Mapping for Syslog](https://www.rfc-editor.org/rfc/rfc5425): bảo mật syslog trên TLS.
- [RFC 5848 — Signed Syslog Messages](https://www.rfc-editor.org/rfc/rfc5848): signing và tính toàn vẹn/nguồn gốc syslog.
- [RFC 6587 — Transmission of Syslog Messages over TCP](https://www.rfc-editor.org/rfc/rfc6587): legacy syslog TCP framing, không thay TLS.
- [RFC 3161 — Internet X.509 Public Key Infrastructure Time-Stamp Protocol](https://www.rfc-editor.org/rfc/rfc3161): trusted timestamping khi cần bằng chứng thời gian.
- [RFC 3339 — Date and Time on the Internet](https://www.rfc-editor.org/rfc/rfc3339): timestamp representations.
- [OpenTelemetry Collector](https://opentelemetry.io/docs/collector/): receivers, processors, exporters, configuration và collector observability.
- [OpenTelemetry Security](https://opentelemetry.io/docs/security/): bảo mật telemetry pipelines và triển khai.
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): log injection, bảo vệ log, event field design, privacy và integrity.
- [OWASP Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html): credentials/keys trong systems và logs.
- [MITRE ATT&CK — Impair Defenses (T1562)](https://attack.mitre.org/techniques/T1562/): hành vi tắt/sửa hệ thống phòng vệ và giám sát.
- [MITRE ATT&CK — Indicator Removal (T1070)](https://attack.mitre.org/techniques/T1070/): xóa hoặc thay bằng chứng hoạt động.
- [MITRE ATT&CK — Disable or Modify Cloud Logs (T1562.008)](https://attack.mitre.org/techniques/T1562/008/): can thiệp cloud logging.
- [Kubernetes — Auditing](https://kubernetes.io/docs/tasks/debug/debug-cluster/audit/): Kubernetes API audit policy và backends.
- [Kubernetes — RBAC Good Practices](https://kubernetes.io/docs/concepts/security/rbac-good-practices/): giảm đặc quyền của agents và admin.
- [Kubernetes — NetworkPolicy](https://kubernetes.io/docs/concepts/services-networking/network-policies/): hạn nguồn/đường collector và egress agents.
- [AWS CloudTrail User Guide](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/cloudtrail-user-guide.html): audit coverage/organization trails và logging status.
- [AWS S3 Object Lock](https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lock.html): retention, legal hold, governance/compliance modes.
- [AWS VPC Flow Logs](https://docs.aws.amazon.com/vpc/latest/userguide/flow-logs.html): network metadata visibility và limitations.
- [Azure Monitor documentation](https://learn.microsoft.com/en-us/azure/azure-monitor/): diagnostic settings, logs, metrics, alerts và retention.
- [Microsoft Sentinel documentation](https://learn.microsoft.com/en-us/azure/sentinel/): detection/content management và security operations.
- [Google Cloud Audit Logs](https://cloud.google.com/logging/docs/audit): control-plane audit types và scopes.
- [Google Cloud Logging sinks](https://cloud.google.com/logging/docs/export): router/sink management và destination configuration.
- [Google Cloud VPC Flow Logs](https://cloud.google.com/vpc/docs/using-flow-logs): quan sát flow metadata và sampling.
- [CIS Controls v8](https://www.cisecurity.org/controls/v8): control families liên quan log management, defense và monitoring.

**Ghi nhớ:** Hệ thống giám sát chỉ đáng tin trong **phạm vi quan sát, danh tính nguồn, tính toàn vẹn, độ mới và độ sẵn sàng đã được kiểm chứng**. Bảo vệ **sensor/agent và cấu hình capture**, xác thực/mã hóa **kênh ingest**, theo dõi **queue/filter/drop**, lưu **raw evidence có chống sửa/xóa và bằng chứng integrity ngoài cùng miền tin cậy**, tách quyền **ingest–search–delete–detection–admin**, đồng thời đo **source coverage, canary end-to-end, rule health và alert delivery**. Một **file có chữ ký đúng, bucket immutable hoặc SIEM không có alert không bao giờ đủ để chứng minh nguồn log trung thực, đầy đủ và không bị làm mù**. Luôn có **runbook điều tra, bảo toàn chứng cứ và phục hồi** với các kiểm thử **ALLOW/DENY/DETECT/RECOVER**.




