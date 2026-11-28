# IDS/IPS phối hợp với SIEM: từ tín hiệu mạng đến phát hiện và ứng phó sự cố

**IDS (Intrusion Detection System)** phát hiện hoạt động có dấu hiệu xâm nhập và tạo cảnh báo; **IPS (Intrusion Prevention System)** có thể chủ động chặn một số lưu lượng phù hợp với chính sách phát hiện khi được triển khai trên đường truyền và cấu hình hành động tương ứng. **SIEM (Security Information and Event Management)** tiếp nhận, quản lý và tương quan sự kiện từ nhiều nguồn để giúp nhóm bảo mật nhìn thấy bức tranh rộng hơn, điều tra và ưu tiên sự cố.

Khi phối hợp, **IDS/IPS cung cấp quan sát sâu về một số hoạt động mạng**, còn SIEM liên kết những tín hiệu đó với firewall, DNS, VPN, NAC, danh tính, máy chủ, cloud và ứng dụng. Một cảnh báo đơn lẻ không tự chứng minh hệ thống bị xâm nhập; và một bản ghi IPS cho biết đã chặn gói cũng không tự chứng minh toàn bộ cuộc tấn công bị ngăn thành công.

Bài học thuộc chương **IDS và IPS** của module **SECURITY_NETWORK_SECURITY**. Nội dung gắn với các lớp phòng vệ từ phân đoạn mạng, firewall và VPN tới xác thực kết nối, DNS, mạng không dây và hạ tầng đám mây; đồng thời tập trung vào phân tích lưu lượng, threat modeling, giám sát xâm nhập và kiến trúc mạng an toàn.

## 1. Mục tiêu học tập

Hoàn thành bài này, bạn có thể:

1. Phân biệt vai trò của NIDS/NIPS, HIDS/HIPS, firewall, NDR, SIEM và SOAR.
2. Thiết kế tuyến thu thập **sensor → collector → chuẩn hóa → enrichment → correlation → alert/case → ứng phó**, bao gồm bảo vệ độ tin cậy dữ liệu.
3. Xác định những trường log cần thiết để tương quan sự kiện theo **IP/port, thời gian, giao thức, tài sản, danh tính và điểm quan sát**.
4. Phân tích tác động của NAT, proxy, VPN, TLS, HTTP/3/QUIC, lưu lượng east–west và cloud tới khả năng quan sát.
5. Viết quy tắc tương quan có điều kiện, ngưỡng, cửa sổ thời gian, ngoại lệ và bằng chứng điều tra; giảm trùng lặp và cảnh báo sai.
6. Xây dựng playbook xác minh, phân loại, cô lập và khôi phục có kiểm soát; không biến SIEM thành hệ thống tự chặn nguy hiểm.
7. Đề xuất chỉ số đánh giá mức bao phủ, chất lượng cảnh báo, độ trễ, tính sẵn sàng và khả năng kiểm toán.

## 2. IDS, IPS, SIEM và các thành phần liên quan

### 2.1. Cùng phát hiện an ninh nhưng không cùng chức năng

| Thành phần | Câu hỏi nó trả lời | Vị trí và hoạt động thường gặp | Giới hạn |
| --- | --- | --- | --- |
| **NIDS** | Có tín hiệu đáng ngờ trong traffic mạng được quan sát không? | Sensor thụ động qua TAP/SPAN hoặc bản sao traffic; sinh event | Không trực tiếp chặn, chỉ thấy lưu lượng đi qua điểm đặt sensor |
| **NIPS** | Có nên ngăn traffic này theo policy phát hiện không? | Thiết bị inline trên đường đi, có thể drop/reset/chặn theo khả năng nền tảng | Có thể gây gián đoạn khi false positive; cần xử lý HA/failover |
| **HIDS/HIPS** | Có hành vi đáng ngờ hoặc vi phạm policy ở endpoint không? | Agent/kiểm soát trên host, máy ảo hoặc workload | Không thay quan sát luồng mạng ngoài host và phụ thuộc bảo vệ agent |
| **Firewall / Network ACL** | Kết nối hoặc gói tin có được đi qua không? | Ranh giới mạng, host, cloud, subnet | Không nhất thiết phân tích payload và hành vi ở L7 |
| **NDR** | Mẫu lưu lượng và hành vi mạng có bất thường không? | Kết hợp flow, metadata, phân tích hành vi, đôi khi packet | Cần baseline, chất lượng telemetry và triage |
| **SIEM** | Nhiều sự kiện có liên hệ thành một chuỗi rủi ro không? | Nền tảng thu thập, chuẩn hóa, truy vấn, tương quan, cảnh báo và hỗ trợ điều tra | Không tự tạo khả năng quan sát ở nơi chưa có nguồn dữ liệu |
| **SOAR / orchestration** | Bước xử lý nào có thể chuẩn hóa hoặc tự động hóa? | Chạy playbook, mở case, gọi API công cụ bảo mật | Cần phê duyệt, phân quyền và biện pháp ngăn phản ứng sai |

SIEM có thể được tích hợp cùng SOAR/UEBA hoặc sản phẩm có chức năng phát hiện mạng nâng cao. Tuy nhiên, khi thiết kế vẫn cần tách **nguồn quan sát**, **logic phát hiện**, **quyết định ứng phó** và **quyền thực thi**.

### 2.2. Một alert IDS không phải kết luận xâm nhập

Một sensor phát hiện mẫu dữ liệu giống chữ ký tấn công có thể tạo event chứa loại alert, chữ ký, mức ưu tiên và thông tin 5-tuple. Đó là **tín hiệu cần đánh giá**, vì:

- Có thể là traffic độc hại thật; cũng có thể do ứng dụng hợp lệ có payload giống mẫu phát hiện.
- Chữ ký có thể phản ánh **thăm dò** chứ chưa có bằng chứng khai thác thành công.
- Cảm biến có thể chỉ thấy một chiều của kết nối hoặc không quan sát được body đã mã hóa.
- IPS có thể ghi **đã thực hiện hành động chặn** tại vị trí của nó, nhưng kẻ tấn công vẫn có thể có đường khác hoặc request trước đó đã tới đích.

Hãy phân biệt **detection (phát hiện)**, **prevention (chặn một phần lưu lượng)**, **compromise (bị xâm nhập)** và **incident (sự cố cần xử lý theo chính sách tổ chức)**. Không dùng chúng như các trạng thái đồng nghĩa.

### 2.3. Signature và anomaly detection

| Cách phát hiện | Ví dụ tín hiệu | Điểm mạnh | Rủi ro / hạn chế |
| --- | --- | --- | --- |
| Signature / rule-based | Một cấu trúc request hoặc đặc tính protocol trùng quy tắc đã biết | Diễn giải được theo rule ID, thuận tiện triage | Có thể bỏ sót biến thể chưa có chữ ký, phát sinh false positive |
| Protocol anomaly | Bản tin không nhất quán với cấu trúc giao thức dự kiến | Hữu ích để nhận diện giao thức bất thường | Phụ thuộc khả năng parser và tình huống hợp lệ không chuẩn |
| Behavioral / anomaly | Số kết nối, dịch vụ đích, thời điểm hoặc tỷ lệ thất bại khác baseline | Có thể thấy hành vi chưa có chữ ký cố định | Cần baseline chuẩn, dễ bị ảnh hưởng triển khai mới/tải cao |
| Threat intelligence enrichment | IP/domain/file hash có trong danh sách tín hiệu rủi ro được quản lý | Bổ sung ngữ cảnh | IOC có thể cũ, chia sẻ IP/CDN/NAT; không đủ kết luận độc lập |

Kết hợp nhiều loại tín hiệu **chỉ có giá trị nếu hiểu ngữ cảnh và mức tin cậy**. Một IOC trùng địa chỉ IP phổ biến của CDN không nên tự động tạo lệnh chặn một tài sản quan trọng.

## 3. Kiến trúc tham chiếu: IDS/IPS đẩy sự kiện về SIEM

~~~mermaid
flowchart LR
    C["Client / Internet"] --> FW["Firewall biên"]
    FW --> IPS["IPS inline (nếu triển khai)"]
    IPS --> P["Reverse proxy / API"]
    P --> APP["Ứng dụng"]
    APP --> DB[("Database")]
    TAP["TAP / SPAN / Traffic mirroring"] -. "Bản sao traffic" .-> IDS["NIDS passive"]
    FW -. "Firewall / NAT / flow logs" .-> COL["Collector"]
    IPS -. "Event phát hiện và hành động" .-> COL
    IDS -. "Alert / network metadata" .-> COL
    P -. "Proxy / WAF logs" .-> COL
    APP -. "App auth / audit logs" .-> COL
    E["DNS / VPN / NAC / EDR / Cloud logs"] -. "Sự kiện bổ trợ" .-> COL
    COL --> N["Parse, normalize, validate"]
    N --> EN["Enrich: asset, identity, zone, NAT"]
    EN --> S[("SIEM: index và correlation")]
    S --> CASE["Alert / Incident case / SOC"]
    CASE --> R["Ứng phó có kiểm soát"]
    R -. "Thay đổi được phê duyệt" .-> FW
    R -. "Thay đổi được phê duyệt" .-> IPS
~~~

Đường nét liền mô tả luồng nghiệp vụ/điều khiển chính; nét đứt mô tả sự kiện hoặc bản sao traffic. Hình **không có nghĩa một sensor được quyền đọc mọi đoạn mạng**. NIDS chỉ thấy những gói được chuyển tới cổng quan sát hoặc hạ tầng mirroring; một IPS inline chỉ kiểm soát lưu lượng thực sự đi qua điểm chặn.

### 3.1. Vị trí đặt sensor thay đổi nội dung SIEM nhìn thấy

