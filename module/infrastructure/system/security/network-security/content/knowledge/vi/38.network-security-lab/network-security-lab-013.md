# Kiểm thử các đường truy cập hợp lệ và bị chặn

## 1. Mục tiêu của bài thực hành

Trong chương **Dự án thực hành bảo mật mạng** của module **SECURITY_NETWORK_SECURITY**, bài này hướng dẫn kiểm chứng một câu hỏi quan trọng của kiến trúc phòng thủ: **kết nối cần thiết có được cho phép, còn kết nối trái chính sách có thực sự bị từ chối tại đúng điểm kiểm soát hay không?**

Kiểm thử truy cập không dừng lại ở việc ping thành công hoặc thấy một rule firewall trên màn hình. Người vận hành cần liên kết **chính sách mong đợi → đường đi thực tế → kết quả kết nối → bằng chứng enforcement → dữ liệu giám sát**. Một rule cho phép hợp lệ nhưng bị route sai vẫn làm ứng dụng ngừng hoạt động. Một rule từ chối chính xác trên firewall A cũng không đủ bảo đảm an toàn nếu có đường đi không qua firewall A.

Bài thực hành kết hợp các năng lực của bảo mật mạng: mô hình hóa ranh giới tin cậy, phân đoạn mạng, firewall/ACL, VPN/ZTNA, IDS/IPS, bảo vệ DNS, xác thực kết nối, giám sát lưu lượng và đặc điểm triển khai trong cloud/Kubernetes. Trọng tâm là **kiểm thử chính sách truy cập theo những luồng cụ thể**, không phải khai thác hoặc vượt qua một hệ thống bên ngoài.

Sau bài học, người học có thể:

1. Xác định luồng **allow**, **deny**, đường bị giới hạn theo định danh và các tình huống ngoại lệ được phê duyệt.
2. Xây dựng ma trận kiểm thử từ asset, zone, giao thức, port, danh tính và đường mạng thực tế.
3. Thiết lập một lab Linux network namespace cô lập, có router và firewall stateful, để thử cả kết nối hợp lệ lẫn không hợp lệ.
4. Phân biệt *kết quả kết nối* với *bằng chứng firewall đã chặn hoặc cho phép*, tránh kết luận sai khi dịch vụ đích không hoạt động.
5. Thu thập log/counters, đối chiếu packet path và nhận diện routing/NAT, DNS, VPN hoặc telemetry làm nhiễu kết quả.
6. Viết báo cáo kiểm thử có ground truth, tiêu chí đạt/trượt, mức độ rủi ro, owner, hướng sửa và bước kiểm thử hồi quy.

**Quy tắc phạm vi:** chỉ thực hiện trên mạng, máy, workload và tài khoản đã được cho phép. Các địa chỉ trong ví dụ thuộc các dải dành cho tài liệu (RFC 5737): `192.0.2.0/24`, `198.51.100.0/24` và `203.0.113.0/24`. Lab tạo các network namespace mới trên máy Linux thử nghiệm; không sử dụng các địa chỉ đó làm mục tiêu trên Internet.

## 2. Tư duy kiểm thử: chứng minh hai chiều của một chính sách

Một kết quả tốt phải chứng minh **hai yêu cầu độc lập**:

- **Đúng quyền (availability of authorized path):** người dùng/workload được phép có thể tới dịch vụ đúng giao thức và cổng, trên đường đi hợp lệ, được xác thực và ghi nhận theo chính sách.
- **Đúng ranh giới (enforcement of forbidden path):** nguồn không được phép không thể truy cập tài nguyên nằm ngoài quyền, kể cả từ một segment, identity hoặc route khác thuộc phạm vi phải kiểm thử.

Các ví dụ:

| Quy tắc | Kiểm thử thuận (positive test) | Kiểm thử cấm (negative test) |
| --- | --- | --- |
| APP được gọi API của DATA trên TCP 443 | APP → API:443 có kết nối và phản hồi hợp lệ | APP → cổng quản trị của DATA bị từ chối |
| GUEST không được vào mạng nội bộ | GUEST → Internet theo chính sách được phép | GUEST → API nội bộ bị chặn |
| Nhân viên có quyền truy cập qua ZTNA | Identity hợp lệ, thiết bị đạt posture → ứng dụng được phép | Identity không có quyền → ứng dụng bị từ chối |
| DNS nội bộ chỉ dùng resolver quản lý | Query qua resolver nội bộ thành công | Truy vấn ra resolver không được phép không đi qua đường ngoài thiết kế |
| Pod frontend chỉ được kết nối backend | frontend → backend đúng port hoạt động | namespace không được phép → backend bị từ chối |

Phải **tách ba loại bằng chứng**:

1. **Bằng chứng tạo phép thử:** nguồn thật sự đã gửi thử nghiệm, đích và dịch vụ thử đang hoạt động, timestamp có thể đối chiếu.
2. **Bằng chứng quyết định:** enforcement point đã xử lý gói hoặc request theo rule/policy nào; có log, counter hoặc trace phù hợp.
3. **Bằng chứng tác động:** luồng hợp lệ thực sự hoạt động ở tầng ứng dụng, luồng cấm không đến được dịch vụ; không có đường vòng chưa được đánh giá.

Vắng kết nối không tự động chứng minh firewall đã chặn; có thể DNS sai, server down, route không tồn tại hoặc TLS thất bại. Ngược lại, `TCP connected` chưa chứng minh API trả kết quả đúng hay tài khoản đã được ủy quyền.

## 3. Phân biệt các lớp truy cập

| Lớp | Câu hỏi phải trả lời | Công cụ hoặc bằng chứng |
| --- | --- | --- |
| L2 / truy nhập | Thiết bị vào đúng VLAN/SSID, NAC và 802.1X có cấp quyền? | Switch/AP/NAC logs, VLAN, interface |
| L3 / route | Gói có route cả chiều đi và về? | Route table, traceroute có giới hạn, flow logs |
| L3–L4 / firewall | Source/destination/protocol/port có đúng rule, state và zone? | Firewall decision, ACL hit count, NAT/session |
| L4 / transport | TCP handshake hoặc trao đổi UDP phù hợp có xảy ra? | `curl`, `nc`, connection metadata, capture được phép |
| TLS / PKI | Server identity, chain, SNI, mTLS và client certificate hợp lệ? | TLS handshake, certificate, authentication logs |
| Application | HTTP/API/DB thực hiện đúng chức năng và quyền nghiệp vụ? | Health check, request ID, application logs |
| Telemetry / detection | Sự kiện có đến hệ thống giám sát, alert có chất lượng? | SIEM, NDR/IDS, DNS logs, correlation ID |

Một phép thử cần xác định lớp được kiểm tra. Ví dụ một negative test ở firewall có thể kỳ vọng **drop SYN**. Nhưng nếu firewall được thiết kế **reject TCP** và client thấy `connection refused`, đây cũng có thể là deny hợp lệ nếu bằng chứng chính sách xác nhận. Không nên dùng duy nhất mã lỗi client làm tiêu chí chấm.

## 4. Đặt phạm vi, điều kiện dừng và trách nhiệm

Trước khi triển khai lab hoặc một cuộc kiểm thử trên staging, lập hồ sơ ngắn:

| Trường | Ví dụ trong bài |
| --- | --- |
| Mã bài / test run | `LAB-ACCESS-013-R01` |
| Môi trường | Máy Linux thực hành, namespace cô lập; không nối Internet |
| Chủ sở hữu | Người học và người quản trị host lab |
| Mục đích | Kiểm thử rule cho CLIENT vào WEB, GUEST không vào WEB |
| Nguồn được phép | `lab-client`, `lab-guest` |
| Đích | `lab-server`, HTTP cổng 8080 |
| Công cụ | `iproute2`, `nftables`, `curl`, Python 3 HTTP server |
| Giới hạn | Kết nối đơn lẻ, không quét cổng, không tải lớn |
| Thời điểm | Ghi giờ UTC trước và sau mỗi phép thử |
| Dừng khi | Host lab có dấu hiệu ảnh hưởng kết nối thật, CPU/bộ nhớ bất thường hoặc ngoài phạm vi |
| Khôi phục | Dừng HTTP server và xóa riêng các namespace lab đã tạo |

Các bước cấu hình bên dưới yêu cầu quyền `sudo` và Linux hỗ trợ network namespace, veth, conntrack/nftables. **Chỉ thực hiện trên host lab dành riêng**; không dùng các ví dụ như câu lệnh thay đổi firewall của máy sản xuất. Nếu không có quyền quản trị hoặc môi trường không hỗ trợ, có thể làm phần thiết kế, bảng expected/observed và kiểm tra log tổng hợp mà không cần chạy lab.

