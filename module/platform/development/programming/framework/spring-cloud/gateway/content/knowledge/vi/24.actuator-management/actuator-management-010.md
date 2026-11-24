# Phân quyền, kiểm toán và phục hồi khi thay đổi tuyến thất bại

## 1. Bối cảnh: thay đổi một route có thể làm hỏng cả cổng vào

Trong kiến trúc microservices, **Spring Cloud Gateway** tập trung route predicate, filter chain, biến đổi đường dẫn/header, service discovery, xác thực, giới hạn lưu lượng, circuit breaker, retry, TLS và khả năng quan sát request. Nhờ **Spring Boot Actuator**, đội vận hành có thể xem route đang hoạt động và, khi được cấp quyền, tạo, xóa hoặc làm mới route mà không cần khởi động lại tiến trình.

Điều này rất hữu ích nhưng cũng có rủi ro lớn. Giả sử route `orders-api` đang chuyển:

~~~text
GET /api/orders/42
  -> Spring Cloud Gateway
  -> lb://ORDER-SERVICE
  -> GET /orders/42
~~~

Một người vận hành vô tình đổi URI thành một host không đúng, đổi `StripPrefix`, đặt `Path=/api/**` quá rộng hoặc sử dụng filter chưa được cài trên một replica. Hệ quả có thể là:

- API hợp lệ trả `404`, `502` hoặc `503` hàng loạt.
- Request đi tới dịch vụ sai, có thể gây rò rỉ header `Authorization` hoặc dữ liệu khách hàng.
- Các Gateway replicas giữ những route cache khác nhau, khiến lỗi xuất hiện không ổn định.
- Một thao tác sửa route qua Actuator đã trả HTTP thành công nhưng quá trình refresh bất đồng bộ lỗi.
- Đội vận hành không biết **ai sửa, sửa gì, trước đó route thế nào**, nên rollback chậm hoặc không chính xác.

Bài thuộc chương **Quản trị Actuator** của module **SPRING_CLOUD_GATEWAY**, với chủ đề **phân quyền, kiểm toán và phục hồi khi thay đổi tuyến thất bại**. Mục tiêu là xây dựng quy trình quản trị có kiểm soát chứ không chỉ học một lệnh `curl` để thêm/xóa route.

Sau bài này, bạn sẽ:

1. Phân biệt ba lớp: **Actuator endpoint access**, **HTTP exposure** và **authentication/authorization/network access**.
2. Thiết kế quyền **viewer, operator, approver, automation** theo nguyên tắc least privilege.
3. Ghi nhận audit trail có **actor, thời điểm, diff, revision, approval, kết quả refresh và rollback**.
4. Hiểu giới hạn CRUD/refresh qua `/actuator/gateway`, đặc biệt với nhiều Gateway replicas.
5. Xử lý lỗi route không hợp lệ, route bị xóa nhầm, thay đổi chưa được áp dụng hoặc được áp dụng một phần.
6. Thiết kế **validate → stage → publish → refresh → verify → rollback/reconcile** có thể kiểm thử.
7. Giữ an toàn TLS, token, secret, Redis và các upstream khi Gateway được quản trị động.

> **Phạm vi:** tập trung vào **Spring Cloud Gateway Server WebFlux**, Spring Boot Actuator và Spring Security reactive. Ví dụ property/mã cần được kiểm tra theo Spring Boot/Spring Cloud release train đang chạy. **Gateway Server MVC** dùng stack khác; không dùng nguyên `SecurityWebFilterChain` của WebFlux cho MVC. Đây là bài hướng dẫn thiết kế và kiểm thử; chưa thay thế Content QA chuyên môn của bước sau.

## 2. Mối đe dọa: endpoint quản trị route không phải API thông thường

Một API nghiệp vụ `GET /api/orders/42` trả dữ liệu được kiểm soát bởi các route, security filters và backend authorization. Còn quyền `POST /actuator/gateway/routes/{id}` có thể **thay đổi chính tuyến đường** mà request nghiệp vụ sẽ đi qua.

Các hành động quản trị nguy hiểm:

| Hành động | Rủi ro điển hình | Mức quyền nên yêu cầu |
| --- | --- | --- |
| Xem danh sách route | Lộ tên upstream, host/port nội bộ, tên filter/metadata | Viewer đã xác thực hoặc truy cập quản trị có kiểm soát |
| Xem một route cụ thể | Lộ cấu trúc predicate, rewrite, service mapping | Viewer |
| Thêm route | Công khai service nội bộ, định tuyến sang host sai | Operator có quyền ghi, qua validation |
| Xóa route | Dừng truy cập API hợp lệ | Operator qua change workflow |
| Refresh cache | Tạo đột biến cấu hình; reload lỗi, tăng tải | Operator hoặc automation được cấp quyền |
| Sửa nhóm route | Mismatch policy giữa các API | Người có quyền release, quy trình duyệt |
| Thay route xác thực | Bypass auth hoặc lộ credential nếu thiết kế sai | Thay đổi nhạy cảm, xét duyệt nâng cao |

Đe dọa không chỉ đến từ attacker bên ngoài. Một script CI có credential quá rộng, người trực ca sửa nhầm route ID hoặc quản trị viên dùng sai môi trường đều có thể gây outage. Vì vậy cần **phân quyền + kiểm toán + phục hồi**, và cần thiết kế cả phòng ngừa lẫn phản ứng khi sai.

### 2.1. Luồng quản trị an toàn

~~~mermaid
flowchart TD
    U["Operator / CI-CD"] --> I["Identity / RBAC / MFA"]
    I --> CP["Control plane quản lý route"]
    CP --> V{"Schema + policy + approval hợp lệ?"}
    V -->|Không| DENY["Từ chối và audit denied"]
    V -->|Có| SNAP["Chụp snapshot + revision hiện hành"]
    SNAP --> SAVE["Lưu candidate / route definitions"]
    SAVE --> EVT["Phát sự kiện refresh tới các Gateway replicas"]
    EVT --> VERIFY{"Kiểm chứng route đã áp dụng?"}
    VERIFY -->|Có| OK["Audit applied + monitoring"]
    VERIFY -->|Không| ROLLBACK["Khôi phục snapshot tốt + refresh + verify"]
    ROLLBACK --> AUD["Audit failure và rollback"]
~~~

**Control plane** và các bước approval/rollback trong sơ đồ là kiến trúc cần tự triển khai hoặc dùng hệ thống tổ chức hiện có; chúng **không phải chức năng tự động mà Gateway Actuator cấp sẵn**.

## 3. Actuator Gateway có những API quản trị nào?

Một số endpoint đặc trưng của Spring Cloud Gateway Server WebFlux:

| HTTP | Endpoint | Mục đích | Khuyến nghị |
| --- | --- | --- | --- |
| `GET` | `/actuator/gateway` | Liệt kê các thao tác khả dụng | Chỉ trong mạng quản trị |
| `GET` | `/actuator/gateway/routes` | Xem các effective routes | Cho viewer có quyền |
| `GET` | `/actuator/gateway/routedefinitions` | Xem definitions theo implementation/version | Cho viewer có quyền |
| `GET` | `/actuator/gateway/routes/{id}` | Xem route một ID | Cho viewer có quyền |
| `GET` | `/actuator/gateway/globalfilters` | Xem global filters | Cần kiểm soát thông tin |
| `GET` | `/actuator/gateway/routefilters` | Xem filter factories | Cần kiểm soát thông tin |
| `POST` | `/actuator/gateway/routes/{id}` | Tạo route động qua writer | Quyền ghi, validation, audit |
| `DELETE` | `/actuator/gateway/routes/{id}` | Xóa route động | Quyền ghi, approval/rollback |
| `POST` | `/actuator/gateway/refresh` | Yêu cầu refresh route cache cục bộ | Quyền ghi, giới hạn tần suất |
| `POST` | `/actuator/gateway/routes` | Tạo nhiều routes theo API được version hỗ trợ | Quyền ghi, validate toàn bộ batch |

**Không phải route nào cũng có thể xóa bằng Actuator.** Route từ `application.yml` hoặc `@Bean RouteLocator` không tự trở thành một bản ghi có thể sửa/xóa bằng `RouteDefinitionWriter`. Tài liệu Gateway 5.x nêu route được quản lý qua Actuator mới được thao tác qua API tương ứng; lệnh xóa route cấu hình tĩnh có thể trả `404`.

