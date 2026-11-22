# Địa chỉ listen/broadcast, kết nối giữa nút và từ ứng dụng

## 1. Tại sao Cassandra có nhiều địa chỉ mạng?

Apache Cassandra là cơ sở dữ liệu **wide-column phân tán**. Một node vừa trao đổi với các node khác trong cluster, vừa có thể nhận câu lệnh CQL từ ứng dụng Java hoặc `cqlsh`. Hai nhóm kết nối này có nhiệm vụ và cấu hình mạng khác nhau:

- **Internode (node ↔ node):** gossip/khám phá thành viên, trao đổi thông điệp đọc ghi, replica, streaming dữ liệu khi bootstrap/repair và nhiều hoạt động quản trị cluster.
- **Native client (ứng dụng ↔ node):** Java Driver và `cqlsh` gửi CQL bằng **native binary protocol**; node nhận yêu cầu làm coordinator, sau đó liên lạc với replica qua đường internode khi cần.

Vì vậy, một node có thể lắng nghe trên địa chỉ mạng nội bộ dành cho **internode** và một địa chỉ khác dành cho **client**. Tên tham số `listen`, `broadcast`, `rpc` và các cổng không thể dùng thay thế tùy ý.

Trong chương **Công cụ và kết nối** của module `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA`, nội dung này kết nối trực tiếp với kiến trúc phân tán, partition key, replication, consistency đọc/ghi, vận hành repair và kết nối từ ứng dụng Java.

Sau bài học, bạn có thể:

1. Phân biệt địa chỉ **bind/listen** với địa chỉ **advertise/broadcast**.
2. Cấu hình đúng cặp `listen_address`–`broadcast_address` cho internode và `rpc_address`–`broadcast_rpc_address` cho client.
3. Giải thích sự khác nhau giữa các cổng `7000`, `7001`, `9042` và `7199`.
4. Kiểm tra kết nối từ node, từ máy ứng dụng, và xác định vấn đề do firewall, NAT, DNS, TLS hay driver discovery.
5. Nhận diện tác động của cấu hình mạng đến gossip, replication, bootstrap, repair và Java Driver.

## 2. Phân biệt bind address và broadcast address

**Bind/listen address** là địa chỉ IP hoặc interface mà tiến trình Cassandra mở socket để **nhận kết nối đến**. **Broadcast/advertised address** là địa chỉ mà node **thông báo cho phía khác để phía đó kết nối lại**. Chúng có thể bằng nhau, nhưng trong mô hình nhiều card mạng, container, NAT hoặc đa vùng mạng thì có thể cần khác nhau.

| Câu hỏi | Bind/listen | Broadcast/advertise |
| --- | --- | --- |
| “Cassandra mở socket ở đâu?” | Trả lời bằng địa chỉ/interface được bind. | Không quyết định socket nào đang lắng nghe. |
| “Peer hoặc driver nên gọi vào địa chỉ nào?” | Chỉ đủ nếu địa chỉ bind cũng được bên kia định tuyến tới. | Công bố endpoint cho phía bên kia sử dụng. |
| “Có thể dùng `0.0.0.0` không?” | Với client `rpc_address` có thể, kèm điều kiện; với internode `listen_address` thì **không**. | Không dùng `0.0.0.0` làm đích kết nối công bố. |
| “Có tự mở firewall không?” | Không. | Không. |

Ví dụ: node bind dịch vụ CQL trên `0.0.0.0:9042`, nghĩa là có thể lắng nghe các IPv4 interface phù hợp. Driver không thể kết nối đến `0.0.0.0` như một địa chỉ node thực sự; nó cần IP hoặc DNS name mà máy ứng dụng có thể truy cập.

### 2.1. Sơ đồ hai nhóm mạng

~~~mermaid
flowchart LR
    subgraph CLIENT["Mạng ứng dụng"]
        APP["Java Driver"]
        CQL["cqlsh"]
    end
    subgraph CLUSTER["Mạng internode"]
        A["Node A"]
        B["Node B"]
        C["Node C"]
    end
    APP -->|"Native CQL / 9042"| A
    APP -->|"Native CQL / 9042"| B
    CQL -->|"Native CQL / 9042"| C
    A <-->|"Internode / 7000"| B
    B <-->|"Internode / 7000"| C
    C <-->|"Internode / 7000"| A
~~~

