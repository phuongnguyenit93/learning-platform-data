# DNS, danh mục dịch vụ và cập nhật điểm cuối

> **Chủ đề:** Software Design Architecture → System Architecture → Microservices  
> **Nhóm kiến thức:** Khám phá và định tuyến

## 1. Vì sao service discovery là bài toán của kiến trúc phân tán?

Trong một ứng dụng chạy ở máy đơn, module có thể gọi nhau qua interface và hàm. Khi tách thành microservices, một service phải biết **địa chỉ mạng và cách kết nối** để gửi yêu cầu đến service khác. Địa chỉ này không nên được giả định bất biến: một instance có thể được tạo, hủy, khởi động lại, chuyển node, thay IP hoặc được thay thế bởi phiên bản mới.

Xét hệ thống đặt hàng:

    Browser
       |
       v
    API Gateway
       |
       +----> Ordering
       |          |
       |          +----> Inventory
       |          '---> Payment
       |
       '---> Catalog

Nếu Ordering được cấu hình gọi Inventory tại `10.2.4.17:8080`, điều gì xảy ra khi container Inventory được thay mới và nhận IP `10.2.8.21`? Nếu tự sửa file cấu hình mỗi lần autoscaling hay deploy, hệ thống mất khả năng mở rộng và vận hành độc lập.

Thay vì phụ thuộc vào một IP cố định, Ordering nên biết **danh tính logic** của năng lực cần gọi, chẳng hạn `inventory`, `inventory.default.svc.cluster.local` hoặc một tên dịch vụ được công bố theo quy ước. Lớp khám phá và định tuyến chịu trách nhiệm chuyển tên logic đó thành nơi có thể nhận yêu cầu tại thời điểm thích hợp.

Từ đây xuất hiện ba câu hỏi khác nhau:

1. **Discovery:** service đích hiện có những endpoint nào?
2. **Routing / load balancing:** request cụ thể nên đi tới endpoint nào?
3. **Endpoint lifecycle:** khi endpoint gia nhập, rời đi hoặc không còn khỏe, các client và proxy biết để cập nhật như thế nào?

**DNS, service registry và endpoint updates là những cơ chế giải quyết các phần khác nhau của ba câu hỏi này.** Không có cơ chế đơn lẻ nào tự bảo đảm mọi request đều thành công.

## 2. Từ tên logic đến endpoint thực tế

Một số khái niệm cần tách riêng:

| Thuật ngữ | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Service identity | Tên logic của năng lực được gọi | `inventory`, `payments` |
| Instance | Một tiến trình/bản sao đang chạy service | Inventory pod A, pod B |
| Endpoint | Điểm mạng cụ thể có thể tiếp nhận kết nối | `10.2.8.21:8080` |
| DNS record | Bản ghi ánh xạ tên sang địa chỉ/tên hoặc dịch vụ | A, AAAA, CNAME, SRV |
| Service registry | Danh mục các service/instance và metadata liên quan | Inventory có 3 instance healthy |
| Load balancer | Bộ phận chọn nơi nhận request hoặc phân phối lưu lượng | Proxy, gateway, client balancer |
| Health/readiness | Tín hiệu về khả năng xử lý request | Instance có nên được đưa vào tập endpoint phục vụ hay chưa |
| Control plane | Phần quản lý và phân phối cấu hình/discovery | Registry controller, discovery API, mesh control plane |
| Data plane | Thành phần thực sự chuyển/gửi lưu lượng | Client socket, proxy, load balancer |

Một tên logic có thể ánh xạ tới **một địa chỉ ảo ổn định** (VIP), hoặc tới **danh sách endpoint động**. Hai cách này cho ra cùng trải nghiệm “gọi service theo tên” nhưng yêu cầu cập nhật endpoint ở các tầng khác nhau.

### 2.1. Hai đường đi điển hình

**Trường hợp A: tên logic → địa chỉ ảo → backend**

    Ordering
       |
       | DNS: inventory.service -> 10.96.20.30
       v
    10.96.20.30 (Service VIP)
       |
       | Lớp load balancing chọn instance
       +----> Inventory A (10.2.8.21)
       +----> Inventory B (10.2.9.15)
       '---> Inventory C (10.2.9.37)

Client không cần liên tục học mọi Pod IP. Lớp định tuyến đứng sau địa chỉ ảo cập nhật tập backend.

**Trường hợp B: tên logic → danh sách endpoint → chọn tại client**

    Ordering
       |
       | Query/Watch registry: inventory
       v
    Registry
       |
       '---> [10.2.8.21:8080, 10.2.9.15:8080]
                          |
                          v
                 Client-side load balancer
                          |
                          v
                 Inventory instance đã chọn

Client hoặc thư viện của nó theo dõi danh sách endpoint và tự chọn instance để gửi request.

Điểm khác biệt quan trọng: **client có thể thấy IP backend hoặc không**, và **nơi quyết định chọn backend** có thể là client, proxy hoặc hạ tầng mạng.

## 3. DNS giải quyết điều gì?

**Domain Name System (DNS)** là hệ thống ánh xạ tên thành các bản ghi tài nguyên. Với việc gọi service, các loại bản ghi thường gặp gồm:

- **A:** tên → địa chỉ IPv4.
- **AAAA:** tên → địa chỉ IPv6.
- **CNAME:** tên → một tên khác; cần phân giải tiếp để tìm địa chỉ.
- **SRV:** tên dịch vụ/giao thức → target, port cùng các thông tin ưu tiên/trọng số theo quy tắc SRV.
- **TXT:** chứa dữ liệu văn bản theo cấu trúc do hệ thống sử dụng; không phải định dạng health/routing phổ quát.

Ví dụ:

    inventory.internal.example A 10.0.10.5
    inventory.internal.example A 10.0.10.6

Client truy vấn `inventory.internal.example` có thể nhận nhiều địa chỉ. Tuy nhiên **nhiều A record không tự đồng nghĩa phân phối tải công bằng hoặc loại bỏ endpoint lỗi**. Việc chọn địa chỉ, giữ cache, tái sử dụng connection và failover phụ thuộc resolver, thư viện ứng dụng và chính sách của hạ tầng.

### 3.1. DNS và TCP/HTTP là hai bước khác nhau

Một chuỗi tương tác có thể là:

    1. Client cần gọi inventory.internal.example
    2. Resolver trả về địa chỉ
    3. Client thiết lập hoặc tái sử dụng kết nối TCP/QUIC tới địa chỉ
    4. Truyền HTTP/gRPC request qua kết nối
    5. Nhận kết quả và giữ/hủy kết nối theo policy

