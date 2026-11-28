# Security monitoring: Giám sát bảo mật và chứng minh khả năng phát hiện

## Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích **security monitoring** và phân biệt nó với logging, performance monitoring, security detection, incident response và security assurance.
2. Lựa chọn sự kiện, tín hiệu và phạm vi quan sát dựa trên tài sản, mối đe dọa và ranh giới tin cậy của hệ thống.
3. Thiết kế pipeline thu thập, chuẩn hóa, bảo vệ, lưu trữ, phân tích và cảnh báo có thể kiểm tra chất lượng.
4. Tạo một **detection use case** với giả thuyết, điều kiện phát hiện, độ nghiêm trọng, ngoại lệ, phản ứng và kiểm thử dương tính/âm tính.
5. Đánh giá tính đầy đủ, hiệu lực và độ tin cậy của chương trình monitoring bằng các chỉ số và bằng chứng tái lập được.
6. Kết nối giám sát liên tục với điều tra sự cố, quản lý phát hiện, khắc phục và tái đánh giá rủi ro.

## 1. Security monitoring giải quyết vấn đề gì?

**Security monitoring** là hoạt động liên tục thu thập, kiểm tra, tương quan và đánh giá dữ liệu phản ánh hành vi, trạng thái cấu hình và sự kiện có ý nghĩa bảo mật; từ đó phát hiện dấu hiệu bất thường, vi phạm chính sách hoặc hành vi tấn công để hỗ trợ phản ứng kịp thời.

Một ứng dụng có thể đã vượt qua kiểm thử bảo mật trước khi triển khai nhưng sau đó vẫn bị lạm dụng token, thay đổi quyền, quét cổng hoặc cấu hình sai. Security monitoring giúp phát hiện những thay đổi và hành vi xảy ra **trong vận hành**.

Trong mô-đun **SECURITY_SECURITY_ASSURANCE**, giám sát bảo mật đóng vai trò kiểm tra liên tục xem hệ thống có còn đáp ứng các mục tiêu bảo mật hay không. Nó liên kết **phân tích rủi ro → security requirements → controls → kiểm thử → audit → phát hiện → khắc phục → xác minh lại**. Tuy nhiên, chỉ có dữ liệu log hoặc dashboard chưa đủ để kết luận một kiểm soát đang có hiệu lực.

**Ví dụ:** đội ngũ tuyên bố “mọi thay đổi phân quyền quản trị production đều được giám sát và cảnh báo trong 5 phút”. Để kiểm chứng, cần chứng minh tối thiểu: đúng nguồn audit log đang phát sinh; sự kiện thay đổi quyền đến hệ thống phân tích đầy đủ; rule phát hiện đúng; cảnh báo đến người chịu trách nhiệm trong thời hạn; thử nghiệm có thời gian và bằng chứng tương ứng.

### 1.1. Các thuật ngữ cần phân biệt

| Khái niệm | Câu hỏi chính | Đầu ra điển hình |
|---|---|---|
| **Logging** | Hệ thống ghi lại những gì đã xảy ra? | Audit event, access log, application log, system event. |
| **Observability** | Có thể hiểu trạng thái và nguyên nhân hành vi của hệ thống đến mức nào? | Logs, metrics, traces, dashboard, mối tương quan. |
| **Performance/availability monitoring** | Dịch vụ có hoạt động đúng hiệu năng và SLO không? | Latency, error rate, CPU, saturation, availability alert. |
| **Security monitoring** | Hành vi/trạng thái nào có khả năng gây rủi ro bảo mật? | Security signal, detection, alert, finding, risk trend. |
| **Detection engineering** | Cần phát hiện kịch bản đe dọa nào, bằng logic gì, với sai số chấp nhận bao nhiêu? | Quy tắc phát hiện, thử nghiệm, phiên bản và hồ sơ chất lượng. |
| **Security operations/SOC** | Ai điều tra, quyết định và phản ứng khi có tín hiệu? | Triage, case, escalation, containment, lessons learned. |
| **Security assurance** | Có bằng chứng đáng tin rằng năng lực phát hiện và phản ứng đáp ứng mục tiêu đã cam kết không? | Ma trận coverage, kết quả kiểm thử, SLA, ngoại lệ, đánh giá độc lập. |

Một số công cụ thường gặp: **SIEM** (tập trung/tương quan dữ liệu và phát hiện), **EDR** (theo dõi/phản ứng ở endpoint), **NDR/IDS** (quan sát hành vi mạng), **cloud security monitoring** (audit/control-plane và cấu hình), **SOAR** (điều phối quy trình xử lý). Không nên đánh giá chất lượng chỉ dựa vào việc tổ chức đã mua công cụ nào.

### 1.2. Giám sát phải trả lời những câu hỏi có thể hành động

Ví dụ các câu hỏi phù hợp:

- Có ai vừa dùng danh tính đặc quyền từ thiết bị hoặc vị trí không phù hợp?
- Ai thay đổi cấu hình tắt audit log, giảm retention hoặc mở quyền truy cập công khai?
- Workload mới có được triển khai với quyền host, secret hoặc mạng vượt quá baseline?
- Có quá trình đọc dữ liệu nhạy cảm với khối lượng hoặc nhịp độ bất thường không?
- Log của một hệ thống quan trọng có bị ngừng phát, trễ hoặc mất sự kiện không?
- Tín hiệu có được gửi đến đúng người, có thể điều tra và xử lý đúng thời gian không?

Câu hỏi “có bao nhiêu log mỗi giây?” hữu ích cho năng lực hạ tầng, nhưng không tự chứng minh khả năng phát hiện hành vi nguy hiểm.

## 2. Bắt đầu từ rủi ro và mục tiêu giám sát

Thiết kế monitoring dựa trên **tài sản, threat model, khả năng tác động và yêu cầu phản ứng**, thay vì mặc định “ghi tất cả và cảnh báo càng nhiều càng tốt”.

### 2.1. Phân tích một kịch bản đe dọa

Giả sử hệ thống có dịch vụ **billing-api**, cơ sở dữ liệu hóa đơn, Kubernetes cluster và hệ thống quản lý danh tính.

- **Tài sản:** dữ liệu hóa đơn, token dịch vụ, quyền quản trị cluster và kho cấu hình.
- **Kẻ tấn công khả dĩ:** tài khoản nhân viên bị chiếm, tài khoản dịch vụ bị lộ, tiến trình ứng dụng bị xâm nhập, người có quyền nội bộ lạm dụng đặc quyền.
- **Đường tấn công:** đăng nhập bất thường → nâng quyền → tạo workload đặc quyền → đọc secret → truy cập dữ liệu trái phép → vô hiệu hóa audit log.
- **Kiểm soát phòng ngừa:** MFA, RBAC, network policy, admission policy, secret management.
- **Giám sát:** sự kiện đăng nhập, cấp quyền, thay đổi policy, tạo pod đặc quyền, truy cập secret và tình trạng audit pipeline.
- **Phản ứng:** điều tra actor và quyền hiệu lực, thu hồi phiên/token khi có căn cứ, khóa thay đổi nguy hiểm, bảo toàn bằng chứng và xác minh ảnh hưởng.

Một threat có thể cần nhiều nguồn telemetry. Ngược lại, một nguồn audit chất lượng cao có thể phục vụ nhiều kịch bản.

### 2.2. Xây dựng danh mục detection use case