| Vị trí quan sát | Nhìn thấy gì | Những gì dễ bỏ sót |
| --- | --- | --- |
| Trước firewall biên | Traffic tới vùng mạng công khai, kể cả kết nối firewall sẽ chặn về sau | Trạng thái ứng dụng, địa chỉ sau NAT, luồng nội bộ |
| Sau firewall biên | Traffic đi qua chính sách biên và trạng thái/dịch địa chỉ tùy vị trí | Request đã bị chặn trước đó |
| Trước TLS termination tại reverse proxy/WAF | IP/port, phiên TLS, kích thước/nhịp traffic và một phần metadata | Path, header, body HTTPS nếu không giải mã hợp lệ |
| Sau TLS termination, ở điểm được phép | Có thể thấy HTTP rõ hoặc telemetry L7 do proxy tạo | Luồng không đi qua điểm đó; rủi ro lưu dữ liệu nhạy cảm |
| Giữa application subnet và data subnet | East–west, truy cập DB và traffic trong vùng nội bộ nếu đường đi qua sensor | Giao tiếp nội bộ cùng host/virtual switch không mirror |
| Cloud traffic mirroring | Gói được bản sao từ các interface/tài nguyên được hỗ trợ | Phần không được mirror, mất gói, giới hạn dịch vụ cloud |
| Cloud flow log | Tóm tắt luồng IP/port/trạng thái theo nhà cung cấp | Payload HTTP hoặc nội dung đã mã hóa |
| Host/EDR telemetry | Process, tài khoản, kết nối và hành vi endpoint | Traffic trên thiết bị không có agent hoặc không được ghi |

Nên lập **coverage map** nối tài sản và trust boundary với sensor/log source tương ứng. Việc có một NIDS tại đường Internet không chứng minh khả năng phát hiện di chuyển ngang giữa các pod trong cùng node hoặc giữa hai VM trên mạng ảo.

### 3.2. Inline IPS và tính sẵn sàng

Khi đặt IPS trên đường truyền, chính sách có thể quyết định **allow, alert, drop, reject/reset** hoặc hành động khác theo sản phẩm. Dữ liệu sự kiện phải ghi nhận **hành động thực sự** thay vì suy ra từ tên chữ ký.

- **False positive khi chặn** có thể làm gián đoạn thanh toán, DNS, phiên quản trị hoặc lưu lượng nghiệp vụ.
- **Bảng trạng thái, throughput, packet drops và latency** cần được theo dõi khi tải cao.
- **Fail-open/fail-closed** khi thiết bị lỗi là quyết định rủi ro về an toàn và khả dụng; phải phù hợp loại dịch vụ và chính sách tổ chức.
- **High availability** cần test failover và tính nhất quán policy/state, không chỉ chứng minh rằng hai thiết bị đang bật.
- Khi kiểm tra rule IPS, có thể dùng chế độ **alert-only/count** trước nếu nền tảng hỗ trợ, sau đó chuyển chặn sau khi đánh giá.

Nếu hệ thống triển khai NIDS ngoài băng, nó **không thể chặn tức thời chính gói đang quan sát** bằng cách chỉ phát một SIEM alert. Các hành động chặn qua firewall/IPS/API là bước ứng phó riêng, có độ trễ và rủi ro thay đổi.

## 4. Luồng dữ liệu từ sensor tới SIEM

Một pipeline đáng tin không chỉ chuyển log tới một kho dữ liệu. Cần bảo toàn **ngữ nghĩa, thời gian, nguồn gốc, độ đầy đủ và quyền truy cập** để các phép tương quan có giá trị.

~~~mermaid
flowchart LR
    S["IDS / IPS event"] --> T["Transport an toàn và buffer"]
    T --> P["Parser + schema mapping"]
    P --> V{"Validate fields?"}
    V -- "Không" --> Q["Quarantine / dead-letter + cảnh báo"]
    V -- "Có" --> N["Normalize + event time"]
    N --> E["Enrich: CMDB / IAM / zone / NAT / TI"]
    E --> I["Index / data lifecycle"]
    I --> C["Detection / correlation"]
    C --> A["Alert grouping / case"]
    A --> H["Human triage / SOAR được kiểm soát"]
~~~

### 4.1. Collection và transport

Nguồn có thể xuất sự kiện bằng syslog, JSON file, agent, API, message queue hoặc cơ chế cloud-native. Khi thiết kế, phải xác nhận:

1. **Giao thức và bảo vệ đường truyền:** ưu tiên kênh có xác thực và mã hóa khi hỗ trợ, đặc biệt khi log vượt trust boundary.
2. **Buffer và retry:** collector có thể lưu đệm khi SIEM gián đoạn; phải giới hạn dung lượng và có chiến lược xử lý queue đầy.
3. **At-least-once và trùng lặp:** retry có thể đưa cùng event vào nhiều lần; cần cơ chế idempotency/dedup dựa trên ID và nguồn.
4. **Sự kiện bị mất:** thu thập dropped-events, queue depth, parser errors và độ trễ ingest; không coi im lặng là bình thường.
5. **Dung lượng:** tính EPS (events per second), kích thước trung bình, đỉnh tải, băng thông, storage và retention.
6. **Phân vùng bảo mật:** quyền collector, tài khoản ingest, khóa API, đường egress và quyền sửa detector phải được giới hạn.

Không nên gửi toàn bộ PCAP hoặc body HTTP vào SIEM chỉ vì có sẵn. Dữ liệu lớn và nhạy cảm có thể thích hợp trong kho forensic được phân quyền riêng, có thời hạn và quy trình truy cập.

### 4.2. Chuẩn hóa event

IDS/IPS, firewall, DNS và EDR có tên trường khác nhau. SIEM cần một lớp schema chung hoặc mapping rõ ràng; có thể tham khảo **ECS**, **OCSF** hoặc schema riêng có kiểm soát, nhưng không được giả định mọi nhà cung cấp dùng cùng tên field hay cùng cấp severity.

| Trường chuẩn hóa gợi ý | Mục đích | Lưu ý |
| --- | --- | --- |
| event.id / vendor_event_id | Định danh sự kiện để trace, dedup | Có thể không duy nhất giữa các sensor; kết hợp source ID |
| event.time | Thời điểm sự kiện thực sự xảy ra | Có timezone và độ chính xác; khác ingest time |
| ingest.time | Thời điểm SIEM nhận event | Dùng đo pipeline latency, không thay event time |
| observer.id, observer.type, location/zone | Cảm biến nào và đặt ở đâu | Rất quan trọng khi NAT/TLS khiến IP được thấy thay đổi |
| source.ip, source.port | Endpoint nguồn theo **góc nhìn của observer** | Không mặc định là IP gốc của người dùng |
| destination.ip, destination.port | Endpoint đích tại vị trí quan sát | Có thể là địa chỉ trước/sau DNAT, proxy hoặc service VIP |
| network.transport, network.protocol | TCP/UDP/ICMP; HTTP/DNS/TLS nếu có | Giao thức tầng vận chuyển và ứng dụng là hai lớp khác nhau |
| rule.id, rule.name, rule.version | Chữ ký/rule khớp | Phiên bản giúp giải thích thay đổi false positive |
| event.action | Hành động sensor/IPS đã thực hiện | Phải map đúng giá trị vendor, ví dụ alerted/blocked |
| severity / confidence | Mức ưu tiên, độ tin cậy theo mô hình đã định nghĩa | Không tự so số severity khác hệ quy chiếu |
| network.direction / segment | Inbound, outbound, east–west theo ranh giới | Cần mô tả ranh giới và orientation cụ thể |
| asset.id, criticality, owner | Tài sản bị ảnh hưởng và mức quan trọng | Lấy từ CMDB/inventory có ngày cập nhật |
| identity.user / workload.id | Danh tính liên quan đã xác minh | Có thể chỉ suy ra gián tiếp; đánh dấu nguồn và độ tin cậy |
| case.id, correlation.id | Gom nhóm diễn biến | Tránh nhân đôi incident từ nhiều event cùng phiên |

Các trường nêu trên là **mô hình minh họa**. Hãy giữ bản raw event để kiểm tra khi mapping không rõ, nhưng bảo vệ raw log vì có thể chứa IP cá nhân hoặc nội dung nhạy cảm. Không đổi giá trị hành động "alert" thành "blocked" chỉ vì hệ thống là một IPS.

### 4.3. Sự kiện IDS/IPS mẫu

JSON sau là **dữ liệu giả phục vụ bài học**, gần với cách một số sensor xuất sự kiện nhưng **không khẳng định là schema gốc của Suricata, Snort hoặc nền tảng SIEM cụ thể**:

~~~json
{
  "event_id": "sensor-a-000184",
  "event_time": "2026-03-10T08:15:22.120Z",
  "sensor": {"id": "nids-dmz-01", "zone": "dmz", "mode": "passive"},
  "event_type": "network_alert",
  "source": {"ip": "198.51.100.25", "port": 54000},
  "destination": {"ip": "10.30.20.10", "port": 443},
  "network": {"transport": "tcp", "direction": "inbound"},
  "rule": {"id": "LAB-2001", "name": "LAB suspicious request pattern"},
  "severity": "medium",
  "action": "alerted",
  "flow_id": "flow-481",
  "http": {"method": "GET", "route_template": "/v1/orders/{id}"}
}
~~~

Ở đây dùng **dải TEST-NET dành cho ví dụ** 198.51.100.0/24 để không chỉ vào người dùng thật. Mặc dù event có trường http, một NIDS nhìn thấy HTTPS trước TLS termination có thể **không có** method và route. Các trường L7 chỉ hợp lệ nếu điểm quan sát/nguồn log thực sự nhìn thấy chúng; không được tự dựng dữ liệu HTTP từ một flow chỉ có IP/port.

Ví dụ IPS xử lý cùng một mẫu có thể có event khác:

~~~json
{
  "event_id": "ips-edge-000185",
  "event_time": "2026-03-10T08:15:22.128Z",
  "sensor": {"id": "nips-edge-01", "zone": "edge", "mode": "inline"},
  "rule": {"id": "LAB-2001", "name": "LAB suspicious request pattern"},
  "source": {"ip": "198.51.100.25", "port": 54000},
  "destination": {"ip": "203.0.113.10", "port": 443},
  "network": {"transport": "tcp"},
  "action": "blocked",
  "result_scope": "matching_packet_or_flow_at_this_enforcement_point"
}
~~~

Event IPS trên dùng **địa chỉ đích công khai**, còn event NIDS dùng **địa chỉ nội bộ**; đây là ví dụ hai vị trí sensor ở hai phía DNAT. Không gộp theo IP đích đơn thuần rồi kết luận hai event không liên quan. Trái lại, cũng không kết luận chúng chắc chắn là cùng một luồng nếu thiếu mapping/timestamp/flow evidence.

### 4.4. Enrichment: bổ sung ngữ cảnh mà không làm sai bằng chứng

Một event network ban đầu chỉ cho biết một kết nối và một tín hiệu. SIEM có thể bổ sung:

- **CMDB/asset inventory:** host nào đang dùng IP, vai trò web/database, mức quan trọng, owner.
- **NAT mapping / proxy logs:** địa chỉ/cổng gốc và đã dịch, IP client tin cậy, request/trace ID.
- **Identity / VPN / NAC:** người dùng hoặc thiết bị gắn với địa chỉ tại một thời điểm; phải xét lease và thời điểm phiên.
- **DNS:** tên miền được truy vấn và thời điểm, không đồng nghĩa một IP kết nối luôn thuộc tên miền đó.
- **Vulnerability/patch inventory:** tài sản có phiên bản hoặc điểm yếu liên quan tới chữ ký không; inventory có đủ mới không?
- **Threat intelligence:** IOC, confidence, nguồn, độ mới, thời hạn còn giá trị và rủi ro IP dùng chung.
- **Zone/sensitivity:** luồng đi vào vùng nào, qua trust boundary nào, có dữ liệu nhạy cảm không?

**Dữ liệu enrichment có thể lỗi thời**. Phải lưu provenance, thời gian snapshot và mức tin cậy; không ghi đè IP gốc trong event bằng một bản suy luận không kiểm chứng.

## 5. Correlation: ghép tín hiệu thành phát hiện có ngữ cảnh

SIEM phát huy lợi ích khi kết hợp những dấu hiệu **có quan hệ thời gian, tài sản hoặc danh tính** để hỗ trợ quyết định. Tuy nhiên, tăng số nguồn trong một rule không tự động làm rule chính xác: một phép join sai có thể tạo rất nhiều false positive.

### 5.1. Ba cấp độ logic

| Cấp độ | Ví dụ | Ưu / nhược điểm |
| --- | --- | --- |
| **Sự kiện đơn** | Một rule IDS ưu tiên cao khớp trên kết nối tới ứng dụng quan trọng | Nhanh, dễ hiểu nhưng thiếu xác nhận ngữ cảnh |
| **Lặp lại / chuỗi** | Nhiều event liên quan tới cùng source và tài sản trong cửa sổ thời gian | Giảm một số nhiễu hoặc thấy chuỗi hành vi; cần threshold và dedup |
| **Đa nguồn** | IDS alert + firewall allow + authentication bất thường + telemetry endpoint | Củng cố hoặc phủ định giả thuyết; yêu cầu chuẩn hóa thời gian và identity |

Một kịch bản điển hình: SIEM nhận event IDS về traffic bất thường tới cổng ứng dụng; tra firewall thấy kết nối **được cho phép**; log reverse proxy có request tương ứng; ứng dụng trả mã lỗi liên quan đến quyền; EDR không ghi nhận process bất thường. Kết luận phù hợp có thể là **đã có hành vi nghi vấn nhưng chưa có bằng chứng xâm nhập thành công**. Nếu EDR/ứng dụng cung cấp thêm bằng chứng thực thi hoặc truy cập dữ liệu bất thường, mức ưu tiên điều tra sẽ khác.

### 5.2. Kịch bản tương quan mẫu theo use case

| Use case | Nguồn tối thiểu | Điều kiện gợi ý | Giá trị điều tra |
| --- | --- | --- | --- |
| Thăm dò nhiều dịch vụ trong vùng nội bộ | NIDS/flow log + asset inventory | Nhiều kết nối không thường lệ từ một workload tới nhiều đích hoặc cổng trong cửa sổ hợp lý | Nhận diện lateral movement tiềm năng, phân biệt job quản trị hợp lệ |
| IDS alert + phiên được phép qua firewall | IDS + firewall + NAT map nếu cần | Trùng dòng kết nối theo 5-tuple hoặc mapping cùng thời gian | Biết request có đi tới vùng được bảo vệ hay đã bị firewall chặn |
| Kết nối lạ tới DB từ vùng web | NIDS/flow log + segmentation policy | Workload web liên lạc trực tiếp DB ngoài allowlist | Review phân đoạn và tài khoản DB, không dựa vào IDS chữ ký duy nhất |
| DNS nghi vấn + kết nối egress tiếp theo | DNS resolver + flow/IDS + endpoint | Truy vấn tên miền hiếm hoặc bị đánh dấu và kết nối liên quan trong khoảng thời gian hợp lý | Tăng ngữ cảnh, vẫn cần kiểm tra shared resolver và CDN |
| Nhiều lần xác thực thất bại và phiên VPN bất thường | VPN/auth + NAC/identity + IDS | Tài khoản/thiết bị có sự kiện đăng nhập và network pattern đáng chú ý | Xem nguồn truy cập, MFA, tài khoản và phiên VPN |
| API có alert và phản hồi lỗi | WAF/IDS + proxy/app log | Request ID hoặc flow gần nhau, nhiều lỗi 4xx/5xx trên endpoint nhạy cảm | Phân biệt blocked ở edge, lỗi ứng dụng và khai thác thành công |
| Egress bất thường từ server có giá trị cao | Flow log/IDS + CMDB + firewall | Destination hoặc lưu lượng mới lạ so với policy được duyệt | Kiểm tra backup, deploy, monitoring trước khi nghi exfiltration |
| IPS chặn lặp lại nhưng sensor sau IPS vẫn thấy traffic | IPS event + NIDS phía sau + flow log | Cùng nguồn/đích/phiên có dấu vết tiếp diễn ngoài kỳ vọng | Xác minh phạm vi rule, failover, bypass, vị trí sensor và timing |

**Mọi ngưỡng đều cần hiệu chỉnh theo tổ chức**: 20 request/phút có thể là bất thường với API quản trị nhưng bình thường với API health check. Chọn cửa sổ và số lần dựa trên traffic baseline, tính đặc thù của tài sản và chi phí điều tra.

### 5.3. Quy tắc tương quan mẫu, không phụ thuộc sản phẩm

Ví dụ: đánh dấu trường hợp **sensor DMZ cảnh báo** và **firewall đã cho phép** một luồng tới tài sản quan trọng. Đây là **pseudo rule** để thảo luận, không phải query chạy được trên một SIEM cụ thể:

~~~yaml
detection_id: DET-IDS-FW-001
title: Network alert on allowed connection to critical asset
sources:
  - ids_alerts
  - firewall_connection_events
  - asset_inventory
join_requirements:
  - normalized_source_and_destination_after_nat_resolution
  - matching_transport_protocol_and_ports_if_available
  - event_time_within_seconds: 120
conditions:
  ids_rule_category: requires_investigation
  firewall_decision: allowed
  asset_criticality: high
group_by:
  - asset_id
  - source_workload_or_client_identity
  - ids_rule_id
window_minutes: 10
output:
  - case_with_raw_event_links
  - timeline
  - observed_actions
response: analyst_triage_before_any_network_block
~~~

Ở đây khoảng 120 giây và cửa sổ 10 phút **chỉ là tham số minh họa**. Cần điều chỉnh dựa trên độ chính xác đồng hồ, độ trễ ingest, định danh phiên và khả năng mất dữ liệu. Không tự động liên kết hai event chỉ vì trùng IP nguồn khi IP đó là NAT gateway dùng chung.

### 5.4. Tránh lỗi khi ghép sự kiện

- **Join theo đúng điểm nhìn:** phân biệt nguồn/đích tại vị trí IDS, IPS, firewall, proxy; dùng NAT mapping khi có.
- **Join theo thời gian sự kiện:** event.time có thể đến SIEM muộn; tránh chỉ dùng ingest.time cho logic chuỗi.
- **Join theo identity khi cần:** user, thiết bị, workload/service account, không chỉ IP động của VPN, DHCP hoặc Kubernetes pod.
- **Dedup trước khi đếm:** hai sensor hoặc cơ chế retry có thể sinh nhiều bản ghi cho cùng một hiện tượng.
- **Đánh dấu thiếu dữ liệu:** nếu firewall log chưa tới hoặc collector đang lỗi, không kết luận “firewall không ghi nhận” là bằng chứng bị chặn.
- **Không khẳng định thành công:** status HTTP, network connection và alert signature không tự chứng minh dữ liệu đã bị lộ hoặc mã độc đã chạy.
- **Giữ bằng chứng raw và mapping:** để SOC có thể xem lại vì sao correlation được tạo.

## 6. Những điều kiện mạng làm sai lệch tương quan

### 6.1. NAT, proxy, VPN và IP động

Giả sử một client từ VPN dùng **10.50.8.42:51620** gọi ứng dụng công khai thông qua NAT:

~~~text
Tại client sau VPN: 10.50.8.42:51620  -> 203.0.113.10:443 TCP
Sau SNAT tại gateway: 198.51.100.20:40071 -> 203.0.113.10:443 TCP
Sau DNAT tại firewall dịch vụ: 198.51.100.20:40071 -> 10.30.20.10:8443 TCP
Reverse proxy tạo kết nối mới: 10.30.20.10:60320 -> 10.30.30.10:8443 TCP
~~~

Đây là một chuỗi **minh họa**, không phải mọi hệ thống đều có đủ bốn chặng. Các dải 198.51.100.0/24 và 203.0.113.0/24 thuộc TEST-NET dành cho tài liệu.

Nhìn từ từng điểm, SIEM có thể nhận **các cặp IP/port khác nhau**:

| Nguồn log | IP nguồn có thể thấy | IP đích có thể thấy | Dữ liệu cần bổ sung |
| --- | --- | --- | --- |
| VPN gateway | 10.50.8.42 hoặc IP ngoài của client tùy vị trí | Endpoint được gọi | User/session/lease, thời điểm |
| Firewall sau SNAT | 198.51.100.20:40071 | 203.0.113.10:443 | Mapping IP/port nguồn trước dịch |
| IDS trong DMZ sau DNAT | 198.51.100.20:40071 | 10.30.20.10:8443 | Mapping đích trước dịch và vị trí sensor |
| Reverse proxy log | IP của gateway/proxy upstream | Host/path ứng dụng | Verified client IP, request ID |
| API log | 10.30.20.10 (IP proxy) | Backend API | Trace ID, principal đã xác thực |

Nếu tương quan chỉ bằng source.ip, hệ thống có thể **gộp nhầm mọi người dùng VPN vào một IP NAT** hoặc tách một hành vi thành nhiều nguồn độc lập. Cần lưu original/translated 5-tuple, timestamp, observer ID, flow/request ID và **độ tin cậy của phép gán danh tính**.