### 4.1. Mục tiêu bảo mật cần có người xác nhận

- Ai quyết định nhóm CLIENT có thể vào WEB?
- Vì sao GUEST phải bị ngăn?
- Kiểm soát ở đâu và liệu có nhánh khác không qua nó?
- Khi rule sai, ai được sửa, ai phê duyệt và kiểm chứng hồi quy?
- Log có đủ để SOC phát hiện truy cập ngoài chính sách không?

Trong môi trường thật, những câu hỏi này thuộc policy owner, network/platform owner, application owner, SOC và risk owner theo RACI của tổ chức. Trong lab, người học đóng vai các bên nhưng vẫn ghi trách nhiệm tương ứng.

## 5. Thiết kế topology lab cô lập

Ta tạo bốn network namespace trong **một máy Linux**, kết nối qua ba cặp veth:

- `lab-client`: mô phỏng máy ứng dụng được phép truy cập.
- `lab-guest`: mô phỏng mạng khách, không được phép truy cập máy chủ nội bộ.
- `lab-server`: máy chủ HTTP thử nghiệm.
- `lab-router`: router ba interface, đồng thời chạy firewall stateful.

~~~mermaid
flowchart LR
    C["lab-client\n192.0.2.10/24"] -->|"c0 ⇄ rc0"| R["lab-router\nnftables forward"]
    G["lab-guest\n198.51.100.10/24"] -->|"g0 ⇄ rg0"| R
    R -->|"rs0 ⇄ s0"| S["lab-server\n203.0.113.20/24\nHTTP :8080"]
    R --> L["Counters + flow evidence"]
    L --> O["Người kiểm thử / SOC"]
~~~

Bảng địa chỉ:

| Namespace | Interface | IPv4 | Gateway |
| --- | --- | --- | --- |
| lab-client | c0 | 192.0.2.10/24 | 192.0.2.1 |
| lab-router | rc0 | 192.0.2.1/24 | Không cần |
| lab-guest | g0 | 198.51.100.10/24 | 198.51.100.1 |
| lab-router | rg0 | 198.51.100.1/24 | Không cần |
| lab-server | s0 | 203.0.113.20/24 | 203.0.113.1 |
| lab-router | rs0 | 203.0.113.1/24 | Không cần |

**Mô hình policy:** chỉ cho phép `lab-client` vào `lab-server:8080/tcp`. Kết nối `lab-guest → lab-server:8080` phải bị chặn. Tất cả forwarding khác mặc định bị chặn, nhưng gói phản hồi của những kết nối đã được cho phép phải đi qua.

Đường ra không có NAT/Internet gateway. Các namespace chỉ kết nối với nhau qua router namespace trong phạm vi mô hình. Đây là một mô hình thu nhỏ để hiểu segmentation; nó không mô phỏng đầy đủ bảo mật Wi-Fi, cloud, VPN hoặc danh tính thực tế.

## 6. Xây dựng môi trường Linux network namespace

Đọc trước toàn bộ các lệnh và xác nhận trên host không có namespace hoặc interface trùng tên. Chỉ tạo tên đã chọn cho bài lab. Các ví dụ dưới đây được thiết kế để thực hiện tuần tự trong terminal của host lab.

### 6.1. Kiểm tra điều kiện

~~~bash
# Trên host Linux dành riêng cho lab
ip -V
nft --version
python3 --version
curl --version

# Kiểm tra trước khi tạo, tránh trùng tên của lab đang chạy
ip netns list
ip link show
~~~

Cần cài đặt `iproute2`, `nftables`, `curl` và `python3` theo cơ chế quản lý gói hợp lệ của môi trường lab; không thay đổi firewall toàn host hay chính sách phân đoạn mạng công ty.

### 6.2. Tạo bốn namespace

~~~bash
sudo ip netns add lab-client
sudo ip netns add lab-guest
sudo ip netns add lab-server
sudo ip netns add lab-router
~~~

Với host dùng chung, không chọn các tên này nếu đã tồn tại. Không xóa namespace của ai khác để giải phóng tên.

### 6.3. Tạo ba kết nối veth

~~~bash
# CLIENT <-> ROUTER
sudo ip link add c0 type veth peer name rc0
sudo ip link set c0 netns lab-client
sudo ip link set rc0 netns lab-router

# GUEST <-> ROUTER
sudo ip link add g0 type veth peer name rg0
sudo ip link set g0 netns lab-guest
sudo ip link set rg0 netns lab-router

# SERVER <-> ROUTER
sudo ip link add s0 type veth peer name rs0
sudo ip link set s0 netns lab-server
sudo ip link set rs0 netns lab-router
~~~

Các interface `rc0`, `rg0`, `rs0` cùng nằm trong `lab-router`; `c0`, `g0`, `s0` nằm ở namespace tương ứng.

### 6.4. Cấp IP và bật interface

~~~bash
sudo ip -n lab-client addr add 192.0.2.10/24 dev c0
sudo ip -n lab-router addr add 192.0.2.1/24 dev rc0

sudo ip -n lab-guest addr add 198.51.100.10/24 dev g0
sudo ip -n lab-router addr add 198.51.100.1/24 dev rg0

sudo ip -n lab-server addr add 203.0.113.20/24 dev s0
sudo ip -n lab-router addr add 203.0.113.1/24 dev rs0

sudo ip -n lab-client link set lo up
sudo ip -n lab-client link set c0 up
sudo ip -n lab-guest link set lo up
sudo ip -n lab-guest link set g0 up
sudo ip -n lab-server link set lo up
sudo ip -n lab-server link set s0 up

sudo ip -n lab-router link set lo up
sudo ip -n lab-router link set rc0 up
sudo ip -n lab-router link set rg0 up
sudo ip -n lab-router link set rs0 up
~~~

### 6.5. Khai báo đường định tuyến

~~~bash
sudo ip -n lab-client route add default via 192.0.2.1
sudo ip -n lab-guest route add default via 198.51.100.1
sudo ip -n lab-server route add default via 203.0.113.1

# Chỉ bật chuyển tiếp bên trong namespace lab-router
sudo ip netns exec lab-router sysctl -w net.ipv4.ip_forward=1
~~~

Bật `ip_forward` trong `lab-router` không có nghĩa đã cho phép luồng qua firewall. Route quyết định **đường đi**, còn nftables quyết định **quyền đi qua**. Cả hai điều kiện đều cần khi kiểm tra allow/deny.

### 6.6. Kiểm tra topology trước khi đặt firewall

~~~bash
sudo ip -n lab-client address show
sudo ip -n lab-client route
sudo ip -n lab-guest route
sudo ip -n lab-server route
sudo ip -n lab-router address show

# Chỉ kiểm tra kết nối tới gateway cùng mạng của client
sudo ip netns exec lab-client ping -c 2 192.0.2.1
sudo ip netns exec lab-guest ping -c 2 198.51.100.1
~~~

Nếu client không ping được **gateway trên link riêng**, kiểm tra interface, địa chỉ và link. Không nên bắt đầu sửa firewall forwarding khi link tại chỗ chưa hoạt động. Ping ở bước này được dùng trong lab vì gateway do chính ta quản lý; ở mạng thật ICMP có thể bị chặn theo chính sách.

## 7. Áp chính sách firewall theo nguyên tắc least privilege

Ta sử dụng **nftables trong namespace `lab-router`**. Chỉ có một rule cho phép TCP 8080 từ CLIENT tới SERVER, rule explicit deny cho GUEST và rule cho luồng đã được thiết lập. Mọi forwarding còn lại bị drop.

**Lưu ý:** đây là cấu hình dành riêng cho namespace thử nghiệm; không áp lên host firewall của máy thật.

~~~bash
sudo ip netns exec lab-router nft -f - <<'NFT'
table inet lab_acl {
  chain forward {
    type filter hook forward priority 0; policy drop;

    # Phản hồi của kết nối đã được cho phép
    ct state established,related counter accept

    # Chỉ CLIENT được mở kết nối mới tới WEB:8080
    iifname "rc0" oifname "rs0" ip saddr 192.0.2.10 ip daddr 203.0.113.20 tcp dport 8080 ct state new counter accept

    # Luồng GUEST -> WEB:8080 phải bị chặn, có counter riêng
    iifname "rg0" oifname "rs0" ip saddr 198.51.100.10 ip daddr 203.0.113.20 tcp dport 8080 counter drop

    # Những luồng forwarding khác bị chặn mặc định
    counter drop
  }
}
NFT
~~~

**Đặc điểm quan trọng:**