Kết quả `GET /actuator/gateway/routes/{id}` thường là dạng hiển thị route đã dựng; **không lấy nguyên output GET làm JSON POST**. API tạo route dùng dạng predicate/filter shortcut như `"Path=/api/orders/**"`, `"StripPrefix=1"` hoặc schema được tài liệu version yêu cầu.

### 3.1. Quyền quản trị không tương đương quyền sử dụng API

Một user được phép gọi `GET /api/orders/**` với `SCOPE_orders.read` **không** có nghĩa có quyền xem hoặc sửa `/actuator/gateway/routes`. Ngược lại, một route operator có thể không được phép đọc đơn hàng khách hàng.

Nên dùng **principal/roles/scopes riêng** cho management API, không lấy quyền của frontend/user thông thường để quyết định route admin.

## 4. Ba lớp bắt buộc để bảo vệ Gateway Actuator

### 4.1. Lớp 1: endpoint access

Ở các nhánh Spring Boot/Gateway mới, `management.endpoint.gateway.access` có giá trị quan trọng:

| Giá trị | Hành vi mong muốn | Dùng khi nào |
| --- | --- | --- |
| `none` | Không cho phép truy cập gateway Actuator endpoint | Môi trường không cần quản trị route HTTP |
| `read-only` | Chỉ cung cấp thao tác đọc; không cho create/delete/refresh | **Mặc định khuyến nghị khi cần quan sát** |
| `unrestricted` | Cho phép cả thao tác quản trị mà endpoint hỗ trợ | Chỉ sau khi có network/auth/RBAC/audit |

Theo tài liệu **Spring Cloud Gateway hiện hành**, Gateway Actuator endpoint **bị tắt truy cập theo mặc định**. Khi cần quan sát, phải cho quyền đọc và expose endpoint tương ứng. Khi muốn tạo, xóa hoặc refresh route, cần mức quyền cao hơn và phải bảo vệ chặt.

Một số bản cũ có property `management.endpoint.gateway.enabled`. Không bật cả những property cũ/mới một cách tùy tiện rồi giả định ưu tiên; hãy dùng cấu hình đúng release train.

### 4.2. Lớp 2: exposure qua HTTP/JMX

Ngay cả khi endpoint được phép truy cập, nó chỉ có mặt ở bề mặt HTTP khi được expose theo cấu hình:

~~~yaml
management:
  endpoint:
    gateway:
      access: read-only
  endpoints:
    web:
      exposure:
        include: health,info,gateway
~~~

Đây là **cấu hình quan sát-only**, không phải cấu hình bảo mật mạng hay cấp quyền cho mọi user. Trên Spring Boot thông thường chỉ một số endpoint như `health` được expose mặc định; cần kiểm tra effective configuration của ứng dụng.

Cẩn thận khi cấu hình:

~~~yaml
# KHÔNG KHUYẾN NGHỊ production công khai:
management:
  endpoints:
    web:
      exposure:
        include: "*"
~~~

Dấu `*` trong YAML phải được trích dẫn. Expose toàn bộ actuator có thể lộ `env`, `beans`, `loggers`, `heapdump` hoặc những khả năng nhạy cảm khác tùy ứng dụng. **Không mở toàn bộ chỉ để dùng một endpoint Gateway**.

Ngoài HTTP exposure, cần xem **JMX exposure** và access permissions nếu hạ tầng có thể truy cập JMX. Việc khóa HTTP không mặc nhiên kiểm soát mọi giao diện quản trị.

### 4.3. Lớp 3: network + authentication + authorization

`access: unrestricted` **không đồng nghĩa chỉ admin mới gọi được**. Nó chỉ cho phép thao tác có sẵn; ai có thể gọi còn phụ thuộc vào:

- Network policy, firewall, ingress/service mesh.
- TLS/mTLS và xác minh client identity.
- Spring Security `SecurityWebFilterChain` hoặc bảo vệ ở reverse proxy/control plane.
- RBAC theo HTTP method/endpoint/route ID.
- Chính sách duyệt thay đổi và khóa credential.
- Rate limiting/abuse protection đối với endpoint quản trị.
- Audit log được bảo vệ.

Tương tự, `read-only` ngăn thao tác thay đổi qua endpoint nhưng vẫn có thể **lộ topology** nếu ai cũng xem được danh sách routes.

**Ba lớp là đồng thời cần thiết, không phải lựa chọn một trong ba.**

## 5. Cấu hình mặc định an toàn cho quan sát

Một cấu hình tham khảo cho Gateway dùng Spring Boot 3.5/SCG WebFlux tương thích:

~~~yaml
management:
  endpoint:
    gateway:
      access: read-only
    health:
      show-details: never
  endpoints:
    web:
      exposure:
        include: health,info,gateway
~~~

Kỳ vọng:

1. `GET /actuator/gateway/routes` có thể được cung cấp nếu identity/network cho phép.
2. `POST /actuator/gateway/refresh` không được phép theo cấu hình read-only.
3. `POST /actuator/gateway/routes/{id}` và `DELETE` không được phép.
4. `health.show-details: never` hạn chế thông tin chi tiết của health response ở ví dụ.
5. Vẫn cần mạng quản trị tách biệt, xác thực và authorization.

**Không mặc định status khi bị chặn là 403.** Tùy tầng đang chặn, endpoint chưa expose có thể là `404`, method không được phép có thể là `405`, security thiếu token có thể trả `401`, thiếu scope có thể là `403`. Mục tiêu là **không thực hiện hành động**, rồi kiểm tra nguyên nhân theo đúng tầng.

### 5.1. Tách management listener khỏi public Gateway

Spring Boot hỗ trợ cấu hình một port quản trị riêng, ví dụ trong môi trường có quản lý network:

~~~yaml
server:
  port: 8080

management:
  server:
    port: 9090
  endpoint:
    gateway:
      access: read-only
  endpoints:
    web:
      exposure:
        include: health,info,gateway
~~~

Đây là cấu hình **tách port**, không tự tách Internet khỏi mạng nội bộ. Trong Kubernetes, nếu Service/Ingress công khai cả port 9090, endpoint vẫn có thể bị truy cập trái phép.

Có thể bind management listener vào địa chỉ nội bộ/loopback phù hợp deployment, hoặc chỉ expose port qua admin proxy, port-forward và network policy đã kiểm chứng. **Không mặc định `localhost` trong container là máy quản trị viên**. Đừng gộp management port vào public ingress chỉ để thử một lệnh curl.

### 5.2. Khi cần thao tác ghi ở staging

Chỉ trên môi trường quản trị đã được bảo vệ, có thể cấu hình:

~~~yaml
management:
  endpoint:
    gateway:
      access: unrestricted
  endpoints:
    web:
      exposure:
        include: health,info,gateway
~~~

Cần hoàn thành các điều kiện trước khi bật:

- Management port không public, có firewall/NetworkPolicy.
- Xác thực mạnh (OAuth2 access token quản trị, mTLS, service identity hoặc cơ chế tương đương).
- Scope/role chuyên biệt cho read và write.
- Audit trail bền vững, có ticket/revision/approval khi cần.
- Route validation, snapshot và rollback đã chạy thử.
- Không chứa giá trị secret trong request body hoặc response.

**Đừng bật `unrestricted` trên production rồi mới xây bảo mật sau.**

## 6. Phân quyền least privilege cho route management

### 6.1. Ma trận role theo thao tác

| Role/Scope minh họa | Đọc routes | Đề xuất thay đổi | Áp dụng thay đổi | Refresh | Rollback |
| --- | --- | --- | --- | --- | --- |
| `gateway.routes.read` | Có | Không | Không | Không | Không |
| `gateway.routes.propose` | Có | Có, qua control plane | Không | Không | Không |
| `gateway.routes.approve` | Có | Có | Duyệt thay đổi khác người đề xuất | Không trực tiếp | Duyệt khi cần |
| `gateway.routes.write` | Có | Theo workflow | Có, với chính sách giới hạn | Có | Có qua quy trình |
| `gateway.routes.reconcile` | Chỉ dữ liệu cần thiết | Không | Không tạo candidate mới | Có, theo revision đã duyệt | Không tùy ý |

Đây là **mô hình role đề xuất**, không phải danh sách authority Spring Cloud Gateway tạo sẵn. Dùng identity provider/control plane để thực thi, với nguyên tắc **separation of duties** cho thay đổi nhạy cảm.