| Mối đe dọa | Security question / use case | Nguồn tín hiệu khả dĩ | Độ ưu tiên điển hình |
|---|---|---|---|
| Chiếm tài khoản | Đăng nhập thành công sau chuỗi thất bại đáng ngờ? | IdP, VPN, SSO, MFA. | Cao nếu là tài khoản đặc quyền. |
| Leo thang quyền | Quyền admin hoặc role binding nhạy cảm vừa được thêm? | IAM audit, Kubernetes API audit, cloud activity log. | Cao. |
| Giảm hiệu lực giám sát | Audit logging bị tắt hoặc đầu ghi sự kiện bị sửa? | Control-plane audit, agent health, config change. | Rất cao với hệ thống trọng yếu. |
| Phá vỡ ranh giới runtime | Có workload mới chạy privileged hoặc hostPath nhạy cảm? | Admission logs, Kubernetes audit, runtime telemetry. | Theo mức ảnh hưởng. |
| Truy xuất dữ liệu bất thường | Actor xuất lượng lớn dữ liệu so với nhiệm vụ/baseline? | DB audit, object-storage access log, egress proxy. | Cao nếu dữ liệu nhạy cảm. |
| Thực thi mã đáng ngờ | Tiến trình lạ chạy ở server ứng dụng? | EDR, process telemetry, container runtime events. | Theo mức tin cậy và ảnh hưởng. |
| Tấn công dịch vụ | Nhiều lỗi xác thực hoặc yêu cầu có mẫu bất thường? | Gateway, WAF, ứng dụng, IdP. | Phụ thuộc quy mô và tác động. |
| Rò rỉ cấu hình | Secret xuất hiện trong log hoặc file chia sẻ? | DLP, secret scanning, log inspection. | Cao nếu secret còn hiệu lực. |

Mức ưu tiên cần hiệu chỉnh theo **khả năng xảy ra × hậu quả × thời gian có thể phản ứng × độ nhạy dữ liệu**, không chỉ dựa trên một từ khóa trong log. Có thể ánh xạ các use case sang chiến thuật/kỹ thuật của **MITRE ATT&CK** để quản trị phạm vi phát hiện; mã ánh xạ chỉ là công cụ phân loại, không phải bằng chứng phát hiện có hiệu lực.

### 2.3. Chọn yêu cầu ở dạng đo được

Ví dụ yêu cầu:

> Đối với mọi thay đổi cấp đặc quyền quản trị trong production, hệ thống phải nhận sự kiện audit hợp lệ, tạo cảnh báo có danh tính actor và đối tượng bị tác động, chuyển đến nhóm trực vận hành bảo mật trong tối đa 5 phút kể từ khi nguồn sinh sự kiện, với phạm vi loại trừ được phê duyệt rõ ràng.

Đây là **mục tiêu minh họa**, không phải SLA chung cho mọi tổ chức. Muốn biến thành bằng chứng assurance, phải định nghĩa cách đo “5 phút”, độ tin cậy của đồng hồ, số lượng trường hợp thử, quyền xem audit và hành vi khi pipeline bị lỗi.

## 3. Kiến trúc security monitoring từ nguồn đến phản ứng

Một kiến trúc điển hình:

~~~mermaid
flowchart LR
    S["Nguồn: IdP, API, cloud, host, K8s, DB"] --> C["Agent / Collector"]
    C --> Q["Transport và buffer"]
    Q --> N["Parse, normalize, enrich"]
    N --> L["Kho lưu trữ có kiểm soát"]
    N --> D["Detection rules và correlation"]
    D --> A["Alert / Case"]
    A --> T["Triage và điều tra"]
    T --> R["Containment / Remediation"]
    R --> F["Retest và cải tiến rule"]
    F --> D
    Q --> H["Theo dõi sức khỏe pipeline"]
    H --> A
~~~

Trong sơ đồ, **nguồn, collector, hàng đợi, parser, kho lưu trữ và rule engine** đều là thành phần phải được bảo vệ và giám sát. Kẻ tấn công có thể tấn công hệ thống quan sát bằng cách xóa log, làm tràn pipeline, gây lỗi parser hoặc giả mạo dữ liệu; vì vậy cần **monitoring of monitoring**.

### 3.1. Đầu vào: nguồn sự kiện

| Lớp | Loại sự kiện quan trọng | Lưu ý triển khai |
|---|---|---|
| **Identity/SSO/IAM** | Đăng nhập, MFA challenge, token, thêm/bớt quyền, thay đổi chính sách xác thực. | Phân biệt đăng nhập thành công, thất bại, từ chối MFA và lỗi kỹ thuật. |
| **Cloud/control plane** | Tạo, cập nhật, xóa resource; sửa firewall/IAM/logging; hoạt động tài khoản root/break-glass. | Kiểm tra phạm vi mọi account/project/region theo thiết kế. |
| **Kubernetes/orchestrator** | API audit, admission deny, tạo workload/RoleBinding/Secret, exec vào container, thay đổi node. | Cân bằng audit policy để tránh bỏ sót hoặc ghi secrets. |
| **Host/endpoint/runtime** | Process creation, nâng quyền, lệnh nhạy cảm, EDR detection, agent tampering. | Kiểm tra sensor thực sự hoạt động trên các node cần bảo vệ. |
| **Network** | DNS, firewall, proxy, WAF, flow log, IDS/NDR. | NAT, proxy và mã hóa có thể che danh tính/mục đích thật của luồng. |
| **Ứng dụng/API** | Xác thực, authorization deny, thay đổi quyền business, tải dữ liệu, xử lý giao dịch nhạy cảm. | Thiết kế event mang ngữ nghĩa nghiệp vụ; tránh chỉ ghi HTTP status. |
| **Database và data service** | Query nhạy cảm, xuất dữ liệu, thay đổi quyền schema, truy cập bucket. | Giảm lộ dữ liệu/PII trong log; xác định actor thực qua connection pool. |
| **CI/CD và supply chain** | Thay đổi pipeline, tạo artifact, deploy production, sửa secret/config, phê duyệt. | Liên kết deployment với commit, artifact digest và danh tính thực hiện. |

Không phải mọi nguồn đều cần thu thập mọi event. Phạm vi được quyết định bởi risk register, yêu cầu audit và khả năng vận hành; mọi khoảng trống trọng yếu phải có owner và kế hoạch xử lý.

### 3.2. Chất lượng event: cần cấu trúc và ngữ cảnh

Một security event hữu ích thường gồm:

| Trường | Vai trò | Yêu cầu chất lượng |
|---|---|---|
| **event_id** | Định danh bản ghi để xử lý trùng lặp và truy vết. | Ổn định trong phạm vi nguồn, hoặc có khóa ghép tương đương. |
| **event_time** | Thời điểm hoạt động được nguồn quan sát. | UTC hoặc timestamp có timezone; đồng hồ nguồn được đồng bộ. |
| **observed_at / ingested_at** | Thời điểm collector/analytics nhận sự kiện. | Phục vụ tính độ trễ ingest và phát hiện backlog. |
| **source** | Hệ thống, tài khoản cloud, cluster, host, workload phát sinh. | Có id môi trường và phân loại trust. |
| **actor** | Danh tính người dùng, workload, service principal hoặc admin. | Không chỉ lưu display name; dùng định danh bất biến nếu có. |
| **action** | Hành động như login, role.grant, secret.read, policy.update. | Taxonomy nhất quán, giữ nguyên raw action để đối chiếu. |
| **target** | Tài nguyên bị tác động. | Bao gồm resource id, tenant và độ nhạy khi thích hợp. |
| **outcome** | Success/deny/failure/unknown và lý do. | Không suy diễn failure là bị chặn bởi security control nếu chưa rõ nguyên nhân. |
| **context** | IP, device, user agent, session/correlation/trace id, request id. | Xử lý NAT, proxy, spoofed header và giới hạn tin cậy. |
| **schema_version** | Phiên bản chuẩn hóa và parser. | Dùng để theo dõi thay đổi schema, phát hiện parse failure. |

