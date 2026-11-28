# Routing theo hostname, path và header trong reverse proxy và cân bằng tải

Giả sử doanh nghiệp có một địa chỉ IP công khai nhưng phải phục vụ nhiều ứng dụng: `app.example.test`, `api.example.test` và các API phiên bản khác nhau. Reverse proxy có thể quyết định đưa một HTTP request vào **backend nào** dựa trên **hostname**, **đường dẫn URL (path)** hoặc **HTTP header**. Nhưng nếu quy tắc quá rộng, không xử lý path chuẩn hóa hoặc tin header do client tự khai báo, request có thể đi nhầm sang API quản trị, một tenant khác, hoặc phiên bản canary chưa được bảo vệ đầy đủ.

**Routing theo hostname, path và header** là khả năng phân loại request ở lớp ứng dụng (L7) rồi chuyển tiếp tới upstream/backend phù hợp theo các điều kiện được định nghĩa và kiểm thử. Bài thuộc chương **Proxy reverse proxy và cân bằng tải** của module **SECURITY_NETWORK_SECURITY**; các quyết định routing liên quan chặt tới phân đoạn mạng, firewall, TLS/PKI, DNS, WAF, IAM/NAC, VPN, IDS/IPS, cloud ingress và giám sát an toàn.

**Nguyên tắc then chốt:** **routing quyết định request được đưa tới đâu; authentication/authorization quyết định request có được phục vụ hay không**. Hostname, path và các header thông thường **không tự chứng minh danh tính hoặc quyền truy cập**. Reverse proxy phải bảo vệ ranh giới tin cậy cả ở trước lẫn sau điểm định tuyến.

## 1. Mục tiêu học tập

Sau bài này, bạn cần:

1. Phân biệt **forward proxy, reverse proxy, load balancer L4 và router L7**; chỉ ra nơi nào đọc được hostname/path/header.
2. Giải thích sự khác nhau giữa **DNS name, TLS SNI, HTTP/1.1 Host và HTTP/2/3 `:authority`**.
3. Thiết kế rule theo **exact host, exact/prefix path và header match**, quy định thứ tự ưu tiên và fallback không mơ hồ.
4. Giải thích rủi ro từ **path normalization/rewrite**, trailing slash, encoded path và header bị giả mạo.
5. Dùng ví dụ NGINX, Gateway API và một cấu trúc policy độc lập sản phẩm để đọc luồng định tuyến.
6. Tách **backend selection, cân bằng tải, health check và authorization**, không dùng routing như một cơ chế cấp quyền.
7. Thiết lập phép thử positive/negative, logging, change/rollback cho multi-tenant, API versioning và canary rollout.

## 2. Reverse proxy nằm ở đâu trong kiến trúc?

Một luồng điển hình:

~~~mermaid
flowchart LR
    U["Browser / API client"] -->|"DNS + TLS + HTTP"| E["Edge CDN / WAF / reverse proxy"]
    E -->|"Host: app.example.test, path: /"| WEB["Web upstream pool"]
    E -->|"Host: api.example.test, path: /v1/"| API["API v1 upstream pool"]
    E -->|"Authorized internal route"| ADMIN["Admin ingress riêng"]
    WEB --> DATA[("Dịch vụ / dữ liệu")]
    API --> DATA
    ADMIN --> DATA
~~~

Hình minh họa **các lựa chọn routing logic**: thực tế edge chỉ được chuyển đến admin ingress khi đã có đường mạng và chính sách cho phép. Không cấu hình một quy tắc `/admin/` công khai rồi coi nó là kiểm soát truy cập.

### 2.1. Forward proxy và reverse proxy

| Loại | Bên sử dụng | Quyết định thường gặp | Điểm bảo mật cần xét |
|---|---|---|---|
| **Forward proxy** | Client chủ động gửi yêu cầu tới proxy để truy cập đích bên ngoài | Egress, destination, HTTP CONNECT, DNS và policy của tổ chức | Ngăn open proxy, kiểm soát egress, xác thực client |
| **Reverse proxy** | Client kết nối tên miền của dịch vụ, thường không cần biết các backend | Virtual host, path, header, upstream, WAF và TLS termination | Trust boundary client → edge → origin |
| **Load balancer L4** | Cân bằng TCP/UDP connection hoặc packet flow | IP, port, protocol và trạng thái connection | Không mặc định nhìn thấy HTTP path/header |
| **Load balancer / ingress L7** | Xử lý HTTP, gRPC hoặc giao thức ứng dụng được hỗ trợ | Host, method, path, headers, cookie, weighted backends | Canonicalization, TLS, header trust và auth policies |

Một sản phẩm có thể đảm nhiệm **nhiều vai trò**. NGINX, Envoy, HAProxy, cloud application load balancer và API gateway có tính năng khác nhau theo phiên bản/chế độ. Tên “load balancer” không bảo đảm có kiểm tra HTTP; phải xác định **tầng giao thức và đường packet thật**.

### 2.2. Routing khác load balancing

- **Routing/traffic classification:** chọn **nhóm backend** theo thông tin request, chẳng hạn `api.example.test/v2/` → pool API v2.
- **Load balancing:** chọn **một instance trong pool** theo thuật toán như round-robin, least-connections, consistent hashing hoặc trọng số.
- **Health check:** xác định instance/backend có đủ điều kiện nhận traffic không; đôi khi có cả liveness, readiness và active/passive checks.
- **Authorization:** kiểm tra user, service identity, tenant, object và hành động được phép. Nên được thực thi bởi gateway/ứng dụng tại boundary phù hợp, **không suy ra từ tên pool**.

Ví dụ: proxy chọn pool `api-v2` do path `/v2/`; sau đó chọn instance `api-v2-b` vì trạng thái tải. Ứng dụng vẫn phải trả `403` nếu user không có quyền. Một backend healthy không chứng minh endpoint đã được phân quyền đúng.

## 3. Nền tảng: hostname thực sự đến từ đâu?

Một request tới `https://api.example.test/v1/orders` thường liên quan **nhiều dạng tên**:

1. **DNS:** client phân giải `api.example.test` thành IP của edge; DNS không tự chứa HTTP path.
2. **TLS SNI:** client có thể gửi tên mong muốn ở giai đoạn bắt tay để server chọn chứng chỉ/cấu hình TLS. SNI thông thường không chứng minh quyền và có thể chịu tác động của ECH/chế độ triển khai.
3. **HTTP/1.1 `Host`:** HTTP header chỉ định authority/host của request. Client có thể tự tạo hoặc thay đổi giá trị.
4. **HTTP/2 và HTTP/3 `:authority`:** pseudo-header biểu diễn authority trong nhiều request; đừng giả định luôn có `Host` theo cùng kiểu HTTP/1.1.
5. **URI absolute-form:** trong một số ngữ cảnh proxy HTTP, request target có thể chứa authority; cần tuân thủ semantics của HTTP và không tùy ý ưu tiên một nguồn khi các nguồn xung đột.

### 3.1. DNS, SNI và Host không phải một giá trị duy nhất

~~~text
URL được yêu cầu: https://api.example.test/v1/orders
DNS:             api.example.test -> 203.0.113.40
TCP/TLS endpoint: 203.0.113.40:443
TLS SNI:         api.example.test       (nếu được gửi theo mode)
HTTP Host:       api.example.test       (HTTP/1.1 điển hình)
HTTP path:       /v1/orders

Ứng dụng phía sau: 10.80.20.11:8080 (chỉ ví dụ nội bộ)
~~~

`203.0.113.0/24` là dải IPv4 dành riêng cho tài liệu; các IP private cũng chỉ dùng minh họa. **DNS chọn IP để kết nối, SNI hỗ trợ chọn TLS context, còn HTTP authority/path giúp L7 reverse proxy chọn route**. Một TLS pass-through proxy có thể định tuyến dựa trên SNI nếu sản phẩm hỗ trợ, nhưng **không đọc được HTTP path/header đã mã hóa** nếu không terminate/decrypt TLS.

### 3.2. Host-header injection và authority confusion

Ví dụ client gửi `Host: attacker.example.test` trong khi kết nối tới một IP của doanh nghiệp. Một số ứng dụng có thể dùng Host để dựng URL reset password, callback, redirect hoặc absolute link. Nếu không kiểm tra authority:

- Link gửi qua email có thể bị tạo với domain do attacker kiểm soát.
- Cache hoặc tenant router có thể chọn sai namespace.
- Log và audit tưởng request đến từ một virtual host khác.
- Backend có thể nhận header nguyên gốc không đáng tin rồi sử dụng cho security decision.

