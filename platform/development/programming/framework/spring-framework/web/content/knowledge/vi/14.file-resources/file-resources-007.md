# Resource chain, phiên bản tài nguyên và đường dẫn có dấu vân tay nội dung trong Spring MVC

## 1. Bài toán: static assets đã đổi nhưng client vẫn thấy nội dung cũ

Trong ứng dụng Spring MVC render trang web, CSS, JavaScript, ảnh và font thường được cache tại browser hoặc CDN để tăng tốc. Nếu tên đường dẫn không đổi sau một lần deploy, cache có thể tiếp tục phục vụ tài nguyên cũ:

```text
Release A:
  HTML -> /css/site.css
  Browser lưu CSS A, Cache-Control: max-age=2592000

Release B:
  HTML -> /css/site.css
  Server có nội dung CSS B, browser vẫn có thể dùng CSS A

Release B với content fingerprint:
  HTML -> /css/site-<hash-B>.css
  URL mới -> cache key mới -> trình duyệt tải CSS B
```

**Content fingerprint** là mã nhận diện được tính từ **bytes nội dung file** và gắn vào public URL, thường nằm trước phần mở rộng. Ví dụ hình thức `/css/site-e36d2e05253c6c7085a91522ce43a0b4.css`. Khi file đổi, fingerprint thường đổi; trình duyệt không dùng nhầm cached response của URL cũ.

**Resource chain** là cơ chế Spring MVC gồm các `ResourceResolver` và `ResourceTransformer` để tìm, kiểm tra phiên bản, biến đổi hoặc phục vụ static resources. Kết hợp chain với `ResourceUrlProvider` và `ResourceUrlEncodingFilter`, ứng dụng có thể **viết URL logic** trong template nhưng **phát URL có version** cho client mà không cần đổi tên file trong source tree.

Sau bài này, cần nắm:

- `ResourceHttpRequestHandler` và các static resource locations.
- Resolver chain so với transformer chain; inbound resource URL so với outbound generated URL.
- `VersionResourceResolver`, `ContentVersionStrategy`, `FixedVersionStrategy`.
- Bật content versioning bằng Spring Boot properties hoặc Java `WebMvcConfigurer`.
- Sinh đường dẫn fingerprint qua Thymeleaf, `ResourceUrlProvider` và `ResourceUrlEncodingFilter`.
- Kết hợp HTTP caching, deploy nhiều phiên bản và CDN để tránh 404.
- Kiểm thử HTML → URL fingerprint → GET asset bằng embedded Servlet container.

Baseline ví dụ chạy là **Java 17+, Spring Framework 6.2.x / Spring Boot 3.5.x và Spring MVC Servlet**. Spring WebFlux dùng API resource reactive riêng; không import `org.springframework.web.servlet.resource` vào ứng dụng WebFlux.

## 2. Spring Boot phục vụ static files từ đâu?

Trong một Boot Servlet app, static resources thông thường được tìm ở:

```text
classpath:/META-INF/resources/
classpath:/resources/
classpath:/static/
classpath:/public/
```

Ví dụ:

| Tệp trong source | URL logic thường gặp |
| --- | --- |
| `src/main/resources/static/css/site.css` | `/css/site.css` |
| `src/main/resources/static/js/app.js` | `/js/app.js` |
| `src/main/resources/public/images/logo.svg` | `/images/logo.svg` |
| `src/main/resources/META-INF/resources/favicon.ico` | `/favicon.ico` |

Boot thường map static content vào `/**`. Có thể đổi pattern bằng `spring.mvc.static-path-pattern` hoặc static locations bằng `spring.web.resources.static-locations`. Folder `templates/` dành cho template engine **không mặc nhiên public** như static. Trong executable JAR, `src/main/webapp` không phải lựa chọn chuẩn như WAR.

Spring MVC đăng ký `ResourceHttpRequestHandler` cho các resource handlers; handler này biết cách đọc resource, xử lý HTTP conditions như Last-Modified, cung cấp media type và chạy resource chain đã cấu hình.

**Không thêm `@EnableWebMvc` chỉ để bật static resources trong Spring Boot**: annotation này có thể khiến Spring Boot MVC auto-configuration không còn áp dụng theo cách mặc định. Nếu cần custom MVC handler, dùng `WebMvcConfigurer` mà không thêm `@EnableWebMvc`, trừ khi bạn chủ ý quản lý toàn bộ MVC infrastructure.

## 3. Sơ đồ hoạt động khi HTML tham chiếu CSS có fingerprint

```text
File trong JAR:
  classpath:/static/css/site.css
                    |
Resource handler /css/** (hoặc Boot static handler /**)
                    |
         VersionResourceResolver
                    |
         ContentVersionStrategy
                    |
    tính MD5 hex từ bytes nội dung
                    |
        ResourceUrlProvider sinh URL
                    |
   /css/site-<fingerprint>.css
                    |
Browser GET /css/site-<fingerprint>.css
                    |
DispatcherServlet / ResourceHttpRequestHandler
                    |
VersionResourceResolver:
   bóc hash từ tên, tìm file site.css,
   xác minh hash khớp resource hiện tại
                    |
PathResourceResolver tìm bytes file thật
                    |
HTTP 200 + CSS + cache headers
```

