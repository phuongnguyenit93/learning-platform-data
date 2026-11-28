# Cô lập endpoint mà vẫn giữ bằng chứng: Ra quyết định và thực hiện trong ứng phó sự cố mạng

## 1. Vì sao cô lập endpoint không chỉ là “rút dây mạng”?

Khi phát hiện một máy trạm có dấu hiệu nhiễm mã độc, một máy chủ tạo kết nối bất thường hoặc một máy ảo bị nghi sử dụng để truy cập trái phép, thao tác nhanh nhất có vẻ là **ngắt mạng hoặc tắt máy**. Nhưng hai hành động này có hệ quả khác nhau và có thể làm mất những bằng chứng thiết yếu: kết nối TCP đang tồn tại, tiến trình chạy trong RAM, khóa giải mã đang hiện diện trong bộ nhớ, dữ liệu chưa được ghi xuống đĩa hoặc dấu vết của kẻ tấn công đang tương tác.

Ngược lại, chần chừ để thu thập chứng cứ cũng có thể tạo điều kiện cho **đánh cắp dữ liệu, mã hóa ransomware, di chuyển ngang và phá hoại** tiếp tục. Người ứng phó phải cân bằng **giảm thiểu thiệt hại ngay lập tức** với **giữ bằng chứng có tính xác thực, toàn vẹn, nguồn gốc và khả năng phân tích**. Đây là một quyết định kỹ thuật lẫn nghiệp vụ, không phải một quy trình cứng luôn “capture RAM trước rồi mới cô lập”.

~~~text
Tín hiệu: EDR cảnh báo một host đang liên lạc với đích đáng ngờ
          |
          v
Xác minh host / mức tác động / mức chắc chắn / sự cố đang diễn ra
          |
          +-- Nguy cơ mất dữ liệu hoặc lây lan ngay?
          |      -> Cô lập theo phương án an toàn khả thi, đồng thời
          |         bảo toàn telemetry và ghi lại mọi thay đổi
          |
          +-- Có cửa sổ thu thập nhanh, có người và công cụ được phép?
                 -> Thu chứng cứ dễ mất được ưu tiên, rồi cô lập
          |
          v
Xác nhận ranh giới cô lập thực sự hoạt động
          |
          v
Thu thập, lập timeline, chain of custody và điều tra nguyên nhân
~~~

**Thông điệp quan trọng:** mục tiêu là **ngăn hành vi gây hại trong khi giữ lại tối đa chứng cứ đáng tin**. Không hy sinh an toàn của tổ chức hoặc con người chỉ để có một ảnh RAM “đẹp”, và cũng không tắt máy mặc định khi còn biện pháp cô lập mạng ít phá hủy hơn.

### Mục tiêu học tập

Sau bài học, người học có thể:

1. Phân biệt **detection, triage, containment, evidence preservation, eradication và recovery**.
2. Xác định **endpoint** cần cô lập, identity của nó và những đường kết nối có thể đi vòng qua policy.
3. Chọn mức cô lập theo **mức nguy hiểm, tính khẩn cấp, độ tin cậy của thông tin và tác động nghiệp vụ**.
4. Nhận diện chứng cứ **dễ mất (volatile)**, chứng cứ trên đĩa và các nguồn lưu vết bên ngoài host.
5. Áp dụng quy tắc **chain of custody**, thời gian UTC, hash, phương thức thu thập và tài liệu hóa mọi thay đổi.
6. Phân tích ưu/nhược của EDR network containment, NAC/quarantine VLAN, firewall ACL, VPN revocation, VM/cloud isolation và shutdown.
7. Thu thập thông tin quan sát có giới hạn trên Windows/Linux mà không nhầm **lệnh chỉ xem** với **forensic acquisition không gây thay đổi**.
8. Kiểm tra cô lập theo cả **egress, ingress, IPv4/IPv6, Wi-Fi/VPN, management plane** và các phiên đã thiết lập.
9. Bảo vệ evidence khỏi bị xóa, ghi đè, thay đổi time zone, lộ secrets hoặc truy cập bởi người không được phép.
10. Xây playbook, test matrix và runbook để bàn giao cho điều tra số và khôi phục hệ thống.

Chủ đề nằm trong chương **Ứng phó sự cố mạng** thuộc module **SECURITY_NETWORK_SECURITY**: vận dụng kiến thức phân đoạn, firewall, VPN, IDS/IPS, DNS, cloud network, packet capture, TLS và giám sát xâm nhập để kiểm soát sự cố **mà không phá hủy khả năng tìm ra sự thật**.

> **Quy tắc thực hành:** chỉ cô lập hoặc thu thập dữ liệu trên tài sản và phạm vi được tổ chức cho phép. Các lệnh và mẫu phiếu bên dưới là hướng dẫn cho môi trường lab hoặc quy trình IR có thẩm quyền; không tự áp lên production, không mở file cá nhân ngoài phạm vi phê duyệt, không tắt máy/đổi ACL/xóa malware hoặc rút ổ đĩa nếu chưa đánh giá hậu quả. Nếu nghi sự cố đang gây nguy hại tức thời, ưu tiên an toàn, thông báo người chỉ huy sự cố và làm theo emergency playbook đã duyệt.

## 2. Khái niệm: cô lập, bảo toàn, thu thập và phục hồi

| Hoạt động | Mục đích | Ví dụ | Không phải |
|---|---|---|---|
| **Triage** | Xác minh dấu hiệu, phân loại mức độ khẩn cấp | So EDR alert với host, user, traffic, change timeline | Kết luận mã độc chỉ từ một IP |
| **Containment** | Giảm khả năng kẻ tấn công tiếp tục gây hại | EDR isolation, ACL chặn egress, quarantine VLAN | Diệt sạch mã độc |
| **Evidence preservation** | Giữ khả năng xác minh điều gì xảy ra | Đóng băng retention, bảo vệ EDR logs, niêm phong ảnh chứng cứ | Chỉ sao chép vài screenshot |
| **Acquisition** | Thu chứng cứ với quy trình có kiểm soát | Memory capture, disk image, log export, network flow records | Bảo đảm dữ liệu luôn không bị thay đổi |
| **Analysis** | Dựng timeline, xác định phạm vi/đường tấn công | Ghép process tree, DNS, proxy, identities và flows | Thay thế đánh giá pháp lý |
| **Eradication** | Loại bỏ khả năng duy trì xâm nhập | Reimage, revoke/rotate credentials, sửa vulnerability | Thực hiện trước khi đã giữ bằng chứng cần thiết |
| **Recovery** | Phục hồi dịch vụ trong trạng thái đáng tin | Build lại từ image sạch, test policy và telemetry | Mở mạng lại chỉ vì host ping được |

**Endpoint** trong bài là hệ thống đầu cuối có thể bị xâm nhập: laptop, workstation, server, VM, container/Pod, thiết bị IoT/OT hoặc workload đặc thù. **Không phải mọi endpoint đều có EDR agent hoặc ổ đĩa bền vững.** Phương án cô lập và bảo toàn phải phù hợp hệ điều hành, quyền quản trị, thời gian tồn tại và mức tác động vận hành.

### 2.1. Những thuộc tính cần giữ khi thu chứng cứ

- **Integrity:** nội dung bản chứng cứ không bị sửa ngoài quy trình có giải thích.
- **Authenticity/provenance:** chứng cứ đến từ đúng host/nguồn/tenant, được thu bởi ai và bằng công cụ nào.
- **Completeness trong phạm vi:** những nguồn quan trọng có được thu không; thiếu phần nào phải nêu.
- **Repeatability:** người độc lập có thể kiểm tra lại phương pháp, hash, timeline và kết quả.
- **Confidentiality:** chứng cứ có thể chứa credentials, dữ liệu khách hàng, dữ liệu cá nhân; phải mã hóa và giới hạn người xem.
- **Chain of custody:** theo dõi liên tục ai nhận, lưu, bàn giao, phân tích và di chuyển chứng cứ.

### 2.2. Tác động của mỗi thao tác tới bằng chứng

Ngay cả lệnh có vẻ chỉ đọc như `ps`, `ss`, `Get-Process` hay một truy vấn EDR vẫn có thể làm thay đổi trạng thái hệ thống: thêm process, cache, command history, audit event, timestamps hoặc thay đổi RAM. **“Ít xâm lấn” không đồng nghĩa “zero impact”.** Mục tiêu là **giảm và ghi lại thay đổi**, chứ không khẳng định tuyệt đối nguyên trạng.

## 3. Mô hình đe dọa trước khi đưa ra quyết định cô lập

### 3.1. Ai và điều gì đang bị đe dọa?

~~~mermaid
flowchart LR
    DEV["Endpoint nghi bị xâm nhập"] -->|"C2 / exfiltration"| EXT["Internet / external service"]
    DEV -->|"Lateral movement"| LAN["Internal services"]
    DEV -->|"Privileged session"| CTRL["Identity / management plane"]
    DEV -->|"Shared storage"| DATA["Customer and backup data"]
    EDR["EDR / telemetry"] -. "Quan sát và containment" .-> DEV
    FW["Firewall / NAC / ZTNA"] -. "Giới hạn đường mạng" .-> DEV
    EVID["Evidence repository"] -. "Bảo toàn logs và artifacts" .-> DEV
~~~

Mỗi mũi tên là một **đường cần xác minh**, không phải dấu hiệu đã xảy ra tấn công. Một host có thể có nhiều NIC, VPN, Wi-Fi, IPv6, proxy hoặc connection đã established. Ngắt **một** interface không tự chứng minh đã chặn mọi đường.

### 3.2. Những câu hỏi triage tối thiểu

| Nhóm câu hỏi | Cần xác minh |
|---|---|
| **Identity** | Host ID/EDR agent ID, hostname, VM/Pod UID, serial, user, IP/MAC theo thời gian |
| **Dấu hiệu** | Alert nào, confidence, hành vi process/network, dấu hiệu false positive |
| **Phạm vi** | Chỉ một endpoint hay nhiều thiết bị, tài khoản hoặc workloads? |
| **Hoạt động hiện tại** | Có exfiltration, ransomware encryption, remote shell hoặc lateral movement đang tiếp diễn không? |
| **Tài sản** | Endpoint là laptop, domain controller, database, clinical/OT controller hay bastion? |
| **Bằng chứng dễ mất** | Có session, process, memory keys, log rolling hoặc ephemeral container cần thu ngay không? |
| **Đường quản lý** | EDR containment có giữ kênh quản lý? Cần OOB, console hay cloud API riêng? |
| **Tác động cô lập** | Ngắt một server có cắt dịch vụ, safety systems, replication hoặc logging không? |
| **Phê duyệt** | Ai là incident commander, owner, legal/privacy và change approver? |
| **Rollback** | Điều kiện mở lại, người có quyền và test an toàn nào? |

**Đừng đồng nhất IP với endpoint.** DHCP lease có thể đã thay đổi; NAT có thể dùng chung IP; một Pod IP có thể tái sử dụng sau khi workload bị xóa. Gắn quyết định cô lập với **identity ổn định và timestamp**, không chỉ địa chỉ nhìn thấy trong một flow log.

## 4. Cân bằng rủi ro: khi nào cô lập trước, khi nào thu nhanh trước?

### 4.1. Ma trận quyết định minh họa

| Tình huống | Ưu tiên thường hợp lý | Điều kiện |
|---|---|---|
| Ransomware đang mã hóa dữ liệu hoặc lan nhanh | **Cô lập ngay** bằng phương án đáng tin | Ghi quyết định và bảo toàn telemetry bên ngoài host |
| Exfiltration đang diễn ra và dữ liệu nhạy cảm bị đe dọa | **Chặn egress/đường thoát khẩn cấp** | Ưu tiên dừng thiệt hại; thu logs từ network/EDR đồng thời |
| Host nghi nhiễm nhưng ổn định, có chuyên gia tại chỗ | **Thu nhanh volatile evidence nếu an toàn**, rồi cô lập | Có thời hạn rõ, không để thu thập kéo dài tạo thêm thiệt hại |
| Hệ thống OT/clinical/safety critical | **Theo playbook an toàn vận hành**, phối hợp owner | Ngắt mạng hoặc tắt host có thể nguy hiểm tới con người/quy trình |
| VM đang chạy ứng dụng sản xuất trọng yếu | **Containment có giới hạn theo flow/identity** khi khả thi | Không ngắt toàn cluster nếu chỉ một workload bị ảnh hưởng |
| Endpoint bị mất liên lạc với EDR | **Bảo vệ tại network/switch/cloud boundary**, xác minh identity | Không đợi EDR online vô hạn |
| Thiết bị chứa khóa giải mã chỉ trong RAM | Cân nhắc **live memory capture sớm** nếu rủi ro cho phép | Không để hệ thống tiếp tục gây hại chỉ để lấy keys |
| Lệnh xóa log/anti-forensics đang thực hiện | **Ưu tiên ngăn tiếp tục thao tác** và thu external logs | Quản lý retention và account compromise đồng thời |

Ma trận này **không phải luật cố định**. Incident commander quyết định dựa evidence, policy, pháp lý và safety. Một live memory acquisition có thể không khả thi hoặc gây thêm hại; việc ngắt mạng trước rồi thu từ host vẫn có thể là lựa chọn đúng.

### 4.2. Ba mức containment cơ bản

1. **Selective containment:** chặn đích C2/egress hoặc một flow/rule cụ thể, giữ một số kết nối nghiệp vụ và quản lý. Hữu ích khi cần giữ dịch vụ nhưng dễ bỏ sót destination khác.
2. **Host/network containment:** ngăn phần lớn ingress/egress của đúng endpoint, có thể giữ kênh EDR/OOB được xác thực. Dễ giảm blast radius hơn nhưng có thể cắt remote evidence collection.
3. **Physical/power isolation:** ngắt vật lý/tắt nguồn khi nguy cơ/safety/playbook yêu cầu. Thường làm mất volatile evidence và có rủi ro tác động dữ liệu/ứng dụng; không dùng mặc định.

### 4.3. Quy tắc “người, thời điểm, lý do”

Trước hành động, hoặc ngay sau khi ngăn nguy hiểm tức thời, ghi:

~~~text
Incident ID: INC-LAB-2026-006
Endpoint: asset-0042 / EDR agent unique ID / VM resource ID
Signal: process and outbound flow anomaly under investigation
Decision: isolate endpoint using approved EDR containment
Decision maker: incident commander / delegated responder
Reason: prevent suspected exfiltration
Decision timestamp: UTC, precise clock source
Expected impact: user's connection and business sessions interrupted
Evidence retained: central EDR, DNS, proxy, firewall and identity logs
Validation: ingress/egress denied except documented management channel
Reversal: only after incident-owner approval and verification plan
~~~

