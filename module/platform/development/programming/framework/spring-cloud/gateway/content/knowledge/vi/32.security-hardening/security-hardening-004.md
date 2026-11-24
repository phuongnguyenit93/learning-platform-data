# Loại bỏ header danh tính giả mạo và chỉ tin proxy đã xác minh

## 1. Vì sao header danh tính trở thành điểm yếu của API Gateway?

Trong kiến trúc microservices, **Spring Cloud Gateway** là cổng vào xử lý route predicate, filter chain, biến đổi path/header, service discovery, xác thực, giới hạn lưu lượng, circuit breaker, retry, TLS và quan sát request. Gateway thường nằm giữa client và các backend vốn **không được trực tiếp tiếp xúc Internet**. Nếu backend tin một header tùy ý do client gửi, vị trí trung tâm của Gateway có thể bị lợi dụng để **nâng quyền hoặc giả danh người dùng**.

Giả sử dịch vụ đơn hàng có logic sai:

~~~java
// Ví dụ PHẢN DIỆN; không dùng làm authorization production.
@GetMapping("/orders")
public Object listOrders(@RequestHeader("X-User-Id") String userId) {
    return orderService.findByOwner(userId);
}
~~~

Một client không có quyền vẫn có thể gửi:

~~~http
GET /api/orders HTTP/1.1
Host: api.example.test
X-User-Id: administrator
X-Role: admin
X-Tenant-Id: finance
X-Forwarded-For: 10.0.0.9
~~~

Nếu Gateway **chuyển tiếp nguyên** các header đó và backend coi chúng là thông tin xác thực, client đã tự chọn danh tính và tenant. Tương tự, nếu một route quản trị cho phép IP nội bộ và Gateway tin `X-Forwarded-For` do client tự khai, kẻ tấn công có thể cố vượt IP allowlist.

Chủ đề **“Loại bỏ header danh tính giả mạo và chỉ tin proxy đã xác minh”** thuộc chương **Gia cố bảo mật** của module **SPRING_CLOUD_GATEWAY**. Bài này tập trung vào **ranh giới tin cậy giữa client → edge/reverse proxy → Gateway → backend**, không coi việc thêm một header bằng `AddRequestHeader` là cơ chế xác thực.

Sau bài, bạn có thể:

1. Phân loại header **client-controlled**, **proxy metadata**, **verified identity** và **hop-by-hop**.
2. Loại bỏ header danh tính giả mạo bằng `RemoveRequestHeader` hoặc một `WebFilter` sớm.
3. Cấu hình xác thực JWT bằng Spring Security WebFlux và phân quyền theo scope/role.
4. Chỉ tạo header nội bộ từ **principal/claims đã xác minh**, với ràng buộc backend có thể tin Gateway.
5. Xác định nguồn đáng tin của `Forwarded`, `X-Forwarded-For`, `X-Forwarded-Proto`, `X-Forwarded-Host` và số proxy hops.
6. Tránh `trustAll()`, cấu hình nhầm `trusted-proxies` hoặc tin trực tiếp client-supplied IP.
7. Thực hiện lab và ma trận kiểm thử chống giả mạo danh tính, trùng header, direct-backend access và IP spoofing.

> **Quy tắc chính:** *Danh tính đã xác minh phải xuất phát từ cơ chế xác thực và đường truyền có kiểm soát, không từ bất kỳ header nào mà client có thể tự đặt.* Header nội bộ do Gateway tạo cũng **không tự bảo mật** nếu backend có thể bị gọi trực tiếp hoặc một thành phần khác có thể giả làm Gateway.

## 2. Phân biệt bốn nhóm header

| Nhóm | Ví dụ | Ai có thể cung cấp? | Mức tin cậy mặc định |
| --- | --- | --- | --- |
| Header request thông thường | `Accept`, `User-Agent`, `X-Request-Id` | Client/proxy | **Không đáng tin** cho quyết định bảo mật |
| Header tuyên bố danh tính/ủy quyền | `X-User-Id`, `X-Role`, `X-Tenant-Id`, `X-Authenticated-User` | Client có thể giả mạo | **Không tin** nếu chưa được edge/Gateway tái tạo từ nguồn xác minh |
| Forwarding/proxy metadata | `Forwarded`, `X-Forwarded-For`, `X-Forwarded-Proto`, `X-Forwarded-Host` | Client hoặc reverse proxy | Chỉ tin **sau khi** xác minh proxy hop và chính sách rewrite |
| Hop-by-hop/transport | `Connection`, `Transfer-Encoding`, `Keep-Alive`, `TE` | Nhiều tầng HTTP | Không chuyển tiếp tùy tiện; dùng bộ lọc transport phù hợp |

Một số tiêu chí:

- `Authorization: Bearer ...` là **credential do client gửi**, không phải khẳng định danh tính đã xác minh. Chỉ sau khi kiểm tra chữ ký/issuer/audience/expiry/scopes mới có principal đáng tin.
- `Cookie: SESSION=...` cũng là chuỗi client gửi; phải kiểm tra tính hợp lệ của session, CSRF và ràng buộc cookie trước khi dùng.
- `X-User-Id` hoặc `X-Tenant-Id` không có chuẩn HTTP tự bảo đảm chữ ký. Đổi tên thành `X-Trusted-User` cũng **không** làm nó đáng tin hơn.
- `X-Forwarded-For` là metadata về chuỗi proxy, **không phải chứng thư xác thực** và không nên được dùng làm role hoặc tenant.
- `Host`/`Forwarded: host=...`/`X-Forwarded-Host` có thể ảnh hưởng lựa chọn route và URL tuyệt đối; kiểm tra trước khi dùng cho redirect/callback.
- Một header có thể xuất hiện **nhiều giá trị**, đổi kiểu viết hoa/thường, dùng ký tự gạch dưới hoặc bị intermediary gộp dấu phẩy. Chính sách cần xét cả dạng trùng và normalization.

### 2.1. Ví dụ một quyết định sai

~~~java
// Sai: khách hàng tự chọn role bằng HTTP request.
String role = exchange.getRequest()
        .getHeaders().getFirst("X-Role");
if ("admin".equals(role)) {
    // Cho phép endpoint quản trị
}
~~~

Chỉ cần client gửi `X-Role: admin` là có thể đi vào nhánh đặc quyền. Ngay cả khi một route predicate có `Header=X-Role,^admin$`, đó vẫn chỉ là **điều kiện định tuyến**, không phải xác thực.

### 2.2. Một quyết định đúng về mặt nguyên tắc

~~~text
Authorization: Bearer <access token>
         ↓
Spring Security Resource Server
  - kiểm tra chữ ký hoặc introspection
  - issuer, expiry/not-before
  - audience, scope/role theo ứng dụng
         ↓
Authentication / SecurityContext
         ↓
Gateway chỉ chuyển thông tin được phép và đã xác minh
         ↓
Backend xác minh token hoặc kênh tin cậy và quyền tài nguyên
~~~

Nếu JWT có claim `tenant_id`, nó cũng chỉ có thể dùng sau khi **token hợp lệ**, claim đến từ issuer được tin và backend/ứng dụng vẫn kiểm tra principal thực sự được quyền truy cập tenant đó.

## 3. Sơ đồ ranh giới tin cậy

~~~mermaid
flowchart LR
    U["Internet client<br/>mọi header đều có thể giả"] --> E["Edge / Ingress<br/>HTTPS + Host allowlist<br/>xóa header nhạy cảm"]
    E -->|"Mạng riêng / TLS"| G["Spring Cloud Gateway<br/>Security authn/authz<br/>route + scrub"]
    G -->|"mTLS / private network"| B["Backend microservice<br/>verify token / trusted identity"]
    U -. "Không được truy cập trực tiếp" .-> G
    U -. "Không được truy cập trực tiếp" .-> B
~~~

Ba nhiệm vụ khác nhau:

1. **Edge** giới hạn đường vào, xác nhận proxy/CDN đứng trước (nếu có), chuẩn hóa Host/forwarded metadata và xóa header danh tính do client tạo.
2. **Gateway** xác thực request, chọn route, tiếp tục làm sạch/ghi đè header nhạy cảm và chỉ truyền thông tin cần thiết xuống backend.
3. **Backend** xác thực token hoặc tin một **kênh Gateway–backend đã được chứng thực**, rồi kiểm tra quyền truy cập tài nguyên. Nó không dựa vào một header có tên nghe đáng tin.

### 3.1. Đường đi nguy hiểm

~~~text
Client
  X-User-Id: admin
  X-Forwarded-For: 10.0.0.8
       ↓
Public Gateway (pass-through mọi header)
       ↓
Backend: "X-User-Id=admin, IP nội bộ → được phép"
       ↓
Giả danh / truy cập dữ liệu người khác
~~~

### 3.2. Đường đi mong muốn

~~~text
Client: X-User-Id=admin, Authorization: Bearer <token-client>
       ↓
Trusted ingress loại bỏ X-User-Id
       ↓
Gateway scrub lại, Spring Security xác thực token
       ↓
Không chuyển "admin" do client tự khai
       ↓
Gateway gửi access token đúng audience hoặc verified metadata
trên kênh riêng/mTLS theo hợp đồng với backend
       ↓
Backend xác thực và kiểm tra chủ sở hữu tài nguyên
~~~

Trong phương án mạnh nhất, backend **tự xác minh JWT/token** thích hợp của nó. Nếu cần dùng header nội bộ thay token, phải có **network ACL/mTLS service identity, không cho direct access, kiểm tra header chỉ đến từ Gateway**, và tốt hơn có cơ chế ký/timestamp để chống giả mạo/phát lại.

## 4. Trust boundary không được dựng bằng một cấu hình duy nhất

| Lớp | Mục tiêu | Cách bảo vệ |
| --- | --- | --- |
| Public DNS/Ingress | Chỉ public route được phép | Host allowlist, HTTPS/TLS, WAF/size limits, không expose management |
| Network Gateway | Không có đường bypass reverse proxy | Firewall, Kubernetes NetworkPolicy, private Service, service mesh policy |
| Forwarded-header normalization | Metadata IP/scheme/host có nguồn | Xóa inbound untrusted values, ghi mới tại trusted edge |
| HTTP Gateway header policy | Không truyền claim giả | `RemoveRequestHeader` hoặc `WebFilter` trước xử lý, sau đó mới set validated claim |
| Identity authentication | Biết ai gọi | Spring Security JWT/opaque token/mTLS, issuer/audience/scope |
| Authorization | Biết được làm gì | Method/path rules + backend resource ownership |
| Gateway→backend | Chỉ Gateway được gọi backend | mTLS workload identity, ACL, private endpoint, token audience |
| Observability | Phát hiện spoofing, policy bypass | Log quyết định đã redact, alert, negative tests |

**Đừng đặt mọi trọng trách vào một `Header=X-Trusted-IP` predicate.** HTTP header không tự cho biết ai thực sự đã gửi nó. Muốn xác minh nguồn phải bắt đầu từ **kết nối và proxy đã kiểm soát**.

### 4.1. Kịch bản có CDN hoặc nhiều proxy

~~~text
Client → CDN → WAF/Load Balancer → Ingress → Gateway → Backend
~~~

Đây là **nhiều hop**. Nếu CDN đã nhận một `X-Forwarded-For` do client tự khai nhưng không reset, chuỗi downstream có thể bắt đầu bằng địa chỉ giả. Nếu Ingress chỉ append, một service đọc “IP đầu tiên” sẽ coi địa chỉ giả là client. Điều cần kiểm soát:

- CDN và WAF có xác nhận nhau qua kết nối/IP/certificate hoặc private link không?
- Thành phần đầu tiên tiếp xúc untrusted client **xóa/ghi đè** header cũ hay chỉ append?
- Các proxy tiếp theo có xác nhận IP/certificate của hop trước không?
- Gateway có bị truy cập trực tiếp từ ngoài chuỗi này không?
- Backend có bị truy cập qua một Service/port khác mà bỏ qua Gateway không?

Chỉ sau khi trả lời được các câu hỏi trên mới nên cấu hình **bao nhiêu trusted hops** và đọc phần nào của forwarded chain.

## 5. Làm sạch header tại edge trước khi vào Gateway

Nơi an toàn nhất để chặn dữ liệu giả mạo là **proxy đầu tiên nhận request từ nguồn không tin cậy**. Edge cần biết đường mạng/cert nào được xem là trusted; sau đó xóa hoặc ghi đè những header chỉ được phép sinh bởi hạ tầng.

