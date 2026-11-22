# Phân giải tên, mạng container, firewall và kiểm tra đường kết nối

## 1. Bài toán: một địa chỉ Cassandra có thể đúng ở nơi này và sai ở nơi khác

Apache Cassandra là cơ sở dữ liệu **wide-column phân tán**. Ứng dụng Java hoặc `cqlsh` gửi CQL đến một node qua **native binary protocol**, thường ở cổng TCP **9042**. Node nhận request đóng vai trò **coordinator** rồi liên lạc với các replica theo partition key, replication và consistency của thao tác. Vì vậy, đường kết nối cần hoạt động ở cả **client → coordinator** và, khi cần, **node → node**.

Trong thực hành, lỗi thường bắt đầu từ một tình huống tưởng đơn giản:

- Chạy `cqlsh 127.0.0.1 9042` **bên trong container Cassandra** thì thành công, nhưng từ máy host lại báo `Connection refused`.
- Ứng dụng Java chạy trên host kết nối qua `localhost:9042`, nhưng khi chạy Java trong container khác thì kết nối thất bại.
- Java Driver kết nối được một contact point, sau đó lại báo lỗi với các peer có IP private không truy cập được từ ứng dụng.
- DNS giải quyết được hostname, nhưng firewall hoặc TLS khiến native handshake không thành công.

Chìa khóa là luôn xác định **tiến trình client đang chạy ở đâu**, tên host được giải quyết thành IP nào **trong chính môi trường đó**, và TCP/TLS/CQL có đi qua được từng lớp hay không.

Bài học thuộc chương **Công cụ và kết nối** của module `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA`. Nó giúp chuẩn bị đường kết nối ổn định để thực hành CQL, thiết kế bảng theo truy vấn, kiểm soát nhất quán đọc/ghi, quan sát replication/repair và truy cập Cassandra từ Java.

**Mục tiêu:**

1. Phân biệt **hostname**, **DNS**, `localhost`, IP của container, host OS và endpoint công bố của Cassandra.
2. Chọn đúng địa chỉ và cổng khi client chạy trên host, trong Docker Compose, trong Kubernetes hoặc ngoài mạng cluster.
3. Kiểm tra theo thứ tự **phân giải tên → TCP → TLS → native protocol → auth → topology → CQL**.
4. Phân biệt firewall cho **native 9042**, **internode 7000**, JMX và các cổng TLS tùy cấu hình.
5. Chẩn đoán lỗi Java Driver kết nối contact point thành công nhưng không truy cập được các node được khám phá.

## 2. Bản đồ đường kết nối

~~~mermaid
flowchart LR
    subgraph HOST["Máy host"]
        H["Ứng dụng Java trên host"]
        P["Cổng host 127.0.0.1:9042"]
    end
    subgraph NET["Mạng Docker Compose"]
        A["Ứng dụng Java trong container app"]
        C["Container cassandra / native 9042"]
    end
    H -->|"TCP đến port published"| P
    P -->|"Docker port forwarding"| C
    A -->|"DNS service: cassandra:9042"| C
    C -.->|"Internode 7000 khi có peer"| R["Node Cassandra khác"]
~~~

Sơ đồ này minh họa **một Cassandra container** và có thể mở rộng thêm peer. Ứng dụng trên **host** và ứng dụng **trong container** nhìn thấy những không gian mạng khác nhau. Không gian mạng của client quyết định ý nghĩa của `localhost`.

### 2.1. Các địa chỉ dễ nhầm

| Địa chỉ hoặc tên | Có nghĩa gì? | Dùng từ đâu? |
| --- | --- | --- |
| `127.0.0.1` / `localhost` | Loopback của **chính network namespace nơi client chạy**. | Host đến dịch vụ publish trên host; container chỉ đến chính nó; các container **trong cùng một Pod Kubernetes** có thể dùng chung loopback. |
| `cassandra` | Tên service được Docker Compose DNS cung cấp trong mạng Compose. | Container cùng mạng Compose; thường **không** phân giải trực tiếp từ host. |
| IP container như `172.18.0.5` | IP trên mạng bridge/container, có thể thay đổi khi tái tạo. | Các container/mạng được định tuyến tương ứng; không nên hard-code trong app. |
| `host.docker.internal` | Tên đặc biệt thường trỏ từ container về host trên **Docker Desktop**. | Container cần gọi dịch vụ trên host; trên Linux thường cần cấu hình phù hợp. |
| `db.example.internal` | DNS name do tổ chức vận hành, có thể trỏ đến host, load balancer hoặc endpoint cụ thể. | Chỉ những máy có DNS và đường mạng tới địa chỉ được phân giải. |
| `cassandra.default.svc.cluster.local` | Tên Service DNS minh họa trong Kubernetes. | Thường từ Pod trong cluster; không tự có nghĩa ở Internet hoặc máy cá nhân. |