Các trường chỉ minh họa; không dùng tên người/thông tin khách hàng thật trong tài liệu học.

## 5. So sánh những phương án cô lập endpoint

### 5.1. Không có một cách cô lập tốt cho mọi tài sản

| Phương án | Thực thi ở đâu? | Ưu điểm | Điểm yếu và lưu ý bảo toàn chứng cứ |
|---|---|---|---|
| **EDR network isolation** | Agent trên endpoint phối hợp EDR console | Nhắm đúng agent/host; có thể duy trì kênh EDR | Phụ thuộc agent, hệ điều hành, chính sách ngoại lệ và khả năng agent bị vô hiệu |
| **NAC quarantine / 802.1X** | Switch/Wi-Fi/controller | Có thể cô lập kể cả khi agent không tin cậy | Đổi VLAN/ACL làm thay địa chỉ/lease, ngắt kênh quản lý và kết nối hiện tại |
| **Switch port disable** | Access switch port | Mạnh nếu xác định đúng port vật lý | Có thể ảnh hưởng nhiều thiết bị qua dock/phone/AP; cắt remote acquisition |
| **Firewall egress/ingress block** | Cloud/on-prem firewall, router, security gateway | Chặn nhanh theo route/zone; vẫn giữ disk/RAM | Flow bypass, IPv6, alternate routes, existing session semantics và NAT |
| **VPN/ZTNA revocation** | Identity/session gateway | Ngắt một đường truy cập từ xa | Không chặn local NIC, Internet egress hoặc credential đã bị lộ ở ứng dụng khác |
| **Cloud security group / NSG** | Cloud virtual network | Nhắm đúng VM/NIC theo platform | Stateful flow semantics, nhiều NIC, public IPv6 và control-plane API riêng |
| **VM virtual NIC disconnect** | Hypervisor/virtualization control plane | Chặn phần lớn traffic từ NIC đã chọn | Có thể ngắt VM quản trị từ xa và service critical; snapshot/memory khác workflow |
| **Host firewall deny** | OS firewall trên endpoint | Có thể chọn đúng flow/port | OS/attacker có thể sửa; thay đổi trạng thái máy và firewall logs |
| **Kubernetes NetworkPolicy** | CNI/pod networking | Cô lập Pod labels/namespaces khi CNI enforce | Không luôn áp lên hostNetwork/node traffic, ephemeral Pods đổi identity |
| **Process terminate** | OS/EDR | Dừng tiến trình gây hại ngay | Mất RAM/process state, có thể kích hoạt cơ chế tự hủy hoặc watchdog |
| **Shutdown/power-off** | OS, BMC/hypervisor hoặc vật lý | Ngừng thực thi trong nhiều tình huống | Mất volatile memory, có thể phá dữ liệu chưa ghi, khó mở ổ mã hóa |

**Network containment không đồng nghĩa host đã an toàn.** Tiến trình độc hại vẫn có thể chạy, mã hóa file cục bộ, xóa logs hoặc dùng kết nối không bị policy bao phủ. Ngược lại, **process termination** chưa chắc loại bỏ persistence hoặc credential đã bị lấy.

### 5.2. Ưu tiên biện pháp ít phá hủy khi rủi ro cho phép

Một nguyên tắc hữu ích là chọn **biện pháp đủ mạnh để dừng rủi ro tức thời, nhưng gây ít thay đổi nhất có thể**. Trong nhiều tình huống ransomware/exfiltration, EDR isolation hoặc network enforcement có thể giữ host chạy để điều tra tiếp. Tuy vậy:

- Nếu agent bị attacker kiểm soát, cần kiểm chứng bằng thiết bị mạng độc lập.
- Nếu endpoint có nhiều NIC, nên kiểm tra cả wired, Wi-Fi, LTE/cellular, VPN, IPv6, virtual bridges và management interface.
- Nếu firewall stateful, hành vi với **established sessions** tùy thiết bị và chính sách; không đoán.
- Nếu network block làm mất khả năng thu RAM qua EDR, cân nhắc **thu trước trong cửa sổ ngắn** hoặc dùng OOB/physical collection.
- Nếu có nguy cơ safety hoặc irreversible damage, ưu tiên phương án khẩn cấp được phê duyệt.

### 5.3. Mục tiêu không phải “tắt mạng xanh toàn bộ”

Một số tổ chức cho phép endpoint đang cô lập vẫn liên lạc với **EDR management hoặc kênh forensic relay đã xác thực**, nhằm tiếp tục gửi telemetry và nhận chỉ thị. Đây là ngoại lệ **hẹp, có chủ đích**, không phải lối ra Internet tự do. Phải ghi:

~~~text
Allowed after containment:
  - Approved EDR control-plane endpoint, if product requires
  - Forensic relay approved by incident lead, if needed

Denied after containment:
  - Internet egress not needed for evidence collection
  - Lateral access to internal applications and peers
  - Inbound sessions from ordinary users/clients
  - Alternate Wi-Fi/VPN/IPv6 routes outside intended exception
~~~

**Đừng sao chép danh sách domain/IP ngoại lệ của một EDR vendor sang sản phẩm khác.** Các ngoại lệ còn phụ thuộc agent, DNS/proxy, TLS pinning và cloud region; dùng hướng dẫn deployment hiện hành của môi trường được quản lý và test tại điểm thực thi.

## 6. Các nguồn chứng cứ: endpoint không phải nơi duy nhất

Một endpoint đã bị xâm nhập là nguồn chứng cứ **quan trọng nhưng có thể đã bị thao túng**. Bảo toàn các nguồn **bên ngoài host** thường ít gây tác động hơn và có thể thực hiện song song với containment.

~~~mermaid
flowchart TB
    EP["Endpoint nghi bị xâm nhập"]
    EP --> EDR["EDR alerts / process tree / isolation events"]
    EP --> DNS["Recursive DNS / authoritative logs"]
    EP --> FW["Firewall / IPS / VPN / NAT flows"]
    EP --> PROXY["Web proxy / WAF / load balancer"]
    EP --> IDP["IdP / SSO / MFA / privileged access"]
    EP --> SIEM["SIEM / log store / centralized audit"]
    EP --> CLOUD["Cloud API / VPC flow / VM metadata"]
    SIEM --> CASE["Restricted evidence repository"]
    EDR --> CASE
    DNS --> CASE
    FW --> CASE
    IDP --> CASE
~~~

### 6.1. Thứ tự nguồn và giá trị điều tra

| Nguồn | Câu hỏi trả lời được | Hạn chế cần ghi |
|---|---|---|
| EDR agent/console | Process chain, alert, file hash, host actions, isolation outcome | Agent có thể bị tắt, telemetry bị trì hoãn hoặc thiếu dữ liệu |
| DNS resolver | Host tra cứu domain nào, lúc nào | Cache/NAT/shared resolver, encrypted DNS và sampling |
| Proxy/CDN | HTTP host/path/status, user identity khi được xác thực | HTTPS inspection scope, privacy, caching |
| Firewall/IDS/IPS | Kết nối, rule/action, bytes/packets, alerts | IP sau NAT, detect vs block, sampled logs |
| DHCP/NAC/switch | IP–MAC–switch port/VLAN mapping theo thời gian | MAC spoofing, dock/AP aggregation, stale lease |
| VPN/ZTNA | User/device/session, assigned address, authentication events | Tunnel up không chứng minh mọi application request |
| IdP/IAM | Sign-in, MFA, token/role/grant changes | Dữ liệu tài khoản có thể không chỉ rõ process trên host |
| Cloud control plane | VM/NIC/security group/snapshot/role changes | Eventual consistency, logs khác region/account |
| Endpoint local logs | Login, process, kernel/network events, service activity | Có thể bị attacker sửa hoặc rotate |
| Network packet capture | Protocol behavior tại một điểm, timing, headers nhìn thấy | Có thể chứa secrets/personal data, traffic encrypted/partial |

**Nguyên tắc đối chiếu:** dùng nhiều nguồn độc lập để kiểm chứng. Không kết luận một IP “là máy A” từ firewall flow vào 14:00 nếu không có lease/VPN/NAT mapping **đúng thời gian 14:00**.

### 6.2. Bảo vệ retention ngay từ đầu

Nhiều logs có vòng đời ngắn: ring buffers, EDR telemetry retention, packet capture rotating files, cloud flow logs theo sampling, VPN session history, NAT translations. Khi nghi sự cố:

1. Xác định nguồn nào sắp **hết retention** hoặc bị rotate.
2. Gửi yêu cầu **legal hold/preservation** theo chính sách tổ chức nếu phù hợp.
3. Export từ hệ thống gốc bằng quyền được duyệt vào **restricted evidence storage**.
4. Giữ metadata: time range, filter, query, export mechanism, dataset ID, tool version.
5. Hash artifacts và ghi người nhận/đường bảo quản, không chỉnh sửa bản gốc.

### 6.3. Tránh “một screenshot là đủ”

Screenshot dashboard hữu ích cho quyết định ban đầu nhưng có thể thiếu **source timestamps, timezone, fields, log IDs, time range và truy vấn**. Cần giữ raw/structured exports khi cho phép, kèm screenshot làm minh họa; nếu platform chỉ có UI, ghi chính xác các giới hạn của chứng cứ.

## 7. Bằng chứng dễ mất và thứ tự ưu tiên thu thập

### 7.1. Volatile evidence là gì?

**Volatile evidence** là thông tin có thể thay đổi hoặc biến mất nhanh khi tiến trình kết thúc, kết nối ngắt, host reboot, memory bị overwrite hoặc container bị tái tạo:

- Memory/RAM của hệ thống hoặc một process theo điều kiện cho phép.
- Danh sách tiến trình, parent–child relationships, command lines và loaded modules.
- Active network sockets, connection states, ARP/NDP/neighbor caches, route table.
- DNS resolver cache, VPN session state, ephemeral credentials/tokens trong bộ nhớ.
- Logged-on users, active sessions, in-memory mounts hoặc encryption state.
- Container/Pod runtime state, ephemeral filesystem và namespace connections.
- Temporary logs/ring buffers và network device session/NAT mappings.

Các nguồn bền vững hơn như disk image hoặc cloud audit logs thường vẫn có thể bị sửa/xóa nếu attacker có quyền. **“Lưu trên đĩa” không đồng nghĩa “vĩnh viễn”.**

### 7.2. Một thứ tự ưu tiên có điều kiện

~~~text
1. Ngăn thiệt hại khẩn cấp nếu đang xảy ra.
2. Ghi incident facts, đồng hồ/time source và người ra quyết định.
3. Giữ independent telemetry: EDR, SIEM, DNS, firewall, IAM.
4. Nếu an toàn và có chuyên gia/công cụ:
      thu quick volatile state (processes, sessions, network);
      cân nhắc full memory acquisition theo giá trị/rủi ro.
5. Cô lập hoặc kiểm tra lại tình trạng cô lập đã áp.
6. Thu disk/volume snapshots hoặc images theo phương pháp hỗ trợ.
7. Bảo vệ evidence, hash, chain of custody, timeline.
8. Eradication/reimage/recovery theo quyết định IR sau bảo toàn.
~~~

**Thứ tự không tuyệt đối:** memory capture có thể mất thời gian và gây tác động đáng kể; ransomware đang mã hóa không nên được để tiếp tục chỉ vì “RAM phải lấy trước”. Hướng dẫn về order of volatility là **một yếu tố hỗ trợ quyết định**, không phải yêu cầu bỏ qua containment.

### 7.3. Chứng cứ không chắc thu được sau khi ngắt mạng

| Thành phần | Hệ quả khi cô lập |
|---|---|
| Remote shell/EDR evidence channel | Có thể ngắt lập tức; một số EDR giữ management exception |
| Active TCP/QUIC sessions | Có thể đứt hoặc timeout, socket state thay đổi |
| DNS cache/ARP/NDP cache | Có thể giữ ngắn hạn rồi hết hạn/đổi |
| In-memory process/network telemetry | Vẫn có thể thu tại host nếu host còn chạy và có quyền |
| Cloud control-plane logs | Thường tiếp tục truy cập qua API provider nếu được cấp quyền |
| Network taps/SPAN captures | Vẫn thu ở vị trí mạng, nhưng traffic từ host có thể dừng |
| Encryption keys trong RAM | Có thể còn khi host chạy; mất khi power-off/reboot |
| Disk artifacts | Có thể còn nhưng bị thay khi host đang hoạt động; nên bảo vệ và thu đúng phương pháp |

### 7.4. Vấn đề live response và tính toàn vẹn

Để thu memory hoặc process data cần thực thi lệnh/công cụ trên host (trực tiếp hay qua EDR). Điều đó **tạo traces mới và có thể thay memory**, và công cụ đang chạy trong OS có thể bị rootkit/attacker ảnh hưởng. Hãy ghi **công cụ, phiên bản, command, thời điểm, kết quả, lỗi và thay đổi dự kiến**; ưu tiên công cụ được tổ chức phê duyệt và giải thích giới hạn trong báo cáo.

Không xóa shell history, clear event logs, tắt EDR hoặc “dọn” artifact trước khi bảo toàn. Nếu có dấu hiệu anti-forensics, ghi lại việc phát hiện và ưu tiên nguồn log độc lập.

## 8. Pre-isolation checklist: xác minh đúng máy, đúng quyền, đúng đường

Cô lập nhầm một host có thể làm gián đoạn hệ thống hợp lệ và phá timeline; cô lập **không trúng host** thì kẻ tấn công vẫn có đường hoạt động. Trước khi bấm nút “Isolate” trong EDR hoặc cấu hình một network policy, cần **định danh endpoint** bằng nhiều thuộc tính.

### 8.1. Tạo một hồ sơ định danh tối thiểu

~~~yaml
# Hồ sơ ví dụ; không chứa dữ liệu thật hoặc thông tin nhận dạng cá nhân.
incident_id: INC-LAB-2026-006
asset:
  asset_inventory_id: asset-lab-0042
  edr_agent_id: agent-id-from-inventory
  hostname: workstation-042.lab.example.test
  cloud_or_vm_id: null
  serial_number_reference: restricted-inventory-record
  owner_team: business-unit-lab
  os_family: windows
observed_network:
  ipv4_at_detection: 192.0.2.42
  ipv6_at_detection: none-observed
  mac_reference: restricted-nac-record
  vpn_session_reference: pending
  switch_or_ap_reference: pending
observations:
  alert_time_utc: pending
  last_seen_time_utc: pending
  identity_confidence: pending-validation
decision:
  incident_commander: pending
  containment_method: pending
  management_exception: pending
  business_impact: pending
~~~

Trong thực tế, IP có thể thuộc NAT/shared network; một EDR agent ID có thể được cài lại hoặc clone sai image. Đối chiếu **EDR record, CMDB, DHCP/NAC, cloud instance ID, user session, MAC/switch port và thời gian** trước khi hành động.

