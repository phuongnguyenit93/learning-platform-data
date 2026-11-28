# Phát hiện data exfiltration qua HTTPS

**Data exfiltration qua HTTPS** là hành vi đưa dữ liệu từ một hệ thống ra điểm nhận không được phép thông qua các kết nối HTTPS, hoặc lợi dụng một dịch vụ HTTPS hợp lệ để chuyển dữ liệu vượt phạm vi được ủy quyền. HTTPS bảo vệ tính bí mật và toàn vẹn **trên kênh truyền** giữa các TLS peers, nhưng **không quyết định người gửi có quyền chuyển dữ liệu đó hay không**. Vì vậy, một kết nối tới **TCP 443**, TLS handshake thành công và chứng thư hợp lệ **không đồng nghĩa luồng dữ liệu đó hợp pháp**.

Ví dụ: một ứng dụng tài chính định kỳ gửi báo cáo đã được phê duyệt tới hệ thống lưu trữ đối tác; lưu lượng upload lớn có thể hoàn toàn bình thường. Ngược lại, một tiến trình bất thường trên máy nhân viên tải hàng loạt hồ sơ khách hàng rồi đẩy chúng tới một tài khoản cloud storage cá nhân qua HTTPS có thể là sự cố rò rỉ dữ liệu. Hai trường hợp đều dùng giao thức bảo mật; sự khác biệt nằm ở **chủ thể, dữ liệu, đích nhận, mục đích, thời điểm, quyền và bằng chứng về hành vi**.

Trong chương **Kiểm soát egress và chống thất thoát dữ liệu** thuộc module **SECURITY_NETWORK_SECURITY**, bài học này kết hợp kiến thức về firewall/egress gateway, proxy, TLS/PKI, DNS, IDS/IPS, phân đoạn mạng, cloud, container và Zero Trust. Mục tiêu là thiết kế **phát hiện đa tín hiệu**, điều tra có căn cứ và giảm thiểu thất thoát mà vẫn bảo vệ hoạt động nghiệp vụ và quyền riêng tư.

> **Nguyên tắc trọng tâm:** **Không thể nhìn thấy nội dung HTTPS bằng flow logs thuần túy**; đồng thời **không cần và không nên giải mã tất cả HTTPS** để có giá trị phát hiện. Hãy phối hợp metadata mạng, danh tính tiến trình/người dùng, thông tin tài nguyên dữ liệu, chính sách đích nhận, sự kiện upload và telemetry từ các điểm có quyền quan sát.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **HTTPS upload hợp lệ, chia sẻ ngoài chính sách, data exfiltration, backup/sync** và truy cập dữ liệu trái quyền.
2. Hiểu những trường thường quan sát được từ **NetFlow/IPFIX, firewall, DNS, TLS, SWG/forward proxy, endpoint EDR, DLP và cloud audit logs**.
3. Giải thích **TLS 1.2/1.3, SNI, ECH, HTTP/2, HTTP/3/QUIC** làm thay đổi khả năng nhìn thấy hostname, request path, payload và byte counts.
4. Thiết kế **egress inventory** gồm user, device, workload, process, destination, account/tenant, data classification và policy decision.
5. Xây dựng **baseline theo role/app/time window** và phát hiện bất thường bằng nhiều tín hiệu, tránh dựa vào một ngưỡng dung lượng cứng.
6. Nhận diện rủi ro **personal cloud storage, file-sharing, API upload, service accounts và các kênh HTTPS hợp lệ bị lạm dụng**.
7. Đánh giá **TLS inspection** dựa trên pháp lý, riêng tư, chứng thư, tính tương thích và kiểm soát truy cập, không giải mã mặc định mọi lưu lượng.
8. Phân tích những đường **bypass egress controls**: direct IP, alternate proxy, IPv6, QUIC, unapproved DoH, cloud NAT, Kubernetes và hybrid routes.
9. Viết **mô hình chính sách, quy tắc tương quan/điểm rủi ro, log giả lập và truy vấn minh họa** có giới hạn.
10. Thực hiện **triage, containment, xác minh dữ liệu/tài khoản bị ảnh hưởng, điều tra và phục hồi**, cùng bộ test an toàn không chuyển dữ liệu nhạy cảm thật.

## 2. Data exfiltration là gì trong ngữ cảnh egress?

**Egress** là lưu lượng đi **từ một vùng được bảo vệ đến vùng/dịch vụ bên ngoài vùng đó**. Trong một doanh nghiệp, “bên ngoài” có thể là Internet, một SaaS tenant cá nhân, tài khoản cloud khác, mạng đối tác, một segment nội bộ ít tin cậy hơn hoặc kho lưu trữ không được phê duyệt.

**Data exfiltration** tập trung vào việc dữ liệu đi tới bên nhận không được phép; không nhất thiết phải dùng giao thức lạ. HTTPS là kênh thường được chọn cho nhiều nghiệp vụ hợp lệ, do đó **phát hiện cần dựa trên ngữ cảnh**, tránh coi mọi upload là đe dọa.

### 2.1. Các tình huống cần tách biệt

| Tình huống | Ví dụ | Đánh giá ban đầu |
| --- | --- | --- |
| **Truyền dữ liệu hợp lệ** | ERP gửi hóa đơn tới API nhà cung cấp đã duyệt | Hợp lệ nếu identity, phạm vi và dữ liệu đúng |
| **Backup/replication** | Database backup mã hóa tới bucket doanh nghiệp | Lưu lượng lớn nhưng có owner, lịch và account đúng |
| **Chia sẻ sai chính sách** | Nhân viên tải bản nội bộ lên cloud cá nhân vì thuận tiện | Vi phạm chính sách, chưa kết luận ý đồ độc hại |
| **Compromised account/session** | Access token bị chiếm dùng để xuất dữ liệu qua API | Cần xác thực dấu hiệu account takeover và data access |
| **Compromised endpoint** | Tiến trình trái chuẩn đọc nhiều tệp rồi upload qua HTTPS | Nghi vấn cần endpoint/process evidence |
| **Misconfigured workload** | Service tự đẩy log chứa PII tới analytics vendor | Có thể là exposure vô ý, vẫn cần xử lý |
| **Unauthorized cross-tenant transfer** | Workload đẩy dữ liệu sang cloud account khác | Cần kiểm tra IAM, tenant và storage audit |
| **Test/telemetry hợp lệ** | Synthetic upload của DLP testing | Hợp lệ nếu trong lịch/phạm vi được cấp |

**Một hành vi không hợp chính sách không tự chứng minh tội phạm hay chủ ý của người dùng.** SOC cần phân biệt **sự kiện, mức tin cậy của tín hiệu, mức ảnh hưởng và giả thuyết** trước khi gắn nhãn.

### 2.2. Dữ liệu nào cần quan tâm?

- Thông tin cá nhân, dữ liệu khách hàng và hồ sơ nhân sự.
- Tài liệu kinh doanh bí mật, hợp đồng, tài chính.
- Source code, thiết kế hệ thống, cấu hình nội bộ.
- Credentials, API keys, token, private keys và secrets.
- Dữ liệu sức khỏe/thanh toán theo chính sách pháp lý tương ứng.
- Database exports, log archives, customer snapshots.
- Dữ liệu nghiên cứu, tài sản trí tuệ và tài liệu chưa công bố.

Cần có **data inventory, classification labels, owner, retention, vùng xử lý và những điểm xuất dữ liệu hợp lệ**. Nếu không biết dữ liệu nào nhạy cảm, detector chỉ có network bytes sẽ rất khó xếp mức ưu tiên.

### 2.3. Data transfer và data access là hai sự kiện khác nhau

Một user có thể **đọc 10.000 records** từ database mà chưa upload ra Internet; một upload 300 MB có thể chứa video truyền thông công khai. Để đánh giá nghi vấn exfiltration, cần đối chiếu **source data access/export** với **network/upload destination** và quyền của chủ thể.

### 2.4. Những nhầm lẫn cần tránh

- **TLS 443 = hợp lệ**: sai, TLS mã hóa kênh chứ không kiểm tra quyền nghiệp vụ.
- **Bytes_out lớn = exfiltration**: sai nếu không có baseline và context.
- **IP đích là cloud provider uy tín = an toàn**: có thể là tài khoản cá nhân trong cùng nền tảng.
- **Không có DLP alert = không có rò rỉ**: DLP có thể không quan sát hoặc không hiểu dữ liệu đã mã hóa.
- **Một domain lạ = độc hại**: có thể do CDN, update, SaaS mới hoặc hệ thống thử nghiệm.

## 3. Threat model: nguồn, đích và trust boundaries

Một kịch bản thường có ba câu hỏi:

1. **Dữ liệu xuất phát từ đâu?** Endpoint nhân viên, application server, container, database hoặc cloud storage.
2. **Chủ thể nào tạo hành vi?** User, process, workload identity, service account, automation hoặc một phiên bị chiếm.
3. **Bên nhận nào nhận dữ liệu?** SaaS tenant/account đã phê duyệt hay chưa, external API, private/public endpoint hoặc cloud bucket.

### 3.1. Luồng phòng vệ điển hình

~~~mermaid
flowchart LR
    D[("Dữ liệu nhạy cảm / database")] -->|"Read/export event"| APP["User, app hoặc workload"]
    APP -->|"HTTPS egress"| EDGE["SWG/Proxy/Firewall/Egress gateway"]
    EDGE -->|"TLS/QUIC network flow"| DEST["External HTTPS destination"]
    APP -. "Process, identity, device telemetry" .-> SOC["Correlation / SIEM / DLP"]
    D -. "DB/object/storage audit" .-> SOC
    EDGE -. "Request/flow/policy metadata" .-> SOC
    DEST -. "SaaS/tenant API audit nếu có" .-> SOC
    SOC --> TRIAGE{"Authorized transfer?"}
    TRIAGE -->|"Có bằng chứng phù hợp"| VALID["Giữ hoạt động và baseline"]
    TRIAGE -->|"Nghi vấn có căn cứ"| IR["Triage, contain, validate impact"]
~~~

### 3.2. Trust boundaries khác nhau

| Biên | Điểm thực thi có thể dùng | Dữ liệu quan sát thường có |
| --- | --- | --- |
| User endpoint → Internet | EDR, device DLP, SWG, endpoint firewall | Process, file operation, user identity, upload |
| Office → Internet | Firewall, proxy, DNS resolver | Source NAT/IP, destination, TLS metadata, policy |
| Workload/VPC → Internet | Cloud egress firewall, NAT, proxy | Workload/IP/port, DNS và egress flow |
| Kubernetes Pod → external | NetworkPolicy/CNI, egress gateway/proxy | Pod/namespace, destination, policy verdict |
| SaaS tenant → external sharing | SaaS audit/DLP/CASB via API | Owner, sharing action, target tenant/account |
| Database → app/export | DB audit, data access monitoring | Principal, operation, record scope và thời điểm |

**Một firewall tại Internet gateway không tự biết database record nào được đọc**, và một database audit log không tự biết file export cuối cùng được tải lên tài khoản cloud nào. Cần correlation và quản trị IDs xuyên các biên.

### 3.3. Phạm vi người dùng và hệ thống

Threat model nên có:

- Nhân viên tại văn phòng, từ xa qua VPN/ZTNA và thiết bị BYOD.
- Privileged administrators, service desks và nhà thầu.
- Servers/workloads, CI/CD jobs, Kubernetes Pods, cloud functions.
- SaaS apps, cloud object storage, private endpoints, external partners.
- Đường IPv4/IPv6, HTTP proxy, HTTP/3/QUIC, direct outbound, backup/DR.

Không nên chỉ kiểm tra một laptop dùng HTTPS trong khi hệ thống thật có **NAT gateway, SaaS-to-SaaS transfers và workload egress** mà gateway không quan sát.

## 4. HTTPS/TLS thực sự che giấu và để lộ điều gì?

**HTTPS** là HTTP chạy qua một kênh bảo mật phù hợp, thông thường **TLS**; với HTTP/3 dùng **QUIC** tích hợp bảo vệ dựa trên TLS 1.3. Các lớp giám sát có mức quan sát khác nhau tùy nơi đặt, giao thức, cấu hình và quyền giải mã.

### 4.1. Không thể suy từ cổng

- **TCP 443** thường phục vụ HTTPS nhưng có thể mang giao thức khác.
- **UDP 443** thường gắn với HTTP/3/QUIC nhưng cũng có những traffic khác.
- HTTPS có thể chạy trên **cổng không phải 443**.
- Một client có thể kết nối trực tiếp IP hoặc qua proxy/PrivateLink theo chính sách.

**Port 443 không chứng minh protocol, chủ thể hay mục đích dữ liệu.**

### 4.2. Visibility matrix

| Trường/thông tin | Network flow không giải mã | TLS-aware sensor | Terminating/inspecting proxy | Endpoint/app audit |
| --- | --- | --- | --- | --- |
| Source/destination IP, port, protocol | Thường có tại điểm capture | Có | Có theo đường qua proxy | Có thể có |
| Tổng bytes/packets, thời gian | Có, theo khả năng flow collector | Có | Có | Có thể liên kết tới process |
| DNS query trước kết nối | Không tự có | Cần liên kết DNS telemetry | Có thể có proxy DNS | Có thể biết hostname |
| TLS version/certificate metadata | Có thể một phần, tùy TLS | Có thể quan sát một số trường | Thấy ở phiên TLS proxy làm peer | App có thể biết TLS state |
| SNI hostname | Có thể thấy nếu không được che | Có thể thấy nếu không bị ECH che | Có khi proxy là TLS endpoint | App biết đích được yêu cầu |
| HTTP Host, URL/path, method | **Không** từ ciphertext | **Không** nếu không terminate/decrypt | Có khi proxy giải mã đúng phiên | Có khi log HTTP layer |
| Upload payload/file content | **Không** | **Không** | Chỉ thấy khi proxy giải mã, policy cho phép và protocol hỗ trợ | Có thể theo endpoint DLP/file events |
| User/tenant/cloud account | Không suy trực tiếp từ IP | Không suy trực tiếp từ TLS | Có thể qua auth proxy/SaaS APIs | Có thể từ IdP/EDR/SaaS audit |
| Loại dữ liệu/classification | Không thể chắc chắn từ bytes | Không thể chắc chắn từ handshake | DLP classifier khi thấy nội dung | Data labels/source audit |

**Nhìn được hostname không đồng nghĩa nhìn được nội dung upload; nhìn được nội dung upload không đồng nghĩa biết người dùng có được phép chia sẻ dữ liệu đó hay không.**

### 4.3. TLS 1.3 và certificate visibility

Trong TLS 1.3, nhiều phần của handshake sau ServerHello, bao gồm **server certificate**, được mã hóa. Một passive sensor không có khóa và không terminate TLS **không thể mặc định đọc server certificate** như trong một số tình huống TLS 1.2. Những mô tả “IDS luôn thấy chứng thư HTTPS của server” là không chính xác nếu không nêu phiên bản và điểm quan sát.

### 4.4. Server Name Indication và Encrypted ClientHello

