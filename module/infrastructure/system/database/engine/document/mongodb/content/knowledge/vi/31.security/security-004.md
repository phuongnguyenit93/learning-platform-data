# Giới hạn mạng, bindIp, firewall và kiểm soát truy cập Atlas trong MongoDB

Một ứng dụng có thể có tên người dùng và mật khẩu MongoDB chính xác nhưng vẫn không kết nối được vì database chỉ lắng nghe trên `127.0.0.1`. Ở chiều ngược lại, ứng dụng có thể kết nối dễ dàng vì database lắng nghe trên mọi interface và firewall cho phép cả Internet truy cập cổng 27017. Trường hợp thứ hai tiện cho thử nghiệm ngắn hạn nhưng tạo một bề mặt tấn công lớn nếu không được kiểm soát.

Trong chương **Bảo mật** của module **Database Engine Document MongoDB**, bài **Giới hạn mạng, bindIp, firewall và kiểm soát truy cập Atlas** hướng dẫn tư duy bảo vệ đường đi từ ứng dụng tới MongoDB. Bài không xem việc “kết nối thành công” là tiêu chuẩn duy nhất: một triển khai tốt còn phải bảo đảm **chỉ đúng nguồn, đúng dịch vụ và đúng identity có quyền truy cập**, với đường truyền được mã hóa.

Sau bài học, bạn sẽ phân biệt được `net.bindIp` và firewall, hiểu localhost/private/public IP, kiểm soát các luồng của replica set và sharded cluster, cấu hình Atlas IP Access List ở mức khái niệm, lựa chọn public connection hoặc private networking, chẩn đoán lỗi theo tầng, và áp dụng nguyên tắc least privilege khi triển khai.

> **Phạm vi:** mọi địa chỉ IP và hostname trong ví dụ là giả định cho môi trường lab. Không mở cổng MongoDB trên máy public, tắt authentication hoặc thay firewall production chỉ để chạy thử những ví dụ.

## 1. Đường đi của một kết nối MongoDB

Một kết nối thông thường đi qua nhiều lớp:

```text
Ứng dụng Java / Node.js / mongosh
              |
              v
        DNS / SRV lookup
              |
              v
       Route / NAT / VPN
              |
              v
 Firewall / security group / network ACL
              |
              v
        Server IP + TCP port
              |
              v
        mongod/mongos bindIp
              |
              v
       TLS và xác minh certificate
              |
              v
      MongoDB authentication (AuthN)
              |
              v
       Authorization (AuthZ / RBAC)
              |
              v
       Database và collection
```

Một kết nối chỉ hoạt động khi mọi lớp có liên quan đều nhất quán:

- DNS phân giải được hostname tới địa chỉ/endpoint đúng.
- Client có route tới endpoint và được phép đi ra ngoài.
- Firewall ở server/cloud cho phép nguồn phù hợp tới port cần thiết.
- MongoDB thực sự lắng nghe trên IP:port đó.
- Client và server thống nhất về TLS và tin cậy chứng chỉ thích hợp.
- Client có credential hợp lệ và đủ database permissions.

Chẳng hạn, **tăng role lên `root` không giải quyết một lỗi TCP timeout**, và **thêm IP vào firewall không sửa được mật khẩu sai**. Phải xác định lỗi ở lớp nào trước khi thay cấu hình.

### Bốn câu hỏi thường bị đánh đồng

| Lớp | Câu hỏi | Ví dụ |
| --- | --- | --- |
| Listener | Tiến trình nhận kết nối tại **địa chỉ nào của máy chủ**? | `127.0.0.1`, `10.10.20.12` |
| Firewall | **Nguồn client nào** được phép đi tới đích/port đó? | `10.20.30.0/24` tới TCP 27017 |
| Authentication | Client là **ai**? | User SCRAM, x.509 identity |
| Authorization | Identity đó được **làm gì**? | `read` hoặc `readWrite` trên một DB |

TLS là một lớp bảo vệ đường truyền và danh tính server, không thay thế bất kỳ mục nào trong bảng.

## 2. Xây threat model trước khi cấu hình

Xét hệ thống có web frontend, một API backend và MongoDB:

```text
Người dùng Internet
       |
       v
  HTTPS API Gateway
       |
       v
Backend private subnet
  10.20.30.10, 10.20.30.11
       |
       v
MongoDB private host
      10.10.20.12
```

Người dùng cuối chỉ cần gọi HTTPS API, **không cần trực tiếp kết nối tới cổng database**. Chỉ backend servers, các thành phần cluster nội bộ và những máy vận hành đã được cấp quyền mới có lý do truy cập MongoDB.

Những rủi ro cần cân nhắc:

1. Lộ TCP 27017 qua public IPv4/IPv6.
2. Mật khẩu hoặc URI bị commit vào repository.
3. Credential của một service được cấp quyền quá rộng.
4. Traffic có thể bị nghe lén nếu không có TLS.
5. Một application server đã bị xâm nhập có thể truy cập DB vì cùng mạng.
6. Một rule firewall hoặc Atlas access list quá rộng tồn tại lâu hơn thời hạn sử dụng.
7. Cluster có thêm member hoặc thay NAT egress IP nhưng policy không được cập nhật.

Chính sách cơ bản là **giảm bề mặt mạng**, nhưng **không coi việc nằm trong mạng riêng là đủ để được tin cậy**.

## 3. `net.bindIp` có ý nghĩa gì?

Với MongoDB tự quản lý, `net.bindIp` quy định **những địa chỉ mạng cục bộ mà `mongod` hoặc `mongos` lắng nghe**. Nó không phải danh sách IP client được phép.

Giả sử server MongoDB có:

```text
Loopback:          127.0.0.1
Private interface: 10.10.20.12
Public interface:  203.0.113.12
```

Địa chỉ `203.0.113.12` thuộc dải dành cho tài liệu, không phải địa chỉ server thực.

### Chỉ cho ứng dụng trên cùng máy

```yaml
net:
  port: 27017
  bindIp: "127.0.0.1"
```

MongoDB chỉ lắng nghe trên IPv4 loopback. Một process cùng host có thể thử kết nối bằng `mongodb://127.0.0.1:27017`. Máy ở subnet khác không thể dùng private IP server để đi vào listener này.

### Cho phép lắng nghe trên private interface

```yaml
net:
  port: 27017
  bindIp: "127.0.0.1,10.10.20.12"
```

MongoDB lắng nghe trên loopback và private NIC của host. Ứng dụng ở máy khác **có thể thử** kết nối tới `10.10.20.12:27017` nếu route/firewall/TLS/AuthN/AuthZ đều cho phép.

### Sai lầm: đặt IP client vào `bindIp`

Ứng dụng có IP `10.20.30.10`, DB server có IP `10.10.20.12`. Nếu trên DB server cấu hình:

```yaml
net:
  bindIp: "10.20.30.10"
```

thì tiến trình có thể không bind được vì `10.20.30.10` **không thuộc host MongoDB**. Muốn chỉ client `10.20.30.10` truy cập, dùng firewall/source ACL, không dùng `bindIp`.

**Ghi nhớ:** `bindIp` chọn **địa chỉ đích cục bộ của server**, còn firewall chọn **địa chỉ nguồn được phép**.

## 4. So sánh localhost, private IP và wildcard

| Địa chỉ | Tác dụng | Lưu ý |
| --- | --- | --- |
| `127.0.0.1` | IPv4 loopback | Thích hợp development cùng máy |
| `::1` | IPv6 loopback | Cần cấu hình IPv6 phù hợp |
| `10.10.20.12` | Một private IPv4 được gán trên server | Phù hợp backend private networking |
| `203.0.113.12` | Public IPv4 minh họa | Không nên expose database public nếu không cần |
| `0.0.0.0` | Tất cả IPv4 interfaces | Có thể bao gồm public NIC |
| `::` | IPv6 wildcard | Cần xét IPv6 exposure riêng |

Nếu dùng:

```yaml
net:
  port: 27017
  bindIp: "0.0.0.0"
```

thì MongoDB không còn chỉ lắng nghe loopback hoặc một private interface cụ thể. Khi host có public NIC và network rules cho phép, cổng MongoDB có thể bị tiếp cận từ Internet.

### `net.bindIpAll`

MongoDB hỗ trợ cơ chế lắng nghe trên tất cả những interface được cấu hình, ví dụ:

```yaml
net:
  port: 27017
  bindIpAll: true
```

Tùy môi trường khởi chạy, cờ tương đương có thể là `--bind_ip_all`. **Không kết hợp `net.bindIp` và `net.bindIpAll` một cách tùy tiện**: chúng là những cơ chế chọn listener thay thế nhau.

Một container được cô lập có thể cần `bindIpAll` bên trong network namespace của container để nhận traffic từ container khác, nhưng điều đó **không chứng minh** host và published port của container đã an toàn. Luôn xem exposure thực tế.

### Khi không ghi `bindIp`

Trong nhiều cấu hình mặc định của MongoDB tự quản lý, MongoDB chỉ lắng nghe localhost. Nhưng package, container image, Helm chart hoặc automation có thể ghi đè giá trị. Vì vậy cần **đọc cấu hình đang chạy và socket listener**, không mặc định rằng mọi deployment không ghi `bindIp` đều an toàn.

## 5. Cẩn thận với IPv6

Việc kiểm tra IPv4 chưa đủ nếu server có IPv6. Một host có thể có:

```text
IPv4 private: 10.10.20.12
IPv6 global:  2001:db8:1234::12
```

`2001:db8::/32` là dải IPv6 dành cho ví dụ. Cần kiểm tra:

- `net.ipv6` và cấu hình listener IPv6 của MongoDB.
- Các địa chỉ `::1`, `::` hoặc IPv6 cụ thể trong socket list.
- DNS AAAA records và route IPv6.
- Cloud/host firewall rules cho IPv6.
- DNS resolver của client có ưu tiên IPv6 hay không.

Một host có thể chặn mọi inbound IPv4 không mong muốn nhưng vẫn có đường vào IPv6 nếu rule thiếu. **Đừng khẳng định database không public chỉ vì một lần kiểm tra trên IPv4 trả timeout.**

## 6. Firewall khác `bindIp` như thế nào?

Giả sử DB bind `10.10.20.12:27017` và một firewall cho phép nguồn `10.20.30.10`.

```text
Client: 10.20.30.10
       |
       v
Router / subnet route
       |
       v
Firewall: allow source 10.20.30.10
       |
       v
Server interface 10.10.20.12:27017
       |
       v
mongod listener
```

Nếu firewall chặn, packet không đến listener. Nếu server không bind vào `10.10.20.12`, dù firewall cho phép, cũng không có MongoDB socket phù hợp để nhận kết nối.

### Rule mẫu theo least privilege

| Source | Destination | Giao thức | Action |
| --- | --- | --- | --- |
| `10.20.30.10/32` | `10.10.20.12:27017` | TCP | Allow |
| `10.20.30.11/32` | `10.10.20.12:27017` | TCP | Allow |
| Bastion được quản lý | `10.10.20.12:27017` | TCP | Allow có giám sát |
| Internet bất kỳ | `10.10.20.12:27017` | TCP | Deny |

Một **allow rule mới** không nhất thiết xóa hay ghi đè những allow rules rộng hơn đã tồn tại. Review exposure phải xét **tập tất cả rules** trong firewall hiện hành.

## 7. Nhiều lớp firewall: host, cloud, network ACL và egress

Đường kết nối có thể đi qua:

1. Host firewall: UFW/nftables/iptables trên Linux, Windows Defender Firewall trên Windows.
2. Cloud security group hoặc network firewall bảo vệ VM/NIC.
3. Subnet network ACL, có thể stateless và cần rule hai chiều.
4. Router, VPN, VPC/VNet peering, NAT gateway.
5. Kubernetes NetworkPolicy hoặc service mesh khi network plugin thực thi.
6. Firewall ở ranh giới mạng công ty/đối tác.

**Cho phép ở một lớp không tự vượt qua lệnh chặn ở lớp khác.**

Một kết nối MongoDB thường do client mở, nên cần:

- Client egress tới hostname/IP và port của DB.
- Server ingress từ IP nguồn mà nó nhìn thấy.
- Đường trả lời hoạt động theo stateful/stateless policy.

Nếu công ty chặn outbound TCP 27017, app vẫn không kết nối được Atlas dù IP đã được thêm vào Atlas Project IP Access List.

### Stateful và stateless filtering

Security group/host firewall thường có tracking trạng thái kết nối; packet phản hồi của connection hợp lệ được xử lý theo state. Một số network ACL ở cấp subnet có thể là **stateless**, nên cần xét cả response traffic và ephemeral client ports. Không nên áp dụng công thức “mở inbound 27017 là đủ” cho mọi sản phẩm mạng.

## 8. Cổng MongoDB, replica set và sharded cluster

`mongod` và `mongos` thường dùng **TCP 27017** nếu không cấu hình khác. Một số môi trường hoặc chế độ khởi chạy có thể sử dụng các cổng khác, ví dụ 27018/27019 trong các cấu hình chuyên biệt. **Port thực tế phụ thuộc deployment**, không phải luôn cố định theo một sơ đồ chung.

### Replica set

```text
Application
    |
    +----> rs-a.example:27017
    +----> rs-b.example:27017
    +----> rs-c.example:27017
```

