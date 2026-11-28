# Triển khai firewall theo nguyên tắc default deny

## 1. Bối cảnh và mục tiêu của dự án thực hành

Một doanh nghiệp có máy người dùng, ứng dụng nội bộ, cơ sở dữ liệu, Wi-Fi khách và hệ thống quản trị. Nếu firewall mặc định **cho phép mọi kết nối** rồi chặn từng cổng nguy hiểm, các dịch vụ mới mở hoặc những đường đi chưa được kiểm kê sẽ dễ trở thành lối truy cập ngoài dự kiến.

Nguyên tắc **default deny** (mặc định từ chối) đảo lại cách ra quyết định: **chỉ những luồng được xác định là cần thiết và được cho phép rõ ràng mới được đi qua**. Mọi lưu lượng không khớp quy tắc cho phép sẽ bị từ chối theo chính sách. Điều này tạo nền tảng cho phân đoạn mạng, quyền tối thiểu (*least privilege*), kiểm soát lưu lượng east-west và giới hạn phạm vi di chuyển ngang (*lateral movement*).

Trong module **SECURITY_NETWORK_SECURITY**, bài thực hành thuộc chương **Dự án thực hành bảo mật mạng** và kết nối với các lớp bảo vệ firewall, VPN, IDS/IPS, DNS, xác thực, mạng không dây và cloud. Kết quả không chỉ là các lệnh cấu hình chạy được, mà còn là một **hồ sơ triển khai có thể kiểm chứng và khôi phục**.

### Người học sẽ hoàn thành

1. Mô tả rõ luồng nào cần được phép và luồng nào phải bị chặn.
2. Tạo một mô hình mạng cô lập bằng Linux network namespaces và triển khai firewall **nftables**.
3. Cấu hình chính sách mặc định `drop` ở các chuỗi `input`, `forward` và `output` của firewall trong lab.
4. Chỉ cho phép **một** luồng ứng dụng được phê duyệt; dùng conntrack cho lưu lượng phản hồi của phiên đã thiết lập.
5. Kiểm tra từ nguồn hợp lệ, nguồn khách và cổng ngoài phạm vi; dùng counter để đối chiếu kết quả.
6. Phân tích các giới hạn của việc chỉ dựa vào IP/port, nhận biết tác động tới DNS, VPN, HA, IPv6, cloud và dịch vụ quản trị.
7. Viết báo cáo về policy, phép thử, bằng chứng, thay đổi và phương án rollback/cleanup.

**Phạm vi an toàn:** đây là bài lab phòng thủ. Chỉ chạy các lệnh trên **máy ảo Linux riêng, được phép quản trị**, không triển khai trực tiếp trên router, firewall hoặc máy chủ sản xuất. Các địa chỉ `192.0.2.0/24`, `198.51.100.0/24` và `203.0.113.0/24` thuộc các dải dành cho tài liệu, được dùng trong mạng ảo cô lập. Không quét hoặc thử kết nối tới hệ thống ngoài phạm vi được cấp phép.

## 2. Hiểu đúng về default deny

Default deny không có nghĩa là “không ai được sử dụng mạng”. Đó là **điều kiện mặc định** khi một luồng không có căn cứ cho phép cụ thể.

Ví dụ:

- Cho phép máy ứng dụng kết nối database qua đúng giao thức/port cần thiết.
- Chặn máy ở mạng khách kết nối database, kể cả khi mạng khách có thể truy cập Internet.
- Chặn truy cập SSH/RDP quản trị từ VLAN người dùng; quản trị đi qua jump host được phê duyệt.
- Giới hạn DNS tới resolver tin cậy, thay vì để mọi máy truy vấn bất kỳ resolver.
- Cho phép phản hồi của kết nối hợp lệ theo cơ chế theo dõi trạng thái, thay vì mở toàn bộ chiều ngược lại.

### Phân biệt bốn loại hành động

| Hành động | Ý nghĩa | Cần lưu ý |
|---|---|---|
| **Accept/allow** | Cho lưu lượng khớp điều kiện tiếp tục xử lý qua hook hiện tại | Không chứng minh dịch vụ đích đang hoạt động hay người dùng đã được xác thực |
| **Drop** | Bỏ gói, thường không trả phản hồi lỗi | Client có thể timeout; không có nghĩa là có lệnh chặn từ đúng firewall nếu thiếu log |
| **Reject** | Từ chối và có thể trả phản hồi như ICMP/TCP reset tùy cấu hình | Giúp chẩn đoán nhưng có thể tiết lộ trạng thái; không phù hợp mọi tình huống |
| **Log/counter** | Ghi nhận sự kiện hoặc tăng bộ đếm gói | Không tự chặn gói nếu không kết hợp verdict/policy; log cần kiểm soát dung lượng |

### Stateful và stateless

**Stateful firewall** duy trì trạng thái kết nối. Nếu nguồn hợp lệ mở một phiên TCP đến đích được phép, gói phản hồi có thể được chấp nhận theo `ct state established,related`. Điều này giúp không phải mở ngược mọi port tạm thời (*ephemeral ports*) từ server về client.

**Stateless ACL** đánh giá từng gói theo trường được khai báo mà không tự suy luận trạng thái phiên; nếu dùng ACL stateless, phải thiết kế chiều đi, chiều về và giao thức tương ứng.

Không được hiểu `established,related` là “tin mọi gói nội bộ”: chỉ các kết nối được hệ thống theo dõi đúng trạng thái mới khớp. Quy tắc **cho phép phiên mới** vẫn phải giới hạn chặt nguồn, đích, giao thức và cổng.

## 3. Thiết kế topology và ma trận luồng

Bài lab sử dụng một VM Linux có bốn **network namespace**. Các namespace dùng chung kernel nhưng có giao diện mạng, bảng định tuyến và firewall namespace riêng; veth pair tạo kết nối ảo. Mô hình này giúp thực hành mà **không phải thay đổi firewall của hệ điều hành host**.

