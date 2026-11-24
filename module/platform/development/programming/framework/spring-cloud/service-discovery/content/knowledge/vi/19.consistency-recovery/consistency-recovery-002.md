# Phân vùng mạng ảnh hưởng đến đăng ký và truy vấn như thế nào

## 1. Phân vùng mạng trong Service Discovery

Phân vùng mạng (network partition) xảy ra khi các thành phần vẫn đang chạy nhưng không thể trao đổi dữ liệu qua một phần mạng. Sự cố có thể chỉ ảnh hưởng một chiều, một subnet, một availability zone hoặc kết nối giữa các vùng địa lý. Vì vậy, “server đang sống” không đồng nghĩa “mọi client đều kết nối được tới server”.

Trong Spring Cloud Service Discovery, một phân vùng mạng có thể tác động đến nhiều đường giao tiếp:

- **Instance → Registry:** service không đăng ký mới được hoặc không cập nhật được metadata/trạng thái.
- **Instance → Registry (heartbeat):** instance đã đăng ký nhưng không gia hạn lease hoặc session được.
- **Registry peer → Registry peer:** các node registry không nhân bản thay đổi được.
- **Client → Registry:** client không truy vấn hoặc không nhận được bản cập nhật registry.
- **Client → Service instance:** client tìm thấy địa chỉ trong registry nhưng không thể kết nối tới instance.

Các đường giao tiếp này độc lập tương đối. Ví dụ, Eureka Server có thể truy cập được từ payment-service nhưng không truy cập được từ order-service; registry vẫn nhận heartbeat từ một nhóm instance trong khi nhóm khác bị mất kết nối. Một client có thể đọc được registry cache cũ nhưng không gọi được địa chỉ instance do NetworkPolicy hoặc route bị lỗi.

## 2. Tách control plane và data plane

Để chẩn đoán chính xác, hãy tách hai mặt phẳng:

- **Control plane của discovery:** đăng ký, heartbeat, health check, replication, truy vấn registry và cập nhật danh sách instance.
- **Data plane của request:** kết nối thực tế từ client đến host/port của instance, qua DNS, proxy, gateway, load balancer và network policy.

Discovery giúp tìm địa chỉ; nó không tạo ra đường mạng đến địa chỉ đó.

~~~mermaid
flowchart LR
    subgraph CP[Control plane]
        APP[Service instance] -->|register / heartbeat| REG[Registry]
        REG -->|replication / watch / fetch| PEER[Peer hoặc client cache]
        PEER --> DISC[DiscoveryClient]
    end
    subgraph DP[Data plane]
        CALL[Caller] --> LB[LoadBalancer]
        LB -->|host:port đã chọn| TARGET[Service instance]
    end
    DISC -.->|Danh sách địa chỉ| LB
~~~

Nếu control plane lỗi nhưng data plane còn thông, request hiện tại có thể tiếp tục chạy bằng danh sách instance đã biết. Ngược lại, discovery có thể báo instance UP trong khi data plane đã bị chia cắt và request thực tế thất bại.

## 3. Các dạng phân vùng và ảnh hưởng trực tiếp

| Phân vùng | Đăng ký và cập nhật | Truy vấn và gọi dịch vụ |
|---|---|---|
| Instance không tới được registry | Register/heartbeat thất bại hoặc timeout | Instance có thể chưa xuất hiện hoặc dữ liệu cũ còn tồn tại |
| Client không tới được registry | Registry vẫn có thể nhận đăng ký từ instance khác | Client tiếp tục dùng cache hoặc không cập nhật được danh sách |
| Registry peer không liên lạc được | Thay đổi không được nhân bản đầy đủ | Các node có thể trả về góc nhìn khác nhau |
| Client không tới được một instance | Registry có thể vẫn ghi instance UP | Lookup thành công nhưng kết nối request thất bại |
| Mất quorum của hệ thống registry | Các thao tác ghi có thể bị từ chối hoặc không tiến triển | Đọc có thể bị giới hạn, stale hoặc vẫn dùng cache tùy provider |
| Phân vùng một chiều | Một phía gửi được nhưng phản hồi không quay lại | Timeout và trạng thái quan sát giữa hai phía không giống nhau |