Một DNS resolver hoặc proxy chung cũng tạo bài toán tương tự: IP của resolver không phải luôn là IP của client đã yêu cầu truy vấn. Khi phân tích DNS, hãy hiểu log được tạo ở recursive resolver, forwarder, stub resolver hay endpoint agent.

### 6.2. Thời gian và cửa sổ tương quan

Các nguồn log có thể dùng:

- Timestamp theo UTC hoặc múi giờ khác.
- Độ chính xác tới giây, mili-giây hoặc ít hơn.
- Event time và receive time khác nhau vì hàng đợi, mất kết nối hoặc xử lý batch.
- Đồng hồ bị lệch do NTP sai hoặc host không đồng bộ.

Nên chuẩn hóa lưu trữ thời điểm về **UTC**, giữ dấu vết timezone gốc khi cần, đồng bộ thời gian cho sensor/gateway/collector và giám sát **clock skew**. Với correlation streaming, thiết kế cơ chế xử lý **late-arriving events** và cập nhật case sau khi log tới muộn nếu SIEM hỗ trợ.

Ví dụ: IDS event lúc 08:15:20Z nhưng firewall event tương ứng nhận vào SIEM lúc 08:17:00Z. Nếu correlation yêu cầu hai sự kiện **cùng phút ingest**, nó có thể bỏ lỡ chuỗi dù event time của chúng chỉ cách nhau vài giây.

### 6.3. TLS, HTTPS và HTTP/3/QUIC

NIDS thụ động đứng ngoài đường giải mã HTTPS thường nhìn thấy **IP, cổng, thời gian, kích thước/nhịp gói và một phần metadata giao thức**, nhưng không đọc được HTTP path, cookie hoặc body đã mã hóa. Với HTTPS ở reverse proxy/WAF, việc đưa **application audit log hoặc proxy request metadata được làm sạch** vào SIEM có thể bổ sung ngữ cảnh mà NIDS không thấy.

Các lưu ý:

- **HTTP/3 chạy qua QUIC trên UDP**, thông thường dùng UDP/443; một sensor/filter chỉ theo dõi TCP/443 có thể bỏ sót một phần traffic.
- **TLS 1.3** và các cơ chế như ECH khi có hỗ trợ có thể hạn chế metadata mà sensor mạng đọc được; đừng dựa vào một trường TLS không luôn xuất hiện làm điều kiện phát hiện duy nhất.
- Nếu dùng **TLS inspection**, điểm giải mã trở thành khu vực xử lý dữ liệu nhạy cảm; cần quyền truy cập, kiểm soát khóa, thông báo/chính sách pháp lý và giới hạn retention thích hợp.
- Nếu WAF/reverse proxy kết thúc TLS, SIEM cần phân biệt **client–edge**, **edge–backend** và các kết nối mới do proxy tạo; không gộp tùy ý chỉ bằng 5-tuple.
- Với **VPN** có mã hóa, sensor ngoài tunnel có thể chủ yếu thấy đường hầm; muốn quan sát nội dung đã giải mã cần cảm biến/log tại đầu tunnel hoặc endpoint có quyền phù hợp.

Không “đoán” nội dung packet đã mã hóa bằng mô tả chữ ký. Một network signature gắn với TLS metadata có thể là tín hiệu rủi ro, nhưng cần bằng chứng từ endpoint, proxy hoặc ứng dụng khi xác minh hành vi ở tầng HTTP.

### 6.4. IPv6, DNS, Wi-Fi và các mạng phân đoạn

Một mạng dual-stack có thể để gói IPv6 đi theo đường khác với IPv4. Nếu SIEM chỉ nhận log firewall IPv4, coverage chưa hoàn chỉnh. Tương tự, traffic trong cùng VLAN, cùng node Kubernetes hoặc cùng vùng cloud có thể không đi qua sensor biên.

Đối với **Wi-Fi và NAC/802.1X**, thông tin gắn một IP với thiết bị/người dùng thường có hiệu lực **theo thời điểm đăng nhập, cấp DHCP lease, chuyển VLAN hoặc roaming**. Phải xét thời gian hợp lệ của mapping khi SIEM nối alert IDS với danh tính người dùng.

Với **DNS over TLS/HTTPS**, resolver hoặc endpoint có thể thấy dữ liệu chi tiết hơn sensor trên đường truyền; các chính sách DNS, quyền xem log và yêu cầu riêng tư phải được cân nhắc. **DNSSEC** hỗ trợ xác thực dữ liệu DNS, không làm truy vấn tự mã hóa.

### 6.5. Packet loss, asymmetric routing và sensor blind spot

NIDS sử dụng SPAN/TAP hoặc traffic mirroring có thể gặp **mất gói**, thiếu một chiều kết nối, traffic đi đường dự phòng hoặc không đủ throughput để giải mã protocol. Hậu quả là parser gặp incomplete stream và SIEM tạo sự kiện thiếu dữ liệu.

Các biện pháp vận hành gồm:

1. Theo dõi **sensor packet drops, decoder errors, interface saturation, flows observed**.
2. Vẽ **đường đi/đường về thực tế** và route dự phòng, đặc biệt qua ECMP, LAG, firewall HA và cloud.
3. Kiểm tra nguồn bản sao traffic có hỗ trợ **cả chiều vào và chiều ra** theo yêu cầu không.
4. Phân tích TLS termination và các vùng chưa có cảm biến; bổ sung flow/host/endpoint telemetry nếu cần.
5. Giữ trường **data_quality/coverage** cho case khi một nguồn chưa có hoặc đang giảm chất lượng.

Không nên đưa ra kết luận “không có dấu hiệu” khi thực chất **không có đủ quan sát**.

## 7. Điều chỉnh rule để giảm nhiễu mà không mất phát hiện

Một SIEM tiếp nhận rất nhiều event sẽ không hữu ích nếu mỗi lần cùng một mẫu packet lại mở một incident riêng. Tuning phải giảm công việc không cần thiết nhưng **giữ khả năng phát hiện tín hiệu có ý nghĩa**.

### 7.1. Những nguồn false positive phổ biến

| Nguyên nhân | Ví dụ | Điều chỉnh an toàn |
| --- | --- | --- |
| Ứng dụng hợp lệ giống chữ ký | Query search có chuỗi hoặc cú pháp giống mẫu rủi ro | Xác minh request và route, điều chỉnh rule theo tham số/đích cụ thể |
| Scanner hoặc job quản trị được phê duyệt | Hệ thống quét lỗ hổng tạo nhiều kết nối | Gắn asset và lịch bảo trì; tạo ngoại lệ theo identity và khoảng thời gian có hạn |
| Nguồn dùng chung IP | Proxy, CGNAT, VPN gateway, NAT egress | Dùng danh tính client/tài sản và mapping tin cậy, không chỉ IP |
| Dịch vụ cập nhật hoặc CDN | Kết nối đến nhiều IP hoặc miền mới | Đối chiếu chứng cứ ứng dụng, allowlist có thời hạn, không chặn một dải CDN rộng theo suy đoán |
| Rule signature thay đổi | Một bản cập nhật tạo nhiều alert mới | Theo dõi rule version, baseline và tỷ lệ sự kiện sau rollout |
| Event bị gửi trùng | Retry collector hoặc nhiều sensor cùng nhìn một phiên | Dedup theo source/event ID/flow và grouping theo case |
| Ranh giới chưa rõ | Alert đến từ sensor nhìn traffic trước firewall, dù packet đã bị chặn | Enrich điểm quan sát và firewall action |
| DNS/identity mapping lỗi thời | Một địa chỉ IP được cấp cho chủ thể khác | Gắn timestamp, lease/session ID và mức tin cậy |

### 7.2. Quy trình tune một detection

1. **Xác định mục đích rule:** threat scenario nào, dữ liệu nào cho phép xác minh?
2. **Thu thập baseline:** phân phối sự kiện theo nguồn, đích, giờ/ngày, asset, phiên bản rule và hành động IPS.
3. **Lấy mẫu sự kiện đã xác minh:** phân loại true positive, benign positive, false positive hoặc không đủ dữ liệu; tránh coi mọi event chưa điều tra là false positive.
4. **Thử điều chỉnh nhỏ:** scoped exception, ngưỡng/cửa sổ thời gian, thêm dữ liệu enrichment, tách policy theo vùng.
5. **Replay bằng dữ liệu synthetic hoặc corpus đã được phê duyệt:** xác minh các tình huống mong đợi vẫn tạo alert và traffic hợp lệ không bị chặn nhầm.
6. **Theo dõi sau triển khai:** detection volume, false-positive rate, missed detections khi có ground truth, MTTD/MTTR và workload của SOC.
7. **Ghi quyết định:** rule owner, phiên bản, lý do, mức rủi ro còn lại và thời hạn rà lại.

**Không nên bỏ qua toàn bộ chữ ký từ một subnet lớn** chỉ vì một ứng dụng hợp lệ tạo nhiều alert. Ngoại lệ rộng làm mất coverage đối với hành vi thật sự bất thường trong subnet đó.

### 7.3. Gộp cảnh báo, suppress và risk scoring

Có thể gom 200 IDS events vào một case khi chúng cùng nguồn đã xác minh, đích, loại hành vi và cửa sổ thời gian thích hợp. Case vẫn lưu **số lượng sự kiện, thời điểm đầu/cuối và liên kết raw logs**, để tránh làm mất dấu hiệu tăng tần suất.

Rủi ro được đánh giá trên nhiều chiều:

| Chiều | Câu hỏi |
| --- | --- |
| Mức quan trọng của tài sản | Dữ liệu/ứng dụng có độ nhạy cảm ra sao? |
| Mức tin cậy của detection | Chữ ký và nguồn telemetry có độ tin cậy nào? |
| Tác động quan sát được | Traffic chỉ bị chặn hay đã vào ứng dụng? Có bằng chứng thực thi/truy cập dữ liệu không? |
| Quyền và phơi nhiễm | Đích là cổng công khai, máy chủ quản trị, DB hay workload nội bộ? |
| Tính lặp lại và chuỗi hành vi | Có nhiều bước liên quan và tăng cường tín hiệu qua thời gian không? |
| Hành động phòng vệ hiện có | IPS đã chặn gói nào? Firewall/EDR đã cô lập host hay chưa? |
| Chất lượng dữ liệu | Có thiếu flow log/NAT map, lệch đồng hồ hoặc mất packet không? |

