# Phân biệt API Gateway với ingress, load balancer và service mesh

## 1. Mục tiêu và bối cảnh

Một ứng dụng microservices có thể dùng cả API Gateway, Kubernetes Ingress, load balancer và service mesh. Các thành phần này thường cùng có khả năng chuyển tiếp HTTP, kiểm tra trạng thái backend, cân bằng tải hoặc áp một số chính sách bảo mật. Điều đó dễ dẫn đến câu hỏi: **chúng khác nhau ở trách nhiệm nào, có thay thế nhau được không và khi nào nên dùng kết hợp?**

Đây là câu hỏi về **ranh giới trách nhiệm mạng và vận hành**, không chỉ là chọn sản phẩm. Một kiến trúc có thể dùng một thành phần đảm nhận nhiều vai trò; một kiến trúc khác phân tách các vai trò vì cần bảo mật, quy mô hoặc ownership khác nhau. Không có quy tắc “mọi hệ thống microservices phải đủ bốn thành phần”.

Mục tiêu bài học:

- Hiểu rõ vai trò chính và phạm vi trách nhiệm của từng thành phần.
- Phân biệt lưu lượng **north–south** (client vào/ra hệ thống) và **east–west** (giao tiếp giữa các dịch vụ).
- Hiểu API Gateway thiên về quản lý hợp đồng và trải nghiệm API; ingress thiên về điểm vào workload; load balancer thiên về phân phối lưu lượng; service mesh thiên về quản lý giao tiếp service-to-service.
- Nhận diện các khả năng chồng lấn: TLS, routing, health check, authentication, rate limiting, retry, observability.
- Thiết kế đường đi request không tạo quá nhiều hop và tránh cấu hình chính sách mâu thuẫn.
- Chọn mô hình phù hợp cho ứng dụng nhỏ, hệ thống API công khai và môi trường microservices đa cụm.

Ví dụ xuyên suốt là hệ thống bán hàng có dịch vụ **Checkout**, **Catalog**, **Inventory**, **Payment** và **Notification**. Tên miền, địa chỉ, ngưỡng và cấu hình minh họa cần thay bằng giá trị thật khi triển khai.

## 2. So sánh nhanh bốn vai trò

| Thành phần | Câu hỏi chính | Trách nhiệm điển hình | Phạm vi thường gặp |
|---|---|---|---|
| **Load balancer (LB)** | Trong nhiều backend có thể phục vụ, gửi lưu lượng tới đâu? | Phân phối kết nối/request, health check, failover, đôi khi TLS termination | Lớp mạng L4 hoặc lớp ứng dụng L7; biên và nội bộ |
| **Ingress** | Lưu lượng từ bên ngoài đi vào các ứng dụng trong cụm như thế nào? | Entry point cho HTTP(S), route theo host/path, TLS, công bố Service | Chủ yếu north–south vào Kubernetes |
| **API Gateway** | Người tiêu thụ API được truy cập năng lực nào với hợp đồng và chính sách gì? | API routing, authentication/authorization integration, quota, throttling, versioning, request transformation, aggregation | API-facing edge; có thể public, partner, internal |
| **Service mesh** | Các workload giao tiếp với nhau an toàn và ổn định ra sao? | mTLS, service identity, traffic policy, telemetry, retries/timeouts khi phù hợp | Chủ yếu east–west giữa workload; có thể hỗ trợ ingress/egress |

**Không nên coi bảng là danh sách tính năng độc quyền.** Một API Gateway cũng có thể cân bằng tải; ingress controller thường chính là L7 reverse proxy/LB; service mesh có gateway cho lưu lượng từ bên ngoài. Ranh giới phân biệt tốt nhất là **mục tiêu, người sở hữu chính sách và mức độ giao diện được quản lý**.

Ví dụ:

- Khi chỉ cần chia 10.000 request giữa bốn instance khỏe, trọng tâm là **load balancing**.
- Khi cần định tuyến api.example.com/orders vào Kubernetes Service orders-api, trọng tâm là **ingress**.
- Khi cần xác thực ứng dụng đối tác, áp quota theo API key, giữ hợp đồng v1/v2 và tổng hợp dữ liệu, trọng tâm là **API Gateway**.
- Khi Checkout gọi Inventory, cần workload identity, mTLS, telemetry và chính sách timeout thống nhất, trọng tâm là **service mesh**.

## 3. North–south và east–west: nhìn từ đường đi request

### 3.1. North–south traffic

Là lưu lượng đi qua ranh giới hệ thống giữa client/bên ngoài và dịch vụ đang chạy bên trong, thường qua DNS, CDN, WAF, LB, gateway hoặc ingress.

~~~text
Browser / Mobile / Partner
           |
         DNS/CDN
           |
      External LB
           |
   Edge/API Gateway
           |
   Kubernetes ingress
           |
       Checkout
~~~

Đường đi trên là **một khả năng**, không phải bắt buộc. Trong kiến trúc thực tế, edge gateway có thể trực tiếp đóng vai trò ingress hoặc ingress controller có thể đủ chức năng gateway, vì vậy không cần xếp thêm mọi lớp.

### 3.2. East–west traffic

Là giao tiếp giữa các workload bên trong hệ thống:

~~~text
Checkout  ---> Inventory
    |
    +----> Pricing
    |
    +----> Payment
~~~

Các lời gọi này có thể dùng service discovery, Kubernetes Service, DNS, direct RPC, mesh proxy hoặc ambient data plane. Service mesh tập trung áp chính sách nhất quán lên giao tiếp giữa workload. Không phải mọi giao tiếp east–west đều đi qua một gateway trung tâm; làm vậy có thể tạo nút nghẽn và single point of failure.

### 3.3. Ranh giới chồng lấn

Một **mesh ingress gateway** vẫn là điểm vào cho traffic north–south. Một **API Gateway** có thể được triển khai ngay trong Kubernetes và được public qua LoadBalancer Service. Một **Ingress controller** có thể cung cấp OAuth integration hoặc rate limiting nếu controller hỗ trợ.

Vì vậy, cần hỏi trước:

1. Ai chịu trách nhiệm bảo vệ **API contract và consumer**?
2. Ai chịu trách nhiệm đưa traffic vào **cụm ứng dụng**?
3. Ai chịu trách nhiệm phân phối lưu lượng giữa **instance**?
4. Ai chịu trách nhiệm chính sách nhất quán cho **service-to-service**?
5. Vai trò nào đã có một thành phần đảm nhiệm tốt, vai trò nào còn thiếu?

