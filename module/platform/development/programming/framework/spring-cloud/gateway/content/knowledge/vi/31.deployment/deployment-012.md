# Phân biệt Kubernetes Ingress, Gateway API và Spring Cloud Gateway

## 1. Ba cái tên dễ nhầm, ba vai trò cần phân biệt

Trong một hệ thống microservices, có nhiều cách đưa lưu lượng HTTP/HTTPS từ Internet đến các dịch vụ chạy trên Kubernetes. Ba thuật ngữ thường xuất hiện cạnh nhau là **Kubernetes Ingress**, **Kubernetes Gateway API** và **Spring Cloud Gateway**. Chúng đều liên quan đến định tuyến request, nhưng **không phải ba tên gọi của cùng một công nghệ**.

- **Kubernetes Ingress** là **API resource chuẩn của Kubernetes** mô tả một phần quy tắc đưa HTTP/HTTPS từ bên ngoài vào các `Service` trong cluster. Nó cần một **Ingress controller** thực thi.
- **Kubernetes Gateway API** là **họ API resources và mô hình phân quyền cấu hình lưu lượng** hiện đại hơn, với các đối tượng như `GatewayClass`, `Gateway`, `HTTPRoute` và `ReferenceGrant`. Nó cũng cần một **controller/data plane implementation** hỗ trợ.
- **Spring Cloud Gateway (SCG)** là **ứng dụng/phần mềm API Gateway xây trên Spring Boot**, nơi lập trình viên khai báo route predicate, filter chain, path/header rewriting, service discovery, authentication, rate limiting, circuit breaker, retry và các chính sách request. Nó có thể chạy **bên trong hoặc ngoài Kubernetes**, sau Ingress/Gateway API hay trực tiếp sau load balancer.

Hai thành phần đầu mô tả **hạ tầng routing của Kubernetes**; thành phần thứ ba là **application gateway** được vận hành như một workload. Cùng tên “Gateway” nhưng một `Gateway` resource của Gateway API **không phải** một bean, route hay Deployment của Spring Cloud Gateway.

~~~mermaid
flowchart TD
    Internet["Internet client"] --> Edge{"Chọn một edge entrypoint"}
    Edge --> Ingress["Ingress resource + Ingress controller"]
    Edge --> KG["Gateway API resources + Gateway controller"]
    Ingress --> Svc["Kubernetes Service: spring-gateway"]
    KG --> Svc
    Svc --> SCG["Spring Cloud Gateway application"]
    SCG --> Catalog["Catalog service"]
    SCG --> Orders["Orders service"]
    SCG --> Identity["Identity service"]
~~~

Sơ đồ biểu diễn **hai kiến trúc thay thế nhau ở vị trí edge**: thông thường không dùng cả Ingress và Gateway API để tranh cùng host/public listener trong một môi trường production. Spring Cloud Gateway là một **lớp ứng dụng tùy chọn** sau edge controller, không phải thành phần bắt buộc để Ingress hay Gateway API hoạt động.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích API resource khác **controller** và khác **data plane** thế nào.
2. Đọc được YAML `Ingress`, `GatewayClass`, `Gateway`, `HTTPRoute` và route YAML của Spring Cloud Gateway.
3. Xác định nơi chịu trách nhiệm **public DNS, TLS termination, host/path routing, authentication, rewrite, retry, circuit breaker và quan sát lưu lượng**.
4. Thiết kế cả trường hợp **Ingress/Gateway API định tuyến trực tiếp tới service** và trường hợp **edge → Spring Cloud Gateway → backend**.
5. Hiểu tách quyền giữa **platform team và application team**, `allowedRoutes`, `parentRefs`, `backendRefs` và `ReferenceGrant`.
6. Không nhầm đường `lb://service` của SCG với `backendRefs` trỏ tới Kubernetes `Service`.
7. Phân tích đường đi TLS/headers/path, tránh double rewrite, auth bypass, spoofed forwarding headers và vòng lặp proxy.
8. Kiểm thử route acceptance, backend reachability, failover, canary, rollout/rollback và vận hành theo khả năng controller thực tế.

> **Phạm vi:** Bài thuộc chương **Triển khai** của module **SPRING_CLOUD_GATEWAY**. Những ví dụ Spring Cloud Gateway tập trung vào **Server WebFlux**, đồng thời chỉ rõ điểm khác của **Server Web MVC**. Các Kubernetes APIs và extension/controller features thay đổi theo phiên bản; không giả định mọi Ingress/Gateway API controller hỗ trợ cùng tính năng, annotation hay CRD.

## 2. Mô hình kiến trúc: API, controller và data plane

Kubernetes resource là **khai báo trạng thái mong muốn**, không phải một chương trình tự nhận HTTP request.

~~~mermaid
flowchart LR
    User["Platform/App team"] -->|"kubectl apply"| API["Kubernetes API server"]
    API -->|"watch resources"| Ctrl["Ingress/Gateway controller"]
    Ctrl -->|"reconcile config"| Proxy["Reverse proxy / cloud LB / data plane"]
    Client["HTTP client"] --> Proxy
    Proxy --> Ksvc["Kubernetes Service"]
    Ksvc --> Pods["Workload Pods"]
~~~

### 2.1. Ingress resource khác Ingress controller

Một `kind: Ingress` chỉ khai báo host/path/backend, TLS và vài thuộc tính chuẩn. **Ingress controller** đọc resource rồi cấu hình NGINX, Envoy, HAProxy, cloud load balancer hoặc một data plane tương ứng tùy sản phẩm. Nếu cluster chưa có controller nhận `IngressClass` phù hợp, YAML có thể được Kubernetes API server chấp nhận **nhưng request từ Internet không được định tuyến**.

### 2.2. Gateway API resource khác Gateway controller

Một `kind: Gateway` khai báo listeners/address/TLS và cách nhận routes; `kind: HTTPRoute` khai báo HTTP routing. **Gateway controller** hiểu và reconcile các objects đó, có thể triển khai data plane từ một cloud LB/proxy/mesh. Gateway API không yêu cầu mọi controller dùng cùng proxy bên dưới.

**Cài CRDs mà không có controller không tạo ra một Gateway hoạt động**. Tương tự, có controller nhưng một `GatewayClass` với `controllerName` không thuộc controller đó sẽ không tự được nhận.

### 2.3. Spring Cloud Gateway là process nhận HTTP thật

SCG là một ứng dụng Spring Boot triển khai thành `Deployment`/`Pods` (hoặc container/VM). Nó tự tiếp nhận HTTP request, chọn route theo **Spring Cloud Gateway route definitions** rồi gọi upstream qua HTTP client. Kubernetes `Service` là địa chỉ ổn định để edge controller chuyển request tới các Pod SCG.

~~~text
Kubernetes control plane:
  Ingress hoặc Gateway/HTTPRoute objects
           |
           v
  Controller reconcile edge proxy

Request data path:
  Client -> Edge proxy -> K8s Service -> Spring Cloud Gateway Pod
                                         -> Catalog/Orders Service -> Pods
~~~

**Phân biệt quan trọng:** Một route `HTTPRoute` được Kubernetes API server chấp nhận chưa chắc ứng dụng Spring Cloud Gateway đã có route tương ứng. Ngược lại, một SCG route được nạp trong JVM chưa chứng minh Internet client có thể đi tới SCG qua Service/Ingress/Gateway API.

## 3. So sánh nhanh theo trách nhiệm

| Tiêu chí | Kubernetes Ingress | Kubernetes Gateway API | Spring Cloud Gateway |
| --- | --- | --- | --- |
| Bản chất | Kubernetes API resource `Ingress` | Họ Kubernetes API resources/CRDs | Ứng dụng Java/Spring Boot và thư viện |
| Cần implementation? | **Ingress controller** | **Gateway API controller** + data plane | **Spring Boot runtime**, outbound HTTP client |
| Chạy ngoài Kubernetes? | Không theo nghĩa Kubernetes API | Không theo nghĩa Kubernetes API | Có |
| Phân vai platform/app | Tương đối hạn chế ở API gốc; thường dựa RBAC/annotations | Thiết kế rõ `GatewayClass`, `Gateway` và `HTTPRoute` | Tùy cấu trúc repository, team và triển khai |
| Public entrypoint | Thường do controller/LB tạo | Do Gateway controller/data plane triển khai | Qua Service/LB/Ingress/Gateway API hoặc trực tiếp nếu được expose |
| Host/path HTTP routing | Có, mức cơ bản | Có, richer route rules theo loại và conformance | Có, qua route predicates |
| Header/method/query match | Tùy ingress controller/annotations; core Ingress hạn chế | HTTPRoute hỗ trợ matching có cấu trúc | Có, qua predicate factories |
| Rewrite/redirect/response headers | Thường controller-specific annotations | Filters theo Gateway API feature/conformance | Gateway filter factories/code |
| Service target | Kubernetes `Service` | `backendRefs` (thường Service) | URI HTTP, `lb://` khi có discovery integration |
| JWT/auth/business authorization | Thường phụ thuộc controller/extension | Phụ thuộc controller/policy extensions, không mặc định | Spring Security + backend authorization |
| Retry/rate limit/circuit breaker | Controller-specific | Tùy supported features/policies | Có các integrations/filter factories tương ứng phiên bản |
| TLS termination | Controller/lb theo TLS configuration | Gateway listener/certificate refs | Có thể tự terminate TLS khi exposed; outbound TLS độc lập |
| Cấu hình thay đổi | `kubectl apply` Ingress | `kubectl apply` Gateway API objects | App config/route source, rollout hoặc refresh tùy thiết kế |
| Đơn vị quan sát | Ingress controller, LB metrics/logs | Gateway controller/data plane metrics/status | Actuator/Micrometer/traces/HTTP client/route ID |
| Nơi thường dùng | Ingress HTTP/HTTPS đã được tổ chức chuẩn hóa | Shared edge routing, delegated ownership, nhiều chính sách rõ ràng | API gateway cần logic ứng dụng, security và filters sâu |

**Không có công nghệ nào tự động thay thế hoàn toàn hai công nghệ còn lại.** Một tổ chức có thể chuyển từ Ingress sang Gateway API mà vẫn giữ nguyên các ứng dụng SCG phía sau; cũng có thể bỏ SCG ở một số API nếu edge controller đã đủ các chính sách cần dùng.

## 4. Kubernetes Ingress: routing HTTP/HTTPS cơ bản

Ingress được cung cấp bởi Kubernetes API `networking.k8s.io/v1`. Về mặt chuẩn, một Ingress mô tả **host/path → Kubernetes Service** và cấu hình TLS tham chiếu Secret. Nó cần Ingress controller, thường được lựa chọn qua `ingressClassName`.

### 4.1. Ví dụ Ingress đến Spring Cloud Gateway

Giả sử SCG đã có `Service` tên `spring-gateway` trong namespace `edge`, expose port 8080. Ingress controller trong cluster quảng bá `IngressClass` tên `public-nginx` (tên **minh họa**, phải thay bằng class thực của cluster).

~~~yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: api-entry
  namespace: edge
spec:
  ingressClassName: public-nginx
  tls:
    - hosts:
        - api.example.test
      secretName: api-tls
  rules:
    - host: api.example.test
      http:
        paths:
          - path: /api
            pathType: Prefix
            backend:
              service:
                name: spring-gateway
                port:
                  number: 8080
~~~

Đường đi mong đợi:

~~~text
GET https://api.example.test/api/catalog/items/42
         |
Ingress controller, host + Prefix /api
         |
Kubernetes Service edge/spring-gateway:8080
         |
Spring Cloud Gateway Pod, nhận /api/catalog/items/42
         |
SCG route chọn Catalog service
~~~

**Chú ý:**

1. `pathType: Prefix` có semantics **theo các thành phần đường dẫn**, không đơn giản là so khớp chuỗi byte tùy ý. Ví dụ path `/api` thường match `/api` và `/api/catalog`, không nên suy rằng nó match mọi chuỗi bắt đầu bằng ba ký tự `api` như `/apix`.
2. Ingress YAML này **không rewrite path**. Client path được chuyển tới SCG theo behavior của controller; **đừng tưởng prefix `/api` tự bị cắt**.
3. `secretName: api-tls` trỏ tới TLS Secret trong namespace chứa Ingress theo quy tắc controller/Kubernetes; Secret phải tồn tại, đúng certificate host và được controller đọc hợp lệ. Không lưu private key trong tài liệu hoặc Git không được bảo vệ.
4. `ingressClassName` phải khớp controller thực; không copy tên NGINX nếu đang dùng cloud provider khác.
5. DNS công khai phải trỏ tới địa chỉ do controller/load balancer cấp. **`kubectl apply` thành công không tự tạo DNS record**.

### 4.2. Core Ingress có giới hạn gì?

Chuẩn Ingress tập trung vào routing HTTP host/path và TLS tương đối cơ bản. Những khả năng như rewrite phức tạp, JWT validation, policy rate limit, header modification hoặc canary **thường được triển khai bằng annotations/CRDs/proxy settings riêng của Ingress controller**. Cùng một annotation có thể vô nghĩa hoặc khác semantics khi đổi controller.

Kubernetes công bố Ingress API đã ở trạng thái **ổn định về tính năng (frozen)**, không phải nơi tập trung thêm nhiều feature routing mới; Gateway API được phát triển nhằm mô hình hóa những nhu cầu rộng hơn. Điều đó **không có nghĩa Ingress hiện có ngừng hoạt động** hoặc mọi cluster phải migration ngay. Quyết định thay đổi dựa trên hỗ trợ controller, mục tiêu vận hành và rủi ro của hệ thống.

