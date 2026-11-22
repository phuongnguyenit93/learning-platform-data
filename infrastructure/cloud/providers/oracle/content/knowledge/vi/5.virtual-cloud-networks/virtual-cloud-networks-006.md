# Stateful rules, stateless rules và cổng phản hồi

Một kết nối có thể thất bại dù đã mở đúng cổng dịch vụ. Nguyên nhân thường nằm ở chiều phản hồi: gói gửi tới cổng 443 của server không có nghĩa gói trả về cũng đi tới cổng 443 của client.

Trong Oracle Cloud Infrastructure (OCI), security rules của Network Security Groups (NSGs) và security lists có thể hoạt động theo chế độ stateful hoặc stateless. Sự khác nhau nằm ở cách theo dõi luồng và cho phép lưu lượng phản hồi.

Bài học thuộc chương **Mạng Virtual Cloud Network** của module Oracle Cloud Infrastructure. Mục tiêu là đọc được địa chỉ và cổng theo từng chiều, chọn đúng chế độ rule, tránh lỗi chồng lấn và kiểm chứng đường phản hồi khi triển khai Compute, dịch vụ ứng dụng hoặc cơ sở dữ liệu Oracle trong VCN.

## 1. Đọc một luồng trước khi viết rule

Với TCP hoặc UDP, hãy ghi đủ năm thành phần:

~~~text
Protocol
Source IP
Source port
Destination IP
Destination port
~~~

Ví dụ một client gọi HTTPS:

~~~text
Client                                       Server
10.50.1.10:53000  ─────── TCP ───────────▶  10.50.2.20:443
10.50.1.10:53000  ◀────── TCP ────────────  10.50.2.20:443
~~~

Trong ví dụ:

- Client chủ động mở kết nối.
- Server lắng nghe cổng 443.
- Client sử dụng cổng cục bộ 53000 cho kết nối này.
- Khi server trả lời, địa chỉ và cổng của hai đầu đổi vai trò nguồn/đích.

