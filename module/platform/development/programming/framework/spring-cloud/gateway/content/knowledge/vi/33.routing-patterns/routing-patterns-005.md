# Backend for Frontend theo từng loại ứng dụng

## 1. Khi một API chung không còn phù hợp với mọi giao diện

Giả sử một hệ thống bán hàng có ba giao diện: **website khách hàng**, **ứng dụng di động** và **trang quản trị nội bộ**. Cả ba cùng cần dữ liệu từ các microservices `catalog`, `orders`, `customers` và `inventory`, nhưng cách chúng sử dụng dữ liệu rất khác nhau:

- Website cần giỏ hàng, đặt hàng, trạng thái đăng nhập qua trình duyệt và thông tin hiển thị theo trang.
- Ứng dụng di động cần payload nhẹ, ít lượt gọi mạng, phân trang phù hợp màn hình nhỏ và xử lý mạng yếu.
- Trang quản trị cần tra cứu nhiều trường, lịch sử thay đổi, thao tác nhạy cảm và quyền truy cập nghiêm ngặt.

Nếu mọi client phải gọi một backend tổng quát, API sẽ tích lũy các tham số kiểu `?device=mobile&admin=true&fields=...`, response chứa quá nhiều dữ liệu và từng thay đổi giao diện có thể làm ảnh hưởng khách hàng khác. **Backend for Frontend (BFF)** giải quyết vấn đề này bằng cách tạo **lớp backend chuyên biệt cho mỗi loại giao diện hoặc trải nghiệm người dùng**.

Trong module **SPRING_CLOUD_GATEWAY**, chúng ta đã có công cụ xây API Gateway qua route predicates, filter chain, path/header rewriting, service discovery và các chính sách như xác thực, rate limiting, circuit breaker, retry, TLS, observability. BFF là một **mẫu kiến trúc triển khai phía sau hoặc kết hợp với Gateway**, không phải tên một `GatewayFilterFactory` hay một route predicate có sẵn.

Bài **“Backend for Frontend theo từng loại ứng dụng”**, thuộc chương **Mẫu định tuyến**, hướng dẫn quyết định khi nào cần BFF, cách dùng Spring Cloud Gateway Server để phân luồng web/mobile/admin, cách thiết kế hợp đồng dữ liệu và bảo mật riêng, cùng lab/test chứng minh không định tuyến nhầm.

Sau bài, bạn có thể:

1. Phân biệt **API Gateway dùng chung**, **BFF chuyên biệt** và **microservice nghiệp vụ**.
2. Thiết kế route qua hostname hoặc path mà không tin header tự khai kiểu `X-App-Type` để cấp quyền.
3. Cấu hình Gateway Server WebFlux 4.x/5.x để chuyển web, mobile, admin đến BFF tương ứng.
4. Giải thích OAuth BFF cho browser: confidential client, cookie session, token phía server, CSRF.
5. Phân biệt mobile public OAuth client + PKCE với browser BFF dùng session.
6. Xây một endpoint tổng hợp dữ liệu bằng WebFlux `WebClient` và kiểm soát timeout/fan-out.
7. Kiểm thử cách chọn BFF, path transformations, authentication, authorization, rate limiting và observability.
8. Đánh giá trade-off về số service, coupling, độ trễ và quyền sở hữu giữa các frontend teams.

> **Phạm vi kỹ thuật:** ví dụ Gateway dùng **Spring Cloud Gateway Server WebFlux**. Server Web MVC có routes/filters tương ứng qua WebMvc.fn nhưng khác packages/filters và namespace cấu hình. Phần OAuth dành cho browser BFF cần được thiết kế độc lập với định tuyến; không mặc định một route Gateway là một OAuth confidential client hoàn chỉnh.

## 2. BFF là gì, khác API Gateway ở đâu?

**API Gateway** thường là điểm vào chung cho chức năng xuyên suốt: chọn upstream theo `Host`/`Path`/`Method`, authn/authz ở biên, headers, TLS, rate limiting, routing, observability. **BFF** phục vụ nhu cầu của **một frontend hoặc nhóm frontend có contract tương tự**: gom dữ liệu, thay đổi DTO, phân trang, caching theo màn hình, xử lý phiên đăng nhập phù hợp.

| Vấn đề | API Gateway dùng chung | BFF theo giao diện | Microservice nghiệp vụ |
| --- | --- | --- | --- |
| Phạm vi | Nhiều clients và nhiều routes | Một trải nghiệm frontend/nhóm tương đồng | Một bounded context/domain |
| Định tuyến | Host/Path/Method predicates | Endpoint hợp đồng giao diện | Business API/resource routing |
| Biến đổi request/response | Filter theo route, header/path/status | DTO composition, shaping, defaults | Business validation và domain logic |
| Xác thực | Chính sách ở biên hoặc token validation | Browser session/OAuth hoặc bearer phù hợp client | Kiểm tra token/workload identity |
| Phân quyền | Chặn truy cập thô tới route | Scope/role theo use case | Resource ownership/tenant checks |
| Nâng cấp | Gateway routing/infra team | Frontend team có thể triển khai độc lập | Domain team |
| Quan sát | Route ID, downstream latency, failures | Screen/use-case latency, fan-out count | Domain latency, DB/business errors |
| Không nên chứa | Quá nhiều UI-specific business DTOs | Business rules lõi/transaction xuyên services | Cấu trúc layout của từng màn hình |

### 2.1. BFF không nhất thiết là một microservice cho mỗi màn hình

Mẫu kiến trúc không yêu cầu tạo một process cho **mỗi view** hay **mỗi thiết bị vật lý**. Nên nhóm theo **mức độ khác biệt của contract và nhịp phát triển**:

- Web desktop và tablet dùng chung cách đăng nhập/payload có thể dùng cùng `web-bff`.
- Ứng dụng iOS và Android cùng UI/contract có thể dùng một `mobile-bff`.
- Trang quản trị có dữ liệu và quyền đặc biệt thường phù hợp với `admin-bff` riêng.

Nếu chỉ có hai endpoints đơn giản và mọi client dùng cùng response, thêm ba services có thể chỉ tăng chi phí vận hành. **Độ khác biệt thực tế** mới quyết định số BFF.

### 2.2. BFF không thay microservices nghiệp vụ

Ví dụ `mobile-bff` có thể tổng hợp tên sản phẩm và trạng thái giao hàng, nhưng **không nên tự quyết định quy tắc tính thuế, chuyển khoản, giữ hàng hoặc phân quyền tài khoản**. Những quy tắc đó thuộc domain services. BFF cần ít state nghiệp vụ và tránh tạo thêm một nguồn dữ liệu không đồng bộ.

### 2.3. API Gateway và BFF có thể là một hoặc hai lớp

Có hai triển khai thường gặp:

**Phương án A — Gateway chung đứng trước nhiều BFF services:**

~~~mermaid
flowchart TD
    W["Web browser"] --> E["Ingress / Edge TLS"]
    M["Mobile app"] --> E
    A["Admin UI"] --> E
    E --> G["Spring Cloud Gateway Server"]
    G -->|"Host/Path web"| BW["web-bff"]
    G -->|"Host/Path mobile"| BM["mobile-bff"]
    G -->|"Host/Path admin"| BA["admin-bff"]
    BW --> S["Catalog / Orders / Customer services"]
    BM --> S
    BA --> S
~~~

**Phương án B — Mỗi BFF cũng dùng Gateway Server bên trong:** một public edge chọn BFF, sau đó `web-bff` dùng chính Spring Cloud Gateway `TokenRelay`, path filters và HTTP routing tới resource servers, bên cạnh controllers tạo DTO. Cách này hợp lý nếu một BFF chủ yếu proxy các APIs và cần OAuth session.

Không có nghĩa **mọi** BFF phải cài Gateway Server starter. Nếu BFF chủ yếu tổng hợp nhiều resource APIs, Spring WebFlux `@RestController` và `WebClient` có thể phù hợp hơn, còn Gateway chung xử lý edge routing.

## 3. Dữ liệu và security theo từng loại ứng dụng

| Đặc điểm | Browser/Web BFF | Native Mobile BFF | Admin BFF |
| --- | --- | --- | --- |
| Client | JavaScript trong browser | iOS/Android/native | Browser nội bộ hoặc admin client |
| Contract | Cart, checkout, profile page | Home/feed nhẹ, pagination nhỏ, offline sync | Audit, reports, bulk operations |
| OAuth phổ biến | BFF confidential client, session cookie; token nằm server | Public OAuth client + Authorization Code/PKCE, bearer access token | SSO/MFA, role/scope mạnh, session hoặc token phù hợp |
| CSRF | Bắt buộc xem xét vì cookie tự gửi | Không mặc định cùng cơ chế nếu chỉ bearer header | Cần CSRF khi dùng cookie session |
| CORS | Ưu tiên same-origin web UI + BFF | Native app không bị browser CORS ràng buộc như JS | Ưu tiên same-origin/admin hostname rõ ràng |
| Response payload | Phong phú theo trang | Gọn, ít lượt gọi, hỗ trợ mạng yếu | Chi tiết, lọc/pagination/audit fields |
| Quota | Theo user/session + route | Theo verified principal, device risk, plan | Theo operator/tenant và loại thao tác |
| Cache | Cart/private no-store, catalog có TTL | Cache featured/read-only hợp lệ, ETag | Rất hạn chế cho dữ liệu nhạy cảm |
| Nguy cơ chính | XSS, CSRF, session fixation, token/session theft | Token theft, replay, app version drift | Privilege escalation, data export, insider risk |

**Không dùng `X-Client-Type: mobile` làm nguồn quyền hạn**. Header do client tự đặt có thể hỗ trợ logging hoặc định dạng nếu được kiểm tra, nhưng không chứng minh thiết bị/người dùng và không được dùng để bỏ qua MFA/authorization. Tương tự, `User-Agent` có thể giả, không phù hợp làm security boundary.

### 3.1. Cùng một domain API, response khác vì use case

Ví dụ orders service trả domain DTO:

~~~json
{
  "orderId": "O-1042",
  "customerId": "C-9",
  "items": [{"sku": "A1", "price": 120000, "qty": 2}],
  "discountBreakdown": {"campaign": "WELCOME"},
  "shipping": {"state": "IN_TRANSIT", "trackingNumber": "TR-99"},
  "internalWarehouseCode": "WH-3",
  "audit": {"lastModifier": "ops-12"}
}
~~~

Web BFF có thể trả thông tin phù hợp trang chi tiết (items, trạng thái giao hàng); mobile BFF có thể chỉ trả `orderId`, `displayTotal`, `shippingState`; admin BFF có thể có `audit` **sau khi kiểm tra quyền**. Đây không phải việc Gateway tự động chọn fields theo User-Agent: **mỗi BFF có contract và DTO do backend code quản lý**.

Không trả `internalWarehouseCode` hoặc private audit metadata cho mobile chỉ vì “frontend không hiển thị”; **dữ liệu không được phép phải bị loại khỏi response từ server**.

## 4. Thiết kế lớp định tuyến BFF: Host hay Path?

Hai cách được dùng nhiều:

| Phương án | Ví dụ public URL | Điểm mạnh | Hạn chế |
| --- | --- | --- | --- |
| **Host-based** | `https://web.example.test/bff/home`, `https://mobile.api.example.test/v1/home` | Tách origin/cookies/TLS theo client, BFF quản lý login callback | Cần DNS/TLS/host routing rõ ràng |
| **Path-based** | `https://api.example.test/web/home`, `.../mobile/home` | Lab/cổng API dùng chung đơn giản | Rewrite path, login redirect/cookie path, CORS và policy phức tạp hơn |
| Kết hợp Host+Path | `admin.api.example.test/admin/audit` | Chỉ một bộ paths trên host dự kiến | Không tự là auth; cần RBAC/network boundary |

### 4.1. Vì sao ưu tiên hostname khi browser BFF giữ session?

Browser BFF sử dụng OAuth2 login qua redirect, callback `/login/oauth2/code/{registrationId}`, session cookie và có thể phục vụ web assets. Nếu Gateway lột tiền tố `/web` bằng `StripPrefix=1`, BFF có thể tạo redirect ra `/login` thay vì `/web/login`, Cookie Path bị lệch và callback không vào BFF.

Tách hostname dễ giữ **public origin** nhất quán cho UI và BFF: ví dụ trang web và BFF cùng ở `https://web.example.test`. Khi muốn dùng `/web/**` vẫn được, nhưng cần cấu hình forwarded prefix, redirect URI, cookies, CORS và tests trên đường thực tế — không chỉ thêm `StripPrefix` rồi coi xong.

### 4.2. Host predicate không phải chứng thực client

Một lệnh HTTP có thể gửi:

~~~bash
curl -i "http://127.0.0.1:8080/bff/home" \
  -H "Host: web.example.test"
~~~

Gateway có thể chọn route web từ Host header. Điều đó **chỉ chứng minh routing**, không chứng minh caller là trình duyệt hợp lệ. HTTPS SNI/certificate, edge allowlist, Spring Security OAuth2 login, session protection và backend authz mới tạo trust boundary.

### 4.3. Không route admin chỉ bằng header giả

**Sai:**