### 8.2. Nguyên tắc four-eyes cho containment nhạy cảm

Với máy chủ sản xuất, hypervisor, domain controller, firewall hoặc thiết bị OT, nhiều tổ chức yêu cầu **đồng phê duyệt** từ incident commander và service/system owner. Trong tình huống khẩn cấp nghiêm trọng, quy trình có thể cho phép hành động trước, ghi nhận/phê duyệt hậu kiểm theo policy. Không tự tạo một quy tắc “phải đợi hai người” nếu điều đó làm tăng thiệt hại đang diễn ra.

### 8.3. Chọn chính xác vùng cô lập

| Cấp độ | Selector phù hợp | Nguy cơ nếu selector quá rộng |
|---|---|---|
| Một endpoint | EDR unique ID, cloud instance/NIC ID, xác nhận port | Chặn nhầm máy IP mới, gián đoạn asset khác |
| Một workload | Pod UID/namespace/ServiceAccount hoặc workload labels đã kiểm chứng | Label chọn quá nhiều replica/các tenant |
| Một VLAN/subnet | Source zone/port policy, device owner | Cắt hàng trăm máy chưa bị ảnh hưởng |
| Một identity/session | User principal, device ID, token/session ID | Logout nhầm toàn đội hoặc không chặn token khác |
| Một C2 destination | FQDN/IP/protocol theo evidence, DNS context | IP chia sẻ với dịch vụ hợp lệ, attacker đổi destination |

**Không dùng `0.0.0.0/0` hoặc toàn bộ private CIDR làm source target của một quy tắc chặn vội** nếu phạm vi mong muốn chỉ một endpoint; cú pháp/semantics của firewall cần được peer review.

## 9. Thu thập thông tin host: nguyên tắc chung trước khi dùng lệnh

### 9.1. Thực hiện qua đâu?

Một cuộc điều tra có thể dùng **EDR live response đã được phê duyệt**, quản trị trực tiếp qua console, OS shell hoặc một công cụ thu thập forensic độc lập. Chọn đường:

1. Cho phép định danh người thao tác và tài sản đích.
2. Có quyền hợp lệ, không dùng credential mượn hoặc bypass policy.
3. Tối thiểu hóa thay đổi ở host, không tải công cụ từ Internet tùy tiện.
4. Không làm mất nguồn logs/sessions quan trọng.
5. Có địa điểm lưu artifact **ngoài host nghi bị chiếm**.
6. Có cơ chế xác minh hash, timestamps và chain of custody.

**Lệnh chỉ truy vấn trạng thái vẫn tạo traces.** Một remote command có thể sinh audit event, thay page cache hoặc ghi history. Vì vậy các ví dụ sau mang tính **low-impact observation** trong môi trường được phép, **không được gọi là acquisition đạt chuẩn forensic chỉ nhờ đọc stdout**.

### 9.2. Checklist trước khi thu

~~~text
Operator identity / approval                 [ ]
Exact endpoint ID and time                   [ ]
EDR and external logs preservation started  [ ]
Time sync / UTC offset recorded              [ ]
Method and tool version documented           [ ]
Evidence destination encrypted/restricted   [ ]
Impact on active sessions considered         [ ]
Untrusted host response limitations noted    [ ]
Memory/disk acquisition specialist consulted [ ]
Containment path and emergency rollback ready[ ]
~~~

**Không ép một host đang nguy hiểm phải tiếp tục online** chỉ để hoàn thành từng checkbox. Quy trình sự cố phải linh hoạt với mức tác động.

## 10. Windows endpoint: quan sát có giới hạn và thu chứng cứ

Các lệnh dưới đây chỉ dành cho Windows host lab hoặc hệ thống đã được tổ chức cho phép. Một số lệnh yêu cầu privileges và có thể tạo audit events. **Không chạy trên máy của người khác hoặc tự thu dữ liệu cá nhân.**

### 10.1. Quan sát system time, identity và interface

~~~powershell
# LOW-IMPACT OBSERVATION: không cấu hình isolation.
# Có thể tạo process/audit artifacts và đọc dữ liệu nhạy cảm.
Get-Date -Format o
Get-ComputerInfo | Select-Object CsName, WindowsProductName, OsBuildNumber
Get-NetIPConfiguration
Get-NetAdapter | Select-Object Name, Status, InterfaceDescription, MacAddress
Get-NetRoute | Select-Object DestinationPrefix, NextHop, InterfaceAlias, RouteMetric
~~~

Ghi lại **timezone, UTC offset, clock source/time skew** nếu có. `Get-NetIPConfiguration` và `Get-NetRoute` cho thấy cấu hình hiện thời, không tự mô tả routes trước khi endpoint được cô lập.

### 10.2. Quan sát process, user session và network connections

~~~powershell
# Chỉ quan sát trong lab; output có thể có usernames/process details.
Get-Process |
  Select-Object Id, ProcessName, Path, StartTime

Get-NetTCPConnection |
  Select-Object LocalAddress, LocalPort, RemoteAddress, RemotePort, State, OwningProcess

Get-NetUDPEndpoint |
  Select-Object LocalAddress, LocalPort, OwningProcess

Get-CimInstance Win32_ComputerSystem |
  Select-Object Name, UserName, Domain
~~~

Một số thuộc tính có thể **thiếu, bị access denied hoặc thay đổi trong lúc lệnh chạy**; không điền giá trị suy đoán. `Get-Process.Path/StartTime` có thể không trả về với process được bảo vệ/không đủ quyền. `OwningProcess` là PID tại thời điểm đo, PID có thể tái sử dụng; kết hợp process creation telemetry và time.

### 10.3. Windows event logs, EDR và registry

- **Security log:** đăng nhập, quyền đặc biệt, process creation khi auditing được cấu hình.
- **System/Application:** reboot, service changes, crash, ứng dụng.
- **PowerShell logs:** script/module/block logging theo cấu hình.
- **Sysmon/EDR telemetry:** process, network, image load, DNS, registry/file events theo sản phẩm/policy.
- **Registry, scheduled tasks, services, startup mechanisms:** persistence/tác động.

**Không coi việc event không có trong log là bằng chứng hoạt động không xảy ra.** Audit policies có thể không bật, event bị rotate, agent bị tắt hoặc log bị sửa.

### 10.4. Export là acquisition, không còn là quan sát không ghi

Ví dụ `wevtutil epl` xuất Event Log ra file **làm phát sinh một file mới** và có thể cần storage/privilege trên host. Chỉ thực hiện theo runbook đã duyệt, lưu file vào evidence repository và ghi tool/version/command/time/hash. Không tạo artifact lớn trên phân vùng nghi bị mã độc kiểm soát nếu có lựa chọn an toàn hơn.

Với memory acquisition, dùng **công cụ đã được kiểm định và bảo quản bởi đội forensic**; ghi quyền, tác động, dung lượng và destination. Không tuyên bố một memory dump “nguyên vẹn tuyệt đối”; quá trình thu bộ nhớ diễn ra khi OS liên tục thay đổi.

### 10.5. Windows encryption và shutdown

Nếu ổ đĩa được bảo vệ bằng **BitLocker** và host đang mở khóa, việc tắt máy có thể khiến quá trình thu offline cần recovery keys thuộc quản lý riêng. Không tự trích xuất key hoặc thay BitLocker policy khi chưa được phép. Khi containment có thể thực hiện mà **host vẫn bật**, cân nhắc giữ nguyên power state để chuyên gia forensic đánh giá dữ liệu đang accessible.

**Không tắt Windows bằng cách giữ nút nguồn theo thói quen**; hành động đó có thể mất RAM, gây filesystem inconsistency và phá các phiên đang hoạt động. Chỉ làm khi risk/safety và người chỉ huy sự cố quyết định.

## 11. Linux endpoint: process, socket, route và system logs

### 11.1. Lệnh quan sát có giới hạn

~~~bash
# LOW-IMPACT OBSERVATION trên Linux lab được cấp quyền.
# Các lệnh tạo process/audit events, không phải forensic acquisition bất biến.
date -u '+%Y-%m-%dT%H:%M:%SZ'
hostnamectl
ip -br address
ip route show
ip -6 route show
ip neigh show
ss -tuna
ps -eo pid,ppid,user,lstart,stat,comm,args
~~~

`ss -tuna` liệt kê TCP/UDP sockets với thông tin theo quyền; `-p` để xem process có thể cần quyền cao và chứa dữ liệu nhạy cảm. `ps` cho thấy snapshot tức thời, không ghi toàn bộ lịch sử process đã thoát. `ip neigh` chỉ cho thấy neighbor cache hiện tại, không thể xác định đầy đủ tất cả máy đã kết nối.

### 11.2. Logs và dữ liệu runtime

~~~bash
# Chỉ đọc journal trong lab, nếu journal tồn tại và có quyền.
journalctl --since "2026-11-28 00:00:00" --until "2026-11-28 01:00:00" --no-pager

# Đọc trạng thái network devices và counters.
ip -s link show

# Liệt kê mounts; filesystem có thể đã bị malware tác động.
findmnt
~~~

Time range trên `journalctl` chịu ảnh hưởng timezone/parsing của host; ghi timezone và dùng `--utc` khi phù hợp để tránh lệch timeline. Các file `/var/log`, journald, auditd, application logs hoặc container logs có retention khác nhau và có thể chưa được bật.

### 11.3. Filesystem, encryption, snapshots

Trước khi lấy disk image:

- Xác định filesystem, volumes, LVM/ZFS/Btrfs/cloud block devices, encryption state.
- Quyết định **live snapshot, crash-consistent snapshot, application-consistent snapshot hoặc offline image** theo yêu cầu.
- Không `fsck`, `chkdsk`, xóa `tmp`, reboot hoặc thực hiện cleanup khi chưa bảo toàn và phê duyệt.
- Nếu dùng write blocker/offline imaging, xác minh target/source và công cụ trước khi thao tác; không mount forensic original read-write.
- Ghi **storage identifiers, snapshot IDs, consistency assumptions, timestamps, hash và chain of custody**.

### 11.4. Linux host có container

Process trong container có thể hiện ở host với PID mapping, network namespaces và overlay storage. Một Pod/container bị xóa có thể mất writable layer hoặc runtime metadata. Cần **thu metadata của orchestrator, node/Pod identity, container image digest, runtime events, logs và volumes** trước khi lifecycle garbage collection xóa chúng, theo quyền được duyệt.

Không tự `docker stop`, `kubectl delete pod` hoặc drain node trong giai đoạn bảo toàn nếu chưa quyết định containment và tác động tới bằng chứng.

## 12. macOS, mobile và thiết bị hạn chế quyền thu thập

### 12.1. macOS endpoint

Đối với macOS, việc thu thập process/network state có thể chịu **System Integrity Protection, TCC/privacy controls, FileVault và EDR capabilities**. Không tắt cơ chế bảo vệ hệ điều hành chỉ để chạy một công cụ forensic không tương thích. Hãy dùng **đội quản lý endpoint/forensic được ủy quyền**, xác nhận quyền truy cập, điều kiện encryption và lựa chọn isolation của EDR hoặc MDM.

### 12.2. Mobile/BYOD

Thiết bị mobile hoặc BYOD có thể chỉ cho phép **managed-app containment, revoke enterprise tokens, remove VPN/MDM enterprise access** theo hợp đồng/đồng ý. Không tự thu toàn bộ dữ liệu cá nhân, hình ảnh hoặc tin nhắn chỉ vì thiết bị từng đăng nhập vào mạng doanh nghiệp. Ghi rõ **legal basis, scope và data minimization**.

### 12.3. Thiết bị OT/IoT không hỗ trợ EDR

Với PLC, sensor, medical device hoặc network appliance, thao tác shutdown, VLAN change hay scan có thể gây tác động tới an toàn và quy trình vật lý. Phối hợp **asset owner, OT safety lead, vendor playbook và SOC**; ưu tiên quan sát từ **switch/firewall SPAN/tap, out-of-band logs, NAC hoặc zone ACL** khi phù hợp, tránh chạy chương trình thu thập tùy ý trên thiết bị.

**Mức cô lập được phép** ở mạng IT không tự tương đương mức được phép trong môi trường an toàn công nghiệp/thiết bị y tế.

## 13. Network evidence: packet capture, flow logs và mapping danh tính

### 13.1. Packet capture có thể giữ được gì?

Một **packet capture (PCAP/PCAPNG)** tại tap/SPAN, sensor hoặc host có thể cung cấp:

- Timestamps và hướng dữ liệu qua điểm capture.
- IP/port/protocol, TCP flags, handshake, reset, retransmission và một số metadata.
- DNS hoặc HTTP payload **khi không được mã hóa và phù hợp quyền thu**.
- Dấu hiệu TLS handshake như SNI khi còn hiển thị, version/cipher context, kích cỡ và timing.
- Mẫu lưu lượng liên quan C2/exfiltration hoặc lateral movement, trong giới hạn quan sát.

**Không mặc định PCAP chứa nội dung HTTPS đã giải mã.** Với TLS/QUIC, phần lớn payload được mã hóa; một PCAP không có keys và quyền hợp pháp thường chỉ cho metadata. Ngay cả capture nhìn thấy TCP handshake cũng không chứng minh người dùng đã hoàn thành tác vụ.

### 13.2. Capture ở đâu sau khi endpoint bị cô lập?

~~~mermaid
flowchart LR
    H["Suspected endpoint"] --> SW["Access switch / virtual switch"]
    SW --> FW["Firewall / IPS"]
    FW --> WAN["External network"]
    TAP["SPAN / TAP sensor"] -. "Quan sát trước/sau isolate" .-> SW
    FL["Flow and policy logs"] -. "Record allowed/denied flows" .-> FW
    EDR["Endpoint telemetry"] -. "Process/socket context" .-> H
    TAP --> CASE["Evidence repository"]
    FL --> CASE
    EDR --> CASE
~~~

Nếu firewall đã chặn egress, PCAP đặt **ngoài firewall** có thể không thấy request mà endpoint vẫn cố gửi. Cần phân biệt **điểm quan sát trước PEP** và **sau PEP**, đồng thời xem firewall drop logs.

### 13.3. Nguyên tắc bảo vệ quyền riêng tư và hiệu năng

- Chỉ capture **đúng endpoint, đúng interface, đúng thời gian và lý do đã duyệt**.
- Hạn chế payload khi metadata đủ; dùng capture filter theo công cụ được kiểm định.
- Không thu thập traffic của cả VLAN chứa nhiều người nếu không có phê duyệt/đánh giá privacy.
- Ghi packet loss/dropped captures, snap length, interface và sensor clock.
- Lưu PCAP trên encrypted restricted storage, có retention và chain of custody.
- Không tải PCAP lên dịch vụ công khai hoặc sandbox không được tổ chức phê duyệt.

