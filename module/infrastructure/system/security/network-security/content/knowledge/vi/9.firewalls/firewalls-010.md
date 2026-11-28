# Firewall logging: ghi nhận, đọc hiểu và khai thác nhật ký tường lửa

**Firewall logging** là quá trình ghi các sự kiện mà tường lửa xử lý hoặc quan sát: lưu lượng được phép, lưu lượng bị từ chối, trạng thái phiên, cảnh báo mối đe dọa, thay đổi cấu hình và lỗi vận hành. Dữ liệu này giúp trả lời: **“Nguồn nào liên lạc với đích nào, bằng giao thức và cổng gì, tại thời điểm nào, khớp rule nào, firewall đã làm gì và bằng chứng đó đáng tin đến đâu?”**

Trong chương **Firewall** của học phần **SECURITY_NETWORK_SECURITY**, logging nối chính sách mạng với việc xác minh hiệu lực, phân tích lưu lượng, mô hình hóa mối đe dọa, giám sát xâm nhập và xử lý sự cố. Một hệ thống có phân đoạn, firewall, VPN, IDS/IPS, NAC, DNS, Wi-Fi và cloud vẫn khó vận hành an toàn nếu người quản trị không biết những luồng nào được cho phép, những luồng nào bị chặn và vì sao.

Bài này trình bày cách thiết kế log, đọc đúng từng trường, hiểu mối quan hệ giữa log với NAT và connection tracking, thu thập tập trung, phân tích bất thường, bảo vệ dữ liệu và kiểm chứng kiểm soát mạng. **Firewall log là dữ kiện do một điểm quan sát ghi lại; nó không tự xác nhận danh tính người dùng hoặc chứng minh một cuộc tấn công đã thành công.**

## 1. Firewall logging giải quyết vấn đề gì?

Những mục tiêu phổ biến:

| Mục đích | Câu hỏi cần trả lời | Ví dụ |
|---|---|---|
| Kiểm chứng policy | Một rule có thực sự chặn hoặc cho phép đúng luồng không? | Guest → DB TCP/5432 bị từ chối |
| Xử lý sự cố | Kết nối lỗi ở firewall, routing, server hay ứng dụng? | User VPN không vào được HTTPS nội bộ |
| Phát hiện bất thường | Có nguồn thử nhiều đích/cổng hoặc traffic tăng đột ngột? | Deny từ một host tới nhiều cổng quản trị |
| Điều tra | Một host bị nghi nhiễm mã độc đã liên lạc với những đâu? | Kết hợp flow của host với DNS và EDR |
| Kiểm toán | Ai thay đổi rule, lúc nào, giá trị nào được thêm/bỏ? | Mở TCP/22 ngoài lịch bảo trì |
| Tối ưu ACL | Rule có hit không, có trùng hoặc phạm vi quá rộng? | Rule allow-any không có owner |
| Sức khỏe vận hành | Thiết bị có phát log, collector còn hoạt động không? | Buffer đầy hoặc syslog gửi thất bại |

**Có log không có nghĩa firewall đang thực thi đúng.** Một log deny cho thấy thiết bị đã từ chối gói/phiên được ghi nhận tại điểm đó; có thể tồn tại đường đi khác hoặc một hệ thống nằm ngoài phạm vi firewall.

### 1.1. Phân biệt firewall log với log khác

- **Firewall traffic log:** ghi luồng và quyết định allow/deny hoặc trạng thái phiên.
- **Firewall threat/IPS log:** ghi đánh giá signature, hành vi, mức cảnh báo và action của chức năng bảo mật.
- **Flow log:** mô tả nguồn, đích, protocol, bytes, packets và trạng thái theo mức thu thập; không phải lúc nào cũng là log của một rule firewall chuyên dụng.
- **Packet capture (PCAP):** chứa packet/frame tại điểm capture, có thể sâu hơn nhưng nhiều dữ liệu và nguy cơ riêng tư hơn.
- **Proxy/application log:** có thể ghi HTTP request, response status, account, chức năng ứng dụng và thông tin sau TLS termination.
- **Identity/VPN/DNS log:** bổ sung user, phiên VPN và tên miền truy vấn, không thay thế firewall log.

Ví dụ, **TCP/443 allow** không có nghĩa API đã trả HTTP 200 hay người gọi được cấp quyền. Firewall có thể cho phép kết nối đến reverse proxy, còn proxy hoặc ứng dụng tiếp tục kiểm tra TLS, tài khoản và quyền.

## 2. Những nhóm sự kiện firewall thường ghi

| Nhóm | Trường dữ liệu có thể có | Ý nghĩa |
|---|---|---|
| Traffic/session | 5-tuple, action, rule, bytes, duration, session ID | Luồng kết nối và policy đã match |
| Deny/drop/reject | Gói/luồng bị loại, policy, lý do | Kiểm chứng phân đoạn, phát hiện truy cập sai |
| Threat/IPS | Signature, category, severity, alert/block/reset | Phân tích hành vi hoặc nội dung nghi vấn |
| Application/URL filtering | App nhận diện, domain, loại URL, verdict | Quy tắc theo lớp 7 nếu thiết bị hỗ trợ |
| NAT/translation | IP và port trước/sau NAT, translation ID | Truy nguồn/đích qua mạng dịch địa chỉ |
| VPN/authentication | Login, tunnel start/end, user/device, kết quả | Liên kết địa chỉ tunnel với identity |
| Configuration/audit | Actor, rule change, commit, version | Điều tra thay đổi control plane |
| System/health | Failover HA, reboot, resource, logging errors | Đánh giá tính đầy đủ của log |
| DNS/security service | Tên miền và kết quả lọc nếu có tính năng | Bổ sung ngữ cảnh cho luồng truy cập |

Không phải firewall nào cũng có tất cả loại log. Một số chỉ ghi sự kiện **deny**, một số ghi **allow** theo session kết thúc, một số cho phép chọn chỉ ghi những rule trọng yếu. Cần biết chính xác **cấu hình logging đang bật** trước khi suy luận từ sự có hoặc không có event.

### 2.1. Action khác với severity

**Action** mô tả việc firewall thực hiện, ví dụ:

- **allow/accept:** cho traffic đi qua theo policy tại điểm kiểm soát.
- **deny/drop:** từ chối, có thể không phản hồi gì cho nguồn.
- **reject/reset:** từ chối và gửi phản hồi lỗi hoặc TCP reset nếu cấu hình/thiết bị cho phép.
- **alert:** ghi nhận nghi vấn nhưng chưa chắc chặn.
- **block/quarantine:** hành động ngăn hoặc cô lập khi tính năng IPS/NAC hỗ trợ.

**Severity** thể hiện mức đánh giá sự kiện của vendor hoặc hệ thống phân tích. Một threat có severity cao nhưng action là **alert** chưa chắc đã bị chặn; một deny do default policy có thể chỉ là thông tin vận hành bình thường.

### 2.2. Thời điểm ghi trong vòng đời kết nối

~~~text
Client              Stateful firewall               Server
  |---- TCP SYN ---------->|                             |
  |                       |  match policy, tạo state    |
  |                       |  session start log?        |
  |                       |---- SYN ------------------->|
  |<---------------------- SYN-ACK ----------------------|
  |---- ACK / data -------->|--------------------------->|
  |                       |  bytes, packets, duration  |
  |                       |  session end log?          |
~~~

Một firewall có thể ghi **start**, **end**, cả hai hoặc chỉ những event bất thường. Nếu chỉ ghi session end, log có thể xuất hiện nhiều phút/giờ sau khi kết nối bắt đầu. Nếu session kết thúc do mất điện hoặc failover, có thể thiếu bản ghi end tùy thiết bị.

Không nên coi số bản ghi traffic là số packet. Một session có thể trao đổi hàng triệu packet nhưng tạo một log tổng hợp; ngược lại một số thiết bị có thể log nhiều packet deny liên tiếp.

## 3. Những trường phải biết khi đọc firewall log

| Trường | Ví dụ | Cách hiểu |
|---|---|---|
| event_time | 2026-11-28T05:00:00Z | Thời điểm xảy ra theo nguồn, cần timezone |
| device_id | fw-internal-01 | Thiết bị hoặc instance tạo sự kiện |
| event_type | traffic_end | Giai đoạn hoặc loại sự kiện |
| source_ip | 10.20.50.27 | IP nguồn tại điểm log |
| source_port | 52314 | TCP/UDP source port |
| destination_ip | 10.20.30.15 | IP đích tại điểm log |
| destination_port | 5432 | TCP/UDP destination port |
| protocol | tcp | Giao thức vận chuyển |
| source_zone | guest | Vùng/zone phía nguồn theo cấu hình |
| destination_zone | data | Vùng/zone đích theo cấu hình |
| direction/interface | ingress / vlan50 | Hướng và interface theo quy ước thiết bị |
| action | deny | Quyết định cuối cùng hoặc event action |
| rule_id | GUEST-DATA-DENY | Quy tắc được match |
| session_id | s-12345 | Dấu liên kết các log phiên nếu hỗ trợ |
| bytes/packets | 240 / 4 | Chỉ số có thể một/hoặc hai chiều |
| duration | 350ms | Thời lượng nếu đã xác định session |
| reason | policy-deny | Lý do do thiết bị báo cáo |
| nat fields | translated_ip/port | Ánh xạ trước/sau NAT nếu được ghi |
| identity | vpn-user-123 | Identity được tích hợp từ nguồn khác |

**5-tuple** là bộ (source IP, source port, destination IP, destination port, protocol). Với TCP/UDP, hai port là hai trường khác nhau; **source port 52314** của client không phải port dịch vụ 5432 của DB. Với ICMP/ICMPv6 không có port TCP/UDP, thường cần ICMP type/code.

### 3.1. Ví dụ firewall event chuẩn hóa

Dữ liệu dưới đây là **minh họa**, không phải log từ hệ thống thật hay một schema bắt buộc của vendor.

~~~json
{
  "event_time": "2026-11-28T05:00:00Z",
  "ingest_time": "2026-11-28T05:00:01Z",
  "event_type": "traffic",
  "device_id": "fw-internal-01",
  "source": {
    "ip": "10.20.50.27",
    "port": 52314,
    "zone": "guest"
  },
  "destination": {
    "ip": "10.20.30.15",
    "port": 5432,
    "zone": "data"
  },
  "network": {
    "transport": "tcp",
    "direction": "ingress"
  },
  "rule": {
    "id": "GUEST-DATA-DENY",
    "version": "2026-11-27"
  },
  "event": {
    "action": "deny",
    "reason": "policy-deny",
    "severity": "informational"
  }
}
~~~

Đọc đúng: tại **fw-internal-01**, traffic TCP từ Guest 10.20.50.27:52314 đến Data 10.20.30.15:5432 bị **deny** theo rule. Chưa đủ để kết luận nguồn là kẻ tấn công, endpoint đích bị xâm nhập, hoặc không tồn tại tuyến truy cập khác.

**Chuẩn hóa log không được làm mất dữ liệu gốc.** Tên trường của mỗi nhà sản xuất, NAT tuple, rule UUID, threat metadata hoặc session termination reason có thể rất quan trọng khi điều tra. Nên lưu original event hoặc tham chiếu đáng tin tới bản gốc.

### 3.2. Source IP không đồng nhất với danh tính

- DHCP có thể gán lại IP cho máy khác.
- NAT/proxy có thể cho nhiều user dùng chung IP.
- VPN cấp IP động theo phiên, thay đổi mỗi lần kết nối.
- Pod/VM/cloud workload có thể bị thay thế và đổi IP.
- MAC có thể bị thay đổi hoặc ngẫu nhiên hóa.

Để gắn event với người/thiết bị, cần đối chiếu **DHCP lease, VPN session, 802.1X/RADIUS/NAC, AP association, EDR/host inventory, cloud identity hoặc ứng dụng** theo cùng khoảng thời gian. Không suy luận danh tính chỉ từ IP nguồn.

## 4. Stateful connection tracking và ý nghĩa trong log

**Stateful firewall** thường theo dõi trạng thái phiên: khi kết nối mới được phép, phản hồi hợp lệ có thể được cho đi qua theo session table. Thiết bị có thể log ở mức **session summary**, thay vì từng gói.