Không nên suy luận chỉ từ một timeout. Cần xác định cặp nguồn-đích, chiều kết nối, cổng, DNS, TLS và thành phần trung gian đang bị ảnh hưởng.

## 4. Điều gì xảy ra với đăng ký và heartbeat?

Khi instance khởi động, nó gửi thông tin đăng ký tới registry. Sau đó, provider thường duy trì sự hiện diện bằng heartbeat, lease, health check hoặc session. Nếu đường mạng bị chia cắt, một số tình huống có thể xảy ra:

1. **Đăng ký mới không tới registry:** tiến trình vẫn chạy nhưng chưa được client khác tìm thấy.
2. **Heartbeat bị mất:** registry có thể coi instance đã mất liên lạc sau một khoảng thời gian.
3. **Trạng thái health không cập nhật:** registry giữ trạng thái cũ vì không nhận được kết quả mới.
4. **Hủy đăng ký không gửi được:** instance đã dừng nhưng registry chưa nhận được thao tác deregister.
5. **Kết nối phục hồi:** client thử đăng ký hoặc gia hạn lại; registry cần thời gian cập nhật và client cần thời gian fetch/watch dữ liệu mới.

Một thao tác register timeout không luôn có nghĩa server chưa ghi dữ liệu. Request có thể đã tới server và được xử lý, nhưng response bị mất trên đường về. Khi retry, ứng dụng cần dựa vào định danh instance ổn định và semantics idempotent của provider để tránh tạo đăng ký trùng hoặc làm sai trạng thái.

## 5. Phân vùng mạng với Eureka

Eureka được thiết kế để hỗ trợ discovery khả dụng trong môi trường phân tán. Eureka Client duy trì registry cache cục bộ và thường tiếp tục cung cấp dữ liệu đã tải khi kết nối đến Eureka Server gặp vấn đề. Các node Eureka Server trao đổi thay đổi với peer theo cơ chế replication; đây là luồng cập nhật có độ trễ, không phải một giao dịch đồng bộ toàn cụm.

### 5.1. Client bị tách khỏi Eureka Server

Nếu một client không truy cập được Eureka Server:

- Client có thể tiếp tục tra cứu các instance trong registry cache cục bộ.
- Instance mới đăng ký ở server có thể chưa xuất hiện trong cache của client đó.
- Instance đã dừng có thể vẫn còn trong cache và được trả về trong lookup.
- Các lần fetch registry có thể thất bại cho đến khi kết nối phục hồi.

Vì vậy, DiscoveryClient.getInstances() trả về danh sách không rỗng không chứng minh registry vừa được truy vấn thành công. Dữ liệu có thể là bản cache gần nhất.

### 5.2. Heartbeat và self-preservation

Eureka Server theo dõi renewals của các instance. Khi số heartbeat nhận được giảm bất thường, cơ chế self-preservation có thể hạn chế eviction để tránh xóa hàng loạt instance chỉ vì sự cố mạng tạm thời.

Điều này giúp bảo vệ registry trước các đợt mất heartbeat diện rộng, nhưng có một đánh đổi: instance thực sự đã chết cũng có thể còn xuất hiện lâu hơn trong registry. Client khi đó có thể chọn địa chỉ stale và request thất bại.

Không nên tắt self-preservation như phản ứng đầu tiên khi thấy instance cũ. Trước hết, kiểm tra mạng giữa client và server, tỷ lệ heartbeat, log eviction, peer replication và hành vi của client cache. Chỉ điều chỉnh ngưỡng hoặc cơ chế eviction sau khi hiểu tác động lên toàn cụm.

### 5.3. Peer partition và góc nhìn registry khác nhau

Nếu các Eureka Server peer không trao đổi được, mỗi node có thể tạm thời có góc nhìn registry khác nhau. Một instance đăng ký với node A có thể chưa xuất hiện ở node B; client đọc từ hai node có thể thấy danh sách khác nhau.

