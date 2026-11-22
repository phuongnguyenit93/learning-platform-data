# Giới hạn nguồn mạng và ngăn truy cập trực tiếp bỏ qua proxy trong Spring Security

## 1. Vì sao reverse proxy xác thực đúng vẫn có thể mất an toàn?

Giả sử một tổ chức đặt **identity-aware reverse proxy** phía trước ứng dụng Spring Boot. Proxy thực hiện SSO bằng OIDC, SAML, Kerberos/SPNEGO hoặc cơ chế được phê duyệt, rồi chuyển một header như `X-Authenticated-User` đến backend. Backend sử dụng Spring Security **pre-authentication** để nhận tên người dùng từ header và nạp quyền nội bộ.

Luồng dự kiến:

~~~text
Internet / nhân viên
       |
       v
HTTPS public hostname: portal.example.org
       |
       v
[Trusted authentication proxy]
  - xác thực người dùng
  - thực thi chính sách truy cập ở biên
  - xóa header do client tự đặt
  - tạo assertion danh tính cho backend
       |
       v
[Spring Boot backend chỉ nhận request từ proxy]
  - xác minh ranh giới peer/proxy
  - chấp nhận identity assertion hợp lệ
  - kiểm tra tài khoản và quyền ứng dụng
       |
       v
Business endpoints
~~~

Nếu backend còn mở cổng trực tiếp, ví dụ `http://app-node:8080`, `NodePort`, một `LoadBalancer</BT> phụ hoặc `hostNetwork`, người gửi request có thể **đi vòng qua proxy**. Nếu Spring lấy danh tính bằng `RequestHeaderAuthenticationFilter` mà không xác minh request đến từ nguồn đáng tin, một header tự khai có thể biến thành principal đã xác thực.

**Đây là lỗi nghiêm trọng về trust boundary**, không phải lỗi thiếu một annotation `@PreAuthorize` đơn lẻ. Khi một bộ lọc pre-auth chấp nhận dữ liệu danh tính từ nguồn không tin, các kiểm tra authorization phía sau có thể thấy một user giả nhưng trông như đã được xác thực.

Bài Knowledge thuộc **Spring Security - federation → Xác thực qua proxy**, chủ đề **“Giới hạn nguồn mạng và ngăn truy cập trực tiếp bỏ qua proxy”**.

### Kết quả học tập

Sau bài này, bạn có thể:

1. Phân biệt **xác thực ở proxy**, **kênh vận chuyển proxy→backend**, **pre-authentication ở Spring** và **authorization tại ứng dụng**.
2. Hiểu vì sao `RequestHeaderAuthenticationFilter` không tự xác thực username trong header.
3. Thiết kế **deny-by-default** ở network layer (security group/firewall/Kubernetes NetworkPolicy), tránh backend public listener và mọi ingress phụ.
4. Biết dùng **mTLS/workload identity** để xác thực hop proxy→backend khi cần assurance cao hơn IP allow-list.
5. Xóa/ghi đè header giả mạo như `X-Authenticated-User`, `Remote-User`, `X-Forwarded-User` và `Forwarded/X-Forwarded-*</BT> tại **ranh giới tin cậy**.
6. Không nhầm **socket peer address** với **client IP lấy từ X-Forwarded-For**; không dùng giá trị do browser kiểm soát để quyết định proxy có đáng tin hay không.
7. Cấu hình Spring Security pre-auth fail closed, không mở form login/basic auth fallback ngoài dự kiến.
8. Kiểm tra các đường bypass qua direct pod IP, NodePort, LoadBalancer phụ, admin/actuator port, localhost sidecar, IPv6 và đường nội bộ khác.
9. Áp dụng ví dụ NGINX, Kubernetes NetworkPolicy, Spring Security config và chương trình Java 17 độc lập.
10. Thực hiện negative tests, quan sát logs/metrics, xử lý rollout/rollback mà không nới quyền tùy tiện.

**Ngữ cảnh:** Java 17+, Spring Boot 3.x, Spring Security Servlet 6.x/7.x, NGINX và Kubernetes là ví dụ. Cấu hình khác nhau tùy cloud, CNI, ingress, service mesh và phiên bản. Các địa chỉ `example.org`, mạng `10.42.0.0/16` đều là minh họa, không phải cấu hình hợp lệ của mọi deployment.

---

## 2. Mô hình tin cậy: ai thực sự đã xác minh danh tính?

Một request từ browser có thể mang:

~~~http
GET /admin/reports HTTP/1.1
Host: portal.example.org
X-Authenticated-User: administrator
X-Forwarded-For: 10.0.0.20
X-Forwarded-Proto: https
~~~

**Không được coi bất kỳ header nào trên đây là bằng chứng danh tính.** Browser, mobile client hoặc một chương trình HTTP có thể tự tạo chúng. Chỉ khi một **proxy đáng tin** đã:
- Xác thực browser/token theo chính sách;
- Loại toàn bộ các phiên bản header do caller gửi;
- Tạo lại identity assertion từ **authentication context đã xác minh**;
- Gửi qua kênh **chỉ proxy được phép kết nối backend**;
- Và backend xác minh/giới hạn nguồn kết nối;

thì backend mới có cơ sở để sử dụng assertion.

### Năm lớp bảo vệ độc lập

| Lớp | Câu hỏi kiểm tra | Ví dụ biện pháp |
| --- | --- | --- |
| **L1: Network reachability** | Bên không phải proxy có mở kết nối tới backend được không? | Firewall, SG, NetworkPolicy, private Service, không NodePort public |
| **L2: Proxy workload identity** | Peer đến backend có thật sự là proxy được phê duyệt không? | mTLS certificate/SPIFFE ID, private endpoint + policy; IP allow-list là bổ sung |
| **L3: Header provenance/integrity** | Identity header có do proxy ghi sau xác thực không? | Strip inbound, overwrite canonical header, reject duplicates |
| **L4: Spring pre-authentication** | Username được lấy chỉ từ kênh đã tin và có hợp đồng chặt chưa? | RequestHeaderAuthenticationFilter + provider + fail closed |
| **L5: Business authorization** | User có được phép truy cập tài nguyên/hành động này không? | UserDetails/account status, tenant/ACL, @PreAuthorize/AuthorizationManager |

**Không chọn một trong năm để thay toàn bộ những lớp còn lại.** TLS public từ browser tới proxy không bảo vệ kết nối nội bộ nếu backend vẫn mở cổng trực tiếp. Ngược lại, một NetworkPolicy đúng cũng không chứng minh proxy đã thực sự xác thực user khi phát header.

## 3. Điểm nguy hiểm của RequestHeaderAuthenticationFilter

Spring Security mô tả `RequestHeaderAuthenticationFilter` là bộ lọc **pre-authentication**: lấy tên người dùng từ một HTTP request header (mặc định lịch sử là `SM_USER` trong ví dụ SiteMinder) và đưa vào cơ chế Spring Security để nạp UserDetails/authorities.

**Bộ lọc này không xác thực chính header đó.** Spring Security documentation cảnh báo: nếu attacker có thể tự đặt header được tin rồi gửi tới ứng dụng, attacker có thể chọn tùy ý username. Điều này đặc biệt nguy hiểm khi user local account mapping có đặc quyền cao.

Luồng sai:

~~~mermaid
flowchart TD
    A[Client không đăng nhập] --> B[Đường mạng trực tiếp vào backend:8080]
    B --> C[Header X-Authenticated-User tự khai]
    C --> D[RequestHeaderAuthenticationFilter chỉ đọc header]
    D --> E[PreAuthenticatedAuthenticationProvider nạp user]
    E --> F[Spring thấy Authentication đã được tạo]
    F --> G[Business endpoint tin principal giả]
~~~

**Rủi ro còn xuất hiện trong mạng nội bộ**: một pod khác, một developer host qua VPN, một công việc batch, một service SSRF-capable hoặc một ingress phụ có thể kết nối backend. “Chỉ private IP” không tương đương “chỉ trusted proxy”.

### Hai điều kiện để pre-auth an toàn hơn

1. **Bất kỳ request nào đến Spring theo đường pre-auth bắt buộc đi qua trusted authentication proxy**, không có đường trực tiếp hoặc authentication fallback không mong muốn.
2. **Proxy tự tạo header danh tính từ kết quả xác thực đáng tin**, không chấp nhận header do browser/user tự khai, và backend không tin headers nếu không có xác thực hop.

Spring có thể kiểm tra trạng thái account và authorities, nhưng **không tự biết nguồn sinh header** nếu network/proxy trust chưa được thiết kế.

## 4. Không nhầm X-Forwarded-For với danh tính proxy

Có ba loại “địa chỉ” dễ bị nhầm:

| Giá trị | Ý nghĩa | Có thể dùng xác minh nguồn proxy không? |
| --- | --- | --- |
| **Transport socket peer** | Endpoint TCP/TLS kết nối trực tiếp tới app server | Có thể là tín hiệu bổ sung nếu lấy từ lớp transport không bị rewrite và network route được kiểm soát |
| **X-Forwarded-For** | Chuỗi client/proxy IP được chuyển tiếp qua HTTP headers | **Không**, nếu edge chưa strip/overwrite và hop trust chưa được xác minh |
| **Forwarded: for/by/host/proto** | Metadata HTTP theo RFC 7239 | **Không**, bản thân header vẫn do client có thể tự tạo |
| **X-Real-IP** | Header IP do proxy có thể đặt | Không thay xác thực proxy |
| **X-Forwarded-Proto** | Scheme gốc theo proxy | Không chứng minh TLS thực giữa proxy và backend |
| **X-Forwarded-Host** | Host gốc theo proxy | Không phải allow-list backend identity |
| **mTLS peer identity** | Certificate/SAN đã được TLS stack xác minh cho hop tới backend | Có thể là bằng chứng workload identity, nếu đúng trust anchors/policy |