**Phòng vệ:** định nghĩa tập hostname hợp lệ tại edge, có default virtual host từ chối host không được nhận diện, xác minh `:authority`/`Host` phù hợp request semantics, và dùng **canonical base URL đã cấu hình** để dựng security-sensitive redirects/links. Không chỉ “đã có HTTPS” rồi tin Host.

### 3.3. SNI khác HTTP authority: xử lý thế nào?

Một kết nối có SNI `app.example.test` nhưng request HTTP cho `api.example.test` cần được xử lý theo quy tắc product/protocol và chính sách an ninh. Trong HTTP/2, một connection có thể được tái sử dụng cho các origin trong điều kiện nhất định; do đó **không nên coi mọi trường hợp khác SNI là tấn công**, nhưng cũng không được để request đi sang tenant khác ngoài chính sách xác nhận origin/coalescing.

Khi request bị gửi tới một server không có thẩm quyền phục vụ target origin, **HTTP 421 Misdirected Request** là một phản hồi có thể phù hợp. Chính sách cụ thể cần thử với HTTP/1.1, HTTP/2, HTTP/3, SNI, certificate SAN và reverse proxy implementation.

## 4. Routing theo hostname: virtual hosting

**Host-based routing** ánh xạ hostname/authority được chấp nhận vào một backend hoặc nhóm quy tắc. Nó hữu ích khi nhiều ứng dụng dùng cùng cổng 443 và IP của reverse proxy.

| Host được chấp nhận | Đường đi mong muốn | Lưu ý |
|---|---|---|
| `app.example.test` | Web UI upstream | Kiểm tra certificate, session cookie, API paths |
| `api.example.test` | API gateway/upstream | Rate limit, version route, AuthN/AuthZ |
| `static.example.test` | Static asset/cache origin | CORS, caching và không lộ dữ liệu người dùng |
| `admin.example.test` | Admin ingress **chỉ qua đường được phép** | mTLS/ZTNA, firewall và quyền quản trị riêng |
| Host không có trong allowlist | Từ chối có kiểm soát | Không đưa vào “upstream mặc định” có quyền rộng |

### 4.1. Exact, wildcard và regular-expression host

- **Exact hostname:** `api.example.test` — phù hợp khi tập domain do tổ chức quản lý rõ.
- **Wildcard:** ví dụ `*.example.test` — có thể tiện cho tenant subdomains, nhưng phải tính takeover, wildcard certificate và namespace ownership.
- **Regex host:** một số proxy hỗ trợ pattern — dễ diễn đạt nhiều tenant nhưng cần chống mơ hồ, regex quá rộng và backtracking theo sản phẩm.

Không xem `tenant-a.example.test` là bằng chứng user thuộc tenant A. Kẻ có quyền gửi HTTP request có thể chọn hostname phù hợp; **tenant authorization ở ứng dụng** phải xác minh identity/token/role và object ownership.

### 4.2. Host normalization và giá trị không chuẩn

Tùy giao thức và proxy, giá trị hostname có thể có **chữ hoa/thường**, port, dấu chấm cuối, IDN/punycode hoặc cách biểu diễn IPv6 literal. Khi viết policy cần xác định:

1. Thành phần nào có trách nhiệm parse và chuẩn hóa authority?
2. Allowed hostnames được lưu ở dạng nào? Có chấp nhận port `:8443` không?
3. Xử lý unknown/multiple/conflicting `Host`/`:authority` thế nào?
4. Host được forward nguyên bản hay được edge đặt thành canonical value?
5. Hành vi khi SNI, certificate SAN và HTTP authority không tương thích ra sao?

Không tự viết logic so chuỗi thủ công rồi bỏ qua semantics của HTTP. Sử dụng parser/router của sản phẩm đã được kiểm thử và **fail closed** với các dạng không mong đợi.

## 5. Routing theo path: URI là ranh giới dễ bị hiểu sai

Với cùng host `app.example.test`, ta có thể định tuyến:

~~~text
GET /                       -> web-frontend
GET /assets/logo.svg        -> static-assets
GET /api/v1/orders          -> api-v1
GET /api/v2/orders          -> api-v2
GET /admin/users            -> từ chối tại public edge;
                               kênh quản trị được thiết kế riêng
~~~

Ba loại match thường gặp:

| Kiểu | Ví dụ điều kiện | Ý nghĩa |
|---|---|---|
| **Exact path** | `/healthz` | Chỉ khớp đúng đường được xác định theo parser/sản phẩm |
| **Path prefix** | `/api/v1/` | Khớp những path nằm dưới prefix theo semantics của bộ định tuyến |
| **Regular expression** | `^/assets/.*\.css$` | Khớp pattern; phải kiểm tra cách xử lý escape, case và normalized URL |

**Prefix `/api` khác prefix `/api/`** trong một số hệ thống. Một bộ matcher dùng so chuỗi có thể bắt nhầm `/apix` nếu rule quá rộng; bộ router khác có thể quy định prefix theo path segment. **Không suy quy tắc segment matching giống nhau giữa NGINX, Envoy, Gateway API và cloud LB.**

### 5.1. Chuẩn hóa URL/path là quyết định bảo mật

Trước khi proxy/backend so match, path có thể trải qua:

- **Percent decoding** (`%2F`, `%2e`...) tùy thành phần.
- **Dot-segment resolution** (`/a/../b`).
- **Repeated slashes** (`//`) và trailing slash.
- **Unicode/encoding/case** trong phần path.
- **Query string**, thường không thuộc phần path nhưng có thể ảnh hưởng routing nếu chính sách riêng dùng query.
- **URL rewriting** khi proxy bỏ/gắn prefix trước khi forward.

Nguy cơ lớn là **proxy và backend nhìn khác nhau về cùng một request**. Ví dụ edge cho rằng path nằm dưới `/public/`, trong khi backend sau khi decode/normalize lại hiểu thành `/admin/`. Vì vậy:

1. Tài liệu hóa **thứ tự parse → normalize → match → rewrite → authorize** của từng hop.
2. Dùng thư viện/parser chuẩn, giới hạn dạng path không mong đợi.
3. Không dựa vào **chặn path string** như kiểm soát quyền duy nhất; backend vẫn phải kiểm tra authorization.
4. Test cả encoded slash/dot, double encoding, mixed case, `//`, trailing slash trong môi trường được cấp quyền.

### 5.2. Rewrite path có thể làm đổi semantics

Một số proxy bỏ prefix từ request trước khi forward:

~~~text
Client:        GET /service-a/api/orders?id=7
Rule:          /service-a/ -> backend A; strip prefix /service-a
Backend sees:  GET /api/orders?id=7
~~~

Nếu backend A mong đợi `/service-a/api/orders` mà proxy đã strip, nó có thể trả 404, redirect sai hoặc auth middleware áp sai route. Với NGINX, **sự khác biệt giữa `proxy_pass http://upstream;` và `proxy_pass http://upstream/;` khi dùng trong location prefix** có thể làm thay đổi cách URI được chuyển tiếp; cần kiểm thử cụ thể với bản NGINX/cấu hình. Không “sửa nhanh” bằng thêm/bớt dấu slash mà không chạy test đường dẫn.

### 5.3. Chặn `/admin/` ở proxy chưa đủ

Ngay cả khi edge trả 403 cho `/admin/`, ứng dụng có thể còn endpoint tương đương qua đường khác, hostname khác hoặc path rewrite khác. Mô hình an toàn:

- Admin endpoint **không được expose** trên public ingress nếu không cần thiết.
- Admin ingress riêng có authentication/MFA, network access policy và audit.
- Backend bảo vệ **mọi admin API theo identity/role**, kể cả khi path bị rewrite.
- Kiểm thử bypass từ public và internal network; không dùng “404” như bằng chứng duy nhất về authorization.

## 6. Routing theo header: linh hoạt nhưng không mặc định đáng tin

**HTTP header routing** chọn backend dựa vào giá trị header được định nghĩa. Một số trường hợp hợp lệ:

| Header/nhóm metadata | Mục đích có thể dùng | Rủi ro cần kiểm tra |
|---|---|---|
| `Accept` | Chọn endpoint hỗ trợ định dạng trả về | Negotiation không tương đương quyền |
| `Content-Type` | Chọn parser/upstream khi product hỗ trợ | Parser mismatch, file upload và request validation |
| `X-Release-Channel: canary` | Thử backend canary với tập client được quản lý | Client có thể tự gửi header nếu không có auth ở nguồn |
| `X-API-Version` | Chuyển đến phiên bản API | Không bảo đảm caller có quyền với version đó |
| `X-Tenant-ID` | Định tuyến theo tenant **sau khi đã xác minh nguồn** | Dễ lẫn tenant nếu chỉ tin header từ client |
| `X-Forwarded-For` | Truyền thông tin IP client qua proxy chain | Có thể bị spoof; chỉ tin từ proxy thuộc danh sách |
| `Forwarded` (RFC 7239) | Thông tin client/proto/host theo chuẩn header | Cần parser/trust boundary phù hợp |
| `Authorization` | Token/credential cho xác thực | Không đặt routing secrets vào log; quyền phải được xác minh |

**Header client gửi là dữ liệu đầu vào không tin cậy** cho tới khi được xác minh nguồn/định dạng/chữ ký theo chính sách. Nếu định tuyến tới backend có quyền cao chỉ vì `X-Internal-User: admin`, người ngoài có thể thử tự gửi chính header đó.

### 6.1. Header routing nên kết hợp gì?

Một rule an toàn hơn có thể là:

~~~text
Điều kiện trước routing:
  - Host trong allowlist: api.example.test
  - Path thuộc /v1/
  - Client đã qua authn hoặc nguồn thuộc kênh được quản lý

Quy tắc triển khai (ví dụ không nhạy cảm):
  - Nếu verified cohort = canary -> api-canary
  - Ngược lại -> api-stable

Mọi request tới api-canary hoặc api-stable:
  - API kiểm tra token, tenant, scope và object-level authorization
~~~

Nếu một demo cho phép header `X-Release-Channel: canary` do client tự chọn, hãy coi đó là **feature routing không mang quyền**, và bảo đảm canary không có khả năng truy cập dữ liệu/role vượt stable. Với production, cohort nên dựa vào danh tính đã xác minh, feature-flag service hoặc proxy **tự tạo/ghi đè metadata** sau auth.

### 6.2. Multi-value, duplicate và hop-by-hop headers

HTTP headers có thể xuất hiện nhiều lần; hành vi gộp, bỏ hoặc ưu tiên của parser khác nhau theo loại header và HTTP version. Đừng tự tạo logic `first value wins` hoặc `last value wins` cho security-sensitive fields khi proxy/backend có thể diễn giải khác.

Đặc biệt:

- `Host`/`:authority`: phải xử lý xung đột theo HTTP semantics và chính sách.
- `Content-Length`, `Transfer-Encoding`, `Connection`: cần parser/normalization nhất quán để giảm rủi ro request framing/desync.
- `X-Forwarded-For`, `X-Forwarded-Proto`, `X-Forwarded-Host`: phải có chính sách **trusted upstreams** và không tin chuỗi do client tự điền.
- `Cookie` hoặc credential: không đưa vào routing logs/cache key một cách tùy tiện vì rủi ro riêng tư.
- gRPC/HTTP/2: metadata và pseudo-headers có semantics riêng; kiểm thử proxy HTTP/2↔HTTP/1.1 translation.

**Request smuggling/desynchronization** có thể xuất hiện nếu hai hop hiểu ranh giới request khác nhau. Tài liệu này chỉ tập trung biện pháp phòng vệ: patch HTTP parser, loại bỏ request không hợp lệ/mơ hồ, làm nhất quán protocol translation và kiểm thử an toàn theo quy trình được cấp quyền.

## 7. Thứ tự ưu tiên rule và hành vi mặc định

Nếu một request khớp nhiều rule, câu hỏi phải trả lời trước khi triển khai là **rule nào thắng và vì sao**.

Ví dụ chính sách logic:

~~~mermaid
flowchart TD
    Q["HTTP request đến proxy"] --> T["TLS handshake và xác minh nguồn ingress"]
    T --> H{"Hostname/authority hợp lệ?"}
    H -->|"Không"| REJ["421/4xx và audit theo policy"]
    H -->|"Có"| N["Parse, normalize path và headers"]
    N --> A{"Endpoint admin/restricted?"}
    A -->|"Có"| P["Route đến security control riêng hoặc deny"]
    A -->|"Không"| E{"Path exact/prefix match?"}
    E -->|"Không"| DEF["Default route an toàn hoặc 404"]
    E -->|"Có"| M{"Header/cohort rule hợp lệ?"}
    M -->|"Có"| CAN["Canary backend"]
    M -->|"Không"| ST["Stable backend"]
    CAN --> AUTH["Backend AuthN/AuthZ + logging"]
    ST --> AUTH
~~~

Quy trình trên là **decision flow do ta thiết kế**, không phải thuật toán chọn `location` của mọi reverse proxy. Để có hành vi dự đoán được:

1. **Cố định host allowlist** hoặc policy attachment theo namespace/site.
2. **Đặt route đặc thù trước route rộng** theo semantics của sản phẩm; không dựa vào thứ tự YAML khi specification dùng precedence khác.
3. Có **fallback an toàn** cho không khớp; không chuyển request lạ tới backend nội bộ nhiều quyền.
4. Xác định behavior khi **path/header malformed**; không đưa request qua parser khác để “thử”.
5. Test mọi giao thoa rule và mỗi biến thể protocol/transport được hỗ trợ.

### 7.1. NGINX `location` precedence (ý chính)

Trong một NGINX `server` block điển hình, việc chọn location có quy tắc riêng: exact match `=`, prefix, ưu tiên dạng `^~` cho prefix được chọn, rồi regex theo quy trình của NGINX và thứ tự khai báo khi thích hợp. Regex locations và nested locations có thể làm logic phức tạp hơn; không nên suy **mọi regex đều luôn thắng mọi prefix**, hoặc **file config viết trước luôn chạy trước**.

Đọc tài liệu sản phẩm và kiểm thử các trường hợp thật. Một rule `/api/` rất rộng có thể bắt một endpoint mà bạn muốn xử lý với rule `/api/admin/` cụ thể hơn nếu thiết kế precedence sai.

## 8. Ví dụ NGINX: routing theo hostname và path

Ví dụ sau dùng **hai hostname được phép**, cổng `8443` trong lab, TLS certificate giả định đã cấp và backend trong mạng private. **Không copy vào production** khi chưa bổ sung authentication, WAF, rate limit, log privacy, health check, timeouts, TLS-to-origin, HA và chính sách mạng.

~~~nginx
# File cấu hình minh họa NGINX: certificates và upstream lab phải tồn tại.
upstream web_pool {
    server 10.80.10.11:8080;
    server 10.80.10.12:8080;
}

upstream api_v1_pool {
    server 10.80.20.11:8080;
    server 10.80.20.12:8080;
}

upstream api_v2_pool {
    server 10.80.21.11:8080;
    server 10.80.21.12:8080;
}

# Catch-all: không đưa host không xác định vào upstream có quyền.
server {
    listen 8443 ssl default_server;
    server_name _;
    ssl_certificate     /etc/nginx/tls/lab-default.crt;
    ssl_certificate_key /etc/nginx/tls/lab-default.key;
    return 421;
}

server {
    listen 8443 ssl;
    server_name app.example.test;
    ssl_certificate     /etc/nginx/tls/lab-app.crt;
    ssl_certificate_key /etc/nginx/tls/lab-app.key;

    location = /healthz {
        return 200 "ok\n";
    }

    # Đường public không được dùng làm admin ingress.
    location = /admin {
        return 403;
    }
    location ^~ /admin/ {
        return 403;
    }

    # Không để đường thiếu dấu slash rơi vào web upstream ngoài ý định.
    location = /api/v1 {
        return 404;
    }
    location = /api/v2 {
        return 404;
    }

    location ^~ /api/v1/ {
        proxy_set_header Host app.example.test;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Request-ID $request_id;
        proxy_pass http://api_v1_pool;
    }

    location ^~ /api/v2/ {
        proxy_set_header Host app.example.test;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Request-ID $request_id;
        proxy_pass http://api_v2_pool;
    }

    location / {
        proxy_set_header Host app.example.test;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Request-ID $request_id;
        proxy_pass http://web_pool;
    }
}

server {
    listen 8443 ssl;
    server_name api.example.test;
    ssl_certificate     /etc/nginx/tls/lab-api.crt;
    ssl_certificate_key /etc/nginx/tls/lab-api.key;

    location ^~ /v1/ {
        proxy_set_header Host api.example.test;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Request-ID $request_id;
        proxy_pass http://api_v1_pool;
    }

    location ^~ /v2/ {
        proxy_set_header Host api.example.test;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Request-ID $request_id;
        proxy_pass http://api_v2_pool;
    }

    location / {
        return 404;
    }
}
~~~

