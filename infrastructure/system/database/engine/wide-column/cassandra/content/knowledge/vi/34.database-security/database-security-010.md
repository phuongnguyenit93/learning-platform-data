# Network binding, firewall và tách luồng ứng dụng/đồng bộ

## Mục tiêu và bối cảnh

Apache Cassandra là cơ sở dữ liệu phân tán theo mô hình **wide-column**. Một ứng dụng gửi câu lệnh CQL tới một **coordinator**; coordinator trao đổi với các **replica** được xác định từ partition key, token và replication strategy. Các node còn trao đổi gossip, mutation, read requests, streaming và repair. Vì vậy, cấu hình mạng sai có thể khiến ứng dụng không kết nối được, node bị đánh dấu `DN`, dữ liệu giữa các datacenter không hội tụ hoặc một dịch vụ quản trị bị lộ ra Internet.

Bài học thuộc chương **Bảo mật** của module `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA`. Trọng tâm là **network binding**, **firewall/segmentation** và **tách đường truy cập ứng dụng khỏi đường giao tiếp giữa các node**. Kiến thức liên hệ partition key, CQL, mức nhất quán đọc/ghi, replication theo DC, compaction, repair, xử lý sự cố và Java Driver.

Sau bài này, bạn có thể:

1. Phân biệt **địa chỉ lắng nghe** (`listen_address`, `rpc_address`) với **địa chỉ được quảng bá** (`broadcast_address`, `broadcast_rpc_address`) và nhận diện rủi ro dùng địa chỉ sai.
2. Phân biệt đường **client → CQL native transport**, đường **node ↔ node** cho gossip/replication/streaming và đường **quản trị/quan sát**.
3. Thiết kế một **ma trận allowlist theo nguồn, đích, port và mục đích**, không mở mọi port Cassandra ra mọi mạng.
4. Hiểu phạm vi bảo vệ của **firewall**, **TLS**, **authentication/authorization** và các cơ chế phân tách quyền, thay vì coi một lớp duy nhất là đủ.
5. Chẩn đoán hiện tượng client kết nối được nhưng replica không thể đồng bộ, hoặc node `UN` nhưng ứng dụng không truy cập CQL.
6. Thực hành kiểm tra cổng, topology, CQL và Java Driver trên lab, ghi kết quả an toàn và có phương án quay lui khi đổi chính sách mạng.

> **Cảnh báo:** thay đổi `listen_address`, `broadcast_address` hoặc chặn port internode có thể chia cắt cluster và gây unavailable. Chỉ diễn tập firewall có chủ đích trong **lab/staging được phép gây lỗi**. Trên production, thay đổi theo quy trình có phê duyệt, mở sẵn đường quản trị và thử theo từng node/rack/DC; không chạy lệnh flush firewall hoặc khóa SSH trên máy đang truy cập từ xa.

## 1. Ba mặt phẳng giao tiếp của Cassandra

Không phải mọi lưu lượng đến node Cassandra đều là một “cổng database”.

| Mặt phẳng | Ai kết nối với ai? | Mục đích | Cổng TCP thường gặp |
| --- | --- | --- | --- |
| **Ứng dụng / CQL native transport** | Java Driver, `cqlsh`, service được phép → Cassandra coordinator | Authentication, CQL request/response, routing client | `9042` mặc định; cổng khác nếu cấu hình |
| **Internode / replication** | Cassandra node ↔ Cassandra node | Gossip, messaging, mutation/read requests, streaming/repair giữa replica | `7000` thường gặp; `7001` có thể xuất hiện ở cấu hình TLS/phiên bản cũ hoặc migration |
| **Quản trị / monitoring** | Bastion/automation được phép → JMX hoặc agent quản trị | `nodetool`, health, metrics, điều tra lỗi | JMX thường `7199`; exporter/agent có thể dùng cổng riêng |

**Đây là bảng định hướng, không phải danh sách port bắt buộc cho mọi phiên bản.** Cassandra 4.x/5.x, cấu hình TLS internode, bản phân phối, container/Kubernetes và custom ports có thể khác nhau. Phải quan sát **listener thực tế**, `cassandra.yaml` và hướng dẫn đúng phiên bản trước khi viết firewall rule.

Đặc biệt:

- `9042` là đường **CQL native transport**, **không phải cổng gossip hoặc streaming**.
- `7000` thường phục vụ giao tiếp **node-to-node**; không có lý do mở nó cho toàn bộ ứng dụng Java.
- `7001` **không nên mở mặc định một cách mù quáng**. Việc cần cổng TLS internode riêng phụ thuộc cấu hình và version; các phiên bản mới có thể dùng đường TLS khác với mô hình “7000 plaintext/7001 TLS” của tài liệu cũ.
- `7199` thuộc vùng **JMX/quản trị**, không phải port ứng dụng. Ở một số cấu hình nó chỉ lắng nghe local; khi bật JMX remote cần chính sách xác thực/TLS/tunnel riêng và có thể có yêu cầu thêm cổng RMI.
- Port `9160` gắn với **Thrift cũ**, không phải cổng CQL chuẩn của Cassandra hiện đại; đừng mở theo checklist lỗi thời.

### Mô hình ví dụ hai datacenter

Giả sử `dc_a` và `dc_b` cùng thuộc **một cluster**, mỗi DC có ba node; ứng dụng A và B nằm ở subnet riêng.

~~~mermaid
flowchart LR
    A["Ứng dụng tại dc_a"] -->|"CQL TLS :9042"| CA["Node Cassandra dc_a"]
    B["Ứng dụng tại dc_b"] -->|"CQL TLS :9042"| CB["Node Cassandra dc_b"]
    CA <-->|"Internode messaging / streaming"| CB
    OPS["Bastion quản trị"] -. "JMX / vận hành qua kênh hạn chế" .-> CA
    OPS -.-> CB
    MON["Monitoring đã cấp quyền"] -. "Metrics qua kênh phù hợp" .-> CA
    MON -.-> CB
~~~

Hình vẽ chỉ là **luồng logic**: thực tế mọi node trong cùng cluster cần các kết nối internode thích hợp đến các peer khác theo topology, không chỉ một cặp đại diện A/B. Nếu firewall chỉ cho phép A1 ↔ B1 mà chặn những node còn lại, gossip/streaming có thể không hoạt động đúng.