Sau khi mạng phục hồi, replication và các chu kỳ fetch tiếp theo giúp dữ liệu hội tụ. Tuy nhiên, không nên giả định mọi node sẽ giống nhau ngay tại thời điểm đường mạng trở lại. Cần so sánh instance ID, host/port, status, metadata và timestamp gia hạn trên từng node.

### 5.4. Cấu hình và quan sát

Ví dụ một số tham số Eureka thường được kiểm tra:

~~~yaml
eureka:
  client:
    registry-fetch-interval-seconds: 30
  server:
    enable-self-preservation: true
    eviction-interval-timer-in-ms: 60000
~~~

Đây là cấu hình minh họa; giá trị mặc định và khả năng cấu hình phụ thuộc phiên bản Spring Cloud Netflix/Eureka. Chu kỳ fetch của client và chu kỳ eviction của server ảnh hưởng đến thời gian nhìn thấy thay đổi. Không cộng các chu kỳ này thành một giới hạn stale tuyệt đối vì retry, cache invalidation, replication và thời điểm phân vùng bắt đầu đều ảnh hưởng kết quả.

## 6. Phân vùng mạng với Consul

Consul có các vai trò khác nhau giữa agent và server:

- Consul agent chạy gần workload, quản lý service/check cục bộ và giao tiếp với Consul server.
- Consul server duy trì catalog và dùng Raft để đồng thuận các thay đổi cần commit.
- Gossip được dùng cho membership và failure detection; RPC giữa agent và server phục vụ các thao tác catalog và điều phối.

### 6.1. Agent mất kết nối đến server

Khi agent không thể liên lạc với Consul server, trạng thái service/check cục bộ và khả năng cập nhật catalog phía server có thể không còn đồng bộ. Service vẫn có thể chạy tại host nhưng các client ở nơi khác có thể không nhìn thấy thay đổi đăng ký hoặc health mới.

Khi kết nối phục hồi, agent và server cần trao đổi lại trạng thái. Hãy kiểm tra log agent, trạng thái check, catalog trên server và service registration tại đúng datacenter/namespace/partition đang sử dụng.

### 6.2. Mất quorum Raft

Consul server cần quorum để commit thay đổi catalog và duy trì trạng thái nhất quán. Nếu server cluster mất quorum, các thao tác ghi cần consensus có thể không tiến triển. Việc đọc phụ thuộc consistency mode và trạng thái server; một số truy vấn stale có thể trả dữ liệu cũ từ follower, trong khi truy vấn yêu cầu tính nhất quán cao cần leader/quorum.

Consul hỗ trợ các chế độ đọc có mức nhất quán khác nhau, chẳng hạn consistent và stale. Chọn stale read có thể tăng khả năng trả kết quả khi hệ thống gặp sự cố nhưng chấp nhận dữ liệu cũ hơn. Với quyết định nhạy cảm như thay đổi cấu hình hoặc thao tác cần trạng thái mới nhất, cần chính sách đọc phù hợp và xử lý lỗi khi không thể xác nhận trạng thái.

### 6.3. Health check không đồng nghĩa đường gọi thông suốt

Consul health check thường được thực hiện từ agent hoặc theo cấu hình check. Một check passing cho biết phép kiểm tra đó thành công từ vị trí của agent. Nó không bảo đảm mọi caller ở mọi subnet đều có thể kết nối tới instance.

Ví dụ, agent trong cùng host gọi được localhost:8080/health, nhưng caller ở subnet khác bị firewall chặn port 8080. Consul vẫn có thể hiển thị service passing trong khi request từ caller thất bại.

## 7. Phân vùng mạng với Kubernetes

Trong Kubernetes, Service Discovery có thể dựa vào Service, EndpointSlice, DNS và Kubernetes API. Nhiều thành phần liên quan đến trạng thái control plane:

- Kubelet báo trạng thái node và Pod về API server.
- EndpointSlice controller theo dõi Pod/Service và cập nhật endpoint.
- API server lưu trạng thái trong etcd.
- Các client dùng list/watch hoặc cache để theo dõi thay đổi.
- kube-proxy hoặc data plane như eBPF/mesh cập nhật đường chuyển tiếp traffic.

