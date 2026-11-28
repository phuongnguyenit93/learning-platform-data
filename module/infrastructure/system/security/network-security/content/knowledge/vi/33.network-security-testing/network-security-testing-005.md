# Kiểm tra firewall rule bằng test traffic

## 1. Mục tiêu và ý nghĩa

Trong chương **Kiểm thử và xác minh bảo mật mạng** của module **SECURITY_NETWORK_SECURITY**, kỹ năng kiểm tra firewall rule bằng test traffic giúp chứng minh chính sách bảo vệ thực sự có hiệu lực. Firewall là một lớp phòng vệ bên cạnh phân đoạn VLAN/VRF, VPN, IDS/IPS, kiểm soát kết nối, bảo vệ DNS, mạng không dây và bảo mật hạ tầng cloud. Rule trông đúng trên màn hình quản trị vẫn có thể vận hành sai vì thứ tự ưu tiên, route, NAT, session còn tồn tại, sai zone, nhầm đối tượng nguồn/đích, cấu hình IPv6 khác IPv4 hoặc dịch vụ đích không hoạt động.

**Test traffic** là lưu lượng được tạo có kiểm soát từ một nguồn xác định tới một đích xác định, với giao thức/cổng, chiều, thời điểm và kỳ vọng đã được nêu trong kế hoạch. Cần kiểm chứng đồng thời:

- **Positive test:** lưu lượng được phê duyệt đi qua ranh giới an ninh và ứng dụng hoạt động đúng.
- **Negative test:** lưu lượng bị cấm thực sự bị chặn tại điểm kiểm soát dự kiến.
- **Regression test:** thay đổi rule không làm hỏng các luồng hợp lệ khác hoặc tạo ra đường truy cập ngoài ý muốn.

Một phép thử kết nối đơn lẻ không phải bằng chứng đầy đủ. Cần gắn kết quả ở client, firewall, server và hệ thống giám sát để xác định **đúng rule đã xử lý đúng luồng**.

### 1.1. Sau bài học, người học có thể

1. Phân biệt kiểm tra cấu hình, kiểm thử TCP/UDP, kiểm tra ứng dụng và xác minh bằng log/counter/packet capture.
2. Chuyển yêu cầu kiểm soát thành ma trận source, destination, zone, protocol, port, action và evidence.
3. Thiết kế positive, negative, boundary và regression test theo phạm vi có phê duyệt.
4. Dùng công cụ thích hợp: ip route, nc, curl, dig, Test-NetConnection, tcpdump và tshark trong lab.
5. Phân tích kết quả phức tạp: rule bị che khuất (shadow), stateful session, NAT, asymmetric route, DNS, TLS, IPv6 và cloud policy.
6. Ghi nhật ký kiểm thử, quyết định PASS/FAIL/INCONCLUSIVE và xử lý lỗi với rollback rõ ràng.

### 1.2. Các tầng xác minh

| Kiểm tra | Trả lời | Chứng cứ | Giới hạn |
|---|---|---|---|
| Review rule | Cấu hình có đúng ý định? | Rulebase, object, thứ tự rule | Không chứng minh packet đi qua rule |
| Policy lookup/simulator | Một luồng dự kiến match gì? | Flow simulation, route/NAT lookup | Không bảo đảm đường truyền hoặc ứng dụng hoạt động |
| Test lớp 3–4 | Đường truyền và transport mở không? | TCP handshake, UDP service reply, PCAP | Không xác thực được chức năng ứng dụng chỉ bằng TCP connect |
| Kiểm thử ứng dụng | Dịch vụ trả đúng chức năng không? | HTTP/TLS/DNS response, log ứng dụng | Có thể chạy qua proxy hoặc đường khác |
| Log/counter/session | Firewall xử lý kết nối theo rule nào? | Policy ID, action, counter, session, NAT | Log có thể sampling, thiếu, trễ hoặc nằm ở hệ khác |
| Test hồi quy | Các luồng khác còn hoạt động đúng không? | Ma trận test trước/sau | Chỉ bao phủ những tình huống đã thiết kế |

## 2. Hiểu đường xử lý packet qua firewall

Tường lửa có thể thực hiện: nhận packet trên ingress interface, nhận diện zone, route lookup, NAT, kiểm tra trạng thái phiên, so security policy, kiểm tra ứng dụng/IPS rồi chuyển packet qua egress. Thứ tự chính xác của các bước **phụ thuộc vendor và phiên bản**, không thể áp chung một pipeline.

~~~mermaid
flowchart TD
    A["Test client"] --> B["Ingress interface / security zone"]
    B --> C["Route / PBR / NAT / session lookup<br/>tùy pipeline thiết bị"]
    C --> D["Security policy match"]
    D --> E{"Hành động hiệu lực?"}
    E -->|DENY / DROP / REJECT| F["Chặn và ghi nhận log/counter<br/>nếu được bật"]
    E -->|ALLOW| G["Egress, L7 policy, inspection<br/>và các bước còn lại"]
    G --> H["Dịch vụ đích, đường về"]
    H --> I["Client, firewall, server<br/>và hệ thống log"]
~~~

### 2.1. Xác định luồng với 5-tuple

| Trường | Ví dụ lab | Vai trò |
|---|---|---|
| Source IP | 10.20.10.25 | Máy thực hiện kiểm thử |
| Source port | 51234 | Cổng phía client, thường là cổng tạm |
| Destination IP | 10.20.40.10 | Đích thực tế được kiểm tra |
| Destination port | 443 | Cổng dịch vụ |
| IP protocol | TCP | TCP/UDP hoặc giao thức khác |

**5-tuple** có thể thay đổi khi đi qua SNAT/DNAT. Phải lưu cả địa chỉ/port ban đầu và sau dịch để nối log trước/sau firewall. Với IPv6, cần bảng kiểm tra và policy riêng nếu hạ tầng dual stack.

### 2.2. Stateful và stateless