~~~mermaid
flowchart LR
  C["ns-client\n192.0.2.10"] -->|"veth"| FW["ns-fw\n192.0.2.1 / 198.51.100.1 / 203.0.113.1\nnftables default deny"]
  G["ns-guest\n203.0.113.10"] -->|"veth"| FW
  FW -->|"veth"| A["ns-app\n198.51.100.20\nHTTP lab TCP/8080"]
  C -->|"TCP/8080 được cấp"| A
  G -.->|"TCP/8080 bị chặn"| A
~~~

Đường mũi tên trực tiếp trong sơ đồ chỉ diễn giải **quan hệ logic cần kiểm thử**; mọi gói chuyển tiếp thực tế đều qua `ns-fw`.

| Thành phần | IP trong lab | Vai trò |
|---|---|---|
| `ns-client` | `192.0.2.10/24` | Máy khách được phép dùng dịch vụ |
| `ns-fw` (phía client) | `192.0.2.1/24` | Gateway của máy khách |
| `ns-fw` (phía app) | `198.51.100.1/24` | Gateway của máy ứng dụng |
| `ns-app` | `198.51.100.20/24` | Web server thử nghiệm |
| `ns-fw` (phía guest) | `203.0.113.1/24` | Gateway của mạng khách |
| `ns-guest` | `203.0.113.10/24` | Máy không được phép truy cập ứng dụng |

Trong lab này, HTTP/8080 chỉ phục vụ một nội dung tĩnh giả, trên mạng namespace cô lập. **Môi trường thực tế phải dùng HTTPS/TLS, xác thực và phân quyền phù hợp; mở port không thay thế các cơ chế đó.**

### Ma trận chính sách mục tiêu

| ID | Nguồn | Đích | Protocol/port | Mong đợi | Lý do |
|---|---|---|---|---|---|
| P1 | `ns-client` | `ns-app` | TCP/8080 | **ALLOW** | Dịch vụ thử nghiệm đã được phê duyệt |
| P2 | `ns-app` | `ns-client` | Traffic phản hồi cho P1 | **ALLOW khi established/related** | Duy trì phiên hợp lệ |
| N1 | `ns-guest` | `ns-app` | TCP/8080 | **DENY** | Mạng khách không có nhu cầu |
| N2 | `ns-client` | `ns-app` | TCP/8081 | **DENY** | Không nằm trong danh sách cổng được phép |
| N3 | `ns-app` | `ns-client` | Phiên TCP mới tới 8080 | **DENY** | Không cấp quyền khởi tạo chiều ngược lại |
| N4 | `ns-client` | `ns-fw` | TCP/22 | **DENY** | Không có SSH quản trị firewall trong lab |
| N5 | `ns-guest` | `ns-client` | Bất kỳ luồng mới | **DENY** | Giới hạn di chuyển ngang |

Một thiết kế production sẽ có các luồng bổ sung như DNS, NTP, syslog, health checks, VPN, backup, ứng dụng phụ thuộc và kênh quản trị được bảo vệ. Trong lab, **không mở thêm vì tiện**, mà ghi vào change request và chỉ thêm khi chứng minh được nhu cầu.

## 4. Chuẩn bị môi trường

### 4.1. Yêu cầu

- Một **máy ảo Linux dùng cho lab**, có quyền `root`/sudo và kernel hỗ trợ network namespaces, veth, nftables, conntrack.
- Các công cụ `ip` (thường từ `iproute2`), `nft`, `python3`, `curl`; trình quản lý gói tùy bản phân phối.
- Hai cửa sổ terminal trong VM: một chạy web server của lab, một dùng để thử và quản trị cấu hình.
- Không sử dụng trực tiếp VM đang làm router hoặc firewall của tổ chức.

Kiểm tra trước:

~~~bash
command -v ip
command -v nft
command -v python3
command -v curl
uname -r
ip netns list
~~~

Nếu thiếu công cụ, cài từ kho gói tin cậy của bản phân phối theo quy trình của lab. Không tùy tiện tải và chạy script cấu hình firewall không rõ nguồn. Các câu lệnh dưới đây sử dụng cú pháp **Linux/bash**, không chạy nguyên văn trong PowerShell Windows.

### 4.2. Biện pháp bảo vệ trước khi thực hành

1. Tạo snapshot VM hoặc có cách khôi phục VM độc lập.
2. Bảo đảm các tên `ns-fw`, `ns-client`, `ns-app`, `ns-guest` **chưa được sử dụng**. Nếu đã tồn tại, dừng và chọn tên mới cho toàn bộ bài; không xóa namespace không phải của mình.
3. Chạy bài trong VM riêng để không đụng địa chỉ hoặc route host đang sử dụng.
4. Ghi thời điểm bắt đầu, phiên bản OS/kernel/nftables và người thực hiện.
5. Xác nhận nguồn kiểm thử chỉ nằm trong các namespace đã tạo; không chạy Nmap vào mạng thật.
6. Giữ kênh console của VM; trong bài không sửa firewall của host, nhưng lỗi thao tác hoặc tên namespace sai vẫn có thể gây ảnh hưởng.

Trong các đoạn lệnh cấu hình, dùng một shell có quyền root trong **VM lab** (ví dụ mở bằng `sudo -i`) để tránh lặp `sudo`. Khi kết thúc, thoát shell root. Không chạy trên production.

## 5. Tạo mô hình mạng cách ly với network namespaces

### Bước 1 — Tạo bốn namespace

~~~bash
# Chạy trong Linux VM lab với quyền root.
# Kiểm tra tên trước: không chạy nếu các namespace này đã tồn tại.
ip netns list

for ns in ns-fw ns-client ns-app ns-guest; do
  ip netns add "$ns"
  ip -n "$ns" link set lo up
done
~~~