### 13.4. Lệnh xem PCAP đã có sẵn

~~~bash
# Chỉ đọc file PCAP mẫu đã được phép lưu trên máy phân tích.
# Không sniff mạng, không thay network settings.
tcpdump -nn -r incident-lab-capture.pcap -c 20

# Nếu có tshark, xem thống kê protocol trong file được phép.
tshark -r incident-lab-capture.pcap -q -z io,phs
~~~

Lệnh `tcpdump -r` đọc nội dung từ file, nhưng vẫn có thể tạo logs/shell artifacts. PCAP có thể chứa dữ liệu nhạy cảm và mã độc trong payload; mở bằng workstation phân tích được cách ly/phần mềm cập nhật, không chạy code tải từ payload.

### 13.5. Flow logs và NAT translation

Một bản ghi `192.0.2.42:51512 → 203.0.113.50:443` tại host có thể thành `198.51.100.7:60231 → 203.0.113.50:443` sau NAT. Nếu không giữ **source/destination mapping, protocol, start/end time, firewall device, action và log sampling**, có thể gắn nhầm kết nối cho một người hoặc asset khác.

**Gắn IP với đúng thời điểm và identity**, đặc biệt trong DHCP, cloud autoscaling, VPN, proxy và Kubernetes Pod networking. Không suy `same public IP = same endpoint`.

## 14. EDR network isolation: thực hiện và xác minh theo sản phẩm

### 14.1. Cơ chế chung

Một EDR có thể triển khai **network containment** bằng host-level filter hoặc driver, chặn những kết nối không được phép trong khi giữ một số đường tới EDR control plane. Một số sản phẩm có chế độ **allowlisted connections** hoặc hỗ trợ live response trong isolation mode; một số khác không.

~~~text
Precondition:
  Correct host and EDR agent identity verified
  Incident commander authorized action
  Risk of ongoing harm documented
  Collection plan and external logs preservation initiated

Action:
  Issue isolate command via approved EDR console/API

Verification:
  EDR reports command accepted AND observed host containment
  Unauthorized ingress/egress no longer succeeds
  Approved EDR management/forensics path behaves as documented
  No alternate VPN/Wi-Fi/IPv6 path bypasses containment
  Time and operator recorded
~~~

**“Command sent” không chứng minh “traffic blocked”.** Agent có thể offline, lệnh queued, host reboot, driver mismatch hoặc OS bị attacker thao túng. Cần đối chiếu kết quả thực từ EDR, firewall/NAC flows và phép thử có giới hạn.

### 14.2. Khi EDR bị mất liên lạc

Nếu host offline đối với EDR, không mặc định lệnh isolation đã được áp. Có thể cần:

- Chặn ở **switch/NAC/cloud security group/firewall**, dựa identity đã xác minh.
- Yêu cầu field responder/OOB access nếu có.
- Giữ endpoint chưa bị power-off để đánh giá memory/drive state khi an toàn.
- Ghi trạng thái **pending/unknown**, không đánh dấu containment hoàn tất chỉ vì UI đã nhận ticket.

### 14.3. Endpoint có nhiều agent hoặc dual boot

Một máy có nhiều OS, NIC, virtual network bridges hoặc cellular connections có thể có đường mạng EDR không kiểm soát theo cùng cách. Nếu thiết bị đã reboot sang OS khác, EDR agent của OS cũ không chắc còn hoạt động. Cần rà **firmware/OOB, boot environment, secondary network và containment qua network** trong mô hình rủi ro.

### 14.4. Bằng chứng từ console

Lưu ở repository:

| Thuộc tính | Ví dụ |
|---|---|
| Agent ID | `lab-agent-0042` |
| Device/OS | `workstation-042`, Windows |
| Isolation action ID | `action-000218` |
| Requested timestamp | UTC tại control plane |
| Agent acknowledgement | Received/applied/failed/unknown |
| Effective network evidence | Firewall drops và test endpoints |
| Management exceptions | Theo policy vendor và config thực |
| Initiating operator | User/role từ audit |
| Rollback approver | Incident commander + system owner |

Không sử dụng chỉ một screenshot `isolated=true` làm bằng chứng toàn diện; ghi **identity, thời điểm, phiên bản agent và independent validation**.

## 15. NAC, switch, Wi-Fi và firewall: cô lập không phụ thuộc endpoint agent

### 15.1. NAC quarantine VLAN

Một NAC có thể sử dụng **802.1X/RADIUS authorization, dynamic ACL hoặc quarantine VLAN** để thay đổi kết nối của một endpoint. Ưu điểm là enforcement ở network, kể cả khi OS không tin cậy. Nhưng:

- Reauthentication có thể thay VLAN/IP/gateway, làm chứng cứ connection state thay đổi.
- Wi-Fi roaming hoặc docking có thể chuyển attachment point.
- Một switch port có thể nối **nhiều endpoints qua phone/AP/hub**, không chỉ một laptop.
- MAC address có thể bị spoof hoặc được randomize.
- Cần xem IPv6 và các VLAN/SSIDs khác ngoài cổng chính.

Không chỉ nhập MAC rồi giả định đúng thiết bị; đối chiếu **EDR asset ID, switch authentication session, port, user, DHCP lease và timestamps**.

### 15.2. Firewall ACL/segmentation

Một quy tắc chặn theo host/named address group có thể giảm rủi ro mà không thay host state, nhưng phải xét:

1. Source/destination identity có đúng không? NAT/policy routing ảnh hưởng log ra sao?
2. Cần chặn cả **inbound, outbound, lateral** hay chỉ egress?
3. IPv4 và IPv6 có cùng policy intent không?
4. Có proxy, VPN, SD-WAN, bypass link hoặc secondary VPC path không?
5. Stateful sessions cũ có bị chấm dứt theo vendor semantics không?
6. DNS/FQDN rule có bị cache/TTL hoặc CDN shared IP ảnh hưởng không?
7. Log deny có đủ để xác minh action, không lộ dữ liệu quá mức?

**Một firewall block C2 IP không phải full endpoint containment.** Attacker có thể dùng đích khác, protocol khác hoặc mạng chưa qua firewall; chỉ coi là **selective containment** khi chưa chứng minh toàn bộ phạm vi.

### 15.3. Chặn switch port hay disable interface?

Đây là thay đổi có ảnh hưởng mạnh tới connectivity và forensic acquisition; chỉ dùng khi xác định đúng switch/port và impact. Cần có tài liệu:

~~~text
Device ID, switch ID, physical port, access VLAN
PoE / connected phone / access point / downstream clients
Cable or docking topology
Authorized operator, change time, rollback steps
Independent evidence of dropped traffic
~~~

Nếu port cấp PoE cho điện thoại hoặc thiết bị điều khiển, shutdown có thể gây sự cố ngoài dự kiến. Cần phối hợp network/OT owner và tránh rút nhầm cáp.

### 15.4. Wi-Fi và mobile data

Block tại SSID hoặc Wi-Fi controller chỉ kiểm soát WLAN đó. Một laptop vẫn có thể chuyển sang **LTE/cellular hotspot, Ethernet, VPN qua đường khác**, nếu policy không chặn. Trên managed endpoint, kết hợp EDR/MDM identity isolation với NAC và xác minh đường phụ.

### 15.5. Những việc tuyệt đối cần tránh trong giai đoạn preservation

- Xóa logs hoặc reset counters sau khi thêm deny rule.
- Gỡ agent giám sát hoặc tắt IDS/IPS để “giảm noise” nếu chưa được duyệt.
- Dùng ACL cực rộng chặn toàn bộ production vì chỉ một IP chưa được xác minh.
- Tự xóa/định dạng endpoint hoặc drive làm “cleanup”.
- Đánh dấu quarantine PASS từ một request timeout khi target vốn đã down.

## 16. Cloud VM và container: bản sao, NIC và tài nguyên chóng mất

### 16.1. Cloud VM

Với VM cloud, containment có thể dùng security groups/NSGs, cloud firewall, private subnet, NIC-level route hoặc disassociate public endpoint theo policy. Các **cloud-native APIs** có thể sửa endpoint state độc lập với OS, nhưng vẫn cần:

- Xác định đúng **instance ID, account/subscription, region, NICs, attached volumes và user-data**.
- Giữ **cloud audit events, VPC/VNet flow logs, security group diff, IAM changes**.
- Hiểu trạng thái **stateful security group/NSG** và existing connections theo provider.
- Chọn snapshot volume hoặc memory capture theo **consistency và cloud support**; snapshot disk **không tự giữ RAM**.
- Không terminate/replace VM trước khi có quyết định điều tra và bảo toàn evidence.

### 16.2. Snapshot và shared-disk consistency

Một volume snapshot có thể là **crash-consistent** chứ không **application-consistent**. Với database hay nhiều disks, snapshot rời rạc có thể không tái tạo đúng trạng thái logic ở một thời điểm. Ghi rõ **snapshot API, identifiers, start/end times, consistency assumptions, volume mapping**, encryption/KMS context và quyền truy cập.

Không suy rằng snapshot thành công tương đương **forensic image complete**; cần kiểm tra phạm vi dữ liệu và khả năng phục hồi/đọc được bởi đội chuyên trách.

### 16.3. Kubernetes workload có tuổi thọ ngắn

Pod có thể bị autoscaler, controller, scheduler hoặc CI/CD **thay thế tự động** khi không khỏe. Nếu nghi một Pod bị xâm nhập:

1. Ghi **cluster, namespace, Pod UID, node, image digest, ServiceAccount, container IDs, deployment revision, labels và creation time**.
2. Bảo toàn **Kubernetes audit events, CNI flow logs, ingress/service mesh telemetry, container logs và runtime alerts**.
3. Đánh giá **ephemeral writable layer, mounted volumes và container process state** trước khi delete/restart.
4. Dùng containment ở đúng **CNI policy, namespace, workload identity hoặc cloud network boundary** theo support.
5. Kiểm tra rằng NetworkPolicy được CNI enforce, không chỉ resource YAML tồn tại.
6. Không xóa Pod ngay theo thói quen; nếu cần giảm lây lan khẩn cấp, ghi nhận mất chứng cứ và ưu tiên thu từ outside sources.

### 16.4. Policy ví dụ chỉ để threat modeling

~~~yaml
# MẪU HỌC TẬP, KHÔNG ÁP DỤNG MÙ QUÁNG:
# NetworkPolicy có thể cô lập ingress/egress của các Pods
# được chọn trong namespace lab, tùy CNI thực thi.
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: incident-isolate-suspect
  namespace: incident-lab
spec:
  podSelector:
    matchLabels:
      ir.example.test/quarantine: "true"
  policyTypes:
    - Ingress
    - Egress
~~~

**Quan trọng:** NetworkPolicy chuẩn có **allow rules mang tính cộng dồn**. Một default-deny chọn Pod không phủ quyết được allow từ một policy khác. Ngoài ra, `ir.example.test/quarantine: "true"` chỉ là **label chọn đối tượng**, không phải bằng chứng chống giả danh; ai có quyền thêm/sửa label có thể thay phạm vi. HostNetwork, node traffic và một số CNI có ngoại lệ; phải review **toàn bộ applicable policies và observed flows**, không coi YAML này là lệnh “cô lập tuyệt đối”.

### 16.5. Tách container image khỏi memory/disk evidence

Container image digest cho biết base image được deploy, **không chứa** các thay đổi runtime trong writable layer, process memory hoặc logs đã rotate. Thu đúng các nguồn đó theo nhu cầu và thẩm quyền. Một Pod được re-created từ cùng image có thể hoạt động bình thường trong khi evidence của phiên bị tấn công đã mất.

## 17. Chain of custody: chứng cứ đi qua những ai?

**Chain of custody** (chuỗi quản lý chứng cứ) là hồ sơ liên tục về việc **ai đã sở hữu/truy cập/di chuyển/biến đổi bản sao chứng cứ**, khi nào, vì lý do gì, tại đâu và bằng công cụ/phương pháp nào. Đây là nền tảng để điều tra nội bộ, pháp chế hoặc cơ quan có thẩm quyền có thể đánh giá độ tin cậy.

### 17.1. Bốn thành phần tối thiểu

1. **Định danh:** incident ID, evidence ID, source asset ID, time range và loại artifact.
2. **Thu thập:** ai, tại đâu, khi nào, công cụ/phiên bản, phương pháp, quyền, những giới hạn/chỉ báo lỗi.
3. **Bảo quản:** hash/checksum, storage location, encryption, access control, retention/immutability.
4. **Bàn giao:** người gửi–người nhận, UTC timestamp, mục đích, thao tác được phép và chữ ký/xác nhận phù hợp.

### 17.2. Mẫu evidence inventory

~~~yaml
# MẪU THAM KHẢO; không phải chứng cứ thực tế.
incident_id: INC-LAB-2026-006
evidence_id: EVID-LAB-0042-001
source_asset_id: asset-lab-0042
artifact_type: centrally-exported-edr-event-bundle
source_system: approved-edr-console
time_range_utc:
  start: "2026-11-28T02:00:00Z"
  end: "2026-11-28T03:00:00Z"
acquisition:
  operator_id: responder-lab-01
  collection_time_utc: "2026-11-28T03:10:00Z"
  tool_name: approved-edr-exporter
  tool_version: version-to-be-recorded
  method: native-export
  filters_or_query: stored-in-restricted-case-notes
  errors_or_limitations: none-reported-pending-review
artifact:
  file_name: edr-events-evid-001.zip
  byte_size: pending
  sha256: pending
  encrypted_storage_reference: evidence-vault-case-006
  original_read_only: true
custody:
  status: pending-seal-and-handoff
  transfers: []
~~~

**Không điền `sha256: pending` bằng chuỗi giả rồi coi hồ sơ hoàn thành.** Giá trị hash phải được tính từ **file cụ thể và bytes cụ thể**, ghi chính xác kích thước, đường lưu và các lần copy.

### 17.3. Bản gốc, forensic copy và working copy

| Loại | Quyền xử lý | Mục tiêu |
|---|---|---|
| **Original source** | Giữ nguyên nếu có thể; hạn chế quyền và phương pháp tác động | Nguồn chứng cứ để kiểm tra provenance |
| **Acquired master/evidence copy** | Sealed, access controlled, hash-verified, immutable nếu phù hợp | Bản chuẩn để xác minh tính toàn vẹn |
| **Working copy** | Có thể parse, index, tạo timeline và thực hiện analysis | Bảo vệ master khỏi các thao tác phân tích |
| **Derived output** | Reports, extracted indicators, screenshots, parsed records | Phải dẫn nguồn và phương pháp biến đổi |