DNS chủ yếu giúp client **tìm đích để kết nối**. Sau khi kết nối đang mở, không phải mỗi HTTP request đều thực hiện một DNS lookup mới. Connection pooling, HTTP/2 multiplexing và keep-alive có thể khiến client tiếp tục gửi nhiều request tới backend đã chọn ngay cả khi DNS record sau đó thay đổi.

Điều này giải thích một hiện tượng dễ nhầm: “DNS đã đổi rồi nhưng traffic vẫn đi tới instance cũ”. Cần kiểm tra cả **DNS cache lẫn vòng đời connection**, không chỉ xem câu trả lời hiện tại của `nslookup`.

### 3.2. TTL không phải công tắc đổi IP tức thời

Mỗi bản ghi DNS có **TTL (Time To Live)** cho phép cache giữ kết quả trong thời gian nhất định theo quy tắc. Khi TTL còn hiệu lực, resolver có thể trả đáp án đã lưu. Một số resolver và runtime có chính sách cache riêng; môi trường có thể có nhiều lớp cache, nên tổng thời gian dữ liệu cũ còn được dùng không nhất thiết đúng bằng một TTL mà operator đặt.

Ví dụ, DNS record thay từ `10.0.10.5` sang `10.0.10.6`, nhưng:

- Recursive resolver vẫn giữ bản ghi cũ theo TTL.
- Client runtime có thể cache tên hoặc địa chỉ.
- HTTP connection pool đang giữ kết nối mở tới IP cũ.
- Một proxy đã nạp danh sách upstream trước đó nhưng chưa refresh.
- Client gặp lỗi, dùng retry và lại chọn cùng kết nối/endpoint.

**Giảm TTL không đủ để bảo đảm chuyển lưu lượng tức thì**. TTL ngắn cũng có chi phí: tăng truy vấn DNS và phụ thuộc nhiều hơn vào khả năng phục vụ của resolver.

### 3.3. Negative caching và lỗi “không tìm thấy”

Khi tên chưa tồn tại hoặc không có bản ghi phù hợp, resolver có thể cache kết quả âm (ví dụ NXDOMAIN) theo quy tắc tương ứng. Nếu một service vừa được tạo sau một truy vấn thất bại, client vẫn có thể nhận lỗi trong một khoảng thời gian. Vì vậy cần kiểm tra:

- Tên có tồn tại đúng namespace/domain không?
- Resolver trả NXDOMAIN hay SERVFAIL, timeout hay địa chỉ nhưng kết nối bị từ chối?
- Có bộ nhớ cache âm ở resolver hoặc trong runtime không?
- Có giới hạn và backoff khi retry DNS không?

Không nên biến lỗi phân giải DNS thành retry vô hạn với tần suất cao: trong sự cố, điều đó có thể tạo tải lớn lên hạ tầng DNS.

## 4. Service registry cung cấp gì ngoài DNS?

**Service registry** là danh mục service instances, thường có thông tin như tên, địa chỉ, port, trạng thái sẵn sàng, zone/region, phiên bản hoặc metadata phục vụ routing. Tùy triển khai, registry có thể cho client truy vấn, đăng ký, hủy đăng ký hoặc nhận cập nhật thay đổi theo watch/stream.

Ví dụ bản ghi logic:

```json
{
  "service": "inventory",
  "instances": [
    {
      "instanceId": "inv-a91",
      "address": "10.2.8.21",
      "port": 8080,
      "zone": "zone-a",
      "status": "READY",
      "version": "2026.11"
    },
    {
      "instanceId": "inv-b13",
      "address": "10.2.9.15",
      "port": 8080,
      "zone": "zone-b",
      "status": "READY",
      "version": "2026.11"
    }
  ]
}
```

Các trường trên chỉ là một **mô hình khái niệm**, không phải schema chuẩn chung của mọi registry. Có hệ thống lưu health và metadata riêng, có nơi chỉ nắm địa chỉ, có nơi tính readiness từ orchestration platform.

### 4.1. Ai cập nhật registry?

Có hai mô hình thường gặp:

**Self-registration:** ứng dụng tự đăng ký khi khởi động, gửi heartbeat hoặc gia hạn lease, và gỡ đăng ký khi dừng có kiểm soát.

**Third-party registration:** agent/controller/orchestrator quan sát vòng đời instance rồi cập nhật danh mục. Trong môi trường Kubernetes, endpoint information thường được điều khiển từ trạng thái workload và service selector, thay vì mỗi ứng dụng tự viết client đăng ký thủ công.

Điều cần giải quyết không phải “cách nào hiện đại hơn”, mà là **bên nào có thông tin chính xác nhất về trạng thái endpoint** và chịu trách nhiệm xóa bản ghi stale khi tiến trình chết đột ngột.

### 4.2. Liveness khác readiness

- **Liveness:** tiến trình có cần được khởi động lại không, theo điều kiện health của hệ thống.
- **Readiness:** tiến trình có đủ điều kiện nhận traffic mới không?
- **Startup:** ứng dụng có cần thời gian khởi động trước khi các kiểm tra khác được áp dụng không?

Một instance vẫn sống nhưng chưa load xong cấu hình, chưa warm up cache hoặc đang quá tải có thể không nên được coi là ready. Ngược lại, một dependency phụ trợ lỗi không nhất thiết khiến ứng dụng không ready cho mọi loại endpoint. Thiết kế health check phải phản ánh **khả năng phục vụ** chứ không chỉ “process còn PID”.

## 5. Ba mô hình khám phá và định tuyến thường gặp

### 5.1. Client-side discovery

Client hoặc thư viện load balancing:

1. Hỏi registry/DNS để lấy danh sách endpoint.
2. Chọn endpoint theo round-robin, ngẫu nhiên, least-loaded hoặc policy khác.
3. Gọi trực tiếp endpoint.
4. Cập nhật danh sách qua watch, poll, TTL hoặc cơ chế refresh.

**Ưu điểm:** có thể chọn backend theo latency, locality hoặc metadata; không nhất thiết có proxy trung gian cho mọi lời gọi. **Đánh đổi:** mỗi client runtime phải giải quyết refresh, health, retry, connection lifecycle và chính sách load balancing; các ngôn ngữ khác nhau có thể triển khai khác nhau.

Ví dụ tưởng tượng một thư viện gRPC biết danh sách endpoint và policy balance. Những chi tiết về resolver và cách cân bằng tải phụ thuộc cấu hình của client; không nên giả định mọi gRPC client tự biết registry của doanh nghiệp.

### 5.2. Server-side discovery

Client chỉ biết một địa chỉ logic ổn định, chẳng hạn proxy, load balancer hoặc VIP. Thành phần trung gian duy trì danh sách backend và chọn instance.

    Client -> LB/VIP -> Service instance

