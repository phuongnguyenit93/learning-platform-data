# Resource chain, phiên bản theo nội dung và vô hiệu hóa bộ nhớ đệm cũ

**Module:** Spring Boot - web-runtime  
**Chủ đề cha:** Tài nguyên tĩnh

## 1. Tình huống và mục tiêu

Một website Spring Boot phục vụ trang HTML với CSS, JavaScript, ảnh và font:

~~~text
GET /assets/css/site.css
GET /assets/js/app.js
~~~

Sau khi deploy bản mới, nội dung CSS/JS đã thay đổi nhưng một số người dùng vẫn thấy giao diện hoặc mã JavaScript cũ. Lý do thường là **browser, proxy, CDN hoặc service worker vẫn giữ response theo URL cũ**. Khi file đổi mà URL giữ nguyên, cache có thể tiếp tục sử dụng bytes cũ cho đến khi hết freshness lifetime hoặc bị vô hiệu hóa bằng một cơ chế riêng.

**Giải pháp cho tài nguyên bất biến** là gắn phiên bản dựa trên bytes vào URL:

~~~text
/assets/css/site.css
      |
      v
/assets/css/site-<content-hash>.css

Thay đổi bytes -> hash đổi -> URL đổi -> cache key mới.
Không đổi bytes -> URL không đổi -> tận dụng lại cache cũ.
~~~

Trong Spring, **resource chain** có thể tạo và phân giải URL như vậy. Nhưng bài toán hoàn chỉnh cần thêm **Cache-Control**, cập nhật link trong HTML, giữ tài nguyên bản cũ khi rollout và hiểu các tầng cache bên ngoài ứng dụng.

Bài học hướng đến các năng lực:

1. Hiểu **ResourceHttpRequestHandler/ResourceWebHandler**, **ResourceResolver**, **ResourceTransformer** và vai trò của resource chain.
2. Phân biệt **ContentVersionStrategy** với **FixedVersionStrategy** và quy tắc tạo URL đúng.
3. Đặt **Cache-Control** cho asset và HTML phù hợp; hiểu **ETag**, **Last-Modified**, **304**, **no-cache**, **no-store**, **immutable**.
4. Thiết lập ví dụ Spring Boot 3.x + Java 17+ cho Spring MVC và nhận biết điểm khác của WebFlux.
5. Thiết kế phát hành tránh lỗi cache cũ, chunk 404, CDN giữ bản cũ hoặc người dùng nhận HTML/JS từ hai release khác nhau.

## 2. Resource chain xử lý tài nguyên tĩnh thế nào?

Spring Boot 3.x mặc định tìm static resource tại các classpath location phổ biến:

- **classpath:/META-INF/resources/**
- **classpath:/resources/**
- **classpath:/static/**
- **classpath:/public/**

Trong **Spring MVC**, Spring dùng **ResourceHttpRequestHandler**; trong **Spring WebFlux**, Spring dùng **ResourceWebHandler**. Static mapping thường là **/**, có thể thay đổi bằng **spring.mvc.static-path-pattern** (MVC) hoặc **spring.webflux.static-path-pattern** (WebFlux).

Resource chain kết hợp hai nhóm thành phần:

| Thành phần | Nhiệm vụ | Ví dụ |
| --- | --- | --- |
| **ResourceResolver** | Ánh xạ URL sang tài nguyên; tìm và trả đường dẫn public. | **VersionResourceResolver**, **PathResourceResolver**, **EncodedResourceResolver** |
| **ResourceTransformer** | Biến đổi nội dung hoặc liên kết bên trong tài nguyên trước khi phục vụ. | **CssLinkResourceTransformer** khi được cấu hình đúng |

Một yêu cầu dùng đường dẫn có fingerprint có thể đi qua:

~~~text
Browser: GET /assets/css/site-<hash>.css
       |
       v