Sơ đồ đơn giản hóa giao tiếp logic. Trong thực tế, mỗi node có thể có **một hoặc nhiều network interface** và firewall riêng. Java Driver thường sử dụng nhiều node sau khi khám phá topology, không nhất thiết dồn mọi truy vấn vào một contact point.

## 3. Các tham số mạng trong cassandra.yaml

| Tham số | Lớp kết nối | Vai trò và lưu ý |
| --- | --- | --- |
| `listen_address` | Internode | Địa chỉ dùng cho giao tiếp node–node. **Không đặt `0.0.0.0`.** |
| `listen_interface` | Internode | Chọn interface thay cho IP; **không đặt đồng thời** với `listen_address`. |
| `broadcast_address` | Internode | Địa chỉ công bố cho node khác. Nếu không đặt, thường lấy theo `listen_address`. |
| `listen_on_broadcast_address` | Internode | Tùy chọn nghe thêm trên địa chỉ broadcast trong một số mạng nhiều interface; không cần trong mọi topology. |
| `storage_port` | Internode | Cổng trao đổi thông điệp giữa node; mặc định **7000/TCP**. |
| `ssl_storage_port` | Internode (legacy) | Cổng SSL kiểu cũ, thường **7001/TCP**, chỉ dùng theo cấu hình phiên bản tương ứng. |
| `rpc_address` | Client native | Địa chỉ bind native server cho Java Driver/cqlsh; có thể dùng `0.0.0.0` với điều kiện đúng. |
| `rpc_interface` | Client native | Chọn interface thay cho `rpc_address`; **không đặt đồng thời**. |
| `broadcast_rpc_address` | Client native | Địa chỉ công bố cho driver, cần tới được từ client; không được là `0.0.0.0`. |
| `start_native_transport` | Client native | Bật/tắt native transport. |
| `native_transport_port` | Client native | Cổng native CQL; mặc định **9042/TCP**. |
| `server_encryption_options` | Internode | Cấu hình TLS/mã hóa node–node. |
| `client_encryption_options` | Client native | Cấu hình TLS cho ứng dụng–node. |

Các thông số trên mô tả **Cassandra server**, thường đặt trong `cassandra.yaml` của từng node. Tên và tình trạng deprecated của một số tùy chọn có thể khác theo bản Cassandra. Cần đọc cấu hình và tài liệu đúng phiên bản trước khi sửa trên cluster đang hoạt động.

### 3.1. Internode: listen_address và broadcast_address

Ví dụ cấu hình tối thiểu **mang tính minh họa**:

~~~yaml
# Cassandra Node A, các IP chỉ là ví dụ trong tài liệu.
listen_address: 192.0.2.11
broadcast_address: 192.0.2.11
storage_port: 7000
~~~

- `listen_address` phải là **địa chỉ hợp lệ của node**, có thể bind trong hệ điều hành. Tài liệu Cassandra cảnh báo không đặt `listen_address: 0.0.0.0`.
- Nếu có `listen_interface`, hãy chọn **một trong hai** cách `listen_address` hoặc `listen_interface`; không cấu hình cả hai. Khi interface có nhiều địa chỉ, phải kiểm tra tùy chọn ưu tiên IPv4/IPv6 tương ứng.
- `broadcast_address` là địa chỉ các peer dùng để giao tiếp với node. Nếu bỏ trống, Cassandra thường lấy `listen_address`. Địa chỉ công bố phải được các node khác định tuyến tới được trên cổng internode.
- `listen_on_broadcast_address` có thể hữu ích trong một số cấu hình **hai interface vật lý**, khi node cần nghe cả trên địa chỉ broadcast và listen. Không bật máy móc nếu router/NAT đã xử lý tuyến tương ứng.

Các IP `192.0.2.x`, `198.51.100.x` và `203.0.113.x` trong bài thuộc **dải dành cho tài liệu minh họa**; chúng không phải địa chỉ để sao chép nguyên vào cluster thật.

Nếu chỉ chạy Cassandra trên laptop, `listen_address: localhost` có thể đủ. Khi thêm node thứ hai ở máy khác, địa chỉ loopback `127.0.0.1` không còn phù hợp vì **127.0.0.1 trên mỗi máy chỉ trỏ về chính máy đó**.

### 3.2. Native client: rpc_address và broadcast_rpc_address

~~~yaml
# Giả định Node A có interface cho mạng ứng dụng.
start_native_transport: true
native_transport_port: 9042
rpc_address: 198.51.100.11
broadcast_rpc_address: 198.51.100.11
~~~