## 4. Load balancer: phân phối lưu lượng

**Load balancer** nhận traffic và chọn một backend trong một tập backend có thể phục vụ. Mục tiêu thường là tăng khả năng phân phối tải, sẵn sàng và sử dụng tài nguyên hợp lý.

### 4.1. Layer 4 và Layer 7

| Loại | Thông tin dùng để chọn backend | Khả năng điển hình | Giới hạn cần lưu ý |
|---|---|---|---|
| **L4 (TCP/UDP)** | Địa chỉ IP, cổng, kết nối, thuộc tính vận tải | Chuyển tiếp kết nối, phân phối luồng TCP/UDP, hiệu năng cao | Không mặc nhiên hiểu URL, HTTP header hoặc JSON |
| **L7 (HTTP/gRPC)** | Host, path, method, header, cookie và trạng thái HTTP | Route theo API, sticky, TLS termination, kiểm tra/điều khiển HTTP | Thêm xử lý ứng dụng và yêu cầu hiểu protocol |

L4 hay L7 phụ thuộc mục tiêu. Một L7 LB có thể xử lý một số khả năng tương tự ingress hoặc API gateway nhưng không vì thế tự quản lý đầy đủ hợp đồng API, developer portal, subscription hay tenant policy.

### 4.2. Thuật toán thường gặp

- **Round-robin:** phân phối luân phiên; phù hợp khi backend có khả năng tương đương.
- **Least connections / least outstanding requests:** ưu tiên backend đang phục vụ ít kết nối/yêu cầu hơn, tùy thuật toán.
- **Weighted balancing:** gán tỷ trọng theo capacity hoặc rollout canary.
- **Consistent hashing:** giữ khóa như session/tenant tương đối ổn định theo backend; cần hiểu hậu quả khi topology đổi.
- **Latency/health-aware:** xem mức khỏe, delay hoặc tải nếu nền tảng hỗ trợ.

Không có thuật toán luôn tốt nhất. Weighted round-robin không tự bảo đảm 5% **người dùng** đi canary: nó có thể là 5% **request**. Nếu cần cohort người dùng cố định, phải có cơ chế sticky/assignment thích hợp.

### 4.3. Health check và failover

Load balancer chỉ nên gửi request tới backend đủ điều kiện phục vụ. Health cần phân biệt:

- **Liveness:** tiến trình còn hoạt động không?
- **Readiness:** instance đã sẵn sàng nhận traffic chưa?
- **Dependency health:** có đủ kết nối hoặc quyền truy cập nguồn dữ liệu cốt lõi để xử lý operation không?

Một instance có thể trả health check thành công nhưng không xử lý được nghiệp vụ do database cạn connection. Ngược lại, health check quá sâu gây thác lỗi khi một dependency phụ tạm ngừng. Quyết định kiểm tra gì phải phù hợp thiết kế resilience.

### 4.4. Load balancer không thay thế những gì?

Một LB đơn giản không mặc định thực hiện:

- API subscription/quota theo sản phẩm.
- Quản lý vòng đời hợp đồng API cho đối tác.
- Phân quyền theo tenant và nghiệp vụ.
- Các chính sách service-to-service mTLS với identity riêng.
- Xử lý idempotency khi gọi Payment.
- Bảo đảm toàn bộ workflow thống nhất dữ liệu.

Một sản phẩm LB có thể bổ sung các tính năng này. Khi đó, cần đánh giá **mức đáp ứng yêu cầu**, không phân loại chỉ dựa trên nhãn marketing.

## 5. Ingress: điểm vào cụm ứng dụng

Trong Kubernetes, **Ingress** là một tài nguyên API mô tả cách HTTP(S) từ ngoài cụm được định tuyến đến Kubernetes Service. **Ingress controller** là thành phần thực tế đọc tài nguyên Ingress và cấu hình data plane/proxy để phục vụ traffic.

### 5.1. Tài nguyên Ingress không tự xử lý request

~~~text
Kubernetes Ingress resource
  host: api.example.com
  /orders -> orders-service
  /catalog -> catalog-service
             |
             v
Ingress controller
  (ví dụ controller dựa trên NGINX, HAProxy, Envoy, ...)
             |
             v
Reverse proxy / data plane đang chạy
             |
             v
Kubernetes Service -> Pods
~~~

**Chỉ khai báo Ingress YAML không đủ để traffic hoạt động** nếu không có Ingress controller phù hợp, thiết lập địa chỉ public, DNS/TLS và các đối tượng Service/Pod tương ứng.

### 5.2. Ví dụ Kubernetes Ingress

~~~yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: commerce-ingress
  namespace: commerce
spec:
  ingressClassName: example-controller
  tls:
    - hosts:
        - api.example.com
      secretName: api-example-tls
  rules:
    - host: api.example.com
      http:
        paths:
          - path: /orders
            pathType: Prefix
            backend:
              service:
                name: orders-api
                port:
                  number: 8080
          - path: /catalog
            pathType: Prefix
            backend:
              service:
                name: catalog-api
                port:
                  number: 8080
~~~

Đây là **mẫu cấu hình**. Giá trị ingressClassName phải trùng với controller có thật; các Service, TLS Secret, DNS và phần networking cần được cấu hình phù hợp. Cách xử lý một số annotation và extension phụ thuộc ingress controller, không nên mặc định tính năng của controller A xuất hiện trên controller B.

Ingress chuẩn tập trung vào route theo host/path và TLS. Nó không tự cung cấp mọi khả năng enterprise API management. Nếu yêu cầu OAuth2, quota theo ứng dụng đối tác, transformation hoặc developer portal, cần xác định controller có tích hợp phù hợp hay có một API Gateway riêng.

### 5.3. Ingress và Kubernetes Service kiểu LoadBalancer

Hai thứ không đồng nghĩa:

- **Service type LoadBalancer:** thường yêu cầu hạ tầng cung cấp một endpoint/load balancer để công bố **một Service**, với chi tiết phụ thuộc cloud/controller. Nó không nhất thiết quản lý nhiều rule HTTP theo hostname/path.
- **Ingress:** mô tả route HTTP(S) tới **nhiều Service**, thường đi qua ingress controller được công bố bởi một endpoint hoặc Service type LoadBalancer.
- **ClusterIP Service:** là điểm truy cập nội bộ ổn định tới tập Pod, hỗ trợ cơ chế cân bằng/phân phối lưu lượng ở tầng Kubernetes/networking.

