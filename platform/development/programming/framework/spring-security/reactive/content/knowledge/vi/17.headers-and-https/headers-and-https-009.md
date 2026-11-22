# Xử lý Forwarded, X-Forwarded-* và ranh giới tin cậy của proxy

## 1. Vì sao một request HTTPS bên ngoài có thể thành HTTP trong WebFlux?

Trong hệ thống Spring Security reactive dùng Spring WebFlux, ứng dụng thường không tiếp nhận kết nối TLS trực tiếp từ trình duyệt. Một CDN, WAF, load balancer hoặc reverse proxy có thể kết thúc HTTPS ở rìa mạng rồi chuyển tiếp request bằng HTTP nội bộ đến Reactor Netty:

~~~text
Trình duyệt
    │
    │ GET https://app.example.com/account
    │ TLS, HTTP/2 hoặc HTTP/1.1
    ▼
┌──────────────────────────────┐
│ Edge / Reverse Proxy         │
│ - Kiểm chứng TLS/Host        │
│ - Xóa header Forwarded giả  │
│ - Ghi header đã xác minh     │
└──────────────┬───────────────┘
               │
               │ GET http://10.0.0.12:8080/account
               │ Host: app.example.com
               │ X-Forwarded-Proto: https
               │ X-Forwarded-Host: app.example.com
               │ X-Forwarded-For: 198.51.100.27
               ▼
┌──────────────────────────────┐
│ Spring Boot WebFlux          │
│ Reactor Netty                │
│ ForwardedHeaderTransformer   │
│ Spring Security WebFilters   │
│ Controller / handler         │
└──────────────────────────────┘
~~~

Ở tầng kết nối backend, request tới `10.0.0.12:8080` là HTTP. Nhưng theo góc nhìn của client, URL công khai là `https://app.example.com/account`. Sự khác biệt này ảnh hưởng đến:

- Scheme/host/port của URL tuyệt đối trong redirect, link ở email và tài liệu API.
- Cơ chế xác định request có bảo mật HTTPS hay không, HSTS và một số chính sách cookie.
- Xử lý prefix khi ứng dụng được publish dưới `/gateway` hoặc `/myapp`.
- IP client trong logs, audit, rate limiting và các chính sách dựa trên network.
- Kiểm tra Origin/CSRF, CORS và OAuth2/OIDC redirect URI.
- Nguy cơ **Host header poisoning**, open redirect và giả mạo địa chỉ IP nếu client được phép tự điều khiển forwarded headers.

Spring Framework và Spring Boot hỗ trợ khôi phục thông tin request ban đầu, **nhưng ứng dụng không thể tự biết một header Forwarded do proxy đáng tin tạo ra hay do client độc hại tự khai báo**. Vì vậy **ranh giới tin cậy (trust boundary) phải được thiết lập ở tầng hạ tầng**, trước khi cho phép backend sử dụng các header này.

### Mục tiêu sau bài

1. Đọc đúng `Forwarded` theo RFC 7239 và nhóm `X-Forwarded-*` phổ biến.
2. Hiểu hai góc nhìn: kết nối vật lý proxy → backend và URL công khai browser → proxy.
3. Cấu hình `server.forward-headers-strategy=none/native/framework` trong Spring Boot WebFlux 3.3.
4. Dùng `ForwardedHeaderTransformer` của WebFlux và chế độ `removeOnly` khi không muốn tin headers.
5. Thiết lập reverse proxy chỉ ghi headers từ thông tin đã kiểm chứng và **xóa cả Forwarded lẫn X-Forwarded-* do client gửi vào**.
6. Nhận diện tấn công giả `X-Forwarded-Host`, `X-Forwarded-Proto`, `X-Forwarded-For` và `X-Forwarded-Prefix`.
7. Phân biệt forwarded metadata với authentication, authorization, CSRF, CORS và TLS thật.
8. Chạy ví dụ Java 17+ Spring Boot WebFlux và kiểm chứng ứng dụng **chấp nhận metadata khi chế độ FRAMEWORK được bật**, đồng thời chứng minh vì sao không được expose backend trực tiếp.

## 2. Các header quan trọng và ý nghĩa chính xác

### 2.1. Chuẩn RFC 7239: `Forwarded`

RFC 7239 định nghĩa một header có thể mang nhiều thuộc tính theo từng hop:

~~~http
Forwarded: for=198.51.100.27;proto=https;host=app.example.com
~~~

Các tham số thường gặp:
- `for=`: địa chỉ client/hop phía trước theo cách proxy ghi nhận; có thể là IPv4, IPv6 được quote đúng chuẩn hoặc giá trị đã được ẩn danh.
- `by=`: địa chỉ/định danh giao diện proxy tiếp nhận request, tùy proxy có điền hay không.
- `proto=`: scheme được proxy thông báo, ví dụ `https`.
- `host=`: host (và có thể port) mà client yêu cầu phía ngoài.

Có thể tồn tại nhiều phần tử do nhiều proxy nối bằng dấu phẩy:

~~~http
Forwarded: for=198.51.100.27;proto=https;host=app.example.com, for=10.0.0.7;by=10.0.0.9
~~~

**Không coi phần tử đầu tiên hay mọi giá trị ở header này là bằng chứng được xác minh**. Nếu proxy tin cậy chỉ *append* mà không xóa header client đã gửi, attacker có thể tự đặt phần tử đầu tiên và khiến ứng dụng hiểu sai nguồn request.

Với IPv6, parser phải theo chuẩn về quoting/brackets thay vì tách thủ công theo dấu `:` hoặc dấu phẩy trong mọi tình huống. **Không tự viết regex parse `Forwarded` rồi dùng nó để cấp quyền**; sử dụng hạ tầng/proxy và thư viện được hỗ trợ, có các giới hạn tin cậy.

### 2.2. Họ `X-Forwarded-*` phổ biến

| Header | Ý nghĩa dự kiến | Nguy cơ khi tin dữ liệu client |
| --- | --- | --- |
| `X-Forwarded-For` | Chuỗi IP client và các proxy trung gian | Giả IP để né rate limit, giả IP trong audit, vượt IP allowlist |
| `X-Forwarded-Proto` | Scheme phía client, ví dụ `https` | App suy nhầm HTTP/HTTPS; redirect, cookie, HSTS sai |
| `X-Forwarded-Host` | Host public mà client gọi | Đầu độc absolute URL, password-reset link, redirect ra attacker domain |
| `X-Forwarded-Port` | Port phía ngoài, ví dụ 443 | Sai URL/redirect, callback URI, origin/port |
| `X-Forwarded-Prefix` | Prefix của public route khi proxy rewrite path | Sai link/base path, redirect prefix bị điều khiển |
| `X-Forwarded-Ssl` | Thông tin SSL từ một số proxy cũ | Một cách khai báo TLS dễ bị giả nếu edge không lọc |

Một request nội bộ có thể mang:

~~~http
GET /account HTTP/1.1
Host: 10.0.0.12:8080
X-Forwarded-Host: app.example.com
X-Forwarded-Proto: https
X-Forwarded-Port: 443
X-Forwarded-For: 198.51.100.27
~~~

Các header không phải “chứng chỉ” của client. Chúng chỉ là văn bản HTTP cho đến khi có **proxy đáng tin** bảo đảm nguồn gốc và tính đúng đắn.

Ngoài ra, chính header `Host` cũng có thể do client bên ngoài lựa chọn. Không mặc định rằng nếu đã loại `X-Forwarded-Host` thì `Host` chắc chắn hợp lệ; ingress cần validate hostname hoặc áp canonical host cho request đi vào app.

