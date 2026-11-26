# SPA cùng origin qua reverse proxy

## Mục tiêu học tập

Sau bài học thuộc chương **Tích hợp ứng dụng**, người học có thể:

- Giải thích cách **Single-Page Application (SPA)** và backend Spring được triển khai phía sau **reverse proxy**, trong khi browser chỉ nhìn thấy **một origin**.
- Phân biệt **origin mà browser nhìn thấy** với mạng nội bộ giữa proxy và backend; hiểu vì sao một request `/api/**` cùng origin thường **không cần CORS**, nhưng vẫn có thể cần **CSRF token**.
- Thiết kế tuyến đường `/`, `/assets/**`, `/api/**` cho SPA, endpoint cấp CSRF token, login/logout và các request có tác động, tránh SPA fallback trả nhầm `index.html` cho API.
- Tích hợp session cookie `HttpOnly; Secure; SameSite` với token CSRF được SPA chủ động gửi trong HTTP header; giải quyết token **deferred**, **XOR-masked**, token invalidation sau login/logout và lỗi phiên hết hạn.
- Cấu hình minh họa **Nginx**, **Spring Security Servlet** và **Reactive/WebFlux**, xác định rõ vai trò của proxy, security filters và ứng dụng frontend.
- Chẩn đoán những lỗi triển khai có liên quan đến `Host`/`X-Forwarded-*`, TLS termination, `Cookie Path`/`Domain`, cache, URL rewrite, CORS, CSP, HSTS và nhiều node ứng dụng.
- Thiết kế bộ kiểm thử **MockMvc**, **WebTestClient**, integration test và **browser E2E** để chứng minh request có/không có token và credential được xử lý đúng.
- Nhận diện giới hạn bảo mật của việc “cùng origin”: **XSS, subdomain cùng site, clickjacking, endpoint GET có tác động và API nhận cookie nhưng tắt CSRF** vẫn cần được kiểm soát.

## 1. Bài toán: frontend SPA và backend là hai dịch vụ, browser thấy bao nhiêu origin?

Một ứng dụng có thể được phát triển thành hai thành phần độc lập:

- **Frontend SPA:** React, Vue, Angular hoặc ứng dụng JavaScript tương đương; bản build gồm `index.html`, JS/CSS và tài nguyên tĩnh.
- **Backend Spring Security:** API có xác thực, phân quyền và những lớp bảo vệ HTTP; có thể dùng **Servlet/Spring MVC** hoặc **Reactive/WebFlux**.

Khi phát triển, frontend thường chạy ở `http://localhost:5173` còn backend ở `http://localhost:8080`. **Đó là hai origin khác nhau** vì port khác nhau. Nhưng ở production, có thể đặt cả hai sau một **reverse proxy**:

~~~text
Internet / Browser
    |
    | https://app.example.com/
    v