HandlerMapping chọn resource handler /assets/**
       |
       v
VersionResourceResolver kiểm tra version của URL
       |
       v
Resolver chain tìm site.css tại resource locations
       |
       v
Transformer (nếu có) xử lý nội dung/link
       |
       v
Resource handler gửi response + HTTP cache headers
~~~

Có hai hướng xử lý cần phân biệt:

- **Inbound:** một URL đã versioned được phân giải và xác thực theo version của tài nguyên hiện có; request không được giải quyết đúng sẽ không tự động biến thành file bất kỳ.
- **Outbound:** khi render HTML hoặc sinh asset link, **ResourceUrlProvider** áp dụng chain để tạo đường dẫn public có version. Nếu template hay JavaScript tự ghi chuỗi URL gốc, Spring không có lý do để tự đổi link đó.

Ví dụ chỉ thay tên file trên HTML thành **site-something.css** mà không có resolver hoặc file tương ứng rất dễ gây **404**. Muốn cache busting hoạt động, **khâu tạo link** và **khâu nhận URL** phải đồng nhất.

## 3. ContentVersionStrategy: fingerprint theo bytes

**ContentVersionStrategy** dùng digest **MD5 tính từ nội dung tài nguyên** và chèn version vào đường dẫn trước phần mở rộng file.

~~~text
File gốc:
  src/main/resources/static/assets/css/site.css

URL logic:
  /assets/css/site.css

URL fingerprint khi thực sự được resolve:
  /assets/css/site-<32-ky-tu-hex>.css
~~~

Ví dụ minh họa, không phải hash thật của file này:

~~~text
/assets/css/site-0123456789abcdef0123456789abcdef.css
~~~

Chính **bytes** quyết định digest: thay một khoảng trắng trong CSS cũng có thể đổi hash. Khi nội dung giữ nguyên giữa hai lần build, URL tương ứng giữ nguyên. Vì vậy trình duyệt/CDN có thể cache rất lâu mà vẫn phân biệt được tài nguyên mới.

**MD5 ở đây chỉ nhằm tạo fingerprint/cache key**, không cung cấp kiểm chứng chữ ký mật mã. Đừng đánh đồng version string với **HTTP ETag**, **Subresource Integrity (SRI)**, code signing hoặc chữ ký phát hành. Mỗi cơ chế có mục đích và yêu cầu tin cậy khác nhau.

**FixedVersionStrategy** dùng một chuỗi phiên bản do release quản lý, ví dụ **v12**:

~~~text
/assets/js/loader.js
      |
      v
/v12/assets/js/loader.js
~~~

Fixed version phù hợp khi cách nạp resource không cho phép sửa tên file (chẳng hạn một số JavaScript module loader), hoặc bạn có quy trình phát hành bắt buộc tăng version. Nhược điểm: **nếu bytes thay đổi mà quên tăng v12, URL vẫn cũ và browser có thể dùng bản cũ**. Spring Boot cho phép áp dụng content và fixed strategy theo path pattern khác nhau.

Với **JS import động, module graph, source map**, việc tự chèn hash vào đường dẫn có thể phá các tham chiếu nội bộ. Khi frontend đã dùng Vite/Webpack/Rollup để sinh hashed assets và manifest, cân nhắc dùng chính manifest làm nguồn URL; không tự giả định Spring rewrite được mọi chuỗi trong bundle.

## 4. Phiên bản URL, cache trong resource chain và cache HTTP khác nhau

| Cơ chế | Có tác dụng tại đâu? | Điều không làm |
| --- | --- | --- |
| **ContentVersionStrategy** | Ánh xạ nội dung file với URL fingerprint. | Không tự đặt Cache-Control/TTL. |
| **FixedVersionStrategy** | Thêm version do ứng dụng/release chọn. | Không tự phát hiện thay đổi bytes. |
| **spring.web.resources.chain.cache** | Cache kết quả xử lý/tra cứu của resource chain **trong server**. | Không xóa browser/CDN cache. |
| **Cache-Control** | Quyết định điều kiện lưu và tái sử dụng HTTP response ở browser/proxy/CDN. | Không thay URL hay tự tăng version. |
| **ETag / Last-Modified** | Là validator cho conditional requests, giúp trả 304 khi phù hợp. | Không bắt cache còn fresh luôn gọi tới server. |
| **CDN purge** | Yêu cầu edge xóa/vô hiệu hóa object theo chính sách nhà cung cấp. | Không bảo đảm xóa bản trong browser hoặc Cache Storage của service worker. |

**Cache-Control: public, max-age=31536000** cho phép cache công khai giữ asset được coi là fresh trong tối đa một năm (theo điều kiện HTTP caching áp dụng). **immutable** cho biết nội dung của resource URL không thay đổi trong thời gian fresh, có thể giúp tránh các yêu cầu revalidation không cần thiết. Chính sách này chỉ hợp khi URL là bất biến và dữ liệu thật sự công khai.

**Cache-Control: no-cache** dễ bị hiểu sai: response **được phép lưu**, nhưng **phải được revalidate trước khi dùng lại**. Đây là lựa chọn thường phù hợp cho HTML entrypoint/manifest, nơi bạn muốn người dùng nhanh chóng nhận link tới assets release mới.

**Cache-Control: no-store** yêu cầu **không lưu response**. Thích hợp khi chính sách dữ liệu nhạy cảm yêu cầu; không phải giải pháp mặc định cho mọi CSS/JS công khai. **max-age=0** thường làm response stale ngay; **must-revalidate** yêu cầu không dùng bản stale khi chưa xác nhận hợp lệ theo quy định caching. Có thể phối hợp **no-cache, max-age=0, must-revalidate** cho HTML.

**ETag / Last-Modified / 304**: server có thể trả validator. Khi cache cần revalidate, client gửi **If-None-Match** hoặc **If-Modified-Since**. Nếu tài nguyên chưa đổi, server có thể trả **304 Not Modified** không kèm body. Nếu endpoint không sinh validator hoặc điều kiện không thỏa, vẫn có thể phải trả **200** với body mới. Version hash ở URL và ETag không phải cùng một cơ chế.

## 5. Chính sách cache theo loại nội dung

| Loại response | Chiến lược URL | Cache-Control gợi ý | Vì sao |
| --- | --- | --- | --- |
| CSS/JS/font/icon công khai, phát hành bất biến | **URL chứa hash nội dung** | **public, max-age dài**, có thể **immutable** | Khi file đổi sẽ có URL mới; bản không đổi tái dùng từ cache. |
| HTML entrypoint, index, tài liệu tham chiếu bundle/manifest | **URL ổn định** | **no-cache** hoặc TTL ngắn + revalidation | Client phải có cơ hội khám phá link mới sau deploy. |
| Dữ liệu API theo người dùng, tài liệu nhạy cảm | Tùy nghiệp vụ | **private/no-store** nếu phù hợp | Tránh shared cache lưu dữ liệu sai hoặc nhạy cảm. |
| Ảnh upload có URL cố định nhưng nội dung được thay | URL có version, hoặc validator/TTL/purge | Theo chính sách thay đổi nội dung | URL cố định cache dài có nguy cơ hiển thị ảnh cũ. |
| Service worker script, frontend app shell offline | Chính sách update của SW | Theo vòng đời SW, không suy từ CSS | Cache Storage do SW quản lý là lớp riêng. |

**Sai lầm quan trọng:** đặt **max-age một năm cho cả HTML**. Nếu HTML V1 chứa link hash H1 vẫn fresh cả năm, browser sẽ không khám phá asset H2 dù Spring đã tạo H2 từ CSS mới.

**Sai lầm khác:** bật content strategy rồi giữ link cứng **/assets/css/site.css** trong HTML. Người dùng tiếp tục tải URL không có version, nên browser có thể xem file mới và cũ là cùng cache key.