### 2.3. `Forwarded` và `X-Forwarded-*` có thể mâu thuẫn

Ví dụ request nguy hiểm:

~~~http
Forwarded: for=203.0.113.10;proto=http;host=evil.example
X-Forwarded-Proto: https
X-Forwarded-Host: app.example.com
~~~

Không nên trông chờ mọi middleware xử lý xung đột theo cùng một thứ tự ưu tiên, đặc biệt giữa các phiên bản hoặc HTTP stacks. **Thiết kế hạ tầng phải xóa cả hai họ header từ client** rồi chỉ phát ra kiểu header mà backend được cấu hình để sử dụng, với các giá trị đã xác minh.

Một proxy chỉ xóa `Forwarded` nhưng để lọt `X-Forwarded-Host`, hoặc ngược lại, vẫn còn lỗ hổng spoofing.

## 3. Ranh giới tin cậy đặt ở đâu?

### 3.1. Tình huống không an toàn: client trực tiếp gửi header đến backend

~~~text
Attacker
   │
   │ GET http://public-app:8080/internal/request-view
   │ X-Forwarded-Proto: https
   │ X-Forwarded-Host: evil.example
   ▼
Spring Boot cấu hình FRAMEWORK
   │
   └─ App có thể hiểu request ở https://evil.example/
      nếu backend nhận header chưa được làm sạch.
~~~

Nếu ứng dụng bật `ForwardedHeaderTransformer` mà cổng backend vẫn mở công khai, client không cần đi qua proxy để tự tạo metadata “trusted”. Framework **không có thông tin đáng tin độc lập** để biết header đến từ proxy hay attacker.

**Vì vậy cấu hình forwarded headers ở backend chỉ có thể đúng khi network boundary cũng đúng.** Lớp bảo vệ chính:
1. Chỉ cho phép traffic đến backend từ proxy/ingress đã phê duyệt (firewall, security group, NetworkPolicy, private service).
2. Proxy public **xóa hoặc ghi đè** mọi `Forwarded` và `X-Forwarded-*` do client đưa vào.
3. Proxy chỉ tạo metadata mới từ scheme/host/client address mà proxy đã xác minh.
4. Kết nối proxy → backend được bảo vệ khỏi nguồn không tin cậy; cân nhắc TLS/mTLS nội bộ cho yêu cầu rủi ro cao.
5. Backend chỉ xử lý các header đã được thiết kế và đã được chứng minh đến từ proxy tin cậy.

### 3.2. Tình huống đúng: edge chuẩn hóa metadata

~~~text
Internet
   │
   │ Client có thể tự gửi:
   │   Forwarded: proto=http;host=evil.example
   │   X-Forwarded-Host: evil.example
   │   X-Forwarded-For: 127.0.0.1
   ▼
TRUST BOUNDARY: proxy public
   ├─ Chặn hostname không nằm trong allowlist
   ├─ Xóa Forwarded do client gửi
   ├─ Xóa toàn bộ X-Forwarded-* do client gửi
   ├─ Đặt X-Forwarded-Proto = scheme đã xác minh
   ├─ Đặt X-Forwarded-Host = canonical host đã xác minh
   ├─ Đặt X-Forwarded-For = IP kết nối đã xác minh
   └─ Chuyển request vào private backend
                    │
                    ▼
         WebFlux ForwardedHeaderTransformer
         ├─ Khôi phục URI scheme/host/port
         └─ Loại các forwarded headers trước handler
                    │
                    ▼
          Spring Security + business handler
~~~

**Cốt lõi:** chỉ nơi đủ khả năng xác minh kết nối phía ngoài mới được quyết định các giá trị forwarded. Framework application layer không tự thay edge validation.

### 3.3. Nhiều proxy liên tiếp

Ví dụ:

~~~text
Browser → CDN → WAF → ingress → Spring WebFlux
~~~

Cần xác định rõ proxy nào là **điểm đầu tiên không còn tin traffic Internet**, điểm nào được tin để ghi `X-Forwarded-For`, và có bao nhiêu hop được phép. Nếu ingress chỉ append `$proxy_add_x_forwarded_for` mà CDN không sanitize client header, phần trái của chain có thể là dữ liệu giả.

Quy tắc “IP thật luôn là giá trị đầu tiên trong X-Forwarded-For” **chỉ đúng trong một số topologies đã được cấu hình an toàn**, không phải chân lý bảo mật. Với nhiều hop, chọn client IP phải dựa trên tập proxy tin cậy, hướng duyệt chain và kiểm chứng điểm bắt đầu; không dùng logic `split(",")[0]` để quyết định quyền nhạy cảm.

`X-Real-IP` cũng không tự đáng tin nếu client được phép gửi qua edge. Chính sách ingress/network quan trọng hơn tên header.

## 4. Cấu hình Spring Boot 3.3: none, native, framework

Spring Boot 3.3 có property:

~~~properties
server.forward-headers-strategy=framework
~~~

Ba chiến lược:

| Giá trị | Ý nghĩa | Khi cân nhắc |
| --- | --- | --- |
| `none` | Không bật xử lý forwarded metadata bằng cơ chế auto-configured của Boot | Backend không cần metadata từ proxy, hoặc chưa thiết lập trust boundary |
| `native` | Giao cho HTTP server/container xử lý forwarded headers | Server/proxy hỗ trợ native; phải xem hành vi/điều kiện trust theo implementation |
| `framework` | Sử dụng hạ tầng Spring Framework; với WebFlux là `ForwardedHeaderTransformer` | Cần khôi phục scheme/host/port cho request trong WebFlux, khi edge đã sanitize |

Ví dụ profile tin cậy:

~~~properties
# Chỉ bật khi app được chặn khỏi Internet trực tiếp
# và reverse proxy loại mọi forwarded headers chưa tin.
server.forward-headers-strategy=framework
~~~

Ví dụ profile không có trusted proxy:

~~~properties
# Không nhận các giá trị forwarded từ request công khai.
server.forward-headers-strategy=none
~~~

**Không suy đoán default giống nhau ở mọi môi trường.** Spring Boot có thể chọn chiến lược mặc định khác khi phát hiện một số nền tảng cloud. Với production, **đặt tường minh** và kiểm tra effective configuration trong deployment.

Lựa chọn `native` phải được kiểm tra theo server cụ thể: Reactor Netty, Tomcat reactive, Jetty reactive có cơ chế và giới hạn khác nhau. Nếu dùng Reactor Netty trong WebFlux, đừng sao chép property chỉ dành cho Tomcat Servlet như `server.tomcat.remoteip.internal-proxies` rồi giả định nó điều khiển Netty.

**Điều rất quan trọng:** `framework`, `native` và `none` mô tả **cách backend xử lý metadata**, không tạo firewall, không buộc request phải đến từ proxy tin cậy, không xác thực HMAC/JWT và không tự xóa header từ client ở ranh giới Internet.

### 4.1. Boot `framework` và bean tự định nghĩa có khác không?

Trong Spring Framework WebFlux, `ForwardedHeaderTransformer` có thể được đăng ký thủ công dưới bean name chính xác `forwardedHeaderTransformer`. Spring Boot khi cấu hình `server.forward-headers-strategy=framework` sẽ thiết lập cơ chế tương ứng.

Không cần vừa bật Boot strategy vừa copy/paste thêm một transformer tùy biến không có lý do. Điều đó có thể thay đổi bean được chọn hoặc tạo cấu hình khó hiểu. Chọn một đường cấu hình rõ ràng, sau đó test.

**Đoạn thay thế**, không nằm trong project runnable phía dưới:

~~~java
@Bean(name = "forwardedHeaderTransformer")
ForwardedHeaderTransformer forwardedHeaderTransformer() {
    return new ForwardedHeaderTransformer();
}
~~~

Đây là **mã trích** dành cho Spring Framework 6.1.x, cần import `org.springframework.web.server.adapter.ForwardedHeaderTransformer` và `org.springframework.context.annotation.Bean`. Với các dòng Spring Framework mới, constructor/cách chọn loại forwarded header có thể thay đổi; phải đối chiếu đúng version đang dùng.

### 4.2. `removeOnly`: xóa header mà không tin metadata

Nếu application **không có proxy đáng tin** nhưng vẫn muốn loại forwarded headers khỏi request trước khi các component phía sau nhìn thấy, Spring Framework cung cấp:

~~~java
@Bean(name = "forwardedHeaderTransformer")
ForwardedHeaderTransformer forwardedHeaderTransformer() {
    ForwardedHeaderTransformer transformer =
        new ForwardedHeaderTransformer();

    transformer.setRemoveOnly(true);
    return transformer;
}
~~~

Đây là **cấu hình thay thế**, không bật đồng thời một cách mù quáng với Boot `framework`. Khi `removeOnly=true`:
- `Forwarded` và các header `X-Forwarded-*` mà transformer biết sẽ được loại khỏi request.
- URI gốc của kết nối không bị rewrite theo các header đó.
- Đoạn code application phía sau không thể vô tình lấy metadata giả từ các header đã bị transformer loại.

Lưu ý `removeOnly` không phải cơ chế định danh client/proxy. Nếu application ở sau proxy thật và cần absolute URLs chính xác, không thể vừa muốn **bỏ qua mọi forwarded metadata** vừa trông chờ framework suy ra scheme ngoài HTTPS từ kết nối HTTP nội bộ.

Với những hệ thống cần chặn spoofing ở upstream, phải bảo vệ ở proxy **dù** có `removeOnly` tại app; đừng nhầm sanitizer application với ingress trust policy.

## 5. Hành vi `ForwardedHeaderTransformer` của WebFlux

Component WebFlux nằm trong:

~~~java
org.springframework.web.server.adapter.ForwardedHeaderTransformer
~~~

Nó xử lý request **trước** khi tạo/đưa exchange qua phần lớn WebFilter/controller, để các API request nhìn thấy thông tin đã khôi phục theo metadata (khi được tin cậy). Sau khi xử lý, các header forwarded được loại khỏi request đã biến đổi để giảm ảnh hưởng ở tầng downstream.

Tác động có thể bao gồm:
- `request.getURI().getScheme()`: từ HTTP nội bộ sang HTTPS công khai.
- `request.getURI().getHost()`: từ địa chỉ backend sang public host.
- `request.getURI().getPort()`: port công khai, có thể là -1 nếu URI dùng port mặc định/không ghi.
- `request.getRemoteAddress()`: có thể phản ánh nguồn được forwarded, tùy implementation và headers; không được coi là IP đã xác thực chỉ vì API trả ra.
- `X-Forwarded-Prefix`: trong các cấu hình/version hỗ trợ, có thể ảnh hưởng context/base path dùng để dựng link/route.

**Không dùng** `request.getSslInfo()` như bằng chứng TLS trực tiếp với browser nếu TLS bị terminate tại proxy: kết nối app nhận là HTTP, dù public URL dùng HTTPS. Cần phân biệt TLS phiên vật lý và metadata đã được edge xác nhận.

**Không dùng** API Servlet `ForwardedHeaderFilter` như bộ lọc chính cho WebFlux; Spring Framework WebFlux hỗ trợ `ForwardedHeaderTransformer`. Đây là khác biệt stack, không chỉ tên class.

### 5.1. Ví dụ sự khác biệt trước–sau

Giả sử browser gọi:

~~~text
https://app.example.com/account
~~~

Proxy gửi đến app:

~~~http
GET /account HTTP/1.1
Host: backend.internal:8080
X-Forwarded-Proto: https
X-Forwarded-Host: app.example.com
X-Forwarded-Port: 443
~~~

Trong backend trước xử lý, URI logic thường là:

~~~text
http://backend.internal:8080/account
~~~

Sau transformer được bật và headers thực sự đã được tin:
 
~~~text
https://app.example.com/account
~~~

Điều này giúp link và redirect phản ánh địa chỉ công khai, nhưng **không làm backend connection tự trở thành TLS**. Vì thế giữa proxy và backend vẫn cần network isolation/TLS phù hợp.

### 5.2. `X-Forwarded-Prefix` dễ bị bỏ sót

Giả sử proxy publish:

~~~text
https://app.example.com/gateway/orders/123
~~~

Nhưng backend nhận:

~~~text
http://orders-service:8080/orders/123
~~~

Một proxy có thể gửi `X-Forwarded-Prefix: /gateway` để WebFlux dựng URLs tương ứng. Tuy nhiên:
- Prefix phải được proxy gán từ routing config đã xác minh, không cho client tùy ý chọn.
- Proxy và backend cần nhất quán việc strip/preserve prefix.
- Hành vi hỗ trợ prefix có thể khác theo Spring Framework version, cách tạo transformer và `setUseForwardedPrefix` ở dòng API mới; phải kiểm tra đúng phiên bản.
- Không tạo quyền truy cập bằng cách so khớp chuỗi prefix thiếu chuẩn hóa.
- Test chính xác các redirect/link khi app được đặt dưới subpath, tránh double-prefix hoặc mất prefix.

Nếu không cần publish dưới prefix, **đừng tự cho client điều khiển `X-Forwarded-Prefix`**.

## 6. Hệ quả đối với Spring Security: không chỉ là URL đẹp

### 6.1. Redirect và absolute URL

Một ứng dụng có thể tự tạo `Location` hoặc link:

~~~http
HTTP/1.1 302 Found
Location: http://backend.internal:8080/login
~~~

Nếu backend không biết scheme/host public, redirect có thể dùng host/port nội bộ, gây lỗi UX hoặc rò cấu trúc hạ tầng. Nếu tin sai `X-Forwarded-Host`, attacker có thể biến link thành:

~~~http
HTTP/1.1 302 Found
Location: https://evil.example/login
~~~

Điều này có thể dẫn đến open redirect, phishing, password-reset link poisoning hoặc sai callback OAuth2/OIDC. Framework không tự biến một Host giả thành Host đáng tin; vấn đề nằm ở đường nhập.

**Khuyến nghị:** với email password reset, OAuth2/OIDC callback, đường dẫn có token hay absolute link nhạy cảm, ưu tiên **public base URL được cấu hình và validate tường minh** (ví dụ `https://app.example.com`) thay vì ghép trực tiếp từ `request.getURI().getHost()`. Nếu cần nhiều tenant/host, phải kiểm host đối với allowlist/mapping đáng tin trước khi tạo link.

### 6.2. HTTPS, redirect loop và HSTS

Một proxy thường terminate HTTPS rồi dùng HTTP nội bộ. Nếu Spring Security hoặc ứng dụng xác định request “insecure” chỉ dựa trên HTTP nội bộ trong khi public HTTPS, chính sách channel redirect có thể gây **redirect loop**:

~~~text
Browser HTTPS → proxy → backend HTTP
Backend tin request đang HTTP → redirect HTTPS
Browser HTTPS → proxy → backend HTTP
... lặp lại
~~~

Khi metadata HTTPS được khôi phục đúng, ứng dụng có thể phân biệt URL công khai. Nhưng đừng dựa vào forwarded header để thay việc **proxy cưỡng chế HTTPS từ Internet**. HTTP → HTTPS redirect ở edge cần được thực hiện với hostname đã validate và TLS đúng.