Ví dụ **chỉ dùng để thảo luận**: một IDS alert mức medium tới database từ vùng web có thể cần ưu tiên hơn nhiều alert mức high đến một dịch vụ public được IPS chặn ngay tại edge. Tuy nhiên, không xem IPS block là bảo đảm tuyệt đối; vẫn cần kiểm tra các dấu vết liên quan.

### 7.4. Không coi chỉ số nhiều alert là thành tích

Thước đo có ý nghĩa gồm **tỷ lệ alert được xác minh có giá trị**, thời gian từ sự kiện đến phát hiện, thời gian xác minh/ứng phó, phần trăm tài sản có coverage, độ trễ nhận log, dữ liệu bị mất và mức ảnh hưởng dịch vụ. Số alert cao có thể phản ánh một đợt tấn công, nhưng cũng có thể do rule lỗi hoặc ingestion trùng.

## 8. Triage và điều tra theo playbook SOC

### 8.1. Các bước tối thiểu

Khi SIEM tạo một case liên quan IDS/IPS:

1. **Xác minh sự kiện có thật và thuộc phạm vi:** rule ID, signature, thời điểm, sensor, phiên bản policy, nguồn, đích và hành động ghi nhận.
2. **Tìm bằng chứng liên quan:** firewall/NAT, DNS, VPN/NAC, WAF/reverse proxy, authentication, EDR và cloud audit theo cửa sổ phù hợp.
3. **Xác định reachability:** request tới đâu? Đã bị IPS chặn ở điểm nào? Có lưu lượng phía sau điểm chặn không? Có đường bypass không?
4. **Xác định tài sản và chủ thể:** CMDB, phiên VPN, user/host/workload identity; ghi mức tin cậy khi chỉ suy ra theo IP.
5. **Đánh giá khả năng tác động:** endpoint có lỗ hổng liên quan không, API có log lỗi/truy cập dữ liệu bất thường không, có tín hiệu thực thi hoặc thay đổi cấu hình không?
6. **Phân loại:** benign/false positive, suspicious needing monitoring, confirmed incident, hoặc insufficient evidence; ghi căn cứ.
7. **Ứng phó theo phê duyệt:** ví dụ điều chỉnh chặn một nguồn cụ thể, cô lập workload hoặc thu hồi session/token theo playbook.
8. **Kiểm chứng và đóng case:** kiểm tra không còn tín hiệu bất thường, dịch vụ hợp lệ hoạt động, bảo toàn bằng chứng và cập nhật detection.

### 8.2. Sơ đồ xử lý

~~~mermaid
flowchart TD
    A["SIEM correlation tạo case"] --> B["Kiểm tra raw event và data quality"]
    B --> C{"Có đủ dữ liệu và đúng phạm vi?"}
    C -- "Không" --> C1["Bổ sung log / điều tra telemetry gap"]
    C -- "Có" --> D["Enrich asset, NAT, identity, firewall action"]
    D --> E{"Có bằng chứng xâm nhập?"}
    E -- "Chưa rõ" --> E1["Điều tra app / endpoint / flow tiếp theo"]
    E -- "Có" --> F["Phân loại sự cố và mức độ ưu tiên"]
    E -- "Không" --> G["Đánh giá benign hoặc false positive"]
    F --> H["Phê duyệt hành động cô lập / thu hồi / ngăn chặn"]
    H --> I["Thực thi, xác minh an toàn, lưu bằng chứng"]
    I --> J["Review rule, cập nhật playbook và khôi phục"]
    G --> J
    C1 --> J
    E1 --> D
~~~

Trong thực tế, tùy mức độ nghiêm trọng tổ chức có thể triển khai một số bước khống chế nhanh song song với điều tra, nhưng cần có **chủ thể chịu trách nhiệm, phạm vi, dấu vết hành động và cách hoàn tác**. Sơ đồ chỉ là mô hình làm việc, không thay chính sách ứng cứu sự cố được phê duyệt.

### 8.3. Playbook ví dụ: IDS phát hiện traffic lạ từ Web đến DB

**Tình huống:** NIDS trong mạng ứng dụng ghi nhận Web API gọi đến DB trên TCP/5432 dù kiến trúc chỉ cho phép Orders API truy cập DB.

| Bước | Hành động | Bằng chứng / quyết định |
| --- | --- | --- |
| 1 | Xác minh NIDS thực sự nhìn thấy TCP/5432 từ Web tới DB | Raw event, observer zone, thời điểm, 5-tuple |
| 2 | Kiểm tra ACL/segmentation và flow log | Kết nối đã bị chặn hay vẫn được allow? Có đường khác không? |
| 3 | Xác định chính xác Web API workload | Asset/namespace/VM, identity, IP tại thời điểm |
| 4 | Tra app/EDR telemetry | Process nào khởi tạo, job nào chạy, log thay đổi deployment |
| 5 | So với ma trận luồng được duyệt | Có thay đổi nghiệp vụ chưa cập nhật hay đây là vi phạm policy? |
| 6 | Nếu nghi xâm nhập, xử lý theo mức độ | Thảo luận isolation có giới hạn, thu thập bằng chứng, bảo vệ DB |
| 7 | Kiểm thử lại | Web → DB bị chặn; Orders API → DB vẫn hoạt động |
| 8 | Cập nhật detection | Điều chỉnh rule và coverage map, ghi owner và kết luận |

Không mặc định kết nối tới DB đã tạo truy vấn hoặc tiết lộ dữ liệu. Nếu log DB có truy cập bằng tài khoản ứng dụng và bản ghi query, đó là bằng chứng cần đánh giá ở lớp khác.

### 8.4. Playbook ví dụ: IPS liên tục chặn traffic Internet

Khi IPS báo chặn hàng nghìn packet từ nhiều địa chỉ tới reverse proxy:

1. Kiểm tra **hành động thực tế** và phạm vi chặn (gói, phiên hoặc policy tùy sản phẩm).
2. Đối chiếu WAF, firewall, reverse proxy và kết quả giao dịch của người dùng.
3. Phân tích source distribution, signature, phiên bản rule, thời điểm update chữ ký và sự kiện thay đổi cấu hình.
4. Nếu có **false positive** với request hợp lệ, điều chỉnh đúng chữ ký/vùng/endpoint; không tự động tắt toàn bộ IPS.
5. Nếu là traffic đáng ngờ nhưng đã bị chặn, tiếp tục quan sát đường bypass, origin, IPv6 và dấu hiệu traffic tới hệ thống khác.
6. Kiểm tra khả năng xử lý IPS/HA và nguy cơ ảnh hưởng availability; tạo case/ticket theo mức ưu tiên.

### 8.5. Phản ứng tự động qua SIEM/SOAR

Những thao tác mức rủi ro thấp như **đính kèm evidence, mở ticket, làm giàu IOC, thông báo SOC** thường phù hợp cho tự động hóa có kiểm soát. Những thao tác **chặn IP, đổi ACL, cô lập VM/pod, thu hồi tài khoản** có thể ảnh hưởng người dùng và dịch vụ; nên có guardrail:

- Xác thực nguồn event, chống trường do attacker tự khai và kiểm tra confidence.
- Không chặn các IP dùng chung (proxy, NAT egress, CDN, DNS resolver) chỉ từ một alert đơn.
- Có allowlist tài sản quan trọng và các ngoại lệ được review; kiểm soát quyền automation.
- Thiết lập **scope, thời hạn, số lượng hành động tối đa và rollback**; tránh khóa chính hệ thống quản trị, DNS hoặc SIEM.
- Ghi **người/logic phê duyệt, hành động, thời điểm, kết quả và dấu vết thay đổi**.
- Tách rõ quyền **đề xuất** và quyền **thực thi**; có review thủ công cho hành động ảnh hưởng lớn.

Một kịch bản đáng lo là attacker tạo traffic hoặc sự kiện có dữ liệu giả để kích hoạt **phản ứng chặn tự động sai mục tiêu**. SIEM cần xử lý log như **dữ liệu không đáng tin**, tránh lấy nguyên văn trường người dùng kiểm soát để tạo lệnh quản trị.

## 9. Vận hành pipeline IDS/IPS–SIEM đáng tin cậy

### 9.1. Kiểm soát khả dụng và tính đầy đủ

Một pipeline có thể **hoạt động về giao diện** nhưng vẫn thất bại âm thầm khi collector không nhận log, parser loại bỏ một trường quan trọng, time skew tăng hoặc hàng đợi đầy. Vì thế cần giám sát chính hệ thống giám sát:

| Nhóm chỉ số | Ví dụ | Tín hiệu cần xử lý |
| --- | --- | --- |
| Sensor health | Uptime, memory/CPU, packet drop, decoder errors | Sensor mất gói hoặc ngừng phát log |
| Network tap/mirror | Tỷ lệ gói được mirror, interface utilization, luồng qua đường dự phòng | NIDS chỉ thấy một phần traffic hoặc một chiều kết nối |
| Transport | Queue depth, retry count, failures, buffer capacity | Nguy cơ log đến muộn hoặc bị mất |
| Parser | Invalid schema, trường bắt buộc thiếu, dead-letter count | Correlation dùng thông tin sai hoặc mất event |
| Time | Event-to-ingest delay p50/p95, clock skew | Cửa sổ tương quan không còn đáng tin |
| Ingestion | EPS theo sensor, bytes/s, event gap theo nguồn | Nguồn im lặng bất thường, ingest trùng hoặc thiếu |
| Detection | Rule execution errors, alert count theo version, case grouping | Rule hỏng, false positive tăng đột biến |
| SOC | Case backlog, time to acknowledge/triage, false-positive reason | Điều tra chậm, không theo kịp sự kiện |
| Enforcement | IPS block rate, session/resource utilization, failover events | Tác động tới traffic hợp lệ hoặc mất khả năng ngăn chặn |

Thiết kế một **heartbeat/health event** từ sensor và collector để phân biệt “không có alert” với “không có dữ liệu”. Nếu nguồn không phát heartbeat hoặc EPS bất thường so với baseline, SOC cần nhận cảnh báo sức khỏe pipeline.

### 9.2. Tính dung lượng và thời hạn lưu

Giả sử một lab có 10 sensor, mỗi sensor sinh trung bình **200 event/giây**, mỗi event sau chuẩn hóa chiếm **800 byte**. Khi đó:

~~~text
Số event trung bình:
10 sensor × 200 EPS = 2.000 EPS

Dữ liệu thô lý thuyết mỗi giây:
2.000 × 800 B = 1.600.000 B/s ≈ 1,6 MB/s (decimal)

Dữ liệu thô lý thuyết mỗi ngày:
1.600.000 × 86.400 = 138.240.000.000 B ≈ 138,24 GB/ngày
~~~

Đây là **bài tính minh họa**, chưa tính index, metadata, replication, compression, burst, lưu trữ phân tầng hoặc backup. Nếu traffic tăng đột biến 5–10 lần, collector/SIEM phải có chiến lược chịu tải thay vì âm thầm xóa alert quan trọng.

Một cách quản lý dữ liệu:

- **Hot data:** các sự kiện gần đây phục vụ correlation/triage; tối ưu truy vấn và dung lượng theo nhu cầu.
- **Warm/cold data:** dữ liệu lịch sử đã giảm mức truy cập, dùng cho điều tra hồi cứu và phân tích xu hướng.
- **Forensic artifacts:** PCAP hoặc log có nội dung nhạy cảm, chỉ giữ theo yêu cầu và phân quyền riêng.
- **Retention:** xác định theo phân loại dữ liệu, nhu cầu điều tra, yêu cầu pháp lý/chính sách và chi phí; không mặc định lưu mọi loại dữ liệu vĩnh viễn.

Không xóa nguyên vẹn bản ghi làm mất bằng chứng cần thiết chỉ vì muốn giảm dung lượng. Ngược lại, lưu toàn bộ HTTP body, token hoặc credentials dài hạn cũng có thể tạo một **rủi ro Information disclosure** mới.

### 9.3. Bảo vệ SIEM và danh tính vận hành

SIEM tập trung dữ liệu từ nhiều vùng và thường nắm thông tin nhạy cảm về hạ tầng, tài khoản, địa chỉ IP và hành vi người dùng. Cần:

- **RBAC/IAM và MFA:** tách quyền đọc log, sửa detection, quản lý connector, xuất dữ liệu và thực thi playbook.
- **Mã hóa truyền/lưu trữ:** bảo vệ kênh sensor–collector–SIEM và vùng lưu log theo mức rủi ro.
- **Audit log cho SIEM:** ghi thay đổi parser, suppression, detection, query/export và hành động SOAR.
- **Data minimization:** masking/pseudonymization các trường cá nhân khi phù hợp, không gửi credential trong log.
- **Bảo mật API token và key:** xoay định kỳ phù hợp, cấp quyền tối thiểu, tránh nhúng vào script/report hoặc hình chụp màn hình.
- **Tách môi trường:** log phòng lab không được vô tình ghi đè hoặc trộn với sự kiện sản xuất làm sai correlation.
- **Chống thao túng:** kiểm tra provenance của nguồn log, bảo vệ quyền sửa event pipeline, giữ raw record/bản lưu bất biến nếu yêu cầu và có khả năng.

Khi chia sẻ case cho nhóm khác, xuất **dữ liệu tối thiểu đủ điều tra** và giới hạn quyền download. SIEM không nên trở thành nơi dễ tra được API key, session cookie hoặc nội dung riêng tư của toàn bộ hệ thống.

### 9.4. Phiên bản hóa detection và quy trình phê duyệt

Detection rule cũng cần kiểm soát thay đổi như source code:

1. Mô tả mục tiêu và threat hypothesis.
2. Liệt kê nguồn log, schema và điều kiện tiên quyết để rule hoạt động.
3. Định nghĩa trường, phép join, threshold, window, ngoại lệ và severity.
4. Đánh giá với dữ liệu giả lập/đã duyệt gồm **true case, benign case, missing data và duplicate**.
5. Review bởi người có trách nhiệm về phát hiện và dịch vụ mục tiêu.
6. Triển khai có version, theo dõi lượng alert và tỷ lệ nhiễu.
7. Chuẩn bị rollback/sửa rule và ghi lý do từng lần suppression.
8. Xem lại sau thay đổi network topology, NAT, gateway, DNS, VPN, cloud hoặc nâng cấp IDS/IPS.

Một rule chỉ đúng khi **dữ liệu đầu vào đúng**. Nếu tổ chức thay reverse proxy, có thể source.ip của app log chuyển thành IP proxy; detection gắn với IP client cũ sẽ sai nếu không sửa mapping.

## 10. IDS/IPS–SIEM trong cloud, container và mạng hỗn hợp

### 10.1. Cloud và traffic mirroring

Trong cloud, một phần lưu lượng có thể đi qua managed load balancer, NAT gateway, service endpoint hoặc internal network không đi qua sensor vật lý của doanh nghiệp. Có thể kết hợp:

- **Flow logs của VPC/VNet/VPC tương đương:** cung cấp metadata kết nối theo cấu trúc dịch vụ; không phải bản sao đầy đủ payload.
- **Traffic mirroring hoặc packet sensor** ở những interface/tài nguyên được hỗ trợ: có thể quan sát packet với giới hạn băng thông và phạm vi cụ thể.
- **Cloud firewall/WAF logs:** giải thích allow/deny ở điểm policy và HTTP request đã được edge xử lý.
- **Cloud control-plane audit:** những thay đổi IAM, security group, route, storage, network policy có thể là tín hiệu bổ sung cho điều tra.
- **Workload logs và EDR:** process, danh tính workload, API access và egress metadata từ host/container.

Không giả định vì đã bật cloud flow log nên NIDS có đủ HTTP payload. Cũng không giả định dịch vụ managed đã tự động chuyển log tới SIEM hoặc giữ dữ liệu theo retention tổ chức cần.

### 10.2. Kubernetes, container và service mesh

Pod IP biến động khi rollout và scale-out, nên SIEM cần bổ sung **cluster, namespace, pod UID, deployment, node, labels và service account** nếu những trường đó có nguồn xác thực. IP cùng một thời điểm có thể thuộc một workload, nhưng về sau thuộc workload khác.

Các nguồn quan sát gồm:

| Nguồn | Tín hiệu | Giới hạn |
| --- | --- | --- |
| CNI/NetworkPolicy flow log | Kết nối pod–pod, kết quả policy nếu CNI hỗ trợ | Hành vi và trường log phụ thuộc CNI |
| Service mesh telemetry | Caller/callee identity, HTTP response, mTLS metadata | Chỉ bao phủ traffic đi qua mesh; không bao phủ mọi đường bypass |
| Kubernetes audit log | Thay đổi pod, policy, Role/RoleBinding, service account | Không tự chứng minh packet đã đi hoặc dữ liệu đã lộ |
| Container/host EDR | Process, command và kết nối theo quyền/khả năng agent | Có thể bị hạn chế bởi runtime hoặc môi trường không có agent |
| NIDS tại node/overlay được hỗ trợ | Traffic đi qua điểm bắt gói | Có thể bỏ sót traffic cùng host hoặc lưu lượng đã mã hóa |

Để triage một cảnh báo east–west, nên gắn địa chỉ IP tại đúng **event time** với pod UID/service identity, sau đó đối chiếu NetworkPolicy hiệu lực và application log. Không chỉ dựa vào tên pod vì pod có thể được tái tạo.

### 10.3. Phối hợp với phân đoạn, VPN, NAC và DNS

Trong một kiến trúc có nhiều lớp:

1. **Segmentation, firewall, network ACL** giới hạn đường có thể đi; SIEM dùng hit/action log để biết lưu lượng đã được phép hay chặn.
2. **Microsegmentation** giảm đường đi ngang; IDS/IPS và SIEM theo dõi kết nối bất thường bên trong vùng và những trường hợp policy bị thay đổi.
3. **VPN và NAC/802.1X** xác thực/gán vùng truy cập; log kết nối hoặc lease hỗ trợ xác định chủ thể ở một thời điểm.
4. **DNS resolver** ghi lại truy vấn phục vụ phát hiện, với chính sách lưu trữ/quyền riêng tư; cần gắn đúng resolver và nguồn query.
5. **WAF/reverse proxy/API** bổ sung thông tin L7 cho request HTTPS mà sensor trước TLS termination không đọc được.
6. **Cloud IAM và audit** cho biết ai thay đổi network/security policy, giúp kết nối sự cố lưu lượng với thay đổi cấu hình.

Thông tin từ nhiều lớp có thể mâu thuẫn. Ví dụ firewall log cho phép TCP/443 nhưng WAF chặn một request HTTP cụ thể; cả hai đều đúng ở **hai tầng khác nhau**. SIEM không được diễn giải "firewall allowed" thành "HTTP request accepted by application".

### 10.4. Bản đồ coverage cho tổ chức hỗn hợp

| Trust boundary | Kiểm soát phòng vệ | Telemetry đưa vào SIEM | Kiểm chứng tối thiểu |
| --- | --- | --- | --- |
| Internet → DMZ | Firewall, IPS, WAF | Firewall action, IPS alert/block, WAF request logs | Alert lab ở edge có request ID/flow ID, không bypass origin |
| User/Guest Wi-Fi → mạng nội bộ | NAC, WLAN ACL, firewall | 802.1X auth, DHCP lease, Wi-Fi controller, firewall | Client khách bị chặn đúng vùng; ánh xạ IP–thiết bị theo thời điểm |
| VPN → ứng dụng nội bộ | VPN gateway, ZTNA, ACL | VPN session/user, IP pool, authentication, allow/deny | User identity gắn được với IP session và luồng ứng dụng |
| Web → Application → DB | Microsegmentation, host firewall, DB auth | Flow log, NetworkPolicy, app/DB audit, EDR | Luồng Web→DB bị từ chối; App→DB hợp lệ được ghi |
| Cloud workload → Internet | Egress policy, NAT gateway | Flow/NAT/cloud firewall, DNS, EDR | IP/port mapping, endpoint được duyệt và log đủ |
| Admin → network/security control plane | MFA, IAM/RBAC, management network | IAM audit, firewall, change logs | Chỉnh sửa rule trái phép tạo sự kiện và case phù hợp |

Mỗi dòng cần có **người sở hữu và ngày kiểm tra gần nhất**. Một cảm biến có trạng thái xanh không chứng minh coverage nếu đường traffic đã được chuyển sang route khác.

## 11. Thực hành trong lab: tương quan sự kiện IDS, firewall và inventory