Spring không bắt buộc **tạo file vật lý có fingerprint**. File đóng gói vẫn là `site.css`; URL versioned là kết quả mapping qua resolver. URL logic `/css/site.css` thường vẫn có thể được yêu cầu trực tiếp, nên cần chính sách cache phù hợp cho cả đường dẫn không version.

### So sánh inbound và outbound

- **Outbound**: tại thời điểm render HTML, `ResourceUrlProvider` tìm public versioned path cho `/css/site.css`, ví dụ `/css/site-abc....css`.
- **Inbound**: client gửi GET vào public versioned path; `VersionResourceResolver` loại phần version và kiểm tra nó có khớp nội dung actual file không.
- **Không khớp version**: URL giả mạo hash thường không được resolver phục vụ; nhiều cấu hình trả 404.
- **Tệp không tồn tại**: version strategy không biến tài nguyên thiếu thành tài nguyên hợp lệ.

Nếu bạn hardcode `href="/css/site.css"` trong một **static HTML file** được phục vụ nguyên bytes, resource URL rewrite không tự chạy trên chuỗi tùy ý đó. Phải dùng template/helper/manifest hoặc build-time rewriting.

## 4. Các thành phần của resource chain

### 4.1. ResourceResolver chain

| Thành phần | Nhiệm vụ |
| --- | --- |
| `PathResourceResolver` | Tìm resource gốc trong configured allowed locations; thường là resolver cuối |
| `VersionResourceResolver` | Áp dụng chiến lược version, sinh/kiểm tra public URL |
| `EncodedResourceResolver` | Chọn tài nguyên đã nén sẵn như gzip/brotli khi thích hợp |
| `WebJarsResourceResolver` | Resolve version-less WebJars URLs khi có locator dependency đúng |

**Thứ tự resolver ảnh hưởng correctness.** Khi có cả `EncodedResourceResolver` và `VersionResourceResolver`, Spring yêu cầu **Encoded trước Version** để content hash được tính dựa trên tệp **không nén**, tránh khác nhau do gzip/brotli.

Resolver có thể cache kết quả lookup theo cấu hình. `resourceChain(true)` trong Java config bật resource chain caching; `spring.web.resources.chain.cache` là property của Boot cho cache chain nội bộ, không tương đương header HTTP `Cache-Control`.

### 4.2. ResourceTransformer chain

Transformer có thể thay đổi **representation** khi phục vụ. Ví dụ `CssLinkResourceTransformer` xét `@import` và `url(...)` trong CSS, tra chain rồi rewrite link tương ứng với public URL:

```css
@import "theme.css";

.banner {
  background-image: url("../images/banner.svg");
}
```

Khi đúng transformer, CSS có thể trả references tới versioned URLs. Nhưng Spring **không tự phân tích lại mọi chuỗi JavaScript** chứa URL, ES-module import, dynamic `fetch()`, source map hay JSON manifest. Khi những assets này có logic phụ thuộc URL, có thể cần bundler, fixed strategy hoặc transformer có chủ đích.

Nếu cả resolver và transformer đều cần, chú ý đúng thứ tự xử lý và test **body thực sự trả về**, không chỉ nhìn source file.

## 5. ContentVersionStrategy: hash bytes và đường dẫn fingerprint

Trong Spring Framework 6.x, `org.springframework.web.servlet.resource.ContentVersionStrategy` dùng **MD5 hex** của nội dung để tạo version đưa vào tên file. Ví dụ:

```text
Resource: /css/site.css
MD5(bytes): <32 ký tự hex của file thật>
Public URL: /css/site-<32 ký tự hex>.css
```

MD5 của file rỗng là `d41d8cd98f00b204e9800998ecf8427e`. Hash này **chỉ hợp lệ cho nội dung rỗng**, không phải cho các đoạn CSS mẫu trong bài. Không hardcode hash giả vào HTML production.

Các đặc tính:

1. Cùng resource bytes/strategy → cùng fingerprint; deploy lại không bắt buộc tạo URL mới.
2. Bytes thay đổi → fingerprint thường khác; URL mới không đụng cache key cũ.
3. Hash từ bytes, nên khác biệt encoding/newlines/chuỗi comment cũng có thể đổi URL.
4. Không phải thuật toán security signing, checksum chống giả mạo hay **Subresource Integrity (SRI)**. MD5 không phù hợp làm bảo đảm nguồn tài nguyên đáng tin.
5. Không tự minify, transpile, tạo tệp .gz/.br hoặc tạo CDN deployment manifest.
6. Phiên bản trong URL giúp invalidation; **không quyết định thời hạn cache HTTP** nếu chưa cấu hình cache headers.

### Filename path version khác query-string version

```text
ContentVersionStrategy:
  /css/site-<hash>.css

Cách thêm query thủ công khác:
  /css/site.css?v=<hash>
```