HSTS (`Strict-Transport-Security`) giúp browser nhớ phải dùng HTTPS cho host đã biết. Spring Security có hỗ trợ response security headers; hành vi HSTS có thể tùy việc request được xem là secure và cấu hình security. Nếu app backend thấy HTTP hoặc phản hồi đi qua edge, hãy kiểm end-to-end rằng browser **thực sự nhận HSTS qua HTTPS public**; có thể đặt/chốt HSTS tại edge nếu đó là tầng giữ TLS.

Không gửi HSTS tùy tiện trên các hostname chưa sẵn sàng HTTPS. `includeSubDomains`/`preload` cần đánh giá toàn bộ domain/subdomain, vì có tác động dài hạn.

### 6.3. Cookie Secure, SameSite, CSRF

Cookie session có các thuộc tính `Secure`, `HttpOnly`, `SameSite`, `Path`, `Domain`. Nếu TLS terminate ở proxy, cấu hình ứng dụng phải nhất quán với **HTTPS công khai**, không chỉ HTTP nội bộ.

Ví dụ production WebFlux:

~~~properties
# Khi browser luôn kết nối HTTPS công khai.
server.reactive.session.cookie.secure=true
server.reactive.session.cookie.http-only=true
server.reactive.session.cookie.same-site=lax
~~~

Đây là cấu hình gợi ý theo threat model, **không phải cấu hình của demo local HTTP**. Cookie `Secure` phải được trình duyệt gửi qua HTTPS; localhost/lab HTTP có thể hoạt động khác tùy browser. `SameSite` là chính sách cookie, không thay CSRF token cho toàn bộ trường hợp.

Quan trọng:
- Forwarded header không tự cung cấp CSRF token và không thay `CsrfWebFilter`.
- Một request POST dùng session/HTTP Basic vẫn phải tuân CSRF mặc định nếu có rủi ro browser CSRF.
- CSRF token trên frontend phải được cấp đúng repository và request handler.
- HTTPS ở edge bảo vệ browser ↔ proxy, nhưng chưa khẳng định proxy ↔ backend được mã hóa hoặc an toàn.
- Đừng đưa session cookie/CSRF token vào log “để debug proxy”.

### 6.4. CORS và Origin không phải forwarded headers

`Origin` là header khác, dùng trong CORS/CSRF origin checks, không phải một định danh user hay proxy đã xác minh. CORS allowlist cần nêu **các origin công khai được phép**; không dựng allowlist từ `X-Forwarded-Host` do client tự gửi.

Nếu cấu hình cho phép origin dựa trên forwarded host chưa được tin:
- Attacker có thể giả host và ảnh hưởng cách backend quyết định same-origin/cross-origin.
- Redirect và CSRF Origin checks có thể sai ở reverse proxy.
- Frontend bị lỗi CORS do scheme/port nhìn thấy bởi backend khác ngoài browser.

Một response CORS thành công không tự cấp authentication/authorization, và việc tắt CORS không chống được CSRF.

### 6.5. IP address, audit, rate limiting và rủi ro giả `127.0.0.1`

Đây là một mẫu cực kỳ nguy hiểm:

~~~java
// PHẢN VÍ DỤ: header client có thể bị giả.
String ip = request.getHeaders().getFirst("X-Forwarded-For");
if ("127.0.0.1".equals(ip)) {
    // CẤP QUYỀN ADMIN -- tuyệt đối không làm!
}
~~~

Một request trực tiếp:

~~~http
X-Forwarded-For: 127.0.0.1
~~~

không biến client thành loopback đáng tin. IP dùng cho rate limit, audit hay cảnh báo chỉ hữu ích nếu được xác định theo **topology proxy đã tin**. Nếu cần network allowlist ở ingress, thực hiện ở tầng mạng/proxy nơi biết peer thực tế và chỉ tin chuỗi proxy đã cấu hình. **Không dùng IP/client address đơn độc thay authentication và authorization** cho dữ liệu nhạy cảm.

Thậm chí `request.getRemoteAddress()` sau khi ForwardedHeaderTransformer được bật có thể phản ánh forwarded info, chứ không đơn thuần là socket peer được quan sát trực tiếp. Khi ghi log “client IP”, ghi rõ nguồn/độ tin cậy và xử lý dữ liệu cá nhân theo chính sách.

## 7. Cấu hình reverse proxy tại đúng trust boundary

Dưới đây là **đoạn Nginx minh họa** cho mô hình Nginx là edge public duy nhất, chỉ phục vụ một hostname HTTPS `app.example.com` và kết nối local backend `127.0.0.1:8080`.

~~~nginx
server {
    listen 443 ssl;
    server_name app.example.com;

    # Thay bằng đường dẫn chứng chỉ thật khi triển khai.
    ssl_certificate     /etc/nginx/tls/app.crt;
    ssl_certificate_key /etc/nginx/tls/app.key;

    # HSTS tại HTTPS edge (quyết định max-age theo policy).
    add_header Strict-Transport-Security "max-age=31536000" always;

    location / {
        proxy_pass http://127.0.0.1:8080;

        # Chốt Host công khai; không tin Host attacker.
        proxy_set_header Host app.example.com;

        # Không chuyển tiếp RFC 7239 do client tự gửi.
        proxy_set_header Forwarded "";

        # Tự GÁN metadata từ nơi edge đã xác minh.
        proxy_set_header X-Forwarded-Host app.example.com;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-Port 443;

        # Dùng socket peer observed tại proxy này.
        # Không dùng $proxy_add_x_forwarded_for nếu
        # chưa xác minh/xóa XFF từ các hop trước.
        proxy_set_header X-Forwarded-For $remote_addr;

        # Bỏ các biến thể không được sử dụng.
        proxy_set_header X-Forwarded-Ssl "";
        proxy_set_header X-Forwarded-Prefix "";
    }
}
~~~

Giải thích và giới hạn:
- Đây là **snip cấu hình hạ tầng**, không thể copy chạy nếu chưa có TLS certificates, route policy và firewall.
- `proxy_set_header Forwarded "";` có ý định **không truyền** header Forwarded từ client. Với Nginx, giá trị rỗng không gửi field tới upstream.
- Các giá trị `X-Forwarded-*` được **ghi đè** bằng dữ liệu mà edge đã kiểm chứng, không lấy nguyên header do client tự gửi.
- `X-Forwarded-For $remote_addr` là địa chỉ **peer của Nginx**. Nếu Nginx ở sau CDN, đó có thể là IP CDN; cần giải pháp xác định real client đúng theo **tập IP CDN đáng tin** và realip module, không mù quáng chọn trái nhất trong chuỗi.
- Backend chỉ được nhận traffic từ Nginx (ở demo là loopback; production thường là private network). Nếu backend vẫn reachable từ Internet, một attacker có thể bypass toàn bộ bước sanitize bằng cách gọi trực tiếp.
- Nginx có thể còn các biến thể forwarding khác; hãy cấu hình **header allowlist**, loại các bản sao/biến thể do client tự gửi và không dựa vào một header chưa được kiểm soát.
- HTTP public port 80 nên có block redirect đến HTTPS với server_name được xác minh; đừng phản chiếu `$http_host` chưa tin thành absolute redirect.
- Cấu hình này giả định **một domain**. Nếu nhiều domain/tenant, validate host và chọn các header tương ứng với mapping đáng tin.

### 7.1. Vấn đề rất thường gặp với `$proxy_add_x_forwarded_for`

Nginx có thể dùng:

~~~nginx
proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
~~~

Lệnh này **append** IP peer vào header XFF hiện có. Nếu một request Internet tự gửi:

~~~http
X-Forwarded-For: 127.0.0.1
~~~

thì chuỗi chuyển tiếp có thể thành `127.0.0.1, 198.51.100.27`. Một backend lấy phần tử đầu tiên sẽ sai. **Không kết luận cú pháp append này luôn nguy hiểm hoặc luôn an toàn**; nó phụ thuộc edge phía trước đã sanitize và danh sách trusted hops. Với topology Nginx là edge đầu tiên, ví dụ ở trên chọn **overwrite** thay vì append.

### 7.2. Edge chưa chắc là CDN

Nếu sử dụng CDN/WAF/Ingress nhiều lớp, cấu hình proxy có thể khác:
- CDN có thể cấp `Forwarded` hoặc XFF theo giao thức riêng.
- Ingress chỉ được tin headers từ CIDR CDN/WAF đã xác minh.
- Traffic không qua CDN phải bị chặn.
- Nếu chuyển sang `Forwarded` chuẩn, backend/proxy cần thống nhất một định dạng, không để hai họ header xung đột.
- Mọi thay đổi provider hoặc route phải chạy lại tests về spoofed IP, host, scheme, path prefix và redirect.

**Hạ tầng quyết định độ tin cậy của metadata; Spring chỉ giúp giải mã/ứng dụng hóa nó.**

## 8. Dự án Java 17+ chạy được: WebFlux quan sát forwarded metadata

Dự án dùng **Spring Boot 3.3.13**, Gradle 8.x và JDK 17+. Phiên bản cố định nhằm minh họa API Spring Framework 6.1.x đồng nhất; production cần dùng dòng được hỗ trợ và kiểm thử lại.

**Mục đích demo:**
- `server.forward-headers-strategy=framework` để thấy forwarded headers thay đổi scheme/host.
- `GET /internal/request-view` yêu cầu quyền `diagnostics:read` qua HTTP Basic, để không công khai thông tin debug.
- `GET /public-link` trả canonical URL từ cấu hình đáng tin, không ghép Host của request.
- `GET /health` là public nhưng không trả thông tin nội bộ.
- Tự gửi forwarded headers vào local port trong test **cố ý chứng minh spoofing có thể xảy ra nếu backend reachable trực tiếp**. Đây không phải cấu hình an toàn cho Internet.
- Unit test `ForwardedHeaderTransformer.removeOnly(true)` chứng minh lựa chọn không tin forwarded headers.

### 8.1. Cấu trúc

~~~text
webflux-forwarded-boundary/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/demo/
    │   │   ├── ForwardedBoundaryApplication.java
    │   │   ├── SecurityConfig.java
    │   │   └── RequestController.java
    │   └── resources/application.properties
    └── test/java/demo/
        └── ForwardedHeadersTests.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'webflux-forwarded-boundary'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Không thêm `spring-boot-starter-web` Servlet. Spring Boot starter reactive dùng Reactor Netty theo mặc định trong ví dụ này.

`src/main/resources/application.properties`:

~~~properties
# DEMO CHỈ DÙNG LOCAL/SAU TRUSTED PROXY.
# FRAMEWORK không tự xác minh peer là proxy tin cậy.
server.forward-headers-strategy=framework

# Canonical URL từ cấu hình backend, không lấy từ request Host.
app.public-base-url=https://app.example.com
~~~

Ở production không được expose cổng backend trực tiếp. Nếu chưa có edge tin cậy, đặt `server.forward-headers-strategy=none` hoặc dùng cấu hình remove-only thích hợp.

### 8.2. Lớp khởi động

`src/main/java/demo/ForwardedBoundaryApplication.java`:

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ForwardedBoundaryApplication {

    public static void main(String[] args) {
        SpringApplication.run(ForwardedBoundaryApplication.class, args);
    }
}
~~~

### 8.3. Spring Security reactive: endpoint debug phải có auth

`src/main/java/demo/SecurityConfig.java`:

~~~java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        UserDetails observer = User.withUsername("observer")
            .password(encoder.encode("observer-demo-pass"))
            .authorities("diagnostics:read")
            .build();

        return new MapReactiveUserDetailsService(observer);
    }

    @Bean
    SecurityWebFilterChain security(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/health", "/public-link").permitAll()
                .pathMatchers("/internal/request-view")
                    .hasAuthority("diagnostics:read")
                .anyExchange().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(form -> form.disable())
            .build();
    }
}
~~~

- HTTP Basic chỉ để minh họa kiểm thử local. Production cần HTTPS và authentication phù hợp.
- `/internal/request-view` không public: host/scheme và một số request metadata có thể hỗ trợ reconnaissance.
- Không dùng forwarded host hoặc forwarded IP để tự cấp role/admin.
- Không disable CSRF: demo chỉ định nghĩa GET, không có side-effecting endpoints. Nếu thêm POST nghiệp vụ, áp CSRF theo loại credentials/browser đang dùng.
- Password demo được BCrypt hash; không hard-code credentials vào bản deploy thật.
- Không có servlet `HttpSecurity` trong project WebFlux.

### 8.4. Controller quan sát URI đã biến đổi

`src/main/java/demo/RequestController.java`:

~~~java
package demo;

import java.net.URI;
import java.util.Locale;
import java.util.Map;

import org.springframework.core.env.Environment;
import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
class RequestController {

    public record RequestView(
        String scheme,
        String host,
        int port,
        boolean forwardedHeaderStillVisible
    ) {}

    private final String publicBaseUrl;

    RequestController(Environment environment) {
        publicBaseUrl = environment
            .getRequiredProperty("app.public-base-url");
    }

    @GetMapping("/health")
    Mono<String> health() {
        return Mono.just("ok");
    }

    @GetMapping("/public-link")
    Mono<Map<String, String>> publicLink() {
        // Không tạo URL có token/redirect từ request Host.
        return Mono.just(Map.of(
            "url", publicBaseUrl + "/help"));
    }

    @GetMapping("/internal/request-view")
    Mono<RequestView> requestView(ServerHttpRequest request) {
        return Mono.fromSupplier(() -> {
            URI uri = request.getURI();

            boolean stillVisible =
                request.getHeaders().keySet().stream()
                    .map(name -> name.toLowerCase(Locale.ROOT))
                    .anyMatch(name -> name.equals("forwarded")
                        || name.startsWith("x-forwarded-"));

            return new RequestView(
                uri.getScheme(),
                uri.getHost(),
                uri.getPort(),
                stillVisible
            );
        });
    }
}
~~~

Điều đáng chú ý:
- `request.getURI()` có thể phản ánh metadata được `ForwardedHeaderTransformer` áp dụng trước khi controller chạy.
- `getHost()` là host quan sát sau biến đổi, **không có nghĩa host đó đã được edge xác minh** nếu backend reachable trực tiếp.
- Sau transformer, các forwarded headers được loại khỏi request downstream theo hợp đồng; test `forwardedHeaderStillVisible` minh họa điều này.
- `getPort()` có thể là `-1` khi URI không chứa port tường minh, kể cả khi scheme là HTTPS; **không kết luận port=-1 là lỗi**.
- `/public-link` lấy base URL từ cấu hình, nên header `X-Forwarded-Host: evil.example` không được chèn vào link do ứng dụng tạo. Canonical config phải được validate và kiểm soát quyền chỉnh sửa trong production.
- Controller không trả remote IP, Authorization, cookie hoặc thông tin mạng nhạy cảm.

## 9. Kiểm thử bằng WebTestClient qua server thật