## 6. Demo Spring Boot 3.x + Java 17+: Spring MVC, Thymeleaf và content hash

Đây là ví dụ chạy được trong **project Spring Boot 3.x đã có Gradle wrapper/plugins**, dùng Java 17 trở lên. Thêm hai dependency vào khối **dependencies** của **build.gradle** (Groovy DSL):

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-thymeleaf'
}
~~~

Không thêm **@EnableWebMvc**: sử dụng auto-configuration Spring MVC và tự động hỗ trợ resource handling của Boot.

### 6.1. Cấu hình asset path và resource chain

Tạo **src/main/resources/application.properties**:

~~~properties
server.port=8080

# Chuyen handler tai nguyen tinh sang /assets/**
spring.mvc.static-path-pattern=/assets/**

# Bat resource chain va content version cho resource cua handler
spring.web.resources.chain.strategy.content.enabled=true
spring.web.resources.chain.strategy.content.paths=/**
spring.web.resources.chain.cache=true

# Cache dai cho static assets /assets/**; khong ap dung cho GET / cua controller
spring.web.resources.cache.cachecontrol.max-age=365d
spring.web.resources.cache.cachecontrol.cache-public=true
~~~

Ý nghĩa:

- **spring.mvc.static-path-pattern=/assets/**: file **src/main/resources/static/assets/css/site.css** có URL logic **/assets/css/site.css**. Không mở rộng cache dài lên route HTML **/** do controller xử lý.
- **spring.web.resources.chain.strategy.content.enabled=true** bật content versioning; **paths=/** áp dụng các path của resource handler. Thuộc tính này không tự fingerprint tất cả API/controller.
- **spring.web.resources.chain.cache=true** cache xử lý ở resource chain, giúp giảm việc lookup/hash lặp lại; Spring Boot 3.3 mặc định là true.
- Hai cấu hình **spring.web.resources.cache.cachecontrol.*** đặt HTTP cache header cho các resource thuộc handler. **365d** tương ứng 31.536.000 giây.

**Giới hạn của cấu hình ngắn này:** resource handler có thể vẫn trả file qua URL gốc không có hash **/assets/css/site.css**, và URL gốc cũng có thể nhận cache header dài. Vì vậy phải bảo đảm mọi HTML/client liên kết tới **URL đã fingerprint**. Hệ thống lớn có thể tách policy theo đường dẫn versioned tại CDN/edge hoặc dùng custom handler để tránh cache dài cho URL cố định.