Ví dụ event giả lập đã được giản lược:

~~~json
{
  "event_id": "evt-2026-012345",
  "event_time": "2026-11-28T03:20:17Z",
  "ingested_at": "2026-11-28T03:20:19Z",
  "source": {
    "system": "identity-provider",
    "environment": "production",
    "tenant_id": "tenant-demo"
  },
  "actor": {
    "id": "user-4812",
    "type": "human",
    "privileged": true
  },
  "action": "authentication.login",
  "outcome": "success",
  "source_ip": "192.0.2.25",
  "session_id": "session-redacted-8a6f",
  "mfa_result": "passed",
  "correlation_id": "request-0318",
  "schema_version": "1.0"
}
~~~

Địa chỉ **192.0.2.25** thuộc dải IP dành cho ví dụ tài liệu. Trong thực tế, hạn chế lưu session ID có thể sử dụng lại, access token, mật khẩu, secret, cookie, raw request body hoặc dữ liệu cá nhân không cần thiết. Khi cần correlation, dùng định danh được thiết kế để truy vết an toàn và quy định retention phù hợp.

### 3.3. Khả năng nhìn thấy nguồn không đồng nghĩa độ tin cậy của nguồn

Độ tin cậy phụ thuộc vào:

- Nguồn sự kiện có được cấu hình **bật audit** và bao phủ đúng hành động cần phát hiện không?
- Collector có đủ quyền đọc nhưng không có quyền sửa tùy tiện bản ghi gốc không?
- Đồng hồ, timezone, schema và version có nhất quán không?
- Event có bị **sampling, throttling, filtering, rate limiting**, mất do queue đầy hoặc lỗi parser không?
- Hệ thống có nhận biết **duplicate**, out-of-order event và late arrival không?
- Khi network tới SIEM mất, agent có buffer và gửi lại không? Có giới hạn hàng đợi và cảnh báo tràn không?
- Có nhật ký và bằng chứng khi nguồn dừng phát hoặc cấu hình thu thập bị đổi không?

Sự kiện “không xuất hiện” có hai khả năng: **không xảy ra hành vi** hoặc **hệ thống không thấy hành vi**. Thiết kế phải giúp phân biệt hai tình huống đó.

## 4. Bảo vệ pipeline và dữ liệu giám sát

### 4.1. Các mục tiêu bảo vệ

1. **Integrity:** đối tượng không có thẩm quyền không sửa/xóa bản ghi hoặc thay đổi rule và kết quả kiểm thử.
2. **Availability:** log vẫn được thu thập và truy vấn trong mức trễ/mất dữ liệu cho phép.
3. **Confidentiality:** người xem log không mặc nhiên được xem toàn bộ PII, bí mật và dữ liệu nghiệp vụ.
4. **Authenticity/provenance:** biết nguồn phát, phiên bản parser, đường truyền và các bước biến đổi.
5. **Retention:** thời gian lưu đúng yêu cầu; có phân tầng và xóa dữ liệu theo chính sách.
6. **Auditability:** truy cập, xuất dữ liệu, sửa parser, thay rule, chỉnh retention và thay đổi quyền đều có dấu vết.

Các cơ chế thường dùng: TLS/mTLS ở đường truyền khi phù hợp; IAM với least privilege; tách quyền producer/reader/admin; mã hóa dữ liệu lưu; immutable/WORM storage khi có yêu cầu; retention lock có kiểm soát; hash/chữ ký hoặc cơ chế xác minh tính toàn vẹn; backup và khả năng khôi phục; audit cho kho log; giám sát hành vi xóa/disable agent.

**“Immutable” cần được xác định theo phạm vi quyền.** Nếu cùng một principal có thể đổi retention, xóa khóa mã hóa, xóa tài khoản lưu trữ hoặc tắt pipeline thì khả năng bảo toàn bằng chứng có thể vẫn chưa đủ mạnh.

### 4.2. Quyền và phân vùng dữ liệu

Trong hệ thống nhiều tenant, event có thể chứa định danh và dữ liệu của nhiều khách hàng. Phân quyền đọc log cần xét:

- Nhóm SOC xem metadata cần điều tra hay payload nhạy cảm?
- Nhân viên phát triển chỉ xem log ứng dụng của dịch vụ mình hay toàn bộ production?
- Audit/forensics có quyền xuất dữ liệu; quyền đó được phê duyệt và ghi nhận ra sao?
- Làm thế nào để giảm quyền của tài khoản CI/CD và service account gửi log?
- Khi có yêu cầu bảo toàn bằng chứng sự cố, ai được đặt legal hold/retention hold theo quy trình phù hợp?

Tổ chức cần hạn chế **log injection**: chuỗi do người dùng nhập có thể chứa xuống dòng, ký tự điều khiển hoặc giá trị giả nhãn. Sử dụng format cấu trúc, escaping phù hợp và phân biệt trường dữ liệu không đáng tin với metadata do hệ thống đặt.

### 4.3. Độ trễ và mất dữ liệu

Một số chỉ số sức khỏe pipeline quan trọng:

- **Ingestion latency:** \(\text{ingested\_at} - \text{event\_time}\), theo p50/p95/p99 và từng nguồn.
- **Coverage of reporting sources:** số nguồn bắt buộc đã gửi heartbeat/event trong cửa sổ quan sát trên tổng số nguồn bắt buộc.
- **Event rejection / parse error rate:** số bản ghi không thể xử lý trên tổng đầu vào.
- **Queue age / backlog:** tuổi sự kiện cũ nhất chưa xử lý, số lượng backlog.
- **Loss estimate:** tỷ lệ thiếu theo sequence number, agent acknowledgment hoặc nguồn đối chiếu; không suy luận chỉ từ tổng event.
- **Rule execution health:** thời điểm chạy cuối, lỗi truy vấn, backlog, kết quả test, độ trễ tạo alert.

Cần đặt ngưỡng theo mức quan trọng của từng nguồn. Dữ liệu về audit IAM thường có yêu cầu độ trễ và tính đầy đủ khác với access log thông thường.

## 5. Detection engineering: từ giả thuyết đến rule kiểm chứng

Một detection use case đủ để vận hành và audit nên gồm các trường sau:

| Thành phần | Câu hỏi cần trả lời |
|---|---|
| **Use case ID và owner** | Ai duy trì rule, liên hệ ai khi có sự cố? |
| **Threat hypothesis** | Hành vi nguy hiểm cụ thể nào cần nhận ra? |
| **Risk/asset scope** | Hệ thống, dữ liệu, tenant, environment nào có nguy cơ? |
| **Data prerequisites** | Event và các field nào bắt buộc? Nguồn thiếu thì sao? |
| **Detection logic** | Filter, join, aggregation, time window, threshold và ngữ cảnh nào? |
| **Exclusions** | Ngoại lệ hợp lệ nào, ai phê duyệt, khi nào hết hạn? |
| **Severity/confidence** | Vì sao cảnh báo ưu tiên như vậy? Độ tin cậy của dấu hiệu ở mức nào? |
| **Response** | Runbook, owner trực, escalation, SLA, hành động nên xác nhận trước? |
| **Validation** | Test dương tính, test âm tính, dữ liệu giả lập/đã ẩn danh và kết quả mong đợi? |
| **Evidence** | Phiên bản rule, dữ liệu thử, kết quả, ngày chạy, người duyệt? |
| **Lifecycle** | Lần rà soát gần nhất, sự kiện kích hoạt cập nhật, ngày hết hạn ngoại lệ? |