Một ứng dụng đơn giản công bố TCP service có thể chỉ cần LoadBalancer Service, không cần Ingress. Một cụm có 20 web service lại có thể dùng một ingress controller cho nhiều host/path.

## 6. Kubernetes Gateway API và khái niệm “gateway”

Tên **Gateway** trong Kubernetes Gateway API dễ bị nhầm với khái niệm **API Gateway** ở tầng sản phẩm. Hai khái niệm có thể gặp nhau nhưng không hoàn toàn đồng nghĩa.

Kubernetes **Gateway API** cung cấp các tài nguyên như GatewayClass, Gateway và HTTPRoute, cho phép tổ chức cấu hình traffic, listener và routing với cách phân tách trách nhiệm rõ hơn trong nhiều tình huống so với Ingress truyền thống.

Một HTTPRoute minh họa:

~~~yaml
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: orders-route
  namespace: commerce
spec:
  parentRefs:
    - name: public-gateway
      namespace: platform
  hostnames:
    - api.example.com
  rules:
    - matches:
        - path:
            type: PathPrefix
            value: /v1/orders
      backendRefs:
        - name: orders-api
          port: 8080
~~~

Để ví dụ vận hành cần có Gateway/GatewayClass, controller hỗ trợ, listener, quyền attach route từ namespace commerce, Service backend và các chính sách liên quan. Đừng coi HTTPRoute này tự tạo đầy đủ hạ tầng.

**Điểm phân biệt:**

- **Gateway API:** tập resource/API của Kubernetes để mô tả networking/traffic.
- **API Gateway:** vai trò hoặc sản phẩm quản lý consumer/API contract, thường gồm authentication, quota, versioning, policy và analytics.
- Một controller triển khai Gateway API có thể cũng cung cấp khả năng API Gateway nâng cao.
- Dùng Gateway API không tự có developer portal, subscription, tenant authorization hay API product lifecycle.

## 7. API Gateway: cổng chính sách và hợp đồng API

**API Gateway** thường đứng ở ranh giới giữa consumer và các năng lực backend. Nó tạo mặt tiền API có thể kiểm soát, che bớt topology nội bộ và nhất quán hóa các chính sách dùng chung.

### 7.1. Những trách nhiệm phổ biến

1. **Tiếp nhận API:** hostname, TLS termination, route theo operation/path/version hoặc client.
2. **Xác thực:** tích hợp OIDC/OAuth2, API key, mTLS cho client phù hợp.
3. **Chính sách truy cập:** kiểm tra scope/claims ở biên và gọi dịch vụ authorization nếu cần.
4. **Rate limiting, quota và throttling:** theo client, application, tenant, route hoặc API product.
5. **Request/response transformation:** đổi format, header, version adapter hoặc chuẩn hóa error khi cần.
6. **API versioning và lifecycle:** giữ v1/v2 song song, deprecation policy và bảo vệ consumer cũ.
7. **API aggregation/BFF:** tổng hợp kết quả nhiều service để tối ưu trải nghiệm client, có giới hạn về complexity.
8. **Observability ở ranh giới:** request volume, latency, status, consumer/API analytics, trace propagation.
9. **Policy ở biên:** giới hạn payload, CORS, WAF integration, IP restrictions hoặc schema validation tùy nền tảng.
10. **API discovery/documentation:** một số sản phẩm hỗ trợ catalog, developer portal, API keys và onboarding đối tác.

Không phải API Gateway nào cũng có mọi tính năng; kiểm tra sản phẩm/cấu hình hiện dùng. Ngược lại, chức năng có mặt trong Gateway không có nghĩa phải bật tất cả.

### 7.2. Ví dụ vai trò của gateway

~~~text
Mobile App                 Partner Client
     |                            |
     +------------+---------------+
                  |
            API Gateway
                  |
        AuthN, quota, API version
                  |
       +----------+----------+
       |          |          |
    Catalog     Checkout   Customer
       |          |          |
     Dữ liệu và nghiệp vụ thuộc từng service
~~~

Ví dụ:

- Mobile dùng token OIDC để gọi GET /v1/products.
- Partner có quota 100 request/giây cho API nhất định.
- Client cũ tiếp tục gọi /v1/orders trong thời kỳ chuyển đổi.
- Gateway chọn backend pool tương thích contract và ghi nhận analytics.

Nhưng **Gateway không nên là nơi duy nhất kiểm tra quyền nghiệp vụ**. Backend Checkout vẫn phải xác minh caller/tenant có được xem đơn hàng hay thực hiện thanh toán không. Một lỗi cấu hình route hoặc đường gọi nội bộ không được biến thành cách truy cập dữ liệu trái phép.

### 7.3. Gateway có thể làm BFF, nhưng không nên chứa domain logic

**Backend for Frontend (BFF)** là lớp API được tổ chức theo nhu cầu một loại client (mobile/web), ví dụ gom giỏ hàng, khuyến mại và tồn kho thành một response.

~~~text
Mobile client
    |
Mobile BFF / API layer
    |
    +--> Cart
    +--> Pricing
    +--> Inventory
~~~

BFF có thể nằm sau API Gateway hoặc được triển khai như một service riêng. Không nên biến cấu hình Gateway thành nơi xử lý giao dịch, quyết định số dư, tính thuế phức tạp hoặc sở hữu trạng thái nghiệp vụ. Các quy tắc và bất biến đó thuộc service/domain sở hữu.

Nếu một endpoint Gateway gọi nhiều backend tuần tự, hãy quan sát **latency end-to-end, deadline propagation, partial failure và timeout**. Aggregation tiện cho client nhưng có thể tăng coupling và làm gateway thành nút nghẽn.

### 7.4. Khi nào API Gateway là không cần thiết?

Nếu chỉ có một web app nội bộ, ít route, không có nhiều loại API consumer và các chính sách ở biên đã được ingress controller đáp ứng, thêm một API Gateway riêng có thể chỉ tạo thêm hop, latency, chi phí và một nguồn cấu hình khác. Quyết định cần dựa trên nhu cầu API management, không phải vì “microservices phải có gateway”.

