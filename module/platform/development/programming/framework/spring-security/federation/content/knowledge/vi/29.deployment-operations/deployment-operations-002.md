# Chỉ tin Forwarded hoặc X-Forwarded-* từ proxy được kiểm soát

> **Module:** Spring Security – federation. **Nhóm kiến thức:** Triển khai và vận hành. Bài Knowledge README này hướng dẫn thiết kế ranh giới tin cậy cho HTTP forwarding headers khi ứng dụng Spring Security đặt sau reverse proxy, ingress, load balancer hoặc CDN. Trọng tâm là **chỉ sử dụng `Forwarded` / `X-Forwarded-*` do proxy đã được kiểm soát tạo hoặc làm sạch**, không coi header tự khai từ trình duyệt là chứng cứ về client IP, scheme, host, port hay path. Các tác động đặc biệt quan trọng với OAuth2/OIDC `redirect_uri`, SAML2 ACS/Destination/Recipient, CAS redirects, session cookies, bảo mật HTTPS, tenant routing và kiểm toán.

## 1. Tuyên bố cốt lõi

**HTTP Forwarded headers là metadata định tuyến, không phải thông tin đã được xác thực.** Client bất kỳ có thể tự gửi:
- `Forwarded: for=...;proto=...;host=...`.
- `X-Forwarded-For: ...`.
- `X-Forwarded-Proto: ...`.
- `X-Forwarded-Host: ...`.
- `X-Forwarded-Port: ...`.
- `X-Forwarded-Prefix: ...`.

Ứng dụng không thể suy ra một header được proxy đáng tin cậy tạo chỉ vì nó tồn tại. **Chỉ tin dữ liệu đã qua ranh giới ingress đáng tin, bị xóa/ghi đè từ input ngoài và được chuyển tới backend trên một kênh có kiểm soát.**

Nếu reverse proxy đã xác thực và chuẩn hóa các trường này thì chúng giúp Spring biết external public URL thực. Nếu proxy chuyển nguyên header của client vào Spring, attacker có thể khiến ứng dụng tin địa chỉ, scheme hoặc host sai.

### 1.1. Quy tắc triển khai ngắn gọn

1. **Chặn truy cập trực tiếp** từ Internet vào port backend Spring; chỉ proxy được định danh có thể kết nối.
2. **Tại edge of trust**, xóa mọi incoming `Forwarded` và họ `X-Forwarded-*` trước khi dựng bộ headers mới.
3. **Chỉ proxy do tổ chức kiểm soát mới sinh giá trị public origin**, dựa trên TLS/virtual host đã xác minh, không sao chép giá trị do client tự khai.
4. Nếu có nhiều proxy, xác định **hops nào được tin** và xử lý chuỗi địa chỉ theo đúng trust semantics, không tin phần tử đầu tiên một cách mù quáng.
5. Spring Boot chỉ bật `server.forward-headers-strategy` tương ứng khi **đã bảo đảm** network boundary và sanitization.
6. Public scheme/host/port/prefix dùng để dựng URL phải qua **allowlist/canonical origin policy**, nhất là callback URL federation.
7. Phân biệt việc **chấp nhận forwarded data** với **chấp nhận credential/authenticated identity**; header này không bao giờ cấp `ROLE_ADMIN`, chọn IdP không phê duyệt hoặc xác minh user.

## 2. Vì sao Spring Security federation đặc biệt nhạy cảm?

Một topology phổ biến:

~~~text
Browser
   |
   | HTTPS https://login.example.org/saml2/authenticate/staff
   v
Reverse Proxy / WAF / Ingress / LB
   | terminates external TLS
   | connects to app via private HTTP or mTLS
   | rewrites scheme, host, port, client address
   v
Spring Boot on 10.23.0.21:8080
   |
   +-- OAuth2Login redirect_uri generation
   +-- SAML2 SP entityID / ACS URLs / metadata
   +-- Login redirect / RequestCache / session cookies
   +-- Client IP for audit and security decisions
~~~

Không có trusted forwarding, ứng dụng chỉ nhìn thấy:
~~~text
request.getScheme()     = "http"
request.getServerName() = "10.23.0.21"
request.getServerPort() = 8080
request.getRemoteAddr() = "10.23.0.8"  (proxy)
~~~

Trong khi địa chỉ người dùng dùng là `https://login.example.org`. Khi proxy cấp metadata đúng:
~~~http
X-Forwarded-Proto: https
X-Forwarded-Host: login.example.org
X-Forwarded-Port: 443
X-Forwarded-For: 198.51.100.77
~~~

Spring có thể suy ra external origin. **Nhưng nếu những header này do browser gửi và proxy không xóa/ghi đè**, các giá trị tương tự có thể là giả mạo. Tính đúng của origin ảnh hưởng trực tiếp đến OAuth2 redirect URI, SAML Assertion Consumer Service, cookie và redirect destination.

### 2.1. Hai nhóm lỗi đối lập

**Không tin forwarding dù proxy đã chuẩn hóa đúng:** Spring tạo callback `http://10.23.0.21:8080/...`, IdP từ chối `redirect_uri`, SAML Recipient/Destination mismatch hoặc cookie không đúng.

**Tin forwarding từ nguồn không kiểm soát:** Spring dựng callback/redirect đến host do attacker chọn, log client IP giả, sai trust tenant, bypass IP-based throttling hoặc tạo Host header poisoning.

Giải pháp không phải bật forwarded headers vô điều kiện. Phải xử lý **trust boundary trước**, rồi mới xử lý **URL correctness**.

## 3. Giải thích từng header

| Header | Thông tin muốn chuyển tiếp | Nguy cơ khi bị client sửa |
|---|---|---|
| `Forwarded` (RFC 7239) | `for`, `by`, `host`, `proto` theo từng hop | Giả client IP, host và scheme; khác parser |
| `X-Forwarded-For` | Danh sách client/proxy IP addresses | Bypass IP allowlist/rate limit, sai audit |
| `X-Forwarded-Proto` | External scheme `https` hoặc `http` | Redirect URI/cookie/scheme confusion |
| `X-Forwarded-Host` | Public host người dùng truy cập | Host poisoning, open redirect, IdP/tenant mix-up |
| `X-Forwarded-Port` | Public port | Callback URL/port mismatch |
| `X-Forwarded-Prefix` | Public path prefix proxy strip/rewrite | Sai context path, callback, link, route confusion |
| `X-Forwarded-Ssl` | Biến thể thể hiện TLS ở edge | Scheme inference không nhất quán |
| `X-Real-IP` | De-facto client IP từ proxy | Spoof nếu không normalize |
| `Host` | HTTP authority client yêu cầu | Cũng cần virtual-host validation, không chỉ forwarded host |

`X-Forwarded-*` là quy ước phổ biến, không được RFC 7239 chuẩn hóa như một bộ có semantics giống hệt. `Forwarded` có ngữ pháp chính thức nhưng **bản thân RFC không xác thực giá trị**; RFC 7239 §8.1 cảnh báo về khả năng sửa đổi header qua từng hop.

### 3.1. Forwarded chuẩn RFC 7239

Ví dụ:
~~~http
Forwarded: for=198.51.100.77;proto=https;host=login.example.org
~~~

Có thể có nhiều hops:
~~~http
Forwarded: for=198.51.100.77;proto=https;host=login.example.org, for=10.23.0.8;proto=http;host=app.internal
~~~

Trường `for` có thể dùng IPv6 trong dấu ngoặc và quoted string, cũng có thể có giá trị `unknown`/obfuscated identifier theo RFC. **Không tự viết parser bằng split đơn giản rồi dùng để xác thực client IP.** Những ví dụ Java ở cuối bài chỉ là mô hình minh họa trust policy, không phải bộ phân tích RFC 7239 production.

### 3.2. X-Forwarded-For dạng danh sách

~~~http
X-Forwarded-For: 192.0.2.99, 198.51.100.77
~~~

Ý nghĩa một danh sách phụ thuộc quy tắc **proxy append và các điểm đã sanitize**. Nếu một client có thể gửi `192.0.2.99` rồi proxy chỉ append IP thực `198.51.100.77`, **phần tử đầu tiên có thể hoàn toàn giả mạo**.

Để xác định địa chỉ đầu cuối dùng trong audit/IP policy, cần **đi từ socket peer đã được tin và duyệt chain về phía client đến địa chỉ đầu tiên không thuộc trusted proxies**, sau khi parse chuẩn và xử lý IPv4/IPv6/duplicate headers đúng. Cách này không sửa được topology mà một proxy thiếu tin cậy có thể giả cả chain; trust set và sanitization vẫn quyết định.

### 3.3. X-Forwarded-Prefix cần chính sách riêng

Khi public URL là `https://login.example.org/portal` còn backend phục vụ đường dẫn `/`, proxy có thể dùng `X-Forwarded-Prefix: /portal`. Nếu cho client kiểm soát prefix, đường dẫn logout, SAML ACS hoặc OAuth callback có thể bị dịch sai.