- **Stateful firewall** ghi trạng thái phiên. Packet phản hồi của kết nối đã được cho phép thường đi theo session table, không cần một rule mở chiều kết nối mới từ server về client. Điều này phụ thuộc chính sách và cách triển khai cụ thể.
- **Stateless ACL** xét các đặc điểm packet theo danh sách luật; có thể cần rule chiều về và xét dải cổng tạm của client.
- **Local-in policy** bảo vệ dịch vụ chạy trên chính firewall (SSH/HTTPS/SNMP quản trị), thường tách với security policy chuyển tiếp giữa các zone.
- **Application-aware policy** có thể nhận diện ứng dụng sau khi bắt đầu phiên. TCP connect thành công chưa chắc ứng dụng được cho phép khi còn quy tắc dựa trên App-ID, URL, TLS/SNI hay IPS.

Đặc biệt, thay đổi ALLOW thành DENY có thể không cắt phiên đang có. Hãy tạo **kết nối mới** để xác minh chính sách mới, và kiểm tra session table. Việc xóa session trên production chỉ nên giới hạn đúng test flow đã được phê duyệt; không tự xóa hàng loạt phiên.

## 3. Chuẩn bị một buổi kiểm thử có kiểm soát

Bản **Test Plan** cần xác định rõ:

| Nội dung | Cần ghi |
|---|---|
| Mục tiêu | Ví dụ USER chỉ được vào App01 qua TCP/443, không qua TCP/22 |
| Phạm vi | Subnet, IP, asset, security zone, site, VPN, VRF, IPv4/IPv6 |
| Thời gian và quyền | Người yêu cầu, người phê duyệt, khoảng thực hiện, đầu mối vận hành |
| Dạng traffic | TCP connect, HTTPS health check, DNS query; số lần và tần suất |
| Điểm quan sát | Máy nguồn, firewall ingress/egress, NAT/session, máy đích, SIEM |
| Điều kiện dừng | Sai đích, lỗi nghiệp vụ, sự cố thật, mất kết nối quản trị, thiếu rollback |
| Kỳ vọng | Allow/deny theo rule cụ thể, trạng thái ứng dụng, bằng chứng |
| Hồi phục | Backup, change ID, rollback, người xử lý, cách test lại |

Chỉ thử lưu lượng tới những đích trong lab hoặc hệ thống được phép, với số kết nối nhỏ và giới hạn thời gian. Không chạy flood, quét toàn dải mạng, gửi payload gây lỗi dịch vụ hay đổi rule ngoài phạm vi. Trước khi tạo traffic, cần xác nhận máy test thực sự ở **đúng zone/VLAN/VPN**. Một phép thử từ máy kỹ thuật ở vùng ADMIN không thể thay thế kiểm thử từ vùng USER.

### 3.1. Định nghĩa trạng thái kết quả

| Trạng thái | Khi nào ghi |
|---|---|
| **PASS** | Bằng chứng đủ cho thấy hành vi tại điểm kiểm soát phù hợp kỳ vọng |
| **FAIL** | Bằng chứng xác nhận policy hoặc chức năng trái kỳ vọng |
| **INCONCLUSIVE** | Không đủ chứng cứ, ví dụ timeout nhưng không thấy packet ở firewall |
| **NOT RUN** | Chưa kiểm thử vì ngoài phạm vi, thiếu điều kiện hoặc chưa được phê duyệt |

Với **negative test**, timeout không đủ để kết luận PASS: có thể server tắt, không có route, host firewall chặn, địa chỉ sai hoặc một thiết bị khác đã drop.

## 4. Topology lab và chính sách yêu cầu

Dưới đây là hệ thống lab giả lập dùng địa chỉ private, không phải dữ liệu mạng thật.

| Thiết bị/vùng | Địa chỉ | Chức năng |
|---|---|---|
| Client-User, USER VLAN | 10.20.10.25/24 | Máy kiểm thử của người dùng |
| Client-Admin, ADMIN VLAN | 10.20.50.25/24 | Máy kỹ thuật có quyền quản trị |
| Client-Guest, GUEST VLAN | 10.20.60.25/24 | Nguồn truy cập không tin cậy |
| App01, APP VLAN | 10.20.40.10/24 | HTTPS TCP/443 |
| DNS01, SERVICES VLAN | 10.20.0.53/24 | DNS UDP/53 và TCP/53 |
| Mgmt01, MGMT VLAN | 10.20.90.11/24 | SSH TCP/22 |
| Firewall-A | Ranh giới các zone | Firewall policy, route và NAT nếu được cấu hình |

~~~mermaid
flowchart LR
    U["USER<br/>10.20.10.25"] --> FW["Firewall-A<br/>Policies + Logs"]
    A["ADMIN<br/>10.20.50.25"] --> FW
    G["GUEST<br/>10.20.60.25"] --> FW
    FW --> APP["APP<br/>App01 10.20.40.10:443"]
    FW --> DNS["SERVICES<br/>DNS01 10.20.0.53:53"]
    FW --> MGMT["MGMT<br/>Mgmt01 10.20.90.11:22"]
~~~

**Chính sách mong muốn:**

1. USER → App01:443/TCP **ALLOW**; ứng dụng phải trả lời đúng.
2. USER → App01:22/TCP **DENY**.
3. USER → DNS01:53/UDP và TCP **ALLOW**; truy vấn DNS phải có phản hồi thích hợp.
4. USER → Mgmt01:22/TCP **DENY**.
5. ADMIN → Mgmt01:22/TCP **ALLOW**, nhưng SSH còn yêu cầu xác thực quyền.
6. GUEST → APP/MGMT **DENY**.
7. USER → DNS ngoài trực tiếp **DENY** nếu policy dùng DNS nội bộ bắt buộc.
8. Mọi luồng liên zone khác **DENY mặc định**, trừ ngoại lệ được phê duyệt.

Nếu các dịch vụ App01, DNS01 hoặc Mgmt01 chưa chạy thật trong lab, cần khởi động/vérify listener trước khi kiểm thử. Không dùng thất bại từ một server không có listener làm bằng chứng firewall DENY.

## 5. Ma trận positive/negative test

