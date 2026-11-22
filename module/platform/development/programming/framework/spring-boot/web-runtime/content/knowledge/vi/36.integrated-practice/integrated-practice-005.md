# Phục vụ giao diện, tài nguyên có phiên bản và chính sách cache trong Spring Boot

## 1. Bài thực hành tổng hợp và yêu cầu đầu ra

Giả sử một Spring Boot service vừa phục vụ **trang HTML** cho người dùng, vừa trả về **CSS, JavaScript, hình ảnh** và một số **JSON API**. Trong mỗi lần deploy, nội dung CSS/JS có thể thay đổi. Trình duyệt có thể giữ một tệp trong cache vài phút, vài tháng hoặc một năm; CDN và reverse proxy cũng có cache riêng. Nếu đặt cùng một chính sách cache cho tất cả URL, có thể xảy ra hai lỗi trái ngược:

- **Cache quá yếu:** mỗi lần mở trang browser lại tải CSS/JS không thay đổi, làm tăng latency/bandwidth.
- **Cache quá mạnh ở URL không có version:** sau deploy HTML mới nhưng browser vẫn dùng CSS cũ; giao diện bị lỗi, client chạy JavaScript không tương thích API hoặc bị kẹt sau khi rollback.

Còn một lỗi nghiêm trọng hơn: một response HTML/API **cá nhân hóa** có thể bị cache bởi shared CDN nếu dùng `Cache-Control: public` một cách vô ý.

Bài thuộc nhóm **Thực hành tổng hợp** trong module **Spring Boot - web-runtime**. Mục tiêu là xây một mini website Spring Boot **Java 17+, Spring Boot 3.3.13, Spring MVC + Thymeleaf**, có hợp đồng cụ thể:

1. `GET /` trả HTML với `Cache-Control: no-cache` (bản demo HTML chung, không chứa dữ liệu cá nhân).
2. HTML tham chiếu CSS/JS bằng đường dẫn **được gắn content hash**: ví dụ dạng `/assets/css/site-<md5>.css`, không hardcode chuỗi hash.
3. Các URL asset có hash hợp lệ có header `Cache-Control: public, max-age=31536000, immutable`.
4. URL asset **không có hash** (nếu vẫn truy cập được) trả `Cache-Control: no-cache`, tránh cache sai phiên bản.
5. `GET /api/catalog` trả JSON với validator `ETag` và chính sách revalidate; gửi `If-None-Match` phù hợp sẽ nhận `304 Not Modified` không có body.
6. `GET /api/account-preview` minh họa response không được lưu bởi shared/private caches với `Cache-Control: private, no-store`.
7. Có **integration tests qua embedded server thật** (`@SpringBootTest(RANDOM_PORT)` và JDK `HttpClient`), không chỉ unit test controller.
8. Có checklist deploy qua CDN/NGINX/SPA và phép thử **thay asset ở phiên bản mới** để phát hiện cache stale.

**Quan trọng:** ví dụ chỉ là web demo để học header và resource chain, chưa có authentication, CSRF, CSP production hoàn chỉnh hoặc user-specific business state. Không công khai `/api/account-preview` với dữ liệu thực nếu chưa có Spring Security và authorization. Các tests được thiết kế để chạy được; tài liệu không tuyên bố đã thực thi Gradle/HTTP trong môi trường biên soạn.

## 2. Bốn lớp cache rất dễ nhầm

```text
                    GET /
Browser
 ├── HTTP cache: HTML/JS/CSS, ETag, max-age
 └── Service worker Cache Storage (nếu app có)
           │
           ▼
CDN / reverse proxy
 └── Shared HTTP cache: s-maxage, public/private, Vary, cache key
           │
           ▼
Spring Boot embedded server
 ├── ResourceHttpRequestHandler phục vụ static files
 ├── Resource chain resolver/cache (trong JVM)
 ├── Thymeleaf template cache (compiled template)
 └── @Cacheable/application data cache (nếu có)
           │
           ▼
DB / Object storage
```

| Tầng cache | Ví dụ | Có bị điều khiển trực tiếp bởi HTTP Cache-Control không? |
|---|---|---|
| Browser HTTP cache | Lưu response CSS/JS/HTML | **Có**, theo HTTP caching semantics |
| CDN/reverse proxy cache | Cache shared response ở edge | **Có**, kết hợp cấu hình riêng của CDN |
| Service Worker Cache Storage | `caches.open("v5")` | **Không tự động**; service worker JS kiểm soát theo code |
| Spring MVC resource chain cache | `spring.web.resources.chain.cache=true` | **Không trực tiếp**; cache nội bộ resolution/metadata |
| Thymeleaf template cache | `spring.thymeleaf.cache=true` | **Không**; cache template parsing, không phải browser |
| Spring Cache abstraction | `@Cacheable` cho service/data | **Không tự động**; tách hoàn toàn HTTP response cache |

Bất kỳ chiến lược nào muốn tránh stale UI phải biết **đang điều khiển tầng nào**. `spring.thymeleaf.cache=false` giúp dev thấy thay đổi template nhanh hơn, nhưng **không làm browser bỏ cache JavaScript**. `@CacheEvict` xóa một key Redis không xóa CSS đã lưu tại browser. `spring.web.resources.chain.cache` tối ưu resolver nội bộ, không thay cho `Cache-Control`.

## 3. Tại sao URL cần mang version?

Giả sử file có đường dẫn cố định:

```text
/assets/css/site.css
```

Ngày 1 CSS có màu xanh, ngày 2 CSS đổi sang tím. Nếu browser đã lưu `/assets/css/site.css` với `max-age=31536000`, nó có thể tiếp tục dùng bản xanh đến khi cache được làm mới; deploy code mới **không buộc browser tải lại** một URL đang fresh.

Chiến lược tốt hơn:

```text
Ngày 1: /assets/css/site-a1b2...c3d4.css
Ngày 2: /assets/css/site-9f8e...7a6b.css
```

Tên ở trên **chỉ minh họa định dạng**, không phải hash thật của tệp demo. Khi nội dung đổi, URL đổi; browser coi đây là tài nguyên mới và tải bản mới. Những tệp cũ có hash vẫn an toàn để giữ trong cache lâu vì nội dung gắn với URL bất biến.

Có hai khái niệm khác nhau:

- **Content-based version:** hash tính từ nội dung tệp, ví dụ Spring Framework `ContentVersionStrategy` dùng **MD5** 32 ký tự hex cho định danh URL. Nội dung không đổi → hash không đổi; đổi một byte → thường hash đổi.
- **Fixed version:** thêm nhãn version release, ví dụ `/v2026-11-08/js/app.js`, thay nhãn khi release mới. Chiến lược này phù hợp trong một số bối cảnh JavaScript module loaders, hoặc khi build pipeline tạo URL/manifest theo release.

**Content hash dùng để invalidation**, không phải biện pháp integrity/authentication chống thay đổi độc hại: MD5 dùng làm version URL không tương đương kiểm chứng chữ ký hoặc `Subresource Integrity` (SRI). Với asset từ CDN bên thứ ba, cân nhắc `integrity="sha384-..."`, `crossorigin` và CSP phù hợp.

### 3.1. Hợp đồng quan trọng

Muốn cache dài hạn theo immutable, **mỗi URL đã có hash không được phục vụ bytes thay đổi**. Không tái sử dụng cùng một `site-a1...css` cho nội dung khác. Nên coi hashed assets như artifacts immutable trong object storage/CDN.

Sau deploy, HTML mới phải trỏ tới URL mới; HTML cũ đã được browser lưu cũng có thể tiếp tục trỏ tới hashed asset cũ. Vì vậy cần **giữ asset từ release cũ trong một khoảng rollout/rollback** hoặc dùng CDN/object storage duy trì chúng. Nếu artifact server mới chỉ mang asset mới và xóa bản cũ, client đang giữ HTML cũ có thể gặp 404 khi tải asset cũ dù URL có hash đúng.

## 4. Cache-Control: no-cache, no-store, private, public và immutable

Một response có thể có header:

```http
Cache-Control: public, max-age=31536000, immutable
```

Hiểu đúng các directive:

| Directive | Ý nghĩa thực tế |
|---|---|
| `max-age=600` | Response được coi là fresh trong tối đa 600 giây kể từ thời điểm phù hợp theo HTTP cache rules |
| `public` | Shared caches có thể lưu khi các điều kiện khác cho phép; **chỉ dùng cho dữ liệu thật sự dùng chung** |
| `private` | Chỉ private cache của một user agent được lưu; shared CDN không được lưu response này |
| `no-cache` | **Được lưu**, nhưng không được tái sử dụng mà chưa revalidate với origin |
| `no-store` | Cache tuân chuẩn không được lưu response; phù hợp nội dung nhạy cảm |
| `must-revalidate` | Khi stale, không dùng lại nếu chưa revalidate thành công; điều kiện áp dụng theo RFC |
| `immutable` | Khi response còn fresh, client hỗ trợ directive không cần revalidate vì URL đại diện cho nội dung bất biến |
| `s-maxage=...` | Freshness dành cho shared caches, có thể khác max-age của browser |
| `stale-while-revalidate=...` | Một số caches được phép trả stale trong lúc revalidate theo directive |
| `Vary: Accept-Encoding` | Cache key còn phụ thuộc request header, giúp phân biệt các biểu diễn gzip/br/identity |

**No-cache không phải no-store.** Đây là hiểu lầm phổ biến nhất: `no-cache` yêu cầu kiểm tra lại trước khi dùng, trong khi `no-store` là chính sách không lưu. Một HTML catalog chung có thể dùng `no-cache`; trang quản trị có token/PII cần xem xét `private, no-store`. Tuy nhiên `no-store` mới được thêm **không bảo đảm xóa ngay dữ liệu từng được cache theo chính sách cũ**; cần kiểm soát migration/cache purge và rủi ro đã tồn tại.

**Không tùy tiện dùng `public` trên nội dung có `Set-Cookie`, Authorization, user ID, giỏ hàng, tài liệu riêng.** Shared cache có thể vô tình trả nội dung của user A cho user B nếu cache key và policy không đúng.