Ví dụ có nguy cơ:

~~~java
// Không làm như vậy để xác định đây có phải trusted proxy:
boolean trustedProxy = request.getHeader("X-Forwarded-For")
        .startsWith("10.42.");
~~~

Caller có thể tự viết header này. Ngoài ra `getRemoteAddr()</BT> trong Servlet có thể **đã bị thay đổi bởi Tomcat RemoteIpValve hoặc ForwardedHeaderFilter**, tùy cấu hình. Nếu muốn kiểm tra **raw transport peer**, lấy từ lớp ingress/firewall hoặc connector có cơ chế lưu địa chỉ peer gốc trước rewrite. Đừng dựa trên một giá trị `getRemoteAddr()</BT> đã được forwarded-header middleware thay thế.

**Nguồn mạng và danh tính người dùng là hai tín hiệu khác nhau**. Một browser IP “nằm trong mạng công ty” không được phép tự viết identity assertion rồi đi thẳng backend.

## 5. Đúng kiến trúc: backend không được public

Một mô hình khuyến nghị:

~~~mermaid
flowchart LR
    U[Internet / corporate browser] --> E[Public edge + authentication proxy]
    E -->|Authenticated private hop| A[Spring Boot backend]
    A --> D[(Database/private dependencies)]
    X[Untrusted client / sibling workload] -.->|Blocked by firewall or NetworkPolicy| A
~~~

Thực hiện:
- Public DNS của app chỉ trỏ vào **edge ingress/proxy**, không trỏ backend IP.
- Backend được triển khai bằng private IP/service, không mở Internet load balancer riêng.
- Firewall/cloud security group ở backend **chỉ cho phép inbound** từ proxy tier; nếu khả thi, dùng identity-based rules/thẻ tài nguyên hơn là IP thủ công.
- Trong Kubernetes, dùng `ClusterIP` service (không tự có Internet ingress) cộng với NetworkPolicy chọn chính xác ingress controller/auth-proxy pods.
- Hạn chế node host ports, `hostNetwork</BT>, NodePort, LoadBalancer khác, internal gateway/route phụ và IPv6.
- Tách admin/actuator/metrics endpoints khỏi public traffic, với authentication và network policy riêng.
- Cho health probes từ những nguồn đúng mà không mở toàn bộ admin API.
- Tăng assurance bằng **mTLS proxy→backend**, backend chỉ tin peer cert đúng workload identity.
- Chỉ sau đó mới cho Spring nhận pre-auth header.

**Không có một thuộc tính Spring Boot `server.address=127.0.0.1` áp dụng được cho mọi deployment.** Trong một số môi trường proxy và app là process trên cùng máy, bind loopback có thể phù hợp; trong Kubernetes pod khác host/network, bind loopback sẽ làm ingress không thể kết nối. Chọn private service/bind address + policy theo topology thật.

## 6. Ma trận đường vào phải kiểm kê

Trước production, lập bảng mọi đường mạng có thể đến app:

| Đường | Có được đến backend? | Bằng chứng bắt buộc |
| --- | --- | --- |
| Public HTTPS qua identity proxy | **Có**, sau xác thực | Proxy identity + network policy + sanitized headers |
| Internet → backend IP/public LB phụ | **Không** | Cloud firewall/SG/LB binding deny |
| Pod bất kỳ cùng namespace → backend | **Không** trừ nếu là trusted proxy/service được chỉ định | NetworkPolicy podSelector chính xác |
| Pod namespace khác → backend | **Không** trừ đường rõ ràng | Namespace/pod selector + RBAC |
| Host node → backend/pod | Chỉ các tác vụ được duyệt | Host firewall/cluster control; CNI behavior |
| NodePort/hostPort → backend | Thông thường **không** | Không expose hoặc firewall deny |
| Localhost bên trong cùng pod | Có thể truy cập bằng sidecar/process | Container isolation/loopback trust; không coi mọi sidecar là proxy |
| Health probe | Chỉ endpoint và nguồn xác định | Health-only path/port/network policy |
| Actuator/management port | Chỉ vận hành | Private port, role auth, distinct policy |
| kubectl port-forward | Chỉ identities được cấp quyền Kubernetes API | RBAC/audit; NetworkPolicy không thay RBAC |
| IPv6 address/public AAAA | Chỉ nếu được thiết kế | Chính sách IPv6 song song IPv4 |
| DR/staging/alternate ingress | Chỉ đường đã được đưa vào trust model | Cùng yêu cầu auth/header hygiene |

**Chú ý Kubernetes:** NetworkPolicy phụ thuộc CNI có hỗ trợ enforcement, và policy lựa chọn theo pod/namespace có thể bị tác động bởi quyền chỉnh labels. Nếu RBAC cho phép untrusted party tự gắn label `app: auth-proxy` lên pod của họ trong namespace đáng tin, label-based allow-list có thể bị abuse. Vì thế cần **RBAC/admission policy** bảo vệ labels và namespace.

## 7. Kubernetes NetworkPolicy: chỉ cho ingress proxy

Trong namespace `apps` có pod chạy backend với label `app: portal-backend`, proxy chạy namespace `edge` và label `app: identity-proxy`. Mẫu:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: portal-only-from-identity-proxy
  namespace: apps
spec:
  podSelector:
    matchLabels:
      app: portal-backend
  policyTypes:
    - Ingress
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: edge
          podSelector:
            matchLabels:
              app: identity-proxy
      ports:
        - protocol: TCP
          port: 8080
~~~

**Ý nghĩa:**
- Những pod được chọn bởi `podSelector</BT> chỉ được nhận ingress phù hợp policy.
- `namespaceSelector</BT> và `podSelector</BT> **trong cùng một phần tử `from`** mang ý nghĩa kết hợp AND: chỉ các proxy pods ở namespace edge.
- Nếu tách selectors thành hai phần tử riêng, semantics là OR và có thể mở rộng nguồn không mong muốn.
- Cổng 8080 là **cổng thực mà backend pod lắng nghe**, không phải luôn là cổng public TLS của proxy.
- Policy này **không** thiết lập TLS, xác thực user, mTLS identity hoặc header cleansing. Nó là kiểm soát mạng L3/L4.

### Những giới hạn phải kiểm tra

1. NetworkPolicy không tự hoạt động nếu CNI không hỗ trợ enforcement.
2. `ClusterIP` không tự bảo vệ khỏi **tất cả** workloads nội bộ; NetworkPolicy mới là một lớp hạn chế pod-to-pod.
3. Node/hostNetwork traffic và NAT path có thể có hành vi phụ thuộc CNI/cloud; cần kiểm thử đường thực.
4. Khi policy chọn tất cả backends, đừng vô ý chặn health probes/sidecars/service mesh traffic mà không có kế hoạch.
5. NetworkPolicy không ngăn Kubernetes API users có quyền cao thực hiện `port-forward`; bảo vệ qua RBAC/audit/admission.
6. IPv6/dual-stack và hostPort cần kiểm tra riêng, không suy policy IPv4 đã bao phủ.
7. Lọc theo labels phụ thuộc bảo vệ quyền đổi labels.
8. Egress cũng cần thiết kế hạn chế đường exfiltration nếu threat model yêu cầu; policy ở đây chỉ minh họa ingress.
9. Có thể cần default-deny toàn namespace và mở whitelist chính xác cho DNS/metrics/health; tránh dùng `ingress: - {}</BT> vì mở tất cả.

**Triển khai từng bước:** tạo test pod **không** có label proxy và xác minh không mở được TCP tới backend; một test proxy pod đã định danh mới được phép kết nối. Nếu không có CNI enforcement, coi policy YAML là **chưa bảo vệ thực tế**.

## 8. Cloud VM/container không dùng Kubernetes

Với VM/EC2/Compute Engine/Azure VM, có thể:

- Backend VM/NIC không có public IP nếu không cần.
- Internal load balancer chỉ nằm trong subnet private và không public listener.
- Security group/network security group inbound giới hạn tới **proxy security group/managed identity source** nếu cloud hỗ trợ; nếu phải dùng CIDR, cập nhật tự động cùng thay đổi proxy IP.
- Trên backend có host firewall deny-by-default.
- Phía proxy chỉ forward tới private address và TLS/mTLS backend được xác minh.
- Cấu hình cân bằng tải không mở “maintenance LB” khác bỏ qua proxy.
- Đường VPN/bastion/CI runners cần được đưa vào threat model, không mặc định tin toàn bộ private RFC1918 space.
- Admin SSH/Kubernetes access theo RBAC, không dùng cổng HTTP app để debug trực tiếp.
- Nếu proxy/app cùng host, app có thể bind loopback/socket Unix và đặt file permissions; nhưng process khác trên cùng host vẫn là một nguồn có thể gọi, cần OS isolation.

**Vì sao chỉ firewall chưa đủ?** Một pod/VM đã compromise nằm trong allow-list hoặc có khả năng giả lập proxy có thể gửi forged identity headers. Do đó mTLS service identity, proxy hygiene, app account checks và monitoring vẫn cần.

## 9. NGINX: strip identity headers do client gửi

Proxy là nơi **chuyển đổi từ “HTTP request không đáng tin” thành “identity assertion nội bộ”**. Nó phải quyết định authentication **trước** khi tạo header.

Các header có nguy cơ:
- `X-Authenticated-User`
- `X-Forwarded-User`
- `Remote-User`
- `X-Remote-User`
- `X-Auth-Request-User`
- `X-User`
- `X-Authenticated-Groups` / `X-Role`
- `X-Forwarded-Client-Cert` nếu dùng service mesh/proxy
- `Authorization` nếu proxy terminate authentication và backend không được nhận raw bearer credentials
- Chuỗi `Forwarded`, `X-Forwarded-For/Host/Proto/Port/Prefix` mà client tự gửi.

**Không phải cứ xóa mọi `Authorization` trên mọi ứng dụng**: một API có thể cần bearer token để backend tự validate. Khi đó thiết kế **hai authentication paths riêng**, không nhập nhằng bearer auth và pre-auth header, và backend phải xác minh bearer token. Nếu proxy đã terminate auth, thường chỉ gửi assertion đã phê duyệt, không gửi credentials không cần.

### Mẫu NGINX có authentication subrequest

Mẫu minh họa có một dịch vụ nội bộ `auth-service` trả:
- **2xx** khi xác thực thành công, với response header `X-Verified-Principal</BT> được tạo từ identity store đã xác minh;
- **401/403** khi không thành công;
- Các status khác xử lý như lỗi upstream, không coi thành công.