**SNI** có thể cung cấp hostname đích trong ClientHello khi không được mã hóa. **Encrypted ClientHello (ECH)**, khi được client/server hỗ trợ và sử dụng, làm giảm khả năng nhìn thấy tên đích thật ở passive observer. Việc quan sát được outer SNI hoặc một tên công khai **không chứng minh đó là hostname ứng dụng cuối cùng**.

### 4.5. Connection encryption không làm mất mọi metadata

Dù không thấy URL/payload, một hệ thống được quyền quan sát vẫn có thể thu thập **source identity, flow size, directionality, timing, connection count, destination address, approved resolver lookup, endpoint process events và SaaS account audit**. Những tín hiệu này không đảm bảo xác định nội dung, nhưng có thể tạo nghi vấn đáng điều tra khi tương quan.

## 5. TLS fingerprints, SNI, JA3/JA4 và giới hạn suy luận

Một số cảm biến sử dụng **TLS/QUIC fingerprinting** hoặc thông tin client handshake để nhóm những loại client stacks. Những tên fingerprint như **JA3/JA4** xuất hiện trong một số công cụ, nhưng thuật toán, trường, khả năng quan sát, chính sách hashing và hỗ trợ phiên bản **khác nhau theo triển khai**.

### 5.1. Khi fingerprints hữu ích

- Một tiến trình bất thường dùng TLS stack khác baseline của ứng dụng doanh nghiệp.
- Đột biến nhóm clients có handshake behavior chưa từng thấy từ một nhóm endpoints.
- Correlation với **process identity, destination risk, EDR detections và data-access events**.
- Phân biệt hoạt động mới với hành vi sync đã có lịch sử trong môi trường cụ thể.

### 5.2. Tại sao fingerprint không đủ là bằng chứng?

Nhiều ứng dụng hợp lệ dùng cùng một thư viện TLS. Browser/update có thể làm fingerprints đổi; middleware/proxy có thể tạo fingerprint thay cho ứng dụng gốc; privacy features và QUIC làm visibility khác đi. **Fingerprint match không xác nhận mã độc, cũng không chỉ ra một file đã bị gửi**.

### 5.3. SNI/domain reputation có thể sai

- Cloud CDN/shared hosting dùng chung nhiều IP và certificates.
- Tên miền mới không mặc nhiên độc hại.
- Dịch vụ hợp lệ có thể có **personal tenants hoặc unapproved storage accounts**.
- Domain reputation feed có false positives, stale data và những khoảng không bao phủ.
- Khi ECH có hiệu lực, observer không nhất thiết biết true target hostname.

**Sử dụng domain reputation như một tín hiệu bổ sung**, không làm nền duy nhất cho khóa tài khoản, cáo buộc hay phân loại incident.

### 5.4. TLS session reuse và HTTP/2 multiplexing

Một HTTPS/TLS connection có thể mang **nhiều requests/streams**, đặc biệt với HTTP/2; HTTP/3 cũng hỗ trợ multiplexed streams. Do đó **“một flow lớn” không tự tương ứng “một file upload”**. Client-side connection pooling, proxy aggregation và long-lived streams thay đổi ý nghĩa của số lượng kết nối.

### 5.5. Tổng quan giới hạn quan sát

**Có thể suy:** những luồng nào có upload bytes cao bất thường, từ process/người dùng nào nếu có telemetry liên kết, tới endpoints nào và gần thời điểm dữ liệu nào được đọc.

**Không thể khẳng định chỉ từ passive TLS:** tên file, nội dung hồ sơ, cloud tenant đích, HTTP method/path hoặc chủ ý người dùng. Muốn kết luận cần thêm nguồn quan sát có quyền hoặc bằng chứng nghiệp vụ.

## 6. Kiến trúc quan sát và kiểm soát egress

Một hệ thống phát hiện hiệu quả không nên chỉ dùng một sensor. Cần hiểu **traffic có thật sự đi qua sensor đó không**.

### 6.1. Reference architecture

~~~mermaid
flowchart TB
    subgraph INTERNAL["Protected environment"]
        EP["Managed endpoint + EDR/DLP"]
        APP["Application server / Kubernetes workload"]
        DB[("DB / Classified data")]
        DB -->|"Data access/export audit"| APP
    end
    EP -->|"HTTPS egress"| PROXY["Approved SWG / Forward proxy"]
    APP -->|"HTTPS egress"| EG["Cloud/K8s egress gateway"]
    PROXY --> FW["Egress firewall / NAT"]
    EG --> FW
    FW --> EXT["External SaaS / API / storage"]
    DNS["Managed DNS resolver"] -. "Name queries" .-> PROXY
    DNS -. "Name queries" .-> EG
    EP -. "Process + file activity" .-> CORR["SIEM / DLP correlation"]
    PROXY -. "HTTP, TLS, user, policy metadata" .-> CORR
    EG -. "Workload + flow data" .-> CORR
    FW -. "Allow/deny flows + NAT" .-> CORR
    DB -. "Object/SQL audit" .-> CORR
    EXT -. "SaaS API audit nếu có" .-> CORR
    CORR --> SOC["SOC triage & authorized containment"]
~~~

Sơ đồ là khái niệm, không quy định tất cả lưu lượng phải qua proxy giải mã. **Đường quản trị, ứng dụng được miễn kiểm tra TLS, private endpoints, cloud SaaS-to-SaaS và máy chủ không cài agent** có thể có telemetry riêng. Vì vậy luôn cần **coverage inventory và negative tests**.

### 6.2. Bốn cấp quan sát

| Cấp | Nguồn | Khả năng chính | Điểm mù |
| --- | --- | --- | --- |
| **L3/L4** | Firewall/NetFlow/IPFIX/cloud flow | Destination IP, port, bytes, duration, allow/deny | HTTP body, account, file contents |
| **TLS/session** | TLS-aware gateway, IDS, proxy handshake | TLS metadata, SNI khi có, handshake errors | Payload nếu không giải mã |
| **L7/proxy/SaaS** | SWG, forward proxy, CASB/SaaS audit | HTTP method/URL/category, user/account, DLP khi có visibility | Direct bypass, opaque end-to-end encryption, API gaps |
| **Endpoint/data** | EDR, endpoint DLP, file/DB/storage audit | Process, file label, export and read activity | Unmanaged devices, SaaS server-side transfers, missing logs |

**Cấp cao hơn không tự tốt hơn ở mọi ngữ cảnh.** Chẳng hạn endpoint DLP có thể biết file đang bị gửi mà không cần giải mã TLS ở gateway; SaaS audit có thể cho biết tenant đích nhưng không nhìn thấy dữ liệu phát sinh trong một client không được quản lý.

### 6.3. Phân tách detection và prevention

- **Detection:** tạo cảnh báo hoặc case dựa trên tín hiệu đủ mức tin cậy.
- **Prevention:** chặn upload, yêu cầu người dùng giải trình, quarantine session, đổi chính sách, vô hiệu token hoặc cô lập thiết bị theo điều kiện được phê duyệt.
- **Containment:** phản ứng khi có sự cố đang diễn ra; mức độ mạnh phụ thuộc rủi ro và tác động nghiệp vụ.

**Không phải mọi alert nên tự động cắt kết nối.** Một backup lớn có thể tạo tín hiệu giống exfil; có thể chọn alert-only, user coaching hoặc require justification cho lớp rủi ro thấp, trong khi dữ liệu cực nhạy cảm đẩy tới unapproved tenant có thể cần block tức thời theo policy.

## 7. NetFlow, IPFIX, firewall và NAT logs

**Flow telemetry** cho biết phiên lưu lượng đi/đến, thường ở dạng tổng hợp. Ví dụ record có thể có:

~~~json
{
  "event_type": "synthetic_network_flow",
  "time_start": "2026-11-28T10:00:00+07:00",
  "time_end": "2026-11-28T10:02:10+07:00",
  "source_ip": "10.60.14.25",
  "source_port": 51432,
  "destination_ip": "203.0.113.42",
  "destination_port": 443,
  "ip_protocol": "TCP",
  "bytes_client_to_server": 188743680,
  "bytes_server_to_client": 1048576,
  "action": "allow",
  "sensor_zone": "corporate-egress-lab",
  "synthetic": true
}
~~~

**203.0.113.42** thuộc dải địa chỉ dành cho tài liệu, không phải endpoint cần kết nối ngoài thực tế. Bytes ở trên minh họa **chiều dữ liệu**, chưa có bằng chứng đó là file nhạy cảm hay một HTTP upload thành công.

### 7.1. Directionality quan trọng hơn tổng bytes

Một flow có tổng 500 MB chưa biết upload hay download nếu chỉ ghi một trường bytes chung. Nên chuẩn hóa:

- **Client → server bytes** và **server → client bytes** nếu sensor cung cấp đáng tin.
- Source/destination theo hướng khởi tạo session, không nhầm sau NAT.
- TCP/UDP và connection lifecycle.
- Số flows và kích thước aggregate theo user/device/app.
- Sampling rate/flow timeout để hiểu độ chính xác.

**Không đồng nhất “egress bytes” ở một firewall với “application upload bytes”**: retransmissions, TLS overhead, proxies hoặc direction counters khác nhau có thể làm số liệu lệch.

### 7.2. NAT correlation

Nhiều users có thể cùng một public NAT IP. Nếu chỉ gắn alarm với IP NAT, sẽ không biết chủ thể nào:

~~~text
Original source:     endpoint-042 / 10.60.14.25:51432
Translated source:   public-nat-lab:62011
Destination:         203.0.113.42:443
Correlation:         NAT table + EDR device + IdP user session
~~~

Đối chiếu phải dùng **timestamp, port mappings, zone và đồng bộ đồng hồ**; không suy một public IP là một user. Nếu record NAT hết retention, ghi rõ giới hạn bằng chứng.

### 7.3. Cloud flow logs và sampling

Cloud flow logs có thể **aggregate records**, cung cấp fields/intervals khác nhau hoặc chỉ cho biết accept/reject theo điểm quan sát. Một số flow logs không đại diện đủ mọi packet hoặc direction. Cần đọc schema của platform đang dùng và không coi **sum(bytes)** là số byte nội dung đã ra khỏi tổ chức với độ chính xác tuyệt đối.

### 7.4. Kết hợp firewall deny logs

Một deny event có thể cho thấy egress policy chặn kết nối tới đích chưa duyệt. Tuy nhiên:

- Deny không chứng minh có dữ liệu đã truyền thành công.
- Allow không chứng minh có dữ liệu exfil.
- Không có record có thể do flow chưa qua sensor, sampling hoặc logging disabled.

Để điều tra phải hỏi **request đã tới đâu** và có telemetry ở từng hop hay không.

## 8. DNS telemetry và domain intelligence

DNS logs có thể liên kết **hostname được truy vấn, nguồn hỏi, record type, response code, thời điểm và resolver**. Đây là tín hiệu hữu ích trong egress monitoring, nhưng không phải chứng cứ upload.

### 8.1. Các dấu hiệu nên xem

| Dấu hiệu DNS | Giả thuyết ban đầu | Cần kiểm chứng |
| --- | --- | --- |
| Destination domain mới cho user/process | Ứng dụng mới hoặc kết nối bất thường | App inventory, endpoint process, owner |
| DNS query tới personal cloud storage | Khả năng chia sẻ ngoài kênh được duyệt | Tenant/account, upload action, policy |
| Domain reputation xấu với bằng chứng đáng tin | Có thể liên quan hạ tầng độc hại | Feed quality, DNS answers, actual connection |
| Query volume tăng mạnh | Retry loop, ndots/search hoặc hành vi bất thường | Baseline, resolver errors, application changes |
| DNS query lạ nhưng không có connection | Lookup-only, blocked connection hoặc cache | Network flow và app telemetry |
| DNS không có nhưng flow tới IP | Cache, direct-IP, proxy DNS, DoH hoặc logging gap | Process/proxy path và data source coverage |

### 8.2. DNS không xác thực HTTP destination

Một HTTPS request có thể đi qua proxy nơi hostname được resolve **ở phía proxy**, không ở client. Có thể có CDN/shared IP và cache. Do đó **“client không hỏi DNS cho domain X” không chứng minh client không truy cập X**.

### 8.3. DNS over HTTPS/DoT

Nếu ứng dụng dùng **DoH hoặc DoT** với resolver khác, corporate DNS logs có thể không thấy tên truy vấn. Phải xem **policy về approved resolvers, endpoint agent/proxy behavior và egress destinations**, không coi mọi DoH là tấn công: resolver mã hóa có thể là lựa chọn bảo vệ riêng tư hợp lệ khi được cho phép.

### 8.4. Domain risk không phải tenant risk

Các nền tảng cloud storage lớn có thể dùng một domain cho nhiều customers. **Cho phép domain của nhà cung cấp** không tự phân biệt **enterprise tenant** với **tài khoản cá nhân**. Muốn phân biệt cần dữ liệu từ **CASB/SaaS API, account/tenant identifiers, proxy-integrated identity hoặc endpoint DLP** nếu công nghệ hỗ trợ.

### 8.5. Không lộ thông tin trong tên miền

Query names có thể chứa tên nội bộ, project, máy hoặc dữ liệu cá nhân. DNS logs phải có **RBAC/retention/redaction** phù hợp, và tuyệt đối tránh đưa secrets vào phần tên hostname khi thiết kế ứng dụng.

## 9. Forward proxy, SWG và HTTP request telemetry

Một **Secure Web Gateway (SWG)** hoặc **forward proxy** có thể cung cấp access logs gắn với user/device, URL category, HTTP method, response status, bytes và policy decision, nhưng **chỉ với những luồng nó thật sự quản lý** và ở mức quan sát cho phép.

### 9.1. Proxy HTTPS theo CONNECT

Một proxy có thể nhận **HTTP CONNECT** để thiết lập tunnel tới hostname/port. Nếu chỉ tạo tunnel mà không giải mã TLS bên trong, proxy có thể biết **đích CONNECT, kết nối và byte counts**, nhưng **không nhất thiết biết HTTP POST/path/body bên trong**.

### 9.2. Proxy terminate/decrypt TLS

Khi proxy là một TLS endpoint có quyền xử lý nội dung theo chính sách, nó có thể quan sát **HTTP method, URL/path, MIME/content type, upload request body** trong những giới hạn kỹ thuật và pháp lý. Điều này có thể cấp tín hiệu cho DLP classifier và allow/block decisions.

Nhưng cần lưu ý:

- HTTP POST/PUT/PATCH thường có thể chuyển dữ liệu, nhưng **không đồng nghĩa mỗi POST là exfil**.
- Request body có thể compressed/encrypted ở tầng ứng dụng.
- Chunked/streamed HTTP, HTTP/2 multiplexing và long-lived connections làm quota/inspection phức tạp.
- CDN và shared SaaS domains làm **destination reputation** kém phân biệt account.
- TLS interception có thể làm hỏng client-certificate auth hoặc certificate pinning.
- Không phải mọi proxy nhìn thấy traffic **HTTP/3/QUIC** hoặc TCP direct bypass.

