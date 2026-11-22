# Chẩn đoán lỗi kết nối, DNS, TLS và server selection timeout trong MongoDB

## 1. Hiểu sự cố kết nối theo từng lớp

Một ứng dụng Java/Spring Data MongoDB có thể báo:

```text
com.mongodb.MongoTimeoutException:
Timed out after 30000 ms while waiting for a server
that matches ReadPreferenceServerSelector{readPreference=primary}
```

Đây **không phải kết luận rằng MongoDB Server đang tắt**. Thông báo chỉ nói MongoDB Java Driver **không chọn được server đủ điều kiện trong khoảng server-selection timeout**. Nguyên nhân gốc có thể thuộc nhiều lớp:

- URI sai hostname, port, database, `replicaSet` hoặc tùy chọn.
- DNS không tìm thấy bản ghi SRV/TXT/A/AAAA, hoặc máy ứng dụng dùng resolver khác máy laptop.
- Firewall, route, VPN, security group hoặc MongoDB Atlas IP access list chặn TCP.
- TCP tới được nhưng TLS handshake thất bại vì CA, hostname, chứng chỉ hết hạn, SNI, phiên bản TLS hoặc mTLS.
- TCP/TLS hoạt động nhưng replica set không có **primary** phù hợp với thao tác, server đang election hoặc member hostnames được quảng bá không reachable.
- Đã tìm được server nhưng xác thực sai user/password/`authSource`.
- Connection pool cạn, checkout chờ quá lâu; đây là lớp lỗi khác server selection, dù cũng có thể xuất hiện dưới dạng timeout.
- Ứng dụng tạo quá nhiều MongoClient, retry storm hoặc bị chặn bởi proxy/sidecar.

### 1.1. Sơ đồ các chặng

```text
Ứng dụng Java / Spring Data
        |
        v
[1] Parse MongoDB URI
        |
        v
[2] DNS
    mongodb+srv: SRV -> target names -> A/AAAA; TXT options
    mongodb:     A/AAAA cho các hosts trong seed list
        |
        v
[3] TCP network / routing / firewall / Atlas allow-list
        |
        v
[4] TLS handshake
    TLS version, chain of trust, hostname/SAN, SNI, mTLS
        |
        v
[5] MongoDB hello / SDAM topology discovery
    standalone / replica set / mongos; roles, read preference
        |
        v
[6] Authentication + authorization
    SCRAM, X.509, authSource, roles
        |
        v
[7] Pool checkout và thực thi command
        |
        v
[8] Kết quả / lỗi của truy vấn
```

**Quy tắc:** kiểm tra **lớp sớm nhất bị hỏng** trước. Tăng `serverSelectionTimeoutMS` không sửa được DNS sai; thêm index không sửa được TLS; đổi password không làm TCP route thông được.

### 1.2. Kết quả học tập

Sau bài này bạn có thể:

1. Đọc error chain và phân biệt DNS, TCP, TLS, authentication, server discovery, pool timeout.
2. Kiểm tra đúng connection string `mongodb://` và `mongodb+srv://`.
3. Dùng `Resolve-DnsName`/`nslookup`, `dig`, `Test-NetConnection`, `nc`, `openssl` theo hệ điều hành.
4. Đọc TLS error, kiểm tra chứng chỉ SAN/CA/truststore, không tắt hostname verification để “chữa” lỗi.
5. Đọc `MongoTimeoutException` và **cluster description** của Java Driver.
6. Phân biệt `serverSelectionTimeoutMS`, `connectTimeoutMS`, `socketTimeoutMS`, pool wait và CSOT.
7. Điều tra Atlas IP access list, egress IP, Private Endpoint, split-horizon DNS.
8. Phân tích replica set primary/secondary, read preference, `directConnection` và advertised member hostnames.
9. Xác minh kết nối thực bằng lệnh `ping`, không dựa vào việc tạo `MongoClient` thành công.
10. Tạo runbook có bằng chứng, time stamps, phạm vi sự cố, owner và bước khôi phục.

---

## 2. Đọc thông báo lỗi: ngoại lệ ngoài cùng và nguyên nhân sâu nhất

Một Java stack trace có thể chứa **nhiều lớp wrapper**:

```text
org.springframework.dao.DataAccessResourceFailureException
  caused by: com.mongodb.MongoTimeoutException:
    Timed out after 30000 ms while waiting for a server
    ...
    caused by: com.mongodb.MongoSocketOpenException:
      Exception opening socket
      caused by: java.net.ConnectException:
        Connection refused
```

Cách đọc:

1. Ghi loại exception ngoài cùng để biết framework phản ứng ra sao.
2. Đọc **MongoDB exception**: `MongoTimeoutException`, `MongoSecurityException`, `MongoSocketException`...
3. Đọc **root cause**: `UnknownHostException`, `ConnectException`, `SocketTimeoutException`, `SSLHandshakeException`.
4. Đọc **cluster description** để biết driver thấy bao nhiêu nodes và vai trò nào.
5. Đối chiếu thời điểm với logs/metrics của MongoDB, DNS, network và deployment.
6. Không xóa các chi tiết `type=...`, `state=...`, `exception=...` khi gửi báo cáo kỹ thuật; nhưng phải **redact credentials và nội dung nhạy cảm**.

### 2.1. Bảng nhận diện nhanh

| Dấu hiệu trong lỗi/log | Lớp đáng kiểm tra đầu tiên | Không kết luận vội |
| --- | --- | --- |
| `UnknownHostException`, `ENOTFOUND`, `NXDOMAIN` | DNS/hostname | DB chắc đã tắt |
| `querySrv ECONNREFUSED` | DNS SRV resolver/port 53 | TCP MongoDB port 27017 chắc bị chặn |
| `No SRV records`, DNS `SERVFAIL` | Resolver, DNS forwarding, SRV service | Mật khẩu sai |
| `Connection refused` | TCP, process listener, firewall reject | TLS cert sai |
| `Connection timed out` | Route/firewall drop/port/network | Chắc chắn không có primary |
| `No route to host` | IP route/security network | Đổi MongoDB user sẽ có tác dụng |
| `SSLHandshakeException` | TLS protocol/cert chain/hostname | Cứ tăng timeout là sửa |
| `PKIX path building failed` | Java truststore/CA chain | Server không chạy |
| `No subject alternative names matching` | SAN/hostname của chứng chỉ | Chỉ cần đổi mật khẩu |
| `Authentication failed`, code 18 | User/password/authSource/mechanism | DNS luôn hỏng |
| `Timed out ... ReadPreferenceServerSelector` | SDAM và mọi lỗi nền | Kết luận server offline ngay |
| `state=CONNECTING`, `type=UNKNOWN` | Mở socket/hello/heartbeat | Server đã được chọn |
| `REPLICA_SET_SECONDARY` nhưng chờ `primary` | Role/primary/election/read preference | Secondary lỗi mạng |
| `Timed out waiting for a connection from the pool` | Pool checkout, concurrency, server load | SRV records sai |
| `Too many connections` | Limits/pool/client churn | Tăng `maxPoolSize` vô hạn |

Đây là **bảng giả thuyết**, không thay việc đọc exception gốc và điều kiện thực tế.

---

## 3. Runbook năm bước đầu của một sự cố

Khi nhận incident “ứng dụng không kết nối MongoDB”, hãy làm theo trình tự:

1. **Phạm vi:** một pod, mọi pods, một AZ/region, chỉ production hay chỉ laptop? Thời điểm bắt đầu UTC? Có rollout, network policy hoặc certificate rotation?
2. **URI và topology:** URI dạng nào; có đúng cluster, seed host, port, TLS, replicaSet, authSource không? **Redact** mọi username/password/token trước khi chia sẻ.
3. **DNS và TCP từ đúng runtime:** kiểm tra ở **chính máy/pod/container bị lỗi**, không chỉ trên laptop thành công.
4. **TLS và authentication:** nếu TCP thành công mà Java không vào được, đọc handshake/cert/truststore hoặc auth error.
5. **SDAM, server selection và pool:** đọc cluster description, member roles, timeouts, checkout waits; chạy `ping` bằng driver cùng môi trường.

### 3.1. Mẫu ghi nhận sự cố

```text
Incident ID:                 ...
First seen (UTC):            ...
Last known good (UTC):       ...
App version + JDK:           ...
MongoDB driver version:      ...
MongoDB deployment/tier:     ...
Pod/container/host:          ...
Egress IP / network path:    ...
URI scheme:                  mongodb:// hoặc mongodb+srv://
URI host (redacted):         ...
Read preference:             primary / secondary / ...
Exception type and cause:    ...
Driver cluster description:  ...
DNS SRV/TXT/A/AAAA result:   ...
TCP port test:               ...
TLS verification result:     ...
Replica set roles:           ...
Pool checkout metrics:       ...
Change before incident:      ...
Recovery/action owner:       ...
```

**Bảo mật:** không đưa nguyên connection string chứa password lên ticket. Có thể giữ host/port, scheme, safe options và URI options sau khi xóa secrets.

---

## 4. Hai định dạng connection string và khác biệt cơ bản

### 4.1. Standard `mongodb://`

Ví dụ self-managed replica set:

```text
mongodb://db1.example.net:27017,db2.example.net:27017,db3.example.net:27017/app?replicaSet=rs0&tls=true
```

- Seed list chứa host:port.
- Với replica set, driver dùng seed list để khám phá toàn topology.
- `tls=true` cần chỉ định khi self-managed deployment yêu cầu TLS; **standard URI mặc định không tự bật TLS** nếu không có cấu hình khác.
- `replicaSet=rs0` giúp xác định đúng replica set.
- `db1`, `db2`, `db3` phải truy cập được từ application environment, không chỉ từ server MongoDB khác.

### 4.2. DNS seedlist `mongodb+srv://`

Ví dụ Atlas giả định:

```text
mongodb+srv://cluster0.example.mongodb.net/app?retryWrites=true&w=majority
```

- Chỉ **một hostname** sau scheme.
- Không được gắn `:27017` trực tiếp vào SRV URI.
- Driver tra cứu DNS SRV `_mongodb._tcp.<hostname>` để tìm node targets/ports.
- Driver có thể đọc TXT record cho những connection options được phép.
- `mongodb+srv://` **mặc định bật TLS** trừ khi có override phù hợp; không nên override TLS thành false để xử lý lỗi.
- DNS SRV thay đổi theo topology, do đó không nên tự hardcode các node IPs.