### 7.1. Workload mất kết nối đến API server

Pod có thể vẫn chạy và xử lý request hiện tại dù ứng dụng hoặc node tạm thời không truy cập được API server. Nhưng client dùng Spring Cloud Kubernetes để watch Service/EndpointSlice có thể không nhận được thay đổi mới; cache tại client có thể trở nên stale.

Nếu node bị tách khỏi control plane, kubelet không thể báo trạng thái mới. Control plane có thể tiếp tục thấy trạng thái cũ trong một khoảng thời gian trước khi đánh dấu node hoặc Pod không sẵn sàng theo các timeout và controller policy.

### 7.2. EndpointSlice và data plane

Khi readiness của Pod thay đổi, EndpointSlice controller cần quan sát thay đổi Pod và cập nhật điều kiện endpoint. Nếu controller hoặc API server không thể ghi nhận thay đổi, các consumer có thể giữ danh sách endpoint cũ.

Ngay cả khi EndpointSlice đã cập nhật, data plane trên node hoặc gateway vẫn cần nhận thay đổi. Nếu một node mất kết nối control plane nhưng vẫn còn traffic data plane, quy tắc forwarding cũ có thể tiếp tục được sử dụng trong thời gian đó.

Đây là lý do cần kiểm tra cả API object lẫn đường request thực tế. kubectl get endpointslices cho biết trạng thái control plane đang lưu; nó không chứng minh mọi proxy hoặc client đã nhận phiên bản mới.

### 7.3. Mất quorum etcd

Kubernetes control plane phụ thuộc etcd để lưu trạng thái cluster. etcd dùng quorum để commit thay đổi. Nếu mất quorum, các thao tác ghi trạng thái cluster không thể tiếp tục bình thường; API server có thể trả lỗi hoặc timeout cho các thao tác cần ghi.

Workload đang chạy trên node vẫn có thể tiếp tục hoạt động trong khi control plane không thể cập nhật Deployment, Pod condition hoặc EndpointSlice. Các thao tác rollout và recovery dựa trên API có thể bị trì hoãn cho đến khi quorum được khôi phục.

## 8. Phân vùng mạng với ZooKeeper

Spring Cloud Zookeeper Discovery sử dụng znodes và session để biểu diễn đăng ký service. Đăng ký thường gắn với ephemeral znode thuộc session của client.

Khi client mất kết nối:

- Client có thể vào trạng thái suspended hoặc disconnected tùy client library.
- Nếu session vẫn còn hiệu lực và kết nối được phục hồi, client có thể tiếp tục session.
- Nếu session hết hạn, ephemeral znode được xóa khỏi ensemble.
- Khi tạo session mới, ứng dụng cần đăng ký lại instance.

Không nên coi việc TCP disconnect là thời điểm ephemeral znode bị xóa ngay. Znode chỉ bị loại khi ensemble xác định session đã hết hạn. Vì vậy, trong thời gian mạng phân vùng, client khác có thể vẫn nhìn thấy đăng ký cũ.

Nếu các ZooKeeper server mất quorum, ensemble không thể commit thay đổi mới. Một số node có thể vẫn trả lời các thao tác đọc theo trạng thái cục bộ, nhưng không thể đảm bảo tiến trình ghi và đồng bộ quorum. Khi khôi phục, cần xác nhận leader/follower, session và znode đăng ký.

## 9. Client cache và dữ liệu stale

Nhiều discovery provider hoặc thư viện client giữ dữ liệu cục bộ để tránh gọi registry cho mỗi request. Spring Cloud LoadBalancer cũng có thể cache danh sách instance tùy supplier và cấu hình.

Trong phân vùng mạng, client có thể gặp các trạng thái:

| Dữ liệu client | Ý nghĩa |
|---|---|
| Cache còn instance UP | Instance từng được nhìn thấy; chưa chắc còn sống hoặc reachable |
| Cache không có instance mới | Client chưa nhận đăng ký mới hoặc watch/fetch bị gián đoạn |
| Cache có instance nhưng status cũ | Thay đổi health hoặc deregister chưa đến client |
| Cache hết hạn hoặc bị làm mới thất bại | Hành vi phụ thuộc provider; client có thể giữ dữ liệu cũ hoặc không trả kết quả |
| DiscoveryClient báo lỗi | Truy vấn hoặc phép probe thất bại; cần phân biệt với kết quả hợp lệ rỗng |