Một cảnh báo **không đồng nghĩa một sự cố đã được xác nhận**. Alert là giả thuyết có bằng chứng ban đầu; triage mới xác định tính hợp lệ, phạm vi và mức tác động.

### 5.1. Ví dụ A — Đăng nhập thành công sau nhiều lần thất bại

**Giả thuyết:** một danh tính có nhiều lần đăng nhập thất bại trong thời gian ngắn, sau đó thành công từ cùng nguồn hoặc phiên có liên quan, có thể là dấu hiệu dò mật khẩu hoặc chiếm thông tin xác thực.

**Dữ liệu bắt buộc:** actor ID, outcome, event_time, source IP/device, MFA result, correlation/session ID nếu có, độ tin cậy của network attribution.

**Quy tắc minh họa (pseudocode):**

~~~text
RULE: auth.success_after_failures
SCOPE: production identity events
WINDOW: 10 minutes
GROUP BY: actor.id + verified_source_context
WHEN:
  count(action == "authentication.login" AND outcome == "failure") >= 8
  AND exists(action == "authentication.login" AND outcome == "success"
             AFTER last_failure WITHIN 10 minutes)
THEN:
  emit alert with actor, source, failures_count, first_seen,
       last_seen, success_time, mfa_result
SEVERITY:
  high when actor is privileged or device is untrusted
  medium otherwise
~~~

Các ngưỡng 8 lần và 10 phút **chỉ để minh họa**. Khi production dùng SSO, retry tự động, proxy dùng chung IP, event out-of-order hoặc ID thay đổi giữa các bước xác thực, phải hiệu chỉnh logic. Không xem cùng IP công cộng là bằng chứng cùng thiết bị/người dùng; cần context đáng tin hơn.

**Positive test:** giả lập chuỗi sự kiện thất bại rồi thành công tương ứng, xác nhận phát hiện đúng actor và thứ tự thời gian.

**Negative test:** một vài lần thất bại của người dùng bình thường; lỗi từ các actor không liên quan; thành công cách xa cửa sổ; IP do hàng nghìn người chia sẻ; test hợp lệ phải không tạo cảnh báo hoặc được điều chỉnh rule để giảm noise.

**Triage:** kiểm tra MFA, thiết bị, vị trí nguồn đáng tin, phiên hiện hành, thay đổi quyền vừa phát sinh và hành vi sau đăng nhập. Không tự động khóa mọi tài khoản chỉ từ tín hiệu trên nếu chưa định nghĩa điều kiện an toàn, đặc biệt với tài khoản vận hành quan trọng.

### 5.2. Ví dụ B — Cấp quyền admin trên Kubernetes

**Giả thuyết:** một actor tạo/sửa **ClusterRoleBinding** hoặc **RoleBinding** cấp quyền vượt baseline, khiến khả năng đọc secrets, thực thi trong pod hoặc thay đổi workloads tăng lên.

Một pipeline kiểm tra có thể chuẩn hóa event thành:

~~~json
{
  "event_time": "2026-11-28T03:27:22Z",
  "source": {"system": "kubernetes-api", "cluster": "prod-eu-1"},
  "actor": {"id": "service-account-release", "type": "workload"},
  "action": "k8s.rbac.binding.create",
  "target": {"kind": "ClusterRoleBinding", "name": "temporary-admin"},
  "outcome": "success",
  "new_role": {"kind": "ClusterRole", "name": "cluster-admin"},
  "request_id": "req-814",
  "change_ticket": null
}
~~~

Rule:

- Theo dõi tạo/sửa RBAC binding trong **production**.
- Phân tích **quyền hiệu lực** (effective permissions), không chỉ tên role. Tên role có thể khác nhau và role có thể được thay đổi sau khi bind.
- Cảnh báo khi binding cấp nhóm quyền nhạy cảm, nhất là quyền quản trị toàn cluster, không có change ticket hợp lệ hoặc nằm ngoài quy trình chuẩn.
- Tương quan actor, mục tiêu, thời gian, các lần tạo pod/đọc secret sau đó và lịch sử deployment.
- Nếu API audit chỉ ghi metadata mà không ghi đối tượng đủ để đánh giá role, cần lấy snapshot RBAC từ API với quyền được cấp và bảo quản như bằng chứng tại thời điểm phát hiện.

**Bằng chứng assurance:** audit event gốc đã được kiểm tra provenance; rule version; test tạo một RoleBinding không có quyền được phép trong namespace thử nghiệm và một thay đổi quyền admin có kiểm soát; kết quả cảnh báo; thời điểm chuyển đến đội trực; hồ sơ xử lý.

### 5.3. Ví dụ C — Audit logging bị vô hiệu hóa

**Giả thuyết:** một tác nhân cố tình giảm khả năng quan sát trước hoặc sau hành vi tấn công.

Nguồn phát hiện cần được đặt đủ **độc lập với chính thành phần bị tắt**. Nếu chỉ dùng log từ một agent đã bị vô hiệu hóa thì không thể chắc chắn nhìn thấy lệnh tắt đó.

Thiết kế khả dĩ:

- Giám sát control-plane event thay đổi audit policy, xóa collector, sửa IAM/retention, tắt EDR.
- Kiểm tra heartbeat/sequence gap/ingestion lag của các nguồn quan trọng.
- So sánh danh sách asset đang tồn tại với danh sách nguồn gửi telemetry.
- Kiểm tra việc tắt log qua một kênh độc lập, ví dụ audit control plane tập trung và inventory.
- Chuyển cảnh báo “mất nguồn quan sát” thành một tình huống cần điều tra, kể cả chưa có dấu hiệu tấn công khác.

Một chương trình chỉ phát hiện “có event xấu” mà không phát hiện “không còn khả năng nhận event” sẽ có điểm mù nghiêm trọng.

### 5.4. Ví dụ D — Truy xuất dữ liệu bất thường

Phân tích dữ liệu nhạy cảm nên kết hợp:

- Danh tính actor, mục đích công việc, phạm vi tenant và quyền được cấp.
- Khối lượng dữ liệu/đối tượng, tốc độ, thời gian, độ mới của đích xuất.
- Các mẫu query/download bình thường của workload và mùa vụ.
- Destination IP/domain/bucket, các thay đổi quyền/secret trước đó.
- Các job sao lưu, migration, ETL hợp lệ được ghi trong change management.

Một cảnh báo “download trên 1 GB” có thể tạo nhiều false positive với backup hợp lệ nhưng bỏ lỡ việc đọc 10 MB chứa dữ liệu nhạy cảm. Cần điều chỉnh theo **rủi ro của đối tượng dữ liệu**, không chỉ kích thước byte.

## 6. Từ signal đến alert, case và incident

### 6.1. Tăng chất lượng tín hiệu

Hệ thống thường trải qua các cấp:

1. **Raw event:** quan sát đơn lẻ, chưa chắc có ý nghĩa bảo mật.
2. **Normalized event:** dữ liệu đã chuẩn hóa và có ngữ cảnh.
3. **Signal/detection hit:** điều kiện rule đã khớp.
4. **Alert:** tín hiệu có mức ưu tiên, liên quan một đối tượng cần chú ý.
5. **Case/investigation:** các tín hiệu và chứng cứ được gom để triage.
6. **Confirmed incident:** đánh giá xác nhận vi phạm hoặc tác động an ninh cần ứng phó theo quy trình.
7. **Finding/control gap:** phát hiện điểm yếu về kiểm soát hoặc coverage, có owner và hạn khắc phục.

Không cần mở incident cho mỗi raw event; ngược lại, một sự cố có thể bao gồm nhiều alert. Định nghĩa rõ trạng thái giúp đo hiệu quả và tránh làm sai số thống kê.

### 6.2. Triển khai phân tuyến cảnh báo

| Mức ưu tiên ví dụ | Điều kiện gợi ý | Hành động |
|---|---|---|
| **Critical** | Phát hiện nguy cơ đang hoạt động đối với dữ liệu/truy cập đặc quyền trọng yếu, có bằng chứng rõ và hậu quả lớn. | Đánh thức đội trực, bắt đầu incident response theo quy trình, ưu tiên containment an toàn. |
| **High** | Dấu hiệu mạnh hoặc hành vi đặc quyền không được phép, nhưng cần thêm dữ liệu xác nhận. | Triage ưu tiên, thu thập context, kiểm tra thay đổi liên quan, escalation phù hợp. |
| **Medium** | Dấu hiệu đáng nghi, có khả năng là vận hành hợp lệ hoặc tác động hạn chế. | Xử lý theo SLA, tương quan với sự kiện khác và baseline. |
| **Low/Informational** | Bất thường yếu, hành vi cần audit, không đòi phản ứng ngay. | Lưu làm context, theo dõi xu hướng, cải thiện logic khi cần. |

Mức độ nghiêm trọng cần xét cả **tác động tài sản** và **độ tin cậy phát hiện**. Quy tắc đặt severity phải được phê duyệt phù hợp và không dựa duy nhất vào trường severity do một nguồn bên ngoài tự khai báo.

### 6.3. Runbook cho một alert thực tế

Một runbook nên trả lời:

- **Kích hoạt:** điều kiện tạo alert, link đến rule, use case ID, owner và dashboard.
- **Kiểm tra đầu tiên:** log nguồn có đầy đủ không; alert có duplication, parser bug hoặc thời gian sai không?
- **Ngữ cảnh:** asset/actor/tenant/nguồn, hoạt động trước và sau, sự kiện thay đổi triển khai, mức nhạy dữ liệu.
- **Quyết định:** expected behavior, false positive, benign anomaly, suspicious, confirmed incident, insufficient evidence.
- **Escalation:** tuyến liên hệ khi không rõ, khi vượt SLA, khi ảnh hưởng nhiều tài khoản hoặc khi pipeline mù.
- **Containment:** các lựa chọn được phép như thu hồi session, giảm quyền, chặn egress, cô lập workload theo quy trình, với đánh giá tác động kinh doanh.
- **Preservation:** bảo toàn dữ liệu gốc, phiên bản query, thời điểm, logs và audit của các hành động điều tra.
- **Closure:** lý do đóng, bài học, ticket khắc phục, ngày kiểm tra lại rule.

SOAR có thể hỗ trợ enrichment, ticketing, khóa token và thông báo. Với hành động có khả năng gây gián đoạn lớn, cần đặt mức tự động hóa theo **độ chắc chắn, tính đảo ngược và phê duyệt**; không suy luận rằng mọi alert đều an toàn để chặn ngay.

## 7. Kiểm chứng hiệu lực detection thay vì chỉ kiểm tra “rule enabled”

Chương trình monitoring cần thử nghiệm giống như bất kỳ security control nào: có tiêu chí chấp nhận, dữ liệu kiểm soát, kết quả quan sát và bằng chứng.

### 7.1. Ba cấp kiểm chứng

**Cấp A — Data readiness**

- Nguồn trong phạm vi có bật audit và gửi event.
- Các trường bắt buộc có mặt, parse đúng, dấu thời gian/actor/target đáng tin.
- Chất lượng pipeline đạt ngưỡng mất dữ liệu/độ trễ đã quy định.
- Schema change được phát hiện, parser lỗi được ghi và có người chịu trách nhiệm.

**Cấp B — Detection effectiveness**

- **Positive tests:** tạo hành vi phù hợp rule và xác nhận alert.
- **Negative tests:** tạo hành vi hợp lệ gần giống để kiểm tra false positive.
- **Boundary tests:** đúng/sát ngưỡng thời gian, số lượng, thay đổi thứ tự, event duplicate, late arrival.
- **Context tests:** actor đặc quyền/không đặc quyền, tenant khác nhau, môi trường test/prod, thay đổi nhãn.
- **Bypass/gap tests:** dữ liệu thiếu trường, agent mất kết nối, service mới xuất hiện, policy thay đổi.
- **Regression:** sau khi sửa parser/rule, các tình huống từng pass vẫn được kiểm chứng.

**Cấp C — Response effectiveness**

- Alert tới đúng kênh trực và có đủ context.
- Có ticket/case và owner; on-call phản hồi theo mục tiêu đã định.
- Người trực đủ thông tin để phân loại, escalation và làm containment an toàn.
- Có chứng cứ kết luận, nguyên nhân, khắc phục và cập nhật rule.
- Có diễn tập/tình huống giả lập để đo toàn bộ đường **event → alert → triage → action**.

### 7.2. Ma trận truy vết assurance

| Claim của chương trình | Test chấp nhận | Bằng chứng lưu | Giới hạn kết luận |
|---|---|---|---|
| **A1: Các nguồn trọng yếu đang được quan sát.** | So inventory tài sản với nguồn telemetry; kiểm tra heartbeat, schema, độ trễ. | Inventory + coverage report + health metrics có timestamp. | Chứng minh phạm vi nguồn, chưa chứng minh mọi hành vi cần thiết đều có event. |
| **A2: Thay đổi IAM đặc quyền được phát hiện.** | Tạo thay đổi được kiểm soát; đo event → alert → case theo SLA. | Event audit, rule version, alert timeline, ticket. | Phụ thuộc quyền, môi trường và loại thay đổi đã thử. |
| **A3: Thay đổi làm yếu audit được phát hiện.** | Mô phỏng thay đổi cấu hình và kiểm tra signal độc lập/heartbeat gap. | Config snapshot, independent audit, alert/case. | Không khẳng định mọi cách vô hiệu hóa telemetry đều bị phát hiện. |
| **A4: Rule có khả năng phân biệt hành vi hợp lệ và đáng ngờ.** | Chạy bộ test dương tính/âm tính và tình huống biên. | Test fixtures, kết quả, false-positive review. | Bộ test không đại diện mọi lưu lượng thực tế. |
| **A5: Người trực phản ứng được trong thời hạn.** | Diễn tập với sự kiện có thời điểm kiểm soát và trực ca thực tế. | Alert delivery, ack time, runbook execution, after-action report. | Kết quả diễn tập không bảo đảm mọi sự cố thật đều có thời gian tương tự. |
| **A6: Dữ liệu bằng chứng được bảo vệ.** | Kiểm tra quyền, retention, khả năng xóa/chỉnh sửa, audit việc truy cập. | IAM snapshot, policy, audit truy cập, kết quả thử phân quyền. | Phải kiểm tra cả người có quyền quản trị và kênh phá hủy gián tiếp. |

