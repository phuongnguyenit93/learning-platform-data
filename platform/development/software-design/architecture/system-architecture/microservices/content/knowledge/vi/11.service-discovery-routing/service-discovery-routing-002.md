# Khám phá dịch vụ phía client và phía máy chủ

> **Chủ đề:** Software Design Architecture System Architecture Microservices  
> **Nhánh kiến thức:** Khám phá và định tuyến  
> **Mục tiêu:** Hiểu cách một dịch vụ tìm đúng instance đang phục vụ của dịch vụ khác; phân biệt client-side service discovery và server-side service discovery; thiết kế registry, DNS, load balancing, health checks, routing và failover phù hợp với môi trường triển khai.

## 1. Vì sao kiến trúc phân tán phải khám phá dịch vụ?

Trong ứng dụng một tiến trình, module A gọi module B qua hàm hoặc interface đã biết. Trong kiến trúc nhiều tiến trình, dịch vụ Ordering cần gọi Pricing hoặc Inventory qua mạng. Nhưng địa chỉ thực tế của từng instance không cố định: container khởi động lại, pod được thay mới, autoscaler thêm bớt replica, node hỏng, môi trường canary được mở và vùng triển khai có thể chuyển đổi.

Ví dụ, Pricing có ba instance:

~~~text
pricing-1  10.20.1.14:8080
pricing-2  10.20.2.51:8080
pricing-3  10.20.3.76:8080

Ordering cần gọi "pricing" — không nên ghi cố định một IP ở code.
~~~

**Service discovery** là cơ chế biến **định danh logic** của dịch vụ, chẳng hạn pricing, thành một hoặc nhiều **điểm cuối thực tế** có thể được sử dụng. Nó trả lời: “Các instance nào hiện có thể nhận request cho dịch vụ này?” Sau đó hệ thống còn phải quyết định **instance nào được chọn**, **khi nào coi là không khỏe**, **gửi qua đường mạng nào** và **xử lý ra sao khi địa chỉ đã lỗi thời**.

Bài toán discovery không chỉ là lưu danh sách IP. Trong vận hành thực tế, nó liên quan mật thiết đến service registration, health/readiness, endpoint lifecycle, load balancing, routing policy, security identity, connection pooling và observability.

### Mục tiêu học tập

Người học có thể:

- Phân biệt tên dịch vụ logic, service instance, service registry, DNS, endpoint và network load balancer.
- Mô tả trình tự gọi dịch vụ ở **client-side discovery** và **server-side discovery**.
- Nhận biết trách nhiệm của caller, registry, proxy/gateway và nền tảng điều phối.
- Chọn mô hình theo khả năng của client, quy mô hệ thống, ngôn ngữ lập trình và yêu cầu vận hành.
- Thiết kế lifecycle register → ready → serve → drain → deregister và chống gọi nhầm instance lỗi.
- Giải thích kết hợp DNS/Kubernetes Service/EndpointSlice, service mesh, gateway và load balancing.
- Xử lý stale endpoints, DNS caching, connection reuse, retry storm, circuit breaking, zone affinity và canary routing.
- Phác thảo kế hoạch triển khai, đo lường, chạy thử lỗi và migration có thể rollback.

## 2. Những khái niệm nền tảng

| Khái niệm | Nghĩa thực tế | Ví dụ |
| --- | --- | --- |
| **Logical service name** | Tên ổn định đại diện cho một capability | pricing, inventory, payment |
| **Service instance** | Một bản chạy cụ thể của dịch vụ | pricing pod 10.20.1.14:8080 |
| **Endpoint** | Địa chỉ và cổng được định tuyến tới, đôi khi gồm protocol/metadata | HTTPS 10.20.2.51:8443 |
| **Service registry** | Nguồn thông tin về instance và trạng thái/thẻ | Một catalog dịch vụ có đăng ký và lease |
| **Registration** | Đưa instance vào danh sách có thể khám phá | pricing-2 đăng ký endpoint |
| **Discovery query/watch** | Tra cứu hoặc theo dõi cập nhật danh sách instance | resolve("pricing") |
| **Load balancer** | Chọn đích xử lý giữa các endpoint đủ điều kiện | round-robin, least requests |
| **Health check** | Xác định instance có thể hoạt động; cần phân biệt liveness/readiness | GET /ready |
| **Service DNS** | Chuyển tên dịch vụ thành địa chỉ hoặc danh sách địa chỉ qua DNS | pricing.svc.cluster.local |
| **Proxy/gateway** | Trung gian nhận request rồi tìm/chọn đích | L7 reverse proxy, ingress, sidecar |
| **Routing policy** | Luật chọn instance, version, zone, tenant hoặc vùng | 10% traffic sang canary |
| **Service identity** | Danh tính bảo mật của workload, không nhất thiết là IP | mTLS certificate/workload identity |

Một **registry** có thể cấp dữ liệu cho client library hoặc cho proxy. **Load balancing** có thể diễn ra ở client, ở proxy hoặc ở một thành phần mạng. **DNS** chỉ là một cơ chế phân giải tên và không tự quyết định đầy đủ mọi chính sách cân tải, retry, health và version.

### 2.1. Không đồng nhất service name với IP

Tên service thể hiện ý nghĩa ổn định theo cấu trúc tổ chức hoặc miền nghiệp vụ; IP/port là chi tiết chạy ở một thời điểm. Cấu hình thường nên chứa **logical destination** hoặc tên DNS ổn định, không hard-code danh sách instance.

Ví dụ:

~~~text
Ý định trong code:
    pricing.quote(order)

Chi tiết có thể thay đổi dưới hạ tầng:
    https://10.20.1.14:8443
    https://10.20.2.51:8443
    https://10.20.3.76:8443
~~~

Dù có registry, caller vẫn phải biết **hợp đồng API** của pricing: endpoint, schema, authentication, timeout, version và ý nghĩa lỗi. Discovery giải quyết việc tìm **ở đâu**, không thay thế API contract về **làm gì**.

### 2.2. Control plane và data plane

Một góc nhìn hữu ích:

- **Control plane:** nhận đăng ký, health, cấu hình, topology, endpoint discovery, routing policy.
- **Data plane:** thực sự chuyển request/response và dữ liệu giữa các dịch vụ.

Nếu control plane ngừng hoạt động tạm thời, một hệ thống tốt có thể vẫn xử lý request bằng cấu hình/endpoint đã được đồng bộ trong thời gian hợp lý, nhưng cập nhật topology, chính sách hoặc chứng chỉ có thể bị trễ. Không có gì bảo đảm tuyệt đối: hành vi khi registry không sẵn sàng phụ thuộc thiết kế cache, lease và hạ tầng.

## 3. Client-side service discovery là gì?

Ở **client-side discovery**, ứng dụng gọi (hoặc thư viện/proxy logic nằm trong phạm vi client-side) lấy danh sách instance và **tự chọn đích** để gửi request. Hệ thống caller chịu trách nhiệm cân tải, thường phối hợp với kết quả health, zone và các quy tắc retry.

### 3.1. Trình tự một request

~~~text
              (1) đăng ký/heartbeat
[Pricing instance A] -------------------+
[Pricing instance B] -------------------+--> [Service Registry]
[Pricing instance C] -------------------+
                                              ^
                                              | (2) resolve / watch pricing
                                              |
[Ordering service] ---- discovery client -----+
       |
       | (3) danh sách: A, B, C
       | (4) chọn B theo load-balancing policy
       +----------------------------------> [Pricing B]
       <---------------------------------- response
~~~

Một triển khai điển hình:

1. Pricing instance được hệ thống đăng ký khi có thể nhận traffic.
2. Registry hoặc hệ thống quản lý endpoint phản ánh trạng thái/metadata.
3. Ordering hỏi registry hoặc nhận luồng cập nhật các instance của Pricing.
4. Load-balancing client trong Ordering lọc endpoint được phép và chọn một endpoint.
5. Ordering tạo/gửi request trực tiếp đến endpoint đó.
6. Khi instance lỗi, Ordering có thể loại tạm, chọn đích khác hoặc trả lỗi theo deadline/retry policy.

