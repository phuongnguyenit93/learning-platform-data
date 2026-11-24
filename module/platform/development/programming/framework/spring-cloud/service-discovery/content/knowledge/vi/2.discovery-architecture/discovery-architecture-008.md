# Vai trò của DNS, bộ định tuyến và service mesh trong khám phá

## Mục tiêu

Sau bài học này, bạn có thể:

- Phân biệt phân giải tên dịch vụ, khám phá instance và định tuyến request.
- Giải thích DNS giúp ứng dụng tìm địa chỉ dịch vụ như thế nào và những giới hạn của DNS.
- Mô tả cách router, reverse proxy và load balancer chọn đích cho request.
- Giải thích service mesh khám phá endpoint và điều khiển lưu lượng giữa các service ra sao.
- Chọn cách kết hợp DNS, registry, router và mesh phù hợp với môi trường triển khai.

## 1. Ba câu hỏi khác nhau trong service discovery

Khi một ứng dụng cần gọi dịch vụ khác, có ba câu hỏi liên quan nhưng không đồng nhất:

1. **Tên dịch vụ phân giải thành địa chỉ nào?** Ví dụ, tên inventory.internal cần được ánh xạ thành một IP hoặc một điểm truy cập.
2. **Request sẽ đi đến instance nào?** Một dịch vụ có thể có nhiều instance; hệ thống cần chọn một đích còn khả năng phục vụ.
3. **Request được chuyển tiếp và kiểm soát như thế nào?** Hệ thống có thể áp dụng routing rule, cân bằng tải, timeout, retry, xác thực và quan sát lưu lượng.

DNS thường giải quyết câu hỏi thứ nhất. Router hoặc load balancer thường tham gia câu hỏi thứ hai và thứ ba. Service mesh cung cấp một lớp hạ tầng cho việc khám phá endpoint và điều khiển giao tiếp giữa các service. Trong khi đó, registry như Eureka hoặc Consul lưu thông tin instance và cung cấp API để các thành phần khác tra cứu.

Không phải hệ thống nào cũng có đủ cả bốn thành phần. Một ứng dụng có thể gọi một địa chỉ DNS ổn định trỏ đến load balancer; một nền tảng khác có thể dùng registry để client tự chọn instance; Kubernetes có thể kết hợp DNS, Service, EndpointSlice và proxy mạng; service mesh có thể lấy dữ liệu endpoint từ API của nền tảng rồi phân phối cấu hình đến proxy.

## 2. DNS: ánh xạ tên dịch vụ thành địa chỉ

DNS (Domain Name System) là hệ thống phân giải tên. Thay vì cấu hình IP trực tiếp trong mã nguồn, ứng dụng gọi một hostname như inventory.internal. DNS resolver truy vấn bản ghi tương ứng và trả về địa chỉ IP hoặc thông tin đích khác.

Luồng đơn giản:

~~~~mermaid
sequenceDiagram
    participant App as Ứng dụng gọi
    participant Resolver as DNS Resolver
    participant DNS as DNS Server
    participant Target as Địa chỉ dịch vụ
    App->>Resolver: Phân giải inventory.internal
    Resolver->>DNS: Truy vấn bản ghi
    DNS-->>Resolver: A/AAAA hoặc CNAME
    Resolver-->>App: Địa chỉ được phân giải
    App->>Target: Kết nối đến địa chỉ
~~~~

Các loại bản ghi thường gặp:

| Bản ghi | Vai trò |
| --- | --- |
| A | Ánh xạ hostname sang địa chỉ IPv4. |
| AAAA | Ánh xạ hostname sang địa chỉ IPv6. |
| CNAME | Tạo bí danh trỏ đến một hostname khác. |
| SRV | Công bố hostname và port của dịch vụ theo một tên service/protocol. |

### DNS có thể trỏ đến một địa chỉ ổn định hoặc nhiều địa chỉ

Một hostname có thể trỏ đến địa chỉ ảo của load balancer. Khi đó client chỉ cần biết tên dịch vụ; load balancer chịu trách nhiệm chọn backend instance. Đây là mô hình phổ biến vì IP backend có thể thay đổi mà client không cần cập nhật cấu hình.

DNS cũng có thể trả về nhiều bản ghi A hoặc AAAA cho cùng hostname. Một số resolver hoặc client phân phối kết quả theo kiểu round-robin. Tuy nhiên, việc trả nhiều IP không tự động bảo đảm mọi IP đều khỏe, có thể truy cập từ client hoặc có tải tương đương. Cơ chế chọn IP và thử lại phụ thuộc resolver, thư viện HTTP và cấu hình ứng dụng.