`cluster0.example.mongodb.net` chỉ là **hostname ví dụ**, không phải cluster đang tồn tại.

### 4.3. URI validation

| Thành phần | Kiểm tra |
| --- | --- |
| Scheme | `mongodb` hay `mongodb+srv` |
| Host | Viết đúng tên, đúng domain, có DNS |
| Port | Dùng trên standard URI; SRV không tự thêm |
| Replica set | Option name khớp server config nếu khai báo |
| `authSource` | Database chứa user dùng để xác thực |
| Database path | Phân biệt database mặc định với auth database |
| TLS | Khớp server/Atlas, certificate verification enabled |
| Read preference | Có member đáp ứng read/write semantics không |
| Credentials | Percent-encode đúng khi đặt trong URI |
| Timeout options | Không dùng một timeout để giải thích tất cả |
| Hidden secrets | URI không bị log nguyên văn |

### 4.4. Ký tự đặc biệt trong password

Nếu password có các ký tự `@`, `:`, `/`, `?`, `#`, `%`, cần **percent-encode đúng** theo URI syntax. Ví dụ chuỗi minh họa `p@ss:w` cần representation thích hợp trong URI như `p%40ss%3Aw`.

Không encode password theo cách này khi **nhập trực tiếp vào password prompt** của công cụ. Tránh double encoding: `%40` đã mã hóa ký tự `@`, không phải luôn cần đổi `%` thành `%25` lần nữa.

**Khuyến nghị:** dùng secrets manager hoặc environment variables để cung cấp URI; tuyệt đối không commit real URI có credentials.

---

## 5. DNS SRV, TXT, A/AAAA: kiểm tra theo đúng thứ tự

Với `mongodb+srv://cluster0.example.mongodb.net/`, driver thường cần:

```text
Step A: SRV _mongodb._tcp.cluster0.example.mongodb.net
        |
        v
      target0.mongodb.net:27017
      target1.mongodb.net:27017
      target2.mongodb.net:27017
        |
        v
Step B: A/AAAA của từng target host
        |
        v
Step C: TXT record trên cluster0.example.mongodb.net
        |
        v
Step D: TCP tới đúng target:port
```

Các hostnames ở trên là **minh họa**; kết quả Atlas thực tế phải lấy bằng DNS lookup hoặc Atlas Connect modal.

### 5.1. Linux/macOS với dig

```bash
# Dùng SRV hostname thật từ URI, thay hostname ví dụ.
dig +short SRV _mongodb._tcp.cluster0.example.mongodb.net

dig +short TXT cluster0.example.mongodb.net

# Dùng từng hostname được SRV trả về.
dig +short A node0.example.mongodb.net
dig +short AAAA node0.example.mongodb.net
```

Một câu trả lời SRV chứa fields kiểu:

```text
priority weight port target
0        0      27017 node0.example.mongodb.net.
```

**Port và hostname phải lấy từ bản ghi thực tế**, không đoán mọi network path đều dùng duy nhất 27017.

### 5.2. Windows PowerShell

```powershell
Resolve-DnsName -Name "_mongodb._tcp.cluster0.example.mongodb.net" -Type SRV
Resolve-DnsName -Name "cluster0.example.mongodb.net" -Type TXT

Resolve-DnsName -Name "node0.example.mongodb.net" -Type A
Resolve-DnsName -Name "node0.example.mongodb.net" -Type AAAA
```

Tùy Windows/DNS environment, có thể dùng `nslookup`:

```powershell
nslookup -type=SRV _mongodb._tcp.cluster0.example.mongodb.net
nslookup -type=TXT cluster0.example.mongodb.net
nslookup node0.example.mongodb.net
```

### 5.3. Phân biệt kiểu lỗi DNS

- **NXDOMAIN**: tên được hỏi không tồn tại theo resolver đang dùng; có thể hostname sai hoặc cluster URI cũ.
- **SERVFAIL**: resolver không hoàn tất lookup; có thể upstream, DNSSEC, forwarding, network policy.
- **Timeout**: DNS server không trả lời; kiểm tra UDP/TCP 53, resolver route, DNS proxy/sidecar.
- **SRV record không có**: DNS resolver không hỗ trợ SRV, domain không có record, cluster paused/deleted hoặc đang dùng sai hostname.
- **SRV có target nhưng A/AAAA không có**: không phân giải được hostname node, đặc biệt hay gặp cấu hình Private Endpoint/split DNS sai.
- **DNS trả địa chỉ nhưng TCP không tới**: DNS có thể hoàn toàn đúng; chuyển qua lớp network.

### 5.4. So resolver

```bash
dig @1.1.1.1 +short SRV _mongodb._tcp.cluster0.example.mongodb.net
```

Lệnh trên chỉ phù hợp **môi trường có chủ đích dùng public DNS**, không phù hợp khi dùng private DNS/Private Endpoint. Với endpoint nội bộ, public resolver có thể trả sai hoặc không thấy bản ghi private; **đừng tự chuyển DNS server của production sang public DNS** mà chưa đánh giá security/network design.

### 5.5. DNS cache và TTL

- OS, CoreDNS, sidecar và JVM có thể cache kết quả khác nhau.
- Negative caching có thể giữ kết quả thất bại một thời gian.
- DNS thay đổi sau failover/cluster scaling; hardcoded IP có thể trở nên sai.
- Đừng sửa `/etc/hosts` để “cứu” một SRV URI rồi coi đó là giải pháp lâu dài.
- Khi so kết quả DNS, ghi rõ resolver, timestamp, TTL và môi trường kiểm tra.

**Quan trọng:** DNS trả IP hợp lệ không chứng minh TCP/TLS/application có thể kết nối.

---

## 6. DNS trong Docker, Kubernetes và môi trường cloud

### 6.1. `localhost` thay đổi theo runtime

- Trên laptop host: `localhost:27017` trỏ tới chính laptop.
- Trong Docker container: `localhost` trỏ tới **container đó**, không phải host machine.
- Trong Kubernetes pod: `localhost` trỏ tới **pod network namespace**, không phải MongoDB Service ở pod khác.
- Trong Atlas: không dùng `localhost` để truy cập cluster bên ngoài nếu không có tunnel được cấu hình.

Ví dụ ứng dụng container kết nối MongoDB container khác trên cùng Docker network nên dùng DNS service/container name phù hợp, chẳng hạn `mongo:27017`, **không dùng `127.0.0.1:27017`**.

### 6.2. Kiểm tra từ bên trong container

```bash
# Tên container ví dụ: api
docker exec api sh -c 'getent hosts mongo || true'

docker exec api sh -c 'getent hosts node0.example.mongodb.net || true'
```

`getent` có thể không tồn tại trong image cực nhỏ. Không cài debug utilities vào production image nếu policy không cho phép; có thể dùng debug container được cho phép.

### 6.3. Kubernetes

```bash
kubectl -n my-namespace get pods
kubectl -n my-namespace get svc

# Chỉ ví dụ, cần shell và nslookup sẵn có trong pod.
kubectl -n my-namespace exec deploy/my-api -- \
  nslookup cluster0.example.mongodb.net
```

Dùng namespace/Deployment names thật. Với CoreDNS hoặc VPC/private endpoints, kiểm tra:

- `/etc/resolv.conf` trong pod.
- CoreDNS health và forwarding rules.
- Kubernetes NetworkPolicy với DNS egress.
- Node/VPC route, NAT Gateway, private endpoint.
- Khác biệt giữa pod được phép ra internet và pod bị chặn.
- Split-horizon DNS cho hostname Private Endpoint.

### 6.4. Replica set hostnames chỉ phân giải được nội bộ

Self-managed replica set có thể quảng bá thành viên:

```text
mongo-0.mongo-headless.database.svc.cluster.local:27017
mongo-1.mongo-headless.database.svc.cluster.local:27017
```

Nếu Java app **chạy bên ngoài cluster**, những hostnames nội bộ có thể không resolve/route được. Seed ban đầu có thể kết nối nhưng sau khi `hello` trả topology, driver cố truy cập members theo tên quảng bá rồi thất bại.

Đây là vấn đề **network topology và replica-set member hostnames**, không phải lý do bật `directConnection=true` trong production một cách vô điều kiện.

---

## 7. Kiểm tra TCP: DNS đúng nhưng kết nối vẫn không tới

Sau khi có **node hostname và port thật**, kiểm tra TCP từ đúng runtime.

### 7.1. Windows PowerShell

```powershell
Test-NetConnection `
  -ComputerName "node0.example.mongodb.net" `
  -Port 27017 `
  -InformationLevel Detailed
