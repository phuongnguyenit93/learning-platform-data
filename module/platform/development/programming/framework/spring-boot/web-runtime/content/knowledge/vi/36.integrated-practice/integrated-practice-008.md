# Đặt ứng dụng Spring Boot sau reverse proxy với chuyển tiếp header và CORS đúng phạm vi

Một ứng dụng Spring Boot có thể chạy khỏe trên `http://127.0.0.1:8080` nhưng khi được đặt sau NGINX, load balancer hoặc API gateway lại sinh `Location` sai hostname, redirect về HTTP dù người dùng truy cập HTTPS, session cookie không gửi lại, hoặc frontend bị báo **CORS policy blocked**. Những lỗi này không phải một vấn đề duy nhất: chúng liên quan tới **địa chỉ public khác địa chỉ upstream**, **Forwarded/X-Forwarded-* headers**, **đường dẫn prefix**, **ranh giới tin cậy của proxy**, **same-origin/CORS của trình duyệt** và **cơ chế bảo mật cookie/CSRF**.

Bài thuộc nhóm **Thực hành tổng hợp** của module Spring Boot web-runtime. Ví dụ chính sử dụng **Java 17+, Spring Boot 3.3.x, Spring MVC/embedded Tomcat, NGINX và một frontend khác origin**. Ta xây một API tạo/đọc đơn hàng nhỏ, triển khai dưới prefix public `/shop`, cấu hình CORS **chỉ cho API orders và origin được phép**, kiểm tra `Location`/redirect, preflight `OPTIONS`, các origin bị từ chối và tác động của HTTPS termination.

## 1. Bài toán cụ thể và kết quả mong muốn

Giả sử hệ thống có cấu trúc:

```text
Browser / frontend
  Origin: https://app.example.test
          |
          | fetch() qua HTTPS
          v
Public reverse proxy NGINX
  https://api.example.test:443
  Public prefix: /shop
          |
          | HTTP nội bộ, đường prefix được bỏ
          v
Spring Boot (cùng host trong bài lab)
  http://127.0.0.1:8080
  Internal root: /
  Internal route: /api/v1/orders
```

Frontend gọi:

```http
POST https://api.example.test/shop/api/v1/orders
Origin: https://app.example.test
Content-Type: application/json

{"sku":"BOOK-001","quantity":2}
```

NGINX nhận HTTPS ở public endpoint và chuyển tới:

```http
POST http://127.0.0.1:8080/api/v1/orders
Host: api.example.test
X-Forwarded-Proto: https
X-Forwarded-Host: api.example.test
X-Forwarded-Port: 443
X-Forwarded-Prefix: /shop
X-Forwarded-For: <client-address>
Origin: https://app.example.test
Content-Type: application/json
```

`<client-address>` là giá trị được proxy đáng tin tự xác lập, **không lấy một chuỗi tùy ý do client gửi làm danh tính đã được xác minh**.

Khi tạo resource thành công, client cần thấy:

```http
HTTP/1.1 201 Created
Location: https://api.example.test/shop/api/v1/orders/1
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Expose-Headers: Location, X-Request-ID
Vary: Origin
Content-Type: application/json
```

Các headers có thể được thêm khác nhau về ordering/casing. ID thay đổi theo runtime; `Location` là ví dụ. Khi browser gửi request JSON cross-origin, có thể có một **preflight OPTIONS trước POST**. Frontend từ `https://evil.example.test` hoặc `http://app.example.test` **không** được phép đọc response qua CORS chỉ vì có đuôi hostname giống hoặc cùng path API.

**Quan trọng:** tên miền `example.test` là ví dụ thuộc vùng tên dành cho thử nghiệm, không phải website triển khai công khai. Muốn thực hiện HTTPS end-to-end ở local, cấu hình hosts/internal DNS và certificate được máy kiểm thử tin cậy, hoặc thay bằng domain nội bộ và certificate thật do bạn quản lý.

## 2. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt public URL, internal URL, client origin, target origin và proxy hop.
2. Biết tại sao Spring Boot có thể thấy `http://127.0.0.1:8080` trong khi browser thấy `https://api.example.test/shop`.
3. Giải thích HTTP `Host`, RFC 7239 `Forwarded`, `X-Forwarded-Proto`, `X-Forwarded-Host`, `X-Forwarded-Port`, `X-Forwarded-Prefix` và `X-Forwarded-For`.
4. Sử dụng `server.forward-headers-strategy=none/native/framework` đúng Spring Boot 3.3.
5. Giải thích vì sao edge reverse proxy phải strip/overwrite forwarded headers trước khi application tin chúng.
6. Thiết kế NGINX `location /shop/` + `proxy_pass .../` với rule bỏ prefix rõ ràng.
7. Tạo `Location` và redirect từ request metadata được proxy chuẩn hóa, không hardcode internal URL.
8. Phân biệt **same-origin** và **same-site**, simple request, preflight và actual CORS request.
9. Cấu hình Spring MVC CORS theo **route và origin cụ thể**, không đặt `allowedOrigins("*")` cho toàn bộ ứng dụng.
10. Hiểu `Access-Control-Allow-Origin`, `Allow-Methods`, `Allow-Headers`, `Expose-Headers`, `Allow-Credentials`, `Max-Age` và `Vary`.
11. Kiểm thử preflight hợp lệ/bị từ chối, path ngoài scope, redirect public và real HTTP bằng `MockMvc`/`RANDOM_PORT`.
12. Phối hợp Spring Security và CORS nếu có authentication.
13. Tránh nhầm CORS với CSRF, authentication, authorization, firewall hoặc chống giả mạo Host.
14. Kiểm tra cookie `Secure`, `HttpOnly`, `SameSite`, `Path` và cross-site credential flows.
15. Xử lý lỗi khi TLS ở proxy, HTTPS redirect, OAuth2 callback, ingress prefix, cache/CDN và multi-proxy hops.

## 3. Các loại địa chỉ: public origin, internal origin và frontend origin

Một **origin** trong mô hình trình duyệt là bộ ba `(scheme, host, port)`. Path **không** tham gia vào so sánh origin.

| URL | Origin | Nhận xét |
| --- | --- | --- |
| `https://api.example.test/shop/api/v1/orders` | `https://api.example.test:443` | API public |
| `https://api.example.test/other` | `https://api.example.test:443` | Cùng origin dù path khác |
| `https://app.example.test` | `https://app.example.test:443` | **Khác origin** với API |
| `http://app.example.test` | `http://app.example.test:80` | **Khác origin** vì scheme |
| `https://app.example.test:8443` | `https://app.example.test:8443` | **Khác origin** vì port |
| `http://127.0.0.1:8080` | `http://127.0.0.1:8080` | Backend nội bộ |

CORS giới hạn những **origin** mà browser cho phép JavaScript đọc response từ server khác origin. Nó không phải hệ thống kiểm soát đường đi mạng. Một non-browser client như `curl` vẫn gọi HTTP API trực tiếp được nếu mạng và authentication cho phép, kể cả không có `Access-Control-Allow-Origin`.

### 3.1. Same-site không giống same-origin

`https://app.example.test` và `https://api.example.test` là hai **origin khác nhau** (hostname khác), do đó frontend fetch cần xử lý CORS. Nhưng theo cách xác định schemeful site của browser hiện đại, hai host cùng registrable domain và scheme HTTPS có thể là **same-site**. Cookie `SameSite=Lax` và CORS là hai cơ chế **khác** nhau.

Ngược lại `https://shop.other-example.test` gọi `https://api.example.test` là **cross-site** thực sự; nếu cookie cần được gửi trong cross-site fetch, thường phải dùng `SameSite=None; Secure` cùng `credentials:"include"` và CORS credential policy phù hợp. Các browser có thể còn hạn chế third-party cookies, nên dù headers đúng vẫn cần browser E2E.

### 3.2. Prefix /shop không nằm trong CORS origin

Một cấu hình CORS không nên viết `allowedOrigins("https://app.example.test/shop")`: đó không phải một origin hợp lệ, vì origin **không có path**. Scope theo đường API được quyết định bởi `CorsRegistry.addMapping(...)` hoặc `CorsConfigurationSource`. Hai chiều độc lập:

- **Origin scope:** ai có quyền dùng JavaScript để đọc response trong browser?
- **Path scope:** các HTTP endpoints nào phát CORS response headers?

Trong bài, origin duy nhất là `https://app.example.test`; các URL Java được cấu hình CORS là `/api/v1/orders` và `/api/v1/orders/**`. NGINX đã bỏ public prefix `/shop` trước khi chuyển đến Spring MVC.

## 4. Một request đi qua reverse proxy thay đổi điều gì?

```text
Browser request:
GET https://api.example.test/shop/api/v1/orders/7

(1) NGINX TLS listener :443
    scheme = https
    host = api.example.test
    public context prefix = /shop

(2) NGINX chuyển upstream:
    GET http://127.0.0.1:8080/api/v1/orders/7
    socket scheme = http
    socket host/port = 127.0.0.1:8080

(3) Header do proxy xác lập:
    X-Forwarded-Proto: https
    X-Forwarded-Host: api.example.test
    X-Forwarded-Port: 443
    X-Forwarded-Prefix: /shop

(4) Spring Boot FRAMEWORK:
    ForwardedHeaderFilter chuẩn hóa request-facing
    scheme / host / port / context-path

(5) Controller:
    tạo Location/redirect theo public request
```

Nếu không xử lý forwarded headers, controller dùng `ServletUriComponentsBuilder` hoặc `HttpServletRequest.getScheme()` có thể nhìn thấy `http`, host internal và thiếu prefix. Kết quả là link nội bộ bị rò ra client, redirect về HTTP hoặc OAuth2 callback mismatch.

### 4.1. Host và X-Forwarded-Host

`Host` là HTTP request target authority trong HTTP/1.1; reverse proxy có thể giữ Host public hoặc thay bằng upstream host. `X-Forwarded-Host` chuyển thông tin public host qua proxy khi cần. `Host` và `X-Forwarded-Host` **đều là bề mặt có thể bị kẻ tấn công kiểm soát nếu edge không validate/overwrite**.

Ví dụ kẻ tấn công gửi:

```http
Host: attacker.example.test
X-Forwarded-Host: attacker.example.test
X-Forwarded-Proto: https
```

Nếu ứng dụng phản chiếu host này vào `Location`/password-reset link, attacker có thể gây **Host header injection**, phishing hoặc redirect sai. Do đó không chỉ “bật framework” là xong: cần **proxy trust boundary**.

### 4.2. X-Forwarded-For không phải chứng thực danh tính