Không bắt buộc query registry cho **mỗi request**. Thư viện thường giữ cache và nhận cập nhật theo polling/watch để tránh registry trở thành nút thắt.

### 3.2. Caller chịu những trách nhiệm gì?

Trong mô hình này, caller hoặc SDK phải làm đúng các công việc:

- Resolve logical service name thành endpoints.
- Cache danh sách, đặt thời hạn cập nhật và xử lý cache stale.
- Chọn endpoint theo thuật toán, metadata, zone hoặc phiên bản phù hợp.
- Tạo connection và tái sử dụng connection pool đúng cách.
- Đặt timeout, deadline và retry hợp lý khi endpoint lỗi.
- Truyền thông tin TLS, authentication và tracing.
- Quản lý trạng thái circuit breaker/outlier nếu hệ thống có.
- Theo dõi metric theo logical service và theo endpoint được chọn.

Bởi vậy, client-side discovery tạo độ chủ động cao nhưng có thể làm **SDK trên nhiều ngôn ngữ** trở nên phức tạp. Nếu mỗi team viết một thuật toán chọn endpoint khác nhau, chính sách hệ thống dễ thiếu nhất quán.

### 3.3. Ưu điểm

- **Bỏ bớt một hop proxy trực tiếp** trong trường hợp caller thực sự gửi đến instance được chọn.
- **Chủ động lựa chọn đích:** ứng dụng có thể dùng thông tin request, affinity, zone hoặc loại workload.
- **Có thể cân tải thông minh ở client:** kết hợp local stats, circuit breaker và giới hạn concurrency.
- **Phù hợp với kết nối dài/gRPC** nếu client hiểu nhiều endpoint và chủ động phân phối stream/connection.
- **Không nhất thiết có một LB làm data-plane bottleneck chung**, dù registry/control plane vẫn là thành phần chung.

### 3.4. Nhược điểm và đánh đổi

- Mọi client library cần hỗ trợ discovery, cache, update và thuật toán cân tải.
- Logic có thể không đồng nhất giữa Java, Go, Node.js, Python và mobile clients.
- Client cần truy cập registry hoặc một nguồn endpoint; phải bảo vệ quyền và độ khả dụng nguồn này.
- Thay đổi chiến lược routing có thể cần cập nhật SDK hoặc cấu hình phân phối rộng.
- Khi topology thay đổi nhanh, stale cache dễ khiến một số client gọi endpoint đã rời hệ.
- Khó bảo đảm mọi caller tuân thủ chính sách trung tâm nếu không có cơ chế thực thi độc lập.

**Phù hợp nhất** khi các caller do tổ chức kiểm soát, có SDK/platform layer tốt, yêu cầu routing linh hoạt và muốn giảm dependency vào một tầng proxy L7 chung.

## 4. Server-side service discovery là gì?

Ở **server-side discovery**, client chỉ biết một **địa chỉ ổn định** của dịch vụ, chẳng hạn load balancer, gateway hoặc virtual IP. Một thành phần ở phía hạ tầng nhận request, lấy/nhận danh sách backend và **chọn instance**. “Server-side” trong thuật ngữ này chỉ mô hình lựa chọn backend qua trung gian; không nhất thiết chính application server đích tự tìm nhau.

### 4.1. Trình tự request

~~~text
[Pricing instances] ---- registration/health ----> [Registry / Endpoints]
                                                       |
                                                       | backend list
                                                       v
[Ordering] ---> [pricing.internal / proxy / LB] ---> [Pricing B]
                 ^ stable address                 backend selected
                 |
                 +-- client không cần biết IP từng Pricing instance
~~~

Một request đi qua các bước:

1. Ordering gửi tới logical address hoặc DNS ổn định của Pricing.
2. Proxy/LB nhận request và có thông tin những backend phù hợp.
3. Proxy/LB chọn đích theo policy: round-robin, least requests, weights, zone, health...
4. Proxy chuyển tiếp và xử lý kết nối tới backend.
5. Khi backend rời hệ, proxy cập nhật pool, ngừng route mới và có thể drain connection.
6. Caller nhận response theo hợp đồng API thông thường.

### 4.2. Ưu điểm

- Caller đơn giản hơn; có thể dùng HTTP/gRPC client tiêu chuẩn.
- Centralized policy: health, canary, traffic splitting, retries hoặc rate limit nếu proxy hỗ trợ.
- Hữu ích khi có nhiều ngôn ngữ lập trình, đối tác và client khó quản lý thư viện.
- Có điểm tập trung để ghi log, metric, TLS termination hoặc kiểm soát truy cập theo yêu cầu.
- Đổi backend mà ít hoặc không cần đổi code client.

### 4.3. Nhược điểm và đánh đổi

- Thêm tầng proxy/virtual service cần được vận hành, theo dõi và đảm bảo HA.
- Tùy lớp cân tải, có thể tăng latency, tiêu thụ băng thông và tài nguyên trung gian.
- Proxy/data plane cấu hình kém có thể trở thành điểm nghẽn hoặc khuếch đại lỗi.
- Một số quyết định thông minh dựa trên ngữ cảnh nghiệp vụ của caller khó đưa vào proxy nếu không có contract/metadata thích hợp.
- Connection reuse có thể làm traffic không đều nếu LB chỉ cân ở cấp kết nối thay vì cấp request.
- Canary, sticky session, tenant affinity và policy của nhiều lớp proxy có thể xung đột nếu không thống nhất.

Một proxy không nhất thiết là **single point of failure**: nó có thể có nhiều replica, route qua hạ tầng cân tải khác hoặc vận hành phân tán. Nhưng cần chứng minh topology và failover thực tế, không chỉ giả định “có LB là luôn an toàn”.

## 5. So sánh trực tiếp hai mô hình

| Khía cạnh | Client-side discovery | Server-side discovery |
| --- | --- | --- |
| Ai tìm/nhận danh sách instance? | Client library/SDK của caller | Proxy, LB hoặc hạ tầng định tuyến |
| Ai chọn instance? | Caller | Tầng trung gian |
| Địa chỉ caller thường gọi | Một endpoint cụ thể sau resolve | Tên/địa chỉ ổn định của service |
| Độ phức tạp ở ứng dụng | Cao hơn; SDK cần logic discovery | Thấp hơn; app thường chỉ biết service URL |
| Độ phức tạp ở hạ tầng | Registry/control plane; client policies | Proxy/LB, backend health, routing config |
| Routing theo ngữ cảnh caller | Linh hoạt nếu SDK hỗ trợ | Phụ thuộc metadata có thể đưa đến LB |
| Quản trị policy tập trung | Cần SDK/config thống nhất | Thường thuận lợi hơn |
| Hiệu năng | Có thể bỏ bớt proxy hop | Có thể thêm hop; một số VIP/L4 rất hiệu quả |
| Khả năng hỗ trợ client đa ngôn ngữ | Phải có SDK phù hợp từng môi trường | Dễ dùng với client chuẩn |
| Failover | Client phải phát hiện và chọn lại | Proxy chọn lại backend, caller vẫn cần timeout |
| Ví dụ điển hình | SDK query/watch registry rồi kết nối IP pod | Reverse proxy/gateway/Kubernetes Service VIP |
| Nguy cơ | Cache stale, policy khác nhau, registry access | Bottleneck, proxy failure, stale backend config |

Bảng này mô tả hai **mẫu hình lựa chọn endpoint**, không phải phân loại nhãn tuyệt đối của một sản phẩm. Nhiều hệ thống kết hợp hai mô hình: ứng dụng gọi DNS ổn định, proxy cạnh ứng dụng tìm và chọn instance, sau đó data plane chuyển request.

### Câu hỏi ra quyết định