**Ưu điểm:** đơn giản hóa client; dễ áp policy routing tập trung và quan sát tại proxy. **Đánh đổi:** tăng trách nhiệm và độ phức tạp ở lớp hạ tầng, thêm đường đi trung gian hoặc thành phần routing phải được vận hành đúng.

### 5.3. Service mesh / sidecar / ambient data plane

Một service mesh có thể cung cấp discovery và routing policy qua **control plane**, còn proxy hoặc thành phần data plane gửi traffic. Một số mô hình dùng sidecar cạnh workload, một số dùng data plane dạng khác. Chúng có thể hỗ trợ mutual TLS, traffic splitting, retries và telemetry, nhưng không mặc nhiên loại bỏ mọi lỗi mạng.

Điều cần hiểu: service không nhất thiết tự truy vấn registry; nó có thể gọi một tên logic rồi **proxy được cấu hình** chọn endpoint. Khi debug phải biết service resolver nào, proxy nào và control plane nào đang là nguồn cập nhật.

## 6. Service discovery trong Kubernetes

Trong Kubernetes, **Service** tạo một địa chỉ logic ổn định cho một tập Pod, còn **EndpointSlice** là một cơ chế lưu và phân phối thông tin endpoint cho việc định tuyến. **CoreDNS** hoặc DNS server theo cấu hình cluster giúp phân giải tên Service.

Ví dụ manifest đơn giản:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: inventory
  namespace: shop
spec:
  replicas: 3
  selector:
    matchLabels:
      app: inventory
  template:
    metadata:
      labels:
        app: inventory
    spec:
      containers:
        - name: inventory
          image: example.test/inventory:1.4.0
          ports:
            - containerPort: 8080
          readinessProbe:
            httpGet:
              path: /health/ready
              port: 8080
            periodSeconds: 5
            failureThreshold: 2
          terminationGracePeriodSeconds: 30
---
apiVersion: v1
kind: Service
metadata:
  name: inventory
  namespace: shop
spec:
  selector:
    app: inventory
  ports:
    - name: http
      port: 80
      targetPort: 8080
      protocol: TCP
  type: ClusterIP
```

Trong ví dụ, client trong cluster có thể gọi:

    http://inventory.shop.svc.cluster.local

Tên DNS đủ có cấu trúc theo namespace và cluster domain mặc định; domain cụ thể của một cluster có thể được cấu hình khác. Với client cùng namespace, tên ngắn `inventory` thường được resolver tìm theo search domains; không nên giả định tên ngắn hoạt động giống nhau từ mọi namespace hoặc ngoài cluster.

**Địa chỉ ClusterIP không phải Pod IP.** DNS của Service thường trả về VIP, còn lớp định tuyến từ VIP tới backend Pod có thể được triển khai bởi kube-proxy hoặc công nghệ data plane thay thế tùy cluster. Khi Pod thay mới, VIP thường giữ nguyên; endpoint backend được cập nhật dựa trên trạng thái tài nguyên Kubernetes.

### 6.1. EndpointSlice biểu diễn tập backend

Để xem endpoint đã được chọn cho Service:

```bash
kubectl get svc inventory -n shop
kubectl get endpointslice -n shop -l kubernetes.io/service-name=inventory
kubectl describe endpointslice -n shop -l kubernetes.io/service-name=inventory
```

EndpointSlice có thể chứa địa chỉ, port, điều kiện endpoint như ready/serving/terminating và thông tin topology. Cách data plane xử lý các điều kiện này phụ thuộc phiên bản và cấu hình cluster.

Một Service có thể tồn tại và phân giải DNS bình thường **nhưng chưa có backend nào ready**. Khi đó lỗi không nằm ở bước phân giải tên: cần xem selector, label Pod, readiness và EndpointSlice.

### 6.2. Headless Service: DNS trả thông tin endpoint trực tiếp

Một Service có `clusterIP: None` là headless. Với mô hình này, DNS có thể trả địa chỉ của endpoint tương ứng thay vì một VIP. Ví dụ khái niệm:

```yaml
apiVersion: v1
kind: Service
metadata:
  name: inventory-headless
  namespace: shop
spec:
  clusterIP: None
  selector:
    app: inventory
  ports:
    - name: http
      port: 8080
      targetPort: 8080