### 8.1. Điều gì xảy ra với những request mẫu?

| Request trong lab | Rule kỳ vọng | Backend/kết quả |
|---|---|---|
| `Host: app.example.test`, `GET /` | `location /` của app | `web_pool` |
| `Host: app.example.test`, `GET /api/v1/orders` | prefix `/api/v1/` | `api_v1_pool` |
| `Host: app.example.test`, `GET /api/v2/orders` | prefix `/api/v2/` | `api_v2_pool` |
| `Host: api.example.test`, `GET /v1/orders` | prefix `/v1/` | `api_v1_pool` |
| `Host: app.example.test`, `GET /admin/users` | prefix `/admin/` | `403` tại proxy |
| `Host: unknown.example.test` | default virtual server (khi HTTP được xử lý) | `421`, có thể bị TLS identity failure trước |
| `Host: api.example.test`, `GET /unknown` | `location /` của api | `404` |

**Lưu ý về HTTPS:** trước khi HTTP `421` có thể xuất hiện, một TLS client gặp default certificate không khớp hostname có thể **từ chối handshake/chứng chỉ**. Không dùng `421` làm bằng chứng duy nhất rằng mọi unknown SNI/Host đã được xử lý đúng.

### 8.2. Những giới hạn cố ý của ví dụ

- `proxy_pass http://...` dùng HTTP từ NGINX đến backend **chỉ vì đây là lab**. Production phải đánh giá TLS/mTLS tới origin hoặc phân đoạn mạng/identity tương ứng; không tự suy “backend private” luôn an toàn.
- `X-Forwarded-For $remote_addr` **ghi đè input không tin cậy** khi NGINX là edge trực tiếp; nếu có CDN/trusted proxy ở trước, `$remote_addr` có thể là IP của CDN. Khi đó cần thiết kế `real_ip` với **allowlist proxy IP** và xác minh chuỗi forward, không trust bất kỳ client-supplied `X-Forwarded-For`.
- `Host` chuyển xuống backend được đặt thành giá trị **cố định đã duyệt** theo virtual host. Không dùng raw Host để cấu tạo URL hoặc backend destination.
- Không có định nghĩa đầy đủ cho WebSocket/gRPC upgrades, cookies, timeouts, retries, rate limiting, TLS versions/curves, certificate rotation và protected health checks.
- HTTP `/admin/` bị chặn theo prefix nhưng **không thay AuthZ của backend** hoặc một private admin ingress riêng.
- `return 200 "ok\n"` là phản hồi liveness minh họa, không chứng minh database/dependencies của ứng dụng khỏe mạnh.

### 8.3. Cấu hình đúng cú pháp chưa đủ

Trong hệ thống thật, phải kiểm tra `nginx -t` trên **bản cấu hình đã qua review và có đầy đủ cert/đường dẫn**, sau đó test routing từ client thực và đối chiếu backend logs. Chỉ khi sản phẩm hỗ trợ, cấu hình rule ở ingress nên được review như **security-sensitive change** vì một thay đổi `location` có thể phá ranh giới tenant hoặc mở đường quản trị.

## 9. Ví dụ header routing với Kubernetes Gateway API

Gateway API có đối tượng `HTTPRoute` cho phép mô tả các điều kiện theo hostname, path, header và backend. Ví dụ dưới đây minh họa **header chọn canary không chứa quyền cao hơn stable**. Nó không phải manifest production hoàn chỉnh: Gateway, listener, Service, namespace, ReferenceGrant (nếu cần), authorization policy và controller tương thích phải tồn tại.

~~~yaml
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: api-release-routing
  namespace: app
spec:
  parentRefs:
    - name: public-gateway
      namespace: networking
  hostnames:
    - api.example.test
  rules:
    - matches:
        - path:
            type: PathPrefix
            value: /v1
          headers:
            - name: X-Release-Channel
              value: canary
      backendRefs:
        - name: api-canary
          port: 8080
    - matches:
        - path:
            type: PathPrefix
            value: /v1
      backendRefs:
        - name: api-stable
          port: 8080
~~~

**Cách đọc:** hostname `api.example.test`, path prefix `/v1` và header `X-Release-Channel=canary` định tuyến về Service `api-canary` nếu route được chấp nhận và rule phù hợp; các request `/v1` khác có thể về `api-stable`. **Không suy rằng thứ tự YAML tự quyết định precedence trong mọi trường hợp**: Gateway API có quy tắc ưu tiên match/route và các điều kiện conflict riêng, phụ thuộc cả spec version và controller implementation. Phải quan sát **status của HTTPRoute** và kiểm thử đường thật.

### 9.1. Header của caller không phải phép cấp quyền

Trong ví dụ, một client bên ngoài có thể **tự gửi `X-Release-Channel: canary`**. Vì vậy canary chỉ phù hợp nếu:

- Nó có **cùng hoặc ít quyền hơn** stable, và ứng dụng vẫn xác thực/token + kiểm tra quyền mỗi request.
- Không chứa API quản trị, dữ liệu thử nghiệm nhạy cảm hoặc tenant khác.
- Không dùng header này để xác minh tư cách nhân viên/nội bộ.
- Nếu muốn cohort canary chỉ cho nhân viên thử nghiệm, hãy dựa vào **identity đã được xác minh** rồi gateway đặt header riêng sau khi loại bỏ header khách gửi.

### 9.2. Gateway API: điều kiện cross-namespace

Một `HTTPRoute` có thể bị giới hạn bởi **listener allowedRoutes**, namespace policy và quyền tham chiếu backend. Cross-namespace backend references cần cơ chế ủy quyền phù hợp, thường là **ReferenceGrant** ở namespace đích. Không cho tenant tùy ý tạo route tham chiếu Service của tenant khác hoặc chiếm hostname chung.

Đừng xem việc một YAML được API server nhận là bằng chứng route đã hoạt động: kiểm tra **Accepted/ResolvedRefs** của HTTPRoute, **Programmed** và listener conditions của Gateway nếu được cung cấp, thông tin conflict theo controller và kết quả end-to-end trên ingress thực.

## 10. Proxy chain và ranh giới `X-Forwarded-*`

Đường đi có thể gồm:

~~~mermaid
flowchart LR
    C["Client không tin cậy"] --> W["CDN / WAF"]
    W --> N["Reverse proxy nội bộ"]
    N --> A["Application"]
    W -.->|"Tạo hoặc chuẩn hóa forwarding metadata"| N
    N -.->|"Tin WAF chỉ khi nguồn/kênh được kiểm chứng"| A
~~~

Các header phổ biến:

| Header | Mục đích | Lỗi thường gặp |
|---|---|---|
| `X-Forwarded-For` | Chuỗi địa chỉ các hop/proxy liên quan tới nguồn | Tin phần do client tự gửi, xác định sai IP user |
| `X-Real-IP` | Một cách chuyển client IP do proxy định nghĩa | Tin từ mọi nguồn thay vì trusted proxy |
| `X-Forwarded-Proto` | Scheme mà client dùng ở hop trước | Tin `https` do client giả để vượt kiểm soát secure cookies/redirect |
| `X-Forwarded-Host` | Host nguyên bản hoặc do proxy chuyển | Host injection, poisoned link/reset URL |
| `Forwarded` | Cấu trúc chuẩn hóa với `for`, `proto`, `host` | Parse sai quoting, chain, IPv6 hoặc trust |
| `X-Request-ID` / trace context | Ghép log qua nhiều hop | Client đưa ID trùng, giá trị không hợp lệ hoặc chứa dữ liệu nhạy cảm |

**Mô hình tin cậy đúng:** proxy tại biên kiểm soát header client, loại bỏ/ghi đè header nhạy cảm hoặc tạo metadata mới; hop tiếp theo chỉ tin metadata khi request đến qua **network/mTLS identity của upstream được phê duyệt** và kiểm tra policy.

### 10.1. Không dùng `X-Forwarded-For` trực tiếp làm ACL

Giả sử backend cho phép IP `10.80.0.8` quyền admin chỉ vì header `X-Forwarded-For` bắt đầu bằng địa chỉ đó. Nếu attacker có thể gửi header tùy ý qua một điểm proxy không ghi đè, ACL bị bypass.