- Client có nằm hoàn toàn trong phạm vi kiểm soát của đội phát triển không?
- Có bao nhiêu ngôn ngữ hoặc runtime cần SDK?
- Có yêu cầu route theo zone, phiên bản, tenant, workload hay quyền truy cập không?
- Muốn canary và thay đổi policy mà không redeploy client?
- Registry/control plane có độ sẵn sàng và cơ chế cache nào?
- Proxy hop có đáng kể trong latency budget không?
- Một endpoint đang được dùng bởi bao nhiêu kết nối dài?
- Ai sẽ trực sự cố khi routing hoặc danh sách backend bị sai?

## 6. Service registry: ai đăng ký, ai giữ và ai xóa instance?

Registry là một nguồn dữ liệu về **những instance được phép nhận request**. Không phải mọi nền tảng đều dùng registry độc lập: orchestrator có thể tự quản lý endpoints và cung cấp discovery qua DNS/API.

### 6.1. Self-registration

Ứng dụng tự đăng ký với registry khi khởi động, cập nhật lease/heartbeat và chủ động deregister khi shutdown.

~~~text
Instance starts
    |
    v
Load config, connect dependencies
    |
    v
Register instance/lease
    |
    v
Heartbeat / renew lease
    |
    v
Drain / deregister on shutdown
~~~

**Ưu điểm:** ứng dụng có thể đăng ký metadata nghiệp vụ hoặc custom readiness dễ dàng.

**Đánh đổi:** mã ứng dụng phải hiểu registry, heartbeat, lease và deregistration. Khi process bị kill cứng, lệnh deregister có thể không chạy; registry cần TTL/health hoặc cơ chế phát hiện lỗi độc lập.

Điểm quan trọng: **không được quảng bá sẵn sàng quá sớm**. Process lắng nghe port chưa có nghĩa đã load config, khởi tạo connection và đủ điều kiện phục vụ.

### 6.2. Third-party registration

Hạ tầng triển khai/orchestrator/agent quan sát instance và cập nhật registry. Ứng dụng chỉ cần cung cấp liveness/readiness hoặc metadata chuẩn.

~~~text
Deploy controller / node agent / orchestrator
        |
        +--> observe instance lifecycle
        +--> evaluate readiness
        +--> update endpoint registry
                          |
                          v
                  Consumers / proxies
~~~

Ưu điểm là ứng dụng giảm coupling với registry, phù hợp đa ngôn ngữ. Đổi lại, platform layer cần được vận hành đúng, có nguồn sự thật rõ và theo dõi sự chậm cập nhật.

### 6.3. Discovery registry cần lưu gì?

Tối thiểu thường là:

- Logical service name và namespace/environment.
- Instance ID ổn định trong vòng đời một lần chạy.
- Endpoint address, port, protocol.
- Availability/readiness hoặc thông tin lease.
- Metadata cần thiết cho routing: version, zone, region, capability, weight.
- Thời điểm cập nhật và TTL nếu dùng lease.
- Quyền đăng ký, sửa và tra cứu.

Không coi registry là một thư mục tùy ý để mọi ứng dụng viết endpoint của người khác. Cần authentication, authorization và khả năng kiểm toán thay đổi.

### 6.4. Nhất quán và độ trễ cập nhật

Danh sách endpoints có thể **không nhất quán tức thời** giữa registry, client cache, DNS cache và proxy. Instance đã bị rút khỏi registry nhưng một caller vẫn giữ connection cũ hoặc địa chỉ đã cache.

Vì vậy discovery không thay thế cho timeout, retry, readiness và graceful shutdown. Các thành phần phải chịu được việc gọi đến endpoint không còn sẵn sàng trong một khoảng ngắn.

## 7. Health checks, readiness, liveness và graceful shutdown

Đây là phần dễ bị xem nhẹ trong service discovery.

### 7.1. Liveness khác readiness

- **Liveness:** tiến trình có còn sống theo nghĩa cần thiết để tự phục hồi/restart không?
- **Readiness:** tiến trình có thể nhận **request mới** hay chưa?
- **Startup condition:** tiến trình đã hoàn thành giai đoạn khởi tạo cần thiết hay chưa?

Một ứng dụng đang chạy nhưng đang chờ kết nối bắt buộc, chưa warm cache hoặc đang drain có thể **alive nhưng không ready**. Liveness quá “nhạy” với phụ thuộc tạm thời dễ làm hệ thống restart hàng loạt trong một incident. Readiness cũng cần thiết kế theo luồng thực: nếu mọi pod cùng loại mình khỏi endpoint khi một dependency chung lỗi, có thể làm tình hình xấu hơn.

### 7.2. Đưa instance vào nhận traffic

~~~text
STARTING
   |
   | load config, secrets, app, local state
   v
READY
   |
   | advertised by registry / endpoints
   v
SERVING
   |
   | preStop / shutdown signal / planned rollout
   v
DRAINING
   |
   | stop new traffic, finish in-flight requests
   v
STOPPED
~~~

Khi triển khai rolling update, instance mới cần đạt readiness trước khi thay hoàn toàn instance cũ. Khi hủy instance, thông thường cần rút readiness hoặc ngừng đăng ký **trước** khi đóng kết nối đang xử lý, chờ khoảng propagation/draining phù hợp rồi mới dừng hẳn.

Trình tự cụ thể tùy runtime, proxy, network và nền tảng. Không có một thời gian drain mặc định đúng cho tất cả workload, đặc biệt với HTTP streaming, WebSocket hoặc gRPC dài.

### 7.3. Stale discovery phải được xử lý như lỗi bình thường

Ngay cả khi health check tốt, vẫn có khoảng:

1. Một instance bắt đầu hỏng.
2. Health check chưa kịp phát hiện.
3. Registry/proxy/client vẫn coi endpoint là ready.
4. Request mới tiếp tục tới và lỗi.

Cần deadline, connection timeout, retry có giới hạn, circuit breaker và/hoặc outlier detection theo yêu cầu. Những cơ chế này **bổ sung**, không thay thế service discovery.

## 8. Cân bằng tải sau khi khám phá

Discovery tìm tập endpoint; **load balancing** quyết định đích cho mỗi kết nối hoặc request.

### 8.1. Một số chính sách thường gặp

| Chính sách | Ý tưởng | Khi hữu ích | Điểm cần lưu ý |
| --- | --- | --- | --- |
| Round-robin | Chọn lần lượt | Backend tương đối đồng đều | Không tự tính yêu cầu có độ nặng khác nhau |
| Random | Chọn ngẫu nhiên | Đơn giản, nhiều backend tương tự | Có dao động thống kê |
| Least connections / least requests | Chọn đích ít tải đang xử lý | Request duration khác nhau | Phải hiểu số đo và cấp cân tải |
| Weighted | Phân traffic theo trọng số | Backend năng lực khác, canary | Cần thay đổi weight có kiểm soát |
| Consistent hashing | Cùng key thường đi cùng nhóm đích | Cache locality, affinity | Skew/hot key và remapping khi topology đổi |
| Zone-aware/locality | Ưu tiên cùng zone/region | Giảm latency/chi phí cross-zone | Không nên phá khả năng failover |
| Adaptive/outlier-aware | Dùng signal latency, error, tải | Hệ thống phức tạp, scale lớn | Nếu policy sai có thể gây dao động hoặc khuếch đại lỗi |

Không có thuật toán tối ưu mọi workload. Một request đọc rất nhanh và một job kéo dài 30 giây không nên chỉ nhìn cùng chỉ số “số kết nối” để kết luận phân tải đều.

### 8.2. Cân tải ở cấp kết nối hay request?

Với TCP/L4 LB, quyết định backend có thể diễn ra khi **thiết lập kết nối**. Một HTTP/2 hoặc gRPC connection có thể mang nhiều request/stream đến cùng backend, làm phân phối lệch dù connection count ban đầu cân đều.

L7 proxy có thể quyết định theo request tùy protocol/configuration. Client-side LB cũng phải hiểu việc connection pool giữ nhiều kết nối hay gộp request vào một kênh. Đừng đánh giá cân tải chỉ bằng “có ba pod nhưng pod thứ nhất rất nóng” mà bỏ qua connection reuse và sticky affinity.