### 9.3. Một access log mẫu

~~~json
{
  "timestamp": "2026-11-28T10:03:11+07:00",
  "dataset": "synthetic-training-event",
  "user_ref": "employee-lab-042",
  "device_ref": "laptop-lab-17",
  "process_ref": "browser-approved",
  "destination_service": "cloud-storage-lab",
  "destination_tenant_class": "unapproved-personal",
  "http_method": "PUT",
  "request_bytes": 73400320,
  "response_status": 201,
  "policy_action": "alert",
  "tls_observation_mode": "approved-application-layer-proxy",
  "content_inspected": false,
  "request_id": "req-lab-https-egress-017",
  "synthetic": true
}
~~~

Record có **request_bytes lớn**, **destination_tenant_class không được duyệt** và status thành công. Đây là tổ hợp đáng điều tra. Nhưng vì **content_inspected=false**, log chưa chứng minh payload chứa PII hay secrets. Nếu nơi phát sinh sự kiện không có khả năng phân biệt tenant, không được bịa trường **destination_tenant_class** từ mỗi hostname.

### 9.4. Reverse proxy khác forward proxy

Reverse proxy bảo vệ **dịch vụ mà tổ chức công bố cho client**; forward proxy/SWG kiểm soát **client ra Internet**. Một public WAF/ingress gateway bảo vệ API inbound **không tự thấy upload từ nhân viên tới SaaS bên ngoài** nếu luồng đi theo route khác.

## 10. Endpoint telemetry, EDR và file-level DLP

**Endpoint DLP** và **EDR** thường có lợi thế khi cần liên kết **file access, tiến trình, user session và network connection** ở máy nguồn mà không phải giải mã toàn bộ HTTPS qua gateway.

### 10.1. Chuỗi tín hiệu đáng giá

Ví dụ một sự kiện kiểm tra:

1. Người dùng/tiến trình truy cập thư mục chứa dữ liệu được phân loại nhạy cảm.
2. Ứng dụng tạo file archive hoặc tập hợp nhiều tài liệu theo workflow.
3. Tiến trình phát sinh upload HTTPS ra một dịch vụ không thuộc danh mục đã phê duyệt.
4. SaaS audit/endpoint DLP có tín hiệu đích là **personal account**.
5. Không có change ticket hoặc business approval cho đợt chuyển dữ liệu.

Nhiều tín hiệu nhất quán tạo bằng chứng mạnh hơn **chỉ một file access hoặc một flow lớn**.

### 10.2. Process identity

EDR có thể cung cấp:

- Process executable path, signer, parent process và process tree.
- User context, device ID và tình trạng agent.
- File read/write/access events theo chính sách/khả năng.
- Network connection metadata theo process.
- Alert về hành vi bất thường hoặc malware.

**Process name hoặc signer hợp lệ không tự chứng minh một upload hợp lệ.** Browser hoặc công cụ đồng bộ được phê duyệt vẫn có thể bị dùng sai; mặt khác script backup hợp lệ có thể trông giống job đóng gói dữ liệu.

### 10.3. File classification

DLP có thể dùng:

- Data labels do tổ chức gắn.
- Phát hiện mẫu dữ liệu nhạy cảm theo chính sách.
- Exact Data Match (EDM) hoặc fingerprinting nếu nguồn được cho phép.
- File metadata, repository ownership, share permissions và policy labels.
- User/app context để phân biệt tác vụ nghiệp vụ.

Classifier có **false positives/false negatives**. Dữ liệu được mã hóa ở tầng ứng dụng, biến đổi định dạng hoặc nằm trong archive có thể vượt khả năng kiểm tra của một sensor; không kết luận “không có DLP match = không có dữ liệu nhạy cảm”.

### 10.4. Endpoint coverage

Đặt câu hỏi:

1. Có bao nhiêu **managed devices** đang chạy DLP/EDR healthy?
2. Chính sách có áp trên **macOS, Windows, Linux, mobile/BYOD** tương ứng không?
3. Có phân biệt user interactive uploads với **background service, backup hoặc agent** không?
4. Agent có thấy traffic của **containers, virtual machines và browser isolation** không?
5. Có offline mode, tamper resistance, log buffering và health alert không?

Mất agent hoặc telemetry coverage là **rủi ro đo lường**, không chứng minh không có data transfer.

## 11. SaaS, CASB và phân biệt tài khoản doanh nghiệp với tài khoản cá nhân

**Cloud Access Security Broker (CASB)** và các tính năng SaaS Security Posture Management (SSPM)/SaaS audit có thể hỗ trợ quan sát việc dùng dịch vụ cloud. Cần phân biệt hai hướng phổ biến:

- **Inline control:** traffic đi qua proxy hoặc điểm truy cập có thể kiểm tra theo danh tính, ứng dụng, session và chính sách.
- **API-based/out-of-band integration:** sản phẩm dùng API của SaaS để đọc audit, sharing activity, files/permissions hoặc policy events trong phạm vi được cấp; không cần thấy mọi packet trên mạng.

### 11.1. Hạn chế của từng hướng

| Hướng | Lợi thế | Giới hạn |
| --- | --- | --- |
| Inline SWG/CASB | Quyết định tại thời điểm request, có thể chặn upload trước khi hoàn tất | Cần traffic thực sự qua PEP; TLS visibility/compatibility |
| SaaS API audit | Biết user, account/tenant, sharing link, object ID và action theo API | Độ trễ, API rate limits, retention, quyền truy cập |
| Endpoint DLP | Gắn file/classification với process/user trước khi upload | Không bao phủ unmanaged endpoint hoặc SaaS-to-SaaS |
| Cloud activity audit | Biết cloud role, bucket/object/tenant và resource events | Không luôn nhìn data contents hoặc external endpoint hoàn chỉnh |

### 11.2. Domain allowlist không đủ

Một tổ chức dùng dịch vụ lưu trữ doanh nghiệp tại **storage.provider.example.test**. User có thể đồng thời đăng nhập một **personal account** trên cùng domain/platform. Nếu policy chỉ nói “allow provider domain”, nó có thể không phân biệt dữ liệu nào được tải lên **enterprise tenant** và dữ liệu nào vào **personal tenant**.

Giải pháp có thể gồm:

1. Xác định **approved tenant/account IDs**.
2. Dùng native SaaS sharing restrictions và audit API khi hỗ trợ.
3. Dùng **tenant restrictions** tại identity/proxy layer nếu sản phẩm có tính năng.
4. Dùng endpoint DLP gắn data classification vào thao tác chia sẻ.
5. Đánh giá browser profiles, managed apps và device posture.
6. Kiểm thử cả **web UI, API client, mobile/desktop sync và service accounts**.

Không giả định mọi SWG có khả năng đọc account ID từ traffic mã hóa, hoặc mọi SaaS đều hỗ trợ chính sách tenant restriction như nhau.

### 11.3. Chia sẻ link không giống upload

Trong một số SaaS, dữ liệu đã nằm trong tenant được duyệt nhưng user thay **sharing permission** để tạo public link hoặc cấp quyền cho external guest. Không nhất thiết có upload HTTPS lớn lúc đó. Vì vậy **exfiltration detection không chỉ dựa vào bytes outbound**; cần kết hợp **share-link, invite, download và external access audit**.

### 11.4. SaaS-to-SaaS transfers

Một ứng dụng SaaS được tích hợp với SaaS khác có thể chuyển dữ liệu **trực tiếp trong cloud**, bỏ qua văn phòng, VPN và gateway Internet của tổ chức. Nên inventory **OAuth grants, third-party integrations, connector permissions, app-to-app exports, webhook destinations** và log từ SaaS API.

### 11.5. Dữ liệu thuộc tenant có quyền nào?

Một file được sao chép tới **enterprise cloud tenant** vẫn có thể lộ nếu folder bị chia sẻ public. Ngược lại, một transfer tới nhà cung cấp bên ngoài có hợp đồng và DPA được duyệt có thể hợp lệ. Đánh giá phải dựa trên **resource owner, contract/authorization và data transfer policy**, không chỉ “nội bộ vs bên ngoài”.

## 12. Cloud workloads, containers và Kubernetes egress

Workloads trong cloud có thể truyền dữ liệu HTTPS qua **NAT Gateway, egress firewall, service mesh egress gateway, HTTP proxy, private endpoint hoặc direct Internet gateway**. Không phải tất cả luồng đều đi qua SWG của nhân viên.

### 12.1. Workload identity và data source

Đối với server/cloud, cần liên kết:

- **Service account/workload identity, cloud role, Pod/namespace**, node và image.
- Data access events từ database, object storage hoặc secrets manager.
- Destination FQDN/IP, TLS identity và egress path.
- IaC/deployment changes, CI/CD job identity, scheduled jobs.
- NetworkPolicy/security group/firewall và proxy policy quyết định.

**Một public NAT IP thường đại diện nhiều Pods hoặc VMs**; cần đủ log để quy về workload chứ không quy cho máy NAT chung.

### 12.2. Kubernetes NetworkPolicy

Kubernetes **NetworkPolicy chuẩn** chủ yếu mô tả **L3/L4 connectivity** qua Pod/namespace/IPBlock/port. Nó **không phải DLP classifier và không có field FQDN allowlist portable cho mọi CNI**.

Một NetworkPolicy chỉ cho workload đi qua egress gateway/proxy có thể hữu ích, nhưng phải xác minh:

1. CNI thực sự **enforce egress**.
2. Các Pods/namespace selectors đúng.
3. DNS path/CoreDNS/NodeLocal DNSCache còn hoạt động.
4. HostNetwork, privileged pods, NodePort, sidecar bypass và IPv6 được kiểm tra riêng.
5. NAT/Service translation không mở rộng đường ngoài ý muốn.

### 12.3. Egress gateway và policy theo workload

~~~mermaid
flowchart LR
    W["Approved workload Pod"] -->|"Egress only to approved proxy"| G["Kubernetes/Cloud egress gateway"]
    G -->|"HTTPS to approved SaaS/API"| EXT["Approved destination/account"]
    W -. "No direct Internet route" .-> UN["Other endpoints"]
    G -. "Flow + proxy telemetry" .-> S["Security analytics"]
    DB[("DB/Data store")] -. "Access audit" .-> S
    W -. "Workload identity" .-> S
~~~

**Egress gateway không tự ngăn Pod khác gọi backend database nội bộ**; cần microsegmentation east–west và application authorization. Cũng không tự chứng minh không có dữ liệu rò rỉ qua **private endpoint hoặc cloud account khác**.

### 12.4. Cloud private endpoint

Private endpoint có thể khiến lưu lượng đi qua private route mà không cần public Internet. Nhưng hành vi truyền dữ liệu giữa **cloud accounts/tenants** vẫn cần được xem xét dưới góc độ egress và data access:

- IAM role nào được phép ghi bucket/object?
- Resource policy có cho cross-account writes không?
- KMS key/certificate và object audit có đầy đủ?
- Dữ liệu nào được copy và đâu là account đích?

**Private path không đồng nghĩa authorized data sharing.**

### 12.5. Serverless và managed services

Một cloud function, ETL service hoặc managed export job có thể không chạy dưới CNI/agent truyền thống. Cần **cloud audit, IAM/resource policies, API gateway/proxy integrations và provider telemetry** phù hợp; không trông chờ EDR trên laptop phát hiện sự kiện này.

## 13. Baseline lưu lượng HTTPS theo hành vi và vai trò

Một **baseline** mô tả hành vi bình thường của user, service, application hoặc device theo thời gian và ngữ cảnh. Không nên dùng một ngưỡng như **“upload hơn 100 MB thì exfil”** cho mọi trường hợp.

### 13.1. Các chiều baseline

| Dimension | Ví dụ | Lý do |
| --- | --- | --- |
| **User/role** | Finance, developer, HR, contractor | Mức dùng dữ liệu khác nhau |
| **Workload/process** | Browser, backup agent, CI job, database export | Luồng tự động khác luồng tương tác |
| **Destination class** | Approved enterprise SaaS, vendor API, unknown | Quyền chuyển dữ liệu khác nhau |
| **Data class** | Public, internal, confidential, restricted | Risk severity khác nhau |
| **Time** | Business hours, monthly backup, quarter-end close | Có seasonality hợp lệ |
| **Direction** | Uploaded vs downloaded bytes | Chỉ phần đi ra phản ánh câu hỏi exfil |
| **Device trust** | Managed/compliant, unmanaged | Ngữ cảnh posture |
| **Account/tenant** | Enterprise-approved vs personal/unmanaged | Cùng domain có thể có nhiều đích |
| **Region/network** | Office, VPN, roaming, cloud region | Latency và routing khác nhau |

### 13.2. Ví dụ baseline giả lập

| Hoạt động | Median upload/ngày (giả lập) | P95 upload/ngày (giả lập) | Nhận xét |
| --- | ---: | ---: | --- |
| Sales → approved CRM | 30 MB | 120 MB | Nhiều tài liệu khách hàng được duyệt |
| Engineering → approved artifact registry | 450 MB | 3 GB | Build artifacts lớn là bình thường |
| Backup job → approved object storage | 90 GB | 140 GB | Theo lịch backup riêng |
| HR → approved HR SaaS | 15 MB | 65 MB | Dữ liệu nhạy cảm dù kích thước nhỏ |
| Contractor → restricted support portal | 4 MB | 18 MB | Quyền nhỏ, thời hạn ngắn |

**Các số liệu là minh họa đào tạo, không phải chuẩn ngành.** Trong vận hành cần thu thập baseline đủ kỳ, phân loại công việc và theo dõi seasonal workloads; không áp ngưỡng giống nhau.

### 13.3. Rolling baseline

Một detector có thể so **upload bytes trong 1 giờ/ngày** với rolling median, percentile hoặc robust statistics theo nhóm có ý nghĩa. Khi nhóm quá ít mẫu, cần dùng **peer-group baseline và chuyên gia duyệt**, không tạo ngưỡng tùy tiện từ một vài phiên.

### 13.4. Không học từ dữ liệu đã bị nhiễm

Nếu baseline giai đoạn huấn luyện có sẵn hành vi chia sẻ sai chính sách, detector có thể coi nó là “bình thường”. Vì vậy phải:

- Xác định **approved workflows** từ business owners.
- Loại/đánh dấu những incident periods được biết.
- Theo dõi policy drift khi ứng dụng mới hoặc kỳ báo cáo thay đổi.
- Không auto-update baseline ngay khi xuất hiện activity bất thường.

### 13.5. Một upload nhỏ có thể nghiêm trọng

Một file chứa API key hoặc danh sách khách hàng nhỏ có thể dưới mọi ngưỡng dung lượng. **Data sensitivity và destination authorization** quan trọng hơn kích thước tuyệt đối. Nên kết hợp **content-level policy ở điểm có quyền quan sát** và **source access events**.

## 14. Behavioral analytics và anomaly detection

### 14.1. Những tín hiệu có giá trị