### 5.1. Mẫu NGINX minh họa cho một trusted ingress

~~~nginx
# PHÁC THẢO CHỈ CHO LAB/REVIEW. Cấu hình ACL, logging, DNS
# và server mặc định vẫn phải được hoàn thiện riêng.
upstream gateway_private {
    server 10.20.30.20:8080;
}

server {
    listen 443 ssl;
    server_name api.example.test;

    ssl_certificate /etc/nginx/tls/fullchain.pem;
    ssl_certificate_key /etc/nginx/tls/privkey.pem;

    location / {
        # Xóa header danh tính do public client tự đặt.
        proxy_set_header X-User-Id "";
        proxy_set_header X-Role "";
        proxy_set_header X-Tenant-Id "";
        proxy_set_header X-Authenticated-User "";
        proxy_set_header X-Verified-Subject "";
        proxy_set_header X-Verified-Tenant "";

        # Edge đơn hop: thay vì tin chuỗi XFF inbound,
        # ghi IP của peer mà NGINX trực tiếp nhận kết nối.
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Host $host;
        proxy_set_header Forwarded "";

        proxy_set_header Host $host;
        proxy_pass http://gateway_private;
    }
}
~~~

Trong NGINX, `proxy_set_header Header-Name ""` bỏ header tương ứng ở upstream request; tuy nhiên ví dụ này **chưa phải cấu hình production đầy đủ**. Cần server mặc định **từ chối Host ngoài allowlist**, TLS certificate/key, timeouts, size limits, access controls, cấu hình upstream riêng và chặn đường trực tiếp tới Gateway.

**Nếu NGINX đứng sau CDN:** `$remote_addr` là địa chỉ CDN/peer trực tiếp, **không mặc định là IP end-user**. Muốn lấy IP end-user phải xác thực rằng request thật sự đến từ CDN đáng tin (IP/CIDR/mTLS/private link), áp chính sách real-IP phù hợp, scrub chuỗi XFF ở ranh giới đúng và chỉ sau đó xây metadata cho Gateway. Không đơn giản đổi thành `$http_x_forwarded_for` từ request bất kỳ.

### 5.2. Vì sao append mà không xóa thường nguy hiểm?

Client gửi:

~~~http
X-Forwarded-For: 10.0.0.8
~~~

Proxy append `198.51.100.77` rồi Gateway nhận:

~~~http
X-Forwarded-For: 10.0.0.8, 198.51.100.77
~~~

Nếu ứng dụng chọn **địa chỉ bên trái nhất** mà không xác minh chuỗi trusted proxies, nó có thể coi `10.0.0.8` là IP nội bộ của client. Cơ chế `maxTrustedIndex` được thảo luận ở phần sau giúp giới hạn số hop đọc từ phía phải; **nhưng vẫn phải chặn kết nối trực tiếp vào Gateway**, không phải cấu hình IP resolver là đủ.

### 5.3. Ngăn bypass qua mạng

Một Gateway chỉ nên nhận request công khai thông qua đường đã kiểm soát. Các cấu hình mạng cần xem xét:

- **VM/bare metal:** firewall chỉ cho địa chỉ edge/load balancer đến listener Gateway; cổng admin riêng không public.
- **Kubernetes:** Gateway application Service có thể là `ClusterIP` nội bộ, nhưng **ClusterIP không tự chặn Pod khác**; bổ sung ingress NetworkPolicy, service mesh identity và RBAC phù hợp.
- **Cloud Load Balancer:** security group/firewall gắn listener Gateway chỉ cho L7 proxy được phê duyệt.
- **Backend:** ingress rules chỉ cho workload identity/service account của Gateway; API chưa xác thực không được gọi trực tiếp qua một Service/NodePort khác.
- **IPv4/IPv6:** kiểm tra cả hai family; một firewall chỉ khóa IPv4 có thể vẫn lộ listener IPv6.
- **NAT/sidecar/port-forward:** xác minh những đường phụ không vượt qua WAF/auth ở edge.

**Không lấy IP allowlist làm cơ chế xác thực danh tính người dùng.** IP có thể thay đổi, shared NAT và proxy có thể phục vụ nhiều principal; token/mTLS identity có mục đích khác.

## 6. Loại bỏ header giả mạo bằng Gateway filter configuration

Spring Cloud Gateway Server WebFlux có `RemoveRequestHeader` và `SetRequestHeader`. Hai bộ lọc này can thiệp request **trước khi gửi xuống downstream** khi một Gateway route đã match.

### 6.1. WebFlux Gateway 5.x — các route mặc định không chuyển identity headers