Driver dùng replica set topology: nó có thể khám phá thêm member hosts sau khi kết nối seed. Nếu client chỉ tới được `rs-a` mà firewall chặn `rs-b` và `rs-c`, kết nối có thể hoạt động lúc đầu rồi fail khi primary đổi node.

### Sharded cluster

```text
Application
    |
    v
  mongos endpoint
    |
    +----> shard replica set A
    +----> shard replica set B
    +----> config server replica set
```

Ứng dụng thường kết nối thông qua **`mongos`** hoặc endpoint được quản lý phù hợp, không trực tiếp đọc sharded collection trên một shard node bất kỳ.

### Phân luồng bảo mật

- Client-to-router/replica-set-member traffic: chỉ app subnet/ops source được phép.
- Replica-set member-to-member traffic: chỉ các members liên quan được phép, có internal authentication.
- Shard/config-server/mongos traffic: chỉ các thành phần cluster cần thiết.
- Admin/backup/monitoring: từ những host quản trị được cho phép và theo chính sách riêng.

Không vì cluster có nhiều node mà mở toàn bộ các cổng nội bộ ra Internet. **HA cần đủ đường mạng, không cần public exposure rộng.**

## 9. Mạng thông chưa có nghĩa truy cập dữ liệu được phép

Ba lớp sau mạng là:

**TLS:** mã hóa traffic và xác minh certificate/hostname server.

**Authentication (AuthN):** xác định client là user/service nào thông qua SCRAM, x.509 hoặc cơ chế được hỗ trợ.

**Authorization (AuthZ):** kiểm tra user có role cho phép lệnh đối với namespace liên quan hay không.

Ví dụ một account chỉ đọc:

```text
service: reporting-reader
MongoDB database: ordersdb
Role: read
Không cấp: readWrite/root/clusterAdmin
```

Tài khoản đã đăng nhập nhưng chạy `insertOne()` bị `not authorized` là dấu hiệu **kiểm soát quyền đang hoạt động**, không phải lỗi firewall.

### Ví dụ `mongod.conf` với TLS và authorization

```yaml
net:
  port: 27017
  bindIp: "127.0.0.1,10.10.20.12"
  tls:
    mode: requireTLS
    certificateKeyFile: "/etc/mongodb/tls/server.pem"
security:
  authorization: enabled
```

Đây là **cấu hình minh họa một phần**, không phải toàn bộ production config. Cần có users/roles, certificate chain và CA, private-key permissions, secret rotation; với replica set/sharded cluster còn cần internal member authentication (chẳng hạn keyfile/x.509) phù hợp. Việc chỉnh `mongod.conf` có thể cần restart/rolling rollout có kiểm soát.

**Không dùng `tlsInsecure` hoặc bỏ qua certificate validation làm giải pháp dài hạn.** Nếu TLS hostname mismatch, hãy sửa hostname, certificate SAN và CA trust theo deployment thực tế.

## 10. Cấu hình lab và môi trường private

### Lab cùng máy

```yaml
net:
  port: 27017
  bindIp: "127.0.0.1"
```

App cùng host sử dụng:

```text
mongodb://127.0.0.1:27017/appdb
```

Lab có thể chưa có production auth/TLS, nhưng **không vì vậy được dùng cấu hình này trực tiếp cho server public hoặc môi trường có dữ liệu nhạy cảm**. Loopback vẫn có thể bị tiến trình độc hại trên cùng host tiếp cận.

### Server private

```yaml
net:
  port: 27017
  bindIp: "127.0.0.1,10.10.20.12"
  tls:
    mode: requireTLS
    certificateKeyFile: "/etc/mongodb/tls/server.pem"
security:
  authorization: enabled
```

Kèm chính sách mạng:

```text
ALLOW tcp/27017
  source: 10.20.30.10/32, 10.20.30.11/32
  destination: 10.10.20.12
DENY tcp/27017
  source: everything else
```

Đây là ví dụ cho cách kết hợp **listener + network ACL + TLS + auth**. Phần cấu hình cluster nội bộ và quản trị hạ tầng vẫn cần thực hiện theo chính sách riêng.

## 11. Firewall Linux và Windows: ví dụ để hiểu rule

Trên Linux với UFW, ví dụ một allow rule:

```bash
# Chỉ là mẫu; kiểm tra policy hiện tại trước khi áp dụng.
sudo ufw allow from 10.20.30.0/24 to 10.10.20.12 port 27017 proto tcp

# Chỉ đọc tình trạng rule.
sudo ufw status verbose
```

Trên Windows PowerShell:

```powershell
# Mẫu rule, cần quyền phù hợp; không chạy tùy tiện trên production.
New-NetFirewallRule -DisplayName "MongoDB trusted app subnet" -Direction Inbound -Protocol TCP -LocalPort 27017 -RemoteAddress 10.20.30.0/24 -Action Allow
```

Hai lệnh **chỉ thêm allow rule**, không tự bảo đảm policy tổng thể đang chặn những source khác. Trước khi bật/thay default firewall policy qua SSH/remote session, phải bảo đảm đường quản trị và khả năng rollback, tránh tự khóa quyền truy cập máy chủ.

## 12. Docker: localhost của container không phải localhost của host

Docker tạo network namespace riêng:

```text
Host: 127.0.0.1
   |
   +--> Published port
             |
             v
       MongoDB container
       127.0.0.1 của container
       Container network address
```

Nếu `mongod` chỉ bind loopback **bên trong container**, kết nối tới network address của container qua NAT có thể thất bại. Trong một lab, có thể yêu cầu MongoDB lắng nghe container interface nhưng chỉ publish port về localhost của host:

```bash
# Chỉ minh họa container networking.
# Không có auth, persistent volume hoặc TLS production.
docker run --rm --name mongo-lab -p 127.0.0.1:27017:27017 mongo:7 --bind_ip_all
```

Ý tưởng: `--bind_ip_all` cho container listener; `-p 127.0.0.1:27017:27017` yêu cầu host published port giới hạn ở IPv4 loopback trong môi trường Docker hỗ trợ. **Cần kiểm tra host firewall, IPv6, Docker version, network driver và các đường truy cập khác**: không suy rằng một cú pháp port mapping đủ bảo vệ mọi topology.

Nếu app và MongoDB chạy cùng một Docker Compose network, có thể dùng service hostname nội bộ và **không publish MongoDB port ra host**.

## 13. Kubernetes: Service và NetworkPolicy

Trong Kubernetes có nhiều lớp:

```text
Application Pod
      |
      v
   Service DNS
      |
      v
  MongoDB Pod / Endpoint
```

**Kubernetes Service** định tuyến tới pod; **NetworkPolicy** giới hạn traffic giữa endpoints khi CNI hỗ trợ/thực thi; **`bindIp`** là socket listener trong container; và **TLS/AuthN/AuthZ** vẫn quyết định bảo vệ MongoDB.