Ở đây, các namespace có bảng định tuyến và stack mạng tách nhau. Chúng chưa có đường đi ra Internet và chưa được cấu hình bridge nối với mạng host.

### Bước 2 — Tạo ba cặp veth

~~~bash
# Cặp client <-> firewall
ip link add client0 type veth peer name fwc
ip link set client0 netns ns-client
ip link set fwc netns ns-fw

# Cặp application <-> firewall
ip link add app0 type veth peer name fwa
ip link set app0 netns ns-app
ip link set fwa netns ns-fw

# Cặp guest <-> firewall
ip link add guest0 type veth peer name fwg
ip link set guest0 netns ns-guest
ip link set fwg netns ns-fw
~~~

**Điểm kiểm tra:** mỗi veth peer của firewall nằm trong `ns-fw`. Không tạo bridge chung giữa client và guest, vì như vậy một số gói có thể đi vòng firewall. Cặp veth chỉ kết nối hai endpoint đã chỉ định.

### Bước 3 — Gán địa chỉ và kích hoạt interface

~~~bash
ip -n ns-client addr add 192.0.2.10/24 dev client0
ip -n ns-fw addr add 192.0.2.1/24 dev fwc

ip -n ns-app addr add 198.51.100.20/24 dev app0
ip -n ns-fw addr add 198.51.100.1/24 dev fwa

ip -n ns-guest addr add 203.0.113.10/24 dev guest0
ip -n ns-fw addr add 203.0.113.1/24 dev fwg

ip -n ns-client link set client0 up
ip -n ns-app link set app0 up
ip -n ns-guest link set guest0 up
ip -n ns-fw link set fwc up
ip -n ns-fw link set fwa up
ip -n ns-fw link set fwg up
~~~

Dùng các lệnh sau để xác nhận chỉ có các địa chỉ mong đợi:

~~~bash
ip -n ns-fw -br addr
ip -n ns-client -br addr
ip -n ns-app -br addr
ip -n ns-guest -br addr
~~~

### Bước 4 — Cấu hình route và chuyển tiếp

~~~bash
ip -n ns-client route add default via 192.0.2.1
ip -n ns-app route add default via 198.51.100.1
ip -n ns-guest route add default via 203.0.113.1

# Chỉ bật IP forwarding trong network namespace firewall.
ip netns exec ns-fw sysctl -w net.ipv4.ip_forward=1

# Kiểm tra đường dự kiến từ client.
ip -n ns-client route get 198.51.100.20
ip -n ns-guest route get 198.51.100.20
~~~

**Tại sao không sửa `net.ipv4.ip_forward` trên host?** Bài lab muốn chuyển tiếp chỉ bên trong `ns-fw`; đổi tham số host có thể biến VM thành bộ định tuyến ngoài dự kiến. `ip netns exec` thực thi thay đổi trong namespace mạng được chọn.

### Bước 5 — Chạy dịch vụ thử nghiệm

Trong **Terminal A**, tạo thư mục chỉ có nội dung lab rồi chạy server bên trong `ns-app`. Không phục vụ thư mục cá nhân hoặc thư mục chứa thông tin nhạy cảm.

~~~bash
# Trên Linux VM lab:
sudo mkdir -p /tmp/network-fw-lab-004-web
printf 'FW-LAB-004 OK\n' | sudo tee /tmp/network-fw-lab-004-web/index.html

# Giữ terminal này để chạy web server; Ctrl+C khi kết thúc.
sudo ip netns exec ns-app python3 -m http.server 8080 \
  --bind 198.51.100.20 \
  --directory /tmp/network-fw-lab-004-web
~~~

Trong **Terminal B**, trước khi tạo firewall, xác nhận topology và baseline. Dùng `sudo -i` để có shell root như các bước cấu hình ở trên.

~~~bash
# Khi chưa áp rule, IP forwarding đã được bật trong ns-fw.
ip netns exec ns-client curl -sS --max-time 3 \
  http://198.51.100.20:8080/

ip netns exec ns-guest curl -sS --max-time 3 \
  http://198.51.100.20:8080/
~~~

Cả hai dự kiến nhận nội dung `FW-LAB-004 OK` nếu kết nối hoạt động và không có cấu hình lọc khác. **Baseline minh họa lỗ hổng:** máy khách và mạng khách đều có thể truy cập cùng ứng dụng khi chưa có chính sách. Nếu baseline không hoạt động, sửa topology, route hoặc server trước; không lắp rule rồi quy mọi timeout cho firewall.

## 6. Triển khai nftables với default deny

### 6.1. Cấu trúc chính sách

Nftables phân loại gói theo table, chain và rule. Trong bài:

- `table inet lab_filter`: dùng họ `inet`, có thể định nghĩa rule IPv4/IPv6; chính lab chỉ gán IPv4.
- `chain input`: gói tới chính firewall `ns-fw`; mặc định `drop`.
- `chain forward`: gói đi ngang qua firewall giữa các namespace; mặc định `drop`.
- `chain output`: gói mới do chính firewall khởi tạo; mặc định `drop`.
- `ct state established,related`: cho phép phần traffic thuộc kết nối đã được theo dõi.
- **Một rule cho phép**: client `192.0.2.10` đến app `198.51.100.20` TCP/8080, đúng interface và đúng trạng thái phiên mới.

**Không đặt `accept all` ở đầu chain.** Chỉ thêm những ngoại lệ có lý do rõ ràng; rule trong `forward` phải gắn với hướng, mạng nguồn/đích và dịch vụ cụ thể.

### 6.2. Tạo bộ quy tắc tối thiểu

Trong **Terminal B** (root của VM lab), nạp ruleset **vào namespace `ns-fw`**, không chạy `nft flush ruleset` ở host.