Ở các phiên bản Spring Framework mới, cách chọn xử lý `Forwarded` so với `X-Forwarded-*` và việc cho phép prefix có thể được cấu hình riêng. **Đối chiếu API/behavior đúng phiên bản**, không mặc định mọi constructor đều xử lý mọi header như nhau.

## 4. Ai là proxy được tin?

**“Proxy đáng tin” không chỉ là một IP private.** Tối thiểu cần:
- Proxy do bạn quản trị hoặc một bên đã có hợp đồng trust cụ thể.
- Connection tới backend chỉ từ proxy đó hoặc các IP/CIDR chính xác.
- Network isolation: firewall/security group/Kubernetes NetworkPolicy/Service firewall.
- Tốt hơn có mTLS hoặc xác thực workload identity trên đường proxy→backend khi threat model cần.
- Edge xóa/ghi đè headers từ request bên ngoài.
- Multi-hop không có đường vòng bỏ qua edge đã sanitize.
- Host/route/tenant do proxy validate trước khi forwarding.
- Có release/change control khi thêm LB/ingress mới.

**Không coi mọi IP 10.0.0.0/8 là trusted proxy** chỉ vì đó là RFC 1918. Trong một VPC, các workloads khác vẫn có thể nằm cùng dải private IP. Chỉ trust các địa chỉ thực sự thuộc gateway/ingress đã được bảo vệ.

### 4.1. Transport peer khác forwarded client IP

- `socket peer`: IP thực tế của kết nối tới backend; có nguồn từ TCP/transport layer, không phải `X-Forwarded-For`.
- `effective client IP`: địa chỉ client suy ra từ trusted proxies và chain.
- `unverified header value`: chuỗi do HTTP request khai; chưa có độ tin cậy.

Một lớp kiểm soát an toàn nên xác định **peer có phải trusted proxy không trước khi diễn giải forwarded data**. Trong một stack có filter/valve đã rewrite `getRemoteAddr()`, giá trị đó có thể là **effective IP**, không còn là raw transport peer; vì thế không tự xây allowlist dựa trên `getRemoteAddr()` sau filter rồi nghĩ mình đã xác thực trực tiếp proxy.

### 4.2. Chặn truy cập trực tiếp là điều kiện cơ bản

Nếu port `8080` của Spring có thể truy cập từ Internet hoặc từ mọi pod:
~~~text
Attacker -> Spring:8080
Header: X-Forwarded-Host: attacker.invalid
Header: X-Forwarded-Proto: https
~~~

và Spring dùng `server.forward-headers-strategy: framework`, framework có thể xử lý metadata do attacker tự khai. **Một framework filter không thay firewall**. Cần ràng buộc đường đi traffic trước; khi app cần direct admin/health traffic, dùng network endpoint/routing khác không xử lý forwarded headers hoặc policy cụ thể.

## 5. Edge of trust: xóa rồi tái tạo

Mẫu đúng:

~~~text
Untrusted browser headers
         |
         v
[Public edge proxy]
  - Reject invalid/unknown public Host
  - Strip ALL incoming Forwarded and X-Forwarded-*
  - Reconstruct allowed public origin from trusted listener/vhost
  - Set real observed client peer, not user-supplied values
  - Forward only to private backend
         |
         v
[Spring app]
  - Accept only this proxy path
  - Apply exactly one configured forwarded-header strategy
  - Validate public scheme/host/port/prefix against allowlist
~~~

**Quan trọng:** Cần loại bỏ **cả** `Forwarded` chuẩn **và** họ `X-Forwarded-*`, kể cả khi ứng dụng chỉ đọc một họ. Các thư viện, gateway hoặc downstream services khác có thể ưu tiên họ còn lại. Việc chỉ overwrite `X-Forwarded-Proto` nhưng để nguyên incoming `Forwarded: host=attacker.invalid` vẫn để lại một nguồn host poisoning.

### 5.1. Có nhiều reverse proxies

Với CDN → edge ingress → internal gateway → Spring:
1. Xác định điểm nào đầu tiên thực sự tin nguồn trước đó.
2. Edge strip incoming headers của client.
3. Edge tạo trusted public host/proto/port và observed client IP.
4. Internal gateway **chỉ** chấp nhận từ edge đã được xác thực.
5. Internal gateway preserve/normalize public origin theo **contract**; không vô tình thay thành scheme HTTP nội bộ.
6. Backend chỉ chấp nhận internal gateway; mọi hop cùng chain có trust/policy rõ.
7. Khi cần IP chain nhiều hop, xử lý proxy list theo right-to-left trusted-hop logic của product/library tương ứng.

**Không dùng một công thức chung cho mọi topology**. Nếu NGINX đang sau TLS-terminating LB, `$scheme` tại NGINX có thể là `http`, không phải public `https`; không đặt `X-Forwarded-Proto: $scheme` một cách mù quáng. Giá trị public HTTPS phải do proxy TLS đã tin xác nhận hoặc do cấu hình canonical origin cố định.

### 5.2. Không tin “proxy ở trong Kubernetes nên chắc chắn an toàn”

Kubernetes Service, pod CIDRs hoặc node private IPs không tự ngăn một pod khác gọi backend. Cần ingress path và NetworkPolicy/security groups. Nếu không thể chứng minh isolate, dùng `NONE` hoặc removeOnly rồi cấu hình public external base URL tĩnh ở nơi cần, thay vì tin HTTP headers.

## 6. NGINX edge: ví dụ strip và set lại forwarding

Ví dụ **chỉ cho topology NGINX trực tiếp terminate HTTPS public trên `login.example.org`, rồi proxy tới private Spring backend**. NGINX config này là một phần của cấu hình thực tế, cần bổ sung TLS policy/default server/firewall và kiểm NGINX version.

~~~nginx
server {
    listen 443 ssl;
    server_name login.example.org;

    ssl_certificate     /etc/nginx/tls/login.example.org.crt;
    ssl_certificate_key /etc/nginx/tls/login.example.org.key;

    location / {
        proxy_pass http://10.23.0.21:8080;

        # Exact approved public authority
        proxy_set_header Host login.example.org;

        # Drop client's standardized Forwarded header
        proxy_set_header Forwarded "";

        # Reconstruct allowed X-Forwarded metadata
        proxy_set_header X-Forwarded-Host login.example.org;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-Port 443;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Real-IP $remote_addr;

        # No public prefix in this topology
        proxy_set_header X-Forwarded-Prefix "";
        proxy_set_header X-Forwarded-Ssl "";
    }
}
~~~

Giải thích:
- `server_name` và default-server routing phải bảo đảm chỉ public hostname được phê duyệt đi vào ứng dụng. Unknown Host/SNI phải bị reject, không chuyển mặc định sang tenant bất kỳ.
- `proxy_set_header Forwarded ""` yêu cầu NGINX không chuyển tiếp header này; nếu gateway khác hỗ trợ những biến thể forwarding riêng, cũng phải strip chúng tại edge.
- `Host` và `X-Forwarded-Host` được đặt bằng **một canonical domain cố định**, không dùng raw `$http_host` cho auth-sensitive endpoints.
- `X-Forwarded-Proto https` đúng vì **chính NGINX là public TLS terminator** ở topology ví dụ.
- `X-Forwarded-For $remote_addr` chỉ an toàn khi `$remote_addr` là observed client peer tại trusted edge. Nếu NGINX nằm sau một LB/CDN, phải cấu hình trusted real-IP recovery hoặc trust contract ở LB.
- Không dùng `$proxy_add_x_forwarded_for` ở public edge nếu muốn loại bỏ XFF do client tự khai, vì biến này **append vào incoming header** thay vì overwrite.
- `ssl_certificate_key` trong NGINX là TLS private key của gateway, **không phải** IdP SAML signing key.
- Chỉ proxy trên mạng private không đồng nghĩa backend an toàn nếu client/pods còn đường truy cập trực tiếp.

### 6.1. Những header phải được xem xét đồng bộ

Ở deployment thật, review hết:
`Forwarded`, `X-Forwarded-For`, `X-Forwarded-Host`, `X-Forwarded-Proto`, `X-Forwarded-Port`, `X-Forwarded-Prefix`, `X-Forwarded-Ssl`, `X-Real-IP` và các vendor-specific alternatives mà stack có thể đọc.

Một số hệ thống có `True-Client-IP` hoặc `CF-Connecting-IP` từ CDN. **Chỉ trust** những headers đó từ địa chỉ/CDN connection đã phê duyệt, không chấp nhận khi request đến từ public Internet trực tiếp.

### 6.2. Cẩn thận với Host header

Dùng:
~~~nginx
proxy_set_header Host $http_host;
proxy_set_header X-Forwarded-Host $http_host;
~~~

trong một proxy không validate public hosts là **lựa chọn nguy hiểm** cho SSO. HTTP Host là dữ liệu của client, có thể có port, unicode/punycode hoặc tên miền attacker. Chỉ dùng dynamic host khi virtual hosts/tenant mapping đã whitelist và normalized rõ ràng; tốt hơn với federation registrations cố định là set canonical host cụ thể.

### 6.3. Không xóa headers ở sai điểm