~~~yaml
predicates:
  - Path=/**
  - Header=X-Admin,^true$
~~~

Client có thể gửi `X-Admin: true`. **Đúng hướng:** route admin theo Host/Path rõ ràng **và** áp SSO/MFA/role+scope, network isolation và audit:

~~~yaml
predicates:
  - Host=admin.api.example.test
  - Path=/admin/**
~~~

Ngay cả hai predicate này vẫn là route selection, **không thay authorization**.

## 5. Cấu hình Gateway Server WebFlux 5.x: một edge, ba BFF

Trong kiến trúc host-based production-like, giả sử:

| Host public được ingress cho phép | Service nội bộ | Chức năng |
| --- | --- | --- |
| `web.example.test` | `http://web-bff:9081` | Web UI, OAuth login, session, REST BFF |
| `mobile.api.example.test` | `http://mobile-bff:9082` | Mobile API `/v1/**` |
| `admin.api.example.test` | `http://admin-bff:9083` | Admin API `/admin/**` |

Public DNS/TLS do Ingress quản lý. Các service names là **tên minh họa**, chỉ resolve được trong mạng/deployment tương ứng. Lab trên localhost sẽ thay bằng `127.0.0.1` với ba port. Gateway không tự cấp chứng chỉ TLS cho ba hosts chỉ vì có `Host` predicate.

### 5.1. application.yml cho Gateway Server WebFlux 5.x

~~~yaml
spring:
  application:
    name: edge-bff-gateway
  cloud:
    gateway:
      server:
        webflux:
          default-filters:
            - RemoveRequestHeader=X-User-Id
            - RemoveRequestHeader=X-Role
            - RemoveRequestHeader=X-Tenant-Id
          routes:
            - id: web-bff-route
              order: -30
              uri: http://web-bff:9081
              predicates:
                - Host=web.example.test
              filters:
                - AddResponseHeader=X-Lab-Bff-Route,web-bff-route

            - id: mobile-bff-route
              order: -20
              uri: http://mobile-bff:9082
              predicates:
                - Host=mobile.api.example.test
                - Path=/v1/**
              filters:
                - AddResponseHeader=X-Lab-Bff-Route,mobile-bff-route

            - id: admin-bff-route
              order: -10
              uri: http://admin-bff:9083
              predicates:
                - Host=admin.api.example.test
                - Path=/admin/**
              filters:
                - AddResponseHeader=X-Lab-Bff-Route,admin-bff-route
~~~

**Giải thích từng tuyến:**

1. `web-bff-route` chỉ match `web.example.test`. Nó **không đặt Path predicate** để các URL `/oauth2/authorization/...`, `/login/oauth2/code/...`, static assets và API `/bff/**` có thể đi đến web BFF. Các URL thật sự được phép/không được phép vẫn do **web BFF SecurityWebFilterChain** kiểm soát.
2. `mobile-bff-route` yêu cầu **cả Host và Path** đúng (AND). BFF chỉ phục vụ hợp đồng API mobile `/v1/**`.
3. `admin-bff-route` yêu cầu Host admin và `/admin/**`. Điều này **không đủ bảo vệ** admin: backend phải kiểm tra SSO/role/scopes/MFA policy.
4. Các BFF giữ nguyên path trong phương án này, không cần `StripPrefix`. Gateway route tới đúng service và giữ hợp đồng URL.
5. `RemoveRequestHeader` loại bỏ một số claim headers do client tự khai **trước khi gọi BFF**, tránh để backend coi chúng là identity.
6. `X-Lab-Bff-Route` là **marker test**, không được backend coi là chứng cứ bảo mật. Trên production, thường bỏ marker hoặc không công khai route ID nếu không có nhu cầu.

**Một lưu ý quan trọng:** `Host=web.example.test` được kiểm tra theo HTTP Host; **không xác minh SNI, nguồn kết nối, hostname authorization hay OAuth login**. Ingress phải từ chối Host không hợp lệ và bảo đảm TLS, backend services chỉ chấp nhận traffic qua đường được phê duyệt.

### 5.2. Method-specific routes và CORS preflight

Bạn có thể thêm `Method=GET,POST` cho một tuyến API nếu hợp đồng chỉ cho phép hai phương thức. Nhưng browser CORS preflight gửi **OPTIONS**, có thể không match route đó; cần cấu hình CORS ở lớp đúng và kiểm thử cả OPTIONS lẫn actual request. Không biến `Method` predicate thành giải pháp authorization.

Ví dụ:

~~~yaml
predicates:
  - Host=mobile.api.example.test
  - Path=/v1/catalog/**
  - Method=GET,HEAD
~~~

Với tuyến chỉ-read, phải có test POST không match và xác nhận không có một fallback rộng nhận request POST ngoài dự kiến.

### 5.3. Tránh một fallback Host/Path quá rộng

Một cấu hình:

~~~yaml
- id: catch-all
  uri: http://web-bff:9081
  predicates:
    - Path=/**
~~~

có thể nhận requests tới hostname admin/mobile không được route chính chọn, làm lộ tài nguyên sai service hoặc gây nhầm debugging. Nếu cần fallback, hãy định nghĩa **mục đích cụ thể**, thứ tự, host allowlist và response chính sách rõ ràng; không tự chuyển request đến web BFF khi Host lạ.

### 5.4. Route order và tách quyền

Spring Cloud Gateway xét routes theo `order` runtime; route có order nhỏ hơn thường ưu tiên khi nhiều tuyến match. Trong bảng trên, các hostname tách biệt nên order không dùng để “cấp quyền”; chỉ làm rõ route priority. Nếu sau này thêm tuyến chung:

~~~yaml
- id: shared-public
  order: 100
  predicates:
    - Host=web.example.test,mobile.api.example.test
    - Path=/public/**
~~~

phải kiểm tra route nào được chọn trước và chính sách bảo mật của từng BFF. Không dùng order như thành trì duy nhất ngăn truy cập admin: BFF và resource services phải xác minh quyền.

## 6. Namespace và starter cho WebFlux Gateway 4.x so với 5.x

Spring Cloud Gateway thay tên module/nhóm configuration qua các release trains. Bài này không ghép các prefixes của hai dòng vào cùng một `application.yml`.

| Mục đích | WebFlux Gateway 4.2/4.3 | WebFlux Gateway 5.x |
| --- | --- | --- |
| Cấu hình route | `spring.cloud.gateway.routes` | `spring.cloud.gateway.server.webflux.routes` |
| Default filters | `spring.cloud.gateway.default-filters` | `spring.cloud.gateway.server.webflux.default-filters` |
| Starter điển hình | `spring-cloud-starter-gateway` ở các bản cũ | `spring-cloud-starter-gateway-server-webflux` |
| Web stack | Spring WebFlux/Reactor Netty | Spring WebFlux/Reactor Netty |
| Kiểm chứng | Effective BOM + runtime route inventory | Effective BOM + runtime route inventory |

Ví dụ rút gọn theo **WebFlux Gateway 4.2/4.3**:

~~~yaml
spring:
  cloud:
    gateway:
      default-filters:
        - RemoveRequestHeader=X-User-Id
        - RemoveRequestHeader=X-Role
        - RemoveRequestHeader=X-Tenant-Id
      routes:
        - id: web-bff-route
          uri: http://web-bff:9081
          predicates:
            - Host=web.example.test

        - id: mobile-bff-route
          uri: http://mobile-bff:9082
          predicates:
            - Host=mobile.api.example.test
            - Path=/v1/**

        - id: admin-bff-route
          uri: http://admin-bff:9083
          predicates:
            - Host=admin.api.example.test
            - Path=/admin/**
~~~

Chọn **Spring Cloud BOM tương thích với Spring Boot** đang dùng. Không coi tên starter mới/cũ là các dependency có thể thêm đồng thời cho chắc. Web MVC có namespace `spring.cloud.gateway.server.webmvc.routes` ở dòng mới và sử dụng API/WebMvc.fn khác, nên đừng copy Java `GlobalFilter` hoặc `ServerWebExchange` của WebFlux sang MVC.

**Kiểm tra sau khi start:** route IDs, URIs, predicates, default-filters đã materialize thật. Một YAML với sai prefix có thể bị Spring bỏ qua và ứng dụng vẫn startup nhưng **không có BFF route nào**.

## 7. Bài lab đơn giản hơn: phân luồng bằng tiền tố Path

Để test ngay trên localhost, dùng một Gateway ở port 8080 và ba BFF stubs ở các port 9081/9082/9083. Ta không mô phỏng OAuth login trong lab này; chỉ chứng minh **route selection và path rewrite**.

| Request public tới Gateway | Downstream URI | BFF nào? |
| --- | --- | --- |
| `GET /web/whoami` | `http://127.0.0.1:9081/whoami` | web |
| `GET /mobile/whoami` | `http://127.0.0.1:9082/whoami` | mobile |
| `GET /admin/whoami` | `http://127.0.0.1:9083/whoami` | admin |
| `GET /unknown/whoami` | Không có route trong fixture này | none |

### 7.1. application-bff-lab.yml trên Gateway 5.x

~~~yaml
server:
  port: 8080

spring:
  application:
    name: edge-bff-lab
  cloud:
    gateway:
      server:
        webflux:
          default-filters:
            - RemoveRequestHeader=X-User-Id
            - RemoveRequestHeader=X-Role
          routes:
            - id: web-bff-lab
              uri: http://127.0.0.1:9081
              predicates:
                - Path=/web/**
              filters:
                - StripPrefix=1
                - AddRequestHeader=X-Lab-Channel,web
                - AddResponseHeader=X-Lab-Bff-Route,web-bff-lab

            - id: mobile-bff-lab
              uri: http://127.0.0.1:9082
              predicates:
                - Path=/mobile/**
              filters:
                - StripPrefix=1
                - AddRequestHeader=X-Lab-Channel,mobile
                - AddResponseHeader=X-Lab-Bff-Route,mobile-bff-lab

            - id: admin-bff-lab
              uri: http://127.0.0.1:9083
              predicates:
                - Path=/admin/**
              filters:
                - StripPrefix=1
                - AddRequestHeader=X-Lab-Channel,admin
                - AddResponseHeader=X-Lab-Bff-Route,admin-bff-lab
~~~

Mở profile khi chạy:

~~~bash
./mvnw spring-boot:run \
  -Dspring-boot.run.profiles=bff-lab
~~~

Hoặc dùng `SPRING_PROFILES_ACTIVE=bff-lab` theo shell/platform đang dùng. Test profile nên **thay thế routes của main profile**, tránh có thêm host-based routes khác khiến kết quả sai.

### 7.2. Thứ tự predicate/filter

Với `Path=/web/**`, request `/web/whoami` chọn route web trước; rồi `StripPrefix=1` mới đổi downstream path thành `/whoami`. Thay đổi path ở filter **không làm Gateway quay lại đánh giá tất cả Path predicates** theo path mới.

`AddRequestHeader=X-Lab-Channel,web` chỉ thêm marker kỹ thuật cho lab. Nó **không phải verified identity**: client có thể gửi header cùng tên, gây đa giá trị. Trong production, nếu BFF muốn có channel đáng tin, xóa inbound marker rồi `SetRequestHeader` từ route metadata tại trusted Gateway và vẫn dùng authenticated principal cho quyền.

### 7.3. Vì sao không dùng Path lab trực tiếp cho OAuth web BFF?

Ví dụ `/web/login/oauth2/code/browser` sẽ bị StripPrefix thành `/login/oauth2/code/browser`, đúng callback **ở phía BFF**; nhưng OAuth provider redirect URI phải trỏ đúng **public URL** `https://api.example.test/web/login/oauth2/code/browser`. Cần cấu hình forwarded prefix/host/scheme đúng, cookie path/same-site đúng và không để OAuth security redirects thiếu `/web`.

Nếu chưa sẵn sàng xử lý các điểm đó, dùng **host-based routing** cho web BFF production. Không copy lab path config và tuyên bố browser OAuth flow đã được bảo mật.

## 8. Browser BFF: OAuth confidential client và cookie session

Một use case quan trọng của mẫu BFF là **giảm việc lộ OAuth access/refresh token cho JavaScript chạy trong browser**. Theo **RFC 10017 (OAuth 2.0 for Browser-Based Applications, tháng 8/2026)**, BFF cho browser có ba nhiệm vụ:

1. Đóng vai một **confidential OAuth client**: khởi tạo authorization code flow và nhận token từ authorization server trên server side.
2. Giữ access/refresh tokens trong **server-side session hoặc kho bảo vệ thích hợp**, browser chỉ nhận session cookie an toàn.
3. Nhận các resource requests từ browser rồi bổ sung **access token thích hợp** trước khi forward đến resource server.

### 8.1. Trình tự browser BFF

~~~mermaid
sequenceDiagram
    participant Browser
    participant BFF as Web BFF
    participant IdP as OAuth/IdP
    participant API as Orders Resource Server
    Browser->>BFF: GET /bff/orders/42 (chưa login)
    BFF-->>Browser: 302 tới IdP /authorization
    Browser->>IdP: Authorization Code flow
    IdP-->>Browser: 302 về BFF callback + code
    Browser->>BFF: GET /login/oauth2/code/browser
    BFF->>IdP: Server-to-server code + client authentication
    IdP-->>BFF: Access token / refresh token (nếu cấp)
    BFF-->>Browser: Session cookie Secure; HttpOnly; SameSite phù hợp
    Browser->>BFF: GET /bff/orders/42 + session cookie
    BFF->>API: GET /orders/42 + token phù hợp resource server
    API-->>BFF: Order data (đã authorise resource)
    BFF-->>Browser: DTO JSON cho web
~~~

**Không đặt access token vào localStorage hoặc response JSON cho browser chỉ để BFF dễ lập trình.** Nếu browser vẫn giữ token và gọi microservices trực tiếp, đó không còn là OAuth BFF giữ token như trên.

### 8.2. Token không lộ khỏi browser không đồng nghĩa không có rủi ro XSS

Với BFF, JavaScript độc hại có thể vẫn **gửi requests dưới session của người dùng** dù không đọc được token. Vì vậy cần cả:

- Chống XSS: CSP, output encoding, tránh unsafe dynamic HTML, dependency hygiene.
- Chống CSRF: token/origin validation cho state-changing requests.
- Session cookie có `Secure`, `HttpOnly` và `SameSite` phù hợp OAuth redirect/cross-site topology.
- Session rotation sau login, logout/invalidation, TTL/idle timeout, renewal và session storage phù hợp multi-replica.
- HTTPS/HSTS, không expose BFF application listener trực tiếp.
- Authorization của backend theo token/claims và object ownership, không chỉ user đã login.

RFC 10017 nhấn mạnh BFF cần **CSRF defense** vì browser tự đính kèm cookie trên những requests nhất định. CORS allowlist hay SameSite cookie có ích nhưng không phải lời giải duy nhất cho mọi same-site cross-origin subdomain.

### 8.3. Cơ chế cookie session phù hợp các loại trang

| Thuộc tính | Khuyến nghị cần cân nhắc | Lưu ý |
| --- | --- | --- |
| `Secure` | Bắt buộc trên HTTPS public | Không phát cookie auth trên HTTP Internet |
| `HttpOnly` | Có cho session cookie | JS không đọc session ID trực tiếp |
| `SameSite=Lax/Strict` | Chọn theo OAuth redirects và domain topology | Strict có thể ảnh hưởng callback/login từ IdP |
| `Path` | Thường `/` khi web UI và BFF cùng host | Nếu path-based, kiểm tra cookie Path sau proxy |
| `Domain` | Ưu tiên host-only cookie | Không mở toàn `.example.test` khi không cần |
| Expiry | TTL, idle timeout, rotation | Không để session tồn tại vô hạn |
| Session store | Multi-replica store an toàn nếu cần | In-memory chỉ phù hợp một process/lab |

Đối với OAuth authorization code callback, cookie state/session có thể cần được browser gửi trong một top-level cross-site redirect. Test trên **trình duyệt thật** (SameSite rules), không chỉ cURL; đừng chọn `SameSite=Strict` máy móc làm hỏng đăng nhập rồi tắt mọi cookie security.

## 9. Cấu hình Spring Cloud Gateway làm một browser BFF

Khi web BFF chủ yếu **proxy các tài nguyên đã có** và bổ sung session OAuth, nó có thể sử dụng **Gateway Server WebFlux riêng**. Trong topology host-based, public edge đã chọn `web-bff-route`; ứng dụng `web-bff` tiếp nhận nguyên paths `/oauth2/**`, `/login/**` và `/bff/**`.

### 9.1. Dependencies

Ví dụ Maven trên Spring Boot/Spring Cloud BOM tương thích:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-gateway-server-webflux</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-oauth2-client</artifactId>
    </dependency>
</dependencies>
~~~

Không gắn versions Spring Cloud riêng khi BOM đã quản lý. Với Gateway WebFlux 4.2, thay starter/prefix routes theo dòng đang dùng; không cài cả Server Web MVC lẫn WebFlux để “bật BFF đầy đủ”.

### 9.2. application.yml minh họa cho web-bff (Gateway 5.x)

~~~yaml
server:
  port: 9081

spring:
  application:
    name: web-bff
  security:
    oauth2:
      client:
        registration:
          browser:
            provider: corporate
            client-id: web-bff-client
            client-secret: ${WEB_BFF_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: openid,profile
        provider:
          corporate:
            issuer-uri: https://idp.example.test/realms/platform
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: web-orders-api
              uri: http://orders-service:9091
              predicates:
                - Path=/bff/orders/**
              filters:
                - StripPrefix=1
                - TokenRelay=
                - AddResponseHeader=X-Lab-Bff-Route,web-orders-api
~~~

Đây là **cấu hình minh họa**, cần thay IdP/issuer và secret bằng giá trị thật được quản lý an toàn. TokenRelay factory chỉ được tạo nếu OAuth2 Client auto-configuration có client registration phù hợp; khi thiếu `spring.security.oauth2.client.*`, bộ lọc có thể không tồn tại.

`StripPrefix=1` đổi `/bff/orders/42` thành `/orders/42` cho orders resource server. `TokenRelay=` (không chỉ định `clientRegistrationId`) dùng access token của người dùng đã login theo tài liệu Gateway, rồi đặt vào downstream Authorization header. **Đó là token relay theo principal**, không tự trao đổi audience; backend phải kiểm tra token có phù hợp resource server hay không.

**Khi backend đòi token audience riêng**, phải triển khai token exchange/authorized client thích hợp thay vì forward một token chỉ dành cho BFF. Không gửi refresh token xuống backend và không log bearer access token.

### 9.3. SecurityWebFilterChain cho web BFF

~~~java
package demo.webbff;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration(proxyBeanMethods = false)
public class WebBffSecurityConfig {

    @Bean
    SecurityWebFilterChain webBffSecurity(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/oauth2/**", "/login/**")
                        .permitAll()
                        .pathMatchers(HttpMethod.GET, "/", "/index.html",
                                "/assets/**", "/favicon.ico")
                        .permitAll()
                        .pathMatchers("/bff/**").authenticated()
                        .anyExchange().denyAll())
                .oauth2Login(Customizer.withDefaults())
                .csrf(Customizer.withDefaults())
                .build();
    }
}
~~~

Đoạn config yêu cầu đăng nhập cho `/bff/**` và giữ CSRF protection của Spring Security. Nếu BFF phục vụ web static files hoặc health endpoints, **thêm đúng allowlist URL cần thiết**; không đổi thành `anyExchange().permitAll()` để sửa lỗi login/CSRF.

### 9.4. Request từ trình duyệt

Với UI và BFF cùng origin `https://web.example.test`:

~~~javascript
const response = await fetch("/bff/orders/42", {
  method: "GET",
  credentials: "same-origin"
});

if (!response.ok) {
  throw new Error("Request failed: " + response.status);
}

const order = await response.json();
console.log(order);
~~~

**Không thêm Authorization Bearer do browser lưu trữ** khi sử dụng BFF confidential-client pattern; browser gửi cookie, BFF xử lý session và downstream token.

Với `POST /bff/orders`, browser cần gửi CSRF token theo cấu hình Spring Security; `credentials: "same-origin"` **không tự thay CSRF defense**. API có thể nhận `X-XSRF-TOKEN` từ cookie riêng do server cấp theo phương án phù hợp, nhưng phải test cookie và token trên actual frontend. Không tắt CSRF toàn cục chỉ vì POST bị 403.

### 9.5. Session/token storage khi web BFF scale ngang

Gateway `TokenRelay` documentation cho biết implementation mặc định của `ReactiveOAuth2AuthorizedClientService` có thể dùng **in-memory data store**. Nếu deploy nhiều replicas:

- Cần chiến lược session và authorized client/token storage chia sẻ an toàn hoặc sticky session với rủi ro đã đánh giá.
- Mã hóa dữ liệu nhạy cảm khi lưu, giới hạn TTL/idle expiration, token rotation, revoke/logout.
- Chống session fixation và kiểm tra CSRF state sau OAuth redirects.
- Quan sát error khi một replica không thấy authorized client/token.
- Không tự chuyển sang cookie chứa plaintext access/refresh tokens để “stateless” mà thiếu encryption/integrity/size/security controls.

Spring Session/Redis là một lựa chọn cho session, nhưng **không tự giải quyết mọi kiểu authorized-client persistence** nếu các bean/services không được tích hợp đúng. Phải test multi-replica login, refresh và logout thật.

## 10. Native Mobile BFF: không sao chép cookie-session pattern của browser

Một ứng dụng iOS/Android native thường là **OAuth public client**: dùng Authorization Code + **PKCE** qua system browser/OS authorization agent và nhận access token theo chuẩn phù hợp. Mobile gọi BFF/API qua:

~~~http
GET /v1/home HTTP/1.1
Host: mobile.api.example.test
Authorization: Bearer <mobile_access_token>
~~~

Trong mô hình này, **mobile-bff** thường là resource server bảo vệ API, xác thực bearer token; nó không cần dùng browser session cookie để làm danh tính mặc định. BFF vẫn có nhiệm vụ chọn DTO tối ưu cho mobile, versioning, aggregation và quota theo user/app.

### 10.1. SecurityWebFilterChain cho mobile BFF

~~~java
package demo.mobilebff;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration(proxyBeanMethods = false)
public class MobileBffSecurityConfig {

    @Bean
    SecurityWebFilterChain mobileSecurity(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers(HttpMethod.GET,
                                "/v1/catalog/public/**").permitAll()
                        .pathMatchers(HttpMethod.GET,
                                "/v1/**").hasAuthority(
                                        "SCOPE_mobile.read")
                        .pathMatchers(HttpMethod.POST,
                                "/v1/**").hasAuthority(
                                        "SCOPE_mobile.write")
                        .anyExchange().denyAll())
                .oauth2ResourceServer(oauth2 -> oauth2
                        .jwt(Customizer.withDefaults()))
                // Chỉ vô hiệu CSRF khi client thực sự chỉ gửi
                // bearer token trong Authorization header, không có cookie auth.
                .csrf(ServerHttpSecurity.CsrfSpec::disable)
                .build();
    }
}
~~~

Cấu hình giả định đã thêm `spring-boot-starter-oauth2-resource-server` và JWT decoder/issuer/audience validators phù hợp. **Không tắt CSRF như trên** nếu mobile-bff còn phục vụ browser hoặc nhận session cookie. Nếu một service phục vụ cả hai loại auth, dùng **SecurityWebFilterChain riêng theo matchers** và test rõ đường nào cần CSRF.

### 10.2. Kiểm tra `aud` và scope

Một JWT có chữ ký hợp lệ nhưng được cấp cho resource server khác **không mặc nhiên dùng được** tại mobile-bff. Cần kiểm tra:

- Issuer/JWK signature và thuật toán chấp nhận.
- Expiration/not-before, clock skew, token revocation khi phù hợp.
- Audience của `mobile-bff`; không nhận token chỉ dành cho web/admin.
- Scopes/roles theo endpoint; không chỉ `authenticated()` cho mọi API.
- User/tenant có quyền truy cập resource cụ thể ở downstream.

Không dùng `X-App-Version`, `User-Agent` hoặc `X-Device-Id` do client tự khai để bypass scope; chúng là metadata, không phải nguồn xác thực.

### 10.3. Mobile BFF nên tối ưu gì?

| Vấn đề | Hành vi BFF | Cách kiểm thử |
| --- | --- | --- |
| Mạng yếu, RTT cao | Gom các calls cần cho một màn hình | Đếm downstream requests, đo p95 trên mobile network simulation |
| Màn hình nhỏ | Trả trường/DTO rút gọn | Contract tests theo app version |
| Kết nối không ổn định | Timeouts, retry idempotent, caching/ETag | Simulate timeout, lost response, resume |
| Release app không đồng bộ | Versioned API, backward compatibility | Tests cho app versions còn hỗ trợ |
| User offline | Dữ liệu có ETag, timestamp, sync cursor hợp lệ | Revalidate, stale data policy |
| Tiết kiệm pin/băng thông | Payload nhỏ, compression phù hợp | Bytes transferred và battery/network tests |

Ứng dụng native tự quản lý token theo khuyến nghị nền tảng, **không lưu access token vào một HTTP header tĩnh** hoặc coi device ID không ký là authentication.

## 11. Admin BFF: mức quyền cao hơn không phải vì route tên “admin”

Admin BFF thường có endpoints:

~~~text
GET  /admin/audit/events
POST /admin/orders/{id}/refund
POST /admin/users/{id}/disable
GET  /admin/reports/export
~~~

Đây là các thao tác có tác động lớn. Route Host `admin.api.example.test` + Path `/admin/**` **không chứng minh quyền quản trị**. Admin BFF cần:

- SSO/MFA/step-up authentication theo mức nhạy cảm.
- Scopes/roles cụ thể (ví dụ `admin.audit.read` và `admin.orders.refund`), **deny by default**.
- Resource-level authorization theo tenant, sở hữu dữ liệu, phân tách nhiệm vụ (SoD) nếu yêu cầu.
- Kiểm tra CSRF nếu dùng cookie session trên browser admin.
- Network isolation, TLS, audit theo operator/action/approval, rate limits riêng.
- Giới hạn data export, PII redaction, pagination, masking và TTL của report.
- Backend services vẫn xác thực/ủy quyền thao tác, không tin `X-Is-Admin: true`.

### 11.1. Spring Security cho admin-bff dùng bearer token

Ví dụ dành cho admin client **chỉ dùng bearer header**:

~~~java
package demo.adminbff;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration(proxyBeanMethods = false)
public class AdminBffSecurityConfig {

    @Bean
    SecurityWebFilterChain adminSecurity(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers(HttpMethod.GET,
                                "/admin/audit/**")
                        .hasAuthority("SCOPE_admin.audit.read")
                        .pathMatchers(HttpMethod.POST,
                                "/admin/orders/*/refund")
                        .hasAuthority("SCOPE_admin.orders.refund")
                        .anyExchange().denyAll())
                .oauth2ResourceServer(oauth2 -> oauth2
                        .jwt(Customizer.withDefaults()))
                // Chỉ áp cho API chỉ có bearer auth; browser-cookie admin
                // phải dùng CSRF/session policy riêng.
                .csrf(ServerHttpSecurity.CsrfSpec::disable)
                .build();
    }
}
~~~