Chỉ thực hành trên hệ thống do bạn quản lý hoặc lab được cấp phép. **Không cần gửi packet tấn công**: bài tập dùng sự kiện mô phỏng để kiểm tra logic SIEM và kỹ năng phân tích. Mọi IP public trong ví dụ thuộc dải TEST-NET dành cho tài liệu.

### 11.1. Mô hình lab

Giả sử:

- Web API ở **10.30.20.12**, chỉ được gọi Orders API.
- Orders API ở **10.30.30.10**, được phép gọi Orders DB.
- Orders DB ở **10.30.40.10:5432**, mức quan trọng **high**.
- Hệ thống quét lỗ hổng được duyệt là **10.30.60.25**, chạy định kỳ trong một khung thời gian đã đăng ký.
- NIDS ứng dụng quan sát lưu lượng đi qua điểm đặt giữa các vùng và gửi alert vào SIEM.
- Firewall phân đoạn ghi sự kiện cho phép/từ chối.
- CMDB chứa thông tin workload, chủ sở hữu và độ nhạy cảm tại thời điểm đó.

Theo thiết kế, **Web API → Orders DB trực tiếp** là luồng **không được phép**. Lab yêu cầu phát hiện dấu hiệu đó nếu có, phân biệt nó với hoạt động kiểm tra được duyệt và kiểm chứng policy mạng.

### 11.2. Bộ sự kiện giả lập

Các bản ghi dưới đây là dữ liệu **mô phỏng**, không phải kết quả xâm nhập thật hay log chuẩn của một sản phẩm:

~~~json
[
  {
    "id": "E01",
    "time": "2026-03-10T09:00:02Z",
    "source_type": "nids",
    "sensor": "nids-app",
    "src_ip": "10.30.20.12",
    "dst_ip": "10.30.40.10",
    "dst_port": 5432,
    "protocol": "tcp",
    "event": "unexpected_database_connection",
    "action": "alert"
  },
  {
    "id": "E02",
    "time": "2026-03-10T09:00:03Z",
    "source_type": "firewall",
    "src_ip": "10.30.20.12",
    "dst_ip": "10.30.40.10",
    "dst_port": 5432,
    "protocol": "tcp",
    "action": "allow",
    "rule_id": "FW-LEGACY-100"
  },
  {
    "id": "E03",
    "time": "2026-03-10T09:00:04Z",
    "source_type": "asset_inventory",
    "ip": "10.30.40.10",
    "asset_id": "orders-db-prod",
    "criticality": "high",
    "owner": "data-team"
  },
  {
    "id": "E04",
    "time": "2026-03-10T09:05:00Z",
    "source_type": "nids",
    "sensor": "nids-app",
    "src_ip": "10.30.60.25",
    "dst_ip": "10.30.30.10",
    "dst_port": 8443,
    "protocol": "tcp",
    "event": "connection_pattern_resembling_scan",
    "action": "alert"
  },
  {
    "id": "E05",
    "time": "2026-03-10T09:05:01Z",
    "source_type": "change_calendar",
    "source_asset": "10.30.60.25",
    "activity": "approved_security_scan",
    "start": "2026-03-10T09:00:00Z",
    "end": "2026-03-10T09:30:00Z",
    "owner": "security-assurance"
  },
  {
    "id": "E06",
    "time": "2026-03-10T09:06:00Z",
    "source_type": "pipeline_health",
    "sensor": "nids-dmz",
    "status": "collector_offline",
    "last_ingest": "2026-03-10T08:50:00Z"
  }
]
~~~

### 11.3. Kết quả phân tích mong đợi

| Nhóm | Sự kiện liên quan | Cách kết luận hợp lý | Hành động tiếp theo |
| --- | --- | --- | --- |
| **CASE-1: kết nối Web→DB bất thường** | E01 + E02 + E03 | Có alert NIDS, firewall cho phép luồng không nằm trong ma trận, đích là DB quan trọng. Đây là **vi phạm ý định phân đoạn cần điều tra**, chưa đủ chứng minh DB bị khai thác | Kiểm tra rule FW-LEGACY-100, ứng dụng/DB audit và EDR; đề xuất thu hẹp rule theo quy trình |
| **CASE-2: scan có lịch** | E04 + E05 | Nguồn có lịch quét được phê duyệt trong khung giờ tương ứng; vẫn cần xác minh đúng job và phạm vi | Gắn nhãn hoạt động được duyệt, giảm nhiễu có điều kiện; không suppress vĩnh viễn nguồn đó |
| **CASE-3: thiếu telemetry** | E06 | Không đủ dữ liệu từ nids-dmz kể từ 08:50Z; không thể kết luận DMZ không có alert | Khôi phục collector, kiểm tra queue, dữ liệu bị mất và các hệ thống log bổ trợ |

Sự kiện E03 dùng trường "time" để thể hiện **thời điểm snapshot của CMDB trong lab**. Trong thiết kế thật, asset inventory cần có effective-time hoặc snapshot validity để bảo đảm IP 10.30.40.10 lúc E01 đúng là Orders DB, nhất là khi workload dùng địa chỉ động.

### 11.4. Thuật toán tương quan minh họa

Pseudo-code dưới đây mô tả tư duy, không gắn với cú pháp query của Splunk, Elastic, Microsoft Sentinel hoặc hệ SIEM cụ thể:

~~~text
input: normalized IDS events, firewall events, inventory snapshots

for each IDS event in event-time order:
    validate fields, sensor health and event provenance
    resolve original/translated IP:port if NAT exists
    attach asset identity valid at event.time

    find firewall event matching:
        network endpoints + transport + appropriate NAT mapping
        within allowed event-time skew

    if destination is high criticality
       and connection violates approved flow matrix
       and firewall decision is "allow":
        group related events into one investigation case
        include raw event IDs and data-quality warnings
        do not auto-block based only on this condition

    if activity is from approved scanner:
        validate job identity, schedule and scope
        annotate case as reviewed benign only if evidence supports it

if a sensor heartbeat or ingest rate is missing:
    raise telemetry-health alert instead of "no threat observed"
~~~

**Đúng ngữ nghĩa của phép ghép quan trọng hơn cú pháp**. Với môi trường có NAT, một rule dùng raw source/destination IP như trên cần bước ánh xạ đúng để không ghép nhầm phiên. Nếu chỉ có event từ một chiều hoặc trường port thiếu, case phải thể hiện mức tin cậy thấp hơn và yêu cầu thêm bằng chứng.

### 11.5. Các phép thử phát hiện

| Test | Dữ liệu đưa vào | Mong đợi |
| --- | --- | --- |
| DT01 | E01 + E02 + E03 | Tạo một case về luồng Web→DB trái policy; không khẳng định compromise |
| DT02 | E01 + E03, nhưng **không có E02** do collector firewall hỏng | Đánh dấu **chưa đủ dữ liệu**, không tự kết luận firewall đã chặn |
| DT03 | E04 + E05, job đúng owner và giờ | Đánh giá hoạt động được duyệt, giữ khả năng audit |
| DT04 | E04 nhưng E05 hết hiệu lực | Tạo/cập nhật case cần điều tra; không suppress vô điều kiện |
| DT05 | E01 được ingest hai lần với cùng event ID/sensor | Dedup bản ghi; không nhân đôi case hoặc tăng số lần giả |
| DT06 | Hai IP nguồn khác nhau cùng NAT ra một IP công khai | Không gộp người dùng khi không có mapping port/thời gian |
| DT07 | E06 xuất hiện | Cảnh báo sức khỏe collector; đánh dấu khoảng trống coverage |
| DT08 | Event IDS có event time cũ nhưng ingest muộn | Xử lý đúng window theo event time hoặc cập nhật case sau nhận muộn |
| DT09 | Traffic cùng source/destination nhưng port khác | Không tự ghép thành cùng phiên khi rule yêu cầu cùng 5-tuple |
| DT10 | Sensor ghi "alerted", firewall ghi "blocked" tại biên | Phân biệt tín hiệu phát hiện với hành động chặn; xem vị trí và đường luồng |

### 11.6. Bài tập thực hành mở rộng

Tự bổ sung ba sự kiện **synthetic**:

1. Reverse proxy trả 403 cho một request từ IP nguồn đã qua NAT.
2. Một bản ghi DNS của cùng workload thể hiện truy vấn tên miền mới trong khoảng thời gian gần E01.
3. Một sự kiện EDR cho biết process nào mở kết nối Web→DB, có owner ứng dụng và thời điểm.

Sau đó viết bản tóm tắt điều tra: tín hiệu nào hỗ trợ nghi vấn, tín hiệu nào làm giảm nghi vấn, bằng chứng nào còn thiếu và hành động nào có thể thực hiện **mà không làm gián đoạn nghiệp vụ ngoài phạm vi**. Không biến mối tương quan thời gian thành lời khẳng định quan hệ nhân quả nếu không có bằng chứng.

## 12. Tình huống tổng hợp: nhiều cảnh báo nhưng chưa rõ sự cố

Một tổ chức có firewall biên, IPS inline, NIDS thụ động tại DMZ, microsegmentation giữa Web và DB, VPN cho nhân viên và SIEM tập trung. Trong một ngày phát sinh:

- IPS edge báo **hàng nghìn gói bị chặn** vào dịch vụ public.
- NIDS ứng dụng phát hiện một số kết nối Web → DB bị đánh dấu bất thường.
- Firewall phân đoạn cho phép một trong các kết nối Web → DB do rule cũ.
- SIEM liên kết nhiều event theo IP, nhưng IP đó là địa chỉ của NAT gateway.
- Nguồn DNS telemetry gián đoạn 20 phút; đồng hồ một sensor lệch khoảng 2 phút.
- Ứng dụng ghi lỗi 403 do authorization, nhưng không có evidence thay đổi dữ liệu.

### 12.1. Những nhận định chưa đủ căn cứ

Không nên vội kết luận:

- “Hàng nghìn gói bị IPS chặn = hàng nghìn lần khai thác thành công.” Chặn và thành công là hai trạng thái khác.
- “Có IDS alert tới DB = dữ liệu DB đã bị lấy.” Cần audit DB, bằng chứng truy vấn, tài khoản và hành vi dữ liệu.
- “Cùng IP NAT = cùng một người dùng.” Phải có port/time mapping hoặc identity đáng tin.
- “Không có DNS alert = không có DNS bất thường.” Nguồn DNS đang bị gián đoạn.
- “HTTP 403 nghĩa là WAF hoặc IPS lỗi.” API có thể trả 403 vì authorization đang hoạt động đúng.