Nếu edge proxy đã strip và reconstruct headers, internal gateway không nên lại xóa public info rồi set `X-Forwarded-Proto: http` theo backend hop. Cấu hình multi-hop cần contract:
- Hop nào chịu trách nhiệm về public scheme/host.
- Hop nào chịu trách nhiệm thực hiện client IP trust.
- Hop nào thêm `for` chain.
- Hop nào drop các alternate headers để tránh xung đột.
- Hop cuối cung cấp origin ổn định cho Spring.

Để audit, thể hiện rõ trên kiến trúc, không ghép bằng các mặc định của nhiều ingress controllers mà không kiểm tra.

## 7. Spring Boot: NONE, NATIVE, FRAMEWORK

Spring Boot hỗ trợ property:

~~~yaml
server:
  forward-headers-strategy: framework
~~~

Các giá trị chính (tên enum có thể thể hiện lowercase trong YAML):
- **NONE:** không suy diễn request origin từ `X-Forwarded-*` theo support của Boot; phù hợp khi backend không nằm sau trusted proxy hoặc dùng canonical external URLs tĩnh.
- **NATIVE:** dùng khả năng native của underlying web container, ví dụ Tomcat `RemoteIpValve`. Các loại headers và trust logic phụ thuộc container/version.
- **FRAMEWORK:** dùng Spring Framework `ForwardedHeaderFilter` cho Servlet hoặc `ForwardedHeaderTransformer` cho reactive/WebFlux, theo phiên bản.

**Không có giá trị nào tự biến một header không đáng tin thành đáng tin.** `FRAMEWORK` không mặc định whitelist remote peer theo CIDR; luôn phải có proxy sanitization và network boundary. Với `NATIVE`, phải kiểm chính xác trust policy của container, không dựa vào defaults rộng.

### 7.1. Khi nào dùng NONE?

- App nhận traffic trực tiếp và không có proxy đã kiểm soát.
- Host, scheme, port tạo callback từ cấu hình public base URL **tĩnh/approved** chứ không cần forwarded metadata.
- Bạn muốn removeOnly mọi forwarded data trước khi business handlers đọc nó.
- Không chắc trust boundary đã kín và chọn fail closed trong lúc sửa hạ tầng.

Cần xác nhận các thư viện/custom filters khác không vẫn tự đọc raw forwarding headers. `NONE` chỉ kiểm soát cơ chế do Boot thiết lập; không tự xóa mọi header khỏi HTTP request ở mọi code path.

### 7.2. Khi nào dùng FRAMEWORK?

- Có edge proxy đã strip/normalize tất cả forwarded headers.
- Cần Spring MVC nhận external scheme/host/prefix để tạo absolute redirects/links.
- Đã kiểm đúng constructor/behavior của Spring Framework version.
- Không cấu hình chồng nhiều filter/valves gây double rewriting.

**Không bật FRAMEWORK chỉ để giải quyết lỗi `redirect_uri` trong khi backend public vẫn truy cập trực tiếp.** Cần sửa topology trước.

### 7.3. Khi nào dùng NATIVE?

- Bạn chọn Tomcat/Jetty/Undertow native forwarding support.
- Container hỗ trợ trusted proxies và header parsing phù hợp.
- Team vận hành kiểm được real socket peer và CIDRs cụ thể.
- Muốn xử lý client IP/remote address tại container trước ứng dụng.

Không giả định NATIVE xử lý mọi thứ giống FRAMEWORK, nhất là prefix/path handling và `Forwarded` RFC. Hãy kiểm tài liệu container và test actual URLs trên runtime.

### 7.4. Tránh xử lý hai lần

Nếu Boot đã tự gắn `ForwardedHeaderFilter` khi `framework`, đừng tự tạo thêm một ForwardedHeaderFilter dùng lại headers mà không hiểu thứ tự. Tương tự, không kết hợp Tomcat `RemoteIpValve` rewrite với filter parse lại raw headers dẫn tới inconsistent origin/peer. Chọn **một pipeline ownership** rõ ràng và test.

## 8. ForwardedHeaderFilter và chế độ removeOnly

Theo Spring Framework, `ForwardedHeaderFilter`:
- Xử lý `Forwarded` hoặc họ `X-Forwarded-*` theo configuration/version.
- Wrap request/response để các hàm lấy scheme, host, port, remote address và redirect phản ánh public origin.
- Loại bỏ forwarded headers khỏi request được wrap để downstream không tự diễn giải lại.
- Phải có thứ tự phù hợp, trước các filters/components dựng request URL.
- Có chế độ `setRemoveOnly(true)` để **chỉ loại bỏ headers mà không dùng chúng**.

Ví dụ ý tưởng (không phải full bean):
~~~java
// Spring Framework, API/constructor phụ thuộc major release:
ForwardedHeaderFilter filter = obtainFrameworkFilterForVersion();
filter.setRemoveOnly(true);
// Register early, so downstream code never consumes untrusted
// Forwarded / X-Forwarded-* values.
~~~

`obtainFrameworkFilterForVersion()` là ký hiệu mô tả API do dự án tự đăng ký, **không phải method của Spring**. Khi triển khai thật dùng constructor/registration API tương ứng với Spring Framework release: một số phiên bản có constructor không đối số; phiên bản mới hơn có constructor chọn dùng chuẩn Forwarded hay họ X-Forwarded. Đoạn snippet **không phải class compile độc lập**.

**Khi removeOnly=true, Spring không sử dụng forwarded public scheme/host**. Nếu ứng dụng vẫn cần external SSO callback, cấu hình public canonical origin một cách tin cậy ở registration/config, hoặc dùng proxy ingress đúng chuẩn rồi bật support đáng tin thay vì vô hiệu hóa chức năng cần thiết.

### 8.1. Thứ tự filter quan trọng

Nếu một filter tạo OAuth2 authorization request/callback URL trước khi forwarded wrapper được áp, URL có thể lấy origin nội bộ. Spring docs yêu cầu ForwardedHeaderFilter ở trước các request context consumers. Nếu đăng ký bằng `FilterRegistrationBean` thủ công, kiểm dispatcher types `REQUEST`, `ASYNC` và `ERROR` theo hướng dẫn framework và thứ tự tương ứng với SecurityFilterChain.

**Không dùng custom filter để “xác minh trusted peer” sau khi Tomcat/Spring đã rewrite `getRemoteAddr()`**, vì lúc đó raw peer có thể đã bị thay. Trust cần được cưỡng chế bởi networking/container stage biết socket peer thực.

## 9. Tomcat RemoteIpValve và trusted proxy rules

Trong Servlet Tomcat, `RemoteIpValve` có thể xử lý:
- `remoteIpHeader`, thường `x-forwarded-for`.
- `protocolHeader`, thường `x-forwarded-proto`.
- `internalProxies` và `trustedProxies` để quyết định chain nào được tin.
- Các trường host/port theo phiên bản/valve properties.

**Cảnh báo:** Defaults của Tomcat ở một số releases tin khá nhiều dải private/loopback như internal proxies. Đừng mặc định mọi pod/host trong RFC1918 là proxy của bạn. Hãy **thu hẹp CIDR/regex** cho các ingress addresses đã kiểm soát.

Một Spring Boot cấu hình tham khảo cho Tomcat ở runtime hỗ trợ tên properties này:

~~~yaml
server:
  forward-headers-strategy: native
  tomcat:
    remoteip:
      remote-ip-header: x-forwarded-for
      protocol-header: x-forwarded-proto
      internal-proxies: '10\.23\.0\.(8|9)'
~~~

Đây là **ví dụ cho hai IP proxy 10.23.0.8 và .9** với matcher pattern; cần kiểm property binding và cú pháp regex/CIDR đúng Tomcat + Spring Boot versions đang dùng. Cũng cần cấu hình host/port handling hoặc canonical public origin theo yêu cầu deployment. Trong một số releases, `server.tomcat.redirect-context-root: false` giúp tránh redirect context-root trước khi xử lý `X-Forwarded-Proto`; kiểm theo tài liệu phiên bản.

### 9.1. internalProxies vs trustedProxies

Theo Tomcat docs, `internalProxies` xác định proxies có thể được xem là nội bộ và bỏ qua trong một số proxy-chain summaries; `trustedProxies` có semantics riêng, được ghi trong `proxiesHeader`. Giá trị mặc định và format thay đổi theo Tomcat version (regex/CIDR). Không ghép một regex `.*` hay `0.0.0.0/0` để “cho mọi proxy là trusted”.

### 9.2. Nguy cơ của app-side rewritten remoteAddr

Một Tomcat valve có thể làm `request.getRemoteAddr()` phản ánh client IP đã được suy diễn từ XFF. Log cần biết đó là “effective IP”, không phải direct TCP peer. Nếu bạn lại dùng value đã rewrite để check request có đến từ trusted proxy hay không, kết quả sẽ sai. Giải pháp là network restriction, container trust handling và telemetry có phân biệt nguồn.

## 10. WebFlux/Reactive khác Servlet

Ứng dụng Spring WebFlux có `ForwardedHeaderTransformer` thay vì Servlet `ForwardedHeaderFilter`. Spring Boot `server.forward-headers-strategy: framework` có thể dùng transformer tương ứng. Không copy cấu hình `FilterRegistrationBean<ForwardedHeaderFilter>` vào Reactive stack rồi kết luận đã bảo vệ.