~~~text
App 10.20.20.21:52011 ---> DB 10.20.30.15:5432   TCP SYN
DB  10.20.30.15:5432 ---> App 10.20.20.21:52011  TCP SYN-ACK

Ví dụ session summary:
session_id=abc123 src=10.20.20.21 sport=52011
dst=10.20.30.15 dport=5432 proto=tcp
rule=APP-DB-ALLOW action=allow
bytes_client_to_server=1200 bytes_server_to_client=5200
duration_ms=1800 end_reason=tcp-fin
~~~

Một session log **allow** không đủ chứng minh dịch vụ DB cho phép user truy vấn dữ liệu. Nó chỉ phản ánh việc firewall xử lý luồng trong phạm vi quan sát của mình.

**Stateless ACL** đánh giá gói riêng lẻ; luồng chiều về có thể match một rule khác. Nếu truy vấn yêu cầu điều tra chiều phản hồi, cần xem trường hướng, source/destination đảo lại, NAT và ephemeral ports. Một gói ICMP lỗi có thể liên quan đến traffic TCP/UDP ban đầu, nhưng vẫn cần đối chiếu protocol/type/code.

### 4.1. Phân biệt log start với end

| Chỉ báo | Start log | End log |
|---|---|---|
| Thời điểm | Gần lúc mở/cho thử kết nối | Khi đóng, timeout hoặc kết thúc phiên |
| Thông tin bytes/duration | Có thể chưa hoàn chỉnh | Thường đầy đủ hơn nếu thiết bị hỗ trợ |
| Kết luận | Đã có quyết định ban đầu | Có tổng kết traffic được quan sát |
| Giới hạn | Không khẳng định bắt tay/ứng dụng đã thành công | Có thể thiếu nếu phiên mất đột ngột, sampling hoặc lỗi logging |

Vì vậy một phép tìm kiếm chỉ dựa vào **event_time trong 1 phút** có thể bỏ sót những phiên bắt đầu trong khoảng đó nhưng log được phát sau nhiều giờ.

## 5. NAT, proxy và load balancer làm đổi cách đọc log

Giả sử có đường:

~~~text
Client Internet 198.51.100.24:51234
          |
          v
Public VIP 203.0.113.10:443
          |
      DNAT / proxy
          |
          v
Backend 10.20.20.10:8443
~~~

Trong một số thiết bị firewall, log có thể ghi cặp địa chỉ/cổng **trước NAT**, **sau NAT**, hoặc cả hai. Nếu có SNAT, địa chỉ nguồn/backend nhìn thấy cũng có thể khác client.

| Điểm nhìn | Source | Destination |
|---|---|---|
| Trước DNAT | 198.51.100.24:51234 | 203.0.113.10:443 |
| Sau DNAT, chưa SNAT | 198.51.100.24:51234 | 10.20.20.10:8443 |
| Sau SNAT nếu có | IP/port đã dịch | Backend thực tế |
| Sau reverse proxy | Proxy IP/port mới | Backend theo upstream của proxy |

Các dải **198.51.100.0/24** và **203.0.113.0/24** được dành cho tài liệu, không phải endpoint thật. Điểm quan trọng là firewall log phải được diễn giải theo **thứ tự NAT/filter và điểm ghi thực tế của sản phẩm**; không thể đưa ra một thứ tự mặc định đúng cho mọi nền tảng.

Với nhiều client cùng chia sẻ IP công cộng, việc truy vết đúng đôi khi cần **timestamp chính xác, source port và NAT translation/session ID**. Nếu chỉ thấy IP công cộng, chưa thể xác định một người cụ thể.

### 5.1. Hostname không nhất thiết xuất hiện trong firewall log

DNS có thể trỏ một hostname đến nhiều IP hoặc CDN; nhiều hostname có thể dùng chung VIP, reverse proxy hoặc load balancer. Firewall L3/L4 chỉ nhìn thấy IP/port thường không đủ để biết **tên miền hoặc URL** người dùng truy cập.

Khi cần tên dịch vụ, đối chiếu resolver logs, DNS response, proxy logs hoặc log điểm kết thúc TLS trong phạm vi được cấp phép. SNI trong TLS có thể hiện diện nhưng không phải lúc nào cũng đọc được, nhất là khi tính năng bảo mật bổ sung như ECH được triển khai.

## 6. Logging pipeline: từ firewall đến SIEM

Một hệ thống trung tâm thường nhận sự kiện từ firewall biên, firewall nội bộ, host firewall, cloud policy và các hệ thống liên quan.

~~~mermaid
flowchart TD
    E[Edge firewall] --> C[Log collector]
    I[Internal firewall] --> C
    H[Host/Cloud firewall] --> C
    C --> P[Parse + normalize + enrich]
    P --> S[(Lưu trữ / index)]
    S --> SIEM[SIEM query + correlation]
    SIEM --> SOC[Cảnh báo / điều tra]
    S --> A[Retention / archive / audit]
~~~

### 6.1. Các bước thiết kế pipeline

1. **Emit:** xác định mỗi firewall tạo traffic, deny, threat, audit và health log nào. Kiểm tra implicit deny và session-end logging có được bật không.
2. **Transport:** chuyển log bằng syslog, agent, API hoặc cloud event stream theo cách nền tảng hỗ trợ; kiểm soát nguồn gửi và mã hóa khi cần.
3. **Buffer và retry:** xử lý collector không sẵn sàng, mạng gián đoạn, queue đầy và backpressure; có cơ chế cảnh báo mất log.
4. **Parse:** tách timestamp, IP, port, zone, action, session và rule ID theo format đúng phiên bản.
5. **Normalize:** ánh xạ thành trường chung để tìm kiếm nhiều vendor; bảo tồn original event.
6. **Enrich:** thêm asset owner, classification, IP→host mapping hoặc thông tin identity hợp lệ với **mốc thời gian của event**.
7. **Store/index:** lưu và tìm kiếm với phân quyền, retention và khả năng khôi phục.
8. **Correlate/alert:** ghép các event cùng luồng, cùng tài sản hoặc cùng khoảng thời gian để phát hiện hành vi cần điều tra.
9. **Audit pipeline:** giám sát độ trễ, parser lỗi, nguồn không gửi log và truy cập dữ liệu log.