1. **New destination** chưa từng có đối với user/workload và chưa được phê duyệt.
2. **Upload tăng bất thường** so với baseline cùng role/process.
3. **Unusual time/window** không khớp lịch làm việc/backup.
4. **Sensitive data access/export** ngay trước outbound flow.
5. **Process deviation**: ứng dụng chưa được duyệt kết nối ra ngoài.
6. **New SaaS tenant/account**, đặc biệt personal/unmanaged.
7. **IdP/EDR risk**: risky session, device non-compliant hoặc tiến trình bị cảnh báo.
8. **Multiple destinations** không liên quan nghiệp vụ trong thời gian ngắn.
9. **Policy bypass indicators**: direct egress/proxy bypass, IPv6 path khác.
10. **Contractor/privileged context** với data access ngoài vai trò.

### 14.2. Tương quan theo thời gian

Một chuỗi giả lập:

~~~text
09:01  IdP: user đăng nhập từ device đã được xác thực.
09:02  Data audit: user đọc nhiều tài liệu "Restricted".
09:04  Endpoint: tiến trình ngoài workflow thường đọc các file đó.
09:05  Proxy: upload 65 MB tới SaaS tenant chưa được phê duyệt.
09:05  Firewall: network flow outbound tương ứng.
09:06  SaaS audit: account đích nhận object mới, nếu nguồn audit có quyền.
~~~

Chuỗi tạo **giả thuyết nghi vấn exfiltration đáng điều tra**, nhưng SOC vẫn cần xem **ticket chuyển dữ liệu, owner approval, tài khoản đích và tính chính xác của identity mapping**. Không tự kết luận đã có dữ liệu bí mật bị lộ chỉ vì upload bytes gần lượng file đọc.

### 14.3. Nguyên tắc giảm false positive

- Loại trừ **approved backup/ETL schedules** có owner, đúng service identity và destination account.
- Không tạo allow exception vĩnh viễn chỉ theo process name.
- Dùng **destination tenant/account** thay vì domain chung khi có dữ liệu.
- Phân biệt release pipeline/artifact uploads với dữ liệu khách hàng.
- Có peer baseline và hiểu sự kiện định kỳ như báo cáo quý.
- Đòi **tối thiểu hai nguồn bằng chứng độc lập** trước tự động containment mạnh trong những workflow nhạy cảm, trừ khi chính sách bắt buộc block một hành vi rõ ràng.

### 14.4. Không nhầm volume với intent

Một user tải lên nhiều files nhỏ thay vì một file lớn vẫn có thể là workflow hợp lệ. Tương tự, upload lúc nửa đêm có thể do timezone hoặc batch processing. **Volume, thời gian và domain** chỉ là tín hiệu; cần **quyền và dữ liệu đích** để xác định hành vi trái chính sách.

### 14.5. Baseline drift và versioning

Mỗi detection policy nên có **version, ngày hiệu lực, baseline window, nguồn dữ liệu, trường được phép sử dụng và owner**. Khi hệ thống migration sang một nhà cung cấp mới, rule phải được re-evaluate thay vì tạo alert hàng loạt rồi tắt hết.

## 15. Phân loại dữ liệu và chính sách DLP

### 15.1. Data classification

Một mô hình có thể sử dụng:

| Nhãn | Ví dụ | Quy tắc chuyển dữ liệu gợi ý |
| --- | --- | --- |
| **Public** | Tài liệu công bố | Có thể share ngoài nếu hợp pháp |
| **Internal** | Hướng dẫn nội bộ | Chỉ kênh/doanh nghiệp được duyệt |
| **Confidential** | Hợp đồng, số liệu kinh doanh | Destination/recipient approved + audit |
| **Restricted** | Hồ sơ khách hàng, secrets, dữ liệu nhạy cảm | Strict allowlist, IAM, encryption, DLP |

**Các mức nhãn là minh họa**. Tổ chức phải áp theo quy định nội bộ/pháp lý, asset owner và dữ liệu cụ thể.

### 15.2. Chính sách theo ngữ cảnh

| Data class | Destination | Chủ thể | Hành động gợi ý |
| --- | --- | --- | --- |
| Public | Public company CDN | Approved publisher | Allow + publish audit |
| Internal | Enterprise storage tenant | Managed employee | Allow theo app policy |
| Confidential | Approved partner API | Service account đã phê duyệt | Allow với encryption, least privilege, logs |
| Confidential | Unmanaged personal cloud account | Employee | Block/quarantine hoặc require approval theo policy |
| Restricted | Unknown/unmanaged endpoint | Bất kỳ | Deny + incident triage |
| Restricted | Approved legal/HR vendor | Authorized workflow | Allow có điều kiện, audit và retention |

### 15.3. Những loại bằng chứng DLP

- Label trên file/document repository.
- Exact match/fingerprint của tài liệu được bảo vệ.
- Cloud data access/export action của user/service.
- Endpoint file access và process-to-network correlation.
- Inline content inspection khi có quyền và khả năng.
- SaaS tenant/account permission changes và download/export events.

### 15.4. Không suy từ MIME/content-type

HTTP **Content-Type** do client/server khai báo có thể không phản ánh nội dung thật. File extension, MIME và compression cũng không đủ xác định data sensitivity. **DLP policy cần content/label/source ownership kết hợp authorization**, không dựa một metadata dễ thay đổi.

### 15.5. Chú ý dữ liệu nhỏ và secrets

Data exfiltration có thể chỉ gồm **một token, một SSH key, một truy vấn DB xuất vài dòng**. Vì vậy thêm detection cho **secrets access, unusual copy/export, external share, cross-account permission changes** ngay cả khi tổng egress bytes thấp.

## 16. TLS inspection: giá trị, rủi ro và giới hạn

**TLS inspection** ở một proxy có quyền thường là quá trình proxy thiết lập hai hoặc nhiều phiên TLS, quan sát nội dung ở điểm kết thúc phiên TLS của nó rồi chuyển request tới upstream qua phiên bảo mật khác. Đây là **một quyết định tin cậy và quyền riêng tư nghiêm túc**, không đơn thuần bật một nút trong firewall.

### 16.1. TLS inspection có thể giúp gì?

Tùy proxy và ứng dụng, inspection có thể:

- Thấy **HTTP method/path/request metadata** để phát hiện upload.
- Kiểm tra **file labels, data patterns, document fingerprints** với DLP engine.
- Áp **destination category, tenant/account restrictions** nếu khả năng nhận dạng có hỗ trợ.
- Chặn hoặc quarantine request trước khi payload đến nơi đích.
- Ghi policy decision và chứng cứ đủ mức cần thiết.

### 16.2. Những chi phí và rủi ro

| Vấn đề | Rủi ro | Kiểm soát |
| --- | --- | --- |
| **Private data visibility** | Proxy/operator có thể thấy nội dung nhạy cảm | Legal/HR approval, least privilege, redaction |
| **Private CA deployment** | Phát hành CA/trust sai có thể tạo nguy cơ MITM | Bảo vệ keys/HSM, quản lý cert lifecycle |
| **Certificate pinning** | Client từ chối MITM proxy dù endpoint hợp lệ | Đánh giá bypass được phê duyệt hoặc endpoint DLP |
| **Client mTLS** | Proxy làm thay đổi peer identity và client cert handshake | Chọn pass-through hoặc thiết kế identity binding |
| **TLS 1.3/ECH/QUIC** | Traffic có thể không được quan sát theo cách mong đợi | Kiểm chứng protocol/visibility, không tự giả |
| **Latency/performance** | TLS/session cost, proxy capacity bottleneck | HA, scaling, SLO, canary |
| **Sensitive apps** | Banking/health/employee private sessions bị thu thập quá mức | Exclusion policy có căn cứ và data minimization |
| **Certificate validation** | Proxy bỏ validate upstream gây MITM | Bắt buộc xác minh upstream trust/name |
| **Data residency** | Payload/logs qua PoP ngoài phạm vi | Vị trí data plane và retention agreements |

### 16.3. Giới hạn khi HTTPS chứa payload mã hóa bên trong

Nếu ứng dụng **mã hóa file ở tầng ứng dụng trước khi upload**, dù proxy terminate TLS, DLP có thể chỉ nhìn thấy ciphertext/opaque object. Do đó vẫn cần **endpoint DLP, source repository labels và SaaS/object audit**. Không cố suy nội dung từ kích thước ciphertext.

### 16.4. Chính sách loại trừ phải có owner

Một số ứng dụng có thể cần **TLS inspection bypass** để bảo đảm tính riêng tư hoặc tương thích. Mỗi ngoại lệ nên ghi:

1. Host/app/owner và lý do.
2. Phạm vi user/device/resource được miễn.
3. Cách bảo vệ thay thế: endpoint DLP, SaaS audit, IAM/tenant restriction.
4. Thời hạn rà soát lại.
5. Bằng chứng rằng **bypass inspection không đồng nghĩa bypass toàn bộ egress policy**.

**Không bao giờ dùng chứng thư giả hoặc tắt kiểm tra danh tính TLS của upstream để che lỗi interception**. Nếu proxy không hỗ trợ app, chọn chế độ đường đi được thiết kế, không âm thầm hạ bảo mật.

### 16.5. Mục tiêu coverage đo được

Thay vì tuyên bố “100% HTTPS đã được kiểm tra”, nên báo cáo:

- Phần trăm traffic qua approved proxy.
- Phần trăm traffic phù hợp chính sách TLS inspection.
- Exclusions với owner, lý do, thời hạn.
- Số session opaque/TLS passthrough.
- Coverage của endpoint DLP và SaaS audit cho phần traffic không inspect.
- Direct egress/IPv6/QUIC path detection.

## 17. HTTP/2, HTTP/3/QUIC, ECH và các thay đổi quan sát

### 17.1. HTTP/2 trên TLS

HTTP/2 thường multiplex nhiều streams trên một kết nối TLS. Một passive observer thấy **connection-level flow** nhưng không phân biệt từng HTTP request/response nếu không giải mã. Proxy terminate TLS có thể tạo **per-request/per-stream metrics**, song các sản phẩm khác nhau về buffering, size limits và log schemas.

### 17.2. HTTP/3 qua QUIC

HTTP/3 sử dụng QUIC trên UDP (thường UDP 443). Một số giải pháp SWG/NGFW xử lý QUIC khác HTTPS/TCP; một số có thể chỉ quan sát network metadata, một số có khả năng QUIC-aware logging hoặc đưa traffic về các đường được quản lý theo chính sách.

**Không nên coi mọi UDP 443 là exfil hoặc áp mặc định “chặn QUIC là đã chặn HTTPS data exfil”.** Browser có thể fallback về TCP, ứng dụng hợp lệ có thể bị tăng độ trễ và vẫn còn HTTPS upload qua kênh khác.

### 17.3. TLS 1.3 và ECH

TLS 1.3 giảm một số handshake metadata nhìn được bởi passive sensors; ECH khi được hỗ trợ bảo vệ ClientHello nhạy cảm hơn. Trong các luồng đó:

- Đừng xây rule bắt buộc **true SNI** phải hiện trên mạng.
- Đừng giả định passive observer có thể đọc server certificate.
- Dùng **endpoint process/app visibility, approved DNS/proxy, flow stats và SaaS API audit** để bù khoảng trống.

### 17.4. Encrypted DNS và resolver governance

Ứng dụng dùng DoH/DoT có thể không xuất hiện trong managed DNS logs. Một chính sách tốt nên xác định **approved DNS resolvers**, đồng thời có **privacy và compatibility review**. Không làm lộ tên truy vấn chỉ để giám sát nếu endpoint DLP/tenant audit đã đủ cho use case.

### 17.5. WebSocket và long-lived HTTP connections

Ứng dụng có thể dùng WebSocket hoặc long-running streams; traffic upload không gói gọn trong một HTTP POST thông thường. Với những luồng này, cần metrics **duration, bytes by direction, identity, destination và application-level messages** nếu endpoint/app có logging thích hợp.

### 17.6. QUIC connection migration

QUIC có thể có hành vi chuyển đường theo network changes. Nếu firewall/collector dùng 5-tuple đơn giản, việc tổng hợp phiên và attribution có thể không khớp trực giác. Cần dựa vào **sensor semantics, endpoint identity, request/connection IDs khi được cung cấp** và chuẩn hóa trước khi so ngưỡng.

## 18. Egress bypass: phạm vi cần kiểm tra và cách phòng vệ

Một policy egress chỉ hiệu quả khi **mọi đường đi liên quan tới workload được bao phủ**. Trong bối cảnh phát hiện, “bypass” có thể là cấu hình nhầm, một workload cũ chưa qua proxy hoặc một hành vi chủ ý né PEP. Không phân loại nguyên nhân khi chưa có bằng chứng.

### 18.1. Những đường quan sát dễ bỏ sót

| Đường | Vì sao có thể bị bỏ sót | Kiểm soát |
| --- | --- | --- |
| **Direct TCP 443** | Workload không dùng proxy hoặc app ignores PAC | Network egress allowlist, endpoint/process telemetry |
| **HTTP/3/QUIC UDP 443** | Proxy chỉ hỗ trợ HTTPS/TCP hoặc log khác | Protocol-aware monitoring và policy phù hợp |
| **IPv6 public egress** | Firewall policy chỉ lập cho IPv4 | Dual-stack egress inventory và tests |
| **Cloud NAT khác** | Subnet có route tới NAT/gateway chưa quản lý | Route/firewall audit, centralized egress |
| **Private cloud endpoint** | Không qua Internet SWG | IAM/object audit, private endpoint policy |
| **SaaS-to-SaaS transfer** | Không đi từ thiết bị công ty | SaaS OAuth/integration inventory và API audit |
| **Unmanaged/BYOD device** | Thiếu endpoint DLP/EDR | Browser restrictions, SaaS control, ZTNA posture |
| **Kubernetes hostNetwork/privileged** | Có thể đi khác CNI egress policy | Admission, host firewall và privileged restrictions |
| **Alternate proxy/VPN** | Route qua hạ tầng không ghi log tập trung | Asset inventory và zero-trust route checks |
| **Encrypted DNS khác resolver** | Corporate DNS logs không thấy query | Approved resolver policy, alternative telemetry |
| **Out-of-band partner link** | Traffic không qua Internet gateway | Partner gateway, contract, route và audit |

### 18.2. Không dùng một allowlist domain chung làm DLP hoàn chỉnh

Nếu **cloud-storage.example.test** được duyệt, còn destination là personal account, domain allow có thể đúng nhưng **data transfer authorization** vẫn sai. Phải bổ sung **account/tenant-aware policy, classification và backend audit**.

### 18.3. Direct IP và certificate identity

Một process có thể tạo HTTPS connection tới một IP nhưng certificate vẫn dùng hostname; ngược lại có trường hợp TLS handshake thất bại do hostname mismatch. Đối với security detection, **đừng suy client không có domain chỉ vì flow log không ghi DNS query**; đối chiếu endpoint/proxy TLS server-name và route khi được phép quan sát.

### 18.4. IPv6 không phải ngoại lệ tùy chọn