Một bảng “đã bật SIEM cho 100% server” không tự đáp ứng các claim A2–A6.

### 7.3. Kiểm tra với sự kiện canary

Để kiểm chứng pipeline định kỳ, có thể phát một **canary event** vô hại, định danh duy nhất, từ một nguồn đã ủy quyền. Sau đó đo thời điểm nguồn sinh sự kiện, SIEM ingest, rule chạy và alert đến on-call.

Ví dụ:

~~~json
{
  "event_type": "security-monitoring.canary",
  "canary_id": "validation-run-2026-001",
  "source": "production-safe-canary",
  "event_time": "2026-11-28T04:00:00Z",
  "expected_detection": "monitoring-health-canary-v1"
}
~~~

Canary phải được thiết kế để **không bị hiểu thành sự cố tấn công thật** và không chứa dữ liệu nhạy cảm. Nó kiểm tra khả năng đi qua một pipeline cụ thể, nhưng **không** thay thế thử nghiệm use case đe dọa thật: canary có thể đến thành công dù log IAM hoặc log database đang mất.

## 8. Đo hiệu quả security monitoring bằng KPI và giới hạn đo lường

Chỉ số phải phục vụ quyết định: tăng coverage, giảm thời gian phát hiện, cải thiện năng lực triage hoặc loại bỏ noise. Tránh dùng “số alert tăng” như chỉ báo mặc định rằng hệ thống an toàn hơn.

### 8.1. Một số KPI cốt lõi

| Chỉ số | Công thức/định nghĩa | Diễn giải và hạn chế |
|---|---|---|
| **Asset/source coverage** | Số tài sản/nguồn bắt buộc có telemetry hợp lệ ÷ tổng số tài sản/nguồn bắt buộc. | Mẫu số cần lấy từ inventory chuẩn; coverage nguồn không bằng coverage threat. |
| **Use-case coverage** | Số tình huống rủi ro ưu tiên có detection đã được thử nghiệm và đạt ÷ tổng tình huống ưu tiên trong phạm vi. | Phụ thuộc chất lượng threat model và tiêu chí “đạt”. |
| **Ingestion latency** | ingested_at − event_time, tính theo phân vị và nguồn. | Đồng hồ không đồng bộ hoặc thời điểm xử lý lại có thể làm sai lệch. |
| **Detection latency** | alert_created_at − event_time. | Có thể gồm cả delay upstream, batch/window và rule scheduler. |
| **MTTD** | Trung bình thời gian từ sự kiện khởi phát đủ quan sát đến lúc phát hiện, trên tập sự cố xác định. | Cần định nghĩa “sự kiện khởi phát” và tập mẫu; không tính được với sự cố không phát hiện. |
| **MTTA** | Trung bình từ alert được tạo/chuyển đến người trực đến khi có ghi nhận tiếp nhận. | Chỉ thể hiện tốc độ nhận, không phản ánh chất lượng điều tra. |
| **MTTR** | Trung bình thời gian phục hồi/khắc phục theo định nghĩa đã chọn. | Rất dễ nhầm giữa response, containment và recovery; phải khai báo rõ mốc. |
| **Alert precision (ước lượng)** | Alert được đánh giá có hành vi cần điều tra ÷ alert được đánh giá trong một mẫu đại diện. | Bị ảnh hưởng bởi cách gắn nhãn và cỡ mẫu; “không bị xác nhận incident” chưa chắc là false positive. |
| **False-positive rate** | Tỷ lệ cảnh báo được xác định là sai theo định nghĩa và mẫu đo. | Không suy trực tiếp từ total alerts, cần nhãn phân loại nhất quán. |
| **Investigation backlog** | Số case chưa xử lý quá SLA theo severity. | Thể hiện năng lực xử lý, không trực tiếp đo tỷ lệ tấn công. |
| **Telemetry health** | Tỷ lệ nguồn đạt ngưỡng độ trễ, parse quality và heartbeat. | Cần tách theo mức độ quan trọng, không làm trung bình che điểm mù. |

**False negative** thường không có số đo toàn diện vì có thể tồn tại các hành vi đã xảy ra nhưng không hề được quan sát. Nên ước lượng khả năng bỏ sót qua purple teaming, replay dataset, threat-informed testing, hậu kiểm sự cố và red-team exercise được cho phép; không tuyên bố “0 false negative” chỉ vì chưa có báo cáo.

### 8.2. Ví dụ tính thời gian

Một audit event có:

~~~text
event_time        = 10:00:00 UTC
ingested_at       = 10:00:08 UTC
alert_created_at  = 10:01:30 UTC
acknowledged_at   = 10:03:00 UTC
contained_at      = 10:12:00 UTC
~~~

Khi các mốc có cùng nguồn thời gian đáng tin:

- **Ingestion latency** = 8 giây.
- **Detection latency** = 90 giây.
- **Time to acknowledge** = 90 giây tính từ lúc alert được tạo.
- **Time to containment** = 12 phút tính từ event.

Các phép tính này chỉ đúng cho **một trường hợp**. Không dùng một mẫu duy nhất để kết luận SLA toàn hệ thống. Nếu sự kiện bị trễ hoặc đồng hồ sai, cần kiểm tra clock skew và ghi lại sự không chắc chắn thay vì tự thay mốc thời gian để “đạt SLA”.

### 8.3. Tập trung vào hiệu quả, không chạy theo số lượng

Ba tình huống có thể cùng xuất hiện khi tăng số rule:

1. Nhiều threat được phát hiện hơn.
2. Nhiều cảnh báo dư thừa khiến on-call quá tải.
3. Nguồn dữ liệu mới chứa nhiều lỗi parser khiến rule báo sai.

Do đó cần quan sát đồng thời: coverage, detection precision, tỉ lệ case xử lý đúng SLA, độ trễ pipeline, tỷ lệ rule có thử nghiệm cập nhật và thời gian nhân sự dành cho điều tra không có giá trị.

## 9. Tình huống thực hành: phát hiện quyền quản trị bất thường

**Bối cảnh:** một tổ chức dùng Kubernetes cho ứng dụng xử lý hồ sơ khách hàng. Một tài khoản automation có quyền triển khai ứng dụng bị lộ. Kẻ tấn công sử dụng quyền có sẵn để tạo ClusterRoleBinding cho một danh tính khác. Hệ thống có SIEM và dashboard “all clusters connected”, nhưng không có rule trực tiếp cho RBAC thay đổi.

**Mục tiêu assurance:** phát hiện mọi thay đổi cấp quyền admin ngoài allowlist trong cluster production và chuyển đến nhóm trực trong 5 phút.

### 9.1. Thiết kế

**Tài sản:** Kubernetes API, secrets, workloads và dữ liệu khách hàng.

**Tín hiệu:** Kubernetes API audit ở mức đáp ứng field actor, verb, object, response; RBAC snapshot để xác định quyền hiệu lực; IAM/deployment event cho correlation.

**Control phòng ngừa bổ sung:** RBAC theo least privilege, kiểm soát service account, chính sách thay đổi quyền và ghi nhận phê duyệt.