## 2. Bind address khác advertised address

**Bind/listen address** quyết định tiến trình Cassandra mở socket trên giao diện mạng nào của **chính máy đó**. **Broadcast/advertised address** là địa chỉ node thông báo cho peer hoặc client dùng để tiếp cận nó. Hai địa chỉ có thể trùng trên host đơn giản nhưng thường khác trong môi trường nhiều NIC, NAT hoặc container.

### Các trường thường gặp trong `cassandra.yaml`

| Cấu hình | Vai trò | Sai lầm dễ gặp |
| --- | --- | --- |
| `listen_address` | Địa chỉ IP trên node để lắng nghe **internode** | Gắn IP không thuộc NIC của máy hoặc nhầm IP public/LB |
| `listen_interface` | Cách chọn interface cho internode ở cấu hình hỗ trợ | Cấu hình đồng thời/mâu thuẫn với `listen_address` |
| `broadcast_address` | Địa chỉ **internode quảng bá** để các node khác tìm đến | Quảng bá `127.0.0.1`, IP không định tuyến được hoặc IP NAT không có đường hai chiều |
| `rpc_address` | Địa chỉ bind dịch vụ **client/native CQL** (tên `rpc` mang tính lịch sử) | Tin rằng `rpc_address` chỉ điều khiển Thrift, hoặc mở `0.0.0.0` mà thiếu firewall |
| `rpc_interface` | Chọn interface client trong bản/config hỗ trợ | Nhầm với đường internode |
| `broadcast_rpc_address` | Địa chỉ **client được quảng bá** qua metadata topology | Quảng bá địa chỉ mà Java Driver không thể định tuyến tới |
| `native_transport_port` | Port CQL native transport, thường 9042 | Mở port nhưng quên TLS/auth hoặc đặt firewall sai subnet |

Trong nhiều bản Cassandra, **`listen_address` không được đặt `0.0.0.0`**: node cần một danh tính endpoint internode có thể định tuyến. Ngược lại, `rpc_address: 0.0.0.0` có thể dùng để bind mọi interface khi cần, nhưng phải có **`broadcast_rpc_address` là địa chỉ cụ thể, reachable** và firewall chặt; đừng mặc định đó là lựa chọn an toàn.

### Ví dụ cấu hình cho một node trong lab

~~~yaml
# cassandra.yaml - TRÍCH ĐOẠN MINH HỌA, KHÔNG PHẢI FILE HOÀN CHỈNH
# Node cass-a1 có IP private 10.20.10.11, ứng dụng đi vào mạng private.
listen_address: 10.20.10.11
broadcast_address: 10.20.10.11
rpc_address: 10.20.10.11
broadcast_rpc_address: 10.20.10.11
native_transport_port: 9042
~~~

Nếu dùng **hai network interface**, chẳng hạn inter-node `10.20.10.11` và CQL `10.30.10.11`, có thể bind/advertise phù hợp theo thiết kế mạng và phiên bản:

~~~yaml
# CHỈ MÔ HÌNH MẠNG KHI CẢ HAI IP THUỘC NODE VÀ ĐƯỢC ĐỊNH TUYẾN.
listen_address: 10.20.10.11
broadcast_address: 10.20.10.11
rpc_address: 10.30.10.11
broadcast_rpc_address: 10.30.10.11
native_transport_port: 9042
~~~

**Không sao chép nguyên IP**. Cả `listen_address` lẫn `rpc_address` phải tương thích interface thực tế và kiến trúc container/host. `broadcast_*` phải là endpoint **các bên tiêu thụ sẽ kết nối được**, không phải chỉ là IP ping thành công từ localhost.

### Vì sao broadcast sai gây lỗi khó hiểu?

Java Driver có thể kết nối thành công contact point ban đầu nhưng sau đó khám phá các node thông qua metadata. Nếu cluster quảng bá `broadcast_rpc_address` không thể truy cập từ subnet ứng dụng, driver có thể báo node unavailable, routing không đều hoặc kết nối chậm dù contact point vẫn trả lời.

Tương tự, nếu `broadcast_address` internode trỏ tới IP không tới được từ một DC, peer có thể không gossip/stream/repair được. Khi node gặp NAT, overlay network hoặc L4 proxy, **cấu hình bind/broadcast cần được thiết kế theo đường kết nối hai chiều thực**, không khắc phục bằng cách mở bừa toàn bộ cổng public.

## 3. Tách luồng ứng dụng, internode và quản trị theo zone

Tách luồng nghĩa là **xác định chính xác ai cần kết nối đến dịch vụ nào**, rồi áp dụng kiểm soát tại security group/firewall/network policy và trên chính host.

Ví dụ các vùng mạng trong **lab**:

- **Cassandra dc_a:** `10.20.10.0/24`.
- **Cassandra dc_b:** `10.20.20.0/24`.
- **Application dc_a:** `10.30.10.0/24`.
- **Application dc_b:** `10.30.20.0/24`.
- **Bastion/automation:** `10.40.0.0/24`.

Các CIDR này **chỉ là địa chỉ giả lập cho bài học**, không phải thiết kế được cấp sẵn cho tổ chức.

### Ma trận chính sách cơ bản

| Nguồn | Đích | Cổng/dịch vụ | Phương án |
| --- | --- | --- | --- |
| Ứng dụng `dc_a` | Node Cassandra `dc_a` | CQL TCP 9042 | **ALLOW** theo subnet/service identity; yêu cầu TLS/auth |
| Ứng dụng `dc_b` | Node Cassandra `dc_b` | CQL TCP 9042 | **ALLOW** tương tự, đúng local DC |
| Cassandra node `dc_a` | Các peer trong `dc_a` và `dc_b` | Internode TCP port cấu hình (ví dụ 7000) | **ALLOW có giới hạn** hai chiều, kể cả giữa DC |
| Cassandra node `dc_b` | Các peer trong `dc_a` và `dc_b` | Internode port cấu hình | **ALLOW có giới hạn** hai chiều |
| Cassandra peer | Cassandra peer | Port TLS internode khác, **nếu thực sự được dùng** | Chỉ allow đúng cấu hình/version; không mặc định luôn mở 7001 |
| Bastion/automation tin cậy | Management listener của node | JMX/agent đã cấu hình | **ALLOW hẹp**, ưu tiên tunnel, xác thực và mã hóa |
| Monitoring được cấp quyền | Exporter/metrics endpoint | Port thực tế của exporter | **ALLOW hẹp**, không public dashboard/metrics |
| Ứng dụng thông thường | Internode/JMX | 7000/7001/7199 | **DENY** nếu không có lý do được duyệt |
| Internet công cộng | CQL/internode/JMX | 9042/7000/7001/7199 | **DENY** theo mặc định |