**Gửi log thành công không đồng nghĩa log đã tìm được trong SIEM.** Cần thử end-to-end từ một sự kiện xác định đến bản ghi có thể truy vấn, kiểm tra quá trình ingest, parser, enrichment, index và retention.

### 6.2. Syslog, JSON, CEF và vendor formats

Syslog là một cách phổ biến để chuyển log thiết bị mạng; message có thể chứa **timestamp, hostname, facility, severity** và phần nội dung tùy nhà sản xuất. Một số hệ thống dùng **CEF, LEEF, JSON** hoặc format riêng.

- Syslog qua **UDP** đơn giản có thể mất gói khi nghẽn, không có xác nhận end-to-end.
- **TCP** hỗ trợ truyền có kết nối nhưng không loại bỏ nguy cơ mất log nếu hàng đợi tràn, dịch vụ lỗi hoặc log chưa được ghi xuống kho.
- **TLS** khi được triển khai đúng bảo vệ dữ liệu trên đường truyền giữa các điểm tham gia; không thay thế phân quyền sau khi collector nhận log.
- **Syslog severity** là mức của bên phát, **không tự tương đương** với threat severity của IPS.
- Parser có thể không hỗ trợ bản firmware/log format mới; nên có kiểm tra schema và lưu bản gốc khi parse lỗi.

### 6.3. Các chỉ số chất lượng logging

| Chỉ số | Ý nghĩa | Cần làm gì khi bất thường |
|---|---|---|
| Devices reporting | Tỷ lệ firewall gửi log theo kỳ vọng | Kiểm tra agent, network, cấu hình logging |
| EPS (events/second) | Lượng sự kiện theo nguồn/loại | Phát hiện spike, phân loại thay đổi traffic |
| Ingest latency | Khoảng cách event time tới ingest time | Kiểm tra buffer, queue, index lag |
| Parse failure | Event không nhận diện được schema | Sửa parser hoặc cập nhật format |
| Dropped/buffered events | Log có thể bị mất | Tăng năng lực pipeline, cảnh báo và review sampling |
| Missing fields | Rule ID, action, 5-tuple thiếu | Xem cấu hình nguồn và mapping |
| Time drift | Đồng hồ các nguồn lệch nhau | Kiểm tra NTP và cấu hình timezone |
| Storage/retention | Không đủ dung lượng hoặc thời gian giữ | Cân đối policy, quyền và chi phí |
| Coverage | Bao nhiêu zone/luồng có log hữu ích | Kiểm chứng những điểm mù trên sơ đồ mạng |

Nếu logging được **sample hoặc aggregate**, không được coi số bản ghi là tổng số kết nối thật. Với một số tính toán có thể cần công thức hiệu chỉnh theo tỷ lệ lấy mẫu, nhưng chỉ khi hiểu rõ cách thiết bị lấy mẫu.

## 7. Timestamp và dựng timeline điều tra

Thông thường có ít nhất bốn mốc:

- **Event time:** thời điểm thiết bị báo rằng sự kiện xảy ra.
- **Session start/end:** mốc đầu/cuối của phiên nếu format có.
- **Ingest time:** lúc collector nhận bản ghi.
- **Index time:** lúc bản ghi có thể tìm thấy qua hệ thống truy vấn.

Nên chuẩn hóa thời gian pipeline về **UTC**, giữ thông tin offset gốc nếu có. Ví dụ **2026-11-28T05:00:00Z** tương ứng **12:00 ngày 28/11/2026 tại UTC+7**. Không lưu chỉ chuỗi “12:00” thiếu múi giờ.

### 7.1. Vì sao đồng hồ lệch gây kết luận sai?

Giả sử firewall ghi kết nối vào 10:00 và VPN gateway có đồng hồ nhanh hơn 6 phút nên ghi login vào 10:06, dù thực tế VPN authentication đã xảy ra ngay trước kết nối. Nếu dùng timestamp không hiệu chỉnh, báo cáo có thể khẳng định user kết nối trước khi đăng nhập.

Cần theo dõi NTP/time sync, ghi **độ lệch được biết**, phân biệt event time với ingest time và khi dựng timeline nên gắn **mức tin cậy** cho từng nguồn.

### 7.2. Session log có thể đến muộn

Một kết nối kéo dài 2 giờ, session end log chỉ xuất hiện khi kết thúc. Truy vấn SIEM chỉ theo khoảng **event time** của lúc bắt đầu có thể không thấy log nếu event_time lấy lúc end. Cần hiểu field nào là session start và field nào là end, cùng time window và ingest delay.

## 8. Đọc một deny event theo sáu bước

Bản ghi **giả định**:

~~~text
time=2026-11-28T05:00:00Z device=fw-segmentation-01
src=10.20.50.27 sport=52314 src_zone=guest
dst=10.20.30.15 dport=5432 dst_zone=database
proto=tcp action=deny rule=GUEST-TO-DATA-DENY
type=traffic direction=ingress
~~~

**Bước 1 — Kiểm tra nguồn:** thiết bị nào phát event; nó có nằm trên đường Guest → DB? Có bằng chứng logging hoạt động ở thời điểm này không?

**Bước 2 — Đọc 5-tuple:** guest **10.20.50.27:52314** đến **10.20.30.15:5432** bằng TCP. Destination port 5432 thường dùng PostgreSQL nhưng chưa chứng minh dịch vụ thật sự chạy PostgreSQL.

**Bước 3 — Đọc action:** **deny** là quyết định tại firewall; không tự đồng nghĩa với threat alert. Hành vi drop/reject/reset chi tiết phụ thuộc vendor và rule.

**Bước 4 — Đối chiếu policy:** kiểm tra rule GUEST-TO-DATA-DENY, zone, phiên bản cấu hình, ưu tiên và NAT tuple ở mốc thời gian đó.

**Bước 5 — Tìm ngữ cảnh:** guest IP thuộc thiết bị nào lúc ấy? Là request do phần mềm hợp lệ, scanner đã phê duyệt, dịch vụ cấu hình sai hay một chuỗi hành vi nghi vấn? Có deny tới nhiều đích/port khác không?