~~~nginx
upstream portal_backend {
    server portal-backend.internal:8080;
}

server {
    listen 443 ssl;
    server_name portal.example.org;

    ssl_certificate     /etc/nginx/tls/portal.crt;
    ssl_certificate_key /etc/nginx/tls/portal.key;

    location = /_auth {
        internal;
        proxy_pass http://auth-service.internal:9000/verify;
        proxy_pass_request_body off;
        proxy_set_header Content-Length "";

        # Không cho client giả header danh tính tới auth service.
        proxy_set_header X-Authenticated-User "";
        proxy_set_header X-Verified-Principal "";

        proxy_set_header X-Original-URI $request_uri;
    }

    location / {
        auth_request /_auth;
        auth_request_set $verified_user
            $upstream_http_x_verified_principal;

        # Chỉ forward khi auth service đã cung cấp principal.
        if ($verified_user = "") { return 403; }

        proxy_set_header X-Authenticated-User $verified_user;

        # Các alias identity không được đi qua từ browser.
        proxy_set_header X-Forwarded-User "";
        proxy_set_header X-Remote-User "";
        proxy_set_header Remote-User "";
        proxy_set_header X-Auth-Request-User "";
        proxy_set_header X-User "";
        proxy_set_header X-Authenticated-Groups "";

        # Header metadata được ghi từ các giá trị proxy quản lý.
        proxy_set_header Forwarded "";
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-Host portal.example.org;
        proxy_set_header Host portal.example.org;

        proxy_pass http://portal_backend;
    }
}
~~~

**Mẫu này không phải cấu hình production đầy đủ**: paths/certificates/auth-service là giả định, TLS tới backend đang là HTTP qua mạng private, và auth service phải **thực sự authenticate** request và bảo vệ response header của nó. Nên dùng HTTPS/mTLS cho hop proxy→backend nếu có thể. NGINX `auth_request` đòi module tương ứng và auth service có contract chuẩn.

### Điều cần hiểu về NGINX

- `proxy_set_header X-Authenticated-User $verified_user` **ghi đè** cùng tên header khi gửi backend; `proxy_set_header Name ""` khiến header đó không được forward.
- NGINX forwarding behavior phải được kiểm tra trong **đúng location/server block**, vì `proxy_set_header` inheritance giữa các level có quy tắc riêng.
- `auth_request_set` lấy giá trị trả từ auth subrequest, **không** lấy `$http_x_authenticated_user` do client tự gửi.
- `if (...) { return 403; }` ở đây chỉ chặn trường hợp auth service trả 2xx nhưng không có principal; đây không phải phương thức xác thực thay auth_request.
- Nếu auth service trả `X-Verified-Principal` dựa trên user-supplied header hoặc cookie chưa được xác minh, proxy vẫn có lỗ hổng.
- Không dùng `proxy_set_header X-Authenticated-User $http_x_authenticated_user` vì như vậy chỉ chuyển tiếp dữ liệu attacker.
- Việc sanitize alias headers cần bao gồm **toàn bộ tên header mà backend/filters thực sự đọc**, không chỉ vài ví dụ trong snippet.
- Quy tắc HTTP header case-insensitive, duplicate headers và biến thể underscore/hyphen phải được kiểm thử qua cả NGINX, LB và container; có thể cần **reject duplicates** ở edge.
- Nếu có CDN/proxy bên ngoài, phải xác định nơi nào là trust boundary **đầu tiên** và strip headers trước khi authentication proxy xử lý.

### Auth service làm gì?

Một auth service đúng hợp đồng:
1. Tự kiểm tra session/OIDC tokens/SPNEGO context hoặc thông tin identity đáng tin;
2. Đánh giá token signature, issuer, audience, expiry, nonce/state/session khi protocol yêu cầu;
3. Kiểm tra status/revocation/quy tắc access ở proxy theo policy;
4. Trả 2xx cùng một principal canonical, không nhận principal từ browser;
5. Trả 401/403 khi chưa authenticated/không được phép;
6. Không trả 2xx với `X-Verified-Principal` giả hoặc trống;
7. Không cho một caller ngoài trusted proxy truy cập endpoint admin/debug để giả authentication response;
8. Có auditing, rate limiting và failure modes fail closed.

## 10. Forwarded headers: dùng được nhưng phải biết ai đã tạo chúng

Khi reverse proxy TLS-terminate rồi gọi app qua HTTP private, Spring có thể cần biết URL public để tạo redirects và SSO callback:

~~~text
Browser: https://portal.example.org/
Proxy -> app: http://portal-backend:8080/
Proxy adds:
  X-Forwarded-Proto: https
  X-Forwarded-Host: portal.example.org
~~~

Spring Boot hỗ trợ:

~~~yaml
server:
  forward-headers-strategy: native
~~~

Tùy container/version, `native` sử dụng khả năng của Tomcat/Jetty/Netty. Nếu cần Spring Framework filter, có thể chọn `framework`. Đối với app không tin hoặc không sử dụng forwarded headers, `none` hoặc `ForwardedHeaderFilter</BT> `removeOnly=true` có thể phù hợp.

**Điều kiện tiên quyết:** proxy ở ranh giới tin cậy phải loại header `Forwarded` và **tất cả** các biến thể `X-Forwarded-*</BT> do outside caller gửi, rồi ghi các giá trị mà chính nó xác định. Spring không thể tự biết header được tạo bởi proxy hay attacker. Đây là cảnh báo trực tiếp trong Spring Framework/Spring Security docs.

### Không sử dụng forwarded header để xác thực workload

`X-Forwarded-For: 10.42.1.5` không nói rằng TCP peer là auth-proxy. `X-Forwarded-Proto: https` cũng không chứng minh mTLS giữa proxy và backend đã xảy ra. Backend cần tin transport/workload identity qua cấu hình **network/TLS riêng**, không dùng các metadata headers làm chứng cứ.

### Nhiều proxy nối nhau

~~~text
Browser -> CDN -> LB -> Identity Proxy -> Spring
~~~

Cần chỉ rõ:
- Proxy nào được phép set client IP;
- Proxy nào được phép set **authenticated principal**;
- Proxy nào strip input của caller;
- Proxy nào thêm `Forwarded/X-Forwarded-*</BT>;
- Thứ tự xử lý/rewrite và `trusted proxies</BT> tại Tomcat/nginx;
- Không có hop nào vô tình forward user-supplied identity header;
- HTTP Host/Proto public được xác định từ allow-list thay vì untrusted `Host`.

Đừng gộp “chuỗi IP do client gửi” với “chứng chỉ workload của proxy”.

## 11. NGINX real_ip module không phải firewall

NGINX `ngx_http_realip_module` cho phép dùng `set_real_ip_from` để xác định những proxy peers mà header `X-Forwarded-For` được tin khi tái tạo client IP.

Ví dụ **chỉ khi NGINX thật sự nằm sau LB đáng tin**:

~~~nginx
set_real_ip_from 192.0.2.10;
real_ip_header X-Forwarded-For;
real_ip_recursive on;
~~~

Các địa chỉ ở đây chỉ minh họa. Nếu đặt `set_real_ip_from 0.0.0.0/0` hoặc một mạng quá rộng chứa clients không tin, attacker có thể điều khiển IP được log/được middleware dùng. Nên giới hạn chính xác LB/proxy peer addresses và kiểm tra `$realip_remote_addr` để điều tra original peer khi module chạy.

**Quan trọng:** cấu hình real-ip phục vụ diễn giải **client network address**, **không** tự cô lập backend và không xác thực `X-Authenticated-User`. Network firewall và mTLS identity vẫn là các biện pháp riêng.

## 12. mTLS: ràng buộc backend với proxy đã được phê duyệt

IP allow-list là một lớp tốt nhưng không luôn đủ:
- Proxy pod IP thay đổi theo deploy;
- Có NAT/load balancers;
- Một pod khác bị compromise hoặc được gắn nhãn sai;
- Một đường nội bộ khác cũng tới backend;
- Một service mesh có thể rewrite source IP.

Với **mutual TLS (mTLS)**:
1. Proxy gửi chứng thư client cho backend TLS endpoint.
2. Backend hoặc sidecar TLS stack xác minh chain, issuer trust anchor, **SAN/workload identity**, validity/revocation theo policy.
3. Chỉ proxy service identity trong allow-list được kết nối.
4. Backend đồng thời xác minh server certificate cho đúng backend identity khi thiết lập upstream TLS.
5. Identity header phải do proxy tạo sau authentication, được bảo vệ khỏi sửa trên hop.