| Test ID | Nguồn → đích | Giao thức/port | Kỳ vọng | Bằng chứng cần có |
|---|---|---|---|---|
| FWT-01 | USER → App01 | TCP/443 | ALLOW, HTTPS hoạt động | Client, firewall ALLOW, app log |
| FWT-02 | USER → App01 | TCP/22 | DENY | Client + policy DENY/counter |
| FWT-03 | USER → DNS01 | UDP/53 | ALLOW, DNS có phản hồi | dig, DNS log, firewall |
| FWT-04 | USER → DNS01 | TCP/53 | ALLOW, DNS có phản hồi | dig +tcp và log |
| FWT-05 | USER → Mgmt01 | TCP/22 | DENY | Firewall DENY và nguồn test |
| FWT-06 | ADMIN → Mgmt01 | TCP/22 | ALLOW tới dịch vụ | Session + AAA/SSH log |
| FWT-07 | GUEST → App01 | TCP/443 | DENY | Firewall DENY |
| FWT-08 | GUEST → Mgmt01 | TCP/22 | DENY | Firewall DENY |
| FWT-09 | USER → DNS resolver ngoài danh sách | UDP/53 | DENY | Rule/counter tại egress, test target hợp lệ |
| FWT-10 | USER → App01 | TCP/80 | DENY nếu không có HTTP redirect được duyệt | Log policy thực tế |
| FWT-11 | ADMIN → Mgmt01, tài khoản thiếu quyền | TCP/22 | Network ALLOW, SSH auth DENY | Firewall ALLOW + AAA DENY |
| FWT-12 | USER IPv6 → Mgmt01 IPv6 | TCP/22 | DENY | IPv6 policy và client |
| FWT-13 | USER → App01 sau thay đổi rule | TCP/443 | Vẫn ALLOW, ứng dụng không lỗi | Regression + health check |

**Chú ý:** FWT-11 có thể hoàn toàn đạt yêu cầu khi network cho phép tới dịch vụ nhưng AAA từ chối tài khoản không đủ quyền. Firewall quyết định đường đến dịch vụ; hệ thống nhận dạng/ủy quyền quyết định ai có thể đăng nhập.

### 5.1. Hồ sơ test case có thể tái sử dụng

~~~yaml
test_id: FWT-01
source:
  host: Client-User
  ip: 10.20.10.25
  zone: USER
destination:
  host: App01
  ip: 10.20.40.10
  zone: APP
transport: TCP
destination_port: 443
expected_network_action: ALLOW
expected_application_result: "TLS hợp lệ, GET /health phản hồi theo hợp đồng ứng dụng"
evidence_required:
  - client_output
  - firewall_rule_id_action
  - application_log
status: NOT_RUN
~~~

Đây chỉ là **mẫu mô tả phép thử**, không phải cấu hình có thể nạp vào firewall. Trước mỗi lần chạy, người kiểm thử cập nhật cửa sổ thời gian và trạng thái môi trường.

## 6. Chuẩn bị baseline và kiểm chứng điểm xuất phát

### 6.1. Ghi cấu hình trước thay đổi

Trước khi test hoặc chỉnh rule, cần lưu:

- Phiên bản cấu hình firewall, rule ID, security zone/interface, các object và thứ tự rule.
- Route, VRF, PBR/SD-WAN policy và NAT translation có liên quan.
- Phiên hiện hữu và cơ chế giữ session sau khi đổi rule.
- Tình trạng App01/DNS01/Mgmt01, health check và dịch vụ đang lắng nghe.
- Đồng bộ thời gian UTC/NTP giữa client, firewall, server và log collector.
- Bản backup và quyền sử dụng console hoặc management path để rollback.

Công cụ **flow simulator/packet tracer** có thể xác minh đường xử lý dự kiến, nhưng vẫn phải chạy test traffic thật để phát hiện sai lệch vận hành.

### 6.2. Xác nhận đúng route và interface nguồn

Trên Linux:

~~~bash
ip -br address
ip route get 10.20.40.10
ip route get 10.20.90.11
~~~

Trên Windows PowerShell:

~~~powershell
Get-NetIPAddress -AddressFamily IPv4
Find-NetRoute -RemoteIPAddress 10.20.40.10
~~~

Nếu máy test có nhiều interface, VPN hoặc route riêng, phải kiểm tra gói thực sự xuất phát từ IP/zone yêu cầu. Route trên máy nguồn chỉ là ý định của hệ điều hành; **chưa xác nhận** packet đi qua đúng firewall.

Nếu có quyền đọc tại máy đích, kiểm tra listener:

~~~bash
ss -ltn
~~~

Có thể kiểm tra service cụ thể theo sản phẩm và quy trình, ví dụ web server đang chạy hay không. Không vô hiệu hóa host firewall để làm test dễ thành công: như vậy làm đổi hệ thống mà phép thử đang cố kiểm chứng.

## 7. Positive test TCP: từ kết nối đến ứng dụng

### 7.1. Kiểm thử port được phép

Trên Client-User trong lab, kiểm tra FWT-01:

~~~bash
nc -vz -w 3 10.20.40.10 443
~~~

Nếu cổng mở, mới chứng minh một TCP handshake thành công. Để kiểm tra HTTPS và endpoint ứng dụng:

~~~bash
curl -v --connect-timeout 3 --max-time 10 \
  https://app.lab.example/health
~~~

Nếu muốn ép hostname tới IP lab nhưng vẫn giữ **Host** và **TLS SNI**, dùng:

~~~bash
curl -v --connect-timeout 3 --max-time 10 \
  --resolve app.lab.example:443:10.20.40.10 \
  https://app.lab.example/health
~~~

Chứng chỉ TLS phải được client tin cậy; nếu tổ chức dùng CA nội bộ, cấu hình trust store hoặc --cacert đúng cách. Không bỏ qua kiểm tra chứng chỉ chỉ để có kết quả PASS. Endpoint /health và HTTP status mong muốn cần do chủ ứng dụng xác nhận.

Trên Windows:

~~~powershell
Test-NetConnection -ComputerName 10.20.40.10 -Port 443
~~~

**Từ TCP sang ứng dụng:** HTTP 200 theo hợp đồng có thể chứng minh luồng hoạt động; HTTP 401/403 cho thấy đã đến một dịch vụ HTTP hoặc lớp proxy/WAF nhưng bị từ chối theo quyền/chính sách, không tự động đồng nghĩa firewall DENY. Phải kiểm tra đúng hệ thống phản hồi.

### 7.2. Khi nào positive test thực sự PASS?