Ví dụ cấu hình khi **backend tự xác thực access token**, không yêu cầu Gateway thêm identity header mới:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          default-filters:
            - RemoveRequestHeader=X-User-Id
            - RemoveRequestHeader=X-Role
            - RemoveRequestHeader=X-Tenant-Id
            - RemoveRequestHeader=X-Authenticated-User
            - RemoveRequestHeader=X-Verified-Subject
            - RemoveRequestHeader=X-Verified-Tenant
          routes:
            - id: orders-api
              uri: http://127.0.0.1:9091
              predicates:
                - Path=/api/orders/**
~~~

Ở đây, `default-filters` áp dụng cho **Gateway Server routes**, không tự loại bỏ header ở những endpoint không dùng Gateway route (ví dụ controller hoặc Actuator handler riêng). Mỗi giá trị header trong danh sách được xóa trước khi Netty HTTP client chuyển request downstream.

**Quan trọng:** Cấu hình trên giả định backend có **cách xác thực riêng**. Nó không tạo `X-Verified-Subject` từ principal, cũng không tự xác minh JWT. Nếu backend đang dựa vào identity header cũ, cần migration protocol trước khi xóa header để tránh phá vỡ functionality; không giữ header client như một lối tắt.

### 6.2. WebFlux Gateway 4.2/4.3 — namespace cũ

Trên những dòng WebFlux Gateway 4.x sử dụng prefix ngắn:

~~~yaml
spring:
  cloud:
    gateway:
      default-filters:
        - RemoveRequestHeader=X-User-Id
        - RemoveRequestHeader=X-Role
        - RemoveRequestHeader=X-Tenant-Id
        - RemoveRequestHeader=X-Authenticated-User
        - RemoveRequestHeader=X-Verified-Subject
        - RemoveRequestHeader=X-Verified-Tenant
      routes:
        - id: orders-api
          uri: http://127.0.0.1:9091
          predicates:
            - Path=/api/orders/**
~~~

Đừng trộn `spring.cloud.gateway.default-filters` của 4.x với `spring.cloud.gateway.server.webflux.default-filters` của 5.x rồi cho rằng cả hai cùng có tác dụng. Dùng **Spring Cloud BOM tương thích Spring Boot** và xác nhận runtime route/filter definitions thực tế. Tên starter cũng thay đổi giữa các dòng Gateway.

### 6.3. Khi chỉ muốn xóa trên một route

~~~yaml
filters:
  - RemoveRequestHeader=X-User-Id
  - RemoveRequestHeader=X-Role
  - RemoveRequestHeader=X-Tenant-Id
~~~

Đặt trong route cụ thể nếu chính sách chỉ áp dụng downstream đó. Nhưng identity spoofing là vấn đề **toàn cổng**, nên trong production thường muốn một **deny-by-default** policy cho tất cả public routes, tránh route mới quên thêm filter.

### 6.4. `RemoveRequestHeader` khác `SetRequestHeader`

| Filter | Hành vi | Phù hợp |
| --- | --- | --- |
| `RemoveRequestHeader=X-User-Id` | Xóa tất cả giá trị header theo tên | Không cho bất kỳ giá trị client nào đi xuống backend |
| `SetRequestHeader=X-Route-Label,orders` | Ghi đè thay vì append mọi giá trị cùng tên | Header kỹ thuật nội bộ tĩnh, không phải user identity |
| `AddRequestHeader=X-Route-Label,orders` | Thêm giá trị | Chỉ dùng khi header được phép đa giá trị |

**Không đặt `SetRequestHeader=X-User-Id,admin` và coi đó là xác thực.** Một giá trị tĩnh không đại diện cho principal. Muốn truyền identity phải lấy từ context đã được xác minh, hoặc chuyển token thích hợp để backend kiểm tra.

### 6.5. Filter route không thay thế ingress scrub

`RemoveRequestHeader` chạy trong Gateway route chain. Nếu request được xử lý bởi một **controller local**, WebFilter khác hoặc custom handler không đi qua Gateway route, chính sách đó có thể không chạy. Hơn nữa, một WebFilter/Security component có thể đọc header **trước khi** route filter xóa nó.

**Bảo vệ nhiều lớp:** xóa ở trusted edge, xóa sớm ở WebFilter nếu cần bảo vệ mọi WebFlux handler, và có policy downstream header tại Gateway route. Chỉ ghép nhiều lớp khi đã kiểm tra thứ tự, tránh việc một filter phía sau vô tình xóa cả identity **được tạo lại từ principal hợp lệ**.

## 7. WebFilter sớm: xóa header trên mọi WebFlux handler

Khi Gateway Server WebFlux có thêm controller, endpoint tùy biến hoặc nhiều route nguồn khác nhau, có thể dùng một **WebFlux `WebFilter`** để loại bỏ header giả **trước routing và trước các filter yêu cầu đọc danh tính**.

Ví dụ Java:

~~~java
package demo.gateway.security;

import java.util.List;

import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;

import reactor.core.publisher.Mono;

@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
public final class UntrustedIdentityHeadersWebFilter
        implements WebFilter {

    private static final List<String> UNTRUSTED = List.of(
            "X-User-Id",
            "X-Role",
            "X-Tenant-Id",
            "X-Authenticated-User",
            "X-Verified-Subject",
            "X-Verified-Tenant");

    @Override
    public Mono<Void> filter(ServerWebExchange exchange,
                             WebFilterChain chain) {

        ServerHttpRequest sanitized =
                exchange.getRequest().mutate()
                        .headers(headers -> {
                            for (String name : UNTRUSTED) {
                                headers.remove(name);
                            }
                        })
                        .build();

        return chain.filter(exchange.mutate()
                .request(sanitized)
                .build());
    }
}
~~~

Giải thích:

1. `@Order(Ordered.HIGHEST_PRECEDENCE)` yêu cầu chạy sớm trong **WebFilter chain**; các component khác phải được review về thứ tự, đặc biệt khi tự tạo thêm WebFilters.
2. `ServerHttpRequest.mutate()` tạo request decorator với header đã thay đổi, không sửa trực tiếp object request gốc.
3. `HttpHeaders.remove(name)` xử lý tên header theo HTTP semantics không phân biệt hoa/thường; tuy nhiên vẫn phải kiểm thử các proxy có cách chuẩn hóa dấu gạch dưới/duplicate names.
4. Filter không đụng `Authorization` hoặc `Cookie`: Spring Security vẫn cần đọc credential phù hợp; loại bỏ credential từ public request mà không có mô hình xác thực thay thế có thể làm mọi API bị 401.
5. Filter cũng **không tự loại bỏ `Forwarded` hoặc `X-Forwarded-*`**: chúng có trust policy và network topology riêng, được xử lý ở phần sau.

**Đây là lớp scrub, không phải lớp tạo danh tính.** Nếu Spring Security chưa được cấu hình, backend vẫn không nên cho phép truy cập chỉ vì một header bị xóa. Nếu Gateway không phải Spring WebFlux (mà là **Server Web MVC**), đoạn Java này không dùng được nguyên trạng; cần `jakarta.servlet.Filter`/`OncePerRequestFilter` hoặc cơ chế MVC tương ứng.

### 7.1. Vì sao không xóa mọi header bắt đầu bằng `X-`?

Không có quy tắc rằng mọi custom header đều không đáng tin và phải bị xóa. Các header như `X-Correlation-Id` hoặc header do một proxy nội bộ phát hành có thể có hợp đồng riêng. Ngược lại, header không mang tiền tố `X-` như `Forwarded` hoặc `Authorization` lại **rất nhạy cảm**.

Hãy dùng **danh sách header có ý nghĩa quyền hạn**, quản lý qua versioned security policy. Nếu cần kiểm soát định dạng ID, chuẩn hóa/generate ở edge/Gateway và tránh log untrusted raw value.

## 8. Xác thực JWT và phân quyền bằng Spring Security WebFlux

Header đã được làm sạch nhưng **một client chưa xác thực vẫn phải bị chặn** ở các API có quyền truy cập. Spring Security Resource Server hỗ trợ JWT/opaque access token với WebFlux; với JWT cần kiểm tra chữ ký, `iss` (issuer), `exp`, `nbf` và chính sách `aud` (audience) của ứng dụng.

### 8.1. Dependencies và cấu hình issuer

Với Spring Boot/Spring Cloud BOM tương thích và Gateway WebFlux:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
</dependency>
~~~

Ví dụ cấu hình:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.test/realms/platform
~~~

Địa chỉ `idp.example.test` chỉ là **placeholder tài liệu**, không phải IdP thật. Trong môi trường chạy phải thay bằng issuer hợp lệ, có metadata/JWK tin cậy và TLS. Spring Security có thể xác thực JWT bằng cấu hình issuer tương ứng, nhưng **kiểm tra audience mong muốn cần được cấu hình riêng** khi ứng dụng có yêu cầu audience cụ thể; đừng mặc định signature hợp lệ là đủ.

### 8.2. SecurityWebFilterChain phân quyền trước routing

~~~java
package demo.gateway.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration(proxyBeanMethods = false)
public class GatewaySecurityConfiguration {

    @Bean
    SecurityWebFilterChain security(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers(HttpMethod.GET, "/api/orders/**")
                        .hasAuthority("SCOPE_orders.read")
                        .pathMatchers(HttpMethod.POST, "/api/orders/**")
                        .hasAuthority("SCOPE_orders.write")
                        .anyExchange().denyAll())
                .oauth2ResourceServer(oauth2 -> oauth2
                        .jwt(Customizer.withDefaults()))
                .build();
    }
}
~~~

Tất cả API không khai báo trong ví dụ đều bị từ chối, bao gồm Actuator nếu đi qua cùng Security chain. **Trong production**, quản trị Actuator bằng management context/port và authorization riêng; health readiness hoặc CORS preflight phải được thiết kế rõ thay vì mở `anyExchange().permitAll()`.

Với bearer-only API không sử dụng browser cookie, cần đánh giá cấu hình CSRF thích hợp. **Không tắt CSRF một cách máy móc** nếu hệ thống còn session/cookie authentication. POST có thể cần CSRF token với default Security policy, nên lab phía dưới tập trung vào GET.

### 8.3. Xác minh audience cùng issuer: ví dụ validator tường minh

Chữ ký của token hợp lệ nhưng token được cấp cho **một ứng dụng khác** không được phép tự động dùng cho Gateway. Ví dụ Spring Security WebFlux với `ReactiveJwtDecoder`:

~~~java
package demo.gateway.security;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;

@Configuration(proxyBeanMethods = false)
public class GatewayJwtDecoderConfiguration {

    @Bean
    ReactiveJwtDecoder jwtDecoder(
            @Value("${demo.security.jwk-set-uri}") String jwkSetUri,
            @Value("${demo.security.issuer}") String issuer,
            @Value("${demo.security.audience}") String audience) {

        NimbusReactiveJwtDecoder decoder =
                NimbusReactiveJwtDecoder
                        .withJwkSetUri(jwkSetUri)
                        .build();

        OAuth2TokenValidator<Jwt> standard =
                JwtValidators.createDefaultWithIssuer(issuer);

        OAuth2TokenValidator<Jwt> audienceCheck = jwt ->
                jwt.getAudience().contains(audience)
                        ? OAuth2TokenValidatorResult.success()
                        : OAuth2TokenValidatorResult.failure(
                                new OAuth2Error(
                                        "invalid_token",
                                        "Required audience missing",
                                        null));

        decoder.setJwtValidator(
                new DelegatingOAuth2TokenValidator<>(
                        standard, audienceCheck));
        return decoder;
    }
}
~~~

Và các properties tự định nghĩa phục vụ `@Value`:

~~~yaml
demo:
  security:
    issuer: https://idp.example.test/realms/platform
    audience: api-gateway
    jwk-set-uri: https://idp.example.test/realms/platform/protocol/openid-connect/certs
~~~

**Đừng sao chép JWK URL placeholder như endpoint production.** Đường lấy JWK phụ thuộc IdP. `JwtValidators.createDefaultWithIssuer` cung cấp những kiểm tra mặc định cùng issuer; `audienceCheck` chỉ nhận token có `aud` chứa audience dự kiến. Ngoài ra cần kiểm tra thuật toán/kích thước khóa, key rotation, scopes, token revocation, claim source, clock skew và các chính sách IdP phù hợp mức rủi ro.

Khi khai báo một `ReactiveJwtDecoder` bean tùy biến, bạn đang **thay/ghi đè decoder auto-configuration** liên quan. Phải kiểm thử invalid signature, wrong issuer, wrong audience, expired, not-before, missing scope. Không chạy đồng thời hai decoder beans không rõ loại token cần dùng rồi trông chờ Spring chọn theo trực giác.

### 8.4. Principal từ JWT vẫn chưa phải quyền truy cập tài nguyên

JWT có:

~~~json
{
  "sub": "user-123",
  "aud": ["api-gateway"],
  "scope": "orders.read",
  "tenant_id": "tenant-42"
}
~~~

Sau khi token được xác minh, Gateway có thể cho phép `GET /api/orders/**` theo `SCOPE_orders.read`. Nhưng backend vẫn phải kiểm tra **user-123 có quyền xem đơn hàng cụ thể không**, và `tenant_id` có phù hợp tài nguyên không. Một scope cấp quyền truy cập API **không đồng nghĩa có quyền đọc mọi order trong mọi tenant**.

## 9. Nếu cần truyền danh tính xuống backend: chọn hợp đồng an toàn

**Ưu tiên:** Backend xác thực một access token **đúng audience của backend** hoặc một token mới từ token exchange/client credentials/delegation theo policy. Chỉ dùng header nội bộ được Gateway sinh từ principal khi backend có kênh tin cậy và hợp đồng rất rõ.

| Phương án | Ưu điểm | Rủi ro/cần làm |
| --- | --- | --- |
| Backend tự verify token phù hợp audience | Không dựa vào header trần | Quản lý IdP/JWKS, audience, scopes, retries/revocation |
| Gateway token exchange cho backend | Tách audience/scope, hạn chế delegation | Token exchange policy, credentials, cache và TLS |
| Gateway phát header `X-Verified-Subject` sau xác thực | Dễ tích hợp backend cũ | **Chỉ an toàn với mTLS/ACL + không direct access + kiểm tra header spoof** |
| Gateway chuyển nguyên `X-User-Id` client | Không có ưu điểm bảo mật | **Không dùng** |

### 9.1. Không dùng `SetRequestHeader` với user ID cố định

~~~yaml
# Sai về nghĩa bảo mật: không tạo được danh tính principal.
filters:
  - SetRequestHeader=X-Verified-Subject,admin
~~~

Điều này chỉ đặt một chuỗi hằng. Một cách khác như `AddRequestHeader=X-Verified-Subject,{userId}` lấy từ URI template cũng sai: client có thể kiểm soát path variables. Danh tính phải đến từ **validated security context**, không từ path/query/header do caller tự chọn.

### 9.2. Ví dụ identity bridge chỉ cho một Gateway route

Một ứng dụng có thể dùng `GlobalFilter` lấy `JwtAuthenticationToken` từ Reactive SecurityContext và gắn header sau khi lọc bỏ header giả ở `UntrustedIdentityHeadersWebFilter` (mục 7). Ví dụ lab dưới đây chỉ áp cho route ID `orders-protected`:

~~~java
package demo.gateway.security;

import org.springframework.cloud.gateway.filter.GatewayFilterChain;
import org.springframework.cloud.gateway.filter.GlobalFilter;
import org.springframework.cloud.gateway.route.Route;
import org.springframework.core.Ordered;
import org.springframework.http.HttpStatus;
import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

import static org.springframework.cloud.gateway.support.ServerWebExchangeUtils.GATEWAY_ROUTE_ATTR;

@Component
public final class VerifiedIdentityBridgeFilter
        implements GlobalFilter, Ordered {

    @Override
    public int getOrder() {
        // Ví dụ lab: test thứ tự thật so với các route filters.
        return 10_000;
    }

    @Override
    public Mono<Void> filter(ServerWebExchange exchange,
                             GatewayFilterChain chain) {

        Route route = exchange.getAttribute(GATEWAY_ROUTE_ATTR);
        if (route == null ||
                !"orders-protected".equals(route.getId())) {
            return chain.filter(exchange);
        }

        return ReactiveSecurityContextHolder.getContext()
                .map(ctx -> ctx.getAuthentication())
                .ofType(JwtAuthenticationToken.class)
                .filter(auth -> auth.isAuthenticated())
                .flatMap(auth -> Mono.justOrEmpty(
                        auth.getToken().getSubject()))
                .filter(subject -> subject.matches(
                        "[A-Za-z0-9._:@-]{1,128}"))
                // Đặt fallback TRƯỚC flatMap trả Mono<Void>:
                // Mono<Void> hoàn tất không phát onNext là bình thường.
                .defaultIfEmpty("")
                .flatMap(subject -> {
                    if (subject.isEmpty()) {
                        return reject(exchange);
                    }

                    ServerHttpRequest sanitized =
                            exchange.getRequest().mutate()
                                    .headers(headers -> {
                                        headers.remove(
                                                "X-Verified-Subject");
                                        headers.set(
                                                "X-Verified-Subject",
                                                subject);
                                    }).build();

                    return chain.filter(exchange.mutate()
                            .request(sanitized).build());
                });
    }

    private Mono<Void> reject(ServerWebExchange exchange) {
        exchange.getResponse()
                .setStatusCode(HttpStatus.UNAUTHORIZED);
        return exchange.getResponse().setComplete();
    }
}
~~~

**Ý nghĩa bảo mật của ví dụ:**

1. Nó **không** lấy `X-User-Id` từ request.
2. Trước đó một `WebFilter` xóa các header danh tính do caller tự gửi.
3. Ở route `orders-protected`, một `GlobalFilter` chỉ nhận `JwtAuthenticationToken` sau khi Spring Security đã xác minh JWT.
4. Header `X-Verified-Subject` được xóa lại rồi **set duy nhất** từ claim `sub` hợp lệ.
5. Nếu không có principal hợp lệ hoặc claim không đúng định dạng, request bị từ chối.
6. Backend vẫn phải chỉ nhận request từ Gateway có service identity và xác minh authorization tài nguyên.

**Giới hạn:** Đây là bridge **minh họa**, không phải một protocol danh tính production hoàn chỉnh. Regex `sub` chỉ là ràng buộc định dạng an toàn cho HTTP header, không phải cơ chế xác thực. Header không được ký và có thể bị giả ở bất kỳ đường backend khác không bị khóa. Filter order `10_000` được chọn cho lab; **phải kiểm tra thứ tự thực giữa GlobalFilter và GatewayFilter/NettyRoutingFilter đúng version**. Không đặt một `RemoveRequestHeader=X-Verified-Subject` chạy **sau** bridge này, nếu không sẽ xóa luôn header đã xác minh. Đừng xây authorization của backend chỉ từ giá trị header trần khi có thể tự verify token.

### 9.3. Tránh “xóa rồi thêm lại từ dữ liệu client”

Một pattern sai:

~~~java
// PHẢN DIỆN: tên header thay đổi nhưng nguồn dữ liệu không thay đổi!
String user = exchange.getRequest().getHeaders()
        .getFirst("X-User-Id");
ServerHttpRequest request = exchange.getRequest().mutate()
        .headers(h -> {
            h.remove("X-User-Id");
            h.set("X-Verified-Subject", user);
        }).build();
~~~

Nguồn `user` vẫn là client input. Việc đổi tên header không nâng cấp độ tin cậy. Tương tự, không lấy `jwt.getClaimAsString("role")` để cấp quyền nếu issuer/claim chưa nằm trong chính sách tin cậy đã được xác minh.

### 9.4. Header nội bộ không được lộ ngược ra response

Khi backend/Gateway log hoặc trả dữ liệu, tránh phản chiếu `X-Verified-Subject` và `X-Verified-Tenant` cho client ngoài hợp đồng. Nếu backend vô tình echo mọi request headers vào JSON response, attacker có thể thu thập định danh nội bộ. Với debug, chỉ dùng marker giả trong môi trường thử nghiệm, rồi loại bỏ trước production.

## 10. Forwarded và X-Forwarded-*: metadata chỉ đáng tin khi proxy đáng tin

Nhóm header phổ biến:

~~~http
Forwarded: for=198.51.100.20;proto=https;host=api.example.test
X-Forwarded-For: 198.51.100.20, 10.20.30.5
X-Forwarded-Proto: https
X-Forwarded-Host: api.example.test
X-Forwarded-Port: 443
X-Forwarded-Prefix: /edge
~~~

`Forwarded` theo RFC 7239, còn `X-Forwarded-*` là conventions được dùng rộng rãi. Chúng có thể giúp backend tái tạo địa chỉ client, scheme, Host gốc và prefix khi Gateway đứng sau một reverse proxy. Nhưng chúng **chỉ là các byte trong HTTP request** cho tới khi xác minh được nguồn tạo.

### 10.1. Hai câu hỏi hoàn toàn khác nhau

1. **Ai có quyền đặt forwarding metadata?** Chỉ edge/proxy đã xác minh bằng đường mạng/cert, sau khi xóa dữ liệu client tự tạo.
2. **Gateway diễn giải metadata ra sao?** Dùng cấu hình `trusted-proxies`, Spring forwarding strategy hoặc RemoteAddressResolver theo phiên bản/đường request.

Cấu hình câu thứ hai **không thể thay thế** câu thứ nhất. Một cấu hình `trusted-proxies` regex tốt vẫn có thể bị bypass nếu client kết nối trực tiếp tới Gateway hoặc ingress không làm sạch header đầu vào.

### 10.2. WebFlux Gateway 5.x — trusted-proxies

Tài liệu Spring Cloud Gateway Server WebFlux 5.x mô tả `spring.cloud.gateway.server.webflux.trusted-proxies` là **Java regular expression** xác định những proxy đáng tin khi xuất hiện trong `Forwarded` hoặc `X-Forwarded` metadata. Đây **không phải CIDR notation**.

Ví dụ giới hạn vào hai địa chỉ proxy cố định trong một network lab:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          trusted-proxies: '^10[.]20[.]30[.](5|6)$'
          x-forwarded:
            for-enabled: true
            host-enabled: true
            proto-enabled: true
            for-append: false
            host-append: false
            proto-append: false
~~~

Giải thích:

- Pattern `^10[.]20[.]30[.](5|6)$` là một **allowlist minh họa** cho `10.20.30.5` và `10.20.30.6`, không phải cấu hình phù hợp mọi môi trường.
- Cấu hình `trusted-proxies` liên quan cơ chế **Forwarded/XForwarded HttpHeadersFilters** của Gateway WebFlux khi chuẩn bị downstream headers.
- `for-append: false`, `host-append: false` và `proto-append: false` yêu cầu cơ chế Gateway **không append** các giá trị hiện có theo tính năng tương ứng, nhưng **không tự xóa mọi header giả trước route matching hoặc trước Spring Security**.
- Nếu muốn bảo toàn toàn bộ proxy chain cho audit, phải có chain trust được kiểm chứng; không bật append chỉ vì muốn nhiều địa chỉ hơn.
- Với Host/Proto, ingress cần kiểm tra hostname và scheme thật; không cho browser tự khai giá trị bên ngoài rồi backend sử dụng làm redirect.

**Cảnh báo:** Không đưa nguyên pattern `.*` hoặc `^.*$` vào `trusted-proxies` chỉ để “làm header hoạt động”. Đó là trust-all theo ý nghĩa matching; pattern phải nằm trong allowlist vận hành được review, và mạng vẫn chặn nguồn không được phê duyệt. Hãy xác minh exact format địa chỉ mà bản Gateway đưa vào regex (IPv4/IPv6, port/quotes) bằng integration tests.

### 10.3. WebFlux Gateway 4.x và Server Web MVC

Một số dòng Gateway 4.x dùng property:

~~~yaml
spring:
  cloud:
    gateway:
      trusted-proxies: '^10[.]20[.]30[.](5|6)$'
      x-forwarded:
        for-append: false
~~~

Đây là **cú pháp prefix cũ**; kiểm tra configuration metadata của bản 4.x cụ thể trước khi áp dụng. Dòng Gateway Server Web MVC mới có namespace tương ứng:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webmvc:
          trusted-proxies: '^10[.]20[.]30[.](5|6)$'
~~~

**Web MVC và WebFlux không dùng chung API filter code**: Web MVC chạy Servlet/WebMvc.fn, còn các ví dụ Java `WebFilter`, `ServerWebExchange` và `GlobalFilter` ở bài này dành cho WebFlux. Các nguyên lý proxy trust vẫn giống nhau, nhưng property và filter lifecycle phải đối chiếu theo stack.

### 10.4. Không nhầm Gateway HttpHeadersFilters với Spring forwarding strategy

Spring Boot có `server.forward-headers-strategy` (thường là `NONE`, `NATIVE`, `FRAMEWORK` tùy môi trường/version). Nó điều khiển cách web server hoặc Spring Framework xử lý forwarded headers ở **phía inbound request**, ảnh hưởng scheme/host/port mà handler nhìn thấy.

Trong khi đó, `Forwarded`/`XForwarded` **HttpHeadersFilters** của Gateway hoạt động khi tạo **request downstream**. Hai cơ chế khác tầng; cấu hình một cái không mặc nhiên khóa cái còn lại.

Nếu bật `server.forward-headers-strategy: framework` hoặc proxy support ở Reactor Netty:

1. Xác nhận edge đã làm sạch forwarded headers.
2. Ngăn client truy cập thẳng vào listener Gateway.
3. Xác minh URI/scheme/Host sau transform trước khi route predicates, OAuth2 redirect và absolute URL generation.
4. Kiểm tra việc strip/append outbound headers có nhất quán với trust boundary.

Không bật inbound forwarding transformer trên Internet listener mà tin mọi forwarded input do client gửi. Với deployment không có trusted reverse proxy, cách an toàn thường là không sử dụng forwarded metadata cho quyết định bảo mật.

## 11. X-Forwarded-For và hai cơ chế IP resolver dễ bị nhầm

### 11.1. `RemoteAddr` thông thường

Route predicate:

~~~yaml
predicates:
  - RemoteAddr=10.20.30.0/24
~~~

theo mặc định xét **remote socket peer address** từ request mà Gateway nhận. Sau một ingress, địa chỉ đó thường là **IP của ingress**, không nhất thiết là người dùng Internet.

Nếu mạng chỉ cho ingress đáng tin đến Gateway, kiểm tra remote socket peer có thể giúp giới hạn kết nối từ proxy. Nhưng nó **không tự chứng minh identity của người dùng cuối**.

### 11.2. `XForwardedRemoteAddressResolver.trustAll()` là rủi ro spoofing

Gateway WebFlux có resolver dựa vào XFF:

~~~java
XForwardedRemoteAddressResolver.trustAll()
~~~

Theo tài liệu Gateway, cách này lấy địa chỉ đầu tiên trong `X-Forwarded-For`, có thể bị client tự đặt. Với request:

~~~http
X-Forwarded-For: 10.0.0.8, 198.51.100.20
~~~

một caller có thể tự khai `10.0.0.8` rồi khiến resolver tin nó là IP client. **Không dùng `trustAll()` cho IP allowlist/quyết định bảo mật trên traffic không đáng tin.**

### 11.3. `maxTrustedIndex(n)` đọc chain từ phía phải

Ví dụ chuỗi XFF:

~~~http
X-Forwarded-For: 192.0.2.10, 198.51.100.20, 10.20.30.5
~~~

Tài liệu Gateway mô tả:

| `maxTrustedIndex` | Địa chỉ được chọn từ ví dụ | Ý nghĩa |
| ---: | --- | --- |
| `1` | `10.20.30.5` | Phần tử cuối cùng, sát Gateway nhất trong XFF |
| `2` | `198.51.100.20` | Lùi hai vị trí từ phải |
| `3` | `192.0.2.10` | Phần tử bên trái nhất của chuỗi này |
| `>3` | `192.0.2.10` theo mô tả hiện tại | Quá số phần tử không tạo thêm xác minh |

`maxTrustedIndex(0)` không hợp lệ. Quan trọng hơn: **một số n phù hợp topology không phải tùy chọn “chọn IP mình muốn thấy”**. Giá trị n phải tương ứng số proxy hops thật sự **đã được kiểm soát**, sau khi edge xóa header inbound client.

Khi chuỗi có các IP client tự giả bên trái, chọn n quá lớn vẫn có thể chọn một IP giả. Nếu Gateway truy cập trực tiếp không qua đúng số hops, mọi giả định cũng có thể sai.

### 11.4. Ví dụ Java RouteLocator với resolver giới hạn

~~~java
package demo.gateway.routing;

import org.springframework.cloud.gateway.route.RouteLocator;
import org.springframework.cloud.gateway.route.builder.RouteLocatorBuilder;
import org.springframework.cloud.gateway.support.ipresolver.XForwardedRemoteAddressResolver;
import org.springframework.cloud.gateway.support.ipresolver.RemoteAddressResolver;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class ExampleRemoteAddrRoutes {

    @Bean
    RouteLocator exampleRoutes(RouteLocatorBuilder builder) {
        RemoteAddressResolver resolver =
                XForwardedRemoteAddressResolver.maxTrustedIndex(1);

        return builder.routes()
                .route("ip-observation-lab",
                        r -> r.remoteAddr(resolver, "198.51.100.0/24")
                                .uri("http://127.0.0.1:9091"))
                .build();
    }
}
~~~

**Đây là lab về IP matching, không phải endpoint quản trị được bảo vệ đầy đủ.** Code trên không có Path predicate nên rất rộng; nếu thử cùng các routes khác, cần gắn Path/method rõ ràng và xác nhận thứ tự. Không đưa snippet vào production nguyên trạng và không dựa vào IP để thay Spring Security. Ví dụ sẽ match địa chỉ `198.51.100.0/24` trong XFF **khi mạng/proxy đã bảo đảm XFF có nguồn**.

### 11.5. `XForwardedRemoteAddr` predicate không tự chứng minh trust

Một số phiên bản Gateway Server WebFlux còn có `XForwardedRemoteAddr` route predicate sử dụng dữ liệu từ `X-Forwarded-For`. Nếu nguồn header chưa đáng tin, việc match CIDR vẫn có thể dựa trên IP giả. Hãy kiểm tra behavior/version và bảo đảm chỉ proxy xác minh mới có quyền thiết lập metadata; khi mục đích là authorization, ưu tiên principal/token verified thay cho IP/header.

### 11.6. IP thật của client không phải luôn xác định được

Do NAT, CDN, VPN, mạng di động, HTTP proxies và IPv6:

- Một IP có thể đại diện hàng nghìn người dùng.
- Một người dùng có thể đổi IP giữa các requests.
- Một số network không cung cấp địa chỉ end-user mà chỉ cung cấp địa chỉ upstream proxy.
- Rate limiter dùng IP làm key có thể gây false positives/negatives nếu chuỗi trust bị hiểu sai.

Vì vậy dùng IP cho **quan sát/quota phụ trợ** và giới hạn mạng, không coi đó là principal thay thế. Với quota theo tài khoản/tenant, cần dùng identity đã xác thực.

## 12. Host, Proto, HTTP headers và TLS cũng nằm trong trust boundary

### 12.1. `X-Forwarded-Host` có thể tạo open redirect

Giả sử ứng dụng tạo URL xác nhận email:

~~~java
// PHẢN DIỆN: không dùng một Host chưa xác minh
// để sinh đường dẫn tới account/reset-password.
String host = request.getHeaders()
        .getFirst("X-Forwarded-Host");
String resetUrl = "https://" + host + "/reset?token=...";
~~~

Nếu client có thể đặt `X-Forwarded-Host: attacker.example.test`, ứng dụng có thể gửi reset link tới domain của kẻ tấn công (**host-header injection**). Với link nhạy cảm, nên dùng **public base URL cố định trong cấu hình được phê duyệt**; nếu cần dynamic host, phải kiểm tra allowlist sau khi edge canonicalize.

### 12.2. `X-Forwarded-Proto` không chứng minh TLS

Request đến Gateway qua HTTP không trở thành HTTPS chỉ vì client đặt:

~~~http
X-Forwarded-Proto: https
~~~

Muốn khẳng định đường public được bảo vệ phải có **TLS termination tại trusted edge**, HSTS được cấu hình phù hợp và network access controls. Nếu SSL/TLS offload tại edge rồi dùng HTTP đến Gateway, đoạn nội bộ vẫn cần network segregation/mTLS theo threat model.

### 12.3. `PreserveHostHeader` không chứng minh Host hợp lệ

Gateway Server có filter `PreserveHostHeader`, có thể chuyển Host nhận từ client tới backend. Nó phục vụ yêu cầu virtual host, **không phải cơ chế xác nhận** Host đã thuộc domain được phép.

Khi backend dựa Host để chọn tenant hoặc tạo callback URL:

- Kiểm soát Host ở public ingress/server_name/TLS.
- Dùng route predicate Host có ý nghĩa **routing**, không thay authentication.
- Chặn đường bypass ingress.
- Nếu cần dùng host gốc, lấy từ một nguồn canonical sau trusted proxy validation.
- Kiểm tra duplicate Host, HTTP/2 `:authority`, case, port và tên miền lạ theo HTTP server behavior.

### 12.4. Hop-by-hop headers và HTTP request smuggling

Các header như `Connection`, `Transfer-Encoding`, `Keep-Alive` không nên được proxy một cách mù quáng. Gateway WebFlux có **RemoveHopByHop HttpHeadersFilter**, tài liệu liệt kê các tên mặc định được loại bỏ ở downstream request.

Không chỉnh allowlist hop-by-hop để “giữ nguyên mọi header” khi chưa có lý do chuẩn HTTP và kiểm thử. Những bất đồng về `Content-Length`/`Transfer-Encoding` giữa edge, Gateway và backend có thể tạo request desynchronization/smuggling; cần cập nhật các bản vá Netty/HTTP server và cấu hình thống nhất. Đây là vấn đề **khác** với JWT identity, nhưng cùng thuộc ranh giới reverse proxy an toàn.

### 12.5. Backend phải xác minh Gateway, không chỉ header

Nếu backend dựa vào `X-Verified-Subject` thì yêu cầu tối thiểu:

1. Không có Internet/NodePort/LoadBalancer route trực tiếp tới backend.
2. Chỉ Gateway workload identity được kết nối (mTLS hoặc kiểm soát network và service identity phù hợp).
3. Header `X-Verified-Subject` chỉ được sinh từ auth context đã xác minh, không từ request client.
4. Backend kiểm tra request thật sự qua kênh được cấp quyền; không tự tin mọi inbound packet có header.
5. Backend vẫn enforce resource-level authorization và tenant ownership.

**Kênh mTLS xác minh workload Gateway, không tự xác minh end-user.** Backend vẫn cần một mô hình delegation/token/verified claims riêng cho danh tính người dùng cuối.

## 13. Lab WebFlux: xác minh header bị xóa và identity chỉ xuất hiện sau JWT

Mục tiêu lab có hai tiến trình:

| Thành phần | Port lab | Vai trò |
| --- | ---: | --- |
| Gateway Server WebFlux | `8080` | Bảo vệ GET route, scrub request identity và có thể phát verified subject |
| Backend echo | `9091` | Quan sát headers downstream trong môi trường thử nghiệm |

Sử dụng project Gateway với dependencies Spring Cloud Gateway **Server WebFlux**, Spring Security Resource Server và BOM tương thích; với Gateway 5.x dùng config namespace `spring.cloud.gateway.server.webflux.*`.

### 13.1. Route chỉ nhận đường đơn hàng

~~~yaml
# Gateway 5.x - application.yml (chỉ minh họa route)
server:
  port: 8080

spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: orders-protected
              uri: http://127.0.0.1:9091
              predicates:
                - Path=/api/orders/**
                - Method=GET
              filters:
                - AddResponseHeader=X-Lab-Route,orders-protected
~~~

Đoạn YAML này dùng cùng route ID mà `VerifiedIdentityBridgeFilter` ở mục 9 kiểm tra. **Nếu bật bridge này**, không đặt một `RemoveRequestHeader=X-Verified-Subject` ở vị trí sau bridge; sử dụng `UntrustedIdentityHeadersWebFilter` chạy sớm để loại bỏ header client rồi bridge set lại từ principal.

Nếu chỉ muốn **scrub, không phát verified identity**, bỏ bridge và dùng `default-filters` mục 6. Hai mô hình phải được kiểm thử riêng; không tự kết hợp các đoạn config thành một pipeline không rõ order.

### 13.2. Backend echo độc lập

Tạo một Spring Boot WebFlux application ở `9091` (ví dụ Spring Boot 3.x với `spring-boot-starter-webflux`):

~~~java
package demo.orders;

import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class OrdersBackendApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrdersBackendApplication.class, args);
    }
}

@RestController
class OrdersEchoController {

    @GetMapping("/api/orders/{id}")
    Map<String, Object> echo(
            @PathVariable String id,
            ServerHttpRequest request) {

        Map<String, Object> body = new LinkedHashMap<>();
        body.put("backend", "orders-echo");
        body.put("orderId", id);
        body.put("userIdFromClient",
                request.getHeaders().getFirst("X-User-Id"));
        body.put("roleFromClient",
                request.getHeaders().getFirst("X-Role"));
        body.put("tenantFromClient",
                request.getHeaders().getFirst("X-Tenant-Id"));
        body.put("verifiedSubject",
                request.getHeaders().getFirst(
                        "X-Verified-Subject"));
        body.put("forwardedFor",
                request.getHeaders().getFirst(
                        "X-Forwarded-For"));
        body.put("authorizationPresent",
                request.getHeaders().containsKey(
                        "Authorization"));
        return body;
    }
}
~~~

~~~yaml
# Backend application.yml
server:
  port: 9091
~~~

**Cảnh báo lab:** Controller echo trả thông tin request headers trong body để **quan sát ở máy thử nghiệm**, không phải mẫu production. Không public endpoint echo, không echo token/cookie, không dùng `verifiedSubject` trả về làm cơ chế authorization. Nếu đặt backend trên Internet, người ngoài có thể gọi trực tiếp với header giả và câu chuyện bảo mật bị phá vỡ.

### 13.3. Chạy backend và Gateway

~~~bash
# Terminal riêng trong project backend
./mvnw spring-boot:run

# Terminal riêng trong project Gateway
./mvnw spring-boot:run
~~~

Windows dùng `mvnw.cmd` nếu cần. Nếu dùng Gateway 5.x cùng Spring Boot 4.x, kiểm tra package/dependency/test starter của Boot 4 theo BOM; ví dụ code WebFlux bên trên mô tả contract tổng quát. **Bài không khẳng định đã build hoặc chạy lab trên repository**.

### 13.4. Thử giả mạo không có token hợp lệ

~~~bash
curl -i "http://127.0.0.1:8080/api/orders/42" \
  -H "X-User-Id: admin" \
  -H "X-Role: admin" \
  -H "X-Verified-Subject: admin" \
  -H "X-Tenant-Id: privileged"
~~~

Với `SecurityWebFilterChain` có rule GET `/api/orders/**` yêu cầu `SCOPE_orders.read`, request này phải **bị từ chối trước khi proxy** (thường 401 vì chưa xác thực). Backend không được thấy request mới.

Nếu vẫn thấy backend trả 200, cần kiểm tra Security config có đang chạy, route/hành vi handler khác, test profile, auto-configuration và cách route filter được lắp.

### 13.5. Thử JWT hợp lệ và header giả mạo

Cần một token **được cấp bởi IdP test**, có issuer/audience đúng, scope `orders.read` và `sub` được định dạng hợp lệ. Không tự bịa một token literal và gọi nó hợp lệ.

~~~bash
# ACCESS_TOKEN được nạp vào environment theo quy trình lab an toàn.
# Không in token ra logs/tickets.
curl -i "http://127.0.0.1:8080/api/orders/42" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "X-User-Id: admin" \
  -H "X-Role: admin" \
  -H "X-Tenant-Id: privileged" \
  -H "X-Verified-Subject: attacker"
~~~

Khi JWT đã được xác minh và route `orders-protected` được chọn, body backend echo dự kiến có cấu trúc:

~~~json
{
  "backend": "orders-echo",
  "orderId": "42",
  "userIdFromClient": null,
  "roleFromClient": null,
  "tenantFromClient": null,
  "verifiedSubject": "user-123",
  "authorizationPresent": true
}
~~~

`user-123` chỉ là **giá trị ví dụ** tương ứng `sub` trong test JWT. Giá trị `verifiedSubject` phải đến từ token đã xác minh, **không bao giờ từ chuỗi `attacker`**. Trường `authorizationPresent` có thể khác theo chính sách chuyển token của Gateway; nếu backend không được phép nhận client token, phải triển khai **token exchange hoặc xóa/đổi bearer token** có chủ đích và cập nhật assertion.

Các header forwarding (như `forwardedFor`) có thể được HTTP client/Gateway giữ hay tạo thêm tùy cấu hình. **Không đánh dấu chúng là trusted chỉ vì xuất hiện trong echo**; kiểm thử trust boundary ở mục 14.

### 13.6. So sánh đường trực tiếp tới backend

Trong lab có thể gọi trực tiếp:

~~~bash
curl -i "http://127.0.0.1:9091/api/orders/42" \
  -H "X-Verified-Subject: attacker"
~~~

Backend echo sẽ thấy chuỗi `attacker` vì **request đã bypass Gateway**. Đây là bằng chứng vì sao backend **không được dựa duy nhất vào header trần**. Trong production, đường trực tiếp phải bị firewall/NetworkPolicy/mTLS chặn, hoặc backend phải tự xác minh bearer token/token nội bộ.

Nếu xây service-to-service identity bằng mTLS, backend chỉ nên tin sender có workload certificate hợp lệ của Gateway. Không cho mọi Pod trong cluster truy cập backend chỉ vì Service type là `ClusterIP`.

### 13.7. Đừng kết luận từ status HTTP đơn lẻ

Một request có thể trả:

| Status | Lý do có thể |
| --- | --- |
| 200 | JWT hợp lệ, policy cho phép, backend trả thành công; hoặc route khác không an toàn nhận request |
| 401 | Chưa xác thực, token sai chữ ký/issuer/audience/expiry hoặc bridge thiếu principal |
| 403 | JWT hợp lệ nhưng thiếu scope/role hoặc backend từ chối |
| 404/405 | Route predicate method/path không match, hoặc handler khác |
| 429 | Rate limiter ngăn client |
| 502/503 | Backend/transport/LB/mTLS thất bại |

Với kiểm thử header spoofing, cần đồng thời xác minh **status + route ID + backend request count + giá trị header downstream**. Đó mới là bằng chứng request không vượt qua ranh giới.

## 14. Kiểm thử chống giả mạo phải bao gồm cả “không được phép”

### 14.1. Ma trận chấp nhận bảo mật

| ID | Tình huống | Kỳ vọng |
| --- | --- | --- |
| S01 | Không có Authorization, gửi `X-User-Id: admin` | Gateway không cấp quyền; backend không nhận request |
| S02 | Token chữ ký sai, header identity hợp lệ giả | 401, không forward |
| S03 | Token đúng chữ ký nhưng issuer sai | Bị từ chối, không forward |
| S04 | Token đúng issuer nhưng `aud` sai | Bị từ chối nếu audience validator đã bật |
| S05 | Token chưa hết hạn nhưng thiếu `orders.read` | 403 theo policy, không forward |
| S06 | Token hợp lệ đúng scope, không có header identity | Route đúng, backend nhận principal/token phù hợp |
| S07 | Token của `user-123` nhưng `X-User-Id: admin` | Backend không thấy giá trị `admin` |
| S08 | Token của `user-123` nhưng `X-Verified-Subject: attacker` | Backend chỉ thấy `user-123` nếu bật identity bridge |
| S09 | `X-Verified-Subject` gửi lặp nhiều values | Không được giữ một giá trị client nào ở downstream |
| S10 | Đổi tên header thành `x-user-id`/`X-USER-ID` | Cũng bị xóa theo HTTP semantics |
| S11 | Header biến thể underscore/mixed normalization | Edge/Gateway kiểm soát policy; không tạo alias bypass |
| S12 | Client tự gửi `X-Forwarded-For: 10.0.0.8` | IP giả không được dùng làm client identity đáng tin |
| S13 | Client trực tiếp vào Gateway thay vì Ingress | Network boundary từ chối đường bypass trong production |
| S14 | Ingress đáng tin gửi forwarding metadata đã reset | Gateway xử lý đúng client peer/trusted chain |
| S15 | `maxTrustedIndex` lớn hơn số hops | Test bắt cấu hình sai/chọn IP không đáng tin |
| S16 | Backend được gọi trực tiếp với `X-Verified-Subject: admin` | Production phải chặn ở network/mTLS hoặc backend không tin header |
| S17 | Host ngoài allowlist hoặc `X-Forwarded-Host` giả | Không sinh redirect/domain đặc quyền từ giá trị giả |
| S18 | TLS public hợp lệ nhưng kết nối Gateway→backend không được chứng thực | Test policy ngăn đường không có mTLS/ACL khi bắt buộc |
| S19 | Route mới không có identity header filters | Policy global/edge vẫn làm sạch; regression test fail nếu bỏ sót |
| S20 | Actuator/public debug echo endpoint lộ header | Không công khai diagnostics/PII, quản trị riêng |
| S21 | Cùng một request có `Authorization` hợp lệ và header tenant giả | Tenant được suy từ IdP/authorization, không từ header |
| S22 | Route fallback match request đã bị route chính loại | Không bypass scope/auth hoặc downstream header policy |
| S23 | JWT hết hạn/chưa có hiệu lực/khóa đã thu hồi | Decoder/IdP validation từ chối theo policy |
| S24 | Không có trusted proxy nhưng HTTP request có `Forwarded` | Không coi host/proto/for client tự khai là thông tin đã xác minh |

Ma trận gồm **positive, negative và topology tests**. Nhiều case cần kết quả từ network policy hoặc TLS/mTLS integration test chứ không thể chứng minh bằng unit test HTTP headers.

### 14.2. Unit test cho `UntrustedIdentityHeadersWebFilter`

Ví dụ JUnit 5 + Spring Test:

~~~java
package demo.gateway.security;

import java.time.Duration;
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.web.server.MockServerWebExchange;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilterChain;

import reactor.core.publisher.Mono;

import static org.assertj.core.api.Assertions.assertThat;

class UntrustedIdentityHeadersWebFilterTest {

    @Test
    void stripsSpoofedIdentityButKeepsBearerForSecurity() {
        var exchange = MockServerWebExchange.from(
                MockServerHttpRequest
                        .get("/api/orders/42")
                        .header("X-User-Id", "admin")
                        .header("x-role", "admin")
                        .header("X-Tenant-Id", "privileged")
                        .header("X-Verified-Subject", "attacker")
                        .header("Authorization",
                                "Bearer LAB_FAKE_TOKEN"));

        AtomicReference<ServerWebExchange> seen =
                new AtomicReference<>();
        WebFilterChain chain = next -> {
            seen.set(next);
            return Mono.empty();
        };

        new UntrustedIdentityHeadersWebFilter()
                .filter(exchange, chain)
                .block(Duration.ofSeconds(2));

        assertThat(seen.get()).isNotNull();
        var headers = seen.get().getRequest().getHeaders();

        assertThat(headers.containsKey("X-User-Id"))
                .isFalse();
        assertThat(headers.containsKey("X-Role"))
                .isFalse();
        assertThat(headers.containsKey("X-Tenant-Id"))
                .isFalse();
        assertThat(headers.containsKey("X-Verified-Subject"))
                .isFalse();
        assertThat(headers.getFirst("Authorization"))
                .isEqualTo("Bearer LAB_FAKE_TOKEN");
    }
}
~~~

Lệnh `block(...)` ở đây **chỉ nằm trong unit test JUnit**, không phải trong WebFlux request pipeline production. Test dùng chuỗi bearer giả để chắc chắn tầng scrub **không xóa credential trước Spring Security**; nó **không xác minh chữ ký JWT**.

Unit test trên kiểm tra header sanitizer **trực tiếp**. Nó chưa kiểm tra security, filter order, Gateway route selection hoặc Netty outbound headers. Cần integration tests qua HTTP Server thật.

### 14.3. Integration test với Gateway và backend stub

Với `@SpringBootTest(webEnvironment=RANDOM_PORT)`, `WebTestClient` và MockWebServer/WireMock, hãy cấu hình backend `uri` đến cổng ngẫu nhiên thay vì cổng 9091 cố định:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: orders-protected
              uri: http://127.0.0.1:${test.backend.port}
              predicates:
                - Path=/api/orders/**
                - Method=GET
~~~

Trong test setup, dùng `@DynamicPropertySource` đưa `test.backend.port` từ stub và tạo **JWT test được ký bằng khóa thử nghiệm** (hoặc mock SecurityContext ở *mock-web* tests chuyên biệt). Đừng thử nhét một `SecurityMockServerConfigurers.mockJwt()` vào HTTP client đi đến server thật rồi giả định server nhận được mock authentication: client-side mock JWT helper hoạt động theo **test context**, không tự tạo bearer token ký số thật cho remote HTTP listener.

Các assertions cốt lõi:

~~~text
Client request token hợp lệ, X-User-Id=admin
    ↓
Gateway Security xác thực JWT
    ↓
Gateway WebFilter bỏ X-User-Id
    ↓
Gateway filter tạo X-Verified-Subject=user-123 (nếu bật bridge)
    ↓
MockWebServer recorded request:
    X-User-Id: KHÔNG CÓ
    X-Verified-Subject: user-123
    Authorization: theo token forwarding policy được test
~~~

Đối với token giả/thiếu scope, MockWebServer **không được nhận request mới**. Dùng count và `RecordedRequest` để phát hiện request vô tình đi qua route fallback hoặc một bean khác.

### 14.4. Thử duplicate/case/alias

~~~bash
# Chỉ trên môi trường thử nghiệm có token hợp lệ.
curl -i "http://127.0.0.1:8080/api/orders/42" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "X-User-Id: admin" \
  -H "x-user-id: another-user" \
  -H "X-Verified-Subject: attacker" \
  -H "X-Verified-Subject: second-attacker"
~~~

Client/proxy có thể gộp duplicate headers hoặc từ chối trước khi Gateway nhận. Vì vậy test phải ghi nhận **dữ liệu thực tế downstream** và HTTP server behavior, không giả định tất cả headers sẽ tới ứng dụng nguyên vẹn. Với header identity không cho phép nhiều giá trị, policy nên **xóa sạch inbound và tạo đúng một giá trị từ principal**.

Các biến thể `X_User_Id` và `X-User-Id` đôi khi bị intermediary chuyển đổi/normalize. Không coi chúng là cùng tên theo chuẩn HTTP một cách tự động; cần chính sách **reject/strip dạng không chuẩn** ở edge và kiểm thử trên đúng proxy đang triển khai.

### 14.5. Kiểm thử topology chứ không chỉ HTTP payload

Hai kiểm tra riêng:

- Từ **Internet/public subnet**, thử kết nối trực tiếp Gateway application port/backend port: phải bị firewall/NetworkPolicy từ chối, không chỉ HTTP 401/403.
- Từ **trusted edge subnet**, request đi đúng ingress và TLS; Gateway thấy remote socket address và sanitized Forwarded/XFF như cấu hình.

Một response 401 ở Gateway **không chứng minh** đường bypass đã bị khóa: attacker vẫn có thể dò endpoint khác, lỗi parser hoặc cấu hình Security matcher thiếu. Network isolation là một lớp phòng vệ độc lập.

## 15. Khóa backend bằng Kubernetes NetworkPolicy và service identity

Giả sử Gateway chạy trong namespace `platform-edge`, backend chạy trong `platform-apps`. Một NetworkPolicy ingress mẫu chỉ cho các Pod Gateway được chọn đi vào port 9091 của backend:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: orders-backend-from-gateway
  namespace: platform-apps
spec:
  podSelector:
    matchLabels:
      app: orders-backend
  policyTypes:
    - Ingress
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: platform-edge
          podSelector:
            matchLabels:
              app: api-gateway
      ports:
        - protocol: TCP
          port: 9091
~~~

Giải thích:

- `podSelector` ngoài cùng chọn **backend Pods được bảo vệ**.
- `from.namespaceSelector` và `from.podSelector` trong cùng item giới hạn **Gateway Pods trong namespace cho phép**.
- `Ingress` policy ngăn Pod khác truy cập port đã chọn, **khi CNI thực sự enforce NetworkPolicy**.
- NetworkPolicy là L3/L4 isolation, **không xác thực end-user**; labels có thể bị cấp sai nếu RBAC/deployment permissions lỏng.
- Nếu Gateway còn gọi backend qua port khác hoặc service mesh sidecar, phải kiểm tra toàn bộ đường thật.

**Không sao chép policy nguyên trạng:** namespace/labels/port chỉ là ví dụ. Test cả đường được phép và đường bị chặn sau triển khai. NetworkPolicy không bảo vệ listener nếu một NodePort/LoadBalancer hoặc hostNetwork bypass chính sách theo CNI/hạ tầng.

### 15.1. Thêm mTLS giữa Gateway và backend

NetworkPolicy giúp thu hẹp nguồn, nhưng một Pod bị compromise hoặc label/ServiceAccount bị cấp sai có thể cần được xử lý bằng **workload identity**. mTLS ở service mesh hoặc trực tiếp qua client/server certificates có thể:

- Xác minh Gateway workload bằng client certificate.
- Xác minh backend đích và chống man-in-the-middle.
- Mã hóa dữ liệu giữa hai service.
- Ràng buộc quyền gọi theo service identity, namespace hoặc policy.

Tuy vậy, **mTLS không tự gắn end-user principal**. Nếu backend cần phân quyền theo `user-123`, vẫn phải có token/delegation/verified header protocol. Đồng thời kiểm tra certificate rotation, SPIFFE/SVID hoặc CA/truststore theo nền tảng đang dùng.

### 15.2. Không để dynamic routes tạo proxy vòng vào control plane

Nếu admin API có thể tạo route tùy ý, một người thiếu quyền có thể cố đưa `uri` tới:

~~~text
http://127.0.0.1:9090/actuator/...
http://169.254.169.254/...
http://internal-admin-service/...
~~~

Đây là rủi ro SSRF/open proxy. Nếu Gateway được cho phép truy cập các endpoint quản trị nội bộ, một route công khai có thể biến thành đường vòng qua trust boundary.

Do đó dynamic route control plane cần:

1. Authentication/RBAC/approval cho create/update/delete route.
2. Allowlist scheme/host/port và kiểm tra DNS resolution/redirect.
3. Chặn loopback, link-local, metadata endpoints và management listener khi không thuộc allowlist.
4. Audit revision, route ID, operator và rollback.
5. Negative test cho URL host/IP bị cấm, kể cả DNS rebinding/race.

Chỉ tin proxy đã xác minh **không ngăn SSRF** nếu client/admin không đủ quyền vẫn có thể thay `uri`.

## 16. Rate limiting, retry và observability phải dùng nguồn danh tính đúng

### 16.1. KeyResolver không được lấy tenant/user từ header giả

Một cách sai:

~~~java
// PHẢN DIỆN: caller tự chọn key và có thể đổi key để tránh quota.
return exchange -> Mono.justOrEmpty(
        exchange.getRequest().getHeaders()
                .getFirst("X-User-Id"));
~~~

Nếu rate limit gắn với `X-User-Id` client tự khai, attacker có thể đổi header mỗi lần và tạo nhiều quota buckets. Tương tự, nếu limiter dựa `X-Forwarded-For` không đáng tin, attacker có thể gửi địa chỉ giả để bypass.

### 16.2. Dùng principal đã xác thực làm quota key

Với JWT Resource Server:

~~~java
package demo.gateway.security;

import org.springframework.cloud.gateway.filter.ratelimit.KeyResolver;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;

import reactor.core.publisher.Mono;

@Configuration(proxyBeanMethods = false)
public class RateLimitIdentityConfiguration {

    @Bean
    KeyResolver verifiedUserKeyResolver() {
        return exchange -> exchange.getPrincipal()
                .ofType(JwtAuthenticationToken.class)
                .map(JwtAuthenticationToken::getName)
                .switchIfEmpty(Mono.just("unauthenticated"));
    }
}
~~~

Với route đã được `SecurityWebFilterChain` bảo vệ, key lấy từ JWT principal đã được xác minh. Giá trị `unauthenticated` là **bucket chung cho những request không có principal nếu route thật sự cho phép chúng đi tới limiter**, không phải cho phép chúng vượt authentication. Trong API nhạy cảm nên để Security **từ chối anonymous trước**; tránh lấy `X-User-Id` làm fallback.

Nếu cần quota theo tenant, key phải đến từ **tenant claim đã xác minh và đã được authorization chấp thuận**, không phải query/header `tenantId`. Đảm bảo bucket key length, charset và cardinality được giới hạn; không đưa JWT nguyên văn vào Redis key/metrics.

### 16.3. Tránh làm lộ thông tin khi retry, circuit breaker và fallback

Retry filter có thể gửi cùng request nhiều lần. Trước khi cho retry, kiểm tra:

- JWT/token còn hợp lệ và có đúng audience cho downstream attempt.
- Header nội bộ được tạo **đúng một lần** hoặc ghi đè, không append duplicate claims.
- Khi circuit breaker dùng fallback handler, fallback **không tự bỏ qua Security** hoặc nhận danh tính từ untrusted header.
- Với POST/PUT/PATCH có side effect, retry cần idempotency key/transaction policy.
- Khi backend fail, response không echo Authorization/Cookie/forwarded metadata trong error message.

Route selection và filter chain có thứ tự pre/post; nếu thêm một filter phía sau `VerifiedIdentityBridgeFilter` có thể sửa `X-Verified-Subject`, phải kiểm tra **thứ tự thực tế** bằng downstream request capture.

### 16.4. Audit và cảnh báo không dùng raw PII

Nên ghi nhận các tín hiệu:

| Tín hiệu | Mục đích |
| --- | --- |
| Public edge nhận inbound identity headers bị cấm | Phát hiện cố giả mạo hoặc client chưa migration |
| Auth 401 theo route class | Theo dõi token thiếu/sai, credential misuse |
| AuthZ 403 theo route class | Phát hiện thiếu role/scope/tenant permission |
| Request tới Gateway từ IP không phải trusted proxy | Phát hiện đường bypass hoặc misconfigured LB |
| Số request có duplicate identity headers | Phát hiện header pollution/casing conflicts |
| Mismatch forwarded Host/Proto với trusted ingress | Phát hiện host/scheme spoofing |
| Backend reject service identity/token | Phát hiện bypass, mTLS hoặc delegation lỗi |
| Route revisions và thay đổi `trusted-proxies` | Audit control plane và cấu hình trust |

Không log raw bearer token, cookie, `X-User-Id` giả, full query chứa secret hoặc thông tin client IP ở nơi không được phép. Audit event nên có **correlation ID tạo/chuẩn hóa tại edge**, route ID, loại vi phạm, status và source hop đã xác minh, với retention policy được phê duyệt.

Các meter labels chỉ nên dùng nhóm có ít biến thể. Không dùng một meter riêng cho từng token/user/IP vì high cardinality và rò rỉ dữ liệu.

### 16.5. CORS không ngăn curl hoặc service-to-service clients

Đặt:

~~~http
Access-Control-Allow-Origin: https://portal.example.test
~~~

chỉ áp quy tắc browser CORS khi client là trình duyệt. Nó **không ngăn curl** gửi `X-User-Id: admin`, cũng không bảo vệ backend gọi trực tiếp. Tránh coi CORS allowlist là anti-spoofing hoặc authentication; vẫn cần JWT/mTLS/network policy.

## 17. Những ngộ nhận phải kiểm tra trong code review

**A — “Header bắt đầu bằng X-Verified thì đáng tin.”**

Sai. Tên header là dữ liệu HTTP; bất kỳ client nào có đường kết nối đều có thể tự gửi cùng tên. Chỉ tin nguồn đã được xác thực và đường mạng được bảo vệ.

**B — “Có Gateway filter RemoveRequestHeader thì controller khác cũng an toàn.”**

Không mặc định. Gateway filter áp dụng cho **routes được chọn**; controller local/Actuator/WebFilter có lifecycle khác. Khi cần toàn WebFlux application, áp lớp `WebFilter` sớm và edge scrub.

**C — “Đặt `trusted-proxies: '.*'` là cho phép mọi proxy đáng tin.”**

Đó là trust-all cực rộng về mặt regex. Không nên dùng trên public path; phải cấu hình giới hạn nguồn và test trên topology có proxy xác minh.

**D — “`XForwardedRemoteAddressResolver.trustAll()` giúp lấy IP đầu tiên chính xác nhất.”**

Không. Địa chỉ đầu tiên có thể do client giả. Dùng `maxTrustedIndex` phù hợp chain và đảm bảo ingress xóa/ghi đè dữ liệu untrusted.

**E — “`maxTrustedIndex(2)` nghĩa là có hai hop thì an toàn.”**

Không tự động. Chỉ có ý nghĩa khi hai hop được xác minh và client không thể kết nối trực tiếp hoặc đưa chuỗi XFF giả không được scrub.

**F — “Gateway đã verify JWT, backend cứ tin header X-User-Id.”**

Không nếu backend còn đường direct access, hoặc header chưa được sinh lại từ verified principal. Token đúng audience hoặc mTLS service identity + verified metadata mới tạo được hợp đồng tin cậy.

**G — “Host=admin.example.test là điều kiện được quyền admin.”**

Sai. Host là route predicate/virtual hosting; có thể bị client điều khiển nếu ingress không hạn chế. Cần authentication/authorization riêng.

**H — “TLS ở public edge là đủ bảo vệ mọi hop.”**

Không. Gateway→backend vẫn có nguy cơ sniffing/spoofing/bypass trong network nội bộ; áp mTLS, security group/NetworkPolicy theo threat model.

**I — “Chỉ cần xóa X-Forwarded-For tại Gateway thì mọi thứ ổn.”**

Không. Nếu bạn xóa metadata hợp lệ mà không có đường tạo lại, backend có thể mất thông tin IP/proto cần thiết. Thiết kế policy tại **trusted ingress**, xác minh ở từng hop, chỉ chuyển field thật sự cần.

**J — “Backend đã trả 200 sau khi thêm header xác thực nghĩa là bảo mật đúng.”**

Không. Cần negative tests với fake identity, wrong issuer/audience/scope, duplicate headers và direct backend access. Một response 200 chỉ cho biết một request được xử lý.

## 18. Troubleshooting khi header bị giả mạo hoặc bị xóa nhầm

| Hiện tượng | Nguyên nhân có thể | Bước kiểm tra |
| --- | --- | --- |
| Backend vẫn thấy `X-User-Id: admin` | Scrub WebFilter không chạy, route filter khác, backend không qua Gateway | Handler mapping, filter ordering, recorded backend request |
| `X-Verified-Subject` thành `attacker` | Header client được pass-through hoặc bridge lấy từ client header | Trace source claim, kiểm tra WebFilter/GlobalFilter |
| Có hai giá trị `X-Verified-Subject` | Dùng `AddRequestHeader`/multiple writers | Dùng remove+set từ principal, kiểm tra order |
| Backend không thấy verified subject dù JWT hợp lệ | Filter order, route ID khác `orders-protected` hoặc remove sau bridge | Route ID, GlobalFilter order, downstream capture |
| Gateway trả 401 cho JWT hợp lệ | Wrong issuer/JWKS, expired/not-before, audience validator, no auth context | Security logs đã redact, token claims ở môi trường test |
| Gateway trả 403 | Thiếu `SCOPE_orders.read` hoặc Security matcher khác | Kiểm tra authorities, role/scope mapping |
| JWT có scope nhưng backend 403 | Resource-level policy/tenant ownership backend | Backend authorization logs, không bỏ qua quyền |
| Direct backend access thành công | Service bị public/NetworkPolicy chưa enforce | Port/Service/Ingress, security group, mTLS |
| Client đổi XFF thì rate limiter key đổi | Limiter dùng untrusted XFF/header | Đổi sang authenticated principal/trusted resolver |
| `RemoteAddr` chỉ thấy IP ingress | Đây là remote TCP peer, không phải end-user IP | Topology, resolver, trust chain |
| `maxTrustedIndex` chọn IP giả | Số hops không đúng hoặc edge không scrub | Captured chain và mạng nguồn thực |
| `trusted-proxies` regex không match | Sai escaping/IPv6/port/case hoặc namespace | Configuration metadata, effective properties |
| Backend nhận `X-Forwarded-Host` từ client | Edge append/thông qua mà không overwrite | Ingress config, spoofed Host tests |
| OAuth redirect trỏ HTTP khi public dùng HTTPS | Forwarded proto không được xử lý đúng | TLS termination, forwarded strategy, allowed public base URL |
| OAuth redirect trỏ domain lạ | Tin X-Forwarded-Host/Host untrusted | Canonical host allowlist, edge reset |
| Sau bật RemoveRequestHeader, backend luôn 401 | Backend trước đó dựa vào header giả hoặc token bị loại sai | Migration contract, token audience, AuthZ backend |
| CORS preflight trả 403 | OPTIONS và Security/CORS policy không thống nhất | Preflight policy, actual GET tests, không mở auth bừa |
| HTTP 502 sau bật mTLS | Certificate, truststore, SNI hoặc client identity sai | TLS handshake diagnostics, SAN/issuer/rotation |
| Route mới bypass global identity policy | Chỉ dùng route-specific filters hoặc fallback không kiểm tra | Default filters/WebFilter, route inventory, tests |
| Management Actuator lộ thông tin routes | Endpoint expose public | Management port/NetworkPolicy/RBAC |

### 18.1. Quy trình điều tra một request nghi giả mạo

1. **Xác định nguồn kết nối thật** tới Gateway: socket peer có phải ingress được phê duyệt?
2. **Kiểm tra ingress scrub**: header nào được xóa/ghi đè, trusted proxy chain có đủ hops không?
3. **Xác minh authentication**: token chữ ký, issuer/audience, expiry và quyền được cấp.
4. **Kiểm tra WebFilter**: identity header client bị loại bỏ trước các handler khác chưa?
5. **Kiểm tra Gateway route ID và filter order**: request có vào đúng route và bridge được chạy không?
6. **Kiểm tra downstream recording**: backend nhận header nào, có duplicate values không?
7. **Kiểm tra kênh backend**: direct access có bị chặn, mTLS principal có đúng không?
8. **Kiểm tra authorization tài nguyên**: user/tenant có quyền với object thật không?
9. **Đối chiếu các phiên bản**: WebFlux 4.x/5.x, Servlet/Web MVC, Spring Security, ingress/controller versions.
10. **Chạy lại negative tests** sau khi sửa và ghi lại revision để rollback.

Không tháo authentication, xóa NetworkPolicy hoặc bật `trusted-proxies: '.*'` để “làm cho test pass”. Những hành động này có thể biến một lỗi cấu hình thành lỗ hổng bảo mật.

### 18.2. Incident runbook khi nghi đã có identity spoofing

1. Chặn đường public/direct access nghi vấn tới Gateway/backend bằng policy có rollback.
2. Tạm ngưng route hoặc tính năng dựa vào header trần, giữ lại logs/audit evidence theo quy trình.
3. Kiểm tra logs và backend access traces để xác định yêu cầu nào dùng header giả, không suy từ một mẫu request.
4. Nếu token/credential có nguy cơ lộ, rotate/revoke theo playbook IdP.
5. Sửa edge scrub, Gateway WebFilter/filters, trusted proxy settings và backend auth contract.
6. Kiểm tra mọi replicas/route definition sources và các đường phụ như NodePort, port-forward, sidecar.
7. Chạy negative suite từ **Internet, trusted ingress và mạng nội bộ**; xác minh mTLS/NetworkPolicy.
8. Theo dõi auth failures, suspicious forwarding metadata, route changes và downstream violations sau rollout.

Không đưa raw JWT/cookie hoặc thông tin cá nhân vào ticket/chat không được phê duyệt. Chỉ báo cáo tác động khi có bằng chứng, phân biệt cấu hình yếu với sự cố khai thác thật.

## 19. Checklist gia cố bảo mật trước production

### 19.1. Edge và mạng

- [ ] Chỉ có **public ingress/edge được phê duyệt** kết nối tới Gateway application listener.
- [ ] Backend chỉ nhận request từ Gateway workload/service identity, không có direct Internet/NodePort/LoadBalancer bypass.
- [ ] Firewall/security groups/NetworkPolicy bao gồm cả IPv4 và IPv6.
- [ ] TLS tại public edge có certificate, hostname validation và rotation đúng.
- [ ] Gateway→backend dùng mTLS/TLS và service authorization nếu threat model yêu cầu.
- [ ] Không công khai Gateway Actuator write endpoints; management listener tách network và có RBAC.
- [ ] Các đường sidecar, port-forward, debugging Service và NAT đã được rà soát.

### 19.2. Header và proxy trust

- [ ] Edge xóa inbound `X-User-Id`, `X-Role`, `X-Tenant-Id`, `X-Authenticated-User` và các identity claims theo danh sách tổ chức.
- [ ] Có chính sách với header identity có tên khác/legacy, kể cả uppercase/lowercase, duplicates và underscore variants.
- [ ] Mọi Gateway Server routes loại bỏ header không được phép trước downstream.
- [ ] Nếu app có WebFlux controllers ngoài routes, có `WebFilter` hoặc cơ chế tương ứng bảo vệ mọi handler.
- [ ] Không có route filter phía sau vô tình append/xóa lại verified identity một cách sai lệch.
- [ ] `Forwarded` và `X-Forwarded-*` chỉ do trusted edge tạo/canonicalize; không tin client raw values.
- [ ] `trusted-proxies` được giới hạn, không dùng `.*`, đúng namespace Gateway WebFlux/Web MVC version.
- [ ] `x-forwarded.*-append` được cấu hình theo thiết kế, có test actual downstream headers.
- [ ] Nếu dùng `maxTrustedIndex(n)`, n phù hợp số verified hops; không dùng `trustAll()` với untrusted clients.
- [ ] `RemoteAddr` và `XForwardedRemoteAddr` không bị nhầm là authentication/role.
- [ ] `Host`/`X-Forwarded-Host`/`X-Forwarded-Proto` được kiểm tra trước khi tạo redirect, callback URL và tenant routing.

### 19.3. Identity và authorization

- [ ] Spring Security Resource Server xác minh chữ ký/keys, issuer, expiry/not-before, audience và token policy.
- [ ] Scope/role được map từ validated authentication context, không từ client header.
- [ ] Không có `permitAll()` hoặc fallback route rộng ngoài chính sách.
- [ ] Gateway không phát header `X-Verified-Subject` từ path/query/header do client điều khiển.
- [ ] Khi truyền header nội bộ, backend xác minh Gateway workload identity/kênh và không chấp nhận direct calls.
- [ ] Ưu tiên token đúng backend audience hoặc token exchange nếu yêu cầu delegated authorization.
- [ ] Backend luôn kiểm tra resource ownership/tenant permission trên dữ liệu thật.
- [ ] RateLimiter/KeyResolver dùng principal đã xác thực hoặc nguồn IP đã được xác minh.
- [ ] CSRF/cookie/session và CORS được xử lý theo loại client; không coi CORS là authentication.

### 19.4. Kiểm thử và vận hành

- [ ] Có positive test token hợp lệ + đúng scope và negative tests token thiếu/sai issuer/audience/scope.
- [ ] Có tests `X-User-Id: admin`, `X-Role: admin`, duplicated `X-Verified-Subject` và case-insensitive names.
- [ ] Backend stub xác nhận **header client biến mất** và verified claim (nếu bật) đúng subject.
- [ ] Có test network bypass từ public subnet tới Gateway/backend phải bị chặn.
- [ ] Có test XFF spoofing qua Ingress thật và test trusted proxy chain.
- [ ] Có test `X-Forwarded-Host`/Proto giả không gây open redirect hoặc URL sai origin.
- [ ] Có test route fallback/dynamic routes không bỏ qua security/filter policy.
- [ ] Có audit security events theo route class và alert cho proxy-trust drift.
- [ ] Không log raw Authorization/Cookie/PII hoặc full forwarded chain vào metrics labels.
- [ ] Có rollback revision/approval cho sửa `trusted-proxies`, filters và destination URIs.
- [ ] Kiểm tra lại sau mỗi thay đổi Gateway BOM, Spring Security, Ingress/CDN hoặc topology mạng.

## 20. Bài tập thực hành

### Bài 1 — Chứng minh vì sao xóa header sau routing chưa đủ

Viết một `WebFilter` đọc `X-User-Id` trước khi Gateway route `RemoveRequestHeader` chạy trong môi trường test. Kiểm tra WebFilter **vẫn có thể thấy giá trị giả** mặc dù backend không nhận. Từ đó giải thích vì sao edge scrub và `UntrustedIdentityHeadersWebFilter` sớm cần thiết cho toàn ứng dụng.

Không triển khai WebFilter dùng giá trị giả để cấp quyền; bài tập chỉ phục vụ quan sát ordering.

### Bài 2 — Kiểm thử header name và duplicate values

Gửi các biến thể:

~~~http
X-User-Id: admin
x-user-id: admin
X-USER-ID: admin
X-User-Id: admin
X-User-Id: other
~~~

Ghi lại raw request tại edge và recorded request ở backend test. Phân biệt HTTP parser gộp giá trị, loại bỏ duplicate hay từ chối request. **Backend không được dùng bất kỳ giá trị nào từ nhóm client identity headers** làm principal.

### Bài 3 — Vẽ chuỗi proxy đúng của hệ thống

Từ topology:

~~~text
Browser → CDN → Ingress → Gateway → Orders backend
~~~

xác định ai được phép đặt XFF, proxy nào trực tiếp kết nối Gateway, có bao nhiêu trusted hops và điểm nào phải reset inbound XFF. Sau đó viết negative test với giá trị `10.0.0.8` giả ở trái cùng và so kết quả của `trustAll()` (chỉ lý thuyết/test cô lập) với `maxTrustedIndex(n)` theo chính sách.

### Bài 4 — Migration từ identity header sang token hợp lệ

Giả sử backend cũ đang tin `X-Tenant-Id`. Lập kế hoạch migration:

1. Backend hỗ trợ xác minh JWT hoặc verified metadata trên kênh mTLS.
2. Gateway loại bỏ raw client `X-Tenant-Id`.
3. Authentication/authorization map tenant theo issuer và resource policy.
4. Đo tỷ lệ clients lỗi, cảnh báo, canary và rollback.
5. Chỉ bỏ hẳn legacy mode khi tất cả backend replicas đã dùng policy mới.

Lập test chứng minh một token có `tenant_id=tenant-42` không được dùng để đọc dữ liệu `tenant-99` chỉ vì path/query client yêu cầu.

### Bài 5 — Đánh giá tác động của Route fallback

Tạo hai routes cùng path, một route yêu cầu quyền và một fallback rộng. Kiểm tra rằng client thiếu scope không thể né security bằng cách làm sai Host/Header của route chính để rơi vào fallback. Nếu có lỗ hổng, sửa policy ở **Spring Security/backend** và thu hẹp route/fallback, không cố chọn một regex bí mật.

## 21. Câu hỏi tự kiểm tra

**1. Vì sao xóa `X-User-Id` ở Gateway vẫn chưa đủ bảo mật backend?**

Vì backend có thể bị gọi trực tiếp qua một đường khác, hoặc một Gateway handler/filter khác có thể đọc header trước khi bị xóa. Cần edge scrub, network/mTLS trust, authentication và backend authorization.

**2. `SetRequestHeader=X-Verified-Subject,admin` có tạo danh tính đã xác minh không?**

Không. Nó chỉ đặt chuỗi hằng. Danh tính phải được lấy từ token/session đã xác thực hoặc cơ chế identity đáng tin.

**3. `spring.cloud.gateway.server.webflux.trusted-proxies` có phải CIDR firewall không?**

Không. Theo docs Gateway, đó là **Java regex** liên quan Forwarded/XForwarded header filters. Firewall/NetworkPolicy là cơ chế riêng, và không thể bị thay bằng regex này.

**4. Vì sao không chọn địa chỉ bên trái nhất trong `X-Forwarded-For`?**

Vì client có thể tự thêm địa chỉ đầu tiên nếu trusted edge không reset. `trustAll()` có nguy cơ spoofing; cần xác minh hop/chain và dùng resolver phù hợp.

**5. Vì sao `maxTrustedIndex(2)` cũng có thể sai?**

Vì giá trị 2 chỉ an toàn nếu topology thực sự có đúng các hop cần tin và không có đường bypass. Khi chuỗi ít phần tử hoặc có client-supplied entries, nó có thể chọn địa chỉ sai.

**6. `WebFilter` và `GatewayFilter` khác nhau gì trong mục đích này?**

WebFilter là bộ lọc WebFlux trước/rộng hơn handler, có thể làm sạch inbound request cho cả controllers; GatewayFilter thuộc chain của **route đã chọn** và thích hợp kiểm soát request downstream theo route.

**7. Vì sao JWT có signature đúng nhưng vẫn cần kiểm tra `aud`?**

Vì token có thể được cấp cho một dịch vụ khác. Audience giúp ràng buộc token có được sử dụng cho ứng dụng/backend mục tiêu hay không.

**8. Rate limiter nên dùng giá trị gì để định danh một người dùng?**

Principal được xác thực hoặc một tenant key đã được xác minh; không dùng `X-User-Id` client tự khai hoặc XFF không được kiểm chứng.

**9. mTLS giữa Gateway và backend có tự cấp quyền đọc mọi order cho user không?**

Không. mTLS xác thực workload service, còn end-user permissions phải được xác minh qua token/claims và resource-level authorization.

**10. Một request với Host admin trả HTTP 200 có chứng minh trust boundary đúng không?**

Không. Cần kiểm tra route thực sự được chọn, JWT/scope/tenant policy, downstream headers, trusted ingress và khả năng bypass backend.

## 22. Tài liệu chính thức và tham khảo

1. [Spring Cloud Gateway WebFlux 5.0 — RemoveRequestHeader GatewayFilter](https://docs.spring.io/spring-cloud-gateway/reference/5.0/spring-cloud-gateway-server-webflux/gatewayfilter-factories/removerequestheader-factory.html): xóa request headers trước khi forward.
2. [Spring Cloud Gateway WebFlux — SetRequestHeader GatewayFilter](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/gatewayfilter-factories/setrequestheader-factory.html): thay thế toàn bộ values cùng tên, khác `AddRequestHeader`.
3. [Spring Cloud Gateway WebFlux — HttpHeadersFilters](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/httpheadersfilters.html): `trusted-proxies`, Forwarded, XForwarded, RemoveHopByHop và append behavior.
4. [Spring Cloud Gateway 5.0 — Configuration Properties](https://docs.spring.io/spring-cloud-gateway/reference/5.0/configprops.html): namespace WebFlux/WebMVC, `trusted-proxies` và X-Forwarded controls.
5. [Spring Cloud Gateway 5.0 — Route Predicate Factories](https://docs.spring.io/spring-cloud-gateway/reference/5.0/spring-cloud-gateway-server-webflux/request-predicates-factories.html): `RemoteAddr`, `XForwardedRemoteAddressResolver.maxTrustedIndex`, rủi ro `trustAll`, `XForwardedRemoteAddr`.
6. [Spring Security — Reactive OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html): xác thực JWT, security context và authorities.
7. [Spring Security — WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html): `SecurityWebFilterChain`, matcher và nhiều chains.
8. [Spring Security — Reactive Request Authorization](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html): phân quyền reactive requests theo principal/scope.
9. [Spring Framework — WebFlux Reactive Core / Filters](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html): WebFilter và WebFilterChain trên WebFlux.
10. [NGINX — proxy_set_header](https://nginx.org/en/docs/http/ngx_http_proxy_module.html#proxy_set_header): quản lý request headers ở reverse proxy.
11. [RFC 7239 — Forwarded HTTP Extension](https://www.rfc-editor.org/rfc/rfc7239): cú pháp `Forwarded` và proxy chain.
12. [Kubernetes — Network Policies](https://kubernetes.io/docs/concepts/services-networking/network-policies/): giới hạn ingress/egress theo Pod và namespace selectors.
13. [OWASP API Security 2023 — Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/): vì sao backend vẫn phải kiểm tra quyền truy cập object.

**Ghi nhớ:** Trong Spring Cloud Gateway, **đừng bao giờ dùng `X-User-Id`, `X-Role`, `X-Tenant-Id` hoặc `X-Forwarded-For` do client tự khai như bằng chứng danh tính hay quyền hạn**. Xóa header nguy hiểm tại **trusted edge** và trong Gateway, xác thực JWT/session với issuer/audience/scope, rồi chỉ phát metadata nội bộ từ **verified principal** qua kênh Gateway→backend được bảo vệ. `trusted-proxies` và `maxTrustedIndex` chỉ có ý nghĩa trên một **proxy chain được xác minh và không có đường bypass**. Thành công là khi negative tests chứng minh mọi header giả bị loại, backend không thể bị gọi trực tiếp và quyền tài nguyên vẫn được kiểm tra — không phải chỉ vì một request hợp lệ trả HTTP 200.