```

Điều này hữu ích cho những ứng dụng cần nhận diện từng instance (ví dụ một số mô hình cluster stateful), hoặc client có khả năng chọn endpoint. Nhưng nó cũng làm client phụ thuộc nhiều hơn vào danh sách endpoint, cơ chế DNS refresh và connection reuse.

**Không coi headless Service tự động tốt hơn cho tất cả microservices.** Với HTTP application thông thường, ClusterIP thường đơn giản hơn và giảm nghĩa vụ discovery ở client.

### 6.3. Kubernetes không loại bỏ vòng đời mạng

Kể cả khi gọi qua Service DNS:

- Pod đang chạy nhưng chưa ready có thể không nằm trong tập nhận traffic.
- EndpointSlice cần thời gian được cập nhật và phân phối tới data plane.
- Kết nối cũ có thể còn tồn tại khi Pod bắt đầu dừng.
- Client có thể nhận connection reset khi node hoặc Pod biến mất.
- DNS cluster hoặc lớp routing có thể gặp sự cố độc lập với ứng dụng.

Do đó discovery, readiness, graceful shutdown, timeout, retry và quan sát mạng vẫn cần thiết.

## 7. Vòng đời một endpoint: từ xuất hiện tới rút khỏi traffic

Hãy xem một instance `Inventory-B` được đưa vào hệ thống:

    CREATED -> STARTING -> NOT_READY -> READY
                                       |
                                       v
                             Được đưa vào routing set
                                       |
                                       v
                                SERVING REQUESTS
                                       |
                                       v
                       DRAINING / TERMINATING
                                       |
                                       v
                      Không nhận request mới
                                       |
                                       v
                                 TERMINATED

Đây là **trình tự khái niệm**. Registry, Kubernetes và load balancer có thể biểu diễn bằng trạng thái khác nhau và không đồng bộ tuyệt đối.

### 7.1. Khi instance mới xuất hiện

1. Orchestrator hoặc hệ thống triển khai tạo tiến trình.
2. Ứng dụng tải cấu hình, mở listener, khởi tạo tài nguyên cần thiết.
3. Readiness/health control xác định thời điểm instance có thể nhận traffic.
4. Registry hoặc EndpointSlice được cập nhật.
5. Client/proxy/data plane nhận được thay đổi qua watch, polling hoặc refresh.
6. Một phần traffic bắt đầu chuyển tới instance mới.

Không nên đưa instance vào rotation quá sớm, khi chưa load xong cấu hình hoặc chưa sẵn sàng. Nhưng cũng không nên thiết kế readiness phụ thuộc vô hạn vào tất cả dịch vụ bên ngoài, khiến một sự cố nhỏ làm cả hệ thống cùng rút khỏi traffic.

### 7.2. Khi instance chuẩn bị dừng

Một quy trình graceful shutdown mong muốn:

1. Instance được đánh dấu không còn nhận request mới.
2. Service discovery/routing được cập nhật và bắt đầu loại endpoint khỏi lựa chọn mới.
3. Thành phần phục vụ ngừng chấp nhận phiên công việc mới theo chính sách.
4. Những request còn đang xử lý được phép hoàn tất trong khoảng thời gian grace.
5. Kết nối và tài nguyên được đóng có kiểm soát.
6. Sau thời hạn, tiến trình kết thúc.

**Không thể giả định bước 2 có hiệu lực tức thì trên mọi client.** Hạ tầng cần có thời gian propagation; một số client có cache hoặc connection cũ. Vì thế quá trình drain nên chịu được một khoảng chuyển tiếp, và client phải có chính sách xử lý lỗi hợp lý.

### 7.3. Graceful termination trong Kubernetes

Kubernetes thường bắt đầu quy trình dừng Pod bằng thời gian grace, gửi tín hiệu kết thúc phù hợp tới tiến trình và cập nhật trạng thái Pod/endpoint theo cơ chế của nó. Ứng dụng cần bắt tín hiệu và ngừng xử lý request mới theo khả năng của framework.

Đối với HTTP/gRPC cần xét:

- Request dài đang thực thi có cần thời gian hoàn tất không?
- Connection keep-alive hoặc HTTP/2 streams được đóng theo cách nào?
- Có long polling, WebSocket hoặc server streaming không?
- Có in-flight message hoặc transaction cần commit/rollback không?
- Nếu client timeout nhưng thao tác có tác dụng phụ đã chạy, làm sao xác minh kết quả?

`terminationGracePeriodSeconds` là **ngân sách thời gian cho việc kết thúc Pod**, không phải bảo đảm mọi request có thể hoàn tất. Mỗi ứng dụng phải chủ động quản lý shutdown. PreStop hook có thể hữu ích trong một số tình huống nhưng không thay thế chính sách drain; hook cũng tiêu thụ một phần thời gian grace.

## 8. Rolling update, autoscaling và thay đổi tập endpoint

Một lần deploy phiên bản mới có thể khiến endpoint set thay đổi liên tục:

    T0: inventory-v1-A, inventory-v1-B
    T1: inventory-v1-A, inventory-v1-B, inventory-v2-C (chưa ready)
    T2: inventory-v1-A, inventory-v1-B, inventory-v2-C (ready)
    T3: inventory-v1-B, inventory-v2-C, inventory-v2-D
    T4: inventory-v2-C, inventory-v2-D

Trong thời gian T1–T4, client có thể nói chuyện với **nhiều phiên bản service khác nhau**. Vì vậy API contract cần tương thích trong giai đoạn rollout; discovery chỉ quyết định nơi gửi, không làm hai phiên bản tự động tương thích.

### 8.1. Autoscaling tăng và giảm số instance

Khi scale out, các endpoint mới được thêm sau khi ready. Khi scale in, một số endpoint bị loại khỏi routing set, tiến trình dừng theo chính sách. Với autoscaling quá nhanh và liên tục, danh sách endpoint biến động nhiều; client-side discovery và proxy cần cập nhật ổn định.

Những vấn đề cần xét:

- Tải tăng đột biến có khiến backend mới chưa sẵn sàng nhưng đã nhận traffic không?
- Connection pool có giữ quá nhiều kết nối tới những endpoint cũ không?
- Tài nguyên sẵn sàng sau scale out có bị dồn vào một instance không?
- Scale in có rút instance đang xử lý request quan trọng quá nhanh không?
- Hệ thống có cần giới hạn tốc độ tăng/giảm số replica để tránh dao động không?

### 8.2. Canary và traffic splitting

Khi v1/v2 cùng tồn tại, đôi khi muốn chỉ 5% request đến v2. DNS round-robin không phải một phương án đáng tin cậy để bảo đảm đúng **5% HTTP request**, do caching, connection reuse và phân phối không đều. Phân phối có trọng số thường cần gateway/load balancer/service mesh hoặc client balancer có khả năng routing theo yêu cầu.

Ngoài tỷ trọng, có thể cần sticky sessions, header-based routing, locality hoặc route theo tenant. Những chính sách này phải được xem như **routing contract**, không chỉ là thay đổi bản ghi DNS.

## 9. DNS cache và connection pool: hai lớp trạng thái dễ bỏ qua

Một ứng dụng Java có thể có:

    Java application
       |
       | HTTP client + connection pool
       |
       | DNS resolution / JVM / OS / local resolver
       v
    Service address
       |
       | TCP/TLS connections reused across requests
       v
    Destination

Khi kiểm tra DNS, phải hiểu có thể tồn tại cache ở JVM, thư viện networking, hệ điều hành, local DNS cache và recursive resolver. Chính sách caching của Java hoặc HTTP client còn phụ thuộc phiên bản runtime và cấu hình bảo mật; không nên đưa một TTL mặc định chung cho mọi ứng dụng.

### 9.1. Một lỗi thường gặp

1. Client truy vấn service name và kết nối tới IP A.
2. Đội vận hành đổi DNS record sang IP B.
3. DNS cache ở client hết hạn nhưng HTTP client vẫn giữ connection sống tới A.
4. Những request tiếp theo tiếp tục sử dụng connection cũ cho tới khi kết nối đóng hoặc chính sách pool loại bỏ nó.

**TTL của DNS record và tuổi thọ connection là hai thông số khác nhau.** Để giảm thời gian bám endpoint cũ có thể cần chính sách connection lifetime, idle timeout, health, retry chọn endpoint khác hoặc chuyển sang cơ chế VIP/proxy khi phù hợp.

### 9.2. Không ép lookup DNS trên mọi request một cách mù quáng

Bắt client bỏ cache và resolve mỗi lần gọi có thể tăng latency, tải lên DNS và mất lợi ích connection reuse. Cần chọn theo yêu cầu chuyển đổi endpoint, hành vi DNS của runtime và hạ tầng định tuyến.

Với ClusterIP ổn định, client thường không cần biết Pod thay IP. Với headless hoặc client-side balancing, việc làm mới danh sách endpoint có thể trở thành trách nhiệm quan trọng hơn.

## 10. Service registry: tính mới, watch và lease

Không phải registry nào cũng có thông tin tuyệt đối nhất quán tại mọi thời điểm. Khi mạng bị phân vùng hoặc một agent mất kết nối, có thể có bản ghi stale hoặc cập nhật chưa tới nơi.

### 10.1. Polling và watch

**Polling:** client hỏi danh sách endpoint định kỳ. Dễ hiểu nhưng có độ trễ phát hiện thay đổi, sinh tải đều lên registry và có thể gây đồng bộ lượng lớn request nếu mọi client poll cùng lúc.

**Watch/stream:** client đăng ký nhận các thay đổi. Giúp giảm độ trễ cập nhật trong điều kiện khỏe, nhưng cần xử lý reconnect, event bị mất, version hoặc cursor, và cơ chế lấy snapshot mới khi không chắc đã nhận đủ delta.

Một client có thể áp dụng:

    startup:
      endpoints = registry.fetchSnapshot()
      subscribeWatch(fromVersion)

    onWatchEvent:
      if version liên tục:
          applyDelta()
      else:
          endpoints = registry.fetchSnapshot()

    onDisconnect:
      backoff + jitter
      reconnect
      reconcileSnapshot()

Pseudocode minh họa tư duy quản lý consistency; các API thật phụ thuộc sản phẩm registry.

### 10.2. Lease và heartbeat không đồng nghĩa ready

Một instance còn heartbeat có thể vẫn bị nghẽn không xử lý được request nghiệp vụ. Một instance ngừng heartbeat có thể chỉ đang mất kết nối tới registry nhưng vẫn phục vụ client hiện hữu. Cần phân biệt:

- Liveness của tiến trình.
- Readiness phục vụ lưu lượng.
- Reachability từ client/proxy.
- Trạng thái đăng ký trong registry.
- Tình trạng overload của chính endpoint.

Việc xóa endpoint khi lease hết hạn là cơ chế phát hiện mất liên lạc, nhưng nên tính tới ngưỡng, jitter và tác động của network partition để tránh rút hàng loạt endpoint khỏe khỏi routing set.

## 11. Health checking và lựa chọn endpoint

Giả sử registry có ba instance, nhưng một instance chậm hoặc trả 5xx. Có ít nhất hai cách bảo vệ:

1. **Chủ động:** readiness/health check phát hiện instance không nên nhận traffic mới.
2. **Bị động:** client/proxy quan sát lỗi và latency để tạm thời tránh endpoint kém khỏe theo chính sách.

Health check chỉ xác minh điều nó kiểm tra. Một endpoint `/health` trả 200 không chứng minh mọi API nghiệp vụ đều đúng. Ngược lại, nếu health check phụ thuộc một dịch vụ ngoài không bắt buộc, nó có thể khiến instance bị rút khỏi traffic dù vẫn phục vụ được phần lớn chức năng.

### 11.1. Load balancing không chỉ có round-robin

Các chính sách có thể bao gồm:

| Cách chọn | Đặc điểm | Rủi ro/điều kiện |
| --- | --- | --- |
| Round-robin | Luân phiên qua danh sách endpoints | Không phản ánh tải thực hoặc latency khác nhau |
| Random | Chọn ngẫu nhiên | Phân phối chỉ cân bằng theo xác suất |
| Weighted | Có trọng số theo năng lực/phiên bản | Cần cấu hình trọng số và quan sát thực |
| Least connections / in-flight | Ưu tiên nơi ít request đang xử lý | Có thể chưa phản ánh độ phức tạp của request |
| Locality-aware | Ưu tiên zone/vùng gần | Phải có fallback khi vùng gần lỗi |
| Consistent hashing | Giữ một mức ổn định ánh xạ key tới endpoint | Cần chính sách xử lý mất/đổi endpoint |
| Sticky session | Cố gắng giữ client tới cùng backend | Dễ tạo lệch tải hoặc phụ thuộc state cục bộ |

Không chính sách nào đúng cho mọi workload. Một service stateless có thể hưởng lợi từ lựa chọn đơn giản; một ứng dụng stateful cần hiểu phân vùng dữ liệu và khóa định tuyến. Việc dùng nhiều endpoint không thay thế thiết kế trạng thái hoặc transaction.

### 11.2. Retry phải tránh khuếch đại lỗi

Khi endpoint thất bại, retry sang instance khác có thể phục hồi một số lỗi tạm thời. Nhưng:

- Không retry vô hạn.
- Không retry mù thao tác có tác dụng phụ, chẳng hạn thu tiền, nếu không có idempotency.
- Không để nhiều tầng gateway/client/proxy cùng retry nhiều lần.
- Dùng deadline tổng, backoff với jitter và retry budget phù hợp.
- Khi cả service quá tải, retry có thể làm tình hình nặng thêm.
- Việc chọn endpoint khác phải thật sự thay đổi đường đi; retry trên cùng connection lỗi có thể không giúp.

**Discovery cho biết nơi có thể gọi; độ tin cậy còn phụ thuộc transport, hợp đồng nghiệp vụ và cơ chế phục hồi.**

## 12. Phân biệt lỗi DNS, lỗi discovery và lỗi backend

Một câu báo lỗi chung “không kết nối được service” chưa đủ để quyết định cần sửa ở tầng nào.

| Triệu chứng | Khả năng nguyên nhân | Bằng chứng cần kiểm tra |
| --- | --- | --- |
| NXDOMAIN | Sai tên, namespace/domain, record chưa tồn tại hoặc cache âm | DNS query, search suffix, bản ghi hiện hành |
| SERVFAIL / DNS timeout | Resolver/control DNS lỗi hoặc mạng tới resolver | DNS metrics, timeout, resolver logs |
| DNS có IP nhưng kết nối từ chối | Không có listener, port sai, policy, backend ngừng | Endpoint port, process listener, service mapping |
| DNS có VIP nhưng không có backend | Selector sai, Pod chưa ready hoặc endpoint set trống | Service/EndpointSlice/readiness |
| Request đến nhầm phiên bản | Routing weight/header/rollout chưa đúng | Proxy route config, trace, version label |
| Một số request 5xx | Backend không khỏe, route lệch, connection lỗi | Per-endpoint errors, logs, trace |
| Chỉ lỗi sau rolling update | Endpoint propagation, draining, keep-alive, API compatibility | Timeline deploy, Pod events, connection resets |
| Chậm sau scale out | Warmup chưa đủ, tải chưa phân phối đều hoặc pool chờ | p95/p99, warmup, pool, load balancing metrics |
| Client vẫn gọi Pod/IP cũ | DNS cache, registry stale, connection reuse hoặc static config | Resolver cache, pool, watch state |

Không kết luận “lỗi DNS” chỉ vì một `nslookup` trả IP cũ. `nslookup` thường quan sát đường resolver của công cụ tại thời điểm đó, có thể khác hoàn toàn cách một ứng dụng Java hoặc proxy đang dùng kết nối có sẵn.

## 13. Case study: chuyển Inventory sang phiên bản mới không làm gián đoạn Checkout

Giả sử hệ thống thương mại có:

    Checkout -> Ordering -> Inventory

Inventory chạy ba instance và được triển khai phiên bản v2 theo rolling update. Mục tiêu là Checkout không phụ thuộc một IP cụ thể, các instance mới chỉ nhận traffic khi ready, và instance cũ có thời gian kết thúc request đang xử lý.

### 13.1. Những giả định ban đầu

- `Inventory` có hợp đồng API ổn định trong giai đoạn v1/v2 cùng chạy.
- Ordering gọi một tên logic, không dùng Pod IP lưu trong cấu hình.
- Lớp data plane có routing tới backend đang ready.
- HTTP client có timeout hữu hạn và connection pooling được cấu hình rõ.
- Thao tác giữ hàng dùng định danh yêu cầu để tránh giữ trùng nếu retry sau timeout.

### 13.2. Trình tự triển khai

1. Tạo Pod Inventory v2 mới.
2. Chờ ứng dụng v2 sẵn sàng và readiness báo thành công.
3. Endpoint controller cập nhật tập endpoint.
4. Lớp routing nhận cấu hình endpoint mới và bắt đầu đưa traffic sang v2.
5. Lấy v1 ra khỏi danh sách nhận request mới theo chính sách rollout.
6. Cho v1 xử lý các request đang tồn tại trong thời gian grace.
7. Kết thúc v1, theo dõi lỗi connection và trạng thái nghiệp vụ.
8. Nếu phát hiện lỗi ở v2, rollback hoặc giảm traffic theo cơ chế của nền tảng, không kỳ vọng mọi client đổi đích tức thì.

### 13.3. Điều cần đo

| Mốc | Quan sát |
| --- | --- |
| Thêm v2 | Thời gian từ Pod ready tới khi nhận request |
| Rút v1 | Thời gian từ khi bắt đầu draining tới request cuối |
| Chuyển tiếp | Số connection reset, timeout, retry và 5xx |
| Chất lượng | p50/p95/p99 latency theo v1/v2 |
| Độ nhất quán | Có reservation lặp hoặc kết quả chưa rõ không? |
| Discovery | EndpointSlice/registry cập nhật và client/proxy thực nhận endpoint mới |
| Tải | Có backend mới bị dồn quá nhiều request khi chưa warmup không? |

Một rollout chỉ được xem là “không gián đoạn theo cam kết” khi **lỗi và tính đúng đắn nghiệp vụ** đạt ngưỡng được định nghĩa trước, không chỉ vì số Pod luôn đạt replicas mong muốn.

## 14. Ví dụ Java: gọi tên logic thay vì IP cụ thể

Một ví dụ dùng Java HTTP Client để diễn đạt ý tưởng gọi theo service identity:

```java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