**Detection logic:** khi một binding được tạo/sửa cấp quyền cluster-admin hoặc quyền tương đương, xác minh actor, namespace/cluster, danh tính đích và đối chiếu thay đổi đã được duyệt. Ưu tiên cao nếu principal ngoài quy trình hoặc thay đổi được thực hiện bởi automation không có quyền quản trị theo thiết kế.

**Triage:** xác minh audit event; kiểm tra actor/credential, thời gian, binding hiện tại, quyền hiệu lực, các lần đọc secret/tạo pod liên quan; hỏi owner xem có change ticket hợp lệ không; quyết định containment theo runbook.

### 9.2. Bộ kiểm thử tối thiểu

| Test ID | Dữ liệu/hành vi được kiểm soát | Kết quả kỳ vọng |
|---|---|---|
| T01 | Tạo RBAC binding ở môi trường kiểm thử, cấp quyền thấp đã được phép. | Không có alert high severity. |
| T02 | Tạo binding cấp quyền admin bằng tài khoản kiểm thử được ủy quyền trong môi trường test và rule cấu hình kiểm thử. | Có detection hit và alert đủ actor/target/change context; không làm thay đổi production. |
| T03 | Sửa binding từ quyền thấp sang quyền admin. | Rule phát hiện cả đường **update**, không chỉ create. |
| T04 | Thêm binding cấp quyền nhạy cảm nhưng role có tên không chứa chữ “admin”. | Phát hiện dựa trên quyền hiệu lực hoặc policy quyền đã định. |
| T05 | Sự kiện API đến chậm hoặc trùng lặp. | Hệ thống xử lý cửa sổ thời gian và de-duplication theo thiết kế, không mất alert cần thiết. |
| T06 | Thử ngừng heartbeat của nguồn giả lập trong sandbox giám sát. | Có cảnh báo health phù hợp để phân biệt “không có sự kiện” với “mất khả năng quan sát”. |
| T07 | Diễn tập chuyển alert đến người trực theo kênh trực thực tế. | Có case, owner, timestamp gửi/nhận, quyết định và kết thúc kiểm thử. |

Các phép thử thay đổi RBAC phải tiến hành trên tài nguyên và danh tính được ủy quyền; chuẩn bị cơ chế rollback cho trạng thái thử. Không cố ý làm giảm logging hay quyền production để tạo evidence nếu không có môi trường và phê duyệt phù hợp.

### 9.3. Hồ sơ bằng chứng

~~~text
evidence/security-monitoring/rbac-admin-change/
  scope-and-risk.md
  detection-use-case.yaml
  log-source-inventory.csv
  data-quality-report.json
  raw-events-sanitized.jsonl
  normalized-events.jsonl
  rule-version.txt
  positive-negative-tests.json
  alert-and-case-timeline.csv
  runbook-review.md
  owner-approval-and-exceptions.md
~~~

**Tối thiểu mỗi evidence record** cần có: use-case ID, environment/cluster, rule version, data source/version, thời gian UTC, test ID, expected/actual outcome, link đến event/alert/case, người thực hiện, người rà soát, tình trạng và hạn kiểm tra lại. Không đưa raw credential hoặc nội dung nhạy cảm vào file báo cáo; dùng kho lưu bảo mật với phân quyền phù hợp.

### 9.4. Phân tích kết quả

Nếu T02 tạo alert trong 45 giây, T03 và T04 không phát hiện, T06 cảnh báo nguồn mất sau 30 phút, thì:

- Đã có bằng chứng **một nhánh detection hoạt động**; không đủ để kết luận “mọi thay đổi quyền admin đều được phát hiện”.
- Phải bổ sung rule/parser hoặc dữ liệu RBAC để bao phủ update và quyền tương đương.
- Phải rà soát yêu cầu thời gian phát hiện lỗi nguồn. Nếu hệ thống phải phát hiện điểm mù sớm hơn 30 phút, hiện tại chưa đạt mục tiêu.
- Ghi finding, owner, thời hạn khắc phục và chạy lại T01–T07 sau sửa.

Một báo cáo đạt assurance cần trình bày **kết quả không đạt và phạm vi chưa kiểm chứng**, không chỉ ghi các test đã pass.

## 10. Continuous monitoring và quản trị thay đổi

### 10.1. Vòng đời vận hành

~~~mermaid
flowchart TD
    Risk["Đánh giá rủi ro / Threat modeling"] --> U["Ưu tiên detection use case"]
    U --> DS["Định nghĩa telemetry + rule + runbook"]
    DS --> V["Kiểm thử + phê duyệt"]
    V --> P["Triển khai và giám sát health"]
    P --> O["Triage / Incident / Finding"]
    O --> C["Tuning, khắc phục, cập nhật coverage"]
    C --> V
    P --> M["Đo coverage, latency, precision, SLA"]
    M --> Risk
~~~

Các thay đổi sau cần kích hoạt đánh giá lại detection và runbook:

- Thêm asset/tenant/cluster mới hoặc thay đổi phạm vi dữ liệu nhạy cảm.
- Chuyển SSO/IdP, nâng cấp API, đổi schema event hoặc cấu hình audit.
- Thay agent/CNI/runtime hoặc kiến trúc log pipeline.
- Sửa IAM/RBAC, thay người trực hoặc kênh cảnh báo.
- Phát hiện incident mới, kỹ thuật tấn công mới trong phạm vi threat model.
- Thay đổi luật retention, yêu cầu quyền riêng tư hoặc phạm vi kiểm toán áp dụng.

Một rule có thể vẫn “enabled” trong UI nhưng không hoạt động vì schema đã đổi, nhãn resource không khớp hoặc stream từ môi trường mới chưa được kết nối.

### 10.2. Phân định trách nhiệm

| Vai trò | Trách nhiệm chính |
|---|---|
| **Asset owner / service team** | Xác định hành vi nghiệp vụ nhạy cảm, cung cấp ngữ nghĩa event và bối cảnh hợp lệ. |
| **Platform/logging team** | Thu thập, vận chuyển, chuẩn hóa, lưu trữ và đo sức khỏe pipeline; bảo vệ hạ tầng log. |
| **Detection engineering** | Xây dựng giả thuyết, rule, bộ test, tuning, versioning và hồ sơ coverage. |
| **SOC / security operations** | Tiếp nhận, triage, escalation, điều tra và phản hồi qua runbook. |
| **Incident response / forensic** | Điều phối sự cố, containment, bảo toàn bằng chứng và bài học sau sự cố. |
| **Security assurance / audit** | Xác lập tiêu chí, đánh giá bằng chứng độc lập, ghi nhận khoảng trống và xác minh khắc phục. |
| **Risk owner** | Chấp nhận rủi ro tồn dư và ngoại lệ trong thẩm quyền, phê duyệt mục tiêu phù hợp. |

Các vai trò có thể kiêm nhiệm ở tổ chức nhỏ; vẫn cần bảo đảm người chịu trách nhiệm và quyền phê duyệt được phân biệt theo mức rủi ro.

### 10.3. Quản lý exception và alert suppression

Tuning không đồng nghĩa xóa hết cảnh báo. Khi tạm thời tắt hoặc loại trừ một rule:

1. Ghi lý do và dữ liệu chứng minh đây là hoạt động hợp lệ/noise.
2. Xác định cụ thể actor, tài sản, nguồn, khoảng thời gian và điều kiện được loại trừ.
3. Ước lượng hành vi tấn công có thể bị che khuất do ngoại lệ.
4. Có chủ sở hữu, phê duyệt và ngày hết hạn.
5. Giữ audit của thay đổi rule; yêu cầu thử lại và đánh giá hậu quả.