### 8.3. Timeout và retry không được bỏ qua tính đúng đắn

Nếu request thất bại ở endpoint A, retry B có thể giảm lỗi nhưng:

- Request gốc có thể **đã được thực thi** dù caller timeout.
- Gọi lại lệnh thanh toán, giữ chỗ hoặc gửi email có thể tạo side effect trùng.
- Retry ở client và proxy cùng lúc có thể nhân số attempt.
- Khi nhiều backend cùng overload, retry có thể tạo bão.

Dùng **idempotency key**, retry budget, deadline truyền xuyên tầng, backoff/jitter khi phù hợp và chính sách không retry tự động với thao tác không an toàn nếu thiếu bảo vệ.

## 9. DNS-based discovery

DNS là cách phổ biến để ứng dụng gọi một tên dịch vụ ổn định thay vì IP cụ thể.

~~~text
Ordering:
    https://pricing.internal

DNS:
    pricing.internal -> 10.40.0.12

Network/LB:
    10.40.0.12 -> Pricing instances
~~~

Có hai biến thể quan trọng:

1. DNS trả địa chỉ **virtual IP/load balancer**. Client kết nối tới địa chỉ ổn định, hạ tầng chọn backend: thiên về server-side balancing.
2. DNS trả **nhiều địa chỉ instance**. Client/runtime nhận tập địa chỉ rồi chọn/kết nối: gần với client-side endpoint selection, tùy cơ chế resolver và thư viện thực tế.

### 9.1. Các điểm khó của DNS

- **TTL và caching:** resolver, OS, JVM, thư viện và proxy có thể cache khác nhau.
- **Record update:** thay đổi DNS không có nghĩa mọi client chuyển ngay lập tức.
- **Kết nối đang mở:** DNS đổi nhưng connection pool vẫn có thể dùng endpoint cũ.
- **Nhiều A/AAAA record:** không nên giả định mọi client sẽ cân bằng request đều hoặc xử lý lỗi tốt.
- **Negative caching:** kết quả không tìm thấy có thể được giữ tạm.
- **SRV/service-specific metadata:** có thể giúp biểu diễn port/priority trong một số mô hình, nhưng không phải client nào cũng hỗ trợ.
- **Bảo mật:** DNS spoofing, quyền sửa bản ghi và độ tin cậy của resolver cần được xem xét theo môi trường.

DNS rất hữu ích để giảm coupling, nhưng để cân tải và failover tốt cần biết **hành vi thực của HTTP/gRPC client**, không chỉ nhìn bản ghi DNS.

### 9.2. Ví dụ Java và DNS caching

Một HTTP client Java tạo connection pool thường phân giải tên khi cần tạo kết nối; request sau có thể tái sử dụng connection mà không thực hiện DNS lookup mới. Nếu một pod cũ bị xóa, request qua connection stale có thể lỗi trước khi pool cập nhật.

Khi gặp sự cố kiểu “đã đổi DNS nhưng traffic vẫn vào backend cũ”, hãy kiểm tra:

- Cache DNS tại client/JVM và resolver.
- Thời gian sống/idle timeout của pooled connections.
- Cơ chế health và khả năng phát hiện connection lỗi.
- Graceful shutdown và propagation delay.
- Số lần retry, request idempotency và log endpoint thực tế.

Đừng tự đặt DNS TTL cực thấp mà không đo ảnh hưởng đến resolver và hạ tầng DNS; TTL thấp cũng không buộc mọi connection đang mở phải chuyển đích.

## 10. Kubernetes: Service, EndpointSlice và headless service

Kubernetes cung cấp các khối xây dựng khiến ứng dụng thường không phải tự triển khai registry riêng.

### 10.1. Service thông thường và virtual IP

Một Service chọn nhóm pod/endpoint theo cấu hình và cung cấp tên DNS ổn định. Tùy chế độ networking, lưu lượng đến Service IP được phân phối tới backend bởi thành phần data plane của cluster (ví dụ kube-proxy, cơ chế IPVS/eBPF hoặc giải pháp tương đương).

~~~text
[Ordering Pod]
      |
      | HTTP https://pricing.default.svc.cluster.local
      v
[Kubernetes Service DNS/ClusterIP]
      |
      +--------> [Pricing Pod 1]
      +--------> [Pricing Pod 2]
      +--------> [Pricing Pod 3]
      ^
      |
  endpoint/readiness state
  do controller duy trì
~~~

Từ góc độ application code, client sử dụng **một tên service**; việc chọn backend do hạ tầng chịu trách nhiệm. Đây thường là ví dụ thực dụng của server-side service discovery/balancing ở lớp network. Tuy nhiên, thuật ngữ “server-side” không đồng nghĩa traffic nhất thiết đi qua một proxy HTTP trung tâm; ở cluster có thể là NAT/L4 dataplane.

### 10.2. EndpointSlice và readiness

Các đối tượng endpoint do cluster quản lý phản ánh địa chỉ backend cùng các điều kiện liên quan. Khi pod thay trạng thái readiness, endpoint controller/data plane cập nhật đường đi của traffic.

Điều đó **không loại bỏ hoàn toàn race condition** khi pod sắp dừng. Cần readiness probe đúng và quá trình drain hợp lý để giảm lỗi trong rolling deploy, node failure hoặc autoscaling.

### 10.3. Headless Service

Một headless Service không cung cấp ClusterIP cân tải kiểu thông thường; DNS có thể trả các địa chỉ pod/endpoint tương ứng. Ứng dụng hoặc thư viện nhận được tập đích và tự quyết định kết nối. Đây là mẫu phù hợp với các hệ thống cần biết instance cụ thể, như clustered database hoặc client có balancing logic riêng.

~~~text
Client resolver:
    pricing-headless.default.svc.cluster.local
        |
        +--> 10.20.1.14
        +--> 10.20.2.51
        +--> 10.20.3.76

Client/lib quyết định kết nối đến đích nào.
~~~

Không nên chọn headless chỉ vì muốn “tối ưu hiệu năng”. Bạn phải có chiến lược xử lý DNS update, lỗi endpoint, phân tải và connection pooling tương ứng.

### 10.4. Ingress/Gateway khác service discovery nội bộ

**Ingress/Gateway API/L7 gateway** thường nhận traffic từ bên ngoài hoặc xử lý routing HTTP phức tạp; **Service** cung cấp một cách định tuyến ổn định tới workload trong cluster. Một số gateway còn được dùng cho east–west traffic, nhưng cần phân biệt điểm vào API và lớp khám phá nội bộ.

Một hệ thống có thể dùng Gateway cho public client, Kubernetes Service cho traffic nội bộ và thêm service mesh cho chính sách mTLS/tracing. Không nhất thiết dồn mọi giao tiếp qua API gateway chỉ vì có nhiều microservice.

## 11. Service mesh và trường hợp ranh giới bị pha trộn

Service mesh thường cung cấp proxy/data plane và control plane để phân phối endpoint và policy. Ứng dụng gọi một tên service hoặc một local proxy; proxy quyết định upstream instance, retry, mTLS và telemetry tùy cấu hình.

~~~text
[Ordering App]
      |
      v
[Local data-plane proxy]
      |
      | endpoint discovery/routing policy từ control plane
      v
[Remote data-plane proxy / Pricing App]
~~~

Ở đây câu hỏi “client-side hay server-side?” không hoàn toàn nhị phân:

- **Từ góc nhìn code ứng dụng:** app không tự chọn backend, giống server-side abstraction.
- **Từ góc nhìn data plane:** proxy nằm cạnh client có thể trực tiếp chọn upstream theo danh sách đã được phân phối, là **proxy-side discovery/load balancing**.
- **Từ góc nhìn platform:** control plane cung cấp topology/policy, còn data plane thực thi.

Do đó hãy mô tả **ai quyết định endpoint và ở tầng nào**, thay vì ép mọi triển khai mesh vào một nhãn đơn giản.

### 11.1. Khi nào mesh tạo ích lợi?