public final class InventoryClient {
    private final HttpClient client = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(2))
            .build();

    public String getAvailability(String sku) throws Exception {
        // URL base được cấu hình, ví dụ:
        // http://inventory.shop.svc.cluster.local
        String baseUrl = System.getenv("INVENTORY_BASE_URL");
        if (baseUrl == null || baseUrl.isBlank()) {
            throw new IllegalStateException("INVENTORY_BASE_URL is required");
        }

        URI uri = URI.create(baseUrl + "/availability?sku=" +
                java.net.URLEncoder.encode(
                    sku, java.nio.charset.StandardCharsets.UTF_8));

        HttpRequest request = HttpRequest.newBuilder(uri)
                .timeout(Duration.ofSeconds(3))
                .GET()
                .build();

        HttpResponse<String> response = client.send(
                request, HttpResponse.BodyHandlers.ofString());

        if (response.statusCode() != 200) {
            throw new IllegalStateException(
                "Inventory status=" + response.statusCode());
        }
        return response.body();
    }
}
```

Ví dụ trên nhằm minh họa **không hard-code Pod IP**, có connection timeout và request timeout hữu hạn. Nó chưa phải production-ready client: chưa có schema cho response, typed errors, auth, tracing, rate limit, circuit breaker, idempotency policy, retry budget hay khả năng hủy request khi business deadline hết.

Trong môi trường Kubernetes với Service ClusterIP, `INVENTORY_BASE_URL` có thể là tên DNS Service. Khi đổi Pod, URL logic không thay đổi. Nếu dùng registry client-side thì lớp chọn endpoint cần được thực hiện bởi một thư viện/adapter riêng, thay vì tự lấy một địa chỉ bất kỳ rồi gắn vào URL.

### 14.1. Tại sao không dùng một biến IP thủ công?

Một biến như `INVENTORY_IP=10.2.8.21` gắn ứng dụng với một instance. Thay Pod, scale hoặc failover sẽ tạo công việc cập nhật cấu hình. Có thể dùng hostname công khai hoặc tên Service hợp lý và quản lý resolution/routing ở tầng thích hợp.

### 14.2. Cấu hình không chỉ là URL

Một service client còn cần những giá trị dựa trên đặc tính dependency:

- Thời gian kết nối và deadline request.
- Mức đồng thời tối đa và kích thước connection pool.
- Loại thao tác có thể retry, số lần và backoff.
- Phương thức authentication/mTLS và tên định danh server được tin cậy.
- Quy tắc log/trace để xác định endpoint đã được chọn.
- Chính sách xử lý response lỗi hoặc phiên bản API không tương thích.

Đổi service discovery không thay thế hợp đồng này.

## 15. DNS và tên dịch vụ trong môi trường đa vùng hoặc đa cluster

Một hệ thống có thể có nhiều zone, region hoặc Kubernetes cluster. Khi đó “Inventory” không phải lúc nào cũng là một tập endpoint có thể truy cập qua cùng một mạng.

Cần phân biệt:

- **Locality:** ưu tiên endpoint cùng zone để giảm latency/chi phí khi phù hợp.
- **Failover:** khi zone không còn phục vụ, route sang vùng khác nếu dữ liệu và quyền cho phép.
- **Traffic policy:** phiên bản mới, nhóm khách hàng hoặc thị trường có thể cần route riêng.
- **Data residency:** dữ liệu nhạy cảm có thể không được phép đi sang vùng khác.
- **Network reachability:** một Pod IP có thể chỉ định tuyến được trong cluster nội bộ, không thể gọi trực tiếp từ cluster khác.
- **DNS namespace:** tên dịch vụ nội bộ cluster có thể trùng nhau giữa hai môi trường và không định danh toàn cục.

Không nên giả định `inventory.shop.svc.cluster.local` ở cluster A tự truy cập được cluster B. Multicluster thường cần giải pháp mạng và discovery/ingress được thiết kế riêng, đồng thời bảo vệ auth, policy và observability xuyên ranh giới.

### 15.1. Failover qua DNS có giới hạn

DNS có thể phân phối nhiều địa chỉ hoặc trả về đích khác tùy hệ thống, nhưng tốc độ failover chịu ảnh hưởng cache và connection reuse. Với các hệ thống có yêu cầu chuyển traffic nhanh, có thể cần health-aware load balancer, gateway hoặc routing layer thực sự, không chỉ đổi bản ghi DNS và chờ TTL.

Một failover tự động cũng phải xét dữ liệu: service ở vùng B có đủ dữ liệu và trạng thái nhất quán để xử lý thao tác từ vùng A không? Routing thành công tới nơi không có dữ liệu thích hợp vẫn có thể là lỗi nghiệp vụ.

## 16. Bảo mật discovery và định tuyến

Tên service không phải bằng chứng về danh tính server. Một client có thể phân giải đúng tên DNS nhưng vẫn cần kiểm tra:

- Kết nối có mã hóa và xác thực server phù hợp không?
- Với TLS, chứng chỉ có khớp tên/danh tính kỳ vọng không?
- Với mTLS, cả client và server có được xác thực theo identity/service account không?
- Có authorization cho từng thao tác và đối tượng dữ liệu không?
- Registry hoặc control plane có bị cấp quyền sửa endpoint tùy ý không?
- Endpoint mới có thể được một actor không tin cậy đăng ký và nhận traffic không?

Nếu danh mục service bị sửa trái phép, client có thể bị chuyển tới endpoint giả. Do đó registry và control plane cần phân quyền, kiểm toán thay đổi và bảo vệ kết nối. Không nên tin rằng một địa chỉ nằm trong mạng nội bộ là đủ an toàn.

### 16.1. Service identity độc lập với IP

Trong hệ thống dùng identity dựa trên workload hoặc chứng chỉ, service có thể được xác thực bằng định danh được phát hành có kiểm soát, không phụ thuộc một IP thay đổi liên tục. Đây là một nguyên tắc quan trọng: **địa chỉ mạng trả lời “đi đâu?”, còn identity trả lời “đây có đúng bên được phép giao tiếp không?”**.

Đừng bỏ qua hostname verification chỉ để làm mTLS/TLS “hoạt động được” sau khi endpoint đổi IP. Thay vào đó cần cấu hình tên/identity và chứng chỉ theo cơ chế được hỗ trợ.

## 17. Observability: cần thấy cả resolution, routing và kết quả nghiệp vụ

Một biểu đồ 5xx tổng của API thường không đủ để chỉ ra lỗi ở đâu trong đường discovery. Cần thu thập bằng chứng từng tầng.

### 17.1. Chỉ số DNS

- Số truy vấn và độ trễ phân giải theo nhóm tên/loại record.
- Tỷ lệ NXDOMAIN, SERVFAIL, timeout và retry.
- Cache hit/miss nếu resolver/client có hỗ trợ.
- Kích thước hoặc mức tải của DNS server/resolver.
- Sự khác nhau giữa DNS trả địa chỉ và khả năng kết nối tới địa chỉ đó.

Không log toàn bộ tên truy vấn nếu có nguy cơ chứa thông tin nhạy cảm; áp dụng giới hạn cardinality và chính sách dữ liệu cho metrics.

### 17.2. Chỉ số registry/discovery

- Số instance được công bố và số instance ready.
- Độ trễ từ thay đổi health tới khi registry/proxy/client cập nhật.
- Watch disconnect/reconnect, thời gian từ lần cập nhật cuối, số lỗi refresh.
- Số endpoint stale hoặc nhận traffic sau khi đã rút khỏi set.
- Số lần registration/lease expiration và thay đổi bất thường.
- Tình trạng control plane không thể phân phối snapshot/delta.

### 17.3. Chỉ số routing và kết nối

- Lưu lượng và latency phân bổ theo service, version, zone, endpoint.
- Connect timeout, connection reset, TLS handshake errors, pool wait time.
- Tỷ lệ retry, retry-success và retry-exhausted.
- Số request đang xử lý trên từng instance.
- Circuit breaker mở, endpoint ejection và tình trạng overload.
- p50/p95/p99 end-to-end cùng tỷ lệ lỗi theo từng route.
- Requests bị gián đoạn trong rolling update hoặc draining.

**Distributed tracing** có thể ghi service dependency, logical destination, route/version và thời gian ở từng span. Không nhất thiết ghi raw IP vào mọi trace nếu gây cardinality hoặc lộ topology; dùng metadata được phép và đủ để chẩn đoán.

## 18. Quy trình chẩn đoán sự cố discovery theo thứ tự

Khi Ordering báo “không gọi được Inventory”, hãy kiểm tra theo các tầng thay vì sửa cấu hình ngẫu nhiên.

**Bước 1 — Định danh:** Ordering đang gọi tên logic và port nào? Có sai namespace, domain, URL scheme hoặc API path không?

**Bước 2 — DNS:** Tên đó phân giải ra gì từ chính môi trường của Ordering? Đây là NXDOMAIN, SERVFAIL, timeout hay trả địa chỉ hợp lệ?

**Bước 3 — Registry/EndpointSlice:** Có endpoint nào đang ready? Selector, label, health hoặc lease có đúng? Danh sách có thay đổi sau deploy không?

**Bước 4 — Routing:** Client/proxy có nhận được tập endpoint mới? Có route tới backend đúng version, zone và port không?

**Bước 5 — Network/transport:** Có TCP/TLS connection không? Bị reset, refused, timeout hay bị policy chặn? Có connection pool giữ kết nối stale không?

**Bước 6 — Service behavior:** Backend có xử lý request và trả đúng status không? Có bị quá tải hoặc chờ database/downstream không?

**Bước 7 — Business effect:** Nếu timeout sau một thao tác có side effect, nó đã thực hiện thành công chưa? Có idempotency key và đường truy vấn trạng thái không?

**Bước 8 — Timeline:** So sánh mốc deploy/scale, readiness, endpoint update, route update và lỗi. Nhiều sự cố chỉ xuất hiện trong vài giây chuyển tiếp.

Quy trình này giúp tách “không phân giải được tên” khỏi “phân giải được nhưng route sai” và “route đúng nhưng nghiệp vụ lỗi”.

## 19. Bài tập kiến trúc: chọn DNS hay registry?

Một nền tảng có bốn thành phần:

1. **Catalog:** HTTP API stateless, triển khai bằng Kubernetes Deployment và Service.
2. **Pricing:** service chạy trên một nhóm VM, số instance thay đổi và có registry hỗ trợ health.
3. **Analytics ingestion:** worker nhận message từ broker, không cần endpoint HTTP để consumer chủ động gọi.
4. **Inventory:** gRPC service có nhiều instance, một số request muốn ưu tiên cùng zone, cần deadline và giám sát latency.

Hãy trả lời:

- Với Catalog, vì sao tên Service DNS và VIP có thể đủ, không nhất thiết viết client registry mới?
- Với Pricing, client-side discovery và server-side load balancer có những đánh đổi nào về refresh và vận hành?
- Với Analytics ingestion, consumer có thật sự cần DNS của từng worker không, hay chỉ cần địa chỉ broker/topic và consumer group?
- Với Inventory, cần policy chọn endpoint theo zone hay chỉ cần một hostname trả A record? Có xử lý fallback khi zone gần không khả dụng không?
- Khi một VM Pricing bị hỏng mà chưa hết lease, hệ thống có rủi ro gì?
- Nếu Inventory đang xử lý request dài trong lúc scale in, quá trình drain cần lưu ý những gì?
- Nếu DNS của một service đổi nhưng Java client vẫn gọi địa chỉ cũ, cần kiểm tra những lớp nào?
- Những metrics nào chứng minh thời gian cập nhật endpoint và tỷ lệ lỗi trong rollout đạt mục tiêu?

**Gợi ý:** Không phải mọi service đều cần một registry độc lập. Nơi có sẵn lớp discovery và định tuyến tin cậy thì nên tận dụng; nơi có yêu cầu routing theo instance và metadata phức tạp mới cần cân nhắc cơ chế bổ sung.

## 20. Các hiểu lầm thường gặp

1. **“Có DNS là tự động cân bằng tải và loại backend chết.”** DNS cung cấp bản ghi; chính sách chọn endpoint và health cần cơ chế phù hợp.
2. **“TTL 5 giây nghĩa là sau đúng 5 giây không còn request tới IP cũ.”** Cache nhiều tầng và kết nối đang mở có thể duy trì lâu hơn.
3. **“Service registry luôn phản ánh trạng thái thực tế tức thời.”** Cập nhật có độ trễ, mất liên lạc và bản ghi stale.
4. **“Liveness 200 nghĩa là Pod sẵn sàng nhận mọi request.”** Liveness và readiness phục vụ mục đích khác nhau.
5. **“Kubernetes Service DNS luôn trả Pod IP.”** ClusterIP Service thường trả VIP; headless Service mới có mô hình trả endpoint trực tiếp.
6. **“Pod xóa khỏi EndpointSlice thì mọi kết nối cũ đã kết thúc.”** Traffic và connection drain cần xử lý riêng.
7. **“Rolling update thành công về replicas nghĩa là không có lỗi.”** Phải đo request failures, latency và business outcome.
8. **“Service discovery giúp các phiên bản API tự tương thích.”** v1/v2 cùng tồn tại vẫn cần contract evolution.
9. **“Retry lỗi kết nối luôn an toàn.”** Side effect có thể đã được thực hiện; cần idempotency và deadline.
10. **“Thêm service mesh là hết lỗi networking.”** Mesh tăng khả năng policy/observability nhưng vẫn có control-plane/data-plane failure.
11. **“Chỉ cần sửa DNS là failover vùng hoàn tất.”** Còn phải xét consistency, kết nối, chính sách dữ liệu và quyền truy cập.
12. **“Tên host nội bộ đủ bảo đảm identity.”** Cần TLS/mTLS và authorization phù hợp.

## 21. Checklist thiết kế discovery cho một service

Trước khi đưa service vào production, có thể ghi rõ:

- **Identity:** tên logic, namespace/domain, port, protocol nào được công bố?
- **Deployment:** instance chạy trên Kubernetes, VM, container platform hay môi trường khác?
- **Discovery source:** DNS, registry, Kubernetes Service, gateway hay mesh?
- **Ownership:** ai đăng ký/gỡ endpoint, ai quản lý health?
- **Readiness:** điều kiện nào cho biết service có thể nhận traffic?
- **Endpoint update:** client/proxy nhận thay đổi bằng TTL, poll, watch hay data plane?
- **Connection lifecycle:** timeout, keep-alive, pool TTL, graceful drain?
- **Routing policy:** round-robin, weighted, locality, canary, session affinity?
- **Failure semantics:** khi không còn endpoint, trả lỗi gì, retry thế nào, có fallback không?
- **Security:** DNS/registry quyền truy cập, server identity, TLS/mTLS, authz?
- **Version overlap:** contract có tương thích trong rolling update không?
- **Observability:** có đo resolution failure, stale endpoint, propagation delay, connection reset và p99 không?
- **Recovery:** khi DNS/registry/control plane lỗi, client có dùng dữ liệu cũ an toàn được trong bao lâu?
- **Testing:** có mô phỏng scale out, scale in, rolling update, mất resolver và stale connection chưa?

Checklist này không ép mọi service dùng cùng một công nghệ. Mục đích là **làm rõ đường đi của một request và cách đường đi ấy thay đổi khi môi trường vận hành thay đổi**.

## 22. Kết luận

**DNS** giúp biến tên dịch vụ thành các bản ghi địa chỉ hoặc định tuyến theo ngữ nghĩa DNS. **Service registry** quản lý danh sách instance và metadata/health theo mô hình của nền tảng. **Load balancer/proxy/client** chọn endpoint cho request cụ thể. **Endpoint update** đồng bộ việc instance gia nhập, rút lui và không còn phục vụ tới các thành phần đang định tuyến.

Một kiến trúc microservices đáng tin cậy không chỉ “gọi được bằng hostname”. Nó cần hiểu vòng đời endpoint, TTL và cache, connection reuse, readiness, graceful shutdown, propagation delay, failover, routing policy, quyền sở hữu và observability. Với Kubernetes, Service/EndpointSlice giải quyết nhiều phần của discovery; với môi trường khác có thể cần registry hoặc proxy phù hợp. Chọn cơ chế đơn giản nhất đáp ứng yêu cầu thay đổi động và độ tin cậy, rồi kiểm chứng bằng rollout và failure testing thực tế.

Điểm ghi nhớ cuối cùng: **Tên logic phải ổn định đối với consumer, trong khi tập endpoint phía sau có thể thay đổi liên tục.** Thiết kế discovery tốt che bớt sự biến động đó khỏi business code, nhưng không được che giấu các trạng thái lỗi mà hệ thống cần nhận biết và phục hồi.