```

Đọc:

- `RemoteAddress`: IP do DNS trả.
- `RemotePort`: port đang thử.
- `TcpTestSucceeded`: TCP handshake có thành công không.
- `SourceAddress`/interface: có thể giúp xác định route.

`TcpTestSucceeded=True` **không chứng minh TLS handshake hoặc MongoDB auth thành công**.

### 7.2. Linux/macOS

```bash
nc -vz node0.example.mongodb.net 27017
```

Một số `nc` implementations dùng cú pháp/flags khác; có thể dùng:

```bash
timeout 5 bash -c '</dev/tcp/node0.example.mongodb.net/27017'
```

Đoạn `/dev/tcp` phụ thuộc Bash, không chuẩn POSIX. Dùng công cụ phù hợp OS và container image thay vì giả định mọi môi trường đều có Bash/nc.

### 7.3. Cách đọc kết quả

| TCP result | Giả thuyết chính |
| --- | --- |
| Kết nối thành công | DNS/route/TCP listener thông; tiếp tục TLS/hello |
| `Connection refused` | Host reachable nhưng port không lắng nghe hoặc thiết bị trả reject |
| Timeout | Firewall drop, network ACL, route, endpoint chưa reachable |
| `No route to host` | IP routing/network unreachable |
| Chỉ một IP thất bại | Node-specific firewall, endpoint/subnet, IPv4/IPv6 |
| Chỉ từ pod A thất bại | Security policy/route/DNS của pod/node đó |
| TCP ổn nhưng driver timeout | TLS, server hello, SDAM, auth, pool hoặc load |

### 7.4. Ping không quyết định TCP

`ping` dùng ICMP, có thể bị firewall/cloud chặn. **Ping thất bại không chứng minh MongoDB TCP thất bại**. Dùng port-level check.

### 7.5. `bindIp` và listener ở self-managed

Trên self-managed server, kiểm tra `mongod` đang chạy và lắng nghe địa chỉ/port đúng:

Linux:

```bash
ss -ltn | grep 27017
```

Windows:

```powershell
Get-NetTCPConnection -LocalPort 27017 -State Listen
```

`mongod` bind vào `127.0.0.1` chỉ nhận localhost traffic; app ở host khác không thể kết nối qua public/private IP đó. Đừng đổi `bindIp` thành `0.0.0.0` trên production khi chưa có TLS, auth và firewall/network policy bảo vệ.

---

## 8. Atlas: IP access list và outbound egress IP

MongoDB Atlas chỉ cho phép client từ những IP/CIDR được đặt trong **project IP access list**, hoặc qua connectivity model như Private Endpoint có policy riêng.

Những lỗi thường gặp:

- Developer cho phép IP laptop nhưng application chạy trên cloud với **NAT egress IP khác**.
- NAT Gateway thay đổi hoặc deployment di chuyển region.
- Có nhiều egress IP vì nhiều AZ, pods hoặc proxies.
- Network policy của cloud chặn outbound TCP 27017.
- Atlas IP allow-list có đúng IP nhưng firewall corporate vẫn chặn.
- Cluster paused/provisioning/deleted.
- Firewall của ISP/proxy yêu cầu cấu hình đặc biệt.

### 8.1. Khám phá egress IP

Một request ra dịch vụ kiểm tra IP từ **chính runtime ứng dụng** có thể giúp biết public egress IP, nhưng cần xét chính sách bảo mật và source NAT. Không lấy địa chỉ public của laptop rồi mặc định đó là egress IP của production pods.

Ở cloud, nguồn đáng tin hơn là network/NAT/VPC configuration của tổ chức.

### 8.2. Không mở `0.0.0.0/0` để “test cho nhanh”

Atlas có thể cho phép thêm một dải rất rộng, nhưng điều đó tăng bề mặt tấn công. Trong production:

- Giới hạn CIDR tối thiểu.
- Tách IP access list theo deployment/environment.
- Dùng private networking khi phù hợp.
- Có expiry cho temporary access nếu policy hỗ trợ.
- Không bỏ TLS/auth.
- Ghi change ticket và owner.

### 8.3. Một cổng mở chưa chắc đủ mọi topology

Atlas dùng các ports phụ thuộc deployment/tier/topology; tài liệu nói port 27017 cho nhiều connections và các tình huống sharded có thể cần ports khác. Lấy **hostname/port chính xác từ connection string hoặc SRV result**, kiểm tra mọi node cần thiết, không mở tùy tiện cả dải ports không có cơ sở.

---

## 9. TLS: sau TCP là bảo vệ kết nối và xác thực máy chủ

Khi MongoDB yêu cầu TLS, driver phải thiết lập TLS handshake trước khi trao đổi các MongoDB protocol commands.

Một số lỗi điển hình:

```text
javax.net.ssl.SSLHandshakeException:
PKIX path building failed
```

```text
javax.net.ssl.SSLHandshakeException:
No subject alternative DNS name matching ...
```

```text
javax.net.ssl.SSLHandshakeException:
Received fatal alert: handshake_failure
```

```text
javax.net.ssl.SSLException:
Unrecognized SSL message, plaintext connection?
```

Thông báo ngoài cùng đôi khi là `MongoSocketOpenException` hoặc `MongoTimeoutException`, còn TLS cause nằm sâu hơn.

### 9.1. SRV và standard TLS defaults

- `mongodb+srv://`: TLS thường **bật mặc định**.
- `mongodb://`: TLS thường **tắt mặc định** nếu không khai báo/không có cấu hình khác.
- Atlas yêu cầu TLS; hãy dùng URI TLS phù hợp.
- Self-managed server có thể yêu cầu hoặc không yêu cầu TLS theo `net.tls.mode`.

Nếu kết nối bằng TLS tới port chạy plaintext MongoDB, có thể xuất hiện lỗi handshake/EOF. Nếu client không TLS tới server bắt buộc TLS, cũng lỗi. **Sửa hai đầu để đồng bộ TLS mode**, không tắt TLS khi chính sách yêu cầu.

### 9.2. Kiểm tra handshake bằng OpenSSL

Trên Linux/macOS với OpenSSL:

```bash
openssl s_client \
  -connect node0.example.mongodb.net:27017 \
  -servername node0.example.mongodb.net \
  -showcerts \
  -verify_return_error
```

- `-connect`: hostname/port TCP.
- `-servername`: SNI; nên khớp hostname thật.
- `-showcerts`: xem certificate chain được trình bày.
- `-verify_return_error`: có thể fail khi chain không được trust.

Chỉ dùng lệnh với **host do bạn quản trị/được phép kiểm tra**. OpenSSL handshake thành công chưa chứng minh MongoDB authentication, read preference hoặc command thành công.

Đối với Windows có OpenSSL được cài, cú pháp tương tự. Nếu không có OpenSSL, dùng Java JSSE debug hoặc công cụ kiểm chứng chứng chỉ được tổ chức phê duyệt.

---

## 10. Đọc chứng chỉ: CA, SAN, validity và mTLS

Một TLS certificate thường có:

- `Subject` và `Issuer`.
- `Subject Alternative Name` (SAN) gồm DNS names/IPs hợp lệ.
- `Not Before` / `Not After`.
- Public key và signature.
- Chuỗi chứng chỉ đến root/intermediate CA.
- Extended Key Usage phù hợp.

### 10.1. Lỗi hostname mismatch

Ví dụ URI kết nối:

```text
mongodb://10.10.0.15:27017/?tls=true
```

Nhưng server certificate chỉ có SAN `db1.internal.example.net`.

Java TLS hostname verification có thể báo **không khớp hostname**. Giải pháp đúng:

- Dùng hostname có trong SAN và đảm bảo DNS/route tới đúng node.
- Hoặc cấp/chuyển certificate hợp lệ cho hostname/IP sẽ dùng.
- Kiểm tra SNI/cert rotation nếu endpoint có nhiều certs.

**Không dùng `tlsAllowInvalidHostnames=true` hoặc `tlsInsecure=true` trên production** để bypass lỗi.

### 10.2. PKIX path building failed

Nguyên nhân thường:

- Server certificate ký bởi private CA nhưng JVM không trust CA.
- Intermediate CA chain bị thiếu.
- JDK truststore khác OS truststore.
- Container dùng JRE/custom image với CA bundles không đầy đủ.
- TLS intercepting proxy phát cert từ CA nội bộ không được chấp nhận.
- Certificate bị thay khi rotation nhưng truststore chưa cập nhật.

Cách xử lý:

1. Xác minh kết nối tới đúng hostname và certificate đang trình bày.
2. Kiểm tra chain, issuer và expiry.
3. Kiểm tra truststore mà **JVM thật sự dùng**.
4. Bổ sung **CA đáng tin và được phê duyệt** vào truststore đúng cách.
5. Khởi động lại/rollout process nếu runtime yêu cầu để đọc truststore mới.
6. Kiểm tra không có MITM/proxy không được phép.

### 10.3. Xem file certificate

Nếu có bản sao public server cert:

```bash
openssl x509 \
  -in server-cert.pem \
  -noout -subject -issuer -dates \
  -ext subjectAltName
```

Kiểm tra lệch clock/NTP: một máy có thời gian sai có thể coi certificate “not yet valid” hoặc expired.

### 10.4. Java truststore và keystore

- **Truststore:** chứa CA/certificates được tin tưởng để xác thực **server**.
- **Keystore:** chứa client certificate/private key để **client** tự chứng minh danh tính khi mTLS/X.509 cần.

Java có thể cấu hình:

```text
-Djavax.net.ssl.trustStore=/secure/path/mongo-truststore.p12
-Djavax.net.ssl.trustStoreType=PKCS12
```

Password truststore phải được truyền qua secrets management phù hợp; **không dán `-Djavax.net.ssl.trustStorePassword=...` chứa password thật vào ticket, logs hoặc repository**.

Kiểm tra truststore bằng `keytool -list -v -keystore ...` với password prompt theo policy.

### 10.5. mTLS và X.509

Một số self-managed deployments yêu cầu client certificate; Atlas X.509 authentication cũng có cấu hình riêng. Phải kiểm tra:

- Server có yêu cầu client cert không?
- Client cert có được cấp từ CA được server tin cậy không?
- Có private key tương ứng, đúng format?
- Certificate subject có map tới user/auth mechanism khi dùng X.509?
- Client keystore khác server truststore ra sao?

**TLS encryption/validation** và **MongoDB user authentication** là các lớp khác nhau. TLS thành công không bảo đảm SCRAM/X.509 login thành công.

---

## 11. TLS version, cipher suites, JDK và JSSE logs

### 11.1. JDK và TLS compatibility

MongoDB Atlas và nhiều deployments hiện đại yêu cầu TLS 1.2+ theo chính sách. JDK cũ có thể thiếu protocol/cipher phù hợp hoặc có lỗi TLS 1.3 ở những patch versions nhất định.

- Ghi chính xác JDK vendor, major và update/patch.
- Xem MongoDB Java Driver compatibility.
- Kiểm tra protocol bị chặn bởi `jdk.tls.disabledAlgorithms`.
- Cập nhật JDK/CA bundle theo chính sách thay vì giảm security constraints.

### 11.2. Bật JSSE debug có kiểm soát

Ví dụ chạy JVM lab:

```bash
java -Djavax.net.debug=ssl,handshake,trustmanager -jar app.jar
```

Có thể dùng `-Djavax.net.debug=all` khi cần rất chi tiết, nhưng **logs cực nhiều** và có thể lộ metadata nhạy cảm. Chỉ bật tạm thời trong môi trường được kiểm soát, đặt log retention và redaction.

Những câu hỏi cần tìm trong debug:

- JVM dùng truststore nào?
- Server gửi certificate chain nào?
- Certificate được chấp nhận hay từ chối vì CA/expiry/SAN?
- TLS version/cipher được chọn?
- Có handshake alert từ client hay server?

### 11.3. Lỗi TLS không nên chữa bằng tăng timeout

Nếu `SSLHandshakeException: PKIX path building failed`, tăng `connectTimeoutMS` hay `serverSelectionTimeoutMS` chỉ làm ứng dụng **chờ lâu hơn trước khi thất bại**. Phải sửa trust/certificate chain.

---

## 12. MongoDB Java Driver và SDAM: chọn server thế nào?

**SDAM** = Server Discovery and Monitoring. Driver theo dõi topology và biết:

- Cluster là standalone, replica set hay sharded `mongos`.
- Server nào reachable.
- Server nào primary/secondary/arbiter.
- Round-trip time (RTT) và trạng thái heartbeat.
- Những members nào đáp ứng read preference và loại thao tác.

Khi thực hiện command, driver tìm một server phù hợp. Nếu hết thời gian mà không tìm được, ném `MongoTimeoutException` với cluster description.

### 12.1. Ví dụ lỗi thật sự có thông tin

```text
com.mongodb.MongoTimeoutException:
Timed out after 30000 ms while waiting for a server
that matches ReadPreferenceServerSelector{readPreference=primary}.
Client view of cluster state is {
  type=REPLICA_SET,
  servers=[
    {address=db1:27017, type=UNKNOWN, state=CONNECTING,
     exception={MongoSocketOpenException:
       caused by ConnectException: Connection refused}},
    {address=db2:27017, type=REPLICA_SET_SECONDARY, state=CONNECTED}
  ]
}
```

Phân tích:

- Driver đã liên hệ được **db2 secondary**.
- Operation đòi **primary**.
- db1 không kết nối được.
- Không có server phù hợp với selector, nên timeout.
- Đây không nhất thiết là DNS toàn cluster thất bại.

### 12.2. `type=UNKNOWN` không phải “server bị xóa”

`type=UNKNOWN`, `state=CONNECTING` nghĩa driver **chưa nhận đủ thông tin để xác định server** trong thời điểm được ghi nhận. Xem nested exception; có thể DNS, TLS, TCP, handshake hoặc discovery.

### 12.3. Server selection vs TCP connect

- **Connect timeout:** một kết nối socket chưa thiết lập trong giới hạn.
- **Server selection timeout:** sau các thử nghiệm discovery, không có server phù hợp với topology/read preference trong giới hạn.
- Một server selection timeout có thể chứa **nhiều connect failures lặp lại** bên trong.

Chẩn đoán phải đọc cả hai; tránh coi chúng là một tham số.

---

## 13. Replica set: primary, secondary và hostnames được quảng bá

### 13.1. Không có primary khả dụng

Trường hợp:

```text
db1: UNKNOWN / unreachable
db2: SECONDARY / connected
db3: SECONDARY / connected
request: write hoặc readPreference=primary
```

Writes phải đi primary; reads mặc định của driver thường là primary. Nếu không chọn được primary, operation có thể timeout dù một secondary phản hồi tốt.

Kiểm tra self-managed replica set:

```javascript
db.hello();
rs.status();
rs.conf();
```

`rs.status()` và `rs.conf()` cần kết nối/role phù hợp và quyền tương ứng. Trên Atlas, dùng cluster status, replication metrics và event logs.

### 13.2. Election và failover

Trong lúc election, có thể có khoảng thời gian không có primary. Nếu cluster khôi phục trong timeout, request có thể thành công; nếu không, driver báo lỗi. Không nhầm failover ngắn với chứng chỉ TLS hỏng.

Những điều cần xem:

- Primary election events.
- Member health và majority/quorum.
- Network partitions.
- Replication lag.
- Disk pressure/CPU saturation.
- Driver heartbeat/topology updates.

Không chạy `rs.reconfig()` hay `rs.stepDown()` trên production chỉ để thử kết nối.

### 13.3. `replicaSet` option sai

URI:

```text
mongodb://db1:27017,db2:27017/?replicaSet=rsWrong
```

Nếu server báo set name `rs0`, driver sẽ không coi đó là topology phù hợp. Kiểm tra `db.hello()`/`rs.conf()` để xác định tên thật.

### 13.4. Advertised hosts không truy cập được

Driver kết nối seed `public-gateway.example.net` thành công; `hello` trả members:

```text
db1.internal.local:27017
db2.internal.local:27017
db3.internal.local:27017
```

Ứng dụng bên ngoài không resolve/route được internal hosts, dẫn tới server selection timeout **sau kết nối seed thành công**.

Giải pháp là cấu hình **topology network/DNS/replica set member hostnames** phù hợp nơi ứng dụng chạy, không mặc định thêm nhiều retries.

### 13.5. `directConnection=true` chỉ khi có chủ đích

```text
mongodb://db1.example.net:27017/?directConnection=true
```

Tùy chọn này yêu cầu driver kết nối **trực tiếp tới một host** thay vì khám phá topology theo cách thông thường. Nó hữu ích cho diagnostics/lab/tunnel trong một số hoàn cảnh, nhưng:

- Không bảo đảm high availability/failover.
- Không sửa DNS/TLS thực sự của mọi replica set members.
- Không nên dùng để che việc các members được quảng bá không reachable trong production.
- Một operation yêu cầu primary vẫn phải thỏa server capabilities/role.

---

## 14. Read preference cũng là điều kiện chọn server

Các chế độ read preference có mục tiêu khác nhau:

| Mode | Đặc điểm | Liên hệ timeout |
| --- | --- | --- |
| `primary` | Chỉ đọc primary | Không có primary → không chọn được |
| `primaryPreferred` | Ưu tiên primary, fallback secondary khi phù hợp | Có thể đọc secondary, phải chấp nhận staleness |
| `secondary` | Chỉ đọc secondary | Không có secondary đủ điều kiện → timeout |
| `secondaryPreferred` | Ưu tiên secondary, fallback primary khi phù hợp | Không bảo đảm read-your-writes |
| `nearest` | Chọn candidates theo latency/topology rules | Không đồng nghĩa read mới nhất |

**Không đổi read preference chỉ để “hết lỗi”** nếu nghiệp vụ cần đọc dữ liệu vừa ghi hoặc strict consistency.

### 14.1. `serverSelectionTimeoutMS` không làm xuất hiện primary

Ví dụ app tăng timeout từ 30 lên 120 giây, nhưng replica set mất majority nhiều phút. Thời gian chờ tăng nhưng điều kiện có primary vẫn không được đáp ứng.

### 14.2. Server selection còn có tags/staleness

Với read preference tags hoặc `maxStalenessSeconds`, một số secondaries có thể bị loại dù TCP/TLS hoạt động. Cần inspect read preference và diagnostics; vấn đề có thể nằm ở selector chứ không phải network.

---

## 15. Timeout: năm đồng hồ khác nhau

Các giá trị mặc định bên dưới phản ánh **các bản MongoDB Java Sync Driver được tài liệu hiện hành mô tả**, nhưng cần kiểm tra driver version và các options đã được Spring/framework override.

| Option/khái niệm | Đồng hồ đo | Default thường gặp | Khi nào đáng điều chỉnh |
| --- | --- | --- | --- |
| `serverSelectionTimeoutMS` | Chờ chọn server hợp lệ trong topology | 30000ms | SLA/troubleshooting; không sửa root cause |
| `connectTimeoutMS` | Chờ tạo TCP socket connection | 10000ms | Route/network latency có căn cứ |
| `socketTimeoutMS` | Chờ socket send/receive | 0 (không đặt limit theo option) | Operation I/O hung; cần budget |
| Pool checkout wait | Chờ lấy connection có sẵn | Theo driver; `waitQueueTimeoutMS` legacy/deprecated | Pool saturation |
| `timeoutMS` (CSOT) | Budget client-side trên operation; gồm selection/checkout/execution | Tùy version/cấu hình; tính năng có thể experimental | End-to-end operation deadline |

### 15.1. Server selection timeout

```text
mongodb://db1.example.net:27017/?serverSelectionTimeoutMS=10000
```

Sau khoảng tối đa 10 giây không chọn được server, driver ném timeout theo semantics của version. Đây là thời hạn **chọn**, không phải giới hạn query execution trên server.

### 15.2. Connect timeout

```text
mongodb://db1.example.net:27017/?connectTimeoutMS=5000
```

TCP connect attempt bị giới hạn khoảng 5 giây. Nếu DNS trả sai route hoặc firewall drop, mỗi attempt có thể thất bại nhưng driver vẫn tiếp tục discovery trong server selection budget.

### 15.3. Socket timeout

```text
mongodb://db1.example.net:27017/?socketTimeoutMS=10000
```

Áp dụng cho socket read/write theo driver semantics. Đừng dùng 10 giây cho mọi analytics query có thể chạy 30 giây trừ khi đó là business policy.

### 15.4. Pool wait khác selection

Nếu server đã được chọn nhưng pool đầy, application có thể đợi checkout. Tùy driver version, `waitQueueTimeoutMS` được mô tả nhưng **đã deprecated** trong docs hiện hành, khuyến nghị dùng client-level operation timeout/CSOT khi phù hợp. Đọc đúng driver release, đừng copy config cũ một cách máy móc.

### 15.5. Client-side operation timeout (CSOT)

MongoDB Java Driver docs hiện hành có `timeoutMS`/CSOT nhằm giới hạn **thời gian một operation** gồm selection, checkout, network và thực thi; tính năng đang được ghi chú **experimental** trong tài liệu.

```text
mongodb://db1.example.net:27017/?timeoutMS=10000
```

Chỉ dùng khi driver version hỗ trợ, đã kiểm tra semantics và policy của ứng dụng. Đừng cộng tất cả individual timeouts rồi khẳng định operation chắc chắn hoàn thành trước tổng đó.

### 15.6. Không chỉ “tăng mọi timeout”

Tăng timeout có thể:

- Giảm false timeout trong failover ngắn.
- Nhưng khiến request threads/virtual threads chờ lâu.
- Làm HTTP gateway đã timeout trước nhưng DB work còn chạy.
- Tạo retry amplification và pool saturation.
- Che sự cố DNS/TLS lặp lại.

Lập timeout budget từ **end-user SLO**, thời gian retry và dữ liệu quan sát, không chỉ dựa vào default.

---

## 16. Java Sync Driver: chương trình ping để xác minh thật

**Tạo MongoClient thành công không chứng minh đã kết nối.** Driver có thể khởi tạo client và khám phá server bất đồng bộ; cần **thực hiện một operation** như `ping`.

### 16.1. Code Java tự chứa