- Nhiều service/ngôn ngữ cần chính sách mTLS và identity thống nhất.
- Muốn quan sát traffic và điều chỉnh routing mà không sửa mọi client.
- Cần canary, fault injection, retries hoặc traffic splitting với quy tắc nhất quán.
- Đội platform có đủ năng lực giám sát và cập nhật các proxy/control plane.

### 11.2. Chi phí không được bỏ qua

- Tăng số thành phần và cấu hình cần vận hành.
- Dễ có retry/circuit breaker trùng giữa SDK và proxy.
- Có overhead CPU/memory, latency và connection behavior.
- Sai policy có thể ảnh hưởng diện rộng.
- Tracing và lỗi có thêm tầng cần đọc.
- Cert rotation, identity và sidecar lifecycle cần quản lý.

Không dùng mesh chỉ để tránh cấu hình một URL. Chọn lớp hạ tầng nhẹ nhất đáp ứng các nhu cầu thực.

## 12. Ví dụ xuyên suốt: Ordering gọi Pricing và Inventory

Giả sử hệ thống thương mại điện tử có:

- **Ordering:** tiếp nhận và quản lý đơn hàng.
- **Pricing:** báo giá, tính tổng tiền.
- **Inventory:** kiểm tra hoặc giữ hàng.
- **Gateway/BFF:** nhận request từ web/mobile.

Để đơn giản, xem hai lời gọi đọc/kiểm tra Pricing và Inventory trong một tương tác. Nếu phải tạo giao dịch phân tán, quy tắc nghiệp vụ và saga cần được thiết kế riêng; discovery không giải quyết tính nhất quán dữ liệu.

### 12.1. Phương án A — client-side discovery

~~~text
Browser --> Gateway --> Ordering
                          |
                          +--> Registry: resolve("pricing")
                          |        |
                          |        +--> pricing-A, pricing-B, pricing-C
                          |
                          +--> select pricing-B --> Pricing B
                          |
                          +--> Registry/cache: resolve("inventory")
                                   |
                                   +--> inventory-A, inventory-B
                          |
                          +--> select inventory-A --> Inventory A
~~~

Ordering dùng SDK discovery và load balancer. Khi Pricing B không phản hồi, SDK đánh dấu lỗi hoặc cập nhật danh sách, cân nhắc endpoint khác theo timeout/retry policy. Ordering vẫn phải đối xử đúng với lỗi Pricing: không được tự coi giá đã hợp lệ.

### 12.2. Phương án B — server-side discovery

~~~text
Browser --> Gateway --> Ordering
                          |
                          +--> pricing.internal --> Pricing LB --> Pricing B
                          |
                          +--> inventory.internal --> Inventory LB --> Inventory A

LB/backend discovery chịu trách nhiệm chọn instance.
Ordering chỉ gọi logical service addresses.
~~~

Ordering không cần thông tin từng instance. Đổi số replica hoặc chuyển qua phiên bản canary chủ yếu nằm ở platform/proxy configuration. Nhưng nếu Pricing LB lỗi, Ordering vẫn phải có timeout/fallback nghiệp vụ hoặc trả lỗi; không thể tin rằng tên ổn định đồng nghĩa availability tuyệt đối.

### 12.3. Phương án C — Kubernetes Service

~~~text
Order pod
   |
   +-- https://pricing:8443 ---> Service ClusterIP
   |                                      |
   |                                  Pricing Pods
   |
   +-- https://inventory:8443 -> Service ClusterIP
                                          |
                                      Inventory Pods
~~~

Application code chỉ biết tên service logic, platform giữ danh sách endpoints; readiness và network data plane xử lý phần lớn discovery/routing. Nếu cần chính sách L7 canary theo header, mTLS hoặc weighted routing tinh vi, có thể bổ sung gateway/mesh đúng phạm vi.

### 12.4. Những gì ba phương án đều cần

- API contract, version và identity/tin cậy giữa dịch vụ.
- Timeouts và deadline theo latency budget end-to-end.
- Trạng thái readiness để không route tới instance chưa sẵn sàng.
- Retry có kiểm soát và idempotency cho hành động có tác dụng phụ.
- Distributed tracing, metric và log ghi destination logical/instance.
- Khả năng chuyển đổi endpoint, rolling update và drain an toàn.
- Kịch bản dependency unavailable và xử lý phù hợp cho người dùng.

## 13. Ví dụ thiết kế Java/Spring theo hướng không khóa vào hạ tầng

### 13.1. Business code không cần biết IP

~~~java
public interface PricingClient {
    Quote calculateQuote(QuoteRequest request);
}

public final class CheckoutApplication {
    private final PricingClient pricingClient;

    public CheckoutApplication(PricingClient pricingClient) {
        this.pricingClient = pricingClient;
    }

    public CheckoutPreview preview(Cart cart) {
        Quote quote = pricingClient.calculateQuote(
            new QuoteRequest(cart.items()));
        return CheckoutPreview.from(cart, quote);
    }
}
~~~

Ứng dụng phụ thuộc vào interface có nghĩa nghiệp vụ. Infrastructure adapter quyết định cách thực thi HTTP call và cách tìm endpoint. Điều này giúp thay discovery strategy mà không sửa lõi nghiệp vụ.

### 13.2. Adapter client-side discovery — mã giả

~~~java
public final class RegistryAwarePricingClient implements PricingClient {
    private final DiscoveryClient discovery;
    private final EndpointPicker picker;
    private final HttpTransport transport;

    @Override
    public Quote calculateQuote(QuoteRequest request) {
        // Discovery trả snapshot có thể lỗi thời.
        List<Endpoint> endpoints = discovery.resolve("pricing");
        Endpoint selected = picker.chooseHealthyCandidate(endpoints);
        if (selected == null) {
            throw new UpstreamUnavailableException("pricing");
        }

        // Transport áp dụng TLS, deadline, telemetry, error mapping.
        return transport.post(
            selected.url("/v1/quotes"), request, Quote.class);
    }
}
~~~

Đây là **pseudo-code minh họa**, không phải một SDK thực có những method chính xác như trên. Trong hệ thống thật phải xử lý cache, watch, pool, retries, endpoint health, authorization, concurrency và điều kiện khi danh sách rỗng. Không được coi chỉ một lần resolve rồi chọn endpoint là đủ cho production.

### 13.3. Adapter server-side discovery — mã giả

~~~java
public final class StableAddressPricingClient implements PricingClient {
    private final HttpTransport transport;
    private final URI serviceBaseUri; // https://pricing.internal

    @Override
    public Quote calculateQuote(QuoteRequest request) {
        return transport.post(
            serviceBaseUri.resolve("/v1/quotes"),
            request,
            Quote.class);
    }
}
~~~

Transport không tự chọn IP backend. DNS/LB/proxy/người vận hành giải quyết đích thực tế. Vẫn phải quản lý connection pool, per-request deadline và status/error mapping.

### 13.4. Cấu hình theo môi trường

~~~yaml
# Ví dụ minh họa, không phải cú pháp của một sản phẩm cụ thể.
clients:
  pricing:
    logicalName: pricing
    baseUrl: https://pricing.internal
    timeoutMs: 800
    maxAttempts: 1
~~~

Không nên copy thông số timeout hoặc số lần retry từ ví dụ vào production; cần đo latency, semantics của operation và giới hạn thời gian tổng. Việc có retry ở tầng LB/mesh phải được tính cùng với retry ở ứng dụng.

### 13.5. Test thay discovery adapter

Các bài kiểm thử có thể dùng:

- **Unit test:** mock PricingClient để kiểm tra business rules, không phụ thuộc registry.
- **Contract test:** xác minh request/response đúng API version.
- **Integration test:** chạy adapter với test registry/proxy và instance được khởi tạo/hủy.
- **Failure test:** registry tạm mất kết nối; endpoint trả timeout; service scale từ 3 xuống 1 replica.
- **Latency test:** đo request end-to-end với connection reuse và routing policy thực.

Trong phương án server-side, kiểm tra hành vi LB/proxy riêng. Trong phương án client-side, kiểm tra SDK discovery, cache invalidation và selection policy.