Không nên chuyển mọi lỗi truy vấn thành danh sách rỗng. Điều đó làm mất khả năng phân biệt:

- **Không có instance:** registry trả lời thành công nhưng service chưa có instance.
- **Không thể truy vấn:** provider, mạng hoặc quyền truy cập đang lỗi.
- **Có dữ liệu cache:** client trả về dữ liệu gần nhất nhưng chưa xác minh được trạng thái hiện tại.

### 9.1. Chọn chính sách khi registry không truy cập được

Chính sách phù hợp tùy loại request:

- Nếu service có thể tiếp tục xử lý với instance đã cache, cho phép dùng dữ liệu gần nhất trong một giới hạn thời gian và vẫn có timeout/retry cho request.
- Nếu thao tác cần trạng thái mới nhất, có thể từ chối hoặc trả lỗi có kiểm soát khi không xác minh được registry.
- Nếu service không có instance, trả lỗi rõ ràng hoặc áp dụng fallback nghiệp vụ đã thiết kế.
- Nếu dùng stale instance, xử lý connection failure và không retry vô hạn vào cùng một địa chỉ.

Không có một lựa chọn stale/fail-fast phù hợp cho mọi service. Hãy xác định hậu quả nghiệp vụ nếu gọi nhầm instance cũ hoặc nếu tạm thời từ chối request.

## 10. Ví dụ tình huống end-to-end

Giả sử ba instance inventory-service đang chạy ở ba node. Một phân vùng mạng làm mất kết nối giữa node của instance A và registry, đồng thời client ở zone-b không thể truy cập instance A.

1. Instance A vẫn chạy nhưng heartbeat không tới registry.
2. Registry chưa chắc xóa A ngay; cơ chế lease, health check hoặc self-preservation quyết định thời điểm thay đổi.
3. Client zone-b vẫn có thể giữ địa chỉ A trong cache.
4. Lookup trả về A nhưng request tới A timeout do đường data plane bị chia cắt.
5. Các instance B và C vẫn có thể phục vụ nếu registry và mạng giữa chúng còn hoạt động.
6. Khi kết nối phục hồi, A gửi lại heartbeat hoặc đăng ký lại tùy provider/session.
7. Client cập nhật danh sách sau replication, fetch/watch và cache refresh.

~~~mermaid
sequenceDiagram
    participant A as inventory A
    participant R as Registry
    participant C as Client zone-b
    participant B as inventory B
    Note over A,R: Network partition
    A-xR: heartbeat / register
    C->>R: Query hoặc đọc cache
    R-->>C: Instance list có thể còn A
    C-xA: Request tới A timeout
    C->>B: Retry có giới hạn / chọn instance khác
    Note over A,R: Network restored
    A->>R: Heartbeat hoặc đăng ký lại
    R-->>C: Thay đổi được đồng bộ dần
    C->>B: Các request tiếp tục theo danh sách cập nhật
~~~

Retry sang B chỉ an toàn nếu request có thể retry và nghiệp vụ xử lý idempotency. Với thao tác tạo thanh toán hoặc ghi dữ liệu, cần idempotency key hoặc cơ chế chống xử lý lặp.

## 11. Recovery sau khi mạng phục hồi

Khi đường mạng trở lại, không nên giả định toàn bộ trạng thái tự đồng bộ ngay lập tức. Hãy phục hồi theo từng lớp:

1. **Khôi phục kết nối:** xác minh DNS, route, firewall, TLS và kết nối hai chiều giữa các node.
2. **Khôi phục quorum:** với Consul, ZooKeeper hoặc etcd, xác nhận leader và quorum ổn định trước khi thao tác ghi lớn.
3. **Khôi phục replication:** kiểm tra peer/agent có đồng bộ được dữ liệu và không còn lỗi liên lạc.
4. **Khôi phục đăng ký:** xác nhận instance đang chạy đã heartbeat hoặc đăng ký lại; instance đã dừng được deregister/evict.
5. **Làm mới client:** xác nhận fetch/watch hoạt động và client cache nhận trạng thái mới.
6. **Làm mới LoadBalancer:** kiểm tra supplier/cache và chính sách chọn instance.
7. **Xác minh data plane:** gửi request thực tế tới các instance còn hợp lệ và kiểm tra latency/error rate.
8. **Đối chiếu trạng thái:** so sánh số instance, instance ID, host/port, status và metadata trên registry với workload đang chạy.

Không xóa thủ công hàng loạt instance chỉ vì registry có bản ghi cũ. Trước khi can thiệp, xác định instance đó còn hoạt động hay không, có đang trong quá trình reconnect hoặc rollout hay không và provider có cơ chế tự phục hồi nào.

## 12. Bảng chẩn đoán theo triệu chứng

| Triệu chứng | Lớp cần kiểm tra đầu tiên | Bằng chứng nên thu thập |
|---|---|---|
| Instance chạy nhưng không xuất hiện | Register path / quyền / mạng tới registry | Log register, DNS, TCP/TLS, catalog hoặc registry API |
| Instance cũ vẫn còn sau khi dừng | Heartbeat, lease, health check, session hoặc eviction | Last renewal, check status, session state, eviction log |
| Hai node registry trả danh sách khác nhau | Peer replication hoặc quorum | Peer status, leader, replication log, thời điểm cập nhật |
| DiscoveryClient trả danh sách cũ | Client cache, fetch/watch | Lần fetch/watch thành công gần nhất, cache TTL, provider log |
| Lookup có instance nhưng request timeout | Data plane | Route, NetworkPolicy, firewall, port, TLS và packet flow |
| Consul không nhận thay đổi catalog | Raft quorum hoặc agent-server RPC | Leader/quorum, agent log, RPC errors |
| Kubernetes EndpointSlice không cập nhật | API server, etcd hoặc controller | Pod condition, controller logs, API errors, etcd health |
| ZooKeeper registration biến mất | Session expiration hoặc mất quorum | Session state, ephemeral znode, leader/follower |

## 13. Runbook kiểm tra phân vùng mạng

Khi có cảnh báo discovery bất thường, thực hiện theo trình tự:

1. Ghi lại thời điểm bắt đầu, service ID, instance ID, client source và registry node liên quan.
2. Xác định phân vùng ảnh hưởng register, heartbeat, peer replication, client query hay request tới instance.
3. Kiểm tra kết nối từ đúng workload/container; kiểm tra cả chiều đi và chiều về.
4. Đối chiếu registry ở nhiều node hoặc nhiều datacenter nếu provider có topology đó.
5. Kiểm tra heartbeat/lease/session và trạng thái health.
6. Đối chiếu client cache với dữ liệu server; ghi nhận timestamp của lần fetch/watch thành công.
7. Gọi trực tiếp health endpoint và port của instance từ mạng của caller.
8. Khôi phục mạng hoặc quorum trước khi ép đồng bộ hoặc xóa registry entry.
9. Sau phục hồi, xác nhận registry hội tụ và client/load balancer dùng danh sách đúng.
10. Theo dõi error rate, timeout và retry để bảo đảm hệ thống không còn dùng endpoint stale.

## 14. Thiết kế để chịu được phân vùng mạng

### 14.1. Định danh instance ổn định

Mỗi instance cần có định danh phù hợp với provider để register, heartbeat và deregister có thể nhận diện cùng một bản ghi. Khi retry register sau timeout, không tạo định danh ngẫu nhiên mới nếu điều đó khiến registry tích lũy nhiều bản ghi stale.

### 14.2. Timeout và retry có giới hạn

Đặt connect timeout, request timeout và retry budget cho thao tác discovery. Dùng backoff và jitter để nhiều client không cùng retry theo một nhịp sau khi mạng phục hồi. Retry không làm một request chắc chắn an toàn; cần xem xét idempotency của thao tác nghiệp vụ.