**mTLS xác thực proxy, không tự xác thực end user.** Một proxy đã được TLS xác minh nhưng tạo sai user assertion vẫn có thể gây nhầm danh tính; vì vậy proxy auth/session policy và Spring business authorization vẫn cần.

### Cảnh báo X-Forwarded-Client-Cert (XFCC)

Trong một số service meshes/proxies, `XFCC</BT> mang metadata certificate qua HTTP. **Không tin XFCC do client tự gửi**; chỉ sử dụng khi mesh/edge đã **strip/overwrite**, kết nối tới app không thể bypass và upstream workload authenticated. Nếu có quyền truy cập trực tiếp backend, một header XFCC tự khai không chứng minh mTLS đã xảy ra.

### Khi proxy và app cùng host

Một Unix domain socket với quyền OS chặt có thể hạn chế process có thể gọi backend, nhưng vẫn cần bảo vệ identity headers/actor permissions. Đừng cho rằng mọi process trên host đều đáng tin. Nếu kết nối TCP loopback `127.0.0.1:8080`, kiểm tra local untrusted processes và admin debug tools.

## 13. Spring Security pre-auth: dùng đúng và hiểu giới hạn

Spring Security có các thành phần:

| Thành phần | Vai trò |
| --- | --- |
| `RequestHeaderAuthenticationFilter` | Đọc principal từ header do proxy tạo; **không xác minh header** |
| `PreAuthenticatedAuthenticationProvider` | Chuyển pre-auth token thành Authentication đã nạp UserDetails/authorities |
| `UserDetailsByNameServiceWrapper` | Adapter gọi `UserDetailsService` từ pre-auth token |
| `SecurityFilterChain` | Thực thi filter, route authorization, session policy |
| `Http403ForbiddenEntryPoint` | Entry point trả 403 khi không có cơ chế login khác |
| `SessionCreationPolicy.STATELESS` | Không duy trì security session theo cách stateful nếu chọn model per-request |
| `OncePerRequestFilter` | Có thể dùng làm guard khi có **trusted transport metadata** |
| `ForwardedHeaderFilter` | Xử lý/loại Forwarded metadata, **không phải bộ xác thực proxy** |

### 13.1 Đoạn cấu hình pre-auth quan trọng

Đây là **một lớp Java minh họa** dùng Spring Security 6.x+ và Boot 3.x. Nó **giả định** một `UserDetailsService` đã được ứng dụng triển khai để nạp account/authorities và một proxy→backend network/mTLS boundary đã thực thi độc lập.

~~~java
package com.example.portal;

import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.core.userdetails.UserDetailsByNameServiceWrapper;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.web.authentication.preauth.PreAuthenticatedAuthenticationProvider;
import org.springframework.security.web.authentication.preauth.PreAuthenticatedAuthenticationToken;
import org.springframework.security.web.authentication.preauth.RequestHeaderAuthenticationFilter;

@Configuration
public class ProxyPreauthConfig {

    @Bean
    AuthenticationManager proxyAuthManager(UserDetailsService users) {
        var wrapper =
                new UserDetailsByNameServiceWrapper<
                        PreAuthenticatedAuthenticationToken>();
        wrapper.setUserDetailsService(users);

        var provider = new PreAuthenticatedAuthenticationProvider();
        provider.setPreAuthenticatedUserDetailsService(wrapper);
        return new ProviderManager(provider);
    }

    @Bean
    RequestHeaderAuthenticationFilter proxyIdentityFilter(
            AuthenticationManager proxyAuthManager) {
        var filter = new RequestHeaderAuthenticationFilter();
        filter.setPrincipalRequestHeader("X-Authenticated-User");
        filter.setExceptionIfHeaderMissing(true);
        filter.setContinueFilterChainOnUnsuccessfulAuthentication(false);
        filter.setAuthenticationManager(proxyAuthManager);
        return filter;
    }

    @Bean
    FilterRegistrationBean<RequestHeaderAuthenticationFilter>
            disableProxyFilterOutsideSecurityChain(
                    RequestHeaderAuthenticationFilter proxyIdentityFilter) {
        var registration =
                new FilterRegistrationBean<>(proxyIdentityFilter);
        registration.setEnabled(false);
        return registration;
    }
}
~~~

**Đây chưa phải một Spring Boot app hoàn chỉnh**, không có `main()`, `UserDetailsService`, proxy transport verification hay một `SecurityFilterChain` gắn filter. Không có stdout. Mã yêu cầu Spring Security, Boot, Jakarta Servlet dependencies theo phiên bản; không chạy bằng `javac` trần.

Những điều đáng lưu ý:
- Header `X-Authenticated-User` **chỉ được xem là đáng tin nếu ranh giới network/mTLS và proxy sanitization đã an toàn**.
- `setExceptionIfHeaderMissing(true)` tránh chấp nhận request thiếu principal dưới cơ chế preauth; nhưng behavior HTTP cuối cùng còn phụ thuộc filter/entry point và exception handling.
- `setContinueFilterChainOnUnsuccessfulAuthentication(false)` ngăn việc provider failure âm thầm rơi tiếp sang cơ chế auth khác; vẫn phải có flow xử lý lỗi phù hợp.
- `setAuthenticationManager` dùng pre-auth provider để load UserDetails; **không tự xác minh username header**.
- `FilterRegistrationBean#setEnabled(false)` tránh Spring Boot tự chạy filter như một Servlet Filter **ngoài** SecurityFilterChain nếu filter bean được tự nhận diện; filter phải được đưa **có chủ đích** vào security chain.
- Nếu Spring dùng session persistence, filter có thể không chạy pre-auth mỗi request khi `SecurityContext` đã có. Cần xác định session/revocation semantics, không nghĩ missing header trong request sau đã tự revoke mọi session.

### 13.2 Gắn filter vào SecurityFilterChain

Mảnh cấu hình Spring Security Servlet:

~~~java
@Bean
SecurityFilterChain webSecurity(
        HttpSecurity http,
        RequestHeaderAuthenticationFilter proxyIdentityFilter)
        throws Exception {
    return http
            .authorizeHttpRequests(auth -> auth
                    .requestMatchers("/health/live").permitAll()
                    .requestMatchers("/admin/**").hasAuthority("PORTAL_ADMIN")
                    .anyRequest().authenticated())
            .sessionManagement(session -> session
                    .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .addFilterBefore(proxyIdentityFilter,
                    UsernamePasswordAuthenticationFilter.class)
            .build();
}
~~~

**Đây là snippet thêm trong lớp `@Configuration`**, cần imports `@Bean`, `HttpSecurity`, `SecurityFilterChain`, `SessionCreationPolicy` và `UsernamePasswordAuthenticationFilter`. Endpoint health có thể trả `permitAll` ở app nhưng **network layer vẫn phải chặn nguồn ngoài**; `permitAll` không có nghĩa public Internet có quyền gọi trực tiếp backend.

Lựa chọn `STATELESS` ở đây giúp mỗi request pre-auth phải dựa vào header mới, nhưng:
- Không thích hợp cho mọi app cần HttpSession/CSRF/session features; phải chọn session model theo nghiệp vụ.
- Nếu dùng session, cần kiểm soát lifetime, principal-change detection và invalidate session khi header/identity thay đổi.
- Không dùng đồng thời form login/basic auth fallback theo cách làm mất giả định “mọi request đã qua proxy”.
- Nên cấu hình explicit `AuthenticationEntryPoint` và failure status cho app/API, không suy error 403 từ fragment nếu chưa test.
- Nếu có một security chain khác, bảo đảm nó không vô tình cho phép request mà không kiểm proxy trust.

**Tại sao không viết `.permitAll()</BT> cho mọi endpoint?** Vì user name trong pre-auth header chỉ là authentication input; mỗi route/object vẫn phải có authorization.

## 14. Network guard trong Spring có thay firewall không?

**Không.** Một `OncePerRequestFilter` có thể kiểm tra raw peer/mTLS identity như **defense in depth**; nhưng:
- Một exception handling/filter order bug có thể làm guard không áp trên error/async dispatch;
- Spring container có thể rewrite `getRemoteAddr()</BT> dựa trên forwarded headers;
- Nếu guard chỉ đọc IP từ header thì dễ bị giả;
- Có thể tồn tại endpoint management trên port khác không đi qua guard;
- Một JVM bị compromise không được firewall/network isolation bảo vệ nội bộ.

Nên dùng network access control **ngoài tiến trình** là lớp cưỡng chế đầu tiên. Trong app, kiểm tra transport identity từ connector/mesh metadata được bảo đảm integrity mới có giá trị.

### Điều kiện với Servlet getRemoteAddr()

Nếu Tomcat RemoteIpValve hoặc Spring ForwardedHeaderFilter đang hoạt động, `request.getRemoteAddr()</BT> có thể được điều chỉnh thành **client IP gốc**, không phải raw socket peer. Không lấy điều đó để allow-list proxies. Với guard thực, nên dùng:
- Network sidecar/service mesh authorization dựa trên authenticated peer identity;
- L4 firewall/security group;
- Raw socket peer metadata do một trusted connector cung cấp và **không bị user-controlled forwarded headers thay đổi**;
- mTLS certificate chain/SAN verified tại TLS terminator.

Một guard nhận `X-Proxy-Verified: true` qua HTTP header **vẫn không chứng minh peer trusted** nếu backend có đường vào khác.

## 15. Java 17 độc lập: mô phỏng điều kiện nhận identity header

Chương trình dưới đây chỉ dùng **Java Standard Library**, không cần Spring/Kubernetes/NGINX. Nó thể hiện một nguyên tắc:

> Chỉ xem header danh tính là **đầu vào được phép chuyển sang account mapping** khi request đến từ proxy peer được cấu hình, peer **đã được xác minh mTLS bởi tầng transport** và header danh tính hợp lệ.

Nó **không tự xác thực certificate, không mở TCP server, không cấp Authentication và không thay network firewall**. Tham số `peerMtlsVerified` mô phỏng kết quả mà **TLS stack thực tế** phải cung cấp; trong production **tuyệt đối không nhận boolean này từ JSON/query/header của client**.

Tệp `TrustedProxyBoundaryDemo.java`:

~~~java
import java.util.Set;

public final class TrustedProxyBoundaryDemo {

    record Request(
            String rawSocketPeer,
            boolean peerMtlsVerified,
            String assertedUser,
            String claimedForwardedFor) {
    }

    private static final Set<String> APPROVED_PEERS =
            Set.of("10.42.7.10", "10.42.7.11");

    static String evaluate(Request request) {
        if (!APPROVED_PEERS.contains(request.rawSocketPeer())) {
            return "DENY_UNTRUSTED_PEER";
        }
        if (!request.peerMtlsVerified()) {
            return "DENY_UNVERIFIED_PROXY";
        }
        String principal = request.assertedUser();
        if (principal == null || principal.isBlank()) {
            return "DENY_MISSING_IDENTITY";
        }
        if (!principal.matches(
                "[a-z0-9._-]{1,64}@example[.]org")) {
            return "DENY_INVALID_IDENTITY";
        }

        // Intentionally do NOT use claimedForwardedFor.
        // Policy approval is not yet application authentication.
        return "ALLOW_FOR_USER_MAPPING";
    }

    public static void main(String[] args) {
        Request normal = new Request(
                "10.42.7.10", true,
                "linh@example.org", "203.0.113.7");

        Request direct = new Request(
                "198.51.100.33", false,
                "admin@example.org", "10.42.7.10");

        Request siblingPod = new Request(
                "10.42.8.15", false,
                "admin@example.org", "10.42.7.10");

        Request fakeProxy = new Request(
                "10.42.7.11", false,
                "admin@example.org", "203.0.113.7");

        Request missingUser = new Request(
                "10.42.7.10", true, "", "203.0.113.7");

        Request malformed = new Request(
                "10.42.7.10", true,
                "admin\r\nX-Role: superuser", "203.0.113.7");

        Request forgedClientIp = new Request(
                "10.42.7.10", true,
                "linh@example.org", "127.0.0.1");

        System.out.println("Normal: " + evaluate(normal));
        System.out.println("Direct: " + evaluate(direct));
        System.out.println("Sibling pod: " + evaluate(siblingPod));
        System.out.println("No mTLS: " + evaluate(fakeProxy));
        System.out.println("No user: " + evaluate(missingUser));
        System.out.println("Malformed: " + evaluate(malformed));
        System.out.println("Forged XFF only: "
                + evaluate(forgedClientIp));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac TrustedProxyBoundaryDemo.java
java TrustedProxyBoundaryDemo
~~~

Stdout **chính xác**:

~~~text
Normal: ALLOW_FOR_USER_MAPPING
Direct: DENY_UNTRUSTED_PEER
Sibling pod: DENY_UNTRUSTED_PEER
No mTLS: DENY_UNVERIFIED_PROXY
No user: DENY_MISSING_IDENTITY
Malformed: DENY_INVALID_IDENTITY
Forged XFF only: ALLOW_FOR_USER_MAPPING
~~~

### Vì sao trường hợp “Forged XFF only” vẫn ALLOW?

Bởi vì chương trình **không dựa vào `X-Forwarded-For` để xác thực proxy**. Trong case đó raw peer vẫn là proxy được phê duyệt và mTLS đã được xác minh; việc giả IP client trong metadata **không tự chuyển thành danh tính khác**. Nếu một ứng dụng dùng XFF để quyết định user có được cấp quyền, đó là sai mô hình. Trong production, proxy cũng phải **strip/overwrite XFF** để client IP logs/rate limits đáng tin, nhưng nó là **cơ chế riêng** với identity authentication.

### Các giới hạn quan trọng

- `APPROVED_PEERS` là tập IP giả, không phải cơ chế quản trị IP động trong production; Kubernetes NetworkPolicy/mesh service identity thường phù hợp hơn.
- `rawSocketPeer` phải được lấy từ tầng transport tin cậy, không từ `request.getRemoteAddr()` đã bị forwarded-header middleware rewrite.
- `peerMtlsVerified` phải là kết quả **TLS peer certificate verification**, không phải header/boolean do caller tự gửi.
- Regex principal chỉ kiểm tra hình thức; backend còn phải **load account, check enabled/tenant/authorities**.
- `ALLOW_FOR_USER_MAPPING` **không** tương đương cho phép business action, không cấp token hoặc quyền admin.
- Không lưu HTTP identity header vào session lâu dài nếu principal/account có thể đổi.
- Ví dụ chỉ là bài tập Java 17 chạy độc lập; không nên copy như authorization bypass trong app thật.

## 16. Phòng header spoofing và duplicate headers

HTTP header names không phân biệt hoa/thường. Tùy proxy/container, tên có dấu gạch ngang/underscore hoặc các header trùng nhau có thể được chuẩn hóa khác nhau.

Ví dụ các biến thể nguy cơ:

~~~http
X-Authenticated-User: alice
x-authenticated-user: admin
X_Authenticated_User: other
X-Forwarded-User: privileged
Remote-User: owner
~~~

Điều gì xảy ra nếu:
- Edge chỉ strip chữ hoa `X-Authenticated-User` nhưng không strip alias?
- NGINX pass duplicate header còn Tomcat `getHeader()</BT> chọn một giá trị khác?
- Một middleware đọc `X_Authenticated_User` thay vì header canonical?
- App có filter A đọc `SM_USER` nhưng auth proxy chỉ overwrite `X-Authenticated-User`?
- Một API route khác dùng `Authorization: Basic` fallback và bỏ qua proxy?
- XFCC bị client giả nhưng service mesh không strip?

Biện pháp:
1. Lập danh mục **tất cả** header danh tính mà mọi app/filter đọc.
2. Strip/overwrite ở edge **bất kể chữ hoa/thường**.
3. Reject duplicate/ambiguous identity headers nếu proxy hỗ trợ.
4. Không đọc header alias bổ sung khi không cần.
5. Chọn **một canonical assertion** do proxy tạo và một grammar principal được quản lý.
6. Có thể dùng signed short-lived assertion với issuer/audience/time, nhưng **nó chỉ có ích nếu app xác minh chữ ký và proxy keys thực sự an toàn**.
7. Kiểm thử thực tế qua đầy đủ CDN→ingress→proxy→app, vì các hop có thể normalize header khác nhau.
8. Không dùng `Host` hoặc `X-Forwarded-Host` tự do làm trusted identity namespace/tenant.
9. Dùng account ID có issuer/tenant scope, không tự động cấp admin dựa trên username.
10. Nếu ứng dụng có trusted original client IP, giữ nó cho logging/rate limits, không dùng thay principal.

### Không “ghi đè sau cùng” nếu có một đường bypass

Ngay cả khi NGINX đã strip headers đúng, điều đó chỉ bảo vệ **request đi qua NGINX**. Một request gửi thẳng backend sẽ **không** đi qua NGINX. Vì thế network isolation/mTLS là phần không thể thiếu của thiết kế.

## 17. Pre-authentication với một signed identity assertion

Header chứa username thuần dựa vào trust của proxy và kênh vận chuyển. Khi nhiều thành phần cùng tham gia hoặc có rủi ro compromise middleboxes, có thể thiết kế một **assertion có chữ ký** cho backend:

~~~json
{
  "iss": "https://identity-proxy.example.org",
  "aud": "portal-backend",
  "sub": "opaque-user-42",
  "iat": 1794000000,
  "exp": 1794000060,
  "scope": "portal.read",
  "tenant": "finance"
}
~~~

Đây chỉ là **ví dụ claim body**, không phải JWT hợp lệ (thiếu JWS header/signature). Nếu chọn JWT:
- Backend phải xác minh **JWS signature**, algorithms allow-list, keys/rotation và `iss/aud/exp/nbf/iat`.
- Assertion phải **ngắn hạn**, không chứa thông tin quá mức, có issuer chính xác và audience riêng cho backend.
- Thực thi policy chống replay/session binding theo nhu cầu, không chỉ kiểm chữ ký.
- Proxy phải tự phát dựa trên identity xác minh, không ký lại username do client khai.
- Backend nên xác minh **workload mTLS của proxy** ngay cả khi assertion có chữ ký nếu mục tiêu là không cho đường direct.
- Một JWT có chữ ký **không tự chặn trực tiếp backend** nếu token bị lộ hoặc backend có cơ chế fallback không kiểm token.
- Backend authorization vẫn áp theo resource, không dựa hoàn toàn vào claims quyền chưa được phê duyệt.

Trong Spring, giải pháp này có thể dùng **Resource Server JWT** thay vì `RequestHeaderAuthenticationFilter`, nhưng đây là một **kiến trúc xác thực khác**, cần token contract rõ và không tự bật chỉ bằng đổi tên header.

## 18. Session và đổi danh tính qua proxy

Một ứng dụng proxy pre-auth có thể dùng session hoặc không:

### Stateless per-request

- Mỗi request có assertion do proxy cung cấp;
- Spring không dựa vào phiên cũ để bỏ qua kiểm tra identity mới;
- Phù hợp API nếu performance/UX cho phép;
- Vẫn phải kiểm tra current account status/authorization;
- Cần CSP/CSRF/headers/cache controls tương ứng endpoint.

### Stateful HttpSession

- Spring lưu Authentication sau pre-auth lần đầu;
- Những request sau có thể được xử lý bằng session dù header thiếu/đã đổi nếu config/filter không kiểm principal changes;
- Nếu user log out khỏi identity proxy nhưng app session chưa bị revoke, user có thể còn local session;
- Phải kiểm soát session TTL, identity change, `setCheckForPrincipalChanges(true)` và invalidation nếu phù hợp;
- Các dữ liệu như group/role có thể stale sau thay đổi IAM;
- Khi nhiều tabs/users dùng chung browser, tránh nhầm principal.

**Không coi “proxy sẽ luôn gửi đúng header” là giải pháp thu hồi phiên.** Dùng session invalidation, SSO logout events, live authorization hoặc yêu cầu assertion mới mỗi request theo SLA.

### Những route dễ bị bỏ qua

Kiểm thử:
- `/api/**` khác `/web/**`;
- `/actuator/**`, `/management/**`;
- `/error`, `/forward`, `/async`;
- WebSocket upgrade endpoint;
- gRPC/HTTP/2 gateway route;
- File upload/status callback;
- Static admin console;
- Scheduled-job HTTP hooks;
- Legacy servlet mapping;
- Sidecar health endpoints.

Nếu một endpoint backend phục vụ external webhook, nên cho nó một **kênh/port/service authentication riêng** với HMAC/mTLS/token validation, thay vì mở toàn bộ backend để nhận webhook và làm mất proxy-only invariant.

## 19. Luồng có nhiều authentication mechanisms

Giả sử Spring app vừa có:
- Header preauth cho web SSO;
- Basic auth cho script cũ;
- API key trên `/internal/**`;
- OIDC token trên `/api/**`.

Đây là tình huống cần **định tuyến security chains rõ ràng**, không để fallback bất ngờ:
- Web pre-auth endpoints chỉ nhận request qua proxy và assertion đã xác minh.
- API cần bearer token phải có issuer/audience/token validation riêng.
- Internal admin endpoints có mTLS/workload identity và network scopes riêng.
- Script batch cần service account với quyền hẹp; không reuse endpoint admin user.
- Không cho `RequestHeaderAuthenticationFilter` đọc identity header trên những request API đã được xác thực khác với account mapping không tương thích.
- Không để `formLogin()` hoặc `httpBasic()` mở một đường login trực tiếp không qua SSO nếu kiến trúc yêu cầu exclusively proxy-auth.
- Nếu có nhiều `SecurityFilterChain`, kiểm tra matcher order và một catch-all chain bảo vệ mọi request còn lại.

Spring Security documentation cảnh báo đặc biệt việc dùng RequestHeaderAuthenticationFilter không phù hợp với những cơ chế login thay thế có thể bypass hệ xác thực external. Điều này không có nghĩa không bao giờ hỗ trợ nhiều mechanism, mà cần **tách các path/trust model** chính xác và test negative cases.

## 20. Đối chiếu biện pháp và các đường vượt qua

| Lỗi kiến trúc | Vì sao nguy hiểm | Biện pháp mạnh |
| --- | --- | --- |
| Backend có public IP:8080 | Client bỏ qua proxy | Private subnet/service + SG/firewall deny |
| Backend chỉ dùng ClusterIP | Pod nội bộ vẫn truy cập được | NetworkPolicy + mTLS workload identity |
| NetworkPolicy cho mọi namespace | Bất kỳ workload nội bộ có thể forge header | Exact namespace+pod selectors và bảo vệ labels |
| Proxy chỉ strip X-User, app đọc SM_USER | Vẫn có header identity bypass | Catalog mọi auth headers, strip all aliases |
| App trust X-Forwarded-For như source IP | Caller có thể tự khai proxy IP | Transport peer/network ACL, mTLS |
| Proxy pass `$http_x_authenticated_user` | Header đến từ browser | Use verified auth-service output only |
| App có httpBasic fallback không mong muốn | Bỏ proxy identity policy | Security chain riêng, deny unwanted mechanism |
| Actuator management trên public port | Bỏ route edge/có endpoint nhạy cảm | Private port + dedicated auth/authorization |
| Spring session giữ principal cũ | Proxy logout không revoke app session | Stateless hoặc session revocation/principal change |
| XFCC client-supplied | Fake mTLS identity | Mesh strip/overwrite, verified peer cert |
| IPv6 public listener ngoài firewall IPv4 | Bỏ policy IPv4 | Dual-stack network policy/test |
| kubectl port-forward không kiểm RBAC | Admin/API path có thể truy cập backend | Kubernetes RBAC/admission/audit |
| Proxy outage, app cho direct fallback | Mất ranh giới xác thực | Fail closed; availability plan không mở backend |
| Proxy workload compromise | Attacker có thể phát header | mTLS + hardened proxy, signing, least privilege và detection |

**Đánh giá các biện pháp như một chuỗi:** nếu backend reachable trực tiếp thì sanitize tại proxy không đủ. Nếu mạng chặn direct nhưng proxy cho phép client ghi header thì không đủ. Nếu proxy sạch nhưng app cho phép quyền admin dựa trên username chưa được map, vẫn chưa đủ.

## 21. Kiểm thử âm tính bắt buộc

### Test A — Happy path qua proxy

1. Truy cập public hostname theo HTTPS.
2. Proxy yêu cầu login SSO nếu chưa có phiên.
3. Sau xác thực, proxy ghi một principal canonical, ví dụ user@realm, từ identity store đã tin.
4. App kiểm tra local account enabled/tenant/authority và chỉ trả resource được phép.
5. Log ở app ghi source service alias/trace ID, không ghi cookies/raw SSO token.
6. Nếu cần, kiểm tra mTLS peer proxy identity đã được TLS stack xác minh.

**Pass:** user login đúng và không cần client tự cung cấp identity header.

### Test B — Browser tự đặt header danh tính

1. Từ test client được phép, gửi request vào public hostname với `X-Authenticated-User` giả.
2. Proxy strip/overwrite header trước backend.
3. Không xuất hiện principal do client tự khai.
4. User chưa đăng nhập nhận login/401/403 theo contract.
5. User đã đăng nhập nhận chính identity do proxy xác minh, không phải header giả.

### Test C — Direct backend port từ nơi không tin

1. Từ pod/host ngoài proxy allow-list, thử kết nối backend private IP/service ở môi trường test.
2. Lớp network policy/firewall phải chặn truy cập **trước** HTTP application.
3. Đừng chỉ kiểm `curl</BT> trả 403: 403 chứng tỏ app đã nhận request; network isolation nên ngăn kết nối khi yêu cầu proxy-only.
4. Nếu mTLS cho phép tới TLS endpoint nhưng không có client cert, handshake phải fail hoặc reverse proxy phải từ chối trước Spring.
5. Ghi lại nguồn, port, network policy và kết quả thực tế.

### Test D — Sibling pod cùng namespace

1. Tạo pod test không có label identity-proxy trong cùng namespace.
2. Test TCP đến backend 8080.
3. Phải bị chặn bởi NetworkPolicy chọn backend.
4. Lặp từ namespace khác.
5. Kiểm soát quyền đổi namespace/pod labels bằng RBAC/admission.

### Test E — X-Forwarded-For spoofing

1. Gửi request qua public proxy với `X-Forwarded-For: 127.0.0.1` hoặc IP proxy giả.
2. Edge strip/overwrite theo policy.
3. App không coi request là từ proxy chỉ nhờ XFF.
4. Client IP logs/rate limit dùng chuỗi trusted hops đã xác định.
5. Không có bypass từ `Forwarded: for=...</BT> hay `X-Real-IP`.

### Test F — Alternate ingress/NodePort

1. Liệt kê những Services, Ingress, LoadBalancers, hostPorts, hostNetwork, management ports có thể đến backend.
2. Kiểm tra đường trực tiếp qua từng endpoint test.
3. Các đường không được duyệt phải deny.
4. Không bỏ sót IPv6/dual-stack và ingress DR.
5. Trình bày inventory được duyệt cho Prime/security owner, không chỉ test một URL public.

### Test G — Authentication proxy outage

1. Làm auth-service test trả 503 hoặc timeout.
2. Proxy phải **fail closed**, không forward anonymous request cùng header do caller tự khai.
3. Backend không mở public fallback vì “tạm thời cho người dùng vào”.
4. User nhận error có thể hành động; monitoring phát cảnh báo.
5. Với các API service-specific, fallback được phép chỉ khi có independent strong authentication được định nghĩa trước.

### Test H — Principal header thiếu/giả/multi-value

1. Proxy auth-service trả 2xx nhưng thiếu header principal → deny.
2. Header trống/whitespace hoặc chứa newline/control chars → deny.
3. Các alias `SM_USER`, `Remote-User`, duplicate header → không thể chọn user khác.
4. Không có tình huống user chưa xác thực lại được mapping tới admin.
5. Theo dõi error type không log giá trị raw header nhạy cảm.

### Test I — Session/logout

1. User A login qua proxy, tạo session nếu app stateful.
2. Logout identity proxy hoặc đổi user tại proxy.
3. App không được tiếp tục xử lý như user A khi yêu cầu phiên mới có policy revoke/principal change.
4. Nếu session A còn theo thiết kế, kiểm tra SLA revocation và live authorization.
5. Test nhiều tab, nhiều node và HTTP/2 keep-alive.

### Test J — User không có quyền tài nguyên

1. Proxy xác thực user hợp lệ và chuyển assertion đúng.
2. Spring tạo Authentication.
3. Route/tài nguyên thuộc tenant khác hoặc yêu cầu quyền khác bị từ chối.
4. Backend không coi “đã đi qua proxy” là quyền gọi mọi business method.
5. Phân biệt authn failure (401/403 theo entry point) với authorization 403.

## 22. Kubernetes: còn lối đi ngoài HTTP không?

Một hệ thống Kubernetes có thể có:
- API server điều khiển `kubectl port-forward`;
- Ingress controller trên node;
- Sidecars truy cập localhost trong pod;
- HostNetwork daemonsets;
- Metrics scraper;
- Service mesh inbound listener;
- CronJobs chạy trong cluster;
- Shared debugging namespaces và CI runners.

Vì vậy chỉ nói “đã dùng NetworkPolicy” chưa đủ. Quy trình:
1. Inventory các pod/labels/namespace và service ports được chọn.
2. Audit RBAC ai có thể `pods/portforward`, `exec`, `patch pod labels` hoặc tạo privileged pod.
3. Cấu hình admission restrictions cho workloads nhạy cảm.
4. Kiểm tra CNI policy enforcement thực tế và hostNetwork exceptions.
5. Tách liveness/readiness endpoints khỏi admin endpoints, không mở allow-all.
6. Hạn chế debug ingress với port 8080 và IPv6.
7. Dùng network packet-level telemetry/mTLS identity để xác minh chỉ proxy connections hợp lệ.
8. Khi một team khác triển khai ingress mới, đòi hỏi security review vì có thể tạo path bypass.

**kubectl port-forward là một thao tác qua Kubernetes API được cấp quyền**, không phải public HTTP. Một developer có quyền port-forward có thể tiếp cận backend qua path mà NetworkPolicy pod-to-pod không nhất thiết kiểm soát. Đây là lý do cần RBAC/admission/audit, không phải lý do bỏ NetworkPolicy.

## 23. TLS termination và Host/redirect poisoning

Proxy terminate TLS trên `https://portal.example.org`, backend nhận HTTP private. Nếu Spring tự dùng `Host` hoặc `X-Forwarded-Host` chưa sanitize để tạo absolute URL:
- Có thể tạo redirect tới domain do caller tự khai;
- OAuth2/SAML callback URL có thể sai;
- Cookie domain/scheme có thể không đúng;
- Link trong email/reset/SSO có thể bị đầu độc;
- Logs có thể ghi client IP giả.

Cách xử lý:
- Public host allow-list cố định trên proxy.
- Proxy strip/overwrite forwarded host/proto/port;
- Spring Boot `server.forward-headers-strategy` chỉ bật sau edge hygiene.
- Kiểm tra trusted proxy ranges ở Tomcat/NGINX real-IP configurations.
- Dùng trusted public base URL cho những redirect nhạy cảm.
- Không coi `X-Forwarded-Proto=https` thay bằng TLS thật trên nội bộ.
- Cookies `Secure/HttpOnly/SameSite` theo flow thực tế.
- Kiểm soát open redirect cho return-to URL.

Nếu có nhiều proxies, cần thiết lập một **quy ước chính thức về header provenance**, không để CDN và ingress tự nối nhiều giá trị rồi app đoán.

## 24. Vận hành: phát hiện đường truy cập trực tiếp

Một số dấu hiệu:
- Backend nhận traffic có socket peer không nằm trong danh sách proxy workloads.
- Header danh tính xuất hiện trong request mà peer không có mTLS.
- Tăng số `PreAuthenticatedCredentialsNotFoundException` hoặc authn failures ở backend.
- Pod backend bị reach từ namespace lạ.
- Request trực tiếp tới cổng management/8080.
- User login ngoài proxy nhưng app có Authentication được tạo.
- Header alias/duplicate xuất hiện thường xuyên.
- Đường ingress mới trỏ cùng service nhưng không gắn auth filter.
- Một deployment service của backend có thêm `type: LoadBalancer` hoặc NodePort ngoài dự kiến.

### Log an toàn

Một event mẫu:

~~~json
{
  "event": "proxy_boundary_request_denied",
  "traceId": "req-opaque-001",
  "backend": "portal-api",
  "peerWorkload": "unknown",
  "trustDecision": "UNVERIFIED_SOURCE",
  "pathGroup": "business",
  "result": "DENY"
}
~~~

Đây là **dữ liệu minh họa**, không phải response của Spring Security. Không ghi raw identity token, user cookie, OIDC ID Token, Kerberos AP-REQ, client certificate private key hoặc toàn bộ forwarded headers.

Các metric gợi ý:
- `proxy_handoff_received_total{source="verified-proxy"}`
- `proxy_handoff_denied_total{reason="untrusted-peer"}`
- `proxy_handoff_denied_total{reason="missing-identity"}`
- `proxy_auth_service_error_total`
- `backend_network_policy_denied_total` nếu CNI/flow logs có
- `unexpected_direct_connection_total` nếu network telemetry có
- `preauth_user_mapping_failure_total`
- `proxy_principal_change_total` khi app stateful

Không dùng principal email hoặc raw client IP chứa dữ liệu nhạy cảm làm metric labels có cardinality lớn. Cần bảo vệ log, retention, dashboards và phân quyền người truy cập.

## 25. Chẩn đoán một số sự cố

| Triệu chứng | Nguyên nhân khả dĩ | Cách kiểm tra |
| --- | --- | --- |
| Spring không thấy principal dù proxy login thành công | Proxy thiếu header, NGINX auth_request_set sai, header bị strip ở hop sau | Xem contract auth-service và backend trace redacted |
| Proxy auth fail nhưng app vẫn trả 200 | Pre-auth bypass, route permitAll, fallback session/basic, alternate ingress | Kiểm tra SecurityFilterChain matchers và network paths |
| Direct backend 8080 reachable | SG/firewall/NetworkPolicy chưa enforce, NodePort, hostNetwork | Kiểm tra TCP reachability từ source không tin |
| Bị 403 mọi request sau áp NetworkPolicy | Proxy pods/namespace labels sai, port mismatch, health blocked | CNI flow logs, selectors, listener ports |
| Backend có identity từ header browser | Edge forward header nguyên bản, không overwrite | Chụp redacted proxy request/response trên lab |
| Wrong original URL trong OIDC redirect | Forwarded headers không đúng trusted proxy path | Public host/proto, Boot forwarded strategy |
| IP audit toàn là LB | Chưa cấu hình real-IP trusted peers hoặc XFF overwrite | Proxy chain, realip_module, Tomcat RemoteIpValve |
| IP audit do caller tự chọn | Proxy tin XFF từ client | Strip all forwarded headers at first trusted edge |
| Session user A tồn tại khi proxy đã logout | Session policy/revocation/principal-change chưa khớp | Stateless vs stateful, expiration/SLO |
| Backend API có 403 dù user valid | App/object authorization, tenant/roles | Kiểm tra ACL không nới proxy whitelist |
| Pod khác có thể gắn label proxy | RBAC/admission quá rộng | Review namespace and label permissions |
| mTLS handshake fail giữa proxy/backend | Certificate/SAN/trust anchor hoặc mesh config sai | Kiểm tra workload identity, không tắt verification |
| API bearer token bị từ chối sau bật preauth | Authentication chains bị trộn | Tách endpoints và issuer/audience contracts |
| Duplicate identity headers | Header normalization/alias handling | Reject/strip, cập nhật proxy config |
| Spring filter chạy hai lần | Boot Servlet auto-registration + SecurityFilterChain | FilterRegistrationBean disable hoặc một registration path |
| Management port public | Actuator config/SG/ingress phụ | Cô lập management endpoints và kiểm tra riêng |

**Không “chữa” bằng `server.forward-headers-strategy=framework` nếu gốc là direct backend exposure.** Forwarded handling là vấn đề URL/client metadata, không phải network isolation.

## 26. Thực hành đánh giá cấu hình trước–sau

### Trước khi hardening

~~~text
Internet --> Identity Proxy --> Spring backend:8080
                    |
                    +--> đặt X-Authenticated-User

Internet -------------------> Spring backend:8080 (public IP còn mở)
Client tự đặt X-Authenticated-User: admin@example.org
Spring RequestHeaderAuthenticationFilter đọc header.
~~~

Ở đây, proxy đã làm đúng ở đường public chính, nhưng backend **có đường mạng trực tiếp**. Framework pre-auth không thể kiểm chứng xuất xứ header, dẫn tới identity spoofing.

### Sau khi hardening

~~~text
Internet --> Trusted Identity Proxy --> [mTLS] --> Spring backend
                 |
                 +-- Authenticating end user
                 +-- Strips caller identity and forwarded headers
                 +-- Creates verified canonical principal

Non-proxy traffic --> Denied at network/firewall policy
Backend:
  - verifies proxy workload boundary
  - reads only sanitized identity assertion
  - loads user/account state
  - enforces authorization per resource
~~~

**Kết quả kỳ vọng:** request bypass không mở được kết nối/tạo Authentication; request qua proxy chưa xác thực không chuyển identity; request qua proxy hợp lệ được map đúng user nhưng vẫn bị giới hạn business roles và ACL.

## 27. Câu hỏi tự kiểm tra có đáp án

**Câu 1.** Spring Security RequestHeaderAuthenticationFilter có tự xác thực `X-Authenticated-User` không?

**Đáp án:** không. Nó chỉ lấy username làm input pre-auth; trust nằm ở external system và network/proxy protections.

**Câu 2.** Proxy đã strip header đúng, backend vẫn có public IP. Đã an toàn chưa?

**Đáp án:** chưa. Caller có thể bypass proxy và gửi header trực tiếp. Cần network isolation và backend peer verification.

**Câu 3.** `X-Forwarded-For: 10.42.7.10` có chứng minh request đến từ proxy IP 10.42.7.10 không?

**Đáp án:** không. Header có thể được caller tạo. Chỉ tin XFF từ đúng hop proxy đã xác minh và strip/overwrite đầu vào.

**Câu 4.** Spring app cần URL public HTTPS dù proxy→app HTTP. Cơ chế nào xử lý và điều kiện?

**Đáp án:** Boot forwarded-header strategy/ForwardedHeaderFilter hoặc container equivalent, **sau** khi edge strip/overwrite Forwarded và X-Forwarded-*.

**Câu 5.** `ClusterIP` có tự chặn mọi pod nội bộ gọi backend không?

**Đáp án:** không. Thường cần Kubernetes NetworkPolicy và CNI enforcement, cùng mTLS khi cần.

**Câu 6.** Một NetworkPolicy có namespaceSelector và podSelector nằm ở hai phần tử `from` riêng. Có giống đặt trong cùng phần tử không?

**Đáp án:** không. Hai phần tử có nghĩa OR; đặt trong cùng phần tử để kết hợp namespace và pod selection.

**Câu 7.** Kubernetes NetworkPolicy có kiểm soát mọi người có quyền `kubectl port-forward` không?

**Đáp án:** không bảo đảm. Port-forward qua Kubernetes API cần RBAC/admission/audit riêng.

**Câu 8.** Proxy trả 2xx cho auth_request nhưng không có identity header. Nên làm gì?

**Đáp án:** deny/fail closed; không tự chọn anonymous/username do browser gửi thay thế.

**Câu 9.** NGINX dùng `proxy_set_header X-Authenticated-User $http_x_authenticated_user`. Vấn đề?

**Đáp án:** đó là giá trị incoming từ browser, không phải principal từ verified auth context. Phải dùng output từ identity/auth service đáng tin.

**Câu 10.** mTLS proxy→backend có thay user authentication không?

**Đáp án:** không. Nó xác thực workload peer, còn proxy phải xác thực end user và backend phải authorize.

**Câu 11.** Backend thấy XFCC có client cert subject; có thể mặc định tin subject đó không?

**Đáp án:** không. Cần mesh/edge sanitize XFCC và authenticated hop, hoặc dùng certificate trực tiếp đã xác minh ở TLS stack.

**Câu 12.** Vì sao port actuator cần kiểm tra độc lập?

**Đáp án:** nó có thể được expose ở management port/ingress khác, bỏ qua auth proxy nếu không giới hạn network/auth.

**Câu 13.** Sau proxy logout, Spring session vẫn authenticated. Lỗi do XFF không?

**Đáp án:** thường là session/revocation model khác. Cần per-request preauth hoặc session invalidation/principal-change policy, không suy là lỗi XFF.

**Câu 14.** Nếu app có API token auth và pre-auth header, phải tắt một trong hai không?

**Đáp án:** không nhất thiết, nhưng cần security chains/trust boundaries riêng, đúng issuer/audience, không fallback bypass SSO.

**Câu 15.** Vì sao không xem private 10.0.0.0/8 là trusted proxy network?

**Đáp án:** nhiều workloads nội bộ khác có thể ở đó. Chỉ allow chính xác proxy peers/workload identities được phê duyệt.

**Câu 16.** TLS public vào edge có bảo vệ HTTP backend khỏi attacker trong cùng cluster không?

**Đáp án:** không. Cần private network isolation và, khi thích hợp, mTLS proxy→backend.

**Câu 17.** Chứng chỉ proxy mTLS đúng nhưng header user=admin do auth service tự khai từ query user. Có an toàn không?

**Đáp án:** không. Workload peer đã được xác minh, nhưng **end-user assertion provenance** sai. Proxy phải xác thực user và map canonical identity trước khi phát header.

**Câu 18.** Nếu app có `.permitAll("/health/live")`, NetworkPolicy có thể bỏ qua cổng health cho cả Internet không?

**Đáp án:** không. `permitAll` chỉ ở lớp app; network access cần giới hạn đúng nguồn health probes.

## 28. Checklist triển khai và QA

- [ ] Đã xác định proxy nào **thực sự xác thực user** và tạo identity assertion.
- [ ] Backend không có đường public/IP/LB/NodePort/Ingress phụ ngoài thiết kế.
- [ ] Firewall/security group hoặc NetworkPolicy **deny by default** tới backend.
- [ ] Chỉ workloads proxy được phê duyệt có quyền kết nối cổng backend.
- [ ] CNI enforcement, IPv4/IPv6, hostNetwork/NodePort/port-forward được kiểm tra.
- [ ] Kubernetes RBAC/admission bảo vệ namespace/pod labels dùng trong allow-list.
- [ ] Nếu cần mTLS, backend xác minh peer certificate/SAN/workload identity.
- [ ] Proxy strip mọi incoming identity header/aliases và reject duplicates phù hợp.
- [ ] Proxy ghi principal canonical **sau khi** auth service trả bằng chứng xác thực hợp lệ.
- [ ] App không tin `X-Forwarded-For` hay `Forwarded` để chứng minh kết nối là proxy.
- [ ] Forwarded metadata được strip/overwrite ở trust boundary; Boot/container xử lý phù hợp.
- [ ] Spring `RequestHeaderAuthenticationFilter` đọc đúng header và UserDetails/account mapping.
- [ ] Preauth failure không chuyển sang unaudited form/basic fallback.
- [ ] Không đăng ký RequestHeaderAuthenticationFilter hai lần ngoài/trong SecurityFilterChain.
- [ ] Stateless/session policy, principal-change/revocation và account disable đã được test.
- [ ] Business authorization theo route/tenant/object không dựa độc quyền vào “đã qua proxy”.
- [ ] Các endpoint actuator/health/webhook/WebSocket/legacy được phân loại riêng.
- [ ] Auth proxy outage/identity missing dẫn tới fail closed, không mở backend direct.
- [ ] Có negative tests forged identity header, duplicate headers, untrusted peer, mTLS mismatch.
- [ ] Test sibling pods, other namespaces, bypass network, IPv6 và management port.
- [ ] Có audit/metrics về attempted direct traffic và auth-header inconsistencies, không log credentials.
- [ ] Có kế hoạch rollout/rollback giữ nguyên proxy-only invariant trong khi deploy.
- [ ] Cấu hình phản hồi cho 401/403/503 phân biệt auth failure, authorization failure và dependency outage.

## 29. Kết luận

Đối với **xác thực qua proxy**, Spring Security pre-authentication chỉ nên xử lý **danh tính đã được proxy đáng tin xác minh và chuyển giao qua kênh được bảo vệ**. Vì `RequestHeaderAuthenticationFilter` không tự kiểm chứng header, **đường kết nối trực tiếp vào backend là một đường bỏ qua xác thực rất nguy hiểm**.

Thiết kế an toàn đòi hỏi **nhiều lớp đồng thời**:

1. **Chặn trực tiếp backend ở mạng**: private endpoint, firewall/security group hoặc Kubernetes NetworkPolicy có enforcement.
2. **Xác thực proxy workload**: mTLS/identity-aware peer kiểm soát đường proxy→backend khi cần.
3. **Bảo vệ nguồn gốc headers**: strip/overwrite toàn bộ incoming identity/forwarded headers, chỉ tạo assertion từ authenticated user context.
4. **Spring pre-auth fail closed**: không fallback authentication ngoài ý định; UserDetails và session policy được kiểm soát.
5. **Authorization và giám sát**: quyền theo account/tenant/object, test bypass thật, thu hồi phiên và theo dõi đường vào lạ.

**Một header danh tính không phải credential có thể tin chỉ vì nó có tên “Authenticated”.** Nó chỉ có giá trị khi toàn bộ ranh giới mạng, proxy và ứng dụng đều thực thi đúng hợp đồng tin cậy.

### Tài liệu chính thức

1. Spring Security — Pre-Authentication Scenarios và Request Header Authentication (cảnh báo header spoofing): https://docs.spring.io/spring-security/reference/servlet/authentication/preauth.html
2. Spring Security — RequestHeaderAuthenticationFilter Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/authentication/preauth/RequestHeaderAuthenticationFilter.html
3. Spring Security — AbstractPreAuthenticatedProcessingFilter (fallback, principal change): https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/authentication/preauth/AbstractPreAuthenticatedProcessingFilter.html
4. Spring Framework — Servlet ForwardedHeaderFilter và security considerations: https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html
5. Spring Security — HTTP security and forwarded header trust: https://docs.spring.io/spring-security/reference/features/exploits/http.html
6. Spring Boot — Embedded Web Servers/Forwarded Headers: https://docs.spring.io/spring-boot/reference/how-to/webserver.html
7. Kubernetes — NetworkPolicy, default deny ingress và selector semantics: https://kubernetes.io/docs/concepts/services-networking/network-policies/
8. NGINX — Reverse Proxy, proxy_set_header and suppress header by empty value: https://docs.nginx.com/nginx/admin-guide/web-server/reverse-proxy
9. NGINX — ngx_http_proxy_module: https://nginx.org/en/docs/http/ngx_http_proxy_module.html
10. NGINX — ngx_http_realip_module, set_real_ip_from trusted peers: https://nginx.org/en/docs/http/ngx_http_realip_module.html
11. NGINX — ngx_http_auth_request_module: https://nginx.org/en/docs/http/ngx_http_auth_request_module.html
12. RFC 7239 — Forwarded HTTP Extension: https://www.rfc-editor.org/rfc/rfc7239.html