**Stateful firewall** thường tự cho phép traffic phản hồi của kết nối đã được thiết lập; **stateless ACL** có thể còn cần quy tắc chiều về và ephemeral ports. Kiểm tra hành vi của nền tảng, không giả định mọi firewall giống nhau.

### Mã chính sách giả để thảo luận, KHÔNG chạy như lệnh firewall

~~~text
# PSEUDOPOLICY, không phải cú pháp của nftables/iptables/Cloud SG
ALLOW app_dc_a -> cassandra_dc_a TCP/9042
ALLOW app_dc_b -> cassandra_dc_b TCP/9042
ALLOW cassandra_dc_a <-> cassandra_dc_a TCP/<internode_configured>
ALLOW cassandra_dc_b <-> cassandra_dc_b TCP/<internode_configured>
ALLOW cassandra_dc_a <-> cassandra_dc_b TCP/<internode_configured>
ALLOW ops_bastion -> management_endpoints TCP/<restricted_management_ports>
ALLOW authorized_monitoring -> metric_exporters TCP/<configured_exporter_ports>
DENY  internet -> cassandra_nodes TCP/<all_database_and_management_ports>
DENY  ordinary_app -> internode_or_JMX
~~~

**Quan trọng:** trong thiết kế nhiều DC, hai nhóm internode phải được phép liên lạc theo nhu cầu **của cùng một cluster**. Việc app chỉ đọc/ghi tại local DC **không có nghĩa** có thể chặn internode cross-DC mà replication vẫn được bảo đảm.

## 4. Gossip, streaming, repair và vì sao không thể chặn “luồng đồng bộ”

Cassandra sử dụng giao tiếp internode cho nhiều mục đích:

- **Gossip/membership:** trao đổi trạng thái node, topology, failure detection và thông tin để định tuyến.
- **Read/write messaging:** coordinator gửi mutation hoặc read/digest requests đến replica cần thiết theo RF/CL.
- **Streaming:** chuyển SSTable/range trong bootstrap, replace, decommission hoặc repair.
- **Hints/repair:** các cơ chế giúp replica bỏ lỡ mutation bắt kịp, tùy phiên bản và trạng thái dữ liệu.

Không thể coi streaming là “dịch vụ phụ không quan trọng” và chặn tùy tiện. Một rule chặn inter-node có thể gây lỗi gossip, đứt streaming, repair thất bại và replica không nhận mutation. Dấu hiệu trực tiếp tại ứng dụng đôi khi **xuất hiện muộn** hơn sự cố mạng vì `LOCAL_QUORUM` có thể vẫn đủ ACK trong DC local.

### Ví dụ mất liên lạc hai DC

Giả sử `NetworkTopologyStrategy` đặt `dc_a:3` và `dc_b:3`. Ứng dụng ghi ở `dc_a` với `LOCAL_QUORUM`:

~~~text
dc_a: A1 ACK + A2 ACK -> write có thể thành công tại LOCAL_QUORUM
dc_b: inter-DC đang bị chặn -> có thể chưa nhận mutation
~~~

Thành công của write **chỉ xác nhận đủ replica local** theo CL, **không bảo đảm** write đã có ở `dc_b`. Nếu chuyển ứng dụng sang `dc_b` ngay sau đó, nó có thể đọc phiên bản cũ. Nếu replica bỏ lỡ `DELETE` trong thời gian quá dài, còn phải đánh giá tombstone và `gc_grace_seconds` trước khi hội tụ để tránh **zombie data**.

~~~mermaid
sequenceDiagram
    participant App as Client dc_a
    participant A as Coordinator dc_a
    participant LA as Replica local dc_a
    participant B as Replica remote dc_b
    App->>A: WRITE LOCAL_QUORUM
    A->>LA: Mutation tới replicas local
    A--xB: Mutation/replication bị chặn WAN
    LA-->>A: Đủ 2/3 ACK local
    A-->>App: WRITE success
    Note over B: Có thể thiếu dữ liệu đến khi đường đồng bộ phục hồi
~~~

**Không kiểm tra “kết nối cross-DC có ổn” chỉ bằng một SELECT ở local quorum.** Phải quan sát inter-node, trạng thái node theo DC, streaming/hints/repair và thực hiện đối soát theo các marker đã được ACK khi thích hợp.

### Đường riêng và mức cô lập

Mạng riêng dành cho internode có thể hữu ích để giảm bề mặt tấn công và kiểm soát băng thông, nhưng cần xét:

- Có routing hai chiều giữa mọi node/replica cần trao đổi không?
- DNS/IP quảng bá có được phân giải/định tuyến từ **tất cả DC liên quan** không?
- TLS internode đã bật đúng phiên bản, cert trust và rotation chưa?
- QoS/bandwidth limit có làm streaming/repair bị nghẽn trong giờ tải cao không?
- Rule ingress/egress có áp dụng đối xứng không, kể cả khi node reboot và IP đổi?
- Có đường quản trị riêng giúp điều tra khi client CQL hoặc internode mất liên lạc không?

## 5. Firewall không thay thế TLS, xác thực và phân quyền

Một rule `ALLOW app_subnet → TCP/9042` chỉ kiểm tra vị trí mạng/identity nếu nền tảng có hỗ trợ; nó **không biết tài khoản CQL đó có được đọc dữ liệu nhạy cảm không**. Bảo vệ nhiều lớp:

| Lớp | Nhiệm vụ | Không thể thay thế |
| --- | --- | --- |
| Network segmentation/firewall | Giảm những máy có đường TCP đến endpoint | Không mã hóa byte, không tự cấp quyền CQL |
| **TLS client-to-node** | Bảo mật đường truyền CQL, xác minh server certificate | Không quyết định role được `SELECT` bảng nào |
| **TLS internode** | Bảo vệ đường liên lạc giữa các node/replica | Không tự chứng minh mọi node hợp lệ theo chính sách trust nếu cấp cert sai |
| Authentication | Nhận diện dịch vụ/người dùng kết nối | Không quyết định quyền đối với mọi keyspace/table |
| Authorization | Cho phép hoặc từ chối thao tác theo role/permission | Không bảo vệ payload khi truyền nếu TLS tắt |
| Host/secret security | Bảo vệ file cấu hình, private key, credential, filesystem | Không thay retention/backup hoặc xử lý sự cố |
| Auditing/monitoring | Phát hiện request bất thường, thay đổi policy hoặc lỗi TLS | Không tự ngăn một kết nối đã được phép |