**Không có một hostname đúng cho mọi client.** Hãy kiểm tra nơi **Java process** hoặc **cqlsh process** chạy thay vì lấy địa chỉ làm việc trên terminal khác và giả định dùng lại được.

### 2.2. Native client và internode là hai đường khác nhau

| Cổng thường gặp | Giao thức/mục đích | Phía nào cần mở đường? |
| --- | --- | --- |
| **9042/TCP** | Cassandra CQL native transport (có thể dùng TLS ngay trên cổng này) | Java Driver/cqlsh → các node có native endpoint cần truy cập |
| **7000/TCP** | Trao đổi internode, gossip, replica request, streaming theo cấu hình | Node Cassandra ↔ node Cassandra |
| **7001/TCP** | Cổng internode TLS kiểu cũ nếu cấu hình phiên bản dùng | Chỉ các node khi thực sự dùng cổng này |
| **7199/TCP** | JMX phục vụ `nodetool`/quản trị | Chỉ máy quản trị được phép |
| **9142/TCP** | Native TLS cổng phụ nếu phiên bản/cấu hình hỗ trợ | Chỉ khi node đã được cấu hình bật; không phải mặc định |

Số cổng có thể thay đổi trong `cassandra.yaml`. Một kết nối TCP đến `7000` không cho phép gửi CQL; ngược lại, `9042` hoạt động không chứng minh gossip, bootstrap hay repair qua internode đang hoạt động. Trong Cassandra 5.0, cổng native TLS riêng `native_transport_port_ssl` bị đánh dấu deprecated; cần xem tài liệu đúng phiên bản.

## 3. Phân giải tên: kiểm tra từ chính nơi ứng dụng chạy

### 3.1. Những lớp có thể tham gia phân giải tên

Một hostname có thể được ánh xạ qua file `hosts`, DNS nội bộ, DNS của Compose/Kubernetes, resolver của hệ điều hành hoặc cơ chế riêng của môi trường triển khai. Mỗi container/Pod có thể có `/etc/hosts` và `/etc/resolv.conf` khác host.

Một lệnh thành công từ **máy cá nhân** không chứng minh cùng hostname cũng giải quyết đúng khi chạy từ **container hoặc server production**. Ngược lại, tên service `cassandra` có thể chỉ tồn tại trong mạng Docker Compose.

Các bước kiểm tra phổ biến trên Linux:

~~~bash
# Kiểm tra tên phân giải thành IP nào, có thể bao gồm /etc/hosts.
getent hosts db.example.internal

# Truy vấn DNS khi có công cụ dig.
dig db.example.internal

# Phân giải tên service từ bên trong một container có hỗ trợ getent.
getent hosts cassandra
~~~

Trên Windows PowerShell:

~~~powershell
Resolve-DnsName db.example.internal
~~~

**Phải chạy tại đúng nguồn phát request.** Ví dụ `getent hosts cassandra` trên host có thể không tìm thấy tên, nhưng trong container cùng Compose network lại trả về IP của Cassandra. Ngoài ra, `getent`/`dig` không có sẵn trong mọi image tối giản; có thể dùng container chẩn đoán cùng network khi cần.

### 3.2. DNS thành công chưa đủ

Giả sử `db.example.internal` phân giải ra `10.30.5.20`. Để kết luận ứng dụng có thể kết nối Cassandra, vẫn phải trả lời:

1. Máy client có đường **routing** đến `10.30.5.20` không?
2. Cổng `9042/TCP` có listener và firewall cho phép không?
3. Cổng đó có yêu cầu **TLS** không, và client có cấu hình tương ứng không?
4. Native protocol/driver có tương thích và thông tin auth đúng không?
5. Khi driver khám phá peer khác, **những peer đó** có địa chỉ reachable từ client không?

Lệnh `ping` chỉ kiểm tra ICMP nếu được cho phép; nhiều môi trường chặn ICMP nhưng TCP vẫn hoạt động. Không dùng thành công/thất bại của `ping` làm kết luận cuối cùng cho native CQL.

## 4. Docker Compose: host port và DNS service

### 4.1. Một Cassandra container cho môi trường học tập

Ví dụ file `compose.yaml` **minh họa** dưới đây dùng một node Cassandra để thử kết nối. Chọn image/tag được dự án cho phép khi triển khai; `cassandra:4.1` ở đây là một phiên bản cụ thể phục vụ ví dụ.

~~~yaml
services:
  cassandra:
    image: cassandra:4.1
    environment:
      CASSANDRA_CLUSTER_NAME: local-network-lab
    ports:
      # Chỉ publish trên loopback của host cho lab.
      - "127.0.0.1:9042:9042"
~~~

Khởi động và kiểm tra:

~~~bash
docker compose up -d
docker compose ps
docker compose port cassandra 9042
docker compose logs --tail=100 cassandra

# Chạy cqlsh ngay trong container Cassandra.
docker compose exec cassandra cqlsh 127.0.0.1 9042
~~~

Cassandra có thể đang khởi tạo schema và native transport khi container đã xuất hiện trong `docker compose ps`; cần xác nhận nó **sẵn sàng nhận CQL** rồi mới đánh giá lỗi. Lệnh `docker compose exec cassandra cqlsh ...` kiểm tra **từ container Cassandra**, không kiểm tra đường từ host.

Do đã publish `127.0.0.1:9042:9042`, từ **terminal trên host**:

~~~bash
cqlsh 127.0.0.1 9042
~~~

Trên Windows host có thể kiểm tra TCP:

~~~powershell
Test-NetConnection -ComputerName 127.0.0.1 -Port 9042
~~~

Nếu không có `cqlsh` ở host, kiểm tra TCP trước, rồi dùng một client được cài trên host hoặc một container chẩn đoán có tuyến phù hợp. `Test-NetConnection` chỉ thử TCP, chưa xác nhận native protocol hay authentication.

### 4.2. Khi ứng dụng Java cũng nằm trong Docker Compose

Nếu có thêm service `app` trên **cùng Compose network**, Java phải gọi tới `cassandra:9042`:

~~~text
Client chạy trên host:
    127.0.0.1:9042  -> Docker port published -> container Cassandra:9042

Client chạy trong container app:
    cassandra:9042  -> DNS của Compose -> container Cassandra:9042

Client app-container dùng 127.0.0.1:9042:
    127.0.0.1 là CHÍNH container app -> thường Connection refused
~~~

Docker Compose cung cấp tên service và mạng mặc định cho các service trong cùng project, trừ khi cấu hình mạng được thay đổi. Thông thường **không cần `ports`** để container `app` gọi `cassandra:9042` trong cùng network. `ports` dùng để **publish cổng ra host**; trường `expose` (nếu có) cũng không tự publish ra host.

Khi tái tạo container Cassandra, IP nội bộ có thể đổi. Dùng **tên service** để Docker DNS phân giải endpoint hiện tại, tránh ghi cứng địa chỉ IP bridge.

### 4.3. Cổng publish và nguy cơ mở quá rộng

~~~yaml
# Chỉ ví dụ về bind của port trên host:
ports:
  - "127.0.0.1:9042:9042"  # chỉ loopback host, phù hợp lab local
~~~

Khác với:

~~~yaml
ports:
  - "9042:9042"  # thường publish trên các interface host
~~~

Giá trị dạng `9042:9042` thường có thể làm port tiếp cận được từ bên ngoài host tùy Docker, hệ điều hành và firewall. Không publish Cassandra native transport ra mạng không tin cậy; khi cần truy cập từ xa, dùng mạng riêng/VPN, firewall giới hạn nguồn, TLS và auth phù hợp.

Một container **không bắt đầu hỗ trợ kết nối từ host chỉ vì tiến trình Cassandra trong container mở 9042**: host cần đường tới container (ví dụ port mapping). Đồng thời, publish port không sửa được lỗi bind/advertise nếu chính Cassandra chưa mở native listener.

### 4.4. Nếu ứng dụng trong container cần gọi dịch vụ Cassandra trên host

Đây là trường hợp **đảo chiều** so với Compose ở trên. Trên Docker Desktop, hostname `host.docker.internal` thường giúp container tìm host:

~~~text
Container app -> host.docker.internal:9042 -> Cassandra trên host
~~~

Trên Docker Engine Linux, tên này không mặc định hoạt động trong mọi cấu hình; có thể cần cấu hình host gateway/network theo tài liệu Docker. Ngoài ra, Cassandra trên host phải bind ở interface có thể nhận kết nối từ container; nếu chỉ nghe `127.0.0.1` trên host, container thường không thể đến qua host gateway. Đây không phải cách cần dùng khi **Cassandra đã là service khác trong cùng Docker network**.

## 5. Môi trường Kubernetes: Pod, Service và DNS

Kubernetes bổ sung một lớp DNS/Service và có vài khác biệt với Docker Compose:

- Các container **trong cùng một Pod** chia sẻ network namespace và có thể gọi nhau bằng `localhost` khi service lắng nghe cổng tương ứng.
- Các **Pod khác nhau** có IP riêng. Một app Pod gọi `localhost:9042` sẽ trỏ tới **chính Pod đó**, không đến Cassandra Pod khác.
- Pod thường truy cập Service bằng tên như `cassandra` trong namespace hoặc FQDN `cassandra.default.svc.cluster.local`.
- Cassandra dạng cluster thường được triển khai bằng **StatefulSet/operator, DNS ổn định, và đôi khi headless Service** để mỗi node có danh tính/endpoint riêng. Một ClusterIP/load balancer chung không bảo đảm Java Driver khám phá và kết nối được từng node mà Cassandra công bố.
- Từ bên ngoài Kubernetes, hostname `*.svc.cluster.local` và Pod IP thường không có DNS/route phù hợp. NodePort/LoadBalancer hay ingress TCP nếu được hỗ trợ phải đi kèm cấu hình native endpoint, topology, firewall và bảo mật chính xác.