**Bước 6 — Kết luận có giới hạn:** “Firewall ghi nhận và từ chối lưu lượng TCP guest → DB theo policy X”. Để kết luận có hành vi ác ý hoặc xâm nhập, cần bằng chứng bổ sung từ endpoint, VPN/NAC, DNS và ứng dụng.

### 8.1. Đọc allow event đúng phạm vi

~~~text
time=2026-11-28T05:05:00Z device=fw-segmentation-01
src=10.20.20.21 sport=52011 src_zone=app
dst=10.20.30.15 dport=5432 dst_zone=data
proto=tcp action=allow rule=APP-DB-ALLOW
session_id=abc123
~~~

Có thể kết luận firewall **đã cho luồng App → DB** theo policy ở thời điểm quan sát. Không thể kết luận chỉ từ đó rằng:

- TCP handshake thành công nếu là session-start event.
- Mọi firewall/host khác trên đường cũng allow.
- DB chấp nhận credential và truy vấn.
- Phiên không có dấu hiệu bất thường hoặc máy App chưa bị chiếm.

Để kiểm chứng nghiệp vụ cần phối hợp log DB, application, connection outcome và quyền truy cập.

## 9. Rule logging và xác minh phân đoạn mạng

Một ma trận giúp định nghĩa “đúng” trước khi đi tìm log:

| Nguồn | Đích | Traffic | Kỳ vọng | Bằng chứng nên đối chiếu |
|---|---|---|---|---|
| Staff | Web nội bộ | TCP/443 | Allow | Firewall log + web log |
| App | DB | TCP/5432 | Allow | Session log + DB audit |
| Guest | DB | TCP/5432 | Deny | Firewall deny tại ranh giới Guest/Data |
| Internet | SSH quản trị | TCP/22 | Deny | Firewall biên/host log |
| VPN admin | Jump host | TCP/22 | Allow theo role | VPN session + firewall + SSH auth |
| App | DNS resolver nội bộ | UDP/53, TCP/53 | Allow theo dependency | Firewall + DNS resolver log |
| Host không thuộc danh sách | Secret service | Luồng ngoài policy | Deny | Distributed/host firewall log |

Không thể chỉ thấy **allow** rồi kết luận toàn bộ hệ thống an toàn. Một flow có thể được firewall A cho phép và bị firewall B chặn; hoặc kết nối được mạng nhưng ứng dụng trả 403/401.

### 9.1. Phân biệt rule hit và rule không hoạt động

Một rule không có log trong một tuần chưa chắc thừa:

- Traffic chỉ diễn ra khi backup định kỳ hoặc failover.
- Thiết bị không bật log allow trên rule đó.
- Session dài chưa có log end.
- Một rule khác được ưu tiên trước (rule shadowing).
- Đường đi thay đổi, NAT khiến match khác dự kiến.
- Sampling hoặc mất log do pipeline.

Phải review với owner nghiệp vụ và data flow trước khi bỏ rule. Một rule được log **hit** cũng không chứng minh rule đó còn cần thiết, vì có thể traffic sai cấu hình hoặc bất thường.

### 9.2. Ordered ACL và rule che nhau

Ví dụ với firewall dùng **first match**:

~~~text
10 ALLOW ANY          -> DB TCP/5432
20 DENY  GUEST_SUBNET -> DB TCP/5432
~~~

Traffic guest có thể được allow bởi rule 10 trước khi xét rule 20. **Allow log với rule ID 10** là bằng chứng trực tiếp về policy đang bị mở rộng quá mức. Trên một số nền tảng cloud/Kubernetes, luật chọn rule có ngữ nghĩa khác; phải đọc cơ chế sản phẩm, không áp máy móc first-match.

## 10. Dùng firewall log để phát hiện bất thường

Firewall log hữu ích cho detection khi kết hợp **bối cảnh tài sản, baseline vận hành, loại trừ các hệ thống được phê duyệt và nguồn xác thực liên quan**.

| Tín hiệu | Kịch bản có thể liên quan | Cách tránh kết luận sai |
|---|---|---|
| Một nguồn thử nhiều destination port | Port scan hoặc ứng dụng lỗi | Kiểm tra asset scanner và lịch kiểm kê |
| Một nguồn thử một port trên nhiều đích | Service discovery hoặc reconnaissance | Kiểm tra source identity/owner |
| Deny đột biến tới Management | Thử truy cập trái phép hoặc đổi route | Đối chiếu VPN, NAC, deployment |
| App gọi DB lạ ngoài danh sách | Misconfiguration hoặc host đã bị chiếm | Xác minh thay đổi nghiệp vụ và IAM |
| Egress tăng đến đích chưa quen | Backup, batch hoặc chuyển dữ liệu bất thường | So sánh bytes, lịch, DNS, ứng dụng |
| Session dài/bytes lớn bất thường | Dịch vụ long-lived hoặc exfiltration nghi vấn | So baseline, log ứng dụng, host telemetry |
| Threat alert đi cùng allow | IPS chỉ cảnh báo hoặc không ở đường chặn | Xem đúng action và signature |
| Traffic mới sau rule change | Mở quyền hợp lệ hoặc sai policy | Xác minh actor, ticket, diff, scope |

### 10.1. Tương quan mẫu quét cổng

Một detector khái niệm có thể tìm:

~~~text
Cùng source identity/IP trong cửa sổ 5 phút:
  có nhiều destination port bị deny trên một host
  và vượt baseline của vùng/loại endpoint,
  và không nằm trong scope của scanner được cấp phép
=> Tạo alert điều tra
~~~

Không có ngưỡng số port hay số giây đúng cho mọi doanh nghiệp. Mạng phát triển phần mềm, mạng văn phòng và hạ tầng OT có lưu lượng khác nhau. Điều chỉnh rule theo baseline, asset criticality, lịch bảo trì và đo false positives.

### 10.2. Một số dashboard có ích

- Số allow/deny theo zone, rule, firewall và thời gian.
- Nguồn tạo deny nhiều nhất, kèm inventory/role khi xác minh được.
- Đích nhạy cảm bị thử kết nối và destination port liên quan.
- Những rule rộng có traffic, rule lâu không hit và rule vừa thay đổi.
- Thay đổi egress theo ứng dụng, DNS name và destination category.
- Cảnh báo IPS theo action thực tế.
- Log loss, parse errors, ingest lag, thiết bị ngừng gửi.