Nếu hệ thống nguồn **không thể giữ bất biến** (host vẫn chạy, logs được append), cần ghi **trạng thái và thời điểm thu**, không hứa toàn bộ original state đã bị đóng băng. Với disk forensic imaging, ưu tiên phương pháp kiểm định và write blocking thích hợp.

### 17.4. Hash giúp gì và không giúp gì?

Hash như **SHA-256** giúp kiểm tra hai bản bytes có giống nhau hay không và phát hiện thay đổi sau khi thu. Nhưng **hash không tự chứng minh chứng cứ ban đầu đến từ đúng thiết bị hoặc chưa bị attacker sửa trước lúc thu**. Điều đó cần chain of custody, acquisition logs, asset mapping và nguồn đối chiếu.

### 17.5. Ví dụ tính hash trên bản sao được ủy quyền

~~~powershell
# Windows: chạy trên bản sao evidence đã được phép lưu.
# Không trỏ nhầm vào ổ gốc hoặc kho chưa được phép.
Get-FileHash -Algorithm SHA256 -LiteralPath "D:\Evidence\case006\artifact-copy.bin"
~~~

~~~bash
# Linux/macOS: chạy trên file evidence copy trong môi trường forensic.
sha256sum /evidence/case006/artifact-copy.bin
~~~

Những lệnh này đọc file và tạo output hash; chưa phải **bằng chứng đầy đủ** nếu không ghi actual file size, collector identity, timestamp, storage path và transfer receipts. Khi truyền file, so hash **trước/sau chuyển** nếu workflow cho phép.

## 18. Timeline và độ chính xác thời gian

Trong sự cố mạng, nhiều log sources dùng timestamp khác nhau: EDR host local time, cloud API UTC, firewall với timezone site, packet capture theo clock của sensor, hoặc ingestion time tới SIEM.

### 18.1. Bốn thời điểm phải phân biệt

| Mốc | Ý nghĩa | Vì sao quan trọng |
|---|---|---|
| **Event time** | Sự kiện thực được nguồn ghi nhận xảy ra | Dựng thứ tự hành vi |
| **Collection time** | Responder/collector lấy dữ liệu | Xác định trạng thái ở lúc thu |
| **Ingestion time** | SIEM/log pipeline nhận bản ghi | Có thể muộn nhiều phút |
| **Action time** | Lệnh containment được gửi/được thực thi | Đánh giá có còn kết nối sau containment không |

Một command isolate được gửi lúc 03:10:00 UTC và agent xác nhận lúc 03:10:07 UTC không có nghĩa mọi packet đã dừng đúng tại 03:10:00. Phải ghi **request time, acknowledgement time, effective enforcement evidence và time offsets**.

### 18.2. Chuyển timestamp có nguồn gốc

~~~text
EDR detection:
  event_time_utc: 2026-11-28T03:01:12.382Z

Firewall session:
  device_time: 2026-11-28 10:01:12 +07:00
  normalized_utc: 2026-11-28T03:01:12Z

SIEM ingestion:
  ingest_time_utc: 2026-11-28T03:02:40Z

Containment:
  action_requested: 2026-11-28T03:10:00Z
  action_acknowledged: 2026-11-28T03:10:07Z
~~~

Đây là những giá trị **giả định** để học. Không cho rằng hai sự kiện cùng giây chắc chắn có quan hệ nhân quả; sampling, network delay và clock skew có thể ảnh hưởng thứ tự.

### 18.3. Đồng hồ không đáng tin và clock skew

- Ghi lại **NTP source/clock state** khi có quyền và trước khi thay đổi cấu hình.
- Không tự sửa system clock của endpoint nghi bị xâm nhập chỉ để đồng bộ logs.
- Khi biết chênh lệch, lưu **timestamp gốc và offset/uncertainty** trong timeline, không ghi đè nguồn.
- Với packet capture, ghi sensor clock/synchronization và capture timestamps precision.
- Với cloud logs, phân biệt event timestamp và API delivery/ingestion timestamps.
- Nếu thời gian không chắc, ghi khoảng bất định thay vì thứ tự “chắc chắn” không có bằng chứng.

### 18.4. Mẫu timeline item

~~~yaml
event_id: timeline-lab-0004
time_original: "2026-11-28 10:02:33 +07:00"
time_utc_normalized: "2026-11-28T03:02:33Z"
time_uncertainty_ms: unknown
source: firewall-session-log
source_record_reference: EVID-LAB-0042-002
asset_identity: asset-lab-0042
event_type: attempted-outbound-connection
direction: egress
network_5_tuple_reference: restricted-case-record
observed_action: firewall-allow
confidence: tentative-until-correlated
corroboration:
  - pending-edr-process-context
~~~

Một timeline tốt phân biệt **observed fact** với **analyst inference**. Ví dụ log có outbound connection attempt là fact; “dữ liệu đã bị đánh cắp” cần bytes/content/endpoint/business evidence khác để xác minh.

## 19. Encryption, secrets và bảo vệ chính kho chứng cứ

### 19.1. Bằng chứng thường chứa dữ liệu nhạy cảm

RAM dump có thể chứa **passwords, bearer tokens, session cookies, encryption keys và dữ liệu người dùng**. Disk image có thể chứa hồ sơ nhân viên/khách hàng, source code và secrets. Packet capture có thể chứa plain HTTP, DNS metadata hoặc authentication material nếu mạng không mã hóa.

**Vì vậy bảo toàn chứng cứ phải bao gồm tính bí mật**, không chỉ tính toàn vẹn. Hệ thống evidence storage cần:

- Role-based access, least privilege và approval.
- Encryption at rest/in transit, key custody phù hợp.
- Access audit, immutable retention khi phù hợp.
- Khu vực forensic analysis tách khỏi endpoints có nguy cơ xâm nhập.
- Data minimization, phạm vi pháp lý/quyền riêng tư, chính sách retention/deletion.
- Quy trình secure transfer, checksums và hậu kiểm người nhận.

### 19.2. Không phát tán IOC bằng cách phát tán dữ liệu

Một URL C2, domain hoặc process hash có thể chia sẻ trong threat intelligence theo policy. Nhưng **nguyên bộ memory dump hoặc PCAP** chứa thông tin cá nhân không nên tự đính kèm email, public ticket hay tải lên sandbox không được phê duyệt. Tách **IOC sanitized report** khỏi **raw evidence** và chỉ liên kết bằng evidence ID.

### 19.3. Khi cần revoke credentials

Một endpoint bị nghi compromise có thể chứa credentials/tokens đã bị sử dụng. Thu hồi/rotate credentials có thể ngăn attacker tiếp tục đăng nhập, nhưng cũng thay trạng thái session/auth logs. Cần:

1. Ghi identity, scopes, sessions, credential IDs và các log có liên quan.
2. Đánh giá **nguy cơ tiếp diễn**: credential còn dùng để truy cập Tier 0/production?
3. Thu hồi khẩn cấp khi cần, không đợi full memory image nếu đang mất dữ liệu.
4. Lưu timestamps của revoke, identity provider events, token lifetime và những sessions còn hoạt động.
5. Kiểm tra persistence qua OAuth apps/service principals, API keys, SSH authorized keys, remote tools theo phạm vi.
6. Không lưu chính secret/token thô trong báo cáo nếu không có yêu cầu forensic hợp pháp cụ thể.

### 19.4. Không đánh đồng encryption với integrity

Một disk snapshot đã được encryption là tốt cho confidentiality, nhưng **chưa chứng minh snapshot chưa bị thay**. Cần hash, version/immutability, audit trail và key management. Ngược lại, file có hash khớp nhưng storage mở cho tất cả analysts vẫn có rủi ro dữ liệu.

## 20. Những hành động có thể phá hỏng điều tra

| Hành động | Điều có thể mất hoặc thay đổi | Thay thế an toàn hơn khi khả thi |
|---|---|---|
| Reboot hoặc shutdown ngay | RAM, volatile keys, active sockets, unsaved buffers | Cô lập mạng, cân nhắc live collection có kiểm soát |
| `kill` tiến trình trước khi ghi trạng thái | Process tree, memory artifacts, network context | Chặn harm ở network/EDR rồi thu evidence theo risk |
| Xóa/quarantine file không ghi lại | File metadata, path, hashes, timeline | Thu/copy có kiểm soát trước hành động nếu an toàn |
| Chạy AV/full disk cleanup ngay | Filesystem thay, xóa artifacts, timestamps | Tách remediation sau preservation/containment |
| Clear Windows logs hoặc `journalctl --vacuum` | Source events, event sequence | Export/preserve central logs; không xóa bản gốc |
| Thay system clock | Timeline gốc và source offset | Ghi clock skew, chuẩn hóa trên analysis copy |
| Tắt EDR/IDS để giảm cảnh báo | Mất telemetry, blind spot khi còn attacker | Tune detections trong phạm vi approved, giữ audit |
| Tải công cụ forensic tùy ý từ Internet | Chèn binary/telemetry mới, nguy cơ supply chain | Dùng verified approved toolkit/offline distribution |
| Gửi PCAP/RAM dump qua public SaaS | Rò rỉ secrets và privacy data | Restricted encrypted evidence repository |
| Mount forensic original read-write | Có thể đổi metadata và filesystem structures | Write blocker/read-only mount, working copy |
| Xóa/terminate Pod ngay | Mất ephemeral layer, container logs/runtime state | Preserve external logs/metadata, đánh giá targeted containment |
| Thay toàn subnet ACL không review | Gián đoạn dịch vụ và mất remote evidence channel | Narrowly scoped containment, explicit owner |
| Trình bày suy đoán như fact | Làm lệch kết luận điều tra | Annotate observation, inference và confidence |

**Không có thao tác nào hoàn toàn không làm thay đổi môi trường sống.** Người ứng phó phải **giảm, ghi và giải thích** những thay đổi do chính hoạt động điều tra tạo ra.

## 21. Case study 1 — Workstation nghi ransomware: cô lập trước, giữ bằng chứng sau

### 21.1. Tình huống giả định

Một workstation thuộc nhóm tài chính tạo nhiều thao tác ghi file, đổi phần mở rộng và kết nối bất thường tới một số máy trong cùng VLAN. EDR sinh alert **suspected ransomware behavior**; có người dùng báo không mở được một số tệp. Máy vẫn còn online và EDR agent báo trạng thái healthy. Team chưa biết đây là mã độc thật hay một batch script hợp lệ.

Các thời điểm giả định:

~~~text
03:01:12 UTC   EDR phát hiện tiến trình có hành vi đổi nhiều tệp
03:01:20 UTC   Firewall ghi nhiều kết nối SMB nội bộ từ endpoint
03:02:05 UTC   Helpdesk nhận yêu cầu về file không mở được
03:02:20 UTC   Incident commander phân loại risk high, đề nghị containment
03:02:40 UTC   EDR isolation command được gửi
03:02:48 UTC   EDR báo đã áp dụng isolation
03:02:52 UTC   NAC/firewall telemetry xác nhận traffic lateral bị chặn
03:03:00 UTC   External logs retention được preservation
03:10:00 UTC   Forensic responder kiểm tra đường thu memory còn được phép
~~~

Đây là **kịch bản luyện tập**, không phải sự cố thực tế hay kết quả quan sát từ hệ thống. Sự phân biệt `command sent` – `agent acknowledged` – `traffic effectively blocked` được giữ để tránh kết luận quá sớm.

### 21.2. Quyết định cô lập

Vì nguy cơ mã hóa/lan sang file shares đang tiếp diễn, team chọn **cô lập ngay tại EDR** sau khi đối chiếu đúng host identity. Không chờ hoàn thành full memory dump nếu điều đó có thể kéo dài khả năng gây hại. Đồng thời, responder khác:

1. Preserves EDR process tree, DNS, firewall, file server access logs và IdP sessions.
2. Ghi **asset ID, user session, public/private IP, UTC clock và incident ticket**.
3. Xác nhận EDR agent có giữ kênh quản lý để thu thêm evidence không.
4. Kiểm tra traffic chặn ở switch/firewall từ network logs.
5. Liên hệ owner file servers và backup teams để đánh giá blast radius.

### 21.3. Sơ đồ containment và bằng chứng

~~~mermaid
flowchart LR
    W["Suspected workstation"] -->|"Attempted SMB"| FS["File server"]
    W -->|"Attempted egress"| EXT["External endpoint"]
    EDR["EDR containment"] -. "Isolate host" .-> W
    FW["Firewall/NAC"] -. "Independent validation" .-> W
    SIEM["SIEM preservation"] --> D["Restricted evidence store"]
    EDR --> D
    FW --> D
    FS --> D
~~~

### 21.4. Thu bằng chứng sau cô lập

Nếu EDR còn hỗ trợ forensic channel, đội được ủy quyền có thể thu **process list, socket state, user sessions, file metadata, memory artifacts** theo playbook và mức rủi ro; ghi **tác động của lệnh thu**. Nếu EDR channel mất, dùng **physical/console response** thay vì mở lại mạng rộng.

Khi có quyết định reimage, trước đó cần giữ **disk evidence/snapshot** theo scope và xác định dữ liệu trên share/backup có bị ảnh hưởng. Không xóa working copies/restore points hay tắt file server logs chỉ vì workstation đã cô lập.

### 21.5. Kiểm thử sau containment

| Luồng/đối tượng | Kỳ vọng | Bằng chứng |
|---|---|---|
| Workstation → file server SMB | DENY | NAC/firewall drops, không tạo session mới |
| Workstation → external arbitrary destination | DENY | Egress policy/flow logs |
| Internet/user → workstation | DENY ngoài đường đã phê duyệt | ACL logs, controlled negative test |
| EDR → workstation management channel | ALLOW nếu sản phẩm hỗ trợ ngoại lệ | EDR heartbeat, signed agent command acknowledgement |
| Forensic export → evidence store | Chỉ qua approved path, nếu có | Transfer audit, file hash, chain of custody |
| Healthy workstation → file server | ALLOW nếu policy không cấm | Positive control không gây tác động |

**Không đánh dấu PASS chỉ bằng việc workstation không ping được**: ICMP có thể bị chặn trước đó; cần evidence từ đúng containment mechanism và một positive control phù hợp.

### 21.6. Những điều phải còn được điều tra

- Source của tiến trình đáng ngờ, parent process và initial access.
- Có credentials nào bị đánh cắp hoặc được dùng trên host khác không?
- File share/object storage/backup có bị truy cập ngoài ý định?
- Có evidence exfiltration thực hay chỉ connection attempts?
- Lateral movement có xảy ra trước thời điểm cô lập?
- Endpoint khác cùng IOC/process/identity cần triage không?
- Khi nào mới đủ điều kiện revoke/tăng bảo vệ và khôi phục máy?