Một suppression áp dụng cho toàn bộ production vì “alert nhiều” có thể làm mất năng lực phát hiện đúng lúc cần.

## 11. Quyền riêng tư, chi phí và giới hạn hệ thống

Security monitoring liên quan nhiều dữ liệu nhạy cảm, nên phải cân bằng yêu cầu phát hiện với các nguyên tắc giảm thu thập dữ liệu và giới hạn quyền truy cập.

- **Data minimization:** chỉ giữ field phục vụ phát hiện/điều tra có căn cứ; tránh thu thập mật khẩu, token, thông tin thanh toán thô hoặc payload chứa dữ liệu cá nhân không cần thiết.
- **Retention:** lựa chọn thời hạn theo mức rủi ro, nghĩa vụ áp dụng, chi phí và nhu cầu điều tra; công bố cách xử lý backup và xóa dữ liệu khi hết hạn.
- **Regional/tenant boundaries:** nơi lưu và quyền truy cập phải phù hợp phân loại dữ liệu/tenant.
- **Integrity vs privacy:** log bất biến giúp bảo toàn bằng chứng nhưng phải được thiết kế đồng thời với thời hạn lưu và quy trình xóa hợp lệ; không lưu dữ liệu vượt mục đích.
- **Volume/cost:** high-cardinality event có thể làm tăng chi phí; ưu tiên nguồn theo rủi ro, đo chi phí ingest/storage/query và đánh giá tác động của sampling.
- **Resilience:** khi pipeline lỗi, cần chiến lược fail-safe phù hợp: buffer, cảnh báo, điều tra khoảng trống, tái thu thập nếu có thể và giới hạn tuyên bố assurance.
- **Noise management:** cảnh báo có độ ưu tiên thấp có thể được gom, tương quan hoặc xử lý theo đợt; bảo đảm các tín hiệu trọng yếu vẫn đến người trực.

Không nên âm thầm bỏ log security-critical chỉ để giảm chi phí. Mọi quyết định sampling/filtering phải thể hiện trong phạm vi coverage và đánh giá rủi ro.

## 12. Các lỗi thiết kế và đánh giá thường gặp

1. **“Có SIEM tức là có monitoring hiệu quả.”** SIEM chỉ là một thành phần; nguồn, rule, kiểm thử và response mới tạo thành năng lực giám sát.
2. **“Thu thập nhiều log hơn chắc chắn an toàn hơn.”** Event không chuẩn hóa, thiếu actor, quá nhiều noise hoặc rò rỉ secret có thể làm giảm chất lượng và tăng rủi ro.
3. **“Chưa thấy alert tức là không có tấn công.”** Có thể mất nguồn, thiếu rule, lỗi parser hoặc kỹ thuật tấn công nằm ngoài coverage.
4. **“Một detection hit là một incident.”** Phải qua triage, đối chiếu bối cảnh và phân loại.
5. **“Rule hoạt động trong test rồi sẽ luôn hoạt động.”** Source schema, quyền, deployment và người trực thay đổi; cần regression và giám sát health.
6. **“Số alert là KPI tốt nhất.”** Tăng cảnh báo có thể chỉ là noise, trong khi các threat quan trọng vẫn bị bỏ sót.
7. **“Tất cả IP/thời gian đều đáng tin tuyệt đối.”** NAT, proxy, header giả, đồng hồ lệch, late event và ingest backlog dễ gây kết luận sai.
8. **“Log bất biến thì không cần RBAC.”** Người dùng trái phép vẫn có thể đọc PII hoặc hủy khả năng sử dụng dữ liệu qua các đường quản trị khác.
9. **“Chỉ cần test phát hiện, không cần test người trực.”** Alert không được đọc hoặc không thể xử lý đúng thời hạn thì mục tiêu assurance vẫn có thể không đạt.
10. **“False positive nên bị xóa hoàn toàn.”** Việc suppression quá rộng có thể tạo false negative; cần theo dõi trade-off và thời hạn ngoại lệ.

## 13. Checklist triển khai security monitoring có thể kiểm toán

- [ ] Có inventory tài sản, nguồn sự kiện, tenant/environment và mức độ quan trọng cập nhật.
- [ ] Có danh mục detection use case gắn với threat model, rủi ro và security objectives.
- [ ] Mỗi use case chỉ rõ event/field bắt buộc, parser, rule logic, owner, severity và runbook.
- [ ] Nguồn quan trọng có health/heartbeat, parse quality, ingestion delay và cảnh báo mất tín hiệu.
- [ ] Timestamps, actor, target, tenant và correlation ID đáng tin hoặc có nêu giới hạn.
- [ ] Log pipeline và kho chứng cứ có phân quyền, kiểm soát truy cập, integrity và retention phù hợp.
- [ ] Rule quan trọng có positive/negative/boundary/regression tests và kết quả được lưu có phiên bản.
- [ ] Tín hiệu có thể chuyển đến người trực đúng kênh; triage và escalation được diễn tập.
- [ ] Có cách đo coverage, độ trễ, precision, backlog và hiệu quả phản ứng; công thức/mẫu số rõ ràng.
- [ ] Sự cố, false positive, missing data và rule failure đi vào backlog cải tiến có owner/hạn xử lý.
- [ ] Ngoại lệ và alert suppression có phạm vi tối thiểu, phê duyệt, hết hạn và bằng chứng.
- [ ] Sau thay đổi nguồn, schema, rule, ứng dụng hoặc rủi ro phải kiểm tra lại claim liên quan.
- [ ] Có hồ sơ evidence để reviewer độc lập truy vết từ **mục tiêu → kiểm soát → kiểm thử → kết quả → quyết định**.

## 14. Câu hỏi tự đánh giá

1. Security monitoring khác logging thuần túy ở bước nào? Nếu tổ chức giữ được toàn bộ log nhưng không có runbook và người trực, claim phát hiện trong 5 phút có thể đạt không? Vì sao?
2. Khi không thấy event IAM trong 24 giờ, cần kiểm tra những giả thuyết nào trước khi kết luận không có thay đổi quyền?
3. Tại sao canary event đến SIEM trong 2 giây chưa chứng minh rule phát hiện thay đổi RBAC admin có hiệu lực?
4. Nếu một rule có 95% cảnh báo được phân loại là hợp lệ nhưng chỉ bao phủ một phần nhỏ threat model, liệu có thể kết luận khả năng phát hiện đã tốt toàn diện không?
5. Khi thay đổi event schema của IdP, các bước bảo đảm rule vẫn phát hiện chuỗi đăng nhập đáng ngờ gồm những gì?
6. Những bằng chứng nào giúp kiểm toán viên phân biệt “rule được bật” với “rule đã được thử nghiệm và người trực có thể phản ứng”?

**Thông điệp chính:** Security monitoring tạo ra khả năng quan sát và phát hiện rủi ro trong vận hành, nhưng giá trị assurance nằm ở **tính đầy đủ của nguồn, logic phát hiện đã kiểm thử, khả năng phản ứng và bằng chứng có thể tái lập**. Một chương trình trưởng thành phải liên tục đo chính năng lực giám sát của mình, nhận diện điểm mù và chứng minh rằng các phát hiện được xử lý cho đến khi rủi ro được kiểm soát.