Thay vào đó:

- Thực thi network ACL tại một hop có **source IP được xác minh bởi network boundary**.
- Nếu cần client IP sau CDN, cấu hình explicit trusted proxies và xử lý chain theo semantics của sản phẩm.
- Với quyền admin, dùng **identity/token/mTLS**, role và audit độc lập với client IP.
- Đối với logs, ghi **peer IP thực tế, forwarded chain, trusted proxy identity, request ID và decision reason** khi có thể, với retention phù hợp.

### 10.2. Routing tới backend theo URL do client gửi là nguy hiểm

Không dùng raw `Host`, `X-Backend` hoặc một query parameter để ghép tùy ý destination trong `proxy_pass`/upstream. Nếu proxy được phép tạo request đến đích do attacker chọn, có thể mở đường cho **SSRF, internal service discovery và truy cập metadata endpoints**.

Chỉ chọn backend từ **allowlist tĩnh/được quản trị**, cấu hình chính sách egress của proxy và hạn chế DNS resolution/redirect nếu product hỗ trợ dynamic upstream. Nếu dùng service discovery, xác minh owner, namespace và danh tính upstream; không chỉ tin một tên miền có thể resolve.

## 11. Cân bằng tải bên trong một route

Sau khi xác định `/v1/` → `api-v1`, proxy có thể chọn instance:

| Chiến lược | Mục tiêu | Rủi ro/điều kiện |
|---|---|---|
| **Round-robin** | Phân chia request/connection tương đối đều theo cấu hình | Request cost khác nhau, long-lived connections |
| **Least connections** | Ưu tiên node có ít active connections hơn | Một connection có thể không tương đương một đơn vị tải |
| **Weighted balancing** | Đưa một tỷ lệ traffic tương đối theo trọng số | Actual distribution phụ thuộc session, connection, health |
| **Hash/consistent hash** | Giữ tính ổn định ánh xạ theo một key | Key client-controlled có thể gây hotspot; privacy và multi-tenant |
| **Sticky session** | Giữ user/session ở một backend | Session state, HA/failover, cookie security |
| **Locality/zone aware** | Ưu tiên backend gần hoặc cùng vùng | Cần failover/health khi vùng lỗi |

**Routing và balancing đều không bảo đảm backend an toàn.** Proxy cần health/readiness check, giới hạn concurrency, timeout, circuit breaking khi hỗ trợ, và ứng dụng vẫn phải kiểm tra AuthN/AuthZ.

### 11.1. Health check phải phản ánh khả năng phục vụ

- **Liveness:** tiến trình đang chạy; không nhất thiết sẵn sàng phục vụ traffic nghiệp vụ.
- **Readiness:** backend đủ điều kiện nhận request tại thời điểm kiểm tra.
- **Dependencies:** database/cache/IdP hoặc service mesh có thể không khỏe dù HTTP `/healthz` trả `200`.
- **Security:** không để health endpoint trả secret, thông tin nhạy cảm hoặc mở một đường truy cập không được phép.

Một endpoint trả 200 không có nghĩa latency p99, tỷ lệ lỗi ứng dụng hay phân quyền tenant đang đúng. Đo trải nghiệm thực tế, không chỉ ping.

### 11.2. Retry và các request có side effects

Khi backend lỗi, proxy có thể retry hoặc chọn instance khác tùy policy. **Không retry mù mọi `POST` có side effect**, vì một request có thể đã được backend thực thi nhưng response thất lạc; retry có thể tạo giao dịch trùng.

Các biện pháp:

- Giới hạn retry theo **idempotency**, tình trạng request đã gửi và loại lỗi.
- Dùng idempotency key/check ở application cho những thao tác tạo giao dịch quan trọng.
- Đặt timeout/budget, tránh retry storms khi backend quá tải.
- Đo tỷ lệ retry/duplicate attempts theo route và backend.

## 12. Canary, blue-green và multi-version routing

### 12.1. Canary theo header hoặc trọng số

Có hai mục tiêu khác nhau:

1. **Canary theo cohort:** chỉ những user/thiết bị đã được xác định được đưa tới bản thử.
2. **Canary theo traffic ratio:** một tỷ lệ request/connection được chọn ngẫu nhiên hoặc theo hashing để đánh giá phiên bản mới.

Ví dụ chính sách logic:

~~~text
Host: api.example.test
Path: /v2/

Đầu tiên:
  - AuthN/identity/cohort được kiểm tra bởi hệ thống đáng tin
  - Route canary chỉ khi verified cohort = test-group
  - Mọi request vẫn qua authorization của API

Đối với traffic còn lại:
  - Stable: trọng số minh họa 95
  - Canary: trọng số minh họa 5

Không có route khớp:
  - 404/deny theo policy, không fallback vào privileged API
~~~

Trọng số **95/5 không có nghĩa chính xác 5% người dùng** hoặc 5% request trong mọi cửa sổ quan sát: cách thực thi có thể theo connection, session, hash, health và kích thước mẫu. Theo dõi phân phối thực tế và áp giới hạn blast radius.

### 12.2. Blue-green và rollback

Blue-green dùng hai môi trường triển khai (Blue/Green) và chuyển traffic từ môi trường hiện hành sang môi trường mới theo kế hoạch. Vấn đề cần xét không chỉ route:

- Schema migration và backward compatibility giữa hai version.
- Session/token/cookie và sticky state.
- Đường truy cập dữ liệu và tenant boundaries.
- Health/readiness, synthetic tests và error budget.
- Kế hoạch rollback khi database không còn tương thích.

**Không tự cho rằng rollback reverse-proxy route là đủ rollback ứng dụng** nếu data state đã bị biến đổi.

### 12.3. Header route và tính ổn định cohort

Nếu canary chọn dựa vào một header mà client có thể thay đổi cho mỗi request, một session có thể nhảy giữa stable/canary, gây lỗi state hoặc kết quả không nhất quán. Cân nhắc:

- Cohort được suy từ identity đã xác minh và được bảo vệ ở edge.
- Hash ổn định theo user/tenant ID đã chuẩn hóa, không dùng raw header bất kỳ.
- Sticky session trong phạm vi phù hợp, với cookie có thuộc tính security đúng.
- Canary database/feature flags và backward compatibility.

## 13. Trust boundaries: TLS, WAF, origin, tenant và cache

### 13.1. TLS termination và route

~~~mermaid
flowchart LR
    C["HTTPS client"] -->|"TLS A"| EDGE["WAF / CDN: TLS termination"]
    EDGE -->|"TLS B nếu được thiết kế"| RP["Reverse proxy / ingress"]
    RP -->|"TLS C / mTLS nếu dùng"| UP["Backend"]
    EDGE -.->|"HTTP Host/path/header có thể được đọc sau TLS"| RP
~~~

Đối với HTTP L7 routing, proxy cần **nhìn thấy request đã giải mã tại một hop được phép** (hoặc nhận thông tin L7 từ một trusted terminator). Khi TLS kết thúc ở CDN, mTLS/HTTPS từ CDN tới origin là **một phiên mới** với certificate và security boundary riêng.

Không suy rằng truy cập client → CDN dùng HTTPS thì mọi hop CDN → origin → service mesh đều được mã hóa. Thiết kế cần xác định certificate validation, origin access control, mTLS nếu phù hợp và log có thể chứa plaintext.

### 13.2. Cache key và tenant separation

Nếu reverse proxy/CDN cache phản hồi API, cache key có thể dựa vào **scheme, hostname, path, query, một số request headers** theo chính sách. Rủi ro:

- Cache key thiếu tenant/identity khi response khác nhau theo người dùng.
- Header `Authorization` bị bỏ qua trong cache policy không phù hợp.
- Query normalization hoặc path decode khác giữa cache và backend.
- `Vary` không được xử lý đúng hoặc cache cookie/header không có chủ đích.
- Hostheader mismatch khiến cache của domain/tenant này trả nội dung cho domain/tenant khác.

**Mặc định an toàn cho dữ liệu cá nhân/tenant là không shared-cache response** trừ khi có thiết kế và kiểm thử chứng minh phân tách đúng. Cache-Control phù hợp là một phần, nhưng vẫn cần kiểm tra behavior cụ thể của CDN/reverse proxy.

### 13.3. Routing không cấp quyền tenant

Một request có `Host: tenant-b.example.test` hoặc `X-Tenant-ID: tenant-b` là **claim do caller thể hiện**. Backend phải xác minh:

- Identity/token của caller có được gắn tenant B không?
- Resource ID/order ID yêu cầu có thuộc tenant được phép không?
- Route/host tương ứng với tài nguyên nào, được quản trị bởi ai?
- Service-to-service identity của upstream có được xác thực không?
- Có direct backend access bypass proxy/tenant filter không?

Không chỉ dựa vào RADIUS/NAC, VLAN hoặc VPN IP để suy quyền API. Network control giới hạn đường vào; application authorization chặn truy cập trái đối tượng.

## 14. Threat modeling cho routing theo host, path, header

| ID | Rủi ro | Kịch bản | Kiểm soát |
|---|---|---|---|
| R01 | **Host header injection** | Host do client gửi được dùng tạo link reset password | Host allowlist, canonical URL, chặn authority không hợp lệ |
| R02 | **SNI/authority mismatch** | Request đi sang virtual host khác ngoài ý định | Policy origin/coalescing rõ, certificate check, 421 khi phù hợp |
| R03 | **Wildcard tenant takeover** | Route wildcard nhận một hostname không có owner | Domain/namespace ownership, route admission và audit |
| R04 | **Path normalization drift** | Edge và backend hiểu encoded path khác nhau | Canonicalization thống nhất, fail closed, backend AuthZ |
| R05 | **Prefix/regex precedence sai** | Route rộng bắt request restricted | Test rule overlap, exact/specific rules, safe fallback |
| R06 | **Rewrite nhầm base path** | Proxy strip prefix, middleware auth áp sai route | Spec path semantics, integration tests |
| R07 | **Spoofed forwarded headers** | Client giả X-Forwarded-For/Proto/Host | Trusted proxy allowlist, strip/overwrite, secure metadata |
| R08 | **Header được dùng như credential** | X-Internal-Role tự gửi chọn admin upstream | Verified identity, mTLS/JWT/AuthZ, deny header-only privilege |
| R09 | **Client chọn arbitrary backend** | Dynamic proxy destination theo raw Host/X-Backend | Backend allowlist, egress ACL, service identity |
| R10 | **Request framing desync** | Parser khác nhau về Content-Length/Transfer-Encoding | Reject malformed input, patch proxies, consistent HTTP semantics |
| R11 | **Cross-tenant cache leak** | Cache key thiếu tenant/auth context | Disable unsafe shared cache, isolate key, tests |
| R12 | **Canary phiên bản có quyền quá rộng** | Header do client chọn dẫn sang API chưa bảo vệ | Canary same auth policy, controlled cohort, gradual rollout |
| R13 | **Gateway route hijack** | Tenant tự tạo route chiếm hostname/Service | Listener/namespace allowedRoutes, RBAC, ReferenceGrant |
| R14 | **Direct origin bypass** | Client bỏ qua CDN/WAF, gọi backend public IP | Private ingress, origin ACL, mTLS/identity và firewall |
| R15 | **TLS mất bảo vệ sau edge** | Edge → origin HTTP qua mạng không tin cậy | TLS re-encryption, peer validation, segmentation |
| R16 | **Health check false positive** | Proxy đưa traffic vào node chỉ trả 200 nhưng app lỗi | Readiness, synthetic SLO, backend metrics |
| R17 | **Retry gây thao tác trùng** | Proxy retry POST khi response đầu thất lạc | Retry budget, idempotency key, app-level dedup |
| R18 | **IPv6/HTTP3 khác policy** | TCP/IPv4 chặn admin nhưng QUIC/IPv6 mở | Kiểm thử đa transport và dual-stack |
| R19 | **Log lộ header/token** | Proxy ghi Authorization/Cookie/PII thô | Redact, least privilege, retention, audit |
| R20 | **Drift giữa các PoP** | Một vùng còn route/admin policy cũ | Versioning, canary, kiểm thử mọi region/PoP |

### 14.1. Chọn biện pháp theo ranh giới

Không có một rule proxy duy nhất giải quyết tất cả R01–R20. Có ít nhất năm boundary cần phân tách:

1. **Client/Internet → edge:** parse HTTP hợp lệ, TLS identity, WAF, Host allowlist, input validation và rate limits.
2. **Edge → proxy:** xác thực trusted proxy, bảo vệ đường truyền, chuẩn hóa headers và metadata.
3. **Proxy → backend:** chỉ chọn từ danh sách upstream được phép, route/firewall/mTLS và bảo vệ health-based selection.
4. **Backend → dữ liệu:** authorization theo user/tenant/object, bảo vệ database/API dù request từ đúng route.
5. **Operator/CI → routing control plane:** RBAC, review, signed/approved config, versioning và rollback.

### 14.2. Không dùng route denial như bằng chứng tuyệt đối

Nếu request `/admin/users` trả 404/403 ở một public hostname, điều đó **không chứng minh** admin backend không thể tới qua hostname khác, IPv6, origin IP hoặc một ingress khác. Cần inventory đầy đủ entry points và kiểm thử negative theo lớp, không chỉ một URL.

## 15. Giám sát: thấy được route nào thật sự được chọn

### 15.1. Trường log hữu ích

| Nhóm | Trường có thể ghi | Mục đích |
|---|---|---|
| **Ingress** | Timestamp/timezone, protocol, TLS/SNI, authority đã chuẩn hóa | Tái dựng entry point |
| **Routing** | Route ID, rule version, match type, selected backend pool | Chẩn đoán route drift và precedence |
| **Upstream** | Instance ID, upstream latency, status, retry count | Nhận biết balancing/health issue |
| **Identity** | Anonymous/verified role hoặc pseudonymous ID theo privacy | Không nhầm client-supplied header với identity |
| **Network** | Trusted peer IP, client IP đã xử lý bởi proxy chain | Phân biệt NAT/proxy và caller |
| **Security** | WAF decision, auth decision, rate-limit action | Xác định deny/allow theo policy |
| **Correlation** | Request ID/trace ID tạo ở edge, ứng dụng và DB trace khi có | Ghép luồng end-to-end |
| **Deploy** | Config hash/version, canary cohort, change ticket | Điều tra drift hoặc sự cố sau rollout |

Không log toàn bộ `Authorization`, `Cookie`, user tokens, body chứa PII hoặc mật khẩu. Khi cần raw request để điều tra, áp scope, phê duyệt, mã hóa lưu trữ và thời hạn giữ liệu phù hợp.

### 15.2. Dashboard và cảnh báo

- **Request distribution theo host/path/route/backend:** phát hiện route đi sai pool.
- **4xx/5xx, p50/p95/p99 latency:** phân biệt security denial với backend failure, kể cả tải canary.
- **Unmatched/malformed host và path:** xem cấu hình, bot, lỗi client hoặc domain mới chưa khai báo.
- **Canary error rate/latency và tỷ lệ traffic thực tế:** dùng ngưỡng rollback có căn cứ.
- **Upstream health, queue, connection reuse, retry/circuit-break:** phòng tránh cascading failure.
- **TLS/certificate errors theo SNI/hostname:** nhận biết PoP drift, HTTPS upgrade và mTLS failure.
- **Gateway route admission errors:** phát hiện conflict hoặc thiếu quyền namespace/backend.
- **Unexpected client-provided forwarded headers:** kiểm tra boundary trước khi đưa vào logs/analytics.

**Không gọi mọi 404 hay header lạ là tấn công.** URL cũ, crawler, lỗi release, proxy ở phía khách và retry hợp lệ đều có thể tạo spike. Đối chiếu change history, inventory, user-agent và firewall/WAF/application logs trước khi quy kết.

## 16. Lệnh quan sát và thử nghiệm an toàn trong lab

Chỉ chạy trên endpoint do bạn sở hữu hoặc được ủy quyền; không thử path bypass hay host confusion đối với hệ thống ngoài phạm vi. Ví dụ sau giả định reverse proxy lab hoạt động ở `127.0.0.1:8443`, certificate hợp lệ cho hai hostname và CA lab ở một đường dẫn thực.

### 16.1. Đọc đường Host + path với curl

~~~bash
# --resolve đưa hostname đến loopback nhưng giữ hostname để dùng TLS/SNI.
# --cacert chỉ định CA tin cậy của lab; KHÔNG dùng -k để bỏ validation.
curl -v \
  --cacert /path/to/lab-root-ca.pem \
  --resolve app.example.test:8443:127.0.0.1 \
  https://app.example.test:8443/api/v1/orders

# Cùng IP/cổng nhưng hostname khác, route khác.
curl -v \
  --cacert /path/to/lab-root-ca.pem \
  --resolve api.example.test:8443:127.0.0.1 \
  https://api.example.test:8443/v2/orders