**Bài học:** hành động cô lập khẩn cấp có thể đúng ngay cả khi chưa thu được toàn bộ RAM, miễn là quyết định được ghi và evidence từ nhiều nguồn độc lập được giữ có kiểm soát.

## 22. Case study 2 — VM sản xuất nghi exfiltration nhưng mất kết nối EDR

### 22.1. Bối cảnh giả định

Một VM production chạy dịch vụ quan trọng có outbound flows bất thường tới một external destination. EDR agent không phản hồi, nên nút isolation trong console chuyển sang **pending**. VM có hai network interfaces: một NIC cho ứng dụng và một NIC cho management. Dịch vụ có HA nhưng không thể tắt máy ngay mà không đánh giá failover.

Tình trạng:

~~~text
VM instance ID: vm-prod-lab-07
Application NIC: nic-app-07
Management NIC: nic-mgmt-07
EDR agent: offline
Firewall egress to observed destination: active
Cloud flow log: available with aggregation/sampling
Disk volumes: encrypted, cloud snapshots supported
Application replicas: HA status pending validation
~~~

### 22.2. Lựa chọn containment

Thay vì tiếp tục nhấn EDR isolation và coi đã thành công, incident commander phối hợp platform/cloud owner:

1. Xác định instance/NIC IDs, network routes, identity và service dependency.
2. Preservation cloud control plane events, VPC flow logs, firewall/NAT session logs và API/app logs.
3. Đánh giá chặn **targeted egress** trước để ngăn suspected exfiltration, có theo dõi đường khác.
4. Nếu cần mạnh hơn, dùng **per-NIC/cloud security group/NSG containment** với tất cả NICs trong phạm vi, xét stateful sessions/IPv6.
5. Xác nhận HA/health và giữ management/OOB path theo policy hoặc chuẩn bị console response.
6. Cân nhắc snapshot/disk evidence **trước terminate/reimage**; memory acquisition chỉ khi platform/forensic team hỗ trợ.
7. Kiểm tra external flows thực sự dừng ở firewall/cloud network PEP.

### 22.3. Tại sao chặn một NIC có thể chưa đủ?

~~~mermaid
flowchart LR
    VM["Production VM"] --> A["NIC app"]
    VM --> B["NIC management"]
    A --> FW["Cloud firewall / route A"]
    B --> MGMT["Management network / route B"]
    FW --> EX["External destination"]
    MGMT -. "Possible alternate egress if misconfigured" .-> EX
~~~

Nếu chỉ chặn application NIC mà management NIC có route ra ngoài hoặc proxy tunnel, exfiltration có thể tiếp tục. Nếu chặn **mọi NIC ngay** có thể cắt khả năng lấy evidence/health checks hoặc làm service down. Cần dựa vào **actual routing, network policies và mục tiêu containment**, không suy từ tên NIC.

### 22.4. Evidence và timeline bắt buộc

| Loại chứng cứ | Nội dung cần ghi |
|---|---|
| Cloud instance/NIC metadata | Resource IDs, regions, addresses, subnet, security groups trước/sau |
| Control-plane audit | Ai sửa NIC/SG/routes, API request ID, UTC timestamp |
| Flow/network | Pre/post NAT addresses, bytes, destination, action, sampling |
| EDR | Agent last seen, isolation command pending, error reason |
| Application | Service logs, health, dependency errors, transaction impact |
| Storage | Snapshot IDs, volume maps, consistency, KMS/encryption context |
| Recovery | HA failover status, rollback decision, release controls |

### 22.5. Phép thử mục tiêu

~~~text
Egress to observed destination          : DENY
Egress via alternative NIC or IPv6     : DENY outside approved exceptions
Healthy replica serves eligible users : ALLOW
Cloud control-plane audit             : PRESERVED
EDR isolation status                  : PENDING/UNKNOWN (không tự PASS)
Disk snapshot evidence                 : CAPTURED/VERIFIED if approved
Rollback path and authorization        : DOCUMENTED
~~~

### 22.6. Bài học

**Khi EDR offline, điểm thực thi ở network/cloud có thể trở thành công cụ containment chính**. Nhưng phải gắn đúng VM/NIC identity, xét nhiều đường đi và giữ cloud metadata/snapshots. Trạng thái lệnh trên console **không thay thế verification of effective isolation**.

## 23. Tái mở mạng: “release isolation” là một quyết định bảo mật mới

Gỡ containment trước khi hoàn tất eradication có thể trả quyền kết nối cho attacker hoặc malware vẫn còn. Các điều kiện khôi phục phải riêng với điều kiện cô lập:

1. **Incident lead xác nhận** phạm vi đã được xác định đủ và rủi ro chấp nhận được.
2. Evidence cần thiết đã được thu/niêm phong hoặc ghi rõ lý do không thể thu.
3. Credential/token/key compromise đã được đánh giá và xử lý theo quyền.
4. Nếu cần, endpoint đã **rebuild từ nguồn đáng tin** thay vì chỉ xóa một file.
5. OS/EDR/patch/security configuration và agent health đạt baseline.
6. NetworkPolicy, firewall/EDR rules mới không tạo **đường bypass**.
7. Business owner duyệt cửa sổ đưa dịch vụ trở lại, có canary và rollback.
8. SOC giám sát hành vi mới; không xóa evidence hoặc đóng incident ngay khi ping thành công.

### 23.1. Cần test điều gì khi thả endpoint?

| Kiểm thử | Kỳ vọng |
|---|---|
| Chứng nhận identity/hostname/asset mapping | Tài sản khôi phục đúng, không nhầm clone/IP |
| EDR health và telemetry | Đầy đủ, policy cập nhật, logs đến SIEM |
| Authorized application flow | Đạt chức năng, TLS/identity và SLO |
| Unauthorized lateral flow | Vẫn DENY theo network policy bình thường |
| Egress to previously observed IOC | Vẫn bị policy bảo vệ nếu còn liên quan |
| Privileged login/MFA | Chỉ roles/identities hợp lệ |
| Post-release monitoring window | Không thấy dấu hiệu persistence mới trong thời gian giám sát |

**Không nới lỏng firewall hoặc tắt EDR mặc định để “chắc chắn host hoạt động”.** Nếu có exception tạm thời, phải có owner, TTL, reason và kiểm soát bù trừ.

## 24. Ma trận 40 trường hợp kiểm thử containment và evidence preservation

Ma trận dưới đây là **bộ tiêu chí kiểm thử đề xuất cho lab/diễn tập được phê duyệt**, không phải kết quả đã chạy. Các kiểm thử active chỉ được thực hiện với tài sản kiểm thử thuộc quyền quản lý; với sản xuất có thể thay bằng **read-only config audit, logs và simulation** để không gây ngắt dịch vụ.

| Test ID | Mục tiêu | Phương pháp có kiểm soát | PASS khi |
|---|---|---|---|
| **IDN-01** | Đúng endpoint identity | So EDR agent ID, CMDB, VM/Pod UID, hostname | Identity trùng và có UTC reference |
| **IDN-02** | IP cũ không chỉ nhầm endpoint | So DHCP lease/NAT/VPN tại thời điểm alert | Không isolate asset mới nhận IP |
| **IDN-03** | Xác định multi-NIC/IPv6 | Inventory NICs/routes/wired/Wi-Fi | Tất cả đường cần kiểm soát đã có owner |
| **IDN-04** | Phân loại impact/safety đúng | Review criticality, OT/production dependencies | Có risk owner/approval theo policy |
| **DEC-01** | Hành động khẩn cấp được phê duyệt | Review incident decision and escalation | Decision maker, reason, time documented |
| **DEC-02** | Thu volatile trước isolate khi an toàn | Simulate low-risk lab incident | Quick capture có hạn thời gian và log tác động |
| **DEC-03** | Cô lập trước capture khi exfil đang diễn ra | Tabletop/lab giả lập high-impact | Không để kéo dài hại chỉ vì full memory dump |
| **DEC-04** | Không tắt nguồn mặc định | Review playbook for live host | Reboot/shutdown chỉ theo risk decision |
| **DEC-05** | Không cô lập quá phạm vi | Impact analysis source/dest match | Không làm mất traffic của asset khác ngoài policy |
| **ISO-01** | Lệnh EDR thực sự áp | So send/ack/EDR status và flow logs | Không chỉ dựa queued/sent status |
| **ISO-02** | Egress Internet bị chặn | Controlled request từ isolated lab asset | DENY ở intended PEP |
| **ISO-03** | Lateral SMB/RDP bị chặn | Controlled lab flow tới peer | DENY, peer vẫn healthy |
| **ISO-04** | Inbound session bị chặn | Approved source test tới lab host | DENY ngoài exception |
| **ISO-05** | EDR management exception đúng | Agent heartbeat/control test nếu hỗ trợ | Only approved management connectivity còn hoạt động |
| **ISO-06** | IPv6 không bypass | IPv4/IPv6 route and policy verification | Deny intent nhất quán |
| **ISO-07** | Wi-Fi/VPN/cellular không bypass | Inventory và controlled alternate-path test | Không tồn tại đường tiếp tục exfil |
| **ISO-08** | Existing stateful sessions bị xử lý | Review firewall sessions/flows after action | Không tiếp tục flow ngoài ý định |
| **ISO-09** | NAC/port mapping chính xác | Switch auth session + port/device association | Không cô lập nhầm AP/phone/other device |
| **ISO-10** | Positive control của nguồn khác vẫn OK | Approved healthy client→same service | Không đánh nhầm outage thành deny PASS |
| **EVD-01** | Central logs được giữ | Export/snapshot retention metadata | EDR/DNS/firewall/IAM logs không mất |
| **EVD-02** | Volatile acquisition được cân nhắc | Review memory/process/socket plan | Decision/time/tool/limits recorded |
| **EVD-03** | Bản gốc và working copy tách biệt | Review evidence repository permissions | Master sealed, working copy tracked |
| **EVD-04** | SHA-256 và size chính xác | Hash authorized copy pre/post transfer | Bytes/hash khớp và ghi evidence ID |
| **EVD-05** | Chain of custody đầy đủ | Diễn tập handoff giữa responders | Có sender, receiver, UTC time, purpose |
| **EVD-06** | Timeline biết clock skew | Correlate UTC host/EDR/cloud events | Original time và offset giữ lại |
| **EVD-07** | Thu thập không tiết lộ secrets | Review capture scope/storage ACL | Không phát tán token/PCAP/RAM công khai |
| **EVD-08** | Không cleanup trước preservation | Review incident workflow và commands | Không delete logs/erase/reimage trước decision |
| **CLOUD-01** | Cloud VM gắn đúng NIC | Instance/NIC IDs, region, SG mapping | Chặn đúng VM, không nhầm IP tái sử dụng |
| **CLOUD-02** | Multi-NIC cloud isolation hiệu quả | Per-NIC flows và route verification | Không còn egress qua NIC phụ |
| **CLOUD-03** | Snapshot đầy đủ metadata | Snapshot volume maps/consistency record | IDs, time, encryption và scope rõ |
| **CLOUD-04** | Pod metadata được bảo toàn | Pod UID/image digest/runtime logs inventory | Chưa mất evidence do auto-recreation |
| **CLOUD-05** | NetworkPolicy enforce thực | CNI logs và test Pod approved/unapproved | Deny đúng policy, không bị allow khác phủ |
| **REC-01** | Rollback path an toàn | Tabletop/lab revert containment | Có người phê duyệt và đường OOB |
| **REC-02** | Eradication trước release | Review security posture/credentials | Không mở lại host còn persistence |
| **REC-03** | Released endpoint vẫn least privilege | Allowed and denied regression flows | Business flows OK, lateral policy DENY |
| **REC-04** | DR/replacement không thất lạc chứng cứ | Restore/rebuild tabletop | Evidence preserved và asset mapping rõ |
| **OBS-01** | No-data không tự PASS | Simulate EDR agent offline | Pending/unknown và escalation phù hợp |
| **OBS-02** | Deny/allow telemetry đến đúng nơi | Correlate PEP/flow timestamps | Thấy hiệu lực tại đúng boundary |
| **OBS-03** | Case report tách fact/inference | Independent evidence review | Kết luận có nguồn và confidence |
| **OBS-04** | Phiên ứng phó được audit | Identity, commands, time, changes review | Người thao tác và actions truy vết |

### 24.1. PASS, FAIL, INCONCLUSIVE

- **PASS:** evidence chứng minh đúng asset, đúng policy boundary, hành động có phê duyệt và kết quả thực; các nguồn chứng cứ chủ yếu được bảo toàn/có lý do nếu không thể thu.
- **FAIL:** isolated host vẫn có đường exfil/lateral ngoài policy; cô lập nhầm asset; hash mismatch không giải thích được; mất evidence bởi cleanup trái quy trình; hoặc bảo mật/mở lại mạng ngoài authorization.
- **INCONCLUSIVE:** không đủ log, host down từ trước, EDR chỉ báo queued, test không tới đúng PEP, chưa biết NAT/host identity hoặc chưa có positive control.

**Timeout không chứng minh containment hiệu quả** nếu endpoint ban đầu đã tắt. **EDR status “isolated” cũng chưa đủ** nếu Wi-Fi/cellular/IPv6 hoặc cloud NIC khác vẫn có đường đi.

### 24.2. Mẫu bằng chứng kiểm thử

~~~yaml
test_id: ISO-02
environment: isolated-authorized-ir-lab
time_utc: pending
incident_id: INC-LAB-2026-006
source:
  endpoint_id: asset-lab-0042
  agent_id: agent-id-from-inventory
target:
  destination: approved-test-endpoint
  protocol: HTTPS
containment:
  method: edr-network-isolation
  action_id: pending
  action_acknowledged_utc: pending
expected:
  arbitrary_egress: deny
  approved_management_channel: policy-specific
  healthy_control_asset_to_test_endpoint: allow
evidence_required:
  - edr-action-and-agent-status
  - firewall-or-nac-observed-flow
  - both-ipv4-ipv6-paths-evaluated
  - timestamps-and-policy-version
  - incident-commander-approval
result: pending-execution
~~~

**Không điền PASS trước khi chạy phép thử đúng điều kiện.** Không lưu raw credentials/PII/packet payload ngoài scope trong record kiểm thử.

## 25. Troubleshooting: khi containment làm mất đường thu hoặc chưa đủ chặn