Reverse proxy (TLS termination, routing)
    |-- GET /, /assets/** --> SPA static files
    |
    |-- /api/** ----------> Spring backend ở mạng nội bộ
                              http://spring-service:8080
~~~

Dưới góc nhìn browser:

~~~http
GET https://app.example.com/
GET https://app.example.com/assets/app.abc123.js
GET https://app.example.com/api/csrf
POST https://app.example.com/api/profile
~~~

Tất cả đều dùng **cùng scheme, hostname và effective port**: `https://app.example.com:443`. Đây là **same-origin** theo mô hình browser.

Còn `http://spring-service:8080` là **địa chỉ upstream trong mạng server**. Việc proxy nói chuyện với upstream qua một host/port khác **không làm các request của browser trở thành cross-origin**. Browser không trực tiếp gọi upstream đó.

### 1.1. Phân biệt origin với site

**Origin** được tính từ scheme, host và port; **site** trong schemeful same-site dựa trên scheme và registrable domain theo quy tắc browser.

| Cặp URL browser | Cùng origin? | Cùng site? | Liên hệ với cấu hình |
|---|---|---|---|
| `https://app.example.com/` → `https://app.example.com/api/orders` | **Có** | Có | Mục tiêu của kiến trúc bài này |
| `https://app.example.com/` → `https://api.example.com/orders` | Không | Có thể có | Cần xét CORS và fetch credentials |
| `https://app.example.com:443/` → `https://app.example.com:8443/api` | Không | Thường có | Port khác làm khác origin |
| `https://app.example.com/` → `http://app.example.com/api` | Không | Khác site theo schemeful same-site | Hạ cấp HTTPS, có thể bị mixed content |
| `https://app.example.com/` → `https://other.test/api` | Không | Không | Cross-origin và cross-site |

**Vấn đề cốt lõi:** Cấu trúc dự án “frontend và backend khác process” **không quyết định** browser có gặp CORS hay không; browser chỉ thấy URL cuối cùng mà nó gửi request đến.

### 1.2. Sơ đồ luồng đọc và ghi

~~~mermaid
sequenceDiagram
    actor U as Người dùng
    participant B as Browser SPA
    participant P as Reverse proxy
    participant S as Spring Security API
    participant D as Service / Database

    U->>B: Mở https://app.example.com
    B->>P: GET /
    P-->>B: index.html
    B->>P: GET /assets/app.js
    P-->>B: JS bundle
    B->>P: GET /api/csrf
    P->>S: GET /api/csrf + cookies nếu có
    S-->>P: Token CSRF + Set-Cookie phiên nếu tạo
    P-->>B: JSON token + cookie
    U->>B: Submit form SPA
    B->>P: POST /api/profile + cookie + X-CSRF-TOKEN
    P->>S: Forward POST với header và cookie
    S->>S: Kiểm tra CSRF, authentication, authorization
    S->>D: Validate và cập nhật
    D-->>S: Kết quả
    S-->>P: 204 No Content
    P-->>B: 204 No Content
    B-->>U: Cập nhật giao diện
~~~

Proxy phải **giữ method, body, các header cần thiết và cookie** khi chuyển tiếp. Nếu header CSRF bị proxy/gateway bỏ, server có thể trả `403` dù SPA đã gửi đúng request.

## 2. Vì sao same-origin giảm CORS nhưng không loại CSRF?

### 2.1. Same-origin giúp request JavaScript đơn giản hơn

Một SPA gọi API bằng đường dẫn tương đối:

~~~javascript
const result = await fetch("/api/profile", {
  method: "GET",
  credentials: "same-origin"
});
~~~

Browser thấy API cùng origin với trang SPA, nên lời gọi này **không cần được CORS cấp quyền như một fetch cross-origin**. Ở `fetch`, `credentials: "same-origin"` là giá trị mặc định thường gặp; viết tường minh giúp làm rõ mô hình session cookie.

Ưu điểm kiến trúc:

- Giảm phức tạp `Access-Control-Allow-Origin`/`Access-Control-Allow-Credentials`.
- Frontend không cần biết hostname/port nội bộ của backend.
- Tránh nhiều lỗi mixed content và domain cookie khác site.
- API, login/logout và CSRF token có thể chia sẻ một host công khai ổn định.
- Proxy có thể tập trung TLS, các rule URL và logging an toàn.

**Tuy nhiên:** Những yêu cầu tới bên thứ ba (CDN, OAuth Provider hoặc API nằm ngoài `app.example.com`) vẫn có thể chịu CORS/chính sách browser riêng. “Ứng dụng SPA cùng origin” không đồng nghĩa **mọi tài nguyên trên Internet** đều trở thành same-origin.

### 2.2. Cookie phiên vẫn là ambient credential

Sau login, backend có thể phát:

~~~http
Set-Cookie: JSESSIONID=opaque-session-id; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Browser tự gửi cookie đó tới request phù hợp:

~~~http
POST /api/profile HTTP/1.1
Host: app.example.com
Cookie: JSESSIONID=SESSION_A
Content-Type: application/json

{"displayName":"Alice"}
~~~

Một website ngoài có thể gây ra **một số kiểu request tới app** mà không cần đọc được cookie hay response. Browser sẽ quyết định có gửi cookie theo `SameSite`/`Domain`/`Path`, kiểu request và ngữ cảnh site. Nếu backend chấp nhận một request thay đổi trạng thái có cookie nhưng **không kiểm tra token hoặc phòng vệ tương đương**, tiền đề CSRF vẫn có thể tồn tại.

Vì vậy với SPA cùng origin **dùng session cookie**, giữ `CsrfFilter` (Servlet) hoặc `CsrfWebFilter` (Reactive) và đưa token CSRF vào request ghi.

> **Same-origin giải quyết quyền giao tiếp frontend–API theo chính sách browser; CSRF token giải quyết tính hợp lệ của những request có tác động khi credential được browser tự gửi.**

### 2.3. Không nhầm SameSite với same-origin

Một trang do attacker kiểm soát ở `https://blog.example.com` có thể khác origin với `https://app.example.com` nhưng vẫn cùng site. Với cookie `SameSite=Lax` hoặc `Strict`, browser có thể gửi cookie của app **đến app** khi request được kích hoạt từ blog.

Trang blog thường không đọc được CSRF token trong DOM/response riêng origin app do **Same-Origin Policy**, vì vậy CSRF token vẫn có giá trị chống request giả mạo.

### 2.4. XSS vẫn là giới hạn nghiêm trọng

JavaScript không tin cậy chạy **trong origin `app.example.com`** có thể sử dụng cùng kênh `GET /api/csrf` và `fetch("/api/...")` như JavaScript hợp lệ. Cookie `HttpOnly` ngăn đọc trực tiếp giá trị session ID, **không ngăn** browser tự gắn cookie cho request same-origin.

Do đó phải chống XSS bằng output encoding, DOM API an toàn, quản lý script bên thứ ba, CSP thích hợp và phân quyền. **CSRF token không thay lớp chống XSS.**

## 3. Chọn URL public và quy tắc định tuyến trước khi viết code

### 3.1. Một hợp đồng URL có chủ đích

Trong bài này thống nhất:

| Public URL | Bên xử lý | Chức năng |
|---|---|---|
| `GET /` | Static server / reverse proxy | Trả `index.html` khởi động SPA |
| `GET /assets/**` | Static server / reverse proxy | Trả JS/CSS/font đã build |
| `GET /dashboard`, `GET /settings` | SPA fallback | Trả `index.html` để router phía client xử lý |
| `GET /api/csrf` | Spring backend | Phát metadata/token CSRF cho client cùng origin |
| `POST /api/login` | Spring Security backend | Form login với CSRF token |
| `POST /api/logout` | Spring Security backend | Logout với CSRF token |
| `GET /api/me` | Spring backend | Trả danh tính người dùng đã xác thực |
| `POST /api/profile` | Spring backend | Cập nhật dữ liệu cần xác thực và CSRF |
| `/api/**` khác | Spring backend | API có trạng thái HTTP thực, không phải SPA fallback |

**Mấu chốt:** `/api/**` không được chuyển sang `index.html` khi backend trả `401`, `403` hoặc `404`. Nếu trả HTML 200 cho request API, frontend dễ báo lỗi JSON parsing khó hiểu, monitoring ghi sai tỷ lệ lỗi và đôi khi che giấu security chain không áp dụng.

### 3.2. Route cho SPA deep link

Một người dùng có thể mở trực tiếp `https://app.example.com/settings`. Nginx không tìm thấy file vật lý tên `settings`, nên có thể trả `index.html` để router client nhận đường dẫn.

Ngược lại, `GET /api/orders/unknown` phải được **forward đến backend**, để API trả `404` phù hợp. Không trả index.html cho nó.

### 3.3. Đừng hardcode backend internal URL trong bundle

**Không nên** để JS production gọi:

~~~javascript
// Sai khi browser không thể hoặc không nên truy cập upstream nội bộ.
fetch("http://spring-service:8080/api/profile");
~~~

**Nên** gọi đường dẫn tương đối same-origin:

~~~javascript
fetch("/api/profile", { credentials: "same-origin" });
~~~

Đường dẫn này phụ thuộc **public path contract**, không phụ thuộc IP của node backend hoặc cổng service. Nếu triển khai SPA dưới prefix `/portal`, phải định nghĩa lại base path/API routing có chủ đích (ví dụ `/portal/api/**` hoặc `/api/**`), không ghép chuỗi tương đối tùy tiện.

## 4. Nginx reverse proxy: định tuyến tĩnh và API

Một cấu hình minh họa cho **HTTPS public edge**:

~~~nginx
upstream spring_backend {
    server 127.0.0.1:8080;  # Ví dụ: thay bằng địa chỉ upstream nội bộ
    keepalive 16;
}

server {
    listen 443 ssl;
    server_name app.example.com;

    # Ví dụ placeholder: sử dụng chứng chỉ và private key thật do hệ thống quản lý.
    ssl_certificate     /etc/ssl/example/app.crt;
    ssl_certificate_key /etc/ssl/example/app.key;

    root /srv/my-spa/dist;
    index index.html;

    # API, login, logout và CSRF endpoint đều đi qua Spring.
    location /api/ {
        proxy_pass http://spring_backend;
        # Không thêm URI sau upstream: giữ nguyên path /api/...
        proxy_http_version 1.1;

        proxy_set_header Host              $host;
        proxy_set_header X-Forwarded-Host  $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Port  $server_port;
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;

        # Không cache các response API dùng session/token.
        proxy_cache off;
    }

    # Asset có fingerprint, có thể cache dài nếu quy trình build bảo đảm tên bất biến.
    location /assets/ {
        try_files $uri =404;
        add_header Cache-Control "public, max-age=31536000, immutable";
    }

    # index.html nên được kiểm tra lại để nhận bản deploy mới.
    location = /index.html {
        add_header Cache-Control "no-cache";
    }

    # Fallback cho client-side routes; KHÔNG áp lên /api/**.
    location / {
        try_files $uri $uri/ /index.html;
    }
}
~~~

Đây là **ví dụ cấu trúc**, không phải một bản cấu hình production hoàn chỉnh: còn cần HTTP→HTTPS redirect phù hợp, TLS versions/ciphers, timeout, giới hạn upload, logging, kiểm soát host, observability và chính sách edge firewall theo hạ tầng.

**Chi tiết dễ gây lỗi:** Trong Nginx, `proxy_pass http://spring_backend;` **không có phần URI phía sau** thường giữ nguyên path `/api/...`. Nếu viết `proxy_pass http://spring_backend/;` **có dấu gạch chéo URI**, Nginx có thể thay prefix đã match, khiến `/api/profile` trở thành `/profile` ở backend. Phải chọn có chủ đích và kiểm tra path backend nhận được.

### 4.1. Ai được quyền đặt forwarded headers?

Các header như `X-Forwarded-Proto` và `X-Forwarded-Host` giúp backend biết **public scheme/host** khi proxy terminate TLS. Nhưng nếu backend **tin những header do client trực tiếp tự gửi**, attacker có thể làm sai việc tạo redirect, absolute URL, kiểm tra origin hoặc ghi log.

Yêu cầu:

- Chặn browser truy cập trực tiếp cổng backend; chỉ proxy đáng tin cậy được kết nối.
- Edge proxy ghi đè hoặc làm sạch các header forwarding theo chính sách, không tin giá trị client tự gắn.
- Backend chỉ xử lý forwarded headers từ chuỗi proxy đáng tin cậy.
- Giới hạn/kiểm tra host công khai và tránh wildcard host không kiểm soát.

### 4.2. Đừng để proxy chặn hoặc sửa CSRF header

Nếu SPA gửi:

~~~http
POST /api/profile HTTP/1.1
Host: app.example.com
Cookie: JSESSIONID=SESSION_A
X-CSRF-TOKEN: MASKED_TOKEN_FROM_SERVER
Content-Type: application/json

{"displayName":"Alice"}
~~~

Proxy phải forward **`X-CSRF-TOKEN`**, cookie và request body đúng. Hãy kiểm tra config gateway/WAF custom nếu request hợp lệ bị `403`. Không viết rule “loại các header `X-*` không biết” rồi vô tình xóa token.

### 4.3. Cache nên tách theo loại response

| Response | Cache policy định hướng | Vì sao |
|---|---|---|
| `/assets/app.hash.js` | Cache dài/immutable khi tên có fingerprint | Giảm tải và tăng tốc |
| `/index.html` | `no-cache`/phải revalidate hoặc policy tương đương | Giúp nhận bản SPA mới |
| `/api/csrf` | **`Cache-Control: no-store`** | Token gắn ngữ cảnh phiên; không chia sẻ qua cache |
| `/api/me` | Thường `no-store` khi chứa dữ liệu cá nhân | Tránh trả nhầm dữ liệu giữa user/phiên |
| `/api/login`, `/api/logout` | Không cache | Response thay đổi trạng thái xác thực |
| API GET công khai | Có thể có cache có kiểm soát | Tùy dữ liệu và authorization |

Với `/api/csrf`, không chỉ dựa vào `proxy_cache off` mà còn cần response header phù hợp để browser/proxy trung gian không lưu token. Không gửi CSRF token trong URL, analytics hay access log.

## 5. Session cookie của SPA cùng origin

### 5.1. Cookie xác thực vẫn có thể là HttpOnly

Cookie phiên nên có chính sách phù hợp:

~~~http
Set-Cookie: JSESSIONID=opaque; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

SPA **không cần đọc chuỗi session ID** bằng JavaScript. `fetch("/api/me", { credentials: "same-origin" })` cho phép browser gửi cookie theo policy, backend dùng phiên để xác định user.

Không dùng:

~~~javascript
const sid = document.cookie; // Không lấy và chép session ID vào header riêng.
~~~

`HttpOnly` khiến session cookie không xuất hiện trong `document.cookie`, nhưng nó vẫn có thể được browser đính kèm vào request phù hợp.

### 5.2. Cookie Path, Domain và context path

Nếu session cookie có `Path=/api`, nó chỉ được gửi tới request có path phù hợp, ví dụ `/api/profile`. Điều đó có thể **hoàn toàn hợp lệ** nếu tất cả endpoint cần auth đều nằm ở `/api/**`.

Nếu cookie lại có `Path=/legacy` nhưng SPA gọi `/api/login`/`/api/profile`, browser có thể không gửi cookie, dẫn đến vòng lặp đăng nhập hoặc `401`. Cần đối chiếu `Set-Cookie` **và** header `Cookie` ở request thực.

Cookie host-only (không có `Domain`) thường phù hợp khi frontend/API cùng host public. Không thêm `Domain=.example.com` chỉ để “cho SPA nhận cookie”: nó không cần chia sẻ cookie sang các subdomain khi mọi request dùng `app.example.com`.

### 5.3. SameSite không miễn CSRF

`SameSite=Lax` thường ngăn cookie ở nhiều cross-site POST, nhưng:

- Top-level cross-site GET vẫn có thể gửi cookie Lax; **GET phải chỉ đọc**.
- Same-site cross-origin từ subdomain ít tin cậy có thể mang cookie cả khi Strict/Lax.
- Login CSRF có thể tạo phiên mới, không nhất thiết dựa vào cookie đã xác thực.
- Browser và policy cookie bên thứ ba không hoàn toàn đồng nhất.

Vì vậy **session-cookie SPA vẫn cần CSRF token** cho request có tác động theo chính sách Spring Security.

## 6. Hai mô hình cấp CSRF token cho SPA

| Mô hình | Kênh cấp token | Client gửi lại qua | Đặc điểm |
|---|---|---|---|
| **Session-backed synchronizer token** | `GET /api/csrf` trả JSON token của phiên | Header `X-CSRF-TOKEN` hoặc tên được server công bố | Giữ expected token trên server; dễ làm rõ session binding |
| **Cookie CSRF repository** | Cookie riêng như `XSRF-TOKEN`; JavaScript đọc khi cấu hình cho phép | Header `X-XSRF-TOKEN` | Cần xử lý cookie scope, raw/masked và cookie injection; không đồng nghĩa signed HMAC |

Trong bài này, **luồng chính dùng synchronizer token theo session** để tách rành mạch cookie xác thực khỏi token CSRF. Biến thể cookie sẽ được phân tích riêng.

### 6.1. Expected token, submitted token và XOR masking

Spring Security Servlet thường dùng `HttpSessionCsrfTokenRepository` để lưu expected token theo phiên. Token được render cho client có thể **XOR-masked** bởi request handler để giảm rủi ro rò rỉ kiểu BREACH. Hai lần GET có thể trả hai **chuỗi masked khác nhau** nhưng cùng tương ứng raw token đang lưu.

~~~text
Expected raw token trong session A: R

GET /api/csrf lần 1  -> token cho client: M1 = mask(R, nonce1)
GET /api/csrf lần 2  -> token cho client: M2 = mask(R, nonce2)

M1 có thể khác M2.
POST với M1/M2 hợp lệ theo handler -> so với expected R.
POST với chuỗi tự bịa hoặc phiên khác -> từ chối.
~~~

**Không tự giả định token JSON là raw token nội bộ.** Dùng đúng giá trị được endpoint cấp và đúng header name theo `CsrfToken`. Khi thay request handler hoặc CSRF repository, phải kiểm thử round-trip thật.

### 6.2. Deferred token và thời điểm phát cookie

Spring Security hiện đại có thể trì hoãn việc tải/tạo CSRF token cho tới khi ứng dụng **thật sự truy cập token**. Với SPA mà `index.html` được proxy phục vụ tĩnh, chỉ mở trang `/` có thể **chưa tạo CSRF token** ở backend.

Vì vậy trước POST đầu tiên, SPA cần gọi `GET /api/csrf` hoặc dùng một kênh cấp token rõ ràng. Endpoint đó phải **đọc/subscribe token** để repository phát giá trị đúng.

Sau login/logout, token cũ có thể bị vô hiệu hóa. SPA nên **lấy token mới qua kênh hợp lệ** sau khi trạng thái xác thực thay đổi; không giữ token cũ suốt vòng đời JS rồi coi `403` là lỗi CORS.

## 7. Luồng frontend chuẩn trước khi nối backend

Một SPA dùng session cookie và token JSON có thể theo trình tự:

~~~mermaid
flowchart TD
    A[SPA tải index.html và JS] --> B[GET /api/csrf, lưu token trong memory]
    B --> C{Đã đăng nhập?}
    C -->|Chưa| D[POST /api/login với token]
    D --> E{Đăng nhập thành công?}
    E -->|Không| F[Hiển thị lỗi login; không giả định phiên mới]
    E -->|Có| G[GET /api/csrf để nhận token của phiên sau login]
    C -->|Có| H[GET /api/me]
    G --> H
    H --> I[POST /api/profile với token hiện hành]
    I --> J{HTTP response}
    J -->|2xx| K[Cập nhật UI]
    J -->|401| L[Đăng nhập lại theo luồng an toàn]
    J -->|403| M[Phân biệt CSRF, authorization và token hết hiệu lực]
    H --> N[POST /api/logout với token]
    N --> O[Xóa state UI và chuẩn bị phiên ẩn danh nếu cần]
~~~

**Chú ý thứ tự:** `GET /api/csrf` thường cần được phép gọi trước login nếu `POST /api/login` thuộc bảo vệ CSRF. `permitAll` cho endpoint cấp token **không làm nó thành endpoint dành cho mọi origin đọc token**; phải giữ policy cùng origin và không mở credentialed CORS rộng.

## 8. Spring Security Servlet: một ứng dụng API dùng session cookie

### 8.1. Các thành phần minh họa

Giả định dự án dùng Spring Boot + Spring MVC với:

~~~text
spring-boot-starter-web
spring-boot-starter-security
spring-security-test              (test scope)
spring-boot-starter-test          (test scope)
~~~

Thêm cách xác thực người dùng phù hợp: `UserDetailsService`, authentication provider, SSO hoặc cơ chế được ứng dụng quản lý. **Không dùng user/password hardcoded trong production**.

Kiến trúc ở đây:

- Nginx phục vụ tài nguyên SPA và forward `/api/**`;
- Spring xử lý `/api/csrf`, `/api/login`, `/api/logout` và API nghiệp vụ;
- Authentication dựa trên `HttpSession`/cookie `JSESSIONID`;
- POST dùng **CSRF token theo phiên**;
- Browser chỉ kết nối đến `https://app.example.com`.

### 8.2. SecurityFilterChain cho API session-based

~~~java
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpStatus;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.HttpStatusEntryPoint;
import org.springframework.security.web.csrf.HttpSessionCsrfTokenRepository;
import org.springframework.security.web.util.matcher.AntPathRequestMatcher;

@Configuration
class SpaServletSecurityConfig {

    @Bean
    SecurityFilterChain spaApiSecurity(HttpSecurity http)
            throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                // Endpoint phát token cho form login trước khi user xác thực.
                .requestMatchers(HttpMethod.GET, "/api/csrf").permitAll()
                // Spring Security vẫn bắt buộc CSRF cho POST login.
                .requestMatchers(HttpMethod.POST, "/api/login").permitAll()
                .anyRequest().authenticated()
            )
            .formLogin(form -> form
                .loginProcessingUrl("/api/login")
                // SPA nhận status thay vì phải parse HTML/redirect login.
                .successHandler((request, response, authentication) ->
                    response.setStatus(HttpServletResponse.SC_NO_CONTENT))
                .failureHandler((request, response, exception) ->
                    response.sendError(HttpServletResponse.SC_UNAUTHORIZED))
            )
            .logout(logout -> logout
                .logoutUrl("/api/logout")
                .logoutSuccessHandler((request, response, authentication) ->
                    response.setStatus(HttpServletResponse.SC_NO_CONTENT))
            )
            .exceptionHandling(errors -> errors
                .defaultAuthenticationEntryPointFor(
                    new HttpStatusEntryPoint(HttpStatus.UNAUTHORIZED),
                    new AntPathRequestMatcher("/api/**"))
            )
            // Session-backed expected token; giữ CSRF ở mọi unsafe API.
            .csrf(csrf -> csrf.csrfTokenRepository(
                new HttpSessionCsrfTokenRepository()
            ))
            .build();
    }
}
~~~

**Những điểm phải hiểu khi dùng mẫu này:**

- `.permitAll()` với `POST /api/login` **chỉ bỏ yêu cầu đã đăng nhập**, không loại bước CSRF. Request login vẫn phải có token hợp lệ, trừ khi chính sách CSRF bị thay đổi ở nơi khác.
- `loginProcessingUrl("/api/login")` để Spring Security form-login filter xử lý request. Không tự tạo `@PostMapping("/api/login")` để xử lý cùng URL nếu không có thiết kế authentication riêng.
- Form login filter dùng **form-encoded body** với trường `username` và `password` theo mặc định; JSON login cần converter/filter tùy chỉnh và kiểm thử riêng.
- `204 No Content` giúp SPA nhận biết thành công mà không phải xử lý redirect HTML. Nếu ứng dụng dùng OAuth2/OIDC hoặc login provider khác, authentication flow/handler phải được thiết kế theo giao thức tương ứng.
- `logoutUrl("/api/logout")` thường được bảo vệ bởi CSRF khi dùng POST; bảo đảm không mở GET logout thực hiện thay đổi phiên.
- `.anyRequest().authenticated()` giữ an toàn cho endpoint khác nếu có request đến backend ngoài `/api/**`. Proxy vẫn nên chỉ forward những route đã định.
- `HttpSessionCsrfTokenRepository` là lựa chọn minh họa minh bạch; Spring Security thường bật CSRF sẵn trong mô hình web session nhưng không nên dựa vào giả định khi có nhiều security chain.
- Spring Security có thể thay đổi session ID sau login để chống session fixation. SPA không phải tự đọc/sao chép session cookie; browser tự quản lý.

**Với custom login success handler**, logic app cần đảm bảo HTTP response có status chính xác, không chứa nội dung HTML ngầm và không cache. Nếu frontend đòi thông tin người dùng sau login, hãy gọi `GET /api/me` thay vì dựa vào cookies mà JavaScript không được đọc.

### 8.3. Endpoint GET /api/csrf: cấp token cho SPA

~~~java
import java.util.Map;

import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class CsrfApiController {

    @GetMapping("/api/csrf")
    ResponseEntity<Map<String, String>> getCsrfToken(CsrfToken token) {
        // Truy cập getToken() buộc giá trị deferred được tạo/tải nếu cần.
        String submittedValue = token.getToken();

        return ResponseEntity.ok()
            .cacheControl(CacheControl.noStore())
            .body(Map.of(
                "headerName", token.getHeaderName(),
                "parameterName", token.getParameterName(),
                "token", submittedValue
            ));
    }
}
~~~

Đây là **endpoint do ứng dụng tự xây dựng**, không phải URL mà Spring Security mặc định tự phát hành. Nó cung cấp **submitted token phù hợp với request handler** cho frontend.

Ví dụ response:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Set-Cookie: JSESSIONID=...; Path=/; Secure; HttpOnly; SameSite=Lax

{
  "headerName": "X-CSRF-TOKEN",
  "parameterName": "_csrf",
  "token": "MASKED_TOKEN_FROM_THIS_RESPONSE"
}
~~~

`Set-Cookie` có thể chỉ xuất hiện khi token/session mới được tạo hoặc khi cookie được thay; response **không phải lúc nào cũng cần lặp Set-Cookie**.

**Kiểm soát endpoint token:**

- Không cho JavaScript ở origin tùy ý đọc response bằng credentialed CORS.
- Không nhúng token vào URL/query string hoặc redirect.
- Không cache response chứa token riêng theo phiên và không đưa vào CDN/public cache.
- Không log raw token hay session ID.
- Khi backend không truy cập token, deferred loading có thể làm token chưa được phát; endpoint mẫu này chủ động đọc `getToken()`.
- Một XSS cùng origin vẫn có thể gọi endpoint và đọc token; cần chống XSS riêng.

### 8.4. Endpoint API đọc và ghi dữ liệu

~~~java
import java.security.Principal;
import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
class ProfileApiController {

    private final ProfileService profiles;

    ProfileApiController(ProfileService profiles) {
        this.profiles = profiles;
    }

    @GetMapping("/api/me")
    Map<String, String> me(Principal principal) {
        return Map.of("username", principal.getName());
    }

    record RenameRequest(String displayName) {}

    @PostMapping("/api/profile")
    ResponseEntity<Void> rename(
            Principal principal,
            @RequestBody RenameRequest input) {

        String name = input.displayName();

        if (name == null || name.isBlank() || name.length() > 80) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "Tên hiển thị không hợp lệ");
        }

        // Service phải kiểm tra quyền, lưu dữ liệu và quản lý transaction.
        profiles.renameIfAuthorized(principal.getName(), name);

        return ResponseEntity.noContent().build();
    }
}
~~~

`ProfileService` là **service giả định của ứng dụng**, không phải class sẵn có của Spring Security. Trong hệ thống thật, cần database, validation, quyền trên từng tài nguyên, audit, xử lý lỗi và transaction phù hợp.

`GET /api/me` chỉ đọc trạng thái xác thực hiện tại; `POST /api/profile` là thao tác ghi và đi qua CSRF filter. **Không dùng GET để đổi profile** vì Spring Security mặc định thường không kiểm tra CSRF trên GET.

### 8.5. Cấu hình Spring Boot cho cookie và forwarded headers

~~~yaml
# application.yml, dành cho triển khai Servlet qua reverse proxy HTTPS đáng tin cậy
server:
  servlet:
    session:
      cookie:
        secure: true
        http-only: true
        same-site: lax
  forward-headers-strategy: framework
~~~

**Điều kiện áp dụng:**

- Public browser dùng HTTPS; proxy gửi đúng `X-Forwarded-Proto: https` và các header tin cậy.
- Backend không được phơi trực tiếp ra Internet và không tin forwarding headers đến từ bất kỳ client nào.
- `server.forward-headers-strategy: framework` là một lựa chọn Spring Boot khi dùng proxy; với container/proxy đặc thù có thể cần strategy và cấu hình khác.
- Nếu dùng Spring Session/custom session cookie serializer, phải cấu hình thuộc tính ở **nơi thực sự phát cookie**. Luôn xem `Set-Cookie` cuối cùng trong browser.
- Không bật cookie `Secure` rồi thử nghiệm bằng HTTP trực tiếp, sau đó kết luận server “không lưu session” chỉ vì browser không gửi cookie.
- Session cookie `HttpOnly` không ảnh hưởng việc SPA lấy **token từ JSON `/api/csrf`**; JS không cần đọc session ID.

## 9. JavaScript SPA: lấy token, đăng nhập và cập nhật dữ liệu

### 9.1. Giữ CSRF token trong state runtime, không trong URL

Một module client tối giản:

~~~javascript
// csrf-client.js — chỉ dùng cho API của CHÍNH origin hiện tại.
let csrfState = null;

async function loadCsrfToken() {
  const response = await fetch("/api/csrf", {
    method: "GET",
    credentials: "same-origin",
    cache: "no-store"
  });

  if (!response.ok) {
    throw new Error("Không lấy được CSRF token: " + response.status);
  }

  const data = await response.json();

  if (!data.headerName || !data.token) {
    throw new Error("CSRF response thiếu headerName hoặc token");
  }

  csrfState = {
    headerName: data.headerName,
    token: data.token
  };

  return csrfState;
}

async function apiFetch(path, options = {}) {
  // Không vô tình gửi CSRF token đến origin bên ngoài.
  if (typeof path !== "string" || !path.startsWith("/api/")) {
    throw new Error("API path phải bắt đầu bằng /api/");
  }

  const method = (options.method ?? "GET").toUpperCase();
  const headers = new Headers(options.headers ?? {});

  // Xác định phương thức theo ngữ nghĩa HTTP/CSRF mặc định.
  const safeMethods = new Set(["GET", "HEAD", "OPTIONS", "TRACE"]);
  const unsafe = !safeMethods.has(method);

  if (unsafe) {
    if (!csrfState) {
      await loadCsrfToken();
    }
    headers.set(csrfState.headerName, csrfState.token);
  }

  return fetch(path, {
    ...options,
    method,
    headers,
    // Cookie JSESSIONID là do browser tự gửi; không đọc bằng JS.
    credentials: "same-origin"
  });
}

function clearCsrfState() {
  csrfState = null;
}
~~~

**Vì sao helper này không tự làm tất cả?**

- Nó chỉ làm việc với URL path bắt đầu `/api/`; trong production nên kiểm soát thêm cách chuẩn hóa URL/URL encoding nếu có đầu vào không tin cậy, tránh cấp token cho đích bất ngờ.
- Nó không thay server kiểm tra CSRF. Một request trực tiếp từ attacker không qua helper này vẫn phải bị filter chặn.
- Không tự động **retry POST** khi thấy `403`: request có thể bị authorization từ chối, token hết hạn, session chuyển đổi hoặc policy khác. Với tác vụ tài chính hoặc không idempotent, retry tự động còn có thể tạo thay đổi trùng.
- Không lưu session ID, CSRF token hoặc access token vào URL/query string/log.
- Token trong memory có thể bị script XSS cùng origin sử dụng; bảo vệ XSS và CSP vẫn bắt buộc.
- Ở trường hợp custom header name, luôn dùng tên mà backend cung cấp và whitelist những header hợp lệ ở nơi tin cậy.

### 9.2. Đăng nhập qua form-urlencoded, nhưng UI là SPA

~~~javascript
async function login(username, password) {
  // GET /api/csrf cũng có thể được gọi trước khi user xác thực.
  await loadCsrfToken();

  const form = new URLSearchParams({
    username,
    password
  });

  const response = await apiFetch("/api/login", {
    method: "POST",
    body: form
    // URLSearchParams cho fetch tạo Content-Type form-urlencoded phù hợp.
  });

  if (response.status !== 204) {
    throw new Error("Đăng nhập không thành công: " + response.status);
  }

  // Token phát trước login có thể bị invalidated khi authentication đổi.
  clearCsrfState();
  await loadCsrfToken();

  return apiFetch("/api/me");
}
~~~

Luồng này giả định **success handler trả `204`** như cấu hình Servlet ở mục 8. Nếu dùng formLogin mặc định trả redirect hoặc OAuth2 login, API contract và cách client xử lý **khác**, không được mặc định parse redirect HTML như JSON.

`POST /api/login` vẫn phải có CSRF token. Nếu backend trả `403` với form login đầu tiên, kiểm tra:

- `GET /api/csrf` có tạo token/pre-authentication session không;
- Request POST có mang **cùng cookie session** không;
- Header CSRF đúng tên/value/format không;
- Proxy có giữ `Cookie` và `X-CSRF-TOKEN` không;
- Session cookie `Secure`/`Path`/`SameSite` có được browser gửi không.

### 9.3. Đọc dữ liệu và cập nhật profile

~~~javascript
async function getCurrentUser() {
  const response = await apiFetch("/api/me");

  if (response.status === 401) {
    return null;
  }

  if (!response.ok) {
    throw new Error("Không đọc được thông tin: " + response.status);
  }

  return response.json();
}

async function changeDisplayName(displayName) {
  const response = await apiFetch("/api/profile", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ displayName })
  });

  if (response.status === 401) {
    throw new Error("Phiên đăng nhập đã hết hạn");
  }

  if (response.status === 403) {
    // Có thể là CSRF hoặc thiếu quyền; không tự đoán nguyên nhân.
    throw new Error("Yêu cầu bị từ chối: kiểm tra phiên, token và quyền");
  }

  if (!response.ok) {
    throw new Error("Cập nhật thất bại: " + response.status);
  }

  // Endpoint mẫu trả 204, không cần response.json().
}
~~~

Nếu nhận `403` ngay sau login, frontend nên xem xét **token mới sau authentication**, nhưng không nên gửi lại thao tác không idempotent một cách mù quáng. Với UI nhạy cảm, giải thích lỗi và yêu cầu người dùng xác nhận hành động sau khi làm mới trạng thái an toàn.

### 9.4. Đăng xuất qua POST có token

~~~javascript
async function logout() {
  const response = await apiFetch("/api/logout", {
    method: "POST"
  });

  if (!response.ok) {
    throw new Error("Đăng xuất không thành công: " + response.status);
  }

  // Dọn dữ liệu hiển thị/CSRF state ở frontend.
  clearCsrfState();

  // Nếu cần form login mới, lấy token trong ngữ cảnh sau logout.
  await loadCsrfToken();
}
~~~

Backend thường dọn session/security context khi logout. Nếu hệ thống có SSO/remember-me/refresh token, cần biết logout có phạm vi nào; **204** chỉ là response contract, không tự chứng minh mọi credential bên ngoài đã được thu hồi.

### 9.5. Xử lý trạng thái khởi động trang

Với SPA, quy trình startup gợi ý:

1. Render shell/loading, không tự suy luận người dùng đã login chỉ vì `localStorage` có `isLoggedIn=true`.
2. Gọi `GET /api/csrf` để có token cho login/POST.
3. Gọi `GET /api/me` để biết principal hiện tại.
4. Nếu `200`, hiện nội dung phù hợp user và authority; nếu `401`, hiện màn hình login.
5. Khi login thành công, lấy CSRF token mới; sau logout, dọn state và lấy token mới cho phiên ẩn danh nếu cần.
6. Nếu nhận `403`, phân biệt token/authorization thay vì xử lý như lỗi mạng.
7. Trên mọi request ghi, áp dụng kiểm tra quyền ở backend; frontend ẩn nút không phải một cơ chế authorization.

## 10. Phương án khác: SPA đọc token từ cookie XSRF-TOKEN

Thay vì endpoint JSON trả token theo session, một số frontend dùng cookie `XSRF-TOKEN`:

~~~http
Set-Cookie: XSRF-TOKEN=raw-csrf-token; Path=/; Secure; SameSite=Lax
~~~

SPA đọc cookie CSRF (nếu được phép) và gửi lại qua header:

~~~http
POST /api/profile HTTP/1.1
Host: app.example.com
Cookie: JSESSIONID=SESSION_A; XSRF-TOKEN=raw-csrf-token
X-XSRF-TOKEN: raw-csrf-token
Content-Type: application/json

{"displayName":"Alice"}
~~~

**Không nhầm hai cookie:**

- `JSESSIONID`: cookie xác thực/định danh phiên, **nên `HttpOnly`**.
- `XSRF-TOKEN`: cookie cung cấp token để frontend đọc và gửi lại, có thể cần **không `HttpOnly`** nếu app thiết kế đọc bằng JS.

### 10.1. CookieCsrfTokenRepository không tự có signed HMAC session binding

Spring Security Servlet cung cấp `CookieCsrfTokenRepository`, ví dụ:

~~~java
import org.springframework.security.web.csrf.CookieCsrfTokenRepository;

CookieCsrfTokenRepository repository =
    CookieCsrfTokenRepository.withHttpOnlyFalse();
~~~

Nó có thể dùng trong `http.csrf(csrf -> csrf.csrfTokenRepository(repository))` khi chọn mô hình cookie. Nhưng đây không phải một **signed double-submit HMAC ràng buộc phiên** tự động. Cần xem:

- Cookie injection từ subdomain ít tin cậy nếu dùng `Domain` quá rộng;
- Trùng tên cookie giữa các path/domain;
- Cookie scope, `Secure`, `SameSite` và chính sách đọc JavaScript;
- Request handler xử lý **raw token header** và **masked token** trong HTML;
- Việc phát lại cookie mới sau login/logout khi token cũ đã bị xóa.

### 10.2. Vấn đề XOR-masked token trên Servlet

Trong một số phiên bản Spring Security, request handler mặc định dùng XOR masking cho form-rendered token. SPA lại đọc **raw token từ cookie** và gửi bằng `X-XSRF-TOKEN`. Nếu handler đang kỳ vọng masked input từ header, request có thể bị `403` dù cookie/header chứa cùng raw token.

Đây là lý do tài liệu Spring Security có mẫu **SPA-specific CSRF token request handler**: tiếp tục mask token khi render, nhưng nhận **raw token** từ header phù hợp, và bảo đảm token deferred được tải/phát khi cần.

Không giải quyết bằng `csrf.disable()`. Khi chọn CookieCsrfTokenRepository, hãy cấu hình request handler tương thích với frontend và **test thực** cả form POST/header, login/logout và raw/masked token theo phiên bản framework. Với bài này, **mẫu JSON synchronizer token theo session ở mục 8–9** là luồng chính, không nên bật đồng thời hai repository khác nhau nếu chưa có chủ đích.

### 10.3. Không mở cookie JS để giải quyết nhầm lỗi

Nếu SPA đọc token bằng `GET /api/csrf`, **không cần `HttpOnly=false` trên session cookie**. Một lỗi 403 không phải lý do để cho JavaScript đọc `JSESSIONID`; việc đó tăng nguy cơ lấy cắp phiên qua XSS.

## 11. Security headers của SPA qua proxy

### 11.1. CSP phải bảo vệ trang SPA, không chỉ response API

Nếu `index.html` do **Nginx** trả mà backend Spring chỉ phục vụ `/api/**`, CSP do Spring Security thêm vào **response backend** **không tự xuất hiện trên index.html**.

Vì vậy chủ sở hữu của từng response cần được xác định:

| Response | Bên tạo | Lớp header cần xem |
|---|---|---|
| `/index.html`, `/settings` fallback | Nginx/static server | CSP, frame-ancestors, MIME/nosniff và cache |
| `/assets/app.js` | Nginx/static server | Content-Type đúng, cache và nosniff |
| `/api/**` | Spring backend, qua proxy | Cache private, security headers cần thiết, tránh leak token |
| Redirect từ backend | Spring, có thể qua proxy | HTTPS public scheme, Location, cache |
| Error page của proxy | Nginx | Không lộ upstream topology, status đúng, headers phù hợp |

Một CSP ban đầu cho SPA chỉ tải script cùng origin:

~~~http
Content-Security-Policy: default-src 'self'; script-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'
~~~

Đây chỉ là **mẫu tham khảo**. `script-src 'self'` có thể không đủ mạnh nếu origin chứa script không tin cậy. Các ứng dụng phức tạp nên nghiên cứu CSP dùng nonce/hash, `strict-dynamic` khi phù hợp, Trusted Types và loại bỏ JavaScript inline không cần thiết.

**Điều quan trọng:** Nếu muốn CSP bảo vệ SPA, header phải có trên **HTML response** mà browser thực sự tải, chứ không chỉ trên JSON của API.

### 11.2. HSTS, X-Content-Type-Options và frame protection

- `Strict-Transport-Security` (HSTS) giúp browser áp dụng HTTPS cho host trong phạm vi chính sách; chỉ dùng khi HTTPS vận hành ổn định và hiểu tác động của `includeSubDomains`/preload.
- `X-Content-Type-Options: nosniff` giúp hạn chế diễn giải sai MIME của script/style.
- `Content-Security-Policy: frame-ancestors ...` hạn chế trang bị nhúng bởi website khác, hỗ trợ chống clickjacking.
- `Referrer-Policy` và những policy khác cần xem theo dữ liệu, product requirements và khả năng tương thích.

Khi proxy là nơi phục vụ HTML và terminate TLS, cần thống nhất **ai thêm header nào**, tránh duplicate CSP xung đột hoặc hở do chỉ thêm ở một route.

### 11.3. CSRF không giải quyết XSS trong SPA

Một script độc hại thực thi tại `https://app.example.com` có thể gọi `GET /api/csrf` và gửi request cùng origin. `HttpOnly` không cho nó đọc trực tiếp session ID nhưng browser vẫn tự gắn cookie.

Do đó tránh `innerHTML` với dữ liệu chưa sanitize, dùng DOM API an toàn như `textContent`, quản lý dependency và chặt chẽ về CSP. Token CSRF được cấp cho script hợp lệ **không thể phân biệt** script hợp lệ với XSS cùng origin.

## 12. Reactive/WebFlux: SPA cùng origin với WebSession

### 12.1. Kiến trúc giống nhau, API bảo mật khác nhau

Khi backend sử dụng **Spring WebFlux/Reactive**, Nginx vẫn có thể phục vụ SPA ở `/` và forward `/api/**` tới một upstream WebFlux. Browser không quan tâm upstream dùng Servlet hay Reactor Netty.

Tuy nhiên Java API tương ứng có khác biệt:

| Chức năng | Spring MVC / Servlet | Spring WebFlux / Reactive |
|---|---|---|
| Security builder | `HttpSecurity` | `ServerHttpSecurity` |
| Security chain | `SecurityFilterChain` | `SecurityWebFilterChain` |
| CSRF filter | `CsrfFilter` | `CsrfWebFilter` |
| Repository theo phiên | `HttpSessionCsrfTokenRepository` | `WebSessionServerCsrfTokenRepository` |
| Phiên server | `HttpSession` | `WebSession` |
| Cookie phiên phổ biến | `JSESSIONID` | Tên do `WebSessionIdResolver` cung cấp, thường là `SESSION` |
| HTTP context | `HttpServletRequest` | `ServerWebExchange` |
| Token trong request | `CsrfToken` | Thường `Mono<CsrfToken>` trên exchange attribute |
| Test | `MockMvc` | `WebTestClient` |

**Không** chuyển `HttpSessionCsrfTokenRepository` sang cấu hình WebFlux; sử dụng các lớp dành cho reactive stack.

### 12.2. SecurityWebFilterChain: giữ CSRF theo WebSession

Một cấu hình minh họa cho WebFlux nhận `/api/**` và session cookie:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.csrf.WebSessionServerCsrfTokenRepository;
import org.springframework.security.web.server.util.matcher.PathPatternParserServerWebExchangeMatcher;

import reactor.core.publisher.Mono;

@Configuration
@EnableWebFluxSecurity
class SpaReactiveSecurityConfig {

    @Bean
    SecurityWebFilterChain spaApiSecurity(ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth
                .pathMatchers(HttpMethod.GET, "/api/csrf").permitAll()
                .pathMatchers(HttpMethod.POST, "/api/login").permitAll()
                .anyExchange().authenticated()
            )
            .formLogin(form -> form
                .requiresAuthenticationMatcher(
                    new PathPatternParserServerWebExchangeMatcher(
                        "/api/login", HttpMethod.POST))
                .authenticationSuccessHandler((exchange, authentication) -> {
                    exchange.getExchange().getResponse()
                        .setStatusCode(HttpStatus.NO_CONTENT);
                    return Mono.empty();
                })
                .authenticationFailureHandler((exchange, exception) -> {
                    exchange.getExchange().getResponse()
                        .setStatusCode(HttpStatus.UNAUTHORIZED);
                    return Mono.empty();
                })
            )
            .logout(logout -> logout
                .requiresLogout(
                    new PathPatternParserServerWebExchangeMatcher(
                        "/api/logout", HttpMethod.POST))
                .logoutSuccessHandler((exchange, authentication) -> {
                    exchange.getExchange().getResponse()
                        .setStatusCode(HttpStatus.NO_CONTENT);
                    return Mono.empty();
                })
            )
            .csrf(csrf -> csrf.csrfTokenRepository(
                new WebSessionServerCsrfTokenRepository()
            ))
            .build();
    }
}
~~~

**Phạm vi và điều kiện của đoạn mã:**

- Đây là ví dụ **thay thế** cho Servlet, không phải cấu hình đặt cùng ứng dụng Servlet.
- Các API cấu hình matcher/login/logout có thể khác chi tiết theo Spring Security version; kiểm tra chữ ký phương thức trên phiên bản dùng thực tế khi triển khai.
- Nếu dùng form login, endpoint POST phải nhận **form-urlencoded credentials**, trừ khi bạn tự thiết kế authentication converter khác.
- Chưa có user provider/JWT decoder/Identity Provider vì bài tập trung vào **SPA + cookie session**.
- `.pathMatchers("/api/login").permitAll()` không tắt CSRF của POST.
- Default logout handler của Reactive có chính sách dọn security context/WebSession có thể khác Servlet; nếu yêu cầu **hủy toàn bộ WebSession**, cần bổ sung `WebSessionServerLogoutHandler`/handler thích hợp và test sau logout.
- Để API ẩn danh trả JSON `401` thay vì redirect HTML form login, cần cấu hình authentication entry point/response policy tương ứng và kiểm thử. Không giả định một `formLogin()` mặc định xử lý AJAX thất bại theo cùng hợp đồng như custom handler này.

### 12.3. Endpoint CSRF Reactive

Trong WebFlux, CSRF token thường được cung cấp bởi `CsrfWebFilter` dưới dạng publisher trên exchange. Endpoint này chủ động subscribe và trả token qua JSON:

~~~java
import java.util.Map;

import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.security.web.server.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

@RestController
class ReactiveCsrfApiController {

    @GetMapping("/api/csrf")
    Mono<ResponseEntity<Map<String, String>>> csrf(
            ServerWebExchange exchange) {

        Mono<CsrfToken> token =
            exchange.getAttribute(CsrfToken.class.getName());

        return token.map(csrf -> ResponseEntity.ok()
            .cacheControl(CacheControl.noStore())
            .body(Map.of(
                "headerName", csrf.getHeaderName(),
                "parameterName", csrf.getParameterName(),
                "token", csrf.getToken()
            )));
    }
}
~~~

Ví dụ giả định request đã đi qua `CsrfWebFilter` và exchange attribute được cung cấp theo cấu hình/phiên bản đang dùng. Nếu custom request handler không đưa token lên attribute hoặc tích hợp khác cách mặc định, phải sửa endpoint cho phù hợp.

**Không sử dụng `block()` trong controller** chỉ để lấy token. Publisher cần được trả về và subscribe bởi reactive runtime.

### 12.4. Controller API Reactive

~~~java
import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

@Controller
class ReactiveProfileApiController {

    private final ReactiveProfileService profiles;

    ReactiveProfileApiController(ReactiveProfileService profiles) {
        this.profiles = profiles;
    }

    @GetMapping("/api/me")
    @org.springframework.web.bind.annotation.ResponseBody
    Mono<Map<String, String>> me(ServerWebExchange exchange) {
        return exchange.getPrincipal()
            .map(p -> Map.of("username", p.getName()));
    }

    record RenameRequest(String displayName) {}

    @PostMapping("/api/profile")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    @org.springframework.web.bind.annotation.ResponseBody
    Mono<Void> rename(
            ServerWebExchange exchange,
            @RequestBody Mono<RenameRequest> request) {

        return Mono.zip(exchange.getPrincipal(), request)
            .flatMap(tuple -> {
                String name = tuple.getT2().displayName();

                if (name == null || name.isBlank()
                        || name.length() > 80) {
                    return Mono.error(new ResponseStatusException(
                        HttpStatus.BAD_REQUEST, "Tên không hợp lệ"));
                }

                return profiles.renameIfAuthorized(
                    tuple.getT1().getName(), name);
            });
    }
}
~~~

`ReactiveProfileService` là **service giả định** trả `Mono<Void>` và phải kiểm tra quyền, validation, lưu trữ/transaction. Với reactive runtime, không gọi JDBC blocking trực tiếp trên event-loop. Những rule HTTP/CSRF của SPA vẫn như Servlet: GET chỉ đọc; POST có session cookie thì phải mang token hợp lệ.

### 12.5. Cookie WebSession và reverse proxy

Nếu ứng dụng quản lý cookie bằng `CookieWebSessionIdResolver` với phiên bản Spring Framework hỗ trợ `addCookieInitializer`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.server.session.CookieWebSessionIdResolver;
import org.springframework.web.server.session.WebSessionIdResolver;

@Configuration
class SpaWebSessionCookieConfig {

    @Bean
    WebSessionIdResolver webSessionIdResolver() {
        CookieWebSessionIdResolver resolver =
            new CookieWebSessionIdResolver();

        resolver.setCookieName("SESSION");
        resolver.addCookieInitializer(cookie -> cookie
            .path("/")
            .secure(true)
            .httpOnly(true)
            .sameSite("Lax"));

        return resolver;
    }
}
~~~

Các điều kiện giống Servlet: public HTTPS, forwarding headers tin cậy, quan sát `Set-Cookie` thật và xác định xem Spring Session/custom resolver có thay cơ chế phát cookie hay không.

## 13. Session khi chạy nhiều instance

Một triển khai thực tế có thể có:

~~~text
                         +--> Spring node A --+
Browser → Nginx /api/ --|                     |--> Shared session store
                         +--> Spring node B --+
~~~

Nếu repository CSRF lưu token theo phiên nhưng mỗi node dùng session store độc lập, luồng:

~~~text
GET /api/csrf  -> Node A phát token gắn session A
POST /api/...  -> Node B không tìm thấy expected token của session A
=> 403 hoặc mất authentication
~~~

Có hai chiến lược thường dùng:

- **Sticky session:** Load balancer giữ user về cùng node; cần đánh giá khi failover/scale và cookie LB.
- **Shared session store:** Dùng Spring Session/khả năng chia sẻ WebSession phù hợp với stack và hạ tầng, cấu hình TTL, serializer và session invalidation nhất quán.

Không sửa sự cố bằng cách **tắt CSRF**. Cần quan sát node ID, session resolution, repository token, store TTL và cookie Path/Domain.

### 13.1. Session fixation và vòng đời token

Sau login, session ID có thể được đổi theo chính sách chống session fixation; CSRF token đã phát trước login có thể bị invalidated. SPA nên lấy token mới **sau authentication thành công**.

Sau logout, phiên và token trước đó có thể bị dọn. Một request POST đang chạy đồng thời với logout ở tab khác cần được xử lý theo policy transaction/authorization phù hợp, không tin token đã cũ để bỏ xác thực.

### 13.2. Trường hợp reload và nhiều tab

- SPA reload mất CSRF state trong memory → gọi lại `GET /api/csrf`.
- Nhiều tab chia sẻ cookie session, nhưng **không nhất thiết chia sẻ JS memory**; mỗi tab có thể có token masked được cấp riêng mà cùng hợp lệ theo repository.
- Tab A logout, tab B còn UI cũ → request tiếp theo có thể `401`/`403`; hướng dẫn đăng nhập lại, không tự động dùng session/token cũ.
- Nếu dùng cookie CSRF repository và client đọc qua JS, xem cookie scope, raw/masked, phiên và chính sách dọn cookie sau logout.

## 14. Kiểm thử Servlet bằng MockMvc

### 14.1. Ma trận API session + CSRF

| ID | Kịch bản | Request | Kỳ vọng |
|---|---|---|---|
| **SPA-01** | GET cấp CSRF pre-login | `GET /api/csrf` | Trả JSON `headerName`/`token` và không cache |
| **SPA-02** | API cần login | `GET /api/me` không session | `401` theo cấu hình entry point |
| **SPA-03** | POST có session và token đúng | `POST /api/profile` với header token | Qua CSRF, cập nhật nếu đủ quyền |
| **SPA-04** | POST có session nhưng thiếu token | `POST /api/profile` không header CSRF | `403` theo policy, không cập nhật |
| **SPA-05** | POST có session với token sai | `POST /api/profile` với header giả | `403`, không cập nhật |
| **SPA-06** | Login không token | `POST /api/login` có credentials | Không tạo authenticated session |
| **SPA-07** | Login có token | Pre-auth session + token đúng | Qua CSRF; success/failure phụ thuộc credentials |
| **SPA-08** | Sau login | GET token mới rồi POST | Token mới đúng phiên hoạt động |
| **SPA-09** | Logout thiếu token | `POST /api/logout` | Bị chặn; không logout |
| **SPA-10** | Logout token hợp lệ | `POST /api/logout` | Dọn auth theo policy |
| **SPA-11** | GET có query gây cập nhật | `GET /api/profile?displayName=...` | Không làm thay đổi dữ liệu |
| **SPA-12** | Token thuộc phiên B | Cookie A + token B | Bị chặn với synchronizer token theo phiên |
| **SPA-13** | CSRF header bị proxy bỏ | POST qua proxy, header mất | Bị chặn; tìm lỗi proxy thay vì tắt CSRF |
| **SPA-14** | API route không tồn tại | `GET /api/not-found` | Backend trả lỗi API đúng, không trả `index.html` 200 |
| **SPA-15** | Browser + HTTPS proxy | GET/POST theo public URL | Cookie, Location, forwarded scheme/host chính xác |

### 14.2. MockMvc: đúng, thiếu, sai

Giả định ứng dụng có `POST /api/profile` như mục 8 và `spring-security-test`:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SpaServletCsrfTests {

    @Autowired MockMvc mvc;

    @Test
    void validTokenInHeaderPassesCsrf() throws Exception {
        mvc.perform(post("/api/profile")
                .with(user("alice"))
                .with(csrf().asHeader())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"displayName\":\"Alice New\"}"))
            .andExpect(status().isNoContent());
    }

    @Test
    void missingTokenIsRejected() throws Exception {
        mvc.perform(post("/api/profile")
                .with(user("alice"))
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"displayName\":\"Wrong\"}"))
            .andExpect(status().isForbidden());
    }

    @Test
    void invalidTokenIsRejected() throws Exception {
        mvc.perform(post("/api/profile")
                .with(user("alice"))
                .with(csrf().asHeader().useInvalidToken())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"displayName\":\"Wrong\"}"))
            .andExpect(status().isForbidden());
    }
}
~~~

Các test này dùng **mock authentication** và token helper. Chúng không chứng minh browser **thật** đã nhận cookie, proxy đã giữ header, hoặc endpoint JS nhận token masked có tương thích. Cần thêm round-trip test.

### 14.3. MockMvc: GET token, giữ session, POST dùng token thật

~~~java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SpaServletRoundTripTests {

    @Autowired MockMvc mvc;
    @Autowired ObjectMapper mapper;

    @Test
    void issuedTokenInSameSessionPasses() throws Exception {
        MvcResult issue = mvc.perform(
                get("/api/csrf").with(user("alice")))
            .andExpect(status().isOk())
            .andReturn();

        JsonNode csrfJson = mapper.readTree(
            issue.getResponse().getContentAsString());

        String header = csrfJson.get("headerName").asText();
        String token = csrfJson.get("token").asText();
        MockHttpSession session = (MockHttpSession)
            issue.getRequest().getSession(false);

        mvc.perform(post("/api/profile")
                .session(session)
                .with(user("alice"))
                .header(header, token)
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"displayName\":\"Alice New\"}"))
            .andExpect(status().isNoContent());

        mvc.perform(post("/api/profile")
                .session(session)
                .with(user("alice"))
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"displayName\":\"Should Not Save\"}"))
            .andExpect(status().isForbidden());
    }
}
~~~

Điều kiện:

- Endpoint `GET /api/csrf` phải thật sự truy cập token và lưu vào session; test nên assert session khác null, không tùy tiện tạo session mới khi POST.
- Với session-backed repository và XOR handler, dùng **token do response cấp**, không dùng raw token tự lấy từ nội bộ.
- Mock principal vẫn khác luồng login qua browser; với production-like test, tạo session xác thực thật và dùng cookie session do server cấp.
- Sau negative case, **kiểm tra ProfileService/database không có thay đổi** ngoài ý muốn.

### 14.4. Test đường login và logout

Có thể tách:

~~~text
1. GET /api/csrf  -> nhận token pre-login + session cookie
2. POST /api/login (form-urlencoded, token đúng) -> 204 và authenticated session
3. GET /api/csrf sau login -> token hiện hành
4. GET /api/me -> đúng user
5. POST /api/logout không token -> từ chối; vẫn được xác thực
6. POST /api/logout có token -> 204
7. GET /api/me với cookie cũ -> không còn được xác thực
~~~

Nếu dùng `with(user())` suốt các request thì test **không chứng minh** login/logout thật; `with(user())` tự cấp principal dù session đã logout. Đối với luồng trên, hãy dùng form login thật với user fixture, cookie jar/session API và kiểm tra hậu logout bằng request **không chèn mock authentication**.

## 15. Kiểm thử Reactive bằng WebTestClient

Ví dụ cho WebFlux đã có `POST /api/profile` trả `204` khi input hợp lệ:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class SpaReactiveCsrfTests {

    @Autowired ApplicationContext context;

    WebTestClient client() {
        return WebTestClient.bindToApplicationContext(context)
            .apply(springSecurity())
            .build();
    }

    @Test
    void validTokenAllowsUpdate() {
        client().mutateWith(mockUser("alice"))
            .mutateWith(csrf())
            .post().uri("/api/profile")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("{\"displayName\":\"Alice New\"}")
            .exchange()
            .expectStatus().isNoContent();
    }

    @Test
    void missingTokenIsRejected() {
        client().mutateWith(mockUser("alice"))
            .post().uri("/api/profile")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("{\"displayName\":\"Wrong\"}")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void wrongTokenIsRejected() {
        client().mutateWith(mockUser("alice"))
            .post().uri("/api/profile")
            .header("X-CSRF-TOKEN", "invalid-token")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("{\"displayName\":\"Wrong\"}")
            .exchange()
            .expectStatus().isForbidden();
    }
}
~~~

`mutateWith(csrf())` mô phỏng token phù hợp trong reactive security test. Để kiểm tra flow thật:

- `GET /api/csrf` để subscribe token và ghi nhận cookie WebSession;
- `POST /api/profile` với **cùng WebSession cookie** và header token;
- thử thiếu/sai/token session khác;
- kiểm tra database/state sau từng request;
- kiểm tra response headers qua proxy thật bằng browser E2E.

Một `WebTestClient` bind application context không phải browser và không tự thực thi SameSite/CORS hoặc lưu toàn bộ cookie như một trình duyệt. Test giữ cookie phải **cố ý quản lý cookie jar/session** hoặc dùng client chạy qua server thật.

## 16. Browser E2E: kiểm tra chính origin công khai, không chỉ test backend

Một ứng dụng có thể chạy hoàn hảo khi gọi trực tiếp `http://localhost:8080/api/profile` nhưng thất bại qua `https://app.example.com/api/profile` do proxy sửa path/header, cookie Secure/SameSite, cache hoặc redirect.

Vì vậy phải kiểm thử **qua public URL**, dưới những browser mà sản phẩm hỗ trợ.

### 16.1. Kịch bản “một origin thật”

Sử dụng môi trường thử nghiệm được phép, ví dụ `https://app.example.test` có DNS/hosts và HTTPS certificate hợp lệ:

1. **Mở SPA:** Truy cập `https://app.example.test/`. Network cho thấy `index.html` và assets tải cùng origin, không bị CSP/MIME chặn.
2. **Mở deep link:** Truy cập thẳng `/settings` hoặc reload trang đó. Reverse proxy trả `index.html`, router SPA hiển thị đúng trang.
3. **Kiểm tra API 404:** Gọi `GET /api/unknown-path`. Backend trả lỗi API, **không** trả HTML SPA status 200.
4. **Lấy CSRF trước login:** Gọi `GET /api/csrf`. Kiểm tra JSON `headerName`/`token`, `Cache-Control: no-store` và cookie session nếu được phát.
5. **Login qua POST:** Gửi form-urlencoded username/password test cùng CSRF token. Quan sát POST thực sự đến `/api/login`, không bị proxy rewrite thành `/login` hoặc trả `index.html`.
6. **Kiểm tra cookie:** Xem `Set-Cookie` sau login và `Cookie` trên request tiếp theo; xác minh `Secure`, `HttpOnly`, `SameSite`, `Path` và `Domain` hợp lý.
7. **Lấy token sau login:** GET `/api/csrf` bằng cùng browser context; không tái sử dụng token cũ nếu authentication đã làm nó mất hiệu lực.
8. **GET current user:** `GET /api/me` trả user đang đăng nhập. Không tự suy luận từ cookie có tồn tại.
9. **POST hợp lệ:** `POST /api/profile` với header/value token hiện hành, JSON hợp lệ; xác nhận thay đổi đúng một lần và response `204`.
10. **POST thiếu token:** Gửi cùng session cookie nhưng không có header CSRF. Xác nhận server từ chối, **dữ liệu không đổi**.
11. **POST token sai:** Gửi token giả hoặc của session B. Xác nhận bị từ chối và không có side effect.
12. **Logout qua POST:** Gửi `POST /api/logout` có token; sau đó GET `/api/me` phải không còn authenticated session.
13. **Mở tab cũ:** Kiểm tra token/session cũ không được chấp nhận cho thao tác ghi.
14. **Kiểm tra assets/headers:** Xem CSP trên `index.html`, HTTPS/HSTS theo chính sách, Content-Type và cache headers ở từng loại response.

**Không dùng dữ liệu production hay tài khoản thật để thử các ca gây tác động.** Nên có test fixtures, khả năng reset dữ liệu và ghi lại bằng chứng HTTP không chứa bí mật.

### 16.2. Kiểm tra hai browser contexts và hai token

Với synchronizer token theo session:

~~~text
Browser Context A (cookie jar A):
    GET /api/csrf -> token A
    POST /api/profile với cookie A + token A -> hợp lệ nếu có auth

Browser Context B (cookie jar B):
    GET /api/csrf -> token B

Browser Context A:
    POST /api/profile với cookie A + token B -> bị từ chối

Sau negative case:
    database/profile và event nghiệp vụ không đổi.
~~~

Không dùng **hai tab chung một browser context** để giả lập hai session: chúng thường chia sẻ cookie. Với session repository, cần tách cookie jar thật sự.

### 16.3. Kiểm tra cross-site và subdomain cùng site

Bên cạnh cùng origin, nên có các test origin:

~~~text
https://app.example.test          SPA và API cùng origin
https://blog.example.test         Khác origin, có thể same-site
https://attacker.other.test       Cross-site
~~~

- Từ blog gửi một form POST đến `app.example.test/api/profile`: cookie `SameSite=Lax` hoặc `Strict` có thể đi cùng vì **same-site**. **Không có token đúng** phải bị CSRF filter chặn.
- Từ attacker ở site khác mở **top-level GET** đến app: cookie `Lax` có thể được gửi; GET không được thực hiện hành động ghi.
- Từ attacker gửi form POST cross-site: browser có thể loại cookie theo SameSite, nhưng đó là **lớp cookie**, không chứng minh CSRF filter đủ tốt nếu request có credential được gửi bằng ngữ cảnh khác.
- Từ origin khác dùng JS fetch: phân biệt lỗi CORS preflight/response với POST server trả `403`.

**Đặc biệt:** cURL/Postman có thể tự gửi header `Cookie` ngay cả khi browser thật sẽ chặn; dùng chúng để kiểm tra **server**, không làm bằng chứng trực tiếp cho SameSite browser.

### 16.4. Hai nhóm kiểm thử độc lập

| Nhóm | Câu hỏi | Công cụ phù hợp |
|---|---|---|
| **Security server** | CSRF token thiếu/sai có bị từ chối không? | MockMvc, WebTestClient, integration tests |
| **Browser + reverse proxy** | Cookie/header/method/path có đến backend đúng qua origin công khai không? | Browser DevTools, Playwright/Cypress hoặc browser automation được phép |
| **Nghiệp vụ** | Request bị từ chối có thực sự không ghi dữ liệu không? | Database assertions, fake service, event recorder |
| **Session lifecycle** | Login/logout/timeout/scale có giữ đúng user/token không? | End-to-end nhiều request, cookie jar và session store |
| **Header/document policy** | CSP/HSTS có trên **HTML** thực tế không? | Network response headers ở index.html và các deep-link |
| **CORS/Fetch Metadata** | Request được browser phân loại same-origin/same-site/cross-site thế nào? | Browser Network, Origin và Sec-Fetch-* khi được gửi |

Nếu test chỉ gọi backend trực tiếp, sẽ bỏ qua một nửa đường đi quan trọng của bài này: **TLS edge → proxy → cookie → security chain → API**.

## 17. Bảng chẩn đoán lỗi SPA qua reverse proxy

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| SPA tải được nhưng `/api/me` trả HTML thay vì JSON | Proxy fallback sang `index.html` hoặc login redirect mặc định | Xem Network response body/content-type; tách `/api/**` khỏi fallback, cấu hình API entry point |
| API trả `404` chỉ sau deploy proxy | `proxy_pass` rewrite bỏ prefix `/api` hoặc backend mapping khác | So request URI public và URI backend nhận; kiểm tra dấu gạch chéo của `proxy_pass` |
| `GET /api/csrf` chạy nhưng POST luôn `403` | Cookie/session không được giữ, header CSRF bị mất hoặc token không đúng dạng | So GET/POST cookies, headerName/token, session ID scope, request handler |
| Login có `204` nhưng `/api/me` là `401` | Cookie không được lưu/gửi, session/auth context chưa persist hoặc node khác | Kiểm tra Set-Cookie/Cookie, domain/path, Session Store, LB |
| Browser báo CORS mặc dù thiết kế cùng origin | JS đang gọi `api.example.com` hoặc `localhost:8080` trực tiếp | Kiểm tra URL Request trong Network, sửa base URL về `/api/**` |
| `fetch` từ SPA không gửi cookie | Cookie Path/Domain/Secure, session expired, credentials mode hoặc third-party policy | Kiểm tra HTTP Cookie header, public scheme và host |
| Login/redirect trỏ về `http://...` hoặc hostname nội bộ | Forwarded proto/host sai hoặc backend tin header không đúng | Kiểm tra proxy trust, `X-Forwarded-*`, URL builder và redirect |
| Proxy trả `502 Bad Gateway` | Upstream không reachable, sai port, timeout/TLS nội bộ | Kiểm tra health của upstream và proxy logs đã khử bí mật |
| POST JSON trả `415` hoặc `400` | Body/content type/controller contract không khớp | Xem Content-Type, converter, validation và payload |
| `GET /settings` được, reload `/settings` trả `404` | Chưa có SPA deep-link fallback | Dùng `try_files ... /index.html` cho route frontend, không áp cho API |
| Asset JS lỗi MIME, browser từ chối execute | Fallback trả HTML cho file JS không tồn tại | Cho `/assets/**` trả `404` khi thiếu; đúng Content-Type và nosniff |
| Header CSP xuất hiện trên API nhưng không trên SPA | Spring chỉ xử lý `/api/**`, index.html do Nginx trả | Gắn CSP ở bên tạo response HTML và test deep-link |
| Cookie có `SameSite=None` nhưng bị chặn | Thiếu `Secure`/HTTPS hoặc browser chặn third-party cookie | Kiểm tra browser cookie warnings, xem lại sự cần thiết của None |
| Login/logout hoạt động node A nhưng node B lỗi | Session store không chia sẻ, LB không sticky/TTL khác | Kiểm tra session affinity/store và expected CSRF token |
| CSRF fail ngẫu nhiên sau login/logout | Token invalidated nhưng SPA giữ token cũ | GET `/api/csrf` sau xác thực đổi, không retry POST mù quáng |
| Request GET làm cập nhật dữ liệu | Backend dùng GET như method ghi; CSRF thường bỏ qua GET | Sửa sang POST/PUT/PATCH/DELETE; kiểm tra side effects |
| Browser `403` nhưng MockMvc `with(csrf())` pass | Test helper không mô phỏng token render, proxy, cookie thật | Kiểm thử GET token → giữ session → POST trên public URL |
| Header `X-CSRF-TOKEN` không tới Spring | Rule WAF/proxy gỡ hoặc đổi header | Xem header phía browser và backend; sửa allowlist/forwarding |
| Cookie session bị ghi nhận trong log | Proxy hoặc app logging quá chi tiết | Che `Cookie`, `Set-Cookie`, `Authorization`, CSRF header và dữ liệu nhạy cảm |
| API `POST /api/logout` bị `302` tới HTML | Logout success handler/entry point chưa khớp SPA | Thống nhất JSON/status contract và kiểm thử sau logout |
| Một trang SPA sau deploy vẫn dùng JS cũ | `index.html` bị cache quá lâu, bundle fingerprint không đồng bộ | Kiểm tra cache index/no-cache và assets immutable có version |

### 17.1. Phân biệt 401, 403 và 404

- **`401 Unauthorized`:** Với API thường biểu thị chưa xác thực hoặc credential không được chấp nhận. Nếu security chain dùng form login entry point, backend có thể trả **redirect HTML** thay vì 401.
- **`403 Forbidden`:** Có thể là CSRF token thiếu/sai **hoặc** người dùng thiếu quyền. Đừng kết luận mọi 403 là CSRF.
- **`404 Not Found`:** Có thể do backend mapping sai hoặc reverse proxy rewrite; nếu response lại chứa `index.html` với status 200, đó là lỗi routing/fallback.
- **`405 Method Not Allowed`:** HTTP method sai; `GET /api/login` có thể không hợp đồng nếu chỉ có POST login.
- **`502/504`:** Thường là lỗi proxy/upstream/network/timeout, không phải CSRF filter.
- **CORS error:** Có thể browser không cho JS đọc response; kiểm tra request có thực sự đến backend hay không.

Để debug, ghi nhận method, request URI public/upstream, security chain, status, cookie **có hay không**, tên CSRF header/field và exception class. **Không ghi nguyên vẹn session ID, access token, refresh token hoặc CSRF token vào log**.

## 18. Những lựa chọn kiến trúc cần cân nhắc

### 18.1. Session cookie hay Bearer token?

Bài này chọn **session cookie**. Nhưng một SPA có thể thay bằng access token Bearer do JavaScript chủ động gắn.

| Kiến trúc | Credential của browser → Spring | CSRF cần xem như thế nào? |
|---|---|---|
| SPA same-origin + `HttpSession` cookie | Browser tự gửi `JSESSIONID` | **Giữ CSRF** cho request ghi |
| SPA same-origin + JWT trong cookie | Browser tự gửi cookie JWT | **Vẫn cần đánh giá CSRF**, dù backend stateless |
| SPA same-origin + Bearer-only API | JS chủ động gắn `Authorization: Bearer`, không có cookie fallback | CSRF kiểu cookie thường không trọng tâm nếu đã **chứng minh bearer-only** |
| SPA → BFF cùng origin | Browser gửi cookie BFF | **Giữ CSRF tại BFF** |
| SPA Bearer access token + refresh cookie | API: header chủ động; refresh: cookie tự gửi | **Đánh giá riêng refresh/login/logout** |

Không bỏ CSRF chỉ vì ứng dụng là “SPA”, “REST” hoặc “JWT”. Phải xét **credential thực sự được backend chấp nhận** và cách browser gửi.

### 18.2. Có cần tách frontend và backend thành subdomain?

Dùng `https://app.example.com` và `https://api.example.com` là một phương án khác, có thể phù hợp với một số hạ tầng. Nhưng nó đòi hỏi xét **cross-origin fetch**, CORS, credentials mode, cookie scope và CSRF token transport.

**Same-origin qua proxy** thường đơn giản hóa tương tác browser/API khi mọi request đã phục vụ dưới một tên miền public. Đó là một lựa chọn tích hợp, không tự là “hệ thống bảo mật tuyệt đối hơn” nếu proxy, SPA hoặc backend bị cấu hình sai.

### 18.3. Có cần cho SPA tải token từ cookie thay vì JSON?

- **Session-backed JSON endpoint:** Dễ giữ session cookie HttpOnly và dùng token do server render cho header; cần một GET token trong lifecycle.
- **Cookie token repository:** Có thể thuận tiện cho một số client framework tự đọc `XSRF-TOKEN`, nhưng phải kiểm soát cookie scope và handler raw/masked.
- **Server-rendered HTML chứa token:** Phù hợp nếu backend thực sự render shell HTML; nếu Nginx phục vụ file tĩnh, không có token do Spring đưa vào shell mặc định.

Chọn một mô hình **nhất quán** và test round-trip; không trộn repository/handler tùy tiện.

## 19. Checklist sẵn sàng triển khai

| Kiểm tra | Tiêu chí thành công |
|---|---|
| **Public origin** | SPA và `/api/**` cùng scheme/host/port trong Network |
| **HTTPS** | Browser chỉ dùng HTTPS; HSTS theo chính sách đã xác nhận |
| **Proxy routing** | `/assets/**` trả asset thật; `/api/**` vào backend; SPA deep-link có fallback |
| **API không bị fallback** | Backend 401/403/404 không biến thành `index.html` 200 |
| **Forwarded headers** | Host/scheme/port public đúng, chỉ tin proxy |
| **Cookie** | `HttpOnly`, `Secure`, `SameSite`, host/path phù hợp và browser thực gửi |
| **CSRF endpoint** | `GET /api/csrf` dùng token đúng repository/handler, no-store |
| **CSRF unsafe methods** | POST/PUT/PATCH/DELETE dùng credential cookie bị kiểm tra token |
| **Login** | `POST /api/login` có CSRF pre-auth, thành công trả response SPA hiểu được |
| **Sau login** | SPA nhận token mới nếu đã invalidated; `/api/me` xác nhận user |
| **Logout** | POST có token; session cũ không còn authenticated |
| **Authentication/authorization** | Mọi endpoint ghi kiểm tra quyền server-side |
| **XSS/CSP** | DOM sink an toàn, CSP trên HTML SPA thực, quản lý script |
| **Cache** | `index.html` có revalidation; assets fingerprint; API token/auth không cache |
| **Multi-node** | Session/CSRF store nhất quán khi LB chuyển node |
| **Observability** | Log che Cookie/Authorization/CSRF/PII |
| **Testing** | Token đúng/thiếu/sai; wrong session; login/logout; proxy E2E; no-side-effects |
| **Browser support** | Kiểm tra SameSite/third-party cookie khi tích hợp ngoài site |

## 20. Câu hỏi tự đánh giá

**Câu 1.** SPA chạy tại `https://app.example.com`, Nginx forward `/api/**` tới `http://spring-service:8080`. Browser có xem request `fetch("/api/me")` là cross-origin không?

**Đáp án:** Không. Browser gọi `https://app.example.com/api/me` cùng origin với trang; kết nối proxy–upstream không phải request cross-origin từ browser.

**Câu 2.** API và SPA same-origin đã tránh CORS, vậy có thể tắt CSRF với POST dựa trên `JSESSIONID` không?

**Đáp án:** Không. Browser tự gửi cookie phiên khi điều kiện cookie cho phép; một website ngoài vẫn có thể kích hoạt một số request. CSRF token là lớp kiểm tra độc lập với CORS.

**Câu 3.** Vì sao phải gọi `GET /api/csrf` khi `index.html` được Nginx phục vụ tĩnh?

**Đáp án:** Nginx phục vụ tệp HTML tĩnh không nhất thiết truy cập CSRF repository của Spring. Token có thể deferred và chưa được phát; SPA cần kênh hợp lệ để nhận token trước POST login hoặc thao tác ghi.

**Câu 4.** Token GET trước login hoạt động, nhưng POST đầu tiên sau login trả `403`. Kiểm tra điều gì?

**Đáp án:** Authentication có thể đổi phiên và làm token cũ mất hiệu lực. SPA cần lấy token mới sau login; đồng thời kiểm tra cookie, raw/masked handler, path proxy và header CSRF.

**Câu 5.** Tại sao `proxy_pass http://spring_backend/;` có thể khác `proxy_pass http://spring_backend;` trong `location /api/`?

**Đáp án:** Bản có phần URI `/` có thể thay prefix `/api/`, làm path backend thay đổi. Phải thống nhất hợp đồng URL và kiểm chứng request URI thực tế.

**Câu 6.** Nginx trả `index.html` với CSP, nhưng URL `/settings` có CSP còn `/api/me` không có. Đâu là điểm cần kiểm tra?

**Đáp án:** CSP bảo vệ trang HTML phải có trên response SPA mà browser tải; các response API do backend phát có security-header policy riêng. Cần kiểm tra các header theo nguồn tạo response, không giả định Spring thêm header cho file Nginx trả.

**Câu 7.** Cookie `JSESSIONID` là HttpOnly. JavaScript có cần đổi nó thành `HttpOnly=false` để gọi API không?

**Đáp án:** Không. Browser tự gắn cookie vào `fetch` same-origin phù hợp; SPA lấy CSRF token qua JSON endpoint hoặc kênh thiết kế riêng, không cần đọc session ID.

**Câu 8.** MockMvc `with(csrf().asHeader())` pass nhưng request từ SPA qua proxy bị `403`. Vì sao?

**Đáp án:** Helper test đã cung cấp token hợp lệ trong môi trường server, nhưng E2E có thể mất cookie, proxy bỏ header, token masked/raw không tương thích hoặc dùng token cũ. Phải kiểm tra từng hop từ browser qua proxy.

**Câu 9.** Hai tab cùng browser đang mở SPA; tab A logout, tab B submit form cũ bị từ chối. Có nên tắt CSRF cho các form cũ?

**Đáp án:** Không. Session/token cũ có thể không còn hợp lệ; yêu cầu tab B làm mới trạng thái và đăng nhập lại nếu cần. Tránh cho request từ phiên cũ đi qua.

**Câu 10.** API không dùng session cookie mà chỉ nhận Bearer header do JS đặt. Đánh giá CSRF có thể khác không?

**Đáp án:** Có, nếu chứng minh API thực sự chỉ chấp nhận credential không được browser tự gửi và không có fallback cookie/Basic/BFF. Nhưng đó là quyết định dựa trên luồng xác thực, không chỉ vì “same-origin” hay “SPA”.

## Kết luận

**SPA cùng origin qua reverse proxy** là mô hình triển khai trong đó browser chỉ thấy một public origin cho **HTML/assets và API**, còn reverse proxy định tuyến `/`, `/assets/**` tới tệp SPA và `/api/**` tới Spring backend. Nhờ vậy, phần lớn `fetch("/api/...")` cùng origin **không cần xử lý CORS phức tạp**, nhưng tính same-origin **không thay thế bảo vệ CSRF** khi browser tự gửi session cookie.

Một tích hợp đúng cần đồng bộ: **cookie phiên `Secure; HttpOnly; SameSite`**, endpoint cấp CSRF token `GET /api/csrf`, header `X-CSRF-TOKEN` trên unsafe request, làm mới token sau login/logout, API entry point phù hợp SPA, đúng public URL qua proxy, cache policy riêng cho token/HTML/assets và những lớp CSP/HSTS/security headers ở **nơi thực sự phát response**.

Với **Spring Security Servlet**, các thành phần chính là `HttpSecurity`, `SecurityFilterChain`, `CsrfFilter` và `HttpSessionCsrfTokenRepository`. Với **Reactive/WebFlux**, chúng là `ServerHttpSecurity`, `SecurityWebFilterChain`, `CsrfWebFilter` và `WebSessionServerCsrfTokenRepository`. Dù triển khai khác nhau, cả hai phải kiểm thử **token đúng/thiếu/sai, cookie/session, login/logout, no-side-effects và hành vi proxy trên public origin**.

Đây là một bài thực hành tích hợp điển hình cho module **SPRING_SECURITY_HTTP_PROTECTION**, nơi CSRF, CORS, security headers, CSP, HSTS, HTTP firewall và bảo vệ session phải bổ trợ nhau thay vì được cấu hình tách rời.

## Tài liệu tham khảo

- [Spring Security — CSRF Protection (Servlet)](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html): token repository, deferred token, XOR masking và SPA.
- [Spring Security — CSRF Protection (WebFlux)](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html): CSRF web filter và WebSession token.
- [Spring Security — Servlet Form Login](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/form.html): form login và authentication flow.
- [Spring Security — Reactive Form Login](https://docs.spring.io/spring-security/reference/reactive/authentication/passwords/form.html): form authentication trong WebFlux.
- [Spring Security — HTTP Security Headers](https://docs.spring.io/spring-security/reference/servlet/exploits/headers.html): CSP, HSTS và các header mặc định.
- [Spring Framework — CookieWebSessionIdResolver](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/server/session/CookieWebSessionIdResolver.html): session cookie cho WebFlux.
- [MDN — Same-origin policy](https://developer.mozilla.org/en-US/docs/Web/Security/Same-origin_policy): origin, quyền đọc response và ranh giới giữa các trang.
- [MDN — Request credentials](https://developer.mozilla.org/en-US/docs/Web/API/Request/credentials): `fetch` credentials modes.
- [MDN — Set-Cookie](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie): cookie Secure/HttpOnly/SameSite/Domain/Path.
- [NGINX — ngx_http_proxy_module](https://nginx.org/en/docs/http/ngx_http_proxy_module.html): `proxy_pass`, đường dẫn URI và forwarding headers.
- [OWASP — Cross-Site Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html): threat model và phòng vệ CSRF nhiều lớp.