### TLS cho CQL client

Trong các phiên bản Cassandra có `client_encryption_options`, yêu cầu TLS cần được cấu hình tương thích cả server và driver. Khi policy là **TLS bắt buộc**, không được để client chuyển sang plaintext nếu handshake lỗi.

~~~yaml
# cassandra.yaml - CHỈ TRÍCH ĐOẠN THAM KHẢO
# Tên khóa con/format có thể khác giữa các phiên bản.
client_encryption_options:
    enabled: true
    optional: false
    # keystore / truststore / client_auth tùy PKI và version
~~~

`optional: false` minh họa không cho plaintext fallback ở các phiên bản hỗ trợ tùy chọn đó. Không đặt password keystore/truststore trong tài liệu public hoặc commit vào Git. Server phải có certificate/key phù hợp và client cần trust anchor, hostname/SAN validation và chính sách rotation.

### TLS giữa các node

~~~yaml
# cassandra.yaml - MẪU KHÁI NIỆM, không thay quy trình migration TLS
server_encryption_options:
    internode_encryption: all
    # keystore/truststore, client_auth, cipher protocols theo phiên bản
~~~

Các lựa chọn `internode_encryption` (ví dụ `none`, `dc`, `rack`, `all`) và cơ chế xác thực chứng chỉ phụ thuộc phiên bản. **Đổi từ plaintext sang TLS phải lập kế hoạch tương thích trong quá trình rolling deployment**: nếu A yêu cầu TLS mà B chỉ nói plaintext, node có thể không liên lạc. Không tự đổi `internode_encryption` trên tất cả node cùng lúc mà chưa có phương án rollback.

### CQL authentication và authorization

Trong deployment yêu cầu bảo mật, cần đánh giá `PasswordAuthenticator` hoặc cơ chế xác thực được hỗ trợ, kết hợp authorizer/role permissions phù hợp. Role của ứng dụng nên được cấp quyền trên **những keyspace/table cần thiết**, không dùng tài khoản superuser chung. Đừng đưa password vào `cqlsh -p ...` hoặc URL/command line nếu môi trường làm lộ process list và shell history.

**TLS có thành công không** và **CQL role có quyền không** là hai phép kiểm thử độc lập. Kết nối TCP thông hoặc TLS handshake đạt nhưng truy vấn bị `Unauthorized` có thể là **tín hiệu phân quyền đang hoạt động đúng**, không phải lý do mở firewall rộng hơn.

## 6. Bảo vệ JMX, nodetool, metrics và đường backup

`nodetool` thường giao tiếp với node thông qua **JMX**, không phải native CQL `9042`. Vì vậy:

- JMX nên chỉ mở tới loopback/bastion/management plane được phê duyệt khi có thể.
- Nếu buộc chạy **remote JMX**, áp dụng authentication, TLS/tunnel, hạn chế CIDR và bảo vệ RMI/endpoints theo runtime cụ thể.
- Monitoring agent/exporter phải có riêng danh sách nguồn được phép; không mặc định công khai port metrics chỉ vì không chứa trực tiếp dữ liệu CQL.
- Các thao tác như `nodetool flush`, `snapshot`, `repair`, `decommission` có tác động khác nhau; cấp quyền thực thi ở OS/automation theo phạm vi công việc và audit.

**Đừng cho ứng dụng nghiệp vụ quyền JMX/SSH đến node Cassandra** chỉ vì nó cần kết nối CQL. Java Driver giao tiếp qua native transport. Nếu một dịch vụ frontend có thể gửi lệnh quản trị lên node, bề mặt tấn công tăng rất nhiều.

Backup cũng cần vùng riêng: node hoặc backup agent có thể đọc snapshot và xuất tới object storage qua kênh mã hóa, nhưng không vì thế mà object bucket phải có quyền truy cập từ mọi pod ứng dụng. KMS, retention bất biến, quyền đọc/ghi/xóa tách biệt và restore test vẫn quan trọng khi đã tách mạng.

## 7. Kiểm tra trạng thái mạng mà không thay đổi firewall

Trước khi sửa cấu hình, thu trạng thái hiện hữu từ **đúng node và client subnet**. Những lệnh sau có tính quan sát; không phải lệnh đóng/mở cổng.

### 7.1. Trên node Cassandra

~~~bash
# Linux: xác minh IP/interface của node.
ip addr show

# Các TCP listeners thường gặp; kiểm tra quyền thực tế.
ss -lntp

# Nếu dùng nftables:
sudo nft list ruleset

# Nếu dùng iptables:
sudo iptables -S

# Trạng thái cluster; nodetool cần kênh quản trị/JMX phù hợp.
nodetool status
nodetool netstats
~~~

Không nhất thiết hệ điều hành có cả `nft` và `iptables`; dùng bộ công cụ đúng nền tảng. Chú ý địa chỉ bind hiển thị:

~~~text
10.20.10.11:7000  -> listener internode trên interface private
10.30.10.11:9042  -> listener CQL trên interface app private
127.0.0.1:7199   -> JMX chỉ local (nếu đúng cấu hình thực tế)
0.0.0.0:9042     -> listener CQL trên mọi IPv4 interface (cần kiểm firewall)
~~~

Đây là ví dụ **giải thích output**, không phải ảnh chụp node thật. `ss` chứng minh socket đang listen nhưng **chưa chứng minh** firewall cho phép từ nguồn remote, chứng chỉ hợp lệ hoặc replica hội tụ.

### 7.2. Từ một client app được phép

~~~bash
# Chỉ kiểm tra TCP reachability; host/IP của lab được phép.
nc -vz 10.30.10.11 9042
~~~

Nếu CQL dùng TLS:

~~~bash
# Thử handshake và xem server certificate, cần PKI/trust phù hợp.
openssl s_client -connect cass-a1.internal:9042 \
  -servername cass-a1.internal