### DNS trong Kubernetes

Trong Kubernetes, DNS cluster thường cung cấp hostname cho Service. Ví dụ, một service tên inventory trong namespace commerce có thể được truy cập bằng:

~~~~text
inventory.commerce.svc.cluster.local
~~~~

Tên ngắn hơn như inventory.commerce hoặc inventory có thể dùng được tùy namespace và search domain của Pod. Với Service kiểu ClusterIP, DNS thường phân giải tên Service thành ClusterIP ổn định. Lưu lượng đến ClusterIP sau đó được chuyển tới một backend Pod phù hợp thông qua cơ chế mạng của cluster.

Với headless Service (clusterIP: None), DNS có thể trả về địa chỉ của các Pod endpoint thay vì một ClusterIP dùng chung. Cách này hữu ích khi client cần biết từng endpoint, chẳng hạn một số hệ thống stateful. Client phải xử lý danh sách địa chỉ và vòng đời endpoint phù hợp.

### Giới hạn của DNS

- **TTL và cache:** resolver, runtime hoặc thư viện có thể cache kết quả. Khi endpoint thay đổi, client có thể tiếp tục dùng địa chỉ cũ cho đến khi cache hết hạn hoặc được làm mới.
- **Health awareness:** bản ghi DNS không nhất thiết phản ánh sức khỏe ứng dụng theo thời gian thực. Một địa chỉ còn trong DNS chưa chắc nhận được request thành công.
- **Độ chi tiết:** DNS thường cung cấp hostname và địa chỉ; nó không mô tả đầy đủ metadata, phiên bản, zone, trọng số hay trạng thái circuit breaker của từng instance.
- **Lựa chọn endpoint:** trả về nhiều IP không đồng nghĩa đã có thuật toán load balancing nhất quán giữa các client.
- **Phạm vi mạng:** địa chỉ được phân giải phải truy cập được từ nơi gọi. Một IP nội bộ có thể không dùng được từ mạng bên ngoài cluster.

DNS phù hợp để cung cấp tên ổn định, dễ cấu hình và tương thích với hầu hết client. Khi cần chọn instance theo sức khỏe, metadata hoặc chính sách traffic phức tạp, thường cần thêm registry, load balancer hoặc service mesh.

## 3. Router và load balancer: chọn đích và chuyển tiếp request

Trong ngữ cảnh service discovery, router là thành phần nhận request và quyết định request được chuyển đến backend nào. Tùy lớp mạng, router có thể hoạt động ở L4 (TCP/UDP) hoặc L7 (HTTP/gRPC). Reverse proxy, ingress controller, API gateway và load balancer đều có thể đảm nhiệm một phần vai trò này.

Một router thường có địa chỉ hoặc hostname ổn định ở phía client. Nó duy trì hoặc nhận cấu hình danh sách backend, kiểm tra sức khỏe endpoint và áp dụng thuật toán chọn đích. Backend có thể được khai báo tĩnh, lấy từ DNS, lấy từ registry như Eureka/Consul hoặc nhận từ control plane của nền tảng.

~~~~mermaid
flowchart LR
    C[Client] -->|inventory.internal| D[DNS]
    D -->|Địa chỉ VIP| LB[Router / Load Balancer]
    LB -->|Chọn backend| I1[Inventory instance A]
    LB -->|Chọn backend| I2[Inventory instance B]
    LB -->|Chọn backend| I3[Inventory instance C]
~~~~

### Các kiểu định tuyến thường gặp

| Kiểu | Cách hoạt động | Ví dụ sử dụng |
| --- | --- | --- |
| L4 load balancing | Chuyển tiếp kết nối TCP/UDP dựa trên thông tin mạng và transport. | Cân bằng kết nối đến một nhóm backend. |
| L7 routing | Đọc thông tin ứng dụng như host, path, header hoặc method để chọn route. | /orders đến order-service, /inventory đến inventory-service. |
| API gateway | Cung cấp điểm vào API, định tuyến đến nhiều service và thường áp dụng xác thực, giới hạn tốc độ hoặc chuyển đổi request. | Client bên ngoài gọi các API microservice qua một cổng chung. |
| Ingress controller | Điều khiển truy cập HTTP/HTTPS từ ngoài vào các Service trong Kubernetes. | Công bố ứng dụng web qua hostname và path. |
| Internal load balancer | Phân phối lưu lượng nội bộ giữa các instance. | Một service gọi service khác qua địa chỉ nội bộ ổn định. |

### Router lấy danh sách backend từ đâu?

Có nhiều cách cung cấp backend:

- **Cấu hình tĩnh:** địa chỉ backend được khai báo trong file cấu hình. Cách này dễ hiểu nhưng khó theo kịp instance thay đổi thường xuyên.
- **DNS:** router phân giải hostname backend định kỳ. Cần chú ý TTL và cách router refresh DNS.
- **Registry:** router hoặc adapter truy vấn Eureka/Consul để lấy danh sách instance, metadata và trạng thái đăng ký.
- **Nền tảng điều phối:** trong Kubernetes, controller hoặc proxy có thể nhận endpoint từ Service và EndpointSlice thông qua API/control plane.

Router có thể thực hiện health check độc lập với registry. Registry cho biết instance đã đăng ký; health check của router xác định backend có phản hồi theo tiêu chí vận hành của router hay không. Hai trạng thái này có thể lệch nhau trong một khoảng thời gian.

### Ví dụ định tuyến theo path

Một API gateway có thể định tuyến:

~~~~text
/api/orders/**     -> order-service
/api/inventory/**  -> inventory-service
/api/payments/**   -> payment-service
~~~~

Client bên ngoài chỉ cần biết hostname của gateway. Gateway phân tích request và chọn đích theo route đã cấu hình. Địa chỉ instance cụ thể có thể do load balancer, registry integration hoặc nền tảng mạng quyết định.

Điểm cần nhớ: gateway không nhất thiết là registry. Gateway thường dùng dữ liệu định tuyến được cấu hình hoặc được đồng bộ từ một nguồn discovery khác. Cũng không phải mọi request nội bộ đều nên đi qua API gateway công khai; giao tiếp east-west giữa service thường có lựa chọn khác.

## 4. Service mesh: khám phá và điều khiển giao tiếp east-west

Service mesh là lớp hạ tầng chuyên quản lý giao tiếp giữa các service. Trong mô hình sidecar phổ biến, mỗi workload có một proxy đi kèm. Ứng dụng gửi request qua proxy cục bộ; proxy thực hiện kết nối đến proxy hoặc workload đích theo cấu hình nhận từ control plane.

Service mesh thường tách thành hai phần:

- **Data plane:** các proxy xử lý lưu lượng thực tế. Proxy có thể thực hiện chọn endpoint, cân bằng tải, timeout, retry, circuit breaking, xác thực và thu thập telemetry.
- **Control plane:** thu thập thông tin service/endpoint từ nền tảng hoặc registry, áp dụng policy và phân phối cấu hình đến proxy.

~~~~mermaid
flowchart TB
    subgraph Control[Control plane]
        K8s[Kubernetes API / Registry]
        CP[Mesh Control Plane]
        K8s --> CP
    end
    subgraph Data[Data plane]
        A[Ứng dụng A] --> PA[Proxy A]
        PA -->|Request east-west| PB[Proxy B]
        PB --> B[Ứng dụng B]
    end
    CP -->|Endpoint và policy| PA
    CP -->|Endpoint và policy| PB
~~~~

Khi ứng dụng A gọi inventory-service, proxy A có thể nhận tên đích logic. Proxy dùng cấu hình endpoint mới nhất để chọn một instance của inventory-service, thiết lập kết nối và áp dụng chính sách. Ứng dụng có thể không cần trực tiếp truy vấn Eureka hoặc Consul trong mỗi request.

### Service mesh khám phá endpoint như thế nào?

Mesh cần một nguồn dữ liệu để biết service và endpoint tồn tại. Nguồn đó có thể là:

- Kubernetes API, gồm Service, Pod và EndpointSlice.
- Registry bên ngoài như Consul hoặc Eureka, thông qua tích hợp phù hợp.
- Cấu hình endpoint được khai báo hoặc đồng bộ từ hệ thống điều khiển khác.

Control plane chuyển thông tin đó thành cấu hình mà proxy hiểu. Với Envoy, một cách phân phối cấu hình động phổ biến là xDS; endpoint discovery có thể được gửi qua Endpoint Discovery Service (EDS). Tên giao thức và cách tích hợp cụ thể phụ thuộc sản phẩm mesh và phiên bản.

Vì vậy, mesh không tự tạo ra danh sách instance từ hư không. Nó cần một nguồn sự thật về service và endpoint, sau đó phân phối thông tin đến data plane. Nếu nguồn dữ liệu chậm cập nhật hoặc control plane mất kết nối, proxy có thể tiếp tục dùng cấu hình endpoint cũ trong một khoảng thời gian.

### Mesh cung cấp gì ngoài discovery?

- Cân bằng tải giữa các endpoint và có thể áp dụng locality-aware routing.
- Timeout, retry và circuit breaking theo policy.
- Mã hóa và xác thực workload, thường thông qua mTLS và service identity.
- Quan sát lưu lượng như request rate, latency, error rate và trace context.
- Canary, traffic splitting hoặc định tuyến theo phiên bản khi sản phẩm mesh hỗ trợ.
- Policy giao tiếp giữa workload, ví dụ service nào được phép gọi service nào.

Mesh có chi phí vận hành: proxy tiêu thụ CPU/bộ nhớ, thêm một lớp xử lý request và yêu cầu quản lý control plane, chứng thư, policy cùng cấu hình mạng. Không nên triển khai mesh chỉ vì cần phân giải một hostname đơn giản.

## 5. So sánh DNS, router và service mesh

| Tiêu chí | DNS | Router / Load balancer | Service mesh |
| --- | --- | --- | --- |
| Nhiệm vụ chính | Phân giải tên thành địa chỉ hoặc thông tin dịch vụ | Chọn backend và chuyển tiếp request | Quản lý giao tiếp service-to-service và policy traffic |
| Đầu vào | DNS record và truy vấn từ resolver | Route, backend pool, health state, endpoint | Service/endpoint từ platform hoặc registry cùng policy |
| Đơn vị thường chọn | Hostname/IP | Kết nối hoặc request | Endpoint cho từng request/kết nối qua proxy |
| Health awareness | Không mặc định theo sức khỏe ứng dụng | Thường có health check backend | Có thể kết hợp health/endpoint state và policy của mesh |
| Metadata và policy | Hạn chế | Tùy khả năng router/gateway | Thường phong phú hơn cho giao tiếp nội bộ |
| Thành phần cần vận hành | DNS zone, resolver, record, TTL | Router, gateway, load balancer và backend config | Control plane, proxy data plane, certificate và policy |
| Trường hợp phù hợp | Tên ổn định, phân giải đơn giản | Điểm vào tập trung, routing theo host/path và cân bằng tải | Nhiều service cần policy, bảo mật và telemetry nhất quán |

Các thành phần có thể phối hợp. Ví dụ, DNS đưa client đến API gateway; gateway lấy backend từ registry; giao tiếp east-west giữa các workload lại đi qua service mesh. Trong một nền tảng khác, Kubernetes DNS phân giải Service name, ClusterIP phân phối đến Pod, còn mesh proxy áp dụng mTLS và retry.

## 6. Kết hợp với Spring Cloud Service Discovery

Spring Cloud cung cấp abstraction để ứng dụng không bị khóa vào một cơ chế registry cụ thể:

- DiscoveryClient cho phép ứng dụng truy vấn instance theo service ID.
- ServiceRegistry cung cấp các thao tác đăng ký và hủy đăng ký instance.
- Spring Cloud LoadBalancer có thể chọn instance từ dữ liệu discovery khi HTTP client được cấu hình tích hợp phù hợp.

Với Eureka hoặc Consul, ứng dụng thường truy vấn registry thông qua implementation của Spring Cloud. Với Kubernetes, có thể dùng tích hợp Spring Cloud Kubernetes để khám phá Service/endpoint theo cấu hình. DNS và địa chỉ router cũng có thể được dùng trực tiếp như một đích ổn định nếu ứng dụng không cần tự chọn từng instance.

Ví dụ, có ba kiểu gọi khác nhau:

1. **Gọi qua DNS/router:** ứng dụng gọi http://inventory.internal; DNS trả về VIP của load balancer và load balancer chọn backend.
2. **Gọi qua Spring Cloud discovery:** ứng dụng dùng service ID inventory-service; DiscoveryClient lấy danh sách instance và Spring Cloud LoadBalancer chọn một instance.
3. **Gọi qua service mesh:** ứng dụng gửi request đến tên đích logic; proxy cục bộ chọn endpoint theo cấu hình do mesh control plane phân phối.

Không nên giả định ba kiểu gọi này tự động tương đương. Với kiểu thứ nhất, ứng dụng có thể chỉ thấy một VIP. Với kiểu thứ hai, ứng dụng có thể nhìn thấy danh sách instance. Với kiểu thứ ba, lựa chọn endpoint thường diễn ra ở proxy. Cần xác định rõ thành phần nào đang thực hiện discovery và thành phần nào đang cân bằng tải để tránh cấu hình trùng lặp hoặc khó chẩn đoán.

### Ví dụ chọn mô hình

| Bối cảnh | Hướng tiếp cận gợi ý |
| --- | --- |
| Một vài ứng dụng nội bộ, ít thay đổi endpoint | DNS trỏ đến địa chỉ ổn định hoặc internal load balancer. |
| Microservice chạy ngoài Kubernetes và cần tìm instance động | Eureka/Consul cùng DiscoveryClient và LoadBalancer. |
| Ứng dụng triển khai trên Kubernetes, chỉ cần gọi Service nội bộ | Kubernetes Service DNS và ClusterIP có thể đã đủ. |
| Nhiều workload cần mTLS, traffic policy và telemetry đồng nhất | Cân nhắc service mesh sau khi đánh giá chi phí vận hành. |
| API công khai cần định tuyến theo hostname/path | API gateway hoặc ingress controller, có thể kết hợp registry hoặc mesh ở phía sau. |

## 7. Những tình huống cần xử lý cẩn thận

**Endpoint cũ còn trong cache.** DNS TTL, cache trong runtime, registry cache và proxy config có chu kỳ cập nhật khác nhau. Khi instance bị thay thế, một client vẫn có thể gửi request đến địa chỉ cũ. Hãy kiểm tra thời gian cache ở từng lớp, thời gian deregistration và cách client xử lý lỗi kết nối.

**Health check không đồng nhất.** Một instance có thể vẫn đăng ký trong Eureka nhưng đã không sẵn sàng phục vụ. Router có thể đánh dấu backend unhealthy trong khi registry chưa cập nhật; mesh có thể có endpoint nhưng áp dụng outlier detection để tạm ngừng gửi traffic. Hãy xác định nguồn trạng thái nào quyết định traffic thực tế.

**Định tuyến sai do địa chỉ không thể truy cập.** DNS hoặc registry có thể công bố IP chỉ có ý nghĩa trong một subnet/container network. Kiểm tra địa chỉ từ đúng network namespace của caller, không chỉ từ máy phát triển.

**Retry làm tăng tải.** Retry ở HTTP client, gateway và mesh có thể chồng lên nhau. Khi backend lỗi, nhiều lớp retry đồng thời có thể khuếch đại lưu lượng. Đặt timeout tổng, giới hạn số lần retry và chỉ retry request an toàn theo ngữ nghĩa.

**Hai lớp cùng cân bằng tải.** Nếu client tự chọn instance rồi lại gửi qua một load balancer khác, có thể xuất hiện hai lần lựa chọn endpoint. Điều này không luôn sai, nhưng cần hiểu lớp nào giữ sticky session, health state và locality policy.

**Control plane hoặc registry tạm thời gián đoạn.** Nhiều proxy có thể tiếp tục dùng cấu hình gần nhất, nhưng khả năng đó tùy implementation và cấu hình. Xác định hành vi khi mất control plane, cách cập nhật endpoint và cách khôi phục trước khi đưa vào production.

## 8. Checklist thiết kế và vận hành

- [ ] Xác định service ID và hostname mà caller sử dụng.
- [ ] Xác định nguồn sự thật của endpoint: DNS, Eureka/Consul, Kubernetes API hay nguồn khác.
- [ ] Chỉ rõ thành phần chọn instance: client, load balancer, gateway hay mesh proxy.
- [ ] Bảo đảm địa chỉ được công bố có thể truy cập từ mạng của caller.
- [ ] Đặt TTL/cache và chu kỳ refresh phù hợp với tốc độ thay đổi instance.
- [ ] Thiết kế health check và graceful deregistration để giảm request đến instance đang dừng.
- [ ] Quy định timeout, retry, circuit breaking và giới hạn tải tại các lớp có tham gia.
- [ ] Bảo vệ DNS nội bộ, registry, gateway, control plane và endpoint quản trị.
- [ ] Theo dõi lỗi phân giải tên, lỗi kết nối, endpoint unhealthy, độ trễ và tỷ lệ lỗi theo từng lớp.
- [ ] Thử nghiệm tình huống endpoint đổi IP, instance dừng đột ngột và registry/control plane mất kết nối.

## Ghi nhớ

- DNS trả lời câu hỏi tên dịch vụ phân giải thành địa chỉ nào; TTL và cache quyết định thời gian địa chỉ cũ còn được sử dụng.
- Router và load balancer chọn backend rồi chuyển tiếp request; danh sách backend có thể đến từ cấu hình, DNS, registry hoặc nền tảng điều phối.
- Service mesh đưa discovery và traffic policy đến proxy data plane thông qua control plane; mesh vẫn cần nguồn dữ liệu endpoint.
- Eureka/Consul, Kubernetes DNS, router và mesh có thể bổ sung cho nhau ở các lớp khác nhau.
- Khi thiết kế, hãy xác định rõ nguồn endpoint, nơi chọn instance và nơi áp dụng health check, bảo mật cùng retry để tránh trạng thái lệch và hành vi khó dự đoán.