### 12.2. Hành động ưu tiên

1. **Bảo đảm nguồn dữ liệu đáng tin:** sửa đồng hồ và collector DNS, xác định khoảng trống và giới hạn của kết luận.
2. **Giữ bằng chứng:** lưu raw IDs, event-time, NAT mapping, phiên bản policy và các event liên quan trong thời hạn được phép.
3. **Ưu tiên luồng Web→DB:** vì trái ý định phân đoạn và đã được firewall cho phép; kiểm tra endpoint/DB và lý do tồn tại rule cũ.
4. **Đánh giá IPS edge:** xác minh các gói bị chặn ở đâu, ảnh hưởng tới origin/backend và người dùng hợp lệ; rà rule vừa cập nhật nếu có.
5. **Sửa correlation:** thêm sensor/zone, NAT port mapping và asset identity để tránh gộp sai nguồn.
6. **Kiểm tra ứng dụng:** xác thực rằng 403 là quyết định quyền hợp lệ; tìm bằng chứng khác nếu nghi bypass.
7. **Chọn biện pháp có phạm vi nhỏ:** thu hẹp ACL/rule sai, cô lập workload nếu có đủ căn cứ và phê duyệt; kiểm thử luồng hợp lệ.
8. **Đóng vòng học tập:** cập nhật threat model, quy tắc phát hiện, dashboard coverage, playbook và owner.

### 12.3. Mẫu tóm tắt case

| Mục | Nội dung cần có |
| --- | --- |
| Case ID / thời gian | Mã incident/case, event time và ingest time, timezone |
| Alert gốc | Sensor, rule ID/version, action, raw event link |
| Tài sản | Asset ID, criticality, owner, role, dữ liệu có thể ảnh hưởng |
| Luồng mạng | Source/destination 5-tuple và điểm quan sát, pre-/post-NAT nếu có |
| Sự kiện liên quan | Firewall, DNS, VPN, NAC, WAF, app, DB, EDR; kèm timestamp |
| Data quality | Thiếu nguồn nào, time skew, packet drop, mức tin cậy enrichment |
| Đánh giá | Xác nhận, nghi vấn, benign hay chưa đủ chứng cứ; phân biệt attempt và outcome |
| Quyết định | Mức ưu tiên và căn cứ, người duyệt biện pháp |
| Ứng phó | Hành động, phạm vi, thời hạn, công cụ, kết quả và rollback |
| Follow-up | Owner, deadline, điều chỉnh policy/detection, kiểm chứng rủi ro còn lại |

## 13. Checklist triển khai trong môi trường thực

### 13.1. Kiến trúc và khả năng quan sát

- [ ] Có bản đồ tài sản, luồng north–south/east–west và ranh giới tin cậy.
- [ ] Xác định NIDS ở đâu, IPS ở đâu, luồng nào đi qua và đường dự phòng.
- [ ] Xác nhận sensor thấy được hai chiều nếu use case yêu cầu và có metric packet drop.
- [ ] Biết vị trí NAT, TLS termination, reverse proxy, VPN tunnel và các điểm khác địa chỉ hiển thị.
- [ ] Đã xét IPv4/IPv6, TCP/UDP, HTTP/3/QUIC và mạng cloud/container.
- [ ] Có dữ liệu bổ trợ từ firewall, DNS, IAM, NAC/VPN, WAF, endpoint hoặc ứng dụng theo mục tiêu phát hiện.

### 13.2. Dữ liệu, correlation và SIEM health

- [ ] Mỗi event có event time, observer identity, rule ID/version, action và network tuple khi nguồn hỗ trợ.
- [ ] Chuẩn hóa severity/action đúng ngữ nghĩa vendor, không đánh đồng IDS alert với IPS block.
- [ ] Có cách gắn user/workload identity vào IP theo thời điểm và ghi độ tin cậy của mapping.
- [ ] Có cơ chế buffer, retry, dedup, parser quarantine, heartbeat và cảnh báo thiếu log.
- [ ] Correlation có rõ threat hypothesis, event window, join keys, trường bắt buộc, ngoại lệ và owner.
- [ ] Rule đã test với true/benign/duplicate/missing/late synthetic cases.
- [ ] Raw events và mapping được giữ đủ để truy dấu, với RBAC và retention phù hợp.

### 13.3. Vận hành và phản ứng

- [ ] Có playbook triage, tiêu chí phân loại incident và quy trình yêu cầu thêm bằng chứng.
- [ ] IPS block mode được đánh giá false positive và availability trước triển khai.
- [ ] SOAR có ràng buộc quyền, phê duyệt cho tác động lớn, scope/time limit và rollback.
- [ ] Có dashboard phát hiện rule/collector/sensor thất bại, packet drop và ingest delay.
- [ ] Có người chịu trách nhiệm review rule, thay đổi network topology và retention.
- [ ] Có cơ chế kiểm toán truy vấn SIEM, export log và thay đổi policy/detection.
- [ ] Chỉ lưu nội dung cần thiết; tránh ghi token, credential hoặc payload nhạy cảm quá mức.

## 14. Câu hỏi ôn tập

**Câu 1.** IDS phát một alert, IPS phát một event "blocked", SIEM có thể tự kết luận hệ thống đã an toàn chưa?

*Gợi ý:* Không. Cần biết vị trí sensor, hành động thật, đối tượng/luồng đã đi qua đâu và có đường khác hay không; phải tìm bằng chứng ứng dụng/endpoint nếu nghi xâm nhập.

**Câu 2.** Tại sao hai event trùng IP nguồn nhưng khác sensor có thể không thuộc cùng user?

*Gợi ý:* IP có thể là NAT gateway, proxy, VPN gateway hoặc địa chỉ được cấp lại. Cần mapping theo port, thời điểm và danh tính được xác minh.

**Câu 3.** Vì sao SIEM phải lưu cả event.time và ingest.time?

*Gợi ý:* Event có thể tới muộn; logic diễn biến cần thời gian thực sự xảy ra, còn độ trễ ingest phản ánh sức khỏe pipeline.

**Câu 4.** Nếu NIDS chỉ đặt trước reverse proxy TLS, nó có đọc được request body HTTPS mặc định không?

*Gợi ý:* Không. Nội dung bị mã hóa ở điểm quan sát; bổ sung log proxy/ứng dụng được phép hoặc cơ chế giải mã hợp lệ nếu thực sự cần.

**Câu 5.** Cần thêm nguồn nào khi IDS cảnh báo Web API kết nối trực tiếp DB?

*Gợi ý:* Firewall/segmentation log, DB audit, EDR/process, inventory và change record để phân biệt luồng bị chặn, thay đổi hợp lệ hay rủi ro.

**Câu 6.** Tại sao một detection yêu cầu IDS + DNS trong cùng phút có thể bỏ lỡ sự kiện?

*Gợi ý:* Nguồn tới muộn, lệch đồng hồ, thiếu log hoặc cách dùng ingest-time sai; cần thiết kế correlation window và data-quality handling.

**Câu 7.** Có nên tự động chặn toàn bộ public IP khi một IDS alert xác định IP đó đáng ngờ?

*Gợi ý:* Không mặc định. IP có thể được dùng chung bởi CDN/NAT và false positive có thể gây gián đoạn; cần confidence, phạm vi, phê duyệt/guardrail và rollback.

**Câu 8.** Khi sensor không gửi alert trong nhiều giờ, cách giải thích nào đáng tin hơn?

*Gợi ý:* Xác nhận heartbeat, EPS, interface, packet drop và collector trước. Không có alert không đồng nghĩa không có nguy cơ.

**Câu 9.** Một firewall log cho phép TCP/443 và WAF log chặn HTTP request; hai bản ghi có mâu thuẫn không?

*Gợi ý:* Không. Firewall cho phép kết nối L3/L4 nhưng WAF có thể chặn request L7 tại chặng kế tiếp.

**Câu 10.** Tại sao không nên lưu mọi packet và header Authorization trực tiếp trong SIEM?

*Gợi ý:* Vừa tốn dung lượng, vừa tăng rủi ro lộ bí mật. Cần phân loại, giảm dữ liệu nhạy cảm, bảo vệ forensic store và giới hạn quyền/retention.

## 15. Ghi nhớ

- **IDS/IPS là nguồn tín hiệu và điểm phát hiện/ngăn chặn**, trong khi **SIEM liên kết dữ kiện từ nhiều lớp** để giúp xác minh, ưu tiên và ứng phó; không thành phần nào tự thay thế bảo mật ứng dụng hay phân đoạn.
- **Sensor placement quyết định coverage**: traffic không đi qua sensor hoặc dữ liệu TLS chưa giải mã có thể không quan sát được nội dung; cần bổ sung flow, proxy, app và endpoint telemetry.
- **Chuẩn hóa event phải bảo toàn ngữ nghĩa** của thời gian, nguồn/đích, hành động, severity, rule và vị trí cảm biến; NAT/proxy/VPN/IPv6 làm thay đổi góc nhìn.
- **Correlation tốt có giả thuyết rõ, phép join đúng, window phù hợp và dữ liệu chất lượng**; không kết luận khai thác thành công chỉ từ alert hay HTTP status.
- **Giảm false positive** bằng tuning có kiểm chứng, gộp event và ngoại lệ hẹp; không loại bỏ coverage bằng cách suppress toàn bộ nguồn hoặc subnet.
- **SIEM cũng cần được giám sát** bằng heartbeat, ingest delay, parser errors, packet drops, EPS và audit log; im lặng có thể là mất dữ liệu.
- **Ứng phó tự động phải có guardrail và rollback**. Những quyết định chặn, cô lập, thu hồi tài khoản có thể ảnh hưởng trực tiếp tới dịch vụ hợp lệ.
- **Bảo mật dữ liệu giám sát** là trách nhiệm độc lập: thu thập đủ để điều tra nhưng giảm token, payload và dữ liệu cá nhân không cần thiết; giới hạn quyền, retention và export.
- Triển khai thành công là **phát hiện đáng tin, điều tra có bằng chứng, ứng phó đúng phạm vi và cải tiến liên tục**, không phải chỉ tăng số lượng alert đưa vào SIEM.