### 6.2. Application và controller HTML

Tạo **src/main/java/com/example/assetcache/AssetCacheApplication.java**:

~~~java
package com.example.assetcache;

import jakarta.servlet.http.HttpServletResponse;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpHeaders;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;

@SpringBootApplication
public class AssetCacheApplication {
    public static void main(String[] args) {
        SpringApplication.run(AssetCacheApplication.class, args);
    }
}

@Controller
class PageController {
    @GetMapping("/")
    public String index(HttpServletResponse response) {
        response.setHeader(
                HttpHeaders.CACHE_CONTROL,
                "no-cache, max-age=0, must-revalidate"
        );
        return "index";
    }
}
~~~

**AssetCacheApplication** khớp với tên file; **PageController** là top-level class package-private trong cùng package và được component scan. Template **index** được Spring Boot tìm trong **src/main/resources/templates/**. Controller chủ động đặt cache policy của HTML, độc lập với resource handler của static assets.

### 6.3. Thymeleaf sinh URL fingerprint

Tạo **src/main/resources/templates/index.html**:

~~~html
<!doctype html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Resource chain demo</title>
    <link rel="stylesheet"
          th:href="@{/assets/css/site.css}"
          href="/assets/css/site.css">
    <script defer
            th:src="@{/assets/js/app.js}"
            src="/assets/js/app.js"></script>
</head>
<body>
    <h1>Resource chain demo</h1>
    <p id="status">loading</p>
</body>
</html>
~~~

Trong Spring Boot MVC khi dùng Thymeleaf/FreeMarker, **ResourceUrlEncodingFilter** được tự cấu hình để các URL được template engine encode có thể đi qua **ResourceUrlProvider**. Với resource chain đã bật, HTML trả về thường dùng:

~~~html
<link rel="stylesheet" href="/assets/css/site-<hash>.css">
<script defer src="/assets/js/app-<hash>.js"></script>
~~~

Các ký hiệu **<hash>** ở trên chỉ minh họa, không phải output thực; giá trị phải được tính từ bytes đúng của từng file. **th:href/th:src** mới là đường tạo URL được hỗ trợ; thuộc tính HTML **href/src** thuần, file HTML tĩnh hoặc đường dẫn hardcoded trong JS sẽ không tự được xử lý tương tự.

### 6.4. Tạo file CSS và JS

Tạo **src/main/resources/static/assets/css/site.css**:

~~~css
body {
    font-family: sans-serif;
    color: #17324d;
}
~~~

Tạo **src/main/resources/static/assets/js/app.js**:

~~~javascript
document.getElementById("status").textContent = "ready";
~~~

Cấu trúc project cần có:

~~~text
src/
  main/
    java/com/example/assetcache/
      AssetCacheApplication.java
    resources/
      application.properties
      templates/
        index.html
      static/
        assets/
          css/site.css
          js/app.js
~~~

Chạy project đã cấu hình Spring Boot plugin và Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

Truy cập **http://localhost:8080/**: nội dung hiển thị từ **loading** thành **ready** khi JavaScript được chạy. Nếu CSS/JS phục vụ qua content strategy, link trong HTML response có hash, nhưng **tên file thực trên classpath vẫn giữ nguyên**.

### 6.5. Kiểm thử từng bước bằng curl

Trên terminal Bash khác:

~~~bash
curl -fsS -D html-headers.txt -o page.html http://localhost:8080/

# Lay URL CSS do template + resource chain thuc su tao
grep -oE '/assets/css/site-[0-9a-f]{32}\.css' page.html

# Doc header cua HTML
cat html-headers.txt
~~~

Đối chiếu:

- HTML route **/** trả **Cache-Control: no-cache, max-age=0, must-revalidate** (thứ tự header có thể khác).
- Trong HTML tồn tại tên CSS có **32 ký tự hex** và tên JS có hash tương ứng. Nếu chỉ thấy link cũ, kiểm tra Thymeleaf dependency, tag **th:href/th:src**, filter và static mapping.
- Browser truy cập các link fingerprint thực, không gặp 404.

