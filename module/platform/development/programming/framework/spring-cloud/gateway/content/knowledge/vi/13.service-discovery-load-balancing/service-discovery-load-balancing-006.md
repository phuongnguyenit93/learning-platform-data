# Predicate và filter mặc định của các tuyến tự sinh trong Spring Cloud Gateway

Khi một hệ thống microservices có nhiều dịch vụ và số instance thay đổi liên tục, việc khai báo mỗi route bằng tay có thể trở nên tốn công. Trong **SPRING_CLOUD_GATEWAY**, **DiscoveryClient Route Definition Locator** có khả năng tạo `RouteDefinition` dựa trên tên dịch vụ mà hệ thống khám phá dịch vụ cung cấp. Điều quan trọng là phải hiểu: **tuyến tự sinh sẽ nhận đường dẫn nào, chuyển tiếp đến service nào và có filter nào mặc định?**

Bài thuộc chương **Khám phá và cân bằng tải**, tập trung vào **Path Route Predicate** và **RewritePath GatewayFilter** mặc định của các tuyến tự sinh. Đây là nền tảng để kết hợp route predicates, filter chain, biến đổi đường dẫn/header, khám phá dịch vụ, xác thực, giới hạn lưu lượng, circuit breaker, retry, TLS và quan sát request trong quá trình xây dựng API Gateway an toàn.

> **Phạm vi:** Các cấu hình chính minh họa **Spring Cloud Gateway Server WebFlux** thuộc những dòng sử dụng namespace `spring.cloud.gateway.discovery.locator.*`, thường gặp ở Gateway 4.x. Ở những dòng mới hơn hoặc **Gateway Server MVC**, tên starter, namespace và tính năng có thể khác. Hãy xác minh tài liệu đúng phiên bản Spring Boot, Spring Cloud release train và Gateway trước khi sử dụng.

## 1. Route thủ công so với route tự sinh