Security rules tương tự:
- Proxy edge sanitize header.
- Direct backend access blocked.
- Consistent public origin.
- Không trust arbitrary host/proto/for.
- WebFlux security và gateway có routing/filters riêng, cần integration tests.

Spring Cloud Gateway có thể forward/rewrite headers cho downstream; tuyệt đối không mặc định filter nào cũng strip giá trị client khai. Tra đúng Gateway release và khai báo trusted proxies/filter order tại từng hop.

## 11. OAuth2/OIDC: ảnh hưởng đến redirect_uri

Spring Security OAuth2 Login thường cấu hình redirect URI template:

~~~text
{baseUrl}/login/oauth2/code/{registrationId}
~~~

Ví dụ public URL:
~~~text
https://login.example.org/login/oauth2/code/staff
~~~

Nếu Spring nhìn thấy backend scheme/host nội bộ, nó có thể dựng:
~~~text
http://10.23.0.21:8080/login/oauth2/code/staff
~~~

IdP sẽ từ chối redirect URI vì không nằm trong registered callback allowlist. Ngược lại, nếu một forwarded host giả được chấp nhận, application có thể gửi `redirect_uri` không đáng tin vào authorization request; ảnh hưởng tùy exact IdP redirect URI validation, nhưng đây vẫn là lỗi nghiêm trọng về trust.

### 11.1. Bản chất lỗi

| Tình huống | Biểu hiện | Nguyên nhân |
|---|---|---|
| `X-Forwarded-Proto` thiếu | `redirect_uri` dùng HTTP nội bộ | App không biết public TLS |
| `X-Forwarded-Host` thiếu/sai | Redirect URI có private hostname | Host reconstruct sai |
| `X-Forwarded-Port` sai | Thêm `:8080` hoặc port khác | Port mismatch |
| Host giả từ client | Callback/Location/links chứa attacker host | Proxy không sanitize |
| Prefix giả | Callback bị thêm/bỏ path | Context path mismatch |
| Multiple host headers | Lib/parser lấy trường khác nhau | Header normalization thiếu |
| Callback thật đúng, session mất | OAuth2 state missing/invalid | Cookie/SameSite/session/ingress issues |

**Không xử lý bằng cách bỏ kiểm OAuth2 state, nonce hoặc IdP registered redirect URI.** Phải sửa proxy trust và URL construction.

### 11.2. Canonical callback là lớp phòng thủ bổ sung

Với một application có public domain cố định, có thể pin redirect URI trong ClientRegistration hoặc config:
~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          staff:
            redirect-uri: "https://login.example.org/login/oauth2/code/staff"
~~~

Đoạn này là **fragment**, cần đầy đủ client/provider config để đăng nhập. Một URI cố định giúp giảm nguy cơ host-influenced callback, nhưng app vẫn cần trusted forwarding cho redirect chung và session behavior. IdP phải register **exact URI**; không dùng wildcard callback vào arbitrary domains.

### 11.3. Issuer và client identity không lấy từ headers

`iss` của OIDC ID Token phải được kiểm bằng provider metadata/configuration đã tin. Không nhận `X-Forwarded-Host: tenant-b.example.org` rồi tự chọn một IdP hoặc client secret khác trừ khi routing đã được whitelist từ trust boundary và đúng account/tenant policy.

Ngay cả khi redirect_uri đúng, state/PKCE/nonce/token validation và local authorization vẫn bắt buộc.

## 12. SAML2: ACS, Destination, Recipient, EntityID

Với Spring Security SAML2 Login, public request origin ảnh hưởng:
- SP entityID trong `RelyingPartyRegistration`.
- Assertion Consumer Service location được công bố qua SP metadata.
- `Response.Destination` của IdP.
- `SubjectConfirmationData.Recipient` của Assertion.
- SAML `AuthnRequest.AssertionConsumerServiceURL` nếu dùng.
- SAML single logout URLs và post-login redirect.

Ví dụ public ACS:
~~~text
https://login.example.org/login/saml2/sso/staff
~~~

Backend thực:
~~~text
http://10.23.0.21:8080/login/saml2/sso/staff
~~~

Nếu server tạo metadata dựa origin nội bộ, IdP có thể gửi tới URL sai hoặc Spring reject response vì Recipient/Destination mismatch. Nếu app tin host giả của client, SP metadata/callback dựng trên origin không phê duyệt gây host injection hoặc sai relying-party registration.

### 12.1. Không “sửa SAML” bằng cách bỏ validation

Khi SAML báo:
- Destination mismatch.
- Recipient mismatch.
- ACS URL invalid.
- SP entityID/audience mismatch.

hãy kiểm external scheme/host/port/prefix và metadata/configuration của trusted proxies trước. **Không vô hiệu hóa SAML signature, audience, Destination, Recipient hoặc InResponseTo validation.** Những checks này đang bảo vệ SP khỏi nhận assertion không dành cho mình.

### 12.2. RelyingPartyRegistration nên dùng public URLs rõ ràng

Với môi trường có một public hostname cố định, cấu hình `entityId` và `assertionConsumerServiceLocation` thành các public HTTPS URLs đã được phê duyệt thay vì phụ thuộc toàn bộ vào request Host. Spring API/version có thể cho phép placeholder `{baseUrl}`, nhưng phải bảo đảm baseUrl suy ra từ trusted proxy hoặc public canonical config.

Cấu hình **IdP metadata** cũng cần đúng public IdP entityID và trusted signing keys; Forwarded headers **không** phải một SAML trust anchor. Không suy ra user identity/roles từ các HTTP headers.

### 12.3. Tách trust ở hai lớp

**Lớp transport/proxy:** xác minh public origin và đường đi từ browser tới app.

**Lớp SAML:** xác minh XML signature, IdP issuer/signing key, Audience, Recipient, Destination, Conditions và request correlation.

Ngay cả nếu public URL được dựng đúng thì SAMLResponse chưa ký hoặc sai issuer vẫn phải bị từ chối. Ngược lại signed assertion đúng nhưng ACS mismatch có thể bị reject một cách hợp lý.

## 13. CAS, Kerberos và các luồng khác

**CAS:** Service URL của CAS client thường chứa public scheme/host/path. Nếu app tin forwarded host giả, service URL/callback và service ticket validation có thể trật mục tiêu. Dùng canonical service URLs và CAS server validation, không bỏ service binding để “pass”.

**Kerberos/SPNEGO:** Kerberos HTTP service principal thường gắn với hostname/SPN mà browser truy cập, ví dụ `HTTP/login.example.org@EXAMPLE.ORG`. Reverse proxy/gateway và backend cần có SPNEGO topology, keytab và hostname contract rõ. Chỉnh `X-Forwarded-Host` không tự thay service principal, không thể hợp thức hóa một Kerberos ticket sai service/realm.

**Logout/OIDC front-channel callbacks:** Host/proto/prefix có thể ảnh hưởng logout redirect URIs. Luôn có allowlist post-logout redirect và session/cookie policies.

## 14. Session cookie, HTTPS và HSTS

Nếu client→proxy dùng HTTPS nhưng proxy→app dùng HTTP:
- Không kết luận browser là insecure chỉ từ raw `request.isSecure()` nội bộ; trusted forwarding có thể mô tả external HTTPS.
- Tuy vậy **cookie Secure nên được bảo đảm rõ** theo public HTTPS deployment, không chỉ trông chờ suy diễn scheme.
- Cần đúng Domain, Path, SameSite, HttpOnly, Secure; host injection có thể ảnh hưởng cookie Domain nếu code tự dựng cookies.
- HSTS nên được thiết lập ở public HTTPS edge/domain theo chính sách, tránh mixed-scheme redirects.
- Internal proxy→app connection vẫn phải được bảo vệ mạng; với dữ liệu nhạy cảm hoặc zero-trust network dùng TLS/mTLS đến backend.

Ví dụ Spring Boot cho public HTTPS session app:
~~~yaml
server:
  servlet:
    session:
      cookie:
        secure: true
        http-only: true
~~~

Đây là fragment, không giải quyết mọi SameSite/protocol case. **SAML HTTP-POST cross-site callback** có thể cần thiết kế SameSite phù hợp (trong một số tình huống cần `SameSite=None; Secure`), trong khi OAuth2 redirects và form POST có ràng buộc khác. Không thay đổi SameSite tùy tiện chỉ để che session correlation issues; phải test trên browsers thật.

### 14.1. CSRF không được thay bằng forwarded headers

`Forwarded`/`X-Forwarded-Proto` không phải CSRF tokens. Header `Origin` hoặc `Referer` cũng có thể là đầu vào cho CSRF/cross-origin policy; cần verify origin against approved external origin theo policy, không lấy một forwarded host chưa trusted để tự “hợp thức hóa” request cross-site.

Khi session bị mất do cookie flags, Spring OAuth2 state hoặc SAML InResponseTo có thể fail. Sửa cookie/proxy trust đúng, không tắt state/CSRF checks.

## 15. IP-based policy, rate limit và audit