~~~bash
ip netns exec ns-fw nft -f - <<'EOF'
table inet lab_filter {
  chain input {
    type filter hook input priority 0;
    policy drop;

    iifname "lo" accept
    ct state invalid drop
    ct state established,related counter accept

    # Không có rule cho phép phiên mới đến chính firewall.
  }

  chain forward {
    type filter hook forward priority 0;
    policy drop;

    ct state invalid drop
    ct state established,related counter accept

    # Chỉ client đã duyệt được gọi web server thử nghiệm.
    iifname "fwc" oifname "fwa" ip saddr 192.0.2.10 ip daddr 198.51.100.20 tcp dport 8080 ct state new counter accept

    # Đếm gói không khớp allow, sau đó áp default drop.
    counter
  }

  chain output {
    type filter hook output priority 0;
    policy drop;

    oifname "lo" accept
    ct state invalid drop
    ct state established,related counter accept

    # Firewall không chủ động mở phiên mới trong lab.
  }
}
EOF
~~~

**Lưu ý về cú pháp:** mỗi rule nftables được viết trên một dòng trong tệp cấu hình gửi tới `nft -f`. Khác với dòng lệnh shell Bash, không dùng ký tự nối dòng Bash để chia nhỏ một rule trong tệp nftables. Nếu nạp ruleset báo lỗi, kiểm tra thông báo và phiên bản công cụ trước khi sửa; không chuyển thành “allow any” để chữa lỗi.

### 6.3. Tại sao lại dùng conntrack?

Khi client mở TCP đến app, gói SYN đầu đi theo chiều `client → app` khớp rule `ct state new`. Phần còn lại của phiên, bao gồm gói SYN-ACK và dữ liệu phản hồi từ app, được conntrack nhận diện là **established/related**, nên không cần một rule `app → client any port`.

Gói mới từ app khởi tạo sang client (không thuộc phiên được cấp) **không** khớp rule cho phép; chính sách `forward drop` sẽ từ chối.

Hệ quả cần lưu ý: connection tracking giúp điều khiển trạng thái ở lớp mạng, **không xác thực người dùng hoặc quyền ứng dụng**. Một request tới cổng 8080 được firewall cho qua vẫn cần được ứng dụng kiểm tra quyền ở môi trường thật.

### 6.4. Kiểm tra ruleset có hiệu lực

~~~bash
# Chỉ đọc quy tắc bên trong namespace lab firewall.
ip netns exec ns-fw nft -a list table inet lab_filter

# Xem các cặp veth và route của firewall.
ip -n ns-fw -br addr
ip -n ns-fw route show
~~~

Phải thấy ba chain có `policy drop`, rule `established,related`, một rule `tcp dport 8080` được phép và bộ đếm cuối chain `forward`. Nếu kết quả khác mục tiêu, dừng, xem bản cấu hình đang áp và chỉnh trong phạm vi lab.

### 6.5. Giới hạn cấu hình thử nghiệm

Không dùng toàn bộ ruleset này trên một firewall thật: các chain `input`/`output` mẫu sẽ khóa cả dịch vụ quản trị, DNS/NTP, log và các kết nối vận hành thiết yếu. Đặc biệt, `input policy drop` không phải cơ chế thay thế xác thực quản trị; trong production cần tạo đường quản trị được bảo vệ và kiểm chứng trước khi chặn mặc định.

## 7. Xác minh với phép thử được phép và bị cấm

Mỗi phép thử cần ghi `test ID`, nguồn/đích, thời điểm, kết quả client, log/counter và kết luận. **Không dựa vào mỗi timeout:** timeout còn có thể do ứng dụng tắt hoặc route lỗi.

### 7.1. P1 — Máy khách được phép truy cập web

~~~bash
ip netns exec ns-client curl -sS --connect-timeout 2 --max-time 5 \
  http://198.51.100.20:8080/
~~~

**Mong đợi:** hiển thị `FW-LAB-004 OK`. Kiểm tra Terminal A có HTTP request và trong nftables counter của rule TCP/8080 tăng. Điều này chứng minh đường đi được cho phép trong **phạm vi thử nghiệm**, chưa chứng minh các kiểm soát khác như authentication hay TLS.

### 7.2. N1 — Mạng khách bị chặn

~~~bash
ip netns exec ns-guest curl -sS --connect-timeout 2 --max-time 3 \
  http://198.51.100.20:8080/
~~~

**Mong đợi:** kết nối timeout hoặc không thành công theo hành vi `drop`. Counter ở cuối `forward` có thể tăng. Đối chiếu với server ở Terminal A: không có HTTP request hoàn chỉnh từ guest. Nếu guest truy cập được, **FAIL** và phải kiểm tra xem có một route, bridge, ruleset hoặc allow rule ngoài dự kiến.

### 7.3. N2 — Client hợp lệ nhưng sai cổng

~~~bash
ip netns exec ns-client curl -sS --connect-timeout 2 --max-time 3 \
  http://198.51.100.20:8081/
~~~

**Mong đợi:** kết nối không thành công; `8081` không được cấp trong allow rule. Trường hợp này quan trọng vì một thiết bị được phép truy cập một dịch vụ **không** được mặc định có quyền truy cập mọi cổng của đích.

### 7.4. N3 — Server mở phiên mới về client

Ví dụ một phép thử TCP từ app tới client trên cùng cổng 8080:

~~~bash
ip netns exec ns-app curl -sS --connect-timeout 2 --max-time 3 \
  http://192.0.2.10:8080/
~~~

Kết nối không được cấp phép ở chiều `app → client`. Tuy nhiên, vì `ns-client` không chạy web server, một phép thử này **không đủ để phân biệt firewall drop với việc không có listener**. Hãy dùng counter và (nếu cần trong phần nâng cao) một listener vô hại trong `ns-client` để xác minh lớp firewall.

### 7.5. N4 — Truy cập trực tiếp firewall bị chặn

~~~bash
ip netns exec ns-client curl -sS --connect-timeout 2 --max-time 3 \
  http://192.0.2.1:22/
~~~