## 14. Khi endpoint thay đổi: những tình huống lỗi điển hình

### 14.1. Instance biến mất nhưng vẫn trong cache

**Hiện tượng:** sau autoscaling down, một phần request vào IP cũ và nhận connect timeout/reset.

**Nguyên nhân khả dĩ:** registry cập nhật chậm, DNS TTL/cache, connection pool còn giữ kết nối, drain chưa xong hoặc client không xử lý endpoint failure.

**Hướng xử lý:** readiness/deregister trước khi kill; cache refresh/watch; connection failure handling; retries an toàn; đo thời gian propagation; giảm thời gian keep-alive nếu có bằng chứng. Không chỉ tăng timeout.

### 14.2. Registry ngừng hoạt động

**Client-side:** client có cache có thể tiếp tục gọi các endpoints đã biết trong một thời gian; instance mới sẽ khó được phát hiện, instance cũ có thể bị gọi quá lâu.

**Server-side:** proxy đã có backend list có thể tiếp tục hoạt động, nhưng không cập nhật kịp endpoints mới hoặc health metadata nếu control plane bị gián đoạn.

Thiết kế nên làm rõ **fail-open/fail-closed** trong từng tình huống, giới hạn độ cũ được chấp nhận, hành vi khi không có endpoint và signal để trực vận hành biết rằng registry đang lỗi. Không nên cho mọi instance tự chuyển sang danh sách ngẫu nhiên không xác thực khi registry lỗi.

### 14.3. Scale-out nhưng traffic dồn vào pod cũ

**Khả năng xảy ra:** L4 LB cân theo connection, client dùng một vài long-lived connections, sticky routing hoặc HTTP/2/gRPC multiplexing. Pod mới dù READY nhưng ít request.

**Khảo sát:** request count/active connection theo pod, behavior của client connection pool, L4/L7 mode, weights, readiness và DNS records.

**Khắc phục:** điều chỉnh cấp cân tải, kết nối, chính sách request balancing hoặc phân phối connection phù hợp; không mặc định cứ thêm replica là throughput tăng tuyến tính.

### 14.4. Retry storm khi upstream quá tải

**Hiện tượng:** latency tăng, nhiều 503/timeouts, lưu lượng upstream vượt số request gốc nhiều lần.

**Nguyên nhân:** caller, gateway và mesh cùng retry; instance unhealthy bị route lại liên tục; health thresholds gây flapping.

**Giảm rủi ro:** retry budget, giới hạn số attempt toàn đường đi, backoff/jitter cho thao tác hợp lệ, admission control, circuit breaker và graceful degradation. Với payment hoặc thao tác ghi, phải xác nhận idempotency.

### 14.5. Sự cố “cùng region nhưng đi vòng liên vùng”

Khi endpoint list không gắn zone/locality hoặc policy ưu tiên nhầm, client có thể gọi cross-region dù backend địa phương đang khỏe. Chi phí mạng và latency tăng; nếu policy cứng “chỉ cùng zone” có thể mất failover khi zone lỗi.

Cần hiểu định nghĩa locality, yêu cầu chịu lỗi, capacity từng zone và cách failover có điều kiện.

### 14.6. Canary nhận quá nhiều hoặc quá ít request

Weight 10% ở LB không nhất thiết tương ứng chính xác 10% request trong mọi thời điểm, nhất là khi sticky sessions, connection-level distribution, nhiều proxy tầng và lượng traffic thấp. Đo **thực tế ở backend và theo user/request class**; không chỉ kiểm tra đã ghi cấu hình weight 10%.

## 15. Discovery không thay thế routing chính sách nghiệp vụ

Khám phá endpoint, cân tải và quyết định nghiệp vụ là những tầng khác nhau:

- **Discovery:** có những instance nào đang có thể phục vụ?
- **Load balancing:** nên gửi request này tới instance nào?
- **Traffic management:** version nào, zone nào, canary hay production?
- **Authorization:** caller có được phép gọi capability này không?
- **Business routing:** đơn thuộc tenant nào, kho nào, tài khoản nào? Có cần định tuyến theo dữ liệu sở hữu không?

Ví dụ một Order của tenant A chỉ được xử lý tại vùng lưu trữ A do quy định dữ liệu. Nếu mọi request được random round-robin toàn bộ vùng thì có thể sai dù toàn bộ endpoints đều khỏe. Routing theo tenant/shard/region cần model riêng và contract rõ.

**Không dùng registry làm hệ thống phân quyền nghiệp vụ.** Registry có thể chứa metadata hỗ trợ routing, nhưng việc kiểm tra quyền, nơi lưu dữ liệu và tính đúng nghiệp vụ vẫn phải được thực thi ở tầng phù hợp.

### Shard-aware và stateful services

Các dịch vụ stateful không thể lúc nào cũng route tới bất kỳ instance. Một database cluster có primary/replica, một stream processor có partition ownership, một session store có quy tắc sharding.

Client-side discovery có thể hữu ích vì client nắm routing key; server-side proxy cũng có thể thực thi routing theo key nếu được cấu hình. Cần phân biệt “nhiều instance giống nhau” với “các node sở hữu dữ liệu khác nhau”.

## 16. Multi-region, failover và disaster recovery

### 16.1. Regional discovery

Một cấu trúc thường gặp:

~~~text
Ordering in region-A
      |
      +--> Pricing region-A (ưu tiên)
      |
      +--> Pricing region-B (failover, khi được phép)
~~~

Cần xác định:

- Có cho phép xử lý dữ liệu tenant ở vùng khác không?
- Ràng buộc latency, consistency và data replication.
- Failover theo health instance hay health toàn vùng?
- Chuyển sang region dự phòng có làm quá tải vùng đó không?
- Thay đổi định tuyến có cần approval/operational switch không?
- Có cơ chế quay lại vùng chính tránh oscillation?

Discovery chỉ cung cấp endpoint; **DR plan** phải bao gồm dữ liệu, capacity, quyền, kiểm tra và chạy thử. Không thể tuyên bố sẵn sàng multi-region chỉ vì tên DNS có thể trỏ sang vùng khác.

### 16.2. Global load balancing

Client ngoài internet có thể qua geo-DNS, global traffic manager hoặc edge LB. Từ đó traffic đi vào regional gateway và tới internal Service. Mỗi tầng quyết định trên dữ liệu khác nhau: địa lý, latency, health, tenancy, version và network reachability.

Phải vẽ rõ *hành trình request* để tránh có ba tầng retry và các chính sách chọn vùng xung đột.

## 17. Service identity, TLS và bảo mật

Khi địa chỉ IP liên tục thay đổi, **IP không phải định danh bảo mật đáng tin cậy**. Hệ thống cần biết caller nào đang kết nối và server nào thực sự cung cấp capability được phép.

### 17.1. Các nguyên tắc

- Dùng TLS phù hợp để bảo vệ đường truyền.
- Kiểm tra danh tính phía server khi kết nối, không chỉ kết nối thành công tới IP.
- Với mô hình zero-trust hoặc giao tiếp nội bộ nhạy cảm, có thể dùng mTLS/workload identity.
- Registry phải kiểm soát ai được đăng ký hay thay đổi endpoint.
- Không tin metadata đăng ký do một workload chưa được xác thực tự công bố.
- Phân quyền gọi service theo identity/role chứ không chỉ theo mạng hoặc IP.
- Bảo vệ secret, credential và vòng đời certificate rotation.
- Cân nhắc nguy cơ SSRF nếu endpoint discovery cho phép chèn URL ngoài phạm vi.

### 17.2. TLS với client-side discovery

Client có thể kết nối trực tiếp tới IP của instance nhưng xác minh identity theo logical service name/certificate. Phải thiết kế SNI, certificate SAN/trust policy tương ứng; không vô hiệu hóa certificate verification chỉ vì hostname và IP khác nhau.

### 17.3. TLS với server-side proxy