~~~

`--resolve` chỉ ảnh hưởng đến việc curl kết nối tới IP được chỉ định cho host:port của lệnh; **không thay DNS hệ điều hành cho mọi ứng dụng**. Các request sẽ thất bại nếu không có server và CA lab phù hợp; đó không phải bằng chứng cấu hình đã sai.

### 16.2. Kiểm tra header routing (lab đã cho phép)

~~~bash
# Trên lab có HTTPRoute tương thích hoặc proxy khác có header canary:
curl -v \
  --cacert /path/to/lab-root-ca.pem \
  --resolve api.example.test:8443:127.0.0.1 \
  -H 'X-Release-Channel: canary' \
  https://api.example.test:8443/v1/orders
~~~

**Không kết luận request đã đi canary chỉ vì client gửi header.** Ví dụ NGINX ở trên **không** có header route; YAML Gateway API được minh họa cho **một deployment khác**. Phải xác nhận route qua response marker được cấp phép, backend/trace log hoặc rule metrics.

### 16.3. Xác minh TLS identity

~~~bash
openssl s_client \
  -connect 127.0.0.1:8443 \
  -servername api.example.test \
  -verify_hostname api.example.test \
  -verify_return_error \
  -CAfile /path/to/lab-root-ca.pem \
  -brief
~~~

Nếu certificate validation lỗi, kiểm tra SAN/chain/time/CA chính xác; **không bỏ `-verify_return_error`** chỉ để đạt kết quả có vẻ thành công. Với HTTP/3/QUIC cần công cụ và telemetry riêng; `openssl s_client` ở đây là kiểm tra **TCP/TLS**.

### 16.4. Kiểm tra NGINX configuration ở môi trường phù hợp

~~~bash
# Chỉ chạy khi máy lab có NGINX và quyền đọc cấu hình/cert phù hợp.
# Câu lệnh kiểm tra cú pháp, không tự reload dịch vụ.
nginx -t
~~~

Lệnh có thể cần quyền đọc/privilege tương ứng. **Kiểm tra cú pháp PASS không xác nhận routing, AuthZ hoặc path normalization an toàn**; phải chạy ma trận end-to-end với các backend và policy tương ứng.

### 16.5. Thử path normalization có kiểm soát

Trong môi trường lab được phê duyệt, dùng client giữ nguyên request path để so sánh cách edge và backend parse:

~~~bash
# Thử path có dot segment nhằm xác nhận policy, không khai thác hệ thống thật.
curl -v --path-as-is \
  --cacert /path/to/lab-root-ca.pem \
  --resolve app.example.test:8443:127.0.0.1 \
  https://app.example.test:8443/api/v1/../admin/
~~~

Kết quả kỳ vọng phụ thuộc **policy chuẩn hóa đã thiết kế**; proxy có thể normalize trước match hoặc reject input. Backend AuthZ phải luôn bảo vệ admin resource. Không sử dụng thử nghiệm này làm căn cứ bypass một hệ thống ngoài quyền kiểm tra.

## 17. Ma trận kiểm thử positive và negative

| ID | Trường hợp | Kỳ vọng | Bằng chứng |
|---|---|---|---|
| P01 | `app.example.test/` | Route web pool đúng | Route ID, backend trace |
| P02 | `app.example.test/api/v1/orders` | Route API v1 | Access/backend logs |
| P03 | `app.example.test/api/v2/orders` | Route API v2 | Upstream selected và response |
| P04 | `api.example.test/v1/orders` | Route v1 theo hostname api | Virtual host + route log |
| N01 | Host ngoài allowlist | Không forward tới upstream có quyền | Default vhost logs/TLS behavior |
| N02 | Host và SNI/authority không tương thích | Hành vi theo policy, không leak sang tenant | SNI, HTTP version, route/421 evidence |
| N03 | `/admin/` từ public web | Không được truy cập admin chức năng | Proxy deny + backend AuthZ |
| N04 | Path `/api/v1/../admin/` hoặc encoded variants trong lab | Không bypass policy vào admin backend | Normalization, route logs, app AuthZ |
| N05 | `/api`, `/api/`, `/apix` | Match đúng semantics được định nghĩa | Route ID cho từng variant |
| N06 | Duplicate/conflicting authority/forwarded metadata | Reject/normalize đúng, không lấy input làm quyền | Parser/security log |
| P05 | Request header canary được policy cho phép | Route canary khi điều kiện phù hợp | Gateway/route/backend log |
| N07 | Client tự gửi header `X-Internal-Role` | Không được nâng quyền/truy cập admin | Identity/authorization decision |
| N08 | Client tự gửi `X-Forwarded-For` giả | Không vượt ACL hoặc rate limit theo trusted-IP policy | Source/trusted-proxy logs |
| P06 | Tài khoản hợp lệ vào API canary | Cùng policy AuthN/AuthZ như stable | Identity, API logs |
| N09 | User tenant A gọi tenant B qua Host/header | 403/deny ở app boundary | Tenant/object AuthZ |
| N10 | Một backend bị đánh unhealthy | Không gửi traffic trái policy, failover đúng | Health state, selected backend |
| P07 | Cân bằng nhiều instance | Distribution đúng expectation trong cửa sổ đo | Upstream/connection metrics |
| N11 | Non-idempotent POST gặp retryable failure | Không tạo giao dịch trùng | App idempotency/event logs |
| P08 | HTTPS IPv4/IPv6 qua edge đã cấu hình | Cùng hostname/route/security outcome | Dual-stack route/test |
| N12 | HTTP/3/QUIC hoặc HTTP/2 policy drift | Không mở route khác trái phép | Transport-specific ingress tests |
| N13 | Direct origin IP/port | Không bypass WAF/identity rules | Firewall/private ingress logs |
| P09 | CDN/region failover | Route/cert/auth giữ đúng khi chuyển PoP | Regional SLO, TLS/route ID |
| N14 | Shared cache qua hai tenant | Không trả dữ liệu tenant khác | Cache headers/key và negative app tests |
| P10 | Route change/canary rollback | Restore expected route và latency/error rate | Config version, change ticket, SLO |
| N15 | Unauthorized namespace gắn HTTPRoute vào Gateway | Bị từ chối theo route admission policy | Resource status/RBAC/allowedRoutes |

Các ca `deny` cần điểm đối chứng: server đích **đang hoạt động** và role được phép vẫn kết nối thành công nếu policy yêu cầu. Timeout tới server đã tắt **không chứng minh firewall/reverse proxy đã chặn**.

## 18. Troubleshooting theo lớp

| Triệu chứng | Giả thuyết cần kiểm tra | Cách phân biệt |
|---|---|---|
| Tên miền không phân giải | DNS, TTL, split-horizon, internal resolver | DNS answer và authority trước TLS |
| TLS handshake/certificate lỗi | SNI/SAN/chain, default server, cert rotation | TLS alerts, cert chain, SNI |
| Request tới sai upstream | Host/path match, precedence, header, fallback | Route ID, config version, backend access |
| Một path 404, path khác OK | Prefix/rewrite/trailing slash, backend router | Proxy `$uri`/`$request_uri` behavior, app logs |
| `/admin` bị chặn nhưng `/admin/` mở | Exact/prefix mismatch | Normalized path, rule precedence, app AuthZ |
| Header canary không có tác dụng | Policy chưa attach, header case/value hoặc wrong gateway | HTTPRoute conditions/controller logs |
| Chỉ một PoP trả khác | Config drift, certificate/key khác, CDN cache | Region, route version, edge logs |
| Rate-limit nhầm khách | Proxy IP bị coi client IP, NAT nhiều người | Trusted chain, peer vs user attribution |
| CDN cache lộ response khác user | Cache key, `Vary`, cookies, private response | Cache rules, tenant tests, app logs |
| 502/503/504 | Upstream unavailable, DNS route, timeout, TLS origin | Proxy error/upstream health/latency |
| Chỉ HTTP/2 hoặc HTTP/3 lỗi | Protocol translation, authority, routing config | H1/H2/H3 regression tests |
| Backend OK nhưng user 403 | WAF/identity/authorization; không phải luôn route sai | Decision point và request trace |
| Blue-green rollback không khôi phục | Database schema/session không tương thích | Application version và migration log |