- Client kết nối đúng IP/port/transport.
- Firewall ghi ALLOW cho **đúng luồng, đúng rule**, theo thời điểm test.
- Đã xem NAT và hướng đi/đường trả lời thực tế khi có liên quan.
- Server hoặc application log xác nhận nhận yêu cầu và trả kết quả đáp ứng hợp đồng.
- Không có security profile/IPS/WAF khác chặn sau bước L4.
- Không làm hỏng một chức năng phụ thuộc quan trọng.

## 8. Negative test TCP: chứng minh hành động DENY

Ví dụ từ Client-User đã được xác minh nằm ở USER VLAN:

~~~bash
nc -vz -w 3 10.20.40.10 22
nc -vz -w 3 10.20.90.11 22
~~~

Kỳ vọng kết nối không mở. Tuy nhiên cần phân biệt:

| Kết quả từ client | Khả năng xảy ra | Cách xác minh |
|---|---|---|
| Timeout | Firewall DROP, mất route, host im lặng, gói thất lạc | Counter, rule log, capture ở ingress/egress |
| Connection refused hoặc TCP RST | Server không lắng nghe, host firewall REJECT hoặc thiết bị mạng trả RST | Xác định nguồn RST và trạng thái listener |
| ICMP administratively prohibited | Một thiết bị từ chối theo chính sách | Xác định IP nguồn thông báo ICMP, log/counter |
| DNS resolution error | Tên đích không phân giải hoặc sai IP | DNS query log, so IP kết nối thực tế |
| TCP connect thành công | Có đường tới cổng dịch vụ và bắt tay thành công | Kiểm tra rule match, NAT, VPN, route bypass |
| Không có log ở firewall | Không đi qua firewall, log disabled, timestamp lệch hoặc thiết bị khác xử lý | Capture, packet path, log pipeline |

**Điều kiện PASS của FWT-02/FWT-05:** test tuple từ đúng source/zone xuất hiện tại firewall cần kiểm chứng, rule DENY đúng được áp, và không có phiên hợp lệ đến dịch vụ qua một đường nằm trong phạm vi kiểm tra. Nếu chỉ có timeout ở client và không thấy packet trên firewall, kết luận **INCONCLUSIVE**.

## 9. UDP và ứng dụng không có TCP handshake

UDP không tạo bắt tay SYN/SYN-ACK/ACK. Công cụ dạng UDP connect/port scan có thể báo kết quả mơ hồ khi không có response; không thể dùng điều đó để chứng minh rule hoạt động.

Ví dụ FWT-03 kiểm tra DNS01, với điều kiện zone app.lab.example đã được tạo trong lab:

~~~bash
dig @10.20.0.53 app.lab.example A +tries=1 +time=2
~~~

Với DNS TCP FWT-04:

~~~bash
dig +tcp @10.20.0.53 app.lab.example A +tries=1 +time=2
~~~

Cách đọc kết quả:

- Có DNS response phù hợp, DNS01 log trùng client và firewall ghi ALLOW: tích cực cho cả network và ứng dụng.
- **NXDOMAIN** vẫn là một response DNS; nếu tên hỏi không tồn tại thì đó có thể là hoạt động bình thường của DNS, nhưng chưa đạt một test yêu cầu A record cụ thể.
- Timeout có thể xảy ra vì firewall, resolver không hoạt động, route sai, packet loss hoặc ứng dụng đích không phục vụ.
- Với **negative UDP test**, không nhận response vẫn chưa đủ. Cần firewall DENY log/counter hoặc capture đúng điểm, kết hợp kiểm soát đích thử nghiệm.
- DNS thực tế thường cần cả UDP lẫn TCP/53; không kiểm thử chỉ một giao thức rồi kết luận DNS đã hoạt động đầy đủ.

Đối với SNMP, NTP, syslog và giao thức UDP chuyên biệt, dùng client/health check hợp lệ và server log thay vì gửi payload tự phát trên production.

## 10. Packet capture và đọc kết quả mạng

### 10.1. Thu lượng gói hạn chế trong lab

Tại sensor hoặc host có quyền, có thể ghi PCAP tập trung vào một test flow. Thay IFACE bằng interface thật:

~~~bash
sudo tcpdump -i <IFACE> -nn -s 128 -c 200 \
  -w /var/tmp/fwt-01.pcap \
  'host 10.20.10.25 and host 10.20.40.10 and tcp port 443'
~~~

Các tùy chọn:

- **-c 200** dừng sau tối đa 200 packet nếu đủ traffic; không có packet thì lệnh có thể tiếp tục đợi cho tới khi người vận hành kết thúc.
- **-s 128** chỉ lưu tối đa 128 byte của mỗi packet; giảm thu thập payload, đồng thời có thể thiếu dữ liệu ứng dụng.
- **Filter** chỉ đúng khi hai địa chỉ IP còn được nhìn thấy tại điểm thu. Sau SNAT/DNAT, phải lọc theo tuple đã dịch.
- **Điểm thu** xác định kết luận: capture ở client không chứng minh packet tới server; capture ở một phía firewall chưa chứng minh chiều về.

Không capture toàn mạng hoặc thu payload người dùng ngoài phạm vi. Ghi timestamp, interface, filter, người thu và nơi lưu file.

### 10.2. Các pattern thường gặp

| Pattern trong capture | Diễn giải có thể | Kiểm tra tiếp |
|---|---|---|
| SYN → SYN-ACK → ACK | Bắt tay TCP hoàn thành giữa các điểm quan sát | L7/TLS, chính sách thực match, máy đích |
| SYN lặp nhưng không có phản hồi | Drop, packet loss, route sai hoặc server im lặng | Capture hai phía firewall và server |
| SYN → RST | Có thiết bị từ chối hoặc không có listener | Nguồn RST, host firewall, policy |
| Firewall ingress thấy SYN, egress không thấy | Packet có thể bị drop tại firewall | Rule action, NAT, security profile, drop diagnostics |
| Firewall egress có SYN nhưng server không thấy | Lỗi phía sau firewall | L2/L3 route, switch, host NIC/ACL |
| TCP thành công, TLS lỗi | Certificate, TLS policy, proxy/inspection | TLS handshake, app logs |
| UDP request có, response không | Server im lặng, firewall chiều về, route hoặc app | Server logs, PCAP, session/counter |