- Rule `ct state established,related` cho phép gói thuộc phiên đã được thiết lập và các gói liên quan đi chiều ngược lại, tránh phá vỡ những phiên hợp lệ.
- Rule `ct state new` cho CLIENT chỉ áp với nguồn, đích, port và interface xác định.
- Rule deny của GUEST được đặt trước rule catch-all để có counter riêng; tất cả các luồng khác vẫn bị chặn.
- Chain `forward` xử lý gói **đi xuyên qua router**. Traffic tới chính các địa chỉ của `lab-router` thuộc hook `input`, không được bài lab này dùng để chứng minh policy forwarding.
- `counter` giúp xem số packet/byte match rule. Nó không phải log chứa đầy đủ danh tính một flow; khi cần truy vết riêng phải kết hợp capture/log có phạm vi.
- State tracking trong netfilter là thuộc tính của namespace hiện tại. Các giao thức không stateful như UDP có cách quan sát khác TCP.

Kiểm tra rule đã nạp:

~~~bash
sudo ip netns exec lab-router nft -a list chain inet lab_acl forward
~~~

Nếu nft không có hoặc kernel không hỗ trợ, **dừng phần thực thi và ghi giới hạn môi trường**. Không thay bằng `flush ruleset` trên host vì có thể tác động mạng thật.

## 8. Tạo dịch vụ canary hợp lệ

Mở **Terminal A** trên cùng host lab, giữ terminal chạy trong suốt bài kiểm thử:

~~~bash
sudo ip netns exec lab-server \
  python3 -m http.server 8080 --bind 203.0.113.20
~~~

Python HTTP server chỉ phục vụ nội dung thư mục làm việc, vì vậy hãy chạy từ một thư mục lab **không chứa dữ liệu riêng tư hoặc file nhạy cảm**. Trong lab nghiêm túc, nên tạo một thư mục rỗng chuyên dụng trước khi khởi động; lệnh trên không phù hợp để mở công khai thư mục của người dùng.

**Kỳ vọng:** server lắng nghe tại 203.0.113.20:8080 trong `lab-server`; không có kết nối từ Internet. Kiểm tra listener và khả năng đáp ứng tại chính namespace server bằng một terminal khác:

~~~bash
sudo ip netns exec lab-server ss -lnt
sudo ip netns exec lab-server \
  curl --head --max-time 5 http://203.0.113.20:8080/
~~~

Một phản hồi HTTP 200 hoặc mã thành công phù hợp với nội dung phục vụ chứng minh canary đang hoạt động tại thời điểm thử. Nếu canary không phục vụ được, **không chấm negative test là thành công**, vì timeout có thể đến từ lỗi dịch vụ.

Có thể sử dụng service HTTP stub nội bộ khác nếu môi trường không có Python 3; phải ghi rõ endpoint và sức khỏe dịch vụ trước mỗi loạt test.

## 9. Lập ma trận kiểm thử trước khi chạy

Mẫu tối thiểu cho topology đã cấu hình:

| Test ID | Source | Destination | Protocol | Expected | Lý do |
| --- | --- | --- | --- | --- | --- |
| T01 | lab-client (192.0.2.10) | lab-server:8080 | TCP/HTTP | **ALLOW** | Luồng ứng dụng đã phê duyệt |
| T02 | lab-guest (198.51.100.10) | lab-server:8080 | TCP/HTTP | **DENY** | Guest không có quyền truy cập nội bộ |
| T03 | lab-client | lab-guest:8080 | TCP | **DENY** | Không có rule cho đường giữa hai vùng |
| T04 | lab-client | lab-server:8080 | TCP/HTTP phản hồi | **ALLOW, stateful** | Gói trả lời thuộc phiên T01 |
| T05 | lab-server | lab-client:8080 | TCP phiên khởi tạo mới | **DENY** | Không có quyền khởi tạo ngược |
| T06 | lab-client | lab-server:8080 | TCP/HTTP sau chỉnh rule hợp lệ | **ALLOW** | Kiểm tra hồi quy |

**Điều kiện chấm:** chỉ T01, T02 là phép kiểm thử hoàn chỉnh sẵn sàng chạy ngay với canary hiện tại; T03 và T05 cần có **listener/flow canary bổ sung** ở đích nếu muốn phân biệt firewall deny với “không có dịch vụ”. T04 được chứng minh gián tiếp bằng response của T01 và counter `established,related`; T06 dành cho một thay đổi được duyệt trong lab. Không ghi PASS cho T03/T05 chỉ vì timeout khi chưa có listener.

Mỗi test phải ghi: execution ID, UTC, source identity/IP, destination IP/port, expected decision, actual client result, firewall counter/event, chứng cứ phía server và nhận định cuối cùng.

## 10. Chạy positive test: CLIENT phải truy cập WEB được

Từ **Terminal B** trên host lab:

~~~bash
# Ghi trạng thái counter trước khi thử
sudo ip netns exec lab-router nft list chain inet lab_acl forward

# Gửi HTTP HEAD request từ nguồn được phép
sudo ip netns exec lab-client \
  curl --head --connect-timeout 3 --max-time 8 \
  http://203.0.113.20:8080/

# Đọc counter sau phép thử
sudo ip netns exec lab-router nft list chain inet lab_acl forward
~~~

**Kỳ vọng kỹ thuật:**

1. Client thiết lập TCP với server:8080 qua `lab-router`.
2. Firewall match rule allow cụ thể từ `rc0` sang `rs0`.
3. Gói phản hồi được phép bởi rule `ct state established,related`.
4. Canary nhận request; client nhận HTTP response hợp lệ.
5. Counter allow tăng so với trước phép thử; counter established có thể tăng do các gói trả lời/tiếp diễn.

**Không kết luận chỉ từ `curl` exit code.** Nếu HTTP trả 404 nhưng TCP/TLS có kết nối, test tầng vận chuyển có thể thành công; đối với tiêu chí ứng dụng thì phải đánh giá lại endpoint. Ở đây dùng `http.server` và đường dẫn `/` nên kỳ vọng response thành công khi thư mục phục vụ tồn tại và có quyền đọc.

Một bản ghi kết quả:

~~~yaml
test_id: T01
execution_id: LAB-ACCESS-013-T01-001
source: lab-client
destination: 203.0.113.20:8080
expected: ALLOW
observed_transport: CONNECTED
observed_application: HTTP_SUCCESS
enforcement_rule: client-to-server-8080-allow
rule_counter_increased: true
server_received_request: true
result: PASS
~~~

Các giá trị trong YAML là **ví dụ minh họa**, không phải kết quả đã chạy trên môi trường người học.

## 11. Chạy negative test: GUEST không được truy cập WEB

Đầu tiên xác nhận canary vẫn hoạt động bằng phép thử tại `lab-server` hoặc T01. Sau đó thực hiện:

~~~bash
sudo ip netns exec lab-router nft list chain inet lab_acl forward

sudo ip netns exec lab-guest \
  curl --head --connect-timeout 3 --max-time 8 \
  http://203.0.113.20:8080/

sudo ip netns exec lab-router nft list chain inet lab_acl forward
~~~

Vì firewall dùng **drop**, client thường thấy timeout. Nếu policy dùng **reject**, phản hồi lỗi có thể khác; tiêu chí chính là *không thiết lập phiên truy cập trái chính sách* và có bằng chứng enforcement tương ứng.

**Cách xác nhận T02 đúng:**

- T01 vẫn thành công, cho thấy server không chết.
- `lab-guest` có IP, interface và route hợp lệ tới router, nên lỗi không do mất kết nối nội bộ.
- Counter trên rule deny `rg0 → rs0`, source 198.51.100.10, destination 203.0.113.20:8080 tăng khi T02 chạy.
- HTTP server không ghi nhận request T02.
- Không có đường thay thế ngoài `lab-router` trong topology đã chốt.

Khi các bằng chứng khớp nhau, đánh giá **PASS (expected DENY)**. Nếu client timeout nhưng rule deny counter không tăng, ưu tiên kiểm tra route, source address, interface, nft chain, rule matching và trạng thái phép thử trước khi tuyên bố đã chặn đúng.

Ví dụ một hồ sơ thất bại:

~~~yaml
test_id: T02
execution_id: LAB-ACCESS-013-T02-001
source: lab-guest
destination: 203.0.113.20:8080
expected: DENY
observed_client: CONNECT_TIMEOUT
deny_rule_counter_increased: false
server_received_request: false
result: INCONCLUSIVE
next_check: Verify source routing, nft policy matching and canary health
~~~

Điểm học quan trọng: một sự cố routing hoặc kết nối đứt cũng làm client thất bại, nhưng **không chứng minh cơ chế segmentation hoạt động đúng**.