X-Forwarded-For thường được dùng cho:
- IP rate limiting.
- Brute-force protection.
- Fraud/abuse telemetry.
- Geolocation/risk scoring.
- Security audit và operational tracing.
- Conditional allowlist của admin endpoints.

Nếu policy lấy **địa chỉ đầu tiên bất kể nguồn**, attacker có thể tự gửi nhiều IP giả và né hạn mức. Cần:
- Dựa vào raw socket peer để xác định proxy được tin.
- Chain parser đúng chuẩn của container/gateway.
- Trusted proxy CIDRs chính xác.
- Có chính sách với malformed/duplicate/IPv6 headers.
- Giới hạn IP-based checks là một lớp giảm rủi ro, không thay MFA, authentication hoặc resource authorization.
- Ghi log điều kiện suy diễn theo stage, phân biệt observed peer và effective client IP.

### 15.1. Hạn chế dùng IP như danh tính vững chắc

NAT, VPN, mobile networks, IPv6 privacy addresses và CDN làm client IP biến động. Đừng biến XFF-derived IP thành immutable user identity hoặc thay thế OIDC `iss+sub`/SAML stable subject. Forwarded IP chỉ phục vụ risk/operation theo chính sách.

## 16. Java 17 standalone: mô hình trust boundary của proxy

Ví dụ này chạy độc lập với JDK 17, **không dùng Spring, NGINX hay mạng thật**. Nó mô phỏng yêu cầu: request chỉ được lấy public scheme/host/for khi transport peer thuộc trusted proxy và gateway đã **sanitize một-hop headers**.

Tệp `TrustedForwardedDemo.java`:

~~~java
import java.util.Set;

public class TrustedForwardedDemo {

    private static final Set<String> TRUSTED_PEERS =
            Set.of("10.23.0.8");
    private static final String HOST = "login.example.org";

    record Request(
            String socketPeer,
            String forwardedProto,
            String forwardedHost,
            String forwardedFor) {
    }

    static String decide(Request r) {
        if (!TRUSTED_PEERS.contains(r.socketPeer())) {
            return "REJECT_UNTRUSTED_PEER";
        }

        if (!"https".equals(r.forwardedProto())) {
            return "REJECT_PROTO";
        }

        if (!HOST.equals(r.forwardedHost())) {
            return "REJECT_HOST";
        }

        if (r.forwardedFor() == null
                || r.forwardedFor().isBlank()
                || r.forwardedFor().contains(",")) {
            return "REJECT_UNSANITIZED_CHAIN";
        }

        return "ACCEPT:https://" + HOST;
    }

    public static void main(String[] args) {
        Request valid = new Request(
                "10.23.0.8", "https",
                "login.example.org", "198.51.100.77");

        Request direct = new Request(
                "203.0.113.9", "https",
                "login.example.org", "198.51.100.77");

        Request hostSpoof = new Request(
                "10.23.0.8", "https",
                "attacker.invalid", "198.51.100.77");

        Request protoSpoof = new Request(
                "10.23.0.8", "http",
                "login.example.org", "198.51.100.77");

        Request unsanitized = new Request(
                "10.23.0.8", "https",
                "login.example.org",
                "192.0.2.99, 198.51.100.77");

        System.out.println("trusted=" + decide(valid));
        System.out.println("direct=" + decide(direct));
        System.out.println("host-spoof=" + decide(hostSpoof));
        System.out.println("proto-spoof=" + decide(protoSpoof));
        System.out.println("unsanitized=" + decide(unsanitized));
    }
}
~~~

Lệnh:
~~~bash
javac TrustedForwardedDemo.java
java TrustedForwardedDemo
~~~

**Stdout chính xác:**
~~~text
trusted=ACCEPT:https://login.example.org
direct=REJECT_UNTRUSTED_PEER
host-spoof=REJECT_HOST
proto-spoof=REJECT_PROTO
unsanitized=REJECT_UNSANITIZED_CHAIN
~~~

**Giải thích:**
- Trusted peer + scheme + canonical host + sanitized single client-address field mới được chấp nhận.
- Direct peer dù có forged headers cũng bị reject.
- Host và proto giả không thể đổi callback origin.
- Demo từ chối chain nhiều hops vì policy cố ý chỉ hỗ trợ edge đã sanitize thành một địa chỉ.

**Giới hạn nghiêm ngặt:** String `socketPeer` trong record chỉ là đại diện cho **transport IP do mạng/container cung cấp**, không phải giá trị do HTTP client gửi. Không nhận record JSON từ client rồi tin. Code chưa parse IP address thực, IPv6, IPv4-mapped IPv6, RFC 7239 quoted strings, proxy hops, TLS identity hay Host normalization. **Không dùng class này như một production ForwardedHeaderFilter hoặc bảo vệ duy nhất**. Production enforcement thuộc ingress/network/container trust và framework được kiểm định.

## 17. Java 17 standalone: vì sao không lấy IP đầu tiên của XFF

Demo thứ hai cho thấy việc duyệt danh sách XFF từ **trusted direct socket peer về phía client**, thay vì chọn phần tử đầu tiên. Mã chỉ xử lý chuỗi IPv4 đơn giản minh họa, **không phải parser XFF đầy đủ và không hỗ trợ RFC7239**.

Tệp `ProxyHopDecisionDemo.java`:

~~~java
import java.util.Set;

public class ProxyHopDecisionDemo {

    static String closestUntrusted(
            String xForwardedFor,
            String socketPeer,
            Set<String> trustedProxies) {

        if (!trustedProxies.contains(socketPeer)) {
            return "REJECT_UNTRUSTED_PEER";
        }

        if (xForwardedFor == null
                || xForwardedFor.isBlank()) {
            return "REJECT_MISSING_CHAIN";
        }

        String[] hops = xForwardedFor.split(",", -1);
        for (int i = hops.length - 1; i >= 0; i--) {
            String hop = hops[i].trim();
            if (hop.isEmpty()) {
                return "REJECT_MALFORMED_CHAIN";
            }

            if (!trustedProxies.contains(hop)) {
                return hop;
            }
        }

        return "REJECT_NO_UNTRUSTED_CLIENT";
    }

    public static void main(String[] args) {
        Set<String> correctTrust = Set.of("10.23.0.8");
        Set<String> dangerouslyBroadTrust =
                Set.of("10.23.0.8", "198.51.100.77");

        System.out.println("sanitized=" +
                closestUntrusted("198.51.100.77",
                        "10.23.0.8", correctTrust));

        System.out.println("client-spoofed-left=" +
                closestUntrusted(
                        "192.0.2.99, 198.51.100.77",
                        "10.23.0.8", correctTrust));

        System.out.println("overtrusted=" +
                closestUntrusted(
                        "192.0.2.99, 198.51.100.77",
                        "10.23.0.8", dangerouslyBroadTrust));

        System.out.println("direct=" +
                closestUntrusted(
                        "198.51.100.77",
                        "203.0.113.9", correctTrust));

        System.out.println("missing=" +
                closestUntrusted("", "10.23.0.8",
                        correctTrust));
    }
}
~~~

Chạy:
~~~bash
javac ProxyHopDecisionDemo.java
java ProxyHopDecisionDemo
~~~

**Stdout chính xác:**
~~~text
sanitized=198.51.100.77
client-spoofed-left=198.51.100.77
overtrusted=192.0.2.99
direct=REJECT_UNTRUSTED_PEER
missing=REJECT_MISSING_CHAIN
~~~

Trong một chain mà edge append địa chỉ thực, thông tin bên trái có thể do client khai. Nếu trust set chính xác chỉ gồm gateway 10.23.0.8, ngay sau nó là untrusted client 198.51.100.77. Nếu nhầm 198.51.100.77 thành trusted proxy, parser đi tiếp tới 192.0.2.99 đã bị spoof. Đây là lý do **trust proxy CIDRs phải chính xác**.

**Production caveat:** Cần parser IP/chains có bảo vệ chặt chẽ, không chỉ `String.split(",")`: IPv6/ports, duplicated headers, whitespace, RFC7239 `unknown`/obfuscated values, chain length, NAT/CDN, network ACLs, multiple hops, PROXY protocol và IP canonicalization. Hãy dùng năng lực container/ingress được kiểm định thay vì sao chép demo làm security code.

## 18. Servlet test: mô phỏng host/proto trong MockMvc

MockMvc có thể giúp kiểm URL generation và security rules, nhưng **gửi header trực tiếp tới MockMvc không chứng minh proxy đã sanitize hoặc backend đã chặn direct traffic**. Phải có full proxy integration test riêng.

Một controller diagnostic chỉ trong test (fragment Spring MVC):

~~~java
@RestController
class PublicOriginProbeController {

    @GetMapping("/__test/origin")
    String origin(HttpServletRequest request) {
        return request.getScheme() + "://"
                + request.getServerName() + ":"
                + request.getServerPort();
    }
}
~~~

Các imports cần cho project:
~~~java
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
~~~

Đây là **Spring class fragment**, không phải JDK17 standalone. Trong test profile có thể dựng request:
~~~java
mvc.perform(get("/__test/origin")
        .header("X-Forwarded-Proto", "https")
        .header("X-Forwarded-Host", "login.example.org")
        .header("X-Forwarded-Port", "443"));