TCP có hai trường source port và destination port để định danh các đầu giao tiếp. Xem [RFC 9293 — TCP Header Format](https://www.rfc-editor.org/rfc/rfc9293.html#section-3.1).

Quan sát tại **VNIC của server**:

| Chiều tại server | Source IP | Source port | Destination IP | Destination port |
| --- | --- | --- | --- | --- |
| Ingress: client gửi yêu cầu | 10.50.1.10 | 53000 | 10.50.2.20 | 443 |
| Egress: server phản hồi | 10.50.2.20 | 443 | 10.50.1.10 | 53000 |

Quan sát tại **VNIC của client**, chính hai gói đó có tên chiều ngược lại: yêu cầu là egress, phản hồi là ingress.

Vì vậy, câu “mở inbound 443” luôn cần thêm câu trả lời: **inbound tại endpoint nào?** Khi kiểm tra rule, không đổi điểm quan sát giữa chừng.

## 2. Stateful và stateless khác nhau ở đâu?

### 2.1. Stateful: cho phép phản hồi dựa trên trạng thái luồng

Rule stateful dùng connection tracking. Khi lưu lượng khởi tạo khớp rule, OCI nhận diện phản hồi thuộc luồng đó và cho phép chiều trả về mà không cần một rule đối xứng riêng tại cùng VNIC. Xem [Security Rules — Stateful Compared to Stateless Rules](https://docs.oracle.com/en-us/iaas/Content/Network/Concepts/securityrules.htm).

Ví dụ tại server:

| Thuộc tính | Giá trị |
| --- | --- |
| Direction | Ingress |
| Mode | Stateful |
| Protocol | TCP |
| Source | 10.50.1.10/32 |
| Source port | All |
| Destination port | 443 |

Với luồng ở phần trước, rule này cho phép yêu cầu vào server. Phản hồi từ server:443 về client:53000 được xử lý bằng trạng thái luồng.

Điều đó **không** đồng nghĩa server được chủ động mở kết nối tới mọi địa chỉ. Ví dụ server mở một kết nối mới từ cổng 54000 tới một API khác trên cổng 443 là một luồng khác, cần điều kiện cho phép phù hợp.

Stateful cũng không tự tạo route, kết nối mạng hoặc tiến trình lắng nghe. Nếu ứng dụng chưa chạy trên cổng 443, rule đúng vẫn chưa đủ để kết nối thành công.

### 2.2. Stateless: từng chiều cần điều kiện cho phép rõ ràng

Rule stateless không cung cấp cơ chế tự cho phép phản hồi dựa trên connection tracking. Để trao đổi hai chiều, cần rule phù hợp ở chiều ngược lại; thiết kế thường dùng một cặp stateless rõ ràng.

Trong API, isStateless=true chọn stateless; false chọn stateful. Xem [AddSecurityRuleDetails](https://docs.oracle.com/en-us/iaas/tools/java/latest/com/oracle/bmc/core/model/AddSecurityRuleDetails.html).

Ví dụ cặp rule tại server cho một lần thử có cổng client cố định:

| Direction | Mode | Peer CIDR | Source port | Destination port |
| --- | --- | --- | --- | --- |
| Ingress | Stateless | Source 10.50.1.10/32 | 53000 | 443 |
| Egress | Stateless | Destination 10.50.1.10/32 | 443 | 53000 |

Điểm quan trọng là dòng egress có **source port 443**, còn destination port là **53000**.

Nếu chỉ tạo egress với destination port 443, rule đó không khớp gói server:443 → client:53000. Nó diễn đạt một loại lưu lượng khác.

### 2.3. Bảng so sánh để lựa chọn

| Nội dung | Stateful | Stateless |
| --- | --- | --- |
| Mô hình quản lý | Theo dõi luồng khớp rule | Xét điều kiện cho phép theo từng chiều |
| Cách thiết kế phản hồi | Dựa vào trạng thái đã ghi nhận | Viết điều kiện chiều trả về |
| Công việc vận hành | Theo dõi khả năng connection tracking | Quản lý cặp rule và phạm vi cổng |
| Điểm dễ sai | Nhầm phản hồi với kết nối mới | Quên đảo source/destination port |
| Cách kiểm chứng | Quan sát kết nối mới và phản hồi | Quan sát gói hai chiều, đối chiếu từng rule |

Đây là lựa chọn ở tầng kiểm soát mạng. Nó không mô tả ứng dụng có giữ session hay không. Một ứng dụng được gọi là “stateless service” vẫn có thể chạy sau các rule stateful.

## 3. Cổng tạm thời và phạm vi phản hồi

### 3.1. Cổng dịch vụ khác với cổng client

Cổng dịch vụ là nơi server lắng nghe, chẳng hạn HTTPS 443 hoặc listener cơ sở dữ liệu trong cấu hình cụ thể. Cổng client thường được hệ điều hành lựa chọn khi ứng dụng mở kết nối và được gọi là **ephemeral port**, hay cổng tạm thời.

Không mặc định mọi client OCI đều dùng cùng một khoảng cổng. Hệ điều hành, cấu hình và ứng dụng có thể làm khoảng thực tế thay đổi.

Trên Linux, có thể đọc cấu hình cấp cổng tự động:

~~~bash
sysctl net.ipv4.ip_local_port_range
~~~

Tài liệu Linux mô tả ip_local_port_range là khoảng dùng để chọn cổng cục bộ cho TCP và UDP. Xem [Linux IP Sysctl](https://docs.kernel.org/networking/ip-sysctl.html).

Khi có client từ internet, đội vận hành server thường không kiểm soát cấu hình cổng của tất cả client. Một khoảng hẹp suy ra từ duy nhất máy thử có thể khiến các client khác thất bại.

### 3.2. Viết rule bằng khoảng đã xác định

Gọi **E** là tập cổng client thực sự sử dụng trong thiết kế. Với server nhận HTTPS từ một nhóm client:

| Rule tại server | Peer | Source port | Destination port |
| --- | --- | --- | --- |
| Ingress stateless | CIDR client | E hoặc All | 443 |
| Egress stateless phản hồi | CIDR client | 443 | E hoặc All |

Chỉ dùng E khi có căn cứ kiểm soát hoặc xác minh nó. Với client không kiểm soát được, có thể cần All ở trường cổng client, đồng thời giới hạn protocol, địa chỉ peer và cổng dịch vụ theo yêu cầu.

**All ở một trường cổng không có nghĩa mọi trường của rule đều mở.** Ví dụ egress TCP, destination là CIDR client và source port 443 vẫn có các điều kiện cụ thể. Tuy nhiên, rule stateless không chứng minh gói khớp điều kiện là phản hồi của một yêu cầu đã nhận.

Một gói bất kỳ đáp ứng cùng điều kiện cũng có thể được tầng rule cho qua. Không dùng source port 443 như bằng chứng xác thực server, phiên TLS hay nguồn gốc nghiệp vụ.

## 4. Khi instance là bên chủ động gọi ra

Một Compute instance thường vừa nhận yêu cầu, vừa gọi API hoặc cơ sở dữ liệu khác. Cần phân tích từng vai trò riêng.

Ví dụ app server gọi API nội bộ:

~~~text
App instance                         API endpoint
10.50.2.20:54000  ────────────────▶  10.50.3.30:443
10.50.2.20:54000  ◀────────────────  10.50.3.30:443
~~~

Tại **VNIC của app instance**:

| Chiều | Source port | Destination port | Peer |
| --- | --- | --- | --- |
| Egress: khởi tạo | 54000 | 443 | Destination 10.50.3.30/32 |
| Ingress: phản hồi | 443 | 54000 | Source 10.50.3.30/32 |

Nếu dùng stateful egress cho yêu cầu, phản hồi được xử lý theo trạng thái tại app VNIC. Nếu dùng stateless, cần cho phép ingress với **source port 443, destination port thuộc tập cổng client**.

Đừng tạo ingress destination port 443 trên app chỉ vì app đang gọi HTTPS. Trong luồng này, app là client; cổng nhận phản hồi là 54000.

Cũng cần kiểm tra endpoint API. Quyền egress ở app không thay cho quyền ingress tại API, và connection tracking ở một đầu không tự cấu hình đầu kia.

### 4.1. Hai VNIC, hai điểm kiểm soát

Với client và server đều là Compute trong VCN, một thiết kế stateful điển hình có:

| Điểm kiểm soát | Lưu lượng khởi tạo cần cho phép |
| --- | --- |
| VNIC client | Egress tới server, destination port dịch vụ |
| VNIC server | Ingress từ client, destination port dịch vụ |

Phản hồi được xử lý theo trạng thái tương ứng ở từng đầu. Nếu một đầu chuyển sang stateless, phải đánh giá lại chiều phản hồi ở chính đầu đó.

Ví dụ ứng dụng gọi Oracle Database cũng áp dụng cách suy luận này: xác định đúng endpoint, cổng listener trong cấu hình triển khai và cổng client thực tế. Không mở một cổng dịch vụ cho mọi subnet chỉ để che lỗi thiếu rule phản hồi.

### 4.2. Load balancer có thể tạo nhiều luồng

Khi có load balancer hoặc proxy, nên vẽ riêng từng chặng:

~~~text
Client ── kết nối A ──▶ Load Balancer
Load Balancer ── kết nối B ──▶ Backend
~~~

Đối với kiểu triển khai có hai kết nối độc lập, kết nối B có địa chỉ và cổng client riêng ở phía backend. Không lấy cổng tạm thời của client ban đầu để viết rule phản hồi cho backend.

Trước khi áp dụng bảng cổng, xác định dịch vụ có kết thúc kết nối, bảo toàn địa chỉ nguồn hay chuyển tiếp theo cơ chế khác. Điều cần ghi nhận là tuple thực tế ở VNIC đang kiểm tra.

## 5. Rule chồng lấn có thể thay đổi cơ chế phản hồi

Nếu một gói khớp cả stateful lẫn stateless rule trong cùng chiều, **stateless được ưu tiên và luồng không được theo dõi theo rule stateful đó**. Xem [Security Rules](https://docs.oracle.com/en-us/iaas/Content/Network/Concepts/securityrules.htm).

Ví dụ tại server:

| Rule | Mode | Source | Protocol | Destination port |
| --- | --- | --- | --- | --- |
| A | Stateful ingress | 10.50.1.10/32 | TCP | 443 |
| B | Stateless ingress | 10.50.0.0/16 | TCP | 443 |

Gói từ 10.50.1.10:53000 tới server:443 khớp cả A và B. Không thể kết luận rằng A sẽ bảo đảm phản hồi tự động.

Nếu không có điều kiện egress phù hợp, yêu cầu có thể tới server nhưng chiều trả về thất bại. Một rule egress khác, kể cả stateful, có thể cho gói trả về đi qua; vì vậy thiết kế phải xét toàn bộ các rule hiệu lực, không chỉ tìm xem “đã có cặp stateless hay chưa”.

Cách quản lý đề xuất:

1. Chọn một cơ chế rõ ràng cho từng nhóm luồng.
2. Kiểm tra các rule rộng có bao trùm rule hẹp không.
3. Ghi rõ lý do nếu phải kết hợp hai chế độ.
4. Kiểm tra bằng kết nối mới sau thay đổi.
5. Không suy luận theo thứ tự hiển thị như một ACL có luật đầu tiên khớp.

### 5.1. Kiểm tra cả security lists lẫn NSGs

Security list gắn ở subnet; NSG gắn vào các VNIC được chọn. Rule của chúng cùng tham gia kiểm soát lưu lượng. Xem [Security Lists](https://docs.oracle.com/en-us/iaas/Content/Network/Concepts/securitylists.htm) và [Network Security Groups](https://docs.oracle.com/en-us/iaas/Content/Network/Concepts/networksecuritygroups.htm).

Ví dụ, NSG mới không có egress nhưng security list của subnet vẫn cho phép egress rộng. Khi đó, một bài thử “xóa rule phản hồi trong NSG” có thể vẫn thành công.

Ngược lại, rule stateless rộng ở một cấu hình khác có thể làm thay đổi giả định tracking. Bản kiểm kê nên gồm mọi security list của subnet và mọi NSG gắn với VNIC đang xét.

## 6. UDP, ICMP và những gói không giống TCP thông thường

### 6.1. UDP vẫn có cổng nguồn và cổng đích

Ví dụ app gửi truy vấn tới một DNS server tự quản trị:

~~~text
App 10.50.2.20:54001  ── UDP ──▶  DNS 10.50.3.53:53
App 10.50.2.20:54001  ◀─ UDP ───  DNS 10.50.3.53:53
~~~

Tại app, rule stateless phản hồi cần ingress từ DNS server, source port 53 và destination port 54001 hoặc tập cổng client phù hợp.

UDP có cấu trúc source/destination port nhưng không có bắt tay TCP. Xem [RFC 768](https://www.rfc-editor.org/rfc/rfc768.html). Connection tracking của firewall là cơ chế riêng; không suy luận rằng UDP bắt buộc dùng stateless.

Ví dụ dùng DNS server tự quản trị để minh họa tuple, không mô tả mọi endpoint DNS đặc biệt của OCI. Nếu ứng dụng cần cả UDP và TCP tới một dịch vụ, phải đánh giá cả hai protocol.

### 6.2. ICMP dùng type/code, không dùng TCP/UDP port

Không viết “mở cổng ICMP”. Với ICMP, điều kiện cần xem là protocol, type, code và địa chỉ nguồn/đích.

Đặc biệt khi dùng stateless với endpoint ngoài VCN, cần bảo đảm thông điệp Path MTU Discovery đi qua. Với IPv4, OCI hướng dẫn cho phép ingress ICMP type 3, code 4; việc chặn thông điệp này có thể gây hiện tượng truyền dữ liệu bị treo. Xem [Hanging Connection](https://docs.oracle.com/en-us/iaas/Content/Network/Troubleshoot/connectionhang.htm).

Đối với IPv6, thông điệp Packet Too Big dùng ICMPv6 type 2, code 0. Xem [Security Lists — IPv6 Traffic](https://docs.oracle.com/en-us/iaas/Content/Network/Concepts/securitylists.htm).

Ping thành công cũng không chứng minh TCP 443 hoạt động. Ping và TCP kiểm tra các loại lưu lượng khác nhau.

### 6.3. Lưu ý gói UDP bị phân mảnh

Chỉ fragment đầu có đầy đủ thông tin cổng để khớp điều kiện TCP/UDP tương ứng; lọc theo cổng có thể làm các fragment tiếp theo bị loại. OCI có hướng dẫn riêng cho UDP phân mảnh, bao gồm việc xem xét All cho source và destination port của các rule liên quan. Xem [Security Rules — Fragmented UDP Packets](https://docs.oracle.com/en-us/iaas/Content/Network/Concepts/securityrules.htm).

Không mở rộng tất cả rule ngay khi thấy timeout. Trước tiên xác định có phân mảnh, lỗi MTU hoặc một vấn đề cổng phản hồi thông thường hay không.

## 7. Thực hành: quan sát sự khác nhau tại server

Phần thực hành dùng hai máy Linux lab trong cùng VCN, có đường đi trực tiếp. Không cần mở dịch vụ thử nghiệm ra internet.

| Thành phần | Cấu hình minh họa |
| --- | --- |
| Client | 10.50.1.10 |
| Server | 10.50.2.20 |
| Dịch vụ thử | HTTP tại TCP 8080 |
| Cổng client cho phép thử | 53000–53009 |
| Điểm thay đổi | NSG gắn với VNIC server |

Dùng HTTP 8080 để quan sát mạng mà không thêm lỗi chứng chỉ TLS. Server phải có sẵn dịch vụ HTTP lắng nghe và OS firewall cho phép đúng lưu lượng lab.

Các giả định cần kiểm tra trước:

- Client có stateful egress tới server:8080.
- Những security lists và NSGs khác không có rule che lấp kết quả.
- Có đường quản trị riêng, không bị thay đổi bởi phép thử.
- Ví dụ không đi qua NAT, proxy hoặc firewall trung gian.
- Nếu môi trường dùng ZPR, các policy liên quan cũng phải cho phép luồng.

### 7.1. Đọc cấu hình hiện tại

Các lệnh OCI CLI sau dùng Bash và principal có quyền phù hợp:

~~~bash
export SERVER_NSG_OCID='ocid1.networksecuritygroup.oc1..replace_lab_nsg'

oci network nsg rules list \
  --nsg-id "$SERVER_NSG_OCID" \
  --all
~~~

Lệnh list cho biết các rule trong NSG được chọn; nó không tự tổng hợp mọi security list và NSG của VNIC. Xem [OCI CLI: NSG rules list](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/network/nsg/rules/list.html).

Ghi lại rule ID trước khi cập nhật để có thể phục hồi đúng cấu hình. Chỉ điều chỉnh tài nguyên lab được giao.

### 7.2. Giai đoạn A: stateful ingress

Cấu hình tại server:

~~~text
Direction:        Ingress
Mode:             Stateful
Protocol:         TCP
Source CIDR:      10.50.1.10/32
Source port:      All
Destination port: 8080
~~~

Từ client:

~~~bash
curl --noproxy '*' \
  --local-port 53000 \
  --connect-timeout 5 \
  --max-time 15 \
  -v http://10.50.2.20:8080/
~~~

Tùy chọn local-port yêu cầu curl dùng cổng cục bộ được chọn; nếu cổng không khả dụng, lệnh có thể thất bại trước khi gửi yêu cầu. Xem [curl manual](https://curl.se/docs/manpage.html#--local-port).

Kết quả mong đợi: nhận phản hồi HTTP mà không cần thêm egress riêng cho phản hồi tại server. Nếu không đạt, kiểm tra listener, OS firewall, rule ở client và đường đi trước khi kết luận về stateful.

### 7.3. Giai đoạn B: stateless ingress, chưa có đường phản hồi

Thay rule ingress lab thành stateless, không để lại rule thử chồng lấn ngoài dự kiến. Chưa thêm egress cho phản hồi server.

Thử lại bằng cổng mới, chẳng hạn 53001. Nếu không có rule nào khác cho phép chiều trả về, client không hoàn tất được trao đổi HTTP.

Dùng một kết nối mới giúp hạn chế nhầm kết quả do phiên còn mở, cổng đang được dùng hoặc trạng thái cũ. Timeout đơn lẻ chưa chứng minh chính xác gói bị loại ở đâu; cần đối chiếu bằng chứng ở phần tiếp theo.

### 7.4. Giai đoạn C: thêm stateless egress phản hồi

Cặp rule mong muốn tại server:

~~~text
Ingress:
  TCP, stateless
  Source 10.50.1.10/32
  Source port All
  Destination port 8080

Egress:
  TCP, stateless
  Destination 10.50.1.10/32
  Source port 8080
  Destination ports 53000-53009
~~~

Khoảng 53000–53009 chỉ phục vụ phép thử có kiểm soát. Nó không phải khoảng ephemeral mặc định chung của OCI.

Payload sau minh họa cách thêm **cả cặp** bằng OCI CLI:

~~~bash
oci network nsg rules add \
  --nsg-id "$SERVER_NSG_OCID" \
  --security-rules '[
    {
      "direction": "INGRESS",
      "protocol": "6",
      "isStateless": true,
      "sourceType": "CIDR_BLOCK",
      "source": "10.50.1.10/32",
      "tcpOptions": {
        "destinationPortRange": {
          "min": 8080,
          "max": 8080
        }
      },
      "description": "Lab HTTP ingress from controlled client"
    },
    {
      "direction": "EGRESS",
      "protocol": "6",
      "isStateless": true,
      "destinationType": "CIDR_BLOCK",
      "destination": "10.50.1.10/32",
      "tcpOptions": {
        "sourcePortRange": {
          "min": 8080,
          "max": 8080
        },
        "destinationPortRange": {
          "min": 53000,
          "max": 53009
        }
      },
      "description": "Lab HTTP replies to controlled client ports"
    }
  ]'
~~~

Protocol 6 là TCP. Không có sourcePortRange ở ingress nghĩa là không giới hạn cổng nguồn bằng trường đó. Cấu trúc dựa trên [AddSecurityRuleDetails](https://docs.oracle.com/en-us/iaas/tools/java/latest/com/oracle/bmc/core/model/AddSecurityRuleDetails.html) và [OCI CLI: NSG rules add](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/network/nsg/rules/add.html).

**Lệnh add thêm rule, không thay thế rule đang có.** Nếu đã giữ ingress từ giai đoạn B, chỉ thêm egress còn thiếu hoặc cập nhật bộ rule theo ID; không chạy cả cặp để vô tình tạo rule trùng.

Thử client với local-port 53002. Kết quả mong đợi là HTTP hoạt động. Sau đó, thử một cổng ngoài khoảng đã cho phép, chẳng hạn 54000: nếu không có đường cho phép khác, phản hồi không khớp egress lab.

Kết thúc thực hành, phục hồi cấu hình đã ghi nhận và dọn tài nguyên lab theo quy trình của bạn.

## 8. Kiểm chứng bằng gói tin, flow logs và metrics

### 8.1. Quan sát tại hai endpoint

Trên server lab, có thể quan sát:

~~~bash
sudo tcpdump -ni any 'host 10.50.1.10 and tcp port 8080'
~~~

Ví dụ diễn giải kết quả:

| Bằng chứng | Cách suy luận ban đầu |
| --- | --- |
| Client phát SYN, server không thấy | Kiểm tra đường đi, rule trước điểm quan sát |
| Server thấy SYN, không tạo SYN-ACK | Kiểm tra listener và OS firewall |
| Server tạo SYN-ACK, client không thấy | Kiểm tra đường phản hồi và rule hai đầu |
| Có phản hồi HTTP nhưng mã lỗi ứng dụng | Tiếp tục điều tra tầng ứng dụng |
| Không bind được cổng client | Kiểm tra cổng cục bộ trước khi xét OCI rules |

Thấy gói phát ra trong tcpdump ở hệ điều hành không bảo đảm nó đã vượt qua mọi điểm kiểm soát mạng sau đó. Vì vậy, kết hợp quan sát hai đầu với dữ liệu OCI.

### 8.2. VCN flow logs

VCN flow logs ghi nhận thông tin lưu lượng được chấp nhận hoặc từ chối theo security lists/NSGs. Có thể dùng để đối chiếu protocol, IP, cổng và hướng của luồng thử. Xem [Flow Logs](https://docs.oracle.com/en-us/iaas/Content/Network/Concepts/vcn-flow-logs.htm).

Trước khi suy luận từ việc “không thấy bản ghi”, xác nhận flow logs và capture filter bao phủ đúng VNIC, thời điểm và loại traffic. Một log ACCEPT ở tầng mạng cũng không chứng minh ứng dụng đã xử lý yêu cầu thành công.

Đối với luồng lab, tìm riêng:

~~~text
10.50.1.10:53002 → 10.50.2.20:8080
10.50.2.20:8080  → 10.50.1.10:53002
~~~

Chỉ xem chiều đầu dễ bỏ sót chính lỗi cổng phản hồi đang cần chẩn đoán.

### 8.3. VNIC metrics và connection tracking

Một số metrics hữu ích trong namespace oci_vcn:

| Metric | Dùng để quan sát |
| --- | --- |
| VnicIngressDropsSecurityList | Gói ingress bị loại do security rules |
| VnicEgressDropsSecurityList | Gói egress bị loại do security rules |
| VnicConntrackUtilPercent | Mức sử dụng bảng connection tracking |
| VnicIngressDropsConntrackFull | Gói ingress bị loại khi bảng tracking đầy |
| VnicEgressDropsConntrackFull | Gói egress bị loại khi bảng tracking đầy |

Xem [VNIC Metrics](https://docs.oracle.com/en-us/iaas/Content/Network/Reference/vnicmetrics.htm). Chọn đúng VNIC và khoảng thời gian tương ứng với phép thử.

Metrics hỗ trợ xác định nhóm nguyên nhân, không thay thế việc đọc rule và tuple. Nếu mức sử dụng tracking tăng cao, đánh giá kiểu kết nối, khả năng tái sử dụng kết nối và nhu cầu hiệu năng trước khi thay đổi mode trên diện rộng.

Không nhầm connection tracking của OCI với bảng conntrack trong hệ điều hành Linux. Quan sát một lớp không tự phản ánh đầy đủ trạng thái của lớp kia.

## 9. Chọn chế độ theo nhu cầu vận hành

Một tiêu chí lựa chọn thực tế:

| Tình huống | Cách tiếp cận đề xuất |
| --- | --- |
| Ứng dụng thông thường, muốn giảm số rule phản hồi | Bắt đầu bằng stateful và giới hạn peer/cổng dịch vụ |
| Lưu lượng lớn, cần đánh giá giới hạn tracking | Đo metrics, lập kế hoạch stateless nếu phù hợp |
| Client có cổng nguồn được kiểm soát | Có thể thiết kế cặp stateless với khoảng cụ thể |
| Client bên ngoài không kiểm soát được | Tránh giả định khoảng cổng hẹp từ máy thử |
| Kết nối nhiều chặng qua proxy hoặc load balancer | Phân tích từng luồng và điểm kiểm soát |
| Dịch vụ dùng nhiều protocol | Ghi rõ TCP/UDP/ICMP và yêu cầu phản hồi từng loại |

Đây là hướng thiết kế, không phải cam kết rằng stateless luôn nhanh hơn hoặc stateful luôn đủ cho mọi tải. Lựa chọn còn liên quan đến khả năng vận hành, số lượng kết nối và phạm vi rule phải quản lý.

Trạng thái theo dõi có vòng đời; sau thời gian không hoạt động, một luồng có thể không còn bản ghi tracking. Không coi rule stateful là quyền phản hồi vô hạn. Khi gặp lỗi sau thời gian idle, xem thêm timeout, cơ chế kết nối lại và các thiết bị trung gian. Xem [Security Rules — Connection Tracking Details](https://docs.oracle.com/en-us/iaas/Content/Network/Concepts/securityrules.htm).

Đối với hệ thống cần sẵn sàng cao, thay đổi mode nên có phạm vi thử nghiệm, phép đo trước/sau và cách phục hồi. Một lỗi rule phản hồi có thể làm gián đoạn cả API ứng dụng lẫn kết nối tới cơ sở dữ liệu dù tài nguyên vẫn ở trạng thái running.

## 10. Các lỗi cần nhận diện nhanh

| Nhầm lẫn | Cách sửa suy luận |
| --- | --- |
| Mở cổng 443 thì cả hai chiều đều có destination 443 | Viết lại tuple cho chiều trả về |
| Stateful ingress cho phép server gọi ra mọi nơi | Phân biệt phản hồi với luồng mới do server khởi tạo |
| Stateless chỉ cần rule chiều yêu cầu | Xác định điều kiện cho phép chiều phản hồi |
| Khoảng cổng Linux trên một máy áp dụng cho mọi client | Kiểm tra OS, cấu hình và ứng dụng thực tế |
| Rule stateful hẹp thắng stateless rộng | Kiểm tra ưu tiên stateless khi cùng khớp |
| NSG không có egress nên chắc chắn gói bị chặn | Kiểm tra toàn bộ security lists và NSGs hiệu lực |
| Ping được thì HTTPS phải hoạt động | Kiểm tra đúng protocol và cổng dịch vụ |
| Đổi mode rồi thử lại trên kết nối cũ là đủ | Tạo kết nối mới, ghi nhận tuple và thời điểm |
| Gói ACCEPT có nghĩa nghiệp vụ thành công | Đối chiếu listener, TLS và kết quả ứng dụng |

Khi bàn giao một bộ rule, cần có ít nhất: bên khởi tạo, hai endpoint, protocol, cổng dịch vụ, tập cổng client, mode của rule và cách kiểm tra hai chiều. Với stateless, phải giải thích được rule nào cho phép gói phản hồi và vì sao phạm vi đó phù hợp với các client thực tế.