Đoạn mã dùng matchers để minh họa quyền riêng từng hành động. Với URL như `/admin/orders/123/refund`, hãy xác minh Spring path pattern matching trên version thật; **không coi chỉ có route path là đủ**. JWT decoder phải validate issuer/audience/scopes và backend phải kiểm tra order 123 có được refund theo business policy.

Nếu admin UI là browser với cookie session, dùng OAuth BFF login tương tự web nhưng **MFA/CSRF mạnh hơn**, thay vì copy `csrf.disable()` từ ví dụ bearer-only. Không trộn cả session và bearer trên một path mà không có rules phân định rõ.

### 11.2. Định tuyến và dữ liệu admin phải tách thật

Lý do nên có `admin-bff` riêng:

- Không gửi trường PII/audit/admin metadata vào web/mobile DTO dù UI không hiển thị.
- Không tái sử dụng token có `aud=mobile-api` để gọi admin resource server.
- Không đặt admin fallback về `web-bff` khi một route admin không khớp.
- Có release cadence, approval và audit policy riêng, không phụ thuộc phiên bản giao diện khách hàng.

Độ tách biệt network/service identity được kiểm chứng bằng chính sách kết nối, không chỉ bởi tên service hoặc prefix URL.

## 12. BFF chỉ chuyên biệt cho giao diện, không phá vỡ ranh giới nghiệp vụ