Lấy path CSS từ chính response rồi kiểm tra asset:

~~~bash
css_path=$(grep -oE '/assets/css/site-[0-9a-f]{32}\.css' page.html | head -n 1)
curl -fsSI "http://localhost:8080$css_path"
~~~

Kết quả kỳ vọng cho URL hợp lệ: HTTP status **200**, content type **text/css** và **Cache-Control** cho public cache với max-age một năm. Không khẳng định ETag luôn xuất hiện; validator phụ thuộc cấu hình và metadata của tài nguyên.

**Thử invalidation bằng content:** sửa một ký tự trong **site.css**, build/khởi động lại app để đảm bảo server sử dụng bytes mới, gọi lại **GET /**. URL CSS phải đổi trong HTML mới; URL JS không cần đổi nếu bytes **app.js** không thay. Đối với JAR/container production, thay đổi được phân phối bằng **bản build/deploy mới**, không sửa tài nguyên trực tiếp trong JAR đang chạy.

## 7. Cấu hình ResourceHandler bằng Java khi cần kiểm soát chi tiết

Bạn có thể cấu hình resolver, location, transformation và cache riêng bằng **WebMvcConfigurer**. Đây là **phương án thay thế** cho cấu hình strategy + static-path-pattern ở mục 6, không cần gắn cả hai cấu hình tương đương lên cùng resource path.

Một tệp độc lập **src/main/java/com/example/assetcache/AssetsMvcConfig.java**:

~~~java
package com.example.assetcache;

import java.time.Duration;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.CacheControl;
import org.springframework.web.servlet.config.annotation.ResourceHandlerRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;
import org.springframework.web.servlet.resource.VersionResourceResolver;

@Configuration(proxyBeanMethods = false)
public class AssetsMvcConfig implements WebMvcConfigurer {

    @Override
    public void addResourceHandlers(ResourceHandlerRegistry registry) {
        registry.addResourceHandler("/assets/**")
                .addResourceLocations("classpath:/static/assets/")
                .setCacheControl(
                        CacheControl.maxAge(Duration.ofDays(365))
                                .cachePublic()
                                .immutable())
                .resourceChain(true)
                .addResolver(
                        new VersionResourceResolver()
                                .addContentVersionStrategy("/**"));
    }
}
~~~

**VersionResourceResolver** bổ sung content strategy; **resourceChain(true)** dùng cache lookup trong chain; **CacheControl.maxAge(...).cachePublic().immutable()** điều khiển HTTP cache headers. Hàm **immutable()** có trên Spring Framework 6.x; chỉ dùng nếu cùng URL không bị thay bytes. Class này cần **spring-boot-starter-web** và Boot MVC; không dùng **@EnableWebMvc** nếu không có chủ đích thay toàn bộ auto-config.

Trong môi trường thật, phân loại đường dẫn để **HTML không nằm trong handler có cache một năm**; nhiều handler có thể cấp TTL khác nhau. Khi thêm custom handler, kiểm tra mapping nào thật sự được chọn, tránh chồng lấn một handler tự viết với default resource mapping. Nếu chọn Java config này, bỏ các thuộc tính strategy/handler tương đương ở mục 6 để tránh khó xác định nơi áp dụng.

### Thứ tự resolver và CSS links

Khi muốn sử dụng file **.gz/.br** precompressed với **EncodedResourceResolver** đồng thời dùng **VersionResourceResolver**, Spring Framework hướng dẫn đăng ký **EncodedResourceResolver trước VersionResourceResolver**, nhằm tính fingerprint trên bản tài nguyên **chưa nén**. Tên version không nên thay đổi chỉ vì các biến thể content-encoding khác nhau.

**CssLinkResourceTransformer** có thể sửa các link tài nguyên như **url(...)** trong CSS nếu được cấu hình đúng. Đối với JS import, module graph hoặc asset manifest của bundler, không mặc định giả định Spring rewrite được mọi link; thông thường build tool nên giữ toàn bộ đồ thị dependency nhất quán.

## 8. Vô hiệu hóa cache cũ phải tính đến vòng đời deployment

Một ví dụ phát hành:

~~~text
Release V1: HTML V1 -> /assets/js/app-H1.js
Release V2: HTML V2 -> /assets/js/app-H2.js
~~~

Khi HTML mới tham chiếu URL mới, người dùng sẽ lấy H2 dù H1 còn trong cache. **Không nhất thiết purge H1** mỗi lần phát hành nếu H1 bất biến và không có sự cố. Nhưng chính sách chưa hoàn chỉnh nếu **xóa H1 ở origin ngay sau deploy**.

Quy trình đề xuất:

1. **Build assets ổn định**; mỗi release có HTML/manifest tham chiếu hash đúng của bundle. Nếu Spring hash resource runtime, toàn bộ instance phải có cùng bytes khi phục vụ cùng URL.
2. **Upload/phân phối assets H2 trước khi công khai HTML V2**. Nếu không, người dùng thấy HTML mới nhưng yêu cầu H2 gặp 404.
3. **Tiếp tục giữ H1 đủ lâu** cho tab cũ, HTML cũ đang cache và dynamic imports. Nếu chỉ có file gốc mới trong Spring Boot JAR V2, **VersionResourceResolver ở V2 có thể không còn phục vụ URL H1** vì hash đó không khớp nội dung file hiện tại.
4. **Cập nhật HTML V2** và đảm bảo HTML revalidate/TTL ngắn để browser khám phá H2. Không dùng TTL một năm cho HTML entrypoint.
5. **Giám sát lỗi 404, chunk load failure, cache hit ratio, response headers, phân phối release giữa các node**, rồi mới dọn H1 theo thời gian tương thích được chọn.

**Rolling deployment:** trong giai đoạn V1 và V2 chạy đồng thời sau load balancer, một request HTML có thể đến node V1 trong khi request asset H1 lại đến node V2. Node V2 chỉ có file mới nên H1 trả 404. Giải pháp phổ biến là **asset storage/CDN độc lập giữ nhiều release**, publish assets trước HTML, hoặc thiết kế cơ chế phát hành nguyên tử/affinity đã được kiểm chứng. Đừng chỉ nói "CDN sẽ tự cache" vì request cache miss vẫn có thể đến origin sai version.

**Khi cần thu hồi gấp vì bảo mật hoặc lỗi nghiêm trọng**, chờ max-age dài có thể không phù hợp. Cần kế hoạch invalidation tại CDN, gỡ file ở origin, thay asset URL/HTML, và lưu ý browser cache/service worker có thể tiếp tục giữ bản sao đã nhận. Purge edge không thể bảo đảm xóa sạch mọi thiết bị người dùng.

## 9. Các tầng cache phải được xác minh riêng

~~~text
Browser
  |- HTTP cache (theo URL và headers)
  |- Service Worker / Cache Storage (nếu app có)
  |
  v
CDN / reverse proxy (co cache key, TTL va chinh sach edge rieng)
  |
  v
Spring Boot resource chain cache (trong tien trinh)
  |
  v
JAR classpath / static directory / asset origin
~~~

**Browser HTTP cache:** căn cứ URL, Cache-Control, Vary và validator. Kiểm tra Chrome/Firefox DevTools Network cho từng response; đừng suy luận từ một lần hard reload duy nhất.

**Service worker:** có thể trả bản cũ từ Cache Storage ngay cả khi HTTP cache đã cập nhật. Quản lý lifecycle, đổi cache name theo release, xác minh chiến lược cleanup và cơ chế cập nhật SW. Khi còn tab cũ cần dynamic import H1, dọn quá sớm có thể làm lỗi.

**CDN/ingress:** có thể ghi đè TTL từ origin, gộp query, bỏ query khỏi cache key, cache HTML lâu hơn dự kiến hoặc chạy stale-while-revalidate. Xem cấu hình và response header thật tại edge, không chỉ local Spring Boot.

**Spring resource chain cache:** giữ kết quả tra cứu trong ứng dụng. Cache này không có quyền điều khiển cache đã nằm ở trình duyệt; khi file trên disk đổi ngay trong một process đang chạy, kết quả đã cache có thể không cập nhật như kỳ vọng. Với production, xuất bản immutable artifact và khởi động instance bản release mới là mô hình dễ kiểm soát hơn.

## 10. Spring WebFlux: giống chain, khác cách rewrite link

Trong WebFlux, tài nguyên tĩnh được phục vụ bởi **ResourceWebHandler** thay cho **ResourceHttpRequestHandler** của MVC. Đường dẫn mặc định được thay bằng **spring.webflux.static-path-pattern**. **WebFluxConfigurer#addResourceHandlers** hỗ trợ chain, resolvers và CacheControl tương tự về chức năng.

Ví dụ class cấu hình dành cho **một project WebFlux độc lập** đã có **spring-boot-starter-webflux**:

~~~java
package com.example.reactiveassets;

import java.time.Duration;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.CacheControl;
import org.springframework.web.reactive.config.ResourceHandlerRegistry;
import org.springframework.web.reactive.config.WebFluxConfigurer;
import org.springframework.web.reactive.resource.VersionResourceResolver;

@Configuration(proxyBeanMethods = false)
public class ReactiveAssetsConfig implements WebFluxConfigurer {

    @Override
    public void addResourceHandlers(ResourceHandlerRegistry registry) {
        registry.addResourceHandler("/assets/**")
                .addResourceLocations("classpath:/static/assets/")
                .setCacheControl(
                        CacheControl.maxAge(Duration.ofDays(365)).cachePublic())
                .resourceChain(true)
                .addResolver(
                        new VersionResourceResolver()
                                .addContentVersionStrategy("/**"));
    }
}
~~~

Tạo file **ReactiveAssetsConfig.java** ở đúng package được component scan. Ví dụ này là một **config class**, không phải chương trình chạy độc lập; app chính cần cấu hình Spring Boot WebFlux.

Khác biệt then chốt: **ResourceUrlEncodingFilter** là cơ chế gắn với servlet response của MVC. WebFlux không có cơ chế transparent URL rewrite tương đương cho mọi template. Trong WebFlux, bạn cần **chủ động** lấy versioned URLs qua **ResourceUrlProvider** theo API reactive hoặc dùng manifest/hash do frontend build sinh và truyền vào template. Không copy giả định "Thymeleaf tự viết lại mọi link" từ demo MVC sang WebFlux.

## 11. Kiểm thử và đối chiếu sau build/deploy

Cần kiểm tra những điều sau tại origin **và** CDN/ingress, không chỉ localhost:

1. **HTML entrypoint:** GET / trả revalidation header phù hợp và dẫn tới CSS/JS URL đã versioned, không phải URL logic cũ.
2. **Versioned assets:** GET đường dẫn được trích từ HTML trả **200**, đúng MIME type và bytes mong đợi, Cache-Control phù hợp.
3. **Nội dung đổi:** CSS đổi bytes thì URL CSS đổi; JS không đổi thì URL JS giữ nguyên. Không hardcode digest nếu không có fixture build cố định.
4. **Old release:** nếu HTML V1 vẫn tồn tại, đường dẫn H1 phải tiếp tục được phục vụ theo chính sách retention. Không để route fallback trả HTML 200 cho một JS/CSS 404.
5. **URL cố định:** nếu còn đường dẫn không hash, xác nhận TTL/ngữ nghĩa cache của nó không ngầm giữ bản lỗi quá lâu.
6. **Transitive assets:** kiểm tra CSS url(font/image), JS dynamic import, chunk, source map, path prefix và context path.
7. **Rolling release:** kiểm tra request asset trong giai đoạn hai phiên bản backend đồng thời chạy.
8. **Service worker/CDN:** xác nhận cache key, bản giữ, thời gian hết hạn, chính sách purge và update hoạt động.

Nếu server cung cấp **Last-Modified**, có thể thử conditional request:

~~~bash
curl -sSI http://localhost:8080/assets/css/site.css

# Thay placeholder bang gia tri Last-Modified vua nhan neu server co:
curl -sSI -H 'If-Modified-Since: <gia-tri-Last-Modified>' \
    http://localhost:8080/assets/css/site.css
~~~

**304 chỉ là kết quả có thể xảy ra** khi validator phù hợp và file không đổi. Placeholder **<gia-tri-Last-Modified>** phải được thay thật; đừng chép nguyên xi làm command kiểm thử. Với versioned asset còn fresh, việc không revalidate cũng là hành vi mong muốn.

## 12. Chẩn đoán các lỗi thường gặp

| Hiện tượng | Điểm cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| Bật content strategy nhưng HTML vẫn chứa site.css | URL đang hardcode hoặc không qua ResourceUrlProvider/ResourceUrlEncodingFilter. | Dùng Thymeleaf/FreeMarker URL expression (MVC), custom helper hoặc build manifest. |
| URL có hash nhưng 404 | Sai pattern/location, hash không khớp bytes, hoặc request chạy vào origin release khác. | Kiểm tra mapping, classpath và lưu giữ assets nhiều release. |
| Trang vẫn cũ sau deploy | HTML/manifest bị cache dài, service worker hoặc CDN còn bản cũ. | Revalidation HTML, xem Cache Storage và edge TTL/cache key. |
| Có lỗi chunk JavaScript sau rolling deploy | Tab cũ cần H1 nhưng node mới chỉ có H2. | Giữ H1 ở asset origin chung; triển khai assets trước HTML. |
| max-age một năm cho mọi nội dung | HTML và tài nguyên có URL cố định bị giữ cũ. | Phân loại đường dẫn và cache policy theo tài nguyên. |
| Hash không đổi dù file source đổi | Build chưa copy tài nguyên, JVM resource chain cache, request đến node cũ. | Kiểm tra bytes trong artifact thực, restart/redeploy và origin đang phục vụ. |
| Hash đổi khi điều chỉnh gzip/br | Thứ tự resolver sai hoặc hash tính trên representation không ổn định. | Đặt EncodedResourceResolver trước VersionResourceResolver và kiểm tra bytes được tính. |
| WebFlux không tự rewrite th:href | Không có ResourceUrlEncodingFilter kiểu MVC. | Tạo URL qua ResourceUrlProvider/reactive API hoặc manifest. |
| JS module import hỏng | Chuỗi import không được cập nhật khi đường dẫn đổi. | Dùng bundler, fixed version strategy hoặc quy trình đồng bộ dependency graph. |
| Chạy CDN purge nhưng browser vẫn thấy bản cũ | CDN không điều khiển browser HTTP cache/service worker. | Đổi URL/HTML reference và quản lý riêng vòng đời browser/SW. |

## 13. Tình huống vận dụng

**Tình huống A:** HTML V1 tham chiếu **app-H1.js**. Bạn deploy V2 và xóa mọi asset V1 khỏi origin. Một tab cũ thực hiện import động app-H1.js sau khi deploy. Điều gì có thể xảy ra? **404** dù link V2 và H2 đều đúng. Cần giữ H1 đủ lâu hoặc phục vụ từ kho asset có nhiều bản.

**Tình huống B:** CSS đã được Spring tạo URL hash mới, nhưng trang vẫn gọi **/assets/css/site.css**. Vì sao? Đường dẫn trong HTML chưa được xử lý qua **ResourceUrlProvider/ResourceUrlEncodingFilter**; cần sửa khâu sinh link trước khi kỳ vọng cache busting hoạt động.