| Dấu hiệu | Giả thuyết | Cách xác minh an toàn |
|---|---|---|
| EDR “isolate sent” nhưng host còn traffic | Agent offline, command pending, driver/policy lỗi | Agent acknowledgement, network PEP logs |
| EDR UI “isolated” nhưng vẫn có external flows | Secondary NIC, proxy/VPN, IPv6, agent bypass | Multi-path inventory, independent firewall logs |
| Cắt network nhưng EDR không còn truy cập | Sản phẩm không giữ management exception hoặc DNS/proxy bị chặn | Vendor behavior, OOB/physical path |
| NAC quarantine không áp lên host | Sai MAC, 802.1X session, switch port, SSID | NAC logs, switch auth session, DHCP leases |
| Disable port ảnh hưởng nhiều máy | Downstream AP/hub/phone/PoE | Physical topology và access switch inventory |
| Firewall block không chặn established TCP | Stateful session semantics hoặc rule chưa áp existing flows | Session table, device config, flow timeline |
| IP deny chặn máy khác sau một giờ | DHCP IP reassignment hoặc NAT | Lease time/asset mapping và rule selector |
| Cloud SG block nhưng vẫn egress | NIC khác, IPv6, VPC route, NAT, SG/NSG semantics | Instance/NIC inventory, flow logs |
| VM snapshot có nhưng RAM không còn | Disk snapshot không thu volatile memory | Method/consistency, original power-state record |
| Pod bị delete trước khi thu | Ephemeral layer/runtime data bị GC | Orchestrator audit, external logs, backup sources |
| PCAP thiếu traffic đáng ngờ | Capture sai interface, sau firewall, sampling/loss | Topology, tap placement, sensor clock/counters |
| DNS logs không match host | Shared resolver, cache, DoH, NAT | Client config và timestamp correlation |
| Hash khác sau transfer | File chưa ổn định, copy lỗi, wrong file/version | Reconcile file size, source/copy and collection logs |
| Time line đảo sự kiện | Clock skew, time zone, delayed ingest | Original/normalized timestamps và uncertainty |
| Windows command không trả PID/Path | Quyền thiếu, process exit, protected process | EDR events, access logs, tool error details |
| Linux logs vắng | Journald retention, audit disabled, attacker tamper | Central SIEM, network/control-plane logs |
| Memory acquisition làm host quá tải | RAM size, memory pressure, output destination | Forensic owner, impact/risk, alternate plan |
| File copy chứa secret tới shared drive | Evidence repository không đáp ứng privacy | Restricted storage, incident privacy owner |
| Chặn exfil làm business service mất sẵn sàng | Shared destination/allowlist quá rộng | Asset impact, policy diff, canary, escalation |
| Host released lại phát C2 signals | Persistence, stolen credentials, incomplete rebuild | Re-isolate, reassess incident scope, revocation |
| Không xác định ai thao tác isolation | Shared admin account, thiếu PAM/console audit | Control-plane audit, identity lifecycle |

### 25.1. Thứ tự chẩn đoán một hành động cô lập

1. Xác định **incident ID, asset identity và business impact**.
2. Tìm **điểm thực thi**: EDR agent, switch/NAC, firewall, cloud NIC hay CNI.
3. So **command requested, accepted, applied** theo UTC.
4. Kiểm tra đường mạng thực: ingress/egress, IPv4/IPv6, wired/Wi-Fi/VPN, established sessions.
5. Chạy **positive control** trên tài nguyên khỏe và **negative flow** từ endpoint lab theo quyền.
6. Đối chiếu EDR, firewall/NAC/cloud logs, không chỉ một UI.
7. Nếu mất kênh thu evidence, đánh giá **OOB/physical response**, không tự mở tất cả egress.
8. Kiểm tra chain of custody, volatile evidence decisions và dữ liệu mất/thiếu.
9. Chỉ sửa containment theo approval; ghi policy diff/action IDs.
10. Kiểm tra lại hiệu lực sau thay đổi, kèm impact lên người dùng và khả năng recovery.

### 25.2. Những kết luận cần tránh

> “Ping không được, vậy đã cô lập hoàn toàn.”

ICMP có thể bị chặn sẵn; TCP/443 hoặc IPv6 vẫn có đường.

> “EDR bảo isolated, nên không cần firewall logs.”

Agent có thể lỗi hoặc không bao phủ NIC/OS paths. Cần independent validation.

> “Có SHA-256 rồi, chứng cứ chắc chắn là thật.”

Hash chỉ xác minh bytes của bản đã hash, không chứng minh nguồn gốc và trạng thái trước thu.

> “Tắt máy là cách giữ bằng chứng tốt nhất.”

Power-off làm mất RAM/sessions và có thể khiến dữ liệu mã hóa không mở được; lựa chọn phụ thuộc risk.

> “Đã xóa mã độc, có thể đóng incident và mở mạng.”

Credential theft, persistence, lateral movement và data access cần được điều tra/khắc phục trước release.

## 26. Runbook cô lập endpoint có bảo toàn chứng cứ

Runbook dưới đây trình bày **quy trình ra quyết định và bàn giao**; các lệnh cấu hình cụ thể để cô lập phải theo **EDR/NAC/firewall/cloud/OT product và phê duyệt** của tổ chức. Không có một lệnh chung an toàn cho mọi môi trường.

### Bước 0 — Xác nhận thẩm quyền và an toàn

- Có incident/case ID, người chỉ huy sự cố hoặc delegated responder.
- Đánh giá nhanh nguy cơ **mã hóa, exfiltration, safety, production impact**.
- Xác nhận tài sản không thuộc hệ OT/medical/critical safety cần phương án riêng.
- Chọn người chịu trách nhiệm **containment**, **forensic acquisition**, **network/cloud**, **asset owner**, **legal/privacy** khi cần.
- Đặt **mục tiêu containment có thể kiểm thử**: chặn những luồng nào, giữ kênh gì, trong bao lâu?

Trong sự cố khẩn cấp, có thể containment trước khi hoàn thành tất cả biểu mẫu theo emergency authorization; **phải ghi quyết định hậu kiểm** và tránh hành động ngoài thẩm quyền.

### Bước 1 — Xác định đúng endpoint

~~~text
Incident ID:
Asset ID:
EDR agent ID:
Hostname / OS:
VM, cloud, node, Pod UID nếu áp dụng:
User/session:
Network addresses + timestamp:
DHCP/NAC/switch port mapping:
Management path / OOB:
Owner / criticality:
~~~

**Không isolate chỉ từ IP đơn lẻ** khi có DHCP/NAT/containers. Kiểm tra các nguồn định danh khác nhau và ghi mức độ chắc chắn.

### Bước 2 — Thu và giữ chứng cứ bên ngoài trước hoặc đồng thời

1. Ghi/giữ **alert, process tree, EDR detection record và agent ID**.
2. Preservation **DNS, proxy, firewall, VPN/IdP, cloud audit, CNI, SIEM** với time range hợp lệ.
3. Đánh giá retention, sampling, clock skew và những nguồn sẽ mất khi cô lập.
4. Tạo restricted evidence workspace với chain of custody và access policy.
5. Ghi người thao tác, công cụ/version, query/filter và thời điểm export.

Nếu exfiltration/ransomware đang diễn ra, bước này có thể **chạy song song** với containment chứ không chờ export hoàn tất.

### Bước 3 — Quyết định thu volatile trước hay sau isolation

~~~mermaid
flowchart TD
    START["Suspected endpoint + incident triage"] --> H{"Ongoing high-impact harm?"}
    H -- "Có" --> ISO["Contain promptly at effective PEP"]
    H -- "Không / kiểm soát được" --> V{"Volatile collection safe, fast, authorized?"}
    V -- "Có" --> CAP["Capture prioritized volatile state"]
    V -- "Không" --> ISO
    CAP --> ISO
    ISO --> VERIFY{"Containment independently verified?"}
    VERIFY -- "Không" --> ALT["Escalate to alternate network/OOB PEP"]
    ALT --> VERIFY
    VERIFY -- "Có" --> EVID["Preserve memory/disk/logs as feasible"]
    EVID --> CASE["Evidence seal + timeline + IR analysis"]
~~~

Điều kiện “có thể thu” bao gồm **người có chuyên môn, công cụ phù hợp, quyền hợp pháp, time budget và rủi ro chấp nhận được**. Full RAM capture trên máy nhiều trăm GiB có thể không thích hợp trước containment.

### Bước 4 — Thực hiện containment đúng scope

| Môi trường | Phương án điển hình | Cần kiểm tra trước khi áp |
|---|---|---|
| Managed workstation | EDR network isolation | Agent identity/health, quản lý ngoại lệ |
| Wired/Wi-Fi unmanaged | NAC dynamic ACL/quarantine, switch/controller | MAC/port/client mapping, shared port/SSID |
| Server không có EDR | Firewall/cloud NIC policy, OOB console | Multi-NIC, production dependencies |
| VPN user session | Revoke session/identity entitlement và endpoint network isolate | Local/external paths không qua VPN |
| Cloud VM | Targeted SG/NSG/firewall/NIC enforcement | Instance ID, stateful existing sessions, IPv6 |
| Kubernetes Pod | CNI/NetworkPolicy hoặc orchestration control theo policy | Pod UID/label, CNI support, ephemeral evidence |
| OT/critical device | Vendor/OT safety playbook và network zone controls | Safety, uptime, protocol limitations |

Ghi **action ID, requested/applied UTC, actor, original policy state, expected effect và rollback owner**.

### Bước 5 — Verify bằng nhiều nguồn

Kiểm tra:

- EDR/NAC/firewall/cloud PEP có áp policy không?
- **Ingress/egress và lateral** traffic còn hoạt động trái ý định không?
- IPv4, IPv6, NIC phụ, Wi-Fi, VPN, cellular, proxy và management path thế nào?
- Existing sessions có tiếp tục theo policy stateful không?
- Positive control từ healthy authorized endpoint có còn hoạt động không?
- EDR/forensic exception có đúng hẹp và cần thiết?
- Có ảnh hưởng hệ thống khác hoặc alert outage mới không?

**Không để trạng thái chỉ “queued”, “unknown” hoặc “timeout” trở thành PASS.** Khi chưa đủ evidence, dùng trạng thái `INCONCLUSIVE`, báo người chỉ huy và triển khai biện pháp thay thế trong phạm vi cho phép.

### Bước 6 — Preservation và acquisition có giám sát

1. Giữ bản gốc logs/exports trong restricted repository.
2. Cân nhắc memory capture và volatile state **khi host còn chạy và điều kiện an toàn**.
3. Thu disk/volume image/snapshot phù hợp OS/cloud, ghi consistency/encryption.
4. Hash artifacts và so trước/sau truyền, lập evidence inventory.
5. Tạo working copy để phân tích, tránh sửa master.
6. Tách facts/inferences, giữ original timestamps và normalize UTC trên timeline.
7. Ghi rõ dữ liệu **không thể thu được và lý do**.

### Bước 7 — Điều tra phạm vi và xử lý persistence

- Phân tích initial access, user/service identities, lateral movement, exfiltration evidence.
- Đối chiếu process/network, DNS, firewall/NAT, auth và cloud logs.
- Thu hồi/rotate **compromised credentials**, review privileged grants/tokens.
- Tìm những asset khác có dấu hiệu liên quan và mở rộng triage theo risk.
- Eradication/rebuild/redeploy bằng nguồn đáng tin sau khi đã giữ evidence theo scope.
- Đánh giá pháp lý/thông báo bên liên quan theo incident policy.

### Bước 8 — Release isolation có điều kiện

~~~text
Evidence acquisition and handoff: verified / documented exceptions
Malware/persistence risk: addressed
Credential and identity risk: assessed and remediated
Endpoint baseline: rebuilt or validated
EDR and logging: healthy
Business owner approval: recorded
Release action/rollback: ready
Positive and negative flows: tested
Enhanced monitoring window: assigned
~~~

**Mở lại mạng không tự là recovery hoàn tất.** Nếu host phát traffic đáng ngờ trở lại hoặc điều kiện bảo mật không đạt, cần tái cô lập và điều tra thêm theo playbook.

### Bước 9 — Hậu kiểm và lessons learned

Một báo cáo sau sự cố nên chỉ ra:

| Phần | Nội dung |
|---|---|
| Detection → decision → effective isolation | Mốc UTC và delay của từng bước |
| Blast radius | Các hệ thống/tài khoản/luồng thực sự bị ảnh hưởng |
| Evidence coverage | Đã thu nguồn nào, thiếu gì và vì sao |
| Integrity/custody | Evidence IDs, hashes, transfer receipts |
| Isolation effectiveness | Kết quả test theo ingress/egress/alternate paths |
| Business effect | Outage, recovery time, dữ liệu/rủi ro đã giảm |
| Root cause và uncertainty | Fact, inference, độ tin cậy |
| Control improvements | EDR/NAC/firewall coverage, audit/retention, identity controls |
| Owners/deadlines | Ai triển khai cải tiến, khi nào đánh giá lại |

## 27. Bài tập tự kiểm tra và ứng dụng

### Bài 1 — Cô lập trước hay lấy RAM trước?

Máy trạm đang mã hóa file share rất nhanh. Đội forensic đề xuất đợi 40 phút lấy full memory dump. Bạn chọn gì?

*Đáp án gợi ý:* ưu tiên containment đủ nhanh để ngăn thiệt hại, ghi lý do, thu external telemetry đồng thời; cân nhắc memory capture sau khi endpoint được ngăn gây hại nếu còn khả thi.

### Bài 2 — EDR command queued

Nút isolate trong EDR console báo “command queued”, agent đã mất heartbeat. Có thể ghi host `ISOLATED` không?

*Đáp án:* không. Trạng thái phải là pending/unknown; kiểm tra network PEP độc lập và cân nhắc NAC/firewall/cloud isolation.

### Bài 3 — Host có hai NIC

Cloud VM có application NIC và management NIC. Chặn NIC ứng dụng có chứng minh không còn egress Internet không?

*Gợi ý:* không. Cần xem routes/SG/NSG trên mọi NIC, IPv4/IPv6, NAT và proxy paths.

### Bài 4 — Máy bị mất điện

Một responder tắt nguồn workstation trước khi ghi RAM. Những loại chứng cứ nào có thể mất?

*Gợi ý:* active sessions, running processes, volatile keys, memory-resident data, in-memory caches, một số filesystem buffers.

### Bài 5 — Volatile evidence và một lệnh `ps`

Một responder chạy `ps aux` và nói “lệnh này không làm thay đổi gì nên là forensic image hoàn hảo”. Đúng không?

*Đáp án:* không. Việc thực thi tạo process/audit/memory/cache changes; cần ghi command/time/tool/output và giới hạn.

### Bài 6 — IP không ổn định

Firewall log lúc 10:00 ghi IP `192.0.2.42`, DHCP lease lúc 11:00 gán IP đó cho máy khác. Nên cô lập máy nào?

*Gợi ý:* xác minh identity theo **thời điểm 10:00**, bằng DHCP/NAC/EDR/asset mapping; không chặn host đang giữ IP 11:00 khi chưa kiểm tra.

### Bài 7 — NetworkPolicy mặc định từ chối