Query version có thể hoạt động, nhưng CDN/proxy policies có thể bỏ qua hoặc chuẩn hóa query parameters. Spring MVC `ContentVersionStrategy` sử dụng URL path với filename versioning. Không mô tả `?v=...` như output chuẩn của class này.

## 6. Bật resource content fingerprint trong Spring Boot 3.5

Với default Boot MVC static handler, cấu hình đơn giản trong **`src/main/resources/application.properties`**:

```properties
spring.web.resources.chain.strategy.content.enabled=true
spring.web.resources.chain.strategy.content.paths=/**
```

YAML tương đương:

```yaml
spring:
  web:
    resources:
      chain:
        strategy:
          content:
            enabled: true
            paths: "/**"
```

Chọn **một** trong properties/YAML; không khai báo trái ngược ở hai nơi rồi đoán precedence.

Với cấu hình này, các assets ở static locations mà handler quản lý có thể có versioned URLs. `/**` ở đây là pattern **tài nguyên tĩnh**, không làm URLs mọi REST endpoints tự có fingerprint.

Nếu chỉ muốn một số thư mục, scope strategy cho URL patterns cụ thể:

```properties
spring.web.resources.chain.strategy.content.enabled=true
spring.web.resources.chain.strategy.content.paths=/css/**,/js/**
```

Để áp dụng cho ảnh/fonts mà CSS references, cần đảm bảo locations/patterns của chúng cũng có versioning hoặc chọn cách build phù hợp.

### Resource chain cache nội bộ

```properties
spring.web.resources.chain.cache=true
```

Property này liên quan cache **resource resolution trong Spring**, không tự tạo `Cache-Control: max-age=...`. Khi dev chỉnh file liên tục, có thể tắt cache hoặc dùng Boot DevTools/rebuild đúng cách. Trong production JAR immutable, cache nội bộ có thể giảm overhead.

### Vì sao không cần Java config cho ví dụ cơ bản?

Boot 3.5 hỗ trợ content/fixed resource strategies qua properties. Nếu đồng thời tự thêm resource handler cho cùng đường dẫn, hãy kiểm tra chain và mapping thực sự nào được dùng: Boot properties **không được giả định tự đi vào mọi custom ResourceHandlerRegistration**.

## 7. FixedVersionStrategy: prefix version thay vì hash từng file

Có loại assets mà filename có hash gây khó, đặc biệt JS module loader với relative module paths. Spring hỗ trợ **fixed version prefix** dựa trên release:

```properties
spring.web.resources.chain.strategy.content.enabled=true
spring.web.resources.chain.strategy.content.paths=/**

spring.web.resources.chain.strategy.fixed.enabled=true
spring.web.resources.chain.strategy.fixed.paths=/js/lib/**
spring.web.resources.chain.strategy.fixed.version=v12
```

Ví dụ output:

```text
/css/site.css
    -> /css/site-<content-hash>.css

/js/lib/module.js
    -> /v12/js/lib/module.js
```

`v12` là giá trị do ứng dụng/deploy quyết định. Khi nội dung JS đổi, URL **không tự đổi** nếu quên tăng version. Đổi v12→v13 dù bytes không đổi có thể khiến browser tải lại file không cần thiết. Đừng cấu hình patterns overlapping mà không test rằng assets trong `/js/lib/**` thật sự dùng fixed thay vì content strategy.

| Tiêu chí | Content version | Fixed version |
| --- | --- | --- |
| Giá trị version | Hash content bytes | Chuỗi release định sẵn |
| Một file đổi | Thường chỉ URL file đó đổi | Cần nâng release version |
| File không đổi qua deploy | URL có thể được dùng lại | Thường URL đổi theo release |
| Phù hợp | CSS, assets độc lập, image/font | JS module tree hoặc rollout theo release |
| Nguy cơ | Relative imports, build dependency graphs | Quên đổi version dẫn đến stale cache |

## 8. Chương trình Spring Boot 3.5 + Thymeleaf minh họa đầy đủ

Ví dụ gồm application Java 17, Thymeleaf template, một CSS, properties và integration tests. Spring Boot quản lý static resource handler, không dùng bean resource handler tùy chỉnh trong ví dụ này.

### 8.1. Cấu trúc thư mục

```text
resource-chain-demo/
├─ build.gradle
└─ src/
   ├─ main/
   │  ├─ java/demo/resource/ResourceChainApplication.java
   │  └─ resources/
   │     ├─ application.properties
   │     ├─ static/css/site.css
   │     └─ templates/home.html
   └─ test/
      └─ java/demo/resource/ResourceChainApplicationTests.java
```

### 8.2. Gradle dependencies

Với project đã khai báo Boot 3.5 plugin, repositories, Java 17 toolchain và dependency management, thêm fragment:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-thymeleaf'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Đây là **fragment `build.gradle`**, không phải toàn bộ file build. Nếu dùng Maven, thêm các starter tương ứng qua Spring Boot BOM.

### 8.3. Properties

Tạo `src/main/resources/application.properties`:

```properties
spring.web.resources.chain.strategy.content.enabled=true
spring.web.resources.chain.strategy.content.paths=/**
```

Không khai báo thêm `@EnableWebMvc` hoặc `WebMvcConfigurer` cho cùng resource pattern. Khi dùng Thymeleaf, Boot auto-configure URL rewriting tương ứng khi điều kiện thích hợp.

### 8.4. Java application và controller

Tạo `src/main/java/demo/resource/ResourceChainApplication.java`:

```java
package demo.resource;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;

@SpringBootApplication
public class ResourceChainApplication {
    public static void main(String[] args) {
        SpringApplication.run(ResourceChainApplication.class, args);
    }
}

@Controller
class HomeController {
    @GetMapping("/")
    String home() {
        return "home";
    }
}
```

**Một file Java hợp lệ:** chỉ `ResourceChainApplication` là public; controller package-private được Boot component scan phát hiện. `@Controller` trả tên view `home`, không trả trực tiếp text/JSON như `@RestController`.

### 8.5. CSS thật

Tạo `src/main/resources/static/css/site.css`:

```css
:root {
  color-scheme: light;
}

body {
  font-family: system-ui, sans-serif;
  margin: 2rem;
  color: #214e34;
}

h1 {
  font-size: 1.8rem;
}
```

Nội dung này là dữ liệu demo. MD5 trong URL phụ thuộc **đúng bytes/line endings** của file khi đóng gói.

### 8.6. Template Thymeleaf

Tạo `src/main/resources/templates/home.html`:

```html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Resource Chain Demo</title>
  <link rel="stylesheet" th:href="@{/css/site.css}">
</head>
<body>
  <h1>Content fingerprint trong Spring MVC</h1>
  <p>Mở DevTools Network để xem CSS URL có hash.</p>
</body>
</html>
```

`th:href="@{/css/site.css}"` là URL logic. Khi Thymeleaf + `ResourceUrlEncodingFilter` + resource chain cùng hoạt động, HTML render cho browser có dạng:

```html
<link rel="stylesheet"
      href="/css/site-0123456789abcdef0123456789abcdef.css">
```

Đây là **minh họa format**, không phải hash thực của CSS trên. Phải lấy versioned URL từ HTML runtime; không hardcode hash vào HTML gốc.

### 8.7. Chạy thử HTTP

```bash
./gradlew bootRun

curl -i 'http://localhost:8080/'
curl -i 'http://localhost:8080/css/site.css'
```

HTTP đầu tiên thường trả 200 `text/html`, HTML có `href` versioned. HTTP thứ hai yêu cầu URL logic, thường trả 200 `text/css`. Sau đó copy đúng public CSS URL từ HTML vào curl, ví dụ:

```bash
# Thay 32 ký tự hex bằng giá trị thực tế từ HTML response.
curl -i 'http://localhost:8080/css/site-0123456789abcdef0123456789abcdef.css'
```

Dòng trên có hash giả, nên **không cam kết 200**; để thành công phải dùng URL runtime thực tế. Header như `Cache-Control`, `ETag`, `Last-Modified` phụ thuộc handler/cache config; đừng tự coi bật fingerprint là đã đặt caching policy một năm.

## 9. Kiểm thử integration qua Servlet container thật

Một unit test gọi `VersionResourceResolver` riêng có thể kiểm tra hash nhưng **không chứng minh HTML rendering, URL filter và Servlet resource handler cùng làm việc**. Dùng `@SpringBootTest(RANDOM_PORT)` để gửi HTTP qua embedded server.

Tạo `src/test/java/demo/resource/ResourceChainApplicationTests.java`:

```java
package demo.resource;

import java.util.regex.Matcher;
import java.util.regex.Pattern;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class ResourceChainApplicationTests {

    private static final Pattern VERSIONED_CSS =
            Pattern.compile("href=\"(/css/site-[0-9a-f]{32}\\.css)\"");

    @Autowired
    TestRestTemplate http;

    @Test
    void templateLinksVersionedCssWhichCanBeFetched() {
        ResponseEntity<String> page =
                http.getForEntity("/", String.class);

        assertEquals(HttpStatus.OK, page.getStatusCode());
        String html = page.getBody();
        assertNotNull(html);

        Matcher matcher = VERSIONED_CSS.matcher(html);
        assertTrue(matcher.find(), "Expected versioned CSS link");

        ResponseEntity<String> css =
                http.getForEntity(matcher.group(1), String.class);

        assertEquals(HttpStatus.OK, css.getStatusCode());
        assertNotNull(css.getBody());
        assertTrue(css.getBody().contains("font-family:"));
    }

    @Test
    void unversionedLogicalUrlStillWorksInThisDemo() {
        ResponseEntity<String> css =
                http.getForEntity("/css/site.css", String.class);

        assertEquals(HttpStatus.OK, css.getStatusCode());
        assertNotNull(css.getBody());
        assertTrue(css.getBody().contains("color-scheme:"));
    }

    @Test
    void incorrectHashDoesNotResolve() {
        String badPath =
                "/css/site-00000000000000000000000000000000.css";

        ResponseEntity<String> css =
                http.getForEntity(badPath, String.class);

        assertEquals(HttpStatus.NOT_FOUND, css.getStatusCode());
    }
}
```