Đây chỉ là phép thử hướng tới TCP/22 của `ns-fw`. Vì không có SSH server trên firewall trong lab, việc timeout hoặc lỗi kết nối **không chứng minh độc lập** chính sách `input drop` hoạt động. Đối chiếu ruleset `input policy drop`, thử với một dịch vụ đã biết đang lắng nghe nếu mở rộng lab và xác định vị trí enforcement.

### 7.6. Đọc counter sau thử nghiệm

~~~bash
ip netns exec ns-fw nft -a list chain inet lab_filter forward
ip netns exec ns-fw nft -a list chain inet lab_filter input
~~~

Ghi lại bộ đếm trước và sau từng phép thử để xác định rule nào nhận gói. Một gói được đếm không đồng nghĩa ứng dụng đã phục vụ thành công, và một bộ đếm `drop` tăng không tự chỉ ra danh tính người dùng. Cần kết hợp với kết quả trên client và server.

### Bảng báo cáo kỳ vọng

| ID | Kết quả dự kiến | Bằng chứng tối thiểu | Đánh giá |
|---|---|---|---|
| P1 | HTTP/8080 từ client thành công | Response ứng dụng + allow counter | PASS nếu cả hai phù hợp |
| N1 | Guest không truy cập được app | Guest test + drop counter + không có request tại server | PASS nếu không tồn tại đường bypass |
| N2 | Client không truy cập TCP/8081 | Test port 8081 + drop counter | PASS nếu không có allow ngoài scope |
| N3 | Server không được chủ động kết nối về client | Thử TCP có listener phù hợp + log/counter | Có thể INCONCLUSIVE nếu chưa tạo listener |
| N4 | Không truy cập dịch vụ quản trị của firewall | Ruleset input + test dịch vụ có listener nếu thử mở rộng | Có thể INCONCLUSIVE nếu không có listener |
| N5 | Guest không đi ngang tới client | Kết nối kiểm thử + drop counter | PASS trong phạm vi test |

**Các bài N3/N4 đã được đánh dấu giới hạn** để không tạo một kết luận quá mức từ kết quả timeout.

## 8. Giải thích phương án DROP, REJECT, LOG và cơ chế ghi nhận

### 8.1. Drop hay reject?

- `drop` phù hợp với chính sách không cung cấp thêm phản hồi cho luồng bị cấm; client thường đợi hết thời gian.
- `reject` hữu ích trong một số mạng nội bộ cần phản hồi nhanh để khắc phục lỗi. Tuy nhiên phải chọn thông báo từ chối phù hợp giao thức và không tiết lộ thông tin không cần thiết.
- Với default deny, có thể dùng `policy drop` và các rule `reject` cụ thể cho một số vùng **sau khi đánh giá**; không có quy tắc “luôn dùng drop” hay “luôn dùng reject” cho mọi môi trường.

### 8.2. Logging có giới hạn

Ghi log mọi gói bị chặn trên mạng bận có thể gây quá tải CPU, I/O và SIEM. Trong lab, có thể bật log **có rate limit** để quan sát; chỉ bật ở VM thử nghiệm:

~~~bash
# Nối vào cuối chain forward, trước verdict mặc định drop.
ip netns exec ns-fw nft add rule inet lab_filter forward \
  limit rate 2/minute log prefix "FWLAB-DENY " level info
~~~

Log kernel có thể hiển thị ở nhật ký **VM host** tùy cấu hình syslog/journald, dù gói được xử lý trong namespace. Lệnh này **không thay đổi** verdict `drop` của chain. `limit` chỉ hạn chế tần suất log, không làm giới hạn tốc độ truyền của các luồng đã được allow.

Có thể kiểm tra trên VM thử nghiệm:

~~~bash
journalctl -k -n 50 --no-pager
ip netns exec ns-fw nft -a list chain inet lab_filter forward
~~~

**Lưu ý:** nhật ký kernel thường chứa thông tin của hệ thống VM, nên chỉ thu và chia sẻ những dòng cần thiết; không công bố IP, thông tin nhận dạng, dữ liệu nhạy cảm của mạng thật.

### 8.3. Cách đánh giá cảnh báo

Một kết nối bị chặn có thể là lỗi cấu hình, phần mềm đang chạy sai, thiết bị mới hoặc hoạt động độc hại. Không tự phân loại một drop là xâm nhập. Những dấu hiệu đáng ưu tiên gồm số lượng nguồn/đích bất thường, port quản trị, đường đi vượt phân đoạn, thời điểm phát sinh, identity và các sự kiện trên endpoint.

## 9. Gỡ lab và rollback an toàn

Điểm mạnh của network namespace lab là **không đòi hỏi chỉnh firewall host**. Sau khi lưu bằng chứng và ngừng server ở Terminal A bằng **Ctrl+C**, trong Terminal B, chỉ xóa những namespace đã tạo cho bài này:

~~~bash
# Kiểm tra danh sách và bảo đảm đúng các namespace do lab tạo.
ip netns list

# Chỉ thực hiện sau khi chắc chắn đây là namespace của bài học.
for ns in ns-client ns-app ns-guest ns-fw; do
  ip netns del "$ns"
done

# Kiểm tra lại: các tên lab phải biến mất.
ip netns list
~~~

Khi xóa namespace, những veth interfaces bên trong sẽ được kernel dọn cùng namespace nếu không còn tiến trình giữ namespace. Nếu còn tiến trình, lệnh `ip netns del` có thể không giải phóng ngay mọi tài nguyên; cần dừng process thuộc bài lab rồi xác minh. **Không chạy `nft flush ruleset` trên host** để “dọn sạch”; nó có thể phá firewall host ngoài phạm vi bài học.

Thư mục chứa trang web giả của lab không thuộc namespace, có thể xóa thủ công khi chắc chắn chỉ chứa nội dung do bài học tạo:

~~~bash
# Chỉ xóa đúng file và thư mục thử nghiệm khi không còn dùng.
sudo rm -f /tmp/network-fw-lab-004-web/index.html
sudo rmdir /tmp/network-fw-lab-004-web
~~~