### 4.1. Ma trận policy được đề xuất

| Loại tài nguyên | URL | Policy gợi ý | Lý do |
|---|---|---|---|
| HTML chung của website | `/` | `no-cache` | Mỗi navigation phải revalidate, tránh giữ giao diện cũ |
| HTML/account cá nhân | `/me` | `private, no-store` | Không lưu dữ liệu nhạy cảm |
| CSS/JS/images có fingerprint | `/assets/site-<hash>.css` | `public, max-age=31536000, immutable` | URL đổi khi bytes đổi |
| CSS/JS chưa fingerprint | `/assets/site.css` | `no-cache` hoặc freshness rất ngắn | Tránh stale khi deploy |
| JSON catalog dùng chung | `/api/catalog` | `public, max-age=0, must-revalidate` + ETag | Revalidation tiết kiệm body |
| JSON access token/profile | `/api/profile` | `private, no-store` | Bảo vệ quyền riêng tư |
| Health/readiness | `/actuator/health/readiness` | Thường không cache hoặc theo infra policy | Tránh kết quả health stale |
| Redirect dài hạn `301/308` | URL canonical | Có kiểm soát | Browser/proxy có thể cache redirect rất lâu |
| Error 404/5xx | Tùy loại | Tránh cache bất ngờ | CDN có thể có negative caching/override |

Đây là **policy minh họa**. Với một API public có high traffic, có thể chọn `s-maxage=60` và browser revalidate; với trang real-time, có thể phải no-store; với assets không version, không bao giờ đặt cache immutable rất dài trừ khi chấp nhận đường dẫn thực sự bất biến.

## 5. Spring Boot 3.3 phục vụ static resources thế nào?

Với Spring Boot MVC auto-configuration, static resources thường được tìm ở các vị trí:

```text
classpath:/META-INF/resources/
classpath:/resources/
classpath:/static/
classpath:/public/
```

Trong project demo ta dùng `src/main/resources/static/`. Nếu đặt:

```text
src/main/resources/static/assets/css/site.css
src/main/resources/static/assets/js/app.js
```

Thì URL không có version (nếu default resource mappings bật) là:

```text
/assets/css/site.css
/assets/js/app.js
```

Properties quan trọng:

```properties
# Bật resolver chain; có thể được bật khi một strategy được enable.
spring.web.resources.chain.enabled=true

# Sinh path có MD5 của nội dung:
spring.web.resources.chain.strategy.content.enabled=true
spring.web.resources.chain.strategy.content.paths=/**

# Tối ưu resolver cache trong JVM; không phải HTTP TTL:
spring.web.resources.chain.cache=true
```

Theo Spring Boot **3.3 Servlet Web Applications**, Thymeleaf/FreeMarker được auto-configure `ResourceUrlEncodingFilter` để các URL do template tạo được rewrite bằng resource chain. Với JSP cần khai báo filter theo hướng dẫn; template engine khác cần helper/macro hoặc `ResourceUrlProvider` riêng.

**Không hardcode MD5 vào HTML template.** Thymeleaf:

```html
<link rel="stylesheet" th:href="@{/assets/css/site.css}">
<script defer th:src="@{/assets/js/app.js}"></script>
```

Ở runtime, tài nguyên đi qua content strategy và URL có dạng `/assets/css/site-<32-hex>.css`. Những đường dẫn mới được `ResourceHttpRequestHandler`/`VersionResourceResolver` tra về đúng tệp gốc. Nếu template xuất thẳng `href="/assets/css/site.css"` (không đi qua URL rewriting), trình duyệt sẽ yêu cầu URL không fingerprinted và policy cache dài hạn có thể gây lỗi.

**Lưu ý CSS/ES modules:** CSS `url(...)` và JavaScript dynamic imports/module loaders có thể cần pipeline biến đổi riêng. Spring docs chỉ ra ContentVersionStrategy có ngoại lệ đối với JavaScript module loader; dùng build manifest/fixed version strategy và kiểm thử deep imports khi cần. Demo cố ý dùng một file CSS và một JS đơn giản, không giả định mọi liên kết lồng nhau tự được rewrite.

### 5.1. Các property HTTP cache của Spring Boot là global cho static resource handler

Ví dụ:

```properties
spring.web.resources.cache.cachecontrol.max-age=365d
spring.web.resources.cache.cachecontrol.cache-public=true
```

Những property này áp policy cho **static resource handler được Boot cấu hình**, thường **bao gồm cả URL không có hash** nếu cùng handler. Vì vậy chỉ bật toàn cục 365 ngày khi bạn đã kiểm soát/đóng toàn bộ đường unversioned hoặc chấp nhận rủi ro của chúng.

Trong demo sau, ta **không** đặt `spring.web.resources.cache.cachecontrol.max-age=365d` global. Thay vào đó dùng **filter kiểm tra URL có đúng content fingerprint do resource chain tính hay không**; chỉ các URL đúng fingerprint mới có lifetime dài. Đây là một cách thực hành khi muốn giải thích tường minh policy hai nhóm URL. Với hệ thống nhiều assets, production nên cân nhắc build manifest + CDN rules/ResourceHandler riêng, để tránh lookup hash mỗi request.

## 6. Kiến trúc project thực hành

Ta tạo một Spring Boot MVC + Thymeleaf project với:
- `HomeController` trả view, HTML có Cache-Control no-cache.
- `CatalogController` trả JSON với `ETag` và revalidation.
- `AccountPreviewController` trả response no-store, chỉ chứa dữ liệu demo.
- `AssetCachePolicyFilter` phân biệt URL có hash được resolver xác nhận và URL thường.
- `src/main/resources/static/assets/css/site.css` và `js/app.js`.
- `src/main/resources/templates/home.html` dùng Thymeleaf URL expressions.
- Tests gửi HTTP thật để xác nhận rendering, hash, cache policy và 304.

```text
spring-cache-site-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/com/example/sitecache/
    │   │   └── SiteCacheApplication.java
    │   └── resources/
    │       ├── application.properties
    │       ├── templates/home.html
    │       └── static/assets/
    │           ├── css/site.css
    │           └── js/app.js
    └── test/
        └── java/com/example/sitecache/
            └── SiteCacheHttpTest.java
```

### 6.1. Gradle và Java 17

**`settings.gradle`:**

```groovy
rootProject.name = 'spring-cache-site-demo'
```

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
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
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-thymeleaf'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Không thêm `spring-boot-starter-webflux` vào demo MVC. `WebClient` có thể dùng trong MVC nếu cần, nhưng yêu cầu bài này là phục vụ view + static resources bằng Servlet MVC và thực hành conditional HTTP caching.

### 6.2. application.properties

**`src/main/resources/application.properties`:**

```properties
spring.application.name=spring-cache-site-demo
server.port=8080

# Cho Boot MVC map static resources mặc định.
spring.web.resources.add-mappings=true

# Content-hash URLs cho CSS/JS.
spring.web.resources.chain.enabled=true
spring.web.resources.chain.strategy.content.enabled=true
spring.web.resources.chain.strategy.content.paths=/**
spring.web.resources.chain.cache=true

# Không đặt HTTP cache một năm toàn cục:
# spring.web.resources.cache.cachecontrol.max-age=365d

# Production template parsing có thể cache.
# Trong lúc phát triển có thể set false:
spring.thymeleaf.cache=true

# Demo không công khai internal error details.
server.error.include-message=never
server.error.include-stacktrace=never
```

**Cần phân biệt:** `spring.web.resources.chain.cache=true` là **cache kết quả resource resolver**, không phải browser Cache-Control. Trong dev, khi chỉnh tệp trực tiếp trên disk của một app JVM đang chạy, resolver cache và Thymeleaf template cache có thể khiến bạn chưa thấy thay đổi ngay; build/restart hoặc cấu hình dev đúng, không suy từ đó rằng content strategy sai.

## 7. Toàn bộ mã Java của ứng dụng

**`src/main/java/com/example/sitecache/SiteCacheApplication.java`:**

```java
package com.example.sitecache;

import java.io.IOException;
import java.util.List;
import java.util.Map;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpHeaders;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Component;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.filter.OncePerRequestFilter;
import org.springframework.web.servlet.resource.ResourceUrlProvider;

@SpringBootApplication
public class SiteCacheApplication {

    public static void main(String[] args) {
        SpringApplication.run(SiteCacheApplication.class, args);
    }
}

@Controller
class HomeController {

    @GetMapping("/")
    String home(Model model, HttpServletResponse response) {
        // Demo HTML dùng chung; no-cache cho phép storage
        // nhưng buộc revalidate trước mỗi lần dùng lại.
        response.setHeader(HttpHeaders.CACHE_CONTROL, "no-cache");
        model.addAttribute("pageTitle", "Giao diện có phiên bản");
        return "home";
    }
}

@RestController
class ApiController {

    @GetMapping("/api/catalog")
    ResponseEntity<List<String>> catalog() {
        // Catalog demo cố định. Khi dữ liệu thay đổi trong
        // production, ETag PHẢI thay theo representation.
        return ResponseEntity.ok()
                .eTag("\"catalog-rev-1\"")
                .header(HttpHeaders.CACHE_CONTROL,
                        "public, max-age=0, must-revalidate")
                .body(List.of("book", "pen"));
    }

    @GetMapping("/api/account-preview")
    ResponseEntity<Map<String, String>> accountPreview() {
        // Chỉ trả dữ liệu demo, chưa có auth.
        // Production: bảo vệ route trước khi trả user data.
        return ResponseEntity.ok()
                .header(HttpHeaders.CACHE_CONTROL,
                        "private, no-store")
                .body(Map.of("state", "demo-only"));
    }
}

@Component
@Order(Ordered.HIGHEST_PRECEDENCE + 20)
class AssetCachePolicyFilter extends OncePerRequestFilter {

    private static final String CSS =
            "/assets/css/site.css";
    private static final String JS =
            "/assets/js/app.js";

    private final ResourceUrlProvider urlProvider;

    AssetCachePolicyFilter(ResourceUrlProvider urlProvider) {
        this.urlProvider = urlProvider;
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain)
            throws ServletException, IOException {

        String contextPath = request.getContextPath();
        String requestUri = request.getRequestURI();
        String path = requestUri.substring(contextPath.length());

        if (path.startsWith("/assets/")) {
            String cssVersioned =
                    urlProvider.getForLookupPath(CSS);
            String jsVersioned =
                    urlProvider.getForLookupPath(JS);

            boolean fingerprintMatches =
                    path.equals(cssVersioned)
                    || path.equals(jsVersioned);

            if (fingerprintMatches) {
                // Chỉ các URL được resource resolver sinh ra
                // từ nội dung HIỆN TẠI mới được cache rất lâu.
                response.setHeader(
                        HttpHeaders.CACHE_CONTROL,
                        "public, max-age=31536000, immutable");
            } else {
                // URLs không hash hoặc hash không hợp lệ
                // không có cache TTL dài do filter này.
                response.setHeader(
                        HttpHeaders.CACHE_CONTROL, "no-cache");
            }
        }

        filterChain.doFilter(request, response);
    }
}
```