Đừng coi `Service type: ClusterIP` tự động nghĩa là “chỉ một app pod được truy cập”. Nhiều cluster cho phép pod-to-pod network nếu không có NetworkPolicy hoặc lớp bảo vệ khác.

Tránh mở `NodePort` hay `LoadBalancer` public cho database chỉ vì một app ngoài cluster không resolve được service DNS. Hãy xem private connectivity, VPN, bastion hoặc gateway có kiểm soát.

## 14. MongoDB Atlas: khác tự quản lý ở đâu?

Với **MongoDB Atlas**, người dùng thông thường **không tự thay `mongod.conf` hoặc `net.bindIp` của node do Atlas quản lý**. Atlas cung cấp project/network controls và các lựa chọn public/private connectivity.

Sơ đồ cho đường public:

```text
Backend app
    |
    v
DNS SRV / Atlas endpoint
    |
    v
Client egress / NAT
    |
    v
Atlas public network endpoint
    |
    v
Atlas Project IP Access List
    |
    v
TLS + MongoDB database user/roles
    |
    v
Cluster data
```

Các lớp này độc lập về mục đích: **IP Access List** quyết định nguồn có thể kết nối qua đường public tương ứng, **Database Access** quyết định user đăng nhập và quyền dữ liệu, và **project/organization roles** quyết định người quản lý có thể thay đổi gì trong Atlas console/API.

## 15. Atlas Project IP Access List

Với những cluster/đường truy cập public chịu kiểm soát bằng Project IP Access List, Atlas cho phép thêm **địa chỉ public IPv4 hoặc CIDR nguồn** của client/ứng dụng.

| Giá trị minh họa | Mục đích | Đánh giá |
| --- | --- | --- |
| `198.51.100.24/32` | Một NAT IP cố định | Hẹp, phù hợp khi đúng nguồn |
| `203.0.113.40/32` | Egress IP của app | Hẹp, cần kiểm tra thực |
| `198.51.100.0/28` | Một dải public giới hạn | Chỉ dùng khi cần cả dải |
| `0.0.0.0/0` | Mọi public IPv4 source | **Không nên duy trì thường xuyên** |

Các public ranges `198.51.100.0/24` và `203.0.113.0/24` là **dải dùng trong tài liệu**, không phải IP cần thêm thật.

### Lấy IP nào để allowlist?

Giả sử:

```text
Laptop ở Wi-Fi:    192.168.1.25
      |
      v
Office NAT:        198.51.100.24
      |
      v
Atlas public endpoint
```

Atlas nhìn thấy **địa chỉ public egress sau NAT**, không phải private IP của laptop. Vì vậy, việc thêm `192.168.1.25/32` vào public access list thường không giúp laptop kết nối qua Internet.

Với app trong Kubernetes:

```text
App pod:           10.2.1.15
Cloud NAT gateway: 198.51.100.24
Atlas source seen: 198.51.100.24
```

Nên xác định IP egress từ **môi trường thực chạy app**, bằng phương pháp được tổ chức cho phép. Không đoán từ địa chỉ pod, node hoặc subnet.

### Vì sao IP list có thể hoạt động gián đoạn?

- Laptop đổi Wi-Fi hoặc bật VPN.
- App chạy qua nhiều NAT gateways ở các availability zones.
- CI runner dùng địa chỉ public động theo mỗi job.
- Serverless app thay đổi egress IP khi scale.
- NAT được thay thế nhưng rule Atlas chưa cập nhật.

Nếu workload có hai NAT IP hợp lệ, cần kiểm soát cả hai nguồn hoặc chuẩn hóa về static egress. **Không dùng `0.0.0.0/0` như một cách sửa nhanh cho egress không ổn định**.

### IP Access List không cấp quyền đọc dữ liệu

Nguồn IP được phép chỉ có thể **bắt đầu kết nối** đến endpoint, không tự có MongoDB credentials. Nhiều services có thể chung NAT IP; mỗi service vẫn cần database user/role riêng.

### Quy trình quản lý Atlas access list

1. Xác định **đúng project và cluster**.
2. Xác định app dùng **public endpoint** hay private connection.
3. Thu thập public egress IP/CIDR thực.
4. Trong khu vực **Network Access/IP Access List** của project, thêm rule hẹp với mô tả và owner.
5. Với quyền tạm thời, dùng expiry/temporary entry khi có.
6. Kiểm tra egress firewall phía app.
7. Kiểm tra TLS, DB user/password và roles.
8. Thu hồi IP không còn nhu cầu.

Tên menu và khả năng từng deployment có thể thay đổi; cần xem tài liệu/giao diện Atlas đang dùng.

## 16. Atlas Database Access và project roles

Những quyền khác nhau:

| Loại | Quản lý | Ví dụ |
| --- | --- | --- |
| Atlas Network Access | IP/CIDR hoặc cơ chế private connectivity được phép | NAT `198.51.100.24/32` |
| Atlas Database Access | Database users và authentication | `orders-service` |
| Database RBAC | Những lệnh user được thực hiện | `readWrite` trên `ordersdb` |
| Atlas Project/Org roles | Ai được quản lý tài nguyên qua UI/API Atlas | Project owner/operator |

**Có quyền đăng nhập Atlas console không có nghĩa tự động là một MongoDB database user.** Tài khoản quản trị Atlas và user để ứng dụng truy cập collections không nên bị đánh đồng.

Một policy ví dụ:

```text
Application: orders-service
Network: static egress NAT /32 hoặc private endpoint
Database user: orders-service
Role: readWrite trên ordersdb
Không cấp: root/atlasAdmin nếu không cần
Secrets: lấy từ secret manager
Transport: TLS, certificate validation bật
```

Không đặt tài khoản quản trị trong URI của service production để tránh việc một lỗ hổng ứng dụng có thể trở thành quyền quản lý toàn bộ cluster.

## 17. Private Endpoint và VPC/VNet peering trên Atlas

Nhiều tổ chức muốn hạn chế traffic tới MongoDB trên đường public. Tùy cloud provider, region, tier và khả năng của deployment, Atlas hỗ trợ các hình thức **private connectivity**, chẳng hạn:

- **Private Endpoint** dựa trên AWS PrivateLink, Azure Private Link hoặc cơ chế tương đương.
- **VPC/VNet peering** giữa mạng ứng dụng và mạng do Atlas quản lý khi được hỗ trợ.

### Private Endpoint

```text
Application VPC/VNet
        |
        v
Private DNS / Private Endpoint IP
        |
        v
Provider private connectivity
        |
        v
Atlas cluster endpoint
        |
        v
TLS + database user + roles
```