Chạy:

```bash
./gradlew test
```

Ba test được **thiết kế để pass** với project/baseline tương ứng; đây là kỳ vọng sau khi rà soát, **chưa phải kết quả Gradle thực thi**. Test kiểm tra hình thức hash gồm 32 hex thay vì hardcode một hash. Nếu deployment có `server.servlet.context-path=/shop` hoặc Security custom, cập nhật pattern/HTTP paths và quyền truy cập tương ứng.

Để kiểm tra thay đổi assets qua hai release, lấy URL A từ build A, chỉnh bytes CSS rồi build B và lấy URL B; assert URL khác, B trả nội dung mới. Không sửa static file runtime trên cùng một JAR rồi dựa vào chain cache để tự refresh.

## 10. Java config khi cần ResourceHandlerRegistry riêng

Phần này là **phương án thay thế** cho tự cấu hình Boot của phần 8, không phải code cần thêm vào demo đó.

Trong app dùng Spring MVC `WebMvcConfigurer` có thể cấu hình một resource handler riêng cho `/assets/**`:

```java
package demo.resource;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.ResourceHandlerRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;
import org.springframework.web.servlet.resource.VersionResourceResolver;

@Configuration
class AssetConfig implements WebMvcConfigurer {
    @Override
    public void addResourceHandlers(ResourceHandlerRegistry registry) {
        registry.addResourceHandler("/assets/**")
                .addResourceLocations("classpath:/static/assets/")
                .resourceChain(true)
                .addResolver(new VersionResourceResolver()
                        .addContentVersionStrategy("/**"));
    }
}
```

Đặt file ở project có directory `src/main/resources/static/assets/`. File `app.css` trong đó có logical URL `/assets/app.css` và public versioned URL `/assets/app-<hash>.css`. `resourceChain(true)` bật caching resolver chain; `VersionResourceResolver` thực hiện versioning; Spring cung cấp cơ chế lookup resource gốc theo locations.

**Lưu ý cấu hình URL:** nếu cùng app vẫn có default Boot static handler `/**` và một custom handler `/assets/**`, phải xác minh path mapping cụ thể được chọn; đừng cấu hình hai bộ version strategies xung đột.

### 10.1. CSS link rewriting

Nếu custom chain cần rewrite `@import` hoặc `url(...)` trong CSS và chưa có transformer tương ứng:

```java
registry.addResourceHandler("/assets/**")
        .addResourceLocations("classpath:/static/assets/")
        .resourceChain(true)
        .addResolver(new VersionResourceResolver()
                .addContentVersionStrategy("/**"))
        .addTransformer(new CssLinkResourceTransformer());
```

Đây là **method fragment**, cần import `org.springframework.web.servlet.resource.CssLinkResourceTransformer`. Test CSS response thực tế, không thêm trùng transformer nếu chain đã tự đăng ký nó.

### 10.2. Kết hợp encoded resolver

Khi có precompressed assets gzip/brotli được tạo bởi build:

```java
registry.addResourceHandler("/assets/**")
        .addResourceLocations("classpath:/static/assets/")
        .resourceChain(true)
        .addResolver(new EncodedResourceResolver())
        .addResolver(new VersionResourceResolver()
                .addContentVersionStrategy("/**"));
```

Đây là **method fragment**, cần import `EncodedResourceResolver`. Thứ tự **Encoded trước Version** là điều quan trọng Spring docs nêu để content fingerprint ổn định với tệp chưa nén. Phải có tệp `.gz`/`.br` thực tế và test `Accept-Encoding`, `Content-Encoding`, `Vary` nếu muốn chứng minh khả năng phục vụ compressed variants. Thêm resolver không tự tạo file nén.

## 11. ResourceUrlProvider và ResourceUrlEncodingFilter

### ResourceUrlProvider

Spring MVC cung cấp `ResourceUrlProvider` làm API xây URL từ handlers và resolver chain:

```java
@Controller
class AssetInfoController {
    private final ResourceUrlProvider resourceUrls;

    AssetInfoController(ResourceUrlProvider resourceUrls) {
        this.resourceUrls = resourceUrls;
    }

    @GetMapping("/asset-info")
    String show(Model model) {
        String publicUrl =
                resourceUrls.getForLookupPath("/css/site.css");
        model.addAttribute("cssUrl", publicUrl);
        return "asset-info";
    }
}
```

Đây là **class fragment**, cần imports cho `@Controller`, `@GetMapping`, `Model` và `ResourceUrlProvider`; template `asset-info` phải có trong project. Trả về có thể là versioned path hoặc `null` khi resource lookup thất bại. `getForLookupPath` nhận **MVC lookup path**, không phải URL Internet có host, và có thể cần xử lý context path/public CDN base theo môi trường.

### ResourceUrlEncodingFilter