### 12.1. Những thao tác hợp lý trong BFF

| Việc cần làm | Web BFF | Mobile BFF | Admin BFF |
| --- | --- | --- | --- |
| Chuyển pagination thành view model | Có | Có, nhỏ hơn | Có, lớn hơn có giới hạn |
| Kết hợp catalog + recommendations | Có | Có, gọn payload | Ít cần |
| Chọn trường hiển thị | Có | Có | Có, theo quyền |
| Xử lý login/token theo client type | Cookie session | Bearer JWT | SSO/role/MFA |
| Hiển thị lỗi domain dễ hiểu | Có | Có | Có + audit reference |
| Thay đổi giao dịch/tính tiền domain | **Không** | **Không** | **Không** |
| Ghi DB domain trực tiếp | Tránh | Tránh | Tránh |

### 12.2. Tránh “đưa cả hệ thống nghiệp vụ” vào BFF

Một anti-pattern:

~~~text
mobile-bff:
  - tự tính tiền và thuế
  - cập nhật tồn kho trực tiếp
  - tạo giao dịch ngân hàng
  - xác nhận đơn hàng
~~~

Khi web BFF và admin BFF cũng có phiên bản riêng của các quy tắc này, hệ thống sẽ có **ba nguồn sự thật khác nhau**, gây lệch kết quả và bảo mật khó kiểm soát. Hãy để domain services sở hữu dữ liệu/giao dịch; BFF chủ yếu orchestrate hoặc compose dữ liệu đã được phân quyền.

### 12.3. Không đưa “data shaping” thành lỗ hổng quyền riêng tư

Ví dụ mobile chỉ cần `displayTotal` nhưng domain response có `internalCost`. Không chỉ truyền nguyên JSON rồi yêu cầu app không đọc field `internalCost`; **server phải tạo DTO rút gọn**. Khi compose nhiều services, phải kiểm tra người dùng có quyền nhận từng nguồn dữ liệu, không dùng chung service token quá rộng cho toàn BFF.

## 13. Xây endpoint tổng hợp dữ liệu bằng WebFlux WebClient

Một BFF có thể giảm số requests giữa frontend và backend. Chẳng hạn mobile home page cần:

~~~text
GET /v1/home
  → GET /catalog/featured
  → GET /catalog/categories
  → JSON {"featuredSkus": [...], "categories": [...]}
~~~

Thay vì mobile gửi hai requests nối tiếp qua mạng 4G, mobile BFF thực hiện **hai downstream calls có thể song song** và trả một DTO gọn. Đổi lại, BFF chịu **fan-out latency, timeout, failure amplification và concurrency**.

### 13.1. Thiết kế dữ liệu không có thông tin nhạy cảm cho lab

Hai upstream ví dụ chỉ trả catalog công khai:

~~~json
// GET /catalog/featured
{"skus":["SKU-A1","SKU-B2"]}
~~~

~~~json
// GET /catalog/categories
{"names":["books","accessories"]}
~~~

DTO mobile:

~~~json
{
  "featuredSkus":["SKU-A1","SKU-B2"],
  "categories":["books","accessories"]
}
~~~

Vì hai APIs ví dụ là **catalog công khai**, code lab không cần chuyển token end-user. Với order/customer private data, phải thêm **token đúng audience** hoặc mTLS/delegation và kiểm tra resource authorization; `WebClient` không tự được bảo vệ bằng `TokenRelay` của một Gateway route.

### 13.2. Java controller WebFlux cho mobile home

`src/main/java/demo/mobilebff/MobileHomeController.java`:

~~~java
package demo.mobilebff;

import java.time.Duration;
import java.util.List;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Mono;

@RestController
public class MobileHomeController {

    public record FeaturedResponse(List<String> skus) {}
    public record CategoriesResponse(List<String> names) {}
    public record MobileHomeResponse(
            List<String> featuredSkus,
            List<String> categories) {}

    private final WebClient catalogClient;

    public MobileHomeController(
            WebClient.Builder builder,
            @Value("${demo.catalog.base-url}") String baseUrl) {
        // URI upstream do cấu hình triển khai được phê duyệt quản lý,
        // không lấy từ query/header của client (tránh SSRF).
        this.catalogClient = builder.baseUrl(baseUrl).build();
    }

    @GetMapping("/v1/home")
    public Mono<MobileHomeResponse> home() {

        Mono<FeaturedResponse> featured =
                catalogClient.get()
                        .uri("/catalog/featured")
                        .retrieve()
                        .bodyToMono(FeaturedResponse.class)
                        .timeout(Duration.ofMillis(800));

        Mono<CategoriesResponse> categories =
                catalogClient.get()
                        .uri("/catalog/categories")
                        .retrieve()
                        .bodyToMono(CategoriesResponse.class)
                        .timeout(Duration.ofMillis(800));

        return Mono.zip(featured, categories,
                (f, c) -> new MobileHomeResponse(
                        f.skus(), c.names()))
                .timeout(Duration.ofSeconds(2));
    }
}
~~~

`application.yml` cho mobile BFF có ví dụ:

~~~yaml
server:
  port: 9082

demo:
  catalog:
    base-url: http://catalog-service:9091
~~~

Code này là một **ví dụ đầy đủ về composition** nhưng chưa phải hệ thống production hoàn chỉnh. Nó cần Spring WebFlux dependency, cấu hình bảo mật, upstream catalog stub, HTTP client connection/read timeouts, status/error translation và tests phù hợp. Không gọi `Mono.block()` trong WebFlux event loop.

### 13.3. Chuyện gì xảy ra khi một upstream lỗi?

`Mono.zip(featured, categories)` chỉ trả khi cả hai thành công; nếu một nhánh lỗi, kết quả mặc định **fail toàn response** và nhánh khác có thể bị cancel. Điều này đôi khi đúng (phải đủ dữ liệu), đôi khi không:

| Dữ liệu | Chính sách nên cân nhắc | Vì sao |
| --- | --- | --- |
| Price/stock trước checkout | Fail closed/không trả thông tin sai | Dữ liệu quyết định giao dịch |
| Featured recommendations | Có thể fallback danh sách rỗng/cached | Chức năng bổ trợ |
| User profile/permissions | Không fallback thành guest/admin tùy tiện | Rủi ro authz |
| Admin audit trail | Fail closed và ghi log tham chiếu | Không được che lỗi dữ liệu kiểm toán |

Nếu muốn fallback chỉ cho recommendations, đặt `onErrorResume`/`onErrorReturn` **tại nhánh optional được phê duyệt**, không đặt một catch-all biến mọi lỗi auth/timeout thành HTTP 200. Với các API ghi dữ liệu, phân tích retry/idempotency key và deadlines, tránh fan-out tạo hai giao dịch không nguyên tử.

### 13.4. Fan-out latency và độ khuếch đại tải

Với hai downstream calls chạy song song:

\[
T_{\mathrm{home}}\approx T_{\mathrm{gateway}}
  + \max(T_{\mathrm{featured}},T_{\mathrm{categories}})
  +T_{\mathrm{compose}}
\]

Đây là mô hình ước lượng khi các calls đồng thời; actual latency còn có queueing, connection pool, TLS, CPU/GC. Nếu một BFF call **10 microservices**, một request frontend có thể tạo **10 downstream requests**; khi traffic tăng 1.000 RPS, backend có thể nhận 10.000 calls/s. Cần đo fan-out factor và giới hạn concurrency/rate.

**Điểm quan trọng:** BFF có thể giảm RTT/băng thông từ client nhưng **không mặc nhiên giảm tổng tải** của hệ thống. Tối ưu dựa trên user experience và SLO thực tế, không chỉ đếm số HTTP calls ở browser.

### 13.5. Không tạo open proxy từ tham số URL

Sai:

~~~java
// Không dùng client input làm điểm đến HTTP tùy ý.
String target = request.getQueryParams().getFirst("url");
return webClient.get().uri(target).retrieve().bodyToMono(String.class);
~~~

Một caller có thể tìm cách truy cập cloud metadata, management endpoints, internal admin services hoặc chuyển access token sang host ngoài. BFF chỉ gọi những backend nằm trong **allowlist cố định**, kiểm tra redirect destinations và DNS resolution nếu dynamic endpoints được hỗ trợ; không dùng `Host` hoặc `X-Forwarded-Host` chưa kiểm tra để dựng downstream URI.

## 14. Lab ba BFF stub trên localhost

Để quan sát route thực sự đến đúng service, triển khai ba instance của **cùng một chương trình echo** với cấu hình khác nhau. Đây là **stub phục vụ học tập**, không có authentication hay dữ liệu nghiệp vụ; không được triển khai public như BFF production.

### 14.1. Spring Boot WebFlux stub

Ví dụ dependencies: `spring-boot-starter-webflux` cùng Spring Boot version phù hợp.

`src/main/java/demo/bffstub/BffStubApplication.java`:

~~~java
package demo.bffstub;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BffStubApplication {
    public static void main(String[] args) {
        SpringApplication.run(BffStubApplication.class, args);
    }
}
~~~

`src/main/java/demo/bffstub/BffStubController.java`:

~~~java
package demo.bffstub;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class BffStubController {

    private final String appName;
    private final AtomicLong requests = new AtomicLong();

    public BffStubController(
            @Value("${demo.bff.name}") String appName) {
        this.appName = appName;
    }

    @GetMapping("/whoami")
    public Map<String, Object> whoami(ServerHttpRequest request) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("bff", appName);
        result.put("path", request.getPath().value());
        result.put("method", request.getMethod().name());
        result.put("channelMarker",
                request.getHeaders().getFirst("X-Lab-Channel"));
        result.put("untrustedUserId",
                request.getHeaders().getFirst("X-User-Id"));
        result.put("requestNumber", requests.incrementAndGet());
        return result;
    }
}
~~~

### 14.2. Chạy ba instances

Trong ba terminal khác nhau của **project BFF stub**:

~~~bash
# Instance web
./mvnw spring-boot:run \
  -Dspring-boot.run.arguments="--server.port=9081 --demo.bff.name=web"

# Instance mobile
./mvnw spring-boot:run \
  -Dspring-boot.run.arguments="--server.port=9082 --demo.bff.name=mobile"

# Instance admin
./mvnw spring-boot:run \
  -Dspring-boot.run.arguments="--server.port=9083 --demo.bff.name=admin"
~~~

Tùy shell/Maven wrapper, cách quote arguments có thể cần điều chỉnh (PowerShell/cmd/Linux). Có thể chạy ba bản jar với `java -jar ... --server.port=... --demo.bff.name=...` sau khi build. Mỗi process có counter riêng; **không assert một số requestNumber cố định** vì phụ thuộc traffic test.

Gateway lab chạy riêng ở port 8080 với profile `bff-lab` của mục 7.

### 14.3. Positive tests bằng cURL

~~~bash
curl -i "http://127.0.0.1:8080/web/whoami" \
  -H "X-User-Id: forged-admin"

curl -i "http://127.0.0.1:8080/mobile/whoami" \
  -H "X-User-Id: forged-admin"

curl -i "http://127.0.0.1:8080/admin/whoami" \
  -H "X-User-Id: forged-admin"
~~~

Response minh họa cho `/mobile/whoami`:

~~~http
HTTP/1.1 200 OK
X-Lab-Bff-Route: mobile-bff-lab
Content-Type: application/json

{"bff":"mobile","path":"/whoami","method":"GET",
 "channelMarker":"mobile","untrustedUserId":null,
 "requestNumber":1}
~~~

Điều cần kiểm tra: marker route do Gateway thêm, tên BFF đúng, downstream path đã được `StripPrefix` thành `/whoami`, và `X-User-Id` do client khai **không xuất hiện** ở stub vì default filter đã xóa.

### 14.4. Negative tests

~~~bash
# Không route nào trong fixture này match.
curl -i "http://127.0.0.1:8080/unknown/whoami"

# Đường dẫn /web/ không có handler / ở stub,
# có thể route match nhưng backend trả 404.
curl -i "http://127.0.0.1:8080/web/"

# Backend stub chỉ có @GetMapping("/whoami").
# POST có thể được Gateway forward nhưng bị backend từ chối.
curl -i -X POST "http://127.0.0.1:8080/mobile/whoami"
~~~

**Ba ca này không tương đương**:

- `/unknown/whoami`: không có Gateway route trong fixture, thường trả 404 nếu không có handler khác.
- `/web/`: Path predicate web **có thể khớp**; backend nhận `/` nhưng không có handler nên trả 404.
- `POST /mobile/whoami`: route Gateway **không giới hạn Method**, do đó có thể forward POST, backend trả 405. Không dùng ca này để kết luận Gateway đã áp Method predicate.

Đây là lý do test cần **route marker + backend request capture**, không chỉ status code.

### 14.5. Đường trực tiếp tới stub

~~~bash
curl -i "http://127.0.0.1:9082/whoami" \
  -H "X-User-Id: forged-admin"
~~~

Stub có thể echo chính header giả (vì bypass Gateway), chứng minh default filter trên Gateway **không tự bảo vệ một backend mở port public**. Production phải chặn direct BFF access hoặc BFF tự xác thực/ủy quyền mọi request không phụ thuộc điểm vào.

## 15. Integration test host-based routing với WebTestClient và MockWebServer