Tên `rpc_address` có tính lịch sử; trong Cassandra hiện đại, nó điều khiển **địa chỉ bind của native CQL transport**. Cổng nhận CQL thường là `native_transport_port`, không phải `storage_port`. Nếu dùng `rpc_interface` để chọn card mạng thì không đồng thời đặt `rpc_address`.

Trường hợp muốn nghe trên nhiều interface:

~~~yaml
# Ví dụ một deployment có kiểm soát firewall.
rpc_address: 0.0.0.0
broadcast_rpc_address: 198.51.100.11
start_native_transport: true
native_transport_port: 9042
~~~

Đây là khác biệt quan trọng:

- `rpc_address: 0.0.0.0` **được phép** trong Cassandra, nhưng bắt buộc đặt `broadcast_rpc_address` thành **địa chỉ cụ thể**, khác `0.0.0.0`.
- `broadcast_rpc_address` không tự bật listener, TLS hay mở port. Driver phải thực sự kết nối tới được endpoint đã công bố.
- Bind trên mọi interface làm tăng bề mặt mạng có thể tiếp cận; cần giới hạn **security group/firewall** và thiết lập TLS, authentication, authorization theo nhu cầu.

**Không thay `broadcast_address` bằng `broadcast_rpc_address`:** một cái dành cho **peer Cassandra**, cái còn lại dành cho **client/driver**.

### 3.3. Các cổng mặc định cần biết

| Cổng | Đối tượng kết nối | Nên mở cho ai? | Ghi chú |
| --- | --- | --- | --- |
| `7000/TCP` | Node ↔ node | Chỉ các node Cassandra được cho phép | Thông điệp internode và streaming; chịu ảnh hưởng cấu hình mã hóa internode. |
| `7001/TCP` | Internode TLS kiểu cũ | Chỉ node khi deployment thực sự dùng | `ssl_storage_port` được đánh dấu deprecated từ Cassandra 4.0; nhiều cấu hình TLS hiện đại dùng cổng 7000. |
| `9042/TCP` | Driver/cqlsh ↔ node | Máy/service ứng dụng được phép | Native CQL; có thể mã hóa TLS ngay trên 9042. |
| `9142/TCP` | Native TLS trên cổng phụ, nếu cấu hình | Chỉ client cần thiết | `native_transport_port_ssl` không mặc định được bật, deprecated từ Cassandra 5.0. |
| `7199/TCP` | JMX/quản trị | Máy quản trị được cấp quyền | `nodetool` sử dụng JMX, không phải native CQL. |

Thay đổi số port mặc định là có thể, nhưng phải thay cả cấu hình mạng, firewall, thông số client và kiểm tra tương thích. Không xem `7000` hoặc `7199` là port để gửi CQL từ Java.

## 4. Kịch bản: cluster ba node, tách mạng internode và client

Giả sử môi trường có ba node, mỗi node có hai interface:

| Node | Địa chỉ internode (`listen`/`broadcast`) | Địa chỉ native client (`rpc`/`broadcast_rpc`) |
| --- | --- | --- |
| A | `192.0.2.11` | `198.51.100.11` |
| B | `192.0.2.12` | `198.51.100.12` |
| C | `192.0.2.13` | `198.51.100.13` |

Địa chỉ trong bảng dành cho giải thích, **không phải IP triển khai thật**. Các interface/route tương ứng phải thực sự tồn tại trước khi dùng một cấu hình tương đương.

Trên **Node A**:

~~~yaml
# Cụm ví dụ: mỗi node phải dùng IP riêng của chính mình.
listen_address: 192.0.2.11
broadcast_address: 192.0.2.11
storage_port: 7000

start_native_transport: true
native_transport_port: 9042
rpc_address: 198.51.100.11
broadcast_rpc_address: 198.51.100.11
~~~

Trên Node B và Node C, thay đúng các địa chỉ của từng node theo bảng trên. Đây là **trích đoạn cấu hình mạng**, không phải file `cassandra.yaml` đầy đủ; một cluster thực tế còn cần cluster name, seed provider, snitch, datacenter/rack, token allocation, auth/TLS, tài nguyên và nhiều thiết lập khác.

### 4.1. Một request đi qua những kết nối nào?

Giả sử ứng dụng Java gửi:

~~~sql
SELECT reading_time, value
FROM sensor_readings.readings_by_device_day
WHERE device_id = 'device-01'
  AND reading_day = '2026-11-21'
LIMIT 10;
~~~

Luồng có thể là:

1. Java Driver mở kết nối **native** đến Node B tại `198.51.100.12:9042`.
2. Node B làm **coordinator**, tính token từ partition key `(device_id, reading_day)`, xác định replica theo metadata ring và replication strategy.
3. Nếu cần trao đổi với Node A/C, coordinator dùng đường **internode** hướng tới `192.0.2.11:7000`, `192.0.2.13:7000` hoặc kết nối hiện có.
4. Coordinator tổng hợp phản hồi theo **consistency level** của truy vấn, trả dữ liệu cho driver qua kết nối native.

Node B có thể vừa là coordinator vừa là replica, tùy token của partition. Không có quy tắc “client kết nối Node B thì dữ liệu chỉ nằm Node B”. Replication factor và consistency quyết định số replica lưu dữ liệu và số phản hồi cần thiết cho thao tác; các địa chỉ mạng quyết định **có trao đổi được hay không**.

### 4.2. Seed nodes là gì?

`seed_provider` khai báo những **contact points internode ban đầu** để node mới tìm cluster và học topology. Seed là vai trò **khám phá**, không phải node chủ hay nơi lưu toàn bộ dữ liệu.

Trong nhiều bản Cassandra, `SimpleSeedProvider` có cấu hình danh sách các host/địa chỉ seed và, tùy phiên bản, có thể kèm cổng internode. Cần theo đúng cú pháp tài liệu phiên bản đang triển khai.

Các seed phải **định tuyến được bằng mạng internode**, không điền nhầm `broadcast_rpc_address` chỉ dành cho Java client. Không cần biến mọi node thành seed; nên chọn các seed ổn định và có kế hoạch phù hợp giữa datacenter.

## 5. NAT, container và địa chỉ có thể truy cập

### 5.1. Vì sao contact point hoạt động nhưng driver vẫn báo lỗi?

Ứng dụng thường bắt đầu với một hoặc vài **contact points**, sau đó Java Driver **khám phá topology** để kết nối nhiều node. Nếu node công bố địa chỉ native ở mạng mà ứng dụng không truy cập được, driver có thể khởi tạo kết nối ban đầu nhưng thất bại khi kết nối peer.

Ví dụ:

~~~text
Máy ứng dụng
  |-- kết nối contact point qua DNS:9042  --> thành công
  |-- driver nhận peer native endpoint: 10.0.8.22:9042
  |-- kết nối đến 10.0.8.22:9042         --> timeout
~~~

Nguyên nhân có thể là `broadcast_rpc_address` công bố IP của container/pod hoặc mạng riêng mà client bên ngoài không tới được; hoặc chính sách địa chỉ/port dịch chuyển qua NAT/proxy chưa phù hợp. Cách xử lý đúng là kiểm tra **endpoint mà driver thực sự khám phá**, route/firewall tới **từng node**, và dùng cơ chế address translation phù hợp nếu hệ thống có NAT.

Một TCP load balancer trước contact point **không tự động bảo đảm** driver có thể truy cập mọi peer được khám phá. Với Kubernetes, nên dựa trên chiến lược networking/operator/driver dành cho nền tảng; không tự đổi IP công bố của từng pod theo cách làm node mất liên lạc.

### 5.2. Ví dụ chỉ NAT ở phía client

Một node có mạng internode riêng và muốn công bố endpoint client qua NAT có thể cần cấu hình tương đương:

~~~yaml
listen_address: 10.20.0.11
broadcast_address: 10.20.0.11

rpc_address: 0.0.0.0
broadcast_rpc_address: 198.51.100.11
native_transport_port: 9042
~~~

Đây là **mô hình giải thích**, không phải cấu hình đủ để chạy: địa chỉ `198.51.100.11` là IP tài liệu, và khi triển khai thực sự phải có **NAT/routing/port forwarding** từ IP công bố tới listener của node, chính sách firewall/TLS và endpoint ổn định cho tất cả node. Cấu hình client NAT không đồng nghĩa tự động giải quyết NAT giữa các **peer internode**.

Nếu cần công bố địa chỉ khác cho các node ở nhiều site/datacenter, hãy xác nhận từ **mỗi node đến tất cả endpoint internode có liên quan**. Khi dùng mạng có IP bất đối xứng, hãy dựa trên khả năng hỗ trợ của phiên bản Cassandra, công cụ quản lý cluster và lớp mạng thực tế.

### 5.3. Tại sao không tùy tiện thay địa chỉ một node đã tham gia ring?