Những lệnh chẩn đoán tham khảo dưới đây giả định namespace `dev` và có quyền đọc:

~~~bash
# Xem Pod IP, trạng thái, node Kubernetes.
kubectl get pods -n dev -o wide

# Xem Service, loại Service và port.
kubectl get svc -n dev

# EndpointSlices đằng sau Service cassandra (tên tùy deployment).
kubectl get endpointslice -n dev -l kubernetes.io/service-name=cassandra

# Kiểm tra NetworkPolicy có thể ảnh hưởng luồng TCP.
kubectl get networkpolicy -n dev

# Thử cqlsh ở Cassandra Pod nếu image có cqlsh.
kubectl exec -n dev cassandra-0 -- cqlsh 127.0.0.1 9042
~~~

Thay namespace, Pod và Service đúng với deployment. Nếu đang điều tra **app Pod không tới được Cassandra**, phép thử quan trọng phải chạy **từ app Pod hoặc một debug Pod có cùng chính sách mạng**. Kiểm tra tại Cassandra Pod chỉ cho biết native listener tại nguồn nội bộ của Cassandra.

NetworkPolicy có hiệu lực tùy plugin mạng (CNI) và chính sách thực tế; `kubectl get networkpolicy` trả về danh sách chưa tự chứng minh package đang bị chặn. Cần đối chiếu cả **ingress tại Cassandra**, **egress tại app**, cổng, labels và namespace selectors nếu có.

## 6. Cassandra bind/advertise: vì sao một contact point chưa đủ?

Cassandra có hai cặp địa chỉ khác nhau trong `cassandra.yaml`:

| Cấu hình | Giao tiếp | Ý nghĩa |
| --- | --- | --- |
| `listen_address` | Internode | IP/interface Cassandra bind cho node ↔ node. **Không dùng `0.0.0.0`.** |
| `broadcast_address` | Internode | Endpoint các node khác dùng để liên hệ node. |
| `rpc_address` | Client native | IP/interface Cassandra bind cho CQL native transport. Có thể `0.0.0.0` với cấu hình đi kèm hợp lệ. |
| `broadcast_rpc_address` | Client native | Endpoint driver khám phá và kết nối. Cần là địa chỉ **cụ thể, reachable** từ các client liên quan. |

Một trích đoạn cấu hình **khái niệm** cho node có IP client thật:

~~~yaml
start_native_transport: true
native_transport_port: 9042

# Có thể nghe trên mọi interface IPv4 của chính node/container.
rpc_address: 0.0.0.0

# IP ví dụ; deployment thật phải có endpoint route được tới node.
broadcast_rpc_address: 192.0.2.20
~~~

Địa chỉ `192.0.2.20` là IP dành cho **tài liệu minh họa**, không phải IP dùng để copy vào hệ thống thật. Nếu `rpc_address` là `0.0.0.0` thì `broadcast_rpc_address` phải khai báo địa chỉ cụ thể, không thể để `0.0.0.0`. **Không gán IP của host vào địa chỉ bind bên trong container** nếu container không sở hữu IP đó.

### 6.1. Trường hợp Java Driver phát hiện peer không truy cập được

Giả sử:

~~~text
Java chạy ngoài mạng container
  |
  | -> db-gateway.example.internal:9042       [TCP thành công]
  |
  | <- metadata: peer Cassandra = 172.18.0.5:9042
  |
  | -> 172.18.0.5:9042                       [timeout]
~~~

Java Driver có thể dùng **contact point** để khởi tạo, rồi khám phá topology và tạo kết nối đến các node khác. Nếu Cassandra công bố địa chỉ bridge/container không route được từ ngoài, một số request hoặc chính việc khám phá/khởi tạo session sẽ gặp lỗi.

Cách kiểm tra:

1. Xác định Java Driver đang chạy trong network namespace nào và log **địa chỉ peer thực tế** mà driver cố kết nối.
2. So sánh địa chỉ đó với `broadcast_rpc_address` và thông tin metadata cluster của node.
3. Kiểm tra DNS/TCP **từ máy Java tới từng native endpoint** mà driver có thể chọn.
4. Nếu dùng NAT, proxy, Kubernetes hay load balancer, sử dụng cơ chế **address translation/gateway hỗ trợ bởi driver/cluster**; thiết kế endpoint ổn định theo node.
5. Không giả định một port mapping của **một** node đủ cho cluster nhiều node hoặc nhiều datacenter.