## 12. Thử kết nối phản hồi: stateful firewall có đủ không?

Stateful firewall không chỉ quyết định request đầu tiên; nó cần cho phép các gói phản hồi của một phiên đã được chấp nhận. Trong lab này, rule `ct state established,related` được đặt trước rule allow để xử lý luồng chiều ngược.

Khi chạy T01:

- SYN đầu tiên từ CLIENT đến SERVER được xử lý bởi rule new TCP/8080.
- Gói phản hồi SYN-ACK từ SERVER về CLIENT thuộc phiên đã được theo dõi và được accept theo state.
- Các gói HTTP tiếp theo được truyền qua dựa trên trạng thái phiên.

Nếu rule allow tăng mà client vẫn timeout, kiểm tra counters `established,related`, route chiều về, service, conntrack và lỗi interface. Một rule allow cho SYN không chứng minh đường trả lời hoạt động.

Để quan sát mà không thay đổi policy, trong môi trường lab được phép:

~~~bash
sudo ip netns exec lab-router nft -a list chain inet lab_acl forward
sudo ip -n lab-router -s link show rc0
sudo ip -n lab-router -s link show rs0
~~~

**Lưu ý:** gói TCP đã đi qua một router chưa chắc mọi bản ghi phản hồi đều được hiển thị trong một bộ log tập trung. Rule counter là dữ liệu cục bộ; nếu mục tiêu lab mở rộng sang SOC thì cần kiểm tra đường thu thập telemetry riêng.

## 13. Nâng cấp bài lab: chứng minh một cổng bị chặn dù dịch vụ đang mở

Một lỗi thử nghiệm phổ biến là kết luận “port 9090 được chặn” khi thực chất server không hề lắng nghe port 9090. Để làm đúng, mở **Terminal C** và tạo thêm một HTTP listener trên máy chủ, ở cổng 9090:

~~~bash
sudo ip netns exec lab-server \
  python3 -m http.server 9090 --bind 203.0.113.20
~~~

Trên host lab, từ một terminal khác kiểm tra canary mới hoạt động ngay bên trong namespace đích:

~~~bash
sudo ip netns exec lab-server \
  curl --head --max-time 5 http://203.0.113.20:9090/
~~~

Tiếp theo, từ CLIENT thử kết nối 9090:

~~~bash
sudo ip netns exec lab-client \
  curl --head --connect-timeout 3 --max-time 8 \
  http://203.0.113.20:9090/
~~~

Firewall không có rule cho phép cổng 9090, vì thế kết nối mới phải match **catch-all drop**. Dùng counter và kết quả tại server để xác nhận:

| Quan sát | Ý nghĩa |
| --- | --- |
| Server:9090 trả lời local | Đích thực sự lắng nghe và sẵn sàng |
| Client:8080 thành công | Route và allow rule cho luồng hợp lệ vẫn tốt |
| Client:9090 không nhận kết nối | Luồng bị từ chối theo kỳ vọng |
| Counter catch-all drop tăng | Có bằng chứng enforcement cho nhánh cấm |
| Server không ghi request từ CLIENT:9090 | Phù hợp với quyết định drop trên router |

Với cổng 9090, nên dùng kịch bản `T07` riêng để không thay đổi ý nghĩa của T01–T06. Nếu vì thiếu route hoặc listener mà client thất bại, phải chấm **INVALID_TEST** hoặc **INCONCLUSIVE** tùy bằng chứng, không ghi PASS.

## 14. Quan sát gói và tránh kết luận sai khi mất log

Trong một mạng nhỏ như lab, có thể quan sát counters và, nếu được phép, capture có giới hạn tại namespace router. Việc capture có thể thu địa chỉ và metadata nhạy cảm trong hệ thống thật; trong ví dụ chỉ dùng canary do người học sở hữu.

~~~bash
# Trên host lab: xem packet tại router phía GUEST, tối đa 30 gói
sudo ip netns exec lab-router \
  tcpdump -ni rg0 -c 30 -s 96 \
  'host 203.0.113.20 and tcp port 8080'
~~~

Một capture tại interface `rg0` có thể cho thấy SYN từ GUEST **đã tới router**. Nếu firewall drop trước khi gửi ra `rs0`, phía server không nhận được SYN; có thể đối chiếu bằng capture thứ hai tại `rs0` hoặc counter đúng rule. Tuy nhiên:

- Vắng gói tại một interface chưa chứng minh không có kết nối; có thể test không chạy hoặc capture sai interface.
- Capture không thay thế kết quả rule ID/decision, nhất là khi hệ thống có nhiều tầng NAT, proxy hoặc stateful firewall.
- Nếu capture bắt đầu sau thời điểm request, sự kiện có thể đã trôi qua.
- Không có telemetry SIEM không đồng nghĩa firewall không chặn; đây có thể là lỗi pipeline/logging riêng.
- Counter có thể tăng do lưu lượng nền nếu lab không thật sự cô lập; cần ghi thời điểm và chênh lệch trước/sau.

Trong production, thường ưu tiên firewall deny log, flow log, session table và distributed tracing trước khi yêu cầu PCAP.

## 15. Kiểm tra DNS để tránh chấm sai lỗi truy cập

Bài lab cơ bản dùng IP trực tiếp để giảm biến số. Nhưng trong ứng dụng thực, người dùng thường truy cập qua FQDN. Kiểm thử theo hostname bổ sung lớp bảo vệ DNS và các rủi ro DNS split-horizon, resolver không đúng view hoặc cached record.

Giả sử chính sách dự kiến:

- `app.internal.example.test` phân giải đến máy chủ WEB được phép.
- CLIENT dùng resolver nội bộ; GUEST không được giải phân giải tài nguyên nhạy cảm theo thiết kế.
- Việc **được trả về một IP** không có nghĩa được phép kết nối TCP tới IP đó.

Quy trình:

1. Kiểm tra resolver và câu trả lời DNS từ đúng network context.
2. Xác nhận A/AAAA và TTL, đối chiếu IP sau phân giải với đích nằm trong policy.
3. Chạy test TCP/HTTP qua hostname và lưu mapping hostname → IP tại thời điểm kiểm thử.
4. Đọc DNS log và firewall log riêng. Với DNS security, có thể cần thử một domain canary nằm trong policy block để chứng minh rule chặn tên miền.
5. Nếu DNS thất bại, không lấy HTTP timeout làm bằng chứng firewall deny. Phân loại **DNS_FAILURE** hoặc **INVALID_TEST** cho mục tiêu kiểm thử firewall.

Ví dụ đối chứng read-only trên một Linux host lab có resolver được cấu hình:

~~~bash
getent ahosts app.internal.example.test
resolvectl query app.internal.example.test
~~~

**Không bắt buộc** triển khai DNS server cho lab namespace ở phần này. Trường hợp không có DNS, ghi rõ “network access control tested by destination IP only”. Việc công bố phạm vi chính xác quan trọng hơn giả lập một hệ thống không thực sự chạy.

## 16. Kiểm tra segmentation theo zone, không chỉ địa chỉ IP

Trong môi trường thật, network security thường áp dụng theo **zone**, **subnet**, **identity**, **security group** hoặc **workload label**, không chỉ một địa chỉ cố định.

Ví dụ bảng quyết định cho hệ thống ba tầng:

| Source zone | Destination zone | Dịch vụ | Expected | Ghi chú |
| --- | --- | --- | --- | --- |
| WEB | APP | TCP 443 | ALLOW | Luồng backend đã duyệt |
| APP | DATA | TCP 5432 | ALLOW có giới hạn | Chỉ workload ứng dụng đến database |
| WEB | DATA | TCP 5432 | DENY | Không cho bỏ qua tầng APP |
| GUEST | APP | TCP 443 | DENY | Không có quyền truy cập mạng nội bộ |
| ADMIN | NETWORK-MGMT | SSH/TLS admin | ALLOW có xác thực mạnh | Qua bastion/ZTNA theo quy trình |
| APP | INTERNET | Egress tới dịch vụ phê duyệt | ALLOW theo policy | Qua egress firewall/proxy |
| APP | INTERNET | Egress không được phê duyệt | DENY | Có log deny phù hợp |

**Điểm cần kiểm tra:** WEB có thể tới APP, nhưng không được bypass APP để tới DATA; route hoặc rule ngoài ý muốn ở tầng trung gian có thể phá vỡ phân đoạn dù từng firewall riêng lẻ có policy đúng.

Một test matrix tốt nên bao phủ:

- Ít nhất một kết nối hợp lệ cho từng luồng bắt buộc.
- Một kết nối không được phép có cùng đích nhưng **source zone khác**.
- Một kết nối có cùng source zone nhưng **port hoặc dịch vụ khác**.
- Một đường truy cập không thuộc quyền của identity thử nghiệm.
- Những đường đi thay thế hợp lệ hoặc trái chính sách (VPN, public IP, peering, cloud attachment) trong phạm vi.

Không nên làm rộng thử nghiệm thành quét toàn bộ cổng hoặc dò tìm ngoài phạm vi. Mỗi test cần một giả thuyết và đích được tổ chức xác nhận trước.

## 17. Kiểm thử các nhánh truy cập qua VPN hoặc ZTNA

VPN/ZTNA bổ sung điều kiện về người dùng, thiết bị và đường truy cập. Do đó hai kết nối có cùng IP đích và port vẫn có thể cho kết quả khác nhau tùy danh tính, mức độ tin cậy hoặc chính sách tunnel.

Ví dụ trong staging:

| ID | Identity | Device posture | Resource | Expected |
| --- | --- | --- | --- | --- |
| VPN-01 | Nhân viên nhóm Ops | Thiết bị đạt chuẩn | Portal nội bộ | ALLOW |
| VPN-02 | Nhân viên không thuộc Ops | Thiết bị đạt chuẩn | Portal Ops riêng | DENY |
| VPN-03 | Người có quyền nhưng thiết bị không đạt chuẩn | Fail posture | Portal nội bộ | DENY theo chính sách |
| VPN-04 | Tài khoản đã thu hồi | Không còn phiên hợp lệ | Portal nội bộ | DENY |
| VPN-05 | Nhân viên có quyền | Kết nối qua tunnel khác được phép | Portal nội bộ | ALLOW theo đường đã duyệt |

Các bước:

1. Xác minh tài khoản test có ủy quyền và trạng thái nhóm/quyền rõ ràng.
2. Xác nhận VPN session/tunnel, assigned IP, route, DNS view và connector health.
3. Đối chiếu access decision trong ZTNA/IdP và firewall segmentation.
4. Chạy yêu cầu tối thiểu tới resource; xác minh kết quả, không mở rộng sang dữ liệu nghiệp vụ.
5. Ghi log auth, policy ID, session ID đã ẩn thông tin nhạy cảm.
6. Đảm bảo test deny không bị sai vì ứng dụng đích đang down hoặc cert bị lỗi.

**Không vô hiệu hóa MFA, đánh tráo danh tính hoặc thử tài khoản người khác để có kết quả deny.** Trong lab dùng tài khoản test có quyền được cấu hình trước. Bài thực hành này không yêu cầu cài một VPN/ZTNA thực tế; phần trên là cách chuyển ma trận kiểm thử sang hệ thống được tổ chức cung cấp.

## 18. IDS/IPS, SOC và câu hỏi “chặn” khác “phát hiện” thế nào?

Trong lab có firewall, bộ counter cho biết có gói match rule. Khi mở rộng sang IDS/IPS, NDR và SOC, cần tách ba mục tiêu:

1. **Enforcement:** flow trái policy có bị chặn không? Tại firewall, NAC, IPS hoặc ZTNA?
2. **Detection:** có alert phù hợp khi có nhiều sự kiện deny, pattern không hợp lệ hoặc policy violation không?
3. **Response:** SOC có tiếp nhận, phân loại và xử lý theo runbook không?

Một IDS hoạt động ở chế độ **detection-only** có thể phát alert nhưng không chặn kết nối. Một IPS có thể ngăn gói nhưng chưa chắc alert được SIEM ingest. Một firewall deny đúng policy cũng không đương nhiên cần tạo incident mức nghiêm trọng cao cho từng gói.

Bảng bằng chứng:

| Hiện tượng | Có thể kết luận | Chưa được kết luận |
| --- | --- | --- |
| Firewall counter deny tăng, canary không nhận | Rule deny đang match packet tại enforcement point | SOC đã nhận alert |
| IDS có signature alert | IDS quan sát được tín hiệu theo rule | Kết nối bị chặn |
| SIEM có event deny | Pipeline ingest được sự kiện | Rule đúng trên mọi đường đi |
| SOC mở case và phân loại đúng | Có phản ứng vận hành trong ca thử | Toàn bộ threat scenario đã được ngăn chặn |
| Không có log tại một gateway | Thiếu bằng chứng ở gateway đó | Hoàn toàn không có lưu lượng |

Muốn đo detection rate, phải chuẩn bị ground truth và tập negative/positive riêng; không dùng số lượng alert làm thước đo duy nhất. Với nhiệm vụ hiện tại, trọng tâm kết luận là **quyền truy cập**, còn phát hiện là một tiêu chí bổ sung khi thiết kế yêu cầu.

## 19. Kiểm tra đường đi ngoài firewall hoặc proxy

Một sai lầm là thấy một firewall chặn đúng một đường và kết luận **không thể truy cập đích bằng đường nào khác**. Trên hệ thống thực, cần xét:

- Nhiều default gateway hoặc policy-based routing.
- Direct Internet access, NAT gateway, VPN split tunnel.
- IPv4 và IPv6 không cùng bộ chính sách.
- Cloud VPC/VNet peering, transit hub, private endpoint, route propagation.
- Workload có nhiều interface hoặc network namespace.
- Proxy chỉ áp cho trình duyệt, trong khi tác vụ nền có thể không sử dụng.
- Failover làm luồng chuyển qua đường dự phòng với policy khác.
- Container/service mesh có những workload ngoài phạm vi CNI/mesh policy.

Không nên tạo đường bypass trên mạng production để “xem có qua được không”. Trước tiên dùng **read-only effective route, policy graph, flow log, inventory và log from enforcement**. Sau đó chỉ dùng canary, traffic synthetic trong phạm vi đã được phê duyệt để xác nhận.

**Tiêu chí:** nếu có một đường thay thế hợp lệ đã được phê duyệt và có control tương đương, ghi là **APPROVED_ALTERNATIVE**. Nếu luồng thuộc diện bắt buộc kiểm soát đi qua đường thiếu enforcement, ghi finding với rủi ro, bằng chứng và owner; không tự sửa routing rộng khi chưa đánh giá ảnh hưởng.

## 20. IPv4, IPv6, NAT và trạng thái phiên

Lab dùng IPv4 để cô lập các biến cơ bản. Khi áp dụng thực tế:

### IPv4 và IPv6

Một endpoint dual-stack có thể dùng IPv6 ngay cả khi rule IPv4 đã đúng. Test matrix cần ghi address family, A/AAAA answer, route và firewall coverage tương ứng. Không coi một negative test IPv4 là bằng chứng mọi kết nối bị chặn.

### NAT và session tracking

Source IP sau NAT có thể khác IP của application. Khi đối chiếu log cần biết IP/port trước và sau NAT, zone, thời gian và session ID. Một rule được áp trước NAT có thể match địa chỉ khác so với rule ở điểm enforcement khác, tùy sản phẩm.

### Proxy và upstream connection

Khi một client dùng forward proxy, proxy tạo kết nối riêng tới backend. Firewall tại egress có thể thấy source là proxy IP, không phải máy trạm; do đó cần correlation ID giữa request tại proxy và flow tại gateway.

### Gói chiều về

Stateful policy thường cho phản hồi của phiên được phép; một số firewall, NACL hoặc security control là stateless và cần rule tương ứng cho chiều hồi đáp. Không áp dụng một công thức “chỉ cần mở inbound” cho mọi loại firewall.

## 21. Cloud lab: chuyển ma trận allow/deny sang VPC hoặc VNet

Trong cloud, nhiều lớp cùng tác động:

~~~mermaid
flowchart LR
    A["Workload A"] --> SG["Security group / NSG"]
    SG --> RT["Subnet route table"]
    RT --> FW["Network firewall / transit"]
    FW --> B["Workload B / service"]
    A -. "Audit/flow log" .-> L["Central observability"]
    SG -.-> L
    FW -.-> L
    B -.-> L
~~~

Sơ đồ chỉ mô tả các yếu tố cần xem xét; thứ tự kiểm tra packet trên sản phẩm cloud có thể khác nhau. Không suy diễn pipeline xử lý nội bộ của nhà cung cấp từ sơ đồ khái niệm.

Checklist cho một flow trong staging:

1. Xác định đúng resource ID, workload identity, subnet, route table và network zone của nguồn/đích.
2. Kiểm tra effective routes, peering/transit, internet/NAT gateway và return path.
3. Đối chiếu security group/NSG, network ACL và firewall rule cho giao thức/port cần kiểm thử.
4. Kiểm tra VM/process/service thực sự listen trên port đó.
5. Chạy positive/negative test đã duyệt bằng endpoint canary.
6. Đối chiếu VPC/VNet flow logs, firewall log, LB/access log và audit trail thay đổi chính sách.
7. Kiểm tra drift sau triển khai hoặc khi tạo subnet/VPC mới.