### 10.3. Phân tích PCAP có sẵn

~~~bash
capinfos /var/tmp/fwt-01.pcap

tshark -r /var/tmp/fwt-01.pcap \
  -Y 'tcp.flags.syn == 1 || tcp.flags.reset == 1' \
  -T fields -e frame.time_epoch -e ip.src -e ip.dst \
  -e tcp.srcport -e tcp.dstport \
  -e tcp.flags.syn -e tcp.flags.ack -e tcp.flags.reset

tshark -r /var/tmp/fwt-01.pcap -q -z conv,tcp
sha256sum /var/tmp/fwt-01.pcap
~~~

Hash SHA-256 giúp chứng minh một file giữ nguyên byte kể từ lúc lấy hash, nhưng **không chứng minh capture đã đủ gói**, không xác nhận nguồn gốc độc lập và không thay thế nhật ký thu thập chứng cứ. Không thể suy ra nội dung HTTPS từ metadata TCP/TLS đã mã hóa.

## 11. Log firewall, hit counter và session table

Mỗi phép thử nên có một **test ID**, khoảng thời gian UTC và bản ghi ở firewall:

| Trường | Giá trị cần đọc |
|---|---|
| Event time | Thời điểm được log ở thiết bị, kiểm tra clock skew |
| Source/destination IP | Trước và sau NAT nếu có |
| Source/destination zone | Xác định policy domain đúng |
| Protocol và port | TCP, UDP hoặc protocol thực tế, source port và destination port |
| Rule UUID/name | Rule thực sự được áp, không chỉ rule dự kiến |
| Action và security profile | ALLOW/DENY/REJECT, IPS/WAF/App-ID sau policy |
| Session ID/state | Phân biệt new/established/reused |
| Route/egress | Interface, VRF, next hop và đường thực tế |
| Bytes/packets | Metadata hỗ trợ đối chiếu, không chứng minh nội dung payload |

**Hit counter tăng** là chỉ báo một rule được match nhưng không đủ thay cho kiểm thử ứng dụng. Nếu nhiều test chạy đồng thời, chỉ dựa vào counter tăng có thể đối chiếu nhầm luồng. Dùng timestamp, tuple và session ID khi có thể.

Log **ALLOW** có thể ghi khi firewall chấp nhận packet đầu phiên, trong khi server không phản hồi. Log **DENY** có thể được bật một phần hoặc lấy mẫu theo cấu hình. Không thấy log cần kiểm tra cả log pipeline, policy logging, filter, timezone và packet path trước khi kết luận không có lưu lượng.

## 12. Bảy nguyên nhân thường gây kết quả bất ngờ

### 12.1. Thứ tự rule và shadowing

Một ví dụ về chính sách **first match**:

~~~text
RULE-10: ALLOW  USER -> APP  any
RULE-20: DENY   USER -> APP  tcp/22
RULE-30: ALLOW  USER -> APP  tcp/443
~~~

Nếu RULE-10 được xét trước và bao trùm toàn bộ luồng, RULE-20 và RULE-30 có thể không bao giờ match. Việc “có rule DENY” không chứng minh cổng SSH đã bị chặn. Xem **rule match thực** và kết quả test, sau đó sửa quy tắc rộng/ưu tiên theo chính sách nhà cung cấp.

### 12.2. Phiên cũ còn sống sau khi đổi rule

Firewall đã đổi ALLOW thành DENY nhưng trình duyệt vẫn làm việc do connection pool hoặc session tracking. Để kiểm chứng rule mới, tạo **một phiên TCP mới** trong phạm vi cho phép, so với session table. Nếu cần xóa session test, chỉ thực hiện với phiên có định danh rõ và sự đồng ý của vận hành.

### 12.3. NAT đổi địa chỉ hoặc port

Ví dụ:

~~~text
Client:              10.20.10.25:52001
Requested VIP:       198.51.100.10:443
Translated server:   10.20.40.10:443
Possible SNAT:       10.20.99.1:52001
~~~

Dải 198.51.100.0/24 là dải dành cho ví dụ tài liệu. Policy có thể xét địa chỉ trước hoặc sau NAT tùy sản phẩm. Đọc session/NAT translation trước khi quy kết server thấy “sai IP” hoặc rule thiếu địa chỉ.

### 12.4. Asymmetric route, PBR, SD-WAN và đường bypass

Request đi qua Firewall-A nhưng response đi một đường khác có thể làm stateful inspection drop hoặc khiến log thiếu chiều về. Một VPN, VRF, route tắt, đường load balancer hoặc cloud route table cũng có thể làm traffic **không đi qua firewall đang kiểm chứng**.

Cần xem route hai chiều, ingress/egress interface, packet capture, policy route và NAT; traceroute đơn lẻ không đủ vì ICMP có thể theo đường khác TCP.

### 12.5. DNS, FQDN object và CDN

Một hostname có thể phân giải ra IP khác do resolver, DNS cache, CDN, split-horizon hoặc IPv6 AAAA. Firewall có FQDN object có thể cập nhật IP theo thời điểm riêng. Ghi **địa chỉ thực sự được kết nối**, DNS resolver, FQDN object hiện có và Host/SNI nếu dùng chính sách lớp 7. Đừng cho rằng mọi request tới một hostname đều dùng một IP.

### 12.6. IPv6 chưa được cấu hình tương đương

Một máy có dual stack có thể mở SSH qua IPv6 dù IPv4 bị chặn đúng. Trong lab có IPv6, kiểm tra riêng bằng lệnh phù hợp:

~~~bash
nc -6 -vz -w 3 fd20:20:90::11 22
~~~

Địa chỉ trên là IPv6 ULA minh họa. Nếu không có endpoint IPv6 để thử, ghi NOT RUN; không công bố IPv6 PASS dựa trên test IPv4.

### 12.7. Firewall ALLOW nhưng IDS/IPS, WAF hoặc application policy chặn

Traffic có thể qua rule lớp 4 nhưng bị từ chối sau đó bởi IPS signature, URL filtering, WAF, TLS inspection, App-ID hoặc endpoint authentication. Để xác minh, xem từng quyết định theo **security policy**, **security profile** và **ứng dụng**; không tự thêm allow-any nhằm giải quyết một lỗi mà lớp khác đang chặn có chủ đích.