Có thể có TLS client → proxy và proxy → backend; mô hình termination hoặc end-to-end encryption phải được xác định. Nếu proxy có quyền giải mã, phải phù hợp ranh giới tin cậy và yêu cầu dữ liệu. Không coi việc “có HTTPS bên ngoài gateway” là bằng chứng mọi hop nội bộ đã được bảo vệ.

## 18. Observability: biết request thực sự đã đi đâu

Trong một incident, câu “Ordering gọi Pricing và lỗi” chưa đủ. Cần phân biệt lỗi resolve, lỗi chọn backend, lỗi network/TLS, timeout và lỗi nghiệp vụ từ Pricing.

### 18.1. Metric quan trọng

| Nhóm | Metric cần theo dõi | Ý nghĩa |
| --- | --- | --- |
| Registry | registration count, lease failures, watch/poll latency | Nguồn endpoint có được cập nhật không |
| Discovery client | resolve success, empty result, cache age, stale endpoint | Caller có danh sách hợp lệ không |
| Proxy/LB | healthy backend count, upstream errors, connection resets | Data plane có route tới đích khỏe không |
| Request | p50/p95/p99, error rate, retry attempts, timeout | Trải nghiệm tổng thể và tải phát sinh |
| Backend | traffic/CPU/memory/active requests theo instance | Cân tải có đều và đúng capacity không |
| Lifecycle | pod readiness changes, drain duration, failed rollouts | Thay đổi instance có làm mất request không |
| Locality | cross-zone traffic, region failover count | Chi phí và độ trễ khi chọn vùng |
| Security | TLS handshake failures, denied calls, cert expiry | Sự cố identity hoặc quyền |

### 18.2. Tracing

Một trace hợp lý có thể chứa:

~~~text
span: Browser -> Gateway
span: Gateway -> Ordering
span: Ordering -> Pricing (logical target)
  attributes:
    service.name = pricing
    net.peer.name = pricing.internal
    selected.endpoint = pricing-B
    retry.attempt = 1
span: Pricing quote calculation
~~~

Tên thuộc tính tùy chuẩn telemetry đang dùng; ví dụ thể hiện thông tin cần truy vết chứ không phải schema bắt buộc. Không thêm high-cardinality label vào mọi metric nếu gây chi phí lớn; endpoint/instance ID có thể phù hợp trong trace/log nhưng phải xem cardinality.

### 18.3. Một số cảnh báo hữu ích

- Số healthy endpoints của service trọng yếu xuống dưới mức tối thiểu.
- Discovery resolve failures hoặc empty responses tăng.
- Backend selection failures dù registry còn endpoints.
- Retry rate tăng đột biến so với request gốc.
- p99 tăng riêng trong rolling deployment.
- Cross-zone traffic bất thường hoặc canary nhận vượt weight.
- Một nhóm instance liên tục ready/unready (flapping).

Cảnh báo cần gắn owner và runbook, tránh tạo hàng trăm alert trùng khi một dependency chung lỗi.

## 19. Quy trình thiết kế và triển khai từng bước

### Bước 1 — Xác định topology hiện tại

Vẽ request path thật:

~~~text
Client --> Edge Gateway --> BFF --> Ordering --> Pricing
                                  \--> Inventory
~~~

Ghi rõ đích logic, nơi resolve, nơi load balance, nơi kiểm tra auth/TLS, các lớp retry và các thành phần dữ liệu trạng thái. Nếu đã có Kubernetes Service, API gateway hoặc mesh, không tự tạo registry mới mà chưa chứng minh thiếu chức năng gì.

### Bước 2 — Định nghĩa SLO và ràng buộc

- SLO request end-to-end và latency budget.
- Số replica, tần suất churn, autoscaling burst.
- Số ngôn ngữ/runtime cần hỗ trợ.
- Zone/region và data residency.
- Network policy và quyền đăng ký/tra cứu.
- Nhu cầu canary, traffic shifting hoặc sticky routing.
- Năng lực vận hành của team/platform.

### Bước 3 — Chọn mô hình theo từng lớp

Một bảng quyết định ví dụ:

| Bối cảnh | Hướng chọn để khảo sát | Điều kiện cần |
| --- | --- | --- |
| Nhiều HTTP service trong một Kubernetes cluster | Service DNS + ClusterIP | Readiness, network policy, timeout |
| SDK nội bộ thống nhất, routing phức tạp | Client-side discovery | Registry/SDK chuẩn, cache/watch, telemetry |
| Rất nhiều loại client cần chính sách chung | Proxy/server-side discovery | HA, capacity và observability cho proxy |
| Microservices đa ngôn ngữ với mTLS/routing phức tạp | Service mesh hoặc proxy layer | Năng lực vận hành mesh và chính sách nhất quán |
| Stateful/sharded system | Discovery có metadata ownership | Key routing, consistency và rebalancing |
| Public traffic từ internet | Edge/global LB + gateway | Rate limit, TLS, auth và regional failover |

Đây là các **ứng viên**, không phải công thức chọn công nghệ.

### Bước 4 — Thiết kế lifecycle instance

Mô tả rõ:

1. Instance khởi động, kiểm tra đủ điều kiện sẵn sàng.
2. Được đăng ký/hiển thị dưới logical service name.
3. Caller/proxy nhận endpoint mới và bắt đầu phân tải.
4. Khi unhealthy hoặc chuẩn bị shutdown, endpoint bị rút khỏi tập nhận request mới.
5. In-flight connections/requests được drain trong giới hạn cho phép.
6. Instance dừng, deregister hoặc lease hết hạn.
7. Traffic còn sót được xử lý bằng timeout/failover có kiểm soát.

### Bước 5 — Thiết kế resilience

- Deadline và retry budget cho từng request.
- Idempotency cho các command có side effect.
- Circuit breaker hoặc load-shedding theo loại lỗi.
- Connection pool và DNS cache lifecycle.
- Hành vi khi registry/control plane không sẵn sàng.
- Cách route khi service tạm không có healthy endpoint.
- Giới hạn cross-zone hoặc failover theo locality.
- Các điểm mà traffic có thể tạo vòng lặp hoặc storm.

### Bước 6 — Triển khai thí điểm

Chọn một dependency ít rủi ro, dùng feature flag hoặc cấu hình routing có thể trả về cách cũ. Đo:

- p95/p99 và tỷ lệ lỗi trước/sau.
- Tỷ lệ request tới từng instance.
- Thời gian instance mới bắt đầu nhận traffic.
- Số request lỗi khi rolling restart.
- Sự đúng đắn của auth/TLS và identity.
- Độ khó debug khi proxy/registry có sự cố.

### Bước 7 — Thử lỗi và hoàn thiện runbook

Dùng thử nghiệm có phạm vi an toàn:

- Kill một instance khi đang nhận traffic.
- Mark unready và đo thời gian traffic ngừng vào instance.
- Khởi động thêm replica khi đang tải.
- Tạm ngưng registry/control plane hoặc mô phỏng query timeout.
- Làm backend tăng latency/503 để kiểm tra retry storm.
- Chuyển weight canary và quan sát distribution.
- Tạo long-lived HTTP/2/gRPC connection rồi rollout.
- Mô phỏng một zone không còn truy cập.
- Hết hạn hoặc thay chứng chỉ trong tình huống kiểm soát.

Ghi kết quả bằng evidence, cập nhật runbook và chỉ mở rộng khi các trường hợp lỗi quan trọng đã có owner/biện pháp.

## 20. Anti-pattern và cách tránh