```java
import com.mongodb.MongoClientSettings;
import com.mongodb.MongoException;
import com.mongodb.MongoTimeoutException;
import com.mongodb.ConnectionString;

import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;

import org.bson.Document;

import java.util.concurrent.TimeUnit;

public final class MongoConnectivityProbe {
    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");

        if (uri == null || uri.isBlank()) {
            throw new IllegalArgumentException(
                "Environment variable MONGODB_URI is required"
            );
        }

        MongoClientSettings settings = MongoClientSettings.builder()
            .applyConnectionString(new ConnectionString(uri))
            .applyToClusterSettings(builder ->
                builder.serverSelectionTimeout(
                    10, TimeUnit.SECONDS
                )
            )
            .applyToSocketSettings(builder ->
                builder.connectTimeout(
                    5, TimeUnit.SECONDS
                )
            )
            .build();

        try (MongoClient client = MongoClients.create(settings)) {
            Document response = client
                .getDatabase("admin")
                .runCommand(new Document("ping", 1));

            System.out.println(
                "MongoDB ping command completed: "
                + response.get("ok")
            );
        } catch (MongoTimeoutException e) {
            System.err.println("Server selection timed out");
            printCauseChain(e);
            throw e;
        } catch (MongoException e) {
            System.err.println("MongoDB operation failed");
            printCauseChain(e);
            throw e;
        }
    }

    static void printCauseChain(Throwable error) {
        Throwable current = error;
        int level = 0;
        while (current != null && level < 12) {
            System.err.println(
                level + ": "
                + current.getClass().getName()
                + ": " + current.getMessage()
            );
            current = current.getCause();
            level++;
        }
    }
}
```

**Lưu ý:** cause messages có thể chứa hostnames, usernames hoặc connection metadata. Trong production, sanitize log output thay vì in nguyên stack trace vào public log sink. Code trên dùng cho diagnostic environment.

### 16.2. Chạy với environment

PowerShell:

```powershell
$env:MONGODB_URI = "mongodb://127.0.0.1:27017/?serverSelectionTimeoutMS=10000"
```

Linux/macOS:

```bash
export MONGODB_URI='mongodb://127.0.0.1:27017/?serverSelectionTimeoutMS=10000'
```

Thay URI bằng giá trị an toàn của deployment thử nghiệm. Dùng secrets injection theo policy đối với production. Không dùng lệnh trên với real password rồi paste vào shell history/ticket.

### 16.3. Các khẳng định của phép thử

- `MongoClients.create(...)` **không đủ** chứng minh connectivity.
- `ping` thành công chứng minh đã chọn server, thiết lập connection và command đã được xử lý theo quyền/connection hiện tại.
- `ping` thành công **không** chứng minh user có quyền đọc collection hoặc transaction/query workload sẽ chạy tốt.
- `ping` thành công một node **không** chứng minh toàn replica set/shards đều reachable.
- Nếu ping thất bại, đọc root cause và cluster description rồi quay về DNS/TCP/TLS/SDAM.

---

## 17. Spring Boot/Spring Data: lỗi xuất hiện lúc nào?

Một ứng dụng Spring Boot có thể khởi tạo `MongoTemplate`/repository bean mà chưa xác minh toàn bộ đường kết nối. Truy vấn đầu tiên hoặc health check thực hiện operation mới làm lỗi bộc lộ.

### 17.1. Cấu hình connection URI

Ví dụ config lab:

```properties
spring.data.mongodb.uri=mongodb://127.0.0.1:27017/appdb
```

Với production, cấp URI qua secret/environment injection tương thích version Spring Boot, và không commit password vào `application.properties`.

### 17.2. Startup probe bằng MongoTemplate

```java
import org.bson.Document;
import org.springframework.data.mongodb.core.MongoTemplate;

public final class DbProbe {
    private final MongoTemplate mongoTemplate;

    public DbProbe(MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    public boolean canPing() {
        Document result = mongoTemplate
            .getDb()
            .runCommand(new Document("ping", 1));

        Object ok = result.get("ok");
        return ok instanceof Number
            && ((Number) ok).doubleValue() == 1.0;
    }
}
```

Đoạn code trên minh họa một **active connectivity check**; trong service thật, không gọi mỗi HTTP request. Cần phân biệt liveness/readiness:

- **Liveness:** service process còn sống, restart nếu không phục hồi; không nên ràng buộc tuyệt đối mọi liveness check vào MongoDB outage ngắn.
- **Readiness:** pod có thể phục vụ traffic cần DB hay không; có thể kết hợp MongoDB health khi policy phù hợp.
- **Startup:** chờ khởi tạo dependency trong budget xác định.

### 17.3. Đừng chỉ nhìn lỗi Spring wrapper

Một Spring Data exception như `DataAccessResourceFailureException` có thể bọc `MongoTimeoutException`. Cần nhìn nested exception/root cause, không chỉ log “Cannot connect to MongoDB”.

### 17.4. Spring Boot Actuator

Nếu dùng Actuator Mongo health indicator, kiểm tra:
- Có bật indicator/endpoint không?
- Health check có thực hiện DB operation không?
- Readiness bị ảnh hưởng ra sao khi failover?
- Timeout của health check có phù hợp probe interval và restart policy?
- Health status có được bật lộ công khai mà tiết lộ metadata không?

Không cho rằng `/actuator/health` trả `UP` đồng nghĩa mọi tenant query và indexes khỏe.

---

## 18. Compass/mongosh thành công nhưng Java thất bại

Đây là tình huống phổ biến:

```text
Compass trên laptop: OK
MongoDB Java pod:    MongoTimeoutException
```

Có nhiều khác biệt:

| Yếu tố | Compass/mongosh | Java app |
| --- | --- | --- |
| Network | Laptop/VPN | Pod/container/VPC |
| DNS resolver | OS/public DNS | CoreDNS/private resolver |
| Egress IP | ISP/VPN IP | NAT gateway/service mesh |
| TLS truststore | OS/app bundle | JVM truststore |
| JDK/TLS stack | Electron/Node/OpenSSL | JSSE |
| URI options | Dán Atlas URI mới | App đang dùng config cũ |
| Authentication | Saved profile/user | Secret/env var khác |
| Replica set discovery | GUI option khác | Java driver SDAM |
| Connection pool | Vài connections | Hàng trăm app threads |
| Driver version | Bundled | Dependency BOM |
| Time | Test lúc khác | Incident/failover thời điểm khác |

### 18.1. Phép so sánh công bằng

Chạy `mongosh` **từ cùng máy/pod** nếu được phép:

```bash
mongosh 'mongodb+srv://cluster0.example.mongodb.net/app'
```

Với secured deployment, cung cấp credentials qua prompt/cơ chế bí mật của công cụ. Bảo đảm same hosts, TLS, authSource, read preference, resolver và network path.

### 18.2. Mongosh OK chưa chắc Java TLS OK

Nếu `mongosh` dùng certificate trust chain từ OS/OpenSSL/Node nhưng JVM dùng custom truststore cũ, cùng endpoint có thể thành công trên shell và thất bại trong Java. Kiểm tra JSSE/debug/truststore và JDK patch version.

---

## 19. Phân biệt authentication failure với TLS/server selection

Sau TCP/TLS/hello, MongoDB xác thực user.

### 19.1. Dấu hiệu authentication

Ví dụ:

```text
MongoSecurityException:
Exception authenticating MongoCredential ...
```

hoặc:

```text
MongoCommandException:
Command failed with error 18 (AuthenticationFailed)
```

Những nguyên nhân điển hình:

- Username/password sai hoặc secret chưa cập nhật.
- `authSource` sai.
- Mật khẩu chứa ký tự đặc biệt trong URI nhưng không percent-encode.
- SCRAM mechanism không phù hợp với user/server.
- X.509 auth mechanism/certificate subject không đúng.
- Credential được tạo ở project/cluster khác.

### 19.2. `authSource` vs default database

URI:

```text
mongodb://user@db.example.net:27017/app?authSource=admin
```

`app` là database mặc định của application, còn `admin` là nơi driver xác thực user. **Hai giá trị có thể khác nhau**. Với Atlas SRV, TXT records có thể cung cấp những option như `authSource=admin`; kiểm tra URI cuối và records thực tế.

### 19.3. Không hạ bảo mật để chẩn đoán

Không tắt auth/TLS hoặc cấp role `root` chỉ để probe kết nối. Dùng user có quyền `ping` hoặc thao tác health được chỉ định, gắn approval và log sự kiện rõ.

---

## 20. Connection pool: TCP/TLS tốt nhưng request vẫn timeout

MongoDB Java Driver duy trì connection pools theo server trong topology.

Theo tài liệu Java Sync Driver hiện hành:

- `maxPoolSize` mặc định thường là **100 mỗi server**.
- `minPoolSize` thường là 0.
- `maxConnecting` thường là 2.
- Mỗi MongoClient có thể mở thêm monitoring connections theo server.

### 20.1. Một MongoClient cho cả application

**Sai**:

```java
public Document findOrder(String uri, String id) {
    try (MongoClient client = MongoClients.create(uri)) {
        return client.getDatabase("app")
            .getCollection("orders")
            .find(new Document("_id", id))
            .first();
    }
}
```

Nếu tạo và đóng client mỗi request, application lặp lại discovery/pool/TLS setup, tạo connection churn và latency cao.

**Đúng:** khởi tạo một `MongoClient` theo service/container lifecycle và tái sử dụng, đóng khi shutdown.

### 20.2. Phân biệt selection với checkout

```text
Server found and eligible
      |
      v
Connection pool checkout
      |
      +-- Connection available -> command
      |
      +-- All connections busy -> wait/queue
                               -> checkout timeout
```

Nếu lỗi là **pool timeout**, DNS/TLS của những connections đang hoạt động có thể hoàn toàn tốt.

Kiểm tra:

- In-use/idle/connecting connections.
- Max pool size và checkout wait time.
- App concurrency, executor/scheduler queues.
- MongoDB slow queries, long transactions.
- Number of MongoClient instances/pods.
- Retry storm, leaked cursors/streams.

### 20.3. Pool size không phải throughput vô hạn

Ví dụ bốn application instances, mỗi instance có pool tối đa 100 connections tới mỗi trong ba nodes: lý thuyết có thể lên đến `4 × 3 × 100 = 1200` pooled sockets nếu tất cả pools đạt tối đa, chưa tính monitoring sockets/topology differences.

Tăng pool vô hạn có thể làm server chậm hơn. Hãy kiểm tra server CPU/IOPS/latency và giảm query time trước khi scale pool.

### 20.4. Tuning timeout khi có CSOT

Một số versions hiện hành có client-side operation timeout `timeoutMS`/CSOT. Docs ghi chú CSOT experimental; tránh sử dụng lẫn lộn `waitQueueTimeoutMS` legacy và CSOT mà chưa đọc semantics của driver.

---

## 21. `directConnection`, tunnels và development traps

### 21.1. Kết nối qua SSH tunnel