~~~

Nếu test đã đăng ký đúng filter và policy, response mô phỏng effective origin; nếu chưa bật forwarding, Spring có thể trả origin của mock request. **Không gắn expected universal stdout cho fragment này**, vì kết quả phụ thuộc MockMvc filter registration, Spring Boot strategy và phiên bản. Route này tuyệt đối không expose public production, vì có thể tiết lộ routing internals.

### 18.1. Integration test ở NGINX/ingress thực

Bắt buộc test:
- Request public HTTPS với **forged X-Forwarded-Host** trong inbound request → backend vẫn thấy canonical host.
- Request public HTTPS với **forged Forwarded** → backend không đọc/ưu tiên header tấn công.
- Request public HTTPS với **forged X-Forwarded-Proto: http** → Spring vẫn generate public HTTPS redirect.
- Request có duplicate/combined conflicting headers → reject hoặc normalized theo policy, không dùng attacker value.
- Direct request tới backend IP/port từ outside trusted network → bị chặn tại network layer.
- Legitimate proxy request → OAuth2 redirect URI/SAML metadata chứa đúng public origin.
- Multi-hop với CDN/LB/ingress → scheme/host/client IP đúng ở mọi node.
- Reverse proxy restart/rollover → không mở lại port backend trực tiếp.

## 19. curl smoke tests an toàn

Từ một máy test được phép truy cập public endpoint, có thể kiểm response headers (tránh in cookies/tokens trong ticket):

~~~bash
curl -si \
  https://login.example.org/saml2/service-provider-metadata/staff

curl -si \
  -H 'Forwarded: for=192.0.2.99;proto=http;host=attacker.invalid' \
  -H 'X-Forwarded-Host: attacker.invalid' \
  -H 'X-Forwarded-Proto: http' \
  https://login.example.org/saml2/service-provider-metadata/staff
~~~

Đây là **hướng dẫn kiểm thử phòng thủ trên môi trường được ủy quyền**, không nhắm hệ thống bên ngoài. Test phải xác nhận metadata SP entityID/ACS **không** bị đổi sang attacker.invalid và public scheme vẫn HTTPS; upstream có thể reject headers thay vì tự sửa. Đừng lưu raw SAML assertions/cookies từ output của `curl -si` vào logs công khai.

### 19.1. Kiểm OAuth2 authorize redirect

Trong môi trường test với valid client registrations:
- Gọi URL bắt đầu đăng nhập cho registration.
- Kiểm `Location` sang IdP chứa `redirect_uri` đã URL-encode đúng public canonical callback.
- Lặp lại với forged Forwarded/X-Forwarded headers.
- Kỳ vọng URI vẫn là approved public URI, hoặc request bị reject; không chứa host attacker.
- Không coi việc IdP từ chối mismatch là bằng chứng proxy đã an toàn; cần ngăn host poisoning ngay tại ingress/app boundary.

### 19.2. Kiểm SAML metadata và assertion callback

Đối chiếu:
- SP entityID trong generated metadata.
- AssertionConsumerService Location.
- IdP-configured ACS/recipient.
- Response Destination và SubjectConfirmationData Recipient.
- Reverse proxy public scheme/host/port.
- RelyingPartyRegistration của đúng IdP/tenant.

Test SAML signature/conditions riêng: proxy header sanitization không thay XML signature validation.

## 20. Kiểm tra Host, Port, Scheme, Prefix theo allowlist

Một proxy đã sanitize là tiền đề, nhưng ứng dụng có thể bổ sung **origin allowlist** với:
- Scheme HTTPS.
- Hostname chính xác từ approved set, đã normalize/canonicalize.
- Port 443 (hoặc port public chính xác).
- Path prefix cho từng registration/tenant.
- Không có userInfo, control characters, unexpected ports, untrusted punycode/homograph hosts.
- Unknown host → reject hoặc route sang safe default không thực hiện SSO.
- Return/success/logout redirects → chỉ tới URLs đã phê duyệt.

**Tránh kiểm suffix thô**:
~~~java
// KHÔNG ĐỦ: attacker-example.org có thể vượt qua
// một điều kiện endsWith("example.org") bất cẩn.
boolean allowed = userProvidedHost.endsWith("example.org");
~~~

Ưu tiên exact host allowlist hoặc kiểm domain boundary đúng với dot separator sau canonicalization/IDNA theo security policy. Chỉ dùng multi-tenant dynamic hosts nếu tenant mapping và issuer trust đã được approved server-side.

### 20.1. Không tự chọn IdP theo Host chưa verified

Một app dùng `staff.example.org` và `partners.example.org` có thể cần hai SAML registrations. Nhưng host routing phải do ingress/server allowlist quyết định. Nếu client tự đặt `X-Forwarded-Host: staff.example.org` từ entrypoint partners rồi server chọn staff IdP trust, có thể tạo tenant/IdP mix-up.

Không bao giờ suy luận approved realm/issuer, signing key hoặc localUserId chỉ từ một HTTP forwarding header.

## 21. Kubernetes, ingress và service mesh

Ở Kubernetes:
1. Chỉ `Ingress Controller`/Gateway API route được Internet tới service.
2. NetworkPolicy chặn pods không được phép truy cập backend port.
3. Load balancer/ingress config xác định trusted upstream CIDRs.
4. Nếu đi qua managed load balancer/CDN, cấu hình real-IP handling chỉ từ IP ranges của nhà cung cấp đã verified.
5. Ingress phải strip và tái tạo Forwarded và X-Forwarded-* theo product-specific config.
6. Service mesh sidecar có thể thêm/chỉnh headers; kiểm toàn bộ hop sequence.
7. External TLS termination làm `X-Forwarded-Proto` có thể phải preserve từ outer trusted hop thay vì dùng scheme HTTP nội bộ.
8. `X-Forwarded-Prefix` phải khớp path rewrite, không phải do caller tự khai.
9. Ingress/SPA/callback route phải share compatible cookie/SameSite/session state.
10. Chỉ expose health/actuator qua control plane/private access nếu không có lý do công khai.

**Không paste một annotation ingress** từ bản Kubernetes khác mà không kiểm controller/version. NGINX Ingress, AWS ALB, Envoy, Traefik và Spring Cloud Gateway có các mặc định/quy tắc khác nhau; đặc biệt khi trust upstream headers.

### 21.1. PROXY protocol khác HTTP Forwarded headers

Một load balancer có thể gửi **PROXY protocol** ở transport connection để chuyển client IP. Đây không phải header HTTP `Forwarded`. Nếu dùng, listener/parser phải cấu hình đúng và chỉ chấp nhận PROXY protocol từ trusted LB; không để Internet clients tự viết một PROXY line tới public backend. Không trộn raw PROXY protocol data với XFF parsing mà thiếu một trust chain nhất quán.

## 22. Header conflicts, precedence và parser ambiguities

Những trường hợp cần reject hoặc canonicalize có kiểm soát:

| Input | Nguy cơ | Policy |
|---|---|---|
| `Forwarded` host=A, `X-Forwarded-Host`=B | Hai thư viện chọn hai hosts khác nhau | Edge strip cả hai, phát một họ canonical |
| Hai dòng `X-Forwarded-Proto` khác nhau | Merge/last-value inconsistency | Reject/normalize tại ingress |
| `X-Forwarded-Host` có comma list | Một lib lấy first, lib lấy last | Reject unexpected multi-values |
| `X-Forwarded-Port` có ký tự không số | URI parser confusion | Validate exact public port |
| `X-Forwarded-Prefix: //evil.example` | Path/URI interpretation | Strip và allowlist prefix |
| `Forwarded: proto=http` trên public HTTPS | Mixed-scheme / redirect issues | Overwrite từ TLS terminator |
| `X-Forwarded-For` với IP attacker bên trái | Rate-limit bypass nếu chọn first | Trust-chain parse từ raw peer |
| `Host` sai, XFH đúng | Host route confusion | Canonical host policy |
| IPv6 in Forwarded with quoted ports | Parser ambiguity | Dùng RFC-compliant parser |
| Proxy nhận raw UTF-8/control chars | Header injection/response splitting | Reject tại gateway/parser |

Đừng tự phát minh thứ tự ưu tiên cho hai families; chọn một contract được hỗ trợ bởi đúng framework release, bảo đảm proxy chỉ phát thông tin canonical tương ứng.

## 23. Negative tests phải kiểm đúng boundary