Ngoài ra HTTP/3 qua **QUIC/UDP 443** có thể dùng đường khác TCP/443. Nếu ứng dụng hỗ trợ QUIC, cần test UDP/443 riêng và kiểm tra fallback, không dùng mỗi nc TCP để tuyên bố mọi HTTPS đều đúng.

## 13. Phương pháp khoanh vùng khi test thất bại

~~~mermaid
flowchart TD
    A["Test khác kỳ vọng"] --> B{"Nguồn, đích, port, zone<br/>và timestamp đã đúng?"}
    B -->|Không| C["Chỉnh test setup, ghi lại điều kiện"]
    B -->|Có| D{"Firewall thấy packet?"}
    D -->|Không| E["Kiểm tra route, VLAN, VPN,<br/>PBR, NAT, điểm capture"]
    D -->|Có| F{"Match đúng rule?"}
    F -->|Không| G["Xem thứ tự rule, object,<br/>shadow, zone, pre/post NAT"]
    F -->|Có| H{"Action đúng kỳ vọng?"}
    H -->|Không| I["Kiểm tra stateful session,<br/>L7/security profile"]
    H -->|Có| J{"Server nhận packet và trả lời?"}
    J -->|Không| K["Egress, return path,<br/>host firewall và listener"]
    J -->|Có| L["Xác minh TLS, ứng dụng,<br/>auth và quyết định kết quả"]
~~~

### 13.1. Bảng chẩn đoán thường gặp

| Triệu chứng | Cần nghi ngờ | Bước xác nhận |
|---|---|---|
| Negative TCP/22 connect thành công | Rule allow rộng, session reuse, bypass | Rule hit thật, session mới, packet path |
| Positive TCP/443 timeout | Rule, route, server/host firewall | Capture hai phía, server listener |
| Firewall ALLOW nhưng app trả 503 | Backend lỗi hoặc proxy | App health, load balancer log |
| Firewall không có log | Traffic đi đường khác, logging tắt, SIEM trễ | Route, capture, logging pipeline |
| DNS UDP OK nhưng TCP 53 lỗi | TCP bị chặn, resolver không listen TCP | dig +tcp, logs và listener |
| HTTP 401/403 | Ứng dụng/AAA/WAF từ chối | HTTP/proxy/app/WAF logs |
| IPv4 DENY nhưng truy cập vẫn có | IPv6 hoặc đường thay thế | IPv6 ACL, proxy, route |
| Nguồn trên server khác IP client | SNAT/proxy/load balancer | NAT/session mapping |
| VPN test khác LAN | Split tunnel, pool/identity, route | VPN policy, zone, client routing |

**Không quy kết firewall sai** khi chưa xác minh traffic thực sự đi qua firewall đó và server sẵn sàng trả lời.

## 14. Trình tự kiểm thử trước và sau một thay đổi

Giả sử vấn đề là rule ALLOW USER → APP any đang quá rộng. Mục tiêu là thu hẹp thành App01:443 mà vẫn duy trì DNS.

**Trước thay đổi:** ghi rule ID và export config; xác minh nguồn USER, baseline health App01/DNS01; chạy FWT-01/02/03/04/05; lưu packet/log/counter và kết quả PASS/FAIL/INCONCLUSIVE.

**Triển khai:** theo change control, thay cấu hình rộng bằng quyền tối thiểu. Pseudopolicy dưới đây **không phải cú pháp copy được của vendor**:

~~~text
ALLOW USER  -> App01      TCP/443
ALLOW USER  -> DNS01      UDP/53, TCP/53
DENY  USER  -> App01      TCP/22
DENY  USER  -> Mgmt01     TCP/22
ALLOW ADMIN -> Mgmt01     TCP/22
DENY  GUEST -> APP/MGMT   any
DENY  other inter-zone flows unless explicitly approved
~~~

**Sau thay đổi:** tạo connection mới và lặp lại các test trước đó; kiểm tra FWT-01 vẫn nhận HTTP/TLS hợp lệ, FWT-02 đúng DENY tại firewall, DNS còn hoạt động và vùng GUEST không được mở. Đối chiếu rule ID với log, application health, session và bản cấu hình thực tế.

**Rollback khi:** dịch vụ thiết yếu bị gián đoạn ngoài giới hạn, mất đường quản trị, rule đánh sai zone, không đủ bằng chứng xác minh thay đổi, hoặc xuất hiện rủi ro mới. Rollback từ bản cấu hình đã được vận hành phê duyệt, sau đó chạy lại smoke test allow/deny. Việc hệ thống báo “rollback completed” không đủ nếu không xác minh chức năng.

## 15. Đặc thù của VPN, Wi-Fi và cloud

### 15.1. VPN

Một kết nối từ VPN user và VPN admin có thể khác IP pool, nhóm danh tính, split tunnel, route và zone. Test plan phải ghi đúng **VPN group, địa chỉ cấp phát, chính sách định tuyến và đường đi**. Không suy rằng có IP nội bộ thì tự động đi qua firewall trung tâm.

### 15.2. Wi-Fi khách, nhân viên và IoT

Để kiểm tra cách ly mạng không dây, cần kết nối test device vào đúng SSID, xác nhận VLAN/NAC mapping và gateway. Tạo test từ guest/IoT tới management service hoặc APP theo ma trận, quan sát firewall policy và log controller. Với roaming/dynamic VLAN, cần kiểm tra định danh thiết bị và chính sách sau chuyển vùng.

### 15.3. Cloud

Hạ tầng cloud có thể sử dụng security group, NSG, subnet NACL, route table, network firewall, NAT gateway, load balancer, host firewall và service mesh. Một luồng giữa hai VM trong cùng subnet **không nhất thiết** đi qua firewall trung tâm. Phải xác định điểm kiểm soát cần kiểm thử và lựa chọn source/destination tương ứng.

Một số security group có ngữ nghĩa stateful, còn NACL stateless hoặc có khác biệt giữa nền tảng; cần đọc rule chiều về và ephemeral ports. Cloud flow logs thường chỉ là metadata, đôi khi có độ trễ hoặc lấy mẫu; luôn so với endpoint và application logs.