**Các bảo đảm và giới hạn của mã:**

1. Một file Java có duy nhất `public class SiteCacheApplication` đúng tên file; `HomeController`, `ApiController`, `AssetCachePolicyFilter` package-private ở cùng package, được Spring component scan.
2. Filter chỉ chạm path bắt đầu `/assets/`. HTML và JSON endpoints nhận cache policy riêng từ controller.
3. `ResourceUrlProvider` lấy URL có version mà Spring resource chain thực sự resolve; filter so sánh **toàn bộ path chính xác**, không tin riêng regex `-<32 hex>` từ client.
4. Hash URL bất kỳ không khớp canonical asset của demo sẽ **không** được đánh dấu immutable; resource handler thường trả 404 khi hash sai. Điều này giảm nguy cơ cache 404 mãi trong thử nghiệm.
5. Demo chỉ có **hai assets được liệt kê**. Khi thêm hàng trăm files, đừng liệt kê tay trong filter: chuyển sang build asset manifest, verified hash registry/CDN policy hoặc resource handlers tách biệt. Đây là một giới hạn thiết kế **được nêu tường minh**, không phải full asset pipeline production.
6. `requestUri.substring(contextPath.length())` dùng URI path khi app chạy dưới root context path mặc định. Nếu ứng dụng chạy sau servlet path mapping hoặc proxy prefix phức tạp, cần xác định URL canonical theo cấu hình và kiểm thử `server.servlet.context-path` cùng trusted forwarded headers. Không tin `X-Forwarded-Prefix` do client tự gửi.
7. Header được set trước khi servlet resource handler ghi nội dung. Demo không cấu hình static handler `CacheControl` toàn cục để tránh handler chồng một TTL khác; integration tests sẽ xác minh giá trị đã gửi.
8. Với error 404, response/handler/container có thể có cơ chế ghi cache headers riêng. Production phải kiểm thử negative caching policy ở CDN; đừng giả định một filter ở app kiểm soát mọi CDN 404.
9. Đường dẫn resources phải **không bị sửa nội dung tại cùng URL hashed**. `ContentVersionStrategy` dùng MD5 cho versioning, không chứng minh an toàn nội dung/SRI.
10. Controller `catalog` dùng `ResponseEntity.eTag(...)`. Spring MVC kiểm tra conditional headers theo `HttpEntityMethodProcessor` và có thể trả 304 khi `If-None-Match` khớp; JDK HTTP tests xác minh cơ chế này qua network thực.
11. `/api/account-preview` chưa xác thực nên không chứa PII. Cấu hình `private,no-store` không thay thế Spring Security hoặc authorization.

**Điểm cần hiểu về thứ tự filters:** Spring Boot auto-configures `ResourceUrlEncodingFilter` cho Thymeleaf trong MVC. Filter cache ở demo không tự tạo URL fingerprint; nó chỉ đặt chính sách dựa trên URL do `ResourceUrlProvider` sinh ra. Trong thực tế, hãy xác minh bằng một HTTP test rằng template rewriting đã thành công trước khi đặt cache TTL dài.

## 8. Thymeleaf view: HTML tham chiếu nguồn nhưng browser nhận URL có hash

**`src/main/resources/templates/home.html`:**

```html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <meta name="viewport"
          content="width=device-width, initial-scale=1">
    <title th:text="${pageTitle}">Trang demo</title>

    <!-- Thymeleaf + ResourceUrlEncodingFilter rewrite URL -->
    <link rel="stylesheet"
          th:href="@{/assets/css/site.css}">
    <script defer th:src="@{/assets/js/app.js}"></script>
</head>
<body>
<main>
    <h1 th:text="${pageTitle}">Giao diện có phiên bản</h1>
    <p>HTML được revalidate, CSS và JS có URL fingerprint.</p>
    <p id="status">JavaScript chưa chạy.</p>
    <a href="/api/catalog">Xem danh mục JSON</a>
</main>
</body>
</html>
```

Chú ý cú pháp Thymeleaf: `th:text="${pageTitle}"` là attribute expression, `th:href="@{/assets/css/site.css}"` là URL expression. Khi template được render qua Thymeleaf và URL encoding filter, link có thể trở thành:

```html
<link rel="stylesheet"
      href="/assets/css/site-<md5-của-nội-dung>.css">
```

Đường dẫn trên là **mô tả định dạng**, không phải HTML thực tế để copy; mã HTML sẽ chứa **32 ký tự hexadecimal** thay placeholder nếu resource chain hoạt động. Không cần tự sửa template mỗi lần CSS đổi.

**Nếu test thấy `href="/assets/css/site.css"` không đổi**, kiểm tra:
- Boot đã load `spring-boot-starter-thymeleaf` và render template bằng Thymeleaf?
- Spring MVC thật hay WebFlux?
- Content version strategy đã bật và paths khớp?
- Link có dùng `th:href`/URL helper đi qua `encodeURL`?
- `ResourceUrlEncodingFilter` có được đăng ký trong filter chain?
- Resource thực sự tồn tại tại classpath static location?
- Context path/proxy path rewrite có làm resource lookup path khác?
- Có tự định nghĩa WebMvcConfigurer/resource handlers vô tình ghi đè resource chain của Boot?

## 9. CSS và JavaScript thực tế

**`src/main/resources/static/assets/css/site.css`:**

```css
:root {
    --brand: #2351a4;
    color-scheme: light;
}
body {
    font-family: system-ui, Arial, sans-serif;
    margin: 2rem auto;
    max-width: 52rem;
    line-height: 1.6;
}
main {
    border-top: 0.35rem solid var(--brand);
    padding-top: 1rem;
}
h1 {
    color: var(--brand);
}
```

**`src/main/resources/static/assets/js/app.js`:**

```javascript
"use strict";

document.addEventListener("DOMContentLoaded", () => {
    const target = document.querySelector("#status");
    if (target) {
        target.textContent = "JavaScript đã tải từ tài nguyên phiên bản.";
    }
});
```

Không dùng external libraries hay dynamic import trong demo; chỉ cần hai static files đủ quan sát:
- CSS có `--brand` giúp kiểm chứng bytes và hash khi đổi màu.
- JS cập nhật `#status` sau DOM load; việc browser đã chạy JS có thể xác minh qua E2E browser test, nhưng HTTP tests không được giả làm browser.
- Nội dung hai tệp không có dữ liệu cá nhân, nên có thể đặt `public, immutable` cho URL **đúng hash**.
- Nếu thêm fonts/images, phải xác định cross-origin policy, content type, CORS và caching riêng.

## 10. Khởi động và kiểm tra thủ công bằng curl

Yêu cầu JDK 17+, Gradle tương thích Boot 3.3.13:

```bash
gradle bootRun
```

Nếu có Gradle Wrapper, dùng `./gradlew bootRun` trên Linux/macOS hoặc `.\gradlew.bat bootRun` trên Windows PowerShell.

### 10.1. HTML

```bash
curl -sS -i http://localhost:8080/
```

Kỳ vọng:
- HTTP 200.
- `Content-Type` HTML (có thể kèm charset).
- `Cache-Control: no-cache`.
- HTML chứa `/assets/css/site-<32hex>.css` và `/assets/js/app-<32hex>.js`.

Không ghi hash “thật” trong tài liệu vì nó phụ thuộc byte-for-byte nội dung file. Hash thay khi thêm newline/sửa encoding, và có thể khác nếu build tool transform/minify.

### 10.2. Lấy CSS URL do server render rồi request

Trên Linux/macOS với `grep -E`:

```bash
curl -sS http://localhost:8080/ -o home.html

ASSET=$(grep -oE \
  '/assets/css/site-[0-9a-f]{32}\.css' home.html \
  | head -n 1)

echo "$ASSET"
curl -i "http://localhost:8080$ASSET"
```

Nếu không tìm được `ASSET`, **không kết luận curl hỏng**; quay lại kiểm tra template auto URL rewriting và resource chain.

Kỳ vọng với URL hợp lệ:
- HTTP 200.
- CSS bytes chứa `--brand`.
- `Cache-Control: public, max-age=31536000, immutable`.

### 10.3. URL không có hash

```bash
curl -i http://localhost:8080/assets/css/site.css
```

Kỳ vọng HTTP 200 và `Cache-Control: no-cache`. Đừng để một URL được tái sử dụng như `site.css` có `max-age=31536000`, nếu nội dung của nó có thể thay đổi ở deploy tiếp theo.

### 10.4. API có ETag

```bash
curl -i http://localhost:8080/api/catalog

curl -i \
  -H 'If-None-Match: "catalog-rev-1"' \
  http://localhost:8080/api/catalog
```