Class `org.springframework.web.servlet.resource.ResourceUrlEncodingFilter` wrap response để các view/helper sử dụng `HttpServletResponse#encodeURL` có thể đưa resource version vào URL trong lúc render.

- Với Spring Boot 3.5, Thymeleaf/FreeMarker thường được Boot auto-configure filter này khi có resource chain thích hợp.
- Với JSP, Spring Boot docs hướng dẫn đăng ký filter theo cách thủ công.
- Với static HTML và client-side JS dựng chuỗi URL, filter **không tự tìm/thay mọi text**.
- Nếu cần output URL ở một API/JSON manifest, gọi provider hoặc dùng build asset manifest.

Ví dụ cấu hình riêng cho JSP:

```java
@Configuration
class ResourceUrlFilterConfig {
    @Bean
    ResourceUrlEncodingFilter resourceUrlEncodingFilter() {
        return new ResourceUrlEncodingFilter();
    }
}
```

Đây là fragment cần imports `Configuration`, `Bean` và `ResourceUrlEncodingFilter`. **Đừng thêm bean này vào demo Thymeleaf đã có filter auto-configured** chỉ vì tưởng mỗi ứng dụng phải tự tạo.

## 12. HTTP cache: resource fingerprint không tự đặt Cache-Control

`ContentVersionStrategy` thay đổi URL dựa trên content; `Cache-Control` thay đổi cách browser/CDN cache response. Đây là hai thao tác **bổ trợ nhưng độc lập**.

| Cơ chế | Tác dụng |
| --- | --- |
| Fingerprinted path | Cache key khác khi nội dung asset thay đổi |
| `Cache-Control: max-age` | Freshness lifetime của response |
| `ETag` / `If-None-Match` | Conditional request nếu HTTP handler có ETag |
| `Last-Modified` / `If-Modified-Since` | Conditional request theo timestamp tài nguyên |
| `304 Not Modified` | Cho phép dùng cached representation sau revalidation |
| `Cache-Control: immutable` | Thông báo asset URL sẽ không đổi representation trong thời hạn thích hợp |
| CDN cache | Tầng cache bên ngoài app; cần chú ý key, purge và version retention |

Java MVC resource handler có thể cấu hình:

```java
registry.addResourceHandler("/assets/**")
        .addResourceLocations("classpath:/static/assets/")
        .setCacheControl(
                CacheControl.maxAge(java.time.Duration.ofDays(365)))
        .resourceChain(true)
        .addResolver(new VersionResourceResolver()
                .addContentVersionStrategy("/**"));
```

Fragment cần import `CacheControl`. **Nguy cơ:** resource handler này cũng có thể phục vụ URL logic `/assets/app.css` không version, nhưng `max-age=365d` sẽ áp lên response đó nếu không phân biệt. Một URL không đổi nhưng content đổi là recipe cho stale cache. Với production cần chia policies giữa URLs versioned và unversioned (hoặc giới hạn truy cập/cache của unversioned) và assert headers cho cả hai.

Property Boot có thể dùng:

```properties
spring.web.resources.cache.cachecontrol.max-age=30d
spring.web.resources.chain.cache=true
```

Cái đầu ảnh hưởng **HTTP headers** của resource handler; cái sau ảnh hưởng **resource resolution cache** trong app. Không bật max-age lớn cho toàn bộ static resources nếu một số entry points hoặc unversioned URLs còn cần revalidate thường xuyên.

### HTML document nên được cập nhật kịp thời

Chiến lược thực tế:

```text
HTML:
  Cache-Control: no-cache (có thể lưu, phải revalidate)
  hoặc TTL ngắn phù hợp sản phẩm

Versioned CSS/JS:
  Cache-Control: public, max-age=31536000, immutable
  chỉ khi URL đại diện cho bytes bất biến và assets cũ còn sẵn
```

Đó là **khuyến nghị kiến trúc**, không phải headers tự sinh bởi resource version resolver. Nếu HTML vẫn cache một tháng, người dùng có thể tiếp tục dùng asset URL từ release cũ dù release mới đã deploy.

## 13. Rolling deployment và asset retention — lý do 404 sau nâng cấp

Giả sử hai server đang phục vụ hai release:

```text
Node A: site.css -> hash AAA
Node B: site.css -> hash BBB

HTML từ A tham chiếu /css/site-AAA.css
Request asset đến B
B chỉ có bytes tương ứng hash BBB
=> VersionResourceResolver không xác nhận hash AAA
=> có thể trả 404
```

Đặc biệt nguy hiểm khi rolling update/blue-green deployment và client vẫn giữ HTML cũ. Resource chain của từng app instance **không phải kho lưu mọi phiên bản đã phát hành**.

Giải pháp:

- Giữ assets của nhiều release trên **shared CDN/object storage** đủ lâu cho rollback/transition.
- Build/đóng gói directories versioned hoặc manifest có retention; không chỉ ghi đè static files cũ.
- Đồng bộ HTML rollout với asset availability.
- Áp dụng fixed release prefix khi nhóm tài nguyên cần deploy nguyên cây phụ thuộc.
- Theo dõi 404 của static URLs, đặc biệt hash từ release trước.
- Không purge CDN versioned assets quá sớm sau rollout.

