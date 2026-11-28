# Phát hiện lateral movement qua network

## 1. Lateral movement là gì và vì sao phải quan sát ở lớp mạng?

**Lateral movement (di chuyển ngang)** là quá trình kẻ tấn công sau khi có chỗ đứng ban đầu tìm cách truy cập hoặc kiểm soát thêm tài khoản, máy chủ, máy trạm hay vùng mạng khác. Mục đích có thể là mở rộng quyền truy cập, tiếp cận hệ thống chứa dữ liệu quan trọng, vượt qua phân đoạn mạng hoặc tiến đến mã hóa, phá hoại hay đánh cắp dữ liệu.

Trong điều tra số trên mạng (*network forensics*), ta tìm **chuỗi kết nối và hoạt động xác thực giữa các tài sản** giúp tái dựng đường đi của kẻ tấn công. Khác với lưu lượng từ Internet vào dịch vụ công khai (*north-south*), lateral movement thường tạo ra dấu vết **east-west**: máy nội bộ nói chuyện với máy nội bộ khác, nhiều khi sử dụng giao thức quản trị hợp lệ như SMB, RDP, SSH, WinRM, RPC hoặc API quản lý cloud.

Ví dụ:

1. Một máy trạm bị kiểm soát gửi yêu cầu kết nối tới nhiều máy trong VLAN máy chủ.
2. Cùng tài khoản xuất hiện trong các phiên đăng nhập đến nhiều đích mới.
3. Sau một phiên SMB/RPC, một máy chủ bắt đầu chạy dịch vụ hoặc tác vụ từ xa khác thường.
4. Từ máy chủ vừa bị truy cập, các kết nối mới tiếp tục mở sang máy thứ ba.

Đáng chú ý, **mỗi kết nối riêng lẻ đều có thể trông hợp lệ**. Điều đáng nghi xuất hiện khi nối các sự kiện theo *nguồn → tài khoản → đích → thời gian → hành động → đích tiếp theo*.

Bài học áp dụng trong module **SECURITY_NETWORK_SECURITY**: kết hợp giám sát lưu lượng, phân đoạn, firewall, VPN, IDS/IPS, DNS, mạng không dây và mạng cloud với log danh tính và máy đích để phát hiện di chuyển ngang, xác định phạm vi và hỗ trợ kiến trúc mạng an toàn.

### Kết quả cần đạt

Sau bài này, người học có thể:

- Nhận ra các dấu hiệu mạng của lateral movement trên Windows, Linux và môi trường cloud/hybrid.
- Tương quan lưu lượng, đăng nhập, tài khoản, tài sản và thay đổi dịch vụ để phân biệt quản trị hợp lệ với truy cập trái phép.
- Dùng flow log, DNS, Zeek, PCAP, IDS/IPS và log hệ điều hành để dựng dòng thời gian di chuyển ngang.
- Xây dựng truy vấn phát hiện có ngữ cảnh, đặt ngưỡng và giảm dương tính giả.
- Ghi nhận kết luận với mức độ chắc chắn thích hợp, bảo toàn bằng chứng và đề xuất hành động ứng phó.

## 2. Phân biệt lateral movement với hoạt động mạng khác

| Hiện tượng | Đặc trưng | Vì sao chưa đủ để kết luận lateral movement? |
|---|---|---|
| **Network discovery / scanning** | Một nguồn thăm dò nhiều IP/cổng | Có thể là kiểm kê, máy quét được phê duyệt hoặc giai đoạn trinh sát chưa truy cập thành công |
| **Đăng nhập quản trị từ xa** | Kết nối SSH/RDP/WinRM/SMB có xác thực | Quản trị viên, hệ thống triển khai phần mềm và bộ công cụ vận hành dùng các giao thức này hằng ngày |
| **Lateral movement nghi ngờ** | Đường đi liên tiếp, tài khoản/nguồn bất thường, quan hệ mới, dấu hiệu truy cập hoặc thực thi từ xa | Cần kiểm tra định danh, phê duyệt, kết quả xác thực và hoạt động sau kết nối |
| **Lateral movement đã được củng cố bằng chứng** | Có dấu vết dùng quyền trái phép trên đích, thực thi từ xa, rồi mở thêm kết nối tới đích khác | Vẫn cần mô tả chính xác phạm vi đã chứng minh và điểm chưa xác minh |
| **Exfiltration** | Dữ liệu đi tới nơi không được phép | Có thể diễn ra sau lateral movement nhưng không đồng nghĩa với di chuyển ngang |
| **Command and control (C2)** | Máy bị kiểm soát liên lạc tới hạ tầng điều khiển | Có thể tạo chỗ đứng hoặc thực thi lệnh; không nhất thiết có thêm tài sản nội bộ bị truy cập |

Hai thuật ngữ hữu ích:

- **Bàn đạp (*pivot*)**: một máy trung gian bị lợi dụng để kết nối đến tài sản khác hoặc chuyển tiếp lưu lượng.
- **Đường di chuyển (*path*)**: chuỗi các cạnh quan sát được, chẳng hạn \`WS-23 → APP-02 → DB-01\`. Một cạnh kết nối **không tự chứng minh** tài sản đích đã bị chiếm.

Lateral movement có thể sử dụng tài khoản hợp lệ, chứng chỉ, token, khóa SSH hoặc phiên truy cập đã bị đánh cắp. Vì thế, phương pháp chỉ dò mã độc hoặc IP độc hại sẽ bỏ sót nhiều trường hợp.

## 3. Các phương thức và dấu vết mạng thường gặp

Cổng mặc định chỉ là **gợi ý ban đầu**: dịch vụ có thể đổi cổng, được chuyển tiếp qua proxy/tunnel hoặc được mã hóa. Nhận diện nên kết hợp fingerprint giao thức, hướng kết nối, ngữ cảnh và log máy đích.

| Đường di chuyển | Giao thức/cổng thường gặp | Dấu vết mạng cần chú ý | Bằng chứng bổ sung hữu ích |
|---|---|---|---|
| **Remote Desktop (RDP)** | TCP/UDP 3389 | Máy trạm bất thường kết nối đến nhiều máy quản trị; phiên RDP lần đầu giữa hai máy | Windows Security 4624 logon type 10; TerminalServices logs, chính sách jump host |
| **SMB / Windows Admin Shares** | TCP 445, đôi khi 139 | SMB giữa các máy không có quan hệ trước đây; truy cập ADMIN$, C$, IPC$; SMB nối tiếp RPC | 4624 type 3, 5140/5145 nếu bật audit, truy cập file, tạo service |
| **WinRM / PowerShell Remoting** | TCP 5985 (HTTP), 5986 (HTTPS) | Máy nguồn mới mở nhiều phiên quản trị đến đích khác thường | WinRM/PowerShell operational logs, 4624, log script và process tree |
| **WMI / DCOM / RPC** | TCP 135 và cổng RPC động | Kết nối RPC từ máy không có chức năng quản trị, sau đó hành động từ xa | WMI-Activity, process creation, 4624, các thay đổi dịch vụ |
| **Remote service / PsExec-like** | SMB và RPC; cổng tùy môi trường | Ghi file qua SMB rồi điều khiển dịch vụ từ xa | Windows System 7045, Security 4697 khi có audit, 5145, process creation |
| **SSH** | TCP 22 | Máy vừa bị truy cập mở SSH tới nhiều máy khác; nguồn/đích lần đầu liên lạc | \`sshd\`/journal logs, \`authorized_keys\`, sudo, process tree |
| **RDP/SSH qua jump host** | Cổng trực tiếp hoặc cổng được chuyển tiếp | Các kết nối bắt nguồn từ bastion; chuỗi truy cập không đúng lịch/đúng người | Session recording, PAM, bastion audit, IAM |
| **Truy cập quản trị cloud/hybrid** | HTTPS 443, private endpoints, VPN | API thay đổi quyền, mở kết nối sang subnet/VPC khác, dùng cùng principal trên nhiều tài nguyên | Cloud control-plane audit, IAM, security group, VPC/NSG flow logs |

Một số ánh xạ với **MITRE ATT&CK** có thể giúp gắn nhãn hành vi: **T1021 Remote Services** (T1021.001 RDP, T1021.002 SMB/Windows Admin Shares, T1021.004 SSH, T1021.006 Windows Remote Management), **T1047 WMI**, **T1569.002 Service Execution**, **T1078 Valid Accounts**. Các mã này là cách mô tả kỹ thuật, không thay thế bằng chứng tại hiện trường.

### Vì sao không nên chỉ lọc port 445 hoặc 3389?

Một kết nối đến cổng 445 có thể do file sharing, GPO, cập nhật hoặc quản trị từ xa. Một kẻ tấn công có thể dùng SSH trên cổng không mặc định hoặc gọi API qua HTTPS; nhiều kết nối RDP hợp lệ cũng diễn ra trong môi trường vận hành. Quy tắc có hiệu quả thường phát hiện **sự lệch chuẩn trong quan hệ máy–máy và tài khoản–máy**, sau đó tìm các sự kiện củng cố.

## 4. Dữ liệu cần có để điều tra qua network

### 4.1. Flow, metadata, nội dung gói tin

| Nguồn | Trường nên thu thập | Giá trị và giới hạn |
|---|---|---|
| **NetFlow/IPFIX/sFlow** | Thời gian, IP nguồn/đích, port, giao thức, chiều, bytes, packets | Dựng quan hệ kết nối ở quy mô lớn; không xác nhận danh tính hay xác thực thành công; sFlow có thể lấy mẫu |
| **Firewall east-west / microsegmentation** | Rule, action allow/deny, zone, IP, port, NAT, thời gian | Biết kết nối có bị chặn ở điểm thực thi đó không; \`allow\` không có nghĩa là phiên ứng dụng thành công |
| **Zeek \`conn.log\`** | \`ts\`, \`uid\`, \`id.orig_h\`, \`id.resp_h\`, \`id.resp_p\`, \`service\`, \`conn_state\`, bytes | Liên kết kết nối với log giao thức; \`SF\` cho biết trạng thái kết nối, không xác minh người dùng đăng nhập |
| **Zeek log giao thức (SMB, Kerberos, NTLM, RDP, DCE/RPC...)** | Tên tài nguyên, hoạt động, định danh quan sát được tùy giao thức và phiên bản | Bổ sung ngữ nghĩa; khả năng phân giải khác nhau theo TLS, phiên bản giao thức, cấu hình sensor |
| **PCAP/PCAPNG** | Gói tin, thứ tự, TCP flags, dữ liệu không mã hóa khi có quyền phân tích | Phục dựng phiên chi tiết; bắt gói tại sai vị trí hoặc sau thời điểm xảy ra sẽ có điểm mù |
| **IDS/IPS** | Signature, nội dung/tham chiếu cảnh báo, IP/port, thời điểm, verdict | Phát hiện chuỗi hành vi được nhận diện; một alert đơn lẻ không chứng minh truy cập trái phép |

Trong hệ thống cloud, VPC Flow Logs / NSG Flow Logs hỗ trợ quan sát đường truyền nội bộ theo điểm thu thập. Chúng thường **không** mang username hoặc lệnh được thực thi. Vì vậy phải kết nối với control-plane audit, IdP và log workload.

### 4.2. Dữ liệu bổ sung để chứng minh hành vi

**Windows:**

- **4624**: đăng nhập thành công; logon type **3** thường liên quan truy cập qua mạng, type **10** liên quan RemoteInteractive/RDP. Không dùng type đơn lẻ để quy kết độc hại.
- **4625**: đăng nhập thất bại, hữu ích khi tìm thử nhiều tài khoản hoặc nhiều đích.
- **4648**: đăng nhập bằng thông tin xác thực được cung cấp tường minh; cần xem tài khoản, nguồn và tình huống.
- **4672**: quyền đặc biệt được gán cho một phiên đăng nhập; thường xuất hiện ở các hoạt động quản trị hợp lệ.
- **4768/4769**: yêu cầu Kerberos TGT/service ticket tại DC trong môi trường Active Directory; service ticket **không** chứng minh đã mở phiên tới dịch vụ.
- **4776**: xác thực NTLM được kiểm tra bởi máy có thẩm quyền; không nhất thiết cho biết toàn bộ đường kết nối.
- **5140/5145**: truy cập share/check truy cập nếu bật auditing thích hợp.
- **7045** (System): service mới được cài đặt; **4697** nếu bật chính sách audit liên quan.
- **Sysmon Event ID 3** (nếu bật cấu hình tương ứng): kết nối mạng gắn với tiến trình; hữu ích để kết nối IP/port với hành vi trên host.

**Linux:** \`sshd\` và systemd journal, PAM, \`sudo\`, \`auditd\`/process telemetry, lịch sử thay đổi SSH key và cấu hình. Cần phân biệt một phiên TCP established với sự kiện “Accepted publickey/password” trong log xác thực.

**Cloud/identity:** IAM sign-in, hoạt động tạo/giả định role, thay đổi network policy, remote management/session service, Kubernetes API audit, container exec, bastion/session manager. Cần biết danh tính logic của workload, không chỉ IP của node.

### 4.3. Bản đồ bối cảnh tối thiểu

Muốn phát hiện một kết nối “lạ” phải biết thế nào là “bình thường”:

- Danh mục tài sản: hostname, IP hiện tại, lease DHCP, owner, vai trò (workstation, DC, application, database, backup, jump host).
- Sơ đồ subnet, VLAN, VPC, routing và vùng tin cậy; tài sản nào được phép quản trị tài sản nào.
- Danh sách máy quản trị, hệ thống quét, phần mềm triển khai, backup, patch management, lịch bảo trì và change ticket.
- Quan hệ tài khoản → nhóm quyền → thiết bị → thời gian sử dụng hợp lệ.
- Điểm đặt sensor và tỷ lệ bao phủ lưu lượng east-west; các vùng không nhìn thấy vì switch, overlay, encryption hoặc thiết kế cloud.

**Giới hạn quan sát:** NAT, DHCP, proxy, IPv6 privacy address, pod/container IP và load balancer làm thay đổi ý nghĩa của địa chỉ nguồn. Không gán ngay một IP cho một người hay một thiết bị trước khi kiểm tra nhật ký ánh xạ theo thời gian.

## 5. Các mẫu phát hiện lateral movement

Phương pháp hiệu quả kết hợp nhiều tín hiệu thành một chuỗi. Có thể phân chia theo mục tiêu của mỗi truy vấn.

### Mẫu A — Fan-out đến nhiều đích quản trị

Một máy trạm thông thường lần đầu khởi tạo kết nối tới nhiều máy khác qua SMB, RDP, WinRM hoặc SSH trong khoảng ngắn.

**Đầu vào:** \`src_host\`, \`dst_host\`, \`dst_port\`, time window, role, allowlist và baseline. Ví dụ ngưỡng khởi đầu cho môi trường nhỏ: **ít nhất 5 đích mới trong 10 phút** qua một hoặc nhiều dịch vụ quản trị; hiệu chỉnh dựa trên phân phối nền thực tế.

**Dễ nhầm với:** vulnerability scanner, phần mềm triển khai, jump host, backup, kiểm kê endpoint. Tìm dấu hiệu xác thực thành công/thất bại và hành vi tiếp theo.

### Mẫu B — Chuỗi nhảy nhiều máy (multi-hop)

Tài sản A khởi tạo kết nối tới B; sau đó **B bắt đầu** liên lạc đến C bằng giao thức quản trị chưa từng dùng. Quan sát B như điểm pivot thay vì chỉ xem A là nguồn ban đầu.

**Đầu vào:** đồ thị các cạnh kết nối theo thời gian và các sự kiện đăng nhập/thực thi trên từng đích.

**Điểm cần xác minh:** một phiên RDP từ A đến B không chứng minh rằng kết nối B → C do kẻ tấn công điều khiển. Cần tìm phiên người dùng, tiến trình tạo kết nối và bối cảnh thay đổi được phê duyệt.

### Mẫu C — Tài khoản xuất hiện trên nhiều đích

Cùng tài khoản dùng phiên đăng nhập thành công ở nhiều máy khác nhau trong khoảng thời gian ngắn, đặc biệt tài khoản đặc quyền hoặc không có nhiệm vụ quản trị các máy đó.

**Đầu vào:** 4624/IdP/VPN/\`sshd\` log, định danh người dùng, máy đích, nguồn thực tế, logon type, kết quả xác thực. Có thể ưu tiên \`first_seen(account, host)\`.

**Dễ nhầm với:** service account, cơ chế single sign-on, tác vụ phân phối, quy trình quản trị theo nhóm hoặc hệ thống có ủy quyền đăng nhập.

### Mẫu D — SMB kết hợp RPC/service execution

Máy X kết nối SMB đến máy Y, có truy cập tài nguyên quản trị, sau đó Y ghi nhận tạo service hoặc tiến trình bất thường; X tiếp tục thực hiện chuỗi tương tự với nhiều máy.

**Độ mạnh của bằng chứng:** cao hơn so với chỉ thấy TCP/445. Kết luận remote execution cần bằng chứng từ log dịch vụ/tiến trình hoặc lưu lượng cho phép phân tích được thao tác tương ứng.

### Mẫu E — Di chuyển ngang vượt phân đoạn

Nguồn thuộc VLAN người dùng bất ngờ truy cập TCP/3389, 445, 5985/5986 hoặc SSH đến subnet sản xuất vốn không có quan hệ quản trị. Firewall cho phép do rule rộng, hoặc có thay đổi ACL/security group gần thời điểm đó.

**Ưu tiên:** tăng khi đích là domain controller, máy giữ khóa/bí mật, hệ thống backup, DNS lõi, firewall/VPN manager hoặc máy chủ dữ liệu nhạy cảm.

### Mẫu F — Xác thực bất thường đi kèm kết nối hợp lệ

Có nhiều lần đăng nhập thất bại vào các đích khác nhau, sau đó một lần đăng nhập thành công từ cùng nguồn/tài khoản hoặc một tài khoản liên quan. Ngay sau đó xuất hiện đăng nhập mới từ máy đích.

**Lưu ý:** thất bại rồi thành công có thể do mật khẩu thay đổi. Phải phân tích số lượng, nhịp, đích, đặc quyền và hành vi sau xác thực.

### Mẫu G — Hoạt động cloud/hybrid

Một danh tính hoặc instance vừa đăng nhập qua VPN hay được cấp role mới, sau đó gọi API quản lý tài nguyên trên vùng khác, mở firewall/security group và thực hiện kết nối quản trị tới các workload trước đó không liên quan.

**Lưu ý:** luồng HTTPS/API có thể che giấu hành động quản trị; đòi hỏi cloud audit để xác định principal, API action và đối tượng bị thay đổi.

## 6. Quy trình điều tra theo dòng thời gian

~~~mermaid
flowchart TD
  A["Nhận alert về east-west traffic hoặc đăng nhập bất thường"] --> B["Xác minh thời gian, nguồn quan sát, mapping IP/hostname"]
  B --> C["Dựng baseline theo vai trò tài sản và thay đổi hợp lệ"]
  C --> D{"Kết nối có bất thường so với ngữ cảnh?"}
  D -->|Không| E["Lưu dấu vết, đóng/điều chỉnh rule nếu hợp lý"]
  D -->|Có| F["Tương quan xác thực và hành động trên máy đích"]
  F --> G{"Có bằng chứng truy cập/thực thi trái phép?"}
  G -->|Chưa rõ| H["Triage có owner, thời hạn và giả thuyết cần kiểm chứng"]
  H --> I["Bổ sung log máy đích, PCAP, danh tính, change ticket"]
  I --> G
  G -->|Có hoặc nghi ngờ đáng tin với tác động lớn| J["Mở hoặc nâng security incident"]
  J --> K["Xác định các bước nhảy, tài sản, tài khoản và phạm vi"]
  K --> L["Bảo toàn bằng chứng và điều phối ngăn chặn theo runbook"]
  L --> M["Cập nhật timeline, mức chắc chắn và biện pháp phòng ngừa"]
~~~

Thực hành theo các bước:

1. **Chốt khoảng thời gian và giả thuyết:** alert bắt đầu lúc nào? Đã có tín hiệu trước đó bao lâu? Tất cả timestamp nên quy đổi về UTC trong hệ thống phân tích, đồng thời giữ nguyên múi giờ của bản gốc.
2. **Định danh nguồn và đích:** đối chiếu lease DHCP, NAT translation, CMDB, VPN/session, cloud instance ID, container ID theo *đúng thời điểm xảy ra*.
3. **Tìm phiên làm điểm xuất phát:** đăng nhập bất thường, truy cập từ máy chưa từng đóng vai trò quản trị, hoạt động trên endpoint hoặc mốc xâm nhập ban đầu nếu đã biết.
4. **Dựng các cạnh east-west:** nhóm theo bộ \`source → destination → protocol/port → timestamp\`, xác định kết nối mới, tập đích, lượt thử và lượt có phản hồi.
5. **Tìm bằng chứng xác thực và hành động:** 4624/4625, Kerberos/NTLM, SSH, RDP, WinRM, service, file access, process creation. Kiểm tra sự khớp thời gian và định danh; tránh diễn giải “TCP accepted” thành “login success”.
6. **Tiếp tục từ mỗi đích đã truy cập:** xét có phiên outbound mới bắt nguồn từ đích, tạo thành A → B → C hay không; tìm thêm nhánh song song.
7. **Xác định mức ảnh hưởng:** tài sản trọng yếu, quyền tài khoản, dữ liệu, số phân đoạn, dấu hiệu persistence hoặc exfiltration; phân biệt đã xác minh với nghi ngờ.
8. **Báo cáo và điều phối:** lưu chứng cứ, thông báo SOC/IR; đánh giá cô lập, thu hồi phiên/quyền, siết phân đoạn và bảo toàn khả năng phục hồi dịch vụ theo thẩm quyền.

### Sơ đồ quan hệ cần tái dựng

~~~mermaid
graph LR
  U["WS-23\nMáy trạm bị nghi chiếm"] -->|"09:12 SMB/445 + auth"| A["APP-02\nỨng dụng nội bộ"]
  U -->|"09:13 RDP/3389"| B["ADMIN-01\nMáy quản trị"]
  A -->|"09:19 WinRM/5985"| C["DB-01\nCơ sở dữ liệu"]
  B -->|"09:22 SSH/22"| D["BACKUP-01\nMáy sao lưu"]
~~~

Sơ đồ chỉ là ví dụ về **các cạnh được quan sát**. Để gọi A hay B là máy đã bị chiếm, phải bổ sung chứng cứ về phiên, tiến trình hoặc hành động trái phép ở các máy đó.

## 7. Phân tích mẫu log mạng

Giả sử hệ thống SIEM chuẩn hóa flow, authentication và hoạt động trên máy. Dữ liệu minh họa sau dùng địa chỉ private nội bộ và thời gian có múi giờ.

| Thời gian | Nguồn | Đích | Quan sát | Diễn giải ban đầu |
|---|---|---|---|---|
| 09:10:12 | 10.20.5.23 (WS-23) | 10.30.8.12 (APP-02) | TCP/445 established | Có phiên SMB; chưa xác minh đăng nhập |
| 09:10:14 | WS-23 | APP-02 | Security 4624, type 3, tài khoản \`corp\\helpdesk2\` | Có đăng nhập qua mạng; cần xác minh tính hợp lệ |
| 09:10:30 | APP-02 | APP-02 | System 7045: service mới ngoài thay đổi cho phép | Tăng mạnh mức nghi ngờ remote execution; kiểm tra origin |
| 09:11:07 | 10.30.8.12 (APP-02) | 10.40.1.30 (DB-01) | TCP/5985, chưa có trong baseline | Xuất hiện cạnh mới APP-02 → DB-01 |
| 09:11:09 | APP-02 | DB-01 | 4624 type 3 và log WinRM | Có phiên quản trị từ xa phù hợp với cạnh mạng |
| 09:12:02 | DB-01 | 10.40.2.9 (BACKUP-01) | TCP/445 + log truy cập share mới | Có thêm bước đi; chưa chứng minh mã độc hoặc xâm nhập backup |

**Phân tích:**

- Một đường đi thời gian có thể là **WS-23 → APP-02 → DB-01 → BACKUP-01**.
- Tín hiệu mạnh nằm ở **quan hệ lần đầu**, tài khoản quản trị không phù hợp vai trò, **dịch vụ mới trên APP-02** và **chuỗi kết nối tiếp diễn**.
- Cần xác minh tài khoản \`helpdesk2\` có đang thực hiện tác vụ hợp lệ, service mới do ai tạo và tiến trình nào tại APP-02 mở WinRM.
- Không kết luận DB-01 hoặc BACKUP-01 đã bị chiếm chỉ dựa trên các dòng mạng; phải tìm bằng chứng ứng dụng và endpoint tại các đích.

### Truy vấn 1 — Phát hiện một nguồn mở kết nối tới nhiều đích quản trị

Đây là **SQL khái niệm** trên bảng telemetry đã chuẩn hóa. Tên cột, phép chia khung thời gian và hàm SQL sẽ khác tùy SIEM hoặc cơ sở dữ liệu.

~~~sql
-- schema giả định: network_flows(ts, src_host, dst_host, dst_port, action)
WITH admin_connections AS (
  SELECT
    FLOOR(EXTRACT(EPOCH FROM ts) / 600) AS window_10m,
    src_host,
    dst_host,
    dst_port
  FROM network_flows
  WHERE dst_port IN (22, 445, 3389, 5985, 5986)
    AND action = 'allow'
)
SELECT
  window_10m,
  src_host,
  COUNT(DISTINCT dst_host) AS distinct_targets
FROM admin_connections
GROUP BY window_10m, src_host
HAVING COUNT(DISTINCT dst_host) >= 5
ORDER BY distinct_targets DESC;
~~~

**Ý nghĩa:** tìm *fan-out*, không xác nhận truy cập thành công. Sau khi tìm được nguồn bất thường, đối chiếu danh sách máy quét/quản trị được phép và xác thực đến từng đích.

### Truy vấn 2 — Tìm quan hệ máy–máy lần đầu trong 30 ngày

~~~sql
-- schema giả định: network_flows(ts, src_host, dst_host, dst_port, action)
-- giả sử :analysis_start là ngày bắt đầu phân tích
WITH history AS (
  SELECT DISTINCT src_host, dst_host, dst_port
  FROM network_flows
  WHERE ts >= :analysis_start - INTERVAL '30 days'
    AND ts < :analysis_start
),
current_edges AS (
  SELECT DISTINCT src_host, dst_host, dst_port
  FROM network_flows
  WHERE ts >= :analysis_start
    AND ts < :analysis_start + INTERVAL '1 day'
    AND action = 'allow'
    AND dst_port IN (22, 445, 3389, 5985, 5986)
)
SELECT c.src_host, c.dst_host, c.dst_port
FROM current_edges c
LEFT JOIN history h
  ON c.src_host = h.src_host
 AND c.dst_host = h.dst_host
 AND c.dst_port = h.dst_port
WHERE h.src_host IS NULL;
~~~

Các quan hệ mới được tìm ra nên được xếp hạng theo vai trò máy nguồn/đích, mức đặc quyền, thời điểm và kết quả xác thực. Việc không có log trong 30 ngày có thể do hệ thống mới, mất log hoặc lượng traffic quá thấp; **“first seen” là thuộc tính của dữ liệu đang có**, không phải khẳng định trong lịch sử chưa từng xảy ra.

### Truy vấn 3 — Trích xuất kết nối từ PCAP bằng Wireshark/TShark

~~~bash
# Phân tích offline một PCAP đã thu thập hợp lệ; không đụng tới mạng trực tiếp.
tshark -r incident.pcapng \
  -Y "tcp.port == 445 || tcp.port == 3389 || tcp.port == 5985 || tcp.port == 5986 || tcp.port == 22" \
  -T fields \
  -e frame.time_utc -e ip.src -e ip.dst \
  -e tcp.srcport -e tcp.dstport -e tcp.flags.syn -e tcp.flags.ack
~~~

Bộ lọc trên giúp định vị phiên cần xem, **không tự phân loại lateral movement**. Với SMB, RDP, SSH hoặc WinRM qua TLS, dữ liệu ứng dụng có thể được bảo vệ bằng mã hóa; analyst thường cần log xác thực và endpoint. Nếu môi trường dùng IPv6, bổ sung các trường và filter IPv6; nếu giao thức chạy ở cổng khác, sử dụng dấu hiệu giao thức hoặc log tương ứng.

### Truy vấn 4 — Tương quan định danh, đăng nhập và flow

Có thể biểu diễn một detector theo logic:

~~~text
Trong cửa sổ 15 phút:
  (1) Host nguồn không thuộc danh sách máy quản trị
  (2) Có kết nối mới sang >= 3 host qua dịch vụ điều khiển từ xa
  (3) Tại >= 1 host đích có đăng nhập thành công
  (4) Có thêm một trong các dấu hiệu:
      - tài khoản không thường dùng trên host đích
      - service/process mới bất thường tại host đích
      - đích bắt đầu kết nối sang host thứ ba
      - lưu lượng vượt vùng mạng được phép
=> Tạo case ưu tiên cao để analyst kiểm tra.
~~~

Các con số chỉ là **giá trị khởi đầu minh họa**. Mỗi môi trường phải điều chỉnh theo baseline và yêu cầu phát hiện. Ngưỡng quá thấp sẽ gây nhiễu; ngưỡng quá cao sẽ bỏ sót kẻ tấn công di chuyển chậm qua một đích.

## 8. Case study: phát hiện di chuyển ngang từ máy trạm lên máy chủ

### Bối cảnh

Doanh nghiệp có ba vùng mạng:

- \`10.20.5.0/24\`: máy trạm của nhân viên.
- \`10.30.8.0/24\`: máy chủ ứng dụng nội bộ.
- \`10.40.1.0/24\`: cơ sở dữ liệu và hệ thống trọng yếu.

Quản trị từ xa qua RDP/WinRM đến máy chủ được thiết kế đi qua jump host, nhưng có một rule firewall cũ cho phép một số kết nối trực tiếp từ VLAN người dùng.

SOC nhận cảnh báo từ flow analytics: \`WS-23\` mở các phiên TCP/445 đến 7 máy ứng dụng trong 6 phút, trong khi baseline tháng trước chỉ truy cập file server. Một số máy từ chối kết nối; một máy \`APP-02\` có phiên TCP hoàn chỉnh.

### Từng bước phân tích

**Bước 1 — Xác minh nguồn:** ánh xạ \`10.20.5.23\` vào \`WS-23\` theo DHCP tại thời gian xảy ra. Kiểm tra VPN và EDR để tránh nhầm với tài khoản dùng laptop khác.

**Bước 2 — Tách quét với truy cập:** log firewall cho thấy nhiều đích không có phiên thành công. Trên \`APP-02\`, Windows Security có logon type 3 với tài khoản có quyền quản trị máy và không có change ticket liên quan.

**Bước 3 — Kiểm tra tác động trên đích:** log System 7045 ghi nhận dịch vụ mới; EDR cho thấy tiến trình phục vụ service sinh lệnh quản trị. Tên service hoặc đường dẫn riêng lẻ có thể trùng với công cụ hợp lệ, vì vậy SOC kiểm tra hash, tài khoản tạo, mốc thời gian và chủ hệ thống.

**Bước 4 — Tìm pivot:** flow cho thấy \`APP-02\` gọi WinRM sang \`DB-01\` vài phút sau. Log WinRM và logon trên \`DB-01\` ghi nhận phiên cùng thời điểm. Tại đây, không có bằng chứng thực thi độc hại hay truy cập dữ liệu bất thường.

**Bước 5 — Ra quyết định:** chuỗi xác thực trái thẩm quyền, thực thi từ xa và pivot đủ cơ sở để mở **suspected/confirmed security incident** theo mức xác minh của tổ chức. Phạm vi xác nhận bao gồm hành vi trên \`WS-23\`, \`APP-02\` và kết nối/phiên vào \`DB-01\`; mức độ kiểm soát thực tế của \`DB-01\` còn cần điều tra.

**Bước 6 — Ứng phó:** theo thẩm quyền và runbook, đội ứng phó lưu log/PCAP, cô lập điểm xuất phát hoặc ngắt phiên nguy hiểm nếu thích hợp, bảo vệ tài khoản liên quan, rà kiểm các máy trong đường đi và khắc phục rule phân đoạn cho phép truy cập trái dự kiến.

### Vì sao đây là tín hiệu tốt hơn một cảnh báo SMB đơn lẻ?

Cảnh báo đã liên kết được **mẫu fan-out → đăng nhập thành công bất thường → service mới → phiên quản trị từ đích sang máy khác**. Đây là mối quan hệ thời gian, danh tính và hành vi. Tuy nhiên, không nên tự suy ra đánh cắp dữ liệu, chiếm toàn bộ mạng hoặc danh tính kẻ tấn công nếu thiếu chứng cứ tương ứng.

## 9. Giảm dương tính giả mà không đánh mất độ nhạy

| Hoạt động hợp lệ có thể giống lateral movement | Cách xác minh | Điều chỉnh detector |
|---|---|---|
| Triển khai phần mềm, patching, orchestration | Danh sách server được ủy quyền, change ticket, khung giờ, service account | Đưa nguồn/identity đúng vai trò vào baseline theo phạm vi, không bỏ qua mọi hành vi từ đó |
| Quét lỗ hổng, kiểm kê tài sản | Job ID, lịch scan, IP scanner, chữ ký ứng dụng | Gắn nhãn hoạt động đã phê duyệt; báo riêng nếu vượt phạm vi hoặc nguồn bất thường |
| Backup và phục hồi | Dịch vụ backup, đích, lịch và kích thước lưu lượng | Baseline theo khung giờ và nhóm máy, phát hiện hành vi mới ở máy backup |
| Quản trị qua jump host/bastion | Bastion audit, tài khoản, session recording, phiếu yêu cầu | Xếp hạng cao phiên đi vòng jump host hoặc dùng principal mới |
| Tác vụ hàng loạt với service account | Công việc định kỳ, máy thực thi, vault và chính sách quyền | Theo dõi đích mới, giờ mới, hành vi khác công việc thường lệ |
| Ứng dụng nội bộ truy cập SMB hoặc API | Chủ ứng dụng, dependency map, release/deployment | So sánh với sơ đồ phụ thuộc và trạng thái phát hành |

Ba nguyên tắc chính:

1. **Dùng allowlist có phạm vi:** cho phép theo cặp \`principal + source role + destination scope + protocol + timeframe\`; không loại trừ toàn bộ một subnet, tài khoản hoặc jump host.
2. **Tách quan sát và xác nhận:** “SMB thành công” có thể chỉ là bắt tay TCP; “4624 thành công” chưa nói lệnh quản trị hay mã độc đã chạy.
3. **Phát hiện cả hành vi chậm:** rule theo cửa sổ 5–15 phút cần bổ sung phân tích 24 giờ, nhiều ngày và các cạnh hiếm cho đối tượng âm thầm di chuyển qua ít máy.

Có thể dùng điểm rủi ro cho từng chuỗi, ví dụ:

~~~text
+2: máy nguồn là workstation, không nằm trong nhóm quản trị
+2: nhiều đích mới qua giao thức quản trị
+3: xác thực thành công bằng tài khoản đặc quyền không thường dùng
+4: tạo service hoặc thực thi từ xa bất thường trên đích
+3: đích vừa được truy cập trở thành nguồn tới máy thứ ba
+3: vượt ranh giới phân đoạn tới tài sản trọng yếu
-2: có change ticket hợp lệ khớp nguồn, danh tính, phạm vi và thời gian
~~~

Bảng điểm chỉ là thiết kế minh họa. Điểm số không tự chứng minh hành vi ác ý; đặc biệt, **một change ticket không xóa bỏ chứng cứ xâm nhập** nếu hành vi thực tế nằm ngoài phạm vi đã duyệt.

## 10. Giới hạn trong môi trường mã hóa, cloud và mạng hiện đại

- **SMB encryption, SSH, RDP, WinRM qua HTTPS:** PCAP có thể nhìn thấy metadata phiên nhưng không thấy lệnh hoặc nội dung. Dùng host logs, PAM, session audit và EDR bổ sung.
- **Overlay, container, service mesh:** IP gốc của pod hoặc workload có thể bị che bởi node, sidecar, SNAT; cần liên kết Kubernetes audit, workload identity và network policy logs.
- **Cloud control plane:** truy cập và thay đổi quyền có thể diễn ra qua API HTTPS, không xuất hiện như kết nối SSH/SMB truyền thống.
- **East-west traffic bị thiếu:** một sensor ở internet gateway có thể hoàn toàn không thấy lưu lượng trong cùng VLAN/VPC; bố trí sensor hoặc flow export đúng vị trí.
- **Log không đồng bộ thời gian:** khi hệ thống lệch vài phút, thứ tự A → B → C có thể bị đảo; luôn ghi clock offset và độ chính xác của timestamp.
- **Không thể kết luận sự vắng mặt:** thiếu log không chứng minh rằng không có lateral movement. Báo cáo cần tách “không quan sát thấy” với “đã loại trừ”.

Khi đề xuất kiến trúc phòng vệ, kết hợp **phân đoạn/microsegmentation**, nguyên tắc least privilege, xác thực mạnh, jump host, hạn chế giao thức quản trị, bảo vệ DNS và lưu log tập trung. Detection kiểm tra xem các lớp bảo vệ có bị vượt qua; firewall/VPN/IDS/IPS giảm mặt tấn công và cung cấp ngữ cảnh cho điều tra.

## 11. Thu thập và bảo toàn chứng cứ

Để một phát hiện hỗ trợ điều tra lại được:

1. **Giữ nguồn dữ liệu và tính toàn vẹn:** lưu bản gốc log/PCAP hoặc bản export có metadata, hash và ghi nhận người thực hiện, thời điểm, nơi lưu; hạn chế sửa file sau thu thập.
2. **Ghi chính xác điểm quan sát:** tên sensor, interface, network tap/SPAN, VPC mirror, network zone; ghi thời gian đồng hồ, tỷ lệ drop/sampling và tình trạng capture.
3. **Thu thập có giới hạn hợp lý:** chọn phạm vi thời gian, IP/asset, loại log liên quan; tôn trọng phân quyền, dữ liệu cá nhân và chính sách lưu giữ.
4. **Giữ khả năng nối nguồn–đích:** bảo toàn DHCP lease, NAT mapping, cloud ENI/instance mapping, DNS, hostname và identity ở thời điểm liên quan.
5. **Xây dựng timeline có nguồn dẫn:** mỗi quan sát ghi \`timestamp | source | destination | principal | evidence_ref | observation | confidence\`; tách giả thuyết khỏi chứng cứ.
6. **Nhận diện điểm mù:** sensor không thấy hết mạng, log chưa bật, tài khoản dùng chung, phiên mã hóa; ghi chúng trong kết luận và đề xuất bổ sung.

Ví dụ bản ghi tối thiểu cho một bước nhảy:

~~~yaml
edge_id: "edge-03"
observed_at: "2026-11-28T09:11:07+07:00"
source:
  host: "APP-02"
  ip: "10.30.8.12"
destination:
  host: "DB-01"
  ip: "10.40.1.30"
network:
  protocol: "TCP"
  destination_port: 5985
  observation: "connection established"
authentication:
  account: "corp\\helpdesk2"
  result: "success"
  evidence_ref: "event-4624-target-001"
related_evidence:
  - "flow-uid-abcd"
  - "winrm-log-008"
interpretation: "Ứng viên bước di chuyển ngang; kiểm tra quyền và tính hợp lệ"
confidence: "medium"
~~~

Bản ghi ví dụ không chứa mật khẩu, token, bí mật vận hành hoặc nội dung nhạy cảm của phiên.

## 12. Checklist cho SOC, NOC và đội điều tra

- [ ] Đã xác định danh tính tài sản nguồn/đích đúng theo thời gian và xử lý NAT/DHCP/VPN chưa?
- [ ] Đã đánh giá **vai trò**, **quan hệ nền** và **phân đoạn mạng** của hai phía chưa?
- [ ] Có fan-out, nhiều đích mới, nhiều đăng nhập, di chuyển giữa subnet hoặc chuỗi A → B → C không?
- [ ] Đã kiểm tra kết quả xác thực trên **máy đích**, không chỉ TCP established hay firewall allow chưa?
- [ ] Đã tìm dấu vết service, process, WMI/WinRM, SSH, RDP hoặc truy cập share sau kết nối chưa?
- [ ] Đã kiểm tra change ticket, patching, scanner, backup và bastion audit liên quan chưa?
- [ ] Đã khoanh phạm vi tài sản, danh tính đặc quyền và tài sản trọng yếu chưa?
- [ ] Đã lưu log/PCAP, mapping định danh, timeline và các giới hạn quan sát chưa?
- [ ] Có chủ sở hữu case, mức độ ưu tiên, mốc cập nhật và tiêu chí nâng thành security incident chưa?
- [ ] Các hành động cô lập, thu hồi quyền, chỉnh ACL hoặc khôi phục có được điều phối để tránh làm mất chứng cứ hay gây gián đoạn không?

## 13. Câu hỏi tự kiểm tra

1. Vì sao 20 kết nối TCP/445 từ một máy trạm đến nhiều máy chủ chưa đủ kết luận lateral movement? Bạn sẽ thu thập thêm hai loại chứng cứ gì?
2. Phân biệt tín hiệu *fan-out* và *multi-hop*. Mỗi loại dễ bị nhầm với hoạt động quản trị hợp lệ nào?
3. Trong Active Directory, log 4769 trên DC và 4624 type 3 trên máy đích đóng vai trò khác nhau thế nào khi dựng một bước nhảy?
4. Tại sao kết nối WinRM trên port 5985 từ APP-02 sang DB-01 không chứng minh được APP-02 đã bị chiếm quyền điều khiển?
5. Nếu VPC Flow Logs không cung cấp tên người dùng, bạn phải kết hợp thêm loại log nào để xác định principal thực hiện các thay đổi quản trị?
6. Nêu ba điểm mù thường gặp khi phân tích PCAP trong môi trường có TLS, overlay và NAT.
7. Hãy đề xuất detector phát hiện cả trường hợp kẻ tấn công đi chậm qua chỉ hai máy trong một ngày; bạn sẽ giảm dương tính giả ra sao?

**Điểm cần nhớ:** Phát hiện lateral movement qua network là công việc **liên kết nhiều bằng chứng**: một đường kết nối mới, một danh tính không phù hợp, một phiên xác thực thành công và một hành động từ xa đáng nghi. Chỉ khi ghép các cạnh theo thời gian và xác minh tại đích, đội điều tra mới có thể dựng được đường di chuyển, mức độ ảnh hưởng và cơ sở để ứng phó.