Nếu tổ chức vận hành dual-stack, một policy IPv4 chặn đích không được duyệt có thể bị vô hiệu về kết quả thực tế nếu IPv6 route vẫn mở. **Test UDP/TCP, A/AAAA, client fallback, IPv6 firewall và cloud load balancers** theo topology đang dùng.

### 18.5. Nguyên tắc phòng vệ

1. Inventory **mọi egress points và routing domains**.
2. Default-deny đến những network segments đặc biệt nhạy cảm khi phù hợp, có exceptions được duyệt.
3. Tập trung Internet egress qua **approved SWG/proxy/firewall** đối với workloads cần kiểm soát.
4. Bảo vệ cloud/Kubernetes **route/NAT/security groups**, không chỉ cấu hình trên Pod.
5. Chặn hoặc phát hiện **proxy bypass/tenant misuse** theo sản phẩm hỗ trợ.
6. Duy trì telemetry coverage cho **private transfers và SaaS APIs**.
7. Kiểm thử **positive workflow** và **negative path** từ môi trường được cấp phép.

**Không dùng những kỹ thuật đi vòng cụ thể để thử trên hệ thống production không được phép**. Với bài lab có thể mô phỏng policy decision hoặc dùng endpoints giả lập trong network test riêng.

## 19. Thiết kế quy tắc phát hiện đa tín hiệu

Một rule mạnh cần biểu diễn được **điều kiện, bằng chứng, ngưỡng, ngoại lệ, độ tin cậy và hành động**. Không có một threshold phù hợp mọi doanh nghiệp.

### 19.1. Những nhóm tín hiệu

| Mã | Tín hiệu | Điểm mạnh | Hạn chế |
| --- | --- | --- | --- |
| **S1** | Upload bytes vượt baseline cho role/process | Dễ đo từ flow | Không biết nội dung |
| **S2** | Unapproved SaaS tenant/account | Chỉ đúng loại đích | Cần CASB/API/proxy hỗ trợ |
| **S3** | Sensitive data read/export trước upload | Liên kết nguồn dữ liệu | Audit có thể thiếu hoặc không gắn được user |
| **S4** | New destination/risky domain | Phát hiện môi trường đích khác thường | Reputation false positive |
| **S5** | Unusual process/device posture | Bổ sung nghi vấn endpoint | Process có thể hợp lệ |
| **S6** | Out-of-hours hoặc pattern khác lịch | Tìm lệch workflow | Timezone/batch/shift |
| **S7** | Direct/proxy-bypass egress | Phát hiện coverage violation | Có ngoại lệ hệ thống hợp lệ |
| **S8** | External sharing permission change | Không cần upload bytes | Chỉ có khi SaaS API audit |
| **S9** | Privileged access hoặc suspicious IdP event | Tăng ngữ cảnh rủi ro | Không trực tiếp chứng minh data loss |
| **S10** | DLP content/classification match | Bằng chứng dữ liệu mạnh hơn | False negatives và visibility limits |

### 19.2. Một chiến lược correlation

Ví dụ minh họa:

- **Low priority:** S1 đơn lẻ, nhưng ứng dụng có baseline chưa ổn định.
- **Medium priority:** S1 + S4, process không có owner hoặc chưa có phê duyệt.
- **High priority:** S1 + S2 + S3, cùng user/device trong time window hợp lý.
- **Critical review:** S3/S10 gắn dữ liệu Restricted với unapproved destination/account và có bằng chứng transfer thành công, hoặc có active compromise indicators.

**Mức độ ưu tiên tùy chính sách doanh nghiệp**, không phải một công thức chuẩn tự động kết luận sự cố.

### 19.3. Các trường buộc phải chuẩn hóa

Một event correlation có thể cần:

~~~text
timestamp_utc
identity.user_id / identity.service_id
endpoint.device_id / workload.pod_uid
process.entity_id
data.resource_id / classification / owner
network.flow_id / src_original / src_nat / dst / transport
proxy.request_id / method / bytes_up
destination.domain / cloud_tenant_id / account_id
policy.id / version / action
evidence.source / confidence / visibility_limit
~~~

Nếu một nguồn không có **cloud_tenant_id** hoặc **bytes_up**, cần để **unknown/not_observed**; tuyệt đối không tự suy giá trị chính xác từ destination IP hay tổng bytes.

### 19.4. Cửa sổ thời gian và tính nhân quả

Một database export và một upload gần nhau về thời gian chưa chắc cùng dữ liệu. SOC cần:

- Cùng subject/device/process chain, không chỉ cùng NAT IP.
- Timestamps chuẩn hóa và clock synchronization.
- Dữ liệu nguồn/đích được gắn ID/label hoặc evidence tương thích.
- Request/session IDs nếu proxy/App/SaaS hỗ trợ.
- Đánh giá các job nền hợp lệ chạy cùng lúc.

### 19.5. Alert severity không phải verdict pháp lý

Mục tiêu của detector là **ưu tiên điều tra hoặc thực thi policy có căn cứ**, không khẳng định motive hay gán nhãn cá nhân từ một vài tín hiệu. Triage phải có review và cơ chế sửa false positive.

## 20. Risk scoring và mô hình quyết định phòng vệ

Một score giúp SOC ưu tiên, nhưng chỉ hữu ích nếu **giải thích được tại sao tăng điểm** và đo được false-positive rate. Dưới đây là một ví dụ đào tạo, **không phải mô hình có thể chạy nguyên trạng hoặc tiêu chuẩn ngành**.

### 20.1. Bảng trọng số minh họa

| Tín hiệu | Điểm ví dụ | Cần bằng chứng |
| --- | ---: | --- |
| Upload vượt p95 của peer-group nhiều lần | +10 | Flow/proxy bytes theo chiều và baseline đủ mẫu |
| Tài khoản SaaS đích không được duyệt | +25 | CASB/SaaS/tenant-aware policy |
| Data class Confidential/Restricted vừa được truy cập | +25 | Data access/DLP/file label theo cùng principal |
| Device có high-risk EDR alert | +20 | EDR finding đã được xác minh |
| Destination mới, thiếu business owner | +10 | App inventory và domain/account metadata |
| Direct egress ngoài đường approved proxy | +15 | Route/firewall evidence thực |
| Phù hợp lịch backup/release đã duyệt | −25 | Job owner, service identity, lịch và approved destination |
| Có data-transfer ticket hợp lệ | −20 | Ticket resource/scope/time/owner khớp |

**Không cộng điểm khi nguồn thiếu dữ liệu.** Nếu không có tenant ID, không cho +25 chỉ vì domain của nhà cung cấp. Nếu log từ nhiều sensor là bản sao cùng một sự kiện, cần tránh **double counting**.

### 20.2. Giả mã xử lý sự kiện an toàn

~~~text
function detectPossibleHttpsExfil(events, baselines, appCatalog):
    observations = normalizeAndDeduplicate(events)
    groups = correlateByTrustedIdentityAndTime(observations)
    findings = []

    for group in groups:
        evidence = []
        limitations = []

        if group.hasVerifiedUploadBytes and baselineIsReliable(group):
            if uploadDeviatesMaterially(group, baselines):
                evidence.append("unusual_outbound_volume")

        if group.saasAccountId is verified:
            if not appCatalog.isApprovedAccount(group.saasAccountId, group.subject):
                evidence.append("unapproved_destination_account")
        else:
            limitations.append("destination_account_not_observed")

        if group.hasVerifiedSensitiveDataAccess:
            evidence.append("sensitive_data_access_near_transfer")

        if group.hasVerifiedEndpointRiskAlert:
            evidence.append("endpoint_risk")

        if group.networkPathIsOutsideApprovedEgress:
            evidence.append("egress_policy_gap")

        if matchingApprovedBusinessWorkflow(group, appCatalog):
            evidence.append("approved_business_context")

        confidence = scoreWithEvidenceQuality(
            evidence, limitations, preventDoubleCounting=true
        )
        if confidence warrants review:
            findings.append({
                "subject": group.redactedSubject,
                "resource": group.resourceId,
                "evidence": evidence,
                "limitations": limitations,
                "priority": confidence,
                "recommendation": "human_review_or_policy_action"
            })

    return findings
~~~

### 20.3. Phân biệt risk score và hành động

Một score cao **không đồng nghĩa quyền tự động khóa tài khoản, xóa file hay công bố danh tính**. Action phải dựa trên severity, chắc chắn của bằng chứng, nội dung policy, độ tin cậy sensor và rủi ro làm gián đoạn doanh nghiệp.

Một policy có thể chọn:

- **Observe:** ghi log và xây baseline.
- **Alert:** tạo case có evidence và business context.
- **Warn/justify:** yêu cầu người dùng xác nhận nghiệp vụ nếu sản phẩm hỗ trợ.
- **Block transfer:** chặn một upload rõ ràng vi phạm DLP policy tại PEP.
- **Quarantine session/device:** chỉ trong incident process, có rollback/owner.
- **Revoke credentials/permissions:** khi có evidence về account compromise và được phê duyệt.

### 20.4. Phân cấp confidence

| Mức | Ví dụ evidence | Cách diễn giải |
| --- | --- | --- |
| **Thấp** | Một flow lớn tới IP cloud | Bất thường định lượng, chưa có data/destination context |
| **Trung bình** | Flow lớn + process mới + đích chưa catalog | Cần triage và xác minh ownership |
| **Cao** | File Restricted + upload tới personal account + cùng user/device | Nghi vấn mạnh, cân nhắc block hoặc containment theo policy |
| **Đã xác minh transfer ngoài quyền** | SaaS/object audit + data owner + policy unauthorized + end-to-end correlation | Đủ để mở xử lý data loss theo bằng chứng; phạm vi phải điều tra |

**“Đã xác minh transfer” không mặc nhiên “đã xác minh người dùng cố ý thực hiện”**. Intent cần điều tra riêng và không nên suy đoán trong detector.

## 21. Truy vấn phân tích minh họa và ngưỡng theo baseline

Một truy vấn hữu ích phải nêu rõ **schema, đơn vị bytes, time window, data source và điều kiện thiếu dữ liệu**. Ví dụ dưới dùng **SQL giả định trên một bảng đã chuẩn hóa**, không phải lệnh cho một SIEM/cloud vendor cụ thể.

### 21.1. Schema logic

~~~text
egress_flow_events(
    timestamp_utc,
    identity_id,
    device_or_workload_id,
    destination_account_class,
    destination_service,
    transport_protocol,
    bytes_client_to_server,
    bytes_observed,
    path_approved,
    telemetry_source,
    event_id
)
~~~

**bytes_client_to_server** chỉ dùng khi flow collector xác nhận direction; nếu không, để NULL và loại khỏi phép tính upload direction. **destination_account_class** có thể là approved/unapproved/unknown, nhưng chỉ khi nguồn có cách kiểm chứng tenant/account thực.

### 21.2. Truy vấn tổng hợp outbound

~~~sql
-- PSEUDO SQL CHO DỮ LIỆU LAB, KHÔNG CHẠY TRÊN DATABASE THẬT.
-- Bảng đầu vào đã được deduplicate và direction được chuẩn hóa.
SELECT
    identity_id,
    device_or_workload_id,
    destination_service,
    destination_account_class,
    COUNT(*) AS observed_flows,
    SUM(bytes_client_to_server) AS bytes_up_observed
FROM egress_flow_events
WHERE timestamp_utc >= :window_start_utc
  AND timestamp_utc < :window_end_utc
  AND bytes_client_to_server IS NOT NULL
  AND transport_protocol IN ('TCP', 'UDP')
GROUP BY
    identity_id,
    device_or_workload_id,
    destination_service,
    destination_account_class;
~~~

Truy vấn này **chỉ tổng hợp dữ liệu đã quan sát**; không quyết định data sensitivity hay hành vi hợp pháp. **SUM trên flow sampled/duplicated** có thể sai lệch, cần normalize trước.

### 21.3. Thêm baseline/risk context

Thay vì hardcode 100 MB, sử dụng:

~~~text
daily_upload_observed = sum(verified_client_to_server_bytes)
peer_baseline_p95 = approved_benchmark(role, app, destination, weekday)
ratio = daily_upload_observed / max(peer_baseline_p95, safe_denominator)

if ratio is unusual and
   (unapproved_account or sensitive_source_data or high_risk_process):
    create_temporary_investigation_finding()
else:
    retain_observation_for_trend_analysis()
~~~

Các biến là **logic khái niệm**. Đừng áp threshold “ratio > N” cho mọi nhóm khi một HR record 50 KB đã có thể nhạy cảm hơn một backup 100 GB.

### 21.4. Xử lý dữ liệu thiếu

| Trường bị thiếu | Cách diễn giải |
| --- | --- |
| **User identity** | Có thể chỉ biết device/workload; đừng gán user từ NAT IP |
| **Process name** | Không suy mọi traffic từ browser |
| **Tenant/account ID** | Không thể kết luận enterprise vs personal chỉ từ SaaS IP |
| **HTTP method** | Không suy POST từ TCP 443 |
| **Upload bytes direction** | Không suy từ total flow bytes |
| **Data classification** | Không tự gán Restricted từ file size |
| **Policy verdict** | Không giả định allow/deny; phải đọc enforcement logs |
| **Exact transfer completion** | Connection open không chứng minh file hoàn tất |

### 21.5. Không biến truy vấn thành hồ sơ giám sát quá mức

Các trường định danh cần **purpose limitation, access control và retention**. Không nên xây bảng vĩnh viễn ghép chi tiết mọi URL người dùng với hồ sơ nhân sự chỉ để giải quyết vài use cases DLP; lưu bằng chứng đúng phạm vi, tránh thu thập thông tin không cần thiết.

## 22. Chính sách egress và DLP trung lập với sản phẩm

YAML sau mô tả **ý định bảo mật**, không thể dán trực tiếp vào firewall, Kubernetes NetworkPolicy, SWG, CASB, DLP hay SIEM. Mỗi mục phải được ánh xạ thành **control implementation + owner + test evidence**.