Giả sử tunnel được phép ánh xạ `localhost:27018` tới một replica-set member:

```text
mongodb://127.0.0.1:27018/?directConnection=true
```

Dùng để kiểm tra một host trong một số lab/tunnel scenarios. Nhưng khi driver khám phá replica set, các advertised hostnames có thể nằm ngoài tunnel; không thể tự coi `directConnection` là giải pháp high availability.

### 21.2. Docker published port

Nếu MongoDB local chỉ published port qua Docker:

```bash
docker run --rm -d \
  --name mongo-connect-lab \
  -p 127.0.0.1:27018:27017 \
  mongo:8.0
```

Cấu hình này **chỉ dành cho lab local**, không bật authentication/TLS; được bind vào loopback `127.0.0.1` của host. Với Docker Desktop, host OS cần Docker Engine hoạt động và image được tải theo policy.

Kết nối:

```bash
mongosh 'mongodb://127.0.0.1:27018/?directConnection=true'
```

Trong một container application khác, `127.0.0.1` lại là container đó, không trỏ tới container MongoDB. Hãy dùng network alias/service name.

### 21.3. Không dùng bindIp 0.0.0.0 tùy tiện

Tự mở MongoDB test không auth ra mạng public là nguy hiểm. Dùng network isolation, `127.0.0.1` host publishing và xóa lab sau thực hành.

---

## 22. Private Endpoint và split-horizon DNS

Các triển khai Atlas qua cloud Private Endpoint/PrivateLink/Private Service Connect có thêm một lớp cấu hình:

- Private Endpoint service và endpoint connection **được chấp nhận/available**.
- DNS names của endpoint resolve thành **private IP phù hợp** từ VPC/VNet của application.
- VPC/VNet routes, subnets, security groups, NACLs cho phép kết nối.
- Atlas private endpoint URI đúng theo region/topology.
- Cross-region/private multi-region deployment có thể yêu cầu endpoints bổ sung.
- DNS forwarders/conditional forwarding cho private zones hoạt động.
- Không dùng nhầm public SRV hostname từ laptop ở nơi chỉ đi được private network.

### 22.1. Điều tra phải thực hiện bên trong private network

Nếu laptop `dig` trả public IP còn pod trả private IP, điều đó **có thể hoàn toàn đúng** theo split-horizon DNS. Điều cần kiểm tra là pod có route và TCP tới **IP của endpoint đang sử dụng** hay không.

### 22.2. SRV có thể đúng, target A không đúng

Một SRV record trả target name; A/AAAA record của target lại resolve tới public IP trong môi trường không có internet egress. Khi đó SRV lookup pass nhưng TCP fail.

Lấy đầy đủ **SRV → targets → A/AAAA → TCP**, không dừng ở “dig SRV ra tên”.

### 22.3. Không chuyển toàn bộ private DNS sang public

Thay DNS resolver bằng `8.8.8.8` có thể làm mất private zones hoặc vi phạm security policy. Nếu issue là private endpoint DNS forwarding, sửa forwarding/private DNS architecture với network team.

---

## 23. Các kịch bản nguyên nhân gốc thường gặp

### 23.1. Atlas IP access list thiếu NAT IP

**Triệu chứng:** kết nối laptop được, ECS/EKS/AKS/VM không được; DNS resolves, TCP timeout.

**Khả năng:** IP trong Atlas project access list là laptop IP, còn app egress qua NAT Gateway khác.

**Xác minh:** đối chiếu NAT egress IP/source CIDR và access list, TCP test từ pod.

**Khắc phục:** whitelist đúng egress IP/CIDR theo policy hoặc dùng approved private networking, không mở `0.0.0.0/0`.

### 23.2. JVM truststore cũ sau cert rotation

**Triệu chứng:** Compass OK, Java `SSLHandshakeException: PKIX path building failed`.

**Khả năng:** JVM image/truststore thiếu CA mới hoặc intermediate.

**Xác minh:** compare cert chain trong handshake, truststore Java và JDK version.

**Khắc phục:** cập nhật trusted CA/JDK image/chain theo quy trình, restart pods khi cần. Không disable hostname verification.

### 23.3. SRV lookup fail trong corporate DNS

**Triệu chứng:** `mongodb+srv://` fail, `dig SRV`/`Resolve-DnsName -Type SRV` không có đáp án, hostname node chuẩn có thể resolve.

**Khả năng:** resolver không hỗ trợ SRV/forwarding sai hoặc cluster paused.

**Khắc phục:** sửa DNS SRV support; nếu phù hợp dùng **standard `mongodb://` connection string do Atlas cung cấp** theo tài liệu. Không tự đoán seed list bằng cách copy IPs đã resolve.

### 23.4. Replica set secondary reachable nhưng primary không

**Triệu chứng:** cluster description có secondary connected; selector đòi primary; selection timeout.

**Khả năng:** election, primary down, majority unavailable, read/write role constraint.

**Khắc phục:** kiểm tra replica set health/quorum và network primary; chờ/khôi phục primary theo runbook. Chỉ đổi read preference khi business cho phép stale reads; writes không thể route tới secondary.

### 23.5. Localhost sai trong container

**Triệu chứng:** ứng dụng trên laptop OK, khi deploy container `Connection refused 127.0.0.1:27017`.

**Khả năng:** MongoDB không chạy **trong cùng container**.

**Khắc phục:** dùng service DNS hoặc approved database endpoint; kiểm tra network/secret config.

### 23.6. Hostname quảng bá nội bộ bị lỗi

**Triệu chứng:** seed node reachable, driver khám phá internal member names rồi `UnknownHostException`.

**Khả năng:** replica set config quảng bá addresses chỉ dùng được trong mạng khác.

**Khắc phục:** sửa network topology/DNS/replica set advertised addresses theo plan; không chỉ bật `directConnection` để che vấn đề production.

### 23.7. Pool exhaustion sau scale-out

**Triệu chứng:** đầu ngày OK, đến peak có checkout timeout; DNS/TCP/TLS checks đều pass.

**Khả năng:** quá nhiều app concurrency, slow queries, pool size hoặc tạo MongoClient mỗi request.

**Khắc phục:** reuse MongoClient, đo checkout metrics/query latency, giảm fan-out/retry, tuning pool hợp lý và capacity planning.

### 23.8. Password sai có dấu @

**Triệu chứng:** TCP/TLS/hello OK nhưng `AuthenticationFailed`, URI có `@` trong password.

**Khả năng:** password không percent-encode dẫn tới parse nhầm host/credential.

**Khắc phục:** inject secrets và URI-encode password chính xác, kiểm tra `authSource`; không in password ra logs.

---

## 24. Quy trình điều tra theo kết quả các phép thử

```text
Ứng dụng không kết nối MongoDB
        |
        v
URI parse được không?
  | NO -> sửa scheme/host/port/percent encoding
  v YES
DNS SRV/TXT (nếu +srv) và A/AAAA thành công?
  | NO -> sửa hostname/resolver/private DNS
  v YES
TCP tới target:port từ runtime thành công?
  | NO -> route/firewall/Atlas IP access list/bindIp
  v YES
TLS handshake/certificate validation thành công?
  | NO -> TLS mode, CA chain, SAN, expiry, SNI, JDK
  v YES
MongoDB hello/SDAM thấy topology phù hợp?
  | NO -> replicaSet/advertised hostnames/primary/election
  v YES
Authentication thành công?
  | NO -> user/password/authSource/mechanism/X.509
  v YES
Pool checkout và command hoạt động?
  | NO -> pool saturation, timeouts, server overload
  v YES
Ping thành công nhưng nghiệp vụ lỗi?
  -> authorization, query indexes, read/write concern,
     schema/validation, session/transactions
```

**Một sơ đồ không thay điều tra ngược:** lỗi ngoài cùng có thể bọc failure sâu hơn. Ví dụ `MongoTimeoutException` vẫn có thể có TLS handshake error trong cause chain.

---

## 25. Lab 1 — DNS/hostname sai

Mục tiêu: nhìn lỗi hostname khác lỗi TCP.

### Chuẩn bị

Dùng tên thuộc reserved `.invalid`, không phải hệ thống thực:

```bash
mongosh 'mongodb://db-does-not-exist.invalid:27017/?serverSelectionTimeoutMS=3000'
```

Kỳ vọng sau khi driver thử và timeout, thông báo có thể chứa DNS failure/`ENOTFOUND`/`getaddrinfo` tùy tool/version/OS.

### So với TCP refused

Nếu có MongoDB lab trên `127.0.0.1:27018`:

```bash
mongosh 'mongodb://127.0.0.1:27019/?serverSelectionTimeoutMS=3000'
```

Giả sử port 27019 không có listener, lỗi thường chứa `ECONNREFUSED`/`Connection refused`.

**Kết luận:** DNS failure xảy ra trước TCP, còn TCP refused nghĩa host/IP được xử lý nhưng port không nhận kết nối.

---

## 26. Lab 2 — TCP và port trên MongoDB local

Nếu đã tạo container lab ở mục 21:

```bash
mongosh 'mongodb://127.0.0.1:27018/?directConnection=true'
```

Windows:

```powershell
Test-NetConnection -ComputerName 127.0.0.1 -Port 27018
Test-NetConnection -ComputerName 127.0.0.1 -Port 27019
```

Linux/macOS:

```bash
nc -vz 127.0.0.1 27018
nc -vz 127.0.0.1 27019
```

Kỳ vọng 27018 reachable và 27019 không có listener, nếu không có service khác sử dụng port 27019.

### Dừng lab

```bash
docker stop mongo-connect-lab
```

Container chạy với `--rm` nên sẽ được xóa khi dừng. Chỉ thao tác trên container do chính lab tạo, không stop MongoDB production.

---

## 27. Lab 3 — TLS mismatch có chủ đích trong local

MongoDB Docker lab mặc định trong ví dụ không bật TLS. Thử:

```bash
mongosh 'mongodb://127.0.0.1:27018/?directConnection=true&tls=true&serverSelectionTimeoutMS=3000'
```

Kỳ vọng handshake không thành công vì client yêu cầu TLS còn server lab không có TLS. **Không** dùng thao tác này trên production để đoán cấu hình.

So với:

```bash
mongosh 'mongodb://127.0.0.1:27018/?directConnection=true&tls=false&serverSelectionTimeoutMS=3000'
```

Trên local lab không TLS, trường hợp thứ hai có thể vào được.

**Bài học:** TLS mode phải khớp hai đầu. Với Atlas/production, **không hạ TLS=false để chữa lỗi**; sửa CA/certificate/TLS compatibility đúng.