## 8. Service mesh: kiểm soát giao tiếp service-to-service

**Service mesh** quản lý kết nối giữa workload theo chính sách dùng chung, thường tách **data plane** (proxy hoặc cơ chế xử lý traffic) và **control plane** (phân phối cấu hình, identity, policy, topology).

Một triển khai mesh có thể dùng **sidecar proxy** cạnh từng Pod, hoặc thiết kế không cần sidecar truyền thống, ví dụ data plane dùng node-level proxy/ambient pattern tùy sản phẩm. Vì vậy không nên đồng nhất service mesh với “mỗi Pod bắt buộc có một Envoy sidecar”.

### 8.1. Chức năng điển hình

- **Workload identity và mTLS:** xác thực danh tính workload và mã hóa kết nối giữa các service.
- **Traffic policies:** route theo subset/release, timeout, retry, outlier detection, circuit breaking hoặc load balancing khi hỗ trợ.
- **Observability:** telemetry HTTP/gRPC, metric, tracing integration và service topology.
- **Authorization policies:** cho phép/không cho workload A gọi workload B theo identity và thuộc tính hợp lệ.
- **Canary east–west:** điều khiển traffic giữa các phiên bản của backend.
- **Egress controls:** chính sách lưu lượng ra khỏi hệ thống đến dependency bên ngoài, tùy triển khai.

Dù mesh làm cho nhiều chính sách nhất quán hơn, nó **không thay thế domain authorization**. mTLS chứng minh “caller là workload Checkout” không mặc nhiên cho phép “Checkout truy cập order của tenant khác”. Quyền business-level vẫn phải được kiểm tra trong service có thẩm quyền.

### 8.2. Ví dụ luồng traffic qua mesh

~~~text
Checkout application
        |
   Local data plane
        |
    mTLS + policy
        |
   Remote data plane
        |
Inventory application
~~~

Mesh có thể biết destination và workload identity mà không yêu cầu ứng dụng tự triển khai mTLS cho từng cặp service. Tuy nhiên ứng dụng vẫn phải xử lý **idempotency, transaction, business errors, trạng thái UNKNOWN sau timeout và quyền nghiệp vụ**.

### 8.3. Control plane và data plane

- **Control plane:** mô tả chính sách, phát hành cấu hình, phân phối certificate/identity hoặc tương tác với hạ tầng identity tùy mesh.
- **Data plane:** thực thi kết nối, routing, mTLS, một số retry/timeout và phát telemetry.

Control plane không nhất thiết nằm trên đường đi trực tiếp của mỗi request. Trong nhiều kiến trúc, data plane có thể tiếp tục dùng cấu hình gần nhất khi control plane tạm không khả dụng. Nhưng mức tiếp tục hoạt động, khả năng cấp mới certificate hoặc cập nhật endpoint phải được kiểm chứng với sản phẩm và failure mode thật.

### 8.4. Mesh và ingress có thể gặp nhau

Một số mesh có **ingress gateway** nhận traffic từ bên ngoài, và/hoặc **egress gateway** điều khiển traffic ra ngoài. Một ingress gateway thuộc mesh có thể chấm dứt TLS bên ngoài, bắt đầu kết nối mTLS nội bộ hoặc gắn identity thông qua chính sách. Điều này không biến mọi cấu hình mesh thành một **API management portal** đầy đủ.

Nếu đã dùng mesh ingress gateway có đủ chức năng rate limiting/authentication/route cho yêu cầu API, một API Gateway khác có thể là dư thừa. Ngược lại, API cho hàng nghìn đối tác có thể cần API Gateway chuyên dụng phía trước mesh để quản lý vòng đời API và consumer.

## 9. Trách nhiệm bảo mật: cái nào kiểm tra điều gì?

Bảo mật thường thất bại khi nhiều tầng tồn tại nhưng mọi tầng đều nghĩ tầng khác đã kiểm tra.

| Yêu cầu | Nơi thường phù hợp | Điều không nên giả định |
|---|---|---|
| TLS từ client đến edge | CDN/LB/Ingress/API Gateway tùy topology | TLS bên ngoài không tự mã hóa mọi hop nội bộ |
| OAuth/OIDC token verification | API Gateway và/hoặc backend | Kiểm tra chữ ký token chưa đủ để cấp quyền đọc mọi dữ liệu |
| API key/quota theo ứng dụng | API Gateway | API key tự chứng minh danh tính end-user |
| Service-to-service mTLS | Service mesh hoặc ứng dụng/hạ tầng tương đương | mTLS tự bảo vệ business authorization |
| Tenant/order ownership | Backend service sở hữu dữ liệu | Chỉ cần có route hợp lệ là được phép truy cập |
| WAF/bot filtering | Edge/CDN/WAF integration | WAF thay thế validation và business rules |
| CORS | Edge/Gateway/backend theo hợp đồng web | CORS là cơ chế authorization của server |
| Rate limiting | Gateway, mesh, backend tùy cấp bảo vệ | Một lớp rate limit bảo vệ được mọi điểm nghẽn |

### 9.1. Chuỗi tin cậy ở edge

Nếu hệ thống dùng header như X-User-Id, X-Tenant-Id hoặc X-Authenticated-Principal để truyền context nội bộ:

1. Edge phải **xóa hoặc từ chối các header giả mạo** từ client.
2. Context nội bộ phải được tạo từ token hoặc danh tính đã xác thực.
3. Đường giao tiếp tới backend phải có mức tin cậy phù hợp: mTLS, network policy, signed context hoặc token propagation.
4. Backend vẫn phải kiểm tra quyền nghiệp vụ và tenant isolation.
5. Nếu có nhiều gateway/ingress, xác định lớp nào là **nguồn duy nhất** phát hành thông tin định danh đáng tin.

Không tin X-Forwarded-For, X-Forwarded-Proto hoặc các header client tự gửi nếu không xác định rõ **trusted proxy chain**. Chúng có thể quan trọng cho audit, URL generation, HTTPS redirect và rate limiting theo IP.

### 9.2. TLS termination và mã hóa nội bộ

Một topology có thể:

~~~text
Client --TLS--> Edge Gateway --TLS/mTLS--> Service
~~~

Hoặc:

~~~text
Client --TLS--> LB/Ingress --HTTP nội bộ--> Pod
~~~