**Tình huống C:** Một file được phục vụ ở URL fingerprint bất biến và không có dữ liệu riêng tư. Có thể cache một năm không? **Có**, nếu xác định đúng chính sách retention, bảo đảm URL không bị đổi nội dung và có kế hoạch thu hồi khi xảy ra sự cố.

**Tình huống D:** Cả browser và CDN đều có asset H1 còn fresh; HTML V2 trỏ H2. Browser có cần purge H1 trước khi tải H2 không? **Không**: H2 là URL khác, cache key khác. H1 có thể hết hạn tự nhiên. Vấn đề là HTML và CDN phải thực sự cung cấp link/bytes H2 chính xác.

**Câu hỏi tự kiểm tra:** (1) ContentVersionStrategy lấy version từ đâu? (2) Khác nhau giữa no-cache và no-store? (3) Vì sao max-age dài cho index.html nguy hiểm? (4) ResourceUrlEncodingFilter dùng ở MVC hay WebFlux? (5) Cache resource chain có xóa browser cache được không? (6) Vì sao cần giữ asset H1 trong rollout? (7) ETag có đồng nghĩa với version hash ở URL không?

**Đáp án:** (1) Digest MD5 từ bytes tài nguyên; (2) lưu và revalidate so với cấm lưu; (3) HTML không khám phá H2; (4) MVC/Servlet; (5) không; (6) HTML/tab cũ và mixed-version instances vẫn gọi H1; (7) không, hai cơ chế khác nhau.

## 14. Tài liệu tham khảo chính thống

- **Spring Boot 3.3 – Servlet Web Applications / Static Content, Cache Busting:** https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html
- **Spring Boot 3.3 – Common Application Properties:** https://docs.spring.io/spring-boot/3.3/appendix/application-properties/
- **Spring Framework – MVC Static Resources:** https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/static-resources.html
- **Spring Framework – MVC HTTP Caching:** https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-caching.html
- **Spring Framework 6.1 – CacheControl Javadoc:** https://docs.spring.io/spring-framework/docs/6.1.3/javadoc-api/org/springframework/http/CacheControl.html
- **Spring Boot – Reactive Web Applications:** https://docs.spring.io/spring-boot/reference/web/reactive.html
- **Spring Framework – WebFlux Static Resources:** https://docs.spring.io/spring-framework/reference/web/webflux/config.html