---

## 28. Lab 4 — Wrong topology/replica set name

Mục tiêu: thấy network reachable nhưng driver không chọn được server phù hợp.

Nếu local lab chỉ là standalone:

```bash
mongosh 'mongodb://127.0.0.1:27018/?replicaSet=wrongSet&serverSelectionTimeoutMS=3000'
```

Vì bạn yêu cầu kết nối replica set tên `wrongSet` nhưng server chỉ là standalone, driver có thể không tìm được server thỏa topology và báo selection timeout hoặc lỗi topology tương ứng.

So:

```bash
mongosh 'mongodb://127.0.0.1:27018/?directConnection=true&serverSelectionTimeoutMS=3000'
```

Lệnh thứ hai kết nối trực tiếp tới standalone lab.

**Lưu ý:** trường hợp này không đại diện cho một production replica set đang mất primary; để chẩn đoán failover cần cluster status/`rs.status()` của replica set thật, không chủ động làm election trên production.

---

## 29. Lab 5 — Kiểm tra Java/Spring theo ba môi trường

Dùng cùng code Java `ping` ở mục 16, lần lượt thử:

1. **Local:** `mongodb://127.0.0.1:27018/?directConnection=true`.
2. **Wrong hostname:** `mongodb://db-does-not-exist.invalid:27017/?serverSelectionTimeoutMS=3000`.
3. **Wrong port:** `mongodb://127.0.0.1:27019/?serverSelectionTimeoutMS=3000`.
4. **TLS mismatch local:** local lab URI có `tls=true`.
5. **Atlas development cluster** đã được cấp quyền: URI lấy từ Atlas Connect modal, secrets injection, không log password.

Ghi trong bảng:

| Case | DNS | TCP | TLS | SDAM | Ping | Exception/cause |
| --- | --- | --- | --- | --- | --- | --- |
| Local đúng | ... | ... | ... | ... | ... | ... |
| Hostname invalid | ... | ... | ... | ... | ... | ... |
| Port đóng | ... | ... | ... | ... | ... | ... |
| TLS mismatch | ... | ... | ... | ... | ... | ... |
| Atlas dev | ... | ... | ... | ... | ... | ... |

**Không cần mọi exception string giống hệt trên mọi driver version**. Điều quan trọng là phân biệt được **lớp hỏng** bằng evidence.

---

## 30. Observability và vận hành: tránh “blind retries”

### 30.1. Metrics cần có

| Metric | Mục đích |
| --- | --- |
| Server selection latency/errors | Không chọn được server/topology |
| TCP connect failures/timeouts | Network route/listener |
| TLS handshake errors | Cert/protocol/trust |
| DNS query failures | Resolver/SRV/TXT/A/AAAA |
| Connection pool checkout wait | Pool saturation |
| Current/open/checked-out connections | Client load |
| MongoDB CPU/disk/network | Server overload |
| Primary elections/replication lag | Replica set availability |
| App request p95/p99 | User-facing impact |
| Error/timeout/retry rate | Amplification và SLO |
| Egress NAT/source IP changes | Atlas access list drift |
| Certificate expiry/rotation events | TLS readiness |

### 30.2. Driver monitoring

MongoDB Java Driver có listeners cho:

- SDAM/cluster/server changes.
- Command started/succeeded/failed.
- Connection pool created/cleared/checkout failures.
- Heartbeat metrics/events.

Cần bật log levels và instrumentation phù hợp framework/version. Không in nguyên URI có credentials hoặc full command bodies chứa PII. Chỉ bật debug verbose trong thời gian hạn chế, có owner và retention.

### 30.3. Retry policy

- Phân biệt **transient failover** với cấu hình sai cố định.
- Dùng exponential backoff có jitter và giới hạn retry budget.
- Tránh nhiều tầng cùng retry (load balancer → API → SDK → driver).
- Với writes, tính đến ambiguous outcome/idempotency keys.
- Nếu server không reachable vì DNS sai, retry vô hạn chỉ tăng áp lực logs và làm triage khó hơn.
- Có circuit breaker/load shedding nếu ứng dụng cần bảo vệ upstream/downstream.

### 30.4. Tập trung vào phục hồi đúng nguyên nhân

Đừng tạo “fix” chỉ bằng đổi 30s thành 120s. Nếu vấn đề là TLS cert hết hạn, **120s chỉ khiến người dùng chờ lâu hơn**. Nếu lỗi là primary election 2–5s, timeout phù hợp cùng retry driver có thể giúp; vẫn cần theo dõi election frequency.

---

## 31. Những hiểu lầm cần tránh

| Nhận định sai | Thực tế |
| --- | --- |
| “Server selection timeout nghĩa database tắt” | Có thể DNS/TCP/TLS/selector/replica set |
| “DNS resolve A là đủ cho +srv” | Cần SRV, target A/AAAA, TXT khi áp dụng |
| “SRV có target nghĩa TCP thông” | Network còn phải kết nối target:port |
| “Ping thất bại là port đóng” | ICMP có thể bị chặn |
| “Test-NetConnection OK nghĩa MongoDB authenticated” | Chỉ kiểm tra TCP |
| “TLS OK nghĩa user/password đúng” | Authentication là lớp khác |
| “SSLHandshakeException chỉ cần tăng timeout” | Cần sửa CA/hostname/protocol |
| “Tắt tlsAllowInvalidHostnames là giải pháp an toàn” | Không; cần cert SAN đúng |
| “JDK luôn tin mọi CA mà OS tin” | JVM có truststore riêng |
| “URI SRV có thể thêm :27017” | SRV URI không chấp nhận port trực tiếp |
| “MongoDB SRV default TLS=false” | SRV thường bật TLS mặc định |
| “Không thấy primary thì đọc/ghi secondary như bình thường” | Writes cần primary, reads có consistency constraints |
| “directConnection=true sửa production failover” | Nó hạn chế topology discovery |
| “MongoClient tạo được nghĩa ping chắc được” | Driver có thể lazy/discover asynchronously |
| “Pool timeout là DNS timeout” | Pool checkout là lớp khác |
| “maxPoolSize=100 là toàn cluster chỉ có 100 sockets” | Pool per server, per MongoClient |
| “Tăng maxPoolSize vô hạn là fix” | Có thể gây saturation |
| “Compass trên laptop OK nghĩa pod OK” | Khác DNS/network/egress/TLS runtime |
| “Private endpoint có thể dùng public DNS bất kỳ” | Có thể cần split-horizon DNS |
| “Tắt TLS để debug Atlas cũng được” | Không phù hợp bảo mật |
| “AuthenticationFailed nghĩa chưa TCP tới được” | Thường TLS/connection đã qua và auth bị từ chối |
| “Một timeout value giải thích mọi timeout” | Các deadline có scope khác |
| “Đổi password mà chưa đọc root cause” | Không xử lý DNS/TCP/TLS |
| “Mọi node advertised đều reachable nếu seed reachable” | Hostname nội bộ có thể unreachable |
| “Java cùng URI với mongosh chắc TLS giống nhau” | JVM truststore khác OS/Node |
| “Log raw connection string không sao” | Có thể lộ username/password |

---

## 32. Bài tập thực hành

### Bài 1 — Chuỗi kết nối

Sắp xếp: TLS, DNS, authentication, TCP, SDAM, pool checkout.

**Đáp án:** URI parse → DNS → TCP → TLS → SDAM/hello → authentication → pool checkout/command, với một số hoạt động monitoring/pooling chồng lấp theo driver.

### Bài 2 — Server selection

`MongoTimeoutException` luôn nghĩa MongoDB Server đang tắt không?

**Đáp án:** Không; driver không chọn được server phù hợp trong giới hạn.

### Bài 3 — Root cause

Stack trace có `MongoTimeoutException` và nested `UnknownHostException`. Bạn kiểm tra lớp nào trước?

### Bài 4 — DNS SRV

Với `mongodb+srv://cluster0.example.mongodb.net/`, tên SRV record nào được query?

**Đáp án:** `_mongodb._tcp.cluster0.example.mongodb.net`.

### Bài 5 — SRV URI

Có hợp lệ không: `mongodb+srv://cluster0.example.mongodb.net:27017/`?

**Đáp án:** Không; SRV URI chỉ có một hostname, không chỉ định port trực tiếp.

### Bài 6 — TXT

TXT record có thể cung cấp loại thông tin gì? Vì sao phải kiểm tra cả SRV và TXT trên URI SRV?

### Bài 7 — DNS NXDOMAIN

Nếu `Resolve-DnsName` trả NXDOMAIN, vì sao tăng `connectTimeoutMS` không giải quyết?

### Bài 8 — DNS SERVFAIL

Kể ba nguyên nhân từ resolver, forwarding hoặc outbound DNS policy.

### Bài 9 — Split DNS

Laptop resolve public IP, pod resolve private IP. Điều đó có luôn là lỗi không?

**Đáp án:** Không; private endpoint có thể dùng split-horizon DNS.

### Bài 10 — TCP refused

`Connection refused` có chứng minh username/password sai không?

**Đáp án:** Không; TCP bị từ chối trước authentication.

### Bài 11 — TCP timeout

Phân biệt firewall drop với firewall reject qua biểu hiện kết nối.

### Bài 12 — Ping

Tại sao `ping` ICMP fail không đủ kết luận port TCP 27017 bị chặn?

### Bài 13 — Windows

Viết lệnh PowerShell kiểm tra TCP tới `db1.example.net:27017`.

**Đáp án:** `Test-NetConnection -ComputerName db1.example.net -Port 27017`.

### Bài 14 — Linux

Viết lệnh `nc` kiểm tra TCP tới hostname và port thật từ SRV record.

### Bài 15 — Atlas allow-list

Tại sao allow-list IP laptop không đảm bảo app pod kết nối được?

### Bài 16 — Private Endpoint

SRV có bản ghi nhưng target A trả public IP trong một VPC chỉ có private route. Bạn kiểm tra gì?

### Bài 17 — TLS defaults

Phân biệt TLS default của standard `mongodb://` và SRV `mongodb+srv://`.

**Đáp án:** Standard thường tắt TLS mặc định; SRV bật TLS mặc định.

### Bài 18 — PKIX

`PKIX path building failed` gợi ý vấn đề gì và hướng xử lý an toàn?

### Bài 19 — SAN

URI dùng IP nhưng server certificate chỉ có DNS SAN. Cần sửa gì?

### Bài 20 — mTLS