Cấu hình thứ hai có thể phù hợp trong một số môi trường đã đánh giá rủi ro, nhưng **không có mã hóa end-to-end đến Pod**. Cần nêu rõ mỗi đoạn kết nối có bảo mật thế nào, ai sở hữu certificate, cách rotation và chính sách network segmentation.

Dùng nhiều proxy làm tăng số nơi có thể kết thúc TLS, ghi log nội dung nhạy cảm hoặc làm mất thông tin client identity. Hãy ghi lại data flow thực tế thay vì mô tả chung “đã bật HTTPS”.

## 10. Routing version, vùng và canary thuộc lớp nào?

Khả năng định tuyến có thể được phân phối theo trách nhiệm:

- **API version routing:** thường gắn với hợp đồng client và API Gateway/edge router.
- **Region routing:** thường kết hợp DNS/global LB, gateway và **data residency policy** của hệ thống.
- **Canary theo release:** có thể ở ingress controller, API Gateway hoặc mesh, miễn là các release tương thích hợp đồng.
- **Stable cohort theo tenant/user:** cần nguồn identity tin cậy và assignment ổn định; weighted request routing không tự bảo đảm ổn định nhóm người dùng.
- **Instance load balancing:** thường do LB, Kubernetes Service, ingress hoặc mesh data plane thực hiện trong backend pool đã chọn.

Một yêu cầu có thể được xử lý theo thứ tự:

~~~text
Authenticated request
       |
API contract version
       |
Allowed region / data residency
       |
Stable cohort / release eligibility
       |
Healthy backend pool
       |
Load balancing among instances
~~~

Nếu đã có một control plane quyết định backend pool, không nên để tầng dưới tự chọn một region khác chỉ vì latency hoặc health mà vi phạm quyền dữ liệu. Phải công bố **quy tắc ưu tiên, fallback và fail-closed**.

## 11. Retry, timeout và circuit breaker: tránh xung đột chính sách

API Gateway, ingress controller, mesh và HTTP client đều có thể hỗ trợ retry hoặc timeout. Nếu bật retry tại mọi tầng, số attempt có thể nhân lên không kiểm soát.

Ví dụ:

~~~text
Gateway: retry tối đa 3 attempt
Mesh:    retry tối đa 3 attempt
Client:  retry tối đa 3 attempt

Trong tình huống bất lợi, một thao tác logic có thể
khuếch đại thành nhiều lần gọi xuống dependency.
~~~

Điều này đặc biệt nguy hiểm với POST tạo Order, giữ tồn kho, thu tiền hoặc gửi email. **Timeout không chứng minh side effect chưa xảy ra.** Phải có idempotency key, trạng thái tra cứu và reconciliation khi kết quả không rõ.

Chính sách tốt:

1. Xác định **tầng sở hữu retry** cho từng loại operation.
2. Phân biệt read-only/idempotent operation với write có tác dụng phụ.
3. Truyền **deadline end-to-end** và tính ngân sách còn lại qua mỗi hop.
4. Chỉ retry lỗi có khả năng phục hồi; không retry mù lỗi validation hoặc business conflict.
5. Giới hạn số attempt, exponential backoff, jitter và tổng tải.
6. Ghi rõ proxy nào có quyền retry và proxy nào chỉ timeout/fail fast.
7. Kiểm tra các status code, method, streaming body và connection reset mà proxy thực tế sẽ retry.
8. Với circuit breaker, thiết kế fallback không phá bất biến nghiệp vụ.

**Trùng chức năng không phải luôn sai**: một gateway có thể chống request quá tải ở biên, mesh bảo vệ downstream bằng circuit breaking, service áp business admission control. Điều quan trọng là các chính sách **bổ sung nhau**, không khuếch đại lỗi hay đưa ra hai quyết định mâu thuẫn.

## 12. Ví dụ kiến trúc một cửa hàng online

Giả sử Shop có:

- **Public API** phục vụ web/mobile và đối tác.
- **Catalog** có lưu lượng đọc lớn.
- **Checkout** xử lý đơn hàng.
- **Inventory**, **Payment** là các dịch vụ nội bộ.
- Nhiều Pod của mỗi service chạy trên Kubernetes.

Một thiết kế có thể là:

~~~text
                     Public Internet
                           |
                       DNS / CDN
                           |
                   External Load Balancer
                           |
                API Gateway / Edge Proxy
             (authn, quota, API versioning)
                           |
                Kubernetes workload entry
              (Ingress nếu cần lớp riêng)
                           |
                    Checkout Pods
                           |
                Service-to-service mesh
                    /            \
              Inventory        Payment
                 Pods            Pods
~~~

Đây không phải lời khuyên luôn triển khai đủ tầng. Nếu API Gateway được chạy ngay trong Kubernetes, public endpoint có thể trỏ thẳng vào Gateway Pod thông qua Service type LoadBalancer hoặc Gateway API controller; **một Ingress nữa có thể không cần**. Cũng có thể dùng ingress controller hỗ trợ đủ nhu cầu API mà không thêm sản phẩm gateway riêng.

### 12.1. Request GET /v1/products

1. Client giải quyết DNS và kết nối tới địa chỉ public.
2. LB/edge chọn điểm nhận traffic khỏe.
3. API Gateway xác thực nếu cần, kiểm quota, định tuyến version v1.
4. Ingress hoặc gateway đưa request tới Catalog Service.
5. Cơ chế LB nội bộ chọn Catalog Pod khỏe.
6. Catalog trả response; layer edge ghi metric và bảo vệ cache theo contract.

Request này thường không cần gọi qua tất cả domain service. Nếu nội dung public có thể cache ở CDN, cần cache key/TTL và chính sách invalidation đúng.

### 12.2. Request POST /v1/orders

1. Gateway xác thực consumer, kiểm payload limit/quota và truyền trace/deadline.
2. Checkout kiểm tra quyền tạo order, idempotency key và bất biến nghiệp vụ.
3. Checkout gọi Inventory/Payment thông qua cơ chế service discovery và traffic policy.
4. Mesh có thể thực hiện mTLS, telemetry và timeout phù hợp ở giao tiếp east–west.
5. Checkout sở hữu trạng thái workflow và xử lý kết quả PENDING/UNKNOWN khi downstream timeout.
6. Gateway chuyển kết quả theo hợp đồng, không tự quyết định một payment đã được commit hay chưa.