**Đi từ ngoài vào trong:** DNS → TLS identity → HTTP authority → path/header parser → route selection → upstream health → firewall/mTLS → application authorization/data. Giữ request ID xuyên các hop giúp tìm được **điểm quyết định thật** thay vì đoán từ mã HTTP cuối cùng.

## 19. Runbook thiết kế và triển khai routing an toàn

### Bước 1 — Kiểm kê entry points

Liệt kê DNS names, TLS termination, SNI/SAN, IPv4/IPv6, HTTP/1.1/2/3, CDN/WAF, ingress controller, Gateway listeners, private origin và direct bypass paths. Xác định ứng dụng/tenant owner.

### Bước 2 — Phác thảo route table theo security zone

Tạo bảng `host + path + header/condition → route/backend → auth policy`. Ghi exact/prefix semantics, fallback, redirect/rewrite và case/encoding. Không cho wildcard route tự động trỏ tới admin/management zone.

### Bước 3 — Định nghĩa trust model cho metadata

Ghi nguồn **client-controlled vs trusted-generated** cho từng header. Phân biệt raw `Host`, SNI, `:authority`, `Forwarded`/`X-Forwarded-*`, identity assertion, canary cohort. Chỉ hop được phép mới có quyền tạo identity headers; backend không được tin một field tự khai.

### Bước 4 — Bảo vệ upstream và quyền ứng dụng

Giới hạn network path từ edge tới backend, TLS/mTLS certificate verification khi áp dụng, service account/IAM, firewall/segmentation, app AuthN/AuthZ và tenant separation. Cấm backend origin bypass nếu không được thiết kế.

### Bước 5 — Viết cấu hình có kiểm soát

Thêm rule cụ thể, safe default, health/timeouts, logs không lộ token, caching policy và rate limits. Với Kubernetes Gateway API, xác minh listener permission, namespace access, backend cross-namespace references, resource status và route conflicts.

### Bước 6 — Test canary có negative cases

Kiểm thử route expected + unexpected host, `:authority`/SNI mismatch, path normalization, header spoofing, direct origin, AuthZ cross tenant, cache, HTTP/2/3, dual-stack, upstream failure. So cả route ID với endpoint và app decision.

### Bước 7 — Rollout và rollback

Version hóa config/manifest, ghi owner/ticket, đặt error/latency thresholds, traffic canary, quan sát SLO và rollback nếu phát hiện route sang sai security zone. Nếu backend schema thay đổi, rollback cần phối hợp app/data.

### Bước 8 — Duy trì liên tục

Khi thêm hostname, path API, tenant, cloud region hoặc CDN PoP, review lại route conflicts, certificates, DNS, controller policies, cache, H2/H3 và security-control coverage. Xóa route orphan để giảm bề mặt tấn công.

## 20. Bài tập tình huống: canary header làm rối tenant

**Bối cảnh giả định:** Doanh nghiệp có một edge TLS và ba upstream: `web`, `api-stable`, `api-canary`. Website `app.example.test` dùng `/api/` cho API, và `api.example.test` phục vụ SDK mobile. Một nhóm nhân viên được phép thử canary. Nhóm phát triển đã tạo rule:

~~~text
Nếu X-Release-Channel = canary:
    chuyển tới api-canary
Ngược lại nếu path bắt đầu /api:
    chuyển tới api-stable
Ngược lại:
    chuyển tới web
~~~

Tuy nhiên rule chỉ xét header/path mà **không kiểm tra hostname và danh tính**. Ứng dụng canary còn bật một endpoint `/debug/` có khả năng đọc thông tin của nhiều tenant. Cùng lúc CDN cấu hình cache key chỉ theo `path`, bỏ qua hostname.

### 20.1. Phân tích vấn đề

1. Vì sao `X-Release-Channel` do client gửi không phải bằng chứng người đó thuộc nhóm canary?
2. Vì sao rule `path bắt đầu /api` có thể bắt nhầm `/apix` hoặc bị xử lý khác giữa các proxy?
3. Khi bỏ hostname khỏi cache key, hai host có path giống nhau có thể gặp rủi ro gì?
4. Vì sao đưa `/debug/` lên canary là vấn đề **authorization/exposure**, không chỉ lỗi routing?
5. Các header `X-Forwarded-For`/`X-Forwarded-Host` có thể ảnh hưởng tới audit, redirect hoặc rate limit như thế nào?
6. Nếu CDN đổi sang HTTP/3 trong một PoP, có thể dựa vào test HTTP/1.1 duy nhất không?
7. Hãy đề xuất rule table, canary strategy, cache policy và ma trận regression phù hợp.

### 20.2. Gợi ý giải quyết

| Vấn đề | Hướng xử lý |
|---|---|
| Header canary không tin cậy | Cohort theo identity đã xác minh, edge **ghi đè** metadata; mọi backend cùng AuthZ |
| Thiếu host allowlist | Exact hostname + route scope; unknown host safe deny |
| Prefix rộng | Dùng segment-aware/exact/prefix semantics được kiểm thử; normalize path trước policy |
| API debug canary | Không expose trên public ingress; bảo vệ riêng theo network, identity và application |
| Cache key thiếu authority/tenant | Tắt shared caching cho response private; thiết kế cache key/Vary phù hợp và test chéo tenant |
| Proxy header chain | Trusted proxy list, strip client input, log source/identity rõ |
| Canary và protocol drift | Canary với giới hạn traffic, H1/H2/H3 + IPv4/IPv6, regional tests |
| Rollback | Config version + backend compatibility + SLO/authorization evidence |

**Bài học:** một request được đưa đúng pool vẫn có thể sai an ninh nếu tenant/user không được xác minh. Một request có header giống “nội bộ” vẫn là dữ liệu từ client nếu không có chứng cứ xác thực. Và **nếu cache, CDN, reverse proxy, API cùng phân tích URL/headers khác nhau**, ranh giới tin cậy có thể vỡ tại một hop không được quan sát.

## 21. Checklist routing theo hostname, path và header

- [ ] Phân biệt forward proxy, reverse proxy, load balancer L4 và L7.
- [ ] Biết DNS, SNI, HTTP Host và `:authority` có vai trò riêng; không tự đồng nhất chúng.
- [ ] Đã kiểm soát hostname allowlist, wildcard ownership, unknown host và SNI/authority policy.
- [ ] Có bảng route rõ `host + path + header → backend`, default safe và owner.
- [ ] Path semantics ghi rõ exact/prefix/regex, segment matching, trailing slash và case.
- [ ] Kiểm thử normalization: percent-encoding, dot segments, `//`, rewrite và query.
- [ ] Không dùng chặn path ở proxy như cách duy nhất bảo vệ admin/tenant.
- [ ] Không dùng raw Host, `X-Backend` hoặc header client để chọn arbitrary upstream.
- [ ] Đã phân loại và bảo vệ `Forwarded`, `X-Forwarded-For`, `X-Forwarded-Proto`, `X-Forwarded-Host`.
- [ ] Identity/role/tenant header chỉ được tin sau xác minh nguồn hoặc chữ ký theo thiết kế.
- [ ] Canary theo header không cấp quyền cao hơn stable; cohort nguồn đáng tin.
- [ ] Gateway/Ingress routes có quyền namespace/listener/backend theo least privilege.
- [ ] TLS termination ở mọi hop được nhận diện; origin ingress và mTLS/TLS khi phù hợp đã được kiểm tra.
- [ ] Health/readiness, timeout, retry, idempotency và các trường hợp backend failover có test.
- [ ] Cache key và chính sách private data không cho cross-tenant response leakage.
- [ ] H1/H2/H3, dual-stack, CDN PoP và service mesh behavior được đối chiếu.
- [ ] Có positive/negative tests cho unknown host, restricted path, header spoofing, tenant khác, origin bypass.
- [ ] Logs có route ID, backend, config version, request ID, WAF/auth decision, không lộ tokens/PII.
- [ ] Có canary rollout, giới hạn blast radius, tiêu chí rollback và runbook ứng dụng/schema.
- [ ] Review rule khi đổi DNS, TLS certificate, API hostname/version, tenant, CDN hoặc region.

**Ghi nhớ:** **Routing L7 trả lời “request đi đâu”, không trả lời “người gọi được phép làm gì”**. Thiết kế đúng đòi hỏi **xác định authority đáng tin, chuẩn hóa path nhất quán, không tin header client tự khai, precedence và fallback rõ**, bảo vệ kết nối tới upstream, xác thực và phân quyền ở ứng dụng, rồi **kiểm thử negative cases và quan sát route thực tế** trước mỗi lần thay đổi.