Cần kiểm tra endpoint đã được liên kết/duyệt, security groups, DNS, routing và **private connection string** chính thức. Tạo endpoint **không đồng nghĩa** app đang dùng nó: nếu ứng dụng vẫn resolve URI sang public hosts, kết nối có thể vẫn đi qua public path.

### Peering

Peering thường cần mạng không chồng CIDR, route và DNS phù hợp, security group/network ACL ở cả hai phía. Nó chỉ cung cấp **đường mạng**, không cấp database permissions.

### Private access và public IP list

Không nên khẳng định mọi private endpoint đều chịu cùng rules với public IP Access List, hoặc private connectivity tự động xóa mọi public connection path. Cơ chế cụ thể phụ thuộc loại endpoint/deployment. Hãy kiểm tra **đường kết nối thực**, những endpoints đang enabled và những access controls tương ứng.

**Mục tiêu:** không chỉ “thêm một đường private”, mà còn tránh để một đường public không cần thiết tiếp tục mở.

## 18. `mongodb+srv://`, DNS và firewall

Atlas thường cung cấp URI dạng:

```text
mongodb+srv://<cluster-hostname>/<database>
```

Ví dụ placeholder:

```text
mongodb+srv://cluster.example.mongodb.net/ordersdb
```

Khi dùng `mongodb+srv://`, driver truy vấn DNS SRV/TXT theo cơ chế hỗ trợ để tìm hosts và một số connection options. Vì thế:

- DNS của client phải phân giải được records cần thiết.
- Firewall phải cho phép outbound đến **những hosts/ports thực sự được công bố**, không chỉ một IP sao chép tạm.
- Client phải tin cậy TLS certificate hợp lệ cho hostname.
- Network proxy/firewall DNS không được chặn các truy vấn cần thiết.

Nếu DNS SRV lookup thất bại, mở rộng Atlas access list **không sửa được DNS**. Nếu SRV hoạt động nhưng TCP tới các member hosts bị chặn, driver vẫn có thể báo server selection timeout.

Không thay URI Atlas bằng một IP tĩnh tình cờ trả về từ DNS, vì topology, certificate name và endpoint có thể thay đổi.

## 19. Kiểm tra listener trên MongoDB tự quản lý

Trên Linux:

```bash
# Kiểm tra socket lắng nghe; không sửa hệ thống.
ss -lntp | grep 27017
```

Kết quả minh họa:

```text
LISTEN ... 127.0.0.1:27017 ...
```

Nghĩa là listener chỉ ở loopback IPv4.

Một output khác:

```text
LISTEN ... 10.10.20.12:27017 ...
```

nghĩa là có listener ở private IP. **Chưa chứng minh firewall allow nguồn client**, TLS đúng hoặc user có quyền.

Trên Windows:

```powershell
Get-NetTCPConnection -State Listen -LocalPort 27017
```

Nếu không có listener, cần kiểm tra `mongod` có chạy không, log startup, file cấu hình đang dùng, cổng có bị tiến trình khác chiếm không và IP trong `bindIp` có thực sự thuộc host không.

## 20. Kiểm tra TCP từ ứng dụng được phép

Từ **chính máy ứng dụng** hoặc môi trường runtime được quyền truy cập:

Linux/macOS:

```bash
nc -vz db.internal.example 27017
```

Windows:

```powershell
Test-NetConnection db.internal.example -Port 27017
```

Hai lệnh chỉ kiểm tra **DNS/routing/TCP**, không xác nhận TLS, authentication hoặc quyền đọc collection. Chỉ dùng với endpoint của bạn hoặc đã được cho phép; không dùng để scan các dải IP bên ngoài.

Nếu TCP fail:

1. Đúng hostname/port chưa?
2. DNS đang phân giải private hay public IP?
3. Client egress/route có đúng không?
4. Server listener bind ở IP đích chưa?
5. Host firewall/security groups/network ACL có cho source phù hợp không?
6. Nếu Atlas, nguồn public egress có trong project IP list hoặc private endpoint có được cấu hình đúng không?

Chỉ sau khi TCP thông mới tập trung xử lý MongoDB protocol, TLS và database authentication.

## 21. Test bằng `mongosh` mà không lộ mật khẩu

Ví dụ self-managed đã bật TLS, authSource trong ví dụ là `admin`:

```bash
mongosh "mongodb://db.internal.example:27017/appdb?tls=true" --username appReader --authenticationDatabase admin --password
```

Ví dụ Atlas với placeholder:

```bash
mongosh "mongodb+srv://cluster.example.mongodb.net/appdb" --username appReader --password
```

Đường dẫn và user phải lấy theo môi trường thật. Với một số cơ chế xác thực/certificate, lệnh cần thêm options phù hợp. Tránh đặt mật khẩu trực tiếp trong dòng lệnh hoặc mã nguồn vì nó có thể xuất hiện trong shell history/process metadata/logs.

Sau khi kết nối:

```javascript
db.adminCommand({ ping: 1 })
```

Lệnh `ping` thành công xác nhận MongoDB có thể đáp ứng command, **không đồng nghĩa user có quyền đọc/ghi mọi collection**. Kiểm tra một operation thực tế được phép để xác nhận RBAC của service.

## 22. Phân loại lỗi kết nối theo lớp

| Triệu chứng | Ưu tiên kiểm tra | Diễn giải |
| --- | --- | --- |
| `ENOTFOUND`, SRV lookup error | DNS | Resolver/hostname/SRV/TXT hoặc private DNS |
| `ECONNREFUSED` | Listener/port | Không có socket nhận hoặc host reset |
| `ETIMEDOUT` | Route/firewall | Packet bị chặn, NAT/route sai, đích không trả lời |
| Server selection timeout | Topology/network | Một hoặc nhiều members/routers không reachable |
| TLS handshake/certificate error | TLS | CA, SAN/hostname, cert hết hạn hoặc policy khác |
| `Authentication failed` | AuthN | Username, password, authSource hoặc mechanism |
| `not authorized` | AuthZ | User đăng nhập nhưng thiếu role |
| Chỉ lỗi trong Docker | Container network | Loopback namespace, service DNS, port mapping |
| Chỉ lỗi ở CI | Egress IP/network | Runner khác source IP với laptop |
| Lỗi khi replica set failover | Member reachability | Chỉ seed node được firewall allow |
| Chỉ lỗi trên một availability zone | NAT/routing | Một egress IP chưa có trong Atlas list |

Những thông báo là **gợi ý chẩn đoán**, không phải mapping tuyệt đối. Driver có thể báo một lỗi bề mặt chung như server selection timeout kèm nested causes; nên xem thông tin endpoint và lỗi gốc.

### Lưu đồ điều tra