Kỳ vọng:
- Request đầu HTTP 200 + JSON `["book","pen"]`, header `ETag: "catalog-rev-1"` và policy `public, max-age=0, must-revalidate`.
- Request sau có `If-None-Match` khớp → HTTP **304 Not Modified**, body rỗng. 304 cho phép client dùng representation đã lưu nếu có; curl đơn giản chỉ hiển thị 304, **không tự ghép lại body cũ như browser cache**.
- Đổi `If-None-Match` thành `"catalog-rev-other"` → HTTP 200 và body đầy đủ.

### 10.5. API nhạy cảm về policy cache

```bash
curl -i http://localhost:8080/api/account-preview
```

Kỳ vọng HTTP 200, JSON `{"state":"demo-only"}` và `Cache-Control: private, no-store`. Đây là preview vô danh; trong production **phải có authentication/authorization** nếu thay bằng dữ liệu tài khoản thực.

## 11. Integration tests dùng web server thật

Một test chỉ gọi `HomeController.home(...)` trực tiếp sẽ không chứng minh resource version URL được Thymeleaf render. `MockMvc` có thể kiểm tra phần MVC, nhưng chúng ta muốn chứng minh cả embedded server, resource handler, HTTP headers, conditional request và static bytes.

Dùng `@SpringBootTest(webEnvironment=RANDOM_PORT)` để khởi động Tomcat thật trên port ngẫu nhiên. `@LocalServerPort` inject port của instance test; `java.net.http.HttpClient` gửi request qua localhost như một HTTP client thực.

**`src/test/java/com/example/sitecache/SiteCacheHttpTest.java`:**

```java
package com.example.sitecache;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class SiteCacheHttpTest {

    @LocalServerPort
    int port;

    private final HttpClient client = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(3))
            .build();

    private HttpRequest.Builder get(String path) {
        return HttpRequest.newBuilder(
                URI.create("http://127.0.0.1:" + port + path))
                .timeout(Duration.ofSeconds(5))
                .GET();
    }

    private HttpResponse<String> send(String path)
            throws Exception {
        return client.send(
                get(path).build(),
                HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8));
    }

    private String header(
            HttpResponse<?> response, String name) {
        return response.headers()
                .firstValue(name).orElse("");
    }

    @Test
    void homeIsRevalidatedAndLinksAreContentVersioned()
            throws Exception {

        HttpResponse<String> response = send("/");
        assertThat(response.statusCode()).isEqualTo(200);
        assertThat(header(response, "Content-Type"))
                .contains("text/html");
        assertThat(header(response, "Cache-Control"))
                .isEqualTo("no-cache");

        assertThat(response.body()).contains(
                "Giao diện có phiên bản");
        assertThat(response.body())
                .containsPattern(
                        "/assets/css/site-[0-9a-f]{32}\\.css");
        assertThat(response.body())
                .containsPattern(
                        "/assets/js/app-[0-9a-f]{32}\\.js");
    }

    private String versionedCssFromHtml(String html) {
        Matcher matcher = Pattern.compile(
                "/assets/css/site-[0-9a-f]{32}\\.css")
                .matcher(html);
        assertThat(matcher.find()).isTrue();
        return matcher.group();
    }

    @Test
    void fingerprintedAssetIsPublicAndImmutable()
            throws Exception {

        String cssUrl = versionedCssFromHtml(
                send("/").body());

        HttpResponse<String> response = send(cssUrl);
        assertThat(response.statusCode()).isEqualTo(200);
        assertThat(header(response, "Content-Type"))
                .contains("text/css");
        assertThat(response.body()).contains("--brand");
        assertThat(header(response, "Cache-Control"))
                .contains("public")
                .contains("max-age=31536000")
                .contains("immutable");
    }

    @Test
    void unversionedAssetMustRevalidate()
            throws Exception {

        HttpResponse<String> response =
                send("/assets/css/site.css");

        assertThat(response.statusCode()).isEqualTo(200);
        assertThat(response.body()).contains("--brand");
        assertThat(header(response, "Cache-Control"))
                .isEqualTo("no-cache");
    }

    @Test
    void falseHashIsNotCachedAsImmutable()
            throws Exception {

        String wrong =
                "/assets/css/site-00000000000000000000000000000000.css";

        HttpResponse<String> response = send(wrong);

        assertThat(response.statusCode()).isEqualTo(404);
        assertThat(header(response, "Cache-Control"))
                .doesNotContain("immutable");
    }

    @Test
    void matchingETagReturns304WithEmptyBody()
            throws Exception {

        HttpResponse<String> original =
                send("/api/catalog");

        assertThat(original.statusCode()).isEqualTo(200);
        assertThat(original.body())
                .contains("\"book\"", "\"pen\"");
        String etag = header(original, "ETag");
        assertThat(etag).isEqualTo("\"catalog-rev-1\"");

        HttpRequest conditional =
                get("/api/catalog")
                        .header("If-None-Match", etag)
                        .build();

        HttpResponse<String> notModified = client.send(
                conditional,
                HttpResponse.BodyHandlers.ofString());

        assertThat(notModified.statusCode()).isEqualTo(304);
        assertThat(notModified.body()).isEmpty();
    }

    @Test
    void differentETagReturnsCurrentRepresentation()
            throws Exception {

        HttpRequest request = get("/api/catalog")
                .header("If-None-Match", "\"some-old-revision\"")
                .build();

        HttpResponse<String> result = client.send(
                request,
                HttpResponse.BodyHandlers.ofString());

        assertThat(result.statusCode()).isEqualTo(200);
        assertThat(result.body()).contains("book");
    }

    @Test
    void previewMustNeverBeStoredBySharedCache()
            throws Exception {

        HttpResponse<String> response =
                send("/api/account-preview");

        assertThat(response.statusCode()).isEqualTo(200);
        assertThat(header(response, "Cache-Control"))
                .contains("private")
                .contains("no-store");
        assertThat(response.body())
                .contains("\"demo-only\"");
    }

    @Test
    void javaScriptIsVersionedAndImmutable()
            throws Exception {

        HttpResponse<String> home = send("/");
        Matcher match = Pattern.compile(
                "/assets/js/app-[0-9a-f]{32}\\.js")
                .matcher(home.body());

        assertThat(match.find()).isTrue();

        HttpResponse<String> js = send(match.group());
        assertThat(js.statusCode()).isEqualTo(200);
        assertThat(js.body()).contains("DOMContentLoaded");
        assertThat(header(js, "Cache-Control"))
                .contains("immutable");
    }
}
```

Chạy:

```bash
gradle test
```

Kỳ vọng: **8 tests** pass nếu Boot 3.3.13, Java17, Thymeleaf URL rewriting và resource chain được kết nối đúng. Đây là kết quả **kỳ vọng, không phải xác nhận đã chạy trên Gradle**.

### 11.1. Các assertion thực sự chứng minh gì?

- `homeIsRevalidatedAndLinksAreContentVersioned`: HTML chạy qua Thymeleaf và URL chứa hash; chỉ nhìn CSS file tồn tại không đủ.
- `fingerprintedAssetIsPublicAndImmutable`: URL được template render được HTTP server giải quyết và đúng cache policy.
- `unversionedAssetMustRevalidate`: bare path không bị gắn TTL một năm như một tài nguyên bất biến.
- `falseHashIsNotCachedAsImmutable`: client không thể giả hash bất kỳ rồi nhận policy immutable của demo.
- `matchingETagReturns304WithEmptyBody`: điều kiện `If-None-Match` được Spring MVC xử lý khi trả `ResponseEntity`; 304 không có body.
- `differentETagReturnsCurrentRepresentation`: validator cũ không vô tình làm response mất body.
- `previewMustNeverBeStoredBySharedCache`: response demo có `private, no-store`; không chứng minh toàn bộ CDN obey header.
- `javaScriptIsVersionedAndImmutable`: JS không bị bỏ quên khi bạn thêm content versioning cho CSS.

**Giới hạn:** tests chưa chạy browser JavaScript thật, chưa kiểm tra CDN, compression, CSP, auth/cookies, TLS và rolling deployment có hai bản assets. Những phần đó cần suite bổ sung ở các mục 15–21.

## 12. Kiểm thử khi asset thay đổi qua hai build

Một test chỉ khởi động một build không chứng minh hash **thay khi bytes thay**. Để kiểm tra end-to-end cache busting, tạo hai artifacts độc lập:

**Release R1**
1. Build jar với `site.css` có `--brand: #2351a4;`.
2. Chạy app và lấy HTML `/`.
3. Trích CSS URL vào biến `CSS_R1`.
4. Lấy asset từ URL đó, tính checksum bytes và ghi nhận policy.

**Release R2**
1. Sửa đúng nội dung CSS thành `--brand: #6138a5;`.
2. Build jar R2 sạch (đảm bảo resources đã được đóng vào artifact mới).
3. Chạy R2 trên port khác.
4. Lấy HTML `/`, trích CSS URL thành `CSS_R2`.
5. Assert `CSS_R1 != CSS_R2` và CSS_R2 chứa màu mới.
6. Cả R1/R2 HTML giữ `Cache-Control: no-cache`.
7. `/assets/css/site.css` ở R2 không có cache lifetime dài.
8. Thử lấy URL `CSS_R1` qua **CDN/asset origin** khi R1 đã bị thay khỏi app fleet. Nếu hỗ trợ người dùng còn giữ HTML cũ, URL R1 vẫn phải được phục vụ từ kho immutable giữ lại.

**Điểm rất quan trọng:** Spring Boot classpath resource handler khi chạy một jar R2 mới có thể **không còn phục vụ hash R1** vì R2 jar chỉ chứa `site.css` bản mới. Content versioning không tự lưu lịch sử của tất cả releases! CDN/object storage có chính sách retention, hoặc build artifacts có thể giữ nhiều phiên bản; phải thiết kế đường phục vụ asset cũ có chủ đích.

### 12.1. Shell smoke test minh họa