### 4.3. Khi nào vẫn chọn Ingress?

Ingress là lựa chọn hợp lý nếu tổ chức đã có controller được vận hành tốt, nhu cầu chủ yếu là **TLS termination + host/path routing đơn giản**, policy hiện tại đáp ứng yêu cầu và việc chuyển đổi không mang lại lợi ích đủ lớn. Kiểm tra roadmap/hỗ trợ phiên bản của vendor để tránh phụ thuộc annotations không còn được duy trì.

## 5. Kubernetes Gateway API: những đối tượng quan trọng

Gateway API thiết kế mô hình **role-oriented** cho ingress/mesh traffic. Với HTTP ingress, các đối tượng thường gặp:

| Resource | Người thường sở hữu | Vai trò |
| --- | --- | --- |
| `GatewayClass` | Platform/cluster operator | Chọn loại controller implementation qua `spec.controllerName` |
| `Gateway` | Platform/network team | Định nghĩa listeners, ports, hostnames, TLS và cách routes được attach |
| `HTTPRoute` | App/team sở hữu API | Match HTTP requests, filters, backend refs; attach qua `parentRefs` |
| `ReferenceGrant` | Owner của namespace **được tham chiếu tới** | Cho phép một số cross-namespace object references |
| `Service` | App/platform team | Đích Kubernetes được HTTPRoute hoặc edge proxy gọi |

**Gateway API là một tập APIs; không phải một chương trình Gateway riêng.** Việc cài CRDs, tạo `GatewayClass` hay `HTTPRoute` mà không có controller/data plane hỗ trợ chưa đủ để chuyển request.

### 5.1. Quan hệ GatewayClass → Gateway → HTTPRoute

~~~mermaid
flowchart TD
    GC["GatewayClass: controllerName"] --> GW["Gateway: HTTPS listener :443"]
    GW -->|"parentRefs + allowedRoutes"| R1["HTTPRoute: /api/catalog"]
    GW -->|"parentRefs + allowedRoutes"| R2["HTTPRoute: /api/orders"]
    R1 --> S1["Kubernetes Service: catalog"]
    R2 --> S2["Kubernetes Service: orders"]
~~~

`GatewayClass` xác định loại gateway controller nào chịu trách nhiệm. `Gateway` là **instance khai báo** cho những listeners/endpoints cụ thể. `HTTPRoute` chỉ mô tả **request match và hành vi route**, nên nhiều nhóm có thể tự quản lý HTTPRoutes được attach vào một Gateway chung dưới chính sách của platform.

### 5.2. Vai trò control plane và data plane

Khi một operator sửa `HTTPRoute`, Kubernetes API server lưu cấu hình, Gateway controller reconcile trạng thái và cập nhật reverse proxy/LB. Request đi qua **data plane** (có thể Envoy, NGINX, cloud LB hoặc sản phẩm khác), **không đi qua Kubernetes API server** trong mỗi HTTP request.

**Controller-managed Gateway** vẫn phải được giám sát, cấp quyền Kubernetes RBAC và vận hành. Lỗi reconciliation có thể khiến resource tồn tại nhưng chưa được data plane lập trình; cần đọc trạng thái chứ không suy từ `kubectl apply` exit code.

## 6. Ví dụ Gateway API: cùng mục tiêu với Ingress, cấu trúc khác

Giả sử tổ chức đã cài **Gateway API CRDs** và một controller hỗ trợ `GatewayClass`, `Gateway` cùng `HTTPRoute`. Ví dụ dưới đây dùng `controllerName: example.net/gateway-controller` **chỉ làm placeholder**; thay bằng giá trị do controller thật công bố.

### 6.1. GatewayClass do platform quản lý

~~~yaml
apiVersion: gateway.networking.k8s.io/v1
kind: GatewayClass
metadata:
  name: public-http
spec:
  controllerName: example.net/gateway-controller
~~~

`GatewayClass` có phạm vi **cluster**, không gắn namespace. Controller thật phải nhận giá trị `controllerName`; nếu không, việc tạo resource **không tạo listener hoặc proxy hoạt động**. Một số controller yêu cầu tham số/installation/config bổ sung ngoài manifest này.

### 6.2. Gateway HTTPS listener do platform quản lý

~~~yaml
apiVersion: gateway.networking.k8s.io/v1
kind: Gateway
metadata:
  name: public-api
  namespace: edge
spec:
  gatewayClassName: public-http
  listeners:
    - name: https
      hostname: api.example.test
      port: 443
      protocol: HTTPS
      tls:
        mode: Terminate
        certificateRefs:
          - kind: Secret
            name: api-tls
      allowedRoutes:
        namespaces:
          from: Same
~~~

Mô hình này yêu cầu một TLS Secret hợp lệ tên `api-tls` trong namespace `edge` và controller được cấu hình xử lý listener. `allowedRoutes.namespaces.from: Same` chỉ cho HTTPRoutes từ **cùng namespace Gateway** attach vào listener theo policy đó. Nó không mở một quyền cross-namespace chung.

### 6.3. HTTPRoute của ứng dụng

~~~yaml
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: app-api
  namespace: edge
spec:
  parentRefs:
    - name: public-api
      sectionName: https
  hostnames:
    - api.example.test
  rules:
    - matches:
        - path:
            type: PathPrefix
            value: /api
      backendRefs:
        - name: spring-gateway
          port: 8080
~~~

HTTPRoute này có ý nghĩa tương đương **ở mức cơ bản** với Ingress phần 4: lưu lượng HTTPS cho `api.example.test/api/**` được controller chuyển tới Kubernetes Service `edge/spring-gateway:8080`. Tuy nhiên **không nên coi nó là bản dịch tương đương 100%** về route precedence, redirect, TLS policy, proxy timeouts, headers hay metrics giữa hai implementations.

### 6.4. Đọc từng trường HTTPRoute

| Trường | Tác dụng | Sai lầm thường gặp |
| --- | --- | --- |
| `parentRefs` | Chọn Gateway/listener để attach HTTPRoute | Tưởng tham chiếu Gateway đồng nghĩa Gateway đã cho phép attach |
| `sectionName: https` | Chọn listener tên `https` | Dùng nhầm tên `protocol` hoặc tên Service |
| `hostnames` | Ràng buộc host được route phục vụ | Tưởng host này tự cấp public DNS/TLS cert |
| `matches.path.type: PathPrefix` | Match tiền tố path theo semantics Gateway API | Giả định Gateway tự strip prefix |
| `backendRefs.name` | Chọn Kubernetes backend Service | Nhầm với Spring Cloud Gateway `lb://` service ID |
| `backendRefs.port` | Cổng **Service** được tham chiếu | Điền `containerPort` dù Service không expose port đó |

**Không tạo cả Ingress của phần 4 và Gateway API của phần 6 cho cùng `api.example.test` trên một hệ thống live rồi để hai edge load balancers cạnh tranh.** Khi migration, phải có chiến lược DNS/canary, test endpoint riêng hoặc chuyển traffic theo từng bước; triển khai YAML minh họa **từng phương án độc lập**.

### 6.5. Gateway API không bảo đảm mọi filter nâng cao

Gateway API mô hình hóa nhiều HTTP matching/filters có cấu trúc hơn Ingress core, nhưng **mức hỗ trợ feature tùy Gateway API release và controller conformance**. Có nhóm tính năng cốt lõi, mở rộng và implementation-specific. Ví dụ URL rewrite, header modification, request mirroring hoặc những policy thời gian/retry có thể có yêu cầu conformance/implementation khác nhau.

Trước khi dùng, xem **conformance report và status của controller**, không tự suy rằng mọi controller hiểu toàn bộ filters chỉ vì API server cho phép lưu field trong CRD.

## 7. Gateway API phân quyền platform và application team

Một lợi ích kiến trúc của Gateway API là tách rõ hai lớp:

- **Platform team** sở hữu listener, cổng, TLS termination, public addresses, GatewayClass và policy cho route attachment.
- **Application team** sở hữu quy tắc path/method/header/backend trong `HTTPRoute` với namespace/RBAC phù hợp.

Ví dụ:

~~~mermaid
flowchart TD
    P["Platform team: edge namespace"] --> GW["Gateway + HTTPS listener"]
    P --> AR["allowedRoutes policy"]
    A["Catalog team: apps namespace"] --> R["HTTPRoute /api/catalog"]
    AR -->|"cho phép namespace attach"| R
    R -->|"backendRefs"| S["Catalog Service in apps"]
    GW --> DP["Gateway controller data plane"]
    R --> DP
~~~

Mặc định `allowedRoutes.namespaces.from: Same` trong ví dụ trước không cho route ở `apps` attach. Nếu muốn **ủy quyền có chọn lọc**, platform có thể dùng **namespace selector** cùng nhãn namespace được kiểm soát.

### 7.1. Cho một namespace ứng dụng attach route

Ví dụ **thay thế** phần `allowedRoutes` của Gateway listener:

~~~yaml
allowedRoutes:
  namespaces:
    from: Selector
    selector:
      matchLabels:
        gateway-access: "approved"
~~~

Namespace `apps` chỉ được phép attach khi nó có label `gateway-access=approved` do **chủ thể được ủy quyền** quản lý. Không để mọi developer tự gắn nhãn namespace nhạy cảm nếu label đó quyết định quyền truy cập public Gateway.

Một HTTPRoute ở namespace `apps` có thể attach tới Gateway ở `edge`:

~~~yaml
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: catalog-api
  namespace: apps
spec:
  parentRefs:
    - name: public-api
      namespace: edge
      sectionName: https
  hostnames:
    - api.example.test
  rules:
    - matches:
        - path:
            type: PathPrefix
            value: /api/catalog
          method: GET
      backendRefs:
        - name: catalog-service
          port: 8080
~~~

Ở đây HTTPRoute và `catalog-service` **cùng namespace `apps`**, nên `backendRefs` không cần một cross-namespace `ReferenceGrant` chỉ để tham chiếu Service đó. Tuy nhiên route phải được listener cho phép attach qua `allowedRoutes`.

### 7.2. allowedRoutes khác ReferenceGrant

Hai cơ chế này giải quyết **hai loại ranh giới**:

| Cơ chế | Câu hỏi trả lời | Nằm ở đâu? |
| --- | --- | --- |
| `Gateway.spec.listeners[].allowedRoutes` | Namespace/kind HTTPRoute nào được phép **attach vào Gateway listener**? | Trên `Gateway` do platform quản lý |
| `ReferenceGrant` | Một HTTPRoute/object trong namespace khác có được phép **tham chiếu backend/đối tượng ở namespace đích** không? | Trong **namespace được tham chiếu tới** |
| Kubernetes RBAC | Ai được tạo/sửa Gateway/HTTPRoute/Secret/ReferenceGrant? | Cluster/namespace permissions |
| NetworkPolicy | Pod nào được kết nối đến Pod/service theo policy mạng? | Network enforcement plugin |
| Spring Security | Principal nào được gọi API kinh doanh? | SCG/application runtime và backend |

**Được attach Gateway không tự có quyền gọi mọi backend Service khác namespace**, và **ReferenceGrant không thay Spring Security**.

## 8. ReferenceGrant khi backend nằm ở namespace khác

Một tình huống phổ biến: Catalog team có `HTTPRoute` ở `apps`, nhưng route muốn chuyển tới `Service edge/spring-gateway` do platform sở hữu. Đây là **cross-namespace backend reference**.

### 8.1. HTTPRoute trong apps tham chiếu Service edge

~~~yaml
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: catalog-via-spring-gateway
  namespace: apps
spec:
  parentRefs:
    - name: public-api
      namespace: edge
      sectionName: https
  hostnames:
    - api.example.test
  rules:
    - matches:
        - path:
            type: PathPrefix
            value: /api/catalog
      backendRefs:
        - name: spring-gateway
          namespace: edge
          port: 8080
~~~

### 8.2. ReferenceGrant tại namespace sở hữu Service

Resource sau phải được **chủ sở hữu namespace `edge` phê duyệt**, không phải developer `apps` tự tạo ở `apps`:

~~~yaml
apiVersion: gateway.networking.k8s.io/v1beta1
kind: ReferenceGrant
metadata:
  name: allow-catalog-routes-to-gateway-service
  namespace: edge
spec:
  from:
    - group: gateway.networking.k8s.io
      kind: HTTPRoute
      namespace: apps
  to:
    - group: ""
      kind: Service
      name: spring-gateway
~~~

`ReferenceGrant` có API version riêng tùy **Gateway API CRDs đã cài** (ví dụ nhiều bản dùng `v1beta1` cho loại này dù `Gateway`/`HTTPRoute` dùng `v1`). Trước khi apply phải kiểm tra `kubectl api-resources` hoặc CRD/version được cluster phục vụ, không mặc định tất cả resources cùng `v1`.

### 8.3. Hai điều kiện độc lập phải đúng

1. **Gateway listener attachment**: `edge/public-api` cho phép namespace `apps` và HTTPRoute phù hợp attach qua `allowedRoutes`.
2. **Backend cross-namespace reference**: `edge` cho phép `HTTPRoute` ở `apps` tham chiếu Service `spring-gateway` qua `ReferenceGrant`.