### 14.3. Cache có chính sách rõ ràng

Xác định thời gian chấp nhận dữ liệu discovery cũ, cách xử lý khi refresh thất bại và thời điểm chuyển sang fail-fast. Không giữ endpoint stale vô hạn mà không có metric hoặc cảnh báo.

### 14.4. Không biến discovery thành điểm phụ thuộc duy nhất

Nếu có thể, dùng service DNS ổn định, cache có giới hạn hoặc fallback đã được thiết kế để giảm tác động của lỗi registry. Tuy nhiên, fallback chỉ có ích nếu địa chỉ thay thế vẫn truy cập được và dữ liệu nghiệp vụ nhất quán.

### 14.5. Tách readiness khỏi liveness

Registry tạm thời không truy cập được không nhất thiết có nghĩa tiến trình phải restart. Dùng readiness để ngừng nhận request khi thật sự không thể phục vụ; dùng liveness để phát hiện tiến trình bị kẹt hoặc không thể tự phục hồi. Tránh restart đồng loạt mọi service khi registry gặp sự cố diện rộng.

### 14.6. Giám sát theo từng đường giao tiếp

Theo dõi riêng register errors, heartbeat failures, peer replication lag, client fetch/watch failures, cache age, lookup result, request connection errors và health check failures. Một chỉ số “registry UP” duy nhất không đủ mô tả tình trạng của toàn bộ đường discovery.

## 15. Kiểm thử phân vùng mạng

Nên thử nghiệm có kiểm soát trong môi trường staging hoặc chaos test:

- Chặn kết nối từ một instance đến registry trong một khoảng thời gian.
- Chặn client truy vấn registry nhưng giữ kết nối data plane.
- Chặn kết nối giữa các peer registry.
- Mất quorum của Consul, ZooKeeper hoặc etcd trong môi trường thử nghiệm phù hợp.
- Chặn client đến một instance nhưng giữ registry hoạt động.
- Khôi phục mạng và đo thời gian hội tụ của registry, client cache và LoadBalancer.

Các kết quả cần ghi nhận:

| Kịch bản | Câu hỏi cần trả lời |
|---|---|
| Mất register | Instance có bị xem là sẵn sàng quá sớm không? |
| Mất heartbeat | Bao lâu registry đổi trạng thái hoặc loại instance? |
| Mất client fetch | Client dùng cache bao lâu và sau đó xử lý ra sao? |
| Mất peer link | Registry có trả kết quả khác nhau giữa các node không? |
| Mất data-plane path | Caller có timeout, retry và chọn instance khác đúng cách không? |
| Phục hồi mạng | Bao lâu các node và client hội tụ? Có đăng ký trùng không? |

Không chạy thử nghiệm chặn mạng trên production nếu chưa có kế hoạch cô lập, phạm vi ảnh hưởng và phương án phục hồi được phê duyệt.

## 16. Tổng kết

Phân vùng mạng có thể làm hỏng riêng từng đường giao tiếp của Service Discovery: đăng ký, heartbeat, peer replication, truy vấn registry hoặc kết nối đến instance. Vì thế, một instance có thể vẫn chạy nhưng chưa được đăng ký; registry có thể giữ bản ghi stale; client có thể lookup thành công từ cache nhưng request thực tế timeout.

Eureka thường tiếp tục phục vụ client bằng registry cache và có self-preservation để hạn chế eviction khi heartbeat giảm bất thường. Consul và ZooKeeper cần quorum cho các thay đổi nhất quán của cụm; Kubernetes phụ thuộc API server, controller và etcd để cập nhật trạng thái control plane. Mỗi provider có cách đọc, cache và phục hồi riêng, nên cần xác minh theo đúng implementation và phiên bản.

Khi xử lý sự cố, hãy tách control plane khỏi data plane, xác định chính xác cặp thành phần bị chia cắt, đối chiếu trạng thái server với client cache và kiểm tra request thực tế. Sau khi mạng phục hồi, xác nhận quorum, replication, đăng ký, client fetch và LoadBalancer cache đã hội tụ trước khi kết luận hệ thống ổn định.