~~~

`nc` báo thành công chỉ có nghĩa đường TCP có thể thiết lập, **không** chứng minh CQL handshake, authentication, authorization, latency hay consistency. `openssl s_client` có thể in chain/certificate nhưng **không đủ** để kết luận toàn bộ PKI và hostname validation của Java Driver đã được cấu hình đúng; phải kiểm tra verify result, trust anchor và tên trong SAN theo thực tế.

Nếu máy chẩn đoán dùng Windows hoặc image tối giản, sử dụng công cụ tương đương có sẵn thay vì cài đặt tùy tiện vào production.

### 7.3. Kiểm tra CQL thật

Từ một phiên `cqlsh` được cấu hình **TLS + credentials bảo mật** theo policy:

~~~sql
SELECT release_version, data_center, host_id
FROM system.local;
~~~

`system.local` nói về **node trả lời câu truy vấn**, không mô tả toàn bộ cluster. Nếu lệnh này chạy được, đường CQL/auth/permission cần thiết cho câu đó hoạt động; chưa đủ chứng minh internode giữa mọi node hay dữ liệu ở các replica đã hội tụ.

~~~bash
# Trên node quản trị có quyền, kiểm tra membership từ nhiều góc nhìn.
nodetool status
nodetool describecluster
nodetool netstats
~~~

**Một cụm vẫn có thể hiển thị các node `UN` tại thời điểm quan sát nhưng phát sinh lỗi streaming/hints hoặc inter-DC replication lag.** Kết hợp metrics, logs và đối soát dữ liệu thực trước khi chốt sự cố mạng đã khắc phục.

## 8. Lab hai DC: kiểm chứng tách đường mà không gây mất dữ liệu

### 8.1. Chuẩn bị và tiêu chí an toàn

Lab minh họa có `dc_a` và `dc_b`, mỗi DC ba node, sử dụng `NetworkTopologyStrategy` với **RF=3 ở mỗi DC**. Nếu môi trường chỉ có một DC, có thể làm bài kiểm tra bind/port/ACL local nhưng **không diễn giải là thử nghiệm replication cross-DC**.

Trước diễn tập:

1. Ghi `nodetool status` và `describecluster`; mọi node cần thiết `UN`.
2. Xác minh client local DC, cert và quyền CQL; không dùng superuser cho ứng dụng lab.
3. Lập manifest các marker đã ACK **ngoài cluster**.
4. Đảm bảo có quyền rollback policy từ management plane **không phụ thuộc chính cổng đang thử**.
5. Chỉ chạy bài **quan sát connectivity** trước; thử chặn inter-DC chỉ trên lab có phương án phục hồi đã chuẩn bị.

### 8.2. Tạo keyspace và bảng

~~~sql
CREATE KEYSPACE IF NOT EXISTS network_lab
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc_a': 3,
    'dc_b': 3
}
AND durable_writes = true;

CREATE TABLE IF NOT EXISTS network_lab.events_by_run (
    run_id text,
    event_id uuid,
    marker text,
    origin_dc text,
    created_at timestamp,
    PRIMARY KEY ((run_id), event_id)
);
~~~

`run_id` là **partition key** và `event_id` là clustering key; các truy vấn dưới chỉ đọc một partition nhỏ. Nếu keyspace đã có, `IF NOT EXISTS` **không sửa RF cũ**. Kiểm tra:

~~~sql
SELECT keyspace_name, replication
FROM system_schema.keyspaces
WHERE keyspace_name = 'network_lab';
~~~

Tên `dc_a`/`dc_b` phải trùng kết quả topology/snitch, không suy từ tên máy hoặc vị trí địa lý. Với lab sáu node RF3+3, mỗi partition dự kiến có ba replica trong mỗi DC.

### 8.3. Ghi và kiểm tra baseline