**Đường internode riêng biệt:** các node Cassandra có thể dùng `listen_address`/`broadcast_address` và `storage_port` 7000 để gossip/streaming. Java Driver không gửi CQL tới 7000. Lỗi mạng internode có thể xuất hiện dưới dạng `Unavailable`, timeout đọc ghi hoặc bootstrap/repair lỗi dù native 9042 vẫn kết nối được.

## 7. Firewall: mở đúng đường, đúng nguồn và đích

Một đường mạng hoàn chỉnh gồm listener trên server, routing và các quy tắc cho phép. Trong nhiều môi trường, gói TCP còn phải đi qua **host firewall, cloud security group/ACL, container forwarding, Kubernetes NetworkPolicy** hoặc proxy.

| Luồng | Cổng điển hình | Phạm vi cho phép gợi ý | Nếu bị chặn |
| --- | --- | --- | --- |
| App/cqlsh → Cassandra native | 9042/TCP | Chỉ mạng ứng dụng được tin cậy; áp dụng TLS/auth | `Connection timed out` / refused / driver no node |
| Cassandra node ↔ node | 7000/TCP | Chỉ các node thuộc cluster và mạng internode | Gossip, replica request, streaming, bootstrap/repair lỗi |
| Internode TLS legacy | 7001/TCP nếu cấu hình dùng | Chỉ node liên quan | TLS internode không hoàn tất |
| Quản trị → JMX | 7199/TCP thường gặp | Chỉ nguồn quản trị được cấp phép | `nodetool` không kết nối tới JMX |
| App → native TLS port riêng | 9142/TCP nếu đã cấu hình | Chỉ app cần thiết | TLS native cổng phụ không hoạt động |

**Phân biệt các kiểu lỗi mạng:**

- `Connection refused` thường cho thấy **không có listener** tại IP/port hoặc thiết bị mạng chủ động từ chối (TCP RST/REJECT).
- `Connection timed out` thường có thể do **DROP/firewall, route, network partition** hoặc phía đích không phản hồi đúng hạn.
- `SSLHandshakeException` cho biết đã tới giai đoạn TLS nhưng thỏa thuận/chứng chỉ không thành công; không phải bằng chứng cổng chưa mở.
- `Unauthorized` trong CQL nghĩa là kết nối và xác thực đã đi đủ xa để server **từ chối quyền CQL**.
- `ReadTimeout`/`WriteTimeout` khi đã gửi CQL thường cần kiểm tra replica, consistency, network internode, tải, compaction hoặc server logs.

Không chẩn đoán bằng cách tắt firewall toàn hệ thống hoặc mở `7000`/`7199` ra Internet. Nên kiểm tra và điều chỉnh quy tắc có **nguồn/đích/cổng tối thiểu** theo chính sách môi trường.

## 8. Quy trình kiểm tra đường kết nối theo lớp

Một checklist cố định giúp không nhầm DNS với lỗi native protocol:

~~~mermaid
flowchart TD
    A["Xác định client chạy ở host/container/Pod nào"] --> B{"Tên đích phân giải đúng IP?"}
    B -->|"Không"| C["Kiểm tra DNS, hosts, network namespace"]
    B -->|"Có"| D{"TCP đến đúng IP:port được?"}
    D -->|"Không"| E["Kiểm tra listener, ports, route, firewall"]
    D -->|"Có"| F{"TLS nếu cần có khớp?"}
    F -->|"Không"| G["Kiểm tra TLS mode, CA, hostname, chứng chỉ"]
    F -->|"Có"| H{"Native handshake và auth thành công?"}
    H -->|"Không"| I["Kiểm tra cqlsh/driver, protocol, credentials"]
    H -->|"Có"| J{"Driver đến được các peer được khám phá?"}
    J -->|"Không"| K["Kiểm tra broadcast RPC, NAT, topology, local DC"]
    J -->|"Có"| L["Chạy CQL theo partition key và xem CL/replica"]
~~~

### 8.1. Bước 1: xác định đúng nguồn và đích

Ghi lại: client chạy trên **host**, container nào, Pod/namespace nào, hay một VM khác; hostname/IP và port đang kết nối; node có bật TLS/auth hay không. Nếu có nhiều endpoint, hãy ghi danh sách đầy đủ.

### 8.2. Bước 2: phân giải tên

~~~bash
# Linux trong môi trường client; tên có thể đến từ hosts hoặc DNS.
getent hosts db.example.internal
~~~

~~~powershell
# Windows host hoặc máy Windows chạy ứng dụng.
Resolve-DnsName db.example.internal
~~~