```bash
# Chạy R1 ở 8080, R2 ở 8081 bằng hai artifacts riêng.
curl -sS http://localhost:8080/ > r1.html
curl -sS http://localhost:8081/ > r2.html

CSS_R1=$(grep -oE \
  '/assets/css/site-[0-9a-f]{32}\.css' r1.html | head -n 1)
CSS_R2=$(grep -oE \
  '/assets/css/site-[0-9a-f]{32}\.css' r2.html | head -n 1)

printf "R1: %s\nR2: %s\n" "$CSS_R1" "$CSS_R2"

test -n "$CSS_R1"
test -n "$CSS_R2"
test "$CSS_R1" != "$CSS_R2"
```

**Không có output digest cố định** vì hash tính theo bytes. Đây là script kiểm tra URL khác nhau, không tự chứng minh asset R1 còn khả dụng tại origin R2. Nếu cả hai URL giống nhau, kiểm tra thực sự đã sửa/tái build resource, Gradle incremental caching và cấu hình content version strategy.

### 12.2. Cần test cả rollback

Sau khi R2 đã phục vụ HTML, một client có thể vẫn có CSS R2 trong cache khi bạn rollback app R1:
- Nếu HTML rollback R1 tham chiếu R1 hash, browser có thể đã cache R1 asset và hoạt động.
- Nếu client giữ HTML R2 cũ trong tab, nó vẫn có thể yêu cầu R2 asset. Nếu R2 bị xóa khỏi mọi origin/CDN và browser chưa cache R2, UI có thể 404.
- Nếu R2 JavaScript dựa vào API chỉ R2 hỗ trợ, giữ asset là chưa đủ. Cần API backward compatibility hoặc app-level reload/version negotiation.
- Một service worker có thể giữ HTML/JS R2 độc lập HTTP cache; cần lifecycle và app upgrade policy riêng.

**Kết luận thực hành:** versioned assets, HTML cache policy và API compatibility phải đi cùng nhau. Không chỉ xem `Cache-Control` trên CSS rồi cho rằng rollout không thể gây lỗi.

## 13. ETag và conditional requests: giảm body nhưng vẫn đúng dữ liệu

HTTP cache validators cho phép client revalidate:

```text
Client                              Server
  │ GET /api/catalog                 │
  ├─────────────────────────────────►│
  │◄──── 200 ETag: "catalog-rev-1" ───┤
  │      body = ["book","pen"]        │
  │                                   │
  │ GET /api/catalog                  │
  │ If-None-Match: "catalog-rev-1"     │
  ├─────────────────────────────────►│
  │◄──── 304 Not Modified ────────────┤
  │      NO response body             │
  │                                   │
  │ client reuses cached body         │
```

**ETag không phải timestamp**; nó là một validator opaque cho selected representation. Có thể dùng:
- Strong ETag: `"revision-7"`, chỉ hợp lệ khi biểu diễn tương ứng thực sự được xem là tương đương mạnh.
- Weak ETag: `W/"revision-7"`, dùng khi biểu diễn có thể khác byte-for-byte nhưng ngữ nghĩa tương đương theo policy HTTP.
- Revision từ database, checksum response bytes, content hash hoặc storage object version.

Trong demo, catalog **cố định** nên `"catalog-rev-1"` là hợp lệ trong phạm vi ấy. Production nếu response thay đổi theo locale, account, query params, role, nội dung DB hay feature flags, **ETag phải thay cho mọi biến thể có thể khác**. Chỉ dùng hằng `"catalog-rev-1"` cho dữ liệu đang thay đổi là bug: client có thể nhận 304 dù body thực đã khác.

### 13.1. Status 304 có gì và không có gì?

- 304 thường được tạo cho conditional GET/HEAD khi selected representation không thay đổi.
- **Không có response message body** của resource.
- Response có thể mang headers metadata cần cập nhật cache entry như `ETag` và `Cache-Control`.
- Một JDK `HttpClient` thuần không tự trở thành browser cache khi gửi `If-None-Match`; test phải giữ body ban đầu nếu muốn mô phỏng reuse.
- `If-None-Match` có ưu tiên so với `If-Modified-Since` theo chuẩn khi cùng có mặt.
- 304 **không có nghĩa app không làm việc gì**; server vẫn có thể query DB/tính ETag trừ khi có revision nhanh/metadata riêng.
- Nếu client chưa có bản body cũ mà vẫn gửi If-None-Match, 304 không cung cấp body mới; consumer phải xử lý đúng.
- Với state-changing methods, `If-Match` và 412 Precondition Failed dùng cho optimistic concurrency là bài toán khác `If-None-Match` của GET cache.

### 13.2. ETag của static resources có tự bật không?

Spring MVC `ResourceHttpRequestHandler` hỗ trợ `Last-Modified`/conditional requests theo metadata resource. **Đừng giả định mọi static resource đều tự có ETag từ Spring Boot** chỉ vì bạn bật content hash URL. Versioned path và HTTP ETag là hai cơ chế khác nhau:
- Content hash URL giúp tạo **cache key mới** khi bytes đổi.
- ETag giúp **revalidate cùng URL** khi cache stale.
- Last-Modified có thể cho revalidation nhưng chịu độ chính xác timestamp và nguồn resource.
- `ShallowEtagHeaderFilter` có thể tạo ETag từ response body sau khi buffer, nhưng **không nên áp dụng rộng lên streaming/download rất lớn** vì buffering CPU/memory; ứng dụng có thể tạo ETag từ metadata/revision hiệu quả hơn.

Thực tế với hashed immutable assets, browser ít cần revalidate khi resource còn fresh. Với HTML/API không hash, ETag/Last-Modified có giá trị lớn hơn.

## 14. Cache policy ở HTML, JSON riêng và redirect

### 14.1. HTML chung

`Cache-Control: no-cache` là lựa chọn đơn giản để browser có thể lưu nhưng phải kiểm tra lại trước khi dùng. Nếu server không cung cấp ETag/Last-Modified cho HTML, revalidation thường nhận 200 và tải lại body. Đây không phải lỗi: HTML thường nhỏ hơn nhiều so với JS bundles, và việc cập nhật asset URL nhanh là quan trọng.

Nếu HTML có dữ liệu cá nhân/CSRF token/secret hoặc chính sách privacy yêu cầu không lưu, dùng `Cache-Control: private, no-store` và tránh CDN public. Không phải mọi HTML đều được phép lưu.

### 14.2. JSON public

Response catalog public có `ETag` và `max-age=0, must-revalidate`. Có thể tối ưu theo nghiệp vụ:
- Catalog hiếm đổi: freshness ngắn và `s-maxage` CDN.
- Pricing/inventory thay đổi nhanh: không cache hoặc revalidate mạnh, chọn data correctness.
- API có user-specific fields: `private` hoặc `no-store`, không dùng shared public cache.
- HTTP `Vary` nếu nội dung tùy `Accept-Language`, `Accept-Encoding` hoặc header khác; tránh `Vary: Cookie` quá rộng làm nổ số cache keys.

### 14.3. Redirect có thể bị cache

`301 Moved Permanently` và `308 Permanent Redirect` có caching semantics khác `302`/`307`. Nếu đổi routing từ `/old` sang `/new` rồi rollback, browser có thể nhớ permanent redirect. Trong rollout nhiều version:
- Test `Location`, scheme/host, query preservation.
- Với proxy TLS termination, cấu hình trusted forwarded headers đúng; không tin header khách tự đặt.
- Không vô tình cache redirect user-specific hay OAuth callback.
- Đặt redirect policy và expiry có chủ đích, không dùng 301 khi route thử nghiệm có thể thay đổi ngay.

## 15. NGINX/CDN: long cache chỉ trên đúng asset paths

Ở production, một cách hiệu quả là **build pipeline tạo fingerprinted assets** và một URL namespace riêng (ví dụ `/assets/v/`), sau đó CDN rule chỉ đặt immutable trên namespace đã bảo đảm toàn tệp bất biến. Với Spring ResourceVersionResolver demo, hash nằm trong filename; CDN cần biết URL đó thật sự tồn tại và không thay đổi.

Một config minh họa NGINX đặt browser caching ở **edge**:

```nginx
# Fragment; TLS server/upstream/ACL khác cần cấu hình đầy đủ.
server {
    listen 443 ssl;
    server_name site.example.test;

    # ssl_certificate /...;
    # ssl_certificate_key /...;

    location /assets/ {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;

        # KHÔNG add_header immutable cho TOÀN /assets/
        # nếu /assets/site.css chưa hash vẫn truy cập được.
        # Để origin filter kiểm soát hoặc dùng policy
        # match đúng hashed path/build manifest.
    }

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Đừng cấu hình proxy cache cho HTML/account
        # nếu chưa xét Cache-Control, Authorization, cookies.
    }
}
```

**Đây không phải cấu hình NGINX production đầy đủ**; thiếu TLS keys/CA, forwarded-header trust boundary, body/header limits, auth/rate limits, logs, timeouts và network controls. Không copy trực tiếp để deploy.

Ở CDN:
- Kiểm tra có **honor origin Cache-Control** hay đang override TTL/error caching.
- Không bao giờ cache `Set-Cookie`/`Authorization`-dependent HTML như public chỉ vì hostname chung.
- Cache key phải phân biệt path/query/header variation cần thiết nhưng không để high-cardinality không giới hạn.
- Nếu CDN hỗ trợ immutable asset retention, giữ old hashes đủ lâu cho active tabs/rollbacks.
- Với compressed variants gzip/br, hỗ trợ `Vary: Accept-Encoding` và kiểm tra ETag semantics của từng representation.
- Có purge plan cho sự cố: **URL hashed sai nội dung, secret bị nhúng vào JS bundle, stale HTML**, nhưng không dựa vào purge như cơ chế deploy mặc định.

**Security:** Không tin `X-Forwarded-*` của client trực tiếp. Reverse proxy phải strip/overwrite headers ở trust boundary, backend chỉ tiếp nhận từ proxies được kiểm soát. Sai scheme/host có thể làm template URL, redirect, cookie Secure và cache key lệch.

## 16. Content compression, Range/HEAD, images và fonts

Các biến thể HTTP có thể làm caching phức tạp hơn:

### 16.1. Compression