~~~yaml
httpsEgressDlpPolicy:
  name: detect-and-control-unauthorized-https-data-transfer
  environment: isolated-training
  owners:
    network: network-security
    endpoint: endpoint-security
    data: data-governance
    identity: identity-platform
    operations: soc
  protectedData:
    classificationLabels:
      - Public
      - Internal
      - Confidential
      - Restricted
    assignOwnerPerDataset: true
    trackApprovedExportWorkflows: true
  subjectAndDevice:
    identitySource: verified-idp-or-workload-identity
    postureSource: managed-edr-mdm
    noIdentityAttributionFromNatAlone: true
    protectSensitiveWorkloadCredentials: true
  destinationPolicy:
    approvedServices: owned-business-catalog
    approvedSaasTenants: explicitly-reviewed-account-ids
    distinguishPersonalAccountsWhenObservable: true
    prohibitUnapprovedSharingOfRestrictedData: true
    restrictCrossCloudAccountWrites: true
  networkPath:
    routeProtectedWorkloadsViaApprovedEgress: true
    manageDirectIpv4Ipv6Paths: true
    inventoryHttp3Quic: true
    documentApprovedDnsResolvers: true
    protectKubernetesHostNetworkPaths: separately
    protectPrivateEndpointsAndSaasToSaasFlows: separately
  inspection:
    requireLegalPrivacyReview: true
    doNotAssumeEveryTlsSessionIsDecryptable: true
    requireUpstreamTlsIdentityValidation: true
    exemptSensitiveCategoriesByReviewedPolicy: true
    coverExemptTrafficWithAlternativeSignals: true
  detection:
    learnBaselinesByRoleAndApplication: true
    normalizeUploadDirection: true
    useVerifiedAccountTenantIdentifiers: when-supported
    correlateDataAccessWithTransfers: true
    weightSensitiveDataMoreThanVolumeAlone: true
    avoidDuplicateSignalInflation: true
    requireEvidenceQualityAndLimitations: true
  actions:
    lowConfidence: observe
    mediumConfidence: triage-alert
    confirmedRestrictedDataToUnapprovedDestination: block-and-investigate
    highImpactContainment: human-approved-incident-process
    preserveAuthorizedBusinessOperations: true
  governance:
    auditAllPolicyAndExceptionChanges: true
    requirePositiveAndNegativeTests: true
    assignExceptionOwnersAndExpiry: true
    redactSensitiveTelemetry: true
    retainDataAccordingToApprovedPolicy: true
    verifyActualControlCoverage: true
    maintainRollbackPlan: true
~~~

### 22.1. Vì sao policy này không tự chặn traffic?

Ví dụ **prohibitUnapprovedSharingOfRestrictedData: true** chỉ là một tuyên bố. Phải cấu hình thực:

- Nguồn data classification/label.
- Đích và account/tenant có thể xác minh.
- PEP có khả năng chặn upload theo session.
- Các luồng bypass tại firewall/endpoint/cloud.
- Cơ chế exception owner và alert.
- Kiểm thử rằng **dữ liệu lab đã gắn Restricted bị chặn**, còn bản báo cáo hợp lệ được chuyển thành công.

### 22.2. Không sử dụng DLP thay cho IAM

DLP có thể phát hiện hoặc chặn một cách chia sẻ; IAM/authorization kiểm soát **ai đọc/export dữ liệu từ đầu**. Một attacker có token hợp lệ quá rộng có thể đọc cả hệ thống trước khi upload. Phòng vệ phải có **least privilege ở data source** cùng với egress policy.

### 22.3. Chính sách với ứng dụng có nội dung mã hóa đầu-cuối

Nếu proxy không xem được payload vì encryption ở tầng ứng dụng, policy phải dựa trên **endpoint data labels, account authorization, transfer metadata, SaaS audits và source access controls**. Không bịa kết quả DLP content match.

### 22.4. Chứng cứ enforcement

Sau khi bật policy, kiểm tra:

1. Transfer hợp lệ tới **approved tenant** vẫn pass.
2. Restricted synthetic file tới **unapproved account** bị chặn ở lớp được thiết kế.
3. Direct route/proxy bypass không bỏ qua kiểm soát được yêu cầu.
4. Alert/incident case có **rule ID, policy version, data source và source confidence**.
5. Các ngoại lệ TLS inspection có owner/expiry và compensating controls.
6. Cloud/Kubernetes workloads có coverage không phụ thuộc SWG của nhân viên.

## 23. Egress prevention và phản ứng theo độ nhạy cảm dữ liệu

**Prevention** có thể xảy ra trước khi traffic tới Internet, tại proxy, endpoint, cloud IAM hoặc một application-layer policy. Một tổ chức nên thiết kế nhiều lớp, nhưng không nên bật các hành động gián đoạn chỉ dựa vào volume anomaly.

### 23.1. Ma trận chính sách minh họa

| Use case | Data sensitivity | Đích nhận | Kiểm soát chính | Hành động gợi ý |
| --- | --- | --- | --- | --- |
| Backup database đã duyệt | Restricted | Enterprise backup account | IAM, storage policy, encrypted transfer, audit | Allow theo lịch và owner |
| HR export theo ticket hợp lệ | Confidential | Approved HR vendor tenant | User role, data owner approval, DLP, TLS | Allow có điều kiện + audit |
| Source artifact publish | Internal | Approved repository | Workload identity, repository access, hashes | Allow + baseline |
| User đưa file Internal lên personal cloud | Internal | Unapproved personal tenant | CASB/endpoint DLP/tenant policy | Warn/block theo policy |
| File Restricted tới unknown endpoint | Restricted | Unknown/unapproved | Endpoint DLP, egress firewall, source audit | Block + investigate |
| Unmanaged device tải hồ sơ khách hàng | Restricted | Bất kỳ | ZTNA posture, SaaS download control, app auth | Deny theo resource policy |
| SaaS public share link được tạo | Confidential | Unrestricted external sharing | SaaS sharing policy/API audit | Disable sharing + review theo quyền |
| Server workload upload sang cloud account mới | Restricted | Cross-account | IAM resource policy, cloud audit, egress controls | Deny/review theo approval |

### 23.2. Chặn tại nguồn dữ liệu khi phù hợp

Nếu dữ liệu Restricted không được xuất khỏi database, chính sách **database/export permissions** có thể loại bỏ nhu cầu phân biệt luồng HTTPS mã hóa sau đó. Nên phối hợp:

- Least privilege SELECT/EXPORT và field/row-level restrictions.
- API scopes, object/tenant authorization.
- KMS, access logs và data classification.
- Approved data export workflow với owner/ticket.
- DLP/egress policy ở các bước ra khỏi hệ thống.

**Một kết nối HTTPS có thể bảo mật về kỹ thuật nhưng vẫn sai về quyền dữ liệu**; kiểm soát ở source thường có tín hiệu nghiệp vụ tốt hơn firewall.

### 23.3. Chặn tại destination/account

Hạn chế upload tới **personal SaaS account** có thể cần broker nhận biết tenant/account; không chỉ domain/IP allowlist. Khi không có tính năng tenant-aware, dùng **SaaS native restrictions, managed browser/device policy và endpoint DLP** theo khả năng.

### 23.4. Block, alert và exception

Chính sách phản ứng nên có:

- **Block** với điều kiện cao độ chắc chắn, ví dụ Restricted data đã gắn nhãn tới external account không được duyệt.
- **Alert/triage** với metadata bất thường nhưng chưa biết payload.
- **User guidance/justification** với những lỗi thao tác vô ý khi sản phẩm hỗ trợ.
- **Temporary exception** được data owner phê duyệt, có time scope/recipient limit.
- **Post-event review** để cải thiện detection khi false positive có bằng chứng.

Không đưa vào exception các quy tắc kiểu **allow all personal storage** chỉ vì một phòng ban cần chuyển một số báo cáo hợp lệ.

### 23.5. Rủi ro tự động containment

Khóa tài khoản hoặc cô lập máy tự động có thể làm mất business availability, đặc biệt với service accounts/production clusters. Đối với các tín hiệu chưa chắc chắn, nên ưu tiên **bảo toàn bằng chứng, xác minh owner và quy trình phê duyệt**, trừ những policy được duyệt từ trước cho dữ liệu tối nhạy cảm.

### 23.6. Cải thiện coverage

- Device chưa quản lý: giới hạn quyền download tại SaaS/app.
- Workload không có agent: cloud IAM, VPC egress, API audit.
- TLS không inspect: endpoint data lineage + SaaS access.
- External third-party: hợp đồng, app/API audit, data handling controls.
- Hybrid/private network: segmentation và những điểm egress quan sát riêng.

## 24. Runbook: điều tra nghi vấn data exfiltration qua HTTPS

**Tình huống giả lập:** SOC nhận được một cảnh báo proxy: user lab vừa upload lượng dữ liệu cao hơn baseline tới một tài khoản cloud storage không thuộc danh sách doanh nghiệp. EDR cho thấy thiết bị đã truy cập nhiều tài liệu Confidential trước đó. Đây là **nghi vấn cần xử lý**, chưa đủ cơ sở để kết luận mức dữ liệu hoặc chủ ý.

### Giai đoạn 1 – Xác nhận alert và phạm vi

1. Xác định **alert ID, policy rule, data sources, confidence, timestamp**.
2. Kiểm tra trường **bytes_up** có xác minh direction hay là total traffic.
3. Kiểm tra có **TLS inspection, SaaS tenant data hoặc endpoint labels** hay không.
4. Kiểm tra destination domain/IP và **account/tenant identifier được xác minh**.
5. Tìm baseline đúng **role, app, process, time window**.
6. Kiểm tra alert trùng do proxy, firewall và NetFlow cùng ghi một session.
7. Xác nhận chủ thể bằng **IdP/EDR/NAT correlation**, không từ public IP chung.
8. Kiểm tra sự kiện có nằm trong **approved transfer/backup/change ticket** không.

**Kết quả bước này:** phân biệt genuine signal với logging error, job hợp lệ hoặc thiếu ngữ cảnh.

### Giai đoạn 2 – Xác nhận source data và luồng

| Câu hỏi | Nguồn evidence |
| --- | --- |
| User/process nào tạo upload? | Endpoint EDR/DLP, proxy auth session |
| Đã đọc/tạo/export dữ liệu nào? | File audit, database audit, object access logs |
| Dữ liệu mang nhãn gì? | Data catalog, file labels, owner |
| Đích nhận là domain hay đúng account nào? | CASB/SaaS audit, proxy tenant controls |
| Request có thành công không? | Proxy completion, SaaS object creation, network/session logs |
| Có workflow được phê duyệt không? | Ticket, owner và business schedule |
| Có malware/account compromise indicators không? | EDR/IdP risk, process lineage |
| Có dữ liệu đi qua kênh khác không? | Firewall/NAT/IPv6, cloud/SaaS audit |

Không chỉ đối chiếu **flow bytes ≈ file bytes** rồi khẳng định nội dung đã chuyển. Compression, TLS overhead, multiplexing và ứng dụng khác có thể làm số lượng tương tự nhưng không cùng đối tượng.

### Giai đoạn 3 – Đánh giá mức khẩn cấp

Một case ưu tiên cao khi có **đích account không được phê duyệt + sensitive data access + upload confirmed + credential/process anomaly**. Tuy vậy mức độ ảnh hưởng phải dựa trên:

- Data class và số record/object được xác định.
- Bên nhận, account ownership và khả năng external sharing.
- Account/workload privileges và khả năng tiếp tục xuất dữ liệu.
- Bằng chứng data access/download của bên nhận nếu có.
- Quy định xử lý sự cố, thời hạn thông báo theo pháp luật/hợp đồng liên quan.

**Không tự kết luận “bị lộ 100.000 hồ sơ” chỉ từ con số 100.000 records được truy vấn** nếu không có bằng chứng export/transfer tương ứng.

### Giai đoạn 4 – Containment có kiểm soát

Theo phân quyền IR/SOC và mức độ chắc chắn:

1. **Block đúng session/destination/account/upload rule** nếu PEP hỗ trợ.
2. Tạm giới hạn **user/service account access tới nguồn dữ liệu** khi có nguy cơ tiếp tục truy xuất.
3. Thu hồi token/credential nghi bị chiếm và bắt buộc authentication lại theo incident process.
4. Cô lập endpoint bị nghi compromise theo quyết định của IR owner, cân nhắc tác động.
5. Disable external share link hoặc quarantine file ở SaaS **qua tính năng và quyền được cấp**.
6. Giữ những luồng sản xuất hợp lệ bằng exception hẹp và monitoring thay vì cắt cả Internet gateway.
7. Bảo toàn logs và forensic artifacts với chain of custody phù hợp.

Không dùng hành động **xóa bằng chứng, phá hủy dữ liệu đích hoặc truy cập trái phép tài khoản cá nhân** để “thu hồi file”. Nếu dữ liệu đã ra ngoài, quy trình pháp lý/hợp đồng và vendor response phải được thực hiện đúng thẩm quyền.

### Giai đoạn 5 – Điều tra root cause

- Người dùng thao tác sai vì thiếu kênh chia sẻ được duyệt?
- Account bị chiếm qua phishing/MFA fatigue/session hijack?
- DLP policy không thấy payload do encryption ở tầng ứng dụng?
- Personal SaaS tenant không được phân biệt bởi domain allowlist?
- Egress bị bypass qua direct IP/QUIC/IPv6 hoặc cloud NAT?
- DB/API quyền export quá rộng?
- Connector/script/workload service account có excess privileges?
- SaaS sharing rules thiếu external recipient restrictions?
- Alert bị trễ do API audit ingestion hoặc flow sampling?

Phân biệt nguyên nhân **thiết kế**, **cấu hình**, **giám sát**, **tài khoản** và **ứng dụng**. Một incident thường có nhiều yếu tố góp phần.

### Giai đoạn 6 – Phục hồi và học hỏi

1. Kiểm tra transfer ngoài quyền đã dừng theo bằng chứng từ PEP/flows/SaaS.
2. Khôi phục legitimate workflows có quyền, không giữ blanket block dài hạn nếu làm gián đoạn không cần thiết.
3. Thu hẹp IAM/resource permissions và egress exceptions.
4. Bổ sung tenant-aware restrictions hoặc endpoint DLP nếu là gap.
5. Tái kiểm thử các đường IPv4/IPv6, proxy và SaaS-to-SaaS.
6. Đo MTTD/MTTR, false positives, affected objects, revoked sessions.
7. Giao owner/action/deadline và thực hiện follow-up control validation.
8. Giới hạn lưu giữ case data theo chính sách và bảo đảm người liên quan có quyền được bảo vệ.

### 24.1. Mẫu bảng điều tra

| Hạng mục | Trạng thái cần có |
| --- | --- |
| Source user/workload | Verified / suspected / unknown |
| Device/process | Verified / suspected / unavailable |
| Sensitive data objects | Identified IDs/classification hoặc unknown |
| Egress direction và amount | Observed metrics + sampling limitations |
| Destination domain/account | Verified account/tenant hoặc domain-only |
| Transfer completion | Confirmed / partial / unknown |
| Unauthorized nature | Owner/policy confirmation |
| Active compromise | Evidence present / absent / unknown |
| Containment actions | Owner, time, rollback, affected systems |
| Notifications | Legal/privacy/security review theo áp dụng |

### 24.2. Tách detection, confirmation và impact

Một detector có thể tạo alert từ 200 MB upload; SaaS audit sau đó xác nhận file mới; nhưng nội dung file thực tế chưa xác minh. **Ghi ba mức riêng:** có hoạt động đáng ngờ, có transfer thành công, và dữ liệu nào thực sự bị ảnh hưởng. Không rút gọn thành một câu kết luận vượt bằng chứng.

## 25. Case study 1: upload qua HTTPS tới tài khoản lưu trữ cá nhân

**Bối cảnh:** Tổ chức dùng một SaaS storage provider cho cả enterprise tenant và các tài khoản cá nhân. Employee laptop đã được quản lý, SWG ghi nhận một HTTPS upload **180 MB** tới domain của provider và không có alert domain reputation vì provider là dịch vụ uy tín.