`X-Forwarded-For` thường thể hiện client IP và các proxy hops. Tuy nhiên chuỗi ở đầu có thể do client tùy ý đưa vào nếu edge dùng cơ chế append mà không loại bỏ header cũ. Không dùng `X-Forwarded-For` làm bằng chứng authentication, quyết định tài khoản, bỏ qua MFA hay ban IP tuyệt đối nếu chưa xác định trusted chain. Dùng network ACL, identity và thư viện phân tích trusted proxies có chính sách rõ.

### 4.3. RFC 7239 Forwarded

RFC 7239 định nghĩa cú pháp chuẩn:

```http
Forwarded: for=198.51.100.42;proto=https;host=api.example.test
```

Các `X-Forwarded-*` là thông lệ không chuẩn nhưng rất phổ biến. Nếu edge tạo `X-Forwarded-*` nhưng vẫn để client gửi `Forwarded` tùy ý, một framework có thể ưu tiên header khác bạn nghĩ. **Loại bỏ/chuẩn hóa cả hai họ headers**, không chỉ một header duy nhất.

## 5. Spring Boot 3.3: NONE, NATIVE và FRAMEWORK

Property quan trọng:

```properties
server.forward-headers-strategy=framework
```

| Giá trị | Hành vi | Khi dùng |
| --- | --- | --- |
| `NONE` | Không áp forwarded headers để sửa request metadata | App public trực tiếp hoặc không có trusted proxy |
| `NATIVE` | Dùng cơ chế native của embedded web server, ví dụ Tomcat `RemoteIpValve` | Proxy headers đơn giản và server native hỗ trợ đủ |
| `FRAMEWORK` | Spring Framework `ForwardedHeaderFilter` cho Servlet, `ForwardedHeaderTransformer` cho reactive | Cần hiểu public scheme/host/prefix, nhất là `X-Forwarded-Prefix` |

**Spring Boot 3.3** không nên bị áp defaults của phiên bản khác. Boot docs nêu trong một số supported cloud platforms, default có thể là `NATIVE`; nếu không, thường là `NONE`. Vì vậy khi hệ thống thật phụ thuộc forwarded metadata, **đặt property tường minh**, kiểm tra runtime config và tests.

### 5.1. Vì sao chọn FRAMEWORK trong bài?

Bài có **public prefix `/shop` bị reverse proxy bỏ trước upstream**. `X-Forwarded-Prefix` được Spring Framework `ForwardedHeaderFilter` dùng để trình bày context path/URI public. NATIVE có thể đủ cho `X-Forwarded-For` và `X-Forwarded-Proto` nhưng mức hỗ trợ prefix/host/port tùy embedded server. **Không giả định NATIVE tự hỗ trợ mọi X-Forwarded-***.

### 5.2. Có cần tự tạo ForwardedHeaderFilter bean không?

Khi dùng Boot 3.3:

```properties
server.forward-headers-strategy=framework
```

Boot tự cấu hình đường xử lý phù hợp. **Không đăng ký thêm `ForwardedHeaderFilter` thủ công** mà không có lý do, vì có thể làm xử lý headers hai lần, ordering/dispatch khó hiểu. Nếu ứng dụng tùy biến filters, kiểm tra Spring Boot auto-registration trước rồi mới điều chỉnh.

### 5.3. ForwardedHeaderFilter làm gì?

Với Servlet stack, filter wrap request để các APIs downstream như `getScheme()`, `getServerName()`, `getServerPort()`, `isSecure()` và đường public context được phản ánh theo forwarded headers đã tin cậy. Nó cũng loại các headers được xử lý khỏi request wrapper để hạn chế tác động về sau. Spring Framework docs yêu cầu filter chạy sớm trước những filters dùng request metadata.

**Filter không tự xác minh nguồn gốc của headers qua network.** Nếu backend bị expose trực tiếp và bất kỳ client nào cũng có thể gửi `X-Forwarded-Host`, FRAMEWORK có thể biến input giả thành request metadata. Chỉ bật khi hạ tầng đã thiết lập trust boundary phù hợp.

### 5.4. ForwardedHeaderFilter removeOnly

Spring Framework có mode `removeOnly` để **bỏ** forwarded headers mà không sử dụng chúng. Đây là phương án khi không tin proxy metadata nhưng muốn các lớp downstream không đọc forwarded headers thô. Trong Spring Boot property đơn giản, dùng `NONE` để không apply forwarding; nếu cần removeOnly, phải thiết kế một filter strategy có thứ tự chuẩn và không đồng thời đăng ký một forwarding filter khác. Không sử dụng removeOnly nếu cần phục hồi public scheme/host/prefix trong cùng request mà không có nguồn dữ liệu đáng tin thay thế.

### 5.5. Tomcat redirect-context-root

Tài liệu Spring Boot 3.3 lưu ý: khi dùng Tomcat và TLS termination ở reverse proxy, nên xét cấu hình:

```properties
server.tomcat.redirect-context-root=false
```

để `X-Forwarded-Proto` được xử lý trước redirect do Tomcat thực hiện đối với context root. Đây là một guard riêng cho trường hợp redirect ở container; không thay việc cấu hình trusted forwarded headers/NGINX.

## 6. Quy tắc tin cậy đối với reverse proxy

Một request Internet không được quyền tự nói “tôi vốn truy cập bằng HTTPS từ host chính thức” chỉ bằng cách gắn `X-Forwarded-Proto: https`. Giá trị forwarded chỉ có nghĩa khi một **proxy đáng tin** đặt nó.

**Ranh giới tin cậy của bài:** NGINX là **edge đầu tiên nhận Internet**. NGINX có hostname/certificate cố định, nhận public traffic, strip hoặc overwrite `Forwarded`/`X-Forwarded-*`, rồi chuyển tới Spring Boot chỉ bind `127.0.0.1` trên cùng host. Các client bên ngoài **không thể mở socket trực tiếp tới upstream**.

### 6.1. Checklist edge

- Validate Host bằng `server_name` và default server policy; từ chối host lạ.
- Terminate TLS đúng certificate và HTTPS redirects theo public authority.
- Strip inbound `Forwarded`, các `X-Forwarded-*` có ý nghĩa (ít nhất Proto/Host/Port/Prefix/For/Ssl/Server) rồi đặt giá trị authoritative.
- Hạn chế direct access vào upstream qua loopback/private subnet/security groups/network policy.
- Không dùng input client tùy ý để tạo `X-Forwarded-Host`.
- Nếu có nhiều proxy hops, đặt rõ ai được phép append/overwrite và nguồn nào là trusted.
- Không tin `X-Forwarded-For` làm authorization; các audit/rate limits dùng verified client attribution qua trusted chain.
- Theo dõi HTTPS scheme, Host và prefix trong logs **mà không log secrets/raw cookies**.
- Test cả trường hợp có header `Forwarded` giả và nhiều giá trị `X-Forwarded-For`.
- Nếu có service mesh/ingress, tránh hai tầng cùng sửa prefix hoặc append scheme khác nhau.

### 6.2. Khi NGINX không phải edge duy nhất

Ví dụ:

```text
Internet -> CDN -> Cloud Load Balancer -> NGINX -> Spring
```

Trong mô hình này, địa chỉ `$remote_addr` tại NGINX có thể là IP của Load Balancer, không phải client cuối. Phải thiết lập tin cậy IP ranges của LB/CDN tại module real IP hoặc ingress tương ứng, xác định chính xác hop nào giữ IP thật, và strip các headers do Internet tự tạo **ngay tại mép ngoài**. Đừng dùng `$proxy_add_x_forwarded_for` không kiểm soát tại edge rồi giả định phần tử đầu tiên luôn là IP thật.

## 7. NGINX HTTPS và rewrite public prefix

Ví dụ cấu hình **NGINX cùng máy với Spring Boot**. Domain/certificate paths được dùng để minh họa; bạn phải cấp certificate đáng tin cho domain thử nghiệm trước khi chạy thật.

File gợi ý `/etc/nginx/conf.d/api-proxy.conf`:

```nginx
# Nếu cần một default server khác, từ chối Host không hợp lệ
# ở chính edge thay vì proxy toàn bộ tên lạ về backend.

server {
    listen 80;
    server_name api.example.test;

    return 308 https://api.example.test$request_uri;
}

server {
    listen 443 ssl;
    server_name api.example.test;

    ssl_certificate     /etc/nginx/tls/api.crt;
    ssl_certificate_key /etc/nginx/tls/api.key;

    # Người dùng gửi /shop không có slash.
    location = /shop {
        return 308 https://api.example.test/shop/;
    }

    location /shop/ {
        proxy_http_version 1.1;

        # Slash cuối: /shop/api/v1/orders
        # trở thành upstream /api/v1/orders.
        proxy_pass http://127.0.0.1:8080/;

        # Host công khai cố định trong mẫu một virtual host.
        proxy_set_header Host api.example.test;

        # Không cho client-supplied RFC 7239 đi tiếp.
        proxy_set_header Forwarded "";

        # Edge tự xác lập thông tin scheme/host/port/prefix.
        proxy_set_header X-Forwarded-Proto  https;
        proxy_set_header X-Forwarded-Host   api.example.test;
        proxy_set_header X-Forwarded-Port   443;
        proxy_set_header X-Forwarded-Prefix /shop;

        # Vì đây là edge, không giữ X-Forwarded-For
        # do client tự gửi đến.
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Real-IP       $remote_addr;

        # Vô hiệu hóa một số header cũ/không dùng.
        proxy_set_header X-Forwarded-Ssl "";
        proxy_set_header X-Forwarded-Server "";

        proxy_connect_timeout 3s;
        proxy_read_timeout    30s;
        proxy_send_timeout    30s;
    }
}
```

### 7.1. Tại sao proxy_pass phải có slash cuối?

So sánh trong một prefix location:

```nginx
location /shop/ {
    proxy_pass http://127.0.0.1:8080/;
}
```

Với dạng upstream URI kết thúc bằng `/`, NGINX thay phần URI khớp `/shop/` thành `/`: external `/shop/api/v1/orders` → upstream `/api/v1/orders`.

Ngược lại:

```nginx
location /shop/ {
    proxy_pass http://127.0.0.1:8080;
}
```

Khi `proxy_pass` **không có URI phần đuôi**, cách chuyển URI khác: thường chuyển nguyên request URI (với chi tiết phụ thuộc rewrite/normalized URI), khiến upstream vẫn nhận `/shop/api/v1/orders`. Khi controller chỉ map `/api/v1/orders`, request sẽ 404. **Không thay dấu slash khi chưa test**.

### 7.2. Tại sao chuyển X-Forwarded-Prefix=/shop?

Spring Boot upstream root là `/`. NGINX đã bỏ `/shop` trong URI đưa vào. Nhưng khi tạo absolute URL, app cần biết public path có `/shop`. `X-Forwarded-Prefix` cung cấp ngữ cảnh đó cho FRAMEWORK strategy để các URI builders tạo link/redirect có prefix.

Không đồng thời đặt:

```properties
server.servlet.context-path=/shop
```

trong cùng topology đang strip prefix rồi lại set forwarded prefix mà chưa thiết kế rõ. Hai cách phục hồi path có thể bị nhân đôi `/shop/shop` hoặc sai mappings. Chọn **một mô hình rõ**: proxy rewrite + forwarded prefix như bài, hoặc giữ prefix và cấu hình app context path phù hợp, rồi test mọi route.

### 7.3. NGINX không tạo CORS headers trong cấu hình mẫu

Ví dụ không có:

```nginx
add_header Access-Control-Allow-Origin *;
```

Ta để **Spring MVC** là nguồn duy nhất xác định CORS scope. Nếu cả NGINX và app thêm ACAO, có thể tạo headers trùng/khác nhau, browser từ chối hoặc gateway cache sai. Chọn một chủ thể sở hữu policy; trong bài này MVC sở hữu CORS và NGINX chỉ forward.

### 7.4. Đừng quên phương thức OPTIONS

CORS preflight là HTTP `OPTIONS` với `Origin` và `Access-Control-Request-Method`. NGINX mẫu không chặn OPTIONS, nên request đi qua upstream để Spring MVC đánh giá. Nếu gateway chặn OPTIONS bằng 405/401 hoặc trả wildcard riêng, frontend sẽ bị lỗi trước khi POST thực sự được gửi.

### 7.5. Cấu hình chỉ dùng được khi certificate tồn tại

Lệnh:

```bash
sudo nginx -t
sudo systemctl reload nginx
```

chỉ chạy thành công khi NGINX đã cài đặt, paths/certificate hợp lệ và bạn có quyền reload. Với domain `.test`, có thể dùng internal CA hoặc công cụ tạo local certificate được máy kiểm thử tin cậy; **đừng thay bằng `-k` vô điều kiện rồi tuyên bố TLS đã được xác thực**.

### 7.6. Một host thật thường còn default-server policy

`server_name api.example.test` chọn virtual host, nhưng nếu đây là server duy nhất trên listener, NGINX có thể xử lý các Host khác trong default vhost tùy cấu hình. Production cần **default_server riêng để reject Host lạ** và certificate/SNI handling phù hợp. Sample trên giả định edge đã có cấu hình virtual host/default server hợp lệ; không phải hardening checklist hoàn chỉnh.

## 8. Ứng dụng Spring Boot: cấu trúc project

Ta dùng Gradle và Java 17. API tạo đơn hàng trả `201 Location` để kiểm tra public URL, GET theo ID và một redirect tới canonical URL.

```text
proxy-cors-lab/
  settings.gradle
  build.gradle
  gradlew
  gradlew.bat
  gradle/wrapper/...
  src/
    main/
      java/demo/
        ProxyCorsLabApplication.java
        OrderInput.java
        OrderView.java
        OrderStore.java
        OrdersController.java
        CorsPolicy.java
        CorrelationFilter.java
      resources/
        application.properties
    test/
      java/demo/
        ProxyCorsMvcTest.java
        ProxyCorsHttpTest.java
```

**Không sử dụng database hoặc authentication trong demo**. Dữ liệu được giữ in-memory và mất sau restart; endpoints được dùng trong lab riêng, không đưa ra Internet thật. Ở production, phải bổ sung Spring Security, authorization theo actor/tenant, persistence và audit.

### 8.1. settings.gradle

```groovy
rootProject.name = 'proxy-cors-lab'
```

### 8.2. build.gradle

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Dùng [Spring Initializr](https://start.spring.io/) để có Gradle Wrapper và project skeleton, rồi thay files theo bài. Nếu chỉ tạo `build.gradle` thủ công mà chưa có `gradlew`, cần Gradle tương thích để tạo wrapper. Spring Boot 3.3 đi với Spring Framework 6.1; đừng trộn Boot 4.x API imports hoặc `javax.validation.*` vào mã Java 17 ở đây.

### 8.3. application.properties

```properties
spring.application.name=proxy-cors-lab

# Mô hình NGINX trên CÙNG MÁY với app.
server.address=127.0.0.1
server.port=8080

# Đọc metadata public do trusted NGINX tạo.
server.forward-headers-strategy=framework
server.tomcat.redirect-context-root=false

# Chỉ một frontend origin cụ thể.
app.cors.allowed-origin=https://app.example.test

# Boot 3.3 graceful shutdown cần cấu hình rõ.
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s

# Giới hạn thông tin lỗi mặc định.
server.error.include-message=never
server.error.include-stacktrace=never
server.error.include-binding-errors=never

# Actuator chỉ ở backend loopback, không public qua proxy sample.
management.endpoints.web.exposure.include=health
management.endpoint.health.show-details=never
```

**Cảnh báo triển khai:** `server.forward-headers-strategy=framework` là lựa chọn đúng **chỉ khi NGINX đáng tin và upstream không được truy cập trực tiếp từ Internet**. Nếu container app ở Pod khác, `127.0.0.1` không còn nghĩa “cùng máy với NGINX”; khi đó app có thể cần bind `0.0.0.0` nhưng chỉ được truy cập qua ingress/service mesh/network policies. Không copy lab config sang cluster mà không đổi network topology.

## 9. Java 17+ code: entry point và model

### 9.1. ProxyCorsLabApplication.java

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ProxyCorsLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(ProxyCorsLabApplication.class, args);
    }
}
```

`@SpringBootApplication` component-scans `demo`, nên các controller, service, config và filter dưới cùng package được đăng ký.

### 9.2. OrderInput.java

```java
package demo;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;

public record OrderInput(

        @NotBlank
        @Pattern(regexp = "[A-Z0-9-]{3,40}")
        String sku,

        @NotNull
        @Min(1)
        @Max(100)
        Integer quantity
) {
}
```

DTO validate dữ liệu đầu vào; không có trường `id` do client chọn. `@NotNull` trên quantity giúp phân biệt thiếu field với số 0; `@Min(1)` ngăn request đặt 0 hoặc âm. `@Pattern` giúp demo giới hạn SKU, nhưng **không thay authorization**.

### 9.3. OrderView.java

```java
package demo;

public record OrderView(
        long id,
        String sku,
        int quantity
) {
}
```

Response model tách khỏi request DTO để tránh phản chiếu tùy ý dữ liệu không nên public, một thói quen tốt khi sau này thêm entity/DB.

### 9.4. OrderStore.java

```java
package demo;

import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

@Service
public class OrderStore {

    private final AtomicLong nextId = new AtomicLong();

    private final ConcurrentMap<Long, OrderView> orders =
            new ConcurrentHashMap<>();

    public OrderView create(OrderInput input) {
        long id = nextId.incrementAndGet();

        OrderView view = new OrderView(
                id,
                input.sku(),
                input.quantity()
        );

        orders.put(id, view);
        return view;
    }

    public OrderView find(long id) {
        OrderView found = orders.get(id);

        if (found == null) {
            throw new ResponseStatusException(
                    HttpStatus.NOT_FOUND, "Order not found");
        }

        return found;
    }
}
```

`AtomicLong` và `ConcurrentHashMap` giúp demo xử lý multi-thread cơ bản trong một JVM, không đem lại persistence, uniqueness trên nhiều Pods hoặc idempotency. Production dùng database/repository transactional và authorization; không dùng ID khó đoán hay CORS như cơ chế phân quyền.

## 10. OrdersController.java: tạo link và redirect public

File `src/main/java/demo/OrdersController.java`:

```java
package demo;

import java.net.URI;

import jakarta.validation.Valid;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.support.ServletUriComponentsBuilder;

@RestController
@RequestMapping("/api/v1/orders")
public class OrdersController {

    private final OrderStore store;

    public OrdersController(OrderStore store) {
        this.store = store;
    }

    @PostMapping(
        consumes = MediaType.APPLICATION_JSON_VALUE
    )
    public ResponseEntity<OrderView> create(
            @Valid @RequestBody OrderInput input) {

        OrderView created = store.create(input);

        URI resourceUri = ServletUriComponentsBuilder
                .fromCurrentRequestUri()
                .path("/{id}")
                .buildAndExpand(created.id())
                .toUri();

        return ResponseEntity.created(resourceUri)
                .body(created);
    }

    @GetMapping("/{id}")
    public OrderView find(@PathVariable long id) {
        return store.find(id);
    }