Địa chỉ internode có liên quan tới danh tính/gossip và metadata topology của cluster. Thay `listen_address` hoặc `broadcast_address` trên một node production rồi restart mà không có kế hoạch có thể khiến peer coi địa chỉ mới như một endpoint khác, làm node khó gia nhập ring hoặc ảnh hưởng khả năng định tuyến/replication.

Nếu cần chuyển node sang máy/IP khác, dùng **quy trình thay thế/decommission/bootstrap** phù hợp phiên bản Cassandra và trạng thái cluster, đồng thời kiểm tra host ID, token, seed, firewall và replication. Không coi thay IP internode là thao tác chỉnh một dòng YAML thông thường.

## 6. Kết nối giữa các node ảnh hưởng dữ liệu và consistency ra sao?

Địa chỉ internode không quyết định **partition key** hoặc **replication factor**, nhưng mạng internode không hoạt động có thể làm cluster không đáp ứng consistency của ứng dụng.

Ví dụ giả định một datacenter với **RF = 3**:

| Tình trạng | Ghi/đọc ở `ONE` | Ghi/đọc ở `LOCAL_QUORUM` |
| --- | --- | --- |
| Ba replica sẵn sàng | Có thể được đáp ứng | Có thể được đáp ứng nếu 2 replica phản hồi. |
| Một replica không sẵn sàng | Có thể được đáp ứng bởi 1 trong 2 replica còn lại | Có thể được đáp ứng nếu cả 2 replica còn lại phản hồi. |
| Chỉ một replica sẵn sàng | Có thể được đáp ứng trong điều kiện phù hợp | Không đủ 2 phản hồi để đạt quorum. |

Đây là ví dụ **đếm replica**, chưa xét mọi trường hợp timeout, failure hoặc topology đa datacenter. Một node `UN` trong `nodetool status` không bảo đảm mọi kết nối/latency internode và CQL đều tốt. Nếu mạng giữa một số node bị chia cắt, coordinator có thể báo `Unavailable`, `ReadTimeout` hoặc `WriteTimeout` tùy thao tác và CL.

Khi bootstrap, repair hay streaming SSTable, dữ liệu được chuyển qua kết nối **internode**. Vì vậy, cổng 9042 hoạt động không có nghĩa repair/streaming sẽ thành công. Ngược lại, internode tốt không chứng minh ứng dụng ngoài cluster kết nối được 9042.

### 6.1. TLS và bảo mật trên hai đường

~~~text
Ứng dụng ---- native CQL/TLS ----> Cassandra node
             client_encryption_options

Cassandra node ---- internode/TLS ----> Cassandra node
                   server_encryption_options
~~~

**`client_encryption_options`** bảo vệ kết nối **client ↔ server**; **`server_encryption_options`** bảo vệ kết nối **server ↔ server**. Bật một bên không tự bật bên kia. Internode TLS hiện đại có thể dùng `storage_port` 7000; `ssl_storage_port` 7001 là phương thức legacy ở nhiều bản 4.x/5.x. Cần phân biệt TLS với CQL authentication/authorization của ứng dụng.

Mạng production cần firewall giới hạn `7000` giữa các node được tin cậy, `9042` từ các máy ứng dụng được cấp phép và `7199` chỉ dành cho quản trị. Không mở cổng internode/JMX ra Internet để “khắc phục timeout”.

## 7. Thực hành chẩn đoán theo từng lớp kết nối

Làm theo thứ tự từ mạng tới Cassandra giúp xác định lỗi ở **địa chỉ bind**, **địa chỉ công bố**, **firewall**, **TLS**, **topology** hay **truy vấn CQL**.

### 7.1. Từ máy ứng dụng: DNS, TCP và cqlsh

Trên Linux/macOS:

~~~bash
# Kiểm tra có mở được kết nối TCP, chưa chứng minh CQL hoạt động.
nc -vz db-a.example.internal 9042

# Kiểm tra native CQL bằng client thực sự.
cqlsh db-a.example.internal 9042
~~~

Trên Windows PowerShell:

~~~powershell
Test-NetConnection -ComputerName db-a.example.internal -Port 9042
~~~

Trong cqlsh:

~~~sql
SHOW HOST;
SHOW VERSION;
SELECT cluster_name, data_center, release_version
FROM system.local;
~~~

Nếu kết nối TCP được nhưng `cqlsh` không vào được, tiếp tục kiểm tra **TLS**, **auth**, khả năng tương thích cqlsh/native protocol và logs trên server. Khi server yêu cầu TLS, phải dùng tùy chọn và truststore/chứng chỉ tương ứng, ví dụ:

~~~bash
cqlsh db-a.example.internal 9042 --ssl -u student
~~~

Không đưa mật khẩu vào câu lệnh shell hoặc file chia sẻ. `--ssl` không thay thế việc xác minh CA, hostname và chứng chỉ theo cấu hình thực tế.

### 7.2. Tại node Cassandra: listener và trạng thái ring

Chạy trên môi trường có quyền quản trị:

~~~bash
# Native transport trên node đã bật chưa?
nodetool statusbinary

# Các node được Cassandra nhìn thấy như thế nào?
nodetool status

# Thông tin gossip/endpoint (đầu ra phụ thuộc phiên bản).
nodetool gossipinfo

# Theo dõi tình trạng streaming khi bootstrap/repair.
nodetool netstats
~~~

Trên Linux có thể xem socket nào đang lắng nghe bằng:

~~~bash
ss -lnt
~~~

Kiểm tra địa chỉ/cổng trong kết quả `ss` và đối chiếu với `rpc_address`, `native_transport_port`, `listen_address` và `storage_port`. `nodetool statusbinary` phụ thuộc đường JMX và trả lời trạng thái native transport ở node được hỏi; `nodetool status` nói về ring, không phải phép thử TCP từ máy ứng dụng.

### 7.3. Kiểm tra đường internode giữa các node

Từ **Node B**, thử TCP tới **địa chỉ broadcast internode của Node A**:

~~~bash
# Ví dụ IP chỉ dùng cho tài liệu; thay bằng địa chỉ thực.
nc -vz 192.0.2.11 7000
~~~

Thử ngược lại từ A tới B và các cặp node liên quan. Nếu mở được TCP nhưng gossip/streaming vẫn lỗi, kiểm tra TLS server-to-server, chứng chỉ, internode authentication, cấu hình cluster và log. Một kết nối TCP đơn lẻ không chứng minh tất cả luồng dữ liệu hai chiều đã thông.

Với Cassandra 4.x+ nếu có các bảng metadata phù hợp, có thể kiểm tra qua cqlsh:

~~~sql
-- Cấu trúc và quyền truy cập system tables phụ thuộc phiên bản.
DESCRIBE TABLE system.local;
DESCRIBE TABLE system.peers_v2;
~~~

Bảng `system.peers_v2` có ở các phiên bản mới; nếu dùng Cassandra cũ hơn, kiểm tra `system.peers` và tài liệu của bản đang chạy. Không thao tác ghi trực tiếp vào các bảng hệ thống để “sửa IP”.

### 7.4. Lỗi nào cần xem ở lớp nào?

| Triệu chứng | Chẩn đoán ưu tiên | Hướng xử lý |
| --- | --- | --- |
| `Connection refused` trên 9042 | Native listener không chạy, bind sai IP/cổng, firewall từ chối | Kiểm tra `start_native_transport`, `rpc_address`, `native_transport_port`, trạng thái listener. |
| TCP 9042 timeout từ ứng dụng | Route, DNS, firewall, security group, NAT | Thử từ chính máy ứng dụng và từng endpoint công bố, không chỉ contact point. |
| `cqlsh` trên node được nhưng từ xa không được | `rpc_address: localhost`, firewall hoặc địa chỉ client | Kiểm tra listener có bind interface cho mạng ứng dụng chưa. |
| Driver vào được contact point rồi mất peer | `broadcast_rpc_address` không tới được hoặc local DC không khớp | Xem danh sách peer mà driver khám phá, tuyến tới từng native endpoint, policy driver. |
| Node B không thấy Node A dù cqlsh hoạt động | Internode `listen/broadcast`, `7000`, seed/gossip | Kiểm tra đường node–node và log gossip; native 9042 là lớp khác. |
| `listen_address: 0.0.0.0` làm node không khởi động hợp lệ | Địa chỉ internode không được phép dùng wildcard | Cấu hình IP/interface internode cụ thể. |
| `rpc_address: 0.0.0.0` mà thiếu `broadcast_rpc_address` | Node không có endpoint cụ thể để công bố client | Đặt địa chỉ công bố có thể định tuyến thực tế. |
| TLS handshake thất bại | Hai phía không thống nhất dùng TLS, CA/hostname sai | Kiểm tra riêng `client_encryption_options` hoặc `server_encryption_options` theo đường lỗi. |
| `Unauthorized` khi CQL đã kết nối | Thiếu quyền CQL trên role/keyspace/table | Kiểm tra authentication/authorization; không đổi port để chữa lỗi quyền. |
| `Unavailable` hoặc timeout khi quorum | Replica không đủ hoặc không phản hồi kịp | Kiểm tra `nodetool status`, internode network, RF, CL, logs và tải hệ thống. |
| Repair/streaming lỗi nhưng query thường vẫn chạy | Kết nối/throughput internode hoặc dung lượng/tài nguyên | Kiểm tra `nodetool netstats`, firewall, TLS, log và tải disk/network. |
| Đổi IP node rồi thấy endpoint/host ID không nhất quán | Thay địa chỉ thành viên ring không theo quy trình | Dừng thao tác tự phát; thực hiện quy trình thay thế/chuyển node đúng phiên bản. |