Nếu tên chỉ giải quyết được trong Docker Compose, hãy chạy thử **bên trong container ứng dụng**, không phải trên host.

### 8.3. Bước 3: kiểm tra TCP

~~~bash
# Linux/macOS: kiểm tra mở kết nối đến native port.
nc -vz db.example.internal 9042
~~~

~~~powershell
# Windows PowerShell: thành công khi TcpTestSucceeded=True.
Test-NetConnection -ComputerName db.example.internal -Port 9042
~~~

Chú ý: `nc` và `Test-NetConnection` chỉ kiểm tra **socket TCP**, không gửi CQL. Nếu thất bại, xác nhận dịch vụ Cassandra đã bật native transport và listener đúng IP:

~~~bash
# Thao tác trong môi trường Cassandra có quyền xem JMX.
nodetool statusbinary

# Trên Linux node/container khi có công cụ và quyền phù hợp:
ss -lnt
~~~

Với Docker, còn kiểm tra `docker compose ps` và `docker compose port cassandra 9042`. Với Kubernetes, kiểm tra Service, EndpointSlice, Pod readiness và NetworkPolicy.

### 8.4. Bước 4: xác minh TLS rồi native protocol

Nếu endpoint **được cấu hình TLS**, có thể thử handshake từ client:

~~~bash
openssl s_client -connect db.example.internal:9042 -servername db.example.internal
~~~

Lệnh này chỉ hợp lý nếu **port thực sự dùng TLS**; port native không TLS sẽ không trả handshake như mong đợi. Chứng chỉ hợp lệ đòi hỏi kiểm tra chuỗi CA, hostname/SAN và chính sách TLS của client; mở kết nối SSL thành công thôi chưa đủ.

Sau đó dùng **cqlsh thật**:

~~~bash
# Nếu server không yêu cầu TLS/auth (ví dụ lab local).
cqlsh db.example.internal 9042

# Nếu server yêu cầu TLS và username.
cqlsh db.example.internal 9042 --ssl -u student
~~~

Đừng ghi mật khẩu trực tiếp vào lịch sử lệnh. Nếu cqlsh chạy được nhưng Java không, cần so sánh **TLS config, credentials, native protocol version, local datacenter và các node Java Driver khám phá**.

Trong cqlsh:

~~~sql
SHOW HOST;
SHOW VERSION;

SELECT cluster_name, data_center, release_version
FROM system.local;

DESCRIBE KEYSPACES;
~~~

`system.local` cho biết cluster/datacenter của node đang nhận request. Tên datacenter này quan trọng với cấu hình `withLocalDatacenter` của Java Driver.

### 8.5. Bước 5: kiểm tra peer và đường internode

Trên node có quyền quản trị:

~~~bash
nodetool status
nodetool gossipinfo
nodetool netstats
~~~

Từ **node B**, thử TCP đến **địa chỉ broadcast internode của node A** (giả định dùng cổng 7000):

~~~bash
nc -vz 192.0.2.11 7000
~~~

`192.0.2.11` là địa chỉ minh họa. Thay bằng địa chỉ thật của peer. Đường node–node thường cần hoạt động theo hai chiều và nhất quán với TLS internode. `nodetool status` hiển thị trạng thái ring, nhưng không thay thế kiểm tra TCP/TLS chi tiết từ từng node hay log server.

## 9. Lab CQL: xác minh kết nối đã tới đúng cluster

Sau khi cqlsh vào được **cluster lab**, có thể tạo dữ liệu để kiểm chứng đầy đủ đường CQL. Ví dụ dưới đây dùng Cassandra **một node, RF = 1**:

~~~sql
CREATE KEYSPACE IF NOT EXISTS connection_path_lab
WITH replication = {
  'class': 'SimpleStrategy',
  'replication_factor': 1
};