    @GetMapping("/{id}/canonical")
    public ResponseEntity<Void> canonical(
            @PathVariable long id) {

        store.find(id);

        URI resourceUri = ServletUriComponentsBuilder
                .fromCurrentContextPath()
                .path("/api/v1/orders/{id}")
                .buildAndExpand(id)
                .toUri();

        return ResponseEntity
                .status(HttpStatus.FOUND)
                .location(resourceUri)
                .build();
    }
}
```

**Tại sao tạo URI bằng builder thay vì hardcode?**

- `fromCurrentRequestUri()` lấy request URI cho POST resource collection, rồi thêm segment ID.
- `fromCurrentContextPath()` lấy scheme/host/port/public context path đã được xử lý, rồi thêm canonical path.
- Khi NGINX strip `/shop` và gửi `X-Forwarded-Prefix=/shop`, Spring Framework forwarding filter có thể khôi phục public prefix.
- Khi proxy terminate HTTPS và gửi `X-Forwarded-Proto=https`, absolute URL không trỏ nhầm HTTP.
- Không dùng nguyên chuỗi `Host`/`X-Forwarded-Host` để nối vào URL thủ công hoặc redirect theo query parameter tùy ý.

**Bài lab không cho phép client chỉ định `returnUrl`/`redirect`**, nên không có open redirect do tùy ý chuyển hướng đến domain người dùng nhập. Với OAuth2/login, mọi redirect target phải được validate theo allowlist/path policy và test dưới attacker-controlled Host headers.

### 10.1. Tại sao redirect dùng 302?

`GET /api/v1/orders/{id}/canonical` là route minh họa trả `302 Found` cùng header `Location` đến resource chính. Một số API dùng 308 cho permanent redirect giữ nguyên method, 303 sau POST/Redirect/Get, hoặc 307 cho temporary redirect giữ method. Không chọn 301/302/303/307/308 ngẫu nhiên khi request có body và side effects, vì browser/client có thể đổi method hoặc cache redirect khác nhau.

### 10.2. URI đúng không bằng hành vi proxy an toàn

Nếu app đọc spoofed forwarded headers trực tiếp từ Internet, URI builder có thể tạo link attacker host dù dùng API framework “đúng”. **Framework chỉ chuyển metadata**, proxy mới thiết lập trust boundary. Integration test giả headers chỉ kiểm chức năng xây URL; security test phải xác minh client bên ngoài **không thể ảnh hưởng** các forwarded values sau NGINX.

## 11. CorsPolicy.java: chỉ cho phép đúng origin, method, header và path

File `src/main/java/demo/CorsPolicy.java`:

```java
package demo;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.CorsRegistration;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class CorsPolicy implements WebMvcConfigurer {

    private final String allowedOrigin;

    public CorsPolicy(
            @Value("${app.cors.allowed-origin}")
            String allowedOrigin) {

        this.allowedOrigin = allowedOrigin;
    }

    @Override
    public void addCorsMappings(CorsRegistry registry) {

        // Collection route.
        configure(registry.addMapping("/api/v1/orders"));

        // Child routes, ví dụ /api/v1/orders/7.
        configure(registry.addMapping("/api/v1/orders/**"));
    }

    private void configure(CorsRegistration mapping) {
        mapping.allowedOrigins(allowedOrigin)
                .allowedMethods("GET", "POST")
                .allowedHeaders(
                        "Content-Type", "X-Request-ID")
                .exposedHeaders(
                        "Location", "X-Request-ID")
                .allowCredentials(false)
                .maxAge(600);
    }
}
```

**Giải thích từng quyết định:**

- `allowedOrigins("https://app.example.test")`: một exact origin HTTPS, không có path, không có wildcard. Đổi bằng property theo môi trường **sau khi review origin allowlist**.
- Hai `addMapping`: scope ở **internal MVC paths**, vì NGINX đã rewrite bỏ `/shop`. Không cấu hình `/shop/api/**` trong Spring khi app thực nhận `/api/**`.
- `allowedMethods("GET","POST")`: GET đọc, POST tạo. **OPTIONS không bắt buộc liệt kê trong allowed methods** khi browser preflight yêu cầu actual POST/GET; Spring CORS processor xử lý OPTIONS preflight dựa trên `Access-Control-Request-Method`.
- `allowedHeaders("Content-Type","X-Request-ID")`: chỉ cho phép preflight xin các request headers được nêu. Browser có thể thêm các safelisted headers không cần liệt kê; nếu frontend thực cần `Authorization`, phải review và thêm nó có chủ đích, không set `*` theo phản xạ.
- `exposedHeaders("Location","X-Request-ID")`: trình duyệt mới cho JavaScript đọc hai response headers này qua `fetch().headers.get(...)`. Nó **không** quyết định headers nào client được gửi.
- `allowCredentials(false)`: lab dùng anonymous API, không cố gửi cookies cross-origin. Đây là chính sách tốt hơn khi không có nhu cầu xác thực bằng cookie.
- `maxAge(600)`: browser có thể cache kết quả **preflight** tối đa 600 giây theo `Access-Control-Max-Age` và browser policy, không phải cache JSON response API.
- Không có `@CrossOrigin` bổ sung trên controllers để tránh sự pha trộn nhiều chính sách gây mở rộng scope ngoài ý muốn.

### 11.1. Vì sao không dùng /**?

Phản ví dụ:

```java
registry.addMapping("/**")
        .allowedOrigins("*")
        .allowedMethods("*");
```

Nó có thể expose CORS cho health/admin endpoints và các API chưa review. Đúng là CORS **không phải authorization**, nhưng một frontend độc hại có thể đọc response của endpoints mà browser mang thông tin đăng nhập hợp lệ trong điều kiện CORS credentials/policy khác; scope càng rộng càng khó audit và dễ tạo lỗ hổng kết hợp.

Bài thực hành chỉ gắn CORS vào collection/child route của API orders. Actuator `/actuator/health` không nằm trong mapping này, và không mặc định cấp `Access-Control-Allow-Origin` cho frontend.

### 11.2. CORS global và @CrossOrigin có thể kết hợp

Spring MVC có thể kết hợp global `CorsRegistry` config với `@CrossOrigin` ở controller/handler. Phép kết hợp cho các danh sách như allowed origins/methods/headers có thể mang tính cộng dồn; một controller đặt `@CrossOrigin(origins="*")` có nguy cơ làm policy rộng hơn kỳ vọng. **Chọn một chủ thể quản lý CORS** hoặc review cách combine rõ ràng; đừng rải annotations qua hàng chục controllers rồi tuyên bố global allowlist luôn là giới hạn cuối.

### 11.3. Nếu có Spring Security

Khi thêm `spring-boot-starter-security`, CORS cần được xử lý **trước Spring Security authentication**, vì preflight thường không mang cookie `JSESSIONID`. Spring Security hỗ trợ `http.cors(withDefaults())` và có thể dùng MVC CORS config khi Spring MVC ở classpath và không có `CorsConfigurationSource` riêng.

Snippet tích hợp **cho project đã cài Spring Security và cấu hình authentication đầy đủ**:

```java
@Bean
SecurityFilterChain security(HttpSecurity http)
        throws Exception {

    http.cors(Customizer.withDefaults())
        .authorizeHttpRequests(auth -> auth
            .requestMatchers(
                "/actuator/health/**").permitAll()
            .anyRequest().authenticated());

    return http.build();
}
```

Đây là **snippet**, cần imports `@Bean`, `SecurityFilterChain`, `HttpSecurity`, `Customizer` và cấu hình auth phù hợp; **không thuộc runnable baseline** chưa cài Security. Không vô điều kiện `csrf.disable()` cho session/cookie authentication. Nếu có nhiều security chains hoặc nhiều `CorsConfigurationSource` beans, chỉ định policy đúng từng chain, tránh framework không biết dùng source nào.

### 11.4. CORS không thay CSRF

CORS giới hạn **đọc response** từ một origin khác trong browser. CSRF là tấn công khiến browser mang credentials của người dùng gửi request không mong muốn. Một cross-origin HTML form có thể gửi requests theo những điều kiện nhất định mà không cần đọc response; server phải có CSRF defenses cho thao tác thay đổi trạng thái khi dùng cookie auth. Spring Security `CookieCsrfTokenRepository`/CSRF tokens, SameSite và Origin/Referer validation có thể được phối hợp tùy threat model.

### 11.5. Authorization header khác cookie

Nếu frontend dùng access token Bearer trong `Authorization`, browser POST với header này thường tạo preflight. Để hỗ trợ token client, CORS policy cần:

```java
mapping.allowedHeaders(
        "Content-Type", "Authorization", "X-Request-ID");
```

Đây là **thay đổi có chủ đích** cho những ứng dụng đã thực sự dùng Authorization, không mở cho mọi endpoint. `Access-Control-Allow-Headers: Authorization` không thay việc server xác thực JWT/token. Browser JavaScript nếu nắm bearer token cũng cần XSS defenses và secure token handling.

## 12. CorrelationFilter.java: response header để kiểm CORS expose

File `src/main/java/demo/CorrelationFilter.java`:

```java
package demo;

import java.io.IOException;
import java.util.UUID;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
public class CorrelationFilter extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {

        response.setHeader(
                "X-Request-ID",
                UUID.randomUUID().toString());

        chain.doFilter(request, response);
    }
}
```

Filter chỉ đặt một header, không đọc body, không log `Authorization`/`Cookie`, không suy đoán client IP từ raw `X-Forwarded-For`. Vì frontend cần đọc `X-Request-ID` trong JavaScript, CorsPolicy `exposedHeaders` liệt kê header này.

**Lưu ý:** nếu một lỗi được NGINX/container sinh trước khi tới app, nó có thể không đi qua filter; do đó không bảo đảm mọi response trên Internet đều có cùng request ID. Với hệ thống multi-hop, nên tạo/normalize correlation ID tại gateway và propagate qua trusted channels.

## 13. Chạy ứng dụng trực tiếp

Từ thư mục chứa Gradle Wrapper:

```bash
./gradlew clean test bootRun
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat clean test bootRun
```

Đóng gói executable JAR và chạy riêng:

```bash
./gradlew bootJar
java -jar build/libs/proxy-cors-lab-0.0.1-SNAPSHOT.jar
```

**Lưu ý:** `java -jar` chạy từ local loopback, chưa có NGINX. Nếu truy cập trực tiếp `127.0.0.1:8080` mà không gửi forwarded headers thì app chỉ biết địa chỉ nội bộ; public URI chỉ xuất hiện khi proxy đã thiết lập headers phù hợp. Các lệnh nội bộ dưới đây là **test chức năng**, không chứng minh trust boundary của NGINX đã an toàn.

### 13.1. POST nội bộ không forwarded headers

```bash
curl -i -X POST \
  http://127.0.0.1:8080/api/v1/orders \
  -H 'Content-Type: application/json' \
  -d '{"sku":"BOOK-001","quantity":2}'
```

Kết quả đầu tiên trên một JVM mới có thể là:

```http
HTTP/1.1 201
Location: http://127.0.0.1:8080/api/v1/orders/1
Content-Type: application/json

{"id":1,"sku":"BOOK-001","quantity":2}
```

Dạng status/header có thể kèm các headers khác, ID tăng theo state. Đây là **internal URL** — đúng khi không có proxy metadata, nhưng không phải `Location` public mong muốn cho browser.

### 13.2. Giả lập proxy metadata nội bộ bằng curl

```bash
curl -i -X POST \
  http://127.0.0.1:8080/api/v1/orders \
  -H 'Content-Type: application/json' \
  -H 'X-Forwarded-Proto: https' \
  -H 'X-Forwarded-Host: api.example.test' \
  -H 'X-Forwarded-Port: 443' \
  -H 'X-Forwarded-Prefix: /shop' \
  -d '{"sku":"BOOK-002","quantity":3}'
```

Với `server.forward-headers-strategy=framework`, `Location` mong đợi:

```text
https://api.example.test/shop/api/v1/orders/2
```

Số ID thay đổi. Nếu Location thiếu `/shop`, kiểm tra filter strategy, upstream rewrite, `X-Forwarded-Prefix`, và có hai tầng cùng rewrite/append hay không. Nếu Location bắt đầu `http://127.0.0.1`, app có thể chưa đọc forwarded metadata hoặc proxy không gửi headers.

**Cảnh báo bảo mật:** việc lệnh curl nội bộ có thể điều khiển `X-Forwarded-Host` cho thấy vì sao **backend không được public trực tiếp** khi bật FRAMEWORK. Test này là functional simulation, không phải chứng nhận hệ thống chống spoofing.

### 13.3. GET và 302 redirect

Sau POST, dùng ID thực:

```bash
curl -i \
  http://127.0.0.1:8080/api/v1/orders/2

curl -i \
  http://127.0.0.1:8080/api/v1/orders/2/canonical \
  -H 'X-Forwarded-Proto: https' \
  -H 'X-Forwarded-Host: api.example.test' \
  -H 'X-Forwarded-Port: 443' \
  -H 'X-Forwarded-Prefix: /shop'
```

Kỳ vọng 302 `Location: https://api.example.test/shop/api/v1/orders/2`. Đừng dùng `curl -L` nếu muốn thấy redirect header gốc; `-L` sẽ cố follow public host (có thể không tồn tại DNS/cert trong local lab).

## 14. CORS preflight: trình duyệt hỏi trước khi POST JSON

Vì frontend `https://app.example.test` và API `https://api.example.test` khác origin, request POST JSON sẽ cần một **preflight** theo các điều kiện Fetch/CORS thông thường, do Content-Type `application/json` không nằm trong các safelisted content types của simple requests.

Trước POST, browser gửi tới public URL:

```http
OPTIONS /shop/api/v1/orders HTTP/1.1
Host: api.example.test
Origin: https://app.example.test
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type
```

NGINX chuyển thành upstream:

```http
OPTIONS /api/v1/orders HTTP/1.1
Origin: https://app.example.test
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type
X-Forwarded-Prefix: /shop
```

Spring MVC nhận preflight và đánh giá CorsPolicy tương ứng. Một response hợp lệ thường có:

```http
HTTP/1.1 200
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Methods: GET, POST
Access-Control-Allow-Headers: content-type
Access-Control-Max-Age: 600
Vary: Origin, Access-Control-Request-Method, Access-Control-Request-Headers
```

**Không hardcode rằng mọi implementation đều trả HTTP 200 đúng những header casing/ordering này.** Spring MVC và proxy có thể trả 200 cho preflight; điều quan trọng là HTTP success và các `Access-Control-Allow-*` khớp yêu cầu, không bị duplications/redirect.

### 14.1. Actual request vẫn phải có CORS headers

Sau preflight pass, browser mới gửi POST. Response POST `201` cần `Access-Control-Allow-Origin` tương ứng để JavaScript đọc body và headers được expose. Preflight pass **không** có nghĩa actual response mặc nhiên đọc được nếu proxy/app quên CORS headers trên đường lỗi/redirect.

### 14.2. Browser tự xử lý preflight

JavaScript không nên tự gửi một OPTIONS giả rồi tưởng browser đã “được cấp quyền”. Browser/Fetch quyết định khi nào cần preflight và cache nó theo policy. `fetch()` thực tế:

```javascript
const api = "https://api.example.test/shop/api/v1/orders";

const response = await fetch(api, {
  method: "POST",
  mode: "cors",
  headers: {
    "Content-Type": "application/json"
  },
  body: JSON.stringify({
    sku: "BOOK-001",
    quantity: 2
  })
});

if (!response.ok) {
  throw new Error("HTTP " + response.status);
}

const order = await response.json();
const resourceLocation = response.headers.get("Location");
const requestId = response.headers.get("X-Request-ID");

console.log(order, resourceLocation, requestId);
```

Đây là **frontend snippet**, chạy từ trang thực sự có origin `https://app.example.test`, không có browser session/token trong lab. `mode:"cors"` không tự cấp permission; server vẫn phải quyết định origin được phép. Vì CorsPolicy expose `Location` và `X-Request-ID`, JS có thể đọc hai headers này nếu actual CORS response hợp lệ.

### 14.3. Tại sao fetch trực tiếp qua Node.js/curl không kiểm CORS?

Node HTTP client hoặc curl không triển khai browser same-origin policy theo cùng cách. Một response thiếu `Access-Control-Allow-Origin` vẫn có thể được Node đọc. **CORS chỉ là một browser enforcement mechanism**, không thể thay firewall/authentication/authorization.

## 15. CORS response headers và mục đích chính xác

| Header | Giai đoạn | Ý nghĩa |
| --- | --- | --- |
| `Origin` | Request | Origin của document/script gửi request |
| `Access-Control-Request-Method` | Preflight request | Browser hỏi có được gửi actual method không |
| `Access-Control-Request-Headers` | Preflight request | Browser hỏi có được gửi non-safelisted request headers không |
| `Access-Control-Allow-Origin` | Preflight/actual response | Server cho phép origin nào đọc response trong browser |
| `Access-Control-Allow-Methods` | Preflight response | Actual methods được phép |
| `Access-Control-Allow-Headers` | Preflight response | Request headers được phép |
| `Access-Control-Allow-Credentials` | Response | Cho phép credentialed cross-origin response nếu true, cần exact origin |
| `Access-Control-Expose-Headers` | Actual response | Response headers mà JS được đọc |
| `Access-Control-Max-Age` | Preflight response | Thời gian browser có thể cache preflight result |
| `Vary` | Response/cache | Phân biệt response theo Origin và CORS request headers/method khi cần |

### 15.1. AllowedHeaders không giống ExposedHeaders

Frontend gửi request header `Content-Type` thì preflight xin `Access-Control-Allow-Headers`. Backend trả response `Location` thì JS đọc được header này nhờ `Access-Control-Expose-Headers`. Không khai `Location` trong `allowedHeaders` để cho JS đọc response — đó là hai hướng dữ liệu khác nhau.

### 15.2. Vary và CDN

Nếu response khác nhau theo `Origin`, cache dùng chung phải phân biệt các biến thể, thường là `Vary: Origin`. Preflight còn có thể vary theo `Access-Control-Request-Method` và `Access-Control-Request-Headers`. Nếu CDN cache response cho một origin rồi phát lại cho origin khác mà thiếu Vary đúng, browser có thể từ chối hoặc policy bị cấu hình sai. Không xóa `Vary` để “tối ưu cache” nếu chưa thiết kế cache key.

### 15.3. Max-Age không phải TTL dữ liệu đơn hàng

`maxAge(600)` cho preflight cache, không nói rằng đơn hàng được cache 600 giây. HTTP response cache còn phụ thuộc `Cache-Control`/`ETag`/`Last-Modified` và proxy/CDN policy. API có dữ liệu riêng tư không được công khai cache chỉ vì CORS pass.

### 15.4. Origin null

Một số contexts như `file://`, sandboxed iframe hoặc privacy modes có thể tạo `Origin: null`. Không thêm `"null"` vào allowlist chung để “sửa CORS” nếu không có threat model đặc biệt; nhiều nguồn không đáng tin có thể mang null origin.

## 16. Trường hợp origin bị từ chối

Một request preflight:

```bash
curl -i -X OPTIONS \
  http://127.0.0.1:8080/api/v1/orders \
  -H 'Origin: https://evil.example.test' \
  -H 'Access-Control-Request-Method: POST' \
  -H 'Access-Control-Request-Headers: content-type'
```

Với CorsPolicy và Spring MVC `DefaultCorsProcessor`, request cross-origin không nằm trong allowlist thường nhận **HTTP 403 Invalid CORS request**, hoặc không có ACAO tùy pipeline/handler; browser từ chối trước actual POST.

Các origin sau **không** tương đương `https://app.example.test`:

- `https://app.example.test.evil.test` — subdomain-lookalike.
- `http://app.example.test` — khác scheme.
- `https://app.example.test:8443` — khác port.
- `https://other.example.test` — host khác.
- `null` — opaque origin, không nằm trong allowlist.
- `https://APP.example.test` — hostnames DNS case-insensitive về nguyên lý, nhưng đừng xây authorization policy dựa vào tự normalize chuỗi Origin không có kiểm soát; dùng framework origin matching và tests.

Browser không phải luôn phát preflight. Với **simple GET**, browser có thể gửi actual GET trực tiếp, rồi tự chặn JavaScript đọc response nếu không có ACAO. Vì vậy **thiếu một OPTIONS trong access logs không chứng minh frontend đang same-origin hoặc CORS đã tắt**.

### 16.1. CORS không ngăn side effects ở mọi trường hợp

Có những requests có thể được gửi bằng HTML form hoặc các đường browser khác dù JavaScript không đọc được response. Nếu endpoint thay đổi trạng thái và dùng cookie-based auth, phải có CSRF validation. Không đặt `allowedOrigins("*")` rồi nghĩ server đang “chặn hacker”: CORS là chính sách đọc theo browser, không phải hàng rào cho HTTP clients khác.

## 17. MockMvc tests cho forwarding và CORS

Bài thực hành dùng Spring Boot full context để có Spring MVC mappings, `ForwardedHeaderFilter` auto-configuration và CORS config. `MockMvc` không start TCP server thật, nhưng rất phù hợp kiểm tra Controller/HandlerMapping/CORS processor/response headers.

Tạo file `src/test/java/demo/ProxyCorsMvcTest.java`:

```java
package demo;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.assertj.core.api.Assertions.assertThat;
import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.startsWith;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.options;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ProxyCorsMvcTest {

    private static final String FRONTEND =
            "https://app.example.test";

    @Autowired
    MockMvc mvc;

    @Autowired
    ObjectMapper json;

    private String requestBody() {
        return """
            {"sku":"BOOK-001","quantity":2}
            """;
    }

    @Test
    void preflightAllowedForExactOriginAndPost()
            throws Exception {

        mvc.perform(options("/api/v1/orders")
                .header(HttpHeaders.ORIGIN, FRONTEND)
                .header(
                    HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD,
                    "POST")
                .header(
                    HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                    "content-type"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                    HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                    FRONTEND))
            .andExpect(header().string(
                    HttpHeaders.ACCESS_CONTROL_ALLOW_METHODS,
                    containsString("POST")))
            .andExpect(header().string(
                    HttpHeaders.ACCESS_CONTROL_MAX_AGE,
                    "600"));
    }

    @Test
    void preflightRejectsUnknownOrigin() throws Exception {
        mvc.perform(options("/api/v1/orders")
                .header(
                    HttpHeaders.ORIGIN,
                    "https://evil.example.test")
                .header(
                    HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD,
                    "POST"))
            .andExpect(status().isForbidden())
            .andExpect(header().doesNotExist(
                    HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN));
    }

    @Test
    void schemeAndPortArePartOfOrigin() throws Exception {
        mvc.perform(options("/api/v1/orders")
                .header(
                    HttpHeaders.ORIGIN,
                    "http://app.example.test")
                .header(
                    HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD,
                    "POST"))
            .andExpect(status().isForbidden());

        mvc.perform(options("/api/v1/orders")
                .header(
                    HttpHeaders.ORIGIN,
                    "https://app.example.test:8443")
                .header(
                    HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD,
                    "POST"))
            .andExpect(status().isForbidden());
    }

    @Test
    void actualPostExposesLocationOnlyToAllowedOrigin()
            throws Exception {

        mvc.perform(post("/api/v1/orders")
                .header(HttpHeaders.ORIGIN, FRONTEND)
                .contentType(MediaType.APPLICATION_JSON)
                .content(requestBody()))
            .andExpect(status().isCreated())
            .andExpect(header().string(
                    HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                    FRONTEND))
            .andExpect(header().string(
                    HttpHeaders.ACCESS_CONTROL_EXPOSE_HEADERS,
                    containsString("Location")))
            .andExpect(header().exists(
                    "X-Request-ID"));
    }

    @Test
    void forwardedPublicLocationContainsHttpsAndPrefix()
            throws Exception {

        MvcResult created = mvc.perform(
                post("/api/v1/orders")
                    .header(
                        "X-Forwarded-Proto", "https")
                    .header(
                        "X-Forwarded-Host",
                        "api.example.test")
                    .header(
                        "X-Forwarded-Port", "443")
                    .header(
                        "X-Forwarded-Prefix", "/shop")
                    .contentType(
                        MediaType.APPLICATION_JSON)
                    .content(requestBody()))
            .andExpect(status().isCreated())
            .andExpect(header().string(
                    HttpHeaders.LOCATION,
                    startsWith(
                        "https://api.example.test/shop/api/v1/orders/")))
            .andReturn();

        JsonNode response = json.readTree(
                created.getResponse()
                       .getContentAsString());

        long id = response.get("id").asLong();

        mvc.perform(get(
                    "/api/v1/orders/{id}/canonical", id)
                .header("X-Forwarded-Proto", "https")
                .header(
                    "X-Forwarded-Host",
                    "api.example.test")
                .header("X-Forwarded-Port", "443")
                .header(
                    "X-Forwarded-Prefix", "/shop"))
            .andExpect(status().isFound())
            .andExpect(header().string(
                    HttpHeaders.LOCATION,
                    "https://api.example.test/shop/api/v1/orders/"
                        + id));
    }

    @Test
    void invalidInputFailsBeanValidation()
            throws Exception {

        mvc.perform(post("/api/v1/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"sku":" ","quantity":0}
                    """))
            .andExpect(status().isBadRequest());
    }

    @Test
    void healthIsNotGivenOrdersCorsPolicy()
            throws Exception {

        mvc.perform(options("/actuator/health")
                .header(HttpHeaders.ORIGIN, FRONTEND)
                .header(
                    HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD,
                    "GET"))
            .andExpect(header().doesNotExist(
                    HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN));
    }
}
```

**Lưu ý kỹ thuật:** các tests không phụ thuộc ID cố định vì `OrderStore` giữ in-memory state giữa test methods. Để kiểm tra forwarded redirect, test parse ID từ POST response. `JsonNode`/`ObjectMapper` có trong `spring-boot-starter-web`; Hamcrest, MockMvc/JUnit/AssertJ thuộc starter-test.

### 17.1. MockMvc kiểm chứng và không kiểm chứng điều gì?

**Có thể:** handler mapping, CORS allow/deny logic, preflight response headers, DTO validation, Spring Boot forwarding filter nếu nó được đăng ký trong test context, `Location` và redirect sinh theo forwarded metadata.

**Không thể:** NGINX có thực strip malicious forwarded headers hay không, proxy_pass rewrite có đúng không, HTTP/TLS 443 certificate, DNS, keep-alive, browser cookie policy, CSP, CDN/ingress behavior và tính an toàn của network ACL.

Một test MockMvc pass với header `X-Forwarded-Host: api.example.test` chỉ chứng minh framework **tin** header và dùng nó đúng như kỳ vọng. Nó không chứng minh hacker không thể gửi giá trị khác đến backend qua một đường bị lộ.

### 17.2. Tránh assertions cứng với không gian dynamic

Khi test `Location`, dùng prefix và ID thực đã trả, không mặc định ID 1 nếu các tests chạy chung context hoặc song song. Với `Vary` và `Access-Control-Allow-Headers`, đừng bắt buộc thứ tự header values/casing nếu contract chỉ cần sự hiện diện của các phần tử.

### 17.3. Nếu test fails vì forwarded filter không xuất hiện

Kiểm tra `server.forward-headers-strategy=framework`, Boot 3.3 version, `@AutoConfigureMockMvc` có add servlet filters, và có custom test filters hay bean nào tắt forwarding. Không tự thêm `ForwardedHeaderFilter` thứ hai trong production chỉ để “làm test xanh”; trước hết xác minh auto-config và test setup.

## 18. RANDOM_PORT: thử HTTP container thật

File `src/test/java/demo/ProxyCorsHttpTest.java`:

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class ProxyCorsHttpTest {

    @LocalServerPort
    int port;

    @Autowired
    TestRestTemplate client;

    private String url() {
        return "http://127.0.0.1:"
                + port + "/api/v1/orders";
    }

    @Test
    void realHttpResponseUsesForwardedPublicUri() {

        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_JSON);
        headers.add(
                "X-Forwarded-Proto", "https");
        headers.add(
                "X-Forwarded-Host", "api.example.test");
        headers.add(
                "X-Forwarded-Port", "443");
        headers.add(
                "X-Forwarded-Prefix", "/shop");

        HttpEntity<String> request = new HttpEntity<>(
                """
                {"sku":"BOOK-123","quantity":1}
                """,
                headers
        );

        ResponseEntity<String> result = client.exchange(
                url(),
                HttpMethod.POST,
                request,
                String.class
        );

        assertThat(result.getStatusCode())
                .isEqualTo(HttpStatus.CREATED);

        assertThat(result.getHeaders().getLocation())
                .isNotNull()
                .satisfies(location ->
                    assertThat(location.toString())
                        .startsWith(
                          "https://api.example.test/shop/api/v1/orders/"));
    }

    @Test
    void preflightWorksOverTcp() {

        HttpHeaders headers = new HttpHeaders();
        headers.add(
                HttpHeaders.ORIGIN,
                "https://app.example.test");
        headers.add(
                HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD,
                "POST");
        headers.add(
                HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                "content-type");

        ResponseEntity<String> result = client.exchange(
                url(),
                HttpMethod.OPTIONS,
                new HttpEntity<>(headers),
                String.class
        );

        assertThat(result.getStatusCode())
                .isEqualTo(HttpStatus.OK);

        assertThat(result.getHeaders().getFirst(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN))
                .isEqualTo("https://app.example.test");
    }
}
```

`RANDOM_PORT` khởi động embedded Tomcat thật với application properties. `TestRestTemplate` gửi request qua TCP loopback. Nó xác nhận Boot forwarding stack và MVC CORS hoạt động trong server HTTP, nhưng vẫn không gọi NGINX thực, không chứng minh header sanitization tại edge và không kiểm tra browser credential restrictions.

### 18.1. Tại sao test gửi header “giả” vào backend lại có giá trị?

Đây là **functional unit/integration assertion** của khả năng tạo đúng public URL *khi receiving trusted proxy metadata*. Nó xác nhận code xử lý prefix/scheme/port theo cấu hình. Cùng phép thử đó cũng bộc lộ rủi ro: nếu backend public, attacker có thể thay host. Cần **thêm kiểm thử E2E qua NGINX** để chứng minh external headers không được tin.

### 18.2. Test request path thật qua NGINX khác RANDOM_PORT

RANDOM_PORT test gọi `/api/v1/orders` và tự đặt `X-Forwarded-Prefix=/shop`. Qua NGINX thật, client gọi `/shop/api/v1/orders` và **không** gửi forwarded headers. NGINX strip prefix và tự tạo metadata. Hai tests có phạm vi khác nhau, đều cần khi production phụ thuộc routing.

## 19. Kiểm thử NGINX end-to-end

Để thử đúng đường bên ngoài, cần DNS/hosts mapping cho `api.example.test` về NGINX server và một certificate được client trust. Trên local host có thể dùng local CA/mkcert hoặc internal PKI theo chuẩn tổ chức.

Lệnh `curl --resolve` ánh xạ hostname cho **một lần curl**; vẫn kiểm tra hostname TLS/certificate theo cách bình thường:

```bash
curl -i \
  --resolve api.example.test:443:127.0.0.1 \
  https://api.example.test/shop/api/v1/orders
```

Nếu certificate không hợp lệ, curl sẽ báo lỗi TLS. Không dùng `--insecure`/`-k` làm mặc định cho bài test security. Hãy cấp CA/cert phù hợp hoặc dùng `--cacert` khi có internal CA.

### 19.1. Tạo đơn hàng qua HTTPS proxy

```bash
curl -i \
  --resolve api.example.test:443:127.0.0.1 \
  -X POST \
  'https://api.example.test/shop/api/v1/orders' \
  -H 'Content-Type: application/json' \
  -H 'Origin: https://app.example.test' \
  -d '{"sku":"BOOK-234","quantity":4}'
```

Kiểm tra:

- HTTP **201**.
- Body có `id` và dữ liệu đã gửi.
- `Location` bắt đầu `https://api.example.test/shop/api/v1/orders/`.
- `Access-Control-Allow-Origin: https://app.example.test`.
- `Access-Control-Expose-Headers` cho phép đọc `Location`, `X-Request-ID`.
- Không có internal `127.0.0.1:8080` trong absolute headers.
- TLS verification thành công.

### 19.2. Preflight qua HTTPS proxy

```bash
curl -i \
  --resolve api.example.test:443:127.0.0.1 \
  -X OPTIONS \
  'https://api.example.test/shop/api/v1/orders' \
  -H 'Origin: https://app.example.test' \
  -H 'Access-Control-Request-Method: POST' \
  -H 'Access-Control-Request-Headers: content-type'
```

Kỳ vọng status success và `Access-Control-Allow-Origin` đúng. Nếu nhận 301/308/302 từ public URL do thiếu trailing slash hoặc HTTP→HTTPS, browser preflight có thể bị hành vi khác nhau tùy browser; tốt nhất frontend gọi **ngay canonical HTTPS URL**. Kiểm tra URL, path và origin chính xác trong DevTools.

### 19.3. Negative test: origin không được phép

```bash
curl -i \
  --resolve api.example.test:443:127.0.0.1 \
  -X OPTIONS \
  'https://api.example.test/shop/api/v1/orders' \
  -H 'Origin: https://evil.example.test' \
  -H 'Access-Control-Request-Method: POST'
```

Spring MVC preflight thường từ chối bằng 403; tối thiểu không được phát ACAO cho origin bị cấm. Việc non-browser curl vẫn gửi được request khác không cho thấy CORS “thất bại” — mục tiêu là browser JS bị chặn đọc response từ origin không được cho phép.

### 19.4. Negative test: spoofed X-Forwarded-Host từ Internet

Đây là phép thử **an toàn trong staging/lab thuộc quyền quản lý**:

```bash
curl -i \
  --resolve api.example.test:443:127.0.0.1 \
  -X POST \
  'https://api.example.test/shop/api/v1/orders' \
  -H 'Content-Type: application/json' \
  -H 'X-Forwarded-Host: attacker.example.test' \
  -H 'X-Forwarded-Proto: http' \
  -H 'Forwarded: for=192.0.2.1;proto=http;host=attacker.example.test' \
  -d '{"sku":"BOOK-345","quantity":1}'
```

**Kỳ vọng an toàn:** NGINX edge loại bỏ/overwrite các giá trị từ client. `Location` phải vẫn trỏ `https://api.example.test/shop/...`, không được chứa attacker host hay HTTP scheme. Nếu nó trỏ attacker host, **trust boundary đã thất bại** dù Spring Boot tests của controller đều xanh.

Không dùng kiểu thử này trên dịch vụ bên thứ ba; chỉ test hệ thống của bạn với quyền và phạm vi rõ.

### 19.5. Negative test: Host ngoài allowlist

Production edge cần reject host lạ hoặc route về default server không proxy app. Đánh giá HTTP Host/SNI/certificate logic bằng kịch bản được tổ chức cho phép; không dùng một `server_name` duy nhất và giả định NGINX tự chặn mọi Host lạ. Bài NGINX sample cần default-server policy bổ sung trước production.

## 20. CORS kết hợp cookie và session: khi nào dùng credentials?

Bài baseline đặt:

```java
.allowCredentials(false)
```

vì API lab không dựa vào cookie. Nếu bạn sử dụng **session cookie authentication**, browser frontend khác origin thường cần:

```javascript
const response = await fetch(
  "https://api.example.test/shop/api/v1/orders",
  {
    method: "POST",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      "X-CSRF-TOKEN": "<token do server cấp>"
    },
    body: JSON.stringify({
      sku: "BOOK-001",
      quantity: 2
    })
  }
);
```

Đây là **snippet cho một hệ thống đã có CSRF token issuing và xác thực**, không phải code chạy được với baseline chưa cài Spring Security. Browser không cho JavaScript tùy ý đặt `Cookie` header thủ công như một request header bình thường; dùng cookie jar và `credentials:"include"`.

Backend phải cho phép credentials chỉ với origin cụ thể:

```java
mapping.allowedOrigins("https://app.example.test")
        .allowCredentials(true)
        .allowedHeaders(
            "Content-Type", "X-CSRF-TOKEN");
```

Đây là **thay đổi riêng** cho deployment cần credentials, thay cho policy baseline, không thêm chồng cùng route. Khi credentials true:

- **Không** dùng `allowedOrigins("*")`. Spring Framework validation không chấp nhận tổ hợp wildcard `*` và allowCredentials true.
- `Access-Control-Allow-Origin` phải là một origin cụ thể phù hợp, không dùng wildcard `*`.
- `Access-Control-Allow-Credentials: true` phải có khi browser thực hiện credentialed cross-origin request.
- Cookie vẫn bị `Secure`, `SameSite`, `Path`, `Domain` và browser privacy policy chi phối.
- Server phải xác thực session/token và CSRF cho state-changing operations; **CORS không thay chúng**.
- Với `Authorization` Bearer thay session cookie, phải cấu hình allowedHeaders phù hợp, không mặc định coi Bearer token là cookie.

### 20.1. Same-origin vs same-site vẫn quan trọng

Frontend `https://app.example.test` gọi API `https://api.example.test` là **cross-origin nhưng có thể same-site**. Browser có thể gửi một cookie SameSite=Lax trong cùng schemeful site nếu `credentials:"include"` và cookie scope cho phép. Tuy nhiên trình duyệt vẫn cần CORS để JS đọc response vì origin khác nhau.

Nếu frontend chạy trên domain khác registrable site, cookie trong cross-site fetch thường cần `SameSite=None; Secure`; nhiều browsers còn hạn chế third-party cookies. Đừng sửa bằng cách tắt CORS, bỏ Secure hoặc đặt wildcard origin. Test browser thật trên domain/topology thực.

### 20.2. Cookie Path và public prefix

Trong bài proxy public API prefix `/shop` nhưng backend context root `/`. Nếu bạn dùng cookie phục vụ API public, có thể cần giới hạn path:

```http
Set-Cookie: session_hint=opaque; Path=/shop; Secure; HttpOnly; SameSite=Lax
```

Trình duyệt dùng public URL path để so khớp cookie. `Path=/shop` gửi cookie tới `/shop/...`, không tới `/api/v1/...` trên root public không phù hợp. Nếu dùng Servlet `JSESSIONID`, cần xem cấu hình `server.servlet.session.cookie.path`/Spring Session serializer và kiểm tra cookie thật qua proxy; **đừng giả định X-Forwarded-Prefix tự sửa mọi cookie Path/Domain**.

### 20.3. Domain: chọn host-only khi có thể

Không đặt `Domain=.example.test` chỉ để “cả frontend và API cùng thấy cookie” khi session chỉ cần gửi tới API. Host-only cookie cho `api.example.test` thường hạn chế bề mặt. `Domain` mở rộng phạm vi subdomains; một subdomain bị chiếm quyền có thể tạo thêm rủi ro. Cookie Path/Domain không thay server-side session authorization.

### 20.4. Secure và HTTPS termination

Nếu app ở HTTP upstream, nó có thể nhìn request `isSecure=false` khi chưa xử lý forwarded headers, dẫn đến tạo cookie không Secure hoặc redirect về HTTP. Với trusted forwarded strategy, downstream request metadata có thể phản ánh external HTTPS. Tuy nhiên production session cookie nên **cưỡng bức Secure** bằng cấu hình rõ thay vì trông chờ điều kiện auto từ header không tin cậy.

### 20.5. CSRF với cookies

Một attacker site có thể khiến browser gửi một số cross-site requests mang credentials trong những điều kiện nhất định mà không cần đọc response. CORS không chống CSRF. Với Spring Security cookie-based login, giữ CSRF protection, configure token transport hợp lý và kiểm thử requests thiếu/invalid token trả 403. Nếu dùng stateless Bearer tokens với threat model khác, CSRF policy có thể khác nhưng vẫn cần xác thực/authorization.

## 21. Khi nhiều lớp có CORS: ai sở hữu policy?

Có thể gặp:

```text
Browser -> CDN -> NGINX -> Spring Security -> Spring MVC
```

Các lớp CDN/NGINX/Security/MVC đều có thể thêm CORS headers nếu cấu hình. Nếu không có owner, lỗi thường là:

- Hai `Access-Control-Allow-Origin` headers hoặc một header chứa hai origins.
- NGINX trả wildcard nhưng Spring trả exact origin.
- Preflight bị Security filter chặn 401/403 trước MVC.
- Gateway trả CORS 200 cho route không tồn tại, actual POST lại 404 không ACAO.
- CDN cache preflight cho origin A rồi trả cho origin B.
- Spring MVC chỉ cấp ACAO cho controller success, proxy-generated 502 không có policy tương ứng.
- Có `@CrossOrigin` trên controller ngoài global allowlist, khiến scope nới rộng.

**Bài chọn MVC làm owner của CORS.** NGINX forward OPTIONS và không phát ACAO. Nếu Spring Security được thêm, cấu hình `http.cors(...)` để integration xử lý preflight đúng filter order, dùng một policy source. Nếu hệ thống cần edge-owned CORS, phải chuyển trách nhiệm hoàn toàn có chủ đích và test cho mọi success/error paths, không thêm headers ở cả hai nơi.

### 21.1. Vary và cache ở CDN

Nếu responses được cache, đảm bảo Vary hoặc cache key phân biệt Origin/Request-Method/Request-Headers khi phù hợp. Cache per user dữ liệu riêng tư cần policy chặt hơn CORS; không cache GET user-specific resources trong shared CDN chỉ dựa vào ACAO. Với credentials/cookies, xem `Cache-Control: private/no-store` theo dữ liệu.

### 21.2. CORS error trong browser không luôn là lỗi gốc

Browser có thể hiển thị “CORS blocked” vì upstream 502/504, TLS error, redirect loop hoặc proxy-generated HTML error không có ACAO. Trong DevTools Network, kiểm tra **status/URL/redirect chain/response headers** và server/NGINX logs. Đừng vội mở `Access-Control-Allow-Origin: *` chỉ để thông báo browser biến mất.

## 22. Bảng kiểm lỗi thực tế

| Triệu chứng | Nguyên nhân khả dĩ | Cách chẩn đoán/sửa |
| --- | --- | --- |
| `Location` bắt đầu `http://127.0.0.1:8080` | Spring chưa nhận/trust forwarded scheme/host | Kiểm `server.forward-headers-strategy` và proxy_set_header |
| `Location` đúng HTTPS nhưng thiếu `/shop` | Thiếu `X-Forwarded-Prefix` hoặc slash rewrite sai | Test proxy_pass và header prefix |
| `Location` thành `/shop/shop` | Cả proxy/context path đều thêm prefix | Chọn một mô hình rewrite/context rõ |
| Kết nối public 404, internal API 200 | NGINX không strip prefix đúng | So sánh proxy_pass có/không trailing slash |
| Redirect HTTP dù browser dùng HTTPS | `X-Forwarded-Proto` sai, Tomcat root redirect | Kiểm TLS edge, redirect-context-root và forwarded strategy |
| Kẻ tấn công điều khiển hostname trong Location | Forwarded headers không được sanitize | Strip/overwrite edge, cấm direct upstream |
| Host attacker được proxy vào app | Default vhost/SNI/Host validation thiếu | Thiết lập reject host lạ ở edge |
| `X-Forwarded-For` hiện IP giả | Edge append client header không kiểm soát | Overwrite ở trust boundary, cấu hình trusted chain |
| Browser CORS chặn POST JSON | OPTIONS bị 404/401/405/redirect hoặc thiếu ACAO | Test preflight đúng public HTTPS URL |
| Preflight 200 nhưng POST bị browser chặn | Actual response không ACAO, proxy error, redirect | Test both OPTIONS and actual POST |
| CORS `allowCredentials=true` với `*` | Wildcard origin bị cấm với credentials | Dùng exact allowedOrigins |
| `Origin=https://evil...` được phép | Wildcard/pattern quá rộng, @CrossOrigin combine | Thu hẹp exact origin and path |
| CORS cấp cho `/actuator/**` ngoài ý muốn | Mapping `/**` hoặc Security/NGINX policy rộng | Scope chỉ API cần thiết |
| Preflight xin Authorization bị từ chối | Chưa allowedHeader Authorization | Cho đúng header khi API dùng bearer |
| Browser không đọc `Location` dù POST 201 | Thiếu Access-Control-Expose-Headers | Expose Location có chủ đích |
| Cookie không được browser gửi | Secure/SameSite/Domain/Path/credentials mismatch | Test DevTools qua HTTPS thật |
| Session cookie Path là `/`, muốn `/shop` | Servlet/Spring Session cookie path chưa cấu hình | Cấu hình đúng cookie path và test |
| Login session POST 403 | CSRF hoặc auth, không hẳn CORS | Phân biệt preflight với actual request |
| User B đọc được order của A | Thiếu authorization, CORS không ngăn | Bổ sung owner/tenant checks |
| NGINX 502 | Backend down/wrong upstream/timeout | Kiểm error logs, port, firewall |
| NGINX 413 upload | client_max_body_size ở proxy | Điều chỉnh theo policy file limit |
| CORS cache sai theo origin | Thiếu Vary/cache key ở proxy/CDN | Kiểm caching contract |
| Backend chỉ bind loopback trong K8s | Proxy ở Pod khác không kết nối được | Bind Pod interface và dùng NetworkPolicy |
| MockMvc pass, public URL vẫn lỗi | MockMvc không đi qua NGINX/TLS | Thêm end-to-end proxy tests |
| API redirect qua domain lạ | Trusted headers/open redirect sai | Tách client redirect target khỏi Host |
| Health endpoint lộ internals | CORS/publishing Actuator quá rộng | Private management/security |
| NGINX pass OPTIONS nhưng Security 401 | CORS chưa chạy trước authentication | Spring Security cors integration |

## 23. Security checklist cho Forwarded/CORS

1. **TLS:** certificate, SNI, HSTS và HTTP→HTTPS redirect đúng public authority. Chỉ bật HSTS sau khi đã quản trị HTTPS/subdomains đầy đủ.
2. **Host allowlist:** edge chỉ chấp nhận hostname dự kiến. Không tạo absolute links từ Host bất kỳ.
3. **Trusted hops:** biết chính xác CDN/LB/ingress nào được phép forward; strip incoming untrusted `Forwarded`/`X-Forwarded-*`.
4. **Backend isolation:** upstream chỉ cho trusted proxy truy cập; với same-host có thể loopback, với Kubernetes là network policy/private Service.
5. **Scheme normalization:** app hiểu external HTTPS, không redirect về HTTP/mixed content.
6. **Prefix ownership:** tránh double rewrite, duplicate context path, và sai OAuth2 redirect URI.
7. **CORS origin allowlist:** exact scheme/host/port, không chứa path; không wildcard cho credentialed flows.
8. **CORS route scope:** chỉ các endpoints dành cho frontend cần thiết, không `/**` vô tội vạ.
9. **CORS methods/headers:** GET/POST và header tối thiểu; thêm Authorization/PUT/DELETE theo API contract.
10. **CORS response exposure:** chỉ expose Location/requestId/headers cần client đọc, không expose bí mật.
11. **CORS preflight:** OPTIONS đi qua proxy; nếu có Security, CORS xử lý trước auth.
12. **Credentials:** allowCredentials true chỉ khi cần; exact origin; cookie Secure/HttpOnly/SameSite/Path.
13. **CSRF:** vẫn bắt buộc đánh giá khi session/cookie auth có state-changing operations.
14. **Authentication/authorization:** CORS không kiểm soát curl/Postman; phải xác minh identity và resource ownership.
15. **Cookie scope:** không đặt Domain quá rộng hoặc Path sai prefix; session ID không được log.
16. **Cache/Vary:** CDN/proxy không cache ACAO hoặc user-specific response sai origin.
17. **Logging:** không log raw `Cookie`, `Authorization`, request body hoặc client-supplied forwarded values như dữ liệu đã tin.
18. **Negative tests:** attacker Host/Forwarded, malicious origin, wrong scheme/port, prefix duplication, proxy 502.
19. **Error behavior:** proxy/Security/container errors có thể không đi qua MVC CORS; cần policy và E2E monitoring riêng.
20. **Deployment:** đo p95/p99 latency, graceful drain, keep-alive, redirect, retries và idempotency khi rolling updates.

## 24. Các câu hỏi tự kiểm tra

**1.** Vì sao Spring Boot tạo Location `http://127.0.0.1:8080` dù người dùng truy cập HTTPS?  
**Đáp án:** Backend nhận HTTP nội bộ; nếu không dùng trusted forwarded metadata, request metadata không phản ánh scheme/host public.

**2.** `server.forward-headers-strategy=framework` tự bảo vệ khỏi spoofed X-Forwarded-Host?  
**Đáp án:** Không. Filter tin các headers nhận được. Edge phải strip/overwrite và backend không public trực tiếp.

**3.** `NATIVE` và `FRAMEWORK` có giống nhau hoàn toàn?  
**Đáp án:** Không. NATIVE dựa embedded server; FRAMEWORK dùng ForwardedHeaderFilter/Transformer, thường cần khi xử lý X-Forwarded-Prefix.

**4.** NGINX `proxy_pass http://127.0.0.1:8080/;` trong `location /shop/` khác gì khi không có slash?  
**Đáp án:** Dạng có URI `/` thay prefix khớp thành `/`; dạng không URI có quy tắc giữ/chuyển đường khác. Test theo topology.

**5.** CORS allowedOrigins có thể dùng `https://app.example.test/shop` không?  
**Đáp án:** Không, origin là scheme + host + port; path scope được định nghĩa riêng trong CorsRegistry.

**6.** App và API cùng site nhưng host khác nhau có cần CORS không?  
**Đáp án:** Có. Same-site không đồng nghĩa same-origin.

**7.** CORS bảo vệ server khỏi curl hoặc non-browser client không?  
**Đáp án:** Không. Nó hạn chế browser JavaScript đọc cross-origin response.

**8.** Preflight OPTIONS thành công thì POST thực tế đã thành công chưa?  
**Đáp án:** Chưa. Browser còn gửi POST, server còn validation/auth/business logic, actual response phải có ACAO phù hợp.

**9.** Vì sao GET có thể bị CORS chặn dù không thấy OPTIONS?  
**Đáp án:** Simple GET thường không preflight; browser chặn JavaScript đọc actual response nếu ACAO thiếu/sai.

**10.** `allowedOrigins("*")` với `allowCredentials(true)` có hợp lệ không?  
**Đáp án:** Không. Spring Framework không cho phép wildcard allowedOrigins khi allowCredentials true; dùng exact origins hoặc patterns được kiểm soát kỹ nếu thực sự cần.

**11.** `Access-Control-Allow-Headers` có giúp JS đọc response Location không?  
**Đáp án:** Không. JS đọc response Location nhờ `Access-Control-Expose-Headers`.

**12.** Thêm `@CrossOrigin` trên controller có thể nới scope so với global config không?  
**Đáp án:** Có thể, vì Spring MVC kết hợp local/global policies. Cần review và test.

**13.** X-Forwarded-For là bằng chứng chắc chắn của IP người dùng?  
**Đáp án:** Không khi chain chưa xác minh; client có thể spoof values ở đầu nếu edge không sanitize.

**14.** Khi frontend sử dụng session cookies, CORS có thay CSRF không?  
**Đáp án:** Không. Cần CSRF và authorization phù hợp, browser cookie policies vẫn áp dụng.

**15.** Cookie `SameSite=Lax` nghĩa là CORS không cần nữa?  
**Đáp án:** Không. SameSite chi phối gửi cookie theo site context; CORS chi phối JavaScript cross-origin response access.

**16.** App có `server.servlet.context-path=/shop` và NGINX vừa strip `/shop` vừa gửi X-Forwarded-Prefix. Có thể gặp gì?  
**Đáp án:** Duplicate prefix, route mismatch hoặc sai Location. Chọn một chiến lược consistent và test E2E.

**17.** Nếu curl gửi Origin malicious rồi vẫn nhận HTTP 201 thì CORS đã thất bại?  
**Đáp án:** Không hẳn: CORS không chặn mọi non-browser HTTP sends. Với cross-origin CORS actual request, browser không được đọc response nếu không có ACAO; server vẫn cần auth/CSRF bảo vệ side effects.

**18.** Tại sao khi dùng proxy chain phải quan tâm RFC Forwarded và X-Forwarded cùng lúc?  
**Đáp án:** Framework/gateway có thể đọc cả hai; nếu chỉ overwrite một họ, client có thể gửi giá trị giả ở họ còn lại.

**19.** Vì sao CDN cần Vary: Origin?  
**Đáp án:** Response CORS có thể khác theo Origin; cache phải phân biệt biến thể để không phát sai policy giữa origins.

**20.** MockMvc test X-Forwarded-Prefix pass có chứng minh NGINX đã strip attacker header không?  
**Đáp án:** Không. MockMvc kiểm chức năng Spring; chỉ E2E test qua edge mới kiểm chứng trust boundary thực.

## 25. Tài liệu tham khảo chính thức

1. [Spring Boot 3.3 — Embedded Web Servers, Running Behind a Front-end Proxy](https://docs.spring.io/spring-boot/3.3/how-to/webserver.html)
2. [Spring Boot 3.3 — Servlet Web Applications](https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html)
3. [Spring Boot 3.3 — Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/)
4. [Spring Framework 6.1 — ForwardedHeaderFilter API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/filter/ForwardedHeaderFilter.html)
5. [Spring Framework — Forwarded Header Filter and Security Considerations](https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html)
6. [Spring Framework 6.1 — CORS](https://docs.spring.io/spring-framework/reference/6.1/web/webmvc-cors.html)
7. [Spring Framework 6.1 — CorsConfiguration API](https://docs.spring.io/spring-framework/docs/6.1.1/javadoc-api/org/springframework/web/cors/CorsConfiguration.html)
8. [Spring Security — CORS Servlet Integration](https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html)
9. [NGINX — ngx_http_proxy_module / proxy_pass / proxy_set_header](https://nginx.org/en/docs/http/ngx_http_proxy_module.html)
10. [NGINX — Reverse Proxy Admin Guide](https://docs.nginx.com/nginx/admin-guide/web-server/reverse-proxy/)
11. [RFC 7239 — Forwarded HTTP Extension](https://www.rfc-editor.org/rfc/rfc7239)
12. [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110)
13. [MDN — Cross-Origin Resource Sharing](https://developer.mozilla.org/en-US/docs/Web/HTTP/CORS)
14. [MDN — Same-Origin Policy](https://developer.mozilla.org/en-US/docs/Web/Security/Same-origin_policy)
15. [MDN — HTTP Cookies](https://developer.mozilla.org/en-US/docs/Web/HTTP/Cookies)
16. [OWASP — HTTP Headers Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/HTTP_Headers_Cheat_Sheet.html)
17. [OWASP — CSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html)

**Kết luận:** Triển khai Spring Boot sau reverse proxy đòi hai bài toán độc lập nhưng có liên hệ. **Forwarded headers** giúp ứng dụng hiểu public scheme/host/port/prefix, với điều kiện **chỉ tin các headers được proxy đáng tin chuẩn hóa**. **CORS** quy định origin/browser nào có thể đọc cross-origin response tại **những API paths cần thiết**, không thay authentication, authorization hoặc CSRF. Một cấu hình tốt phải đồng nhất NGINX rewrite, `server.forward-headers-strategy=framework`, Spring MVC CorsRegistry, cookie/redirect policy và **kiểm thử cả MockMvc, HTTP thật lẫn E2E qua proxy HTTPS**, kể cả các trường hợp malicious Origin và spoofed Forwarded headers.
