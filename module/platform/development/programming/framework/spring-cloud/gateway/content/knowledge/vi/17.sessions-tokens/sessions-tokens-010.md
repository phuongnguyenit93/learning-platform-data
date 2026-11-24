# Ngăn ghi log hoặc chuyển token đến đích không được tin cậy

## 1. Một token hợp lệ vẫn có thể bị lộ ở API Gateway

Trong hệ thống microservices, **Spring Cloud Gateway** đóng vai trò cổng vào: nó chọn route bằng predicate, thực thi filter chain, chuyển đổi đường dẫn/header, phân giải service qua `lb://`, gọi backend qua HTTP(S) và ghi nhận tín hiệu vận hành. Gateway thường đi qua những dữ liệu nhạy cảm nhất của request: **access token, session cookie, API key và thông tin danh tính**.

Xác minh token thành công **không đồng nghĩa token đã được bảo vệ khỏi rò rỉ**. Một token hợp lệ vẫn có thể:

- Bị ghi vào access log hoặc debug log khi filter in toàn bộ request headers.
- Bị xuất qua Reactor Netty wiretap/HTTP client logging, tracing hoặc một exception handler tự tạo.
- Bị chuyển nguyên vẹn tới một backend **không có nhu cầu sử dụng** token đó.
- Bị chuyển tới service không đáng tin do route cấu hình sai, route động hoặc bản ghi service discovery bị thao túng.
- Bị lộ trong URL query, redirect `Location`, `Referer`, browser history, cache, dashboard hoặc công cụ quan sát.
- Bị giữ trong response `Set-Cookie` hoặc được sao chép sang một message queue/analytics system ngoài ý muốn.

Ví dụ một route public trỏ đến bên thứ ba nhưng không xóa `Authorization`:

~~~text
Client
  GET /api/public/recommendations
  Authorization: Bearer <access-token>
        |
        v
Spring Cloud Gateway
        |
        v
https://recommendation-vendor.example
  Authorization: Bearer <access-token>  <-- RỦI RO RÒ RỈ
~~~

Nếu upstream nhận được token dành cho một API khác, token có thể xuất hiện trong log, tracing hoặc storage của bên đó. Bên nhận **không được phép dùng token** chỉ vì đã được Gateway gửi sang; nhưng Gateway cũng không nên phát tán một bearer credential có thể bị người giữ nó sử dụng ở nơi khác.

Bài học thuộc chương **Phiên đăng nhập và token** của **Spring Cloud Gateway**. Trọng tâm là **kiểm soát đường đi của token** và **ngăn token xuất hiện trong telemetry**, bổ sung cho xác thực, phân quyền, TLS, giới hạn lưu lượng, circuit breaker và khả năng quan sát request. Ví dụ sử dụng **Spring Cloud Gateway Server WebFlux**, Spring Security reactive và Reactor Netty.

**Kết quả mong đợi:** Sau bài học, bạn có thể xác định ranh giới tin cậy của mỗi route, cho phép hoặc loại bỏ credential theo nhu cầu, phân biệt các loại token, viết logging an toàn, kiểm tra debug/wiretap và xây test phát hiện token bị rò rỉ. Bạn cũng sẽ hiểu vì sao không thể chỉ dựa vào một filter hoặc một regex che chuỗi `Bearer` là đủ.

> **Nguyên tắc gốc:** Chỉ gửi token đến **đúng đối tượng nhận đã được phê duyệt**, đúng **audience/scope**, qua kênh được bảo vệ; **không ghi token thô vào log, metrics, traces hoặc lỗi trả về client**.

## 2. Phân loại bí mật trước khi quyết định chuyển tiếp

Các dữ liệu dưới đây có mục đích và vòng đời khác nhau:

| Loại | Vị trí thường gặp | Nơi được phép dùng | Rủi ro chính |
| --- | --- | --- | --- |
| **OAuth2 access token** | `Authorization: Bearer ...` | Resource server phù hợp với audience và scope | Ai giữ token dạng bearer có thể dùng nó khi còn hiệu lực |
| **Refresh token** | Secure server-side storage hoặc cơ chế do Authorization Server thiết kế | Thành phần được phép làm mới token | Thường có thời hạn/khả năng cấp token mới; giá trị cao hơn access token |
| **OIDC ID token** | OAuth2/OIDC client | Ứng dụng khách xác nhận sự kiện đăng nhập theo contract OIDC | Không phải token thay thế access token để gọi API |
| **Session ID** | Cookie, ví dụ `SESSION=...` | Ứng dụng/session store đã cấp phiên | Có thể cho phép chiếm quyền phiên nếu bị lộ |
| **API key** | Header chuyên dụng, đôi khi query (không khuyến nghị) | API/service đã đăng ký key và scope | Thường là bí mật dài hạn nếu không rotation |
| **CSRF token** | Header/form hoặc phần cơ chế session | Luồng chống CSRF của ứng dụng | Không nên coi là access token hoặc log nguyên văn |
| **Authorization code / PKCE verifier** | OAuth2 redirect và client flow | OAuth2 client/Authorization Server trong phiên trao đổi | Rò rỉ có thể phá hỏng flow nếu phối hợp thêm yếu tố khác |

**Access token khác ID token.** ID token có audience là OAuth2 client và dùng xác nhận danh tính trong OpenID Connect; nó không phải giấy phép mặc định để gọi `orders-service`. **Refresh token càng không nên được gửi đến các business API**: việc làm mới token phải do thành phần được ủy quyền thực hiện.

Một token tự chứa dạng JWT có header/payload có thể giải mã thành JSON để đọc claims, **nhưng chưa xác minh chữ ký thì không được tin nội dung**. Không ghi toàn bộ JWT vào log để “xem quyền”; hãy lấy các thông tin đã được Spring Security xác minh từ `Authentication` hoặc context đáng tin.

### Không chỉ tìm đúng một header

Bí mật có thể nằm ở nhiều nơi:

- `Authorization`, `Proxy-Authorization`.
- `Cookie`, `Set-Cookie` hoặc header dùng tên riêng như `X-API-Key`, `X-Auth-Token`.
- URL query như `?access_token=...`, `?api_key=...`, `?session=...`.
- Body của login, token refresh, callback OAuth2 và các API credentials.
- WebSocket handshake, GraphQL variables, request/response error payload, trace baggage.
- Cấu hình bí mật trong environment, JVM system properties, exception message hoặc route metadata.

Một cơ chế log chỉ che `Authorization` **không đủ** nếu đội ngũ vẫn ghi full URL, cookies, request body hoặc debug data của OAuth2.

## 3. Sơ đồ ranh giới tin cậy của Gateway

Một Gateway có ít nhất ba ranh giới liên quan token:

~~~mermaid
flowchart TD
    U[Browser / Mobile / Partner] -->|Bearer token, session cookie| G[Spring Cloud Gateway]
    G --> A[AuthN/AuthZ: Spring Security]
    A --> P{Route + egress policy}
    P -->|Public catalog, no credentials| C[Catalog service]
    P -->|Orders, scoped access token| O[Orders service]
    P -->|External vendor, no credentials| V[Third-party service]
    G -. Safe metadata only .-> L[Logs / Metrics / Tracing]
    G -->|Configured internal auth only| I[Identity service]
~~~

**Ranh giới thứ nhất — client → Gateway:** Client có thể gửi credential bất hợp lệ, giả mạo header, URL nhạy cảm hoặc body bất kỳ. Gateway xác thực theo chính sách và tuyệt đối không coi input thô là danh tính đáng tin.

**Ranh giới thứ hai — Gateway → backend:** Gateway trở thành HTTP client, chọn `uri` từ route hoặc load balancer. Việc một request được chấp nhận ở Gateway **không tự động cấp phép** gửi credential nguyên bản tới mọi backend. Quyết định forward token phải dựa trên **dịch vụ nhận, audience, loại token và chính sách**.

**Ranh giới thứ ba — Gateway → telemetry:** Logs, metrics, traces, error reporting, APM, SIEM và support tools có người dùng, retention, exporter và quyền truy cập riêng. Dữ liệu gửi tới đây cần là **metadata an toàn**, không phải credential có thể sử dụng lại.

Một mạng “internal” không đồng nghĩa mọi service trong mạng có mức tin cậy như nhau. Ví dụ service báo cáo, hệ thống analytics và công cụ hỗ trợ bên thứ ba không nên nhận token của API quản trị hoặc refresh token của người dùng.