- Browser có thể yêu cầu `Accept-Encoding: br, gzip`; server hoặc CDN trả `Content-Encoding` tương ứng.
- Nếu cùng URL có nhiều representations theo encoding, caches phải xử lý `Vary: Accept-Encoding` đúng.
- Với static precompressed resources, Spring resource chain có `EncodedResourceResolver` và `VersionResourceResolver`. Tài liệu Spring Framework hướng dẫn **đăng ký EncodedResourceResolver trước VersionResourceResolver** nếu cấu hình thủ công, để content hash tính trên tài nguyên chưa nén.
- `server.compression.enabled=true` có thể làm response body bytes khác dạng chưa nén, nên ETag/hash contract phải xét representation. Không tự giả định ETag của raw file và compressed representation luôn mạnh tương đương.
- Không làm CDN cache compressed body rồi trả cho client không gửi Accept-Encoding tương ứng.

### 16.2. Range/partial content

Download videos/large files đôi khi dùng `Range: bytes=...` và HTTP 206 Partial Content; response có `Content-Range`, `Accept-Ranges`. Các server/resource handlers có mức hỗ trợ khác nhau; phải test trên đúng runtime.

Không áp một response buffering ETag filter lên file lớn/streaming mà không đo memory. Nên dùng asset/object storage/CDN tối ưu range requests khi media lớn; content-hash URL của tệp không thay thế byte-range semantics.

### 16.3. Hình ảnh và fonts

- Images không thay đổi có thể fingerprint tương tự CSS/JS, kể cả AVIF/WebP/PNG.
- Fonts tải cross-origin có thể cần CORS; `Access-Control-Allow-Origin` và `Cross-Origin-Resource-Policy` tùy kiến trúc.
- Responsive images với `srcset` phải có version cho **từng** biến thể (width/format), không chỉ bản mặc định.
- CSS có `url(...)` trỏ tới fonts/images phải được rewrite/build manifest nhất quán; một CSS có hash mới mà trỏ tới file không tồn tại vẫn làm giao diện hỏng.
- Với dữ liệu cá nhân như avatar private, dùng signed URLs đúng TTL và không tự đặt `public, immutable` nếu quyền truy cập có thể thay đổi.

## 17. Service workers và SPA: HTTP Cache-Control không kiểm soát toàn bộ caching

Nếu frontend có service worker:
- `CacheStorage` có thể giữ HTML/JS dù HTTP response là no-cache, tùy logic service worker.
- Chiến lược `cache-first` cho app shell với URL không hash có thể khiến client mãi chạy bản cũ.
- `network-first` cho HTML có thể phù hợp nhưng cần offline fallback và timeout.
- Khi phát hành service worker mới, activate/claim/skipWaiting phải có UX và schema/API compatibility plan.
- Không để service worker cache `/api/account`, token responses, CSRF-sensitive HTML khi không có thiết kế privacy rõ.
- `service-worker.js` thường cần freshness/revalidation phù hợp để browser phát hiện bản SW mới; không cache bất biến cùng URL.

**SPA fallback với Spring Boot:**
- Các đường static assets phải được phục vụ thật; không forward **mọi** 404 asset thành `index.html` với status 200, vì browser sẽ nhận HTML cho URL `.js`, gây MIME type error và CDN cache sai.
- Route client-side SPA như `/dashboard` có thể forward `index.html` khi request Accept là HTML và không trùng API/static paths.
- Với hashed asset thiếu, trả **404** để phát hiện lỗi triển khai, không gửi HTML fallback.
- Dữ liệu SEO/prerender, history router, base path, Content-Security-Policy và cache of index.html cần thử trên path thật của proxy.

Ví dụ ý tưởng **không phải code standalone**:

```text
GET /dashboard     + Accept: text/html  -> index.html
GET /assets/x.js   + Accept: */*        -> resource hoặc 404
GET /api/users     + Accept: */*        -> API hoặc 404
```

Việc phân nhánh theo path/Accept phải được kiểm tra an toàn, không dùng một universal catch-all controller làm mất status 404 của resources.

## 18. WebFlux và static resource handling: phần nào giống, phần nào khác?

Spring Boot WebFlux vẫn có hỗ trợ static resources và resource versioning với reactive resource handlers, nhưng **không sử dụng Servlet `Filter` hoặc `ResourceUrlEncodingFilter` giống MVC**. Với WebFlux:
- Handler pipeline dùng `WebFilter` và `ServerWebExchange`.
- Thay đổi response cache headers thông qua `ServerHttpResponse.getHeaders()`/`WebFilter` có thể thực hiện trước khi commit.
- Template engine integration và URL rewriting phải theo reactive stack, không copy nguyên MVC `ResourceUrlProvider`/`HttpServletResponse.encodeURL`.
- `spring.web.resources.*` có các common properties, nhưng verify behavior với `@SpringBootTest(RANDOM_PORT)` trên Reactor Netty.
- Với Spring WebFlux, `WebSession` khác Servlet `HttpSession`; cache policy không thay session/authorization.
- Nếu app có cả `starter-web` và `starter-webflux`, Boot thường ưu tiên MVC; không dựa vào việc chỉ import `Mono` để đoán runtime.

Mảnh WebFlux minh họa **không phải ứng dụng runnable riêng**:

```java
// Trong một WebFilter của Spring WebFlux:
@Override
public Mono<Void> filter(
        ServerWebExchange exchange,
        WebFilterChain chain) {

    String path = exchange.getRequest()
            .getPath().value();

    if (path.equals("/api/account")) {
        exchange.getResponse().getHeaders().set(
                HttpHeaders.CACHE_CONTROL,
                "private, no-store");
    }

    return chain.filter(exchange);
}
```

Muốn dùng thực tế cần imports, bean registration, auth policy và kiểm tra đường đi qua reverse proxy. Nếu đã dùng frontend build (Vite/Webpack/Angular/React) sinh manifest fingerprinted assets, có thể để NGINX/CDN phục vụ static files riêng và Boot chỉ phục vụ API. Đây cũng là kiến trúc hợp lệ; điều cần bảo đảm vẫn là **HTML/API/cache key hợp đồng nhất quán**.

## 19. Cache busting không đảm bảo giao diện và API tương thích

Giả sử:
1. R1 JavaScript gọi `GET /api/orders` và đọc trường `totalCents`.
2. R2 JavaScript gọi cùng endpoint nhưng cần trường `totalAmount`.
3. Browser còn giữ HTML/JS R1 trong tab cũ, còn backend R2 đã bỏ `totalCents`.
4. Dù assets có URL hash đúng, R1 JS vẫn lỗi vì **API contract bị phá**.

Giải pháp:
- Server duy trì backward-compatible API fields trong thời gian active clients còn dùng.
- Trì hoãn xóa endpoint/schema cũ trong rollout window.
- Cung cấp app version endpoint/negotiation nếu thật sự cần, nhưng không bắt reload bất ngờ khi user đang nhập form.
- Với WebSocket/SSE, thiết kế protocol compatibility và reconnect semantics.
- Test browser client R1 với API R2 và ngược lại trong thời gian mixed deployment.
- Dữ liệu session/cookie/schema cũng phải compatible giữa R1/R2; asset hash không giải quyết serializer hoặc authentication.
- Nếu cần cưỡng bức reload UI, có banner/UX và bảo vệ unsaved state.

**Dấu hiệu kiểm tra sai:** “R2 HTML đã có CSS_R2, nghĩa là user sẽ dùng đúng JS R2”. Một tab cũ không reload có thể vẫn chạy JS R1 trong memory hàng giờ. Code nên chịu được mixed frontend/backend versions khi hệ thống yêu cầu zero-downtime.

## 20. ETag của API dynamic và invalidation theo dữ liệu

Một API catalog có thể có dữ liệu từ DB; khi thay:
- Tăng revision của catalog, hoặc tính hash từ canonical representation.
- Nếu response lọc theo tenant, locale, currency hoặc quyền, đưa các dimensions ảnh hưởng body vào ETag hoặc cache key.
- Không dựa vào `updatedAt` nếu revision có thể bị trùng trong cùng đơn vị thời gian, clock skew hoặc update backfill.
- Nếu dùng `Last-Modified`, lưu ý timestamp precision đến giây và client/server clock, cần contract phù hợp.
- `If-None-Match` của GET tránh gửi body nhưng có thể vẫn tốn DB query để xác định revision.
- Khi có `@Cacheable` service phía trong, cache key/eviction là chuyện độc lập với ETag ở HTTP layer.

Một mẫu an toàn dùng ETag theo revision:

```java
// Mảnh method minh họa, không standalone:
@GetMapping("/api/catalog")
ResponseEntity<CatalogDto> readCatalog() {
    CatalogSnapshot snapshot = catalogService.current();

    String etag = "\"catalog-" + snapshot.revision() + "\"";

    return ResponseEntity.ok()
            .eTag(etag)
            .header(HttpHeaders.CACHE_CONTROL,
                    "public, max-age=0, must-revalidate")
            .body(snapshot.payload());
}
```

`CatalogDto`, `CatalogSnapshot` và `catalogService` phải được ứng dụng triển khai. **Revision phải duy nhất cho mỗi representation biến đổi** và không thể chia sẻ mù quáng giữa tenants. Nếu catalog chứa dữ liệu theo quyền truy cập, **không dùng public**; ưu tiên `private` hoặc `no-store` và authorization chính xác.

### 20.1. Có thể dùng HTTP 304 cho tài nguyên mang Authorization không?

HTTP caching có các quy tắc phức tạp khi request mang `Authorization`. Shared caches không được tùy tiện dùng lại response nếu response không có directive cho phép theo chuẩn; private cache còn có chính sách riêng. Tuy nhiên **đừng dựa vào hành vi tình cờ của CDN** để bảo vệ bí mật. Với API cá nhân, đặt `Cache-Control: private, no-store` khi cần và kiểm thử qua gateway; không phát ETag chứa bí mật hoặc user identifiers có thể đoán được.