**Tăng deny không phải lúc nào là xấu.** Một rule tốt có thể chặn hàng loạt retry hoặc scan. Cần xác định điều gì đang tạo deny và kết quả nghiệp vụ có bị ảnh hưởng không.

## 11. Firewall log có những điểm mù gì?

Firewall chỉ có thể log traffic **đi qua hoặc được xử lý bởi nó**. Đây là hạn chế nền tảng của mọi phương án điều tra.

| Luồng hoặc sự kiện | Firewall biên có thấy đầy đủ? | Nguồn log bổ sung |
|---|---|---|
| Internet → public website | Thường có nếu trên đường đi | Reverse proxy, WAF, app |
| App VLAN → DB VLAN qua firewall nội bộ | Firewall nội bộ có nếu trên đường bắt buộc | DB, L3 gateway, flow logs |
| Hai máy cùng VLAN truyền trực tiếp | Thường không qua firewall biên | Host firewall, EDR, switch telemetry |
| Pod → pod cùng node | Phụ thuộc kiến trúc datapath | CNI/NetworkPolicy flow logs |
| VPN user → tài nguyên nội bộ | Phụ thuộc điểm tunnel/giải mã | VPN identity, post-VPN firewall |
| Thay đổi cloud security group | Không phải traffic data plane | Cloud audit/IAM log |
| Traffic qua private peering ngoài đường firewall | Firewall biên không thấy | VPC/VNet flow logs tại điểm phù hợp |
| TLS không được giải mã | Có thể chỉ thấy metadata | TLS termination/app logs |

### 11.1. Mã hóa và khả năng quan sát

Với TLS, mTLS, IPsec VPN hoặc MACsec, thiết bị không nắm khóa/không ở điểm giải mã thường không đọc được **payload bản rõ**. Nó vẫn có thể ghi metadata như IP, port, thời gian, số byte và một số thông tin bắt tay tùy giao thức.

Đừng mặc định firewall log chứa HTTP URL, body hoặc username khi chỉ có TCP/443. Nếu tổ chức dùng TLS inspection, phải xác định phạm vi giải mã, quản lý chứng chỉ, quyền truy cập và yêu cầu riêng tư. **TLS bảo vệ nội dung, nhưng không tự bảo đảm tính sẵn sàng của mạng**; firewall vẫn có thể thấy và chặn một số luồng bị nghẽn hoặc không được phép.

### 11.2. IPv6, NAT, Wi-Fi và đường phụ

Một rule/log IPv4 không bao phủ IPv6. Một SSID guest có thể đi qua NAT hoặc firewall khác Staff. Một IP VPN có thể được cấp cho nhiều phiên khác nhau theo thời gian. Các đường peering, network overlay, load balancer hoặc service mesh có thể đưa traffic qua những điểm kiểm soát khác.

Mọi báo cáo cần ghi **điểm quan sát** và giới hạn coverage; đừng khẳng định mọi traffic toàn mạng đều được thấy nếu chưa kiểm chứng topology.

## 12. Kết hợp firewall với các loại log khác

### 12.1. IDS/IPS

IDS nhận diện và cảnh báo theo signature/hành vi trong phạm vi sensor quan sát. IPS có thể chặn khi triển khai inline hoặc có cơ chế thực thi phù hợp. Khi một firewall allow log trùng IPS alert:

1. Kiểm tra alert severity và signature.
2. Kiểm tra **IPS action** là alert, drop, reset hay hành động khác.
3. Ghép 5-tuple, session ID, timestamp.
4. Xác minh endpoint/ứng dụng có thấy hành động tương ứng.
5. Không suy luận chỉ từ nhãn “critical” rằng đã chặn toàn bộ traffic.

### 12.2. DNS

DNS resolver log giúp liên hệ tên miền với kết quả trả về; firewall log cho biết có traffic đến IP/port. Một DNS query không chứng minh client đã mở TCP tới IP trả về; nhiều IP có thể chia sẻ hostname/CDN và DNS cache có thể làm lệch thời điểm. Với DoH/DoT, điểm quan sát DNS thay đổi; firewall L3/L4 có thể chỉ thấy HTTPS/TLS tới resolver.

### 12.3. VPN, NAC và Wi-Fi

Khi điều tra IP thuộc VPN hoặc Wi-Fi, dùng log xác thực, phiên VPN, DHCP, 802.1X/RADIUS, AP association và device inventory để xác định thiết bị/danh tính theo **thời điểm sự kiện**. MAC address có thể thay đổi và IP có thể được tái sử dụng; không nên gán một người dùng vĩnh viễn cho một IP.

### 12.4. Cloud và Kubernetes

Cloud flow log có thể báo ACCEPT/REJECT theo điểm quan sát/loại rule tương ứng, nhưng không tự đồng nghĩa với thành công của ứng dụng. Cần thêm firewall policy logs, cloud audit, VPC/VNet telemetry, load balancer, host, workload và database logs.

Kubernetes NetworkPolicy phụ thuộc plugin mạng/CNI có thực thi hay không; một policy tồn tại trong API server chưa chắc traffic bị chặn. Một số log cần lấy từ datapath của CNI, service mesh hoặc node. Audit log control plane giúp biết ai đổi label, policy hay network configuration.

## 13. Bảo mật và quyền riêng tư của firewall log

Log có thể chứa cấu trúc mạng, IP riêng, tài khoản, thông tin truy cập, hostname và đôi khi nội dung liên quan ứng dụng. Khi thiết kế cần bảo vệ log như một tài sản nhạy cảm.

**Các nguyên tắc chính:**