## 16. Báo cáo kết quả có chứng cứ

### 16.1. Ví dụ log tổng hợp

Các sự kiện sau là dữ liệu giả lập, không mô tả output chính xác của một nhà sản xuất:

~~~text
2026-01-15T09:00:00Z TEST id=FWT-01 src=10.20.10.25 dst=10.20.40.10 tcp/443
2026-01-15T09:00:01Z FW   policy=ALLOW-USER-APP action=ALLOW session=8101 src=10.20.10.25 dst=10.20.40.10
2026-01-15T09:00:02Z APP  client=10.20.10.25 GET /health status=200
2026-01-15T09:01:00Z TEST id=FWT-02 src=10.20.10.25 dst=10.20.40.10 tcp/22
2026-01-15T09:01:01Z FW   policy=DENY-USER-SSH action=DENY src=10.20.10.25 dst=10.20.40.10
2026-01-15T09:02:00Z TEST id=FWT-06 src=10.20.50.25 dst=10.20.90.11 tcp/22
2026-01-15T09:02:01Z FW   policy=ALLOW-ADMIN-MGMT action=ALLOW session=8102 src=10.20.50.25 dst=10.20.90.11
2026-01-15T09:02:02Z SSH  user=lab-admin auth=SUCCESS src=10.20.50.25
~~~

FWT-01 có firewall ALLOW và HTTP 200: hỗ trợ xác minh cả policy và dịch vụ. FWT-02 có firewall DENY khớp test: hỗ trợ kết luận gói mới bị chặn. FWT-06 kết hợp network ALLOW và auth SUCCESS; không dùng SSH auth thành công để suy ra mọi tài khoản đều có quyền.

### 16.2. Bảng kết quả mẫu

| Test ID | UTC | Kỳ vọng | Quan sát | Evidence ID | Đánh giá |
|---|---|---|---|---|---|
| FWT-01 | 09:00 | HTTPS ALLOW | HTTP 200, FW ALLOW | FW-L01, APP-L01 | PASS |
| FWT-02 | 09:01 | SSH DENY | Client không connect; FW DENY | FW-L02 | PASS |
| FWT-03 | 09:04 | DNS UDP ALLOW | DNS response hợp lệ, resolver log | DNS-L01, FW-L03 | PASS |
| FWT-05 | 09:07 | Mgmt SSH DENY | Timeout, không tìm thấy firewall log | CLIENT-T05 | INCONCLUSIVE |
| FWT-06 | 09:02 | Admin SSH ALLOW | Network ALLOW, auth SUCCESS | FW-L04, AAA-L01 | PASS |
| FWT-12 | — | IPv6 DENY | Chưa có IPv6 endpoint | — | NOT RUN |

Các giá trị chỉ minh họa. FWT-05 chưa thể PASS vì không có chứng cứ packet đến firewall và bị chặn ở đó.

### 16.3. Evidence manifest

Mỗi kết quả cần lưu **Test Run ID**, Test ID, tài sản nguồn và đích, subnet/zone, protocol/port, thời gian UTC bắt đầu/kết thúc, expected/actual, rule UUID, NAT/session, nguồn log/capture, người kiểm thử, người review và hash file khi có hiện vật.

Bảo vệ PCAP/log bằng quyền truy cập tối thiểu và chính sách lưu giữ của tổ chức; test traffic có thể chứa token hoặc dữ liệu nhạy cảm từ ứng dụng. Hash cho file sau export nhằm kiểm tra tính toàn vẹn byte, không tự chứng minh log đã đầy đủ.

## 17. Đo độ bao phủ và chất lượng kiểm thử

**Coverage** cần xét nhiều chiều:

- Nguồn: USER, ADMIN, GUEST/IoT, VPN, cloud workload.
- Đích: APP, management, DNS, Internet egress, private/public endpoint.
- Giao thức: TCP, UDP, IPv4, IPv6, TLS/HTTP, DNS UDP và TCP.
- Hướng: inbound/outbound, kết nối mới và gói phản hồi.
- Tuyến: NAT, primary/failover, PBR/VRF/VPN/SD-WAN.
- Policy: allow, deny, implicit deny, exception, shadow và application layer.
- Trạng thái: trước/sau change, session mới/cũ, HA/failover nếu được phê duyệt.
- Quan sát: client, firewall ingress/egress, server, SIEM/telemetry.

Ví dụ có 12 test bắt buộc, 10 PASS, 1 FAIL và 1 NOT RUN: tỷ lệ PASS trên tổng số bài bắt buộc là **10/12 = 83,3%**. Không được che giấu một FAIL trọng yếu phía sau tỷ lệ tổng; mỗi FAIL/NOT RUN cần rủi ro, owner và kế hoạch xử lý.

Kiểm thử tốt **không chỉ là nhiều ca thử**. Cần ca thử được đặt đúng zone, có outcome đo được, bằng chứng tại ranh giới, biết phân biệt lỗi ứng dụng và mạng, và có kiểm thử hồi quy.

## 18. Bài tập tình huống

### Bài tập 1 — Rule shadowing

Firewall có thứ tự:

~~~text
10 ALLOW USER -> APP any
20 DENY  USER -> APP TCP/22
30 ALLOW USER -> APP TCP/443
~~~

Sau khi thêm rule 20, kết nối TCP/22 vẫn thành công. Hãy giải thích tình huống và đề xuất bằng chứng đủ để xác nhận.

**Gợi ý:** trong firewall first-match, rule 10 bao trùm nên rule 20 không xử lý packet. Cần log rule match, tìm shadow, sửa allow-all theo least privilege và kiểm thử lại phiên mới.

### Bài tập 2 — Timeout không đồng nghĩa DENY

Từ USER, TCP/22 tới Mgmt01 timeout và không có firewall log. Người kiểm thử đánh PASS. Hãy đánh giá.

**Gợi ý:** chưa đủ. Cần xác nhận đúng source zone/route, packet xuất hiện tại ingress, rule DENY hoặc counter/capture tương ứng. Nếu không xác định được, ghi INCONCLUSIVE.

### Bài tập 3 — DNS UDP chạy, TCP 53 không chạy