Một ETag không phải access token: nó không thay authorization. Nếu user B gửi ETag của user A, server vẫn phải xác thực quyền, chọn representation của user B rồi mới đánh giá conditional request.

## 21. Security: chỗ nào cache có thể trở thành lỗ hổng?

### 21.1. Shared cache key không có user identity

Nếu API `/api/me` trả dữ liệu của người đăng nhập nhưng origin lỡ dùng `Cache-Control: public, max-age=600`, CDN có thể lưu response theo URL và trả cho một user khác. Rủi ro càng cao khi CDN bỏ qua cookies/Authorization trong cache key.

Giải pháp:
- Không dùng shared caching cho dữ liệu private trừ khi có thiết kế key/authorization cực kỳ rõ.
- Dùng `Cache-Control: private, no-store` cho nội dung nhạy cảm theo policy.
- Cấu hình CDN bypass cache khi có auth/cookie phù hợp, không chỉ hy vọng browser tự xử lý.
- Xem chính sách `Set-Cookie` và tránh cache nhầm response login/logout.
- Test bằng **hai người dùng synthetic A/B** qua proxy: response của A không bao giờ hiển thị cho B.

### 21.2. Asset public chứa secrets

JavaScript bundle có thể lộ:
- API keys giả định là bí mật (client-side API key không thể giữ bí mật nếu nằm trong JS).
- URLs nội bộ, feature flags, debug metadata.
- Source maps với source code/tokens nếu publish nhầm.
- Internal configuration nhạy cảm từ build-time environment.

**Content hash không bảo mật tệp.** Nếu secret được ship trong JS, cả asset đã cache ở browser/CDN đều có thể còn tồn tại lâu; xóa file ở origin chưa xóa mọi bản đã phân phối. Cần secret rotation và incident response, không chỉ đổi URL.

### 21.3. Cache poisoning và path normalization

Các proxy có thể khác nhau về normalization của:
- Query string và thứ tự parameters.
- URL encoding, percent-decoding, semicolon parameters.
- Header `Host`, `Forwarded` và `X-Forwarded-*`.
- HTTP `Vary` và Content-Encoding.
- Redirect/path case sensitivity.

Đừng coi regex “có vẻ là hash” như xác thực file tồn tại hoặc là phiên bản đúng. Trong demo, filter so khớp **URL canonical do resource chain sinh**. Production với nhiều files cần manifest/verified storage và cache key policy chặt chẽ. CDN không được cache response 200 của HTML fallback vào URL JS/hash bị thiếu.

### 21.4. CSP và SRI

- CSP như `script-src 'self'`/nonce phù hợp giúp giới hạn script sources, cần cân nhắc inline scripts.
- SRI xác minh bytes cho script/style subresources hỗ trợ, thường dùng với CDN third-party.
- Resource URL MD5 versioning giúp cache invalidation nhưng không phải cryptographic integrity check.
- Không gắn wildcard CORS credentials với `*` cho API có cookie session.
- Không tin SSL/TLS termination headers từ client; proxy trust config cần kiểm thử.

## 22. Observability và debugging theo mỗi tầng

Một asset URL 404 sau deploy có thể đến từ:
- HTML đang trỏ tới hash của release cũ mà origin đã xóa.
- Thymeleaf không rewrite URL nên client gọi path cũ.
- CDN rule rewrite mọi 404 sang HTML 200.
- `spring.web.resources.static-locations` bị thay.
- App đang chạy dưới context path khác.
- Build tool không copy `static/assets` vào jar.
- Cache control bị CDN override.
- Resource chain dùng fixed/content version strategy không khớp.
- CDN cached 404 trước khi asset được upload.

**Tín hiệu nên thu thập:**

| Tín hiệu | Ý nghĩa |
|---|---|
| HTTP 200/304/404/5xx cho `/assets/**` | Cache hit/miss, missing assets, origin errors |
| CDN cache status: HIT/MISS/BYPASS | Có cache đúng nhóm URL không |
| HTML response/cache headers | Có revalidate sau deploy không |
| Fingerprinted asset unique paths | Build version phân phối thực |
| 304 ratio trên API public | Mức tiết kiệm body, cần đi kèm latency |
| JS error rate sau rollout | Client cũ/API incompatibility |
| Resource handler exceptions | Sai lookup/version/static paths |
| Response bytes + TTFB | Bandwidth/latency khi bật cache |
| Frontend version vs API version | Phát hiện mixed-version failures |
| Security header compliance | CSP/CORS/Cache-Control leak prevention |

Không đưa raw `Cookie`, `Authorization`, session ID, user ID tùy ý hoặc full URLs chứa secrets vào metric labels. Với HTTP API, dùng route template và reason enums hữu hạn. CDN logs có thể chứa query tokens; cần redact/retention policy.

### 22.1. Debug theo đường đi ngắn nhất

1. `curl -I /`: HTML Cache-Control và Content-Type đúng chưa?
2. `curl -s /`: asset URL đã có hash chưa?
3. `curl -I <hashed-url>`: status 200 và immutable chưa?
4. `curl -I <bare-url>`: có bị cache một năm sai không?
5. `curl -H 'If-None-Match: ...' /api/catalog`: 304 hay 200?
6. Test qua domain/CDN: response headers có bị override không?
7. Test R1→R2: hash đổi, old asset retention đủ chưa?
8. Test browser thật với Disable Cache bật/tắt để phân biệt resource chain vs HTTP cache.
9. Nếu offline service worker hoạt động, xóa/kiểm tra Cache Storage **trong môi trường test** để tách một nguồn stale.
10. Kiểm tra build resource contents trong jar/image và routing/proxy rewrite rules.

Đừng vội “Ctrl+F5 rồi xong”: hard refresh che nguyên nhân stale cache, không giúp những người dùng ngoài production tự nhận đúng bản release.

## 23. Ma trận QA hoàn chỉnh

| Kiểm thử | Input | Kỳ vọng |
|---|---|---|
| HTML freshness | GET `/` | 200 text/html + no-cache |
| HTML version links | GET `/` | URL CSS/JS có 32 hex MD5 của content |
| Hashed CSS | GET URL từ HTML | 200 CSS + public max-age=31536000 immutable |
| Hashed JS | GET URL từ HTML | 200 JS + immutable |
| Bare CSS | GET `/assets/css/site.css` | 200 + no-cache |
| Hash giả | GET `site-0000...css` | 404, không gắn immutable |
| API ETag | GET `/api/catalog` | 200, ETag đúng selected representation |
| Conditional GET | If-None-Match đúng | 304 body rỗng |
| Stale ETag | If-None-Match sai | 200 body mới |
| Sensitive API | GET `/api/account-preview` | private, no-store |
| CSS content deploy | Thay màu trong CSS R2 | R2 URL khác R1; bytes đúng |
| Old asset retention | GET R1 URL sau R2 | Có asset nếu policy giữ historical hashes |
| HTML rollback | R2→R1 | R1 HTML trỏ đúng R1 assets; tabs cũ không 404 |
| API compatibility | JS R1 gọi API R2 | Không bị phá business contract |
| Browser cache | 2 lần navigation với cache enabled | HTML revalidate; hashed assets HIT khi fresh |
| CDN policy | GET /assets/, /api/me | Asset public, account never shared |
| Compression | Accept-Encoding: gzip/br | Vary/Content-Encoding đúng, bytes hợp lệ |
| HTTP/2/TLS | Request qua ingress | Cert valid, h2 negotiated theo yêu cầu |
| SPA fallback | Asset không có | 404, không bị index.html giả 200 |
| Service worker | Upgrade khi có cache-first | Không giữ app shell cũ vô hạn |
| Authentication | User A và B qua CDN | Không lộ response private xuyên users |
| Error cache | 404/5xx/redirect | Không cache bất ngờ |
| Observability | R2 rollout | CDN HIT/MISS, client errors, 404 assets phù hợp |

**Không ép tất cả cases vào một unit-test class.** 8 HTTP tests của demo là core suite; browser/CDN/staging tests là suite bổ sung theo hạ tầng. Với browser Playwright/Selenium, dùng bản build có frontend thật và xác minh DOM sau khi JS chạy. Với CDN, dùng môi trường staging có caching policy giống production để kiểm chứng headers/TTL.

## 24. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân | Hướng giải quyết |
|---|---|---|
| HTML vẫn tham chiếu `site.css` | Không qua Thymeleaf URL rewrite hoặc content strategy chưa bật | Dùng `th:href` + Boot chain; test HTML qua HTTP |
| CSS vẫn cũ sau deploy | Bare URL cached 1 năm | Dùng fingerprinted URL; giảm TTL bare path |
| CSS hash không đổi khi sửa file | Build/resources cache hoặc thay file không nằm trong artifact | So resource jar bytes, rebuild và restart |
| Hashed URL 404 | Static file không có/lookup strategy mismatch | Kiểm tra classpath, resource chain và deployment |
| Old tab bị 404 assets sau rollout | Xóa assets release cũ quá sớm | Retain immutable historical assets ở CDN/object storage |
| HTML API cũ không tương thích | Frontend tab vẫn chạy JS R1 | Backward-compatible API, reload/version policy |
| `Cache-Control` dài trên cả bare CSS | Dùng Boot global cache max-age một năm | Tách policy theo verified hashed URL |
| No-cache bị hiểu là không lưu | Nhầm semantics | Dùng no-store khi phải cấm lưu |
| User A nhận dữ liệu user B | CDN public cache response cá nhân | private/no-store, auth-aware CDN bypass |
| API luôn 304 dù dữ liệu đổi | ETag hằng không đổi theo representation | Tính từ revision/hash hợp lệ |
| API luôn 200 dù ETag đúng | Không qua ResponseEntity conditional path, cache validator khác | Kiểm tra ETag quotes/If-None-Match/handler |
| Static asset không có ETag | Resource handler không tự tạo ETag theo kỳ vọng | Dùng Last-Modified/hashed URL; ETag riêng nếu cần |
| CDN trả HTML cho `.js` | SPA fallback bắt cả missing assets | Giữ 404 cho assets |
| Service worker vẫn hiển thị UI cũ | Cache Storage được app điều khiển khác HTTP cache | Quản lý SW lifecycle/version |
| Dev chỉnh HTML chưa thấy thay đổi | Thymeleaf template cache | Set dev profile `spring.thymeleaf.cache=false`, restart phù hợp |
| Static content reload chưa đổi | Resource chain cache nội bộ/JAR packaging | Dev profile, rebuild resources, kiểm tra runtime |
| CSS path sai dưới context-path | Hardcode absolute URL/proxy prefix | Dùng Thymeleaf `@{...}`, test context path |
| URL hash 32hex bị tưởng SRI | ContentVersionStrategy MD5 chỉ versioning | Dùng SRI SHA-384 và CSP phù hợp |
| CDN gzip variants lỗi | Thiếu/misconfigured Vary | Test Accept-Encoding và compressed representations |
| Browser cache làm 301 không đổi | Permanent redirect cached | Dùng redirect status/policy có kiểm soát |
| Asset JS chứa secret | Embed secrets vào frontend bundle | Rotate secret, purge/incident response |
| Profile page có no-cache nhưng cần privacy | No-cache vẫn cho phép lưu | Dùng private/no-store đúng policy |
| Asset hash mới nhưng runtime API cũ | Mixed deployment frontend/backend | Compatibility test và rollout sequencing |
| Nhiều assets, filter lookup tốn CPU | Per-request ResourceUrlProvider calls | Build manifest hoặc CDN object storage/rules |
| Login cookie khác khi qua proxy | SameSite/Secure/forwarded headers sai | Secure proxy trust, auth integration tests |
| HTML bị proxy cache trái origin | CDN override Cache-Control | Inspect CDN config/headers và bypass routes |