Một flow có status **ACCEPT** trong một nguồn flow log có thể vẫn bị chặn tại tầng khác; ý nghĩa trường ACCEPT/REJECT phụ thuộc vị trí và sản phẩm. Ngược lại, vắng flow log có thể do cấu hình collection hoặc sampling, không chứng minh packet không tồn tại.

## 22. Kubernetes: kiểm tra đúng ingress và egress policy

Với Kubernetes, policy có thể áp theo namespace, pod label và CNI. Tồn tại một NetworkPolicy YAML không chứng minh pod thật sự bị cô lập nếu CNI không enforce hoặc có policy khác mở thêm quyền.

Ví dụ minh họa **deny ingress mặc định** cho một namespace thử nghiệm:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-ingress
  namespace: lab-app
spec:
  podSelector: {}
  policyTypes:
    - Ingress
~~~

Chính sách này chọn tất cả pod trong namespace cho loại **Ingress**; nó không thiết lập default-deny **Egress**. Với Kubernetes NetworkPolicy, các policy có hiệu lực có thể kết hợp cho phép theo hướng cộng dồn, không dùng thứ tự rule như một firewall truyền thống.

Một ma trận thử nghiệm:

| Test | Nguồn | Đích | Expected |
| --- | --- | --- | --- |
| K8S-01 | Pod cùng namespace có policy allow phù hợp | API service | ALLOW |
| K8S-02 | Pod ngoài namespace không có quyền | API service | DENY |
| K8S-03 | Pod được phép | DNS service cần thiết | ALLOW nếu policy quy định |
| K8S-04 | Pod không được phép egress | Canary bên ngoài | DENY nếu egress policy có hiệu lực |

Trong cluster test:

~~~bash
kubectl get pods -n lab-app -o wide
kubectl get services -n lab-app
kubectl get endpointslices -n lab-app
kubectl get networkpolicies -n lab-app
~~~

Kiểm tra thêm CNI/mesh-specific policy, Service endpoints, DNS và policy theo cả nguồn/đích. Các lệnh trên là **chỉ đọc** và chưa đủ chứng minh allow/deny; cần test có ground truth với workload canary và log chính xác.

Nếu có service mesh mTLS, kết nối transport được phép ở CNI vẫn có thể bị từ chối bởi identity/authentication ở mesh. Ghi tách từng tầng để tránh sửa sai network policy.

## 23. Chẩn đoán một test fail

Một negative test có thể thất bại theo hai hướng:

- **Unexpected allow:** truy cập trái policy vẫn thành công.
- **False PASS do timeout:** kết nối thất bại vì lý do ngoài control được kiểm tra.

Một positive test cũng có thể thất bại do thiếu listener, DNS, route, firewall, TLS hoặc ứng dụng. Hãy dùng cây quyết định:

~~~mermaid
flowchart TD
    A["Test có source, dest, policy, ground truth?"] -->|Không| X["INVALID_TEST"]
    A -->|Có| B{"Canary đích khỏe?"}
    B -->|Không| X
    B -->|Có| C{"Nguồn và route đúng?"}
    C -->|Không| R["Sửa topology / test setup"]
    C -->|Có| D{"Enforcement có event/counter đúng flow?"}
    D -->|Không| E["Kiểm tra bypass, rule matching,\ntelemetry và vị trí sensor"]
    D -->|Có| F{"Decision có đúng expected?"}
    F -->|Không| G["POLICY_FAIL: đánh giá rủi ro,\nđề xuất sửa có kiểm soát"]
    F -->|Có| H{"Kết quả client/server khớp?"}
    H -->|Không| I["Chẩn đoán TLS, backend,\nreturn path hoặc log"]
    H -->|Có| J["PASS: lưu bằng chứng\nvà phạm vi kiểm chứng"]
~~~

### 23.1. Các nguyên nhân thường gặp

| Dấu hiệu | Nguyên nhân khả dĩ | Kiểm tra ưu tiên |
| --- | --- | --- |
| CLIENT:8080 timeout, counter allow không tăng | Source sai, route/interface sai, rule không match | Route và IP trong namespace, iifname/oifname |
| CLIENT:8080 timeout, allow counter tăng | Đường phản hồi, server, conntrack hoặc drop tiếp theo | Server health, established counter, packet path |
| GUEST:8080 thành công | Route/policy khác hoặc rule allow quá rộng | Effective policy, đường đi, enforcement |
| GUEST:8080 timeout, deny counter không tăng | Lỗi route, thiếu listener, interface khác | Canary health và route |
| Counter deny tăng nhưng canary vẫn nhận request | Dùng flow khác hoặc có đường thay thế | Source/dest/time correlation, topology |
| HTTP báo 403 nhưng TCP OK | Lỗi quyền ở tầng ứng dụng/WAF | Auth, WAF rule, request ID |
| Chỉ IPv6 được truy cập | Policy IPv6 khác IPv4 | IPv6 route/rules, DNS AAAA |
| Sau failover mới thấy bypass | Gateway phụ thiếu policy hoặc route lệch | HA, change history, backup path |
| SIEM không có event, local counter tăng | Logging chưa bật hoặc pipeline lỗi | Syslog/collector/parser/retention |
| Kết quả chập chờn | Timing, route convergence, NAT/state timeout, loss | Metrics, flow logs, window test |

Sửa lỗi cấu hình cần theo quy trình thay đổi và kiểm thử lại cả allow lẫn deny. **Không** thêm allow-any/deny-any rộng vào mạng sản xuất để chứng minh một giả thuyết.

## 24. Đánh giá bằng chứng và phân loại kết quả

Dùng một trạng thái rõ ràng cho mỗi test execution:

| Trạng thái | Khi sử dụng |
| --- | --- |
| **PASS_ALLOW** | Flow được phép hoạt động đúng tầng yêu cầu và qua enforcement hợp lệ |
| **PASS_DENY** | Flow cấm bị từ chối, canary khỏe, có bằng chứng control được kỳ vọng match |
| **FAIL_UNEXPECTED_DENY** | Flow hợp lệ bị chặn do chính sách/đường đi không như thiết kế |
| **FAIL_UNEXPECTED_ALLOW** | Flow trái policy vẫn tới đích hoặc bypass một control bắt buộc |
| **INCONCLUSIVE** | Dữ liệu không đủ phân biệt policy với route/service/telemetry |
| **INVALID_TEST** | Môi trường test sai, canary down, điều kiện không đúng hoặc test không thực hiện |
| **NOT_RUN** | Chưa chạy, không được tính là PASS |

**Một số đặc điểm chấm điểm:**

- `PASS_ALLOW` phải có kết quả ứng dụng đáp ứng tiêu chí và bằng chứng đường đi; không chỉ `TCP handshake` nếu tiêu chí yêu cầu HTTP.
- `PASS_DENY` phải chứng minh đúng control chặn, trừ khi thiết kế chấp nhận một control tương đương đã phê duyệt.
- Một deny không được ghi PASS nếu đích không có listener hoặc test thiếu route, dù client thấy timeout.
- Một unexpected allow cần đánh giá phạm vi; có thể là ngoại lệ hợp lệ chưa được cập nhật trong test, hoặc thực sự là lỗ hổng.
- Nếu test chưa chạy do môi trường lỗi, ghi INVALID_TEST hoặc NOT_RUN, không tự thay expected result.

**Ví dụ nhật ký kiểm thử:**

~~~csv
run_id,test_id,source,destination,protocol,expected,observed,firewall_evidence,canary_evidence,result
R01,T01,lab-client,203.0.113.20:8080,TCP,ALLOW,HTTP_SUCCESS,allow-counter-increased,received,PASS_ALLOW
R01,T02,lab-guest,203.0.113.20:8080,TCP,DENY,TIMEOUT,deny-counter-increased,not-received,PASS_DENY
R01,T07,lab-client,203.0.113.20:9090,TCP,DENY,TIMEOUT,catchall-counter-increased,listener-healthy,PASS_DENY
~~~

Các hàng CSV trên là **dữ liệu minh họa kỳ vọng**, chỉ ghi thành kết quả thực khi có bằng chứng sau chạy.

## 25. Chỉ số hoàn thành và chất lượng kiểm thử

### 25.1. Chỉ số chính

Với bộ test hợp lệ đã chạy:

\[
\text{Policy pass rate}=\frac{\text{Số test PASS_ALLOW + PASS_DENY}}{\text{Tổng test hợp lệ đã chạy}}
\]

Nên tách hai tỷ lệ:

\[
\text{Allow success rate}=\frac{\text{PASS_ALLOW}}{\text{Tổng test ALLOW hợp lệ}}
\]

\[
\text{Deny enforcement rate}=\frac{\text{PASS_DENY}}{\text{Tổng test DENY hợp lệ}}
\]

Nếu mẫu số bằng 0, báo **N/A**, không tự ghi 100%.

### 25.2. Coverage và confidence

**Test matrix coverage** = số trường hợp test đã chạy hợp lệ / số trường hợp bắt buộc trong phạm vi đã phê duyệt.

**Evidence completeness** = số test hợp lệ có đủ client result, enforcement evidence và canary/endpoint evidence / số test hợp lệ.

**Policy drift findings** = số tình huống cấu hình thực tế khác baseline, phân loại theo zone, asset, đường đi và người phụ trách.

Không đánh đồng **100% PASS trong 3 test** với **100% an toàn toàn bộ mạng**. Chỉ số phải được giải thích cùng phạm vi: source/destination, protocol, số lần chạy, address family, trạng thái routing/failover và thời gian thực hiện.

### 25.3. Ví dụ tính kết quả

Giả sử đợt thử nghiệm có 12 trường hợp bắt buộc, đã chạy 10 trường hợp, nhưng 1 trường hợp vô hiệu vì canary down. Trong 9 test hợp lệ có:

- 4 test ALLOW: 3 PASS_ALLOW, 1 FAIL_UNEXPECTED_DENY.
- 5 test DENY: 4 PASS_DENY, 1 FAIL_UNEXPECTED_ALLOW.

Khi đó:

\[
\text{Policy pass rate}=\frac{3+4}{9}\approx77{,}8\%
\]

\[
\text{Allow success rate}=\frac{3}{4}=75\%,\qquad
\text{Deny enforcement rate}=\frac{4}{5}=80\%
\]

Độ phủ test hợp lệ trên danh mục bắt buộc = 9/12 = **75%**. Một test vô hiệu không được tính PASS hoặc FAIL và phải có kế hoạch thử lại. Nếu tính “đã cố chạy” thì 10/12 = 83,3%, nhưng đó là chỉ số khác và cần ghi tên rõ ràng.

## 26. Báo cáo phát hiện và kế hoạch sửa

Khi phát hiện **FAIL_UNEXPECTED_ALLOW**, báo cáo tối thiểu cần có:

1. **Flow vi phạm:** source asset/identity/zone, đích và giao thức/port.
2. **Expected policy:** điều kiện nào yêu cầu deny, do ai phê duyệt.
3. **Observed behavior:** timestamp, kết quả client, server/canary và enforcement.
4. **Path/evidence:** route, NAT, firewall rule ID, event/counter, proxy hoặc cloud flow log.
5. **Phạm vi ảnh hưởng:** một workload, một subnet, nhiều zone hay đường backup.
6. **Rủi ro:** khả năng truy cập trái quyền, kiểm soát bù trừ còn hoạt động và loại dữ liệu/tài sản bị tác động.
7. **Owner/action:** nhóm chịu trách nhiệm, hướng sửa và thẩm quyền phê duyệt.
8. **Validation:** positive/negative test cần chạy lại, tiêu chí rollback và kiểm tra tác động ngoài dự kiến.

Ví dụ định dạng:

~~~yaml
finding_id: LAB-013-F01
scenario: GUEST reaches internal WEB service unexpectedly
environment: staging
policy_expected: guest-to-internal-deny
source_zone: GUEST
destination: 203.0.113.20:8080
test_id: T02
observed:
  client: HTTP_SUCCESS
  server: request_received
  enforcement: no_matching_deny_on_expected_path
  timestamp_utc: 2026-11-28T04:00:00Z
classification: FAIL_UNEXPECTED_ALLOW
impact: Unauthorized reachability of internal test service
owner: network-platform
reviewer: security-architecture
action:
  - Confirm effective routing and enforcement
  - Correct scoped policy through approved change
  - Retest T01 and T02
  - Verify logs and alternative paths
status: OPEN
~~~

Dữ liệu là **ví dụ tổng hợp**, không phản ánh kết quả vừa chạy. Với hệ thống thật, không chép token, thông tin cá nhân, private key hoặc PCAP chứa dữ liệu khách hàng vào báo cáo mở.

### 26.1. Sửa đúng nguyên nhân

- **Sai rule:** bổ sung rule theo least privilege, đúng source/zone, destination/service và thứ tự evaluation của sản phẩm; review và rollback.
- **Sai route:** sửa đường đi đến đúng enforcement, kiểm tra return path, HA, NAT và các subnet liên quan.
- **Sai identity:** sửa mapping user/device/workload hoặc quyền ZTNA/NAC, không tắt MFA.
- **Sai DNS:** sửa resolver/zone/view nếu lỗi ngăn positive test; không dùng kết quả DNS để thay kết luận firewall.
- **Thiếu log:** sửa ingestion/parser/clock đồng thời giữ nguyên phát hiện enforcement thực tế.
- **Bypass ngoài dự kiến:** rà toàn bộ equivalent paths và guardrail onboarding để tránh tạo lại lỗ hổng.
- **Server không khỏe:** chuyển application owner, chạy lại sau khi đích sẵn sàng; không sửa firewall nếu không có bằng chứng liên quan.

## 27. Kiểm thử hồi quy sau thay đổi

Sau một lần sửa policy, luôn chạy lại **hai chiều**:

- Trường hợp từng thất bại phải đạt expected decision.
- Trường hợp hợp lệ trước đó vẫn được phép, không làm gián đoạn nghiệp vụ.
- Trường hợp cấm cùng phân đoạn khác vẫn bị chặn, không tạo allow quá rộng.
- Log, counter, request ID và alert phù hợp được ghi nhận.
- Đường backup/failover, IPv6, cloud hoặc VPN có liên quan không tạo ngoại lệ mới.

Trong dự án thực tế, đưa kiểm tra vào CI/CD hoặc policy-as-code:

~~~text
FOR EACH authorized_flow:
    verify source identity and expected destination/protocol
    verify effective route crosses approved enforcement
    simulate policy decision from desired configuration
    run approved synthetic connectivity test where feasible
    collect enforcement and application evidence
    fail change review if required positive test fails

FOR EACH forbidden_flow:
    validate deny expectation and actual enforcement path
    check route alternatives and address families in scope
    run approved negative test against healthy canary
    fail change review if unexpected allow is confirmed

publish coverage, evidence, deviations, owner, rollback decision
~~~

Các bước trên là mô hình quy trình, không phải script để tự ý thay đổi mạng. Kiểm thử tĩnh đối với policy giúp phát hiện một số lỗi trước deployment; kiểm thử runtime cần thiết để biết dữ liệu chuyển qua đúng đường thực tế.

## 28. Bài tập mở rộng theo kịch bản

### 28.1. Thêm vùng DATA

Mở rộng topology thành `WEB → APP → DATA` hoặc thêm một namespace `lab-data`. Đề xuất chính sách:

- `lab-client` chỉ được truy cập ứng dụng ở cổng dịch vụ cho phép.
- Một workload APP được phép kết nối DATA trên cổng database thử nghiệm.
- GUEST và CLIENT không được kết nối thẳng DATA.

**Yêu cầu:** lập ma trận thêm hai positive và ba negative test; chú ý listener, đường về, kiểm tra DNS, route, rule counters và packet path. Không thử quét cổng; chỉ dùng port canary được chọn trước.

### 28.2. Mô phỏng policy drift

Trong môi trường lab được phép, giả định một rule vô tình cấp quyền quá rộng. **Không cần tạo bypass thực tế trên production.** Sử dụng policy sample hoặc một thay đổi được duyệt trong namespace cô lập để phân tích điều kiện mà negative test có thể chuyển từ DENY sang ALLOW.

**Yêu cầu:** chỉ ra test nào phải fail, log/counter nào thay đổi, phương án rollback và kiểm thử hồi quy. Từ đó đề xuất một guardrail ngăn policy trở nên rộng hơn baseline.

### 28.3. Tình huống VPN/ZTNA

Dùng một danh sách identity test có nhóm quyền khác nhau. Tạo expected decisions cho từng người và thiết bị; phân biệt lỗi đăng nhập, lỗi truy cập sau xác thực, route/DNS và policy ứng dụng.

**Yêu cầu:** ít nhất ba test ALLOW/DENY và cách đối chiếu authorization logs với application logs mà không tiết lộ dữ liệu tài khoản.

### 28.4. Tình huống cloud

Dựa trên sơ đồ giả định hai VPC có shared firewall, chọn ba subnet: APP, DATA và GUEST. Một subnet mới có route table chưa đúng baseline.