## 8. Thực hành CQL: mạng hoạt động rồi mới kiểm tra mô hình dữ liệu

Khi endpoint và cqlsh đã kết nối thành công, tiếp tục kiểm tra CQL. Lab dưới đây chỉ phù hợp với **môi trường đơn node** để luyện tập, nên dùng `SimpleStrategy` và RF = 1:

~~~sql
CREATE KEYSPACE IF NOT EXISTS network_lab
WITH replication = {
  'class': 'SimpleStrategy',
  'replication_factor': 1
};

CREATE TABLE IF NOT EXISTS network_lab.readings_by_device_day (
  device_id text,
  reading_day date,
  reading_time timestamp,
  reading_id uuid,
  value double,
  PRIMARY KEY ((device_id, reading_day), reading_time, reading_id)
) WITH CLUSTERING ORDER BY (reading_time DESC, reading_id ASC);

INSERT INTO network_lab.readings_by_device_day
  (device_id, reading_day, reading_time, reading_id, value)
VALUES ('device-01', '2026-11-21', '2026-11-21T01:00:00Z',
        11111111-1111-4111-8111-111111111111, 25.1);

INSERT INTO network_lab.readings_by_device_day
  (device_id, reading_day, reading_time, reading_id, value)
VALUES ('device-01', '2026-11-21', '2026-11-21T01:05:00Z',
        22222222-2222-4222-8222-222222222222, 25.3);

SELECT reading_time, value
FROM network_lab.readings_by_device_day
WHERE device_id = 'device-01'
  AND reading_day = '2026-11-21'
LIMIT 10;
~~~

Kỳ vọng có hai row, thời điểm `01:05` trước `01:00`. Điều kiện `WHERE` chỉ rõ **composite partition key** `(device_id, reading_day)`, giúp Cassandra định tuyến đến partition. Địa chỉ `listen/broadcast` và native port giúp **đường kết nối hoạt động**, nhưng không thay thế yêu cầu thiết kế bảng theo truy vấn.

Với hệ thống nhiều datacenter, nên dùng replication strategy phù hợp như `NetworkTopologyStrategy` và số replica theo datacenter thực. `RF = 1` trong lab không cho thấy hành vi quorum hoặc chịu lỗi nhiều node. Khi đánh giá consistency, cần kiểm tra đồng thời topology và mức phản hồi yêu cầu.

## 9. Kết nối từ Java Driver và kiểm tra topology

Ví dụ dùng API **Apache Cassandra Java Driver 4.x**. Trong deployment thực tế, thay contact points bằng **native addresses mà máy ứng dụng thực sự truy cập được** và thay tên local datacenter bằng giá trị tra được từ `system.local`:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;

import java.net.InetSocketAddress;
import java.time.LocalDate;

public class CassandraNetworkExample {
    public static void main(String[] args) {
        // Các địa chỉ IP thực tế phải truy cập được từ ứng dụng.
        // "datacenter1" chỉ là ví dụ, xác minh qua SELECT từ system.local.
        try (CqlSession session = CqlSession.builder()
                .addContactPoint(new InetSocketAddress("127.0.0.1", 9042))
                .withLocalDatacenter("datacenter1")
                .build()) {

            PreparedStatement prepared = session.prepare(
                "SELECT reading_time, value " +
                "FROM network_lab.readings_by_device_day " +
                "WHERE device_id = ? AND reading_day = ?");

            ResultSet result = session.execute(
                prepared.bind("device-01", LocalDate.of(2026, 11, 21)));

            for (Row row : result) {
                System.out.println(
                    row.getInstant("reading_time") + " => " +
                    row.getDouble("value"));
            }
        }
    }
}
~~~