Thực hành bằng cURL giúp hiểu route. Để chống lỗi khi thêm BFF mới, cần **HTTP integration tests lặp lại trong CI**. Ta chạy Gateway Server WebFlux trên cổng ngẫu nhiên, ba MockWebServer cũng trên cổng ngẫu nhiên, rồi kiểm tra chính xác **Host → BFF target**, Path/Method và header filtering.

### 15.1. Cấu trúc fixture

~~~text
JUnit 5 + WebTestClient
      ↓ GET với Host cụ thể
Gateway Server WebFlux (RANDOM_PORT)
  ├── Host=web.example.test      → MockWebServer WEB
  ├── Host=mobile.api.example.test, Path=/v1/**
  │                             → MockWebServer MOBILE
  └── Host=admin.api.example.test, Path=/admin/**
                                → MockWebServer ADMIN
~~~

Đây là **test routing không có authentication** để tách việc chọn route khỏi Spring Security/IdP. **Không** dùng kết quả pass của class này để tuyên bố admin BFF đã được bảo vệ: security suite riêng phải test scopes, cookie/CSRF, MFA và backend resource authorization.

### 15.2. Dependencies cho Gateway 4.3 + Spring Boot 3.5

Ví dụ Maven (Spring Cloud BOM tương thích):

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-gateway-server-webflux</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>

    <dependency>
        <groupId>com.squareup.okhttp3</groupId>
        <artifactId>mockwebserver</artifactId>
        <version>4.12.0</version>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Trong class Java dưới đây, import `@AutoConfigureWebTestClient` dùng package của **Spring Boot 3.5**. Khi nâng cấp Spring Boot 4.x, cần kiểm tra test module/package auto-configuration mới, **không chỉ đổi Gateway YAML prefix**. MockWebServer 5.x cũng có API packages thay đổi; code mẫu cố định MockWebServer 4.12.0.

### 15.3. Gateway application test

`src/main/java/demo/edge/EdgeGatewayApplication.java`:

~~~java
package demo.edge;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class EdgeGatewayApplication {
    public static void main(String[] args) {
        SpringApplication.run(EdgeGatewayApplication.class, args);
    }
}
~~~

### 15.4. application-bff-test.yml: chỉ có ba routes test

File `src/test/resources/application-bff-test.yml` dành cho **Gateway 4.3 + Boot 3.5**:

~~~yaml
spring:
  cloud:
    gateway:
      default-filters:
        - RemoveRequestHeader=X-User-Id
      routes:
        - id: web-bff-route
          order: -30
          uri: http://127.0.0.1:${test.web.port}
          predicates:
            - Host=web.example.test
          filters:
            - AddResponseHeader=X-Lab-Bff-Route,web-bff-route

        - id: mobile-bff-route
          order: -20
          uri: http://127.0.0.1:${test.mobile.port}
          predicates:
            - Host=mobile.api.example.test
            - Path=/v1/**
          filters:
            - AddResponseHeader=X-Lab-Bff-Route,mobile-bff-route

        - id: admin-bff-route
          order: -10
          uri: http://127.0.0.1:${test.admin.port}
          predicates:
            - Host=admin.api.example.test
            - Path=/admin/**
          filters:
            - AddResponseHeader=X-Lab-Bff-Route,admin-bff-route
~~~

**Phiên bản Gateway 5.x:** di chuyển phần `routes` và `default-filters` vào `spring.cloud.gateway.server.webflux.*`; nếu dùng Boot 4.x, đối chiếu cả imports/test starter. Không đặt cả hai namespace trong một fixture rồi đoán cái nào có hiệu lực.

Nếu project chính có thêm Java `RouteLocator`/discovery routes hay default routes từ một config source khác, cần bảo đảm **profile bff-test chỉ có ba routes như trên**; nếu không negative test có thể bị fallback route nhận và trả 200.

### 15.5. JUnit 5: chạy HTTP qua Gateway và ghi nhận backend calls

`src/test/java/demo/edge/BffRoutingTest.java`:

~~~java
package demo.edge;

import java.io.IOException;
import java.util.concurrent.TimeUnit;

import okhttp3.mockwebserver.Dispatcher;
import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;

import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.parallel.Execution;
import org.junit.jupiter.api.parallel.ExecutionMode;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        classes = EdgeGatewayApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
@ActiveProfiles("bff-test")
@Execution(ExecutionMode.SAME_THREAD)
class BffRoutingTest {

    private static final MockWebServer WEB = startStub("web");
    private static final MockWebServer MOBILE = startStub("mobile");
    private static final MockWebServer ADMIN = startStub("admin");

    @Autowired
    WebTestClient client;

    @DynamicPropertySource
    static void registerStubPorts(DynamicPropertyRegistry registry) {
        registry.add("test.web.port", WEB::getPort);
        registry.add("test.mobile.port", MOBILE::getPort);
        registry.add("test.admin.port", ADMIN::getPort);
    }

    private static MockWebServer startStub(String name) {
        MockWebServer server = new MockWebServer();
        server.setDispatcher(new Dispatcher() {
            @Override
            public MockResponse dispatch(RecordedRequest request) {
                return new MockResponse()
                        .setResponseCode(200)
                        .addHeader("Content-Type", "application/json")
                        .addHeader("X-Bff-Stub", name)
                        .setBody("{\"bff\":\"" + name + "\"}");
            }
        });
        try {
            server.start();
        } catch (IOException e) {
            throw new ExceptionInInitializerError(e);
        }
        return server;
    }

    @AfterAll
    static void closeStubs() throws IOException {
        WEB.shutdown();
        MOBILE.shutdown();
        ADMIN.shutdown();
    }

    @Test
    void webHostGoesOnlyToWebBff() throws InterruptedException {
        int webBefore = WEB.getRequestCount();
        int mobileBefore = MOBILE.getRequestCount();
        int adminBefore = ADMIN.getRequestCount();

        client.get().uri("/bff/home")
                .header(HttpHeaders.HOST, "web.example.test")
                .header("X-User-Id", "forged-admin")
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueEquals(
                        "X-Lab-Bff-Route", "web-bff-route")
                .expectHeader().valueEquals("X-Bff-Stub", "web")
                .expectBody()
                .jsonPath("$.bff").isEqualTo("web");

        assertThat(WEB.getRequestCount()).isEqualTo(webBefore + 1);
        assertThat(MOBILE.getRequestCount()).isEqualTo(mobileBefore);
        assertThat(ADMIN.getRequestCount()).isEqualTo(adminBefore);

        RecordedRequest forwarded =
                WEB.takeRequest(1, TimeUnit.SECONDS);
        assertThat(forwarded).isNotNull();
        assertThat(forwarded.getPath()).isEqualTo("/bff/home");
        assertThat(forwarded.getMethod()).isEqualTo("GET");
        assertThat(forwarded.getHeader("X-User-Id")).isNull();
    }

    @Test
    void mobileHostAndPathChooseMobileBff()
            throws InterruptedException {
        int before = MOBILE.getRequestCount();

        client.get().uri("/v1/feed?page=1")
                .header(HttpHeaders.HOST, "mobile.api.example.test")
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueEquals(
                        "X-Lab-Bff-Route", "mobile-bff-route")
                .expectHeader().valueEquals("X-Bff-Stub", "mobile");

        assertThat(MOBILE.getRequestCount()).isEqualTo(before + 1);
        RecordedRequest forwarded =
                MOBILE.takeRequest(1, TimeUnit.SECONDS);
        assertThat(forwarded).isNotNull();
        assertThat(forwarded.getPath()).isEqualTo("/v1/feed?page=1");
    }

    @Test
    void adminHostAndPathChooseAdminBff()
            throws InterruptedException {
        int before = ADMIN.getRequestCount();

        client.get().uri("/admin/audit/events")
                .header(HttpHeaders.HOST, "admin.api.example.test")
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueEquals(
                        "X-Lab-Bff-Route", "admin-bff-route")
                .expectHeader().valueEquals("X-Bff-Stub", "admin");

        assertThat(ADMIN.getRequestCount()).isEqualTo(before + 1);
        RecordedRequest forwarded =
                ADMIN.takeRequest(1, TimeUnit.SECONDS);
        assertThat(forwarded).isNotNull();
        assertThat(forwarded.getPath())
                .isEqualTo("/admin/audit/events");
    }

    @Test
    void unknownHostHasNoBffRoute() {
        int webBefore = WEB.getRequestCount();
        int mobileBefore = MOBILE.getRequestCount();
        int adminBefore = ADMIN.getRequestCount();

        client.get().uri("/bff/home")
                .header(HttpHeaders.HOST, "unknown.example.test")
                .exchange()
                .expectStatus().isNotFound()
                .expectHeader().doesNotExist("X-Lab-Bff-Route");

        assertThat(WEB.getRequestCount()).isEqualTo(webBefore);
        assertThat(MOBILE.getRequestCount()).isEqualTo(mobileBefore);
        assertThat(ADMIN.getRequestCount()).isEqualTo(adminBefore);
    }

    @Test
    void mobileHostCannotUseAdminPath() {
        int adminBefore = ADMIN.getRequestCount();
        int mobileBefore = MOBILE.getRequestCount();

        client.get().uri("/admin/audit/events")
                .header(HttpHeaders.HOST, "mobile.api.example.test")
                .exchange()
                .expectStatus().isNotFound()
                .expectHeader().doesNotExist("X-Lab-Bff-Route");

        assertThat(ADMIN.getRequestCount()).isEqualTo(adminBefore);
        assertThat(MOBILE.getRequestCount()).isEqualTo(mobileBefore);
    }
}
~~~

### 15.6. Đọc đúng ý nghĩa kết quả test

- Các tests **không** khẳng định web/mobile/admin đã authenticated; stub đáp 200 cho mọi downstream request. Mục tiêu là **BFF selection**.
- Một request Host sai trả 404 trong **fixture không có fallback**. Nếu bổ sung route khác, phải đổi expected route ID/target chứ không coi mọi negative đều 404.
- `WEB.takeRequest(...)` kiểm tra path giữ nguyên ở host-based route, khác lab `StripPrefix=1` ở mục 7.
- `X-Lab-Bff-Route` chỉ là marker phục vụ test; một route matcher chính xác nhưng security fail vẫn cần test riêng.
- Các counters từ MockWebServer chứng minh request không bị gửi nhầm sang BFF khác.
- Header `X-User-Id` giả bị `RemoveRequestHeader` xóa ở route test; **không chứng minh mọi endpoint/handler đều được scrub**. Với production, làm sạch tại trusted edge và WebFilter phù hợp.
- Class dùng `@Execution(SAME_THREAD)` để tránh những tests trong class chia sẻ counters/recorded queues chạy song song. Các suites khác không nên dùng chung ba stub này.
- Cấu hình 4.3/Boot 3.5 rõ ràng: khi migrate 5.x/Boot4, cập nhật namespace và imports trước khi chạy.

### 15.7. Chạy và xác nhận số test thật sự được thực thi

~~~bash
./mvnw -Dtest=BffRoutingTest test
~~~

Đảm bảo build/test runner báo **5 tests executed**, không phải “build successful / 0 tests”. Nếu dùng Gradle/Failsafe/JUnit tags, điều chỉnh include patterns tương ứng.

Đây là **mẫu test để người học tự triển khai**; bài này chưa chạy Maven/Gradle hoặc suite trong repository, nên không báo PASS cho bài kiểm thử học thuật.

## 16. Security test matrix riêng cho từng BFF

Route test đạt **không đủ** để triển khai. Từng BFF cần một bộ test xác thực/ủy quyền riêng với token test được cấp/được ký trong môi trường thử nghiệm.

| ID | Request | Expected |
| --- | --- | --- |
| SEC01 | Browser chưa login gọi `/bff/orders/42` | Redirect/login hoặc 401 tùy contract, không leak private data |
| SEC02 | Browser có session cookie hợp lệ, GET cùng origin | BFF dùng authorized client, downstream token đúng audience |
| SEC03 | Browser POST không có CSRF token, cookie hợp lệ | Bị từ chối, backend không bị gọi |
| SEC04 | Browser POST với CSRF token hợp lệ và quyền | Được xử lý theo contract |
| SEC05 | Cookie của web host được gửi tới admin host | Không được coi là admin session do Domain/host-only policy |
| SEC06 | Mobile thiếu bearer token tới `/v1/me` | 401, không forward private data |
| SEC07 | Mobile bearer ký đúng nhưng `aud` sai | Bị từ chối |
| SEC08 | Mobile token đúng audience nhưng thiếu `SCOPE_mobile.read` | 403 |
| SEC09 | Mobile gửi `X-Is-Admin: true` | Không tạo admin role |
| SEC10 | Admin thiếu `SCOPE_admin.audit.read` | 403 và không gọi audit API |
| SEC11 | Admin có role đọc audit nhưng cố POST refund | Bị từ chối nếu không có refund permission |
| SEC12 | User một tenant thử truy cập resource tenant khác | Backend kiểm tra ownership và từ chối |
| SEC13 | Client tự đặt `X-User-Id/X-Tenant-Id` | Gateway không relay như verified identity |
| SEC14 | Client giả Host admin | Có thể chọn route khi test Host, nhưng **BFF authz vẫn phải chặn** |
| SEC15 | Client đi thẳng tới BFF/service port | Production network/mTLS policy phải chặn bypass |
| SEC16 | Admin export response chứa PII ngoài quyền | Server response phải loại bỏ field không được phép |
| SEC17 | Browser logout, session cookie cũ được dùng lại | Session không còn hợp lệ theo logout policy |
| SEC18 | Token refresh/session store gặp lỗi | Không fallback thành anonymous admin, có error mapping rõ |

**Đặc biệt SEC14:** không cố “chặn mọi request có Host admin” khi người dùng Internet có thể tới cùng IP; cấu hình Host routing đúng vẫn có thể match, nhưng **không hề tự cho phép thao tác admin**. Điều cần chứng minh là Security chain, MFA, backend scopes, network isolation và dữ liệu không rò rỉ.

## 17. Cross-cutting policies: đặt ở Gateway chung hay từng BFF?

Spring Cloud Gateway có nhiều filter factories: headers/path rewrite, `RequestRateLimiter`, `CircuitBreaker`, `Retry`, `TokenRelay` (đúng điều kiện OAuth2 client), caching/response filters và metrics. Không nên đặt mọi bộ lọc vào **một default-filters list** cho mọi BFF mà không xét sự khác biệt browser/mobile/admin.

### 17.1. Quy tắc phân công chính sách

| Chính sách | Edge/Gateway chung | BFF chuyên biệt | Domain service |
| --- | --- | --- | --- |
| TLS termination, Host allowlist | Có | Mặc định nhận qua kênh riêng | Verify service-to-service TLS khi cần |
| Routing Host/Path | Có | BFF route nội bộ cho use case | Endpoint domain |
| Chống header identity spoofing | Scrub client-controlled headers | Không tin metadata chưa xác minh | Không tin header trần ngoài trust boundary |
| Browser OAuth login/cookie | Route đến web BFF, không quản session thay BFF | **Web BFF** confidential client + CSRF | Xác thực token đúng audience |
| Mobile bearer JWT | Có thể validate coarse auth ở edge | **Mobile BFF** validate scopes/audience | Resource-level authorization |
| Admin SSO/MFA/roles | Edge chỉ bảo vệ perimeter | **Admin BFF** enforce use-case authorization | Check object/transaction permissions |
| Rate limit | Edge quota thô toàn site/client | Quota theo user/plan/action | Domain quota/idempotency |
| Retry/circuit breaker | Mức transport/route nếu phù hợp | Fan-out budgets và fallback theo use case | Business retries/transactions |
| Caching | Public responses có cache contract | Data shaping/cache theo người dùng | Source of truth/ETag |
| Observability | Route IDs/latency/upstream health | Screen SLO, fan-out attempts, view model errors | Domain transaction metrics |

### 17.2. Rate limiter khác nhau theo frontend

Mỗi BFF có traffic mix khác:

- **Web checkout:** hạn chế theo authenticated user/account; chống bot nhưng không ảnh hưởng không cần thiết tới session login/callback.
- **Mobile feed:** quota theo verified principal/plan, có thể thêm per-device risk signals đã xác minh. Không coi `X-Device-Id` tự khai là identity.
- **Admin export/refund:** quota nghiêm hơn, rate + concurrency limits + approval/audit; limit theo operator và tenant/action.

Nếu dùng Gateway Server WebFlux `RequestRateLimiter`, cần `KeyResolver` lấy key đáng tin. Ví dụ key theo principal:

~~~java
package demo.edge;

import org.springframework.cloud.gateway.filter.ratelimit.KeyResolver;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import reactor.core.publisher.Mono;

@Configuration(proxyBeanMethods = false)
public class RateLimitKeys {

    @Bean
    KeyResolver authenticatedPrincipalKeyResolver() {
        return exchange -> exchange.getPrincipal()
                .map(principal -> principal.getName())
                .switchIfEmpty(Mono.just("anonymous"));
    }
}
~~~

Đây là một **mẫu resolver**, không phải policy hoàn chỉnh. Với browser BFF giữ session, edge Gateway phía trước **có thể không có principal OAuth đã xác thực**, nên resolver ở **edge** sẽ thấy anonymous cho nhiều web sessions. Khi cần quota từng người dùng, đặt limiter ở **web BFF sau session authentication** hoặc tích hợp principal propagation đáng tin (không từ raw header). Với native mobile bearer, có thể xác thực token tại edge nếu thực sự cấu hình Resource Server đúng.

Đừng dùng `X-User-Id`/`X-Tenant-Id` hoặc `X-Forwarded-For` chưa tin cậy để tạo rate limit keys. Quota state dùng local memory trên nhiều replicas có thể dẫn đến quota nhân theo số node; Redis/cluster store cần policy khi storage bị lỗi.

### 17.3. Circuit breaker và retry theo downstream, không theo “mọi request”

| Loại thao tác | Retry? | Fallback? |
| --- | --- | --- |
| GET catalog public idempotent | Có thể, bounded attempts + deadline | Cached data đã kiểm tra freshness |
| GET user profile/private order | Có thể hạn chế nếu backend contract cho phép | Không trả profile của user khác hoặc dữ liệu giả |
| POST checkout/payment | Không retry mù quáng | Cần idempotency key/trạng thái giao dịch rõ |
| Admin refund/disable account | Không retry bất cẩn | Fail closed + audit/escalation |
| Recommendations widget | Có thể retry nhẹ | Danh sách rỗng/last-known-good nếu hợp đồng cho phép |

SLO của BFF phải tính số downstream attempts. Nếu một BFF tổng hợp ba upstreams và mỗi upstream tự retry ba lần, một request UI có thể tạo đến **9 attempts**, chưa tính retry ở edge. Phải có **retry budget xuyên các tầng**, timeout/deadline tổng và circuit breaker khi upstream chập chờn.

Không đặt `Retry` filter trong edge rồi để BFF tự retry các POST side-effecting mà không có idempotency contract.

### 17.4. CORS: browser vs native

Browser cùng origin `https://web.example.test` gọi `/bff/**` thường tránh phần lớn cấu hình CORS. Nếu UI ở `https://app.example.test` nhưng BFF ở `https://web.api.example.test`, đó là **cross-origin** dù có thể cùng site: cần cấu hình CORS rõ ràng, allowlist Origin, methods, headers và credentials.

Với cookie session:

~~~http
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Credentials: true
Vary: Origin
~~~

**Không dùng `Access-Control-Allow-Origin: *` khi cho phép credentials.** Browser còn yêu cầu fetch credentials mode phù hợp và cookie SameSite/Secure. CORS không ngăn curl/mobile native hoặc service-to-service clients gọi API; nó **không phải authentication**.

Native apps không chịu browser CORS preflight theo cùng cơ chế. Vì vậy đừng “sửa lỗi mobile bearer 401” bằng cách tắt CORS/CSRF/security lung tung; hãy xác định lỗi ở JWT audience, scope, TLS, token expiry hay network.

### 17.5. Cache theo phạm vi chia sẻ dữ liệu

| Response | Cache policy nên cân nhắc | Rủi ro |
| --- | --- | --- |
| Public catalog featured | CDN/BFF TTL ngắn, ETag | Stale inventory/prices nếu dùng sai |
| Mobile public categories | ETag, conditional GET | App cũ cần schema tương thích |
| Web cart/order private | `Cache-Control: private, no-store` theo mức nhạy cảm | Cache leak giữa users |
| Admin audit/export | Thường `no-store` | PII/security audit retention |
| User-specific recommendations | Cache key theo verified principal/tenant khi được phê duyệt | Cross-user data leakage |

Không tạo cache key chỉ bằng path khi response phụ thuộc cookie/token/tenant. Cần phân biệt HTTP cache, Gateway LocalResponseCache (nếu sử dụng và đủ điều kiện), distributed cache trong BFF và domain cache; chúng có **invalidation, auth sensitivity và consistency semantics khác nhau**.

### 17.6. Service discovery và workload identity

Trong Kubernetes có thể dùng DNS nội bộ như `http://mobile-bff:9082`; trong Spring Cloud discovery, Gateway Server có thể route `lb://mobile-bff` khi có Spring Cloud LoadBalancer/discovery integration phù hợp. Đây là **lựa chọn service resolution**, không tự cấp quyền gọi BFF.

Cần:

- BFF services không expose trực tiếp Internet nếu public edge là entrypoint đã thiết kế.
- NetworkPolicy/security groups và khi cần mTLS cho edge→BFF→domain services.
- Gateway trust forwarded headers chỉ từ proxies đã kiểm soát.
- BFF không tin `X-Authenticated-User` hay `X-Client-Type` do client tự gửi.
- Backend xác minh bearer token đúng audience hoặc workload identity đã được phê duyệt.

## 18. Hiệu năng của BFF: khi một lớp mới giúp, khi nào gây hại?

### 18.1. Mô hình độ trễ

Nếu browser/mobile phải gọi ba backend **tuần tự**:

\[
T_{\mathrm{client\;seq}}
\approx T_A+T_B+T_C+3T_{\mathrm{client\;RTT}}
\]

Nếu BFF gọi ba backend **song song** và trả một response:

\[
T_{\mathrm{BFF}}
\approx T_{\mathrm{client\;RTT}}
 +T_{\mathrm{edge}}
 +\max(T_A,T_B,T_C)
 +T_{\mathrm{compose}}
\]

Đây là công thức **ước lượng**, không phải số đo từ hệ thống thật. Nó cho thấy BFF có thể hữu ích khi frontend RTT lớn và backend-to-backend latency thấp. Nhưng nếu BFF tạo quá nhiều requests hoặc có concurrency limits kém, p99 vẫn có thể xấu hơn client gọi trực tiếp.

### 18.2. SLO không giống nhau cho ba loại ứng dụng

| Client | Chỉ số nên theo dõi |
| --- | --- |
| Web checkout | Core Web Vitals liên quan UI, p95 checkout API, retry/double-submit, auth/session failures |
| Mobile feed/home | Bytes/response, number of client RTT, p95/p99 trên mạng yếu, offline/cache hit |
| Admin audit/refund | Correctness, 403/401 policy, audit completeness, export durations, sensitive error rates |

Đừng đặt một p99 duy nhất cho mọi BFF rồi bỏ qua khác biệt. Admin batch export có thể dài nhưng phải có async job/pagination và trạng thái rõ ràng; mobile home cần latency thấp/payload nhẹ hơn.

### 18.3. Batch, pagination và streaming

Các kỹ thuật:

- **Pagination/cursor:** mobile trả mỗi trang ít items; cursor có ký/validation nếu nó mang thông tin quyền hoặc filter.
- **Batch fetching:** một BFF request gom nhiều SKU/id có giới hạn; chặn `N+1` fan-out.
- **ETag/If-None-Match:** giảm bytes trên danh sách ít thay đổi, không làm lộ user-specific cache.
- **Compression:** đánh giá CPU/bandwidth theo loại payload và TLS support.
- **Streaming/SSE:** chỉ dùng khi frontend cần realtime; cẩn thận event-loop, backpressure và long-lived connections.
- **Async jobs:** admin exports lớn nên dùng job + polling/webhook an toàn thay vì giữ một HTTP request nhiều phút.

Không dùng `Mono.zip` với hàng nghìn phần tử không giới hạn để “tăng song song”. Hãy có concurrency budget, connection pool sizing, per-upstream timeout và cancellation khi client ngắt kết nối.

### 18.4. Đừng lặp business logic ở ba BFF để “tối ưu”

Khi một quy tắc dùng chung (giá cuối, quyền xem order, áp thuế) được copy vào web/mobile/admin BFF, lỗi nhất quán có thể tốn kém hơn RTT tiết kiệm. Domain services nên phát một API ổn định; mỗi BFF chỉ chọn cách **trình bày và phối hợp** phù hợp client.

## 19. Observability và ownership của BFF

Một trace/request có thể đi qua:

~~~text
browser → ingress → edge-gateway (route=web-bff-route)
        → web-bff (useCase=checkout-summary)
        → orders-service
        → inventory-service
~~~

Cần correlation giữa các hops:

| Tầng | Span/metric gợi ý | Điều cần tránh |
| --- | --- | --- |
| Edge | route ID, status, duration, target BFF, retries | Log JWT/cookie/raw query |
| BFF | use-case, frontend version bucket, fan-out count, cache hit, p99 | High-cardinality user ID/token in labels |
| Backend | business operation, result, DB latency, authz decision | Rò PII/domain secrets |
| Security | 401/403 reason category, issuer/audience failures, CSRF failures | Log raw tokens/session IDs |

Một số logs có thể ghi `traceId` và `routeId`, nhưng **tên field là convention triển khai** chứ không mặc định mọi Gateway version phát đủ dữ liệu này. Dùng OpenTelemetry/Micrometer/Reactor context propagation theo stack hiện tại; kiểm tra trace context được truyền đúng qua WebClient/fan-out.

### 19.1. Nhãn frontend version cần giới hạn cardinality

Không dùng mỗi build number/beta hash, user ID hoặc full User-Agent làm metric label. Nếu muốn so p95 của mobile cũ/mới, nhóm theo `apiMajorVersion=1|2` hoặc nhóm app releases đã xác định. Việc đặt vô số labels có thể làm Prometheus/cardinality bùng nổ và gây rò rỉ thông tin.

### 19.2. Mỗi BFF cần owner rõ ràng

Ví dụ:

| BFF | Primary owner | Shared dependencies |
| --- | --- | --- |
| web-bff | Web experience team | Platform auth/TLS/metrics standards |
| mobile-bff | Mobile team | Domain API contracts, schema/versioning |
| admin-bff | Back-office team + Security review | Audit/RBAC/PII compliance |

Platform/Gateway team sở hữu edge routing, TLS, networking, common filters và SLO nền tảng; **frontend teams có thể phát hành DTO riêng**. Những thay đổi source-of-truth trong domain service vẫn phải được phối hợp với domain owners.

### 19.3. Tracing giúp phát hiện một request bị định tuyến sai

Nếu mobile app gặp response shape của web BFF:

1. Kiểm tra public `Host` và path mà Gateway nhận.
2. Kiểm tra route ID thực tế đã chọn, default/route filters và route order.
3. Kiểm tra backend service `mobile-bff` hay `web-bff` đã nhận call.
4. Kiểm tra cache key, CDN/Ingress rewrites và route refresh revision.
5. Kiểm tra app version/contract tests.

Không đoán bằng HTTP 200: cả hai BFF có thể trả 200 nhưng schema hoàn toàn khác.

## 20. Khi nào nên dùng BFF, khi nào một Gateway chung đã đủ?

Mẫu BFF đổi **coupling và ownership** lấy khả năng tối ưu theo frontend. Không nên áp nó như một quy tắc bắt buộc chỉ vì hệ thống có microservices.

| Tình huống | Lựa chọn phù hợp hơn | Lý do |
| --- | --- | --- |
| Một frontend, ít endpoints, payload hầu như giống API domain | Có thể dùng Gateway + domain services | Tránh deploy thêm service chỉ để proxy |
| Web và mobile cùng một contract, chỉ khác CSS/layout | Thường chưa cần BFF riêng | Frontend tự định dạng, backend không phình to |
| Browser cần OAuth confidential client, token không vào JS | **Browser BFF** hợp lý | Session cookie + server-side token management |
| Mobile cần DTO gọn, gom 4–5 requests thành một | **Mobile BFF** đáng cân nhắc | Giảm RTT/băng thông phía client |
| Backoffice có RBAC/MFA/audit/export khác khách hàng | **Admin BFF** riêng đáng cân nhắc | Tách phạm vi quyền và chu kỳ thay đổi |
| Public API dùng chung nhiều bên thứ ba | API Gateway + versioned general API | Không ép tất cả partners theo UI-specific DTO |
| Frontend đã dùng GraphQL với resolver chọn fields đúng | Đánh giá trước khi thêm BFF | Có thể có lợi ích tương tự, nhưng vẫn cần auth/security |
| BFF chỉ làm pass-through cùng một URI, không shaping/auth riêng | Cân nhắc dùng Gateway route trực tiếp | Giảm một network hop |
| Nhiều frontend teams độc lập release cùng backend | BFF per experience/team | Giảm tranh chấp contract chung |

### 20.1. Chi phí mới do BFF tạo ra

Mỗi BFF mới cần:

- Build, CI/CD, vulnerability scanning, dependency patching.
- DNS/service discovery, TLS/mTLS, secrets và network policies.
- On-call, logs/traces/metrics, SLO và capacity planning.
- API contracts, backward compatibility, canary/rollback.
- Security review cho OAuth/session/bearer token.
- Testing data aggregation, retries/fallback và user-specific caching.

Nếu những chi phí này lớn hơn lợi ích UX, **không tách chỉ vì tên mẫu thiết kế**. Có thể khởi đầu một BFF module/controller trong application hiện tại, rồi tách deployables khi rõ ranh giới và ownership.

### 20.2. BFF và GraphQL không loại trừ nhau tuyệt đối

GraphQL có thể cho client chọn trường dữ liệu, giảm over-fetching; vì vậy nó đôi khi làm giảm nhu cầu viết BFF DTO riêng. Nhưng:

- GraphQL vẫn cần endpoint auth, query cost/depth/rate limiting, resolver N+1 protection.
- Browser vẫn cần chiến lược OAuth/session/CSRF; GraphQL **không tự bảo vệ tokens**.
- Admin/mobile có quyền và SLO khác nhau dù cùng một GraphQL schema.

Quyết định dựa trên contract/ownership/threat model, không dựa vào “GraphQL hoặc BFF” như một lựa chọn nhị phân.

## 21. Migration từ API chung sang BFF

Giả sử hiện tại mọi client gọi:

~~~text
https://api.example.test/api/orders/{id}
https://api.example.test/api/catalog/items
https://api.example.test/api/profile/me
~~~

Mục tiêu mới:

~~~text
https://web.example.test/bff/orders/{id}
https://mobile.api.example.test/v1/home
https://admin.api.example.test/admin/audit/events
~~~

Không nên chuyển toàn bộ traffic trong một lần. Một kế hoạch từng bước:

### 21.1. Bước 1 — Lập bản đồ client và contract

- Thu thập request patterns theo **loại client hợp lệ** từ analytics/telemetry đã được phê duyệt.
- Ghi rõ endpoints, method, authentication flow, scopes, payload sizes, p95/p99, app versions.
- Phân loại dữ liệu public/private/regulated, business operations, caching policy.
- Xác định endpoints đang chịu over-fetching hoặc chatty network calls.
- Xác định teams ownership và on-call của từng frontend.

Không phân nhóm users bằng header `X-Client-Type` do client tự khai như thể nó đã xác minh; dùng identifiers/release channels có nguồn tin cậy và không lưu token/PII trong logs.

### 21.2. Bước 2 — Tách web/mobile/admin BFF tối thiểu

1. Chọn một use case có lợi ích rõ, ví dụ mobile home aggregation.
2. Tạo DTO và endpoint mới ở mobile-bff, không copy business logic domain.
3. Public edge thêm route mới **không chồng lấn** route cũ.
4. BFF xác thực đúng loại client, domain services vẫn xác minh quyền.
5. Thêm contract tests và negative auth tests trước khi có client thật.

### 21.3. Bước 3 — Chuyển traffic theo nhóm

- Canary 1%→10%→50%→100% hoặc rollout theo app release cohort được xác định.
- Giữ route cũ trong khoảng backward-compatibility cần thiết.
- Theo dõi route selection, BFF/underlying service errors, p99, cache/fan-out và user outcomes.
- Không route fallback lén về một backend khác khi token/scopes không tương thích.
- Có rollback route revision và kiểm tra cả DNS/TLS/Host/forwarding chain.

### 21.4. Bước 4 — Đổi authentication đúng lớp

Đối với browser web:

- Không chuyển token từ localStorage sang session bằng cách chỉ đổi header tại Gateway. Cần thiết kế **authorization code confidential-client login**, session, CSRF, refresh/logout.
- Dùng `TokenRelay` nếu web BFF sử dụng Gateway route tới resource server và OAuth2 client được cấu hình phù hợp.
- Xác minh token audience của downstream; nếu khác, dùng token exchange.

Đối với mobile:

- Giữ Authorization Code/PKCE flow của native public client hoặc chiến lược được phê duyệt, không copy session cookie browser chỉ để “đồng nhất”.
- Kiểm tra các app versions cũ vẫn có API hỗ trợ trong transition.

Đối với admin:

- Thêm SSO/MFA/step-up auth, action-level scopes và audit của admin BFF trước khi dời chức năng.
- Không chỉ chuyển URL từ `/api/admin/**` sang `/admin/**` rồi coi đã an toàn.

### 21.5. Bước 5 — Loại bỏ API cũ có kiểm soát

Chỉ loại bỏ route cũ khi:

- Không còn clients đang phụ thuộc (hoặc đã công bố end-of-support).
- Không có auth/identity bypass qua route cũ.
- Contract/observability reports đã xác nhận các luồng web/mobile/admin mới.
- Có fallback/rollback chính thức không làm rò quyền.
- TTL caches/DNS/session và CDN behavior được tính đến.

**Điểm dễ bỏ sót:** một app mobile đã phát hành trên store có thể còn chạy nhiều tháng. Không assume tất cả clients cập nhật đồng thời như web SPA.

## 22. Troubleshooting BFF routing và security

| Triệu chứng | Nguyên nhân có thể | Bước kiểm tra |
| --- | --- | --- |
| Web OAuth login redirect sang `/login` thiếu `/web` | Path-based StripPrefix + public base URL sai | Redirect URI, Forwarded-Prefix, cookie Path, use host-based |
| OAuth callback bị 404 | Gateway không route `/login/oauth2/code/**` đến web BFF | Host route predicates, route inventory, IdP redirect allowlist |
| Browser session không bền giữa replicas | WebSession/authorized client in-memory hoặc cookie key không ổn định | Session store, token persistence, sticky/Redis policy |
| POST web BFF trả 403 | CSRF token vắng/mismatch | Cookie/token repository, header, Origin/SameSite, không tắt CSRF mù |
| Login thành công nhưng downstream 401 | TokenRelay chưa có OAuth2 client config hoặc token audience sai | Authorized client, TokenRelay factory, JWT audience |
| Mobile request có bearer nhưng 401 | Wrong issuer/JWKS/audience/expired token | JWT decoder, public client PKCE, scopes |
| Mobile request 403 | Thiếu `SCOPE_mobile.read/write` | Authority mapping/route policy |
| Admin Host đúng nhưng bị 403 | Admin BFF thiếu authority hoặc MFA policy | SecurityWebFilterChain, IdP roles, resource permission |
| Admin Host giả vẫn route tới admin | Host predicate không xác thực client | Kiểm tra RBAC/MFA/network, không chỉ Host |
| BFF sai trả 200 | Host/Path route overlap, fallback rộng | Response marker, backend stub, route order |
| `StripPrefix=1` bỏ quá nhiều path | Prefix path khác thiết kế hoặc rewrite nhiều lần | RecordedRequest path và filter list |
| Mobile GET `/v1/home` trả 502 | Một upstream catalog unreachable | HTTP client logs, DNS, timeouts, fan-out |
| Mobile payload quá lớn | Trả nguyên domain DTO | DTO shaping, bytes/response, contract tests |
| p99 tăng sau thêm BFF | Thêm hop, fan-out lớn, pool/GC, retries | Traces, downstream attempts, p99 per use case |
| Public catalog bị cache sai | Cache keys/Vary/TTL không phù hợp | ETag, Cache-Control, CDN, user-specific variants |
| User A thấy dữ liệu user B | Cache key theo path hoặc bypass authorization | Tắt cache nguy hiểm, audit authz, tenant tests |
| Admin audit mất sự kiện | BFF fallback che downstream errors | Fail-closed policy, audit pipeline, SLO |
| Browser `fetch` bị CORS block | Cross-origin + credentials config sai | Origin allowlist, preflight, SameSite, actual GET |
| Mobile X-App-Type đổi mà access cũng đổi | Dùng client-controlled header để phân quyền | Tách route metadata với verified principal |
| Cookie bị gửi sang subdomain ngoài ý muốn | Domain cookie quá rộng | Host-only cookie, Secure/HttpOnly/SameSite |
| TokenRelay hoạt động một node, lỗi node khác | Authorized-client store không chia sẻ | Token/session persistence, replica routing |
| Header `X-User-Id` giả đến downstream | Route default filter không áp hoặc direct access | Edge scrub, Gateway effective filters, network |
| `/actuator/gateway/routes` không thấy BFF host route | Sai config prefix/starter, routes chỉ trong profile khác | BOM, active profile, effective runtime routes |
| Test chỉ trả 404 khi Host sai nhưng vẫn rò data | Có controller/fallback khác hoặc backend trực tiếp | Recorded backend calls, security tests |

### 22.1. Quy trình gỡ lỗi theo thứ tự

1. **Xác định loại client** đang gọi và yêu cầu nghiệp vụ/authorization thật.
2. **Quan sát public request**: scheme, Host, path, method, Origin và auth mode.
3. **Xác nhận Gateway route** được materialize đúng version/prefix và route ID được chọn.
4. **Xác nhận BFF target** bằng backend request capture, không chỉ status 200.
5. **Kiểm tra security** ở BFF: cookie session/CSRF hay bearer JWT/scopes/audience?
6. **Kiểm tra downstream**: resource server token audience, domain permissions, fan-out count.
7. **Phân tích response/cache**: DTO đúng giao diện, không lộ trường private, Vary/ETag hợp lý.
8. **Kiểm tra metrics/tracing**: p95/p99 theo route/use case, retries/timeouts.
9. **Kiểm tra topology**: edge forward headers, DNS/TLS, service discovery, NetworkPolicy.
10. **Chạy regression suite** với các ca web/mobile/admin đúng/sai trước khi rollout.

Đừng sửa Host/path bug bằng cách đặt `Path=/**` cho tất cả BFF, hoặc sửa 401 bằng cách xóa hết Spring Security. Những thay đổi đó có thể biến một lỗi định tuyến thành lỗ hổng cross-client authorization.

## 23. Checklist triển khai BFF theo loại ứng dụng

### 23.1. Thiết kế và routing

- [ ] Phân biệt rõ **Gateway chung**, **BFF theo trải nghiệm** và **domain services**.
- [ ] Có tiêu chí định lượng lý do tách BFF: khác contract, session/auth, SLO, team ownership.
- [ ] Quy hoạch Host/Path rõ; nếu browser BFF giữ OAuth callback, ưu tiên same-origin/host-based.
- [ ] Route IDs duy nhất, order rõ, không có fallback wildcard nhận nhầm admin/mobile.
- [ ] Test đúng namespace Gateway WebFlux 4.x hoặc 5.x; không ghép hai phiên bản.
- [ ] Chỉ thêm `StripPrefix/RewritePath` khi downstream contract cần; recorded path tests PASS.
- [ ] Kiểm tra `Host` predicate **không được dùng như authentication**.
- [ ] Không route theo `X-Admin`, `X-Client-Type` hoặc User-Agent do client tự khai để bỏ qua security.
- [ ] Có network isolation để clients không bypass Gateway/BFF qua port nội bộ.
- [ ] Public DNS/TLS/SNI, forwarded host/proto và proxy trust được kiểm tra ở ingress thật.

### 23.2. Browser/Web BFF

- [ ] OAuth confidential client chạy phía server; access/refresh tokens không lộ cho browser JS.
- [ ] Có session cookie `Secure`, `HttpOnly`, `SameSite`, `Path`, host scope và TTL đúng.
- [ ] CSRF được bảo vệ với mọi state-changing browser requests, cả khi có subdomains same-site.
- [ ] OAuth redirect/callback giữ public Host/scheme/prefix sau reverse proxy.
- [ ] `TokenRelay` chỉ bật khi OAuth2 client registration và authorized client đúng.
- [ ] Access token chuyển downstream phải có đúng audience/scope; token exchange nếu cần.
- [ ] Multi-replica token/session storage, logout/invalidation/rotation được test.
- [ ] Không cache private cart/orders cho người khác; response headers phù hợp.
- [ ] UI static assets và login endpoints có allowlist; private `/bff/**` đòi authentication.

### 23.3. Mobile BFF

- [ ] Native OAuth client dùng Authorization Code/PKCE theo chính sách nền tảng.
- [ ] BFF Resource Server xác minh issuer/signature/expiry/audience và scopes.
- [ ] Không copy cookie/CSRF policy của web một cách máy móc sang bearer-only APIs.
- [ ] Mobile DTO nhỏ, phân trang/cursor/versioning theo app release còn hỗ trợ.
- [ ] Có timeout, max fan-out, cache/ETag và retry idempotent với mạng yếu.
- [ ] Không dùng `X-Device-Id` hoặc `X-App-Version` làm verified identity.
- [ ] Test backward compatibility với những app releases có thể còn hoạt động.

### 23.4. Admin BFF

- [ ] SSO/MFA/step-up theo mức nhạy cảm và scopes/roles theo từng action.
- [ ] Không có wildcard `/admin/**` được `permitAll()` ngoài ý muốn.
- [ ] Domain services kiểm tra quyền tài nguyên/tenant; BFF không tự cấp role từ headers.
- [ ] CSRF cho browser-cookie admin, khác bearer-only endpoints.
- [ ] Audit đầy đủ cho refund, disable, export, data reads nhạy cảm.
- [ ] PII masking/export limits, no-store, resource ownership và network isolation.
- [ ] Có negative tests admin token thiếu scope và Host giả từ Internet.

### 23.5. Vận hành và chất lượng

- [ ] HTTP routing tests với backend stub xác nhận đúng BFF và route marker.
- [ ] Security tests riêng cho authn/authz, CSRF/CORS, direct access và header spoofing.
- [ ] Mỗi BFF có SLO, dashboards, alerts, on-call, rollback plan.
- [ ] Fan-out/request, downstream retries, p95/p99 và cache hit rates được đo.
- [ ] Không dùng raw JWT/cookie/user ID/tenant ID làm metric labels.
- [ ] Dynamic routes được phê duyệt, URI allowlist/SSRF checks và revision audit.
- [ ] Có canary theo app version/route ID, tránh rollback thay đổi sai audience.
- [ ] Không chạy unit/integration tests trên Internet backend thật; dùng cổng ngẫu nhiên.
- [ ] CI xác nhận **số tests thực thi**, không chấp nhận build xanh nhưng 0 tests.
- [ ] Mọi thay đổi API đáp ứng cả contract và security backward compatibility.

## 24. Bài tập thực hành

### Bài 1 — Thiết kế routes cho bốn loại client

Hệ thống có browser, mobile, admin và partner API. Hãy đề xuất:

- Một Host/Path namespace cho từng loại.
- Route predicates, IDs, order và BFF upstream targets.
- Security policy của từng service.
- Header nào phải bị scrub ở edge/Gateway.
- Kiểm thử 4 positive và ít nhất 8 negative requests.

**Gợi ý:** Partner API không nhất thiết là “BFF của đối tác”; có thể là public API với contract ổn định. Đừng gộp partner vào mobile BFF chỉ vì cả hai dùng bearer token.

### Bài 2 — Từ path-based lab chuyển sang host-based

Đang có:

~~~text
GET /web/whoami    → port 9081 /whoami
GET /mobile/whoami → port 9082 /whoami
GET /admin/whoami  → port 9083 /whoami
~~~

Hãy viết lại bằng:

~~~text
Host=web.example.test        GET /whoami
Host=mobile.api.example.test GET /v1/whoami
Host=admin.api.example.test  GET /admin/whoami
~~~

Cập nhật stub mappings và tests. Chứng minh **không còn cần StripPrefix**, hostname lạ không có route và mobile Host không thể chọn admin backend. Thảo luận vì sao giả Host thành admin **không** đủ để tạo quyền quản trị.

### Bài 3 — Tự xây web BFF có đăng nhập

Trên một IdP thử nghiệm:

1. Đăng ký OAuth2 confidential client với redirect URI đúng public hostname.
2. Cấu hình `oauth2Login` và `SecurityWebFilterChain` bảo vệ `/bff/**`.
3. Cấu hình `TokenRelay=` cho một route tới resource server thử nghiệm.
4. Đọc network trace trong browser để xác nhận **không có access/refresh token trong JS/localStorage**.
5. Kiểm tra session cookie và CSRF khi POST.
6. Test logout, expired session và một request thiếu/giả CSRF token.

Không dùng production IdP/real tokens trong bài tập; dùng tài khoản/issuer test và chặn log raw secrets.

### Bài 4 — Mobile home aggregation và fallback có chủ đích

Từ ví dụ `MobileHomeController`:

- Thêm optional recommendations API thứ ba.
- Nếu recommendations timeout, trả mảng rỗng **chỉ** cho trường optional.
- Nếu price/authorization API lỗi, không fallback thành dữ liệu giả.
- Benchmark thời gian hai calls tuần tự và song song trên local stub.
- Giới hạn concurrency và ghi metric downstream attempts.
- Kiểm thử response shape không chứa internal fields.

### Bài 5 — Bảo vệ admin BFF trước Host giả và token sai

Tạo test:

~~~http
GET /admin/audit/events HTTP/1.1
Host: admin.api.example.test
Authorization: Bearer <token-aud-mobile>
X-Is-Admin: true
~~~

Kỳ vọng admin BFF **từ chối** vì token không có audience/scope phù hợp, dù Gateway Host predicate match. Thêm một test with proper admin token nhưng thiếu `SCOPE_admin.audit.read` và một test đủ scope. Verify backend không nhận requests bị từ chối.

### Bài 6 — Kiểm thử data leak từ cache

Tạo response private có `customerName` khác nhau cho hai test users. Bật một cache thử nghiệm rồi chứng minh:

1. Request user A không làm user B nhìn thấy DTO của A.
2. Cache key/tenant policy đúng.
3. Header `Cache-Control` phù hợp khi trả private data.
4. Logout/permission changes xử lý cache hợp lệ.

Nếu chưa chứng minh được bốn điều kiện trên, **không bật cache cho private data** để chỉ giảm latency.

### Bài 7 — Lập migration plan có rollback

Giả sử một app mobile v1 còn 20% traffic và v2 bắt đầu dùng `/v2/home`. Viết kế hoạch:

- Route/version compatibility matrix.
- Canary cohorts, telemetry, SLOs.
- Biện pháp phòng dữ liệu/scope leak giữa v1/v2.
- Cache invalidation và rollback.
- Thời điểm đủ điều kiện deprecate v1 và cách thông báo tới client teams.

Không giả định người dùng sẽ cập nhật native app cùng ngày phát hành.

## 25. Câu hỏi tự kiểm tra

**1. BFF có phải một GatewayFilterFactory của Spring Cloud Gateway không?**

Không. BFF là **mẫu kiến trúc** tạo backend chuyên biệt theo frontend; Spring Cloud Gateway là công cụ có thể dùng để định tuyến đến BFF hoặc triển khai một BFF thiên về proxy.

**2. Vì sao cần web BFF riêng khi mobile API đã tồn tại?**

Nếu web cần cookie session/OAuth confidential client và DTO theo trang, trong khi mobile dùng public OAuth client + PKCE và payload gọn, hai phía có threat model/contract khác. Nhưng nếu mọi API giống nhau, chưa chắc cần tách hai deployables.

**3. Định tuyến bằng `Host=admin.api.example.test` có tự cấp quyền admin không?**

Không. Client có thể tự gửi Host trong một số môi trường; route predicate không thay JWT validation, SSO/MFA, RBAC hay domain resource authorization.

**4. Browser OAuth BFF nên lưu access token ở đâu?**

Trên **server-side BFF/session store bảo vệ phù hợp**, không trả token cho JavaScript. Browser nhận session cookie an toàn, còn BFF dùng token đúng audience khi gọi resource server.

**5. `TokenRelay=` có biến mọi access token thành token phù hợp downstream không?**

Không. Nó relay token theo OAuth authorized client; resource server vẫn phải kiểm tra audience/scope. Nếu audience khác, cần token exchange/đăng ký client thích hợp.

**6. Native mobile app có bắt buộc dùng cookie session của browser BFF không?**

Không. Native app thường dùng OAuth Authorization Code + PKCE và bearer token; BFF có thể là Resource Server. Nếu dùng cookie thì cần threat model/CSRF policy tương ứng, không copy máy móc.

**7. Vì sao path-based `/web/**` đôi khi làm OAuth login hỏng?**

Do `StripPrefix` biến downstream path, trong khi redirect URI, cookie Path và public scheme/Host vẫn cần khớp đường người dùng nhìn thấy. Host-based routing dễ tránh lớp rewrite này.

**8. Vì sao admin BFF có thể cần riêng service?**

Vì có quyền/PII/audit/MFA và nhịp phát hành khác web/mobile. Tuy nhiên quyền thực thi phải được kiểm tra tại BFF **và** domain services.

**9. Một endpoint mobile dùng `Mono.zip` hai upstreams có chắc nhanh gấp đôi không?**

Không. Nó có thể giảm RTT từ client và song song downstream calls, nhưng còn latency lớn nhất của upstreams, connection pool, CPU, fan-out và error handling. Cần đo p95/p99 trên workload đại diện.

**10. Vì sao không cache user-specific response theo path đơn thuần?**

Vì cùng path có thể trả dữ liệu khác nhau theo principal/tenant. Cache không có phạm vi danh tính đúng có thể khiến người dùng thấy dữ liệu của nhau.

**11. BFF có thay đổi business transaction của microservices không?**

Không nên. BFF tạo DTO/orchestrate calls theo trải nghiệm; domain service sở hữu business rules, trạng thái/transactions và authorization tài nguyên.

**12. Khi positive test trả 200 nhưng sai BFF, cần xem gì?**

Xem effective Host/Path, Gateway route ID/order, backend request capture và fallback routes. Một status 200 không chứng minh request đã đi đúng nơi.

**13. CORS có đủ bảo vệ browser BFF không?**

Không. Cookie session cần CSRF protection; CORS chỉ là browser policy, không thay authentication hay ngăn native/curl clients.

**14. Khi nào một Gateway dùng chung là đủ?**

Khi client contracts gần giống nhau, không cần session/auth riêng hoặc data shaping đáng kể, và BFF chỉ thêm pass-through/network hop. Quyết định phải xét cost vs benefit.

## 26. Tài liệu tham khảo

1. [Microsoft Azure Architecture Center — Backends for Frontends Pattern](https://learn.microsoft.com/en-us/azure/architecture/patterns/backends-for-frontends): định nghĩa BFF, vấn đề single backend cho nhiều frontend, quyền sở hữu theo UI, trade-off deployment và ví dụ mobile/web.
2. [RFC 10017 — OAuth 2.0 for Browser-Based Applications](https://www.rfc-editor.org/rfc/rfc10017.html): Best Current Practice 2026; định nghĩa OAuth BFF confidential client, cookie session, token server-side, CSRF/XSS và outbound proxy restrictions.
3. [Spring Cloud Gateway Server WebFlux 5.0 — Route Predicate Factories](https://docs.spring.io/spring-cloud-gateway/reference/5.0/spring-cloud-gateway-server-webflux/request-predicates-factories.html): `Host`, `Path`, `Method`, AND giữa predicates, URI template.
4. [Spring Cloud Gateway WebFlux 4.2 — Route Predicate Factories](https://docs.spring.io/spring-cloud-gateway/reference/4.2/spring-cloud-gateway/request-predicates-factories.html): đối chiếu namespace `spring.cloud.gateway.routes` và contract 4.x.
5. [Spring Cloud Gateway Server WebFlux — TokenRelay GatewayFilter](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/gatewayfilter-factories/tokenrelay-factory.html): OAuth2 Client registration, `TokenRelay=` và authorized client storage.
6. [Spring Cloud Gateway Server WebFlux — StripPrefix GatewayFilter](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/gatewayfilter-factories/stripprefix-factory.html): đổi path sau route match.
7. [Spring Cloud Gateway Server WebFlux — Spring Security Integration](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/spring-security.html): SecurityWebFilterChain, OAuth2 client/resource server integration.
8. [Spring Security — Reactive OAuth2 Login](https://docs.spring.io/spring-security/reference/reactive/oauth2/login/index.html): OAuth login với Spring WebFlux.
9. [Spring Security — WebFlux CSRF](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html): token repository và cookie/header CSRF protection.
10. [Spring Security — Reactive OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html): JWT validation với WebFlux.
11. [Spring Security — Reactive Authorization](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html): authorization rules theo request và principal.
12. [Spring Framework — WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html): reactive HTTP client và request/response composition.
13. [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html): test Gateway HTTP response và assertions.
14. [OkHttp MockWebServer](https://square.github.io/okhttp/features/mockwebserver/): upstream stubs, recorded requests và test downstream call counts.
15. [OWASP — API Security Top 10 (2023)](https://owasp.org/API-Security/editions/2023/en/0x11-t10/): object-level authorization, resource exhaustion, SSRF và API security.

**Ghi nhớ:** **Backend for Frontend** không chỉ là thêm một route theo `X-Client-Type`. Nó là quyết định tách **hợp đồng dữ liệu, mô hình authentication/session và quyền sở hữu triển khai** theo web, native mobile hoặc admin. Dùng Spring Cloud Gateway để route bằng **Host/Path đã thiết kế**, giữ browser OAuth BFF tokens phía server, cho native mobile BFF xác minh bearer/PKCE đúng cách và bảo vệ admin BFF bằng MFA/RBAC/resource authorization. Một BFF tốt giúp frontend nhận **đúng dữ liệu với ít lượt gọi hơn**, nhưng vẫn phải giữ domain services làm nguồn sự thật, kiểm soát fan-out/cache/timeout, và chứng minh bằng **routing tests lẫn security tests** rằng không có đường nhầm sang BFF khác hoặc lộ dữ liệu xuyên người dùng.
