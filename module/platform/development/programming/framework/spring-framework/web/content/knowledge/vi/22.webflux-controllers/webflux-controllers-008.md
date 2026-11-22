# Cấu hình CORS, tài nguyên tĩnh và HTTP caching trong Spring WebFlux

## 1. Mục tiêu và ba vấn đề HTTP thường đi cùng nhau

Một ứng dụng Spring WebFlux có thể đồng thời phục vụ **API JSON**, **website/tài nguyên tĩnh** và **browser frontend ở origin khác**. Ba cơ chế thường bị nhầm vì đều liên quan đến response headers:

1. **CORS (Cross-Origin Resource Sharing):** browser có được phép cho JavaScript ở origin A đọc response từ origin B không?
2. **Static resources:** URL nào được ánh xạ tới file CSS/JS/image/HTML, file được tìm theo thứ tự nào, và tài nguyên được gửi bằng HTTP ra sao?
3. **HTTP caching:** cache trình duyệt/CDN có được lưu hoặc dùng lại response không, trong bao lâu, và khi nào sử dụng `ETag`/`Last-Modified` để kiểm tra lại?

Một API có thể có **CORS đúng nhưng caching sai**, hoặc **cache đúng nhưng browser vẫn từ chối đọc vì CORS**. Ví dụ:

~~~http
GET /api/public/catalog HTTP/1.1
Origin: https://app.example.test
Accept: application/json
~~~

Server có thể trả:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.test
Vary: Origin
Cache-Control: public, max-age=60
ETag: "catalog-2026-a"
Content-Type: application/json

{"edition":"2026-A","subjects":["WebFlux","HTTP"]}
~~~

`Access-Control-Allow-Origin` điều khiển quyền đọc qua **CORS trong browser**. `Vary: Origin` cho cache biết representation/response headers có thể thay đổi theo origin. `Cache-Control` quyết định cách dùng cache. `ETag` giúp client gửi conditional request và nhận 304 nếu response chưa đổi.

Bài tập trung **Spring WebFlux reactive stack**, không phải Spring MVC Servlet. Ví dụ đầy đủ dùng **Java 17**, **Spring Boot 3.3.5** và `spring-boot-starter-webflux`; không thêm `spring-boot-starter-web`. Một số trang tài liệu Spring “current” là Framework 7, trong khi Boot 3.3.5 quản lý Spring Framework 6.1.x; các code mẫu chỉ dùng API phù hợp Spring 6.1.

### Sau bài này bạn sẽ

- Giải thích origin, same-origin policy và CORS preflight.
- Phân biệt simple CORS requests, non-simple requests, credentials, preflight và actual response.
- Cấu hình `@CrossOrigin`, `WebFluxConfigurer.addCorsMappings`, `CorsWebFilter` khi phù hợp; không mở CORS tùy tiện.
- Biết CORS phải được phối hợp với **Spring Security WebFlux**, không thay authentication/authorization/CSRF.
- Phục vụ file từ `classpath:/static/` và tùy chỉnh `ResourceHandlerRegistry`.
- Đặt Cache-Control cho tài nguyên tĩnh, tránh cache HTML entrypoint quá lâu trong khi hashed JS/CSS có thể cache dài.
- Dùng `ResponseEntity.cacheControl(...)`, `eTag(...)`, `lastModified(...)` và conditional GET trả 304.
- Phân biệt `Cache-Control: no-cache`, `no-store`, `private`, `public`, `max-age`, `s-maxage`, `immutable`.
- Nhận biết sự khác nhau giữa `Access-Control-Max-Age` với `Cache-Control: max-age`.
- Viết kiểm thử WebTestClient cho preflight, origin bị từ chối, 200/304, file tĩnh, private caching.
- Chẩn đoán các lỗi thường gặp qua browser Network, curl, CDN, proxy và headers.

## 2. Nền tảng: Origin và same-origin policy

Một **origin** được xác định từ **scheme + host + port**. Ví dụ:

| URL | Origin | So với `https://app.example.test` |
| --- | --- | --- |
| `https://app.example.test/dashboard` | `https://app.example.test` | Cùng origin |
| `https://app.example.test:443/page` | Default HTTPS 443 | Cùng origin |
| `http://app.example.test/page` | HTTP thay vì HTTPS | Khác origin |
| `https://api.example.test/v1` | Subdomain khác | Khác origin |
| `https://app.example.test:8443` | Port khác | Khác origin |
| `https://cdn.example.test/app.js` | Host khác | Khác origin |

Browser thực thi **same-origin policy** để giới hạn JavaScript truy cập response từ origin khác. **CORS là giao thức để server nói với browser rằng một origin cụ thể được phép đọc response**, không phải phương thức xác thực user.

Ví dụ frontend:

~~~javascript
const result = await fetch(
  "https://api.example.test/api/public/catalog"
);
const data = await result.json();
~~~

Nếu trang đang chạy ở `https://app.example.test` thì đây là cross-origin fetch. Browser có thể gửi `Origin: https://app.example.test`. Server phải cung cấp CORS response headers phù hợp thì JavaScript mới đọc được JSON.

**CORS không ngăn tất cả HTTP requests được gửi đến server.** curl, Postman và server-to-server HTTP clients thường không áp dụng cùng kiểm tra CORS của browser. Nếu một endpoint DELETE không có authorization, việc CORS từ chối frontend độc hại **không làm endpoint an toàn** trước một HTTP client trực tiếp.

### 2.1. Origin không phải site, và khác URL path

Cookie SameSite dùng khái niệm **site** (schemeful site) chứ không hoàn toàn trùng origin. Hai subdomains có thể là same-site nhưng cross-origin. CORS quyết định browser JS có được đọc cross-origin response không; SameSite quyết định một phần cách cookie được gửi; CSRF chống việc lạm dụng authenticated browser requests. **Không thay thế ba cơ chế này cho nhau.**

### 2.2. Đừng nhầm CORS với CSP

- CORS là hợp đồng **resource server → browser** về quyền truy cập cross-origin.
- Content Security Policy (CSP) như `connect-src`, `script-src` là chính sách **document/app frontend** về nguồn nào được load/connect.
- Browser có thể yêu cầu cả hai đều phù hợp. `Access-Control-Allow-Origin` hợp lệ không làm `connect-src 'self'` tự cho phép gọi API ngoài origin.
- Các headers `Cross-Origin-Resource-Policy` (CORP) và `Cross-Origin-Embedder-Policy` (COEP) phục vụ use cases bảo vệ embedding/cross-origin isolation khác; chúng không phải alias của CORS.

## 3. Một CORS request thông thường diễn ra thế nào?

Một GET không gắn request header đặc biệt có thể được browser gửi trực tiếp:

~~~http
GET /api/public/catalog HTTP/1.1
Host: api.example.test
Origin: https://app.example.test
Accept: application/json
~~~

Server:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.test
Vary: Origin
Content-Type: application/json

{"edition":"2026-A"}
~~~

Browser xem xét `Access-Control-Allow-Origin`. Nếu khớp origin và chính sách credentials phù hợp, JavaScript có thể đọc body. Nếu không, browser báo CORS error cho script dù server có thể đã xử lý request và gửi HTTP status/body.

**Không cố “sửa CORS” bằng cách thay `mode: "no-cors"`** trong fetch. Nó thường tạo opaque response mà JavaScript không đọc body/headers như một API JSON thông thường. Proxy browser extension tắt bảo mật không phải giải pháp triển khai production.

### 3.1. Request header Origin khác header Referer

`Origin` chứa nguồn yêu cầu theo browser semantics; `Referer` có thể bị rút gọn/ẩn theo Referrer-Policy và không phải thay thế chính xác cho Origin. Server CORS phải dùng cấu hình CORS chuẩn, không tự so sánh chuỗi bằng `request.getHeaders().getFirst("Referer")`.

### 3.2. Truy cập tài nguyên công khai bằng curl

~~~bash
curl -i 'http://localhost:8080/api/public/catalog' \
  -H 'Origin: https://app.example.test'
~~~

Bạn có thể thấy CORS headers từ server. Nhưng curl không tự áp dụng same-origin policy: **việc curl đọc được JSON không chứng minh browser cũng đọc được**. Dùng browser DevTools và test preflight/actual response khi xác nhận CORS.

## 4. Preflight: khi browser hỏi trước bằng OPTIONS

Nếu frontend gửi một request không thuộc nhóm CORS-safelisted, ví dụ:

~~~javascript
await fetch("https://api.example.test/api/public/echo", {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    "X-Client-Trace": "ui-demo"
  },
  body: JSON.stringify({name: "An"})
});
~~~

thì browser thường gửi **preflight OPTIONS** trước actual POST:

~~~http
OPTIONS /api/public/echo HTTP/1.1
Origin: https://app.example.test
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type,x-client-trace
~~~

Server chấp thuận ví dụ:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Methods: GET,POST
Access-Control-Allow-Headers: Content-Type,X-Client-Trace
Access-Control-Max-Age: 600
~~~

Sau preflight hợp lệ, browser mới gửi actual POST và kiểm CORS **trên response actual**. Không coi preflight thành công là đã xác thực user hoặc bảo đảm POST thành công.

### 4.1. Khi nào có preflight?

Những điều kiện hay kích hoạt preflight:
- HTTP method không phải một trong GET/HEAD/POST với các ràng buộc Fetch.
- Gửi custom headers như `X-Client-Trace`, `Authorization`.
- POST với `Content-Type: application/json` (không phải một trong các Content-Types được safelist trong tình huống chuẩn).
- Một số giá trị/kiểu headers và chế độ request khác có ràng buộc của Fetch.

Không đưa ra quy tắc đơn giản sai rằng “mọi POST đều preflight” hoặc “GET không bao giờ preflight”. Ví dụ GET có `Authorization` thường cần preflight khi cross-origin.

### 4.2. Preflight cache khác response cache

| Header | Ai dùng? | Ý nghĩa |
| --- | --- | --- |
| `Access-Control-Max-Age: 600` | Browser CORS-preflight cache | Cho phép tái sử dụng kết quả permission check một thời gian (browser có thể giới hạn mức tối đa) |
| `Cache-Control: max-age=600` | Browser HTTP cache / shared cache theo quy tắc | Freshness của HTTP representation, không phải permission preflight |
| `Expires` | HTTP caching | Thời điểm hết fresh theo semantics HTTP |
| `ETag`, `If-None-Match` | Conditional HTTP request | Có thể giảm tải body qua 304 |
| `Vary: Origin` | HTTP caches | Chỉ reuse response khi request headers phù hợp variant key |

Một server có thể đặt `Access-Control-Max-Age: 3600` mà API JSON vẫn có `Cache-Control: no-store`. Không suy từ một header sang header còn lại.

### 4.3. Đừng tự viết một OPTIONS handler trả dấu sao cho mọi origin

Tự gắn:

~~~http
Access-Control-Allow-Origin: *
Access-Control-Allow-Credentials: true
~~~

là một tổ hợp **không hợp lệ cho credentialed CORS requests**. Với credentials, Access-Control-Allow-Origin phải là origin cụ thể được cho phép; không dùng wildcard `*`. Spring CORS sẽ giúp validate cấu hình phù hợp nhưng security review vẫn cần thiết.

## 5. Bốn response headers CORS quan trọng

### 5.1. `Access-Control-Allow-Origin`

Cho phép origin cụ thể hoặc `*` khi thật sự phù hợp cho tài nguyên công khai không credentialed. Với `allowCredentials(true)`, không được dùng `allowedOrigins("*")` theo hợp đồng và Spring validation. Có thể dùng `allowedOriginPatterns` theo các pattern kiểm soát nếu use case thực sự yêu cầu, nhưng tốt hơn là allowlist một tập origins hữu hạn.

### 5.2. `Access-Control-Allow-Methods`

Dùng trong preflight để khai báo methods được phép đối với browser cross-origin request. Nó **không tự mở method mapping** trên server: CORS cho POST không biến một controller chỉ có GET thành POST endpoint. Cũng không cấp user permission.

### 5.3. `Access-Control-Allow-Headers`

Cho phép các **request headers** mà browser định dùng trong actual request, ví dụ `Content-Type`, `Authorization` hoặc `X-Client-Trace`. Không nhầm với `Access-Control-Expose-Headers`.

### 5.4. `Access-Control-Expose-Headers`

Chỉ định các **response headers không mặc nhiên CORS-safelisted** mà frontend JS được phép đọc.

~~~javascript
const response = await fetch("https://api.example.test/api/public/catalog");
console.log(response.headers.get("ETag"));
~~~

Nếu muốn browser JavaScript đọc `ETag`, có thể đặt `Access-Control-Expose-Headers: ETag`. Việc header tồn tại trên network không đảm bảo fetch JS đọc được nếu chưa được expose phù hợp.

**Lưu ý:** `Set-Cookie` là forbidden response header name và không thể biến thành header JS đọc được chỉ bằng `exposedHeaders("Set-Cookie")`. Cookie vẫn có policies riêng.

## 6. Ba cách cấu hình CORS trong Spring WebFlux

### 6.1. `@CrossOrigin` trên annotated controller

Dùng khi chỉ một hoặc vài endpoints đặc biệt:

~~~java
@CrossOrigin(
        origins = "https://app.example.test",
        methods = {RequestMethod.GET},
        maxAge = 600)
@GetMapping("/api/public/catalog")
public Mono<Catalog> catalog() {
    return Mono.just(catalogService.current());
}
~~~

Đây là **fragment**, không độc lập: cần class controller, `Catalog` và service. `@CrossOrigin` ở class áp dụng cho các methods được phép và có thể kết hợp với cấu hình global; quy tắc combine giữa class/method/global cần được kiểm nếu có nhiều lớp policy.

Ưu điểm: policy nằm gần endpoint, dễ hiểu nếu chỉ vài exception. Nhược điểm: khó audit khi hàng trăm controllers gắn origins khác nhau và mỗi môi trường có frontend origins khác nhau.

### 6.2. `WebFluxConfigurer.addCorsMappings`: cấu hình chung cho URL pattern

Đây là lựa chọn chuẩn để quản lý CORS cho nhóm annotated APIs:

~~~java
@Configuration
public class CorsWebConfig implements WebFluxConfigurer {

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/public/**")
                .allowedOrigins("https://app.example.test")
                .allowedMethods("GET", "POST")
                .allowedHeaders("Content-Type", "X-Client-Trace")
                .exposedHeaders("ETag", "X-Request-Id")
                .allowCredentials(false)
                .maxAge(600);
    }
}
~~~

**Đối với Spring Boot**, chỉ thêm `@Configuration implements WebFluxConfigurer`, **không gắn `@EnableWebFlux`** nếu muốn giữ các WebFlux auto-configurations của Boot. `@EnableWebFlux` dùng khi bạn có chủ đích tiếp quản cấu hình framework và chấp nhận cấu hình lại những tích hợp Boot cần thiết.

Giải thích:
- `addMapping("/api/public/**")` là path pattern áp dụng.
- `allowedOrigins` chỉ cho origin frontend được công bố.
- `allowedMethods` gồm GET và POST.
- `allowedHeaders` cho phép JSON + header custom của client.
- `exposedHeaders` cho JavaScript đọc ETag hoặc correlation header do server gửi.
- `allowCredentials(false)` không bật credentialed CORS.
- `maxAge(600)` là thời gian **preflight cache**, theo giây.

Không dùng cấu hình origin production `"*".allowCredentials(true)`. Nếu API có auth cookie, cân nhắc explicit origins, secure cookies, CSRF và Spring Security integration.

### 6.3. `CorsWebFilter` cho functional routes / xử lý sớm toàn stack

Với WebFlux.fn hoặc muốn CORS được xử lý trong WebFilter chain, Spring cung cấp `CorsWebFilter`:

~~~java
@Bean
CorsWebFilter corsWebFilter() {
    CorsConfiguration cors = new CorsConfiguration();
    cors.setAllowedOrigins(List.of("https://app.example.test"));
    cors.setAllowedMethods(List.of("GET", "POST"));
    cors.setAllowedHeaders(
            List.of("Content-Type", "X-Client-Trace"));
    cors.setAllowCredentials(false);
    cors.setMaxAge(600L);

    UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
    source.registerCorsConfiguration("/api/public/**", cors);
    return new CorsWebFilter(source);
}
~~~

Đây là **fragment**: class config và imports phù hợp còn thiếu. Servlet `CorsFilter` không phải bean của WebFlux reactive stack; dùng đúng `org.springframework.web.cors.reactive.CorsWebFilter` và `org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource`.

**Chọn một nguồn chính sách CORS rõ ràng.** Đừng vô ý bật cả global registry, `@CrossOrigin`, một CorsWebFilter và thêm CORS headers trong gateway mà không xác định thứ tự/chồng lấn. Kết quả có thể là duplicate/contradictory headers hoặc việc kiểm soát không đồng nhất giữa preflight và actual responses.

### 6.4. Spring Security WebFlux phải xử lý preflight trước auth

Preflight thường **không mang cùng cookie authentication** như actual request. Nếu authentication filter chặn OPTIONS trước khi CORS xử lý, browser báo lỗi CORS dù API POST sau đó có thể hợp lệ.

Khi thêm `spring-boot-starter-security` và `SecurityWebFilterChain`:
- Đảm bảo CORS integration được thực hiện **trước security authentication/authorization**, theo hướng dẫn Spring Security reactive.
- Có thể cấu hình `CorsWebFilter` hoặc `CorsConfigurationSource` phù hợp để Spring Security tích hợp.
- `http.cors(...)` ở reactive security nên được cấu hình theo phiên bản Security 6.x đang dùng.
- Không disable toàn bộ CSRF chỉ vì frontend cross-origin.
- Actual GET/POST phải vẫn qua authentication/authorization/object ownership.
- Test 200/401/403/OPTIONS bằng `WebTestClient` với filter chain thật.

Không copy snippet Servlet `HttpSecurity`/`SecurityFilterChain` sang reactive `ServerHttpSecurity`/`SecurityWebFilterChain`.

## 7. CORS không phải authorization và không ngăn CSRF

Một endpoint có `Access-Control-Allow-Origin` rộng vẫn phải kiểm:
- Ai là caller, token/session có hợp lệ không?
- User có được đọc tài nguyên ID đó hay không?
- Tenant hiện tại là tenant nào?
- Browser credentialed requests có CSRF token cho thao tác state-changing không?
- Có rate limits và protections khác không?

CORS phần lớn ngăn JavaScript ở origin không được phép **đọc** cross-origin responses; nó không đảm bảo request gây side effect không bao giờ tới server. Form submission, cross-site requests và HTTP clients trực tiếp là những threat models khác.

### 7.1. `credentials: "include"` đòi hỏi nhiều điều kiện

Browser request:

~~~javascript
fetch("https://api.example.test/api/account/me", {
  credentials: "include"
});
~~~

Nếu server muốn hỗ trợ credentialed CORS:
- Chỉ cho **origins xác định**.
- `Access-Control-Allow-Credentials: true` trên response phù hợp.
- Cookie attributes phải cho phép gửi cross-site khi cần (`SameSite=None; Secure` khi phù hợp), và browser có thể có third-party cookie restrictions.
- CSRF/session security vẫn cần đúng.
- Không thể dùng `Access-Control-Allow-Origin: *` với credentialed response.

Ngay cả khi `allowCredentials(true)` trong Spring CORS, nó không tạo auth session, không cấp role và không bảo đảm cookie sẽ được browser gửi; các cấu hình khác vẫn quyết định.

### 7.2. CORS với CDN

Nếu server thay `Access-Control-Allow-Origin` theo incoming `Origin`, cần tránh CDN trả response có ACAO của origin A cho origin B. Framework có thể phát `Vary: Origin`, `Access-Control-Request-Method`, `Access-Control-Request-Headers` khi phù hợp; CDN phải tôn trọng `Vary` hoặc có custom cache key an toàn.

**Không dùng `Vary: Origin` thay `Cache-Control: no-store/private` cho tài nguyên chứa dữ liệu user.** Hai clients cùng Origin không phải cùng một user. CORS và cache key không là authentication mechanism.

## 8. Spring Boot WebFlux phục vụ tài nguyên tĩnh mặc định

Spring Boot hỗ trợ static resources trong các thư mục classpath quen thuộc:
- `classpath:/static/`
- `classpath:/public/`
- `classpath:/resources/`
- `classpath:/META-INF/resources/`

Ví dụ file:

~~~text
src/main/resources/static/index.html
src/main/resources/static/css/app.css
src/main/resources/static/js/app.js
~~~

Có thể được phục vụ tại:
- `GET /` cho welcome page `index.html` khi không có route khác ưu tiên.
- `GET /css/app.css`.
- `GET /js/app.js`.

Spring Boot WebFlux dùng `ResourceWebHandler` để phục vụ các files đó. Mapping mặc định thường `/**`; có thể thay bằng `spring.webflux.static-path-pattern` và `spring.web.resources.static-locations` theo phiên bản Boot tương ứng.

**Không coi `src/main/webapp` của Servlet WAR là nguồn file chuẩn cho Boot WebFlux executable JAR**. WebFlux không phụ thuộc Servlet WAR deployment; đặt files dưới `src/main/resources` để đóng gói đúng.

### 8.1. Static file không phải view template

- `src/main/resources/static/index.html` thường là HTML **nguyên bản**, không tự xử lý biến Thymeleaf như một template.
- Template engines dùng thư mục riêng `templates/` và view resolvers.
- JS/CSS bundler có thể xuất files vào `static/assets/`; cần quản lý cache busting/versioned names.
- SPA client-side routes như `/app/settings` không được mặc định tự map về `index.html` trong mọi setup WebFlux. Nếu cần SPA fallback, cấu hình có kiểm soát và tránh bắt nhầm `/api/**`, file assets hoặc status 404.

### 8.2. Tùy chỉnh static path trong properties

~~~properties
spring.webflux.static-path-pattern=/assets/**
~~~

Đây là ví dụ cấu hình thay mapping static tài nguyên mặc định, **không phải ví dụ dự án runnable bên dưới**. Nếu dùng, phải cập nhật HTML asset paths và hiểu welcome page behavior; không gắn thêm properties này vào demo nếu đã chủ động cấu hình resource handler `/docs/**`.

### 8.3. Static resources có thể chịu CORS không?

Có. Browser fetch một file tĩnh bằng JavaScript qua origin khác có thể cần CORS, trong khi một thẻ HTML như `<img src>` hoặc `<script src>` tuân theo các cơ chế tải/hiển thị liên quan khác. Nếu muốn một frontend fetch fonts/assets qua CDN, cấu hình CORS cho các URL assets cần thiết hoặc tại CDN. Không tự cho rằng CORS mapping `/api/**` áp dụng cho `/assets/**`.

## 9. `ResourceHandlerRegistry`: custom route cho tài nguyên tĩnh

WebFlux có `WebFluxConfigurer.addResourceHandlers`:

~~~java
@Override
public void addResourceHandlers(ResourceHandlerRegistry registry) {
    registry.addResourceHandler("/docs/**")
            .addResourceLocations("classpath:/docs/")
            .setCacheControl(
                    CacheControl.maxAge(Duration.ofMinutes(5))
                            .cachePublic());
}
~~~

Khi ứng dụng đóng gói `src/main/resources/docs/guide.txt`, request `GET /docs/guide.txt` sẽ đọc resource tương ứng. `max-age=300` giới hạn freshness cho HTTP cache trong ví dụ; `public` cho phép shared caches dùng response nếu không có ràng buộc khác.

### 9.1. Các thành phần quan trọng

- `addResourceHandler("/docs/**")`: URL pattern do server tiếp nhận.
- `addResourceLocations("classpath:/docs/")`: root thư mục nguồn, không phải URL client dùng.
- `setCacheControl(...)`: policy HTTP cache cho các tài nguyên được phục vụ bởi handler đó.
- Resource resolvers và transformers có thể tham gia cache-busting/versioned URLs, compressed resources, path resolution.

Không truyền file system path từ query parameter trực tiếp sang resource loader mà không có path validation. Các path traversal protections của Spring vẫn nên được giữ; không tự disable normalization checks để “fix” một đường dẫn khó.

### 9.2. Metadata, 304 và `Last-Modified`

Resource handler có thể dùng metadata như last-modified để hỗ trợ conditional requests: client gửi `If-Modified-Since`, server có thể trả **304 Not Modified** nếu file không đổi và preconditions phù hợp. Không cam kết mọi loại resource (file trong JAR, cloud object, dynamic generated file) luôn có last-modified timestamp chính xác như nhau.

`Cache-Control` chỉ nói cache policy; `Last-Modified` và `ETag` cung cấp validators. Browser có thể dùng fresh cached asset mà **không gửi request**; khi stale, nó có thể gửi conditional request thay vì tải full bytes lại.

### 9.3. Không đặt cache lâu cho tài nguyên có URL không versioned

Nếu `/js/app.js` vẫn cùng URL sau deploy nhưng bạn đặt `Cache-Control: public, max-age=31536000, immutable`, client có thể dùng JS cũ trong thời gian dài. Với files thay nội dung thường xuyên, dùng max-age ngắn và validators, hoặc triển khai filenames/hashes.

## 10. Versioned assets và chính sách cache dài hạn

Frontend build tools thường tạo:

~~~text
/assets/app.f2a21c6a.js
/assets/app.83e4d9cd.css
/assets/logo.9da430ef.svg
~~~

Khi filename phản ánh content hash và build/deployment bảo đảm assets cũ vẫn truy cập được trong giai đoạn chuyển phiên bản, có thể đặt policy dài:

~~~http
Cache-Control: public, max-age=31536000, immutable
~~~

Nhưng `index.html` có thể chỉ nên:

~~~http
Cache-Control: no-cache
ETag: "index-build-20261021"
~~~

để mỗi lần browser revalidate entrypoint, nó có thể nhận references mới tới hashed assets.

**`no-cache` không có nghĩa "cấm lưu".** Nó cho phép lưu nhưng yêu cầu revalidation trước reuse. `no-store` mới là chỉ thị cấm lưu response vào HTTP caches tuân thủ quy tắc, phù hợp dữ liệu bí mật/nhạy cảm hơn.

### 10.1. `VersionResourceResolver` của WebFlux

Spring WebFlux có resource chain và `VersionResourceResolver` có thể tạo versioned resource URLs theo content hash hoặc fixed strategies:

~~~java
registry.addResourceHandler("/assets/**")
        .addResourceLocations("classpath:/static/assets/")
        .resourceChain(true)
        .addResolver(new VersionResourceResolver()
                .addContentVersionStrategy("/**"));
~~~

Đây là **fragment** cho một use case khác, không đặt chung với custom `/docs/**` demo bên dưới. Nếu frontend tham chiếu `/assets/app.js` mà server kỳ vọng `/assets/app-<hash>.js`, cần quy trình build/URL rewriting hoặc `ResourceUrlProvider` tương ứng. **Đừng chỉ bật resolver và cho rằng HTML/JS links tự động được rewrite đúng trong mọi WebFlux view**.

Khi kết hợp compressed resolvers (`EncodedResourceResolver`) và versioning, Spring docs yêu cầu chú ý thứ tự để hash được tính từ bytes **chưa nén**. Hãy dùng resource chain được test đúng trên cả file gzip/Brotli và CDN; không gán ETag của representation khác nhau tùy tiện.

### 10.2. CDN cache lâu cần chiến lược giữ phiên bản cũ

Một HTML cũ có thể vẫn tham chiếu `app.oldhash.js` ngay sau deploy mới. Nếu server/CDN xóa asset cũ ngay, người dùng đang mở tab cũ có thể lỗi. Chiến lược triển khai assets hashed nên bảo đảm:
- Files cũ còn sẵn trong cửa sổ tương thích.
- CDN purge không xóa nhầm content-addressed files vẫn được client dùng.
- HTML entrypoint nhận validators hoặc freshness ngắn.
- Build atomic và rollback không dẫn tới “HTML mới + assets cũ không còn”.
- Security patch nguy cấp có kế hoạch invalidation đặc biệt.

## 11. HTTP caching: khái niệm nền tảng

Một cache có thể là:
- Browser private cache.
- Shared proxy/CDN cache.
- Reverse proxy ứng dụng.
- Service worker cache (cơ chế khác biệt, có script quản lý riêng).
- Application-level cache như Spring Cache/Redis (không tự tuân HTTP headers).

Các đối tượng này **không mặc nhiên có cùng cache key/eviction policy**. Một `@Cacheable` ở service không tự gửi `Cache-Control`/ETag ra HTTP. Ngược lại, `Cache-Control: no-store` ở response không tự xóa mọi entry trong Redis hoặc database.

### 11.1. `Cache-Control` directives

| Directive | Diễn giải cốt lõi | Dùng khi |
| --- | --- | --- |
| `no-store` | HTTP cache không được lưu response/request theo quy tắc | Dữ liệu nhạy cảm hoặc không muốn HTTP caching |
| `no-cache` | Có thể lưu, nhưng phải revalidate trước reuse | HTML entrypoint, nội dung cần luôn kiểm tính mới |
| `private` | Shared cache không được lưu; private cache có thể lưu | Dữ liệu cá nhân khi browser caching được phép |
| `public` | Cho phép shared cache lưu khi các điều kiện khác đáp ứng | Public assets/data |
| `max-age=N` | Freshness theo giây | Public resource ít đổi |
| `s-maxage=N` | Freshness cho shared cache, override max-age cho shared cache | CDN/proxy policy riêng |
| `must-revalidate` | Hạn chế dùng stale khi cần revalidation | Nội dung cần xử lý stale nghiêm |
| `immutable` | Gợi ý không revalidate khi fresh vì representation bất biến | Content-hashed assets |
| `no-transform` | Yêu cầu intermediaries không transform representation | Nội dung cần giữ nguyên |

Không tự kết luận một response với `Cache-Control: public` luôn được CDN cache: request Authorization, cookie, status, cache key, CDN configuration, `Vary` và headers khác vẫn ảnh hưởng. Không đưa dữ liệu user vào public cache do hiểu sai `public`.

### 11.2. Fresh vs stale

Giả sử:

~~~http
Cache-Control: public, max-age=60
~~~

Trong khoảng fresh, cache có thể trả response mà không liên hệ origin (nếu cache thực sự lưu và các điều kiện còn đúng). Sau đó response stale, client/cache có thể cần conditional revalidation.

Một response với `no-cache` có thể được **lưu** nhưng phải kiểm lại để dùng; không coi nó là “disable browser cache” một cách tuyệt đối.

### 11.3. HTTP cache key và query strings

Đường dẫn `/api/public/catalog?lang=vi` và `?lang=en` là hai target URIs khác nhau trong cache model thông thường, nhưng CDN có thể cấu hình bỏ query params. Với response phụ thuộc `Accept-Language` hoặc `Origin`, cần `Vary` thích hợp. Không dựa vào cache key lý thuyết khi gateway/CDN đã override key.

## 12. Conditional GET: `ETag`, `Last-Modified` và 304

### 12.1. Chuỗi 200 → If-None-Match → 304

Lần đầu:

~~~http
GET /api/public/catalog HTTP/1.1
~~~

Response:

~~~http
HTTP/1.1 200 OK
ETag: "catalog-2026-a"
Cache-Control: public, max-age=60
Content-Type: application/json

{"edition":"2026-A","subjects":["WebFlux","HTTP"]}
~~~

Khi cache cần revalidate:

~~~http
GET /api/public/catalog HTTP/1.1
If-None-Match: "catalog-2026-a"
~~~

Nếu server xác định representation tương ứng chưa thay đổi:

~~~http
HTTP/1.1 304 Not Modified
ETag: "catalog-2026-a"
Cache-Control: public, max-age=60
~~~

304 không có response body JSON mới; cache/browser giữ body đã lưu nếu còn có thể dùng nó với metadata cập nhật. **304 không phải 200 với body rỗng**. Một client tự viết bằng HTTP library không có cache vẫn có thể nhận 304 mà không có bytes JSON để parse — cần có cached representation trước đó hoặc xử lý khác.

### 12.2. ETag mạnh và yếu

- Strong ETag thường dạng `"abc123"`, biểu thị validator mạnh theo quy tắc byte-for-byte của representation.
- Weak ETag dạng `W/"abc123"`, hữu ích khi muốn phản ánh tương đương ngữ nghĩa nhưng bytes có thể khác.
- ETag là **opaque token**, không phải hash được browser tự hiểu. Không để lộ private state hoặc internal database secrets trong token.
- Nếu cùng ETag được dùng cho hai JSON representations khác nhau theo ngôn ngữ/media type, bạn có thể gặp sai semantics; tính/định nghĩa ETag theo representation hợp lệ và `Vary`.

Trong Spring WebFlux, `ResponseEntity.BodyBuilder.eTag("catalog-2026-a")` sẽ chuẩn hóa dấu ngoặc kép để tạo ETag hợp lệ. Đừng tự nối dấu quote nhiều lần không kiểm.

### 12.3. Last-Modified

~~~http
Last-Modified: Thu, 01 Oct 2026 00:00:00 GMT
~~~

Client có thể gửi `If-Modified-Since`. Timestamp có độ phân giải theo giây trong HTTP date, nên thay đổi nhiều lần trong cùng một giây khó biểu diễn chính xác; một ETag theo version/resource representation thường đáng tin hơn cho granular updates.

Nếu client gửi cả `If-None-Match` và `If-Modified-Since`, HTTP semantics quy định thứ tự ưu tiên cho conditional evaluation; **không tự cộng hai điều kiện thành AND tùy ý**.

### 12.4. 304 không có nghĩa bỏ qua authorization

Nếu resource tùy user/tenant, server vẫn cần kiểm authentication/authorization ở request revalidation. Một attacker không được phép không thể nhận 304 rồi lợi dụng cache/body cũ của người khác. 304 và ETag giảm bandwidth, không phải skip permission checks.

### 12.5. Precondition cho writes

`If-Match`/ETag còn có thể dùng optimistic concurrency cho PUT/PATCH/DELETE; server có thể trả **412 Precondition Failed** khi tài nguyên đã đổi. Đây là mục đích khác với GET `If-None-Match` → 304. Với update cần so sánh version trong transaction an toàn, không chỉ dựa trên ETag rồi update database ở bước sau không đồng bộ.

## 13. Dùng `CacheControl` và `ResponseEntity` trong Spring WebFlux

Spring `CacheControl` xây response header đúng các use cases phổ biến:

~~~java
CacheControl cache = CacheControl.maxAge(Duration.ofSeconds(60))
        .cachePublic();
~~~

Controller trả:

~~~java
@GetMapping("/api/public/catalog")
public ResponseEntity<Catalog> catalog() {
    return ResponseEntity.ok()
            .cacheControl(cache)
            .eTag("catalog-2026-a")
            .body(new Catalog("2026-A", List.of("WebFlux", "HTTP")));
}
~~~

Đây là fragment (class `Catalog` và biến `cache` chưa có); demo runnable ở mục 17 khai báo đầy đủ. Với WebFlux có thể dùng cả `Mono<ResponseEntity<T>>` nếu metadata/status/body chỉ biết sau công việc bất đồng bộ. Không gọi `.block()` để chuẩn bị cache policy trong controller.

### 13.1. Spring hỗ trợ conditional requests khi ResponseEntity có validators

Spring WebFlux có thể xử lý conditional GET/HEAD dựa trên ETag/lastModified được trả từ controller và đưa ra 304 theo điều kiện. Cấu hình cần đúng contract, method và version. Dùng WebTestClient gửi `If-None-Match` để xác minh behavior thay vì đoán.

### 13.2. API cá nhân hóa: `no-store`

~~~java
@GetMapping("/api/example-sensitive")
public ResponseEntity<Map<String,String>> sample() {
    return ResponseEntity.ok()
            .cacheControl(CacheControl.noStore())
            .body(Map.of("sample", "not real user data"));
}
~~~

Đây là fragment. `no-store` thích hợp khi HTTP response rất nhạy cảm; nhưng nó không tự ngăn server app logs hoặc người dùng tự sao chép thông tin. Nếu response thực sự chứa dữ liệu cá nhân, authentication + object/tenant authorization vẫn là điều kiện tiên quyết.

### 13.3. Shared cache với `Authorization`

RFC 9111 có các hạn chế/ngoại lệ cho shared caches với response của request có Authorization. Không đặt `Cache-Control: public` hoặc `s-maxage` cho tài nguyên credentialed có body cá nhân hóa khi chưa có kiến trúc cache key/security được review kỹ.

Một user có thể truy cập cùng `/api/me` với user khác; nếu CDN cache theo URI đơn thuần, cả hai có nguy cơ nhận cùng body. `Vary: Origin`, `Vary: Accept` hoặc `Vary: Authorization` không phải giải pháp thay thế đầy đủ cho tenant/user isolation và safe caching policy. Dùng `private/no-store` theo độ nhạy cảm.

## 14. CORS và cache có tương tác phức tạp

### 14.1. Public API phụ thuộc Origin

Server có thể phản hồi một whitelist origin từ request và gửi `Vary: Origin`. Nếu một shared cache bỏ qua `Vary` hoặc CDN custom key không xét Origin, nó có thể phục vụ response của origin A cho origin B, dẫn đến browser lỗi CORS hoặc chính sách ngoài ý muốn.

CORS chỉ nói origin nào được JS đọc. Một response có ACAO cho app.example.test **không** có nghĩa dữ liệu an toàn để lưu vào shared cache. Nếu dữ liệu tùy user, đánh giá Cache-Control độc lập.

### 14.2. Vary: Accept-Encoding và versioned assets

Compressed resources có các variants gzip/Brotli; khi representation phụ thuộc `Accept-Encoding`, `Vary: Accept-Encoding` liên quan đến cache selection. Không phục vụ cùng ETag mạnh cho bytes nén và chưa nén nếu vi phạm strong validator semantics.

### 14.3. Browser preflight cache không thay ETag validation

CORS preflight permission có thể được cache 600 giây, nhưng cùng client có thể gửi conditional GET bất cứ lúc nào cần revalidation HTTP. Browser có thể không gọi OPTIONS lần nữa nhưng vẫn gọi GET và nhận 304. Hai hệ cache độc lập, không nên dùng chung invalidation assumption.

### 14.4. CORS headers trong 304 response

Một conditional request từ frontend khác origin vẫn chịu CORS. Nếu response 304 được gửi nhưng mất `Access-Control-Allow-Origin`/`Vary` phù hợp qua gateway/cache, browser có thể không dùng response như mong muốn. Kiểm 200 **và** 304 qua Origin header trong integration/CDN tests.

## 15. Cấu hình nào áp dụng cho file tĩnh và API?

| Phạm vi URL | Loại response | CORS | HTTP cache gợi ý |
| --- | --- | --- | --- |
| `/api/public/**` | JSON public, không bí mật | Allowlist frontend origins cần dùng | Freshness ngắn + ETag |
| `/api/account/**` | Dữ liệu xác thực | Explicit origin + credentials nếu cần | `no-store` hoặc `private` theo policy |
| `/docs/**` | File docs public | Chỉ cần CORS nếu browser JS đọc cross-origin | `max-age` ngắn, validators |
| `/assets/**` hashed | JS/CSS/images public | Theo CDN/font/fetch needs | `public, max-age=31536000, immutable` khi filenames thật sự content-addressed |
| `/index.html` | Entrypoint cập nhật thường | Thường cùng origin | `no-cache` hoặc freshness ngắn + validators |
| `/api/admin/**` | Quản trị | Hạn chế origin, không mở từ mọi site | `no-store`, auth và authorization bắt buộc |

**Không sử dụng một global `Cache-Control: public` cho mọi URL**, vì nó có thể vô tình áp lên 401/403/PII/error pages. Cũng không dùng `@CrossOrigin(origins="*")` trên tất cả controllers chỉ để tránh lỗi frontend development.

## 16. Demo runnable: Java 17 + Spring Boot 3.3.5 WebFlux

Ứng dụng nhỏ triển khai:
- `GET /api/public/catalog`: response JSON ổn định, `Cache-Control: public, max-age=60`, `ETag: "catalog-2026-a"`, `Last-Modified` cố định.
- `POST /api/public/echo`: nhận JSON nhỏ từ `@RequestBody Mono<HelloRequest>` và trả JSON; ví dụ để test CORS preflight.
- `GET /api/example-sensitive`: fixture không chứa PII nhưng minh họa `Cache-Control: no-store`.
- `GET /docs/guide.txt`: file public từ classpath, cache 5 phút qua `ResourceHandlerRegistry`.
- `GET /`: trang `static/index.html` do Spring Boot auto-config phục vụ.
- `WebFluxConfigurer`: allowlist CORS chính xác cho `/api/public/**`, custom static handler cho `/docs/**`.
- `WebTestClient`: kiểm valid/invalid origins, preflight POST, ETag/304, static content và no-store.

Ứng dụng không có auth/database, vì mục tiêu là CORS/static/cache. Không xem endpoint `example-sensitive` là ví dụ bảo vệ dữ liệu người dùng thật; ở production thêm Spring Security và resource-level authorization.

~~~text
webflux-cors-static-cache/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/com/example/cacheweb/
    │   │   ├── CacheWebApplication.java
    │   │   ├── config/WebFluxHttpConfig.java
    │   │   └── web/CatalogController.java
    │   └── resources/
    │       ├── static/index.html
    │       └── docs/guide.txt
    └── test/java/com/example/cacheweb/
        └── CorsStaticCacheIntegrationTest.java
~~~

### 16.1. Gradle và Java

`settings.gradle`:

~~~groovy
rootProject.name = 'webflux-cors-static-cache'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
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
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

**Không thêm** `spring-boot-starter-web`: khi cả MVC và WebFlux starters có mặt, Spring Boot thường chọn MVC application type; ví dụ trên cần WebFlux với Reactor Netty. Gradle wrapper nên được tạo bằng phiên bản Gradle tương thích với Java 17/Boot 3.3.5 nếu project chưa có `gradlew`.

### 16.2. Main application

`src/main/java/com/example/cacheweb/CacheWebApplication.java`:

~~~java
package com.example.cacheweb;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CacheWebApplication {

    public static void main(String[] args) {
        SpringApplication.run(CacheWebApplication.class, args);
    }
}
~~~

### 16.3. WebFlux HTTP config: CORS và file tĩnh

`src/main/java/com/example/cacheweb/config/WebFluxHttpConfig.java`:

~~~java
package com.example.cacheweb.config;

import java.time.Duration;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.CacheControl;
import org.springframework.web.reactive.config.CorsRegistry;
import org.springframework.web.reactive.config.ResourceHandlerRegistry;
import org.springframework.web.reactive.config.WebFluxConfigurer;

@Configuration
public class WebFluxHttpConfig implements WebFluxConfigurer {

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/public/**")
                .allowedOrigins("https://app.example.test")
                .allowedMethods("GET", "POST")
                .allowedHeaders("Content-Type", "X-Client-Trace")
                .exposedHeaders("ETag", "X-Request-Id")
                .allowCredentials(false)
                .maxAge(600);
    }

    @Override
    public void addResourceHandlers(ResourceHandlerRegistry registry) {
        registry.addResourceHandler("/docs/**")
                .addResourceLocations("classpath:/docs/")
                .setCacheControl(
                        CacheControl.maxAge(Duration.ofMinutes(5))
                                .cachePublic());
    }
}
~~~

Không dùng `@EnableWebFlux` để giữ Boot auto-config. CORS mapping chỉ áp dụng cho `/api/public/**`, không mở origin cho `/api/example-sensitive` hoặc `/docs/**`. Nếu browser JavaScript cần fetch `/docs/**` cross-origin, phải thêm CORS policy riêng sau khi review, không tự suy nó từ public cache.

### 16.4. Controller: ResponseEntity, ETag, Last-Modified, no-store

`src/main/java/com/example/cacheweb/web/CatalogController.java`:

~~~java
package com.example.cacheweb.web;

import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api")
public class CatalogController {

    public record Catalog(String edition, List<String> subjects) {}
    public record HelloRequest(String name) {}
    public record HelloResponse(String greeting) {}

    private static final String CATALOG_VERSION = "catalog-2026-a";
    private static final Instant UPDATED =
            Instant.parse("2026-10-01T00:00:00Z");

    @GetMapping(
            path = "/public/catalog",
            produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<Catalog> catalog() {
        Catalog data = new Catalog(
                "2026-A", List.of("WebFlux", "HTTP"));

        return ResponseEntity.ok()
                .cacheControl(
                        CacheControl.maxAge(Duration.ofSeconds(60))
                                .cachePublic())
                .eTag(CATALOG_VERSION)
                .lastModified(UPDATED)
                .body(data);
    }

    @PostMapping(
            path = "/public/echo",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<ResponseEntity<HelloResponse>> echo(
            @RequestBody Mono<HelloRequest> body) {

        return body.map(request -> {
            String name = request.name();

            if (name == null || name.isBlank()
                    || name.length() > 50) {
                throw new ResponseStatusException(
                        HttpStatus.BAD_REQUEST, "Invalid name");
            }

            return ResponseEntity.ok()
                    .cacheControl(CacheControl.noStore())
                    .body(new HelloResponse(
                            "Hello, " + name.trim()));
        });
    }

    @GetMapping(
            path = "/example-sensitive",
            produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<Map<String, String>> noStoreExample() {
        return ResponseEntity.ok()
                .cacheControl(CacheControl.noStore())
                .body(Map.of(
                        "note", "Fixture only; no personal data"));
    }
}
~~~

**Điểm đáng kiểm trong code:**
- `CATALOG_VERSION` và `UPDATED` là metadata giả định **ổn định vì catalog fixture cố định**. Khi catalog thật thay, bắt buộc thay ETag/version và lastModified cho phù hợp nội dung.
- `.eTag(CATALOG_VERSION)` được Spring chuẩn hóa thành `"catalog-2026-a"`.
- `.cacheControl(...)` tạo Cache-Control response header; **không** tự tạo `Vary: Origin`, việc đó thuộc CORS processing.
- `.lastModified(UPDATED)` thêm Last-Modified, tạo cơ sở `If-Modified-Since` khi phù hợp.
- `ResponseEntity<Catalog>` có status/headers/body quyết định đồng bộ; nó phù hợp vì dữ liệu fixture không có call bất đồng bộ. Với reactive service, dùng `Mono<ResponseEntity<Catalog>>` khi metadata đến từ reactive publisher.
- POST `echo` trả response `no-store` vì đó là input-driven response; thực tế echo có thể chứa PII nên không cache.
- `@RequestBody Mono<HelloRequest>` để codec Spring đọc JSON; không đọc request `Flux<DataBuffer>` lần thứ hai.
- Không dùng `block()`, `Thread.sleep` hoặc JDBC blocking trên event loop.
- Error body từ `ResponseStatusException` phụ thuộc Spring Boot error handling; sample tests chỉ kiểm status 400, không khẳng định JSON schema cố định.
- Vì không có security dependency, sample `example-sensitive` **không có auth**; nó chỉ dạy HTTP cache directive.

### 16.5. Trang HTML mặc định

`src/main/resources/static/index.html`:

~~~html
<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <title>WebFlux HTTP demo</title>
</head>
<body>
  <h1>WebFlux CORS / Static / Cache</h1>
  <p>Trang này được phục vụ từ classpath:/static/index.html.</p>
</body>
</html>
~~~

Spring Boot có welcome page detection; khi không có handler `GET "/"` ưu tiên hơn, `/` sẽ trả nội dung của `index.html`. Đây là **file HTML tĩnh**, không xử lý Thymeleaf expressions.

### 16.6. File docs phục vụ bởi handler tùy chỉnh

`src/main/resources/docs/guide.txt`:

~~~text
WebFlux resource guide
~~~

`GET /docs/guide.txt` sẽ đọc file theo path registration trong `WebFluxHttpConfig`. `Cache-Control` được set ở ResourceWebHandler cho route này; nếu cần CORS cho docs tải bằng browser cross-origin fetch, cấu hình nó riêng.

## 17. Integration tests với WebTestClient

Dùng embedded Reactor Netty với port ngẫu nhiên để kiểm cả HTTP routing, CORS và response headers. Đây không phải Servlet MockMvc tests.

`src/test/java/com/example/cacheweb/CorsStaticCacheIntegrationTest.java`:

~~~java
package com.example.cacheweb;

import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class CorsStaticCacheIntegrationTest {

    private static final String FRONTEND =
            "https://app.example.test";

    @Autowired
    WebTestClient client;

    @Test
    void publicCatalogHasExplicitCorsAndCacheHeaders() {
        client.get().uri("/api/public/catalog")
                .header(HttpHeaders.ORIGIN, FRONTEND)
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueEquals(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, FRONTEND)
                .expectHeader().valueEquals(
                        HttpHeaders.ETAG, "\"catalog-2026-a\"")
                .expectHeader().valueContains(
                        HttpHeaders.CACHE_CONTROL, "max-age=60")
                .expectBody()
                .jsonPath("$.edition").isEqualTo("2026-A")
                .jsonPath("$.subjects[0]").isEqualTo("WebFlux");
    }

    @Test
    void conditionalGetReturns304WithoutNewBody() {
        client.get().uri("/api/public/catalog")
                .header(HttpHeaders.ORIGIN, FRONTEND)
                .header(HttpHeaders.IF_NONE_MATCH, "\"catalog-2026-a\"")
                .exchange()
                .expectStatus().isNotModified()
                .expectHeader().valueEquals(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, FRONTEND)
                .expectHeader().valueEquals(
                        HttpHeaders.ETAG, "\"catalog-2026-a\"")
                .expectBody().isEmpty();
    }

    @Test
    void allowedPreflightPermitsJsonPostAndCustomHeader() {
        client.options().uri("/api/public/echo")
                .header(HttpHeaders.ORIGIN, FRONTEND)
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                        "content-type,x-client-trace")
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueEquals(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, FRONTEND)
                .expectHeader().valueContains(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_METHODS, "POST");
    }

    @Test
    void forbiddenOriginIsRejectedByCorsProcessor() {
        client.get().uri("/api/public/catalog")
                .header(HttpHeaders.ORIGIN, "https://evil.example.test")
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void actualJsonPostIsHandledAndNotCached() {
        client.post().uri("/api/public/echo")
                .header(HttpHeaders.ORIGIN, FRONTEND)
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(Map.of("name", "An"))
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueEquals(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, FRONTEND)
                .expectHeader().valueContains(
                        HttpHeaders.CACHE_CONTROL, "no-store")
                .expectBody()
                .jsonPath("$.greeting").isEqualTo("Hello, An");
    }

    @Test
    void personalizedPolicyExampleSaysNoStore() {
        client.get().uri("/api/example-sensitive")
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueContains(
                        HttpHeaders.CACHE_CONTROL, "no-store")
                .expectBody()
                .jsonPath("$.note").exists();
    }

    @Test
    void customDocsResourceIsServedWithShortPublicCache() {
        client.get().uri("/docs/guide.txt")
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueContains(
                        HttpHeaders.CACHE_CONTROL, "max-age=300")
                .expectBody(String.class)
                .isEqualTo("WebFlux resource guide\n");
    }

    @Test
    void defaultBootWelcomePageServesHtml() {
        client.get().uri("/")
                .exchange()
                .expectStatus().isOk()
                .expectHeader().contentTypeCompatibleWith(
                        MediaType.TEXT_HTML)
                .expectBody(String.class)
                .value(html -> {
                    if (!html.contains("WebFlux CORS / Static / Cache")) {
                        throw new AssertionError("Missing welcome content");
                    }
                });
    }
}
~~~

### 17.1. Vì sao test 304 quan trọng?

Nếu chỉ kiểm GET thông thường, bạn chưa biết `If-None-Match` được Spring xử lý đúng. Test trên gửi cùng ETag từ lần trước và kỳ vọng:
- HTTP 304.
- Body trống.
- ETag vẫn nhất quán.
- CORS header có mặt cho frontend origin hợp lệ.

**Trong mạng có CDN**, kiểm lại qua CDN vì shared caches có thể sửa headers/cache key hoặc tự trả 304 mà không tới origin. Embedded server test chỉ chứng minh hành vi application.

### 17.2. Kiểm preflight khác kiểm actual POST

Preflight test có `OPTIONS`, `Origin`, `Access-Control-Request-Method` và `Access-Control-Request-Headers`. Actual POST test gửi JSON body và kiểm echo. Browser phải được phép ở **cả hai bước**, và security logic vẫn được chạy trên actual request theo kiến trúc.

### 17.3. Vì sao không assert từng byte headers khác?

Server/container có thể thêm Date, Content-Length, transfer-encoding hoặc thay thứ tự fields. Tests nên tập trung HTTP semantics:
- ACAO đúng origin.
- ETag quote format.
- Cache-Control chứa max-age/no-store phù hợp.
- 304 không có body.
- GET static file thành công.
- Không cho phép origin ngoài allowlist.
- HTML content và content type.

Một vài header như `Vary` có thể gồm nhiều values; khi muốn kiểm `Origin`, dùng match contains thay vì giả định chỉ một dòng và thứ tự cố định.

### 17.4. Chạy dự án

Ở folder project có Gradle wrapper hợp lệ:

~~~bash
./gradlew test
./gradlew bootRun
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat test
.\gradlew.bat bootRun
~~~

Nếu project chưa có Gradle wrapper, dùng bản Gradle đang cài để tạo wrapper phù hợp; đừng nghĩ các file `settings.gradle` và `build.gradle` tự sinh `gradlew`. Demo trình bày đầy đủ source/build, không bao gồm wrapper binary/scripts.

## 18. Thử bằng curl và browser

### 18.1. Request CORS thành công

~~~bash
curl -i 'http://localhost:8080/api/public/catalog' \
  -H 'Origin: https://app.example.test'
~~~

Dự kiến HTTP 200 cùng `Access-Control-Allow-Origin: https://app.example.test`, Cache-Control `max-age=60`, ETag `"catalog-2026-a"`.

### 18.2. Revalidate catalog

~~~bash
curl -i 'http://localhost:8080/api/public/catalog' \
  -H 'Origin: https://app.example.test' \
  -H 'If-None-Match: "catalog-2026-a"'
~~~

Dự kiến HTTP 304 và body rỗng. `curl` không tự quản lý HTTP cache tương tự browser thông thường, nên khi trực tiếp gọi 304, đừng mong nó in lại JSON body đã nhận từ lần trước.

### 18.3. CORS preflight

~~~bash
curl -i -X OPTIONS \
  'http://localhost:8080/api/public/echo' \
  -H 'Origin: https://app.example.test' \
  -H 'Access-Control-Request-Method: POST' \
  -H 'Access-Control-Request-Headers: content-type,x-client-trace'
~~~

Dự kiến 200 với CORS preflight approval headers. Thử origin không được phép:

~~~bash
curl -i -X OPTIONS \
  'http://localhost:8080/api/public/echo' \
  -H 'Origin: https://evil.example.test' \
  -H 'Access-Control-Request-Method: POST'
~~~

Server WebFlux CORS processor dự kiến từ chối bằng 403. Nếu đặt thêm Spring Security hoặc gateway, có thể có thứ tự/layer error khác, cần test deployment thực.

### 18.4. Actual POST

~~~bash
curl -i -X POST \
  'http://localhost:8080/api/public/echo' \
  -H 'Origin: https://app.example.test' \
  -H 'Content-Type: application/json' \
  -H 'X-Client-Trace: sample' \
  -d '{"name":"An"}'
~~~

Dự kiến HTTP 200:

~~~json
{"greeting":"Hello, An"}
~~~

và `Cache-Control: no-store`. Lưu ý browser sẽ preflight cho request này trong ngữ cảnh cross-origin; curl không tự gửi OPTIONS trước.

### 18.5. Static files

~~~bash
curl -i 'http://localhost:8080/docs/guide.txt'
curl -i 'http://localhost:8080/'
~~~

`/docs/guide.txt` trả nội dung text file với max-age 300. `/` trả HTML từ static index.html. Không cần viết controller thủ công chỉ để phục vụ hai files này.

## 19. Debugging CORS bằng Chrome/Firefox DevTools

Khi browser báo “blocked by CORS policy”, hãy lần lượt:
1. Xác định **Origin thật** của frontend (scheme/host/port), không dùng URL backend thay.
2. Xem Network: browser có gửi OPTIONS preflight không?
3. Nếu có OPTIONS, kiểm HTTP status và `Access-Control-Allow-Origin/Methods/Headers/Max-Age`.
4. Kiểm CORS headers trên **actual response**, kể cả 304/401/403/500/error paths khi relevant.
5. Kiểm cookies có gửi không, `credentials` mode, `SameSite`, `Secure`, third-party cookie policy.
6. Với Spring Security, xác nhận CORS xử lý trước authentication/authorization.
7. Kiểm gateway/CDN có strip `Origin` hoặc response ACAO không.
8. Nếu response cacheable, kiểm `Vary: Origin`/cache key.
9. Kiểm CSP `connect-src` của frontend và TLS/mixed-content: chúng có thể chặn request độc lập CORS.
10. So sánh browser với curl OPTIONS/actual requests có đầy đủ headers tương ứng.

**CORS errors đôi khi che lỗi thực sự** như 401, 502 hoặc reverse proxy trả HTML error không có ACAO. Đừng chỉ thêm `Access-Control-Allow-Origin: *` toàn cục; hãy sửa upstream error path hoặc auth/CORS integration.

## 20. HTTP caching troubleshooting

| Triệu chứng | Nguyên nhân hay gặp | Hướng sửa |
| --- | --- | --- |
| Browser luôn tải lại JS dù unchanged | Không có freshness hoặc validator | Cache-Control + ETag/Last-Modified |
| JS mới deploy nhưng browser vẫn chạy bản cũ | URL không versioned, max-age quá dài | Content-hashed filenames hoặc freshness ngắn |
| HTML cũ trỏ tới JS đã bị xóa | Purge tài nguyên cũ quá sớm | Giữ assets cũ qua cửa sổ tương thích |
| 304 không có JSON body nên app báo parse error | HTTP client không có cache nhưng tự gửi If-None-Match | Không parse 304 như 200, dùng cache store đúng |
| Thay nội dung nhưng ETag không đổi | Validator gắn sai version/representation | Tính/đổi ETag cùng dữ liệu |
| Cùng URL hai ngôn ngữ bị cache nhầm | Thiếu `Vary: Accept-Language` hoặc CDN key sai | Correct Vary/custom cache key |
| CORS origin A thành origin B sau cache HIT | CDN bỏ qua `Vary: Origin` | Cấu hình Vary/cache key đúng |
| Private profile trả data user khác | `Cache-Control: public`/key không theo user | no-store/private + security review |
| GET public không được cache dù max-age | Request/response cache constraints, auth/cookie/CDN policy | Xem cache logs/headers và gateway rules |
| `no-cache` vẫn hiện trong browser storage | Hiểu nhầm no-cache | no-store nếu thực sự cấm lưu |
| 304 qua CDN nhưng ACAO mất | CDN/proxy rewrite headers | Test CORS 200/304 và preserve headers |
| Last-Modified sai lệch timestamp | File/JAR metadata hoặc server clocks | ETag phù hợp, kiểm resource source |
| Cached POST response không như mong đợi | Cache behavior của unsafe methods không tự như GET | Dùng HTTP semantics và policy cụ thể |
| Multiple Content-Encoding variants dùng sai ETag | Representation/validator không nhất quán | ETag/Vary theo bytes/semantics |
| Static resource handler không tìm file | Classpath location sai hoặc package resource thiếu | Kiểm JAR và addResourceLocations |
| `@EnableWebFlux` làm mất Boot behavior | Tự tiếp quản framework config | Bỏ annotation khi chỉ cần WebFluxConfigurer |
| Spring Boot chạy MVC thay vì WebFlux | Có cả starter-web và starter-webflux | Chọn đúng starter/application type |

### 20.1. `Vary` không giải quyết privacy tự thân

`Vary: Origin` tách variants theo origin. User Alice và Bob ở cùng một frontend origin, nên cache vẫn có thể trộn user-specific bodies nếu dùng một cache key chỉ gồm URI và Origin. Dữ liệu bí mật cần security + `private/no-store` đúng policy và kiểm CDN.

### 20.2. `Access-Control-Max-Age` không đảm bảo browser luôn cache đủ giây

Browser có thể cap, evict hoặc tách preflight cache theo network partition/security context. Không thiết kế hệ thống bắt buộc “OPTIONS chỉ một lần mỗi giờ”. Nếu proxy/edge muốn tối ưu preflight traffic, đo thực tế, đừng dựa vào giá trị cấu hình như một SLA.

## 21. Production checklist

- [ ] Biết frontend origins thực cho từng môi trường: dev/stage/prod, scheme/host/port.
- [ ] Chỉ allow origins cần thiết; không đặt credentials=true cùng wildcard origin.
- [ ] Allowed methods/headers/exposed headers là allowlist có mục đích, không mở tất cả mặc định.
- [ ] Preflight xử lý trước Security auth khi sử dụng credentials/Authorization.
- [ ] CORS không thay authentication, authorization, CSRF hay object ownership.
- [ ] Tránh trùng/chồng lấn `@CrossOrigin`, WebFluxConfigurer, CorsWebFilter và gateway.
- [ ] Kiểm actual + OPTIONS responses, cùng các 304/401/403/error paths.
- [ ] CDN/cache tôn trọng Origin/Vary và không serve private data cross-user.
- [ ] Có HTTP cache policy riêng cho API public, API private, HTML entrypoint và hashed assets.
- [ ] Content-hashed JS/CSS mới được cache max-age dài/immutable; giữ assets cũ khi deploy.
- [ ] Static resources nằm trong classpath đúng, resource handlers không expose private files.
- [ ] Không bật `@EnableWebFlux` nếu chỉ muốn mở rộng Boot defaults.
- [ ] Dùng `ResponseEntity.eTag`/`lastModified` nhất quán với representation thật.
- [ ] Kiểm If-None-Match/If-Modified-Since và behavior 304 body rỗng.
- [ ] 304 và cached response vẫn tôn trọng CORS + authorization.
- [ ] Không dùng no-cache đồng nghĩa no-store; chọn theo sensitivity.
- [ ] Không để raw private headers/cookies/tokens vào CDN logs hoặc cache metadata.
- [ ] Viết WebTestClient integration tests cho config và contract headers.
- [ ] Kiểm staging với gateway/CDN/browser thực, vì embedded tests không phản ánh mọi edge config.
- [ ] Giám sát CORS preflight failures, 304 ratio, cache HIT/MISS, stale responses và deployment cache busting.

### Câu hỏi tự kiểm tra

**1.** Origin trong CORS gồm những phần nào?

**Trả lời:** Scheme, host và port (kể cả cổng mặc định theo URL semantics). Path không là một phần của origin.

**2.** CORS preflight có phải request POST thật không?

**Trả lời:** Không. Browser gửi OPTIONS để hỏi server method/headers dự định có được chấp nhận cross-origin không, rồi mới gửi actual request khi hợp lệ.

**3.** Vì sao `Access-Control-Allow-Origin: *` không dùng cùng credentialed CORS?

**Trả lời:** Browser CORS rules không cho wildcard ACAO trong credentialed responses; phải dùng origin cụ thể được phép và `Access-Control-Allow-Credentials: true` khi phù hợp.

**4.** `Access-Control-Max-Age` có giống `Cache-Control: max-age` không?

**Trả lời:** Không. Header thứ nhất về browser preflight permission cache; thứ hai về freshness HTTP representations.

**5.** `Cache-Control: no-cache` có cấm lưu body không?

**Trả lời:** Không. Nó cho lưu nhưng phải revalidate trước reuse. `no-store` mới yêu cầu không lưu trong HTTP caches tuân thủ.

**6.** `ETag` đem lại điều gì khi có `If-None-Match`?

**Trả lời:** Client/cache revalidate; nếu representation chưa đổi thì server có thể trả 304 không có body, giúp tránh truyền lại payload.

**7.** Tại sao tài nguyên hashed có thể cache lâu hơn `index.html`?

**Trả lời:** URL chứa content hash đổi khi bytes đổi; browser có thể coi asset URL cũ immutable. Entrypoint index.html cần được cập nhật để trỏ tới phiên bản asset mới.

**8.** Dùng `@EnableWebFlux` trong mọi Boot WebFlux app có nên không?

**Trả lời:** Không. Khi chỉ muốn bổ sung config, dùng `@Configuration implements WebFluxConfigurer` không có `@EnableWebFlux` để giữ Boot auto-config.

**9.** CORS cho `/api/public/**` có tự áp dụng cho `/docs/**` không?

**Trả lời:** Không. Path mapping cần được định nghĩa cho docs/assets riêng nếu cross-origin browser JS phải truy cập.

**10.** Một GET authenticated có `Vary: Origin` đã an toàn cho CDN shared caching chưa?

**Trả lời:** Chưa. Origin không đại diện cho user/tenant; authorization và private/no-store caching policy phải độc lập.

**11.** Khi body đã được browser cache fresh, nó có phải gửi `If-None-Match` không?

**Trả lời:** Không nhất thiết. Fresh cache có thể được dùng trực tiếp. Khi cần revalidate, client có thể gửi conditional request.

## 22. Tài liệu chính thức và chuẩn HTTP

- [Spring Framework — WebFlux CORS](https://docs.spring.io/spring-framework/reference/web/webflux-cors.html): `@CrossOrigin`, `CorsRegistry`, CorsWebFilter, credentials, origins.
- [Spring Framework — WebFlux Configuration](https://docs.spring.io/spring-framework/reference/web/webflux/config.html): `WebFluxConfigurer`, static resources, `ResourceHandlerRegistry`, resource chain.
- [Spring Framework — WebFlux HTTP Caching](https://docs.spring.io/spring-framework/reference/web/webflux/caching.html): `CacheControl`, `ResponseEntity.eTag`, `Last-Modified`, 304.
- [Spring Framework — WebFlux ResponseEntity](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/responseentity.html): status/headers/body sync và reactive combinations.
- [Spring Boot 3.3 — Reactive Web Applications](https://docs.spring.io/spring-boot/3.3/reference/web/reactive.html): auto configuration, static paths, web application type.
- [Spring Security — Reactive CORS Integration](https://docs.spring.io/spring-security/reference/reactive/integrations/cors.html): preflight trước security, CorsWebFilter và security integration.
- [Spring Framework — ResourceHandlerRegistration Javadoc 6.1](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/reactive/config/ResourceHandlerRegistration.html): add locations, cache control và resource chain.
- [Spring Framework — CacheControl Javadoc 6.1](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/http/CacheControl.html): maxAge/noStore/noCache/cachePublic/cachePrivate.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html): conditional requests, validators, 304, 412, ETag.
- [RFC 9111 — HTTP Caching](https://www.rfc-editor.org/rfc/rfc9111.html): Cache-Control, shared/private caches, Vary, freshness, revalidation.
- [MDN — Cross-Origin Resource Sharing](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS): preflight, ACAO, credentials và browser behavior.
- [MDN — HTTP Caching](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Caching): fresh/stale, validators, cache busting.
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html): reactive HTTP integration tests.

**Ghi nhớ:** CORS quản lý **quyền đọc cross-origin trong browser**, static resource handlers quản lý **file-to-URL mapping**, HTTP caching quản lý **lưu/tái sử dụng/revalidate representation**. Chúng cùng xuất hiện trong Spring WebFlux nhưng giải quyết ba vấn đề độc lập. Hãy dùng cấu hình origins có kiểm soát, quản lý tài nguyên tĩnh qua WebFluxConfigurer, versioned assets khi cache dài và `ResponseEntity`/`CacheControl`/`ETag` cho API; kiểm chứng bằng WebTestClient cùng browser/CDN tests khi triển khai thật.