Đoạn mã dành cho lab trên máy cục bộ. Khi chuyển sang cluster, cung cấp contact points là host/port native thực, ví dụ nhiều node trong **cùng datacenter** ứng dụng ưu tiên. Driver kết nối contact point để khám phá topology, rồi có thể tạo kết nối tới các peer đã công bố địa chỉ native. Việc đưa ba contact points không có nghĩa driver sẽ chỉ dùng đúng ba node đó.

**Chú ý:**

- `withLocalDatacenter(...)` phải khớp tên datacenter mà cluster thực sự báo. Sai tên có thể khiến driver bỏ qua node cần kết nối.
- Java Driver làm việc qua **9042/native CQL**, không nối vào `listen_address:7000` của internode.
- `CqlSession` nên có vòng đời dài trong ứng dụng, tái sử dụng cho nhiều truy vấn; ví dụ `try-with-resources` minh họa đóng session khi chương trình kết thúc.
- Dùng prepared statements/bind parameters để tránh ghép dữ liệu đầu vào thành chuỗi CQL.
- Nếu ứng dụng báo timeout sau khi đã kết nối thành công, phải xét **partition key**, RF, consistency, trạng thái replica và internode; chưa thể kết luận đó là lỗi `rpc_address`.

## 10. Bài tập tự thực hành

1. Giải thích bằng lời hai đường “Java Driver → coordinator” và “coordinator → replica”. Chỉ rõ port và nhóm địa chỉ dùng cho mỗi đường.
2. Trong cấu hình hai network interface, xác định vai trò của `listen_address`, `broadcast_address`, `rpc_address`, `broadcast_rpc_address`. Vì sao hai cặp không thể tùy ý tráo đổi?
3. Một node đặt `listen_address: 127.0.0.1` khi tham gia cluster hai máy. Dự đoán lỗi và đề xuất địa chỉ có thể dùng thay thế.
4. Giải thích vì sao `rpc_address: 0.0.0.0` cần `broadcast_rpc_address` cụ thể và vì sao không đặt `listen_address: 0.0.0.0`.
5. Mô tả quy trình xác minh từ máy ứng dụng đến node: DNS → TCP 9042 → cqlsh/TLS/auth → peer discovery → CQL. Khi nào cần chuyển sang kiểm tra 7000?
6. Trong kịch bản RF = 3, một replica không thể nhận thông điệp internode. Hãy tính số phản hồi cần cho `ONE` và `LOCAL_QUORUM`, rồi mô tả điều kiện để thao tác vẫn thành công.
7. Java Driver kết nối contact point thành công nhưng báo timeout với peer ở địa chỉ `10.0.8.22:9042`. Bạn cần xem cấu hình nào và kiểm tra kết nối từ đâu?
8. Giả sử chuẩn bị thay IP của một node production. Giải thích vì sao không nên chỉ sửa `broadcast_address` và restart; cần những bước quản lý topology nào?
9. Chạy CQL lab ở mục 8 sau khi kiểm tra endpoint. Giải thích vì sao truy vấn phải lọc đủ `(device_id, reading_day)` dù kết nối native đã thành công.

**Tiêu chí hoàn thành:** biết phân biệt và cấu hình đúng hai cặp địa chỉ listen/broadcast, xác định cổng cho từng loại kết nối, kiểm tra network từ đúng nguồn, giải thích được lỗi peer discovery và liên hệ lỗi mạng với replication/consistency của Cassandra.

## Tài liệu tham khảo

- [Apache Cassandra — cassandra.yaml configuration](https://cassandra.apache.org/doc/stable/cassandra/managing/configuration/cass_yaml_file.html): `listen_address`, `broadcast_address`, `rpc_address`, `broadcast_rpc_address`, `storage_port`, native transport và các tùy chọn TLS.
- [Apache Cassandra — Architecture](https://cassandra.apache.org/doc/stable/cassandra/architecture/overview.html): cấu trúc node/cluster, replication và client coordinator.
- [Apache Cassandra — Gossip](https://cassandra.apache.org/doc/stable/cassandra/architecture/gossip.html): cách các node học trạng thái thành viên cluster.
- [Apache Cassandra — nodetool](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/nodetool/nodetool.html): trạng thái node, native transport, gossip và streaming.
- [Apache Cassandra Java Driver 4.x — Core](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/index.html): contact points, local datacenter, metadata/topology và session.