**Ranh giới rõ:** Gateway bảo vệ lối vào API, mesh bảo vệ giao tiếp workload, còn Checkout/Payment bảo vệ quyết định nghiệp vụ và dữ liệu.

## 13. So sánh các phương án kiến trúc

| Bối cảnh | Phương án bắt đầu hợp lý | Điều cần theo dõi |
|---|---|---|
| Một web app nội bộ, vài endpoint | LB/Ingress hoặc một reverse proxy đủ chức năng | TLS, routing, health check, authentication tại nơi phù hợp |
| Nhiều service nhưng cùng một đội, ít consumer | Ingress/controller + backend services | Có thật sự cần API management và mesh không? |
| API công khai cho mobile/partner | API Gateway + cơ chế public endpoint | OAuth/API key, quota, versioning, analytics, abuse protection |
| Nhiều đội và nhiều service east–west | Mesh **nếu** lợi ích mTLS/policy/telemetry vượt chi phí | Control plane, certificate, proxy overhead, troubleshooting |
| Multi-region có yêu cầu residency | Global LB + policy định tuyến theo tenant/data + entry point từng vùng | Quyền dữ liệu, replication, failover, split-brain |
| Hệ thống cần canary nhiều bản triển khai | Gateway/Ingress/Mesh tùy nơi sở hữu policy | Version compatibility, sticky cohort, rollback dữ liệu |
| Xử lý TCP không phải HTTP | L4 LB hoặc gateway hỗ trợ giao thức đó | Ingress HTTP có thể không phù hợp |

**Nguyên tắc tối giản:** bắt đầu từ yêu cầu và topology thực tế. Thêm thành phần khi nó giải quyết vấn đề đã xác định và nhóm đủ năng lực vận hành. Mỗi proxy mới có thể tăng latency, điểm lỗi, cấu hình, chi phí, certificate và hành trình debug.

## 14. Bảng so sánh trách nhiệm chi tiết

| Khả năng | Load balancer | Ingress/controller | API Gateway | Service mesh |
|---|---|---|---|---|
| Phân phối giữa instance | Cốt lõi | Thường có | Thường có | Thường có |
| Route HTTP theo host/path | L7 LB có thể có | Cốt lõi | Cốt lõi | Có tùy data plane |
| Public API product, subscription | Không phải vai trò cốt lõi | Không phải mặc định | Thường là trọng tâm khi có API management | Không phải trọng tâm |
| API key/quota theo consumer | Tùy sản phẩm | Tùy controller | Thường hỗ trợ | Có thể cần tích hợp |
| AuthN/AuthZ tại edge | Tùy sản phẩm | Tùy controller | Trọng tâm phổ biến | Ingress gateway/policy có thể hỗ trợ |
| Workload identity/mTLS east–west | Không phải trọng tâm | Không phải trọng tâm | Không phải trọng tâm | Trọng tâm phổ biến |
| Canary / weighted traffic | Nhiều L7 LB hỗ trợ | Tùy controller | Tùy gateway | Tùy mesh |
| Service-to-service retries/timeout | Tùy L7 | Tùy controller | Có ở edge | Thường hỗ trợ theo policy |
| API aggregation/BFF | Không phải vai trò cốt lõi | Không phải mặc định | Có thể có | Không phải trọng tâm |
| Traffic telemetry/tracing | Có ở mức nhất định | Có ở mức nhất định | Ở biên API | Giữa các workload |
| Data residency/business authorization | Cần policy bổ sung | Cần policy bổ sung | Có thể tích hợp | Cần service/domain ownership |

Bảng mô tả **vai trò thường gặp**, không phải danh sách tính năng tuyệt đối. Việc chọn giữa các sản phẩm cần kiểm tra khả năng thực tế, mức hỗ trợ giao thức, giới hạn license, cách vận hành và yêu cầu bảo mật.

## 15. Các lỗi kiến trúc thường gặp

### 15.1. “Cứ có Kubernetes Ingress là có API Gateway đầy đủ”

Ingress route theo host/path, nhưng một API sản phẩm có thể cần lifecycle, token policy, quota, consumer analytics và versioning. Những chức năng này có thể nằm trong controller nâng cao hoặc một gateway riêng, không tự xuất hiện khi khai báo Ingress.

### 15.2. “API Gateway thay thế luôn service mesh”

Gateway bảo vệ ranh giới API không tự tạo mTLS/identity giữa Checkout và Payment trong các đường gọi nội bộ không đi qua gateway. Cần đánh giá yêu cầu service-to-service security và traffic policy riêng.

### 15.3. “Service mesh là một load balancer nên không cần LB”

Mesh có thể làm balancing nội bộ, nhưng hệ thống vẫn cần cơ chế công bố endpoint public và phân phối traffic vào data plane. Không nhầm nhu cầu north–south và east–west.

### 15.4. “Mỗi service phải có API Gateway riêng”

Một gateway public trung tâm cho mọi thứ có thể thành nút nghẽn, nhưng một gateway cho từng service cũng không mặc nhiên tốt. Tùy đội/miền, có thể chọn shared edge, domain gateway hoặc BFF. Service-to-service thông thường không nên vòng qua central public API Gateway nếu không có lý do.

### 15.5. “Càng nhiều proxy càng an toàn”

Bốn proxy liên tiếp có thể tăng surface tấn công, điểm lưu credential, nơi cấu hình TLS, complexity logging và độ trễ. Bảo mật phụ thuộc vào **chính sách đúng, trust boundary rõ và kiểm thử**, không chỉ số lớp.

### 15.6. “Đã xác thực ở Gateway thì backend khỏi kiểm quyền”

Sai với multi-tenant, order ownership hoặc thao tác tài chính. Gateway có thể kiểm token/scope nhưng backend phải xác minh quyền nghiệp vụ trên đối tượng cụ thể.

### 15.7. “Bật retry ở tất cả các tầng sẽ tăng độ tin cậy”

Retry chồng nhau có thể làm tăng tải và lặp tác dụng phụ. Phải có retry owner, deadline và idempotency.

### 15.8. “Service mesh luôn bắt buộc khi có microservices”