**Yêu cầu:** chỉ ra cách kiểm tra effective route, security group, flow log, failover và canary test để kết luận đây là thiếu route, firewall policy mismatch hay bypass inspection.

## 29. Mẫu báo cáo thực hành

~~~markdown
# Báo cáo LAB-ACCESS-013

## Phạm vi
- Environment:
- Test run ID:
- Người kiểm thử / người phê duyệt:
- Thời gian UTC:
- Sơ đồ zone / IP / protocol:
- Điều kiện dừng và rollback:

## Chính sách
| Test ID | Source | Destination | Expected | Policy ID |
| --- | --- | --- | --- | --- |

## Kết quả
| Test ID | Client | Enforcement | Server/canary | Result |
| --- | --- | --- | --- | --- |

## Bằng chứng
- IP/route/namespace hoặc cloud resource:
- Firewall rule/counter/event:
- Request ID / server health:
- Logs tại SOC:
- Ảnh chụp hoặc đường dẫn lưu chứng cứ có kiểm soát:

## Đánh giá
- Allow success rate:
- Deny enforcement rate:
- Test coverage:
- Invalid / inconclusive:
- Các đường chưa được kiểm thử:

## Findings
- Lỗi / nguyên nhân / mức tác động:
- Owner và action:
- Re-test expected:
- Rủi ro còn lại:

## Nghiệm thu
- Positive test:
- Negative test:
- Đường thay thế:
- Telemetry:
- Chữ ký người kiểm thử / người duyệt:
~~~

Mẫu này có thể đi cùng YAML/CSV ground truth; chứng cứ phải được truy vết bằng `test_id` hoặc `execution_id` thay vì gắn nhầm log có thời điểm gần giống.

## 30. Dọn dẹp lab và xác nhận host bình thường

Sau khi hoàn thành, dừng **cả hai** HTTP server trong các terminal đang chạy bằng `Ctrl+C`. Đảm bảo không còn tiến trình đang sử dụng các namespace lab. Sau đó chỉ xóa **bốn namespace được tạo cho bài học này**, với điều kiện chắc chắn chúng thuộc phiên lab hiện tại:

~~~bash
sudo ip netns del lab-client
sudo ip netns del lab-guest
sudo ip netns del lab-server
sudo ip netns del lab-router

# Kiểm tra lại danh sách
ip netns list
~~~

Veth bị xóa cùng namespace khi không còn reference. Nếu một namespace vẫn còn tiến trình đang chạy, phải dừng đúng tiến trình lab trước khi xóa; không dùng lệnh kill toàn cục hoặc xóa mọi namespace trên host. Không dùng `nft flush ruleset` trong host namespace vì có thể xóa chính sách mạng ngoài bài lab.

Checklist đóng lab:

- [ ] Các HTTP server thử nghiệm đã dừng.
- [ ] Không còn namespace/interface lab mới tạo.
- [ ] Không thay đổi firewall, route hoặc DNS thật của host.
- [ ] Chứng cứ tổng hợp đã được lưu, ẩn dữ liệu nhạy cảm và có thời hạn giữ.
- [ ] Những giới hạn chưa kiểm thử được ghi rõ.
- [ ] Báo cáo có kết quả allow/deny, counter, nguyên nhân và bước retest.

## 31. Câu hỏi ôn tập và đáp án

**Câu 1.** GUEST không truy cập được WEB và curl báo timeout. Có thể đánh giá PASS_DENY ngay không?

**Đáp án:** Chưa. Cần xác minh WEB đang hoạt động, GUEST có route đúng, firewall deny rule match với flow và không có lỗi môi trường làm phép thử vô hiệu.

**Câu 2.** Vì sao T01 cần cả HTTP response và firewall counter?

**Đáp án:** HTTP response chứng minh người dùng truy cập dịch vụ thành công; counter cho thấy luồng đi qua rule allow đang kiểm tra. Cần cả hai khi mục tiêu vừa là chức năng kết nối vừa là hiệu lực enforcement.

**Câu 3.** Khi firewall có rule cho phép nhưng client timeout, lỗi có chắc chắn tại firewall không?

**Đáp án:** Không. Có thể rule không match, route sai, phía đích không có listener, thiếu return path, conntrack/ACL khác drop hoặc service không khỏe. Cần đối chiếu flow, logs và các lớp liên quan.

**Câu 4.** Một test DENY thành công tại IPv4 có đủ chứng minh toàn bộ policy dual-stack không?

**Đáp án:** Không. Nếu môi trường hỗ trợ IPv6, cần kiểm tra IPv6 route, nguồn/đích, firewall policy và khả năng bypass tương ứng.

**Câu 5.** Nếu IPS phát alert, có thể kết luận flow đã bị chặn không?

**Đáp án:** Không. Cần biết IPS ở chế độ detect hay prevent, xem action thật và dữ liệu bên đích. Một alert không tự đồng nghĩa với việc kết nối bị ngăn.

**Câu 6.** Làm thế nào chứng minh một luồng trái quyền bị chặn do firewall thay vì dịch vụ không lắng nghe?

**Đáp án:** Kiểm tra listener hoạt động từ vị trí được phép, thử positive control tới cùng đích/port, đọc deny rule counter/event và đối chiếu server không nhận request bị cấm.

**Câu 7.** Khi sửa một rule khiến GUEST bị chặn, có cần chạy lại phép thử CLIENT được phép không?

**Đáp án:** Có. Một rule quá rộng có thể chặn luôn luồng hợp lệ. Phải kiểm tra cả PASS_ALLOW lẫn PASS_DENY và những kết nối phụ thuộc liên quan.

**Câu 8.** Một kết nối đi qua cloud NAT khác nhưng vẫn hoạt động. Có tự động là lỗi an ninh không?

**Đáp án:** Chưa chắc. Cần so sánh đường thực tế với kiến trúc đã phê duyệt, control tương đương, telemetry và rủi ro. Chỉ kết luận bypass khi luồng thuộc diện bắt buộc kiểm soát nhưng không đi qua enforcement phù hợp.

**Câu 9.** Vì sao phải ghi cả `INVALID_TEST` và `INCONCLUSIVE`?

**Đáp án:** INVALID_TEST dành cho phép thử không đáp ứng tiền đề (ví dụ canary down); INCONCLUSIVE dành cho thử nghiệm có diễn ra nhưng thiếu bằng chứng để phân loại. Trộn cả hai vào PASS hoặc FAIL làm sai chỉ số.

**Câu 10.** Bằng chứng nào cho thấy network security đã áp dụng đúng theo mục tiêu?

**Đáp án:** Có ma trận policy được phê duyệt, đường thực tế và enforcement point được xác minh, luồng hợp lệ hoạt động, luồng trái quyền bị chặn, telemetry đủ truy vết và các đường thay thế trong phạm vi không tạo vi phạm.

## 32. Tiêu chí hoàn thành dự án

Một bài lab được coi là hoàn thành về mặt kỹ thuật khi:

- [ ] Mô tả đúng topology và ranh giới CLIENT, GUEST, SERVER, ROUTER.
- [ ] Có bảng IP/route và giải thích được vai trò default gateway.
- [ ] Có rule stateful allow cụ thể và deny mặc định trong router namespace.
- [ ] Canary được xác minh khỏe trước negative test.
- [ ] T01 có HTTP response và bằng chứng rule allow/established.
- [ ] T02 có bằng chứng deny rule match và server không nhận request.
- [ ] Có ít nhất một trường hợp thử bị từ chối với service thật sự đang listen.
- [ ] Có phân loại rõ PASS, FAIL, INVALID và INCONCLUSIVE.
- [ ] Có giải thích về DNS, NAT, IPv6, VPN/ZTNA, IDS/IPS, cloud/Kubernetes khi mở rộng phạm vi.
- [ ] Có bảng kết quả, chứng cứ theo execution ID, số đo coverage và hướng xử lý phát hiện.
- [ ] Có ít nhất một phương án retest sau thay đổi.
- [ ] Cleanup chỉ tác động đến tài nguyên lab và được xác minh.

**Thông điệp chính:** kiểm thử mạng an toàn không chỉ đặt câu hỏi “có kết nối được không?” mà phải xác nhận **đúng đối tượng, đúng dịch vụ, đúng đường đi, đúng quyết định policy và có bằng chứng**. Chỉ khi kiểm tra cả **đường được phép** và **đường bị chặn**, ta mới có cơ sở đánh giá hiệu lực phân đoạn và firewall, đồng thời nhận ra các lỗi routing, danh tính, giám sát hoặc bypass có thể làm sai kết luận.