DNS response qua UDP hợp lệ nhưng dig +tcp timeout. Hãy đề xuất quy trình khoanh vùng.

**Gợi ý:** kiểm tra rule TCP/53 riêng, TCP listener ở DNS01, host firewall, return route, server và firewall logs. Không kết luận toàn bộ DNS đã PASS.

### Bài tập 4 — Firewall ALLOW nhưng ứng dụng không dùng được

Firewall ghi ALLOW TCP/443, curl trả lỗi chứng chỉ hoặc HTTP 503. Có nên mở ANY-ANY?

**Gợi ý:** không. Kiểm tra TLS certificate/hostname, app health, load balancer, WAF, reverse proxy, security profile, server logs và đường phản hồi.

### Bài tập 5 — IPv6 bypass

IPv4 SSH vào Mgmt01 bị chặn, IPv6 SSH lại mở. Nhóm cần ghi gì trong báo cáo?

**Gợi ý:** FAIL đối với mục tiêu cách ly management plane nếu IPv6 thuộc phạm vi; nêu nguồn/đích IPv6, rule match, khuyến nghị ACL/firewall IPv6 tương ứng và retest.

### Bài tập 6 — Đề xuất ma trận

Cho môi trường ở mục 4, hãy lập tối thiểu 8 test gồm ít nhất 3 negative, 3 positive và 1 regression. Với mỗi test cần nguồn, đích, zone, protocol, port, outcome, rule ID và cách chứng minh.

**Tiêu chí đạt:** test sử dụng đúng vị trí, không đánh đồng TCP connect với chức năng ứng dụng và không đánh dấu negative PASS nếu thiếu log tại điểm kiểm soát.

### 18.1. Rubric 100 điểm

| Tiêu chí | Điểm | Bằng chứng |
|---|---:|---|
| Scope, quyền và Test Plan | 15 | Mục tiêu và điều kiện dừng rõ |
| Ma trận allow/deny | 20 | Phủ nguồn, đích, port, zone |
| Thực thi TCP/UDP/ứng dụng | 15 | Công cụ đúng, listener được kiểm tra |
| Đối chiếu firewall/capture/log | 20 | Rule ID, action, NAT/session |
| Phân tích lỗi và false PASS | 15 | Route, shadow, session, IPv6 |
| Regression/rollback | 10 | Kế hoạch đổi rule và phục hồi |
| Báo cáo và chứng cứ | 5 | PASS/FAIL/INCONCLUSIVE, evidence |
| **Tổng** | **100** | Đánh giá theo bằng chứng thay vì số probe |

## 19. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách sửa |
|---|---|---|
| Chỉ đọc rule, không tạo traffic | Không phát hiện shadow/bypass | Thực hiện test đúng tuple, xem match |
| Dùng ping thay TCP/443 | Sai giao thức kiểm thử | nc + curl và server log |
| Timeout nghĩa là firewall DENY | False PASS | Ingress capture + rule/counter |
| TCP connect nghĩa là HTTPS OK | Bỏ qua L7/TLS | Test endpoint ứng dụng |
| Dùng sai VLAN/SSID/VPN group | Không kiểm tra đúng policy | Xác nhận nguồn/route trước |
| Không phân biệt UDP và TCP | Bỏ sót DNS TCP/53 | Test mỗi transport đúng mục đích |
| Quên NAT | Đối chiếu sai IP | Original/translated tuple |
| Quên session tồn tại | Rule mới bị đánh giá sai | Tạo kết nối mới |
| Quên IPv6/QUIC | Có đường thay thế chưa kiểm soát | Test đúng giao thức/stack |
| Không thấy firewall log thì kết luận PASS | Có thể traffic đi đường khác | Capture, routing, logging health |
| Allow-any để sửa lỗi | Mở bề mặt tấn công | Điều tra nguyên nhân theo lớp |
| Bỏ kiểm thử hồi quy | Ứng dụng hợp lệ có thể ngừng hoạt động | Positive tests trước/sau |
| Không có bằng chứng file và owner | Không thể review hoặc retest | Evidence manifest và ticket |

## 20. Checklist trước khi bàn giao

- [ ] Test Plan rõ tài sản/zone, IP, giao thức/cổng, người phê duyệt và điều kiện dừng.
- [ ] Đã kiểm tra nguồn test ở đúng VLAN/VPN/VRF, đích có listener và dịch vụ sẵn sàng.
- [ ] Đã lưu cấu hình, route, NAT, rule order và baseline trước thay đổi.
- [ ] Positive test kiểm tra cả luồng mạng và dịch vụ ứng dụng.
- [ ] Negative test xác nhận chính firewall/rule định kiểm chứng đã chặn lưu lượng.
- [ ] UDP được kiểm bằng phản hồi ứng dụng và log; không suy luận từ timeout đơn lẻ.
- [ ] Có rule ID, action, timestamp, source/zone, đích, session và NAT mapping khi liên quan.
- [ ] Đã xét stateful session, shadow rule, local-in policy, NAT, routing, IPv6 và L7.
- [ ] Đã kiểm tra các phụ thuộc VPN, Wi-Fi, DNS, proxy, IDS/IPS và cloud khi thuộc phạm vi.
- [ ] Có bằng chứng từ client, firewall, server hoặc sensor theo tiêu chí của từng test.
- [ ] Tệp log/PCAP được giới hạn phạm vi, lưu có kiểm soát và ghi evidence ID/hash.
- [ ] Mọi ca FAIL, INCONCLUSIVE, NOT RUN đều có lý do, owner và bước tiếp theo.
- [ ] Sau thay đổi có regression test, người xác nhận nghiệp vụ và phương án rollback.
- [ ] Báo cáo kết luận riêng điều đã chứng minh, rủi ro còn lại và phần chưa kiểm chứng.

**Tiêu chí hoàn thành:** một firewall rule được xác minh khi test traffic từ **đúng vị trí và đúng giao thức** tạo ra **đúng hành vi chính sách** với bằng chứng nhất quán giữa client, firewall và đích. Phương pháp này đưa hoạt động kiểm soát mạng từ việc “có rule trong cấu hình” thành một năng lực có thể đo lường, tái kiểm thử và sử dụng trong giám sát cũng như phản ứng sự cố.