Không dùng `rm -rf` trên thư mục khác. Nếu tên namespace hoặc thư mục đã tồn tại trước khi bắt đầu, **không áp dụng các lệnh cleanup mẫu lên tài nguyên đó**.

### Trong sản xuất, rollback phải khác

Với một firewall thật, rollback cần khôi phục **đúng rule/commit đã thay đổi** và không ghi đè thay đổi hợp lệ của nhóm khác. Trước khi chuyển policy sang default deny, luôn có:

- Backup cấu hình và revision được xác nhận.
- Kênh console/OOB hoặc management VLAN không phụ thuộc luồng sắp khóa.
- Danh sách dependency, cửa sổ thay đổi, phê duyệt và người chịu trách nhiệm.
- Kế hoạch dừng/khôi phục nếu mất liên lạc, làm hỏng DNS/VPN, thay đổi NAT hoặc phá dịch vụ quan trọng.
- Positive/negative tests từ nhiều vùng, kể cả failover và IPv6 khi có.

## 10. Chuyển từ lab sang thiết kế mạng thực tế

Trong môi trường thật, default deny phải dựa trên **ma trận luồng nghiệp vụ**, không phải sao chép ruleset của bài học.

### 10.1. Kiểm kê luồng và chủ sở hữu

Cần biết:

- Tài sản/ứng dụng được phép tạo phiên mới đến những đích nào.
- Giao thức, port, chiều, định danh nguồn, chứng chỉ và loại quyền cần thiết.
- Các luồng vận hành: DNS, DHCP, NTP, IdP/RADIUS, SSH/HTTPS quản trị, syslog/SIEM, backup, monitoring, PKI, update repositories.
- Các luồng hiếm: failover, disaster recovery, job định kỳ, thay chứng chỉ, backup/restore, scaling.
- Đường Internet, VLAN nội bộ, cloud VPC/VNet, private endpoint, VPN, Wi-Fi và tenant khác.

Không thấy lưu lượng trong 15 phút **không chứng minh** dịch vụ không cần; việc thu baseline phải đủ chu kỳ hoạt động, kết hợp chủ hệ thống và kế hoạch DR.

### 10.2. Phân biệt ba loại traffic

1. **Input:** vào chính firewall/router/VM; đặc biệt nhạy cảm ở management plane. Cho phép quản trị từ bastion/VLAN quản trị có xác thực, không mở SSH từ mọi nguồn.
2. **Forward:** đi xuyên qua thiết bị kiểm soát. Thiết kế theo cặp nguồn–đích–dịch vụ, phân đoạn và danh tính nếu có hỗ trợ.
3. **Output:** do chính firewall/host khởi tạo. Trong production có thể cần NTP, DNS, syslog, giám sát và cập nhật; `output drop` mà không thiết kế rule cần thiết có thể làm hỏng vận hành.

**Bộ rule lab khóa tất cả phiên mới từ chính firewall** vì firewall namespace không cần gọi dịch vụ ngoài. Đây không phải cấu hình production mặc định có thể áp trên mọi router/firewall.

### 10.3. IPv4 và IPv6

Bài lab dùng địa chỉ IPv4; table `inet` không có nghĩa đã thiết kế đủ chính sách IPv6. Trên mạng thật cần xem:

- IPv6 addressing, route, prefix delegation, RA/ND, DNS AAAA và kết nối trực tiếp.
- Quy tắc tương ứng cho luồng IPv6, không vô tình có một allow rộng hơn IPv4.
- ICMPv6 cần thiết cho hoạt động mạng; **chặn toàn bộ ICMPv6 có thể làm hỏng Neighbor Discovery và Path MTU Discovery**.
- Thiết bị có thể hỗ trợ IPv6 ngay cả khi đội vận hành chỉ kiểm thử IPv4.

Không tự sao chép `ip saddr`/IPv4 rules sang IPv6 bằng cách thay chuỗi địa chỉ; kiểm tra semantics và lưu lượng điều khiển của IPv6.

### 10.4. DNS, VPN và Wi-Fi

- **DNS:** client chỉ được hỏi resolver được phép; xem TCP/UDP 53, DoT/DoH và lưu lượng trả lời, logging, DNS filtering. Nếu không có DNS, một phép thử bằng IP trực tiếp có thể thành công nhưng ứng dụng vẫn không hoạt động.
- **VPN:** có MFA không có nghĩa tài khoản được phép truy cập cả LAN. Luồng mới phải giới hạn theo nhóm/người dùng/thiết bị, subnet, ứng dụng và phiên.
- **Wi-Fi/NAC:** guest và IoT cần vùng riêng; khi RADIUS/802.1X lỗi, không tự cấp full corporate VLAN. Lưu lượng của guest tới management hoặc DB cần âm tính khi kiểm thử.
- **IDS/IPS:** default deny giảm đường không cần thiết, nhưng traffic được allow vẫn cần giám sát và kiểm tra ở lớp phù hợp. Trong failover, tuyến mới không được bỏ qua chính sách bắt buộc.

### 10.5. Cloud và Kubernetes

| Nền tảng | Điểm thực thi | Điểm dễ nhầm |
|---|---|---|
| Cloud security group | Ingress/egress với các semantics stateful theo nền tảng | Một allow mới không tự thay thế allow rộng cũ; phải xem **effective policy** |
| Subnet NACL / NSG | Kiểm soát vùng mạng, có thể stateless hoặc stateful tùy dịch vụ | Thứ tự rule, chiều trả lời và ưu tiên khác nhau theo sản phẩm |
| Network virtual appliance | Firewall trong tuyến nội bộ/cloud | Route failover có thể đi vòng appliance nếu cấu hình sai |
| Kubernetes NetworkPolicy | Quy tắc ingress/egress trên pod theo selector | Cần CNI hỗ trợ; nhiều allow policies có thể cộng gộp |
| Service mesh/mTLS | Xác thực, ủy quyền workload/application | Không thay cho route/security group ở mọi lớp |
| Host firewall | Luồng đến/from chính VM | VM có thể có nhiều NIC, IPv6, container và port published |