**Route thủ công** cho phép tự đặt tên API công khai, target service và filter:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: inventory-api
          uri: lb://inventory-service
          predicates:
            - Path=/api/inventory/**
          filters:
            - StripPrefix=2
~~~

Cấu hình này do người triển khai quyết định: URL public là `/api/inventory/**`, còn `StripPrefix=2` bỏ hai đoạn `api` và `inventory`. Dùng URI `lb://inventory-service` **không có nghĩa đây là route tự sinh**; route vẫn hoàn toàn được khai báo thủ công.

**Route tự sinh** thì khác: nếu bật DiscoveryClient locator, Gateway có thể lấy tập **service IDs** từ `DiscoveryClient` hoặc `ReactiveDiscoveryClient` và dựng `RouteDefinition` mà không cần mục `routes` tĩnh tương ứng với từng dịch vụ.

~~~yaml
spring:
  cloud:
    gateway:
      discovery:
        locator:
          enabled: true
~~~

Ví dụ registry trả về service ID `inventory-service`, Gateway có thể tạo route cho service đó. Theo cơ chế mặc định, client thường gọi:

~~~http
GET /inventory-service/products/42?sort=price HTTP/1.1
Host: gateway.example.test
~~~

Và downstream `inventory-service` nhận path `/products/42`, giữ query `sort=price` nếu các filter khác không đổi nó.

**Lưu ý:** bật `enabled: true` không tự tạo registry, không đăng ký backend và không bảo đảm có instance hoạt động. Cần một implementation discovery tương thích, thông tin service đúng và cơ chế load balancing cho `lb://`.

## 2. Những thành phần mặc định của một route tự sinh

Trong dạng ký hiệu tổng quát, predicate mặc định có thể được diễn giải là **`Path=/{serviceId}/**`**: `{serviceId}` được thay bằng ID dịch vụ lúc sinh route, chứ không phải chuỗi URL nguyên văn mà client phải gửi.

Với service ID `inventory-service`, mô hình mặc định trong Gateway Server WebFlux thường có:

| Thành phần | Hành vi mặc định | Tác dụng |
|---|---|---|
| **Predicate `Path`** | Match `/inventory-service/**` | Chỉ chọn route khi path bắt đầu bằng tên service |
| **Filter `RewritePath`** | Loại đoạn `/inventory-service` ở đầu path | Downstream nhận path API nội bộ, không mang tiền tố service ID |
| **URI đích** | `lb://inventory-service` | Chuyển việc chọn instance cho cơ chế load balancer |
| **Route ID** | Do locator tạo theo quy tắc của implementation | Được dùng để quan sát và quản lý route; không tự cho rằng bằng đúng service ID |

Giả định một backend có endpoint `GET /products/42`:

~~~text
Client:
  GET /inventory-service/products/42?sort=price

Path predicate:
  /inventory-service/** -> match

RewritePath:
  /inventory-service/products/42 -> /products/42

URI:
  lb://inventory-service

Backend:
  GET /products/42?sort=price
~~~

Ở đây **predicate chọn route trước**, filter **sửa path sau**, rồi routing/load balancer mới chọn đích. `RewritePath` mặc định chỉ giải quyết tiền tố path, không tự xóa query string, request headers hay JSON body.

### Biểu thức mặc định được hiểu như thế nào?

Khi sinh route, locator sử dụng `serviceId` như một biến trong biểu thức cấu hình. Hai phép biến đổi có thể diễn đạt khái niệm như sau:

~~~text
Path predicate:
  / + serviceId + /**

RewritePath:
  regexp      = / + serviceId + /?(?<remaining>.*)
  replacement = /${remaining}

Destination:
  lb://serviceId
~~~

`remaining` là nhóm capture của regex: đoạn path còn lại sau tiền tố service ID. Đây là **công thức minh họa để giải thích hành vi**, không phải YAML của một route tĩnh. Khi tùy biến DiscoveryClient locator, biểu thức cấu hình động và cách escape ký hiệu thay nhóm regex phải tuân theo phiên bản đang chạy.

**Không nhầm route tĩnh với route tự sinh**: trong route tĩnh, `/inventory-service/**` là một giá trị cố định; trong locator tự sinh, giá trị tương ứng được tạo cho **mỗi service ID**.

~~~mermaid
flowchart TD
    REG["Registry: inventory-service"] --> DISC["DiscoveryClient"]
    DISC --> LOC["DiscoveryClientRouteDefinitionLocator"]
    LOC --> DEF["RouteDefinition: Path, RewritePath, lb://"]
    DEF --> ROUTE["RouteLocator: Route có thể thực thi"]
    REQ["GET /inventory-service/products/42"] --> MATCH{"Path có khớp?"}
    ROUTE --> MATCH
    MATCH -->|Không| OTHER["Xét route khác"]
    MATCH -->|Có| REWRITE["RewritePath -> /products/42"]
    REWRITE --> LB["Load balancer chọn instance"]
    LB --> DOWN["Backend inventory-service"]
    DOWN --> RESP["Response về client"]
~~~

## 3. DiscoveryClient và LoadBalancer là hai nhiệm vụ khác nhau

Nhiều lỗi được gán chung cho “discovery” trong khi chúng xảy ra ở những giai đoạn khác nhau.

**Service discovery** trả lời: *Có những service ID nào và những instance nào được đăng ký?* **DiscoveryClient Route Definition Locator** trả lời: *Có cần tạo route cho service ID ấy không, và quy tắc chọn request là gì?* **Spring Cloud LoadBalancer** trả lời: *Trong các instance của service đang có, request này đi đến instance nào?*

Giả sử registry cung cấp:

~~~text
inventory-service
  - instance A: 10.20.1.11:8080
  - instance B: 10.20.1.12:8080

billing-service
  - instance C: 10.20.2.21:8080
~~~

Locator có thể sinh **một route cho inventory-service** và **một route cho billing-service**, không cần sinh riêng một route cho instance A và B. Khi request match route inventory, load balancer mới chọn A hoặc B.

| Thay đổi hệ thống | Có cần đổi route tự sinh? | Chọn instance có thể đổi? |
|---|---|---|
| Thêm service ID mới | Có thể cần refresh/tạo thêm route | Có |
| Thêm instance cho service đã biết | Không nhất thiết | Có |
| Một instance mất kết nối | Route có thể vẫn tồn tại | Có |
| Thay `Path`/`RewritePath` của locator | Cần áp dụng cấu hình và cập nhật routes | Không trực tiếp |
| Một service không còn instance nào | Route có thể vẫn hiện diện | Không thể chọn instance khả dụng |

Đường đi thực tế còn phụ thuộc cache và cơ chế refresh của DiscoveryClient/LoadBalancer. **Có route không chứng minh có backend khỏe mạnh**; một request có thể match path nhưng thất bại vì load balancer không tìm được instance.

## 4. Điều kiện cần để tuyến tự sinh hoạt động

Một môi trường Gateway cần tối thiểu:

1. **Gateway Server WebFlux** đúng web stack và release train.
2. Một **DiscoveryClient hoặc ReactiveDiscoveryClient** phù hợp với registry bạn chọn, ví dụ Eureka, Consul hoặc tích hợp môi trường orchestration.
3. Registry có **service ID thật** và instance backend đăng ký đúng.
4. Thuộc tính **discovery locator enabled** đúng namespace của phiên bản.
5. Một cơ chế **load balancing** xử lý URI có scheme `lb://`; thường cần Spring Cloud LoadBalancer, chẳng hạn artifact `spring-cloud-starter-loadbalancer` nếu dependency chưa có.
6. Kết nối mạng từ Gateway tới các instance backend, gồm DNS/service discovery, TLS và firewall phù hợp.

Ví dụ cấu hình về **phía Gateway locator**:

~~~yaml
spring:
  application:
    name: edge-gateway
  cloud:
    gateway:
      discovery:
        locator:
          enabled: true
          lower-case-service-id: true
~~~

Đây **không phải cấu hình hoàn chỉnh của Eureka/Consul/Kubernetes**; mỗi giải pháp cần starter và cấu hình riêng. `lower-case-service-id: true` hữu ích khi registry, ví dụ một số cấu hình Eureka, trả tên service viết hoa trong khi nhóm vận hành muốn URL path chữ thường.

Tuy nhiên, không khẳng định mọi registry đều phân biệt case hoặc normalize service ID như nhau: hãy kiểm tra **tên gốc từ DiscoveryClient**, **Path thực sự được sinh** và **URI `lb://...` cuối cùng**.

## 5. Mặc định Path và RewritePath: điều cần kiểm tra trực tiếp

Khi dịch vụ mang tên `orders`, ví dụ:

~~~text
GET /orders/api/v1/42
~~~

Theo mặc định, Route Predicate khớp `/orders/**` và filter rewrite loại `/orders` để backend có thể nhận:

~~~text
GET /api/v1/42
~~~

Điều này giải quyết một khác biệt thường gặp: **backend không cần biết tiền tố service ID của Gateway**.

Có ba tình huống cần phân biệt:

| Tình huống | Kết quả thường gặp | Chẩn đoán |
|---|---|---|
| Không có route khớp `/orders/**` | 404 nếu không có handler khác | Kiểm tra locator, service ID, Path/case, route order |
| Route khớp, rewrite sai làm backend nhận `/orders/api/v1/42` | Backend có thể trả 404 | Kiểm tra RewritePath và request path thực nhận |
| Route khớp, rewrite đúng, nhưng không có instance | Lỗi chọn instance/routing, thường 5xx hoặc 404 theo cấu hình | Kiểm tra registry instances, LoadBalancer, kết nối |

**Không nên suy từ HTTP status một mình.** Tốt nhất là dùng backend echo/log để biết path nhận được và bật khả năng quan sát route ID, request URI, instance đã chọn một cách có kiểm soát.

### Mặc định không phải quy tắc URL public bắt buộc

Nhiều sản phẩm muốn URL `/api/orders/**` thay vì `/orders/**`. Khi đó có thể:

- Viết **route thủ công** với public prefix rõ ràng và `StripPrefix`/`RewritePath` phù hợp.
- Tùy biến mẫu predicate/filter của DiscoveryClient locator theo đúng phiên bản.
- Sinh routes bằng hệ thống cấu hình có review/approval, độc lập với service ID nội bộ.

Khi dùng locator nhưng muốn prefix `/api/{serviceId}/**`, **phải sửa đồng bộ cả Path và RewritePath**. Chỉ sửa Path sẽ khiến downstream nhận sai path; chỉ sửa RewritePath có thể khiến route không bao giờ match URL public mới.

## 6. Tùy biến danh sách predicates: dễ mất mặc định Path

Đây là điểm dễ gây lỗi nhất trong chủ đề này: **khi thay cấu hình `discovery.locator.predicates`, bạn không nên mặc định Gateway vẫn tự thêm Path ban đầu**.

Tài liệu Gateway hướng dẫn: nếu bạn muốn có thêm predicate tùy biến **và vẫn giữ chức năng mặc định**, hãy **khai báo lại Path mặc định** bên cạnh các predicates mới.

### Ví dụ thêm Method

Muốn một route tự sinh chỉ nhận GET, cùng với Path có tiền tố service ID:

~~~yaml
spring:
  cloud:
    gateway:
      discovery:
        locator:
          enabled: true
          predicates:
            - name: Path
              args:
                pattern: "'/' + serviceId + '/**'"
            - name: Method
              args:
                methods: "'GET'"
~~~

Ví dụ thể hiện cấu trúc khai báo locator có **biểu thức dựa vào serviceId**. Tên field, kiểu giá trị được bind và cú pháp biểu thức của `Method` phải đối chiếu với đúng phiên bản Gateway: trong phần này, quan trọng nhất là **giữ lại Path** khi thêm một điều kiện mới.

Ở mức logic, các predicates trên cùng một route thường kết hợp **AND**. Vì vậy request `POST /orders/42` không match route chỉ cho phép GET, dù Path đúng.

Nếu vô tình chỉ còn predicate `Method` và không còn Path, route có thể trở nên **quá rộng**, chồng lấn routes khác và điều phối request đến backend ngoài ý định. Đặc biệt nguy hiểm nếu locator được bật cho nhiều service nội bộ.

### Mặc định không tự bảo vệ quyền truy cập

Ngay cả khi Path hợp lệ, Gateway không tự phân biệt một service ID là public hay internal. Nếu registry có `internal-admin`, URL `/internal-admin/**` có thể trở thành điểm truy cập ngoài ý muốn khi bật locator mà không có giới hạn. Cần **lọc danh sách service IDs**, áp dụng network segmentation và xác thực/phân quyền.

## 7. Tùy biến danh sách filters: dễ mất mặc định RewritePath

Tương tự, khi bạn đặt `discovery.locator.filters` để thêm filter tùy biến, **phải xác minh RewritePath mặc định có được giữ lại hay không**.

Ví dụ mong muốn mỗi request đến service tự sinh có thêm header chẩn đoán `X-Edge-Discovery: gateway`. Mô hình filter đúng về ý định:

~~~text
1. RewritePath:
     regexp      = '/' + serviceId + '/?(?<remaining>.*)'
     replacement = '/${remaining}'

2. AddRequestHeader:
     name  = X-Edge-Discovery
     value = gateway
~~~

Nếu bạn chỉ khai báo filter `AddRequestHeader` mà không còn `RewritePath`, backend có thể nhận cả tiền tố service ID. Request tới `/orders/api/v1/42` vẫn match Path nhưng bị forward với path không mong muốn.

### Ví dụ property-style tham khảo

Cấu hình của discovery locator thường biểu diễn factory và `args` dưới dạng các property paths, trong đó một số đối số là **biểu thức SpEL** để tính theo service ID:

~~~properties
spring.cloud.gateway.discovery.locator.enabled=true
spring.cloud.gateway.discovery.locator.filters[0].name=RewritePath
spring.cloud.gateway.discovery.locator.filters[0].args[regexp]='/' + serviceId + '/?(?<remaining>.*)'
spring.cloud.gateway.discovery.locator.filters[0].args[replacement]="'/${remaining}'"
spring.cloud.gateway.discovery.locator.filters[1].name=AddRequestHeader
spring.cloud.gateway.discovery.locator.filters[1].args[name]=X-Edge-Discovery
spring.cloud.gateway.discovery.locator.filters[1].args[value]=gateway
~~~

**Lưu ý:** Phần `args[replacement]` trong ví dụ là một **SpEL string literal** biểu diễn path thay thế sử dụng nhóm regex `remaining`. Khi chuyển đổi giữa định dạng `.properties` và YAML, cần kiểm tra cách phiên bản đang chạy diễn giải ký hiệu `${remaining}` (property placeholder hoặc regex replacement) và các quy tắc escaping. Hãy đối chiếu biểu thức mẫu trong tài liệu *DiscoveryClient Route Definition Locator* cùng phiên bản, rồi xác minh path thực tế bằng integration test.

Phần `AddRequestHeader` làm việc với request headers, còn `RewritePath` làm việc với đường dẫn. Hai filter giải quyết hai mục tiêu riêng; một filter header **không thay được** bước xóa tiền tố path.

### Cú pháp locator không giống route tĩnh

Route tĩnh thông thường có:

~~~yaml
predicates:
  - Path=/orders/**
filters:
  - StripPrefix=1
~~~

Ở đây tên `orders` đã được ghi **cố định**. Discovery locator cần biểu thức theo từng `serviceId` để sinh route cho nhiều service, không thể sao chép bộ filter dành cho một tên service rồi mặc nhiên dùng cho tất cả service.

## 8. Mở rộng tiền tố public và đường dẫn backend

Giả sử nhóm cần public URL:

~~~text
/api/inventory-service/products/42
~~~

nhưng backend inventory nhận:

~~~text
/products/42
~~~

Một locator tùy biến phải biểu đạt:

| Giai đoạn | Quy tắc mong muốn |
|---|---|
| Route matching | `Path=/api/{serviceId}/**` |
| Rewrite | Bỏ cả `/api/{serviceId}` |
| Routing | Chọn backend bằng URI `lb://{serviceId}` |

Không nên chỉ thêm `/api` vào Path mà để RewritePath mặc định chỉ xóa `/{serviceId}`, vì tiền tố `/api` làm regex không còn khớp từ đầu đường dẫn. Khi đó backend có thể nhận path nguyên dạng `/api/inventory-service/products/42` và trả 404.

~~~mermaid
flowchart LR
    A["Client /api/inventory-service/products/42"] --> B["Path match /api/inventory-service/**"]
    B --> C["RewritePath bỏ /api/inventory-service"]
    C --> D["/products/42"]
    D --> E["lb://inventory-service"]
    E --> F["Instance backend"]
~~~

**Cân nhắc thiết kế:** Trong API public, URL được coi là một phần hợp đồng với khách hàng. Service ID lại là chi tiết triển khai có thể đổi khi phân tách hoặc gom dịch vụ. Đôi khi route thủ công với URL public ổn định phù hợp hơn việc tự phơi bày toàn bộ tên service trong registry.

## 9. Kiểm soát service nào được tự sinh route

Một registry có thể chứa:

~~~text
catalog
orders
billing
internal-admin
metrics-agent
~~~

Nếu bật locator trên một Gateway public mà không giới hạn service IDs, hệ thống có nguy cơ sinh cả URL `/internal-admin/**` hoặc `/metrics-agent/**`, tùy những service DiscoveryClient nhìn thấy. Đây là lý do route tự sinh cần **chính sách allowlist và network access**.

Một số bản Gateway hỗ trợ thuộc tính `include-expression`, dùng biểu thức SpEL quyết định có sinh route từ một service ID hay không. Ví dụ minh họa:

~~~yaml
spring:
  cloud:
    gateway:
      discovery:
        locator:
          enabled: true
          include-expression: "serviceId == 'catalog' or serviceId == 'orders'"
~~~

Biểu thức trên chỉ đúng nếu registry thực sự trả các tên `catalog` và `orders` theo kiểu chữ đó. Nếu registry cung cấp `CATALOG`, biểu thức so sánh case-sensitive cần được điều chỉnh/kiểm chứng. **Không dựa vào việc bật `lower-case-service-id` rồi tự kết luận biểu thức lọc đã chạy trên ID lowercase**; hãy quan sát dữ liệu DiscoveryClient và routes đã sinh của chính phiên bản bạn dùng.

Trong hệ thống thật, còn cần:

- Giới hạn service discovery theo environment/namespace, tránh gom public và internal không kiểm soát.
- Spring Security hoặc cơ chế xác thực/phân quyền ở tầng thích hợp.
- NetworkPolicy, firewall và không cho client bên ngoài truy cập trực tiếp backend ngoài ý định.
- Rate limiting phù hợp từng API, không chỉ theo header do client tự nhập.
- Bảo vệ endpoints quản trị route và discovery; không cho Internet thay đổi routes động.

## 10. Filter chung và filter của route tự sinh

Sau khi `RouteDefinition` được sinh và chuyển thành `Route`, request vẫn đi qua hệ thống filter chain của Gateway.

| Loại | Phạm vi thường gặp | Ví dụ |
|---|---|---|
| **Discovery locator filters** | Mẫu filter để tạo ra các route tự sinh | RewritePath mặc định, thêm header cho tuyến discovery |
| **`default-filters`** | Filter được gắn vào các routes theo cơ chế mặc định của Gateway | SetRequestHeader dùng chung |
| **`GlobalFilter`** | Pipeline Gateway sau khi Route được chọn | Trace/correlation ID, chính sách chung |
| **`WebFilter`** | Pipeline Spring WebFlux trước/lân cận route matching | Spring Security, chặn request ở tầng web |
| **Load-balancing routing filter** | Xử lý URI scheme `lb://` trong chuỗi Gateway | Chọn service instance |

Các nhóm này **không đồng nghĩa** với nhau. Thêm một `default-filter` không có nghĩa bạn đã sửa mảng `discovery.locator.filters`; và một `GlobalFilter` không có nghĩa mọi request không match route cũng đều chạy qua nó.

Thứ tự chạy phụ thuộc cơ chế `Ordered`, filter của Route và các filter nội bộ. Khi có nhiều filter sửa cùng path/header, hãy kiểm tra **request backend thực nhận**, thay vì suy luận chỉ theo thứ tự dòng YAML.

### Liên hệ với retry, circuit breaker và TLS

Một route tự sinh có thể tích hợp `Retry` hoặc `CircuitBreaker` theo phiên bản, nhưng những cơ chế đó **không tự xuất hiện chỉ vì bật DiscoveryClient**. Kiểm soát timeout, backoff, số lần thử lại và idempotency, đặc biệt với request ghi dữ liệu.

Tương tự, URI `lb://serviceId` chỉ biểu diễn đích qua load balancer; để bảo vệ đường truyền, cần cấu hình TLS trên client → Gateway và Gateway → downstream theo chính sách. Không suy rằng mọi URI `lb://` tự động sử dụng HTTPS hoặc xác thực certificate.

## 11. Chẩn đoán lỗi theo từng bước

Một cách hiệu quả là tìm xem lỗi nằm tại **tạo route**, **chọn route**, **rewrite path** hay **chọn instance**.

| Triệu chứng | Giai đoạn nghi ngờ | Bằng chứng cần tìm |
|---|---|---|
| Không có route nào tự sinh | DiscoveryClient / locator | `enabled` đúng namespace, registry có service IDs, đã refresh chưa |
| Có route nhưng `/orders/**` trả 404 ở Gateway | Path match | Service ID đúng case, predicate trong Route runtime, route order |
| Backend nhận `/orders/items` thay vì `/items` | RewritePath | Locator filters có giữ RewritePath không, regex/replacement có đúng không |
| Route match nhưng không có backend | LoadBalancer / discovery instance | Instance list, đăng ký health/status, dependency load balancer |
| Lúc thành công lúc 5xx | Một số backend instances lỗi hoặc connection/TLS | Instance được chọn, logs, health checks |
| Sau tùy biến Method thì GET đến sai backend | Đã mất Path predicate, route match quá rộng | Danh sách predicates mới và route order |
| Sau thêm header thì backend 404 | Đã mất RewritePath mặc định | So sánh path downstream trước và sau |
| Registry vừa thêm service nhưng Gateway chưa thấy | Cache / refresh | Service IDs hiện có và tập Routes runtime ở từng node |
| Route service nội bộ tự xuất hiện ở public | Allowlist/registry scope | `include-expression`, network boundaries, bảo mật route |
| Service ID uppercase gây mismatch | Case normalization | ID registry, generated Path, URI `lb://` |

### Dùng công cụ quan sát nào?

1. Kiểm tra **runtime dependency và logs khởi động**: Gateway Server WebFlux, discovery implementation và load balancer.
2. Kiểm tra **service IDs và instances thực sự** từ DiscoveryClient.
3. Kiểm tra **routes đã tạo**: ID, URI, Path predicate, RewritePath, order.
4. Gửi request qua Gateway và so sánh **path tại client** với **path tại backend**.
5. Quan sát route ID, status, latency, retry và instance đích qua logging/metrics/tracing khi được cấu hình.

Một số phiên bản Spring Cloud Gateway cung cấp Actuator Gateway endpoint cho routes/refresh. Chỉ expose management endpoints khi thật sự cần, bảo vệ bằng authentication/network và đối chiếu tài liệu đúng phiên bản. Trong môi trường nhiều Gateway instance, một refresh trên một node không nhất thiết đồng bộ mọi node.

## 12. Thực hành: kiểm chứng Path và RewritePath mặc định

**Điều kiện thử nghiệm:**

- Gateway Server WebFlux chạy cổng `8080`.
- DiscoveryClient kết nối tới registry đã đăng ký service ID `inventory-service`.
- Có instance inventory phục vụ `GET /products/42`, có thể echo/log raw path.
- LoadBalancer cho `lb://` hoạt động và discovery locator bật đúng version.

### Bước 1 — Kiểm tra Route runtime

Trước khi gửi HTTP, xác nhận Gateway đã sinh route tương ứng service ID `inventory-service`. Ghi lại URI dạng `lb://inventory-service` (hoặc cách biểu diễn của registry), predicate Path và RewritePath thực tế. **Đừng tự đoán route ID; ghi ID thật được sinh.**

### Bước 2 — Gửi request hợp lệ

~~~bash
curl -i "http://localhost:8080/inventory-service/products/42?sort=price"
~~~

Backend được kỳ vọng nhận path `/products/42` và query `sort=price`, nếu không có filter khác can thiệp. Response HTTP phụ thuộc endpoint backend.

### Bước 3 — Gửi URL không thuộc Path mặc định

~~~bash
curl -i "http://localhost:8080/products/42"
curl -i "http://localhost:8080/unknown-service/products/42"
~~~

Các request không match route `inventory-service` mặc định. Nếu không có route/handler khác, thường nhận 404. Điều này **không chứng minh DiscoveryClient đã lỗi**; nó cho thấy các URL không thuộc pattern được sinh cho service ấy.

### Bước 4 — Thử thiếu service instance

Trong lab, ngừng đăng ký các instance inventory hoặc tắt backend. Nếu route vẫn có nhưng load balancer không chọn được instance, Gateway thường trả lỗi dạng **503** hoặc mã khác tùy cấu hình, thay vì 404 do route không match. Phân biệt tình huống “không route”, “không instance” và “instance trả lỗi”.

### Bước 5 — Tùy biến filter rồi quan sát

Trong môi trường thử nghiệm, thay cấu hình locator filters bằng **chỉ một filter thêm header**, không giữ RewritePath. Làm mới routes đúng cơ chế, gọi lại URL mặc định và quan sát backend có thể nhận `/inventory-service/products/42`. Sau đó khôi phục RewritePath mặc định của phiên bản, xác minh backend nhận `/products/42`.

| Test | Path client | Path backend dự kiến | Ý nghĩa |
|---|---|---|---|
| Locator mặc định | `/inventory-service/products/42` | `/products/42` | Path + RewritePath hoạt động |
| Locator thiếu RewritePath | `/inventory-service/products/42` | Có thể vẫn mang service ID | Mặc định đã bị thay thế |
| Không đúng Path | `/products/42` | Không forward theo route này | Predicate không match |
| Có route nhưng thiếu instance | `/inventory-service/products/42` | Không có instance nhận | Lỗi load balancing, không phải Path |

### Bước 6 — Ghi biên bản kiểm thử

Lưu **service ID, route ID, URI, predicate/filter đã nạp, path backend nhận, instance được chọn và mã phản hồi**. Không ghi token, session cookie hoặc query chứa dữ liệu cá nhân nguyên văn. Với API nhiều môi trường, thử cả service ID viết hoa, URI có query, backend 404 và thời điểm service scale up/down.

## 13. Nên dùng tuyến tự sinh hay route thủ công?

| Tiêu chí | Route tự sinh | Route thủ công |
|---|---|---|
| Nhiều dịch vụ có URL quy ước thống nhất | Ít khai báo lặp | Cần thêm route/tệp cấu hình |
| Dịch vụ có thể tự xuất hiện/biến mất | Phù hợp khi discovery/cache được quản lý tốt | Thường cần quy trình cập nhật route |
| URL public phải ổn định dù đổi tên service nội bộ | Cần tùy biến cẩn thận | Dễ tách URL bên ngoài khỏi service ID |
| Chính sách bảo mật khác nhau theo API | Cần allowlist/policy chi tiết | Dễ review từng route nhưng vẫn cần security |
| Lo ngại expose service nội bộ | Phải kiểm soát registry scope và include-expression | Có thể chỉ khai báo API được phê duyệt |
| Cần cân bằng tải giữa instances | Dùng `lb://` | Cũng dùng `lb://` được, không cần auto route |

**Khuyến nghị thực hành:** dùng route tự sinh khi registry/namespace đã được kiểm soát, mọi service được phép public và tiền tố URL theo service ID phù hợp. Dùng route thủ công hoặc nguồn cấu hình được phê duyệt khi API có hợp đồng public và yêu cầu phân quyền khác nhau. Trong cả hai trường hợp, `lb://` vẫn có thể tận dụng load balancing.

## 14. Checklist trước khi triển khai

- [ ] Tôi đã xác nhận phiên bản Gateway, Spring Cloud và đúng web stack WebFlux/MVC.
- [ ] DiscoveryClient đã hoạt động và trả service IDs mong muốn.
- [ ] Có LoadBalancer hoặc cơ chế tương ứng xử lý URI `lb://`.
- [ ] Tôi hiểu predicate Path mặc định thường match `/{serviceId}/**`.
- [ ] Tôi hiểu filter RewritePath mặc định loại tiền tố `/{serviceId}` trước khi forward.
- [ ] Tôi đã xác nhận query/header/body không bị rewrite path thay đổi ngoài ý định.
- [ ] Khi tùy biến danh sách predicates, tôi **giữ lại Path** nếu cần hành vi mặc định.
- [ ] Khi tùy biến danh sách filters, tôi **giữ lại RewritePath** nếu cần hành vi mặc định.
- [ ] Tôi đã kiểm tra biểu thức theo serviceId và escaping regex replacement theo phiên bản.
- [ ] Tôi đã xử lý case của service ID và đối chiếu Path/URI `lb://` thực tế.
- [ ] Tôi không expose service nội bộ tự động qua registry public.
- [ ] Tôi đã thiết kế xác thực, phân quyền, rate limiting, retry/circuit breaker và TLS riêng.
- [ ] Tôi kiểm thử được ba lỗi riêng: không match route, path downstream sai, không chọn được instance.
- [ ] Tôi đã kiểm tra route refresh/cache và trạng thái các node Gateway khi registry thay đổi.
- [ ] Tôi chỉ expose management endpoints khi có quyền truy cập phù hợp.

## Tài liệu tham khảo chính thức

- [Spring Cloud Gateway Reference](https://docs.spring.io/spring-cloud-gateway/reference/) — mục **DiscoveryClient Route Definition Locator**, predicate/filter mặc định và cấu hình tùy biến theo từng phiên bản.
- [Spring Cloud Gateway Project](https://spring.io/projects/spring-cloud-gateway) — thông tin dự án và release train.
- [Spring Cloud Commons — Common Abstractions](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html) — DiscoveryClient và Spring Cloud LoadBalancer.
- [Spring Cloud Netflix](https://docs.spring.io/spring-cloud-netflix/reference/) — ví dụ registry/discovery với Eureka khi dự án dùng tích hợp này.
- [Spring Boot Actuator](https://docs.spring.io/spring-boot/reference/actuator/) — nguyên tắc quản trị và bảo mật endpoints.

**Ghi nhớ:** Ở route tự sinh, **Path mặc định dùng tiền tố service ID** để chọn request và **RewritePath mặc định loại tiền tố ấy** trước khi gọi downstream. **Thay danh sách predicates/filters của discovery locator có thể làm mất hành vi mặc định**, vì vậy phải chủ động khai báo lại những thành phần cần thiết, kiểm thử path thực nhận và kiểm soát nghiêm dịch vụ nào được phép truy cập qua Gateway.