Đối với một hệ thống nhỏ, có thể dùng mTLS ở ứng dụng/proxy, service discovery và observability hiện có. Mesh hữu ích khi cần policy nhất quán ở quy mô phù hợp, nhưng mang chi phí triển khai và debug riêng.

### 15.9. “Load balancer bảo đảm mọi request luôn thành công”

LB giúp tránh backend lỗi và phân phối tải, không sửa lỗi nghiệp vụ, dữ liệu sai, database outage, code bug hay dịch vụ phụ thuộc mất kết nối.

### 15.10. “Gateway API của Kubernetes chính là sản phẩm API Gateway”

Gateway API là resource model và routing API của Kubernetes. Nó có thể được một API Gateway product triển khai, nhưng không tự mang mọi khả năng API management.

## 16. Các góc nhìn vận hành phải có

### 16.1. Quan sát toàn chuỗi

Đo ít nhất:

- **Client-visible latency p50/p95/p99:** thời gian request từ biên đến response.
- **HTTP/gRPC status rate:** tỷ lệ 2xx/4xx/5xx và lỗi timeout.
- **Routing decision:** backend pool, phiên bản, vùng, cohort.
- **LB active connections / queue / backend health:** phát hiện cạn capacity.
- **Gateway auth/rate-limit failures:** phân biệt tấn công, cấu hình và người dùng hợp lệ bị chặn.
- **Mesh upstream errors/retries/mTLS failures:** phát hiện lỗi giao tiếp nội bộ.
- **Service error/latency:** phân biệt chi phí ở proxy với xử lý nghiệp vụ.
- **Trace context:** liên kết request xuyên các tầng, có sampling hợp lý.
- **SLO/error budget:** đánh giá có cần dừng rollout hay rollback không.

Đừng dùng user ID, email hoặc token làm metric label cardinality cao. Giữ log/traces có bảo vệ khi cần truy vết chi tiết.

### 16.2. Chống single point of failure

API Gateway, ingress controller hoặc mesh gateway có thể trở thành điểm lỗi chung nếu triển khai một replica hoặc chỉ một zone. Thiết kế redundancy, health check và autoscaling dựa trên tải thực tế. Với control plane của mesh, kiểm tra hành vi khi cấu hình không thể cập nhật hoặc certificate không thể xoay vòng.

### 16.3. Quản lý cấu hình thống nhất

Mỗi policy phải có **owner** rõ:

| Chính sách | Chủ sở hữu gợi ý | Khu vực kiểm tra |
|---|---|---|
| Public API version và quota | API/platform team | API Gateway |
| Host/path route vào cluster | Platform/Kubernetes team | Ingress/Gateway API |
| Cloud L4/L7 public endpoint | Infrastructure/platform | LB/DNS |
| Workload identity/mTLS | Security/platform | Mesh và identity provider |
| Business authorization | Domain/service team | Service code/policy |
| Retry/idempotency cho payment | Payment/Checkout domain team | Client contract và service |
| Cross-region data policy | Security/data architecture | Router + data layer |

Bảng chỉ là ví dụ phân chia trách nhiệm. Tránh hai đội độc lập thay cùng một loại rule mà không biết nhau.

### 16.4. Quy tắc thay đổi có kiểm soát

Routing và security config cũng là phần mềm. Nên version-control, review, lint/test, triển khai theo môi trường, audit và có rollback. Một dòng cấu hình route sai có thể đưa traffic vào backend không tương thích hoặc lộ dữ liệu sai tenant.

## 17. Triển khai theo giai đoạn

### Giai đoạn A — Chỉ cần đưa ứng dụng ra ngoài

Một ứng dụng nội bộ mới có ba endpoint HTTP, một nhóm quản lý và ít consumer. Có thể bắt đầu với DNS + LB/Ingress, TLS, readiness, log/metrics và authentication phù hợp. Chưa cần mesh nếu chưa có yêu cầu mTLS/policy ở quy mô lớn.

### Giai đoạn B — Có nhiều consumer API

Khi mobile/partner cần versioning, quota, onboarding và policy nhất quán, đánh giá thêm API Gateway hoặc các khả năng tương ứng của ingress/controller đang dùng. Định nghĩa API contract trước khi chọn sản phẩm.

### Giai đoạn C — Có nhiều service-to-service dependencies

Khi nhiều nhóm phải quản lý mTLS, telemetry, timeout, access policy và canary east–west, đánh giá service mesh. Thử pilot ở một nhóm service, đo chi phí CPU/memory, độ trễ, độ phức tạp debug và lợi ích policy trước khi phủ toàn bộ.

### Giai đoạn D — Multi-region/tuân thủ

Thêm global routing, data residency và regional failover dựa trên quyền sở hữu dữ liệu. LB/gateway chỉ chọn tuyến; replication, primary ownership, RPO/RTO và consistency phải được thiết kế ở tầng dữ liệu và workflow.

## 18. Bài tập tình huống 1: nên chọn lớp nào?

**Bối cảnh:** Công ty có một ứng dụng quản trị nội bộ trên Kubernetes, ba backend HTTP. Mọi endpoint đều dùng cùng OIDC provider. Không có API đối tác, không cần quản lý subscription/quota. Các backend gọi nhau rất ít.

Hãy trả lời:

1. Có cần API Gateway chuyên dụng hay ingress controller với tích hợp authentication là đủ?
2. Có cần service mesh ngay từ đầu không? Lợi ích cụ thể nào bù chi phí?
3. Một public LB và một ingress controller thực hiện những vai trò nào?
4. Nếu backend scale từ 2 Pod lên 8 Pod, thành phần nào phân phối traffic?
5. Bạn sẽ theo dõi hai metric nào để biết cấu hình đã đáp ứng nhu cầu?

**Gợi ý:** dùng kiến trúc tối giản trước, phân định authentication và authorization, áp TLS, readiness và observability. Không tự thêm một lớp vì tên gọi nghe đúng chuẩn microservices.

## 19. Bài tập tình huống 2: hệ thống thanh toán nhiều service

**Bối cảnh:** Hệ thống công khai API cho đối tác, có Checkout, Inventory và Payment, cần quota theo ứng dụng. Các service nội bộ có yêu cầu mTLS. Đội triển khai muốn bật retry ở gateway, ingress controller, mesh và Payment client.

Câu hỏi:

1. Chức năng nào phù hợp với API Gateway, ingress/LB, mesh và code Payment?
2. Retry ở bốn tầng có thể gây ra tình huống nguy hiểm nào đối với thanh toán?
3. Khi Checkout timeout nhưng Payment đã ghi authorization, trạng thái nên được biểu diễn và đối soát thế nào?
4. Những điểm nào cần xác thực danh tính workload và quyền nghiệp vụ?
5. Nếu Service Mesh gặp lỗi control plane, data plane phải có chính sách xử lý nào?
6. Ba metric nào phân biệt lỗi ở edge, lỗi east–west và lỗi domain Payment?
7. Nếu API Gateway chạy trong cùng cluster và nhận traffic qua Service type LoadBalancer, có nhất thiết cần thêm ingress controller trung gian không?

**Gợi ý:** một chính sách retry có owner, idempotency key, deadline propagation, trạng thái giao dịch truy vấn được, backend authorization, mTLS và các quy tắc fail-closed khi cần.

## 20. Thực hành đọc hai sơ đồ và tìm điểm dư thừa

**Sơ đồ A:**

~~~text
Internet -> Cloud LB -> Kubernetes Ingress -> Orders Service
~~~

**Sơ đồ B:**

~~~text
Internet -> Cloud LB -> API Gateway -> Ingress Controller
         -> Mesh Ingress Gateway -> Orders Service
         -> Sidecar -> Inventory Sidecar -> Inventory
~~~

Hãy lập bảng cho mỗi hop:

- Nhận traffic từ đâu và chuyển đến đâu?
- Có chuyển đổi protocol hoặc kết thúc TLS không?
- Có xác thực hoặc tạo identity mới không?
- Có policy khác biệt mà hop trước chưa đảm nhiệm không?
- Có thể bỏ hoặc hợp nhất hop mà vẫn đáp ứng yêu cầu không?
- Nếu hop lỗi, request bị ảnh hưởng thế nào?
- Trace và log phải giữ những thông tin nào qua hop?

**Không kết luận sơ đồ B luôn sai:** có thể tổ chức đặt một API Gateway quản lý đối tác ở biên và một mesh quản lý east–west. Tuy nhiên, hai ingress/gateway cùng route host/path mà không bổ sung chính sách rõ ràng có thể là dấu hiệu phức tạp không cần thiết.

## 21. Mẫu ADR quyết định kiến trúc mạng/API

~~~markdown
# ADR: API Gateway, Ingress, Load Balancer và Service Mesh

## Bối cảnh
- Loại client: nội bộ / mobile / đối tác:
- Số dịch vụ, số nhóm và môi trường triển khai:
- Loại traffic: HTTP, gRPC, TCP, event:
- SLO latency, availability, security và compliance:
- Yêu cầu quản lý API:
- Yêu cầu mTLS và policy east-west:

## Phương án
1. Chỉ LB + Ingress
2. API Gateway kết hợp entry point
3. Ingress + Service Mesh
4. API Gateway + Mesh (Ingress riêng chỉ khi cần)
5. Một giải pháp hợp nhất nhiều vai trò

## So sánh
- Bảo vệ API contract và consumer:
- Public entry/routing:
- Service discovery / load balancing:
- Workload identity / mTLS:
- Authorization domain:
- Retry/deadline ownership:
- Observability:
- Độ trễ và số hop:
- Độ phức tạp vận hành, chi phí:
- Failover/rollback và blast radius:

## Quyết định
- Sơ đồ đường đi request thực tế:
- Vai trò và owner của từng tầng:
- Các chính sách bị cấm trùng nhau:
- Các giả định và rủi ro:
- Tiêu chí pilot/đo lường:
- Ngày xem lại:
~~~

Mẫu ADR cần được dùng để ghi **lý do lựa chọn** thay vì chỉ ghi tên sản phẩm. Hai hệ thống dùng cùng Kubernetes vẫn có thể cần kiến trúc mạng khác nhau vì API consumer, dữ liệu và đội vận hành khác nhau.

## 22. Checklist trước khi đưa vào production

- [ ] Có sơ đồ north–south và east–west đúng với đường đi traffic thực tế.
- [ ] Biết component nào nhận request public, đâu là service discovery và đâu là LB.
- [ ] Phân biệt Ingress resource, ingress controller và Service type LoadBalancer.
- [ ] Không nhầm Kubernetes Gateway API với toàn bộ chức năng của sản phẩm API Gateway.
- [ ] API Gateway có lý do tồn tại rõ: contract, quota, identity, versioning hoặc aggregation.
- [ ] Mesh có lý do rõ: workload identity/mTLS, traffic policy, telemetry ở east–west.
- [ ] TLS termination, certificate, trusted proxy chain và identity propagation được ghi rõ.
- [ ] Backend vẫn kiểm tra domain authorization và tenant ownership.
- [ ] Không bật retry trùng ở nhiều tầng mà không có kế hoạch tổng thể.
- [ ] Deadline và idempotency được dùng cho operation có side effect.
- [ ] Canary/backends cùng contract được kiểm chứng; rollback không phá trạng thái dữ liệu.
- [ ] Health check, readiness, capacity, autoscaling và failover đã được thử nghiệm.
- [ ] Có metrics/logs/traces đủ để định vị lỗi theo lớp edge, ingress, mesh và domain.
- [ ] Policy được version-control, có owner, test và cơ chế khôi phục.
- [ ] Đã đo chi phí và latency từng hop; bỏ những lớp không tạo giá trị riêng.
- [ ] Kế hoạch region/data residency và topology dữ liệu phù hợp khi hệ thống đa vùng.

## 23. Ghi nhớ

**Load balancer** giải quyết việc phân phối lưu lượng đến backend. **Ingress** tạo và điều khiển điểm vào ứng dụng trong cụm Kubernetes. **API Gateway** tập trung vào bề mặt API dành cho consumer, hợp đồng, xác thực và chính sách tại biên. **Service mesh** tập trung quản trị giao tiếp giữa các workload, nhất là mTLS, identity, traffic policy và telemetry.

Các khái niệm **không loại trừ nhau**: một proxy/controller có thể đảm nhiệm nhiều vai trò. Một kiến trúc tốt không cần nhiều thành phần nhất, mà cần đúng **ranh giới trách nhiệm**, khả năng bảo vệ dữ liệu và API, chính sách không mâu thuẫn, đường truyền quan sát được và chi phí vận hành hợp lý.