Phân biệt truststore và keystore trong Java.

### Bài 21 — JDK

Compass kết nối được, Java fail TLS. Vì sao cần kiểm tra JDK truststore và TLS versions?

### Bài 22 — Security

Vì sao không đặt `tlsAllowInvalidHostnames=true` để xử lý hostname mismatch trên production?

### Bài 23 — Server selection vs connect

Giải thích hai options `serverSelectionTimeoutMS` và `connectTimeoutMS`.

### Bài 24 — Pool

Pool đã có 100/100 connections checked-out, thêm request phải làm gì? Dấu hiệu khác server selection timeout là gì?

### Bài 25 — CSOT

`timeoutMS`/CSOT là deadline của bước nào? Vì sao cần xác minh driver version?

### Bài 26 — Replica set

Driver thấy một connected SECONDARY nhưng cần PRIMARY. Vì sao có thể timeout?

### Bài 27 — Read preference

Chuyển primary sang secondaryPreferred có thể giúp một read khi không có primary; rủi ro consistency là gì?

### Bài 28 — `replicaSet`

URI khai báo `replicaSet=rsWrong`, server báo `rs0`. Điều gì cần sửa?

### Bài 29 — Advertised hostname

Seed reachable nhưng `hello` trả internal names mà client không resolve được. Bạn xử lý ở lớp nào?

### Bài 30 — directConnection

Dùng `directConnection=true` trong SSH tunnel có ích gì? Vì sao không là giải pháp lâu dài cho high availability?

### Bài 31 — Lazy connection

Tại sao tạo `MongoClient` thành công chưa chứng minh đã kết nối? Lệnh nào xác minh?

**Đáp án:** Thực thi `ping` command và kiểm tra kết quả.

### Bài 32 — Authentication

`AuthenticationFailed`, error code 18; vì sao đây thường không phải DNS failure?

### Bài 33 — Password URI

Password có `@` và `:`. Cần mã hóa gì khi đặt trong URI? Có cần mã hóa nếu nhập vào password prompt không?

### Bài 34 — Spring Data

Một Spring Boot app start OK nhưng request đầu tiên mới timeout. Vì sao có thể xảy ra?

### Bài 35 — Docker

Trong container, `localhost` là host laptop hay chính container?

**Đáp án:** Chính container/pod network namespace.

### Bài 36 — Kubernetes

Hãy liệt kê việc kiểm tra CoreDNS, NetworkPolicy, NAT egress và private endpoint trước khi kết luận Atlas hỏng.

### Bài 37 — Connection churn

Vì sao tạo một `MongoClient` cho mỗi HTTP request dễ gây connection storm?

### Bài 38 — Timeout budget

API gateway timeout sau 15s, nhưng driver serverSelectionTimeoutMS=120000. Những rủi ro gì?

### Bài 39 — Case study

App trên EKS bị `MongoTimeoutException` sau deploy, Compass laptop OK, DNS SRV/A pass, TCP trong pod fail. Hãy lập investigation plan và sửa đúng lớp.

### Bài 40 — Case study tổng hợp

Sau certificate rotation, Java pods fail PKIX, mongosh trên bastion OK. Lập checklist chứng minh JDK truststore/CA chain, kiểm tra thời gian và rollout an toàn.

---

## 33. Checklist production

### URI và credentials

- [ ] Scheme `mongodb`/`mongodb+srv` đúng.
- [ ] Hostname/port lấy từ deployment/Atlas URI chính thức.
- [ ] `replicaSet`, `authSource`, read preference đúng.
- [ ] Password URI percent-encoded đúng, không double-encode.
- [ ] Secrets không nằm trong tickets, command history hay logs.
- [ ] Có quy trình rotation user/cert và rollback.

### DNS và network

- [ ] SRV/TXT/A/AAAA kiểm tra từ runtime ứng dụng.
- [ ] Resolver/CoreDNS/VPC DNS/Private Endpoint được kiểm tra đúng.
- [ ] TCP đến mọi target cần thiết, đúng host/port.
- [ ] Atlas IP access list khớp egress IP thực.
- [ ] Không dùng ping làm phép thử TCP duy nhất.
- [ ] Self-managed `bindIp`/listener/firewall đúng.
- [ ] Replica set advertised member hostnames reachable.
- [ ] Không sửa private DNS sang public resolver tùy tiện.

### TLS và authentication

- [ ] TLS mode khớp server và policy.
- [ ] CA chain trusted, SAN khớp hostname, certificate chưa hết hạn.
- [ ] JDK truststore/keystore đúng, clock/NTP chính xác.
- [ ] Không bật invalid hostname/certificate flags trên production.
- [ ] Client cert/X.509 đúng nếu mTLS được yêu cầu.
- [ ] MongoDB database user, authSource, SCRAM/X.509 mechanism đúng.
- [ ] TLS debug logs được bảo vệ và tắt sau điều tra.

### SDAM, pool và timeouts

- [ ] Có primary/secondary phù hợp operation/read preference.
- [ ] Cluster description và nested exceptions được giữ lại sau redaction.
- [ ] Thời gian chờ được thiết kế theo SLO.
- [ ] Không tăng toàn bộ timeouts để che lỗi.
- [ ] Có MongoClient singleton và pool sizing hợp lý.
- [ ] Có monitor checkout wait, selection failures, retries.
- [ ] Health/readiness probe thực hiện operation có giới hạn hợp lý.
- [ ] Có incident runbook failover và recovery.

### Post-incident

- [ ] Xác định root cause theo lớp cụ thể.
- [ ] Xác minh DNS → TCP → TLS → SDAM → auth → `ping`.
- [ ] Test từ tất cả AZ/regions hoặc runtime types bị ảnh hưởng.
- [ ] Kiểm tra app p95/p99, error/retry rates và DB cluster health.
- [ ] Ghi timeline, owner, changes, rollback và actions phòng ngừa.
- [ ] Không đưa dữ liệu nhạy cảm vào postmortem.

---

## 34. Tổng kết

Lỗi kết nối MongoDB cần được phân tích như một **chuỗi phụ thuộc**, không phải một lỗi duy nhất:

1. **URI** phải đúng scheme, hostname, port, credentials và options.
2. **DNS**: với `mongodb+srv`, phải kiểm tra SRV/TXT và A/AAAA của từng target; với Private Endpoint, phải kiểm tra private DNS từ đúng runtime.
3. **TCP**: kiểm tra port thực bằng `Test-NetConnection`/`nc`, xác định firewall, routes, egress IP và Atlas allow-list.
4. **TLS**: kiểm tra certificate chain, Java truststore, SAN, expiry, SNI, protocol và mTLS; không vô hiệu hóa verification trên production.
5. **SDAM/server selection**: `MongoTimeoutException` cho biết driver **không tìm được server đáp ứng selector** trong budget; root cause có thể DNS/TCP/TLS hoặc replica set không có primary phù hợp.
6. **Authentication**: sau network/TLS, kiểm tra user/password/`authSource` và cơ chế xác thực.
7. **Connection pool** và operation timeouts là lớp khác với server selection; async/threads/pool đều có giới hạn.
8. **Kiểm chứng kết nối thật bằng `ping`**; tạo `MongoClient` thành công chưa đủ.
9. **Vận hành production** cần giữ source of truth là error chain + cluster description + DNS/TCP/TLS evidence + Atlas/server metrics, thay vì chỉ tăng timeout.

Câu hỏi vận hành tốt nhất là:

> **“Lỗi xuất hiện ở bước nào của DNS → TCP → TLS → SDAM → authentication → pool/command, và phép đo nào chứng minh điều đó?”**

### Tài liệu MongoDB chính thức

- [MongoDB — Troubleshoot Server Selection Timeout](https://www.mongodb.com/docs/manual/troubleshooting/server-selection-timeout/) — các nguyên nhân DNS, network, TLS và phương pháp xử lý.
- [MongoDB Atlas — Troubleshoot Connection Issues](https://www.mongodb.com/docs/atlas/troubleshoot-connection/) — IP access list, SRV records, TLS, ports, auth.
- [MongoDB Atlas — Troubleshoot Private Endpoint Connections](https://www.mongodb.com/docs/atlas/troubleshoot-private-endpoints/) — private DNS, endpoint status và routing.
- [MongoDB — Connection String Formats](https://www.mongodb.com/docs/manual/reference/connection-string-formats/) — standard/SRV syntax, seedlist.
- [MongoDB — Connection String Options](https://www.mongodb.com/docs/manual/reference/connection-string-options/) — TLS, authentication, read preference và timeouts.
- [MongoDB Java Sync Driver — Connection Troubleshooting](https://www.mongodb.com/docs/drivers/java/sync/current/connection/connection-troubleshooting/) — MongoTimeoutException, cluster description, TLS diagnostics.
- [MongoDB Java Sync Driver — Cluster Settings](https://www.mongodb.com/docs/drivers/java/sync/current/connection/specify-connection-options/cluster-settings/) — `serverSelectionTimeoutMS`, `localThresholdMS`.
- [MongoDB Java Sync Driver — Socket Settings](https://www.mongodb.com/docs/drivers/java/sync/current/connection/specify-connection-options/socket-settings/) — `connectTimeoutMS`, `socketTimeoutMS`.
- [MongoDB Java Sync Driver — Connection Pools](https://www.mongodb.com/docs/drivers/java/sync/current/connection/specify-connection-options/connection-pools/) — maxPoolSize, maxConnecting và pool wait.
- [MongoDB Java Sync Driver — Client-Side Operation Timeout](https://www.mongodb.com/docs/drivers/java/sync/current/connection/specify-connection-options/csot/) — CSOT/`timeoutMS`, experimental note.
- [MongoDB Java Sync Driver — TLS/SSL](https://www.mongodb.com/docs/drivers/java/sync/current/security/tls/) — truststore, keystore, SAN và certificate verification.
- [MongoDB Manual — Replication](https://www.mongodb.com/docs/manual/replication/) — replica set, roles, failover.
- [MongoDB Manual — Read Preference](https://www.mongodb.com/docs/manual/core/read-preference/) — server selector semantics.
- [MongoDB Java Driver — Monitoring](https://www.mongodb.com/docs/drivers/java/sync/current/logging-monitoring/monitoring/) — command/pool events.
- [Spring Boot — MongoDB](https://docs.spring.io/spring-boot/reference/data/nosql.html) — MongoDB autoconfiguration.
- [Spring Boot Actuator — Health](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html) — liveness/readiness/health groups.