1. **Quyền tối thiểu:** phân quyền xem, export, sửa retention và xóa log theo vai trò; ưu tiên tách quyền quản trị firewall với quyền xóa lịch sử.
2. **Xác thực nguồn:** collector chấp nhận sự kiện từ firewall/agent đáng tin; ghi device ID và đường thu thập.
3. **Bảo vệ truyền tải:** ưu tiên transport có xác thực/mã hóa khi phù hợp; syslog UDP đơn giản có nguy cơ mất/gỉa mạo event trên đường không được bảo vệ.
4. **Bảo vệ lưu trữ:** mã hóa dữ liệu, quản lý khóa, backup và quyền truy cập.
5. **Toàn vẹn:** audit mọi hành động thay đổi/xóa, cân nhắc retention chống sửa đổi theo yêu cầu.
6. **Tối thiểu hóa dữ liệu:** tránh đưa secret, token, request body, URL chứa dữ liệu cá nhân vào trường không cần thiết.
7. **Retention xác định:** giữ log theo nhu cầu vận hành, điều tra và chính sách tổ chức; có quy trình hủy an toàn.
8. **Giám sát hệ thống log:** cảnh báo collector mất kết nối, queue tràn, parser lỗi và đồng hồ lệch.
9. **Kiểm toán truy vấn:** ghi ai tìm kiếm và xuất bản ghi nhạy cảm.
10. **Khả năng khôi phục:** thử tìm lại và đọc bản ghi cũ theo phạm vi retention được định nghĩa.

### 13.1. Cân bằng logging và hiệu năng

Ghi từng packet trên các đường truyền lớn có thể tốn lưu trữ, băng thông và tài nguyên firewall. Có thể chọn:

- Ghi **deny tại ranh giới nhạy cảm** và các rule quan trọng.
- Ghi **session summary** cho các luồng allow quan trọng.
- Ghi **threat/IPS** và **config audit** đầy đủ trong khả năng hệ thống.
- Dùng sampling/aggregation khi có lý do hiệu năng, nhưng mô tả rõ giới hạn khi thống kê.
- Phân tầng hot/warm/archive theo nhu cầu tìm kiếm.
- Định nghĩa dung lượng EPS cao điểm, retry/buffer và giới hạn mất log chấp nhận được.

**Không có cấu hình tối ưu chung.** Cần lựa chọn dựa trên dữ liệu thật, độ nhạy hệ thống và yêu cầu vận hành, đặc biệt trước các đợt DDoS hoặc thay đổi topology.

## 14. Quy trình điều tra một kết nối bị chặn

Ví dụ câu hỏi: **“Từ 09:00–09:20, vì sao App A không tới được DB B TCP/5432?”**

### Bước 1 — Xác định rõ đối tượng

Ghi source host/IP, destination host/IP, protocol/port, thời gian, timezone, zone và người báo lỗi. Nếu ứng dụng dùng hostname, ghi địa chỉ DNS được phân giải tại thời điểm lỗi.

### Bước 2 — Vẽ đường đi

Xác định switch, VLAN, router, firewall, VPN, NAT, load balancer, cloud policy và host firewall. Đặc biệt nếu hai host cùng subnet, firewall liên VLAN có thể không thấy traffic.

### Bước 3 — Tìm traffic log đúng điểm

Lọc theo 5-tuple, thời gian, rule ID/action và session/NAT ID; mở rộng cửa sổ nếu có log end/ingest trễ. Nếu không có event, kiểm tra logging được bật, loại event, đường đi, pipeline và clock trước khi kết luận không có traffic.

### Bước 4 — Xem phản hồi

Nếu có TCP SYN nhưng không thấy SYN-ACK hoặc có reset, cần đối chiếu counters, packet capture tại điểm được phép, route chiều về, state table và host listener. Không phải firewall log nào cũng chứa mọi TCP flag.

### Bước 5 — Xem ứng dụng và danh tính

Nếu firewall allow nhưng DB ghi authentication failed, trọng tâm là credential, TLS, ủy quyền DB hoặc ứng dụng, thay vì mở rộng ACL.

### Bước 6 — Ghi kết luận

Phân biệt **confirmed**, **hypothesis**, **unknown**; đính kèm timestamp, log source, rule/version, hệ quả, owner, đề xuất thay đổi và điều kiện kiểm chứng. Không mở quyền **Any → Any** để “thử cho chạy” trong production.

### Bước 7 — Kiểm chứng sau xử lý

Sau khi thay đổi đúng quy trình, thử lại luồng được phép và luồng phải bị chặn từ nguồn phù hợp, kiểm tra log và tình trạng nghiệp vụ. Cập nhật runbook hoặc detection rule nếu nguyên nhân là thiếu log hay parser sai.

## 15. Lệnh quan sát an toàn trong môi trường được quản trị

Các lệnh sau **chỉ đọc trạng thái hoặc log**. Chúng không tự bật logging, và không bảo đảm trả sự kiện nếu hệ thống chưa cấu hình ghi.

### 15.1. Linux

~~~bash
# Đọc ruleset hiện hành nếu firewall dùng nftables
sudo nft list ruleset

# Đọc sự kiện kernel gần đây được journal lưu (nếu có)
sudo journalctl -k --since "30 minutes ago"

# Nếu hệ thống dùng UFW, xem trạng thái và chính sách
sudo ufw status verbose

# Xem thông tin đồng bộ thời gian
timedatectl status
~~~

**Lưu ý:** nftables chỉ ghi những sự kiện theo cơ chế log/trace được cấu hình; một số hệ thống dùng NFLOG/ulogd, syslog file hoặc agent riêng. Không có log trong journal không chứng minh không có traffic.

### 15.2. Windows PowerShell

~~~powershell
# Trạng thái profile và chính sách ghi log
Get-NetFirewallProfile |
  Select-Object Name, Enabled, LogFileName, LogAllowed, LogBlocked

# Liệt kê một phần rule hiện có
Get-NetFirewallRule |
  Select-Object -First 20 DisplayName, Direction, Action, Enabled

# Đọc một số event Windows Filtering Platform nếu auditing đã bật
Get-WinEvent -FilterHashtable @{
  LogName = 'Security'
  Id = 5152, 5156, 5157
} -MaxEvents 20
~~~

Windows Filtering Platform audit events và file **pfirewall.log** (nếu bật) khác nhau về format và mức chi tiết. Quyền đọc Security log và audit policy quyết định có lấy được event tương ứng hay không.

### 15.3. Cloud

Dùng dịch vụ logging và công cụ truy vấn đã được tổ chức cấp quyền để xem **firewall logs, VPC/VNet flow logs, load balancer logs, cloud audit logs**. Trước truy vấn, xác minh account/project, region, scope, thời gian, retention và quy tắc bảo vệ dữ liệu.