CREATE TABLE IF NOT EXISTS connection_path_lab.events_by_device_day (
  device_id text,
  event_day date,
  event_time timestamp,
  event_id uuid,
  event_type text,
  PRIMARY KEY ((device_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);

INSERT INTO connection_path_lab.events_by_device_day
  (device_id, event_day, event_time, event_id, event_type)
VALUES ('sensor-01', '2026-11-21', '2026-11-21T01:00:00Z',
        11111111-1111-4111-8111-111111111111, 'temperature');

INSERT INTO connection_path_lab.events_by_device_day
  (device_id, event_day, event_time, event_id, event_type)
VALUES ('sensor-01', '2026-11-21', '2026-11-21T01:05:00Z',
        22222222-2222-4222-8222-222222222222, 'humidity');

SELECT event_time, event_type
FROM connection_path_lab.events_by_device_day
WHERE device_id = 'sensor-01'
  AND event_day = '2026-11-21'
LIMIT 10;
~~~

**Kỳ vọng:** hai row, row `01:05:00Z` trước `01:00:00Z`. Partition key `(device_id, event_day)` giúp định tuyến truy vấn tới partition tương ứng; thành công ở lớp TCP/TLS không thay thế thiết kế bảng theo truy vấn. Nếu gặp `Unavailable` hoặc timeout khi nâng consistency, phải xem thêm **replication factor, số replica đang phản hồi và mạng internode**.

`SimpleStrategy`/RF = 1 chỉ dùng cho lab đơn node. Với cluster nhiều node/datacenter, thường dùng `NetworkTopologyStrategy` và số replica phù hợp datacenter thực tế.

## 10. Java Driver: cấu hình hostname theo nơi ứng dụng chạy

Ví dụ sau sử dụng **Apache Cassandra Java Driver 4.x**. Tên host được lấy từ biến môi trường để cùng một chương trình có thể chạy trên host hoặc trong Compose network.

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

import java.net.InetSocketAddress;
import java.time.LocalDate;

public final class CassandraNetworkDemo {
    public static void main(String[] args) {
        // Host Java: CASSANDRA_HOST=127.0.0.1 nếu publish port local.
        // Container app: CASSANDRA_HOST=cassandra nếu cùng Compose network.
        String host = System.getenv().getOrDefault("CASSANDRA_HOST", "127.0.0.1");
        // Thay bằng data_center thực lấy từ system.local.
        String dc = System.getenv().getOrDefault("CASSANDRA_DC", "datacenter1");

        try (CqlSession session = CqlSession.builder()
                .addContactPoint(new InetSocketAddress(host, 9042))
                .withLocalDatacenter(dc)
                .build()) {

            PreparedStatement ps = session.prepare(
                "SELECT event_time, event_type " +
                "FROM connection_path_lab.events_by_device_day " +
                "WHERE device_id = ? AND event_day = ?");

            for (Row row : session.execute(
                    ps.bind("sensor-01", LocalDate.of(2026, 11, 21)))) {
                System.out.println(
                    row.getInstant("event_time") + " -> " +
                    row.getString("event_type"));
            }
        }
    }
}
~~~

**Ý nghĩa:**

- Ở **host**, nếu Compose publish `127.0.0.1:9042:9042`, chọn `CASSANDRA_HOST=127.0.0.1`.
- Ở **container app cùng Compose network**, chọn `CASSANDRA_HOST=cassandra`; không dùng `127.0.0.1` vì nó chỉ app container.
- Ở **máy ngoài cluster**, chọn DNS/IP native endpoint **có tuyến mạng thật** và cấu hình TLS/auth nếu server yêu cầu.
- Với **Kubernetes**, chọn endpoint được deployment/operator/driver hỗ trợ; xác nhận driver tới được các peer sau khi discovery.
- Giá trị `datacenter1` là ví dụ, không phải tên DC mặc định bất biến. Lấy tên thật từ `SELECT data_center FROM system.local;`.

`CqlSession` nên được tái sử dụng và có vòng đời dài trong service. Driver có thể kết nối các peer khác ngoài contact point, nên các địa chỉ do Cassandra công bố cũng phải phù hợp với mạng ứng dụng. Khi gặp `AllNodesFailedException` hoặc lỗi không có node khả dụng, xem **nguyên nhân theo từng node** trong exception/log, rồi so sánh hostname/IP, port, TLS, authentication và local DC.

Nếu môi trường cần TLS/auth, cấu hình SSL context và auth provider đúng theo driver (kèm quản lý secrets). Không bỏ qua xác minh chứng chỉ hoặc hard-code mật khẩu trong source để né lỗi.

## 11. Bảng đối chiếu lỗi thường gặp

| Hiện tượng | Nơi nên kiểm tra trước | Hướng xử lý |
| --- | --- | --- |
| Host `cqlsh 127.0.0.1 9042` lỗi, nhưng `docker compose exec cassandra cqlsh` thành công | Port mapping từ container ra host, host loopback và firewall | Xem `docker compose ps`, `docker compose port`, listener native và TCP từ host. |
| Java trong app-container dùng `localhost:9042` thất bại | Network namespace của app container | Dùng tên service `cassandra:9042` khi chung Compose network. |
| Host không phân giải `cassandra` nhưng container thì được | Docker Compose service DNS chỉ hoạt động trong network phù hợp | Host dùng published port hoặc DNS endpoint host; không dùng Compose service name ngoài network. |
| DNS resolve đúng nhưng TCP timeout | Route, firewall/ACL, security group, NAT hoặc listener không phản hồi | Kiểm tra TCP từ chính client tới IP:port; đối chiếu chính sách đường mạng. |
| TCP `9042` mở nhưng cqlsh không kết nối được | TLS, native protocol, auth, server readiness | So sánh cấu hình và log client/server; thử cqlsh với TLS/credentials đúng. |
| `SSLHandshakeException` | Cổng TLS, CA, truststore, SAN/hostname, protocol TLS | Kiểm tra endpoint và cấu hình mã hóa hai phía. |
| Java vào được contact point rồi lỗi các node khác | Peer native endpoints công bố không route được | Xem `broadcast_rpc_address`, metadata/driver log, NAT và khả năng TCP tới từng peer. |
| App Pod không tới Cassandra Service | Namespace/DNS Service, EndpointSlices, Pod readiness, NetworkPolicy | Kiểm tra DNS và TCP từ app Pod; so sánh ingress/egress policy và labels. |
| `nodetool status` thấy node down nhưng cqlsh một node vẫn chạy | Internode/gossip có sự cố | Kiểm tra đường 7000 giữa node, TLS internode, gossip/log và replication. |
| Truy vấn `SELECT` báo `Unauthorized` | CQL role/grants | Kiểm tra quyền keyspace/bảng; không phải lỗi DNS. |
| `ReadTimeout` / `WriteTimeout` sau khi kết nối thành công | Replica, CL, tải, network internode, compaction | Xem RF/consistency và logs/metrics; không suy ngay ra lỗi DNS hoặc 9042. |
| CQL bị từ chối vì điều kiện lọc không phù hợp | Thiết kế bảng/partition key | Kiểm tra `DESCRIBE TABLE`, chọn bảng theo truy vấn; không sửa bằng firewall. |

## 12. Bài tập tự thực hành

1. Vẽ đường đi khi `cqlsh` chạy trên **host** tới Cassandra trong Docker Compose có `ports: ["127.0.0.1:9042:9042"]`. Chỉ rõ cổng host và cổng trong container.
2. Khi Java chạy trong service `app` trên cùng Compose network, giải thích vì sao `127.0.0.1:9042` sai và `cassandra:9042` đúng.
3. Chạy `getent hosts` hoặc `Resolve-DnsName` từ đúng môi trường client. Cho biết hostname trả về IP nào và tại sao test trên host có thể khác container.
4. Dùng `nc -vz` hoặc `Test-NetConnection` thử TCP 9042. Giải thích vì sao TCP thành công chưa đủ kết luận TLS, auth và CQL chạy tốt.
5. Một Java Driver kết nối được `db-gateway.example.internal:9042` nhưng không tới peer `172.18.0.5:9042`. Nêu nguyên nhân, cách xác định peer được công bố và giải pháp mạng phù hợp.
6. So sánh yêu cầu firewall cho ứng dụng → Cassandra native (`9042`) và Cassandra node ↔ node (`7000`). Tại sao không nên mở `7199` cho ứng dụng?
7. Trên Kubernetes, giải thích khác biệt giữa `localhost` của hai Pod, tên Service DNS và địa chỉ Pod. Nêu ba đối tượng Kubernetes cần xem khi app Pod không kết nối được.
8. Chạy lab CQL ở mục 9, sau đó đọc bằng Java Driver. Thay `CASSANDRA_HOST` theo nơi chạy và xác nhận tên datacenter thật.
9. Giả sử TCP 9042 từ Java thành công nhưng `ReadTimeout` ở `LOCAL_QUORUM`: đưa ra thứ tự kiểm tra RF, tình trạng replica, internode, tải và consistency.

**Tiêu chí hoàn thành:** xác định đúng nguồn/đích kết nối, chọn hostname hợp lệ theo network namespace, phân biệt service DNS với host published port, kiểm tra tuần tự DNS/TCP/TLS/CQL, hiểu peer discovery và phân biệt lỗi mạng client với lỗi internode/replication.

## Tài liệu tham khảo

- [Apache Cassandra — cassandra.yaml](https://cassandra.apache.org/doc/stable/cassandra/managing/configuration/cass_yaml_file.html): native transport, `rpc_address`, `broadcast_rpc_address`, `listen_address`, các cổng và TLS.
- [Apache Cassandra — Architecture](https://cassandra.apache.org/doc/stable/cassandra/architecture/overview.html): coordinator, node, cluster, replica và gossip.
- [Apache Cassandra — cqlsh](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/cqlsh.html): kết nối CQL qua native protocol và kiểm tra phiên.
- [Docker Docs — Networking in Compose](https://docs.docker.com/compose/how-tos/networking/): DNS service, container networking, host port và container port.
- [Kubernetes — DNS for Services and Pods](https://kubernetes.io/docs/concepts/services-networking/dns-pod-service/): tên Service và cách phân giải trong cluster.
- [Kubernetes — Network Policies](https://kubernetes.io/docs/concepts/services-networking/network-policies/): ingress/egress policy giữa Pod và Service.
- [Apache Cassandra Java Driver 4.x — Core](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/index.html): contact points, local datacenter, topology và session.