Với Kubernetes, triển khai default-deny ingress/egress cho pod cần **thêm các luồng cho DNS và dependency thực sự**. Không áp policy chặn hết egress trên production mà chưa kiểm thử resolution, API, telemetry và các dịch vụ hỗ trợ.

## 11. Mở rộng lab theo từng cấp độ

### Bài nâng cao A — Thay allow rộng bằng danh sách chính xác

Thử thay `ip saddr 192.0.2.10` bằng một subnet lớn để quan sát nguy cơ: guest vẫn bị chặn do interface khác, nhưng một máy khác xuất hiện trong cùng client subnet có thể được cấp quyền quá mức. Sau đó đưa rule về /32.

**Mục tiêu:** hiểu sự khác biệt giữa một host và cả CIDR, cũng như vai trò của interface/zone. Không nhất thiết phải chạy với toàn bộ mạng ngoài lab.

### Bài nâng cao B — Thêm DNS có chủ đích

Thiết kế thêm resolver namespace riêng (chỉ trong lab), cấp một luồng UDP/TCP 53 cần thiết và kiểm thử rằng DNS tới resolver ngoài phạm vi bị chặn. Phân biệt ứng dụng hoạt động bằng IP và hoạt động bằng tên miền.

**Mục tiêu:** default deny không thể chỉ nhìn port của dịch vụ chính; nó còn phải xét dependency và cách dịch vụ định danh đích.

### Bài nâng cao C — Quản trị firewall qua một vùng riêng

Tạo namespace quản trị với một cặp veth mới và SSH daemon thử nghiệm có cấu hình riêng, chỉ cho phép nguồn quản trị định danh rõ ràng. Kiểm chứng từ client và guest không đăng nhập được; tài khoản quản trị có ghi log và quyền hạn phù hợp.

**Mục tiêu:** tách management plane khỏi data plane. Đừng vô tình mở SSH của host hoặc sử dụng mật khẩu mặc định.

### Bài nâng cao D — Phát hiện quét cổng nhẹ và quan sát drop

Trong phạm vi lab đã được phê duyệt, tạo một số kết nối TCP thử tới các port không được cho phép; kiểm tra counter/log có rate limit, phân biệt kết nối bị chặn với server không có listener.

**Mục tiêu:** chuyển từ cấu hình chính sách sang kiểm chứng và giám sát. Không tự quét hệ thống ngoài lab.

### Bài nâng cao E — Kiểm chứng failover và policy parity

Dựng thêm một firewall namespace dự phòng với cùng policy trong môi trường mô phỏng đã lên kế hoạch. Chuyển route thử từ firewall A sang firewall B, kiểm tra P1 vẫn hoạt động và N1/N2 vẫn bị chặn. Tính cả mất session, khả năng failback và telemetry.

**Mục tiêu:** một đường dự phòng không được trở thành đường vòng qua firewall.

## 12. Những lỗi thường gặp khi dùng default deny

| Sai lầm | Hậu quả | Cách khắc phục |
|---|---|---|
| Bật `drop` ngay trên máy production đang SSH mà không có ngoại lệ/OOB | Mất quyền quản trị hoặc gián đoạn dịch vụ | Có console/OOB, backup, rule management trước, commit-confirmed nếu hỗ trợ |
| Dùng `allow any` để “khắc phục” outage | Phá nguyên tắc tối thiểu và tạo đường lan truyền | Xác định đúng nguồn/đích/port/identity và cấp có thời hạn |
| Chỉ test kết nối thành công | Không thấy guest/user đi vào vùng nhạy cảm | Chạy **negative tests** cùng với positive tests |
| Tin timeout là do firewall | Có thể do route, DNS, host/port không chạy | Đối chiếu listener, route, rule counter và log tại enforcement point |
| Không xét established/related | Phản hồi kết nối hợp lệ bị rớt hoặc mở chiều về quá rộng | Dùng stateful rule có kiểm soát, hiểu giao thức |
| Chặn toàn bộ ICMP/ICMPv6 | Chẩn đoán khó và IPv6 có thể hỏng ND/PMTUD | Thiết kế thông báo điều khiển cần thiết theo nền tảng |
| Chỉ bảo vệ north-south | Lưu lượng giữa các vùng hoặc cùng subnet có thể không đi qua firewall | Đặt segmentation/host controls và sensor ở nơi có đường đi |
| Bỏ qua NAT, IPv6, container, cloud peering | Quy tắc nhìn đúng nhưng không khớp luồng thực tế | Kiểm tra địa chỉ tại điểm thực thi và các đường thay thế |
| Không có logging/expiry | Không biết rule đã dùng ra sao, ngoại lệ tồn tại quá lâu | Có owner, audit, counter, log rate limit, review định kỳ |
| Rollback bằng `flush ruleset` trên host | Xóa cả firewall bảo vệ host hoặc rule của ứng dụng khác | Chỉ rollback đúng table/chain/rule đã thay đổi theo change record |
| Chỉ dựa trên IP | Máy bị chiếm trong dải được cấp vẫn sử dụng kết nối hợp lệ | Thêm xác thực, TLS/mTLS, quyền ứng dụng, device posture và EDR |
| Copy lệnh lab vào production | Khóa DNS/NTP/VPN, SSH và monitoring | Dựng ma trận dependency, staging, phê duyệt và triển khai từng bước |

## 13. Khung báo cáo kết quả dự án

Người học nộp một báo cáo ngắn nhưng có chứng cứ, chẳng hạn:

~~~yaml
lab_id: "FW-DEFAULT-DENY-004"
environment: "isolated-linux-vm"
objective: "Only approved client can access app TCP/8080"
topology:
  client: "ns-client / 192.0.2.10"
  app: "ns-app / 198.51.100.20"
  guest: "ns-guest / 203.0.113.10"
  firewall: "ns-fw"
policy:
  default_input: "drop"
  default_forward: "drop"
  default_output: "drop"
  allow_new:
    source: "192.0.2.10"
    destination: "198.51.100.20"
    protocol: "tcp"
    destination_port: 8080
  allow_established_related: true
evidence:
  - "nft list table inet lab_filter -a"
  - "P1 client curl output and server request"
  - "N1 guest curl and forward drop counter"
  - "N2 wrong-port test and forward drop counter"
test_results:
  P1: "pending"
  N1: "pending"
  N2: "pending"
  N3: "not-run or inconclusive until extra listener"
  N4: "not-run or inconclusive until service-backed test"
cleanup: "pending"
remaining_risks:
  - "Firewall is IP-based, not user-authenticated"
  - "Application example uses HTTP only inside isolated lab"
  - "IPv6 and production service dependencies are outside base lab"
~~~

Các giá trị `pending` phải được cập nhật dựa trên **kết quả học viên tự quan sát**; không ghi `PASS` nếu chưa chạy hoặc chưa có chứng cứ. Báo cáo nên bổ sung timestamp, ảnh chụp/log cần thiết, phiên bản công cụ, đường dẫn evidence có quyền truy cập phù hợp và các lỗi gặp phải khi khôi phục.

### Tiêu chí đánh giá

| Hạng mục | Trọng số gợi ý | Điều kiện đạt |
|---|---:|---|
| Topology và baseline | 20% | Namespace/route đúng, thấy guest ban đầu có thể truy cập app |
| Rule default deny | 25% | Ba chain có `policy drop`, allow theo đúng luồng P1 |
| Phép thử và đối chiếu bằng chứng | 25% | P1 thành công; N1/N2 bị chặn; có rule counters/log phù hợp |
| Phân tích bảo mật | 15% | Nêu được giới hạn IP/port, stateful tracking, identity/TLS/IPv6 |
| Cleanup và rollback | 15% | Dọn đúng namespace của bài, không sửa firewall host |

Tỷ trọng chỉ phục vụ hướng dẫn học; giảng viên có thể điều chỉnh. Một thử nghiệm không có âm tính hợp lệ **chưa chứng minh được** default deny hoạt động như thiết kế.

## 14. Checklist thực hành

- [ ] Bài thử nằm trên VM Linux cô lập, có quyền quản trị và cách phục hồi.
- [ ] Đã kiểm tra namespace name chưa được sử dụng trước khi tạo.
- [ ] Đã dựng đúng ba cặp veth và route qua `ns-fw`, không có bridge nối tắt.
- [ ] Đã quan sát baseline khi chưa cài nftables policy.
- [ ] Đã nạp ruleset chỉ trong `ns-fw` và xác minh `input/forward/output policy drop`.
- [ ] Rule cho phép chỉ khớp nguồn, đích, hướng và TCP/8080 được phê duyệt.
- [ ] `ct state established,related` cho phép phản hồi của phiên hợp lệ.
- [ ] P1 thành công, N1/N2 bị chặn với counter và bằng chứng từ server.
- [ ] N3/N4 có kết luận theo đúng giới hạn của phương pháp thử, không suy đoán từ timeout.
- [ ] Đã xem rủi ro IP spoofing, quyền ứng dụng, TLS, DNS, VPN, IPv6 và các lớp bổ sung.
- [ ] Đã ghi log/báo cáo, dừng web server và xóa đúng tài nguyên lab.
- [ ] Có phương án triển khai production riêng với owner, approval, dependency và rollback.

## 15. Câu hỏi tự kiểm tra và bài tập

1. Vì sao default deny có ý nghĩa hơn việc “chặn một danh sách cổng nguy hiểm”? Nó có hạn chế gì nếu chỉ dùng IP/port?
2. Phân biệt `input`, `forward`, `output` tại firewall Linux. Nếu chặn `output` của một firewall thật, dịch vụ vận hành nào có thể bị ảnh hưởng?
3. Giải thích vì sao client được mở phiên mới TCP/8080 nhưng server không được tự khởi tạo mọi phiên về client.
4. Nếu guest timeout tới app, những bằng chứng nào giúp kết luận firewall đã chặn thay vì ứng dụng bị tắt?
5. Khi subnet App tăng từ 2 máy lên 200 máy, cấp toàn bộ CIDR làm source của rule có hệ quả gì? Có cách định danh nào tốt hơn?
6. Nếu ứng dụng cần thêm DNS và NTP, bạn sẽ lập ma trận luồng và kiểm thử các dependency như thế nào trước khi thêm rule?
7. Vì sao dùng `table inet` không có nghĩa chính sách IPv6 của bài đã hoàn chỉnh?
8. Một route failover chuyển traffic sang router bỏ qua firewall chính. Cần phép thử âm tính nào để phát hiện?
9. Với Kubernetes, tại sao chỉ tạo một NetworkPolicy tên “default-deny” chưa chắc đã bảo đảm hiệu lực? Bạn cần xác minh gì về CNI và tập policy khác?
10. Hãy thiết kế phiên bản production của lab: tách user/guest/app/DB/management, sử dụng HTTPS, xác thực ứng dụng, logging, owner, rollback và kiểm thử trước/sau khi áp chính sách.

**Điểm cần nhớ:** default deny là **một nguyên tắc kiểm soát đường đi**, không phải một câu lệnh thần kỳ. Một firewall đáng tin phải có danh sách luồng được phê duyệt, quy tắc cho phép tối thiểu, xử lý trạng thái kết nối đúng, phép thử chứng minh cả **luồng hợp lệ hoạt động** lẫn **luồng ngoài phạm vi bị chặn**, và kế hoạch khôi phục an toàn khi có lỗi.