## 25. Checklist triển khai production

- [ ] Phân loại HTML public, HTML private, JSON public, JSON private và static assets.
- [ ] HTML có policy cập nhật nhanh: no-cache hoặc no-store nếu cá nhân.
- [ ] CSS/JS/fonts/images có URL content-hashed hoặc build-versioned được bảo đảm.
- [ ] Không hardcode hash; template/helper/manifest sinh URL từ build/resource chain.
- [ ] Asset có hash hợp lệ có public max-age dài + immutable.
- [ ] URL không hash không bị cache dài, hoặc được đóng/redirect an toàn.
- [ ] CDN/object storage giữ old assets trong rollout và rollback window.
- [ ] Spring resource chain và Thymeleaf URL rewriting đã được HTTP test thực xác minh.
- [ ] Không nhầm resolver/template cache trong JVM với HTTP cache ở browser/CDN.
- [ ] ETag API đổi khi representation đổi; conditional GET trả 304 đúng.
- [ ] Dynamic private content có auth và private/no-store theo policy.
- [ ] Không cache tokens/CSRF/account/Set-Cookie vào shared CDN.
- [ ] Vary và compression variants được kiểm tra.
- [ ] Browser service worker Cache Storage có version/purge/lifecycle riêng.
- [ ] Không forward missing JS/CSS assets sang SPA index.html 200.
- [ ] API backward compatibility với tab JS của release cũ.
- [ ] Kiểm thử R1→R2→rollback bằng browser/CDN staging, không chỉ một JUnit test.
- [ ] Dùng HTTP `RANDOM_PORT` integration tests cho headers, 304, hashed URLs.
- [ ] Security có CSP/SRI/TLS/proxy header trust phù hợp.
- [ ] Metrics CDN HIT/MISS, asset 404, JS errors, cache policy violations.
- [ ] Không đăng secrets/PII trong bundles, logs, snapshots hoặc metrics.
- [ ] Có rollback/purge strategy và incident response cho assets sai.

## 26. Câu hỏi tự kiểm tra

**1. Vì sao cần hash trong tên CSS thay vì chỉ đặt max-age nhỏ?**  
Vì URL có hash trở thành cache key mới khi nội dung thay đổi, nên có thể giữ immutable rất lâu mà client vẫn tải bản mới sau deploy.

**2. `Cache-Control: no-cache` có cấm browser lưu response không?**  
Không. Nó cho phép lưu nhưng yêu cầu revalidate trước khi dùng lại. `no-store` mới là directive không lưu.

**3. Có nên đặt `spring.web.resources.cache.cachecontrol.max-age=365d` cho mọi static files?**  
Chỉ khi toàn bộ đường dẫn có thể cache dài thật sự bất biến hoặc đã chặn đường bare/unversioned. Nếu cùng handler còn `site.css` thay đổi thì có nguy cơ stale.

**4. Thymeleaf có tự đổi `href="/assets/css/site.css"` thành URL hash không?**  
Không nên giả định. Dùng `th:href="@{/assets/css/site.css}"` với content resource chain và ResourceUrlEncodingFilter, rồi kiểm thử HTML render thật.

**5. `spring.web.resources.chain.cache` có phải browser Cache-Control không?**  
Không. Đó là cache resolver/resource chain trong JVM.

**6. ETag có tác dụng gì khi HTML/API không có URL hash?**  
Nó cho phép conditional request; khi selected representation không đổi, server trả 304 body rỗng và client tái sử dụng body cache.

**7. Spring static handler có tự phát ETag mạnh cho mọi file không?**  
Không nên dựa vào giả định đó. Static handler thường hỗ trợ Last-Modified; content version URL là cơ chế khác ETag.

**8. Nếu HTML đã có JS_R2 nhưng backend rollback API về R1, có chắc app chạy?**  
Không. Tab cũ hoặc HTML/JS đã cache có thể gọi API mới. Cần API compatibility hoặc controlled reload.

**9. Vì sao phải giữ old hashed assets sau deploy?**  
Vì client có thể còn giữ HTML cũ trỏ tới URL hash R1, và chưa từng tải hoặc đã evict tệp R1 khỏi browser cache.

**10. Content hash MD5 của Spring có giống SRI không?**  
Không. MD5 URL strategy phục vụ versioning/cache busting, SRI dùng hash cryptographic riêng cho integrity của subresources.

**11. CDN có được cache một response cá nhân hóa chỉ vì URL giống nhau không?**  
Không an toàn. Phải dùng auth-aware cache policy, private/no-store hoặc thiết kế phân vùng rõ, tránh cache shared user data.

**12. Tại sao 304 không có JSON body mà vẫn hữu ích?**  
Vì browser/cache đã có representation từ 200 trước đó; 304 chỉ nói bản đó chưa thay đổi và cung cấp metadata cache.

**13. Nếu tệp bị gzip, ETag/URL hash phải xét những gì?**  
Selected representation, Content-Encoding/Vary và cách hash tính trước/sau nén; không gộp nhầm các variants.

**14. Service worker có phải tuân theo browser HTTP Cache-Control khi dùng Cache Storage API không?**  
Không tự động. Service worker có caching code và lifecycle riêng, phải được thiết kế/kiểm thử.

**15. Một Java unit test controller có chứng minh asset URL thực sự chứa hash không?**  
Chưa. Cần render Thymeleaf qua web runtime thực, rồi HTTP GET chính URL được sinh ra.

## 27. Tài liệu chính thức

1. **Spring Boot 3.3 — Servlet Web Applications / Static Content**: mặc định static locations, versioned resource URLs và `ResourceUrlEncodingFilter` auto-config cho Thymeleaf/FreeMarker. https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html
2. **Spring Boot 3.3 — Common Application Properties**: `spring.web.resources.chain.*`, `spring.web.resources.cache.cachecontrol.*`, `spring.thymeleaf.cache`. https://docs.spring.io/spring-boot/3.3/appendix/application-properties/
3. **Spring Framework — Static Resources (Spring MVC)**: `ResourceHttpRequestHandler`, `VersionResourceResolver`, `ContentVersionStrategy`, `ResourceUrlProvider` và `ResourceUrlEncodingFilter`. https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/static-resources.html
4. **Spring Framework — HTTP Caching (MVC)**: Cache-Control, ETag và conditional request behavior. https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-caching.html
5. **Spring Framework — Resource Handling (WebFlux)**: tương ứng reactive resource handling và cache policies. https://docs.spring.io/spring-framework/reference/web/webflux/config.html
6. **Spring Boot 3.3 — Testing Spring Boot Applications**: `@SpringBootTest(RANDOM_PORT)` và `@LocalServerPort`. https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html
7. **Thymeleaf + Spring Integration**: `th:href` URL expressions và Spring MVC link rewriting. https://www.thymeleaf.org/doc/tutorials/3.1/thymeleafspring.html
8. **RFC 9111 — HTTP Caching**: Cache-Control, validators, Vary, freshness, shared/private caches và conditional requests. https://www.rfc-editor.org/rfc/rfc9111.html
9. **RFC 9110 — HTTP Semantics**: 304 Not Modified, If-None-Match, ETag, Last-Modified và conditional requests. https://www.rfc-editor.org/rfc/rfc9110.html
10. **MDN — Cache-Control** (giải thích tương thích browsers và immutable): https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Cache-Control
11. **MDN — Service Worker Cache API**: Cache Storage và sự khác biệt với HTTP cache. https://developer.mozilla.org/en-US/docs/Web/API/Cache
12. **NGINX — Proxy Module**: proxy caching/cache key/revalidation/header handling. https://nginx.org/en/docs/http/ngx_http_proxy_module.html

**Kết luận thực hành:** Để phục vụ giao diện hiệu quả mà vẫn deploy/rollback an toàn, hãy **revalidate HTML**, dùng **URL có content hash cho CSS/JS**, đặt **immutable cache chỉ cho tài nguyên thật sự bất biến**, không cache shared dữ liệu cá nhân và dùng **ETag/304 cho API public cần revalidation**. Phân biệt rõ cache tại browser, CDN, service worker, Spring resource chain và template engine. Kiểm thử bằng HTTP thật qua Spring Boot `RANDOM_PORT`, sau đó thêm thử nghiệm R1→R2/rollback và CDN/browser staging để xác nhận policy ở toàn bộ đường đi.