Đối với công ty có nhiều team, một role write tổng quát vẫn có thể quá rộng. Một operator quản lý `/api/catalog/**` không nhất thiết được sửa route thanh toán hoặc auth service. Cần **route-level authorization** tại control plane: namespace, owner, environment, target URI và loại filter được cho phép.

### 6.2. HTTP method không đủ cho business authorization

Spring Security có thể phân biệt GET/POST/DELETE trên đường Actuator. Tuy nhiên, việc kiểm tra:

- Người này chỉ được sửa routes của **catalog** hay của **orders**?
- Thay đổi làm tăng quyền truy cập thông qua `RemoveRequestHeader` có được phép?
- Tên URI mới có nằm trong allowlist tổ chức?
- Thay đổi cần hai người duyệt không?
- Có đang triển khai production freeze không?

là **policy cấp nghiệp vụ quản trị**, không được bảo đảm chỉ bằng `.hasAuthority("SCOPE_gateway.routes.write")`.

Vì vậy, đối với sản phẩm production, nên dùng **control plane** có validation/RBAC chi tiết và chỉ cho automation identity của control plane truy cập Actuator write trên mạng riêng.

## 7. Ví dụ Spring Security Reactive bảo vệ Actuator

### 7.1. SecurityWebFilterChain theo path và method

Ví dụ sau minh họa cách tách **management chain** khỏi **application API chain** khi cả hai dùng WebFlux. Giả định:

- Admin gọi bằng OAuth2 **Bearer JWT** có authority `SCOPE_gateway.routes.read` hoặc `SCOPE_gateway.routes.write`.
- Issuer, audience, JWK và các điều kiện xác minh token đã được cấu hình đúng.
- Management API thực sự dùng path `/actuator/**` của deployment.
- API được bảo vệ bằng bearer token **stateless**; không dùng cookie/session của browser làm credential admin.

~~~java
package example.gateway.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.util.matcher.PathPatternParserServerWebExchangeMatcher;

@Configuration
@EnableWebFluxSecurity
public class GatewaySecurityConfig {

    @Bean
    @Order(0)
    SecurityWebFilterChain actuatorChain(ServerHttpSecurity http) {
        return http
            .securityMatcher(
                new PathPatternParserServerWebExchangeMatcher("/actuator/**"))
            // Chỉ cân nhắc tắt CSRF vì admin API này dùng Bearer
            // token stateless, không dùng session/cookie browser.
            .csrf(ServerHttpSecurity.CsrfSpec::disable)
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/actuator/health").permitAll()
                .pathMatchers(HttpMethod.GET, "/actuator/gateway/**")
                    .hasAnyAuthority(
                        "SCOPE_gateway.routes.read",
                        "SCOPE_gateway.routes.write")
                .pathMatchers(HttpMethod.POST, "/actuator/gateway/**")
                    .hasAuthority("SCOPE_gateway.routes.write")
                .pathMatchers(HttpMethod.DELETE, "/actuator/gateway/**")
                    .hasAuthority("SCOPE_gateway.routes.write")
                .anyExchange().denyAll()
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }

    @Bean
    @Order(1)
    SecurityWebFilterChain applicationChain(ServerHttpSecurity http) {
        return http
            .csrf(ServerHttpSecurity.CsrfSpec::disable)
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/api/public/**").permitAll()
                .anyExchange().authenticated()
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

**Giới hạn rất quan trọng của ví dụ:**

1. Chưa có policy phân quyền nghiệp vụ theo route ID; scope write cho phép rộng hơn những gì nhiều tổ chức chấp nhận.
2. Chưa khai báo dependency Security hoặc Resource Server, issuer/JWK, kiểm tra `aud`, TLS hay mạng quản trị.
3. Nếu `management.endpoints.web.base-path` hoặc context path được đổi, phải cập nhật matcher.
4. **Khi management port tạo context riêng**, phải kiểm tra những `SecurityWebFilterChain` nào thực sự được áp dụng trên management context của đúng phiên bản Boot. Đừng cho rằng bean ở app context tự bảo vệ mọi HTTP listener trong mọi topology.
5. Vô hiệu hóa CSRF **chỉ có điều kiện** cho API thực sự stateless/Bearer. Nếu management UI có cookie/session browser, cần CSRF protection riêng.
6. Việc tự khai báo `SecurityWebFilterChain` có thể làm Boot **không còn tự áp dụng các quy tắc security Actuator mặc định**. Cần test toàn bộ endpoints, không chỉ `gateway`.
7. Với opaque token/introspection, dùng cấu hình Resource Server `opaqueToken` thích hợp thay `jwt`; ví dụ đang giả định JWT.

Điểm chính là xây security rule rõ ràng và test được, **không dùng một ví dụ Java để khẳng định endpoint đã an toàn nếu chưa kiểm tra listener và request thực tế**.

### 7.2. Vì sao không nên expose Actuator qua route công khai?

Nếu tạo Gateway route:

~~~yaml
# PHẢN VÍ DỤ: không public management bằng route như sau.
- id: expose-admin
  uri: http://localhost:9090
  predicates:
    - Path=/admin/**
  filters:
    - StripPrefix=1
~~~

thì bạn có thể vô tình đưa CRUD/refresh ra public data plane, khiến các cơ chế auth/rate-limit/circuit breaker có quan hệ vòng hoặc dễ cấu hình sai. Thường an toàn hơn khi quản trị qua management network/control plane riêng, có end-to-end authorization và monitoring.

Đừng xem tên đường dẫn `/secret-admin` hoặc `/actuator` là lớp bảo vệ. Security by obscurity không đủ chống gọi API trực tiếp.

## 8. Kiểm toán: phải trả lời được ai, sửa gì, khi nào và kết quả ra sao

**Audit trail** là chuỗi bản ghi có thể kiểm chứng về quá trình thay đổi. Access log chỉ cho biết có một HTTP POST/DELETE tới Actuator; một log như:

~~~text
POST /actuator/gateway/routes/orders-api -> 201
~~~

**không đủ** vì chưa biết người duyệt, snapshot cũ, route mới, sự thành công của refresh trên từng replica hay kết quả rollback.

### 8.1. Các trường audit nên có

| Trường | Tác dụng |
| --- | --- |
| `changeId` | Liên kết proposal, approval, publish, refresh, rollback |
| `actor` | Danh tính đã xác thực (subject/service identity), không lấy header client tùy ý |
| `source` | CI pipeline, operator console, emergency change |
| `environment` | staging/production/region/cluster |
| `routeId` hoặc danh sách routes | Đối tượng thay đổi |
| `action` | CREATE, DELETE, UPDATE, REFRESH, ROLLBACK |
| `reason`/`ticket` | Lý do kinh doanh/kỹ thuật, liên kết change management |
| `approval` | Người phê duyệt hoặc policy tự động hợp lệ |
| `beforeRevision`, `afterRevision` | Xác minh thứ tự và tránh lost update |
| `beforeDigest`, `afterDigest` | Dấu vân tay snapshot đã chuẩn hóa |
| `validationResult` | Policy/schema/security/compatibility pass/fail |
| `storeResult` | Ghi shared source thành công hay không |
| `refreshResults` | Replica nào nhận/áp dụng, thất bại ở đâu |
| `finalState` | APPLIED, PARTIAL, FAILED, ROLLED_BACK |
| `timestamp`, `correlationId` | Điều tra và nối log/traces |

Chỉ ghi chi tiết cần thiết: URI/metadata có thể tiết lộ topology; raw token, `Authorization`, cookie, client secret, private key phải được **loại bỏ hoặc mã hóa/redact** theo chính sách.

### 8.2. Một audit event mẫu

~~~json
{
  "eventType": "gateway.route.change",
  "changeId": "chg-2026-0159",
  "actor": {
    "subject": "operator-023",
    "authMethod": "workload-or-admin-identity"
  },
  "environment": "production",
  "routeIds": ["dyn-orders-api"],
  "action": "UPDATE",
  "ticket": "CHG-1542",
  "approval": "approved",
  "beforeRevision": 41,
  "targetRevision": 42,
  "beforeDigest": "sha256:example-before",
  "afterDigest": "sha256:example-after",
  "validationResult": "PASS",
  "publishResult": "COMMITTED",
  "replicaResults": {
    "gateway-a": "APPLIED",
    "gateway-b": "APPLIED",
    "gateway-c": "FAILED"
  },
  "finalState": "PARTIAL",
  "recordedAt": "2026-11-24T09:20:00Z"
}
~~~

Đây là **schema thiết kế minh họa**, không phải JSON được Spring Cloud Gateway mặc định phát. Các `sha256:example-...` chỉ là placeholder; trong hệ thống thật phải tính digest từ canonical route snapshot, và không coi hash là chữ ký số.

**PARTIAL là trạng thái quan trọng.** Một operation có thể commit shared route thành công nhưng không được mọi Gateway replica áp dụng; audit phải ghi sự thật thay vì đánh dấu `SUCCESS` ngay khi Actuator trả 200.

### 8.3. Audit log cần bền vững và khó chỉnh sửa

Không chỉ ghi audit vào `System.out` của một pod vì pod có thể bị thay thế giữa lúc sự cố. Production nên dùng:

- Một audit service hoặc log pipeline tập trung với access control.
- Append-only hoặc immutable/WORM retention nếu yêu cầu tuân thủ.
- Đồng hồ/UTC time thống nhất và correlation ID.
- Chính sách retention, redaction, encryption và quyền xem audit.
- Cơ chế không làm thất lạc **ý định và commit thay đổi** khi hệ thống log tạm lỗi.

Nếu dùng database/outbox, nên lưu **thay đổi + audit/outbox trong cùng transaction** khi kiến trúc lưu trữ cho phép. Không tự giả định Actuator CRUD và một hệ thống audit bên ngoài là atomic transaction.

### 8.4. Spring Boot auditevents có đủ không?

Spring Boot Actuator có endpoint `/actuator/auditevents` khi audit infrastructure được cấu hình phù hợp. Nó hữu ích cho một số security/audit events nhưng **không tự bảo đảm ghi toàn bộ diff của mỗi thao tác tạo/xóa route**.

Để có lịch sử quản trị route đầy đủ, cần **instrument control plane hoặc lớp bao quanh write/refresh operation**. Nếu chỉ bật `auditevents` rồi không thấy nội dung before/after route, đó không có nghĩa thao tác chưa xảy ra.

## 9. Quy trình thay đổi route: từ đề xuất đến applied revision

Một thay đổi an toàn nên có vòng đời độc lập với HTTP status của một request quản trị.

~~~mermaid
sequenceDiagram
    autonumber
    participant O as Operator / CI
    participant C as Control Plane
    participant R as Route Store
    participant B as Change Bus
    participant A as Gateway A
    participant G as Gateway B
    O->>C: Proposal + baseRevision=41
    C->>C: RBAC + approval + validate route
    C->>R: Đọc snapshot v41, kiểm tra CAS
    R-->>C: Snapshot v41
    C->>R: Lưu snapshot/candidate v42
    R-->>C: Persisted
    C->>B: routes.changed(revision=42)
    B-->>A: Signal 42
    B-->>G: Signal 42
    A->>R: Đọc v42
    G->>R: Đọc v42
    A->>A: Refresh + verify effective routes
    G->>G: Refresh + verify effective routes
    A-->>C: APPLIED 42
    G-->>C: FAILED 42
    C->>C: Audit PARTIAL + activate rollback policy
~~~

**Các bước CAS, revision, bus, ACK và auto-rollback ở trên là phần kiểm soát bổ sung, không có sẵn chỉ từ một Actuator HTTP endpoint.**

### 9.1. Trước khi ghi: validate candidate

Một candidate `RouteDefinition` cần đi qua những kiểm tra:

1. **Route ID:** duy nhất, có namespace/owner, không ghi đè route static.
2. **URI scheme/host:** allowlist `lb`/HTTPS và domain/service ID được phép; không nhận host do client tùy tiện cung cấp.
3. **Path/Host/Method predicates:** không mở rộng bất ngờ sang endpoint `/actuator`, admin hoặc route khác.
4. **Order/priority:** không chiếm route có độ ưu tiên cao gây bypass.
5. **Filter factory:** tên filter có trên tất cả binary versions; args hợp lệ.
6. **Headers:** không thêm/xóa `Authorization`/`Cookie`/`Forwarded` làm lộ credential hoặc phá trust boundary.
7. **Security impact:** xác thực, phân quyền, TLS, rate limiting, retries, circuit breaker có còn đúng không?
8. **Cross-route conflicts:** path overlap, duplicate IDs, orphan routes, fallback loops.
9. **Resilience:** có dependency upstream, load balancer instances và thời gian timeout chấp nhận được.
10. **Rollback plan:** có trước snapshot, version và khả năng tạo lại cấu hình tốt.

**Không đánh giá route hợp lệ chỉ bằng cú pháp JSON.** Một `uri: http://169.254.169.254` có thể đúng cú pháp nhưng gây SSRF hoặc truy cập cloud metadata; một `Path=/**` cũng đúng cú pháp nhưng có thể khớp quá rộng.

### 9.2. Phân biệt trạng thái thay đổi

| Trạng thái | Ý nghĩa |
| --- | --- |
| `PROPOSED` | Có yêu cầu thay đổi, chưa được duyệt |
| `VALIDATED` | Qua schema/policy/compatibility checks |
| `APPROVED` | Có quyền và phê duyệt cần thiết |
| `COMMITTED` | Desired definitions đã được lưu |
| `REFRESH_REQUESTED` | Đã phát tín hiệu refresh, chưa chứng minh áp dụng |
| `APPLIED` | Replica mục tiêu xác minh effective routes đúng revision |
| `PARTIAL` | Chỉ một phần replicas/routes áp dụng thành công |
| `FAILED` | Validation, write hoặc refresh/apply thất bại |
| `ROLLBACK_REQUESTED` | Đã yêu cầu khôi phục snapshot tốt |
| `ROLLED_BACK` | Đã xác minh route hiệu lực quay về nội dung an toàn |

Không chuyển thẳng `COMMITTED → APPLIED` chỉ vì một `POST /actuator/gateway/refresh` trả `200`. Đây là một lỗi quan sát đặc biệt nguy hiểm ở cụm nhiều replicas.

## 10. Ví dụ lệnh Actuator trong môi trường staging được bảo vệ

> **Cảnh báo:** các lệnh chỉ dùng trong **mạng quản trị đã xác thực** hoặc staging cô lập. Không copy vào shell public, không bỏ authorization và không chạy trên production ngoài quy trình change. `ADMIN_TOKEN` phải được cấp qua secret manager hoặc identity flow bảo vệ; không paste token thật vào ticket/log.

### 10.1. Chọn đúng endpoint của từng replica

~~~bash
# Các hostname chỉ là ví dụ; không phải hệ thống thật.
export ADMIN_A="https://gateway-a-admin.internal.example"
export ADMIN_B="https://gateway-b-admin.internal.example"

# ADMIN_TOKEN phải được cung cấp qua một kênh an toàn.
# Không export giá trị bí mật thật trong tài liệu hoặc ảnh chụp.
~~~

**Không dùng một URL public load-balanced** cho thao tác xác minh/refresh nhiều replica: hai lần gọi có thể cùng đi tới A.

### 10.2. Snapshot trước khi thay đổi

~~~bash
# Đọc route hiện hành, lưu vào kho snapshot đã bảo vệ.
curl -fsS \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  "$ADMIN_A/actuator/gateway/routes"

curl -fsS \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  "$ADMIN_B/actuator/gateway/routes"
~~~

`GET /routes` rất hữu ích để **quan sát effective route**, nhưng output dạng hiển thị **không nhất thiết là route definition có thể POST trực tiếp**. Snapshot có thể phục hồi cần lưu cả **source-of-truth definitions** ở định dạng ghi được, revision, order, metadata, hash/diff và policy tương ứng.

Nếu route nằm trong YAML/Java DSL, sửa nó trong nguồn quản lý cấu hình và deploy/refresh đúng cơ chế; không kỳ vọng Actuator writer biến nó thành dynamic route.

### 10.3. Tạo route thử nghiệm

Một route demo mới (không trùng ID):

~~~bash
curl -i -X POST \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  "$ADMIN_A/actuator/gateway/routes/dyn-orders-demo" \
  --data '{
    "predicates": ["Path=/api/orders/**"],
    "filters": ["StripPrefix=1"],
    "uri": "lb://ORDER-SERVICE",
    "order": 0
  }'
~~~

Đây là shortcut DSL được tài liệu Actuator Gateway mô tả. Đảm bảo mock/registry có `ORDER-SERVICE` và route `Path=/api/orders/**` **không xung đột** với route đang có trước khi chạy. Tài liệu Gateway phiên bản mới mô tả create thành công có thể trả **201 Created**.

**Đừng POST vào một ID đã tồn tại.** Tài liệu Gateway 5.x cảnh báo việc làm này có thể gây duplicate definition nội bộ và lỗi 500 khi truy vấn routes. Nếu cần cập nhật route đã tạo qua Actuator, các version có thể yêu cầu xóa rồi tạo lại; thao tác này không nguyên tử và có khoảng hở, nên cần control plane/snapshot workflow riêng cho production.

### 10.4. Refresh A rồi xác minh

~~~bash
curl -i -X POST \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  "$ADMIN_A/actuator/gateway/refresh"

curl -fsS \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  "$ADMIN_A/actuator/gateway/routes/dyn-orders-demo"
~~~

`POST /refresh` có thể trả **200 không body**. **Không kết luận thành công chỉ từ 200**, bởi quá trình làm mới có thể bất đồng bộ và route có thể xây dựng lỗi.

Kiểm tra tiếp:

- `GET /routes` có route đúng ID/URI/order/predicate/filter không?
- Synthetic request tới đúng **gateway-a** có được xử lý đúng path không?
- Audit record ghi `APPLIED` chỉ sau khi đã xác minh thực tế?
- Có 404/5xx hay route conflict mới?
- Với security policy, route có bị mở quá rộng không?

### 10.5. B và những replica khác

Nếu dùng **shared route repository** như Redis, B có thể đọc cùng definition nhưng vẫn giữ **local route cache cũ**. Refresh/verify từng replica bằng management endpoint riêng hoặc node-local event subscriber:

~~~bash
curl -i -X POST \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  "$ADMIN_B/actuator/gateway/refresh"

curl -fsS \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  "$ADMIN_B/actuator/gateway/routes/dyn-orders-demo"
~~~

Nếu A dùng **InMemoryRouteDefinitionRepository**, route tạo trên A không tự xuất hiện ở B chỉ nhờ refresh B. Phải xác minh source chung, không xem refresh là cơ chế truyền dữ liệu qua cluster.

### 10.6. Xóa route trong staging

~~~bash
curl -i -X DELETE \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  "$ADMIN_A/actuator/gateway/routes/dyn-orders-demo"

curl -i -X POST \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  "$ADMIN_A/actuator/gateway/refresh"
~~~

Thao tác delete phải đi kèm audit và snapshot. Trong bài tập, chỉ xóa ID `dyn-orders-demo` do bạn tạo ở staging; **không dùng ví dụ để xóa route đang phục vụ người dùng thật**.

## 11. Refresh bất đồng bộ và sự khác biệt giữa ba kết quả

### 11.1. Kết quả ghi source

Một thao tác save route trả thành công chỉ cho biết `RouteDefinitionWriter` đã nhận/lưu theo repository implementation.

- **In-memory:** chỉ JVM đó có definitions mới.
- **Redis shared repository:** các replicas có thể đọc definitions mới từ cùng Redis.
- **Git/Config Server:** còn cần reload config theo cơ chế tương thích.

**Save thành công không có nghĩa route đã được Gateway chạy.**

### 11.2. Kết quả refresh local

`POST /actuator/gateway/refresh` yêu cầu xóa/làm mới cache **của instance nhận lệnh**. Tài liệu Gateway mới nêu lỗi trong **asynchronous refresh** có thể khiến routes hiện hành không bị thay đổi. Điều này là hành vi cần kiểm tra theo đúng release, **không phải bảo đảm last-known-good bền vững trên mọi loại repository**.

Một request đã được định tuyến trước refresh có thể tiếp tục dùng route cũ cho đến khi nó hoàn tất. Refresh không phải giao dịch “chuyển tất cả in-flight requests ngay lập tức”.

### 11.3. Kết quả áp dụng toàn cụm

Với nhiều Gateway replicas, cần:

1. Ghi **desired revision** vào source chung.
2. Fan-out signal (event bus/agent/control plane) đến **mỗi replica**.
3. Trigger local refresh ở từng node.
4. Đọc effective routes và kiểm chứng hành vi node đó.
5. Ghi **applied revision** của từng node.
6. Chỉ công bố `APPLIED` khi những node cần thiết đã hội tụ; nếu không là `PARTIAL` hoặc `FAILED`.
7. Reconcile khi node mất event, khởi động lại hoặc không kết nối được tới store.

Một HTTP 200 duy nhất không chứng minh cụm nhiều node đã cập nhật.

## 12. Những kiểu thất bại phải phân biệt

| Loại lỗi | Dấu hiệu | Nguyên nhân có thể | Phản ứng đầu tiên |
| --- | --- | --- | --- |
| **Unauthorized** | 401/403 ở admin endpoint | Token/scope sai, CSRF hoặc RBAC | Không retry bằng credential cũ; kiểm tra quyền |
| **Endpoint unavailable** | 404/405 | Gateway Actuator disabled/read-only/not exposed, path/version sai | Kiểm tra access/exposure/matcher |
| **Validation failed** | 4xx hoặc control plane reject | Predicate/filter args/URI không hợp lệ | Không publish candidate |
| **Route build failed** | Refresh báo/ghi lỗi | Custom filter không có, URI/filter config sai | Giữ trạng thái bảo vệ, rollback candidate |
| **Store write failed** | Redis/DB timeout/5xx | Network, auth, Redis outage | Không phát event `COMMITTED` giả |
| **Refresh event lost** | A mới, B cũ | Bus/PubSub rớt, node offline | Reconcile desired vs applied |
| **Mixed snapshot** | Một số route mới, số khác cũ | CRUD từng route không atomic | Versioned snapshot/rollback |
| **Conflicting route** | Request đi sai route, có 404/5xx | Path overlap, order, duplicate ID | So effective routes, dừng rollout |
| **Security regression** | Endpoint nhạy cảm không còn auth | Filter/predicate bị thay sai | Emergency policy block, rollback |
| **Upstream unavailable** | 502/503 sau route mới | `lb://` thiếu instance, DNS/TLS lỗi | Kiểm tra discovery/URI, rollback nếu do change |
| **Success mismatch** | Actuator 200 nhưng traffic vẫn lỗi | Applied chưa đúng hoặc nghiệp vụ lỗi riêng | Synthetic test + trace theo node |
| **Audit pipeline failed** | Không có event cần thiết | Log pipeline/store mất | Đưa change vào trạng thái chưa xác nhận, reconcile |

**Đừng gộp mọi lỗi 5xx thành “route refresh thất bại”.** Một route có thể được áp dụng đúng, nhưng upstream chết hoặc TLS certificate hết hạn; cần xác định tầng và thời điểm lỗi trước khi quyết định rollback.

## 13. Runbook phục hồi khi route change thất bại

### 13.1. Quy trình khẩn cấp

Khi một route change gây lỗi production:

1. **Dừng những thay đổi mới** vào cùng route/namespace, tránh hai operator cùng rollback rồi ghi đè nhau.
2. **Phân loại ảnh hưởng:** route ID nào, region/replica nào, tỷ lệ 4xx/5xx, auth impact, có rò rỉ credential hay không.
3. **Lưu bằng chứng:** current desired revision, effective routes từng node, audit change ID, error logs đã redact.
4. **Chặn đường nguy hiểm ngay:** nếu route gửi tới host trái phép, dùng network policy/firewall/WAF/identity revocation bổ sung trong khi khôi phục.
5. **Lấy last-known-good snapshot** từ kho version được bảo vệ; không copy thủ công một response GET verbose thành POST JSON.
6. **Áp dụng rollback có phiên bản** bằng control plane hoặc quy trình quản trị được phê duyệt.
7. **Refresh từng node**/phát event cluster theo cơ chế được kiểm chứng.
8. **Xác minh** route definitions, path/URI/order, authentication và synthetic requests qua các node.
9. **Quan sát ổn định**: 404/5xx, p95/p99 latency, upstream metrics, rate limiting và security events.
10. **Audit incident:** ai quyết định rollback, from/to revision, thành công/partial/failure, timeline và bài học.

### 13.2. Sơ đồ ra quyết định

~~~mermaid
flowchart TD
    A["Phát hiện lỗi sau route change"] --> B{"Có nguy cơ security/SSRF?"}
    B -->|Có| C["Chặn khẩn tại network/auth; dừng rollout"]
    B -->|Không| D["Kiểm tra desired vs applied"]
    C --> D
    D --> E{"Lỗi chỉ ở một replica?"}
    E -->|Có| F["Reconcile/refresh node đó, test"]
    E -->|Không| G["Đánh giá candidate và snapshot tốt"]
    F --> H{"Node đã hội tụ và traffic tốt?"}
    H -->|Có| I["Audit recovered + monitor"]
    H -->|Không| G
    G --> J["Publish revision rollback mới"]
    J --> K["Refresh mọi replica liên quan"]
    K --> L{"Verify all replicas + auth + upstream"}
    L -->|Pass| I
    L -->|Fail| M["Giữ incident mở; cô lập node/route; escalations"]
~~~

**Không cố refresh liên tục một route definition sai**: nếu definition vẫn sai, refresh nhiều lần không làm cho route hợp lệ. Phải sửa hoặc quay về snapshot tốt, rồi mới refresh.

## 14. Ví dụ phục hồi: filter không tồn tại trên gateway-b

**Trạng thái trước thay đổi:**

~~~yaml
# Route definition minh họa ở revision 41.
id: dyn-orders-api
uri: lb://ORDER-SERVICE
predicates:
  - Path=/api/orders/**
filters:
  - StripPrefix=1
order: 0
~~~

Operator muốn bổ sung một custom filter `VerifyPartnerHeader` và tạo revision 42. Nhưng:

- `gateway-a` đã triển khai binary có `VerifyPartnerHeaderGatewayFilterFactory`.
- `gateway-b` vẫn dùng binary cũ, **không có factory đó**.
- `gateway-c` đang mất kết nối Redis.

Kết quả:

~~~text
Desired revision: 42

gateway-a: applied 42
gateway-b: failed route conversion
gateway-c: still applied 41

Change status: PARTIAL
~~~

**Hành động sai:** chỉ nhìn kết quả POST ghi Redis rồi đánh dấu `SUCCESS`, hoặc retry refresh B không giới hạn.

**Hành động đúng:**

1. Ghi audit `PARTIAL` với lỗi filter compatibility.
2. Dừng rollout, ngăn candidate mới cùng route được publish.
3. Chọn rollback về nội dung revision 41 đã biết tốt.
4. Publish **revision 43 chứa nội dung tương đương v41**, thay vì phát lại số revision 41 khiến consumer monotonic coi là event cũ.
5. A/B/C tải revision 43, refresh và verify; nếu C offline, yêu cầu reconcile khi node trở lại.
6. Audit `ROLLED_BACK` **sau khi** cả node mục tiêu có hiệu lực đúng; nếu một node còn stale thì tiếp tục `PARTIAL`.
7. Lập kế hoạch triển khai binary filter tới mọi replica trước khi thử revision khác.

Lưu ý: `RedisRouteDefinitionRepository` cơ bản không tự cung cấp **versioned snapshot + monotonic rollback** như trên. Đây là kiến trúc cần thêm vào control plane/repository, không phải lệnh `POST /refresh` sinh ra revision mới.

### 14.1. Khi chỉ có Actuator CRUD thủ công thì sao?

Nếu một route động đã được tạo qua Actuator và API phiên bản yêu cầu **delete rồi create** để cập nhật ID đang tồn tại, quy trình emergency có thể là:

~~~text
1. Snapshot definition cũ ở định dạng ghi được.
2. DELETE route ID lỗi trên source đang dùng.
3. POST route ID đó với definition đã kiểm tra.
4. POST /gateway/refresh trên node nhận lệnh.
5. Refresh/verify các replica khác nếu dùng shared source.
6. Test hành vi và ghi audit.
~~~

**Cảnh báo:** khoảng giữa bước 2 và 3 route có thể vắng mặt; khi có cache/replicas, trạng thái nhìn thấy có thể không nhất quán. Không tuyên bố đây là **atomic update/zero-downtime rollback**. Nếu cần an toàn nghiêm ngặt, dùng versioned snapshots, staged rollout hoặc quá trình deployment phối hợp.

## 15. Rollback khác “undo” trong memory

Có ba thứ phải quay lại đúng:

1. **Desired route definitions** trong shared repository/Git/control plane.
2. **Effective route cache** ở từng Gateway JVM.
3. **Trạng thái các hệ thống liên quan** như ConfigMap, service discovery, auth policy, filter binary và network policy.

Nếu chỉ refresh local cache mà desired definitions vẫn chứa route lỗi, node có thể lại tải lỗi đó. Nếu chỉ sửa shared source nhưng không refresh, một số node vẫn chạy route cũ. Nếu route dùng một custom filter đã bị gỡ khỏi binary, rollback definition cũng có thể thất bại nếu snapshot không tương thích.

Một **last-known-good snapshot** cần có:

| Thành phần | Nội dung cần lưu |
| --- | --- |
| Route definitions | ID, URI, predicates, filters, order, metadata |
| Revision/digest | Version monotonic hoặc commit hash |
| Compatibility | Release train, custom filter factories, schema |
| Security policies | Những ràng buộc không được phép giảm |
| Dependencies | Service registry, TLS truststore, Redis config |
| Validation report | Những synthetic tests đã pass |
| Rollback instruction | Cách re-apply/refresh/verify trên từng node |
| Audit references | Change ID, operator/approval, incident |

Với cập nhật **nhiều route liên quan**, ghi từng route một có thể tạo **mixed-version snapshot**. Hãy cân nhắc transactional source, versioned namespace/active revision pointer hoặc staged activation. Actuator CRUD thông thường không tự bảo đảm nguyên tử trên một bộ route động.

## 16. Nhiều Gateway replicas và sự thật về refresh cục bộ

Một event `RefreshRoutesEvent` được publish bằng Spring `ApplicationEventPublisher` chỉ tác động đến **ApplicationContext/JVM cục bộ**. `POST /actuator/gateway/refresh` cũng chỉ tác động tới **instance nhận request**.

~~~mermaid
flowchart LR
    CP["Approved route revision 43"] --> STORE[("Shared route store")]
    CP --> BUS["Route change notification"]
    STORE --> A["Gateway A"]
    STORE --> B["Gateway B"]
    STORE --> C["Gateway C"]
    BUS --> A
    BUS --> B
    BUS --> C
    A --> ACK["Convergence monitor"]
    B --> ACK
    C --> ACK
~~~

Nếu dùng `InMemoryRouteDefinitionRepository`, ghi route ở A không làm B nhận definition mới; **refresh B cũng không giải quyết khác biệt nguồn dữ liệu**. Có thể dùng `RedisRouteDefinitionRepository` cho shared definitions nhưng **vẫn cần notify và refresh từng replica**.

Một message bus (Redis Pub/Sub, Kafka, RabbitMQ, Spring Cloud Bus khi cấu hình tương thích) có thể phát thông báo route-changed, nhưng **việc bus nhận message không chứng minh node đã apply**.

### 16.1. Desired revision và applied revision

Một bảng kiểm soát ví dụ:

| Replica | Desired | Applied | Kết quả |
| --- | ---: | ---: | --- |
| gateway-a | 43 | 43 | APPLIED |
| gateway-b | 43 | 43 | APPLIED |
| gateway-c | 43 | 42 | STALE |

Không nên coi cluster **ROLLED_BACK** nếu C vẫn đang phục vụ route lỗi v42. Có thể tạm đưa C ra khỏi load balancer cho đến khi reconcile/validate thành công, tùy mức độ ảnh hưởng và SLO.

Thời điểm apply phải được xác minh **sau khi route mới được dựng/hiển thị hoặc kiểm thử**, không chỉ sau khi gọi local refresh.

### 16.2. Lost event và khởi động lại

Với Redis Pub/Sub, subscriber offline có thể bỏ lỡ message; cần periodic reconciliation hoặc bus durable khi phù hợp. Ở startup, mỗi node nên so desired revision với route state đã tải trước khi nhận traffic cần policy mới.

Đừng mặc định cache trong memory là **persistent last-known-good** sau pod restart. Nếu route source tạm không khả dụng, behavior cold start phải được load-test/chaos-test và có policy xử lý rõ.

## 17. Kiểm thử authorization, audit và rollback

### 17.1. Ma trận quyền

| Ca | Actor/thiết lập | Request | Kỳ vọng |
| --- | --- | --- | --- |
| A1 | Không credential | `GET /actuator/gateway/routes` | Không lấy được dữ liệu quản trị; có thể 401 |
| A2 | Reader scope | `GET /actuator/gateway/routes` | Được nếu endpoint exposed/read-only |
| A3 | Reader scope | `POST /actuator/gateway/refresh` | Không thực thi; có thể 403/404/405 |
| A4 | Reader scope | `DELETE /actuator/gateway/routes/id` | Không thực thi, có audit denied nếu policy yêu cầu |
| A5 | Writer scope nhưng không approval | Đề xuất thay route nhạy cảm | Control plane từ chối |
| A6 | Writer scope + approval hợp lệ | Thay route trong scope | Qua validation, audit, apply/verify |
| A7 | Writer scope | Tạo route sang host bị cấm | Validation/SSRF policy từ chối |
| A8 | Token không đúng audience/issuer | Bất kỳ management call | Authentication không được chấp nhận |
| A9 | `access: read-only` | POST refresh dù writer token hợp lệ | Endpoint không thực hiện write |
| A10 | `access: unrestricted`, không có network allow | Admin call từ Internet | Network policy từ chối |

Chỉ assert status cụ thể khi đã cố định security/Actuator version và network topology. Với lỗi blocked endpoint, **không thực hiện hành động** quan trọng hơn phân biệt 403/404/405 trong một tài liệu tổng quát.

### 17.2. Ma trận thay đổi thất bại

| Ca | Tình huống | Assertion |
| --- | --- | --- |
| F1 | Predicate sai cú pháp | Không publish route sai; audit VALIDATION_FAILED |
| F2 | Custom filter không có ở một replica | PARTIAL/FAILED; node lỗi không ACK applied |
| F3 | URI trỏ tới private metadata host | Rejected trước khi write |
| F4 | Route ID trùng | Không tạo bản ghi trùng; audit conflict |
| F5 | Redis write timeout | Không phát message COMMITTED giả |
| F6 | Refresh trả 200 nhưng cache chưa đổi | Applied vẫn ở revision cũ |
| F7 | Bus mất event khi node offline | Reconcile phục hồi revision |
| F8 | Event v42 đến sau v43 | Consumer không rollback nhầm về v42 |
| F9 | Hai operator sửa cùng revision | CAS/optimistic concurrency chặn lost update |
| F10 | Hai route cần đổi cùng lúc | Snapshot không bị mixed-version ngoài policy |
| F11 | Rollback v43 chứa nội dung v41 | Tất cả node phục vụ lại behavior an toàn |
| F12 | Một node vẫn phục vụ route lỗi | Không đánh dấu ROLLED_BACK cho cluster |
| F13 | Audit store tạm lỗi | Change workflow có trạng thái rõ, không ghi success giả |
| F14 | Request đang xử lý qua route cũ | Có hành vi in-flight được dự đoán/kiểm tra |
| F15 | Actuator admin token bị rò rỉ | Có cơ chế revoke credential, chặn network và audit incident |

### 17.3. Kiểm tra với WebTestClient

Đoạn minh họa dưới đây là skeleton cho **kiểm thử quyền**, yêu cầu khởi động app có Spring Security, actuator và test identities:

~~~java
// Pseudocode hướng kiểm thử WebFlux Security:
// clientWithoutToken.get("/actuator/gateway/routes")
//     -> expect 401 khi endpoint được expose nhưng yêu cầu auth.
//
// clientWithReader.get("/actuator/gateway/routes")
//     -> expect 200.
//
// clientWithReader.post("/actuator/gateway/refresh")
//     -> expect write bị từ chối, route cache không bị thay đổi.
//
// clientWithWriter.post("/actuator/gateway/refresh")
//     -> expect request được nhận nếu access=unrestricted,
//        nhưng cần tiếp tục kiểm tra effective route mới.
~~~

**Đây không phải Java test class chạy độc lập**; cần `WebTestClient`, mock JWT/opaque token, server port và config đúng cho test. Với management port riêng, test phải gửi request tới **management listener**, không chỉ main server của Gateway.

Để chứng minh refresh không phá auth, kiểm tra cả security endpoints trước/sau thay đổi và synthetic traffic thực tế qua route predicates/filter chain.

### 17.4. Quan sát route behavior bằng synthetic requests

Sau mỗi thay đổi, nên thử ít nhất:

1. Một request GET hợp lệ qua route mới.
2. Một request path gần giống nhưng **không** nên khớp.
3. Một request thiếu token: vẫn bị từ chối ở security layer.
4. Một request thiếu scope: vẫn 403 theo chính sách.
5. Một request với header bị giới hạn: không bị lộ `Authorization` sang host sai.
6. Một request đến `lb://` khi service registry có và không có instances.
7. Một request qua từng Gateway replica, không chỉ qua public load balancer.
8. Route có `RewritePath`, `StripPrefix`, rate limit, circuit breaker hoặc retry vẫn giữ behavior đã duyệt.

Đây là **kiểm chứng nghiệp vụ và bảo mật**, không chỉ “route count tăng từ 10 lên 11”.

## 18. SLO, metrics và cảnh báo cho quản trị route

Các chỉ số nên thu thập:

| Metric/observation | Lý do |
| --- | --- |
| `gateway_route_change_requests_total` | Đếm đề xuất/tạo/xóa/refresh theo actor class/môi trường |
| `gateway_route_change_denied_total` | Phát hiện lạm dụng hoặc policy không phù hợp |
| `gateway_route_validation_failures_total` | Theo dõi candidate lỗi |
| `gateway_route_refresh_attempts_total` | Đếm local refresh và lỗi |
| `gateway_route_applied_revision` | Node nào đã hội tụ |
| `gateway_route_convergence_lag_seconds` | Alert khi node stale vượt ngưỡng |
| `gateway_route_rollback_total` | Đếm rollback và nguyên nhân |
| HTTP 404/5xx per route/node | Phát hiện regression sau rollout |
| p95/p99 latency và upstream errors | Phân biệt routing lỗi với service lỗi |
| Security audit events | Theo dõi thao tác trái phép trên management API |

**Các metric tên `gateway_route_...` ở bảng là đề xuất custom instrumentation**, không phải mọi tên đều có sẵn trong Spring Cloud Gateway/Micrometer.

Không đưa raw route URI tùy biến, request ID, access token hoặc change description dài vào **metric labels** vì rủi ro cardinality và dữ liệu nhạy cảm. Dùng route ID đã kiểm soát, environment, outcome class làm dimensions; chi tiết audit đưa vào log bảo vệ.

### 18.1. Alert hữu ích

- Có write/refresh attempt không được phê duyệt.
- Actuator management API bị gọi từ mạng ngoài allowlist.
- Desired revision lệch applied revision hơn SLA.
- Một node báo refresh error liên tục.
- Sau change, tỷ lệ 404/5xx hoặc auth failures tăng.
- URI/route count/order khác baseline mà không có change ID.
- Audit pipeline mất dữ liệu hoặc ghi failure.
- Rollback đã yêu cầu nhưng chưa converged sau thời gian chính sách.

## 19. Những lỗi thiết kế thường gặp

| Sai lầm | Hậu quả | Cách tránh |
| --- | --- | --- |
| Chỉ đặt `management.endpoint.gateway.access: unrestricted` | Có quyền thao tác nhưng chưa có bảo vệ HTTP | Network isolation + auth + RBAC + audit |
| Expose `*` trên public API | Lộ nhiều actuator endpoints không cần thiết | Chỉ expose các ID cần dùng |
| Dùng token user cho route admin | Mở privilege ngoài mục tiêu | Admin identity/scope riêng |
| Tự viết SecurityWebFilterChain rồi quên Actuator | Boot auto-security có thể back off | Match và test quản trị cụ thể |
| Disable CSRF cho app dùng cookie login | Tăng rủi ro CSRF | Chỉ disable khi thực sự stateless/Bearer |
| Tin header `X-User`/IP chưa xác minh trong audit | Audit actor bị giả mạo | Lấy từ principal, trusted proxies |
| Xem 201/200 là applied toàn cluster | Bỏ qua refresh error/stale node | Per-node verify + applied ACK |
| Gọi refresh 3 lần qua LB | Có thể chỉ tác động một node | Management address riêng từng replica |
| Ghi route vào InMemoryRepo rồi refresh B | B vẫn không có definition | Shared source hoặc deploy thống nhất |
| POST vào route ID đã tồn tại | Có thể duplicate và 500 theo version | Validate uniqueness, dùng update workflow phù hợp |
| Dùng GET route output làm POST body | Sai schema shortcut DSL | Snapshot definition đúng định dạng |
| Delete rồi create mà nghĩ atomic | Khoảng thời gian route vắng mặt | Versioned snapshots/staged rollout |
| Rollback chỉ sửa Redis, không refresh | Node vẫn chạy cache lỗi | Reconcile local caches và verify |
| Rollback số revision nhỏ hơn | Event consumer bỏ qua như thông báo cũ | Monotonic revision mới chứa snapshot tốt |
| Retry refresh khi definition sai | Không sửa được nguyên nhân | Validate/fix/rollback candidate |
| Audit chỉ có access log HTTP status | Không biết ai sửa gì và có converged chưa | Audit change ID/revision/diff/approval |
| Bật URI tùy ý trong control plane | SSRF, lộ credential, route bypass | Allowlist, egress policy, validation |
| Cache được giả định là last-known-good sau restart | Cold start vẫn lỗi khi store outage | Durable snapshot/test recovery |
| Thay route có auth policy mà không regression test | Bypass hoặc chặn nhầm người dùng | Security synthetic tests + approval |
| Log header `Authorization` ở endpoint quản trị | Lộ admin credential | Redaction, secret rotation, access control |

## 20. Bài thực hành tổng hợp: đổi route orders và cố ý tạo lỗi

**Kiến trúc test:**

- Gateway Server WebFlux chạy hai replicas A/B.
- Cùng đọc route definitions từ một shared repository phù hợp.
- Có management network riêng, JWT admin scopes và Actuator access chỉ bật write trong staging.
- Một control plane mock có audit record/revision.
- Mock `ORDER-SERVICE` trả response rõ upstream target và request path đã làm sạch.

**Yêu cầu:**

1. Cấu hình `management.endpoint.gateway.access: read-only`; xác nhận reader xem được route, nhưng POST/DELETE/refresh không thực hiện.
2. Chuyển sang `unrestricted` trong staging sau khi bật network/auth; xác nhận chỉ writer có quyền gọi write.
3. Snapshot route `dyn-orders-api` revision 41, lưu checksum/metadata.
4. Tạo candidate revision 42 đổi `StripPrefix` và thêm một filter không tồn tại ở Gateway B.
5. Đưa candidate qua validation; kiểm tra hệ thống có chặn trước publish khi phát hiện filter mismatch không.
6. Nếu bài kiểm thử cố tình cho publish trong môi trường cô lập, quan sát A/B có thể khác trạng thái.
7. Ghi audit `PARTIAL` với error detail đã redact, không gắn success từ HTTP 200.
8. Publish revision 43 với nội dung an toàn của revision 41; refresh A/B.
9. Synthetic test GET orders, request thiếu token, request thiếu scope và path rewrite.
10. Xác nhận cả A/B applied 43, rồi mới ghi audit `ROLLED_BACK`.
11. Cố ý cho B bỏ lỡ notification; kiểm tra reconciliation bắt kịp.
12. Xuất báo cáo: change ID, actor, ticket, before/after diff, apply failure, recovery duration, p95 latency và những bài học an toàn.

### 20.1. Dấu hiệu PASS

~~~text
Preflight:
  Gateway Actuator disabled by default; explicitly read-only for observers
  Admin management access isolated and authenticated
  Writer permission separated from viewer

Route change:
  Candidate validated
  Pre-change snapshot preserved
  Audit records actor, revision, diff, approval

Failure:
  Refresh failure not reported as cluster APPLIED
  Replica mismatch detected by convergence monitor

Recovery:
  Safe snapshot restored as new revision
  Every target replica verified
  Security and upstream behavior re-tested
  Audit finalized as ROLLED_BACK
~~~

Dấu hiệu trên là **tiêu chí cho bài kiểm thử**, không phải báo cáo một deployment thực tế đã chạy.

## 21. Checklist trước production

- [ ] `management.endpoint.gateway.access` có giá trị phù hợp; ưu tiên `read-only` khi chỉ quan sát.
- [ ] `management.endpoints.web.exposure.include` chỉ chứa endpoint cần thiết.
- [ ] Management port/network không bị expose ra public API hoặc thông qua Gateway route tùy tiện.
- [ ] Admin authentication, TLS/mTLS và RBAC đã kiểm thử cả listener thật.
- [ ] Reader/proposer/approver/writer có quyền tách biệt, write scope có route-level policy.
- [ ] Custom `SecurityWebFilterChain` không vô tình bỏ bảo vệ các Actuator khác.
- [ ] Có CSRF policy đúng cho cookie/session hoặc bearer-only stateless admin.
- [ ] Route candidate được validate URI, schemes, predicate, filter, order, auth và compatibility.
- [ ] Control plane có approval, revision/optimistic concurrency và change freeze khi cần.
- [ ] Audit trail có actor đã xác minh, changeId, before/after, kết quả và rollback.
- [ ] Không log secret, Bearer token, cookie, toàn bộ environment hoặc PII.
- [ ] Snapshot khôi phục ở định dạng ghi được, không phụ thuộc raw GET verbose output.
- [ ] Không POST mù vào route ID đang tồn tại; đã kiểm tra behavior theo Gateway version.
- [ ] Không giả định create/delete/refresh là atomic multi-route transaction.
- [ ] Có shared repository hoặc cơ chế phân phối source rõ cho multiple replicas.
- [ ] Local refresh và per-replica apply verification hoạt động đúng.
- [ ] Bus/reconciliation xử lý event trùng, mất hoặc đến sai thứ tự.
- [ ] HTTP 200 refresh không bị xem là proof of cluster convergence.
- [ ] Có runbook rollback version mới, không chỉ “undo” cache cục bộ.
- [ ] Đã chaos-test Redis/bus outage, cold start, stale nodes và filter compatibility.
- [ ] Có synthetic tests kiểm tra path, auth, scopes, TLS, retry, rate limiting và upstream.
- [ ] Metrics/alerts cho unauthorized change, refresh failure, convergence lag và 404/5xx.
- [ ] Route admin credentials được rotate/revoke và audit có retention được bảo vệ.

## 22. Tổng kết và tài liệu tham khảo

**Spring Cloud Gateway Actuator là một bề mặt điều khiển có quyền lực lớn.** Muốn dùng an toàn, cần kết hợp:

1. **Endpoint access và exposure:** `management.endpoint.gateway.access` cùng `management.endpoints.web.exposure.include`.
2. **Xác thực/phân quyền:** mạng quản trị riêng, TLS, Spring Security reactive, quyền read/write và control plane có approval.
3. **Kiểm toán:** actor đã xác minh, route diff, revision, change ID, validation, refresh outcome và kết quả áp dụng từng node.
4. **Phục hồi:** snapshot tốt, versioned rollback, refresh từng replica, xác minh effective routes và synthetic security tests.

Một lệnh `POST /actuator/gateway/refresh` trả 200 **không chứng minh mọi Gateway replica đã dùng cấu hình mới**; một thao tác write thành công cũng không đảm bảo route đã build và phục vụ đúng. Sự tin cậy đến từ quy trình **validate → commit → notify → refresh → verify → audit → reconcile/rollback**, được kiểm thử cả khi Redis, service discovery hoặc một replica gặp lỗi.

Các nguyên tắc này giúp Gateway tiếp tục định tuyến an toàn cho microservices khi thay đổi route động, mà không vô tình phá xác thực, giới hạn lưu lượng, circuit breaker, retry, TLS hoặc observability.

### Tài liệu tham khảo chính thức

- [Spring Cloud Gateway Server WebFlux — Actuator API](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/actuator-api.html).
- [Spring Cloud Gateway 5.0 — Actuator API: create/delete, refresh và giới hạn cập nhật route ID](https://docs.spring.io/spring-cloud-gateway/reference/5.0/spring-cloud-gateway-server-webflux/actuator-api.html).
- [Spring Cloud Gateway Server WebFlux — Sharing Routes](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/sharing-routes.html).
- [Spring Boot — Actuator Endpoints: access, exposure và security](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html).
- [Spring Boot 3.5 — Actuator Endpoints](https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html).
- [Spring Security — WebFlux Security Configuration](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html).