### 25.1. Chuỗi sự kiện giả lập

~~~text
08:45  User đăng nhập IdP, MFA thành công.
09:02  Endpoint file audit: mở các báo cáo dự án có nhãn Confidential.
09:07  Endpoint DLP: những file đó được dùng trong một phiên upload.
09:08  SWG: HTTPS request bytes_up tăng đột biến.
09:09  CASB: account đích thuộc personal tenant không được phê duyệt.
09:10  SaaS audit: object mới được tạo trong account đích.
09:12  SOC: không tìm thấy approved transfer request cùng phạm vi.
~~~

Đây là **bản ghi huấn luyện**, không phải sự kiện người dùng thật. Những field như DLP file link, tenant ID và object creation chỉ xuất hiện nếu sản phẩm có hỗ trợ/cho phép quan sát.

### 25.2. Vì sao chỉ dùng firewall sẽ bỏ sót?

Firewall có thể thấy **destination SaaS IP/443**, tổng upload và cho phép vì IP/provider thuộc danh mục trusted. Nó **không tự biết tenant cá nhân**, nội dung hay quyền chia sẻ. Đây là khoảng trống giữa **destination service allowed** và **destination account authorized**.

### 25.3. Điều gì giúp tăng confidence?

- Source file audit xác định tài liệu Confidential, không chỉ dung lượng.
- Proxy/EDR liên kết cùng user/device/process và time window.
- CASB xác nhận personal account thay vì suy từ domain.
- SaaS audit xác nhận object được tạo.
- Application/data owner xác minh không có approval.

### 25.4. Hành động phù hợp

1. Dừng những uploads tiếp theo tới unapproved account theo policy nếu PEP hỗ trợ.
2. Bảo toàn evidence và kiểm tra tác động dữ liệu, không suy motive.
3. Xem xét user guidance, phishing/account risk và sự tồn tại kênh chia sẻ hợp lệ.
4. Siết SaaS tenant restrictions, app sharing controls và endpoint DLP.
5. Kiểm tra các browser/native sync/API client paths, IPv4/IPv6.
6. Tái chạy ca positive: approved account workflow vẫn hoạt động.

### 25.5. Bài học

**Cloud provider reputation không phải data authorization.** Khi nhiều tenants dùng chung dịch vụ, cần nhận biết **account/tenant đích hoặc nguồn dữ liệu**, không đủ chỉ cho phép tên miền.

## 26. Case study 2: cloud workload ghi dữ liệu qua HTTPS

**Bối cảnh:** Một analytics job trong Kubernetes có quyền đọc bảng tổng hợp khách hàng. Job chạy bằng service account, upload kết quả tới object storage qua một **cloud private endpoint**. Network team chỉ giám sát Internet egress qua forward proxy của nhân viên nên không thấy bất thường.

### 26.1. Điều tra bối cảnh

Một thay đổi IaC gần đây bổ sung quyền **write object tới một cloud account mới** cho workload. API audit ghi nhận export nhiều objects từ source storage và PutObject tương ứng ở account đích. Private endpoint không đi qua Internet gateway, và không có một file upload HTTPS rõ ràng tại SWG.

**Không thể coi “không có proxy log” là không có dữ liệu chuyển ra ngoài**. Một đường private cross-account transfer có thể cần xử lý theo data egress policy tương đương.

### 26.2. Kiến trúc kiểm soát

~~~mermaid
flowchart TD
    SRC[("Restricted dataset")] -->|"Approved DB/storage read"| JOB["Kubernetes analytics job"]
    JOB -->|"Private HTTPS endpoint"| EP["Cloud private service endpoint"]
    EP --> ACCOUNT["Cloud destination account"]
    JOB -. "Workload identity/Pod/namespace" .-> DET["Security detection"]
    SRC -. "Object/DB access audit" .-> DET
    EP -. "Cloud network logs" .-> DET
    ACCOUNT -. "Cloud account/object audit" .-> DET
    IAM["IAM + resource policies"] -. "Restrict account/resource/action" .-> EP
    NET["CNI/NetworkPolicy/cloud firewall"] -. "Constrain permitted paths" .-> JOB
    DET --> SOC["Triage and approved response"]
~~~

### 26.3. Những lỗ hổng tiềm tàng

| Lớp | Lỗ hổng | Cách khắc phục |
| --- | --- | --- |
| IAM | Service account có quyền ghi ngoài danh sách | Least-privilege role/resource policies |
| Cloud account | Cross-account destination chưa duyệt | Account/organization restrictions, audit |
| Network | Private endpoint path nằm ngoài SWG | Private path inventory/flow telemetry |
| Kubernetes | Workload egress policy rộng | NetworkPolicy/CNI và egress gateway theo khả năng |
| Data | Dataset được export không có owner approval | Data access/export authorization |
| Detection | Chỉ đo outbound TCP/443 public | Correlate cloud API/storage audit |
| Governance | IaC thay role mà không review | Change approval, policy-as-code và drift monitoring |

### 26.4. Tiêu chí xác minh

1. Workload chỉ được đọc các datasets được cấp quyền.
2. Writes chỉ tới **approved account/bucket/container**.
3. Mọi cross-account grant có owner/approval và audit.
4. NetworkPolicy và cloud network rules có bằng chứng enforcement.
5. Positive backup/ETL workflow tiếp tục hoạt động.
6. Negative test tới unapproved account bị từ chối theo IAM/resource policy.
7. Logs cho thấy **object/action/identity** dù payload vẫn mã hóa.

### 26.5. Bài học

**Data exfiltration không nhất thiết rời cloud qua Internet**. Cloud cross-account, SaaS integrations và private endpoints vẫn cần được đánh giá theo quyền dữ liệu, audit và đích nhận.

## 27. Ma trận kiểm thử an toàn cho HTTPS exfiltration detection

**Phạm vi:** chỉ dùng **lab network, synthetic files, fake identities, test SaaS tenants và cloud accounts do tổ chức kiểm soát**. Không dùng dữ liệu cá nhân hoặc bí mật thật; không tạo payload exfil cho tài khoản bên thứ ba; không thực hiện flood, scan hoặc làm quá tải proxy. Những trường hợp policy bypass được **mô phỏng có kiểm soát hoặc thử tại đường lab đã được cấp quyền**, không thử trên production trái phép.

### 27.1. Các ca kiểm thử

| Mã | Tình huống | Kết quả kỳ vọng |
| --- | --- | --- |
| T-01 | User hợp lệ upload báo cáo Public tới enterprise SaaS tenant | Allow, policy decision và audit đúng |
| T-02 | Backup job hợp lệ tải lượng dữ liệu lớn vào approved backup account | Không tự báo exfil chỉ vì volume |
| T-03 | Developer upload build artifact lớn tới approved registry | Baseline role/process tránh false positive |
| T-04 | HR user gửi synthetic Restricted file tới unapproved test account | DLP/policy block hoặc alert theo thiết kế |
| T-05 | Upload small synthetic secret marker tới unapproved account | Data classification quan trọng hơn byte threshold |
| T-06 | User upload lượng cao nhưng không có classification source | Alert có limitations, không kết luận Restricted |
| T-07 | Một NetFlow record có nhiều bytes nhưng direction unknown | Không gọi bytes là upload có xác nhận |
| T-08 | Cùng một session được ghi ở proxy và firewall | Deduplicate/correlate, không cộng hai lần |
| T-09 | Nhiều clients dùng một NAT IP | Attribution dùng source mapping/identity, không gán một user |
| T-10 | Destination domain là trusted SaaS nhưng tenant cá nhân | Tenant-aware policy nhận diện khi có evidence |
| T-11 | Cùng trusted domain vào enterprise-approved tenant | Allow theo policy, không chặn toàn provider |
| T-12 | SaaS external sharing link đổi từ private sang public trong test tenant | SaaS audit phát hiện dù egress bytes thấp |
| T-13 | SaaS-to-SaaS integration được cấp quyền truy cập file mẫu | API/integration audit có coverage |
| T-14 | OAuth app không được phê duyệt được cấp quyền test data | Governance/alert ghi nhận risky grant |
| T-15 | HTTPS flow không qua proxy đã được kiểm soát trong lab | Firewall/endpoint telemetry phát hiện path ngoài policy |
| T-16 | TCP 443 tới đích không được duyệt | Egress enforcement deny ở lớp được chỉ định |
| T-17 | UDP 443/HTTP/3 tới endpoint test được duyệt | Sensor coverage và protocol classification được ghi nhận |
| T-18 | HTTP/2 nhiều requests trên một TLS session | Không suy 1 flow = 1 upload object |
| T-19 | HTTP/3/QUIC connection thay đường trong lab | Collector attribution và limitations được ghi |
| T-20 | TLS 1.3 passive sensor không thấy server certificate | Không tuyên bố đã quan sát chứng thư từ ciphertext |
| T-21 | Client dùng ECH khi test environment hỗ trợ | Detection không phụ thuộc true SNI nhìn thấy |
| T-22 | TLS inspection được bật cho approved test app | HTTP metadata được log theo policy và privacy |
| T-23 | Client certificate/pinning test app không tương thích inspection | Exception được xử lý/ghi nhận, TLS verification không tắt |
| T-24 | TLS-inspection-exempt traffic phát sinh data upload test | Endpoint/SaaS audit là compensating telemetry |
| T-25 | HTTP content-type giả/không khớp test file | Không dùng MIME để kết luận sensitivity |
| T-26 | Đã mã hóa file ở tầng app trước TLS trong test | DLP ghi nhận visibility limit, không bịa plaintext inspection |
| T-27 | Process mới trên endpoint truy cập synthetic files và có outbound flow | Correlation nâng độ ưu tiên nhưng cần owner/approval |
| T-28 | Endpoint EDR không báo lỗi nhưng personal upload trái policy | DLP/tenant signals vẫn phát hiện |
| T-29 | Endpoint không có DLP agent | Coverage gap được báo; không kết luận không có transfer |
| T-30 | DNS query tên lạ không có outbound connection | Không kết luận transfer thành công |
| T-31 | HTTPS flow không có DNS log do resolver phía proxy | Đối chiếu proxy/DNS source đúng |
| T-32 | DoH/DoT từ ứng dụng được quản lý và phê duyệt | Không tự đánh dấu độc hại |
| T-33 | Unapproved resolver trong lab xuất hiện | Resolver governance/log phát hiện |
| T-34 | SaaS domain reputation thấp nhưng account/flow là workflow test hợp lệ | Human review tránh false positive |
| T-35 | Cloud Kubernetes Pod gọi approved external API | NetworkPolicy/egress gateway áp đúng route |
| T-36 | Kubernetes Pod thử egress ngoài allowlist trong lab | CNI/cloud policy chặn hoặc ghi event |
| T-37 | Pod hostNetwork khác Pod thường về egress | Host firewall/coverage được kiểm tra riêng |
| T-38 | IPv4 policy chặn nhưng IPv6 route test chưa được cấu hình | Dual-stack gap được phát hiện và sửa |
| T-39 | Cloud function/serverless test copy tới approved storage account | Cloud API audit gắn service identity |
| T-40 | Cloud workload thử ghi object mẫu tới unapproved cross-account destination | IAM/resource policy từ chối, không dựa SWG |
| T-41 | Application DB user xuất lượng lớn records trong lab | Data access/export alert có context |
| T-42 | Database export không có HTTPS flow tương ứng | Không kết luận có exfil từ data-access event đơn lẻ |
| T-43 | HTTPS upload cao trong cuối kỳ tài chính được phê duyệt | Baseline/ticket tránh alert không cần |
| T-44 | Synthetic Restricted upload đúng approved partner account | Allow có điều kiện và audit, không blanket block |
| T-45 | IdP/MDM high-risk state xuất hiện cùng transfer | Priority tăng theo evidence quality |
| T-46 | Policy mới làm false positive với backup job | Rollback/exception hẹp, kiểm chứng negative controls còn hiệu lực |
| T-47 | SaaS audit API đến trễ so với proxy logs | Correlation xử lý late events và update case |
| T-48 | Proxy, firewall, app và DB clocks lệch trong lab | Normalization/time skew được phát hiện |
| T-49 | SWG chỉ thấy CONNECT tunnel, không decrypt | Không tạo HTTP method/file evidence giả |
| T-50 | Direct private endpoint transfer ngoài Internet proxy | IAM/cloud account/resource audit phát hiện |

### 27.2. Cấu trúc evidence cho một bài test

Một ca đạt cần lưu:

1. **Test case ID, phạm vi được phép, môi trường và owner**.
2. Identity được che định danh; endpoint/workload và posture.
3. Source data: **test resource ID, classification** và ticket.
4. Destination: **FQDN/IP/service, account/tenant khi đã xác minh**.
5. Protocol: TCP/TLS, UDP/QUIC, HTTP version theo khả năng quan sát.
6. Network: bytes theo chiều, NAT mapping, proxy/egress path.
7. Application: file/share/object event và request status khi có.
8. Decision: allow/alert/block/unknown tại đúng PEP.
9. Expected/observed result, policy version và source limitations.
10. Không chứa password, access token, real PII, private keys hoặc real document content.

### 27.3. Positive tests quan trọng ngang negative tests

Nếu detector chặn mọi upload lớn, nó có thể làm backup, report distribution và build release thất bại. Bộ test phải xác nhận **authorized transfers còn hoạt động** theo chính sách, đồng thời những destination/tài khoản ngoài quyền được từ chối khi có khả năng enforcement.

### 27.4. Kiểm thử với file giả lập

Ví dụ tạo synthetic metadata, không sử dụng thông tin cá nhân thật:

~~~json
{
  "test_case": "T-04",
  "file_id": "synthetic-doc-restricted-001",
  "classification": "Restricted",
  "content_type": "synthetic-data-only",
  "actual_personal_data": false,
  "approved_destination_account": "enterprise-test-tenant",
  "attempted_destination_account": "unapproved-test-tenant",
  "expected_policy_decision": "block-or-alert-as-designed",
  "test_data_owner": "lab-security-team"
}
~~~

Không cần tạo một mẫu credential thật hoặc payload dữ liệu khách hàng để kiểm tra chính sách. **Synthetic labels và test tenants** có thể đủ để xác minh logic detection/PEP. Với classifier cần xem nội dung, dùng **mẫu kiểm thử được tổ chức phê duyệt** không chứa dữ liệu thật.

### 27.5. Điều kiện dừng test

Dừng và báo owner khi:

- Test traffic bất ngờ đi tới IP/account không thuộc lab.
- Có bằng chứng DLP/EDR collection chứa dữ liệu thật.
- Policy thay đổi làm gián đoạn production user/workload.
- Phát hiện điều kiện vượt phạm vi ủy quyền.

**Mục tiêu là kiểm thử phòng vệ, không chứng minh có thể gửi dữ liệu ra ngoài bằng thủ thuật né giám sát.**

## 28. Troubleshooting, tuning và giảm báo động sai

### 28.1. Alert xảy ra nhưng không thấy HTTP upload

Kiểm tra:

- Sensor chỉ thấy **TLS/NetFlow** nên không có HTTP method/payload.
- TLS session dùng **HTTP/2, HTTP/3, WebSocket hoặc opaque tunnel**.
- Proxy chưa bật L7 logging hoặc log sampling.
- Endpoint app dùng một đường không qua SWG.
- Event mới chỉ thể hiện **connection established**, chưa có completed object/upload audit.

Không ghi **HTTP POST confirmed** nếu chỉ có outbound TCP 443.

### 28.2. Upload lớn nhưng business owner nói hợp lệ

Xác minh:

1. **User/service identity** khớp đúng app owner/automation.
2. Dữ liệu được phép xuất, nguồn và destination account thuộc danh sách.
3. Transfer có ticket/contract/approved workflow.
4. Lịch, process/endpoint và volume phù hợp baseline.
5. Không có external sharing policy trái phép sau upload.

Nếu hợp lệ, tạo **exception cụ thể theo owner/app/account/time/risk** hoặc điều chỉnh baseline, không disable DLP cho cả provider domain.

### 28.3. Flow large nhưng proxy bytes nhỏ

Lý do có thể là:

- Hai sensors đo các chiều hoặc time windows khác nhau.
- Traffic không qua proxy, hoặc có những requests khác cùng connection.
- Firewall flow có retransmission/TLS overhead.
- NAT/session mapping hoặc sampling không khớp.
- Proxy request bytes chỉ tính HTTP body hoặc nội dung một request.

Cần normalize **đơn vị, field semantics, capture location và timeline** trước khi đánh giá.

### 28.4. DNS log có domain nhưng không có flow

Domain có thể đã được resolve nhưng client không kết nối, request bị blocked, DNS response cache/proxy route khác, hoặc hệ thống chỉ hỏi dự phòng. **DNS query không xác nhận data transfer.**

### 28.5. DLP content classifier không match

Xem:

- File có nhãn hoặc nguồn data classification đúng không?
- Sensor có thực sự **thấy payload** không?
- File có được mã hóa ở tầng app, compressed/streamed hoặc chuyển dạng không?
- Classifier có hỗ trợ type/size/encoding không?
- Có mất endpoint agent hoặc SaaS API permission không?

Không sửa bằng cách giả tạo **content classification** từ file size hay tên file.

### 28.6. Không có cảnh báo trên workload cloud

Nên kiểm tra:

- Workload traffic đi **NAT, private endpoint, egress gateway hay SaaS-to-SaaS**?
- Có CNI/NetworkPolicy logs và cloud resource audit không?
- Workload identity/account fields có được gửi tới SIEM không?
- Cloud API logs có **write/copy/export operation** không?
- Có ingestion delay, event sampling hoặc retention gap không?

Không khẳng định không có leak chỉ vì **employee SWG** không thấy lưu lượng.

### 28.7. False positives và false negatives

| Vấn đề | Ví dụ | Cách cải tiến |
| --- | --- | --- |
| **False positive** | Dev upload release artifact lớn | Baseline theo app/service account/registry |
| **False positive** | Tháng cuối quý có export hợp lệ | Seasonal workflow + approved ticket |
| **False positive** | CDN/destination vừa đổi IP | Inventory/reputation context, DNS/TLS data |
| **False negative** | Một secret nhỏ ra personal account | Data sensitivity/endpoint DLP |
| **False negative** | Sao chép SaaS-to-SaaS | SaaS integration audits |
| **False negative** | Traffic bypass proxy qua IPv6 | IPv6 route/firewall inventory |
| **False negative** | App-level encrypted payload | Source file labels + data access audit |
| **False negative** | Workload dùng private cloud endpoint | Cloud IAM/object audit |

### 28.8. Các KPI cho tuning

- **Alert precision** trong cases được review, theo detector và nhóm người dùng.
- **True-positive confirmation rate** với evidence quality tags.
- **Time to detection (MTTD)** và **time to contain (MTTC)**.
- **False-positive business cost**: block sai, mất thời gian user/SOC.
- **Coverage**: endpoint DLP, managed proxy, cloud audit, tenant-aware monitoring.
- **Unknown destinations/unknown identities/unknown bytes direction**.
- **Policy bypass exposure**: số đường proxy/IPv6/host/cloud path thiếu coverage.
- **Exception count và thời hạn**, dữ liệu nhạy cảm ngoại lệ.
- **Data owner sign-off** và hiệu lực object authorization ở nguồn.

### 28.9. Tính riêng tư và quản trị model

Nếu dùng anomaly model hoặc machine learning, phải document **features, training window, drift, false-positive evaluation, decision thresholds, bias/seasonality**. Quyết định ảnh hưởng người dùng cần có **human oversight** và khả năng giải thích, không tự áp biện pháp nghiêm trọng chỉ từ một score không minh bạch.

## 29. Câu hỏi ôn tập và bài tập thiết kế

### Câu hỏi 1 – Vì sao HTTPS hợp lệ không chứng minh transfer được phép?

**Gợi ý:** TLS bảo vệ kết nối nhưng không xác nhận user có quyền mang dữ liệu nào tới tài khoản nào.

### Câu hỏi 2 – NetFlow/IPFIX có thể đọc tên file và payload HTTPS không?

**Gợi ý:** Không. Flow thường thấy IP/port/bytes/time; cần endpoint, proxy có quyền hoặc SaaS audit.

### Câu hỏi 3 – Tại sao TLS 1.3 ảnh hưởng tới khả năng thấy server certificate ở passive IDS?

**Gợi ý:** Certificate handshake được mã hóa theo quy trình TLS 1.3, không mặc định hiện rõ như một số TLS 1.2 captures.

### Câu hỏi 4 – ECH làm thay đổi việc dựa vào SNI như thế nào?

**Gợi ý:** True hostname có thể bị che; outer SNI không nhất thiết là đích ứng dụng cuối cùng.

### Câu hỏi 5 – Một HTTPS flow có bytes_client_to_server lớn có phải upload file nhạy cảm không?

**Gợi ý:** Chưa thể biết; cần HTTP/app/file data, baseline và destination authorization.

### Câu hỏi 6 – Vì sao domain allowlist của cloud provider không phân biệt account?

**Gợi ý:** Nhiều tenants/accounts dùng cùng domain/IP; cần tenant-aware/SaaS audit/DLP.

### Câu hỏi 7 – Tại sao HTTP CONNECT proxy log không đủ biết PUT/POST?

**Gợi ý:** CONNECT có thể chỉ tạo một TLS tunnel; proxy không terminate/decrypt request bên trong.

### Câu hỏi 8 – Nên kết hợp data access logs và outbound flow ra sao?

**Gợi ý:** Cùng identity/process/time window, data classification, destination account và request IDs; chú ý correlation không tự chứng minh cùng file.

### Câu hỏi 9 – Vì sao một file chứa secret nhỏ vẫn cần alert?

**Gợi ý:** Impact từ tính nhạy cảm lớn hơn upload volume.

### Câu hỏi 10 – TLS inspection có những rủi ro chính nào?

**Gợi ý:** Quyền riêng tư, private CA trust, certificate pinning/mTLS, latency, data residency và nội dung mã hóa tầng ứng dụng.

### Câu hỏi 11 – HTTP/3 thường liên quan protocol nào?

**Gợi ý:** QUIC thường trên UDP, nhưng không suy mọi UDP 443 là HTTP/3.

### Câu hỏi 12 – Vì sao không có DNS log chưa chứng minh không có HTTPS connection?

**Gợi ý:** Cached DNS, proxy-side resolution, DoH/DoT, direct IP hoặc telemetry gap.

### Câu hỏi 13 – Thế nào là visibility gap trong Kubernetes?

**Gợi ý:** CNI/hostNetwork/NAT/private endpoint có thể đi ngoài employee SWG; cần cloud/workload logs riêng.

### Câu hỏi 14 – Đích SaaS cùng domain nhưng account personal thay đổi quyết định ra sao?

**Gợi ý:** Dữ liệu có thể ra khỏi authorized enterprise tenant dù provider vẫn trusted.

### Câu hỏi 15 – Một event database EXPORT đã đủ xác nhận exfiltration chưa?

**Gợi ý:** Chưa. Cần xem dữ liệu sau export đi đâu, transfer completion và quyền nghiệp vụ.

### Câu hỏi 16 – Vì sao auto-block từ volume anomaly đơn lẻ có thể nguy hiểm?

**Gợi ý:** Backup/release hợp lệ có thể rất lớn; mất availability và gây false positives.

### Câu hỏi 17 – Khi flow và proxy log không cùng số bytes, nguyên nhân nào cần xét?

**Gợi ý:** Direction, request/body semantics, sampling, retransmission, NAT, compression và thời gian capture.

### Câu hỏi 18 – Khi điều tra, cần phân biệt ba mức kết luận nào?

**Gợi ý:** Có nghi vấn từ tín hiệu, có transfer hoàn tất theo bằng chứng, và dữ liệu nào ngoài quyền thực sự bị ảnh hưởng.

### Câu hỏi 19 – Vì sao cloud private endpoint vẫn nằm trong phạm vi data egress?

**Gợi ý:** Cross-account copy có thể là chuyển dữ liệu ngoài tổ chức dù không đi Internet public.

### Câu hỏi 20 – Những bằng chứng nào cần bảo vệ quyền riêng tư?

**Gợi ý:** User/device IDs, browsing/upload activity, file names/labels, request metadata, tenant/account và DLP matches.

### Bài tập thiết kế tổng hợp

Một công ty có **1.000 endpoints**, hai vùng Kubernetes, SaaS enterprise storage, cloud object storage và hệ thống HR/Finance/Engineering. Người dùng làm việc ở văn phòng, VPN và ZTNA. Workloads dùng cả NAT Internet và private endpoints; doanh nghiệp muốn phát hiện việc dữ liệu **Confidential/Restricted được đưa ra ngoài qua HTTPS** nhưng không gây gián đoạn backup/build và không buộc giải mã mọi HTTPS.

Hãy thực hiện:

1. Vẽ **data source → endpoint/workload → DNS/proxy/egress gateway → destination** và các trust boundaries.
2. Lập inventory các **user roles, devices, processes, workloads, source data classes, approved tenants/accounts, egress paths**.
3. Nêu chính xác **flow/TLS metadata nào nhìn được và không nhìn được** trong TLS 1.3, ECH, QUIC.
4. Thiết kế routing/effective egress controls cho endpoint, on-prem servers, Kubernetes Pods, hostNetwork và cloud private endpoints.
5. Thiết kế **endpoint DLP + proxy/SWG + SaaS API/CASB + database/object audit** phối hợp.
6. Lập ma trận quyền upload cho HR, Finance, Developer, Backup service và Contractor theo classification và account.
7. Định nghĩa **correlation keys** giữa IdP, device, process, DB access, flow, proxy request và SaaS object event.
8. Thiết kế **baselines** theo role, process, destination và seasonality thay vì threshold chung.
9. Mô tả một **risk scoring rule** có yếu tố data sensitivity, tenant destination, endpoint risk và workflow exception.
10. Giải thích **false positives** của build/backup và false negatives của secrets nhỏ.
11. Nêu điều kiện khi TLS inspection có lợi và khi cần pass-through với compensating controls.
12. Thiết kế chính sách cho **HTTP/3/QUIC, IPv6, DoH/DoT và direct routes** không dựa vào việc mọi flow phải decrypt.
13. Chỉ ra cách phát hiện **SaaS personal account** dùng chung domain với enterprise tenant.
14. Thiết kế cloud IAM/resource controls để chặn **cross-account object writes** ngoài danh sách.
15. Xây **ít nhất 15 positive/negative tests** bằng synthetic data, không dùng PII thật.
16. Xây runbook **triage → confirmation → containment → impact assessment → recovery** với evidence limitations.
17. Đặt KPI: detection coverage, precision, MTTD/MTTC, source/data attribution và exception expiry.
18. Xác định **privacy/retention policy và human-review gate** trước khi xử lý account/user.

**Tiêu chí đạt:** hệ thống có thể phát hiện hoặc chặn những transfers **thực sự trái quyền** bằng tín hiệu nhiều lớp; vẫn cho nghiệp vụ hợp lệ chạy; và phân biệt rõ **network metadata, upload completion, data classification, account ownership và application authorization**.

## 30. Những điều cần ghi nhớ

- **HTTPS/TLS bảo vệ kênh truyền, không xác nhận quyền chuyển dữ liệu.** Một kết nối có TLS hợp lệ vẫn có thể bị lạm dụng để gửi dữ liệu ra ngoài.
- **Data exfiltration phải được đánh giá theo dữ liệu, chủ thể, đích nhận, mục đích và quyền**, không chỉ theo cổng 443 hoặc tổng bytes.
- **Flow/NAT logs cho network metadata**; passive TLS sensors không tự xem HTTP payload. TLS 1.3, ECH, HTTP/2 và QUIC còn ảnh hưởng độ bao phủ của từng trường.
- **Forward proxy chỉ tạo CONNECT tunnel không tự biết HTTP method/file**; TLS inspection có thể quan sát hơn nhưng cần quyền riêng tư, cert validation và compatibility review.
- **Endpoint EDR/DLP, proxy/SWG, DNS, cloud storage audit, SaaS/CASB và ứng dụng** cung cấp những mảnh bằng chứng khác nhau; cần tương quan đúng người dùng, workload và time window.
- **Cloud provider/domain được tin không đồng nghĩa account/tenant đích được duyệt**; personal SaaS tenants và external shares cần cơ chế kiểm soát riêng.
- **Data sensitivity quan trọng hơn dung lượng**: một secret nhỏ có thể nghiêm trọng hơn một bản backup lớn được phê duyệt.
- **Baseline phải theo role, app, process, destination, lịch và approval**, không lấy ngưỡng byte chung cho mọi workload.
- **Risk score là công cụ ưu tiên điều tra, không phải phán quyết về chủ ý**; không suy fields thiếu hoặc cộng lặp cùng một sự kiện.
- **Egress coverage phải bao gồm TCP/HTTPS, HTTP/3/QUIC, IPv6, direct proxy bypass, Kubernetes/hostNetwork, cloud NAT và private endpoints** theo topology thực.
- **Private cloud cross-account và SaaS-to-SaaS transfers cũng là các đường dữ liệu ra ngoài**, dù không đi qua Internet proxy của nhân viên.
- **DLP không thay IAM và business authorization ở nguồn dữ liệu**; cần hạn chế export/read và kiểm tra người nhận.
- **Containment phải có bằng chứng, quyền và tác động được đánh giá**, bảo toàn logs, tránh xóa hoặc truy cập tài sản bên ngoài trái phép.
- **Kiểm thử bằng dữ liệu tổng hợp và tài khoản lab** phải có cả allow hợp lệ và deny ngoài chính sách; không dùng dữ liệu khách hàng hoặc secrets thật.
- **Một alert chỉ xác nhận nghi vấn**, còn kết luận về transfer hoàn tất và dữ liệu bị ảnh hưởng cần chứng cứ độc lập, được ghi rõ giới hạn.