URL content-hash chỉ hữu ích cho long cache nếu **cùng URL luôn biểu diễn cùng bytes** và origin có thể phục vụ nó khi còn client cần.

## 14. JavaScript module imports và source maps

Ví dụ JS module:

```javascript
// main.js
import { greet } from "./util.js";
greet();
```

Nếu HTML tham chiếu `main-<hash>.js` thì relative import `./util.js` trong JavaScript **không bảo đảm** tự được resource chain rewrite. `CssLinkResourceTransformer` chỉ xử lý CSS `@import`/`url()`, không phân tích ES module syntax.

Các phương án:

1. **Fixed version prefix** cho toàn bộ cây JS lib/module nếu relative paths cần giữ nguyên.
2. **Bundler** như Vite, webpack hoặc Rollup xuất files có hashes và rewrite import references, kèm manifest.
3. Custom JS transformer chuyên biệt nếu có lý do mạnh và test parser/build correctness.
4. Giữ unversioned module import paths với caching policy phù hợp, nhưng có trade-off về cache busting.

Source maps `.map`, web fonts, SVG/images trong CSS, `srcset`, dynamic JS `fetch` hay CDN-hosted assets cũng cần kiểm tra URLs riêng; không giả định ResourceUrlEncodingFilter tự can thiệp mọi trường hợp.

## 15. Bảo mật static content và Spring Security

Static resources thường public, nhưng việc đặt tệp trong `static/` **không tự biến nó thành an toàn để công khai**. Không đưa private key, credentials, database backups, file cấu hình nhạy cảm hoặc các tệp upload có thể thực thi script vào resource locations công khai.

Khi dùng Spring Security, cần allow static paths **đúng phạm vi**:

```java
http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/css/**", "/js/**", "/images/**")
            .permitAll()
        .anyRequest().authenticated());
```

Fragment yêu cầu Spring Security config và imports tương ứng, **không có trong runnable demo**. Với custom mapping `/assets/**`, sửa matchers tương ứng. Không mở `/**` chỉ vì CSS bị 403.

Hash MD5 **không thay thế HTTPS/SRI/CSP hoặc bảo vệ supply-chain**. Nếu tải third-party resources, cần chính sách integrity và CORS phù hợp. Với tệp người dùng upload, cần bảo vệ path traversal, MIME, content disposition và authorization độc lập với resource versioning.

## 16. Sai lầm thường gặp khi cấu hình

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| HTML vẫn chứa `/css/site.css` | Không dùng URL rewriting; link nằm trong static HTML; filter thiếu | Xem HTML source, Thymeleaf và `ResourceUrlProvider` |
| Link versioned có hash nhưng GET 404 | Wrong hash, build bytes khác, URL mapping/scope/CDN sai | Xác minh packaged file và version actual |
| Build mới CSS đổi nhưng hash cũ | Container vẫn dùng JAR cũ, cache lookup/devtools chưa refresh, rebuild chưa copy assets | So sánh bytes trong build artifact |
| Hash khác dù CSS “giống nhau” | Khác whitespace/line endings/encoding/build transforms | So sánh byte-for-byte |
| CSS background/font 404 | CSS internal links không được rewrite hoặc relative path sai | Kiểm tra CSS output/transformer |
| JS module imports lỗi | JS links không được rewrite như CSS | Dùng bundler/fixed strategy |
| CSS GET 200 nhưng browser vẫn cũ | Cache HTML/unversioned paths quá dài | Xem Cache-Control và URLs thật trên Network tab |
| Sau rolling deployment có 404 assets | Node mới không giữ URL hash cũ | Shared asset store/version retention |
| Tất cả assets 401/403 | Security matcher không permit versioned path | Chỉnh whitelist chính xác |
| Dev sửa CSS mà không cập nhật | Resource chain cache hoặc build file chưa refresh | Tắt cache dev, rebuild/restart |
| JSP không đổi links | Thiếu `ResourceUrlEncodingFilter` hoặc URL tag không gọi `encodeURL` | Dùng filter/helper/provider |
| Có gzip/br nhưng hash bất ổn | Encoded/Version resolver order sai | Encoded trước Version |
| Tự thêm `@EnableWebMvc` làm mất tính năng Boot | MVC auto-config bị thay | Dùng `WebMvcConfigurer` |
| Static resources mất sau deploy JAR | Dùng `src/main/webapp`/path sai | Đặt trong classpath static |
| URL có dấu fingerprint nhưng sai host | CDN URL/forwarded proxy/context-path config không đồng bộ | Kiểm tra external base URL |

## 17. Kiểm tra phiên bản Spring Framework và Boot

| Phiên bản thường gặp | Điều cần nhớ |
| --- | --- |
| Spring Framework 5.x / Boot 2.x | Resource chain tồn tại; một số bản Boot rất cũ dùng `spring.resources.*` thay vì `spring.web.resources.*` |
| Spring Framework 6.x / Boot 3.x | Java 17+, properties `spring.web.resources.chain.strategy.content.*` và Thymeleaf URL rewriting như ví dụ |
| Spring Framework 7.x / Boot 4.x | Resource chain và content/fixed strategies vẫn có; Boot 4 reference tiếp tục mô tả `spring.web.resources.chain.strategy.*`; starter/test infrastructure có thể đổi |