## 16. Tình huống thực hành có đáp án

### Tình huống A — Nhiều deny từ một máy Guest

SIEM có 20 deny event từ **10.20.50.27** tới **10.20.30.15:5432** trong năm phút; rule **GUEST-DATA-DENY**.

**Câu hỏi:** đã chứng minh DB bị tấn công thành công chưa?

**Gợi ý:** chưa. Những event cho thấy firewall tại điểm quan sát đã deny các nỗ lực liên lạc tương ứng. Cần biết source là ai tại thời điểm đó, có scanner hợp lệ không, có đường thay thế không, và các log DB/endpoint/IDS có dấu hiệu khác không.

### Tình huống B — Firewall allow, ứng dụng báo authentication failed

Một event cho biết App → DB TCP/5432 **allow**, ứng dụng nhận lỗi đăng nhập.

**Câu hỏi:** nên thêm rule allow rộng hơn?

**Gợi ý:** không có căn cứ. Xem DB auth, credential, TLS, quyền tài khoản, route các chặng sau firewall và application log. Cho phép ở L3/L4 không có nghĩa người gọi được ủy quyền trong DB.

### Tình huống C — Nhiều user cùng một IP NAT

Firewall thấy IP public **198.51.100.24**. Một session bị nghi vấn trong lúc nhiều user dùng chung NAT.

**Câu hỏi:** có thể truy trách nhiệm bằng IP không?

**Gợi ý:** không đủ. Cần source port, timestamp có timezone, NAT mapping, VPN/proxy/user session logs và đối chiếu chính xác. IP public có thể đại diện nhiều máy.

### Tình huống D — Không có deny event nhưng kết nối lỗi

Ứng dụng không kết nối được server; SIEM không hiển thị deny.

**Câu hỏi:** có thể kết luận firewall đã allow?

**Gợi ý:** chưa. Có thể gói không đi qua firewall đó, implicit deny không bật logging, mất log, sampling, parser lỗi, clock lệch hoặc host firewall chặn. Phải xác minh topology và pipeline.

### Tình huống E — Chỉ có session end log

Log cho một phiên có duration 15 phút và bytes hai chiều; không có start log.

**Câu hỏi:** có phải mất log?

**Gợi ý:** không nhất thiết. Thiết bị có thể chỉ cấu hình ghi ở session end. Kiểm tra loại logging, timestamp start/end, pipeline và HA failover trước khi gọi là mất dữ liệu.

### Tình huống F — Alert port scan từ máy kiểm kê

Một nguồn thử nhiều port ở các host nhưng inventory xác nhận nguồn là scanner đang chạy công việc được phê duyệt.

**Câu hỏi:** cần loại bỏ mọi cảnh báo từ scanner?

**Gợi ý:** nên tạo ngoại lệ **hạn chế theo nguồn, phạm vi và thời gian đã cấp quyền**, sau khi xác minh job; tiếp tục cảnh báo nếu scanner chạy ngoài scope hoặc thay đổi hành vi bất thường.

### Tình huống G — Rule cloud mở rộng ngoài lịch

Audit log ghi một principal thêm security group rule **0.0.0.0/0 TCP/5432**, nhưng flow logs chưa thấy kết nối trái phép.

**Câu hỏi:** điều gì đã được xác minh?

**Gợi ý:** đã có thay đổi control plane tăng bề mặt tiếp cận. Chưa chắc DB public reachable (còn route, IP public, NACL, DB auth), cũng chưa chứng minh data exfiltration. Cần review actor/ticket/IAM, hoàn nguyên nếu sai, rà soát exposure và tiếp tục audit.

## 17. Checklist hoàn thiện firewall logging

- [ ] Liệt kê firewall/zone và xác nhận traffic nào đi qua từng điểm.
- [ ] Chọn log deny, allow/session, threat, system, VPN và config/audit phù hợp.
- [ ] Có timestamp kèm múi giờ, device ID, 5-tuple, action, rule, zone/interface nếu nền tảng hỗ trợ.
- [ ] Biết log ở session start/end, theo packet/flow hay sampling.
- [ ] Hiểu pre-NAT/post-NAT, session ID, source port và điểm đặt proxy.
- [ ] Có đồng bộ thời gian và phân biệt event time với ingest time.
- [ ] Giữ original event để giải thích các trường riêng của nhà sản xuất.
- [ ] Theo dõi log ingestion, parse errors, EPS, buffering và thiết bị ngừng gửi.
- [ ] Bảo vệ log qua transport, quyền, mã hóa, lưu trữ, retention và audit truy cập.
- [ ] Có ma trận luồng allow/deny để kiểm chứng phân đoạn và firewall rule.
- [ ] Ghép log với VPN/NAC, DNS, IDS/IPS, EDR, ứng dụng và cloud audit khi cần.
- [ ] Hiểu điểm mù cùng VLAN, cloud datapath, IPv6, route phụ và mã hóa.
- [ ] Có baseline, tuning và xử lý false positive cho cảnh báo bất thường.
- [ ] Báo cáo kết luận có giới hạn bằng chứng; không suy diễn danh tính hay exploit từ một event.
- [ ] Kiểm chứng end-to-end từ firewall đến SIEM và khả năng tìm lại sự kiện đúng retention.

## 18. Kết luận

**Firewall logging** biến chính sách bảo mật thành những dấu vết vận hành có thể kiểm tra. Giá trị của log nằm ở việc diễn giải chính xác **nguồn–đích–giao thức–port, quyết định policy, thời gian và điểm quan sát**, đồng thời hiểu giới hạn từ NAT, state tracking, TLS, cấu hình ghi log và đường đi mạng.

Khi kết hợp với **phân đoạn, VPN, NAC, DNS, IDS/IPS, endpoint, ứng dụng và cloud audit**, log firewall giúp phân tích lưu lượng, phát hiện thay đổi, điều tra xâm nhập có căn cứ, tìm nguyên nhân kết nối thất bại và duy trì kiến trúc mạng an toàn. Muốn làm được điều đó, phải thiết kế từ đầu một pipeline có coverage, chất lượng dữ liệu, khả năng tìm kiếm, kiểm soát truy cập và quy trình kiểm chứng thường xuyên.