Khi cần kiểm `server.forward-headers-strategy` của Spring Boot, dùng **server HTTP thật ở random port** thay vì chỉ binding mock WebFilterChain. Như vậy auto-configuration của Reactor Netty + forwarded transformer thực sự được dùng.

`src/test/java/demo/ForwardedHeadersTests.java`:

~~~java
package demo;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.server.adapter.ForwardedHeaderTransformer;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment =
    SpringBootTest.WebEnvironment.RANDOM_PORT)
class ForwardedHeadersTests {

    @LocalServerPort
    int port;

    private WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient.bindToServer()
            .baseUrl("http://localhost:" + port)
            .build();
    }

    @Test
    void healthIsPublicButDiagnosticsRequireAuthentication() {
        client.get().uri("/health")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("ok");

        client.get().uri("/internal/request-view")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void noForwardedHeadersMeansLocalHttpScheme() {
        client.get().uri("/internal/request-view")
            .headers(h -> h.setBasicAuth(
                "observer", "observer-demo-pass"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.scheme").isEqualTo("http")
            .jsonPath("$.host").isEqualTo("localhost")
            .jsonPath("$.forwardedHeaderStillVisible")
                .isEqualTo(false);
    }

    @Test
    void frameworkUsesTrustedRfc7239HeaderWhenPresent() {
        client.get().uri("/internal/request-view")
            .headers(h -> h.setBasicAuth(
                "observer", "observer-demo-pass"))
            .header("Forwarded",
                "for=198.51.100.27;proto=https;host=app.example.com")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.scheme").isEqualTo("https")
            .jsonPath("$.host").isEqualTo("app.example.com")
            .jsonPath("$.forwardedHeaderStillVisible")
                .isEqualTo(false);
    }

    @Test
    void frameworkUsesXForwardedSchemeAndHost() {
        client.get().uri("/internal/request-view")
            .headers(h -> h.setBasicAuth(
                "observer", "observer-demo-pass"))
            .header("X-Forwarded-Proto", "https")
            .header("X-Forwarded-Host", "app.example.com")
            .header("X-Forwarded-Port", "443")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.scheme").isEqualTo("https")
            .jsonPath("$.host").isEqualTo("app.example.com")
            .jsonPath("$.forwardedHeaderStillVisible")
                .isEqualTo(false);
    }

    @Test
    void directClientCouldSpoofHostIfBackendWerePublic() {
        // Test CHỦ Ý thể hiện rủi ro.
        // Không có trusted proxy sanitizer trong môi trường test.
        client.get().uri("/internal/request-view")
            .headers(h -> h.setBasicAuth(
                "observer", "observer-demo-pass"))
            .header("X-Forwarded-Host", "evil.example")
            .header("X-Forwarded-Proto", "https")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.host").isEqualTo("evil.example");
    }

    @Test
    void canonicalLinkCannotBePoisonedByForwardedHost() {
        client.get().uri("/public-link")
            .header("X-Forwarded-Host", "evil.example")
            .header("X-Forwarded-Proto", "https")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.url")
                .isEqualTo("https://app.example.com/help");
    }

    @Test
    void removeOnlyDiscardsBothHeaderFamiliesWithoutUsingThem() {
        ForwardedHeaderTransformer transformer =
            new ForwardedHeaderTransformer();
        transformer.setRemoveOnly(true);

        ServerHttpRequest raw = MockServerHttpRequest
            .get("http://internal.local:8080/check")
            .header("Forwarded",
                "for=198.51.100.9;proto=https;host=evil.example")
            .header("X-Forwarded-Proto", "https")
            .header("X-Forwarded-Host", "evil.example")
            .build();

        ServerHttpRequest transformed = transformer.apply(raw);

        assertThat(transformed.getURI())
            .isEqualTo(raw.getURI());
        assertThat(transformed.getHeaders().containsKey("Forwarded"))
            .isFalse();
        assertThat(transformed.getHeaders().containsKey(
            "X-Forwarded-Host")).isFalse();
        assertThat(transformed.getHeaders().containsKey(
            "X-Forwarded-Proto")).isFalse();
    }
}
~~~

### 9.1. Test gì và không chứng minh được gì?

1. `healthIsPublicButDiagnosticsRequireAuthentication`: kiểm URL debug chỉ cho user có quyền, không để anonymous lấy metadata.
2. `noForwardedHeadersMeansLocalHttpScheme`: với kết nối HTTP local không có Forwarded, app quan sát scheme HTTP.
3. `frameworkUsesTrustedRfc7239HeaderWhenPresent`: trong chế độ FRAMEWORK, app khôi phục scheme/host từ RFC 7239, và forwarded header không còn hiện downstream.
4. `frameworkUsesXForwardedSchemeAndHost`: minh họa kiểu X-Forwarded-* phổ biến ở proxy.
5. `directClientCouldSpoofHostIfBackendWerePublic`: **cố ý minh họa nguy cơ**: nếu backend có thể được gọi trực tiếp, client giả Host qua header được áp dụng! Test PASS không có nghĩa bảo mật đạt; nó chứng minh **vì sao cần edge sanitizer và network isolation**.
6. `canonicalLinkCannotBePoisonedByForwardedHost`: link quan trọng dùng base URL cấu hình thay vì phản chiếu untrusted host.
7. `removeOnlyDiscardsBothHeaderFamiliesWithoutUsingThem`: test API transformer độc lập, không cần khởi động server khác.

**Bộ test có chủ đích không tự mô phỏng Nginx**: muốn chứng minh chống giả header từ Internet, phải có integration/E2E test request **đi qua proxy thật** và kiểm rằng backend chỉ nhận giá trị đã sanitize. Test app trực tiếp không thể tự chứng minh ranh giới network đã được khóa.

### 9.2. Test header ở đâu?

Sau khi proxy đã sanitize:
- Gửi request bên ngoài có `Forwarded: proto=http;host=evil.example` và `X-Forwarded-Host: evil.example`.
- Đối chiếu public redirect/link vẫn dùng `https://app.example.com`.
- Đảm bảo backend không reachable trực tiếp từ Internet.
- Kiểm proxy log/observability cho request-id nhưng không ghi credentials hay nhạy cảm.
- Kiểm `X-Forwarded-For` chứa IP đã xác minh, không nhận chuỗi client tự gửi.
- Kiểm trường hợp nhiều hop và trường hợp sai Origin/Host.
- Kiểm HSTS/cookie Secure thực sự xuất hiện trên HTTPS public response.
- Kiểm redirect không có loop, không trỏ tới địa chỉ backend nội bộ.
- Với OIDC, kiểm `redirect_uri` khớp URI đã đăng ký và không bị Host poisoning.

## 10. Chạy và quan sát bằng curl

Từ thư mục dự án:

~~~bash
gradle bootRun
~~~

Nếu có Gradle Wrapper, dùng `./gradlew bootRun` (Unix/macOS) hoặc `gradlew.bat bootRun` (Windows). Chạy test riêng:

~~~bash
gradle test
~~~

Đây là ví dụ local HTTP, **không gửi credentials thật qua plaintext trên Internet**.

### 10.1. Request chưa có forwarded headers

~~~bash
curl -s -u observer:observer-demo-pass \
  http://localhost:8080/internal/request-view
~~~

Một response điển hình:

~~~json
{
  "scheme": "http",
  "host": "localhost",
  "port": 8080,
  "forwardedHeaderStillVisible": false
}
~~~

Kết quả `port` có thể thay đổi theo cổng thật và cách URI được biểu diễn. Khi dùng URI mặc định không chỉ định port, `port=-1` là hợp lệ.

### 10.2. Mô phỏng trusted proxy bằng forwarded headers

~~~bash
curl -s -u observer:observer-demo-pass \
  -H 'X-Forwarded-Proto: https' \
  -H 'X-Forwarded-Host: app.example.com' \
  -H 'X-Forwarded-Port: 443' \
  http://localhost:8080/internal/request-view
~~~

Kỳ vọng nổi bật:

~~~json
{
  "scheme": "https",
  "host": "app.example.com",
  "port": -1,
  "forwardedHeaderStillVisible": false
}
~~~

`port=-1` chỉ là một biểu diễn có thể gặp khi URI không ghi port tường minh. Điều cần xác nhận là **scheme, host, optional port và việc loại header** chứ không hard-code duy nhất một trị số port cho mọi runtime.

### 10.3. Cố tình giả mạo host để quan sát nguy cơ

~~~bash
curl -s -u observer:observer-demo-pass \
  -H 'X-Forwarded-Host: evil.example' \
  -H 'X-Forwarded-Proto: https' \
  http://localhost:8080/internal/request-view
~~~

Trong môi trường test backend nhận trực tiếp và đã bật `framework`, bạn có thể thấy:

~~~json
{
  "scheme": "https",
  "host": "evil.example",
  "port": -1,
  "forwardedHeaderStillVisible": false
}
~~~

**Điều này là cảnh báo, không phải một feature bảo mật.** Framework đã xử lý đúng về mặt API nhưng không biết header giả do ai gửi. Không cho phép đường gọi trực tiếp này trong triển khai production.

### 10.4. Canonical link vẫn không bị đổi

~~~bash
curl -s \
  -H 'X-Forwarded-Host: evil.example' \
  http://localhost:8080/public-link
~~~

Response:

~~~json
{
  "url": "https://app.example.com/help"
}
~~~

Bởi handler lấy public URL từ property đáng tin, không từ Host/X-Forwarded-Host. Với multi-tenant, hãy dùng bảng mapping hostname/tenant được quản trị và validate thay vì nối chuỗi raw header.

## 11. Những lỗi vận hành thường gặp và cách sửa

| Triệu chứng | Nguyên nhân có thể | Chẩn đoán và sửa |
| --- | --- | --- |
| Redirect trỏ về `http://10.0.0.x:8080` | App nhìn URI nội bộ, chưa dùng metadata public | Kiểm proxy gán scheme/host, Boot strategy phù hợp |
| Browser vào HTTPS nhưng redirect HTTPS lặp liên tục | App/ngữ cảnh security vẫn nghĩ request là HTTP | Kiểm forwarded proto, chain, proxy HTTPS enforcement và rewrite |
| Link reset mật khẩu chứa attacker domain | Tin Host/X-Forwarded-Host do client gửi | Canonical public URL + validate host + edge strip/overwrite |
| Cookie không có `Secure` trên browser HTTPS | Chính sách cookie và perceived scheme chưa đúng | Đặt cookie secure policy đúng; kiểm response qua HTTPS public |
| HSTS không xuất hiện trên browser | App nhìn HTTP hoặc edge không gắn header | Kiểm HSTS tại edge và Spring Security header policy |
| IP audit luôn là proxy | Không xử lý XFF hoặc không có trust-aware client IP source | Xác định topology, trusted hops, logging policy |
| Audit IP là `127.0.0.1` từ request Internet | Client giả XFF và proxy append không sanitize | Edge overwrite; không dùng raw XFF làm quyền |
| CORS báo sai origin/port | Public host/port khác backend, allowlist sai | Định nghĩa origin public rõ ràng; không lấy allowlist từ untrusted header |
| OAuth2 login callback báo mismatch | Redirect URI sai public scheme/host/prefix | Config canonical base URL/registered redirect URI, test proxy |
| URL dưới `/gateway` bị mất prefix | Proxy strip prefix nhưng transformer/links không được cấu hình tương ứng | Đồng bộ X-Forwarded-Prefix và routing; test end-to-end |
| URL bị double prefix | Proxy và app cùng thêm prefix | Thống nhất strip/preserve semantics |
| `server.forward-headers-strategy=native` không xử lý như kỳ vọng | Server implementation khác nhau | Đọc docs native server, dùng framework khi cần và bảo vệ proxy |
| `ForwardedHeaderTransformer` không được áp dụng | Bean name sai hoặc Boot config chưa bật | Kiểm Boot strategy hoặc bean tên `forwardedHeaderTransformer` |
| Local test cho host giả thấy `evil.example` | Backend đang trust header từ request trực tiếp | Đó là expected demonstration; khóa backend sau trusted proxy |
| App HTTP trực tiếp vẫn trả 200 | Cổng backend exposed, bypass edge HTTPS enforcement | Firewall/network isolation, không dựa vào forwarded-header config |
| Client gửi hai header Forwarded/XForwarded xung đột | Proxy không chuẩn hóa hai kiểu | Edge strip cả hai, tạo một định dạng được phê duyệt |
| Auth bị từ chối dù forwarded metadata đúng | Forwarded không phải credentials | Kiểm session/token/Basic và authorization độc lập |

## 12. Checklist thiết kế ranh giới tin cậy

### 12.1. Network và edge

- [ ] Cổng backend chỉ reachable từ proxy/ingress đã phê duyệt; không có đường gọi Internet bypass.
- [ ] Ingress xác minh Host bằng allowlist/canonical mapping, không phản chiếu raw `Host` vô điều kiện.
- [ ] Ingress xóa **cả** `Forwarded` và `X-Forwarded-*` chưa tin, gồm Proto, Host, For, Port, Prefix và biến thể được dùng.
- [ ] Proxy ghi lại headers từ scheme/host/client connection đã xác minh.
- [ ] Nếu nhiều hop, có danh sách trusted proxies/CIDRs, quy tắc chọn client IP rõ ràng, không blindly chọn phần tử đầu tiên.
- [ ] HTTP public được chuyển sang HTTPS đúng hostname; TLS và HSTS policy được kiểm qua browser.
- [ ] Traffic proxy → backend được bảo vệ bằng isolation và TLS/mTLS khi phù hợp.

### 12.2. Spring Boot/WebFlux

- [ ] Chọn tường minh `server.forward-headers-strategy` thích hợp với kiến trúc.
- [ ] Khi dùng `framework`, hiểu rằng ForwardedHeaderTransformer tin metadata đã vào app; framework không tự xác thực proxy.
- [ ] Không nhầm `ForwardedHeaderFilter` Servlet với `ForwardedHeaderTransformer` WebFlux.
- [ ] Không cấu hình trùng Boot auto transformer và custom bean không được review.
- [ ] Nếu không có proxy đáng tin, cân nhắc `none` và/hoặc transformer `removeOnly`.
- [ ] Khi có prefix, kiểm version/hành vi `X-Forwarded-Prefix` và đường dẫn downstream.
- [ ] Không coi `request.getRemoteAddress()` sau forwarded processing là bằng chứng authz.
- [ ] Không `block()` hoặc tự `subscribe()` trong reactive security handlers.

### 12.3. Spring Security và ứng dụng

- [ ] Authentication/authorization không phụ thuộc `X-Forwarded-For: 127.0.0.1` hoặc Host chưa tin.
- [ ] Redirect, OAuth2 callbacks và reset links dùng public base URL/mapping đã validate.
- [ ] Cookie Secure/HttpOnly/SameSite khớp HTTPS public và cơ chế session/CSRF.
- [ ] HSTS trên response HTTPS public được kiểm thực tế, không chỉ giả định app đã set.
- [ ] CORS allowlist/CSRF Origin checks không bị host spoofing điều khiển.
- [ ] Rate limiting và audit IP dựa trên identity/network đã xác minh.
- [ ] Không log Authorization, cookie, reset token, CSRF token hoặc client IP nhạy cảm quá mức.
- [ ] Test positive qua proxy thật và negative headers giả/đa hop/bypass route.
- [ ] Monitoring có cảnh báo redirect tới host lạ, tăng 3xx loop, IP spoofing và backend direct access.

## 13. Câu hỏi luyện tập và lời giải

**Câu 1.** Browser dùng HTTPS nhưng backend Reactor Netty nhận HTTP. Điều đó có bất thường không?

**Đáp án:** Không khi TLS được terminate ở reverse proxy. Cần metadata công khai đáng tin và bảo vệ riêng kênh proxy → backend.

**Câu 2.** `X-Forwarded-Proto: https` có chứng minh socket backend là TLS không?

**Đáp án:** Không. Header chỉ thông báo scheme mà proxy cho biết, không phải bằng chứng mã hóa ở hop hiện tại.

**Câu 3.** Khi nào `server.forward-headers-strategy=framework` an toàn?

**Đáp án:** Khi app chỉ nhận request từ trusted proxies và proxy đã xóa/ghi đè headers chưa tin ở trust boundary, với topology và hostname được kiểm.

**Câu 4.** Vì sao Spring không tự phân biệt Forwarded do Nginx và attacker gửi?

**Đáp án:** Cả hai xuất hiện là HTTP headers. App không có bằng chứng độc lập về nguồn gốc từng field nếu network/proxy không bảo vệ.

**Câu 5.** Proxy xóa `Forwarded` nhưng giữ nguyên `X-Forwarded-Host` của client, có đủ không?

**Đáp án:** Không. Spring hỗ trợ cả hai họ; cần loại header không tin của **cả hai**.

**Câu 6.** Vì sao `X-Forwarded-For` phần tử đầu không luôn là IP đáng tin?

**Đáp án:** Proxy append có thể giữ phần tử do client giả, và chuỗi qua nhiều hop đòi chính sách trusted hops.

**Câu 7.** `none`, `native`, `framework` khác nhau điều gì?

**Đáp án:** Là lựa chọn Boot về **cách xử lý** forwarded metadata: không bật, HTTP server native, hoặc Spring Framework. Không giá trị nào tự tạo firewall.

**Câu 8.** `removeOnly(true)` làm gì?

**Đáp án:** Loại forwarded headers khỏi request downstream mà không dùng nội dung chúng để rewrite URI.

**Câu 9.** Làm sao tránh password-reset link trỏ đến `evil.example`?

**Đáp án:** Dùng canonical public base URL/mapping đã validate và bảo đảm ingress loại/ghi đè header Host/Forwarded chưa tin.

**Câu 10.** Đặt `X-Forwarded-Prefix: /admin` có nên tự mở quyền admin không?

**Đáp án:** Không. Prefix chỉ là metadata routing, không phải authorization claim. Host/path phải được kiểm riêng.

**Câu 11.** Vì sao có thể bị redirect loop khi TLS termination?

**Đáp án:** Browser HTTPS nhưng backend thấy HTTP rồi liên tục redirect HTTPS; cần scheme public đáng tin và kiểm chính sách redirect giữa app/proxy.

**Câu 12.** HSTS có nên chỉ xem qua response HTTP nội bộ?

**Đáp án:** Không. Phải xác minh response qua **HTTPS browser-facing** có header phù hợp và không làm hỏng domain/subdomains.

**Câu 13.** Có thể dùng IP `127.0.0.1` lấy từ XFF để bỏ qua authentication không?

**Đáp án:** Tuyệt đối không. Header có thể giả mạo; authorization phải dựa trên identity đáng tin và policy.

**Câu 14.** Unit test transformer có đủ kiểm ranh giới proxy production không?

**Đáp án:** Không. Cần E2E request qua ingress và network test chứng minh backend không reachable trực tiếp.

**Câu 15.** CORS có chấp nhận mọi Origin vì `X-Forwarded-Host` trông như domain của mình không?

**Đáp án:** Không. CORS allowlist phải cố định/validate theo cấu hình đáng tin; forwarded header không phải bằng chứng Origin.

**Câu 16.** Khi dùng multiple reverse proxies, có nên luôn dùng `$proxy_add_x_forwarded_for`?

**Đáp án:** Không thể kết luận chung. Phải xem proxy trước đã sanitize chưa, mạng tin cậy, real IP module và quy tắc chọn IP.

**Câu 17.** Vì sao `RequestView.port=-1` không nhất thiết là lỗi?

**Đáp án:** Java URI trả -1 khi không có port tường minh; HTTPS mặc định 443 có thể không xuất hiện như số trong URI.

**Câu 18.** Một test cố ý gửi `X-Forwarded-Host: evil.example` rồi thấy backend nhận evil.example — test FAIL hay PASS?

**Đáp án:** Đây là **test mô tả khả năng spoof** của chế độ FRAMEWORK khi backend bị gọi trực tiếp. PASS theo mục đích giáo dục, nhưng sản phẩm chỉ an toàn khi proxy boundary chặn đầu vào đó.

**Câu 19.** API WebFlux cần bean transformer thủ công khi đã cấu hình `server.forward-headers-strategy=framework`?

**Đáp án:** Không nhất thiết; Boot cung cấp cơ chế phù hợp. Tránh cấu hình trùng nếu chưa có lý do.

**Câu 20.** Biện pháp quan trọng nhất để không tin nhầm forwarded headers là gì?

**Đáp án:** **Chặn truy cập trực tiếp backend + sanitize/recreate cả Forwarded và X-Forwarded-* tại trusted proxy**, rồi mới bật diễn giải trong app.

## 14. Tài liệu tham khảo chính thức

- Spring Framework 6.1 — WebFlux Forwarded Headers: https://docs.spring.io/spring-framework/reference/6.1/web/webflux/reactive-spring.html#webflux-forwarded-headers
- Spring Framework — `ForwardedHeaderTransformer` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/server/adapter/ForwardedHeaderTransformer.html
- Spring Boot 3.3 — Running Behind a Front-end Proxy Server: https://docs.spring.io/spring-boot/3.3/how-to/webserver.html#howto.webserver.use-behind-a-proxy-server
- Spring Boot 3.3 — `ServerProperties.ForwardHeadersStrategy`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/web/ServerProperties.ForwardHeadersStrategy.html
- Spring Security — Forwarded Headers và HTTP Security: https://docs.spring.io/spring-security/reference/features/exploits/http.html
- Spring Security — HSTS và Security Response Headers: https://docs.spring.io/spring-security/reference/features/exploits/headers.html
- RFC 7239 — Forwarded HTTP Extension: https://www.rfc-editor.org/rfc/rfc7239
- OWASP — HTTP Headers Security Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/HTTP_Headers_Cheat_Sheet.html
- OWASP — Unvalidated Redirects and Forwards: https://cheatsheetseries.owasp.org/cheatsheets/Unvalidated_Redirects_and_Forwards_Cheat_Sheet.html

**Ghi nhớ:** `Forwarded` và `X-Forwarded-*` là **metadata hữu ích nhưng không tự đáng tin**. Trong WebFlux, `ForwardedHeaderTransformer` khôi phục scheme/host/port khi ứng dụng cho phép, không kiểm chứng ai đã gửi header. Muốn xử lý đúng và an toàn, hãy **sanitization tại edge + chỉ cho trusted proxy truy cập backend + cấu hình Boot đúng + kiểm thử positive/negative**, rồi thiết kế redirect, HTTPS/HSTS/cookie/CSRF và IP-based observability dựa trên ranh giới tin cậy đã được chứng minh.