| ID | Tình huống | Expected |
|---|---|---|
| T01 | Trusted proxy + canonical https/host/port | App sees approved public origin |
| T02 | Direct external request to backend:8080 | Network deny |
| T03 | Browser gửi X-Forwarded-Host attacker.invalid | Edge overwrite/reject |
| T04 | Browser gửi Forwarded host attacker.invalid | Edge strip/reject |
| T05 | Browser gửi X-Forwarded-Proto http | Effective public scheme vẫn https |
| T06 | Browser gửi X-Forwarded-Port 8080 | Effective public port vẫn 443 |
| T07 | Browser gửi X-Forwarded-Prefix /evil | Prefix theo approved routing |
| T08 | Browser tự thêm X-Forwarded-For fake IP | Rate limit/audit không tin fake |
| T09 | Duplicate Forwarded/XFH conflicts | Reject/canonicalize |
| T10 | Multi-hop proxy chain đúng trust | Accurate effective client IP |
| T11 | Overbroad trusted CIDR | Security regression test fail |
| T12 | Unknown Host/SNI | Reject/route safe, không SSO tenant khác |
| T13 | OAuth2 redirect_uri sau login start | Exact public HTTPS callback |
| T14 | OAuth2 callback với state/nonce sai | Authentication reject |
| T15 | SAML metadata SP entityID/ACS | Public canonical URLs |
| T16 | SAML Destination/Recipient wrong | Reject SAML response |
| T17 | IdP issuer/signature wrong dù headers chuẩn | Reject SAML response |
| T18 | CAS service URL mismatch | Reject/fix canonical service |
| T19 | Kerberos SPN sai hostname | Kerberos validation fail, không sửa qua XFH |
| T20 | Callback session cookie mất sau TLS redirect | Correct cookie flags/network |
| T21 | SAML POST cross-site cookie behavior | Test SameSite correctly |
| T22 | Internal ingress tự set XFP=http | Regression, fix trusted hop |
| T23 | CDN sends trusted real-IP data from verified peer | IP mapping accurate |
| T24 | Untrusted pod calls backend with spoofed XFH | Network deny |
| T25 | Response Location generated by app under hostile Host | No attacker host |
| T26 | Return URL after login points external unapproved | Reject open redirect |
| T27 | Internal app uses `getRemoteAddr()` after rewrite as raw peer | Detect architecture bug |
| T28 | WebFlux and Servlet deployments mixed | Each uses correct transformer/filter |
| T29 | Spring Boot NATIVE + duplicated FRAMEWORK filter | Detect/dismantle double handling |
| T30 | Production config accidentally trusts staging proxy domain | Deployment guard fails |

**Các test nên chạy trong môi trường được ủy quyền, có proxy thật và host đã phê duyệt.** MockMvc-only tests không chứng minh firewall và NGINX đã strip headers.

## 24. Observability và logging an toàn

Ghi log nên phân biệt:
- Internal raw transport peer ở trusted ingress, nếu platform cho phép.
- Trusted proxy identity/cluster.
- Normalized external origin (low-cardinality).
- Effective client IP do proxy chain suy ra.
- SSO protocol/registration ID.
- Callback validation outcome.
- Denial category: `UNTRUSTED_PROXY`, `INVALID_FORWARDED_HOST`, `FORWARDED_CONFLICT`, `BAD_EXTERNAL_SCHEME`, `SAML_RECIPIENT_MISMATCH`, `OIDC_REDIRECT_URI_MISMATCH`, `COOKIE_SESSION_LOST`.

Không log raw SAMLResponse, OIDC ID Token/access token, session cookies, Kerberos Authorization: Negotiate, client secrets, JWT claims hoặc sensitive PII. IP addresses cũng có thể là personal data theo luật/chính sách; retention và access control phải phù hợp.

### 24.1. Metrics hữu ích

Các metric names dưới đây là **đề xuất**, không mặc định Spring phát:
- `proxy_forwarded_header_rejected_total`.
- `proxy_trust_peer_denied_total`.
- `invalid_public_host_total`.
- `oauth2_redirect_uri_mismatch_total`.
- `saml_destination_recipient_rejected_total`.
- `session_cookie_persistence_failure_total`.
- `proxy_header_conflict_total`.
- `origin_normalization_failure_total`.

Không gắn raw Host, full forwarded headers, client IP hoặc arbitrary XFF chain làm metric labels: chúng có cardinality cao và có thể chứa data do attacker điều khiển. Sử dụng approved labels như registration, gateway ID, known environment và failure category.

## 25. Troubleshooting thực tế

| Triệu chứng | Khả năng | Chẩn đoán |
|---|---|---|
| OAuth2 IdP báo redirect_uri_mismatch | App dựng internal http/host/port | Kiểm public Origin vs effective request |
| OAuth2 callback về nhưng state invalid | Session/cookie khác node hoặc host | Cookie flags, Secure/SameSite, session store |
| SAML Recipient mismatch | ACS scheme/host/prefix sai | So SAML data với trusted public ACS |
| SAML Destination mismatch | Proxy ghi nhầm public scheme | Kiểm XFP từ đúng TLS terminator |
| SP metadata chứa internal IP | Không bật/đúng forwarded strategy hoặc static URLs | Kiểm registration và proxy |
| Location header trỏ attacker.invalid | Host poisoning hoặc untrusted XFH | Strip at edge, allowlist public host |
| Cookies không có Secure | App nghĩ external http hoặc policy cookie sai | Secure=true, external HTTPS |
| HTTPS redirect loop | HSTS/scheme mismatch | Kiểm forwarded proto và redirect chain |
| Audit IP luôn là proxy | Chưa xử lý XFF đúng trust | NATIVE/gateway client IP config |
| Audit IP bị người dùng đổi tùy ý | Chọn first XFF từ untrusted input | Sanitize/chain trust |
| CSRF fail sau login | Wrong Host/Origin, cookie session, token | Origin policy/session/CSRF |
| User vào sai tenant | XFH/Host-driven routing untrusted | Approved tenant hostname mapping |
| Bật FRAMEWORK mà vẫn có XFH giả | Backend accessible trực tiếp | Firewall/NetworkPolicy ingress |
| NATIVE hoạt động ở node A nhưng không ở B | Tomcat/container versions khác | Đồng bộ config/trust CIDR |
| /portal callback bị thiếu prefix | X-Forwarded-Prefix/rewrite chưa đúng | Kiểm path routing and registration |
| Header Forwarded và XFH trái nhau | Proxy chưa strip family kia | Normalize tại edge |
| IdP signing key bị báo lỗi sau proxy change | Có thể unrelated protocol trust | Phân biệt key verification vs URI mismatch |
| CAS service ticket invalid | CAS service URL host/scheme mismatch | Canonical public service config |
| Kerberos không login trên hostname mới | SPN/keytab/service principal mismatch | Kiểm public hostname/SPN |
| WebFlux request URL sai | Dùng wrong Servlet assumptions | ForwardedHeaderTransformer / gateway |
| One CDN POP làm login fail | Upstream trust/proto mismatch | So config mỗi edge/site |
| Deployment thêm LB làm mất client IP | Hop chain không cập nhật | Trusted proxy policy inventory |

### 25.1. Trình tự debug ngắn

1. Xác định public URL/host/port/prefix được phê duyệt.
2. Vẽ mọi hop browser → CDN/LB → ingress → service mesh → Spring.
3. Ghi ai terminate TLS và ai tạo/strip forwarded headers.
4. Kiểm backend có đường truy cập trực tiếp không.
5. Kiểm Spring Boot strategy và native valve/filter ownership.
6. Test request hợp lệ và request có forged `Forwarded`/`X-Forwarded-*`.
7. So public callback `redirect_uri`, SAML ACS và metadata.
8. Kiểm session cookie, state, CSRF và HTTP redirect chain.
9. Xác minh authority/tenant rules riêng, không đánh đồng proxy với IdP.
10. Bổ sung integration regression tests và release guard.

## 26. Những anti-pattern nguy hiểm

1. Bật `server.forward-headers-strategy: framework` khi backend port public.
2. Coi mọi private IP trong 10/8 là trusted proxy.
3. Dùng raw `request.getHeader("X-Forwarded-Host")` để chọn tenant/issuer.
4. Dùng raw `X-Forwarded-For.split(",")[0]` cho IP allowlist.
5. Để proxy chỉ strip XFH nhưng giữ `Forwarded` từ Internet.
6. Dùng `$proxy_add_x_forwarded_for` ở untrusted public edge mà không normalize.
7. Dùng raw `$http_host` để dựng SSO callback không kiểm domain.
8. Lấy `X-Forwarded-Proto` từ một downstream HTTP hop thay vì external TLS terminator.
9. Tin cả Forwarded và XFF/XFH có giá trị xung đột.
10. Bật NATIVE và FRAMEWORK cùng nhau không hiểu ordering.
11. Dùng `getRemoteAddr()` đã rewrite làm bằng chứng raw socket peer.
12. Vô hiệu hóa OAuth2 state/nonce để chữa `redirect_uri` sai.
13. Bỏ SAML Recipient/Destination/Audience validation vì ACS mismatch.
14. Cho wildcard IdP redirect URIs hoặc success URLs tùy ý.
15. Không restrict backend từ K8s pods khác trong cùng cluster.
16. Tin CDN-specific client-IP header từ request không đến từ CDN.
17. Copy private keys/identity claims vào debug logs.
18. Gán `ROLE_ADMIN` dựa trên client-provided origin/tenant header.
19. Coi HTTPS ở browser đồng nghĩa backend không cần network security.
20. Bỏ kiểm Host/virtual-host vì “đã có TLS”.
21. Sửa cookie SameSite mà không test SAML POST cross-site.
22. Trộn TLS certificate với SAML signing/decryption credentials.
23. Đưa test/staging host vào production allowlist không kiểm soát.
24. Tắt rate limiting khi IP sau proxy bị sai thay vì sửa trusted hop.
25. Chỉ test bằng MockMvc headers và kết luận đã kiểm NGINX/firewall.