Một NetworkPolicy `podSelector` chọn Pod nghi bị tấn công, không có allow rules. Có chắc Pod đã bị chặn dù namespace có một ALLOW policy khác?

*Đáp án:* không. Standard NetworkPolicy có allow rules cộng dồn; phải xét toàn bộ policies và CNI enforcement.

### Bài 8 — EDR và IPv6

Sau containment, ping IPv4 không được nhưng host vẫn gửi request qua IPv6. Kết luận gì?

*Gợi ý:* containment chưa đạt mục tiêu; phải xem EDR coverage, IPv6 routes/firewall và alternate NICs, triển khai biện pháp bổ sung có thẩm quyền.

### Bài 9 — Packet capture ở sau firewall

PCAP đặt ngoài firewall không thấy traffic dù deny logs ở firewall tăng. Có thể nói host không cố kết nối nữa không?

*Đáp án:* không. Gói có thể bị chặn trước điểm capture; cần logs/tap ở đúng phía hoặc EDR network events.

### Bài 10 — Hash và provenance

Hai bản file có cùng SHA-256; điều đó tự chứng minh file gốc được lấy từ đúng VM chưa bị sửa bởi attacker không?

*Đáp án:* không. Hash chứng minh tính đồng nhất bytes của hai bản, còn provenance cần asset identity, acquisition logs và nguồn xác minh.

### Bài 11 — Snapshot cloud

Một VM disk snapshot có thể tự chứa memory của SSH process đang chạy không?

*Gợi ý:* không mặc định. Disk snapshot lưu storage theo cloud semantics, không tự lưu toàn RAM; kiểm tra platform-specific memory acquisition nếu cần.

### Bài 12 — Windows encrypted volume

Laptop đang bật và volume BitLocker đã unlock. Vì sao reboot ngay có thể gây khó cho forensic analysis?

*Gợi ý:* mất volatile keys/sessions và có thể cần recovery keys sau power-off; phối hợp chuyên gia trước khi quyết định, nếu rủi ro cho phép.

### Bài 13 — Phân biệt detect và block

IDS out-of-band báo hàng nghìn alerts. Có thể khẳng định chính IDS đã chặn traffic độc hại không?

*Đáp án:* không. Detection-only và inline blocking khác nhau; cần xem sensor mode và firewall/network PEP logs.

### Bài 14 — False positive do NAC

NAC quarantine cùng một switch port khiến một điện thoại IP và workstation mất mạng. Cần điều tra gì?

*Gợi ý:* port physical topology, PoE/downstream devices, NAC identity, source mapping và impact; tránh giả định mỗi port chỉ có một thiết bị.

### Bài 15 — Time skew

EDR host timestamp và firewall event timestamp chênh hai phút. Có nên sửa log gốc cho chúng trùng nhau?

*Đáp án:* không. Giữ original timestamps; normalize trên working timeline với offset và uncertainty.

### Bài 16 — Chain of custody

Responder sao chép RAM dump qua một USB chưa mã hóa, gửi cho ba người và không ghi nhận ai nhận. Những thuộc tính chứng cứ nào bị ảnh hưởng?

*Gợi ý:* confidentiality, chain of custody, provenance/transfer audit và khả năng chứng minh integrity; cần quy trình lưu/chuyển kiểm soát.

### Bài 17 — Từ chối sai vì backend down

Unapproved host không truy cập được database, nhưng database service đang tắt. Có thể ghi “Firewall isolation PASS” không?

*Đáp án:* không; cần positive control với dịch vụ khỏe và PEP deny logs.

### Bài 18 — Credential theft

Endpoint đã cô lập mạng nhưng attacker có thể đã lấy API token và đang sử dụng từ máy khác. Cô lập endpoint có đủ không?

*Gợi ý:* không. Cần triage credentials, revoke/rotate theo risk, rà sessions/API logs, tìm persistence và các asset liên quan.

### Bài 19 — Pod tự bị thay thế

Một Kubernetes Pod nghi bị xâm nhập tự restart và bị Deployment thay bằng Pod UID mới. Những evidence nào có thể đã mất?

*Gợi ý:* volatile memory, old Pod network namespace, writable layer/logs theo retention, runtime state. Thu orchestration/EDR/CNI/central logs và image digest/old UID trước khi lifecycle xóa khi có thể.

### Bài 20 — Thiết kế tổng hợp

Một doanh nghiệp có laptop EDR, Linux VM cloud hai NIC, Kubernetes Pods và OT gateways. Hãy xây **4 luồng ALLOW, 6 luồng DENY**, thứ tự evidence collection, cách xác minh containment và quy trình release cho một incident giả định.

*Gợi ý:* ALLOW authorized EDR management, forensic evidence transfer, healthy business client→replica, OOB recovery; DENY suspect endpoint→Internet, lateral SMB/RDP, API/admin, alternate IPv6 route, unapproved Pod→DB, direct VPN bypass. Ràng buộc từng luồng với đúng PEP, asset ID, UTC, credential controls, evidence IDs, safety owner và positive/negative tests.

## 28. Checklist cô lập endpoint và bảo toàn bằng chứng

### 28.1. Triage và quyết định ban đầu

- [ ] Có **incident ID, asset owner, incident commander và quyền xử lý** rõ ràng.
- [ ] Endpoint được nhận dạng qua **EDR/cloud/VM/Pod UID, asset ID, host và network mapping theo thời gian**, không chỉ IP.
- [ ] Đã phân loại **mức độ thiệt hại đang diễn ra**, phạm vi lây lan và tác động đến an toàn/sản xuất.
- [ ] Đã xác định việc trì hoãn để thu RAM có chấp nhận được không; nếu không, chọn containment khẩn cấp phù hợp.
- [ ] Có người chịu trách nhiệm **forensic collection, network/cloud enforcement, service owner và pháp lý/privacy** khi cần.
- [ ] Đã xác định management/OOB recovery và nguy cơ tự cắt kênh thu thập.
- [ ] Mọi quyết định và thời điểm UTC được ghi nhận, kể cả hành động khẩn cấp có hậu kiểm.

### 28.2. Kiểm soát các đường mạng

- [ ] Xác định **đúng PEP**: EDR, NAC, switch, firewall, cloud NIC, CNI hoặc host firewall.
- [ ] Xét **ingress, egress, lateral traffic** và cả existing TCP/QUIC sessions.
- [ ] Xét **IPv4/IPv6, wired/Wi-Fi, VPN, cellular, VLAN, virtual bridge, multiple NICs và proxy routes**.
- [ ] EDR containment có **agent acknowledgement và effective network evidence**, không chỉ queued/sent.
- [ ] Các ngoại lệ EDR/forensic management **hẹp, đúng nguồn/đích và đã được phê duyệt**.
- [ ] Cloud SG/NSG/firewall targeting dựa **instance/NIC IDs, route và provider semantics**.
- [ ] NAC/switch targeting đã kiểm tra **port topology và downstream devices**.
- [ ] Với Kubernetes, đã xác minh **CNI enforcement, toàn bộ NetworkPolicies cộng dồn, Pod UID và hostNetwork exceptions**.
- [ ] Với OT/safety devices, hành động tuân theo **owner/vendor/safety playbook**.
- [ ] Không mở rộng ACL cả subnet/VPC nếu chỉ muốn cô lập một endpoint.

### 28.3. Volatile evidence và acquisition

- [ ] Đã bảo toàn **EDR alerts/process tree và central SIEM/DNS/firewall/VPN/IAM/cloud logs**.
- [ ] Các nguồn log có nguy cơ rotate/hết retention được xử lý theo policy.
- [ ] Đã cân nhắc **RAM, process tree, user sessions, network sockets, routes/ARP/NDP, credentials in memory và ephemeral artifacts** theo rủi ro.
- [ ] Mỗi công cụ live response có **tên, version, operator, UTC time, command và known impact**.
- [ ] Không gọi lệnh chỉ đọc là **không gây thay đổi tuyệt đối**.
- [ ] Không reboot/shutdown/kill process/cleanup/reimage trước khi quyết định preservation theo risk.
- [ ] Memory/disk acquisition được thực hiện bởi người có **thẩm quyền và công cụ phù hợp**, với giới hạn được ghi.
- [ ] Disk/volume snapshots có **source identity, volume map, consistency, encryption/KMS context và IDs**.
- [ ] Pod/container ephemeral logs, writable layer và runtime metadata được xử lý trước lifecycle deletion khi có thể.
- [ ] Chứng cứ không thể thu được đã được **nêu rõ lý do và độ không chắc chắn**.

### 28.4. Tính toàn vẹn, timeline và quyền riêng tư

- [ ] Evidence master/working copies tách biệt; original được bảo vệ read-only/immutable khi khả thi.
- [ ] Có **evidence ID, byte size, SHA-256, tool method/version và storage location** cho artifacts được thu.
- [ ] Chain of custody theo dõi **collector, transfers, recipients, UTC timestamps và mục đích truy cập**.
- [ ] Giữ **original timestamps**, chuẩn hóa UTC và ghi clock skew/uncertainty.
- [ ] Timeline phân biệt **observed facts, correlations, inference và confidence**.
- [ ] Raw RAM dumps/PCAP/disk images được **mã hóa, giới hạn quyền và không phát tán qua public channels**.
- [ ] Quy định dữ liệu cá nhân, retention, legal hold và privacy được tuân thủ.
- [ ] Evidence không bị chèn vào cùng kho backup/log mà suspected identity vẫn có toàn quyền xóa/sửa.

### 28.5. Kiểm thử và kết luận containment

- [ ] Có **positive control** chứng minh service/healthy source vẫn hoạt động đúng.
- [ ] Có **negative tests** cho egress Internet, lateral movement, inbound unauthorized và alternate paths.
- [ ] Ghi **PEP/policy/action ID, applied time, actual allow/deny logs**; không chỉ suy từ timeout.
- [ ] Đã xét EDR offline, cloud stateful connections, NAT và network capture placement.
- [ ] Các kết quả thiếu chứng cứ được đánh dấu **INCONCLUSIVE**, không tạo báo cáo PASS giả.
- [ ] Hành động containment không gây gián đoạn các tài sản khác ngoài dự kiến hoặc có escalation nếu có.
- [ ] Có owner và kế hoạch cho **credential revocation, account/role abuse, persistence và lateral scope**.

### 28.6. Phục hồi, release và cải tiến

- [ ] Chỉ release khi có **approval, risk assessment và eradication/rebuild decision** phù hợp.
- [ ] EDR, audit, MFA/IAM, TLS và endpoint security baseline đã khôi phục.
- [ ] Sau mở mạng, legitimate flows hoạt động; **unauthorized flows vẫn bị deny**.
- [ ] Có canary, monitoring window, rollback và phương án tái cô lập.
- [ ] Incident report ghi timeline **detection → decision → applied containment → validation → recovery**.
- [ ] Evidence IDs, hashes, chain of custody và giới hạn điều tra được bàn giao.
- [ ] Lessons learned có owner, hạn xử lý và kiểm tra lại coverage của EDR/NAC/firewall/telemetry.

**Kết luận:** cô lập endpoint có hiệu quả khi ta xác định đúng tài sản, chọn đúng điểm kiểm soát mạng, chặn được những đường gây hại và **chứng minh bằng quan sát độc lập**. Bảo toàn bằng chứng có hiệu quả khi ta ghi lại quá trình ra quyết định, thu thập những dữ liệu dễ mất theo rủi ro, giữ các nguồn log bên ngoài host, bảo vệ dữ liệu bằng **hash/chain of custody/timeline** và không làm sạch hệ thống trước lúc điều tra cần thiết. Hai mục tiêu này phải được thực hiện **đồng thời, có phê duyệt và có kế hoạch phục hồi**, thay vì coi “rút dây mạng” hoặc “copy một file log” là đã hoàn thành ứng phó sự cố.

### Tài liệu tham khảo và đọc thêm

- [NIST SP 800-61 Rev. 3 — Incident Response Recommendations and Considerations for Cybersecurity Risk Management](https://csrc.nist.gov/pubs/sp/800/61/r3/final): tổ chức ứng phó sự cố và kết nối với quản trị rủi ro.
- [NIST SP 800-86 — Guide to Integrating Forensic Techniques into Incident Response](https://csrc.nist.gov/pubs/sp/800/86/final): thu thập, phân tích và xử lý chứng cứ số trong IR.
- [NIST SP 800-92 — Guide to Computer Security Log Management](https://csrc.nist.gov/pubs/sp/800/92/final): vận hành, thu thập và bảo vệ logs.
- [NIST SP 800-184 — Guide for Cybersecurity Event Recovery](https://csrc.nist.gov/pubs/sp/800/184/final): chuẩn bị và tổ chức phục hồi sau sự cố.
- [NIST SP 800-137 — Information Security Continuous Monitoring](https://csrc.nist.gov/pubs/sp/800/137/final): quan sát liên tục để hỗ trợ quyết định theo rủi ro.
- [RFC 3227 — Guidelines for Evidence Collection and Archiving](https://www.rfc-editor.org/rfc/rfc3227): nguyên tắc thu thập/bảo quản, gồm order of volatility; sử dụng như tài liệu lịch sử và đặt trong bối cảnh công nghệ mới.
- [CISA — Federal Government Cybersecurity Incident and Vulnerability Response Playbooks](https://www.cisa.gov/resources-tools/resources/federal-government-cybersecurity-incident-and-vulnerability-response-playbooks): tài liệu mẫu cho incident response orchestration và decision logging.
- [CISA — StopRansomware Guide](https://www.cisa.gov/stopransomware/ransomware-guide): containment, preservation và recovery trong tình huống ransomware.
- [Kubernetes — Network Policies](https://kubernetes.io/docs/concepts/services-networking/network-policies/): semantics của ingress/egress policy và khả năng enforce phụ thuộc CNI.
- [Kubernetes — Auditing](https://kubernetes.io/docs/tasks/debug/debug-cluster/audit/): giữ sự kiện API khi điều tra workload/container.
- [Prometheus — Monitoring basics](https://prometheus.io/docs/introduction/overview/): metrics/alerting hỗ trợ xác minh dịch vụ và telemetry health.
- [OpenTelemetry — Logs](https://opentelemetry.io/docs/concepts/signals/logs/): ngữ nghĩa logs và tương quan observations.
- [RFC 7011 — IP Flow Information Export (IPFIX)](https://www.rfc-editor.org/rfc/rfc7011): cấu trúc và vận chuyển flow records.
- [RFC 8446 — TLS 1.3](https://www.rfc-editor.org/rfc/rfc8446): bảo vệ transport và hạn chế khả năng đọc payload từ PCAP.
- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): event logging, data minimization và bảo mật log.
- [OWASP — Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html): bảo vệ tokens, keys, credentials có thể xuất hiện trong evidence.