Thiếu một trong hai, HTTPRoute có thể hiển thị trong cluster nhưng không được controller lập trình thành một rule có backend hợp lệ; kiểm tra `status.parents[].conditions` như `Accepted`, `ResolvedRefs` theo phiên bản/controller. Đừng dùng cluster-admin rights làm cách “sửa nhanh” attachment/reference bị từ chối.

### 8.4. Cấp quyền hẹp nhất

`ReferenceGrant` cho phép theo nhóm/kind/namespace nguồn và kind/name đích theo schema, **không phải RBAC theo từng HTTP path**. Vì vậy có thể cần nhiều lớp kiểm soát:

- Giới hạn những namespace được attach bằng label do platform kiểm soát.
- Chỉ cho phép tham chiếu **Service được chỉ định** thay vì mọi Service.
- RBAC cấm nhóm ứng dụng tự sửa Gateway/Certificate Secret/ReferenceGrant của platform.
- Review HTTPRoute rules để tránh route che path quản trị của nhóm khác.
- NetworkPolicy và backend authentication tiếp tục giới hạn những kết nối dù route reference đã được phép.

## 9. HTTPRoute có thể chọn backend trực tiếp hoặc gọi qua Spring Cloud Gateway

Cùng một public API có thể dùng **hai mô hình**.

### Mô hình A — Gateway API trực tiếp tới business services

~~~mermaid
flowchart LR
    C["Client"] --> E["Gateway API data plane"]
    E -->|"HTTPRoute /api/catalog"| Catalog["Catalog Service"]
    E -->|"HTTPRoute /api/orders"| Orders["Orders Service"]
~~~

Mô hình này phù hợp khi controller và hệ sinh thái policy đáp ứng yêu cầu: TLS, HTTP routing, header handling và các chính sách edge đã được kiểm chứng. Lợi ích là **ít một proxy hop** và ít tài nguyên ứng dụng phải vận hành.

### Mô hình B — Gateway API/Ingress tới Spring Cloud Gateway

~~~mermaid
flowchart LR
    C["Client"] --> E["Ingress hoặc Gateway API data plane"]
    E --> S["Service spring-gateway:8080"]
    S --> G["Spring Cloud Gateway"]
    G -->|"Route/Filters"| Catalog["Catalog Service"]
    G -->|"Auth/Rate limit"| Orders["Orders Service"]
~~~

Mô hình này phù hợp nếu SCG cung cấp **logic routing/filters/bảo mật dành riêng cho ứng dụng**, các tích hợp Java/Spring đã được vận hành tốt hoặc có nhiều API contracts phải biến đổi. Tuy nhiên nó tăng một HTTP hop, có thể thêm **TLS handshake, buffering, queueing, connection pool, telemetry và điểm lỗi**.

### Không có phương án thắng tuyệt đối

| Câu hỏi | Nếu câu trả lời là “có” | Hàm ý thiết kế |
| --- | --- | --- |
| Chỉ cần host/path routing và TLS đơn giản? | Có | Ingress hoặc Gateway API có thể đủ |
| Cần delegated route ownership nhiều namespaces/teams? | Có | Gateway API thường có mô hình rõ hơn |
| Cần custom Java filters hoặc Spring Security/business integration? | Có | Cân nhắc Spring Cloud Gateway |
| Controller edge đã hỗ trợ auth/rate limit phù hợp và được audit? | Có | Có thể tránh duplicate policy ở SCG |
| Cần route predicates/rewrite theo application contract rất đặc thù? | Có | SCG có thể là lớp thích hợp |
| Latency/tài nguyên cực nhạy và SCG không thêm giá trị? | Có | Kiểm tra bỏ bớt proxy hop |
| Có nhiều deployment clusters hoặc chạy ngoài Kubernetes? | Có | SCG app có thể mang logic portable, nhưng edge hạ tầng vẫn cần |

**Không được coi Spring Cloud Gateway là lớp “bắt buộc” chỉ vì module đang dạy SCG**; một quyết định triển khai tốt phải chứng minh mỗi lớp có trách nhiệm riêng và có giá trị rõ ràng.

## 10. Spring Cloud Gateway thực thi route như thế nào?

Trong **Server WebFlux**, SCG chạy trên Spring WebFlux/reactive runtime, route predicates và `GatewayFilter`/`GlobalFilter` xử lý request, sau đó HTTP client gọi backend.

Một cấu hình ví dụ **trên dòng hỗ trợ `spring.cloud.gateway.server.webflux.routes`**:

~~~yaml
server:
  port: 8080

spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: catalog-read
              uri: http://catalog-service.apps.svc.cluster.local:8080
              predicates:
                - Path=/api/catalog/**
                - Method=GET
              filters:
                - StripPrefix=1
                - RemoveRequestHeader=Authorization
                - RemoveRequestHeader=Cookie

            - id: orders-read
              uri: http://orders-service.apps.svc.cluster.local:8080
              predicates:
                - Path=/api/orders/**
                - Method=GET
              filters:
                - StripPrefix=1
~~~

Đường đi giả định:

~~~text
Client GET /api/catalog/items/42?lang=vi
  -> Ingress/Gateway API (KHÔNG rewrite)
  -> Service spring-gateway:8080
  -> SCG Path=/api/catalog/**; Method=GET
  -> StripPrefix=1: /catalog/items/42?lang=vi
  -> RemoveRequestHeader Authorization và Cookie
  -> GET http://catalog-service.apps.svc.cluster.local:8080/catalog/items/42?lang=vi
~~~

Trong K8s, URI kiểu `http://catalog-service.apps.svc.cluster.local:8080` dùng DNS **Kubernetes Service** trực tiếp. Nếu đổi thành `lb://catalog-service`, cần có **Spring Cloud LoadBalancer + ServiceInstance/discovery integration** phù hợp. `lb://` **không được tạo tự động chỉ vì đã chạy trên Kubernetes**.

### 10.1. Namespace cấu hình theo phiên bản

Ở các dòng trước, bạn có thể gặp `spring.cloud.gateway.routes` thay vì `spring.cloud.gateway.server.webflux.routes`. Với Server Web MVC có thể là `spring.cloud.gateway.server.webmvc.routes` hoặc `spring.cloud.gateway.mvc.routes` tùy release. **Không copy cấu hình một nhánh vào nhánh còn lại rồi nghĩ route được đăng ký**.

### 10.2. WebFlux và Web MVC khác nhau

| Gateway Server WebFlux | Gateway Server Web MVC |
| --- | --- |
| Spring WebFlux, Reactor-based routing/filter chain | Spring MVC/Servlet, WebMvc.fn |
| Reactive `GatewayFilter`/`GlobalFilter` | MVC before/handler/after filters, Servlet Filter |
| `SecurityWebFilterChain` | `SecurityFilterChain` |
| Reactor Netty outbound HTTP trong cấu hình phổ biến | HTTP client/request factory theo version MVC |
| Reactive backpressure, `Mono`/`Flux` | Servlet processing/async/streaming semantics riêng |

Hai biến thể cùng có thể được expose qua Ingress hoặc Gateway API, nhưng **không cùng dependency/API/configuration contract**. Không trộn `GlobalFilter` reactive vào project Gateway Server MVC.

### 10.3. Route SCG không tự bảo vệ backend

`Path=/api/orders/**` và `Method=GET` là **routing predicates**, không chứng minh caller được đọc đơn hàng. SCG cần Spring Security thích hợp và backend Orders vẫn phải kiểm tra token audience, scope, tenant và ownership; nếu backend có thể bị gọi trực tiếp, network/security layers phải chống bypass.

## 11. Nên match path, rewrite path và đặt header ở lớp nào?

Trong mô hình hai gateway hops, một HTTP request có thể trải qua **hai lần chọn route và hai lần xử lý path/header**. Sai lầm phổ biến nhất là để cả Ingress/Gateway API lẫn SCG tự cắt cùng prefix mà không có contract.

### 11.1. Quy tắc đơn giản: một nơi sở hữu mỗi phép biến đổi

Giả sử client gọi:

~~~text
GET https://api.example.test/api/catalog/items/42?lang=vi
~~~

Backend Catalog chỉ có endpoint:

~~~text
GET /catalog/items/42?lang=vi
~~~

Thiết kế dễ kiểm thử:

~~~mermaid
flowchart LR
    C["Client /api/catalog/items/42"] --> E["Ingress hoặc Gateway API: match /api, KHÔNG rewrite"]
    E --> G["SCG: Path=/api/catalog/**; StripPrefix=1"]
    G --> U["Catalog nhận /catalog/items/42"]
~~~

Khi đó:

| Lớp | Path đầu vào | Thao tác | Path đầu ra |
| --- | --- | --- | --- |
| Edge Ingress/Gateway API | `/api/catalog/items/42` | Chỉ match host/path | `/api/catalog/items/42` |
| Spring Cloud Gateway | `/api/catalog/items/42` | `StripPrefix=1` | `/catalog/items/42` |
| Catalog backend | `/catalog/items/42` | Xử lý GET theo nghiệp vụ | Response |

**Phản mẫu:** Gateway API controller rewrite `/api/catalog` thành `/catalog`, rồi SCG vẫn tìm `Path=/api/catalog/**`. Kết quả có thể là 404 ở SCG, không phải backend 404. Nếu SCG có catch-all route, request còn có thể bị chuyển sang **backend khác**.

### 11.2. Gateway API URLRewrite có phải luôn có?

Gateway API mô tả filter như `URLRewrite` trong HTTPRoute, nhưng việc hỗ trợ và chi tiết hành vi phải kiểm tra **feature conformance của controller**. Một ví dụ có điều kiện:

~~~yaml
# Một đoạn trong HTTPRoute rule; chỉ dùng khi controller hỗ trợ URLRewrite.
matches:
  - path:
      type: PathPrefix
      value: /api/catalog
filters:
  - type: URLRewrite
    urlRewrite:
      path:
        type: ReplacePrefixMatch
        replacePrefixMatch: /catalog
backendRefs:
  - name: catalog-service
    port: 8080
~~~

Ví dụ này phù hợp với mô hình **Gateway API gọi trực tiếp Catalog**, khi Catalog kỳ vọng `/catalog/...`. Không dùng cùng lúc với SCG route chờ prefix `/api/catalog` nếu không sửa lại contract ở SCG. Đối với Ingress core, rewrite thường là annotation/extension phụ thuộc controller, không có một cú pháp chuẩn liên thông tương đương mọi implementation.

### 11.3. Match method/header/query ở mỗi lớp

Gateway API HTTPRoute có cấu trúc HTTP match cho method/header/query theo khả năng spec/controller; Spring Cloud Gateway có route predicate factories như `Method`, `Header`, `Query`. Nếu edge chỉ match `PathPrefix=/api` nhưng SCG chỉ cho phép `GET` trên Catalog, POST sẽ đi tới SCG rồi không match route; final status phụ thuộc security/error handler và routes khác.

**Đừng coi việc một request không match ở edge là biện pháp authorization**. Phải có Spring Security/backend checks cho private/admin APIs và test cả path base, trailing slash, encoded slash, case/normalization và HTTP method khác.

### 11.4. Header do lớp nào sở hữu?

| Header/metadata | Đề xuất điểm kiểm soát | Vì sao |
| --- | --- | --- |
| `X-Forwarded-Proto`, `Forwarded` | Proxy/ingress **tin cậy** ở ranh giới mạng | Không tin giá trị client tự gửi |
| `X-Request-ID`/trace context | Một owner cho correlation + propagation được kiểm soát | Tránh phát sinh IDs mâu thuẫn |
| `Authorization` | Spring Security, token audience policy | Không tự forward token tới mọi upstream |
| `X-Gateway-Source` | SCG sau authentication hoặc platform edge theo contract | Header tĩnh không đủ chứng minh identity |
| `Host` | HTTP client/proxy routing rules | Không sao chép Host public thành upstream Host tùy tiện |
| `Content-Length`, `Transfer-Encoding` | HTTP transport từng hop | Tránh framing sai khi rewrite/buffer body |
| `Cache-Control`, `Set-Cookie`, `Location` | Đúng origin/owner của response policy | Tránh lộ cookie, redirect nội bộ, cache sai |

Hai proxies cùng gắn `Access-Control-Allow-Origin` hoặc `Strict-Transport-Security` có thể tạo duplicate/mâu thuẫn. Chọn **một owner chính** cho mỗi nhóm security/HTTP response headers và kiểm tra response cuối từ Internet client.

## 12. TLS termination: HTTPS có thể chỉ bảo vệ một hop

Một Ingress `tls.secretName` hoặc Gateway listener `protocol: HTTPS` + `tls.mode: Terminate` bảo vệ **client → edge proxy**. Điều này **không đồng nghĩa** mọi hop tiếp theo đều được mã hóa.

~~~mermaid
flowchart LR
    C["Internet client"] -->|"TLS #1"| Edge["Ingress/Gateway API proxy"]
    Edge -->|"HTTP hoặc TLS #2"| G["Spring Cloud Gateway Pod"]
    G -->|"HTTP hoặc TLS #3"| B["Orders backend"]
~~~

### 12.1. Đọc topology TLS thật

| Hop | Ví dụ từ bài | Có HTTPS chưa? |
| --- | --- | --- |
| Client → edge | `https://api.example.test` | Có khi listener/cert thực hoạt động |
| Edge → SCG Service 8080 | BackendRef hoặc Ingress Service port 8080 | **Không tự có HTTPS** chỉ vì public listener HTTPS |
| SCG → Catalog | `uri: http://catalog-service.apps.svc.cluster.local:8080` | Không; URI đang là HTTP |
| SCG → Orders | `uri: https://orders-service.apps.svc.cluster.local:8443` | Có nếu client xác minh CA/hostname và kết nối thành công |

Đối với controller edge có hỗ trợ backend TLS origination/policy, có thể cấu hình hop Edge → SCG dùng TLS; khả năng và API cụ thể phụ thuộc controller/Gateway API feature/version. Tương tự, service mesh có thể tự mTLS giữa sidecars. **Đừng coi mTLS có hay không chỉ từ manifest HTTPRoute**.

### 12.2. Các yếu tố bảo mật TLS

- Certificate phải khớp hostname/SNI, có trust chain hợp lệ và còn hiệu lực.
- Với SCG outbound HTTPS, xác minh **hostname verification và CA trust**, không dùng trust-all SSL.
- Với mTLS, phân biệt client certificate danh tính của SCG/edge/sidecar theo hop.
- Quản lý TLS Secrets/keystore ở cơ chế secrets được tổ chức phê duyệt; giới hạn quyền RBAC, rotation và audit.
- Khi cert rotation, kiểm tra existing connections và connection pools có được thay/đóng theo policy phù hợp.
- Không log private key, bearer tokens hoặc cookie trong debug/wiretap.

### 12.3. TLS ở nhiều lớp ảnh hưởng latency

Trong mô hình Edge → SCG → Catalog, có thể phát sinh nhiều TCP/TLS handshakes trên những kết nối mới. Keep-alive, HTTP/2, pooled outbound clients và TLS resumption giảm một phần chi phí; nhưng **mỗi lớp proxy tăng điểm nghẽn tiềm năng**. Khi đo latency, tách client→edge, edge→SCG và SCG→Catalog; không gọi mọi chậm trễ “Spring Cloud Gateway xử lý chậm” nếu thực tế edge connection pool đang chờ.

### 12.4. Redirect HTTP sang HTTPS

HTTP → HTTPS redirect có thể do edge controller hoặc SCG làm. Nên chọn một owner cho redirect để tránh loops:

~~~text
Client HTTP -> Edge redirects HTTPS -> Edge HTTPS -> SCG HTTP internal
~~~

Nếu SCG không tin trusted-proxy scheme đúng và tự thấy `http` ở hop nội bộ, nó có thể tiếp tục redirect dù client ngoài đã dùng HTTPS. Hãy chuẩn hóa `Forwarded`/`X-Forwarded-Proto` tại proxy đáng tin và cấu hình Spring forwarded-header handling theo model của ứng dụng, không tin headers từ Internet.

## 13. Authentication/authorization nằm ở đâu?

Ba công nghệ đều có thể xuất hiện trong hệ thống có authentication, nhưng **trách nhiệm cụ thể khác nhau**.

### 13.1. Kubernetes Ingress và Gateway API không tự cấp quyền user theo nghiệp vụ

Ingress core và HTTPRoute core mô tả cách chọn backend; chúng **không mặc định triển khai toàn bộ OAuth2/OIDC login, JWT validation, ownership check hoặc RBAC nghiệp vụ**. Một controller có thể cung cấp external auth, JWT policy hoặc extension, nhưng đó là **implementation/policy cụ thể**, không được giả định chỉ từ `kind: Gateway`.

Ví dụ `HTTPRoute` match `/api/admin` không có nghĩa chỉ admin được gọi. Nếu ứng dụng Orders không xác minh quyền, người dùng có thể đọc tài nguyên sai dù traffic đi qua public HTTPS.

### 13.2. Spring Cloud Gateway áp security theo runtime

Với **Server WebFlux**, Spring Security thường dùng `SecurityWebFilterChain`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class GatewaySecurityConfiguration {

    @Bean
    SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
        return http
                .authorizeExchange(auth -> auth
                        // Chỉ cho phép health probes ở đúng endpoint kiểm tra.
                        // Vẫn phải giới hạn network access tới application port.
                        .pathMatchers(
                                HttpMethod.GET,
                                "/actuator/health/liveness",
                                "/actuator/health/readiness").permitAll()
                        .pathMatchers(
                                HttpMethod.GET, "/api/catalog/**").permitAll()
                        .pathMatchers(
                                HttpMethod.GET, "/api/orders/**")
                                .hasAuthority("SCOPE_orders.read")
                        .anyExchange().denyAll())
                .oauth2ResourceServer(oauth2 ->
                        oauth2.jwt(Customizer.withDefaults()))
                // Chỉ cho Bearer-only stateless API, không dùng cookie auth.
                .csrf(ServerHttpSecurity.CsrfSpec::disable)
                .build();
    }
}
~~~

Với **Server Web MVC**, security tương ứng là `SecurityFilterChain` và `HttpSecurity` (Servlet), **không sao chép `SecurityWebFilterChain` và `Mono` sang MVC**.

Ví dụ chỉ minh họa route public/private:

- `/api/catalog/**` public GET.
- `/api/orders/**` yêu cầu authority `SCOPE_orders.read`.
- Các request khác bị deny-by-default, trừ khi thêm rules được phê duyệt.

Để JWT validation đúng cần issuer/JWKS trust, thời hạn, **audience theo API** và authority mapping phù hợp. Resource Server có thể không tự xác minh audience nghiệp vụ chỉ vì đã cấu hình issuer. `csrf(...disable)` trong ví dụ chỉ hợp lý với Bearer-only stateless APIs; nếu browser dùng session/cookie auth, cần đánh giá và bật CSRF protection phù hợp.

Hai exceptions GET `/actuator/health/liveness` và `/actuator/health/readiness` trong ví dụ dành cho Kubernetes probes **trong mạng được kiểm soát**. Public Ingress/HTTPRoute chỉ match `/api` nên **không nên expose Actuator qua public host**. Nếu tổ chức dùng management port riêng hoặc health probe paths khác, cần xây một security/probe policy tương ứng, không mở `/actuator/**` hoặc `permitAll()` cho toàn bộ management endpoints. Một public Catalog endpoint mang Bearer token hỏng vẫn có thể bị Resource Server từ chối dù route được `permitAll()`, vì authentication filter có thể xử lý credential do client cung cấp.

### 13.3. Backend vẫn phải phân quyền tài nguyên

Một user có `SCOPE_orders.read` **không đương nhiên** được xem đơn hàng của người khác. Backend Orders phải xác minh identity, tenant, resource ownership và quyền thao tác. Nếu backend chỉ dựa vào header `X-User-Id` do client/SCG tạo từ dữ liệu không đáng tin, có thể mở lỗ hổng IDOR/bypass.

### 13.4. Token forwarding là một quyết định riêng

Nếu SCG Resource Server nhận access token có audience cho Gateway, không tự forward token đó tới Catalog/Orders chỉ để tiết kiệm bước xác thực. Cần thiết kế trust/token exchange hoặc backend validation có audience hợp lệ; chỉ chuyển tới dịch vụ được phép trên TLS và theo scope. Với API public Catalog không cần user credential, dùng filter **loại `Authorization`/`Cookie`** như ví dụ phần 10.

**Lưu ý:** Route filter xóa header **không thay thế** policy bảo vệ cổng hoặc network egress. Client có thể cố gọi service backend trực tiếp nếu mạng cho phép; backend và NetworkPolicy phải chặn các đường không được ủy quyền.

## 14. Client IP, Host và Forwarded headers qua nhiều proxy

Khi Ingress/Gateway API đứng trước SCG, IP nguồn của kết nối SCG nhìn thấy có thể là edge proxy, node, sidecar hoặc địa chỉ được NAT; nó **không luôn là IP public của client**.

~~~text
Client: 198.51.100.27
  -> Ingress/Gateway API edge proxy
     X-Forwarded-For: ... (được proxy tin cậy tái tạo theo policy)
  -> Spring Cloud Gateway
     remoteAddress của TCP hop có thể là địa chỉ edge
  -> Backend
~~~

Các địa chỉ trong ví dụ là địa chỉ mẫu, không phải IP đo được.

### 14.1. Không tin Forwarded do client tự gửi

Một client có thể cố gửi:

~~~http
GET /api/orders/42 HTTP/1.1
Host: api.example.test
X-Forwarded-For: 127.0.0.1
X-Forwarded-Host: internal-admin.example.test
X-Forwarded-Proto: https
X-User-Role: ADMIN
~~~

Nếu SCG hoặc backend lấy `X-Forwarded-For` từ request này làm IP tin cậy để bypass rate limit/authorization, hoặc dùng `X-Forwarded-Host` chọn backend URI, hệ thống có thể bị bypass/SSRF.

Thiết kế an toàn hơn:

1. Cấu hình **trusted proxies/networks** tại ranh giới edge; loại hoặc chuẩn hóa forwarding headers do client tự gửi.
2. Chỉ chấp nhận chuỗi forwarded metadata từ các proxy được quản lý.
3. Cấu hình Spring forwarded-header handling dựa trên trusted proxy deployment, không bật tin mọi X-Forwarded header vô điều kiện.
4. Không dùng IP client làm yếu tố xác thực duy nhất, nhất là khi có NAT/CDN/shared IP.
5. Rate limit key nên dựa vào principal/API key đã xác minh khi thích hợp, kết hợp policy IP tin cậy nếu cần.
6. Test **trực tiếp tới SCG Service** (trong môi trường cho phép) để xác định liệu có đường bypass edge policy hay không.

### 14.2. Preserve Host và backend virtual hosting

Một HTTP proxy có thể gửi `Host: api.example.test` hoặc thay bằng hostname upstream, phụ thuộc route config/HTTP client. Nếu backend dùng virtual-host routing, cần một contract rõ cho Host/SNI. **Không tự sao chép public Host đến mọi backend**; TLS hostname verification phải dựa vào tên dịch vụ đích được xác định hợp lệ, không lấy SNI từ header do client tự nhập.

### 14.3. Hop-by-hop headers

`Connection`, `Transfer-Encoding`, `Keep-Alive`, `Upgrade` và các header được chỉ ra trong `Connection` là thông tin của **mỗi hop**, không được sao chép mù quáng qua hai proxy. Để transport từng lớp xử lý, đồng thời test `Content-Length`, `Content-Encoding`, `Location`, `Set-Cookie`, CORS và caching trên **response cuối**.

## 15. Deploy Spring Cloud Gateway Pod sau Ingress hoặc Gateway API

Các resource Ingress/HTTPRoute ở phần trước giả định tồn tại Kubernetes `Service edge/spring-gateway:8080`. Dưới đây là Deployment/Service minh họa để hoàn thiện bức tranh. **Image phải là image do tổ chức tự build và phê duyệt**, không phải container có sẵn ở địa chỉ mẫu.

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: spring-gateway
  namespace: edge
spec:
  replicas: 2
  selector:
    matchLabels:
      app: spring-gateway
  template:
    metadata:
      labels:
        app: spring-gateway
    spec:
      terminationGracePeriodSeconds: 45
      containers:
        - name: gateway
          image: registry.example.test/platform/spring-gateway:1.0.0
          ports:
            - name: http
              containerPort: 8080
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: http
            periodSeconds: 5
            failureThreshold: 3
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 10
            failureThreshold: 3
          startupProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 5
            failureThreshold: 24
          resources:
            requests:
              cpu: 200m
              memory: 256Mi
            limits:
              cpu: "1"
              memory: 768Mi
---
apiVersion: v1
kind: Service
metadata:
  name: spring-gateway
  namespace: edge
spec:
  type: ClusterIP
  selector:
    app: spring-gateway
  ports:
    - name: http
      port: 8080
      targetPort: http
~~~

### 15.1. Để probe hoạt động cần cấu hình ứng dụng

Ví dụ Spring Boot (kiểm tra property theo phiên bản):

~~~yaml
server:
  port: 8080
  shutdown: graceful

management:
  endpoint:
    health:
      probes:
        enabled: true
  endpoints:
    web:
      exposure:
        include: health
~~~

**Giả định** Actuator có dependency, liveness/readiness probes được bật và chúng lắng nghe trên **cùng application port 8080**. Nếu dùng `management.server.port` riêng hoặc custom `management.endpoints.web.base-path`, probe path/port phải thay tương ứng; chú ý một management port có thể khỏe trong khi data plane 8080 bị lỗi, nên cân nhắc **kiểm thử đường data plane** khi thiết kế readiness.

### 15.2. Liveness không giống readiness

| Probe | Mục tiêu | Phản mẫu |
| --- | --- | --- |
| **Liveness** | Process đã bị kẹt không thể tự phục hồi chưa? | Cho liveness phụ thuộc Catalog DB khiến toàn bộ Gateway pods restart vì backend lỗi |
| **Readiness** | Pod có đủ điều kiện nhận traffic hay không? | Luôn OK dù route config chưa nạp hoặc HTTP listener không phục vụ |
| **Startup** | Cho phép startup warm-up hợp lệ trước liveness | Timeout quá ngắn khiến Boot/JVM bị restart liên tục |

Resource requests/limits ở YAML là **số mẫu để hiểu cú pháp**, không phải thông số hiệu năng khuyến nghị. Phải đo latency, CPU, JVM heap, Netty event loop hoặc Servlet threads, outbound pool và error rates trước khi quyết định.

### 15.3. Shutdown/rollout không được cắt requests đang xử lý

Trong rolling update:

1. Pod cũ có thể chuyển sang terminating và cần rời khỏi Service endpoints theo cơ chế Kubernetes/controller.
2. Gateway nên ngừng nhận request mới khi không còn ready, đồng thời **được phép kết thúc requests đang chạy** trong grace period.
3. HTTP client pools, response streaming, SSE/WebSocket và retry in-flight cần lifecycle phù hợp.
4. Edge controller/Service dataplane có thể còn một khoảng propagation delay trước khi không gửi traffic tới Pod cũ.

`server.shutdown: graceful` của Spring Boot là một phần của giải pháp, **không thay** readiness, termination grace, load balancer drain, PDB và kiểm thử thực tế. Không áp `preStop: sleep 5` như một “con số thần kỳ” cho mọi cluster.

### 15.4. Scale gateway khác scale business service

Tăng `replicas` cho SCG có thể tăng capacity inbound, nhưng mỗi replica có DNS/cache/connection pool và các state riêng. Nếu dùng in-memory rate limiter, số replica tăng có thể đổi quota hiệu dụng; nếu dùng shared Redis limiter, cần đảm bảo backend store chịu tải. Cân nhắc HPA, PodDisruptionBudget, topology spread và multi-zone availability theo SLO của cổng vào.

## 16. Kubernetes Service/DNS khác Spring Cloud Gateway service discovery

Có ít nhất **ba cách diễn tả đích** trong bài, nhưng chúng không hoàn toàn tương đương:

| Nơi khai báo | Cách tham chiếu | Ai chọn đích? |
| --- | --- | --- |
| Ingress | `backend.service.name: spring-gateway`, `port.number: 8080` | Ingress controller → Kubernetes Service/endpoints |
| Gateway API | `backendRefs: [{name: spring-gateway, port: 8080}]` | Gateway API controller/data plane → Service/endpoints |
| SCG static URI | `uri: http://catalog-service.apps.svc.cluster.local:8080` | SCG HTTP client → Kubernetes DNS/Service |
| SCG discovery URI | `uri: lb://catalog-service` | Spring Cloud LoadBalancer + ServiceInstance supplier |

### 16.1. Service và Endpoints/EndpointSlices

Kubernetes `Service` ổn định tên/port trong cluster và chọn các Pod endpoints tương ứng theo selector cùng readiness (phụ thuộc Service mode). `EndpointSlice` biểu diễn các endpoints thực tế được quản lý. Trong nhiều triển khai, kube-proxy hoặc eBPF data plane cân bằng kết nối đến Pod. Ingress/Gateway API controller có thể đọc endpoints trực tiếp hoặc đi qua Service VIP tùy implementation.

**Đừng suy ra Service có DNS record nghĩa là có Pod healthy.** Có thể Service tồn tại nhưng EndpointSlices rỗng vì pods chưa Ready, selector sai hoặc backend port sai; edge có thể trả lỗi upstream 503/502 tùy controller.

### 16.2. Spring Cloud LoadBalancer không tự nắm Kubernetes Services

`lb://catalog-service` là một scheme/routing abstraction của Spring Cloud Gateway. Để hoạt động, application cần integration cung cấp `ServiceInstance` từ discovery/source phù hợp; nó không phải một cú pháp Kubernetes DNS tiêu chuẩn.

Với triển khai đơn giản trong cluster, HTTP URI đến FQDN của Service là một lựa chọn rõ ràng:

~~~yaml
uri: http://catalog-service.apps.svc.cluster.local:8080
~~~

Trong một ứng dụng cần client-side discovery/zone-aware selection, `lb://` có thể hợp lý nhưng phải kiểm tra supplier, LoadBalancer cache, TLS/host và fallback/no-instance behavior. Chọn một cơ chế theo yêu cầu, không nhân đôi load balancing vô thức.

### 16.3. Tại sao latency và failover có thể khác?

Khi SCG kết nối tới Service VIP bằng pooled HTTP connections, một số connections có thể còn trỏ tới Pod cũ cho tới khi đóng hoặc lỗi. Khi dùng client-side `lb://`, việc chọn instance và DNS/HTTP client pool có cơ chế cache, health và failover khác.

Do đó khi rollout:

- Kiểm tra request distribution qua các Pod thực sự, không chỉ status `Service`.
- Theo dõi connection idle lifetime, TLS handshake và stale connection resets.
- Không giả định xóa một EndpointSlice làm mọi TCP connection đang mở lập tức chuyển đích.
- Retry chỉ cho những operations an toàn theo idempotency và deadline.
- Không để client chọn tùy ý service ID/URI, tránh SSRF hoặc token egress.

## 17. Header, rewrite, canary và chính sách resilience: phân quyền rõ owner

Ingress/Gateway API controller có thể hỗ trợ nhiều tính năng L7, trong khi Spring Cloud Gateway có hệ sinh thái route filters phong phú. Nếu bật cùng một policy ở hai lớp, một request có thể bị **rewrite, retry, ratelimit hoặc redirect hai lần**.

### 17.1. HTTPRoute weighted backends so với route weight của SCG

Một HTTPRoute có thể khai báo backendRefs với `weight` khi controller hỗ trợ feature đó:

~~~yaml
# Đoạn nằm trong HTTPRoute.spec.rules[]
matches:
  - path:
      type: PathPrefix
      value: /api/catalog
backendRefs:
  - name: catalog-v1
    port: 8080
    weight: 90
  - name: catalog-v2
    port: 8080
    weight: 10
~~~

Đây là **mô hình Gateway API đi trực tiếp tới hai Service versions**. Nó không có nghĩa **mỗi 10 requests** sẽ chính xác 9 request tới v1, 1 request tới v2. Distribution phụ thuộc controller, traffic sample, hashing/stickiness, health và retries. Đừng áp cùng lúc một canary 10% ở HTTPRoute **và** canary 10% ở SCG rồi gọi đó là “10% production traffic”; phân phối thực có thể khác và khó audit.

### 17.2. Phân chia policy theo trust boundary

| Chính sách | Lớp thường phù hợp | Điều cần xác minh |
| --- | --- | --- |
| Public DNS/TLS certificates | Edge controller/ingress | Certificate/SAN, listener/address |
| Admission HTTP ở perimeter | Edge + network controls | Allowed hosts, methods, max body size |
| Public redirect HTTP→HTTPS | Một owner ở edge | Không redirect loop |
| App-route rewrite/header changes | SCG hoặc Gateway API; **chọn một owner** | Backend nhận URL/header đúng |
| JWT validation và scopes | SCG/Spring Security hoặc approved edge auth | Backend cũng kiểm tra quyền tài nguyên |
| Rate limiting | Edge chống abuse, hoặc SCG cho API/user budgets | Key identity, distributed quota, không giới hạn hai lần sai |
| Retry | Một tầng chính theo operation | Total attempts/budget, idempotency |
| Circuit breaker | Gần dependency, đủ telemetry và fallback policy | Không retry/fallback che outage |
| Service discovery | K8s Service/data plane hoặc SCG LB | Đúng instance, failover, TLS identity |
| CORS | Một owner cho browser-facing origin | OPTIONS preflight và headers không mâu thuẫn |
| Access logging/tracing | Cả hai lớp với correlation có chọn lọc | Không double count và không lộ tokens |

**Ví dụ retry amplification:** Nếu edge retry hai lần bổ sung (tổng 3 attempts) và SCG cũng retry hai lần bổ sung (tổng 3 attempts), một client request có thể tạo **tối đa 9 upstream attempts** theo nhánh tuần tự, chưa tính retries ở backend. Vì vậy retry phải có **overall deadline, số lần thử hữu hạn, backoff/jitter và idempotency guard**.

### 17.3. Request mirror không đồng nghĩa canary nhận business traffic

Gateway API controller có thể hỗ trợ request mirroring hoặc extension; SCG cũng có những cơ chế filter/cấu hình tùy phiên bản. Mirror copy một số requests sang backend quan sát, **không nhất thiết dùng response của backend được mirror** để trả client. Với POST có side effect, mirror vào một service thật có thể **tạo giao dịch trùng**. Chỉ mirror traffic đã được bảo vệ dữ liệu, có target sink không tạo side effect và quyền rõ ràng.

### 17.4. Filters mở rộng cần conformance test

Gateway API `RequestHeaderModifier`, `ResponseHeaderModifier`, `URLRewrite`, `RequestRedirect`, `RequestMirror` và các chính sách chuyên sâu khác có thể khác nhau về **Core/Extended/Implementation-specific** và version. Với Spring Cloud Gateway, filter factories cũng phụ thuộc Server WebFlux/Web MVC release. Không dùng “feature giống tên” làm bằng chứng semantics giống nhau; chạy HTTP tests trên controller/runtime đích.

## 18. Bảo mật Kubernetes control plane và management plane

Một thiết kế bảo mật Gateway cần bảo vệ **ai được thay cấu hình** và **ai được gọi API**, không chỉ HTTPS cho client.

### 18.1. Ba mặt phẳng cần bảo vệ

~~~mermaid
flowchart TD
    Admin["Platform admins"] --> KAPI["Kubernetes API / RBAC"]
    KAPI --> GWC["Ingress hoặc Gateway API resources"]
    GWC --> EDGE["Edge data plane"]
    Client["Client"] --> EDGE
    EDGE --> SCG["Spring Cloud Gateway application"]
    Ops["Ops personnel"] --> ACT["Protected Actuator/metrics"]
    ACT --> SCG
    SCG --> SVC["Backend services with own authorization"]
~~~

| Mặt phẳng | Ai có quyền? | Điểm nguy hiểm |
| --- | --- | --- |
| **Kubernetes control plane** | Platform/owners qua RBAC và admission | HTTPRoute trỏ backend trái phép, Ingress/Gateway sửa public host/TLS |
| **HTTP data plane** | Client phù hợp authn/authz policy | Bypass, SSRF, token forwarding, abuse |
| **SCG management plane** | Operators theo quyền thấp nhất | Route listing secrets, route creation/refresh/delete, metrics chứa sensitive labels |

Không publicize API server credentials, service account tokens hoặc Actuator admin endpoints. Một HTTPRoute edit có thể điều hướng traffic sang backend khác; vì vậy **GitOps review và Kubernetes RBAC** phải chặt chẽ tương tự khi thay firewall/routing policy.

### 18.2. Namespace/RBAC/ReferenceGrant không thay NetworkPolicy

Ngay cả khi Gateway listener cấm một HTTPRoute ở namespace lạ attach, Pod của namespace đó có thể vẫn thử gọi trực tiếp Kubernetes Service của SCG/backend nếu network cho phép. **NetworkPolicy** (khi CNI thực sự thực thi) giúp giới hạn Pod-to-Pod traffic, nhưng không thay JWT/mTLS/authorization vì không quản lý quyền tài nguyên người dùng.

### 18.3. Bảo vệ SCG Actuator

Spring Cloud Gateway có các actuator endpoints và management capabilities khác nhau theo version. Không dùng `management.endpoints.web.exposure.include: "*"` trên public listener. Tách management port/network nếu cần, yêu cầu Spring Security ops permissions và giới hạn read/write, đồng thời chỉ expose health/metrics cần thiết.

Một edge Gateway có thể chặn `/actuator/**` trên public host, nhưng nếu một internal Service cho phép bất kỳ Pod nào gọi management port thì vẫn có đường bypass. Kiểm tra cả **Service type, ports, NetworkPolicy và authentication ở chính ứng dụng**.

### 18.4. Kubernetes Secret và TLS certs

TLS Secret ở Ingress/Gateway listener được tham chiếu bằng tên, không nên hardcode private key vào YAML bài học. Với production, cân nhắc cấp phát/rotation qua hệ thống quản lý bí mật được phê duyệt, RBAC tối thiểu, audit và quy trình hết hạn/thu hồi. Một `Secret` không tự được bảo mật tuyệt đối chỉ vì là object Kubernetes; storage encryption, access grants và secret delivery đều cần review.

### 18.5. Chống route takeover và shadowing

Một HTTPRoute mới có thể có hostname/path overlap với route đã tồn tại. Khi có nhiều teams, policies phải chống shadowing route quản trị, route identity và route nội bộ. Gateway API có quy tắc conflict/precedence, nhưng **không nên dựa vào suy luận chưa kiểm chứng về thứ tự resource apply**. Dùng conformance tests, lint/admission policies và review route ownership.

## 19. Observability: muốn debug phải biết response do ai tạo

Với kiến trúc hai gateway lớp, một HTTP status 404/503 có thể được tạo bởi:

~~~text
Client
  |
  v
Ingress/Gateway API data plane  ---> 404/503 trước khi tới SCG
  |
  v
Spring Cloud Gateway             ---> 401/403/404/429/503/504 tại Gateway
  |
  v
Catalog/Orders backend           ---> HTTP 404/503 thật từ backend
~~~

Những status có thể trùng nhưng nguyên nhân khác nhau; không chỉ nhìn `curl -i` rồi kết luận “SCG route sai”.

### 19.1. Mỗi lớp cần metric gì?

| Lớp | Số đo gợi ý | Tác dụng |
| --- | --- | --- |
| Public edge | Requests, host/route, status, TLS errors, backend selection | Biết request có tới edge và được forward không |
| Ingress/Gateway controller | Reconciliation errors, accepted/programmed status | Biết cấu hình đã thành data plane chưa |
| Kubernetes Service | Ready endpoints, EndpointSlices, pod restarts | Biết đích có người phục vụ |
| SCG | Route ID, Spring Security outcome, filters, response status | Phân biệt match/auth/fallback |
| SCG outbound client | Connection pool, DNS/connect/TLS, upstream status/attempts | Phân biệt transport với backend 503 |
| Backend | Request count, trace span, handling time, app status | Biết backend có nhận request thật không |

Nhãn metrics nên dùng **route ID/Service ID ổn định** thay vì raw URL với IDs/user tokens, tránh cardinality cao và lộ PII. Tracing có thể propagate `traceparent` hoặc headers tương ứng nếu config cho phép; không đưa bearer token/cookie vào trace baggage.

### 19.2. Controller status là điểm bắt đầu

Khi dùng Gateway API, kiểm tra:

- `GatewayClass` có được controller chấp nhận?
- `Gateway` có điều kiện cho thấy listener và cấu hình đã được program?
- `HTTPRoute.status.parents[]` cho biết attachment có `Accepted` không, backend references có `ResolvedRefs` không?
- Address/port/certificate của Gateway có sẵn và khớp public DNS?
- Route parentRefs, hostnames và listener allowedRoutes có khớp nhau không?

Tên và semantics của **status conditions** có thể thay đổi theo release/controller; đọc output thực và đối chiếu API/implementation. **Resource được lưu trong API server không đồng nghĩa request có route hoạt động.**

### 19.3. Một số lệnh quan sát an toàn

~~~bash
# Ingress: xem class, host, status và events.
kubectl -n edge get ingress api-entry -o yaml
kubectl -n edge describe ingress api-entry

# Gateway API: xem class, listeners và routes.
kubectl get gatewayclass public-http -o yaml
kubectl -n edge get gateways
kubectl -n edge describe gateway public-api
kubectl -n edge get httproutes
kubectl -n edge get httproute app-api -o yaml

# Kubernetes Service và Pod state.
kubectl -n edge get svc spring-gateway
kubectl -n edge get endpointslices \
  -l kubernetes.io/service-name=spring-gateway
kubectl -n edge get pods -l app=spring-gateway

# Chỉ dùng với quyền được cấp; log có thể chứa dữ liệu nhạy cảm.
kubectl -n edge logs deployment/spring-gateway --tail=100
~~~

Các lệnh giả định resource names và quyền RBAC như ví dụ; **không phải kết quả đã chạy**. Với HTTPRoute ở namespace `apps`, thay `-n edge` thành `-n apps` khi đọc route, còn Gateway/ReferenceGrant ở `edge`. Các lệnh có thể trả lỗi nếu controller/CRDs chưa được cài; đó là manh mối về môi trường, không nhất thiết là YAML sai.

### 19.4. Đo request qua hai proxies bằng HTTP test

~~~bash
# Domain phải trỏ tới edge listener đã triển khai ở môi trường test.
curl -i \
  --connect-timeout 3 --max-time 10 \
  'https://api.example.test/api/catalog/items/42?lang=vi'
~~~

Để xác nhận backend nhận đúng request, dùng **backend stub/request journal** ghi method/raw path/raw query và các header **đã allowlist**. Trong lab có thể tạm expose endpoint test chỉ đọc để nhận biết Pod/instance nào xử lý; không xuất hostname, tokens, full internal topology trên production public API.

**Có thể xảy ra bốn trạng thái khác nhau:** edge chấp nhận nhưng SCG không có route; SCG có route nhưng Service không có endpoints; backend trả HTTP lỗi; hoặc request không qua edge đúng do DNS/TLS listener sai. Mỗi trạng thái cần bằng chứng khác nhau.

## 20. Đánh giá hiệu năng và tài nguyên khi có hai lớp Gateway

Một lớp proxy thêm vào đường đi thường có chi phí:

- L7 routing/filter computation.
- Network hop và có thể TCP/TLS setup trên kết nối mới.
- Outbound connection pool, queues và timeouts.
- HTTP header/body processing; một số filters có thể buffer body.
- JVM heap/CPU/GC, Reactor Netty event loop hoặc Servlet threads của SCG.
- Metrics/traces và cấu hình secrets/certificates.

Tuy nhiên **bỏ Spring Cloud Gateway không tự bảo đảm hệ thống nhanh hơn** nếu controller edge phải thực hiện chính các policy đó bằng extensions nặng, hoặc backend phải tự gánh auth/filters mà SCG đang cung cấp.

### 20.1. Phân rã latency theo hai hops

\[
T_{\text{client-visible}} \approx
T_{\text{client-edge}}
+T_{\text{edge-processing}}
+T_{\text{edge-SCG}}
+T_{\text{SCG-processing}}
+T_{\text{SCG-backend}}
+T_{\text{response-transfer}}
\]

Đây là **ngân sách khái niệm**, không phải công thức cộng p95 của từng thành phần. Một pooled connection không cần TCP/TLS handshake mới trên request tương ứng; retries có thể có nhiều outbound attempts; một số hoạt động chồng lấn. Muốn giải thích p99, cần traces/transport metrics gắn với **cùng operation**.

### 20.2. Benchmark hai kiến trúc có đối chứng

| Biến số | Phương án A: Edge trực tiếp | Phương án B: Edge → SCG |
| --- | --- | --- |
| Public edge/controller | Giữ cùng implementation | Giữ cùng implementation |
| Backend service/version | Cùng Catalog | Cùng Catalog |
| TLS public | Cùng certificate/protocol | Cùng certificate/protocol |
| Backend TLS | Ghi rõ từng hop | Ghi rõ từng hop |
| API auth/policy | Tương đương về chức năng | Tương đương về chức năng |
| Response size/QPS | Cố định | Cố định |
| Retry/breaker behavior | Cùng contract | Cùng contract |
| Metrics | p50/p95/p99, 4xx/5xx, CPU | p50/p95/p99, 4xx/5xx, CPU |

**Không so sánh A không auth, không retry với B có JWT, rate limit và retries rồi kết luận “SCG làm chậm X ms”.** Khi policy khác nhau, phép đo không cô lập chi phí của proxy hop.

### 20.3. Capacity và availability

Nếu SCG là entrypoint dùng chung cho nhiều domains, cần xác định blast radius: một lỗi filter code, memory leak hoặc Redis rate limiter chậm có thể ảnh hưởng tất cả API. Đặt replicas, readiness, timeouts, admission control và circuit breaker phù hợp. Tách SCG theo domain/BFF khi cần team isolation, nhưng cũng cân nhắc overhead của nhiều gateway deployments.

## 21. Migration từ Ingress sang Gateway API mà vẫn giữ SCG

Trong nhiều hệ thống, mục tiêu migration là **thay cách cấu hình edge**, không phải thay toàn bộ logic Spring Cloud Gateway. Một kế hoạch an toàn nên giữ API contracts và SCG backend ổn định trong giai đoạn đầu, rồi mới đánh giá có nên di chuyển một số route/filter lên lớp edge.

### 21.1. Bảng kiểm kê trước khi chuyển

| Thành phần hiện tại | Cần lưu lại | Tại sao quan trọng |
| --- | --- | --- |
| `IngressClass` và controller | Tên, version, annotations hỗ trợ | Không có bản dịch hoàn toàn portable cho mọi annotation |
| Public host/DNS/LB | IP/hostname, DNS TTL, certificate | Tránh downtime hoặc đứt HTTPS |
| Ingress rules | Host, PathType, path priority, backend port | Đảm bảo HTTPRoute cùng request selection |
| Ingress annotations | Rewrite, redirects, CORS, auth, timeouts, upload size | Phân loại sang Gateway API/SCG/controller extension |
| Kubernetes Service | Namespace, port, selectors, EndpointSlices | Tránh route đến Service không có ready Pods |
| SCG routes | Route IDs, predicates, filters, URI, ordering | Không vô tình double rewrite hoặc bypass |
| Spring Security | Public/private/admin rules, JWT issuer/audience | Không thay đổi quyền khi đổi edge |
| Rate limit/retry/breaker | Owner và deadlines, idempotency | Tránh áp policy hai lần |
| Operational SLO | Latency, availability, rollback threshold | So sánh migration có bằng chứng |

### 21.2. Lộ trình migration nhiều giai đoạn

~~~mermaid
flowchart TD
    A["Kiểm kê Ingress + SCG contract"] --> B["Chọn Gateway API controller và conformance"]
    B --> C["Cài CRDs/controller, cấu hình GatewayClass/Gateway"]
    C --> D["Tạo test listener/hostname riêng"]
    D --> E["HTTPRoute tới cùng SCG Service"]
    E --> F["So sánh auth, path/header, TLS, 2xx/4xx/5xx"]
    F --> G{"Parity + SLO đạt?"}
    G -->|Không| H["Sửa Gateway API policy / rollback thử nghiệm"]
    H --> E
    G -->|Có| I["Canary/DNS cutover có kiểm soát"]
    I --> J["Quan sát & rollback window"]
    J --> K["Retire Ingress cũ sau khi ổn định"]
~~~

**Lưu ý:** Với một public hostname, không có nghĩa có thể gắn hai public load balancers rồi dựa vào route order để chọn một. Hãy dùng **host thử nghiệm riêng**, address riêng, cơ chế traffic shifting của hạ tầng hoặc chiến lược DNS được tổ chức phê duyệt. Khi dùng DNS cutover, cần xem TTL/cache của client, certificate ở cả hai endpoints, sessions/websockets và khoảng thời gian **hai entrypoints cùng nhận traffic**.

### 21.3. Không migration bằng cách copy annotation nguyên văn

Một Ingress annotation có thể mô tả rewrite/canary/auth hoặc load-balancer settings thuộc **một vendor cụ thể**. Gateway API có thể có filter/policy tương ứng nhưng:

- Cú pháp có thể khác.
- Tính năng có thể thuộc Extended/implementation-specific và controller không hỗ trợ.
- Thứ tự xử lý rewrite/header/auth có thể khác.
- Việc redirect/rewrite `Location`, `Host` hoặc forwarded headers có thể khác.
- HTTP status khi route không hợp lệ/không có backend có thể khác.

Vì vậy thiết kế bảng mapping **yêu cầu nghiệp vụ → khả năng controller → HTTP test**, không lập bảng mapping chỉ theo tên trường.

### 21.4. Kiểm thử trước khi cutover

Hai endpoint test (Ingress cũ và Gateway API mới) cần được gọi với **cùng** method/path/query/header, token test và payload. Backend stub xác minh đường đi sau SCG như nhau. Kiểm thử cả:

- `GET /api/catalog/items/42` và query UTF-8/encoded characters.
- POST vào GET-only route, 404 route miss, 404 backend.
- Anonymous và JWT thiếu scope vào Orders.
- Redirect/cookie/CORS/preflight theo browser-facing contract.
- HTTPS certificate/SNI, Host header và forwarded metadata.
- Large upload/streaming nếu API có hỗ trợ.
- Backend 503, connect timeout, retries/fallback và rate limiting.

Sau cutover, giám sát **accepted/programmed status**, số endpoints ready, HTTP 4xx/5xx, route-level p95/p99 và backend request counts. Có rollback cả DNS/address và controller resources, không tắt auth/TLS khi sự cố.

### 21.5. Có nhất thiết bỏ Spring Cloud Gateway không?

Không. Sau khi đổi Ingress → Gateway API, SCG vẫn có thể tiếp tục giữ business-aware routes, Spring Security và custom filters. Chỉ cân nhắc loại SCG khi chứng minh các trách nhiệm của nó đã được thay bởi edge/backend một cách **tương đương về chức năng, bảo mật, khả năng quan sát và hiệu năng**, chứ không phải vì hai tên đều chứa từ “Gateway”.

## 22. Troubleshooting theo từng tầng

Một request không thành công cần được quy về nơi có vấn đề: **DNS/TLS listener, Gateway API attachment, Kubernetes Service, SCG route/filter, hay backend**.

| Triệu chứng | Tầng nghi ngờ đầu tiên | Bằng chứng cần xem |
| --- | --- | --- |
| `kubectl apply` Ingress thành công nhưng không có public traffic | IngressClass/controller/LB/DNS | Controller có nhận Ingress? Service address/status? DNS? |
| HTTPRoute tồn tại nhưng traffic không match | Gateway API attachment/hostname/listener | `parentRefs`, `allowedRoutes`, `Accepted` |
| HTTPRoute backend ref bị invalid | ReferenceGrant/Service namespace/port | `ResolvedRefs`, ReferenceGrant ở namespace đích |
| Gateway HTTPS listener không hoạt động | GatewayClass/controller/TLS Secret | Status, listener conditions, cert/SAN/SNI |
| Client báo certificate mismatch | Public DNS/SNI/TLS Secret | Hostname của cert, ingress/Gateway address |
| `/api/catalog` 404 ở SCG sau migration | Double rewrite hoặc route namespace sai | Backend HITS, SCG route match/path nhận thật |
| 404 ở edge, SCG HITS=0 | Host/path/method không match edge | Ingress/Gateway controller route and logs |
| 404 ở backend, SCG route đã match | SCG StripPrefix/RewritePath sai hoặc item không tồn tại | Backend raw path và business response |
| 503 ở edge nhưng SCG không nhận request | Service không có ready endpoints, controller backend health | Service/EndpointSlices/Pods |
| SCG trả 503 khi Catalog không có instance | SCG discovery/load balancer | ServiceInstance cache/HTTP client failure |
| 502/504 tăng khi backend chậm | Outbound connect/TLS/read timeouts | HTTP client metrics, error types |
| Ingress route đúng nhưng Authorization bị mất | Header filtering ở edge hoặc SCG | Request journal không chứa secret values |
| User gọi được Orders không có quyền | Spring Security/backend authorization | JWT validation/rules, backend ownership test |
| 401 chỉ xảy ra với token hợp lệ sau migration | Proxy/header/issuer/audience mismatch | Authorization propagation, JWT decoder logs sanitized |
| Browser CORS error, curl vẫn 200 | Preflight/Origin policy | OPTIONS response, owner CORS header, credentials |
| HTTP→HTTPS redirect loop | Forwarded Proto/redirect ở hai lớp | HTTPS edge termination và SCG trusted-proxy config |
| Cookie domain/path sai | Response rewrite/Set-Cookie policy | Browser-facing headers sau cả hai proxies |
| Rate limit thay đổi khi scale Pods | Per-instance state/keying | Shared store, key resolver, attempts |
| Retry khiến backend overload | Edge và SCG cùng retry | Attempts per inbound request |
| Một replica SCG lỗi ngẫu nhiên | Config/deployment/pool mismatch | Per-Pod revision/route IDs/metrics |
| HTTPRoute canary không ra 90/10 ở 10 calls | Cỡ mẫu/quy tắc phân phối nhỏ | Controller algorithm, larger controlled sample |
| Actuator lộ endpoint quản trị | Management Service/ingress/security policy | Exposures, RBAC/network, ops auth |
| TLS public đúng nhưng backend hop không mã hóa | Edge→SCG hoặc SCG→Service config | URI scheme, backend TLS policy và packet path |

### Quy trình 10 bước

1. **DNS và listener:** Client kết nối đúng IP/LB, SNI, certificate và port chưa?
2. **Controller ownership:** IngressClass/GatewayClass có controller thực quản lý chưa?
3. **Route acceptance:** Host/path/parentRefs/allowedRoutes/ReferenceGrant hợp lệ không?
4. **Edge response provenance:** Edge có tạo lỗi trước khi gọi SCG không?
5. **Kubernetes Service:** Service port và ready EndpointSlices trỏ đúng Pod/targetPort chưa?
6. **SCG inbound:** Pod có nhận request không, Spring Security có chặn trước route không?
7. **SCG routing:** Route ID nào match, path/header sau filter ra sao?
8. **Outbound:** DNS/TCP/TLS/ServiceInstance/connection pool có kết nối backend thành công không?
9. **Backend:** Backend có nhận request và trả HTTP status gì, có retry nhiều lần không?
10. **Response cuối:** Edge có chỉnh header, cookie, Location, CORS hoặc body không?

Điều quan trọng là **phải có evidence theo từng ranh giới**. Không “sửa” bằng cách thay `pathType: ImplementationSpecific`, mở wildcard CORS, tắt TLS verification hoặc cho tất cả Gateway routes public, vì những thay đổi đó có thể che triệu chứng nhưng mở lỗ hổng mới.

### Khi cần kiểm tra SCG độc lập với edge

Trong môi trường test và với quyền RBAC hợp lệ, có thể port-forward tới Kubernetes Service:

~~~bash
kubectl -n edge port-forward svc/spring-gateway 18080:8080
~~~

Sau đó ở một terminal khác:

~~~bash
curl -i 'http://127.0.0.1:18080/api/catalog/items/42'
~~~

Nếu direct port-forward hoạt động nhưng public hostname không, vấn đề có thể ở edge/TLS/route rewrite; nếu cả hai đều thất bại, xem SCG/Service/backend. **Port-forward là kênh debug có quyền truy cập Kubernetes**, không chứng minh đường edge, NetworkPolicy hoặc TLS giống production; không dùng để bypass authentication hay quản lý dữ liệu thật trái chính sách.

## 23. Ma trận kiểm thử từ edge đến backend

| ID | Thử nghiệm | Kết quả cần xác minh |
| --- | --- | --- |
| T01 | Ingress/Gateway API listener đã có public address | DNS/LB trỏ đúng listener |
| T02 | HTTPRoute `Accepted/ResolvedRefs` | Controller đã nhận route/backend hợp lệ |
| T03 | HTTPRoute namespace chưa được `allowedRoutes` cho phép | Không attach |
| T04 | Cross-namespace backendRef thiếu ReferenceGrant | Không được resolve |
| T05 | ReferenceGrant được owner cấp đúng Service name | BackendRef hợp lệ, không mở mọi Service |
| T06 | GET Catalog ASCII | Response 200 từ backend đúng |
| T07 | GET Catalog có query UTF-8/encoded plus | Backend nhận raw path/query đúng contract |
| T08 | Prefix `/api` và `/apix` | Không match sai theo path semantics |
| T09 | HTTP method không được cho phép | Không proxy tới backend qua route GET-only |
| T10 | Double rewrite có chủ đích trong sandbox | Test phát hiện 404/path mismatch |
| T11 | Backend trả HTTP 404 | Phân biệt với route miss 404 |
| T12 | SCG route không tồn tại | Edge forward nhưng SCG route miss |
| T13 | Service không có ready EndpointSlices | Edge/Gateway failure theo controller contract |
| T14 | SCG outbound connect refused | Không treo vô hạn, error an toàn |
| T15 | Backend trả 503 | Final response không bị đổi 200 giả |
| T16 | TLS public cert sai hostname | Client phải reject |
| T17 | TLS tới backend cert không hợp lệ | SCG/client phải fail closed |
| T18 | HTTP→HTTPS redirect | Không redirect loop |
| T19 | Client spoof X-Forwarded-/Host | Không SSRF, không bypass |
| T20 | Anonymous gọi Orders | 401/deny theo policy, backend HITS=0 |
| T21 | JWT thiếu scope | 403/deny theo policy, backend HITS=0 |
| T22 | JWT đúng issuer/audience/scope | Đúng route; backend vẫn xét ownership |
| T23 | Public Catalog nhận token/cookie | Không lộ credential tới backend không cần |
| T24 | CORS OPTIONS preflight | Header/origin chính xác, không double owner |
| T25 | 2xx response có Set-Cookie/Location | Không lộ nội bộ hoặc đổi sai contract |
| T26 | Canary backendRefs 90/10 | Kiểm chứng phân phối với đủ samples |
| T27 | Retry edge + SCG | Attempts không vượt tổng budget |
| T28 | Circuit breaker OPEN | Không gọi backend, fallback đúng |
| T29 | Rolling update SCG | Readiness/drain, không tạo outage đáng kể |
| T30 | Multi-replica SCG | Routes/security config nhất quán |
| T31 | Large upload/streaming | Body/headers và graceful termination đúng |
| T32 | Actuator admin endpoints | Không bị public client truy cập |
| T33 | Hỏng một edge/controller replica | Availability theo SLO, không mất route hàng loạt |
| T34 | Migration cutover/rollback | Cả hai entrypoints trả contract tương đương |

**Không nhất thiết triển khai tất cả ngay**, nhưng những kiểm thử sát trust boundary (T03–T05, T19–T25, T32) và dữ liệu kinh doanh (T06–T17) nên có trước rollout. Mọi destructive test như tạo/delete route hoặc tắt backend chỉ thực hiện trên **môi trường sandbox**, không chạm production.

### Hai loại test cần phối hợp

- **Kubernetes acceptance test:** resource được controller chấp nhận, listener có địa chỉ, Service có ready endpoints và policy cross-namespace đúng.
- **HTTP contract test:** Client thật đi qua listener tới backend stub; assert method, path, headers, status, body và request count.

Một `kubectl apply` success **không thay** HTTP integration test. Ngược lại, một `curl` trả 200 một lần **không chứng minh** cross-namespace policies, authentication hoặc rollback đúng.

## 24. Bài thực hành: một API, hai lựa chọn edge

**Bối cảnh:** Tổ chức có Spring Cloud Gateway đang phục vụ Catalog và Orders trong Kubernetes. Bạn được yêu cầu triển khai một public endpoint HTTPS và đánh giá hai phương án **Ingress hoặc Gateway API**, giữ SCG làm application gateway. Sau đó, thử mô hình edge trực tiếp tới Catalog ở một môi trường lab khác để nhận diện ưu/nhược điểm.

### Phần A — Chuẩn bị cluster test

1. Chọn **Kubernetes version và controller implementation** được tổ chức hỗ trợ. Kiểm tra Gateway API CRDs/controller có sẵn nếu định thử Gateway API.
2. Dựng namespace `edge` và `apps`, phân quyền truy cập phù hợp; không dùng cluster-admin credentials cho một app developer.
3. Dựng Catalog stub và Orders stub ở `apps` với HTTP methods/path rõ và request journal an toàn.
4. Deploy Spring Cloud Gateway (Server WebFlux hoặc Server Web MVC, chọn một) với hai routes và security phù hợp.
5. Tạo `Service edge/spring-gateway:8080`, kiểm tra ready EndpointSlices.
6. Cấp TLS certificate test hợp lệ cho `api.example.test` hoặc host lab khác, không lưu private key trong tài liệu public.
7. Cấu hình DNS/test host để trỏ đúng edge address của **mỗi phương án riêng**, không để hai controllers tranh một endpoint.

### Phần B — Triển khai Ingress

1. Dùng YAML Ingress phần 4, thay `ingressClassName` theo controller cluster.
2. Kiểm tra `kubectl describe ingress`, address, TLS Secret và controller logs đã sanitize.
3. Gọi GET Catalog/Orders với token test phù hợp. Xác minh Ingress chỉ match host/path, không rewrite.
4. Dùng backend journal xác nhận SCG `StripPrefix=1` và header policies.
5. Thử URL không match/host sai/POST vào GET-only route; kiểm tra status và backend HITS.

### Phần C — Triển khai Gateway API **thay thế** Ingress

1. Dùng controller supported `GatewayClass`, `Gateway` và `HTTPRoute` của phần 6, sửa `controllerName` theo cluster.
2. Dùng test listener/hostname/address riêng hoặc tạm vô hiệu phương án Ingress trong sandbox; không để cùng public hostname định tuyến mơ hồ.
3. Kiểm tra `GatewayClass` acceptance, `Gateway` listener status và `HTTPRoute.status.parents[]`.
4. Gọi cùng bộ HTTP requests và so sánh path/status/body/header với phương án Ingress.
5. Tạo HTTPRoute ở namespace `apps` rồi chứng minh `allowedRoutes.from: Same` chặn attachment.
6. Đổi sang namespace selector **do platform kiểm soát** và xác minh route attach.
7. Cho HTTPRoute ở `apps` tham chiếu Service `edge/spring-gateway`, kiểm tra bị từ chối nếu chưa có `ReferenceGrant`; sau khi owner namespace `edge` tạo ReferenceGrant hẹp, xác minh attachment/backend resolution.
8. Xóa grant trong sandbox, xác minh không còn route hợp lệ tới backend đích và không có đường đi bypass khác.

### Phần D — So sánh edge trực tiếp và qua SCG

1. Tạo một HTTPRoute mới qua **test hostname** đưa `/api/catalog` trực tiếp tới Catalog Service ở cùng namespace route.
2. Nếu backend cần path `/catalog/**`, dùng URLRewrite khi controller hỗ trợ hoặc giữ backend contract nguyên để không phụ thuộc extended feature.
3. So sánh với Gateway API → SCG → Catalog, nhưng **giữ cùng auth, request/response policy, TLS và payload**.
4. Đo throughput, p95/p99, CPU/memory, TLS/connections và error rates.
5. Ghi lại chính sách nào do SCG đang cung cấp nhưng edge không có hoặc khó quản lý; không bỏ bước JWT/authorization chỉ để benchmark nhanh.

### Phần E — Bảo mật, fault và lifecycle

1. Gửi `X-Forwarded-For`/`X-Forwarded-Host` giả; không được thay principal, backend target hoặc trusted client IP.
2. Thử JWT không có quyền và JWT sai audience; backend không nhận request được phép bỏ qua security.
3. Thử expired TLS cert hoặc hostname mismatch trên **test listener**; kết nối phải fail closed.
4. Đưa backend Catalog vào trạng thái không Ready; phân biệt edge 503, SCG 503 và backend HTTP 503.
5. Rolling update SCG giữa các replicas, quan sát readiness/graceful drain.
6. Kiểm tra route listing/Actuator không expose ngoài management network.
7. Thử canary hoặc retry trong một layer với backend stub; đếm attempts, **không retry POST thiếu idempotency**.

### Phần F — Báo cáo và tiêu chí đạt

Báo cáo gồm:

- Sơ đồ ba lớp **Kubernetes config/controller/data plane – SCG application – backend**.
- Ingress manifest và GatewayClass/Gateway/HTTPRoute manifests đã điều chỉnh theo controller thật.
- Kubernetes versions, Gateway API CRD/controller conformance, Spring Boot/SCG starter/version.
- Phân quyền `allowedRoutes`, `ReferenceGrant`, RBAC và NetworkPolicy.
- TLS termination ở từng hop và cert rotation/trust model.
- Backend journal cho GET/POST, path rewrite, headers, response status và count.
- Security results anonymous/user/admin/JWT, CORS, forwarding-header spoof.
- Metrics, fault injection, rolling update và phương án rollback.
- Quyết định chọn Ingress/Gateway API và có giữ SCG hay không, kèm bằng chứng.

**Tiêu chí đạt:** Người học giải thích được **resource nào cấu hình hạ tầng, controller nào thực thi, SCG chịu trách nhiệm gì**, triển khai được ít nhất một phương án edge với backend HTTP test, chứng minh namespace permissions và security không bị bypass, đồng thời có kế hoạch canary/rollback.

## 25. Khung ra quyết định và các hiểu lầm thường gặp

Không nên bắt đầu bằng câu hỏi “Ingress hay Gateway API hay Spring Cloud Gateway tốt nhất?” mà bằng **ba câu hỏi tách biệt**:

1. **Ai sẽ tiếp nhận public traffic?** Ingress controller, Gateway API controller hay một public load balancer khác?
2. **Chính sách nào cần thực hiện ở edge?** TLS termination, host/path routing, header policy, auth tích hợp, traffic splitting, cross-namespace ownership?
3. **Có cần application gateway không?** Custom Java filters, Spring Security, service discovery, domain-specific API transformations, fallback hoặc các chính sách mà edge controller chưa đáp ứng?

### 25.1. Gợi ý lựa chọn theo hoàn cảnh

| Hoàn cảnh | Cấu hình thường đáng cân nhắc | Vì sao |
| --- | --- | --- |
| Một vài HTTP services, TLS + host/path đơn giản | **Ingress + controller** | Đơn giản nếu hệ thống đã có Ingress vận hành ổn định |
| Shared cluster có nhiều teams muốn tự chủ routes | **Gateway API + controller** | Phân vai Gateway/GatewayClass/HTTPRoute và attachment policies rõ |
| Cần path/header match, delegated routes và canary controller hỗ trợ | **Gateway API** | Cấu hình L7 có cấu trúc, kiểm tra conformance |
| Có logic Spring Security và custom Java filters nhiều API | **Ingress/Gateway API → Spring Cloud Gateway** | Giữ application gateway cho chính sách nghiệp vụ |
| Backend API đã đủ policy, extra hop tăng cost mà không có giá trị | **Edge controller → Service trực tiếp** | Giảm layers, nhưng phải bảo đảm tương đương security/observability |
| Cần dùng Spring Cloud Gateway ngoài Kubernetes | **SCG sau LB/reverse proxy phù hợp** | Không phụ thuộc Kubernetes API |
| Cần định tuyến TCP/UDP/gRPC đặc biệt | **Xem protocol-specific Gateway API resources và controller support** | Không mặc định Ingress core hoặc SCG hỗ trợ mọi L4/L7 protocol |
| Controller hiện tại thiếu feature cần thiết | **SCG hoặc controller extension khác** | Đánh giá security/support/operational cost |
| Hệ thống Ingress rất ổn định, migration rủi ro lớn | **Giữ Ingress, cải tiến có mục tiêu** | Không chuyển chỉ theo tên công nghệ mới |

### 25.2. Gateway API không chỉ có HTTPRoute, nhưng không phải controller nào cũng có tất cả

Gateway API có các loại route khác nhau cho những protocol/case sử dụng, ví dụ **HTTPRoute**, **GRPCRoute**, và những route TCP/TLS/UDP ở các kênh/phiên bản hỗ trợ. Điều đó **không biến một HTTPRoute thành TCP load balancer**, cũng không chứng minh Gateway controller bạn cài đã hỗ trợ tất cả. Kiểm tra:

- Các CRDs/versions thực sự tồn tại trong cluster.
- Controller conformance/features cho protocol và filter bạn cần.
- Cách cấp TLS credentials, passthrough/termination và backend protocol.
- Access control, cross-namespace policy, traffic status/telemetry của resource đó.

**Spring Cloud Gateway Server WebFlux/Web MVC chủ yếu là application-layer HTTP gateway**, với hỗ trợ những giao thức như WebSocket tùy stack/version và cấu hình. Nó không tự trở thành generic raw TCP/UDP gateway thay cho một L4 controller. Đừng chọn công nghệ chỉ vì đều có từ “gateway”.

### 25.3. Những nhận định sai và cách hiểu đúng

| Nhận định sai | Điều đúng |
| --- | --- |
| “Ingress là Ingress controller.” | `Ingress` là API object; controller/data plane thực thi routing. |
| “Apply Ingress YAML thành công là HTTPS đã có.” | Cần controller, LoadBalancer/address, public DNS và TLS Secret/cert hợp lệ. |
| “Gateway API là một proxy có sẵn trong Kubernetes.” | Gateway API là resources/CRDs và spec; cần controller/data plane. |
| “Có GatewayClass là route hoạt động.” | Cần controller nhận class, Gateway listener và HTTPRoute được attach/resolve. |
| “GatewayClass/Gateway/HTTPRoute là Spring Cloud Gateway objects.” | Chúng là Kubernetes Gateway API resources, không phải SCG route definitions. |
| “HTTPRoute attach được Gateway thì được quyền tham chiếu mọi namespace.” | `allowedRoutes` cho phép attachment; cross-namespace backend ref cần `ReferenceGrant` khi áp dụng. |
| “ReferenceGrant mở quyền HTTP cho người dùng.” | Nó cho phép Kubernetes object reference, không cấp JWT scope hoặc network authorization. |
| “Gateway API tự hỗ trợ mọi JWT, rate limit, retry và mirror.” | Policy/filter support phụ thuộc controller/spec conformance/extension. |
| “Ingress có đủ annotation nên portable sang controller khác.” | Annotations thường implementation-specific. |
| “Ingress/Gateway API match `/api` sẽ tự bỏ prefix.” | Routing match và URL rewrite là hai hành vi khác nhau. |
| “Gateway API có rewrite thì SCG cũng nên StripPrefix.” | Hai rewrite dễ xung đột; chọn owner/contract rõ. |
| “Kubernetes Service có port đúng nghĩa là backend Ready.” | Cần ready endpoints và container/Service port khớp. |
| “`lb://catalog` đồng nghĩa Kubernetes `Service`.” | SCG LoadBalancer cần ServiceInstance/discovery integration riêng. |
| “Public HTTPS nghĩa là mọi hop internal cũng HTTPS.” | Mỗi hop Edge→SCG→backend có protocol/TLS độc lập. |
| “Header X-Forwarded-For là IP client đáng tin.” | Chỉ tin sau trusted proxy normalization/config đúng. |
| “Một route private của SCG là đủ để ngăn gọi backend trực tiếp.” | Backend còn cần authentication/authorization và network policies. |
| “Spring Cloud Gateway tự thay được Ingress controller.” | SCG là ứng dụng; vẫn cần public exposure/TLS/DNS/network deployment thích hợp. |
| “Thêm SCG luôn tăng độ an toàn.” | Chỉ an toàn nếu security/token policy đúng, không tạo thêm bypass/SSRF/management surface. |
| “Bỏ SCG chắc chắn giảm latency đáng kể.” | Cần benchmark tương đương policy; bottleneck có thể ở backend/edge. |
| “Gateway API migration xong thì phải xóa SCG.” | Có thể thay chỉ lớp edge và tiếp tục dùng SCG cho business/API policies. |
| “HTTP status 404 cho biết route nào lỗi.” | Edge, SCG và backend đều có thể trả 404; cần provenance/metrics. |
| “Endpoint Actuator qua ClusterIP thì không cần bảo vệ.” | Pod khác có thể truy cập; phải có auth/network isolation. |
| “Rate limit trên từng Pod sẽ tự thành quota toàn cluster.” | Thường cần store/chính sách chia sẻ nếu yêu cầu distributed quota. |
| “Một HTTPRoute weighted 90/10 nghĩa 10 calls luôn chia 9/1.” | Distribution là thống kê, phụ thuộc controller và traffic sample. |

### 25.4. Checklist duyệt kiến trúc trước production

~~~text
[ ] Biết chính xác Ingress controller hoặc Gateway API controller/data plane.
[ ] GatewayClass/controllerName và supported CRDs/conformance được xác minh.
[ ] Mỗi public host có một chiến lược entrypoint/DNS/rollback rõ ràng.
[ ] TLS termination và mTLS được vẽ cho từng hop, không bật trust-all.
[ ] Ingress/HTTPRoute host/path/method match đúng, không double rewrite.
[ ] Namespace route attachment và cross-namespace ReferenceGrant tối thiểu.
[ ] Kubernetes RBAC, NetworkPolicy và secret management được review.
[ ] Service ports, targetPorts, ready EndpointSlices và SCG probes hợp lệ.
[ ] SCG starter/route namespace phù hợp Server WebFlux hoặc Web MVC.
[ ] SCG và backend đều có authorization phù hợp, JWT audience được kiểm tra.
[ ] Trusted proxy/Forwarded headers và rate-limit key chống spoof.
[ ] Auth, CORS, redirect, response headers có owner ở từng boundary.
[ ] Retry/circuit breaker/canary không trùng/chồng chính sách ngoài ý muốn.
[ ] Actuator/admin/metrics không expose public hoặc không có bảo vệ.
[ ] Có backend HTTP journal để xác nhận final path/method/headers/count.
[ ] Có 2xx/3xx/4xx/5xx, TLS failure, no-endpoint và rollout tests.
[ ] Metrics/traces phân biệt edge, SCG, outbound HTTP và backend.
[ ] Có canary, SLO gate, runbook, rollout và rollback được thử nghiệm.
~~~

## 26. Tổng kết

- **Kubernetes Ingress** là API resource HTTP/HTTPS routing của Kubernetes; **Ingress controller** mới là thành phần reconcile và vận hành data plane nhận request.
- **Kubernetes Gateway API** là một họ Kubernetes APIs, thường có `GatewayClass`, `Gateway`, `HTTPRoute` và `ReferenceGrant`. Nó tách vai trò platform/application rõ hơn, nhưng **vẫn cần controller/data plane**, CRDs và controller support/conformance.
- **Spring Cloud Gateway** là **ứng dụng Java/Spring Boot** nhận và proxy HTTP request. Nó bổ sung route predicates, filter chain, header/path rewrite, khám phá dịch vụ, Spring Security, rate limit, retry, circuit breaker và quan sát request; **không phải Kubernetes Gateway resource**.
- **Ingress/Gateway API và SCG có thể phối hợp**: edge sở hữu public TLS/host/traffic entrypoint, SCG sở hữu những API policies mà tổ chức cần. Hoặc edge route **trực tiếp** tới business Service nếu không cần SCG.
- **`allowedRoutes`** kiểm soát HTTPRoute nào được attach vào Gateway, còn **`ReferenceGrant`** kiểm soát các cross-namespace object references thích hợp. Cả hai không thay Kubernetes RBAC, NetworkPolicy hoặc API authorization.
- **Kubernetes Service**, `backendRefs` và **SCG `lb://`** là những khái niệm routing/discovery khác nhau; muốn dùng `lb://` cần integration cung cấp ServiceInstances.
- **TLS termination ở edge không tự mã hóa các hop trong cluster**. Bảo vệ từng kết nối và kiểm tra hostname/CA/mTLS theo policy; không để forwarded headers hoặc Host từ client quyết định quyền/đích upstream.
- **Một biến đổi path/header, CORS, redirect, retry hoặc rate limit nên có owner rõ ràng**. Hai proxies cùng làm cùng việc có thể gây double rewrite, redirect loop, retry storm, credential leak hoặc quota sai.
- **Triển khai thành công cần đủ ba loại bằng chứng:** Kubernetes resource/controller status, Service/Pods healthy và HTTP request/response đi đúng từ client tới backend. `kubectl apply` success hoặc một `curl 200` không tự chứng minh security/rollout đúng.
- **Migration Ingress → Gateway API** có thể chỉ thay lớp edge, **không bắt buộc loại Spring Cloud Gateway**. So sánh tính năng, bảo mật, hiệu năng, SLO và vận hành với từng controller thật trước khi quyết định.

Nguyên tắc cuối cùng: **hãy xác định rõ ai sở hữu cấu hình lưu lượng, ai thực thi HTTP forwarding, ai bảo vệ danh tính và ai chịu trách nhiệm cho API contract**. Khi những ranh giới đó minh bạch, bạn có thể dùng Ingress, Gateway API và Spring Cloud Gateway đúng vai trò, tránh thêm lớp proxy không cần thiết và triển khai cổng vào microservices an toàn, có thể quan sát, nâng cấp và rollback.

### Tài liệu để đối chiếu theo phiên bản

- **Kubernetes Ingress:** https://kubernetes.io/docs/concepts/services-networking/ingress/
- **Kubernetes Service:** https://kubernetes.io/docs/concepts/services-networking/service/
- **Kubernetes Gateway API:** https://gateway-api.sigs.k8s.io/
- **Gateway API HTTPRoute:** https://gateway-api.sigs.k8s.io/api-types/httproute/
- **Gateway API ReferenceGrant:** https://gateway-api.sigs.k8s.io/api-types/referencegrant/
- **Spring Cloud Gateway reference:** https://docs.spring.io/spring-cloud-gateway/reference/

Hãy chọn tài liệu tương ứng **Kubernetes/Gateway API CRD version, Gateway/Ingress controller, Spring Boot/SCG starter và runtime hiện có**. Bài học cung cấp mô hình và ví dụ để kiểm thử; các manifest dùng tên controller, host, namespace, Service và container image **minh họa**, không được áp nguyên lên production khi chưa được phê duyệt.