```text
Ứng dụng không kết nối được
       |
       v
DNS/SRV phân giải được?
    |            |
  Không          Có
    |            |
    v            v
  Sửa DNS     Route/TCP thông?
                 |          |
               Không        Có
                 |          |
                 v          v
          bindIp/firewall  TLS hợp lệ?
                            |      |
                          Không    Có
                            |      |
                            v      v
                       CA/cert   AuthN OK?
                                  |     |
                                Không   Có
                                  |     |
                                  v     v
                              Credentials  AuthZ OK?
                                             |    |
                                           Không  Có
                                             |    |
                                             v    v
                                           Roles Thành công
```

Không mở thêm IP ranges hoặc tắt TLS validation chỉ vì chưa xác định được lỗi thuộc lớp nào.

## 23. Trường hợp A: Java app cùng máy với MongoDB

```text
Developer laptop:
  Java app
  mongod: 127.0.0.1:27017
```

Nếu app cùng network namespace với MongoDB, URI localhost là hợp lý. **Không cần `bindIpAll` hoặc mở port ra LAN**. Nhưng nếu Java app chạy trong một container còn MongoDB chạy trên host hoặc container khác, `127.0.0.1` của Java container không còn là loopback của MongoDB.

Giải pháp cần đúng network topology, không phải đổi password MongoDB.

## 24. Trường hợp B: App VM và MongoDB VM ở subnet khác

```text
App VM: 10.20.30.10
       |
       | TCP 27017, TLS
       v
DB VM: 10.10.20.12
```

Thiết kế:

- `mongod` bind `10.10.20.12` và có thể `127.0.0.1` cho nhu cầu local.
- Firewall cho source `10.20.30.10/32` tới đích TCP 27017.
- Cloud routing/security groups cho private path.
- MongoDB bật TLS và authentication.
- Service user chỉ có DB role cần thiết.

Nếu kết nối fail, đọc listener và rule thật. **Không đổi `bindIp` thành `0.0.0.0` theo phản xạ.**

## 25. Trường hợp C: Atlas có NAT egress tĩnh

```text
App private IP: 10.2.1.15
NAT public IP: 198.51.100.24
Atlas public endpoint
```

Các bước:

1. Cho phép nguồn public `198.51.100.24/32` trong đúng Atlas project theo đường truy cập public.
2. Kiểm tra app outbound tới Atlas hosts/ports.
3. Dùng SRV URI chính thức và TLS.
4. Cấp database user riêng và role giới hạn.
5. Nếu có nhiều zones/NATs, kiểm tra mọi egress IP hợp lệ.
6. Giám sát nếu egress IP thay đổi.

Thêm private IP `10.2.1.15` vào public allowlist không thay thế NAT IP.

## 26. Trường hợp D: Atlas Private Endpoint

```text
App VPC/VNet
      |
Private DNS + Private Endpoint
      |
Atlas
```

Checklist:

- Endpoint đã được tạo, approved/associated đúng deployment.
- DNS resolve đúng hostname và địa chỉ cho private connection.
- Network route và security group cho phép traffic.
- Ứng dụng sử dụng **private endpoint URI**, không tình cờ dùng public URI.
- Database user/TLS/roles vẫn đúng.
- Không để public path rộng ngoài ý muốn.

Private connectivity **không tự cho phép một app bị xâm nhập đọc mọi database**; credentials và RBAC vẫn là ranh giới bắt buộc.

## 27. Trường hợp E: Mobile app kết nối Atlas trực tiếp

Một mobile app của hàng nghìn người dùng có IP thay đổi theo Wi-Fi/nhà mạng/VPN. Nếu nhúng MongoDB password trong package và bắt mobile kết nối Atlas:

- Không duy trì được public allowlist hẹp cho mọi thiết bị.
- Database credentials có nguy cơ bị trích xuất.
- Khó giới hạn nghiệp vụ và rate limit ở tầng backend.
- Client có thể tiếp cận DB API vượt quá ý định UI nếu role rộng.

Kiến trúc thường phù hợp:

```text
Mobile app
     |
HTTPS API (user authentication/authorization)
     |
Backend server với static egress/private endpoint
     |
MongoDB Atlas với service user và DB RBAC
```

Người dùng cuối không cần biết URI/database credential. API backend chịu trách nhiệm kiểm tra tenant/role, áp dụng business validation và quản lý connection pool.

## 28. Least privilege xuyên suốt

| Tầng | Chính sách tối thiểu |
| --- | --- |
| Listener | Chỉ interface thực sự cần |
| Routes | Chỉ đường mạng đã được phép |
| Firewall | Source/destination/port hẹp |
| Atlas public IP list | Egress IP/CIDR nhỏ nhất hợp lệ |
| Private connectivity | Chỉ VPC/VNet/service cần truy cập |
| TLS | Certificate hợp lệ, không bypass verification |
| Database credentials | Một identity riêng theo ứng dụng |
| RBAC | Role đúng DB/actions, không dùng root |
| Secret management | Chỉ runtime được phép đọc secret |
| Logging/Audit | Theo dõi thay đổi chính sách và thất bại truy cập |

Ví dụ một reporting job chỉ cần đọc:

```text
reporting-job
Network: analytics subnet
DB user: reporting-reader
DB role: read trên ordersdb
Không cấp: readWrite/root
```

Ngay cả khi reporting server bị chiếm quyền điều khiển, giới hạn mạng và RBAC có thể giảm phạm vi tác động.

## 29. HA và network access

Chính sách bảo mật không được làm replica set mất khả năng hoạt động:

```text
App subnet
  |
  +--> rs-a:27017  [allow]
  +--> rs-b:27017  [blocked]
  +--> rs-c:27017  [blocked]
```

Khi rs-b trở thành primary, app không truy cập được dù URI trước đó đôi lúc hoạt động qua rs-a. Vì thế phải:

1. Kiểm tra đường client tới **những member endpoints được topology công bố**.
2. Cho replica-set members giao tiếp nội bộ theo rules và internal authentication.
3. Xác nhận DNS hostnames có thể phân giải từ app.
4. Test read/write behavior sau failover trong môi trường thích hợp.
5. Giới hạn theo đúng member/zone, không biến internal cluster ports thành public services.

Với sharded cluster, app sử dụng router/managed endpoints; network của shard/config members cần được thiết kế riêng theo chức năng.

## 30. Quản lý thay đổi và drift

Một network access entry nên có thông tin:

```text
Rule ID:
Owner:
Environment/project:
Business reason:
Source IP/CIDR:
Destination/port:
Created:
Review/expiry:
Approved by:
Rollback method:
```

Thực hành:

- Không để `0.0.0.0/0` thường trực chỉ vì IP developer thay đổi.
- Có thời hạn cho quyền bảo trì tạm.
- Thu hồi IP/NAT cũ, vendor hoặc CI runner đã ngừng.
- Kiểm tra thay đổi của security groups, host firewall, Atlas IP list và database roles.
- Tách production/staging/development network policy.
- Test cấu hình từ **đúng application runtime**, không chỉ laptop operator.
- Giữ backup và phương án quản trị nếu firewall rollout nhầm.

### Metrics và alert

| Tín hiệu | Ý nghĩa |
| --- | --- |
| Listener chuyển sang wildcard | Nguy cơ public exposure |
| Rule mới cho TCP 27017 từ Internet | Nguy cơ truy cập không mong muốn |
| Atlas IP list xuất hiện `0.0.0.0/0` | Cần review ngay |
| Auth failures tăng mạnh | Password sai, credential attack hoặc rotation issue |
| TLS handshake errors tăng | CA/certificate/hostname mismatch |
| Connection attempts từ subnet lạ | Workload/network bất thường |
| Replica-set selection timeout tăng | Topology/firewall/route vấn đề |
| Service role tăng thành admin | Privilege escalation |
| Private Endpoint DNS đổi | Nguy cơ đi sai public/private path |

Không chỉ review sau khi có sự cố; triển khai một lịch review cấu hình để phát hiện drift.

## 31. Những nhầm lẫn thường gặp

| Nhầm lẫn | Vì sao sai? | Cách hiểu đúng |
| --- | --- | --- |
| “`bindIp` là IP client” | Là local listener address của MongoDB | Dùng firewall để hạn chế client source |
| “Đặt `0.0.0.0` là cách sửa lỗi chuẩn” | Có thể mở public interface | Chỉ bind interface cần thiết |
| “Password mạnh nên mở public port không sao” | Tăng bề mặt brute-force và tấn công | Private network + TLS + auth |
| “Firewall allow = có quyền đọc DB” | Firewall chỉ cho packet đi qua | RBAC độc lập |
| “`127.0.0.1` trong Docker là loopback host” | Khác network namespace | Dùng service DNS/network phù hợp |
| “ClusterIP Service ngăn mọi pod truy cập” | Chưa chắc có NetworkPolicy | Cần chính sách CNI/network rõ |
| “Atlas IP list cần IP riêng của pod” | Public path thấy NAT egress | Allowlist public source thực |
| “`0.0.0.0/0` không nguy hiểm vì có auth” | Mọi nguồn có thể thử TCP/handshake | Dùng CIDR hẹp |
| “Atlas project role là MongoDB user” | UI management và DB identity khác nhau | Tách quyền quản lý và quyền dữ liệu |
| “Private Endpoint nghĩa là không cần TLS” | Private path không thay identity verification | Vẫn TLS/AuthN/AuthZ |
| “Có endpoint là app tự đi private” | DNS/URI/route có thể vẫn public | Kiểm tra đường thật |
| “SRV URI chỉ cần mở một IP” | Driver khám phá nhiều hosts | Cho phép topology endpoints cần thiết |
| “Chỉ mở seed node là đủ cho replica set” | Failover cần reach members khác | Test HA paths |
| “TCP thành công là truy vấn chắc thành công” | Còn TLS/AuthN/AuthZ | Kiểm tra từng lớp |
| “Bỏ kiểm tra TLS certificate là sửa lỗi” | Mất bảo đảm server identity | Sửa CA/hostname/certificate |
| “`not authorized` là lỗi firewall” | Đây là RBAC sau khi kết nối | Cấp quyền đúng, không mở network |
| “IPv4 đã chặn nên không có public exposure” | IPv6 có thể còn đường vào | Kiểm tra hai stack |
| “Allow rule mới xóa rule cũ” | Rules có thể cùng hiệu lực | Review tổng thể |

## 32. Bài tập thực hành và đáp án

### Bài 1. Điền IP vào `bindIp`

DB VM có `10.10.20.12`; App VM có `10.20.30.10`. Nên đặt giá trị nào trong `net.bindIp` trên DB?

**Đáp án:** Bind `10.10.20.12` (có thể thêm `127.0.0.1`). Hạn chế source App VM bằng firewall allow `10.20.30.10/32` tới TCP 27017.

### Bài 2. Public exposure

VM có public NIC, MongoDB bind `0.0.0.0`, security group allow TCP 27017 từ `0.0.0.0/0`. Điều gì cần sửa?

**Đáp án:** Hạn chế listener về private/loopback interfaces cần thiết và firewall nguồn hẹp; không giữ network exposure Internet rộng. TLS/AuthN/RBAC vẫn cần.

### Bài 3. TCP thành công, auth thất bại

`Test-NetConnection` thành công nhưng `mongosh` báo `Authentication failed`. Có nên mở thêm firewall?

**Đáp án:** Không. TCP đã thông; kiểm tra user/password, `authSource`, authentication mechanism và secret rotation.

### Bài 4. NAT ở Atlas

App pod IP `10.2.1.15` ra Internet qua NAT `198.51.100.24`. Atlas public endpoint nhìn thấy nguồn nào?

**Đáp án:** Thông thường public egress `198.51.100.24`. Access list cần cấu hình đúng source đó, không phải private pod IP.

### Bài 5. Nhiều NATs

Hai zones đi qua NAT A và NAT B. Access list chỉ có NAT A. Vì sao app fail ngẫu nhiên?

**Đáp án:** Workload dùng zone B sẽ đi ra bằng IP khác chưa được phép. Cần thống kê tất cả egress IP hợp lệ hoặc thiết kế static egress.

### Bài 6. Atlas console role

Một user đăng nhập được Atlas UI và có quyền xem cluster. Có chắc họ có MongoDB database account đọc được `orders` không?

**Đáp án:** Không. Project/organization management roles khác MongoDB Database Access/roles.

### Bài 7. Private Endpoint DNS

Đã tạo Private Endpoint nhưng app vẫn resolve MongoDB URI sang public hosts. Có thể khẳng định traffic private chưa?

**Đáp án:** Chưa. Kiểm tra private URI, DNS routing, endpoint state và path thực tế.

### Bài 8. SRV lookup

`mongodb+srv://...` bị DNS lookup error dù firewall TCP 27017 có allow. Cần điều tra gì trước?

**Đáp án:** DNS SRV/TXT resolver, hostname và private DNS nếu có. Không mở Atlas IP list rộng để chữa DNS.

### Bài 9. Replica set failover

App chỉ reach rs-a, không tới rs-b/rs-c. Sau failover không tìm được primary. Vì sao?

**Đáp án:** Network policy/route/DNS tới các replica-set endpoints chưa đáp ứng topology; cần allow paths cần thiết mà không public các nodes.

### Bài 10. Docker localhost

App container gọi `mongodb://127.0.0.1:27017` nhưng DB ở container khác. Lỗi ở đâu?