| Anti-pattern | Vấn đề | Cách sửa |
| --- | --- | --- |
| Hard-code IP/port của service | Deployment thay đổi làm lỗi client | Dùng logical service name và discovery |
| Client query registry mỗi request | Registry trở thành bottleneck, latency tăng | Cache/watch theo semantics cho phép |
| Chỉ có registry, không có health/readiness | Route đến instance chưa sẵn sàng | Readiness/lease/health và drain |
| Coi DNS update là đổi connection lập tức | Traffic còn vào endpoint cũ | Quản lý resolver, pool và graceful shutdown |
| Mỗi team tự viết SDK discovery riêng | Policy thiếu nhất quán, khó debug | SDK/platform contract chuẩn |
| Đặt proxy một replica rồi gọi là HA | Đơn điểm lỗi mới | Triển khai HA và capacity test |
| Chỉ LB theo số kết nối với gRPC dài | Traffic không đều | Hiểu cấp balancing và kết nối |
| Retry cả ở app, gateway và mesh | Retry amplification, quá tải | Một chính sách end-to-end với retry budget |
| Mặc định retry POST thanh toán | Trùng side effect | Idempotency, deadline và đúng semantics |
| Xóa pod trước khi rút endpoint | Nhiều reset/5xx lúc rollout | Drain readiness và preStop có kiểm soát |
| Liveness kiểm tra mọi dependency | Restart cascade khi downstream lỗi | Phân biệt liveness với readiness |
| Client tin metadata registry không xác thực | Routing/SSRF, lộ dữ liệu | ACL, identity và validate endpoints |
| Dùng load balancer để che mọi lỗi nghiệp vụ | Trả kết quả sai dù request thành công | Tách resilience hạ tầng và business invariant |
| Không đo endpoint đã chọn | Sự cố routing khó điều tra | Telemetry về logical target và selected instance |
| Mọi dịch vụ đi qua public API gateway | Thêm hop, coupling và bottleneck | Chọn internal service discovery đúng phạm vi |
| Canary chỉ cấu hình weight, không đo traffic | Phân phối thực khác kỳ vọng | So sánh backend metrics theo request |
| Tạo registry riêng khi platform đã đủ | Tăng chi phí vận hành và nguồn sự thật trùng | Tận dụng cơ chế được quản lý trước |

## 21. Bài tập tình huống A — dịch vụ giá trong Kubernetes

**Bối cảnh:** ứng dụng Java dùng Kubernetes. Ordering gọi Pricing qua một tên DNS service. Pricing có bốn pod, mỗi pod 8080. Khi triển khai phiên bản mới, đôi khi request lỗi connection reset; thêm pod thứ năm không làm phân phối request đều.

**Câu hỏi:**

1. Mô hình khám phá hiện tại gần client-side hay server-side? Vì sao phải biết thực tế có ClusterIP hay headless service?
2. Làm thế nào để kiểm tra một pod đã sẵn sàng trước khi nhận request?
3. Vì sao một request còn có thể vào pod sắp dừng dù readiness vừa chuyển thành false?
4. Nếu caller giữ HTTP/2 connection dài, điều gì có thể xảy ra với phân phối tải?
5. Những metric nào giúp phân biệt lỗi DNS cache, connection pool, LB và pod readiness?
6. Thiết kế một tiến trình drain/rolling update để giảm 5xx.
7. Nếu Pricing trả timeout, request nào an toàn để retry? Những request có tác dụng phụ cần điều kiện gì?

**Một hướng giải:**

Với Kubernetes Service ClusterIP và các pod tương đương, ứng dụng thường gọi tên service ổn định trong khi hạ tầng chọn backend. Nên quan sát EndpointSlice/readiness, termination grace period, pool behavior và cấp cân tải (connection/request). Nếu dùng headless service, DNS có thể trả danh sách pod IP để client chọn; khi ấy caller phải xử lý nhiều responsibility hơn. Việc rút endpoint thường có độ trễ propagation nên cần draining và retry an toàn.

## 22. Bài tập tình huống B — nhiều ngôn ngữ và đa vùng

**Bối cảnh:** một công ty có 45 service viết bằng Java, Go, Python và Node.js ở hai vùng. Tất cả cần authentication, weighted canary và routing ưu tiên cùng vùng. Hiện mỗi team có một thư viện HTTP riêng; cách timeout/retry không đồng nhất.

**Câu hỏi:**

1. Ưu/nhược điểm nếu yêu cầu mọi nhóm triển khai client-side discovery với registry chung?
2. Nếu đưa routing xuống gateway hoặc service mesh, phần nào được tập trung, phần nào vẫn thuộc application code?
3. Một hop proxy có thực sự là vấn đề hiệu năng lớn không? Cần đo bằng cách nào?
4. Nếu zone chính không có healthy endpoint nhưng vùng dự phòng còn service, failover cần những điều kiện nào?
5. Có những quyền truy cập và nguy cơ rò dữ liệu nào khi client có quyền xem endpoint ở cả hai vùng?
6. Làm sao ngăn retry amplification khi policy tồn tại ở SDK và proxy?
7. Chọn một phương án kiến trúc, nêu các giả định, SLO, rủi ro và điều kiện đổi quyết định.

**Một hướng giải:**

Với đa ngôn ngữ và nhu cầu chính sách thống nhất, proxy/server-side discovery hoặc mesh có thể giảm việc nhân bản logic trong từng SDK. Tuy nhiên, ứng dụng vẫn phải xử lý business-level deadlines, idempotency, API contract và fallback đúng nghiệp vụ. Quyết định multi-region phải xét data residency, capacity, consistency và quyền; không chỉ kiểm tra endpoint còn sống.

## 23. Checklist cho thiết kế service discovery thực tế

**Bài toán và mô hình**

- [ ] Mỗi dependency có logical service name và owner rõ.
- [ ] Đã xác định ai cập nhật registry/endpoint và ai chọn instance.
- [ ] Phân biệt client-side, server-side và proxy-side discovery theo data path thực tế.
- [ ] Đã so sánh yêu cầu SDK, hạ tầng, latency và vận hành.
- [ ] Đã quyết định quy tắc lựa chọn endpoint: weights, zone, version, tenant/shard nếu cần.

**Độ tin cậy**

- [ ] Instance chỉ được route khi ready theo contract.
- [ ] Có lifecycle start, ready, drain, stop/deregister rõ.
- [ ] Đã đo thời gian propagation của endpoint/health updates.
- [ ] Có xử lý danh sách rỗng, registry outage, stale cache, DNS failure.
- [ ] Có timeout, retry budget, circuit breaker và idempotency đúng thao tác.
- [ ] Đã kiểm chứng connection reuse, gRPC/HTTP2 và phân phối traffic thực.

**Bảo mật và quan sát**

- [ ] Xác thực và phân quyền đăng ký/tra cứu endpoints.
- [ ] TLS/mTLS, identity và secret rotation đúng ranh giới.
- [ ] Có metric healthy backend, resolve error, cache age, upstream 5xx, retry.
- [ ] Trace/log đủ thông tin về logical destination, selected backend, attempt.
- [ ] Có runbook cho registry failure, proxy failure, flapping và rollover.

**Vận hành thay đổi**

- [ ] Có canary routing và phương án quay về policy trước.
- [ ] Đã thử scale-out, scale-in, rolling restart và zone failure.
- [ ] Đo SLO end-to-end, không chỉ thấy endpoint lookup thành công.
- [ ] Bản ghi quyết định kiến trúc (ADR) nêu rủi ro, owner và điều kiện xem lại.

## 24. Tổng kết

**Service discovery** tách định danh dịch vụ ổn định khỏi địa chỉ instance thay đổi theo thời gian. Với **client-side discovery**, caller hoặc SDK của nó tìm và chọn backend. Với **server-side discovery**, caller gửi tới một địa chỉ ổn định để proxy/LB/hạ tầng tìm và chọn instance. Trong DNS, Kubernetes hoặc service mesh, cần nhìn vào vị trí thực hiện endpoint selection để mô tả đúng mô hình thay vì chỉ dựa vào tên công nghệ.

Lựa chọn tốt nhất không phải phương án có ít thành phần nhất trên sơ đồ mà là phương án giúp hệ thống **đổi instance an toàn, phân tải đúng, chịu lỗi có kiểm soát, dễ bảo mật và dễ quan sát** trong điều kiện vận hành thực tế. Registry, readiness, graceful draining, connection pooling, deadlines, retries và identity cùng tạo ra một đường gọi đáng tin cậy; bỏ sót một phần có thể khiến discovery “đúng” nhưng trải nghiệm người dùng vẫn thất bại.