## 27. Checklist triển khai/QA

- [ ] Đã xác định public origin, approved hosts/ports và prefix.
- [ ] Đã vẽ và review toàn bộ proxy/CDN/LB/ingress/service mesh hops.
- [ ] Backend chỉ nhận kết nối từ trusted proxy identity/network.
- [ ] Edge strip cả `Forwarded` và mọi `X-Forwarded-*` đầu vào.
- [ ] Edge set public proto/host/port từ trusted listener/vhost.
- [ ] Edge set XFF từ observed peer/trusted prior-hop data, không raw client value.
- [ ] Multi-hop đã định nghĩa hop ownership và right-to-left trust rules.
- [ ] Unknown Host/SNI và duplicate/conflicting headers bị reject/normalize.
- [ ] Spring Boot chọn đúng NONE/NATIVE/FRAMEWORK cho runtime.
- [ ] Tomcat internalProxies/trustedProxies thu hẹp, không tin mọi RFC1918.
- [ ] Không có double header parsing/rewriting không rõ ownership.
- [ ] WebFlux dùng đúng ForwardedHeaderTransformer khi cần.
- [ ] Public OIDC redirect_uri đúng IdP registration exact allowlist.
- [ ] SAML SP metadata ACS/entityID dùng HTTPS canonical domain.
- [ ] SAML Destination/Recipient/InResponseTo checks còn nguyên.
- [ ] CAS service URL và Kerberos SPN topology đã được xác minh khi áp dụng.
- [ ] Session cookie Secure/HttpOnly/Path/SameSite theo browser SSO flow.
- [ ] HSTS/TLS policy ở public edge và proxy→app transport có bảo vệ.
- [ ] CSRF/cross-origin policy không tin Host chưa verified.
- [ ] Tenant routing và local identity mapping không dựa HTTP header không tin.
- [ ] Có positive public redirect + SAML/OIDC full integration tests.
- [ ] Có negative forged Forwarded, XFH, XFP, XFF, Prefix, duplicates.
- [ ] Direct backend request bị chặn trong network security test.
- [ ] Logs phân biệt raw peer/effective client IP, không lộ tokens.
- [ ] Metrics low-cardinality và alert khi proxy header conflicts.
- [ ] Tài liệu deployment xác định người quản trị trust set và key rotation.
- [ ] Mọi thay đổi ingress/CDN/gateway đều có regression test SSO.
- [ ] Không bypass authentication/authorization để che header mismatch.

## 28. Câu hỏi ôn tập

1. **Tại sao không thể tin X-Forwarded-Host trực tiếp?** Client có thể tự gửi giá trị đó.
2. **Ai phải strip forwarded headers từ Internet?** Proxy tại edge của trust boundary.
3. **Chỉ strip X-Forwarded-Host đã đủ chưa?** Chưa, cần cả Forwarded và các biến thể X-Forwarded khác.
4. **X-Forwarded-Proto dùng làm gì?** Cho biết external HTTP/HTTPS scheme do trusted proxy quan sát.
5. **X-Forwarded-For là chứng cứ tuyệt đối về IP client?** Không, cần trusted hops và sanitization.
6. **Tại sao lấy first XFF nguy hiểm?** Client có thể tự điền phần tử bên trái trước khi proxy append.
7. **Proxy dùng IP 10.0.0.8 có tự đáng tin không?** Không, phải nằm trong allowlist và network trust boundary.
8. **server.forward-headers-strategy=NONE nghĩa là gì?** Boot không dùng native/framework forwarding support do property này, nhưng custom code vẫn cần review.
9. **NATIVE và FRAMEWORK khác nhau?** Container native handling vs Spring Framework filter/transformer.
10. **ForwardedHeaderFilter có tự xác định header đến từ trusted proxy không?** Không; trust bắt đầu từ proxy/network.
11. **removeOnly có tác dụng gì?** Loại bỏ forwarded headers mà không dùng chúng để rewrite request.
12. **Tại sao tránh double handling?** Có thể làm sai scheme, host, port hoặc IP.
13. **OAuth2 redirect_uri sai cần xử lý ở đâu?** Public origin/proxy config và ClientRegistration, không bỏ state.
14. **SAML Recipient mismatch có nên tắt validator không?** Không, sửa ACS/public origin.
15. **Public ACS HTTPS nhưng backend HTTP có thể đúng không?** Có nếu TLS terminate ở trusted proxy và backend protected.
16. **Forwarded header có thay IdP signing key hay issuer không?** Không.
17. **Kerberos SPN có tự đổi khi XFH đổi?** Không.
18. **CORS lỗi có chứng minh forwarding không an toàn không?** Không đủ, nhưng cần kiểm origin/proxy cùng security routing.
19. **Cookie Secure tại sao quan trọng?** Browser chỉ gửi cookie qua HTTPS, tránh rò session qua HTTP.
20. **SAML POST SameSite Lax luôn phù hợp không?** Không, cần test browser/cross-site callback và policy.
21. **Tại sao cần Host allowlist khi có TLS?** Host vẫn là request metadata dùng để chọn tenant/links.
22. **Khi nào dùng canonical public URL tĩnh?** Khi app có fixed domain hoặc không thể bảo đảm forwarding trust.
23. **Kubernetes Service private có bảo đảm chỉ ingress gọi được không?** Không, cần NetworkPolicy/firewall.
24. **Demo Java17 có thể thay Tomcat RemoteIpValve không?** Không, chỉ minh họa trust invariant.
25. **Direct backend port public, bật FRAMEWORK có an toàn không?** Không.
26. **Một CDN client-IP header có thể tin từ bất kỳ request nào không?** Không, chỉ từ verified CDN peer.
27. **Để debug login loop cần kiểm gì?** Redirect URI, public scheme/host, cookie/session, request correlation.
28. **Cần kiểm gì sau sửa proxy?** OIDC authorize/callback, SAML metadata/ACS, Host spoofing, session và role policies.
29. **Forwarded có phải chứng cứ user đã đăng nhập không?** Không.
30. **Quy tắc tổng quát?** Chỉ nhận metadata do proxy kiểm soát sinh ra tại trust boundary đã bảo vệ, rồi mới cho Spring dùng.

## 29. Nguồn tham khảo chính thức

- Spring Framework – Servlet Filters, ForwardedHeaderFilter và Security Considerations: https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html
- Spring Framework – ForwardedHeaderFilter Javadoc: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/filter/ForwardedHeaderFilter.html
- Spring Boot – Embedded Web Servers, Running Behind a Front-end Proxy: https://docs.spring.io/spring-boot/how-to/webserver.html
- Spring Boot – server.forward-headers-strategy application property: https://docs.spring.io/spring-boot/appendix/application-properties/
- Spring Security – OAuth2 Login Core, default redirect URI: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html
- Spring Security – OAuth2 Authorization Requests/redirect-uri template: https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorization-grants.html
- Spring Security – SAML2 Login Overview: https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
- Spring Security – SAML2 RelyingPartyRegistration: https://docs.spring.io/spring-security/reference/servlet/saml2/login/relying-party.html
- Apache Tomcat – RemoteIpValve configuration (Tomcat 11, đối chiếu version runtime): https://tomcat.apache.org/tomcat-11.0-doc/config/valve.html
- NGINX – proxy_set_header và $proxy_add_x_forwarded_for: https://nginx.org/en/docs/http/ngx_http_proxy_module.html
- IETF RFC 7239 – Forwarded HTTP Extension, §8 Security Considerations: https://www.rfc-editor.org/rfc/rfc7239
- OWASP – Unvalidated Redirects and Forwards: https://cheatsheetseries.owasp.org/cheatsheets/Unvalidated_Redirects_and_Forwards_Cheat_Sheet.html
- OWASP – Cross-Site Request Forgery Prevention: https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html
- OWASP – Session Management: https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html
- OWASP – HTTP Security Response Headers: https://cheatsheetseries.owasp.org/cheatsheets/HTTP_Headers_Cheat_Sheet.html

**Tổng kết:** Spring Security cần biết public scheme, host, port và prefix khi chạy sau proxy, nhất là để dựng OAuth2/OIDC `redirect_uri` và SAML2 ACS/metadata. Nhưng `Forwarded`/`X-Forwarded-*` tự thân là **HTTP input do client có thể giả mạo**. Cách triển khai đúng là **chặn direct backend traffic → edge strip mọi forwarding headers đầu vào → trusted proxy tái tạo public origin từ nguồn đã xác minh → Spring chọn đúng NONE/NATIVE/FRAMEWORK → validate canonical origin → giữ nguyên SAML/OIDC authentication, CSRF và authorization checks**. Đừng đánh đổi an toàn bằng việc tin mọi private IP, đọc XFF đầu tiên hoặc tắt các security validators chỉ để callback đăng nhập hoạt động.