**Đáp án:** `127.0.0.1` trong app container trỏ về app container. Dùng service hostname/network được kiểm soát.

### Bài 11. IPv6

Host có listener `:::27017` và IPv4 firewall chặn toàn Internet. Đã an toàn chưa?

**Đáp án:** Chưa. Cần kiểm tra IPv6 route, DNS AAAA và IPv6 firewall.

### Bài 12. TLS mismatch

Client báo certificate hostname mismatch. Đội muốn bật `tlsInsecure` lâu dài.

**Đáp án:** Không nên. Sửa hostname URI, SAN certificate, CA trust/rotation thay vì bỏ xác minh.

### Bài 13. Least privilege

Reporting job chỉ cần `find()` trong `ordersdb` nhưng được cấp role `root`.

**Đáp án:** Dùng database user riêng với quyền đọc phù hợp, chỉ cho network nguồn hợp lệ và dùng TLS.

### Bài 14. CI runner IP động

CI runner thay IP theo mỗi job, developer đề xuất `0.0.0.0/0` vĩnh viễn trong Atlas.

**Đáp án:** Ưu tiên static NAT egress, self-hosted runner/private networking hoặc temporary access list entry có expiry; không mở toàn bộ IPv4 thường trực.

### Bài 15. `bindIp` không thuộc host

Server không có `10.10.20.99` nhưng config bind địa chỉ đó, tiến trình không khởi động.

**Đáp án:** Kiểm tra địa chỉ interface của DB host và sửa listener sang IP hợp lệ; firewall không sửa lỗi socket bind.

### Bài 16. Các project Atlas

Team thêm đúng NAT IP vào staging project, nhưng app URI trỏ tới production cluster.

**Đáp án:** Access list của staging không áp dụng cho production project. Cần xác minh đúng target project/cluster và tuân thủ policy production.

### Bài 17. NAT chung

Hai services dùng cùng public NAT đã allowlist. Có nghĩa service B được đọc data của service A không?

**Đáp án:** Không. Mỗi service vẫn cần MongoDB database credentials và roles hợp lệ. IP allowlist không thay database authorization.

### Bài 18. Mobile app

Mobile app nhúng MongoDB credentials và kết nối Atlas trực tiếp từ mạng của người dùng.

**Đáp án:** Rủi ro lộ secrets, egress IP động và thiếu kiểm soát nghiệp vụ. Thường nên đi qua HTTPS backend sử dụng service identity và network path được kiểm soát.

### Bài 19. Lỗi `not authorized`

App login thành công nhưng `insertOne()` bị từ chối. Có cần đổi `bindIp`?

**Đáp án:** Không. AuthN đã thành công và lệnh thất bại ở **AuthZ**. Kiểm tra role đúng DB/action theo least privilege.

### Bài 20. Điều tra cấu hình

Một rule mới cho phép `0.0.0.0/0` tới 27017 nhưng MongoDB vẫn có authentication. Có cần cảnh báo?

**Đáp án:** Có. Network exposure tăng, phải review và đóng rule không cần. Authentication không loại bỏ rủi ro từ việc mở listener tới nhiều nguồn.

## 33. Checklist production

1. Xác định đúng MongoDB endpoints, IP, port và topology.
2. Chỉ bind vào loopback/private interfaces cần thiết, không mở wildcard theo phản xạ.
3. Kiểm tra IPv4/IPv6, Docker/Kubernetes port exposure và listener thực tế.
4. Giới hạn inbound/outbound theo source/destination/port tại mọi lớp firewall.
5. Với replica set/sharded cluster, mở đủ luồng HA nội bộ và client paths; không public internal endpoints.
6. Bật TLS/certificate validation và authentication phù hợp.
7. Cấp role tối thiểu, tách credentials theo service; không dùng root cho app.
8. Quản lý secrets qua công cụ phù hợp; không đưa password vào code/log.
9. Với Atlas public path, dùng project IP Access List với public egress IP thật và CIDR hẹp.
10. Với Atlas private path, kiểm tra private endpoint/peering, DNS, routing và public exposure.
11. Dùng connection string do deployment cung cấp, không hard-code IP discovery tạm.
12. Test từ ứng dụng/runner thực, không chỉ laptop developer.
13. Phân loại lỗi DNS → route/TCP → TLS → AuthN → AuthZ.
14. Kiểm thử failover/topology paths và IPv6 nếu có.
15. Có owner, mục đích, thời hạn, review và rollback cho mỗi sensitive network rule.
16. Giám sát listener changes, Atlas IP list drift, auth failures và permission changes.

## 34. Tổng kết

Trong MongoDB tự quản lý, **`net.bindIp` quyết định server lắng nghe trên interface nào**, còn **firewall/security groups/network ACL** quyết định những nguồn nào có thể kết nối tới interface đó. Với development cùng máy, `127.0.0.1` thường đủ. Với hệ thống nhiều máy, nên chọn **private interface và firewall hẹp theo application subnet** thay vì mở `0.0.0.0` ra mọi interface.

Với **MongoDB Atlas**, **Project IP Access List** quản lý nguồn cho những đường public connection tương ứng, **Database Access** quản lý database users và roles, còn **Private Endpoint/peering** cung cấp lựa chọn đường mạng riêng khi được hỗ trợ. NAT egress, DNS SRV, private DNS, topology và TLS đều ảnh hưởng khả năng kết nối.

Một triển khai an toàn không chỉ kết nối được, mà phải bảo đảm **đúng nguồn – đúng đường mạng – đúng danh tính – đúng quyền dữ liệu**. Khi xảy ra lỗi, hãy chẩn đoán theo lớp thay vì mở rộng IP Access List, tắt certificate validation hoặc cấp quyền quản trị không cần thiết.

### Tài liệu tham khảo chính thức

- [MongoDB Manual — Security Checklist](https://www.mongodb.com/docs/manual/administration/security-checklist/)
- [MongoDB Manual — Configuration File Options](https://www.mongodb.com/docs/manual/reference/configuration-options/)
- [MongoDB Manual — Authentication](https://www.mongodb.com/docs/manual/core/authentication/)
- [MongoDB Manual — Role-Based Access Control](https://www.mongodb.com/docs/manual/core/authorization/)
- [MongoDB Atlas — Configure IP Access List Entries](https://www.mongodb.com/docs/atlas/security/ip-access-list/)
- [MongoDB Atlas — Database Users](https://www.mongodb.com/docs/atlas/security-add-mongodb-users/)
- [MongoDB Atlas — Private Endpoints](https://www.mongodb.com/docs/atlas/security-private-endpoint/)
- [MongoDB Atlas — Network Peering](https://www.mongodb.com/docs/atlas/security-vpc-peering/)