Kết nối `cqlsh` tới **một coordinator tại `dc_a``. Trong `cqlsh`:

~~~text
CONSISTENCY LOCAL_QUORUM
~~~

~~~sql
INSERT INTO network_lab.events_by_run
    (run_id, event_id, marker, origin_dc, created_at)
VALUES (
    'net-demo-01',
    11111111-1111-4111-8111-111111111111,
    'BASELINE-A', 'dc_a', '2026-11-21T09:00:00Z'
);

SELECT event_id, marker, origin_dc
FROM network_lab.events_by_run
WHERE run_id = 'net-demo-01';
~~~

Chỉ ghi **ACK_LOCAL_QUORUM** vào manifest khi client thực nhận thành công; `WriteTimeout` có kết quả **UNKNOWN_WRITE**, không phải chắc chắn mutation chưa đến replica. Khi kiểm tra từ `dc_b` với `LOCAL_QUORUM`, có thể thấy `BASELINE-A` sau replication, nhưng **ACK ở `dc_a` không đòi quorum `dc_b` xác nhận**.

### 8.4. Ma trận kiểm tra lưu lượng

| Phép thử | Nguồn → đích | Kỳ vọng khi policy đúng | Nếu thất bại, kiểm tra |
| --- | --- | --- | --- |
| CQL A | App A → coordinator `dc_a` TCP/9042 | TLS/auth/CQL thành công | `rpc_address`, `broadcast_rpc_address`, ACL, cert/SAN, role |
| CQL B | App B → coordinator `dc_b` TCP/9042 | TLS/auth/CQL thành công | Local DC driver, endpoint quảng bá, policy |
| App → internode | App A/B → Cassandra TCP/7000 | **Bị từ chối** theo policy | Nếu thông, có rule quá rộng |
| App → JMX | App A/B → JMX | **Bị từ chối** theo policy | JMX bind/remote, firewall |
| Internode intra-DC | Node A1 → A2/A3, B1 → B2/B3 | Port/config đúng, peer hoạt động | Bind/broadcast, inter-node TLS, ACL hai chiều |
| Internode inter-DC | Node `dc_a` ↔ node `dc_b` | Giao tiếp phục vụ replication/repair | WAN, VPN, DNS, route, TLS và ACL |
| Quản trị | Bastion → kênh management được cấp | Chỉ identity được duyệt truy cập | Tunnel, JMX/RMI/TLS, bastion policy |

**Không dùng `nc` từ một app pod để kiểm tra quyền JMX bằng credential production**. Phép kiểm tra từ chối chỉ cần xác nhận kết nối bị chặn theo kế hoạch; tránh brute-force authentication hay scan mạng ngoài phạm vi lab được phép.

### 8.5. Thử nghiệm cô lập có kiểm soát trong lab

Thay vì đưa ra lệnh `iptables DROP` nguy hiểm có thể sao chép nhầm, thực hiện bằng **policy/network emulator của lab** theo ba kịch bản, mỗi kịch bản phải có cách hoàn tác đã kiểm chứng:

**Kịch bản A — Chặn riêng CQL từ ứng dụng tới một node:**

- Không chặn internode và không dừng Cassandra.
- Java Driver có thể route tới node khác nếu topology/policy cho phép; một client chỉ dùng một endpoint có thể lỗi kết nối.
- Peer gossip/streaming vẫn có thể khỏe; **app `ConnectTimeout` không tự là replica loss**.

**Kịch bản B — Chặn đường internode từ một node tới peers:**

- Node có thể bị peer coi là down, mutation/repair/streaming bị ảnh hưởng.
- Với RF3 một DC, nếu còn hai replica khỏe, `LOCAL_QUORUM` có thể tiếp tục đáp ứng một số request; `ALL` sẽ giảm khả năng sẵn sàng.
- **Không tiếp tục** nếu lab không còn đủ replica hoặc lỗi thứ hai xuất hiện.

**Kịch bản C — Chặn internode giữa `dc_a` và `dc_b` nhưng giữ đường ứng dụng local:**

- `LOCAL_QUORUM` của mỗi DC có thể còn đáp ứng với replica local còn khỏe.
- Replication giữa DC bị gián đoạn; client chuyển vùng có nguy cơ không thấy mutation đã ACK ở DC nguồn.
- Chỉ kết thúc khi đã **khôi phục ACL**, quan sát cluster ổn định và đối soát marker/repair theo quy trình; không chỉ chờ `nodetool status` hiển thị `UN`.

Ghi thời điểm chặn/mở, rule ID, phiên bản firewall, node/port, CL, trace/request ID và **read/write error**. Khi xuất hiện timeout, không gộp thành “MISSING” hoặc “dữ liệu đã mất”.

## 9. Java Driver 4.x: local DC, TLS và coordinator thực tế

Java Driver cần **địa chỉ có thể kết nối**, **local datacenter đúng** và cấu hình TLS/certificate phù hợp. Contact points hỗ trợ khám phá cluster; sau khi biết topology, driver có thể kết nối các node được quảng bá qua metadata. Do đó bảo vệ chỉ một địa chỉ contact point là **không đủ**.

Ví dụ sau nhắm tới Java Driver 4.x. Nó dùng truststore của JVM hoặc `SSLContext` được cung cấp an toàn từ cấu hình deployment. **Không bypass certificate validation** và không hard-code username/password trong mã.

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.ExecutionInfo;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.metadata.Node;

import javax.net.ssl.SSLContext;
import java.net.InetSocketAddress;
import java.util.UUID;

public final class SecureCassandraProbe {
    public static CqlSession connectLab(SSLContext trustConfiguredTls)
            throws Exception {
        return CqlSession.builder()
            .addContactPoint(new InetSocketAddress("10.30.10.11", 9042))
            .addContactPoint(new InetSocketAddress("10.30.10.12", 9042))
            .withLocalDatacenter("dc_a")
            .withSslContext(trustConfiguredTls)
            // Authentication/hostname validation được cấu hình
            // theo PKI và driver deployment, không ghi secret ở đây.
            .build();
    }

    public static void check(CqlSession session,
                             String runId, UUID eventId) {
        PreparedStatement query = session.prepare(
            "SELECT marker FROM network_lab.events_by_run " +
            "WHERE run_id = ? AND event_id = ?");

        ResultSet result = session.execute(
            query.bind(runId, eventId)
                .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
                .setIdempotence(true));

        ExecutionInfo info = result.getExecutionInfo();
        Node coordinator = info.getCoordinator();
        System.out.printf("coordinator=%s%n",
            coordinator == null
                ? "unknown"
                : coordinator.getEndPoint());
        var row = result.one();
        System.out.println(row == null
            ? "QUERY_SUCCEEDED_NO_ROW"
            : "QUERY_SUCCEEDED_WITH_ROW");
    }
}
~~~

**Bảo vệ TLS cần thiết ở ngoài đoạn mã:** server phải bật client encryption phù hợp, cấp cert với SAN đúng địa chỉ/hostname được driver dùng, trust anchor phải tin cậy, policy của driver cần **hostname verification**, và user/role CQL được cấp quyền tối thiểu. Đoạn mã chỉ thể hiện cấu trúc session/truy vấn, **không phải toàn bộ cấu hình production**.

Nếu TLS handshake, authentication hoặc CQL thất bại, ghi **CONNECT/TLS/AUTH/READ_ERROR** riêng. `ResultSet` chỉ tồn tại khi query thành công; không có hàng mới là trường hợp `MISSING_AT_SELECTED_CL` để đối chiếu với manifest. Không coi một connection exception là bằng chứng thiếu partition.

### Khi app có nhiều datacenter

Nếu muốn truy cập `dc_b` là **local DC** trong failover, cần session/load-balancing configuration phù hợp `dc_b` và contact points được route đúng; không chỉ đổi `host` nhưng giữ `withLocalDatacenter("dc_a")`. Điều này ảnh hưởng cả **định tuyến coordinator** lẫn ý nghĩa `LOCAL_QUORUM`.

Không xây logic tự động fallback mọi query sang remote DC khi có lỗi mạng mà chưa đánh giá **RPO, dữ liệu đã hội tụ, write ownership và fencing**. Một request CQL thành công ở DC dự phòng không chứng minh các write mới nhất đã đến đủ replica của DC đó.

## 10. Theo dõi và xử lý sự cố mạng theo triệu chứng

### Tầng 1 — Client không mở được TCP/9042

**Dấu hiệu:** TCP timeout/refused, Java Driver không kết nối đến contact points.

Kiểm tra `ss -lntp` trên node, `rpc_address`/`native_transport_port`, firewall host/SG/network policy, routing/DNS và cổng quảng bá. `Connection refused` có thể do listener không chạy; timeout có thể do drop/routing, nhưng không phải lúc nào cũng vậy. Đừng tự mở internode port cho app để giải quyết lỗi CQL.

### Tầng 2 — TCP thông nhưng TLS/auth không thành công

**Dấu hiệu:** TLS handshake failure, certificate unknown, hostname mismatch, CQL authentication error hoặc unauthorized.

Kiểm tra server/client encryption settings, CA, SAN, hạn cert, thời gian hệ thống, KMS/secret rotation, role CQL. **Không khắc phục bằng cách tắt kiểm tra certificate hoặc mở plaintext tạm lên Internet**.

### Tầng 3 — App truy cập CQL nhưng cluster hiện `DN`/repair lỗi

**Dấu hiệu:** `nodetool status` có node down, streaming/repair thất bại, internode TLS errors.

Kiểm tra `listen_address`/`broadcast_address`, actual internode ports, peer-to-peer ACL **hai chiều**, route inter-DC, DNS, MTU, certificates, gossip/failure detector và log của node liên quan. Việc `SELECT` ở `LOCAL_ONE` thành công **không xác nhận internode ổn**.

### Tầng 4 — Tất cả node `UN` nhưng dữ liệu đọc khác theo DC

**Dấu hiệu:** write ACK ở DC A nhưng đọc tại DC B không thấy, hints/repair chưa hoàn tất.

Phân tích CL của write/read và local DC coordinator, lưu marker đã ACK trong manifest độc lập, kiểm tra networking xuyên DC, hints/repair/streaming. **Không vội kết luận mất dữ liệu** nếu remote còn lag; cũng không vội cho replica bỏ lỡ DELETE lâu ngày quay lại nếu có nguy cơ zombie.

### Bảng chẩn đoán nhanh

| Quan sát | Khả năng đầu tiên | Hành động ưu tiên |
| --- | --- | --- |
| `ss` không thấy 9042 | Native transport tắt/bind sai/khởi động lỗi | Kiểm tra config/log, không mở SG vô ích |
| 9042 listen nhưng app TCP timeout | ACL/routing/DNS/NAT | Kiểm nguồn/đích, rule ingress/egress |
| TLS cert hostname không khớp | Endpoint quảng bá sai hoặc SAN thiếu | Sửa PKI/hostname/advertise, không bypass verification |
| App vào contact point được, node khác unreachable | `broadcast_rpc_address`, routing discovery | Đối chiếu metadata endpoints và reachability |
| CQL chạy, `nodetool` JMX lỗi | Management plane bị chặn hoặc JMX auth/config | Dùng bastion/tunnel có quyền, không mở 7199 public |
| Node bị `DN` sau firewall rollout | Internode bị chặn hoặc TLS khác cấu hình | Quay lui rule, xác minh giao tiếp peer |
| Repair/streaming không chạy qua DC | Inter-DC network, cert, bandwidth | Xác minh port/config và phạm vi repair |
| Read `LOCAL_QUORUM` A đúng, B cũ | Replication lag hoặc khác biệt replica | Đối soát, kiểm hints/repair, không giảm CL để che lỗi |
| CPU/network tăng sau khi mở rule | Retry storm, traffic không mong muốn hoặc compaction | Rate limit, audit nguồn traffic, metrics theo node |

## 11. Runbook thay đổi firewall/binding an toàn

Một quy trình production nên có **bằng chứng trước và sau**; firewall thay đổi thành công về mặt API không đồng nghĩa ứng dụng và replication hoạt động đúng.

### Trước khi đổi

1. **Inventory:** liệt kê node/DC/rack, IP private/public, NIC, advertised endpoints, server/client TLS, JMX/exporter và cổng thực tế.
2. **Luồng phụ thuộc:** xác minh ứng dụng nào dùng CQL, node nào cần nói chuyện internode, repair/streaming cross-DC, monitoring và backup.
3. **Rủi ro:** xác định RF, consistency level ứng dụng, số node đang down, quorum khi mất một node và khả năng mất liên lạc cả DC.
4. **Nguồn kiểm chứng:** metrics, CQL marker đã ACK, latency, logs, trace ID; đừng chỉ ghi “ping thành công”.
5. **Rollback:** ghi rule ID/version hiện tại, phương pháp hoàn tác qua management plane độc lập, người chịu trách nhiệm và điểm dừng.
6. **Secrets/PKI:** certificate, CA, auth, KMS và hostname verification sẵn sàng trước khi bật TLS bắt buộc.

### Trong khi đổi

- Triển khai **theo từng node/zone hoặc rule hẹp** trước; giám sát gossip, ring, CQL và internode latency.
- Với thay đổi **bind/broadcast**, kiểm tra địa chỉ mới thực sự có trên interface, mọi peer/client reach được và driver discovery không trả endpoint sai.
- Với thay đổi **TLS**, thực hiện kế hoạch tương thích/rolling phù hợp version, không tạo một khoảng node mới chỉ TLS còn node cũ chỉ plaintext mà không thể giao tiếp.
- Khi phát hiện node `DN` hoặc write/read timeout tăng vượt ngưỡng, **dừng rollout và quay lui** theo phương án đã chuẩn bị.
- Tránh chạy topology change/repair nặng/compaction lớn đồng thời với thay đổi mạng khi chưa có lý do và ngân sách tài nguyên.

### Sau khi đổi

~~~text
CHECK 1: Từ app subnet, chỉ CQL endpoint được phép mới reachable.
CHECK 2: App không mở được internode/JMX endpoints ngoài policy.
CHECK 3: TLS server certificate, hostname, auth và quyền CQL đúng.
CHECK 4: Driver khám phá và chọn coordinator trong local DC đúng.
CHECK 5: nodetool status theo các node/DC không có bất thường mới.
CHECK 6: Inter-node messaging, hints, streaming/repair không báo lỗi.
CHECK 7: Marker đã ACK kiểm chứng theo CL/partition key, có log lỗi riêng.
CHECK 8: p95/p99, error rate và số retry không xấu hơn ngưỡng.
CHECK 9: Audit rule/PKI change có chủ sở hữu, timestamp và rollback ID.
~~~

**Không dùng một query `SELECT COUNT(*)` toàn bảng** để chứng minh điều kiện 7: tốn tài nguyên và count bằng nhau không đảm bảo các event ID giống nhau. Đối chiếu đúng primary key/marker với manifest tin cậy.

## 12. Mô hình đe dọa và những hiểu sai thường gặp

| Ngộ nhận | Cách hiểu đúng |
| --- | --- |
| “RF=3 nên có thể chặn traffic node-to-node sau khi dữ liệu đã ghi.” | RF dựa trên replica trao đổi mutation/repair; chặn internode gây replica lag, lỗi hoặc mất availability. |
| “`LOCAL_QUORUM` chỉ cần DC local, vậy có thể chặn inter-DC mãi.” | ACK local không đợi remote, nhưng replication cross-DC vẫn cần đường mạng và hội tụ. |
| “Đổi `rpc_address` sang `0.0.0.0` là an toàn vì driver có password.” | Bind mọi NIC mở rộng bề mặt tấn công; vẫn cần firewall, TLS và quyền tối thiểu. |
| “`broadcast_rpc_address` có thể để `127.0.0.1` vì contact point vẫn kết nối.” | Driver khám phá endpoint qua metadata; IP quảng bá không route được làm các node khác unreachable. |
| “Mở `7000/7001` cho app để truy vấn nhanh hơn.” | Đó là traffic internode, không phải API CQL của ứng dụng. |
| “Port `7001` luôn là internode TLS trên mọi Cassandra.” | Phụ thuộc phiên bản/migration; kiểm actual listener và cấu hình. |
| “Firewall đã chặn Internet thì không cần TLS.” | Traffic nội bộ vẫn có rủi ro interception, lateral movement và lộ credential. |
| “Có TLS thì không cần Cassandra permissions.” | TLS bảo vệ kênh, authorizer kiểm soát role được làm gì. |
| “`nc` thông nghĩa là client đã đăng nhập an toàn.” | TCP reachability không xác nhận TLS, auth, CQL và least privilege. |
| “Node `UN` tức là mọi dữ liệu/replica đã đồng bộ.” | Membership không chứng minh đủ mutation, repair hoặc read correctness. |
| “JMX không chứa dữ liệu người dùng nên có thể public.” | JMX cho phép quan sát/quản trị nhạy cảm; phải giới hạn truy cập và xác thực. |
| “Network policy đổi thất bại thì chỉ cần restart tất cả node.” | Có thể làm outage nặng hơn; ưu tiên kiểm rule, bind/advertise, TLS và rollback có kiểm soát. |

## 13. Bài tập thực hành và câu hỏi tư duy

**Bài 1 — Phân biệt bind và broadcast.** Node có `listen_address=10.20.10.11` và `broadcast_address=127.0.0.1`. Mặc dù tiến trình có thể listen, vì sao peer khác không thể tin cậy địa chỉ đó? Khi node có hai NIC, cách chọn cặp bind/broadcast nào cần xét?

**Bài 2 — Ma trận firewall.** Với hai DC, hai subnet app và một bastion, lập allowlist cho CQL, internode và management. Chỉ rõ nguồn/đích, port, chiều liên lạc, policy deny và cách kiểm tra không mở JMX/7000 cho ứng dụng.

**Bài 3 — Client discovery.** Java Driver kết nối được `cass-a1:9042` nhưng báo timeout với `cass-a2`. Trên `cass-a2`, `ss` có listener 9042. Bạn kiểm tra `broadcast_rpc_address`, metadata, firewall/route và cert SAN như thế nào?

**Bài 4 — Cross-DC consistency.** Keyspace đặt RF3 ở `dc_a` và RF3 ở `dc_b`. Client ghi ở `dc_a` với `LOCAL_QUORUM` rồi WAN bị chặn. Vì sao vẫn có thể nhận ACK? Khi failover sang `dc_b`, điều gì phải kiểm chứng trước khi nhận ghi mới?

**Bài 5 — Phân loại lỗi.** Một app gọi CQL bị `ReadTimeout`, một app khác bị TLS handshake failure, và `nodetool status` vẫn `UN`. Những triệu chứng đó thuộc lớp nào? Vì sao không nên ghi cả ba thành “MISSING DATA”?

**Bài 6 — Internode TLS rollout.** Giải thích rủi ro khi một nửa cluster chỉ cho TLS còn nửa kia chỉ chấp nhận plaintext. Phác thảo kế hoạch certificate/truststore, compatibility phase, canary, rollback và kiểm tra gossip/repair.

**Bài 7 — JMX và quyền vận hành.** Một team đề xuất mở `7199` từ toàn bộ ứng dụng Java vì cần xem trạng thái node. Thiết kế phương án metrics exporter hoặc bastion có xác thực thay thế, phân quyền và audit.

**Bài 8 — Multi-NIC và container.** Node quảng bá container IP không route được từ app subnet. Vì sao một load balancer đưa được request đến contact point vẫn chưa đủ cho token-aware discovery? Nêu ít nhất hai cách sửa kiến trúc mạng/advertise.

**Bài 9 — Security regression test.** Viết bộ synthetic checks sau firewall rollout có một phép thử **được cho phép** và một phép thử **phải bị từ chối** cho từng mặt phẳng CQL, internode, management. Nêu cách ngăn test chạm dữ liệu production.

**Bài 10 — Dữ liệu sau partition mạng.** Một replica bỏ lỡ DELETE khi bị cô lập quá lâu, tombstone có nguy cơ bị purge ở nơi khác. Tại sao chỉ mở lại 7000 không đảm bảo an toàn? Nêu bước kiểm tra `gc_grace_seconds`, repair history và lựa chọn rebuild/replace.

## Ghi nhớ

**Bảo mật mạng Cassandra là phân tách đúng ba luồng: CQL ứng dụng, giao tiếp internode và quản trị/giám sát.** `listen_address`/`rpc_address` quyết định nơi tiến trình bind, còn `broadcast_address`/`broadcast_rpc_address` quyết định địa chỉ peer và driver được quảng bá; cả hai phải định tuyến được trong đúng vùng mạng. Firewall chỉ cho phép **nguồn → đích → port cần thiết**, trong đó internode vẫn phải thông suốt giữa các replica/DC của cùng cluster. Kết hợp TLS, xác thực, quyền tối thiểu, JMX hạn chế và kiểm chứng sau thay đổi bằng **topology, driver routing, latency và dữ liệu đã ACK**. Không lấy một phép TCP connect hoặc một node `UN` làm bằng chứng rằng cluster vừa an toàn vừa hội tụ.