## 4. Đừng nhầm xác thực thành công với quyết định forward token

Tại Gateway Server WebFlux, Spring Security có thể xác thực Bearer JWT:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.test/realms/store
~~~

Cấu hình này giúp **xác thực token đầu vào** theo khả năng và validator của phiên bản Spring Security, nhưng **không phải một chính sách tự động xóa Authorization khi proxy**. Trong một HTTP reverse proxy, nếu bạn không có bộ lọc loại bỏ credential, header `Authorization` có thể được chuyển xuống upstream như những request headers khác. Hãy xác minh hành vi thực ở phiên bản Gateway và filter chain của mình, không suy đoán “token đã validate rồi nên bị giữ lại ở Gateway”.

Ba câu hỏi độc lập:

1. **Inbound validation:** token client gửi có hợp lệ cho chính Gateway/API của ta không?
2. **Authorization:** principal có quyền gọi endpoint này không?
3. **Outbound release:** có được **tiết lộ credential này** cho service được chọn không? Token có phù hợp audience/scope và đường truyền không?

Một yêu cầu có thể vượt qua câu hỏi (1) và (2) nhưng câu trả lời (3) vẫn là **không**.

### Audience quan trọng hơn việc URL đích “trông có vẻ nội bộ”

Ví dụ:

~~~json
{
  "iss": "https://identity.example.test/realms/store",
  "sub": "user-742",
  "aud": ["shop-gateway"],
  "scope": "catalog.read orders.read",
  "exp": 1999999999
}
~~~

Đây chỉ là **JWT payload minh họa**, không phải JWT đã ký. Nếu token chỉ có audience `shop-gateway`, không thể mặc định nó được thiết kế cho `orders-service`. Backend phải xác minh đúng audience của **chính mình**; nếu không, token do hệ thống A cấp có thể bị nhầm dùng tại hệ thống B (token substitution).

Vì vậy, ngay cả khi service nội bộ được phê duyệt, có thể cần **token exchange**, delegated token hoặc cơ chế identity nội bộ hạn chế audience/privileges, thay vì copy nguyên access token client.

## 5. Chính sách theo route: mặc định không chuyển credential

Hãy tạo bảng egress **trước khi viết YAML**:

| Route | Đích đã phê duyệt | Credential đầu vào | Quyết định outbound |
| --- | --- | --- | --- |
| `public-products` | `lb://catalog-service` | Có thể client gửi Authorization dù API public | **Xóa Authorization/Cookie không cần thiết** |
| `orders-private` | `lb://orders-service` | Access token đã xác thực | Chỉ chuyển access token nếu Orders thực sự là audience được phép và backend tự xác minh |
| `admin-private` | `lb://admin-service` | Token có authority quản trị | Chỉ chuyển đúng token/credential do policy admin cho phép, qua kênh bảo vệ |
| `partner-recommendations` | `https://vendor.example.test` | Bất kỳ | **Xóa toàn bộ credential nội bộ**; nếu cần vendor key, dùng credential **riêng** của Gateway |
| `login-token` | Identity/Authorization Server | Credentials hoặc authorization code | Chỉ gửi đúng bí mật được flow cho phép đến endpoint IdP tin cậy |
| `unlisted/dynamic` | Chưa được phê duyệt | Bất kỳ | **Không chuyển token**; tốt hơn là không mở route |

**Deny-by-default đối với token egress** nghĩa là **không mặc định forward** chỉ vì route đã match. Với mô hình phức tạp, nên áp rào bảo vệ ở cấp cấu hình route, mạng, service token validation và kiểm thử; không dựa duy nhất vào danh sách route ID nếu URL đích có thể bị thay đổi sau đó.

### Không chuyển tất cả cookie theo thói quen

Cookie có thể mang session ID, refresh token, CSRF cookie hoặc dữ liệu preference. Một route public chỉ trả danh mục thường **không cần** session cookie. Khi chuyển sang analytics/vender bên ngoài, việc gửi `Cookie` của domain Gateway không chỉ rủi ro với token mà còn có thể tiết lộ thông tin người dùng.

Nếu một backend thực sự dùng cookie auth, phải thiết kế contract rõ; không nên xóa `Cookie` bừa bãi rồi phá ứng dụng. Ngược lại, nếu dùng Bearer token, hãy đánh giá có cần chuyển bất kỳ cookie nào xuống backend không.

## 6. RemoveRequestHeader: cách đơn giản để ngăn lộ token trên route không cần auth