Không lấy code từ WebFlux package `org.springframework.web.reactive.resource` khi dùng MVC `org.springframework.web.servlet.resource`. Cùng tên class nhưng API/return types khác.

Khi chuyển Boot 3→4, kiểm tra: Spring MVC starters, handler registration, resource chain, template filter, URL rewriting, cache headers, Security rules, WebJars locator và integration tests. Đừng chỉ kiểm tra project biên dịch; cần HTTP tests thật.

## 18. Checklist triển khai production

- [ ] Xác định đúng static asset owner: Spring MVC, bundler, object storage hay CDN.
- [ ] Chọn một chiến lược versioning chính, tránh thêm hash hai tầng không chủ đích.
- [ ] Content strategy được bật cho đúng patterns/locations, fixed strategy cho assets phù hợp.
- [ ] URL logic từ template/provider được rewrite, không hardcode MD5.
- [ ] Version resolver xác minh inbound URLs, có test hash sai 404.
- [ ] Resource resolver ordering đúng, nhất là Encoded trước Version.
- [ ] CSS internal links, JS modules, fonts, source maps và CDN paths được test.
- [ ] Cache headers cho HTML, versioned và unversioned assets được tách phù hợp.
- [ ] Giữ assets cũ đủ lâu khi rolling deployments, CDN/cache/rollback.
- [ ] Spring Security chỉ permit các static paths cần public.
- [ ] Không đặt secret/config/upload tùy tiện trong static locations.
- [ ] Có integration test HTML→fingerprinted href→asset GET và test sau rebuild.
- [ ] Có monitoring cho cache hit ratio, static 404 và URLs sai hostname/prefix.

## 19. Bài tập thực hành

1. Sửa một ký tự trong `site.css` của ví dụ rồi build lại. URL trong HTML thay đổi không? Vì sao hash phụ thuộc line endings?
2. Phân biệt outbound `ResourceUrlProvider` với inbound `VersionResourceResolver`.
3. Vì sao `@{/css/site.css}` trong Thymeleaf có thể được rewrite nhưng hardcoded href trong `static/index.html` thì không?
4. Khi thêm `spring.web.resources.cache.cachecontrol.max-age=365d`, URL logic `/css/site.css` có rủi ro gì?
5. Nếu HTML release A trỏ `site-A.css` nhưng request được route đến node B chỉ có bytes release B, vì sao có thể 404?
6. Viết test kiểm tra CSS link từ trang HTML theo regex thay vì MD5 cố định.
7. Dùng `CssLinkResourceTransformer` với CSS `url("../images/logo.svg")` rồi kiểm tra response.
8. Dùng Java config có `EncodedResourceResolver` và `VersionResourceResolver`: đăng ký theo thứ tự nào?
9. Khi ES module sử dụng relative import, vì sao FixedVersionStrategy hoặc bundler manifest có thể tốt hơn tự fingerprint filename?
10. Dự án đã dùng Vite tạo `app-<hash>.js`. Có cần thêm Spring VersionResourceResolver nữa không? Phân tích kết quả URL và chi phí.
11. Với Security bật, tại sao versioned `/css/site-<hash>.css` bị 403 dù file tồn tại? Sửa matcher mà không mở API.
12. Tìm sự khác biệt giữa cache chain trong JVM và HTTP cache browser; thiết kế kiểm thử cho mỗi loại.

## 20. Tài liệu chính thức

- [Spring Framework 6.2 — Static Resources](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config/static-resources.html): `ResourceHttpRequestHandler`, resource chain, version resolver và URL provider.
- [Spring Boot 3.5 — Servlet Static Content](https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html): content/fixed strategies, default locations, Thymeleaf/FreeMarker integration.
- [Spring Boot 4 — Servlet Static Content](https://docs.spring.io/spring-boot/4.0/reference/web/servlet.html): resource chain configuration và tương thích thế hệ mới.
- [Spring Framework 6.2 — ContentVersionStrategy](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/servlet/resource/ContentVersionStrategy.html): MD5 fingerprint.
- [Spring Framework 6.2 — VersionResourceResolver](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/servlet/resource/VersionResourceResolver.html): inbound/outbound version paths.
- [Spring Framework 6.2 — ResourceUrlProvider](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/servlet/resource/ResourceUrlProvider.html): sinh public static URL.
- [Spring Framework 6.2 — CssLinkResourceTransformer](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/servlet/resource/CssLinkResourceTransformer.html): CSS @import và url().
- [Spring Framework 6.2 — ResourceUrlEncodingFilter](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/servlet/resource/ResourceUrlEncodingFilter.html): rewrite link trong response encoding.
- [Spring MVC — HTTP Caching](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-caching.html): Cache-Control và conditional requests.