Với các route đã biết rõ, **RemoveRequestHeader GatewayFilter Factory** cho phép loại bỏ header từ request trước khi gửi tới upstream.

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: public-products
              uri: lb://catalog-service
              predicates:
                - Path=/api/public/products/**
              filters:
                - RemoveRequestHeader=Authorization
                - RemoveRequestHeader=Cookie
                - RemoveRequestHeader=Proxy-Authorization
                - RemoveRequestHeader=X-API-Key

            - id: partner-recommendations
              uri: https://vendor.example.test
              predicates:
                - Path=/api/public/recommendations/**
              filters:
                - RemoveRequestHeader=Authorization
                - RemoveRequestHeader=Cookie
                - RemoveRequestHeader=Proxy-Authorization
                - RemoveRequestHeader=X-API-Key
                - RemoveRequestHeader=X-Auth-Token

            - id: orders-private
              uri: lb://orders-service
              predicates:
                - Path=/api/orders/**
              filters:
                - RemoveRequestHeader=Cookie
~~~

**Giải thích:**

- Hai route công khai không gửi token/cookie client đến service vốn không cần chúng.
- Route tới vendor bên ngoài càng phải có chính sách **loại bỏ credential mặc định**; nếu vendor cần một API key riêng, cấp qua hệ thống quản lý secret và cơ chế tích hợp riêng, **không chuyển API key của người dùng**.
- Route Orders minh họa **chỉ bỏ Cookie**, còn Authorization có thể đi xuống service. **Điều này chỉ đúng khi** policy đã cho phép forward và backend Orders kiểm tra token phù hợp audience/scope. Nếu token chỉ dành cho Gateway, hãy **đổi cơ chế** thay vì copy token.
- `RemoveRequestHeader` chỉ loại header được chỉ định; nó **không tự xóa** token trong query string, body hoặc custom header khác. Tên header HTTP không phân biệt hoa thường.

**Điều kiện:** `lb://` cần Spring Cloud LoadBalancer và nguồn ServiceInstance được kiểm soát. URI `https://vendor.example.test` trong ví dụ là địa chỉ minh họa; không phải đích để thực sự gửi dữ liệu. Với các dòng Spring Cloud Gateway WebFlux trước, prefix YAML thường là `spring.cloud.gateway.routes` thay vì `spring.cloud.gateway.server.webflux.routes`. Dùng đúng namespace của bản triển khai.

### Cẩn thận với thứ tự filter

Filter `RemoveRequestHeader` không tạo một “bất biến” vĩnh viễn nếu **một filter chạy sau lại thêm Authorization**. Ví dụ, cấu hình `TokenRelay`, `SetRequestHeader=Authorization,...` hoặc custom GatewayFilter sai thứ tự có thể làm credential xuất hiện trở lại.

Vì vậy phải **xem cả chuỗi filter**, không chỉ một dòng YAML; integration test phải quan sát **headers mà backend thực sự nhận**. Nếu cần cơ chế bảo vệ egress tập trung, kiểm tra ở gần bước gửi HTTP cuối cùng và bảo vệ extension point bằng policy đáng tin, thay vì giả định filter đứng đầu chuỗi luôn là lớp cuối cùng được áp dụng.

### Bảo vệ ở route + ở mạng

Ngay cả khi tất cả header auth bị loại bỏ, một route dynamic vẫn có thể định tuyến tới metadata service hoặc admin service sai. Chính sách **route destination allowlist, service discovery trust, TLS/mTLS, network policies** vẫn cần thiết; strip credential không tự ngăn SSRF hoặc truy cập tài nguyên nội bộ.

## 7. TokenRelay không đồng nghĩa “token nào cũng chuyển được”

Spring Cloud Gateway có **TokenRelay GatewayFilter Factory** trong các cấu hình dùng **Spring Security OAuth2 Client**. Nó có thể lấy access token của authorized client và đặt vào request được proxy đến backend. Điều này hữu ích với các luồng đăng nhập OAuth2 và ủy quyền sang service khác, **nhưng không tự chứng minh rằng đích đến đáng tin hoặc token đúng audience**.

Mẫu cấu hình minh họa ở một route đã được kiểm soát:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: protected-orders
              uri: lb://orders-service
              predicates:
                - Path=/api/orders/**
              filters:
                - TokenRelay=
~~~

**Cần hiểu đúng ví dụ:**

- Chỉ dùng khi ứng dụng có **OAuth2 Client configuration/authorized-client context** thích hợp; loại starter và khả năng auto-configuration tùy phiên bản.
- `TokenRelay` khác với việc chỉ bật `oauth2ResourceServer().jwt()`. Một resource server xác minh Bearer token **không mặc nhiên là OAuth2 Client** có authorized client để relay.
- Access token được relay phải có quyền và **audience hợp lệ với Orders service**. Nếu không, backend cần từ chối hoặc hệ thống cần token exchange.
- Không gắn TokenRelay trên một route ra **vendor không được phê duyệt**, route động có host tùy ý hay endpoint public không cần token.
- Nếu route có các filter khác ghi/đọc Authorization, **thứ tự filter** và giá trị header thực tế tại upstream cần được kiểm chứng.
- Tên factory, khả năng hỗ trợ và phương thức cấu hình có thể khác giữa các dòng Spring Cloud Gateway; kiểm tra phiên bản ứng dụng đang dùng.

### Token forwarding, token exchange, service credential

| Cách làm | Ý nghĩa | Khi nào hợp lý? |
| --- | --- | --- |
| **Forward access token** | Backend nhận token của client | Backend là audience hợp lệ, có cùng mô hình tin cậy và tự xác minh |
| **Token exchange / on-behalf-of** | Gateway hoặc một thành phần tin cậy đổi token sang token mới cho backend | Cần token audience/scope ngắn hơn hoặc phân tách ranh giới dịch vụ |
| **Service-to-service credential** | Gateway xác thực chính nó với backend | Backend cần gọi bởi hệ thống, không cần token người dùng nguyên bản |
| **Không gửi credential** | Upstream nhận request đã bỏ token/cookie | Service public/anonymous hoặc nhà cung cấp không cần danh tính |

Không dùng một **shared admin token** để proxy mọi request của người dùng xuống backend. Cách đó phá vỡ attribution và có thể biến một request user thành thao tác có đặc quyền của Gateway. Với token exchange, cần bảo vệ khóa, chủ thể thay mặt, scope, TTL, audit và cơ chế revocation theo chính sách IdP.

### Phân biệt session login với bearer-only request

Một browser đăng nhập qua OAuth2 Login có thể có session cookie tại Gateway và authorized-client store. Gateway có thể dùng TokenRelay theo context đó. Trong một API stateless Bearer JWT, việc client gửi Authorization tới Gateway rồi Gateway proxy nguyên header là một luồng **khác**. Không nên tự suy diễn session cookie, CSRF hoặc OAuth2 client state từ sự hiện diện của JWT.

## 8. Service discovery và route động: đích nào thực sự nhận token?

Trong Gateway Server WebFlux, URI route `lb://orders-service` có thể được phân giải bởi **ReactiveLoadBalancerClientFilter** thành một `ServiceInstance` cụ thể, ví dụ `https://orders-2.internal.example:8443`. Kết nối HTTP thực sự được tạo đến instance đó, không phải chuỗi service ID logic.

~~~mermaid
flowchart TD
    A[Authorized route: lb://orders-service] --> B[LoadBalancer resolves ServiceInstance]
    B --> C{Host / namespace / certificate trusted?}
    C -->|Có| D[HTTP(S) request to approved instance]
    C -->|Không| E[Reject routing or do not release credential]
    D --> F[Backend validates audience, token and user permission]
~~~

**Route ID không phải bằng chứng cuối cùng về nơi token sẽ tới.** Nếu một route `orders-private` được đổi URI thành host ngoài, hoặc registry bị ghi bản ghi độc hại, một allowlist dựa đơn thuần vào tên route không ngăn credential bị chuyển tới nơi không được tin.

Một chính sách đáng tin cần bao phủ:

1. **Nguồn route definition:** chỉ người/quy trình được ủy quyền có thể thay route URI, predicate và filter.
2. **Service discovery:** hạn chế quyền ghi registry, cô lập namespace/environment/tenant, kiểm tra instance do hệ thống đăng ký.
3. **Đích thực:** kiểm soát host, scheme, port, mạng hoặc service identity; không cho `lb://` phân giải tới địa chỉ không được phê duyệt.
4. **TLS:** xác minh chứng chỉ, tên hostname và CA; mTLS nếu yêu cầu danh tính service-to-service.
5. **Token scope/audience:** backend tự kiểm tra token phù hợp service và thao tác; token exchange khi cần.
6. **Redirect/fallback:** không để backend hoặc filter tự redirect token tới một host khác ngoài chính sách.

### Cảnh báo SSRF trong dynamic routing

Không tạo URI outbound trực tiếp từ một header như:

~~~http
X-Target-URL: http://127.0.0.1:8081/admin
~~~

rồi cho request đi đến giá trị đó. Một attacker có thể khiến Gateway gửi request vào admin/metadata endpoint hoặc internal network. Nếu request còn có Bearer token, lỗi trở thành **SSRF kết hợp rò rỉ credential**.

Giới hạn đích đến bằng allowlist/bản ghi dịch vụ tin cậy, cấm scheme và port không cần thiết, xác thực quyền gọi route động và áp network egress policy. Đừng chỉ kiểm tra chuỗi hostname trước khi DNS hoặc service discovery resolve mà bỏ qua địa chỉ cuối cùng thực tế.

### Không biến 302 của backend thành nơi phát tán token

HTTP redirect là giao dịch mới; việc client hoặc HTTP client có tự theo redirect, chuyển Authorization sang host mới hay không phụ thuộc cấu hình và implementation. Không dựa vào giả định “client sẽ luôn bỏ Authorization khi đổi host”, cũng không cố ý cấu hình HTTP client tự theo redirect sang host tùy ý cùng token. **Đích redirect phải được xem là một ranh giới tin cậy mới**, được kiểm tra với hop mới, method và credential riêng.

## 9. Các nguồn log có thể chứa token

Ngay cả khi bạn không viết `log.info(token)`, token vẫn có thể rò rỉ gián tiếp. Hãy kiểm kê:

| Nguồn | Nội dung có thể bị ghi | Biện pháp |
| --- | --- | --- |
| Access log của ingress/CDN/WAF | Full URL, query, một số request headers | Không dùng token trong URL; cấu hình log format/headers an toàn |
| HTTP server access log của Gateway | URI, status, thời gian, client IP | Chỉ log route/template và metadata cần thiết; kiểm soát query |
| Reactor Netty `wiretap` | Byte/header chi tiết của HTTP exchange khi bật | Tắt trong production trừ đợt chẩn đoán được phê duyệt và bảo vệ |
| Gateway custom `GlobalFilter` | `exchange.getRequest().getHeaders()`, body, `getURI()` | Dùng allowlist field được phép log; không dump request/response |
| Spring Security/OAuth2 DEBUG/TRACE | Auth flow, token/claim/header tùy thành phần/version | Kiểm soát mức log, kiểm tra output thực trước khi bật |
| Exception handling | URI, header hay message chứa bí mật do input gây ra | Error response/log theo mã lỗi và trace ID, không nhúng raw input |
| Distributed tracing/APM | URL, request headers, baggage, attributes | Header capture allowlist, sanitize URL, bảo vệ exporter |
| Metrics | URL đầy đủ, user ID, token hoặc query làm label | Chỉ dùng nhãn có cardinality giới hạn như route ID/status |
| Log của backend/sidecar | Authorization/Cookie sau khi proxy | Xóa credential khi không cần; áp cùng logging policy |
| Support/debug tool | HAR, curl verbose, screenshot, heap dump | Redaction, quyền truy cập, retention và quy trình chia sẻ |

**Không gọi `request.getHeaders().toString()`, `exchange.toString()` hoặc serialize nguyên request để log** rồi mong middleware mặc định luôn che được token. Một bộ serializer mới, custom filter hoặc nâng cấp thư viện có thể thay đổi cách trình bày header và lộ giá trị.

### Wiretap và log level

Trong những dòng Gateway WebFlux hỗ trợ các property tương ứng, một cấu hình chủ đích **không bật wiretap** là:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          httpclient:
            wiretap: false
          httpserver:
            wiretap: false
~~~

**Đừng nhầm nó với việc vô hiệu hóa tất cả logging.** Đây là ví dụ cấu hình ở một namespace Gateway; các phiên bản cũ thường dùng prefix `spring.cloud.gateway.httpclient.wiretap` và `spring.cloud.gateway.httpserver.wiretap`. Reactor Netty, server container, ingress, Spring Security và APM còn có logging riêng. Cần kiểm tra property thực sự được bind và xem log trong môi trường thử nghiệm.

Tránh bật đồng loạt `TRACE` cho `reactor.netty`, `org.springframework.security` hoặc ghi HTTP wire data khi xử lý token thật. Nếu bắt buộc chẩn đoán sự cố, sử dụng **dữ liệu giả**, thời gian bật ngắn, phân quyền log và quy trình xóa dữ liệu theo chính sách.

### Chú ý access log của URL

Ngay cả log chỉ chứa `request URI` cũng nguy hiểm khi token đi qua query:

~~~text
GET /callback?code=<authorization-code>&state=<state> HTTP/1.1
GET /stream?access_token=<token> HTTP/1.1
~~~

Không cố “chữa” bằng cách chỉ che Authorization header. Authorization code và access token đều có thể bị lộ qua URL logging, browser history, referrer hoặc monitoring. Cần thiết kế giao thức phù hợp và **tắt/che raw query** ở những nơi ghi log callback hoặc streaming.

## 10. Mẫu GlobalFilter chỉ ghi metadata an toàn

Một cách làm đơn giản là **chỉ log field được phép**, không lấy toàn bộ request headers hoặc body. Ví dụ trong Gateway Server WebFlux:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.cloud.gateway.filter.GatewayFilterChain;
import org.springframework.cloud.gateway.filter.GlobalFilter;
import org.springframework.cloud.gateway.route.Route;
import org.springframework.core.Ordered;
import org.springframework.http.HttpStatusCode;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

import static org.springframework.cloud.gateway.support.ServerWebExchangeUtils
        .GATEWAY_ROUTE_ATTR;

@Component
public class SafeGatewayAccessLogFilter implements GlobalFilter, Ordered {

    private static final Logger log =
            LoggerFactory.getLogger(SafeGatewayAccessLogFilter.class);

    @Override
    public int getOrder() {
        return -1000;
    }

    @Override
    public Mono<Void> filter(ServerWebExchange exchange, GatewayFilterChain chain) {
        String method = exchange.getRequest().getMethod() == null
                ? "UNKNOWN"
                : exchange.getRequest().getMethod().name();

        return chain.filter(exchange).doFinally(signal -> {
            Route route = exchange.getAttribute(GATEWAY_ROUTE_ATTR);
            String routeId = route == null ? "unmatched" : route.getId();
            HttpStatusCode status = exchange.getResponse().getStatusCode();
            String statusText = status == null
                    ? "unknown"
                    : Integer.toString(status.value());

            // Không log URI đầy đủ, Authorization, Cookie, body hoặc token.
            log.info("gatewayRoute={} method={} status={} signal={}",
                    routeId, method, statusText, signal);
        });
    }
}
~~~

**Vì sao cách này giảm nguy cơ lộ token?**

- `route.getId()` đến từ route definition do hệ thống quản lý, không phải raw query/client path. **Vẫn cần chính sách kiểm soát route ID/metadata**, vì route ID động có thể chứa input tùy ý nếu cho phép cấu hình không đáng tin.
- `method`, `status` và `signal` là metadata giới hạn; không cần đọc credential.
- `doFinally` quan sát `onComplete`, `onError` hoặc cancellation theo Reactor; không tự subscribe hay block event-loop.
- Không gọi `getURI().toString()` nên tránh log query chứa token, authorization code hoặc thông tin tìm kiếm riêng tư.

Đây chỉ là **filter logging minh họa**. Nó không thay thế access log/proxy log, bảo mật hệ thống telemetry hoặc policy strip Authorization outbound. `GlobalFilter` cũng chỉ hoạt động trên request thuộc Gateway route; nó không tự bao phủ mọi WebFlux controller/Actuator. Nếu cần log ở lớp web application, dùng cơ chế WebFlux phù hợp và cùng nguyên tắc allowlist.

### Nếu cần trace request theo từng lần

Ưu tiên **trace ID do hệ thống quan sát tạo**, với giá trị được validate/chuẩn hóa và quyền truy cập phù hợp. Không dùng access token, session ID, raw Authorization header hoặc hash thô của token làm trace ID. Hash không làm token trở nên an toàn trong mọi trường hợp và có thể tạo mã liên kết người dùng lâu dài không được phép.

Chỉ ghi những thuộc tính thực sự cần: route ID, HTTP method, status, signal, latency và loại lỗi. **Không dùng full URL có query**, header bí mật hoặc body làm tag tracing. Khi instrument HTTP client outbound, cần áp chính sách như vậy ở cả hop Gateway → backend.

## 11. Không dùng regex “che mọi bí mật” làm tuyến phòng thủ duy nhất

Một anti-pattern phổ biến:

~~~java
// KHÔNG NÊN: ví dụ chống mẫu.
log.info("request={}", exchange.getRequest().getHeaders());
~~~

rồi áp một biểu thức chính quy lên log line để thay `Bearer ...` bằng `***`. Cách này dễ thất bại khi token:

- Có định dạng JWT, opaque, multi-line, URL-encoded hoặc bị chia qua nhiều trường.
- Nằm trong query/body/cookie chứ không phải chuỗi bắt đầu bằng `Bearer`.
- Có nhiều header cùng tên hoặc khác hoa-thường.
- Đi qua thư viện logger/exporter **trước khi bước redaction chạy**.
- Nằm trong exception stack, debug snapshot, HTTP wiretap hoặc message payload.

**Tốt nhất là không thu thập giá trị bí mật ngay từ đầu.** Khi bắt buộc ghi một tập header rất nhỏ để chẩn đoán, tạo danh sách cho phép như `User-Agent` hoặc một correlation ID đã được kiểm tra đầu vào; với các header có thể chứa dữ liệu người dùng, vẫn cần đánh giá lại. Cấu hình logger/trace exporter sao cho chúng không thu thập Authorization, Cookie và Set-Cookie ngay từ đầu.

### Kiểm tra response header nữa

Rò rỉ không chỉ nằm ở request:

~~~http
HTTP/1.1 200 OK
Set-Cookie: SESSION=<session-secret>; Secure; HttpOnly; SameSite=Lax
~~~

Response logger, body dumper hoặc support tool có thể ghi `Set-Cookie` và vô tình tiết lộ session. Nếu Gateway trả token ở JSON body của login, response body logging cũng có thể lộ token. Chính sách “không log secrets” phải áp dụng **cả hai chiều**.

## 12. Session cookie, refresh token và CSRF

Một Gateway có thể nhận yêu cầu từ browser thông qua session cookie thay vì Bearer Authorization header. Các cookie an toàn thường cần thuộc tính:

~~~http
Set-Cookie: SESSION=<opaque-secret>; Path=/; Secure; HttpOnly; SameSite=Lax
Cache-Control: no-store
~~~

Đây là **minh họa chính sách**: lựa chọn `SameSite=Lax` hay `Strict`/`None` phụ thuộc login flow, origin và nhu cầu cross-site. `SameSite=None` phải đi kèm `Secure` trên browser hiện đại. Thuộc tính `HttpOnly` giảm nguy cơ JavaScript đọc cookie nhưng **không vô hiệu hóa XSS hoặc CSRF**, và `Secure` chỉ yêu cầu cookie đi qua HTTPS, không làm nó an toàn khi bị đưa vào log hoặc gửi cho service không được phép.

### Cookie forwarding không giống cookie của browser

Browser tự quản lý việc gửi cookie theo domain, path, SameSite và Secure. Sau khi nhận Cookie, Gateway trở thành **HTTP client mới** khi gọi upstream. Nếu copy nguyên header `Cookie` xuống một service khác, bạn đang truyền giá trị ngoài cơ chế chọn cookie của browser. Không cho rằng browser sẽ tự chặn Gateway làm việc đó.

Với một ứng dụng sử dụng session **chỉ tại Gateway**, backend không cần biết `SESSION`. Hãy xóa cookie session khi proxy nếu không có contract cụ thể. Với mô hình backend tự xác thực session, phải quyết định session store, cookie scope, domain, CSRF, bảo mật hop và phương án thu hồi rõ ràng.

### Refresh token và session store

Refresh token nên được giữ trong thành phần có quyền làm mới access token, được mã hóa/bảo vệ phù hợp khi lưu, giới hạn quyền truy cập và có rotation/revocation theo thiết kế Authorization Server. **Không chuyển refresh token xuống Catalog hoặc Orders service** chỉ vì hệ thống dùng OAuth2.

Không đưa refresh token vào baggage/trace attributes, Redis key dễ lộ, log của token store hoặc error body. Ngay cả khi lưu token trong Redis/session store, hãy bảo vệ ACL, TLS giữa các service, TTL, encryption policy và khả năng truy cập console/admin.

### CSRF và CORS không thay thế việc giữ bí mật token

Nếu xác thực bằng cookie/session do browser tự gửi, cần bảo vệ **CSRF** cho thao tác thay đổi trạng thái. Nếu frontend gọi API cross-origin, cần chính sách **CORS** có Origin allowlist phù hợp và preflight được xử lý trước authentication khi thiết kế yêu cầu.

CORS chỉ kiểm soát hành vi của **browser**; nó không ngăn một HTTP client hoặc Gateway đã có token gửi token sang host khác. Tương tự, CSRF protection không ngăn dev bật wiretap hoặc in session cookie vào log.

## 13. Không đặt token trong URL, path hoặc fragment để tiện định tuyến

Một Bearer token trong query:

~~~http
GET /api/reports?access_token=<secret> HTTP/1.1
~~~

có thể xuất hiện trong:

- Reverse proxy, CDN hoặc Gateway access logs.
- Browser history và bookmark.
- Analytics/monitoring sử dụng raw URL.
- Link được sao chép cho support hoặc đối tác.
- Referer trong một số trường hợp điều hướng và chính sách browser.
- Cơ chế cache nếu URL được dùng làm khóa/cache metadata.

**Khuyến nghị:** Với API HTTP thông thường, dùng `Authorization: Bearer ...` qua HTTPS và đưa ra chính sách header logging/forwarding rõ ràng. Không đặt refresh token vào query hoặc path. Fragment `#...` không đi trong request-target HTTP thông thường, nhưng vẫn có thể bị JavaScript, browser extension hoặc client-side analytics đọc; vì vậy **không coi fragment là nơi lưu credential an toàn**.

### OAuth2 callback có authorization code

Authorization Code flow có thể mang một **authorization code ngắn hạn** trong callback URL theo protocol. Mặc dù code khác access token, đây vẫn là dữ liệu nhạy cảm. Với Authorization Code + PKCE, code bị đánh cắp riêng lẻ thường chưa đủ để đổi token nếu thiếu `code_verifier` hợp lệ, nhưng đó **không phải lý do được phép log code**.

Hãy tránh log query của callback, bảo vệ `state`/`code_verifier`, ràng buộc redirect URI và dùng TLS. Khi có lỗi callback, trả một error code/trace ID an toàn thay vì in `code`, `state` hay raw URL trong response.

### WebSocket và EventSource

Một số browser API có hạn chế về cách tự gắn Authorization header (ví dụ WebSocket browser API và native EventSource). Đừng xử lý bằng cách chuyển access token dài hạn sang `?token=...` rồi bỏ qua logging policy.

Các hướng thiết kế cần đánh giá theo ứng dụng:

- Session cookie được bảo vệ đúng `Secure`, `HttpOnly`, SameSite/CSRF và **Origin validation** cho WebSocket handshake.
- Một bước HTTP authenticated trước để cấp **ticket ngắn hạn, ràng buộc audience và dùng một lần** cho kết nối realtime, với chính sách tuyệt đối không log ticket.
- Một client có khả năng đặt header Authorization theo giao thức và môi trường thực tế, nếu đáp ứng bảo mật.

Không có cách nào ở trên tự động an toàn; cần kiểm tra tình huống token/ticket bị ghi vào access log của ingress và rủi ro replay. **HTTP keep-alive không bảo vệ bearer token**; TLS chỉ bảo vệ khi truyền, không bảo vệ bản sao trong log hoặc ở một upstream không đáng tin.

## 14. Tracing, baggage và metrics: credential không phải thông tin quan sát

Distributed tracing rất hữu ích để tìm vì sao một request qua Gateway bị lỗi do route predicate, filter chain, Spring Cloud LoadBalancer, timeout hoặc CircuitBreaker. Nhưng **trace propagation** không nên mang Bearer token như một attribute/baggage item.

Ví dụ những thông tin có thể hợp lý:

~~~text
gateway.route.id = orders-private
http.request.method = GET
http.response.status_code = 200
upstream.service = orders-service
error.type = connection_timeout (nếu có)
trace_id = <generated-id>
~~~

Những thông tin **không phù hợp** làm tags/labels:

~~~text
http.request.header.authorization = Bearer <token>
http.request.header.cookie = SESSION=<secret>
url.full = /api/orders/42?access_token=<secret>
user.access_token = <token>
session.id = <session-id>
~~~

**Baggage** trong hệ thống tracing có thể được chuyển giữa nhiều service, nên đặt credential trong baggage còn gây **lan truyền bí mật**. Token không nên được dùng làm correlation ID; request ID/trace ID phải có semantics riêng và được kiểm soát khi nhận từ client.

Các quy tắc thực tế:

1. Chỉ capture một **allowlist** các HTTP headers không nhạy cảm.
2. Xóa query string khỏi span name/URL attribute hoặc sanitize theo whitelist tham số có nhu cầu chính đáng.
3. Dùng **route template hoặc route ID** thay vì full raw path/query làm metric label.
4. Hạn chế số lượng nhãn; token, session ID và user ID thường có cardinality rất lớn.
5. Áp redaction cả ở SDK/agent **trước khi gửi dữ liệu** và ở collector/exporter như tuyến phòng vệ bổ sung.
6. Kiểm soát quyền xem traces/logs, nơi lưu, retention, export sang bên thứ ba và quy trình xóa dữ liệu.

### Ghi lỗi thay vì ghi bí mật

Khi JWT validation thất bại, ghi:

~~~text
route=orders-private result=authentication_failed cause=expired_token
~~~

thay vì:

~~~text
Authorization failed for Bearer eyJ...
~~~

Tên loại lỗi cần được chuẩn hóa để không đưa toàn exception message chứa input thô vào log. Việc trích thông tin như issuer/subject/tenant cũng cần đánh giá dữ liệu cá nhân và ranh giới truy cập; không mặc định mọi claim trong JWT đều phù hợp làm log.

## 15. TLS bảo vệ đường truyền nhưng không quyết định đối tượng nhận

Hai hop cần xét riêng:

~~~mermaid
flowchart LR
    Client[Client] -->|HTTPS / TLS 1| Gateway[Spring Cloud Gateway]
    Gateway -->|HTTPS / TLS 2| Upstream[Trusted backend]
~~~

TLS hop client → Gateway bảo vệ credential khi client gửi qua mạng. Nếu TLS kết thúc tại ingress, Gateway có thể nhận HTTP trong mạng nội bộ, và vẫn cần network segmentation/giới hạn tin cậy phù hợp. Với Gateway → backend, hãy xác minh:

- **HTTPS thực sự được dùng** khi policy yêu cầu.
- Certificate chain, hostname/SAN và truststore hợp lệ; **không tắt verification** cho đỡ lỗi.
- Với service discovery, `lb://` được resolve thành host/port/secure scheme đúng và thuộc vùng tin cậy.
- Nếu dùng **mTLS**, service identity trong chứng chỉ được kiểm tra và gắn với quyền truy cập.
- Proxy/sidecar không tự chuyển token sang một destination khác theo cấu hình rewrite hoặc redirect không được duyệt.

**HTTPS đến một vendor không được phép vẫn là rò rỉ token.** TLS bảo vệ dữ liệu trên đường tới **người nhận**, nhưng không biến người nhận thành đối tượng được phép có credential.

Đối với các header `Forwarded`/`X-Forwarded-Host`, chỉ tin nguồn proxy đã được xác thực hoặc do hạ tầng kiểm soát. Nếu một custom GatewayFilter dùng giá trị này để dựng URL outbound hoặc redirect, có thể dẫn tới host do client chỉ định. Chỉ dùng allowlist và xác minh URI cuối.

## 16. Thất bại giữa luồng, retry và CircuitBreaker cũng có thể nhân bản token

Gateway có thể gọi upstream nhiều lần khi dùng Retry GatewayFilter hoặc cơ chế phục hồi tương tự. Mỗi lần retry có thể gửi **lại Authorization header**, request body hoặc credential khác cho instance được chọn. Nếu một retry chọn đích không đáng tin do cấu hình/discovery sai, token có thể bị gửi nhiều lần.

**Retry phải được xem là một phần của egress policy:**

- Mọi attempt cần tuân theo cùng chính sách audience/destination/credential.
- Đừng retry sang một service khác chỉ vì nó cùng interface nếu service đó không được phép nhận token.
- Giới hạn số lần, deadline và phương thức HTTP được phép retry.
- Với `POST /orders` hoặc thanh toán, cần idempotency key và hợp đồng backend để tránh lặp side effect.
- Không đưa Authorization, Cookie hoặc toàn exception chứa headers vào log retry/circuit breaker.

**CircuitBreaker fallback** có thể dùng URI nội bộ `forward:/internal/fallback` để tạo response. Handler fallback không nên log toàn exchange, cũng không được xem phần client-supplied Authorization là bằng chứng ủy quyền nếu không đi qua security context đáng tin. Không để lỗi auth 401/403 bị fallback thành 200 thành công giả.

### Response đã commit thì không thể “đổi sang 401”

Với SSE/NDJSON, response có thể đã gửi status 200 và một phần body. Khi upstream gặp lỗi hoặc một dependency auth bị thu hồi trong lúc stream, Gateway không thể quay về thay status/header đã commit. Thiết kế stream cần cơ chế hết hạn/đóng kết nối, làm mới quyền và reconnect nếu phù hợp; **không ghi token của stream vào sự kiện lỗi** gửi cho client.

## 17. Một GatewayFilter tùy chỉnh để minh họa cách loại credential

Khi filter có sẵn `RemoveRequestHeader` đáp ứng yêu cầu, **hãy ưu tiên dùng nó**. Trong một số tình huống cần logic có điều kiện, có thể viết `GatewayFilter` thực hiện việc xóa các credential được quy định **trước khi chuyển request sang filter tiếp theo**.

~~~java
import org.springframework.cloud.gateway.filter.GatewayFilter;
import org.springframework.http.HttpHeaders;
import org.springframework.http.server.reactive.ServerHttpRequest;

final class CredentialStrippingGatewayFilter {

    private CredentialStrippingGatewayFilter() {}

    static GatewayFilter forAnonymousUpstream() {
        return (exchange, chain) -> {
            ServerHttpRequest sanitized = exchange.getRequest()
                    .mutate()
                    .headers(headers -> {
                        headers.remove(HttpHeaders.AUTHORIZATION);
                        headers.remove(HttpHeaders.COOKIE);
                        headers.remove(HttpHeaders.PROXY_AUTHORIZATION);
                        headers.remove("X-API-Key");
                        headers.remove("X-Auth-Token");
                    })
                    .build();

            return chain.filter(
                    exchange.mutate().request(sanitized).build());
        };
    }
}
~~~

Đoạn code trên:

1. Không đọc hoặc log **giá trị** của bất kỳ token nào.
2. Tạo request decorator không chứa những header credential đã chỉ định.
3. Truyền **exchange mới** tới phần còn lại của chuỗi bằng `chain.filter(updatedExchange)`.
4. Trả lại publisher `Mono<Void>` cho framework, không tự `subscribe()` hoặc `block()`.

Nếu bạn có Java Route DSL, filter có thể được gắn **chỉ lên route đã được xét duyệt**, chẳng hạn:

~~~java
// Minh họa một đoạn trong RouteLocatorBuilder.routes().
.route("public-catalog", r -> r.path("/api/public/products/**")
        .filters(f -> f.filter(
                CredentialStrippingGatewayFilter.forAnonymousUpstream()))
        .uri("lb://catalog-service"))
~~~

Đây là **một phương án thay thế** cho các filter `RemoveRequestHeader` trong YAML ở phần 6; không cần thêm cả hai chỉ để lặp thao tác. Trong dự án thật, route DSL phải nằm trong cấu hình `RouteLocator` hoàn chỉnh với dependency đúng phiên bản.

**Giới hạn bảo mật:** Filter này chỉ bỏ các header được liệt kê **ở giai đoạn nó chạy**. Một filter về sau có thể thêm token lại; các credential trong URL/body không bị xóa; route có thể bị đổi đích. Do đó đây **không phải cơ chế egress enforcement hoàn chỉnh**. Cần policy route, nguồn discovery tin cậy, kiểm soát filter order, kiểm thử headers tại upstream và network/TLS bảo vệ như đã phân tích.

### Unit test: downstream không thấy Authorization hoặc Cookie

~~~java
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import org.springframework.cloud.gateway.filter.GatewayFilterChain;
import org.springframework.http.HttpHeaders;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.web.server.MockServerWebExchange;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.assertj.core.api.Assertions.assertThat;

class CredentialStrippingGatewayFilterTest {

    @Test
    void doesNotPassCredentialsToNextFilter() {
        MockServerWebExchange exchange = MockServerWebExchange.from(
                MockServerHttpRequest.get("/api/public/products/42")
                        .header(HttpHeaders.AUTHORIZATION, "Bearer synthetic-only")
                        .header(HttpHeaders.COOKIE, "SESSION=synthetic-only")
                        .header("X-API-Key", "synthetic-only")
                        .build());

        AtomicInteger calls = new AtomicInteger();
        GatewayFilterChain downstream = nextExchange -> {
            calls.incrementAndGet();
            HttpHeaders headers = nextExchange.getRequest().getHeaders();

            assertThat(headers.containsKey(HttpHeaders.AUTHORIZATION)).isFalse();
            assertThat(headers.containsKey(HttpHeaders.COOKIE)).isFalse();
            assertThat(headers.containsKey("X-API-Key")).isFalse();
            return Mono.empty();
        };

        StepVerifier.create(
                CredentialStrippingGatewayFilter.forAnonymousUpstream()
                        .filter(exchange, downstream)
        ).verifyComplete();

        assertThat(calls.get()).isEqualTo(1);
    }
}
~~~

Test này yêu cầu JUnit 5, Spring Test, Reactor Test và AssertJ tương thích. Nó **chỉ xác minh exchange chuyển tới filter tiếp theo**, không xác minh headers trong request do Reactor Netty thực sự gửi. Hãy bổ sung **integration test với upstream stub** để xác minh request cuối sau tất cả filters và load balancing. Token `synthetic-only` chỉ là dữ liệu giả để test; không đưa access token thật vào source code.

## 18. Ma trận kiểm thử chống rò rỉ ở hai hướng

Mục tiêu không chỉ là response HTTP 200/401/403 đúng, mà là **bí mật không xuất hiện ở nơi không được phép**. Đối với từng route, nên có các kiểm thử:

| Tình huống | Kết quả cần xác nhận |
| --- | --- |
| Request anonymous vào Catalog | Gateway gọi đúng Catalog, không tự thêm credential |
| Request mang JWT hợp lệ vào Catalog public | Catalog **không nhận Authorization/Cookie** nếu contract không cần |
| Request mang JWT của Orders vào Orders route | Chỉ chuyển khi đúng audience/policy; Orders kiểm tra lại |
| JWT sai issuer hoặc hết hạn | Security chặn theo chính sách; upstream private không bị gọi |
| JWT có authority user vào admin route | 403; backend admin không nhận request/token |
| Request vào vendor route có Authorization/Cookie/API key | Vendor stub không nhận những header bị cấm |
| Service discovery trả instance ngoài allowlist | Không được gửi credential đến instance đó; policy fail closed |
| Một filter chạy sau vô tình chèn Authorization | Integration test bắt được egress header rò rỉ |
| Backend trả redirect ra host không tin cậy | Không tự chuyển token qua hop mới ngoài chính sách |
| Login/refresh response chứa token | Logs, metrics/traces không ghi response body/Set-Cookie |
| Client gửi token trong query hoặc path | Bị từ chối hoặc xử lý theo policy đã thiết kế; không bị log/chuyển tiếp tùy tiện |
| Error, timeout, retry, CircuitBreaker fallback | Không dump header/body/token trong exception hoặc error response |
| WebSocket/SSE reconnect | Ticket/cookie/token không bị log hoặc chuyển sang service khác |

### Kiểm thử qua backend stub

Trong môi trường thử nghiệm, tạo upstream stub có khả năng **ghi nhận trong bộ nhớ** sự hiện diện của các header, ví dụ:

~~~json
{
  "receivedAuthorization": false,
  "receivedCookie": false,
  "receivedApiKey": false
}
~~~

Stub **không cần trả giá trị token**, chỉ cần trả boolean hoặc assert trên request đã nhận. Điều này giúp test tự động xác minh an toàn mà không vô tình tạo thêm một endpoint công khai chuyên echo secret.

### Canary token trong test pipeline

Tạo một **credential thử nghiệm ngắn hạn, chỉ dùng ở môi trường kiểm thử**, có giá trị nhận diện riêng; gửi qua những route phù hợp rồi quét logs, trace storage và output test để chắc chắn không xuất hiện nguyên văn. Phải quét **các sink thực**, gồm ingress, Gateway, backend stub, APM và error reporting; không chỉ đọc console của Gateway.

Nếu dùng Spring Security Resource Server, **JWT giả không có chữ ký hợp lệ có thể bị chặn 401 trước khi route public chạy**, ngay cả khi rule authorization là `permitAll`. Vì vậy test egress nên dùng JWT test **hợp lệ từ issuer kiểm thử** hoặc một môi trường test có security configuration được kiểm soát, thay vì cho rằng gửi `Bearer abc` sẽ tới filter của route.

### Curl chỉ dành cho môi trường test

~~~bash
# Không đưa token thật vào command trực tiếp hay curl -v.
# Biến này phải chứa token TEST có thời hạn ngắn từ môi trường kiểm thử.
curl -i \
  -H "Authorization: Bearer ${TEST_ACCESS_TOKEN}" \
  'http://localhost:8080/api/public/products/42'

# Thử route yêu cầu auth, backend tự kiểm tra audience/scope.
curl -i \
  -H "Authorization: Bearer ${TEST_ACCESS_TOKEN}" \
  'http://localhost:8080/api/orders/42'
~~~

Lệnh này mô tả cách gọi để kiểm thử, **không phải bằng chứng đã chạy**. Chạy local/HTTPS trong lab, không dùng token production; lưu ý đối số process, terminal history, CI logs và shell tracing có thể lộ thông tin nếu không được kiểm soát. Trong kiểm thử tự động, hãy dùng secret management và HTTP client test phù hợp để không ghi token vào process args/log.

## 19. Tình huống sự cố và cách ứng phó khi phát hiện token lộ

Giả sử một ngày phát hiện log `TRACE` của Gateway đã lưu nguyên Authorization header trên route Orders. Tắt log ngay là cần thiết nhưng **chưa đủ**, vì token có thể đã nằm trong nhiều bản sao của log và APM.

Một quy trình ứng phó ở mức khái niệm:

1. **Giới hạn phạm vi ngay:** tắt chế độ dump/wiretap không cần thiết, dừng exporter có lỗi và chặn quyền xem log không phù hợp; giữ bằng chứng theo chính sách ứng phó sự cố.
2. **Xác định loại bí mật bị lộ:** access token, refresh token, session cookie hay signing key? Tác động và biện pháp khắc phục khác nhau.
3. **Xác định thời gian và nơi lưu:** Gateway, ingress, sidecar, backend, APM, SIEM, backups, support attachments và môi trường test/production.
4. **Thu hồi/giảm khả năng sử dụng lại:** revoke hoặc vô hiệu hóa token/session nếu IdP/session store hỗ trợ; với token ngắn hạn không có revocation tức thời, kết hợp TTL, hạn chế quyền và phát hiện sử dụng bất thường.
5. **Đổi bí mật khi phù hợp:** rotation refresh token/API key hoặc credential bị lộ; **không tự động cho rằng phải thay signing key toàn hệ thống** chỉ vì một access token đã lộ, trừ khi bằng chứng cho thấy khóa ký hoặc hệ thống phát hành bị ảnh hưởng.
6. **Kiểm tra truy cập bất thường:** dấu hiệu token được sử dụng ngoài dự kiến, route/service không hợp lệ hoặc action admin lạ. Tránh đưa token thật vào cảnh báo.
7. **Xử lý dữ liệu đã lưu:** áp chính sách xóa, retention, legal hold, thông báo và kiểm soát bản sao theo quy định tổ chức.
8. **Khắc phục gốc:** đổi logging sang allowlist, thêm egress stripping/policy, kiểm soát route/discovery, bổ sung integration tests.
9. **Phòng tái diễn:** rà tác động của nâng cấp framework, bật debug, thay APM instrumentation và thay cấu hình ingress.

Nếu chỉ lộ **access token của một người dùng**, việc thu hồi token/session của người đó có thể là bước phù hợp hơn việc vô hiệu hóa toàn hệ thống. Nếu lộ **refresh token có quyền mở rộng**, cần xem khả năng cấp access token mới; nếu lộ **khóa ký hoặc secret của OAuth2 client**, phạm vi xử lý có thể lớn hơn nhiều.

### Cần thiết kế cách cảnh báo mà không lặp lại sự cố

Một hệ thống phát hiện credential trong log không nên gửi **chính chuỗi credential** vào Slack/email/ticket của cả nhóm. Hãy cảnh báo với loại rò rỉ, vị trí sink, khoảng thời gian, ID sự cố và một tham chiếu kiểm soát truy cập. Công cụ quét secret có thể dùng dấu hiệu/hệ thống nhận diện riêng và policy hạn chế quyền đọc; không tạo kho tập trung chứa thêm bản sao token.

## 20. Checklist triển khai an toàn cho Spring Cloud Gateway

Trước khi đưa một route mới vào production, hãy kiểm tra theo từng lớp:

| Lớp | Câu hỏi kiểm tra | Bằng chứng mong đợi |
| --- | --- | --- |
| **Phân loại route** | Public, authenticated, admin, internal hay third party? | Danh mục route có owner và security policy |
| **Authentication** | Token đầu vào được xác minh chữ ký, issuer, thời hạn và audience phù hợp? | Test token hợp lệ/hỏng và policy Spring Security |
| **Authorization** | Caller có đúng scope/role/quyền tài nguyên? | Test anonymous/user/admin và backend ownership |
| **Token egress** | Route có thật sự cần token? Loại nào, audience nào? | Policy allowlist/strip token và test backend |
| **Các credential khác** | Có cần Cookie, API key, Proxy-Authorization, refresh token không? | Test không forward ngoài nhu cầu |
| **URI đích** | Route, redirect, discovery và host/port có do nguồn tin cậy kiểm soát? | Registry/route RBAC, host allowlist và network policy |
| **TLS/mTLS** | Có xác minh certificate và service identity trên hop outbound? | Test TLS, truststore, hostname và mTLS nếu cần |
| **Logging** | Có log full headers, query, body, Set-Cookie hoặc lỗi chứa secrets không? | Kiểm tra cấu hình và kết quả canary test |
| **Tracing/metrics** | Có capture Authorization, Cookie, token trong URL/baggage/tags không? | Kiểm tra span payload, exporter và metric labels |
| **HTTP filters** | RemoveRequestHeader có chạy trước egress? Filter sau có thể thêm token lại không? | Integration test với upstream stub |
| **Error/retry** | Retry/fallback có thể chuyển token sang đích khác hoặc in bí mật không? | Test timeout, no-instance, redirect, retry |
| **Quản trị** | Actuator, route definitions, config, diagnostics và logs có bị lộ không? | Access control, chỉ bật endpoint cần thiết |
| **Lưu trữ** | Access/refresh token và session được giữ trong store phù hợp? | TTL, rotation/revocation, encryption và ACL |
| **Ứng phó sự cố** | Nếu token lộ, có cách tìm các bản sao và thu hồi không? | Runbook, alert an toàn, quy trình xóa/rotation |

Đặc biệt, một route có thể **hợp lệ về mặt functional** nhưng **không đạt an toàn**. Ví dụ:

~~~text
GET /api/public/products/42 -> 200 OK
~~~

không chứng minh backend **không nhận access token**, CDN **không ghi query**, hoặc telemetry **không thu thập Cookie**. Kiểm thử an ninh cần bằng chứng về **đích nhận và các sink lưu dữ liệu**, không chỉ status và JSON body.

### Quy tắc bổ sung cho route động

Nếu ứng dụng cho phép tạo/sửa route khi runtime đang chạy, mỗi thay đổi phải qua review và kiểm thử tự động tương tự code deployment:

1. Không route từ Internet tới địa chỉ nội bộ/metadata endpoint ngoài allowlist.
2. Không cho một service ID mới tự được nhận user/admin token.
3. Không thay `https://` bằng `http://` khi hop outbound yêu cầu bảo mật.
4. Không thêm `TokenRelay` hoặc `SetRequestHeader=Authorization` vào route vendor nếu không có phê duyệt.
5. Không mở Actuator/Gateway route-management endpoint ra Internet để client không tin cậy tự chỉnh egress.
6. Không dùng query/header người dùng để tự chọn URI proxy, và không dựa vào route ID duy nhất khi resolved host có thể bị đổi.

**Fail closed:** nếu không xác nhận được service identity, audience hoặc quyền gửi token, đừng phát tán credential “để thử xem backend có chấp nhận không”.

## 21. Bài thực hành tổng hợp: bảo vệ một route public và một route private

**Bối cảnh:** Cổng API phục vụ Catalog public, Orders cần đăng nhập, Admin yêu cầu scope riêng và một dịch vụ recommendations bên ngoài. Gateway dùng filter chain, discovery, TLS và tracing. Nhóm phải chứng minh **token không xuất hiện trong log và không được forward tới service không được phê duyệt**.

### Phần A — Thiết kế chính sách egress

1. Lập ma trận tương tự phần 5: route ID, URI, service identity, loại credential, audience, authority, việc có/không được chuyển token.
2. Đặt chính sách **mặc định không forward** token cho route không có trong allowlist.
3. Trên Catalog và Vendor, dùng `RemoveRequestHeader` xóa `Authorization`, `Cookie`, API key và custom token headers không cần thiết.
4. Đối với Orders, quyết định token của client có đúng audience hay cần token exchange; backend phải kiểm tra quyền với từng đơn hàng.
5. Đối với Admin, kiểm tra authority và service identity trên TLS/mTLS nếu policy yêu cầu; tránh gửi cùng credential tới service analytics.

### Phần B — Cấu hình logging an toàn

1. Tắt wiretap HTTP server/client hoặc xác minh rằng nó không được bật trong môi trường có credential thật.
2. Thêm `SafeGatewayAccessLogFilter` ở phần 10 hoặc dùng logging/metrics framework tương đương, chỉ ghi route ID, method, status, signal và latency nếu cần.
3. Cấu hình ingress, sidecar, backend stub và APM không lưu `Authorization`, `Cookie`, `Set-Cookie`, raw query hoặc login body.
4. Đảm bảo JWT validation error và CircuitBreaker fallback không ghi toàn exception/message chứa token.

### Phần C — Chạy test theo ranh giới tin cậy

1. Dùng access token **test hợp lệ** từ issuer test, có audience và scope đúng, gọi Catalog public. Upstream stub phải xác nhận **không có Authorization/Cookie**.
2. Gọi Orders với token audience Orders phù hợp; backend xác minh token và trả dữ liệu đúng quyền sở hữu.
3. Gọi Admin bằng token user thường; Gateway từ chối và upstream admin **không được gọi**.
4. Gọi Vendor với token test và API key giả; stub không thấy credential từ client.
5. Thay host của một instance discovery hoặc một route test sang đích **không nằm trong allowlist**; xác nhận policy không cho token được gửi.
6. Thử bật một filter thêm Authorization sau bước remove trong **môi trường test cô lập**; integration test phải phát hiện rò rỉ, sau đó loại bỏ filter sai.
7. Gửi request lỗi/timeout/retry và kiểm tra trace/APM/exported logs không chứa credential có thể sử dụng lại.

### Phần D — Rà token trong URL và phiên đăng nhập

1. Gửi request kiểm thử chứa tham số mang tên `access_token` với **giá trị giả**; ghi nhận route xử lý theo policy từ chối/sanitize. Không dùng token thật.
2. Kiểm tra login/OAuth2 callback không để code, verifier, access token hay refresh token trong access log.
3. Kiểm tra `Set-Cookie` của response session không được dump sang log/trace.
4. Thử SSE/WebSocket handshake trong lab; xác minh ticket hoặc credential đi theo hợp đồng và không bị log bởi ingress.
5. Kiểm tra token/secret test hết hạn hoặc được thu hồi sau khi kết thúc bài thực hành.

**Tiêu chí đạt:** (1) Đích được phê duyệt nhận đúng credential cần thiết; (2) Catalog/Vendor không nhận token/cookie trái phép; (3) backend private/admin xác minh đúng token/audience/quyền; (4) logs, traces, metrics, error responses và debug artifacts không chứa token thô; (5) TLS và nguồn route/discovery được bảo vệ; (6) có ma trận test, bằng chứng từ upstream stub và runbook ứng phó khi phát hiện rò rỉ.

## 22. Hiểu lầm thường gặp

| Nhận định sai | Điều đúng |
| --- | --- |
| “Đã validate JWT ở Gateway thì Authorization không bị forward.” | Validation và forwarding là hai quyết định; phải kiểm tra outbound headers thực tế. |
| “Service chạy trong VPC nên có thể nhận mọi token.” | Mạng nội bộ không đồng nghĩa mọi service là audience hoặc trust domain phù hợp. |
| “Token được truyền qua HTTPS thì gửi cho vendor nào cũng an toàn.” | TLS bảo vệ đường truyền, không cấp quyền cho người nhận. |
| “Gắn TokenRelay sẽ tự bảo vệ các route private.” | TokenRelay cần OAuth2 client context và không thay thế authentication/authorization/audience checks. |
| “Chỉ cần xóa Authorization trên route public.” | Cần kiểm tra Cookie, API key, query, body, Set-Cookie, filters về sau và các sink log/tracing. |
| “Che chữ Bearer bằng regex là đủ.” | Nhiều loại secret và nhiều sink khác nhau; ưu tiên không thu thập bí mật ngay từ đầu. |
| “Tắt Gateway log thì không còn lộ token.” | Ingress, CDN, backend, Netty wiretap, APM, SIEM hoặc support artifacts vẫn có thể lưu. |
| “Tên route nằm trong allowlist nên host đã đáng tin.” | Service discovery, route rewrite và redirect có thể thay đổi đích thực; cần kiểm tra trust tới endpoint cuối. |
| “CORS sẽ ngăn token bị forward đến service khác.” | CORS là chính sách browser, không kiểm soát việc Gateway proxy token. |
| “Một JWT có chữ ký đúng có thể được dùng ở mọi microservice.” | Phải xác minh issuer, expiry, audience, scope và quyền tài nguyên; có thể cần token exchange. |
| “Tắt log là đủ xử lý vụ lộ token.” | Bản sao cũ vẫn tồn tại; cần thu hồi/rotation phù hợp và quy trình quản lý sự cố. |

## 23. Tổng kết

- **Access token, refresh token, ID token, session cookie và API key có mục đích khác nhau**; không mặc định mọi credential được phép đi cùng mọi request.
- **Xác thực ở Gateway không tự động tạo chính sách outbound an toàn.** Mỗi route cần quyết định đích, audience/scope và loại credential được phép chuyển tiếp.
- Dùng `RemoveRequestHeader` hoặc một filter có kiểm thử để **loại Authorization, Cookie và các bí mật không cần thiết** khỏi request gửi đến Catalog public, vendor hoặc service không có quyền nhận.
- **TokenRelay chỉ là cơ chế truyền access token trong ngữ cảnh OAuth2 Client thích hợp**; không thay thế policy về audience, service identity, TLS, authorization và token exchange khi cần.
- **Không log raw headers, query string, request/response body nhạy cảm, Cookie, Set-Cookie, JWT hoặc authorization code**. Dùng allowlist metadata an toàn như route ID, method, status và trace ID hợp lệ.
- **Wiretap, ingress logs, APM, tracing baggage, metrics và error handlers** đều là những nơi có thể rò rỉ bí mật; phải kiểm tra cả đường inbound và outbound.
- **Service discovery, route động, redirect, retry và fallback** có thể làm thay đổi nơi credential được gửi hoặc làm nhân bản các request. Bảo vệ nguồn route, đích thực, network egress và TLS/mTLS.
- **Kiểm thử từ phía backend stub và telemetry sink** mới chứng minh token không bị forward/log trái phép. Nếu đã lộ, cần xử lý cả bí mật và các bản sao trong hệ thống lưu trữ, không chỉ tắt debug.

Giữ token đúng **người nhận, mục đích, thời hạn và phạm vi quyền** là điều kiện nền tảng để Spring Cloud Gateway trở thành điểm vào microservices an toàn mà vẫn quan sát và vận hành được.
